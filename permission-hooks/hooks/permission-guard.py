#!/usr/bin/env python3
"""PreToolUse hook that guards against dangerous operations.

For Bash: checks commands against 8 categories of dangerous patterns, a
worktree-destruction stage that asks git what a restore would cost, plus an
out-of-project path guard.

For Read/Edit/Write: checks file paths against sensitive file patterns.

Returns permissionDecision: "ask" for any match so the user gets an
approval prompt.

Active only in bypassPermissions mode — the one mode where CC approves
everything and this hook is the sole safety net. In every other permission
mode the hook defers (returns no output) so CC's native permission flow
applies; unknown/missing modes fail safe (the guard stays active).

PROJECT_ROOT is embedded at install time via sed. For --global installs
it's empty and falls back to cwd from the hook event.
"""
import bisect
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import namedtuple
from datetime import datetime

PROJECT_ROOT = "{MG_INSTALL_PROJECT_ROOT}"

# ── Optional rule groups ────────────────────────────────────────────────────
# .env files and environment dumps. Disabled by default: reading and writing
# .env is routine work in this setup, so the ask-per-call cost outweighs the
# guard. Flip to True and reinstall to restore both the file patterns and the
# printenv/env dump rules. The tests gate on this same constant.
ENV_PROTECTION = False

_ENV_RULES = [
    # Unlike every other category rule this one matches an operand (the
    # redirect target) rather than a command verb, so check_command's quote
    # masking hides a quoted target: `echo x > "cfg/.env"` does not match.
    # Unquoted targets — the common form — still do, and the write itself
    # still reaches the out-of-project guard, which recovers quoted redirect
    # targets from the original string (see _candidate_write_targets).
    (r">\s*\S*\.env\b", "writing .env file"),
    (r"\bprintenv\b", "environment dump"),
    (r"\benv\s*($|[|;>])", "environment dump"),
]

_ENV_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.env(?!\.example|\.template|\.sample|\.test)(\b|$)"), ".env file"),
]

# PostgreSQL password file. Disabled by default for the same reason as
# ENV_PROTECTION: reading ~/.pgpass — and inspecting its mtime, which the
# path-based scan cannot tell apart from a read — is routine work in this
# setup, so the ask-per-call cost outweighs the guard. Flip to True and
# reinstall to restore it. Writes are unaffected: a redirect into ~/.pgpass
# still asks via the out-of-project home-directory guard. SSH keys, .netrc,
# .my.cnf and the rest of SENSITIVE_FILE_PATTERNS stay gated. The tests gate
# on this same constant.
PGPASS_PROTECTION = False

_PGPASS_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.pgpass$"), "PostgreSQL password file"),
]

# ── Shell words ─────────────────────────────────────────────────────────────
# Several rules read a command's own words: git's options, and the arguments
# of push, branch, tag, reset, rm, curl and the other _cmd_arg rules. A `.*`
# there ran on into the next command: `git push origin v6 && git log
# main..build-f-crawl` asked as a force push, because `push\s+.*-f\b` read past
# the `&&` and took the `-f` inside a branch name for the flag.
#
# A word splits at a space, tab or newline, as bash splits it, and the command
# ends at `;`, `|`, `&` or a paren. Within a word:
#   - a redirect belongs to the command: `2>&1`, `&>log`, `>|log`, `<<<`.
#   - a substitution is one piece: `$(…)`, `<(…)`, `>(…)` and backticks, with
#     parens nested two deep for `$((…))`. Its separators do not end the
#     command, so `"$(git branch | head -1)" --force` is still read, and its
#     words are not the command's, so the `+` of `v$(date +%Y)` is not a
#     refspec. A command inside one is read where it starts, like any other.
#   - a quoted span without whitespace is one piece too. check_command masks
#     quotes to filler, except in a command that nests a shell. There the text
#     stays as written, and `-o 'a;b' --force` must not end at the `;`. A span
#     with whitespace is left alone, because there a command often starts
#     inside the quotes: the first quote it meets closes them, and pairing
#     that quote with the next one would hide `--force` in
#     `eval "git push x" --force "y"`.
#   - a backslash takes the next character with it, so `\;` does not end the
#     command.
# Each piece has one reading and every loop is possessive, so nothing
# backtracks. A quote or `$` that opens nothing is an ordinary character.
_SUBST = r"(?:[$<>]\((?:[^()]++|\((?:[^()]++|\([^()]*+\))*+\))*+\)|`[^`]*+`)"
_WORD = (
    r"(?:" + _SUBST
    + r"""|'[^' \t\n]*+'|"(?:[^" \t\n\\]++|\\.)*+"|[^ \t\n;|&<>()`\\$'"]++|\\.|[$'"]"""
    + r"|>[&|]?+|<&?+|&>)++"
)

# The start of a word, up to where another command can begin inside it: plain
# characters and escapes, but no paren or backtick, so never inside a
# substitution. `x/git`, `\git` and `$x/git` get there; `$(git` does not. A
# backslash right before the name escapes its first letter, and bash still
# runs git for `\git`.
_TO_CMD = r"(?:[^ \t\n;|&()`\\]|\\.)*?\\?"


def _abbrev(option, shortest):
    """*option*, or any prefix of it down to *shortest*.

    git and getopt_long take any unambiguous prefix of a long option;
    *shortest* is the shortest one no other option of the command shares.
    """
    rest = ""
    for char in reversed(option[len(shortest):]):
        rest = "(?:" + re.escape(char) + rest + ")?+"
    return re.escape(shortest) + rest


# The scan of a command's words stops at a word that starts another such
# command, `x/git push` included. The search starts again there and reads the
# rest, so no word is read twice: scanning each push to the end of its
# command read `git push a git push a …` over and over, quadratic in its
# length.
#
# The restart reads the words between `git` and the subcommand as git's
# options, with the same _WORD. So a command with options (`git -C d push`)
# stops the scan only when none of those words is the argument the rule looks
# for, which the outer command would have read as its own. A command behind a
# paren, a backtick or a substitution does not stop it, since those pieces can
# run past its name and the restart would split the words differently.
#
# That leaves backticks. The same character opens and closes them, so a
# command that starts inside a pair takes the closing backtick for an opening
# one and reads on to the next: `` git push `git push `git push … `` reads to
# the end once per push, quadratic in its length, as it did with `.*`.
# Refusing a push inside a backtick span would fix that, and miss the flag in
# `` git branch `git branch --show-current`-bak -f ``.
def _cmd_arg(head, restart, arg, values=None, end_of_options=False):
    """Pattern for a command that has an argument matching *arg*.

    *head* matches the command up to its arguments. *restart(guard)* matches
    another such command from its name on, checking *guard* on each word it
    reads before the arguments. *values* matches the options whose value is
    the next word; that word is skipped, not read as an argument, so the
    `-refname` of `git branch --sort -refname` is not an -f. With
    *end_of_options*, a `--` word ends the scan: what follows is operands, so
    `rm -- -r` removes a file named `-r`.

    bash drops a backslash in front of the argument, so `\\--force` is
    `--force`. A redirect may follow the head with no space, as in
    `git push>log --force`.
    """
    arg = r"\\?(?:" + arg + r")"
    another = _TO_CMD + restart(r"(?!" + arg + r")") + r"(?=[ \t<>]|&>)"
    stop = r"|--(?![^ \t\n;|&<>()])" if end_of_options else ""
    skip = r"(?!" + arg + r"|" + another + stop + r")"
    word = skip + _WORD
    if values:
        # A value may look like the argument; it only has to not start
        # another command.
        word = (skip + r"(?:(?:" + values + r")[ \t]++(?!" + another + r")" + _WORD
                + r"|" + _WORD + r")")
    return (
        head + r"(?:(?=[<>]|&>)" + _WORD + r")?+"
        r"(?:[ \t]++" + word + r")*+[ \t]++" + arg
    )


# ── git's own options ───────────────────────────────────────────────────────
# git takes options of its own ahead of the subcommand: `git -C <dir> reset
# --hard`, `git -c k=v rebase …`, `git --no-pager push --force`. Every git rule
# starts with _GIT, so none of them can be stepped around that way. The options
# that take a separate value swallow it, so the value is never read as the
# subcommand. Only option words are consumed: in `git log --grep reset` the
# subcommand is `log`, and no rule reads `reset` there.
#
# A value is one _WORD. With `\S+`, the value of
# `git -C "$(git rev-parse --show-toplevel)" push --force` ended at the first
# space, `rev-parse` read as the subcommand, and no rule asked.
#
# The options are read possessively (`*+`), so each word gets one reading.
# Git gives -c and -C the next word even when it starts with a dash, so the
# first reading is also git's. With backtracking, `-c -c` could be a pair or
# two bare options. `git -c -c -c … x` had exponentially many readings to try
# before the match failed: 26 of them took most of a second, and every step
# added about 60%.
#
# The scan also stops at a word that ends in a `git` the search can start
# from again: the value of `-c git`, or of `-C ~/src/git`. The search reads the
# same options from that `git`, so no rule misses a match. Without the stop,
# every `git` in `git -c git -c git …` read all the options after it once
# more, quadratic in the length: 5,000 of them took 40 seconds. _TO_CMD keeps
# the stop out of substitutions, so a match that starts at such a `git` always
# has the outer command in front of it (`git -C ~/src/`), and the worktree
# exemption, which wants the git command at the start of its command, asks.
_GIT_STOP = r"(?!" + _TO_CMD + r"\bgit(?![^ \t\n]))"


def _git_options(guard=""):
    """git's own options, each option and value word checked by *guard*."""
    guard = _GIT_STOP + guard
    return (
        r"(?:[ \t]++" + guard + r"(?:-[Cc][ \t]++" + guard + _WORD
        + r"|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source)[ \t]++(?!-)"
        + guard + _WORD + r"|-" + _WORD + r"))*+"
    )


_GIT = r"\bgit" + _git_options() + r"[ \t]++"


def _git_arg(sub, arg, values=None):
    """Pattern for a `git <sub>` that has an argument matching *arg*."""
    return _cmd_arg(
        _GIT + sub,
        lambda guard: r"\bgit" + _git_options(guard) + r"[ \t]++" + sub,
        arg, values,
    )


# ── git push ────────────────────────────────────────────────────────────────
# Options whose value is the next word.
_PUSH_VALUES = r"-o|--(?:push-option|repo|receive-pack|exec)"

# A force push is spelled three ways:
#   - -f, also inside a bundle (-uf). A bundle's -o takes the rest of it as its
#     value, so the f must come before any o: -of is not a force push.
#   - any --force option. That covers --force-with-lease[=…] and the
#     abbreviations git accepts (--force-w); anything shorter than --force is
#     ambiguous, and git refuses it.
#   - a refspec with a leading `+`, which forces just that ref (`git push
#     origin +main`).
_GIT_FORCE_PUSH = _git_arg(
    "push",
    r"(?:(?:-(?=[A-Za-np-z0-9]*f)[A-Za-z0-9]++|--force(?:-[\w-]*+)?(?:=\S*+)?)(?![\w-])"
    r"|\+[^ \t\n;|&])",
    _PUSH_VALUES,
)

# --mirror force-updates every remote ref and deletes the ones gone locally.
_GIT_MIRROR_PUSH = _git_arg("push", _abbrev("--mirror", "--m") + r"(?![\w-])", _PUSH_VALUES)

# Deleting remote refs: -d, also inside a bundle, or --delete (down to --de,
# since --d could be --dry-run); a refspec with no source, `:feature`, but
# not the bare `:` that pushes matching branches; and --prune, which deletes
# every remote branch that no local one matches.
_GIT_DELETE_PUSH = _git_arg(
    "push",
    r"(?:-(?=[A-Za-np-z0-9]*d)[A-Za-z0-9]++|" + _abbrev("--delete", "--de") + r")(?![\w-])",
    _PUSH_VALUES,
)
_GIT_COLON_DELETE_PUSH = _git_arg("push", r":[^ \t\n;|&<>()]", _PUSH_VALUES)
_GIT_PRUNE_PUSH = _git_arg("push", _abbrev("--prune", "--pru") + r"(?![\w-])", _PUSH_VALUES)

_GIT_TAGS_PUSH = _git_arg("push", _abbrev("--tags", "--ta") + r"(?![\w-])", _PUSH_VALUES)

# ── git branch and tag ──────────────────────────────────────────────────────
_BRANCH_VALUES = (
    r"-u|--(?:set-upstream-to|sort|format|contains|no-contains|merged|no-merged|points-at)"
)

# -f resets an existing branch; -M and -C overwrite the one they name. In a
# bundle they must come before any t or u, which take the rest of the bundle
# as their value: -uf sets the upstream to `f`. --force takes the
# abbreviations down to --forc, since --for could be --format.
_GIT_FORCED_BRANCH = _git_arg(
    "branch",
    r"(?:-(?=[A-Za-sv-z]*[fMC])[A-Za-z]++|" + _abbrev("--force", "--forc") + r")(?![\w-])",
    _BRANCH_VALUES,
)

# -d deletes a merged branch and -D any branch, in a bundle under the same
# rule as above (-dr, -rD). --delete takes every abbreviation down to --d,
# which no other branch option starts with.
_GIT_BRANCH_DELETE = _git_arg(
    "branch",
    r"(?:-(?=[A-Za-sv-z]*[dD])[A-Za-z]++|" + _abbrev("--delete", "--d") + r")(?![\w-])",
    _BRANCH_VALUES,
)

# The same for tags: -d in a bundle before -m, -F, -u or -n, which take the
# rest of it as their value, or --delete down to --d.
_TAG_VALUES = (
    r"-[mFu]|--(?:message|file|local-user|cleanup|sort|format|contains|no-contains"
    r"|merged|no-merged|points-at)"
)
_GIT_TAG_DELETE = _git_arg(
    "tag",
    r"(?:-(?=[A-EG-Za-lo-tv-z]*d)[A-Za-z]++|" + _abbrev("--delete", "--d") + r")(?![\w-])",
    _TAG_VALUES,
)

# ── git reset, remote, submodule ────────────────────────────────────────────
# --hard anywhere in the reset (`git reset -q --hard`, `git reset HEAD~1
# --hard`), down to --h, which no other reset option starts with.
_GIT_RESET_HARD = _git_arg("reset", _abbrev("--hard", "--h") + r"(?![\w-])",
                           r"--pathspec-from-file")

# `git remote` takes -v before its subcommand. Every subcommand that changes
# a remote asks: add, remove, set-url, rename and set-head, and prune, which
# deletes the remote-tracking branches the remote no longer has, as
# `update -p` does on the way.
_GIT_REMOTE = r"remote(?:[ \t]++(?:-v|" + _abbrev("--verbose", "--v") + r")(?![\w-]))*+"
_GIT_REMOTE_WRITE = (
    _GIT + _GIT_REMOTE
    + r"[ \t]++(?:add|remove|rm|set-url|rename|prune|set-head)(?![\w-])"
    + r"|" + _git_arg(_GIT_REMOTE + r"[ \t]++update",
                      r"(?:-p|" + _abbrev("--prune", "--p") + r")(?![\w-])")
)

# `git submodule` takes --quiet and --cached before its subcommand.
_GIT_SUBMODULE_WRITE = (
    _GIT + r"submodule(?:[ \t]++(?:-q|--quiet|--cached)(?![\w-]))*+"
    r"[ \t]++(?:add|deinit)(?![\w-])"
)

# ── git config ──────────────────────────────────────────────────────────────
# `git config` needs more than one pattern's worth of care: scope and format
# options sit between the subcommand and the operands, a key with no value is
# a read, and both spellings of the command are in the wild (`git config
# --unset x` and the newer `git config unset x`). Matching write intent
# directly beats listing read flags to exempt — the old exemption list ended
# in a bare `--`, which quietly spared every long option including
# `git config --global user.name "x"`.

# Options that may precede the operands. Consumed so they can't hide a write.
# The four that take a value swallow it too, whether attached or separate.
_GIT_CONFIG_OPTS = (
    r"(?:\s+(?:--(?:global|local|system|worktree|includes|no-includes|null"
    r"|name-only|show-origin|show-scope|fixed-value)"
    r"|--(?:file|blob|type|default)(?:=\S+|\s+\S+)"
    r"|-f\s+\S+|-z))*"
)

# A write is a mutating flag, a mutating subcommand, or a key with a value
# after it. The value cannot be a redirect or a shell terminator — those end
# the command, leaving a bare-key read. The key must carry its section dot:
# git rejects a write to a sectionless key ("key does not contain a section"),
# and the rules scan the raw command string, so an undotted key would flag
# ordinary prose containing the words — `echo "=== git config rule ==="`. The
# middle of the key stays permissive for URL subsections
# (`url.https://github.com/.insteadOf`) but must end on a key character, so a
# trailing-dot abbreviation ("git config e.g. foo") is not a write either.
_GIT_CONFIG_WRITE = (
    _GIT + r"config(?!\s+(?:get|list)\b)"
    + _GIT_CONFIG_OPTS
    + r"\s+(?:"
    r"--(?:add|unset|unset-all|replace-all|rename-section|remove-section|edit)\b"
    r"|-e\b"
    r"|(?:set|unset|edit|rename-section|remove-section)\b"
    r"|[\w-]+\.\S*[\w-][ \t]+[^\s)`;&|<>]"
    r")"
)

# ── Command position ────────────────────────────────────────────────────────
# Words like "service" and "kill" are common in prose, paths and regex
# alternations. Anchoring such a word to a place where bash starts a command
# keeps the text cases quiet; quoted text is masked before the rules read it,
# so the `| service` in `git commit -m "a | service"` is filler. Anchored at
# only the start, `;`, `&` and a newline, these commands ran unasked from
# everywhere else a command starts. _CMD_START takes in:
#
#   - the start of the string, `;`, `&`, a newline, a pipe, `||`, a subshell,
#     a group, a command or process substitution: `| kill`, `(ln …)`,
#     `{ kill …; }`, `$(dd …)`, `` `kill …` ``, `<(kill …)`
#   - after a reserved word or an assignment: `if kill …`, `! kill`,
#     `FOO=1 kill …`
#   - behind a command that runs its arguments: `xargs kill`, `timeout 30
#     kill`, `find … -exec kill`, env, nohup, nice and the rest of _RUNNERS.
#     Their options are followed as flags, numbers and `{}`; one that takes a
#     word (`timeout -s KILL 5 …`) ends the prefix, so that form is not seen.
#     `command` takes only -p: `command -v kill` asks where it is, it does not
#     run it.
#
# A `{` opens a group only with a space behind it, so brace expansion
# (`docs/{kill,ln}.md`) and `${kill}` stay text.
#
# The anchor runs at every `"`, `(` and `|` of every Bash call, once per rule
# that uses it, so no two of its alternatives may match the same token, and
# each token is taken atomically: with `\w+=\S*` both an env argument and an
# assignment of its own, `env A=1 A=1 …` went quadratic and `nice 1=1 1=1 …`
# exponential. An assignment starts with a letter or `_`, as bash's do, a
# number argument holds no `=`, and an assignment value is read to at most
# 512 characters, so a quote-dense line with no spaces cannot make every
# anchor rescan the rest of it. A longer value ends the prefix.
_RUNNERS = r"(?:env|nohup|setsid|exec|eval|time|nice|stdbuf|timeout|xargs|watch)"
_RUNNER_ARGS = r"(?:[ \t]+(?:-\S*+|\d[^\s=]*+(?!=)|\{\}))*+"
_CMD_PREFIX = (
    r"(?>(?:if|then|elif|else|do|while|until|!"
    r"|[A-Za-z_]\w*+=\S{0,512}+"
    r"|command(?:[ \t]+-p)?"
    r"|" + _RUNNERS + _RUNNER_ARGS
    + r")[ \t]+)*+"
)
_CMD_AT = r"(?:^|[;&|\n(`]|(?<!\$)\{(?=\s)|[ \t]-(?:exec|execdir|ok|okdir)(?=[ \t]))[ \t]*+"
_CMD_START = _CMD_AT + _CMD_PREFIX

# systemctl also starts where a nested shell's string does, which
# check_command reads unmasked: `bash -c "systemctl …"`, `eval 'systemctl …'`.
# Only a quote with the command right behind it counts; a closing quote and a
# space (`grep "x" systemctl.md`) is followed by an argument. The other
# command-position rules leave this out: their words are common in quoted
# prose, and `xargs grep -l "passwd reset"` is read unmasked because of the
# xargs.
_CMD_START_OR_QUOTE = r"(?:" + _CMD_AT + r"|[\"'])" + _CMD_PREFIX

# A command called by its path: `/usr/bin/kill`.
_CMD_PATH = r"(?:(?:/[\w.-]+)*/)?"

# `\brm` also matches the tail of a flag: `-` is not a word character, so
# `docker run --rm` has a word boundary right before the `r`. Put this in front
# of a command word so a flag spelled like the command is not read as a call to
# it. It anchors nothing else, so `xargs rm`, `sudo rm` and `find -exec rm`
# stay in view.
_NOT_FLAG = r"(?<!-)"

# ── systemctl ───────────────────────────────────────────────────────────────
# systemctl is mostly introspection: is-enabled, list-timers, show and friends
# report state and exit. Exempting the single literal `status` asked on every
# one of those, and any global option before the subcommand (`systemctl --user
# status foo`) defeated the exemption altogether.
#
# The read set is small and closed; the write set grows with systemd (freeze,
# thaw, mount-image, …). So name the reads and flag the rest — that keeps a
# subcommand systemd adds tomorrow on the asking side.

# Global options that may sit between `systemctl` and the subcommand. The short
# options that take a separate value swallow it, so the `service` in
# `systemctl -t service list-units` can't be mistaken for a subcommand.
_SYSTEMCTL_OPTS = r"(?:\s+(?:-[HMtpnosP]\s+\S+|--[\w-]+=\S+|--[\w-]+|-[A-Za-z]+))*"

_SYSTEMCTL_READ = (
    r"(?:status|show|show-environment|cat|help|get-default"
    r"|is-active|is-enabled|is-failed|is-system-running"
    r"|list-(?:units|unit-files|sockets|timers|jobs|dependencies|machines"
    r"|paths|automounts))(?![\w-])"
)

# Two negative lookaheads, not one match-the-write pattern: a greedy option
# group followed by a positive match backtracks until the option itself is
# taken for the subcommand, which is how `--user status` would get flagged. A
# lookahead that fails has nothing to backtrack into.
#
# The `word` group marks where the command starts, for _rule_commands.
_SYSTEMCTL_WRITE = (
    _CMD_START_OR_QUOTE
    + r"(?P<word>" + _CMD_PATH + r"systemctl)(?![\w-])"
    # Bare `systemctl [options]`, redirected or not, just lists units.
    + r"(?!" + _SYSTEMCTL_OPTS + r"\s*(?:$|[)\n;&|]|\d*[<>]))"
    + r"(?!" + _SYSTEMCTL_OPTS + r"\s+" + _SYSTEMCTL_READ + r")"
)

# Services any project may start, stop and restart without asking; see the
# Managed systemd units section. Adding one here takes an edit and a reinstall,
# like the rule groups above.
SYSTEMCTL_MANAGED_UNITS = (
    "prefect-server.service",
    "finance-data-worker.service",
    "stock-ranker-worker.service",
)

# ── Arguments of other commands ─────────────────────────────────────────────
# The same word reading as the git rules, through _cmd_arg. These commands
# take no options before their name, so the restart is the name alone.


def _named(name):
    """Head and restart for _cmd_arg: a command called *name*."""
    return name + r"(?![\w-])", lambda _guard: name


# rm -r, -R or --recursive (down to --r) anywhere among its options: GNU rm
# takes options after the operands too, as in `rm build -rf`, until a `--`.
_RECURSIVE_RM = _cmd_arg(
    *_named(_NOT_FLAG + r"\brm"),
    r"(?:-(?=[A-Za-z]*[rR])[A-Za-z]++|" + _abbrev("--recursive", "--r") + r")(?![\w-])",
    end_of_options=True,
)


def _subcommand(name, value_options, subcommands):
    """*name* whose first word after its options is one of *subcommands*.

    *value_options* take the next word as their value, so the value is not
    read as the subcommand. `brew search install` searches; it installs
    nothing.
    """
    return (
        name + r"(?![\w-])(?:[ \t]++(?:" + value_options + r")[ \t]++[^ \t\n;|&]++"
        r"|[ \t]++-[^ \t\n;|&]*+)*+[ \t]++(?:" + subcommands + r")(?![\w-])"
    )


# Installing or removing packages. apt, yum, dnf and brew name it with a
# subcommand after their options (`apt-get -y install`), apk with add and
# del; pacman with an operation flag (-S, -R, -U, also in a bundle such as
# -Syu, but not the -S queries -Ss, -Si, -Sl, -Sg, -Sp).
_PACKAGE_WORDS = r"install|remove|purge|uninstall"
_PACKAGE_CHANGE = (
    _subcommand(r"\b(?:apt-get|apt)", r"-[oct]|--(?:option|config-file|target-release)",
                _PACKAGE_WORDS)
    + r"|" + _subcommand(r"\b(?:yum|dnf)",
                         r"-[cdexR]|--(?:config|repo|repoid|exclude|installroot|releasever"
                         r"|enablerepo|disablerepo)", _PACKAGE_WORDS)
    + r"|" + _subcommand(r"\bbrew", r"(?!)", _PACKAGE_WORDS)
    + r"|" + _subcommand(r"\bapk", r"-[Xp]|--(?:repository|root|keys-dir|cache-dir|arch)",
                         r"add|del")
    + r"|" + _cmd_arg(
        *_named(r"\bpacman"),
        r"(?:-(?=[A-Za-z]*[RU])[A-Za-z]++|-(?=[A-Za-z]*S)(?![A-Za-z]*[silgp])[A-Za-z]++"
        r"|--(?:sync|remove|upgrade))(?![\w-])")
)

# A request that sends data or writes: a POST, PUT, PATCH or DELETE method, or
# a body. curl's short options bundle, and the first one in a bundle that
# takes a value takes the rest of it, so only its flag options may come first:
# -sd sends data, -XGET does not, -sXPOST does. curl sends a body with -d and
# every --data form, --json, -F/--form and -T/--upload-file; wget with
# --post-data, --post-file, --body-data and --body-file, and --data, which
# wget refuses but the rule has always caught.
_HTTP_WRITE_METHOD = r"(?i:post|put|patch|delete)(?![\w-])"
_CURL_FLAGS = r"[#0-46aBfgGIijJklLMnNOpqRsSvVZ]*+"
_HTTP_SUBMIT = (
    _cmd_arg(
        *_named(r"\bcurl"),
        r"-" + _CURL_FLAGS + r"(?:X[ \t]*+" + _HTTP_WRITE_METHOD + r"|[dFT])"
        r"|--request(?:=|[ \t]++)" + _HTTP_WRITE_METHOD
        + r"|--(?:data[\w-]*+|json|form[\w-]*+|upload-file)(?![\w-])",
    )
    + r"|" + _cmd_arg(
        *_named(r"\bwget"),
        r"--(?:post|body)-(?:data|file)(?![\w-])|--data[\w-]*+(?![\w-])"
        r"|--method(?:=|[ \t]++)" + _HTTP_WRITE_METHOD,
    )
)

# `gh api` writes with a POST, PUT, PATCH or DELETE method, or with a field or
# an input body, which make it a POST. Its only flag short option is -i, so
# only that may come first in a bundle.
_GH_API_WRITE = _cmd_arg(
    *_named(r"\bgh[ \t]++api"),
    r"-i*+(?:X[ \t]*+" + _HTTP_WRITE_METHOD + r"|[fF])"
    r"|--method(?:=|[ \t]++)" + _HTTP_WRITE_METHOD
    + r"|--(?:field|raw-field|input)(?![\w-])",
)


def _runs_stdin(name, script_options, stdin_word=r"-"):
    """An interpreter *name* that runs the program on its standard input.

    It does when it is given only options: no script operand, and none of
    *script_options*, which hand it the program another way. *stdin_word*
    names stdin as the program outright. A quote or backtick after the
    options closes the nested shell string the pipeline sits in.
    """
    stdin_word = r"(?:" + stdin_word + r")(?![^ \t\n;|&)])"
    return (
        _CMD_PATH + name + r"(?![\w.-])"
        r"(?:[ \t]++(?!" + script_options + r"|" + stdin_word + r")[-+][^ \t\n;|&)]*+)*+"
        r"(?:[ \t]++" + stdin_word + r"|[ \t]*+(?![^;|&)\n\"'`]))"
    )


# A download run as code. Piped into an interpreter that runs its standard
# input, later in the same pipeline, with `sudo` or `env` in front or not:
# `curl … | tee log | sudo bash`. A pipe may be followed by a newline, and the
# pipeline goes on. `| python3 -m json.tool`, `| python3 -c …`, `| node -e …`
# and `| perl -ne …` read the download as data, so they do not count. Or
# handed to a command as a process or command substitution: `bash <(curl …)`,
# `sh -c "$(curl …)"`, `eval "$(curl …)"`, `. <(curl …)`, where the command
# has to be at a command start (not the `.` of `diff . <(curl …)`). The
# pipeline ends at `;`, `&&`, `||` and a newline; its scan stops at the next
# curl or wget, which reads the rest itself, so it stays linear.
_STDIN_INTERPRETER = (
    r"(?:" + _runs_stdin(r"(?:ba|z|da|k)?sh", r"-[A-Za-z]*c", r"-s?")
    + r"|" + _runs_stdin(r"python[0-9.]*", r"-[A-Za-z]*[cm]")
    + r"|" + _runs_stdin(r"(?:perl|ruby)", r"-[A-Za-z]*[eE]")
    + r"|" + _runs_stdin(r"node", r"-[A-Za-z]*[ep]|--(?:eval|print)")
    + r")"
)
_PIPE_INTO = (
    r"\|&?[ \t\n]*+(?:sudo(?:[ \t]++-\S++)*+[ \t]++"
    r"|env(?:[ \t]++[A-Za-z_]\w*+=\S*+)*+[ \t]++)?" + _STDIN_INTERPRETER
)
_DOWNLOAD = r"\b(?:curl|wget)(?![\w-])"
_PIPE_TO_SHELL = (
    _DOWNLOAD
    + r"(?:(?!" + _DOWNLOAD + r")(?:[^\n;&|]|(?<=[<>])&|&(?=>)"
    + r"|(?!" + _PIPE_INTO + r")\|&?+(?![|&])[ \t\n]*+))*+"
    + _PIPE_INTO
    + r"|" + _CMD_START + r"(?:" + _CMD_PATH
    + r"(?:(?:ba|z|da|k)?sh|python[0-9.]*|perl|ruby|node)|source|\.)(?![\w.-])"
    r"(?:[ \t]++-\S++)*+[ \t]++[\"']?(?:[<$]\(|`)[ \t]*+" + _DOWNLOAD
    # _CMD_START reads eval as a runner and takes it in, so eval stands alone.
    + r"|(?<![\w.-])eval[ \t]++[\"']?(?:\$\(|`)[ \t]*+" + _DOWNLOAD
)

# ── Category definitions ────────────────────────────────────────────────────
# Each category maps to a list of (regex_string, description) tuples.

# The checkout rule carries no exemption on purpose. It used to read
# `git\s+checkout\s+(?!--)`, i.e. it treated the `--` spelling as the benign
# "file restore" case and let it through — which is the wrong way round (see
# the Git worktree destruction section). Every checkout now reaches a guard:
# the pathspec forms are claimed by check_worktree_destruction, which asks git
# whether there is anything to lose and suppresses this rule when there is
# not, and everything else — branch switches, --detach, --force — asks here.
GIT_CHECKOUT_RULE = "git checkout"

# Read by check_linked_worktree_rule, which judges these rules' forms; see the
# Linked worktrees section.
GIT_SWITCH_RULE = "git switch"
GIT_REBASE_RULE = "git rebase (not recovery)"
GIT_STASH_RULE = "git stash destruction"

# Suppressed for local targets by check_local_http; see the Local HTTP targets
# section for what "local" means and why only this one rule is exempted.
HTTP_SUBMIT_RULE = "HTTP data submission"

# Suppressed for a plain `chmod +x` by check_exec_bit_chmod; see the Exec-bit
# chmod section.
PERMISSION_CHANGE_RULE = "permission/ownership change"

# Suppressed for lifecycle calls on SYSTEMCTL_MANAGED_UNITS by
# check_managed_systemctl; see the Managed systemd units section.
SYSTEMCTL_RULE = "systemctl (not a read subcommand)"

CATEGORIES = {
    "Git Branch & History": [
        (_GIT + r"checkout\b", GIT_CHECKOUT_RULE),
        (_GIT + r"switch\b", GIT_SWITCH_RULE),
        (_GIT_BRANCH_DELETE, "branch deletion"),
        (_GIT_FORCED_BRANCH, "forced branch move"),
        (_GIT + r"rebase\s+(?!--abort|--continue|--quit|--skip)", GIT_REBASE_RULE),
        (_GIT_RESET_HARD, "git reset --hard"),
        (_GIT + r"stash\s+(drop|clear)\b", GIT_STASH_RULE),
        (_GIT_TAG_DELETE, "git tag deletion"),
    ],
    "Git Destructive Remote": [
        (_GIT_FORCE_PUSH, "force push"),
        (_GIT_MIRROR_PUSH, "mirror push"),
        (_GIT_DELETE_PUSH, "remote branch deletion"),
        (_GIT_COLON_DELETE_PUSH, "remote branch deletion (colon syntax)"),
        (_GIT_PRUNE_PUSH, "remote branch pruning"),
        (_GIT_TAGS_PUSH, "pushing tags"),
        (_GIT_REMOTE_WRITE, "remote management"),
        (_GIT_CONFIG_WRITE, "git config write"),
        (_GIT_SUBMODULE_WRITE, "submodule management"),
    ],
    "GitHub CLI": [
        (r"\bgh\s+pr\s+(merge|close)\b", "PR merge/close"),
        (r"\bgh\s+repo\s+(create|delete|fork|archive)\b", "repo management"),
        (r"\bgh\s+release\s+(create|delete)\b", "release management"),
        (_GH_API_WRITE, "GitHub API mutation"),
        (r"\bgh\s+auth\b", "GitHub auth"),
        (r"\bgh\s+secret\b", "GitHub secret management"),
    ],
    "Package Publishing": [
        (r"\b(npm|yarn|pnpm)\s+publish\b", "package publish"),
        (r"\b(pip|twine)\s+upload\b", "package upload"),
        (r"\bnpm\s+(adduser|token|login|unpublish)\b", "npm auth/unpublish"),
    ],
    "Infrastructure": [
        (r"\bssh\s", "remote access (ssh)"),
        (r"\bscp\s", "remote file transfer (scp)"),
    ],
    "Destructive Filesystem": [
        (_RECURSIVE_RM, "recursive rm"),
        (r"\b(chmod|chown)\b", PERMISSION_CHANGE_RULE),
        (_CMD_START + _CMD_PATH + r"ln\s+(?!=)(?:-|\S+\s)", "symlink creation"),
        (r"\b(mkfs|mount|umount)\b", "disk operations"),
        (_CMD_START + _CMD_PATH + r"dd\s", "raw disk operations"),
    ],
    "Secrets & Credentials": [
        *(_ENV_RULES if ENV_PROTECTION else []),
        (_HTTP_SUBMIT, HTTP_SUBMIT_RULE),
        (_PIPE_TO_SHELL, "pipe-to-shell"),
    ],
    "System Operations": [
        (r"\bsudo\b", "sudo"),
        (_PACKAGE_CHANGE, "package manager"),
        (r"\bcrontab\s+(?!-l\b)", "crontab modification"),
        (_SYSTEMCTL_WRITE, SYSTEMCTL_RULE),
        # Only where bash starts a command (see _CMD_START), and only with an
        # argument: these words are common in prose and paths ("kill the
        # test", /etc/passwd, "iptables rules").
        (_CMD_START + _CMD_PATH + r"(launchctl|service)\s+\S", "service manager"),
        (_CMD_START + _CMD_PATH + r"(useradd|userdel|usermod|passwd)\s+\S", "user management"),
        (_CMD_START + _CMD_PATH + r"(iptables|ufw)\s+\S", "firewall management"),
        # Behind xargs, kill takes its arguments from stdin.
        (_CMD_START + _CMD_PATH + r"(kill|killall)\s+\S"
         r"|\bxargs(?:[ \t]++(?:-[adEILnPs]|--(?:arg-file|delimiter|eof|replace|max-lines"
         r"|max-args|max-procs|max-chars))[ \t]++\S++|[ \t]++-\S++)*+[ \t]++"
         + _CMD_PATH + r"(?:kill|killall)(?![\w-])",
         "process termination"),
    ],
}

# Compile all rules into a flat list at module load
RULES = []
for category, patterns in CATEGORIES.items():
    for regex_str, description in patterns:
        RULES.append((re.compile(regex_str), description, category))

# Absolute paths that are always safe to reference
SAFE_ABSOLUTE_PATHS = ["/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/tmp"]

# ── Session context (auto-approval via sidecar file with rolling TTL) ──────
# Stage 0 gates the emit-context.py script (human approval required).
# Once approved, the hook writes a sidecar file with a timestamp.
# Subsequent auto-approved tool calls bump the timestamp (rolling TTL).
# The context expires after CONTEXT_TTL_S of inactivity.
_EMIT_SCRIPT_RE = re.compile(r"\bemit-(context|edit-guard)\.py\b")
CONTEXT_TTL_S = 30 * 60  # 30 minutes

# Sidecar filename inside the session dir. Deliberately NOT "context.json":
# the GSD statusline caches its context-window percentage to
# <session-dir>/context.json on every render, which would overwrite the
# sidecar and silently disarm the window (fail-safe — the foreign payload has
# no "command" key — but auto-approval would never stick). Mirrored by
# scripts/auto-approve-session.py.
SIDECAR_FILENAME = "auto-approve.json"

# Pause latch, written by scripts/auto-approve-session.py (usually from another
# session) and cleared only by its `unpause` subcommand. Kept in its own file
# rather than merged into SIDECAR_FILENAME: this hook is a read-only consumer of
# the latch, so a concurrent TTL bump on the auto-approve sidecar can never drop
# a pause request. The latch is sticky on purpose — every guarded call asks for
# as long as it exists, so a whole wave of parallel subagents stops, not just
# whichever one happened to make the next tool call.
PAUSE_FILENAME = "pause.json"

# ── Usage gate ──────────────────────────────────────────────────────────────
# scripts/usage-watch.py publishes one account-wide reading (the daemon owns the
# thresholds and precomputes the verdict, so this hook stays a cheap file read on
# every tool call). A session silences it for the current window with
# `mute-session-limit`, which writes USAGE_MUTE_FILENAME into its session dir.
#
# Fail directions are deliberately opposite. An unreadable or stale reading must
# NOT gate work: a monitoring hiccup blocking every tool call is worse than the
# limit itself, which merely cuts off and resets. An unreadable mute must NOT
# grant silence: a corrupt file that happens to disable a warning is the bad
# direction.
USAGE_FILENAME = "usage.json"                 # account-wide, in the base dir
USAGE_MUTE_FILENAME = "usage-mute.json"       # per session
# Three missed ticks (the daemon's default interval is 10 min).
USAGE_STALE_S = 30 * 60
# Reported reset instants drift ~a minute between reads, so window identity is
# fuzzy — mirrored in scripts/auto-approve-session.py.
USAGE_WINDOW_TOL_MIN = 10

_DEFAULT_SESSION_BASE = "/tmp/claude-code"


def _session_base():
    """Base dir for session sidecars. Overridable so tests never touch the real one."""
    return os.environ.get("MG_SESSION_BASE", _DEFAULT_SESSION_BASE)


def _session_dir(session):
    return os.path.join(_session_base(), f"mg-session-{session}")

# Number of trailing JSONL lines to inspect for recent command invocation.
# Needs to be large enough to span the full slash-command load: <command-name>
# tag + body + attachments (one line each) + last-prompt + assistant thinking/
# tool_use. A /mg: command with many referenced attachments can push the tag
# ~20–40 lines back, so we use a generous window that still excludes ancient
# invocations.
_RECENT_LINES = 200


def _session_id(transcript_path):
    """Derive session ID from transcript path.

    Subagent transcripts live at .../SESSION_UUID/subagents/agent-xxx.jsonl.
    For these, return the parent session UUID so sidecar files are shared.
    """
    if not transcript_path:
        return None
    parts = transcript_path.replace("\\", "/").split("/")
    try:
        sub_idx = parts.index("subagents")
        if sub_idx > 0:
            return parts[sub_idx - 1] or None
    except ValueError:
        pass
    session = os.path.basename(transcript_path)
    if session.endswith(".jsonl"):
        session = session[:-6]
    return session or None


def _write_context_sidecar(transcript_path, command):
    """Write/update session context sidecar file. Best-effort."""
    try:
        session = _session_id(transcript_path)
        if not session:
            return
        session_dir = _session_dir(session)
        os.makedirs(session_dir, exist_ok=True)
        path = os.path.join(session_dir, SIDECAR_FILENAME)
        with open(path, "w") as f:
            json.dump({"command": command, "timestamp_ms": int(time.time() * 1000)}, f)
    except Exception:
        pass


def _update_context_timestamp(transcript_path):
    """Bump sidecar timestamp. Best-effort."""
    try:
        session = _session_id(transcript_path)
        if not session:
            return
        path = os.path.join(_session_dir(session), SIDECAR_FILENAME)
        with open(path) as f:
            data = json.load(f)
        data["timestamp_ms"] = int(time.time() * 1000)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


_RECENT_CMD_RE = re.compile(
    r'<command-name>/mg:'                # slash-command invocation tag
    r'|"skill"\s*:\s*"mg:'               # Skill tool_use input (compact or pretty JSON)
    r'|Launching skill:\s*mg:'           # Skill tool_result body
)


def _emitter_follows_command(transcript_path):
    """Return True if a /mg: command was loaded in the recent transcript tail.

    A /mg: command can reach the LLM through two channels, each leaving a
    different fingerprint in the transcript:

    1. **Slash command** — CC injects a ``<command-name>/mg:...`` tag.
    2. **Skill tool** — CC emits an assistant ``tool_use`` with
       ``"name":"Skill"`` and ``"skill":"mg:..."``, followed by a
       ``tool_result`` whose body is ``Launching skill: mg:...``. No
       ``<command-name>`` tag is produced.

    The emit-context.py call happens some entries later — typically after
    the command body, referenced attachments, last-prompt marker, and any
    assistant thinking. With attachments, that gap can be 20–40 lines, so
    we scan a wide tail (``_RECENT_LINES``) to still catch the marker
    while excluding ancient invocations.

    Note: CC strips YAML frontmatter (including ``allowed-tools:``) before
    writing command content to the transcript, so for slash commands we
    match on the ``<command-name>`` tag rather than the body text.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path) as f:
            lines = f.read().splitlines()
    except (OSError, IOError):
        return False

    tail = "\n".join(lines[-_RECENT_LINES:]) if lines else ""
    return bool(_RECENT_CMD_RE.search(tail))


def check_session_context(transcript_path):
    """Return the active context command name (e.g. 'AUTO-DOC') or None.

    Reads the session context sidecar file and checks whether its
    timestamp is within CONTEXT_TTL_S.
    """
    if not transcript_path:
        return None
    session = _session_id(transcript_path)
    if not session:
        return None
    path = os.path.join(_session_dir(session), SIDECAR_FILENAME)
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return None

    command = data.get("command")
    timestamp_ms = data.get("timestamp_ms", 0)
    if not command or not isinstance(timestamp_ms, (int, float)):
        return None

    age_s = time.time() - timestamp_ms / 1000
    if age_s > CONTEXT_TTL_S or age_s < 0:
        return None
    return command


def check_pause(transcript_path):
    """Return latch info if the session is paused, else None.

    This hook is a read-only consumer: the latch is created by the ``pause``
    subcommand of scripts/auto-approve-session.py and removed only by
    ``unpause``. It never expires — it is a request that holds until cleared.

    A latch we cannot parse still counts as paused. Unlike the auto-approve
    sidecar, this marker *withholds* privilege, so ignoring an unreadable one
    would fail in the unsafe direction: a run the user asked to stop would keep
    going. ``unpause`` removes a corrupt latch as readily as a valid one.
    """
    if not transcript_path:
        return None
    session = _session_id(transcript_path)
    if not session:
        return None
    path = os.path.join(_session_dir(session), PAUSE_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return {"paused_at_ms": None, "note": None}
    if not isinstance(data, dict):
        return {"paused_at_ms": None, "note": None}
    paused_at_ms = data.get("paused_at_ms")
    note = data.get("note")
    return {
        "paused_at_ms": paused_at_ms if isinstance(paused_at_ms, (int, float)) else None,
        "note": note.strip() if isinstance(note, str) and note.strip() else None,
    }


def _usage_windows_match(mute_iso, verdict_iso):
    """True when a mute was taken out for the window the verdict is about."""
    if not mute_iso or not verdict_iso:
        return False        # a mute with no window silences nothing
    try:
        a = datetime.fromisoformat(mute_iso)
        b = datetime.fromisoformat(verdict_iso)
    except (TypeError, ValueError):
        return False
    return abs((a - b).total_seconds()) <= USAGE_WINDOW_TOL_MIN * 60


def check_usage_gate(transcript_path):
    """Return the published usage verdict if this call should ask, else None.

    The daemon owns the thresholds and precomputes ``over``/``binding``, so this
    is a file read and two comparisons — cheap enough for every tool call.

    Returns None (no gate) when the reading is missing, unparseable, stale, not
    over the limit, or muted by this session for the window in question.
    """
    path = os.path.join(_session_base(), USAGE_FILENAME)
    try:
        with open(path) as f:
            reading = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return None
    if not isinstance(reading, dict) or not reading.get("ok") or not reading.get("over"):
        return None

    read_at_ms = reading.get("read_at_ms")
    if not isinstance(read_at_ms, (int, float)):
        return None
    age_s = time.time() - read_at_ms / 1000
    if age_s > USAGE_STALE_S or age_s < 0:
        return None                     # nobody is publishing; don't gate on guesses

    binding = reading.get("binding")
    verdict_window = reading.get("window_iso")
    if not _muted(transcript_path, binding, verdict_window):
        return reading
    return None


def _muted(transcript_path, binding, verdict_window):
    """True when this session muted the limit warning for this window.

    A mute records the window of *each* limit at the time it was taken out, so a
    pre-emptive mute works whichever limit later binds. Unlike the pause latch, an
    unreadable mute grants nothing: a corrupt file must not silence a warning.
    """
    session = _session_id(transcript_path)
    if not session:
        return False
    try:
        with open(os.path.join(_session_dir(session), USAGE_MUTE_FILENAME)) as f:
            mute = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return False
    if not isinstance(mute, dict):
        return False
    windows = mute.get("windows")
    if not isinstance(windows, dict):
        return False
    return _usage_windows_match(windows.get(binding), verdict_window)


def _usage_reason(reading):
    """Build the ask reason for a call made close to the usage limit.

    Like the pause latch, this deliberately does not name the command that
    silences it: on a deny the text is fed back to the agent, and it must not read
    as instructions for switching off its own warning.
    """
    kind = reading.get("binding") or "usage"
    pct = reading.get("pct")
    human = reading.get("window_human")
    pct_txt = f"{pct}% " if pct is not None else ""
    resets = f", resets {human}" if human else ""
    return (f"[permission-guard] {kind} limit at {pct_txt}used{resets} — close to a "
            f"rate-limit cutoff; approving continues this call")


def _pause_reason(latch):
    """Build the ask reason shown for a paused session.

    Deliberately does not name the command that clears the latch: on a deny the
    reason text is fed back to the agent, and it must not read as instructions
    for unlatching its own gate.
    """
    age = ""
    paused_at_ms = latch.get("paused_at_ms")
    if paused_at_ms:
        secs = max(0, int(time.time() - paused_at_ms / 1000))
        age = f" {secs}s ago" if secs < 60 else f" {secs // 60}m ago"
    note = f" — note: {latch['note']}" if latch.get("note") else ""
    return (
        f"[permission-guard] PAUSED by user{age} — this run stays paused until "
        f"the user resumes it; approving lets only this one call through" + note
    )


# ── Edit guard (manual toggle for Edit/Write/NotebookEdit) ──────────────────
# The emit-edit-guard.py script prints a SESSION_FEATURE marker into the
# transcript.  Default is ON (edits allowed).  When the latest marker is OFF,
# Edit/Write/NotebookEdit are blocked until the user runs /mg:edit-on.
_EDIT_GUARD_RE = re.compile(r"SESSION_FEATURE: MG:EDIT_GUARD_(ON|OFF)_(\d{10,})")


def check_edit_guard(transcript_path):
    """Return True if the edit guard is active (edits should be blocked).

    Scans for the most recent EDIT_GUARD marker with a valid timestamp.
    No marker or latest=ON means edits are allowed (returns False).
    Latest=OFF means blocked.

    The timestamp suffix distinguishes real emitter output from phantom
    matches (source code / grep output appearing in the transcript).
    Unlike session context markers, the edit guard never expires — it is
    a manual toggle that persists until explicitly flipped.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path) as f:
            raw = f.read()
    except (OSError, IOError):
        return False

    matches = list(_EDIT_GUARD_RE.finditer(raw))
    if not matches:
        return False  # No marker → default ON (edits allowed)

    # Take the last marker; reject only future timestamps (clock skew)
    last = matches[-1]
    timestamp_ms = int(last.group(2))
    age_s = time.time() - timestamp_ms / 1000
    if age_s < 0:
        return False  # clock skew / forged future timestamp

    return last.group(1) == "OFF"


# ── Edit guard bridge writer (best-effort status for statusline) ──────────
def _write_edit_guard_bridge(event):
    """Write edit guard state to a session-scoped bridge file.

    The statusline hook reads this file to show an edit guard badge.
    Best-effort: never raises, never breaks the hook.
    """
    try:
        transcript_path = event.get("transcript_path", "")
        if not transcript_path:
            return
        session = _session_id(transcript_path)
        if not session:
            return
        blocked = check_edit_guard(transcript_path)
        state = "OFF" if blocked else "ON"
        session_dir = _session_dir(session)
        os.makedirs(session_dir, exist_ok=True)
        bridge_path = os.path.join(session_dir, "edit-guard.json")
        with open(bridge_path, "w") as f:
            json.dump({"state": state, "ts": int(time.time())}, f)
    except Exception:
        pass


# Claude's internal directory (memory, settings, etc.) — always allowed
_CLAUDE_DIR_TILDE = "~/.claude/"
_CLAUDE_DIR_ABS = os.path.expanduser("~/.claude/")

# The user's home directory (no trailing slash). The workspace-sibling
# allowance is suppressed when a project's parent directory IS $HOME (or the
# filesystem root), since every home dotfile/folder would otherwise look like a
# "sibling project" and be allowed implicitly.
_HOME_DIR = os.path.expanduser("~").rstrip("/")


def _is_claude_internal(path):
    """Return True if *path* points inside Claude's own ~/.claude/ directory."""
    return path.startswith(_CLAUDE_DIR_TILDE) or path.startswith(_CLAUDE_DIR_ABS)

# Characters to strip from tokens when extracting potential file paths.
# Quotes plus common shell/code punctuation that isn't part of real paths.
_TOKEN_STRIP_CHARS = "'\"`(),[]{}"

# Commands that modify files (used by out-of-project path guard). chmod and
# chown are here for the one chmod the category rules let through (see the
# Exec-bit chmod section): `chmod +x ~/.local/bin/x` must still ask.
FILE_MODIFYING_CMDS = re.compile(
    _NOT_FLAG + r"\b(rm|mv|cp|mkdir|touch|tee|chmod|chown)\b"
)
# Captures the target of a write redirect (> or >>). The (?<!\d) lookbehind
# excludes fd-prefixed redirects (e.g. 2>) and the (?!&) lookahead excludes fd
# duplications (e.g. >&2 / 2>&1) — neither is a file write we guard. Group 1 is
# the file the redirect writes to.
_REDIRECT_TARGET_RE = re.compile(r"(?<!\d)>{1,2}\s*(?!&)([^\s;|&<>]+)")

# Heredoc body stripping — removes content between heredoc markers
# so that data inside heredocs is not mistaken for shell arguments.
# A heredoc operator and its delimiter word: `<<EOF`, `<<-EOF`, `<< 'EOF'`,
# `<<"EOF"`, `<<\EOF`.
_HEREDOC_OPERATOR_RE = re.compile(r"<<(-?)[ \t]*\\?['\"]?(\w+)['\"]?")


def _heredoc_lines(command):
    """Map each line of *command*, as a delimiter line reads, to where those lines end.

    A delimiter line may have tabs before it and whitespace after it. The
    ends are in order, so _heredoc_body_end finds the first one after a
    body's start by bisection rather than by reading the lines again: every
    unterminated `cat <<a` read the rest of the command once more.
    """
    lines = {}
    start, n = 0, len(command)
    while start <= n:
        newline = command.find("\n", start)
        end = n if newline == -1 else newline
        lines.setdefault(command[start:end].lstrip("\t").rstrip(), []).append((start, end))
        start = end + 1
    return lines


def _heredoc_body_end(lines, start, delimiter):
    """Return where the heredoc body at *start* ends, or None if it never does.

    The body runs to the first line at or after *start* holding only
    *delimiter* (see _heredoc_lines). The returned index is that line's
    newline, which stays; the body and the delimiter line go.
    """
    spans = lines.get(delimiter, [])
    found = bisect.bisect_left(spans, (start, -1))
    return spans[found][1] if found < len(spans) else None


def _strip_heredocs(command):
    """Remove heredoc bodies so their content is not parsed as shell arguments.

    The rest of the opener line stays: only the lines after it are the body,
    so in `cat > f <<'EOF' && git push --force` the push is still a command.

    A scan rather than a pattern, reading quotes as bash does. An operator
    inside quotes or a comment opens nothing: `echo "<<EOF"` is text, and the
    lines after it are commands. One inside a command substitution in double
    quotes does, as in `git commit -m "$(cat <<'EOF' … EOF)"`. A body starts
    after the first newline outside quotes and ends at its delimiter line; a
    body that never ends stays in place and is read as commands. Each
    character is read once: the pattern this replaced scanned to the end of
    the command from every unterminated `<<`, quadratic in its length.
    """
    if "<<" not in command:
        return command
    out = []
    lines = None  # built on the first heredoc, see _heredoc_lines
    pending = []  # delimiters whose bodies start after the next newline
    # Enclosing contexts, as in _mask_quoted: '"' a double-quoted span, ')' and
    # '`' a command substitution opened inside one; None the top level.
    stack = [[None, 0]]
    copied = 0
    i, n = 0, len(command)
    while i < n:
        context = stack[-1]
        char = command[i]
        if context[0] == '"':
            if char == "\\":
                i += 2
            elif char == '"':
                stack.pop()
                i += 1
            elif command.startswith("$(", i):
                stack.append([")", 0])
                i += 2
            elif char == "`":
                stack.append(["`", 0])
                i += 1
            else:
                i += 1
            continue
        if char == "\\":
            i += 2
            continue
        if char == "\n":
            i += 1
            if pending:
                if lines is None:
                    lines = _heredoc_lines(command)
                end = i
                for delimiter in pending:
                    end = _heredoc_body_end(lines, end, delimiter)
                    if end is None:
                        break
                    end += 1
                pending = []
                if end is not None:
                    out.append(command[copied:i])
                    copied = i = end - 1  # keep the delimiter line's newline
            continue
        if char == "#" and (i == 0 or command[i - 1] in _COMMENT_START_AFTER):
            newline = command.find("\n", i)
            i = n if newline == -1 else newline
            continue
        if command.startswith("$'", i):
            i += 2
            while i < n and command[i] != "'":
                i += 2 if command[i] == "\\" else 1
            i += 1
            continue
        if char == "'":
            close = command.find("'", i + 1)
            i = n if close == -1 else close + 1
            continue
        if char == '"':
            stack.append(['"', 0])
        elif command.startswith("<<<", i):
            i += 3
            continue
        elif command.startswith("<<", i):
            operator = _HEREDOC_OPERATOR_RE.match(command, i)
            if operator:
                pending.append(operator.group(2))
                i = operator.end()
                continue
        elif context[0] == ")":
            if char == "(":
                context[1] += 1
            elif char == ")":
                if context[1]:
                    context[1] -= 1
                else:
                    stack.pop()
        elif context[0] == "`" and char == "`":
            stack.pop()
        i += 1
    out.append(command[copied:])
    return "".join(out)


# Quote masking — the contents of quoted spans are replaced by this filler so
# shell punctuation inside a string literal (a `>` closing an XML tag in a sed
# pattern, an `rm` inside a commit message) is not read as shell syntax.
# Comments are masked the same way: bash never runs them.
_MASK_CHAR = "x"

# A `#` starts a comment only at the start of a word.
_COMMENT_START_AFTER = " \t\n;&|()<>"

# Nested shell invocations: the quoted argument IS a command, so masking it
# would hide a real redirect or a real rm target. Those commands are scanned
# raw instead — a spurious prompt beats a missed out-of-project write.
_SHELL_INVOKER_RE = re.compile(
    r"\b(?:bash|sh|zsh|ksh|dash)\s+(?:-\w+\s+)*-\w*c\b"  # bash -c, sh -lc, …
    r"|\beval\b"
    r"|\bxargs\b"
    r"|\bssh\b"
)

# Shell segment (split points: newline ; | &) and whitespace-delimited token,
# both applied to the masked command so quoted separators don't split.
_SEGMENT_RE = re.compile(r"[^\n;|&]+")
_TOKEN_RE = re.compile(r"\S+")

# A backslash at the end of a line joins it to the next one, unless that
# backslash is itself escaped (an even run of backslashes before it).
_CONTINUATION_RE = re.compile(r"(?<!\\)((?:\\\\)*)\\\n")


def _join_continuations(command):
    """Return *command* with each backslash-newline continuation read as spaces.

    Two spaces for the two characters, so offsets into the result still line
    up with the original command.
    """
    return _CONTINUATION_RE.sub(lambda match: match.group(1) + "  ", command)


def _command_text(command):
    """Return *command* the way every check reads it.

    Heredoc bodies are dropped first, since a `\\` ending a line inside a
    quoted heredoc is data, not a continuation. Continuation lines are then
    joined, so `git push origin main \\` + newline + `--force` reads as the
    one command bash runs.
    """
    return _join_continuations(_strip_heredocs(command))


def _mask_quoted(command):
    """Return *command* with the contents of quoted spans replaced by filler.

    Length and character offsets are preserved, so a match found in the masked
    string can be sliced straight out of the original. The quote characters
    themselves are kept — only what they enclose is masked, which is enough to
    stop a quoted `>` from reading as a redirect while a genuinely quoted
    write target (``> "/tmp/my file"``) still resolves to its real path.

    Backslash escapes are honoured outside single quotes; an unterminated
    quote masks to the end of the string, as the shell would keep reading.

    A command substitution inside double quotes — `"$(…)"` or a backtick
    pair — is left visible: bash runs it, so `echo "$(sudo ls)"` is a sudo,
    not a string. Inside it, quoting starts afresh, so the pattern in
    `"$(grep "rm -rf" log)"` is still data.

    A comment is masked up to its newline. Left alone, the apostrophe in
    `# it's done` would open a quote that hides every line down to the next
    apostrophe.
    """
    out = list(command)
    # Enclosing contexts, innermost last: '"' is a double-quoted span; ')' and
    # '`' are a command substitution opened inside one, waiting for its closer;
    # None is the top level. A ')' context counts the parentheses opened inside
    # it, so a subshell does not close it early. A stack rather than recursion,
    # so no nesting depth can make the hook raise.
    stack = [[None, 0]]
    i, n = 0, len(command)
    while i < n:
        context = stack[-1]
        char = command[i]
        if context[0] == '"':
            if char == "\\":
                # \" and \$ do not close the span or open a substitution.
                width = min(2, n - i)
                out[i:i + width] = _MASK_CHAR * width
                i += 2
            elif char == '"':
                stack.pop()
                i += 1
            elif command.startswith("$(", i):
                stack.append([")", 0])
                i += 2
            elif char == "`":
                stack.append(["`", 0])
                i += 1
            else:
                out[i] = _MASK_CHAR
                i += 1
            continue
        if char == "\\":
            i += 2  # escaped char outside quotes — nothing to mask
            continue
        if char == "#" and (i == 0 or command[i - 1] in _COMMENT_START_AFTER):
            newline = command.find("\n", i)
            end = n if newline == -1 else newline
            out[i:end] = _MASK_CHAR * (end - i)
            i = end
            continue
        if command.startswith("$'", i):
            # ANSI-C quoting: a backslash escapes the next character, so the
            # `\'` of `$'don\'t'` does not close the span. Read as a plain
            # single quote, the span ended there, and the next `'` opened one
            # that hid every command up to the one after it.
            end = i + 2
            while end < n and command[end] != "'":
                end += 2 if command[end] == "\\" else 1
            end = min(end, n)
            out[i + 2:end] = _MASK_CHAR * (end - i - 2)
            i = end + 1
            continue
        if char == "'":
            close = command.find("'", i + 1)
            end = n if close == -1 else close
            out[i + 1:end] = _MASK_CHAR * (end - i - 1)
            i = end + 1
            continue
        if char == '"':
            stack.append(['"', 0])
        elif context[0] == ")":
            if char == "(":
                context[1] += 1
            elif char == ")":
                if context[1]:
                    context[1] -= 1
                else:
                    stack.pop()
        elif context[0] == "`" and char == "`":
            stack.pop()
        i += 1
    return "".join(out)


def _mask_nested_quoted(command):
    """Return *command* with each top-level quoted span read as a nested shell does.

    A nested shell runs a quoted string as a command, and quotes inside that
    string are its own. Unmasked, the quoted `;` of
    `bash -c "curl -H 'a; b' -X POST …"` ends the curl, and nothing reads the
    `-X POST`; masked, the whole curl is filler. Here the top-level quotes
    stay as written and what they hold goes through _mask_quoted, after
    `\\"` inside double quotes is read as the quote the nested shell sees.
    Comments are masked, as _mask_quoted masks them. Length is preserved.
    """
    out = list(command)
    i, n = 0, len(command)
    while i < n:
        char = command[i]
        if char == "\\":
            i += 2
            continue
        if char == "#" and (i == 0 or command[i - 1] in _COMMENT_START_AFTER):
            newline = command.find("\n", i)
            end = n if newline == -1 else newline
            out[i:end] = _MASK_CHAR * (end - i)
            i = end
            continue
        ansi = command.startswith("$'", i)
        if ansi or char in "'\"":
            if ansi:
                i += 1
                char = "'"
            end = i + 1
            while end < n and command[end] != char:
                end += 2 if (char == '"' or ansi) and command[end] == "\\" else 1
            end = min(end, n)
            inner = command[i + 1:end]
            if char == '"':
                inner = inner.replace('\\"', ' "')
            elif ansi:
                inner = inner.replace("\\'", " '")
            out[i + 1:end] = _mask_quoted(inner)
            i = end + 1
            continue
        i += 1
    return "".join(out)


# ── LLM evaluator constants ─────────────────────────────────────────────────
HAIKU_TIMEOUT_S = 12
HAIKU_MODEL = "haiku"
TRANSCRIPT_CONTEXT_LINES = 10
TRANSCRIPT_MSG_MAX_CHARS = 200

# Paths where recursive rm is considered safe (temp/test cleanup)
SAFE_RM_PATH_PREFIXES = ("temp/", "./temp/", "/tmp/")

# Directory components that indicate a temp/scratch directory
_TEMP_COMPONENTS = ("/tmp/", "/temp/")


def _path_is_temp(path):
    """Return True if *path* is inside a tmp or temp directory."""
    # Prefix match (original behaviour)
    if any(path.startswith(prefix) for prefix in SAFE_RM_PATH_PREFIXES):
        return True
    # Component match — /tmp/ or /temp/ anywhere in the path
    return any(comp in path for comp in _TEMP_COMPONENTS)


def _is_safe_rm(command):
    """Return True if every rm segment in *command* targets only temp directories.

    Compound commands joined by ``&&``, ``||``, or ``;`` are split into
    segments.  Only segments containing an ``rm`` invocation are examined —
    non-rm segments are irrelevant.  If no segment contains ``rm``, return
    False (this function is specifically about rm safety).
    """
    # Split on shell compound operators (&&, ||, ;)
    segments = re.split(r'\s*(?:&&|\|\||;)\s*', command)

    rm_segments = [seg for seg in segments if re.match(r'^\s*rm\s', seg.strip())]

    # Must have at least one rm segment
    if not rm_segments:
        return False

    for seg in rm_segments:
        tokens = seg.split()
        paths = [t.strip("'\"") for t in tokens[1:] if not t.startswith('-')]
        if not paths:
            return False
        if not all(_path_is_temp(p) for p in paths):
            return False

    return True


# ── Git worktree destruction ────────────────────────────────────────────────
# `git checkout -- <path>`, `git restore <path>` and `git clean -f` are the
# only operations this guard sees that can destroy work with NO recovery path.
# A discarded worktree modification leaves no reflog entry and no object in the
# database to recover from: the bytes are gone. (`git reset --hard` is in the
# same class and has its own always-ask rule.)
#
# The old checkout rule exempted the `--` spelling as "file restore", which had
# it exactly backwards. `git checkout <branch>` REFUSES when it would overwrite
# local modifications; `git checkout -- <file>` is *designed* to discard them.
# The exemption spared the irreversible form and asked about the recoverable
# one — and a real ~500-line loss went through it unprompted.
#
# Asking on every restore would be too noisy to stay readable, and a prompt
# nobody reads is not a guard. So the discriminator is whether there is
# anything to lose: git itself is asked, scoped to the pathspecs the command
# names, and a restore over a clean path stays silent. Uncertainty asks — an
# unresolvable working directory, a pathspec neither git nor the filesystem
# recognises (which means we resolved it wrong), or a git that will not answer
# all land on the ask side, because the cost of a spurious prompt here is a
# keystroke and the cost of a miss is unrecoverable work.
#
# `git stash push` is deliberately NOT here: it moves work rather than
# destroying it, `git stash list` still holds it, and the point where it does
# become irreversible — `git stash drop|clear` — already has its own rule.

_GIT_TIMEOUT_S = 5

# Redirects are stripped before tokenising so `2>/dev/null` is not read as a
# pathspec. Matches an optional fd, the operator, and its target.
_REDIRECT_STRIP_RE = re.compile(r"&?\d*(?:>>|>|<<<|<)\s*&?\S+")

# git's own options that take a separate value, so a value can never be read as
# the subcommand. `-C` is captured: it moves the repo the command acts on.
_GIT_GLOBAL_VALUE_OPTS = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
})

# Subcommand options taking a separate value, per verb. `-m` is absent on
# purpose: on checkout it means --merge and takes nothing.
_CHECKOUT_VALUE_OPTS = frozenset({"--conflict", "--pathspec-from-file"})
_RESTORE_VALUE_OPTS = frozenset({
    "-s", "--source", "--conflict", "--pathspec-from-file",
})
_CLEAN_VALUE_OPTS = frozenset({"-e", "--exclude", "--pathspec-from-file"})

# checkout options that mean "make or move a branch" rather than "restore a
# path". These are branch operations and belong to the category rule.
_CHECKOUT_BRANCH_OPTS = frozenset({
    "-b", "-B", "--orphan", "--detach", "--track", "-t", "--no-track",
    "--guess", "--no-guess",
})

# verb: the git subcommand. paths: the pathspecs it names. bounded: whether it
# named any (an unbounded `git clean -f` reaches the whole tree). ignored:
# whether ignored files are in scope (-x/-X). chdir: a `git -C <dir>` override.
GitWorktreeCmd = namedtuple("GitWorktreeCmd", "verb paths bounded ignored chdir")

# How many paths to name in a prompt before summarising the rest.
_REASON_PATH_LIMIT = 3


def _tokenize_segment(text):
    """Split one shell segment into tokens, quotes removed.

    shlex gets quoted paths with spaces right; an unbalanced quote makes it
    raise, and a whitespace split is a good enough fallback there.
    """
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError:
        return text.split()


def _split_operands(args, value_opts):
    """Split *args* into (flags, before_dashdash, after_dashdash, saw_dashdash).

    Options in *value_opts* swallow their separate value so it is never
    mistaken for an operand. The `--` split is kept because it is the only
    unambiguous pathspec marker git offers.
    """
    flags, pre, post = [], [], []
    saw_dashdash = False
    i = 0
    while i < len(args):
        token = args[i]
        if saw_dashdash:
            post.append(token)
            i += 1
            continue
        if token == "--":
            saw_dashdash = True
            i += 1
            continue
        if token.startswith("-") and token != "-":
            flags.append(token)
            if token.split("=", 1)[0] in value_opts and "=" not in token:
                i += 2
            else:
                i += 1
            continue
        pre.append(token)
        i += 1
    return flags, pre, post, saw_dashdash


def _flag_names(flags):
    """Return the set of long-option names and the concatenated short letters.

    `-fd` and `--force -d` have to answer the same question, so short clusters
    are flattened into one string to test letters against.
    """
    names = {flag.split("=", 1)[0] for flag in flags}
    shorts = "".join(
        flag.lstrip("-") for flag in flags if not flag.startswith("--")
    )
    return names, shorts


def _path_exists_under(base_dir, path):
    """Return True if *path* names something on disk, resolved against base_dir.

    lexists, not exists: a dangling symlink is still a path the command names.
    """
    if not base_dir:
        return False
    candidate = path if os.path.isabs(path) else os.path.join(base_dir, path)
    return os.path.lexists(candidate)


def _parse_checkout(args, base_dir, chdir):
    """Classify a `git checkout` invocation, or None if it is a branch op."""
    flags, pre, post, saw_dashdash = _split_operands(args, _CHECKOUT_VALUE_OPTS)
    names, _ = _flag_names(flags)
    if names & _CHECKOUT_BRANCH_OPTS:
        return None
    if saw_dashdash:
        # Everything after `--` is a pathspec by definition. Anything before it
        # is a tree-ish, which changes what the worktree is overwritten WITH,
        # not whether it is overwritten.
        paths = post
    else:
        # `git checkout foo` is ambiguous: branch or path. Only claim it when
        # every operand names something on disk — a partial match means we are
        # guessing, and the category rule (which asks) is the safer reader.
        if not pre or not all(_path_exists_under(base_dir, p) for p in pre):
            return None
        paths = pre
    if not paths:
        return None
    return GitWorktreeCmd("checkout", paths, True, False, chdir)


def _parse_restore(args, chdir):
    """Classify a `git restore` invocation, or None if the worktree is safe."""
    flags, pre, post, saw_dashdash = _split_operands(args, _RESTORE_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    staged = "--staged" in names or "S" in shorts
    worktree = "--worktree" in names or "W" in shorts
    if staged and not worktree:
        # Index-only: unstages, leaves the worktree untouched. Not a loss.
        return None
    paths = post if saw_dashdash else pre
    if not paths:
        # git restore refuses without a pathspec, so there is nothing to guard.
        return None
    return GitWorktreeCmd("restore", paths, True, False, chdir)


def _parse_clean(args, chdir):
    """Classify a `git clean` invocation, or None if it deletes nothing."""
    flags, pre, post, saw_dashdash = _split_operands(args, _CLEAN_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    if "--dry-run" in names or "n" in shorts:
        return None
    if not ("--force" in names or "f" in shorts):
        # Without -f git refuses (clean.requireForce defaults to true).
        return None
    ignored = "x" in shorts or "X" in shorts
    paths = post if saw_dashdash else pre
    return GitWorktreeCmd("clean", paths, bool(paths), ignored, chdir)


def _parse_git_worktree_cmd(tokens, base_dir):
    """Return a GitWorktreeCmd for *tokens*, or None if it destroys nothing."""
    if not tokens or os.path.basename(tokens[0]) != "git":
        return None
    index, chdir = 1, None
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        name = option.split("=", 1)[0]
        if "=" in option or name not in _GIT_GLOBAL_VALUE_OPTS:
            index += 1
            continue
        if name == "-C" and index + 1 < len(tokens):
            chdir = tokens[index + 1]
        index += 2
    if index >= len(tokens):
        return None
    verb, args = tokens[index], tokens[index + 1:]
    if verb == "checkout":
        return _parse_checkout(args, base_dir, chdir)
    if verb == "restore":
        return _parse_restore(args, chdir)
    if verb == "clean":
        return _parse_clean(args, chdir)
    return None


def _run_git(root, args):
    """Run a git command in *root*. Returns stdout, or None if git would not answer."""
    try:
        result = subprocess.run(
            ["git", "-C", root] + args,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _git_knows_path(root, path):
    """Return True if *path* is on disk or tracked by the repo at *root*.

    The point is to catch our own misresolution. A pathspec that neither the
    filesystem nor the index recognises means the base directory we resolved it
    against is probably wrong — in which case a clean `git status` for it
    proves nothing, and the caller must ask rather than clear.
    """
    if _path_exists_under(root, path):
        return True
    return _run_git(root, ["ls-files", "--error-unmatch", "--", path]) is not None


def _git_pending(root, cmd):
    """Return the porcelain lines *cmd* would destroy, or None if unknown."""
    args = ["status", "--porcelain"]
    # Untracked files are what clean deletes and what a restore cannot touch.
    args.append("--untracked-files=" + ("all" if cmd.verb == "clean" else "no"))
    if cmd.ignored:
        args.append("--ignored=matching")
    if cmd.paths:
        args.append("--")
        args.extend(cmd.paths)
    output = _run_git(root, args)
    if output is None:
        return None
    lines = [line for line in output.splitlines() if line.strip()]
    if cmd.verb == "clean":
        return [line for line in lines if line[:2] in ("??", "!!")]
    return [line for line in lines if line[:2] not in ("??", "!!")]


def _porcelain_paths(lines):
    """Extract the path from each porcelain line, rename arrows resolved."""
    paths = []
    for line in lines:
        path = line[3:] if len(line) > 3 else line
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip().strip('"'))
    return paths


def _worktree_reason(cmd, lines):
    """Build the prompt text naming what this command would destroy.

    The paths are the point of the prompt, so they lead. A count only appears
    when there is more than one, and the list is truncated so a wide sweep
    stays readable.
    """
    paths = _porcelain_paths(lines)
    shown = ", ".join(paths[:_REASON_PATH_LIMIT])
    if len(paths) > _REASON_PATH_LIMIT:
        shown += f", +{len(paths) - _REASON_PATH_LIMIT} more"
    if len(paths) > 1:
        shown = f"{len(paths)} paths ({shown})"
    verb = "deletes untracked" if cmd.verb == "clean" else "discards uncommitted changes in"
    scope = "" if cmd.bounded else ", across the whole tree"
    return f"git {cmd.verb} {verb} {shown}{scope} — not recoverable from git"


def _judge_worktree_cmd(cmd, base_dir):
    """Return ("ask", reason) or ("clear", None) for one parsed git command."""
    root = base_dir
    if cmd.chdir:
        root = cmd.chdir if os.path.isabs(cmd.chdir) else os.path.join(base_dir or "", cmd.chdir)
    if not root or not os.path.isdir(root):
        return ("ask", f"git {cmd.verb} destroys uncommitted work and the "
                       "directory it would run in could not be resolved")
    if cmd.bounded:
        unknown = [p for p in cmd.paths if not _git_knows_path(root, p)]
        if unknown:
            return ("ask", f"git {cmd.verb} targets a path this guard could not "
                           f"resolve, so what it would destroy is unknown: "
                           f"{', '.join(unknown[:_REASON_PATH_LIMIT])}")
    lines = _git_pending(root, cmd)
    if lines is None:
        return ("ask", f"git {cmd.verb} destroys uncommitted work and git would "
                       "not report what is pending")
    if not lines:
        return ("clear", None)
    return ("ask", _worktree_reason(cmd, lines))


def _resolve_cd(base_dir, target):
    """Return the directory a `cd <target>` lands in, or None if unknowable."""
    if target.startswith("-"):
        return None  # `cd -` needs shell history this hook does not have
    if os.path.isabs(target):
        return target
    if not base_dir:
        return None
    return os.path.normpath(os.path.join(base_dir, target))


def check_worktree_destruction(command, base_dir):
    """Check whether *command* would destroy unrecoverable worktree content.

    Returns ("ask", reason), ("clear", None), or None when no segment invokes a
    worktree-destroying git command. "clear" means a restore was recognised and
    git reports nothing pending for its paths — the caller uses it to suppress
    the broad checkout category rule, which would otherwise ask about a no-op.

    Segments are read off the quote-masked copy so a quoted `;` does not split
    the command, and sliced from the original so pathspecs keep their real
    text. A `cd` in an earlier segment moves the base directory, because that
    is where the git command will actually run.
    """
    command = _command_text(command)
    masked = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)
    cwd = base_dir
    cleared = False
    for segment in _SEGMENT_RE.finditer(masked):
        text = command[segment.start():segment.end()]
        tokens = _tokenize_segment(_REDIRECT_STRIP_RE.sub(" ", text))
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "cd" and len(tokens) > 1:
            cwd = _resolve_cd(cwd, tokens[1])
            continue
        parsed = _parse_git_worktree_cmd(tokens, cwd)
        if not parsed:
            continue
        decision, reason = _judge_worktree_cmd(parsed, cwd)
        if decision == "ask":
            # First loss wins: the prompt names the command that would destroy
            # work, and the user is deciding about the whole compound anyway.
            return ("ask", reason)
        cleared = True
    return ("clear", None) if cleared else None


# ── Local HTTP targets ──────────────────────────────────────────────────────
# HTTP_SUBMIT_RULE exists to catch data leaving the machine, and it reads the
# verb (-X POST, -d) rather than the target — so a POST to a service on this
# host or on this tailnet asks exactly as loudly as one to a stranger. Routine
# local API work (a Prefect query, a health check against a dev server) then
# costs an approval per call, the same trade ENV_PROTECTION and
# PGPASS_PROTECTION were switched off over.
#
# check_local_http buys that back for local targets only, and suppresses THAT
# ONE RULE. Everything else still stands: pipe-to-shell keeps its own rule (a
# local URL is no safer to pipe into a shell), and a credential in the argument
# list still asks, because check_sensitive_in_command runs after the category
# rules regardless of what they skipped.
#
# "Local" is decided by ADDRESS, not by name, so a tailnet needs no per-host
# entry: every URL host is resolved and every address it answers with has to
# land in one of these networks. Add a CIDR here to trust more — e.g.
# "192.168.0.0/16" for a home LAN, deliberately not trusted by default.
LOCAL_HTTP_NETWORKS = (
    "127.0.0.0/8",          # loopback; Debian/Ubuntu also park the host's own name at 127.0.1.1
    "::1/128",
    "0.0.0.0/32",           # curl sends this one to localhost
    "100.64.0.0/10",        # Tailscale IPv4 (the CGNAT range tailnets allocate from)
    "fd7a:115c:a1e0::/48",  # Tailscale IPv6 (ULA)
)

_LOCAL_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in LOCAL_HTTP_NETWORKS)

# Resolution is fail-closed: NXDOMAIN, a timeout, or a resolver that is not
# answering leaves the host untrusted and the rule asks as before. The lookup
# runs in a daemon thread because getaddrinfo() ignores
# socket.setdefaulttimeout(), so a stalled resolver would otherwise stall the
# tool call. It is only ever reached once the rule has already matched, and
# MagicDNS and /etc/hosts both answer in single-digit milliseconds.
LOCAL_HTTP_RESOLVE_TIMEOUT_S = 1.0

# The authority of any scheme://… URL: everything up to the first path
# separator, whitespace, quote or shell metacharacter. A bracketed IPv6
# literal is captured whole so its colons are not read as a port.
_URL_AUTHORITY_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]*://(\[[^\]\s]*\]|[^/\s'\"`<>|&;)]*)"
)


def _resolve_host(host):
    """Return the set of addresses *host* answers with, or None if it cannot.

    None covers every failure the same way — unknown name, no resolver,
    timeout — because the caller treats all three as "not local".
    """
    box = {}

    def lookup():
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            box["addrs"] = {info[4][0] for info in infos}
        except (OSError, UnicodeError, ValueError):
            box["addrs"] = None

    worker = threading.Thread(target=lookup, daemon=True)
    worker.start()
    worker.join(LOCAL_HTTP_RESOLVE_TIMEOUT_S)
    return box.get("addrs")


def _ip_is_local(text):
    """Return True if *text* is an address inside LOCAL_HTTP_NETWORKS."""
    try:
        # A link-local address carries a zone id (fe80::1%eth0) that
        # ip_address does not parse.
        addr = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    return any(addr in network for network in _LOCAL_NETWORKS)


def _url_host(authority):
    """Return the hostname out of a URL authority, or "" if there is none."""
    authority = authority.rsplit("@", 1)[-1]  # drop user:password@
    if authority.startswith("["):             # [::1]:4200
        return authority[1:].partition("]")[0]
    return authority.split(":", 1)[0]         # host:port


def _host_is_local(host):
    """Return True if *host* names this machine, the loopback, or the tailnet."""
    host = host.strip().rstrip(".").lower()
    if not host:
        return False
    # RFC 6761 reserves localhost and its subdomains for the loopback, and
    # answering without a lookup keeps the common case working on a machine
    # whose resolver is down.
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        pass
    else:
        return _ip_is_local(host)
    addresses = _resolve_host(host)
    if not addresses:
        return False
    # ALL of them: a name that answers with one local and one public address
    # can still reach the public one.
    return all(_ip_is_local(address) for address in addresses)


# Ways to send a request somewhere its URL does not name. curl's --resolve and
# --connect-to pin a name to another address, a proxy or SOCKS option relays
# it, --doh-url and --dns-servers resolve the name elsewhere, and -K/--config
# reads more options from a file; wget takes the same from -e/--execute and
# --config. A *_proxy variable in the command reroutes either one.
_HTTP_REROUTE_RE = re.compile(
    _cmd_arg(
        *_named(r"\bcurl"),
        r"--(?:resolve|connect-to|proxy[\w.-]*+|preproxy|socks[\w-]*+|doh-url|dns-servers"
        r"|config)(?![\w-])|-" + _CURL_FLAGS + r"[xK]",
    )
    + r"|" + _cmd_arg(*_named(r"\bwget"), r"(?:-e|--execute|--config)(?![\w-])")
    + r"|(?i:\b(?:https?|ftp|all)_proxy=)"
)


def check_local_http(command):
    """Return True if every URL in *command* points at a local address.

    Scanned raw rather than quote-masked, because a URL is exactly the kind of
    argument that gets quoted, and a hidden ``"https://api.example.com"`` is
    the one thing this must not miss. Heredoc bodies are dropped the same way
    check_command drops them — a URL in a payload is data, not a target.

    A command with no URL at all returns False: the rule matched on some
    target this cannot see (a bare host, a --url read from a variable), and
    an unseen target is not a local one. So does any single untrusted URL —
    ``curl -d @x localhost && curl -d @x api.example.com`` is one command,
    and one leak is enough. So does a request rerouted past its URL
    (_HTTP_REROUTE_RE): ``curl -d @x --resolve localhost:80:203.0.113.5
    http://localhost/`` sends the data to 203.0.113.5.
    """
    text = _command_text(command)
    # Every reading check_command uses, so no quoted `;` hides the option.
    if any(_HTTP_REROUTE_RE.search(copy)
           for copy in (text, _mask_quoted(text), _mask_nested_quoted(text))):
        return False
    hosts = set()
    for match in _URL_AUTHORITY_RE.finditer(text):
        host = _url_host(match.group(1))
        if not host:
            return False
        hosts.add(host)
    if not hosts:
        return False
    return all(_host_is_local(host) for host in hosts)


# ── Reading a rule's matches for an exemption ───────────────────────────────
# An exemption retires a whole rule, so it must read every command that rule
# matched, and read each one as bash will run it. Three ways to get that wrong,
# each of which once let a real change through as a harmless one:
#
#   - A command substitution or subshell is a command of its own, but splits
#     no _SEGMENT_RE segment: `chmod +x a $(chmod 777 b)` read as one chmod
#     whose mode is +x.
#   - A backslash-newline joins two lines into one command:
#     `find / | xargs \` + newline + `chmod +x f` read as a chmod of its own,
#     though xargs runs it on every file find prints.
#   - With a nested shell in the command, check_command scans quoted text too,
#     so the rule can match inside a string that masking hides from segment
#     parsing: `bash -c "chmod 777 x"`.
#
# The third used to be handled by refusing any command with a nested shell in
# it, which also refused a plain `chmod +x a` that merely shared a command line
# with an unrelated `bash -c 'echo hi'`. Now only a match that actually sits
# inside a quoted span refuses; a chmod run BY another command (`sudo chmod`,
# `xargs chmod`, `find -exec chmod`) still fails each check's own test, since
# the chmod is not where the command starts.

# Split points for one simple command: _SEGMENT_RE's, plus the parentheses and
# backticks that open and close a subshell or a command substitution. The `&`
# of a redirect (`2>&1`, `&>log`) is not one.
_COMMAND_BREAK_RE = re.compile(r"[\n;|()`]|(?<![<>])&(?!>)")

_RULE_RE_BY_DESCRIPTION = {description: compiled
                           for compiled, description, _category in RULES}


def _rule_commands(command, description):
    """Return (before, word, after) for every match of rule *description*.

    *word* is the matched text; *before* and *after* run from it to the
    nearest command break on each side. All three are read off the masked
    command, after heredocs are dropped and continuation lines joined.

    Returns None when a match cannot be read this way: one inside a quoted
    span (see above), or one that itself runs across a command break, as
    `git rebase` + newline does — bash runs a bare `git rebase` there.

    A rule that matches context in front of its command (systemctl's
    command-position anchor takes in `; `, `$(`, `xargs `) marks where the
    command starts with a `word` group; *word* and *before* split there.
    """
    rule_re = _RULE_RE_BY_DESCRIPTION[description]
    has_word = "word" in rule_re.groupindex
    command = _command_text(command)
    masked = _mask_quoted(command)
    matches = list(rule_re.finditer(masked))
    if _SHELL_INVOKER_RE.search(command):
        visible = {match.start() for match in matches}
        if any(match.start() not in visible for match in rule_re.finditer(command)):
            return None
    found = []
    for match in matches:
        word_start = match.start("word") if has_word else match.start()
        word = masked[word_start:match.end()]
        if _COMMAND_BREAK_RE.search(word):
            return None
        breaks_before = list(_COMMAND_BREAK_RE.finditer(masked, 0, word_start))
        start = breaks_before[-1].end() if breaks_before else 0
        next_break = _COMMAND_BREAK_RE.search(masked, match.end())
        end = next_break.start() if next_break else len(masked)
        found.append((masked[start:word_start], word, masked[match.end():end]))
    return found


# ── Exec-bit chmod ──────────────────────────────────────────────────────────
# PERMISSION_CHANGE_RULE asks on every chmod, so an agent marking its own
# helper script executable asks exactly as loudly as `chown -R` on $HOME. The
# execute bit is no boundary for the agent: `bash script.sh` runs the same
# file without it and without a prompt, and this guard never reads a script's
# body either way (heredocs are stripped before scanning). Asking there buys
# nothing.
#
# What +x does add is a file that something ELSE runs later, with no tool call
# in between for this guard to see. Git only runs a hook that is executable,
# and .git/hooks is in-project, so the out-of-project check does not cover it.
# Any command that mentions a hook or a .git directory therefore keeps asking
# — a deliberately broad text match, since the target is often quoted or
# built from a variable. A hook path assembled entirely from variables set in
# an earlier call is not caught; writing the hook file is unguarded too.
#
# check_exec_bit_chmod suppresses THAT ONE RULE, and only when every chmod in
# the command adds nothing but the execute bit to named files. Numeric modes,
# removals, `=`, -R (GNU chmod reads it after the operands too), any chown,
# and a chmod run by another command (`find -exec`, `xargs`, `sudo`) all still
# ask. Out-of-project targets still ask: chmod is in FILE_MODIFYING_CMDS, and
# check_outside_project runs after the category rules regardless of what they
# skipped.

# Clauses like u+x, a+x or +x, comma-separated: execute added, nothing taken.
_EXEC_BIT_MODE_RE = re.compile(r"[ugoa]*\+x(?:,[ugoa]*\+x)*")

# Output-only options. Anything else starting with `-` — -R, --reference, or a
# mode like -w that removes a bit — keeps the rule in force.
_CHMOD_QUIET_OPTS_RE = re.compile(r"-[cfv]+|--(?:changes|silent|quiet|verbose)")

_HOOK_MENTION_RE = re.compile(r"\.git\b|hook", re.IGNORECASE)


def _is_exec_bit_chmod(segment):
    """Return True if *segment* is `chmod [quiet opts] <+x mode> <file>...`."""
    tokens = _TOKEN_RE.findall(_REDIRECT_STRIP_RE.sub(" ", segment))
    if not tokens or tokens[0] != "chmod":
        return False
    operands = []
    for token in tokens[1:]:
        if token.startswith("-"):
            if not _CHMOD_QUIET_OPTS_RE.fullmatch(token):
                return False
        else:
            operands.append(token)
    return len(operands) >= 2 and bool(_EXEC_BIT_MODE_RE.fullmatch(operands[0]))


def check_exec_bit_chmod(command):
    """Return True if every chmod/chown in *command* is a plain `chmod +x`.

    The hook check reads the raw command, since a quoted or variable target is
    exactly what quote masking would hide. Each chmod is then read as its own
    command by _rule_commands.
    """
    if _HOOK_MENTION_RE.search(_command_text(command)):
        return False
    found = _rule_commands(command, PERMISSION_CHANGE_RULE)
    return bool(found) and all(_is_exec_bit_chmod("".join(parts)) for parts in found)


# ── Managed systemd units ───────────────────────────────────────────────────
# SYSTEMCTL_RULE asks on every systemctl that is not a read, so bouncing the
# Prefect server and its workers — routine for the projects that run them —
# asks as loudly as `systemctl isolate rescue.target`.
#
# check_managed_systemctl suppresses THAT ONE RULE, and only when every
# systemctl in the command starts, stops, restarts, reloads or resets named
# SYSTEMCTL_MANAGED_UNITS. A bare name means its .service, as it does to
# systemctl. Everything else still asks: enable/disable, mask, edit, kill,
# isolate, daemon-reload; a glob, variable or quoted unit, whose target this
# cannot read; any option outside the output-only ones below (-H and -M reach
# another host or container, --job-mode=isolate stops everything else); and a
# systemctl behind a runner (`timeout 30 systemctl …`) or in a nested shell's
# string, which is not read as a command of its own.

_SYSTEMCTL_LIFECYCLE_VERBS = frozenset({
    "start", "stop", "restart", "try-restart", "reload",
    "reload-or-restart", "try-reload-or-restart", "reset-failed",
})

_SYSTEMCTL_SAFE_OPTS = frozenset({
    "--user", "--system", "--no-block", "--no-pager", "--no-ask-password",
    "--wait", "-q", "--quiet",
})

# Reserved words leave the systemctl behind them its own command
# (`if systemctl restart …; then`). A runner does not: `timeout`, `xargs` and
# the rest of _RUNNERS keep asking.
_SHELL_RESERVED_WORDS = frozenset({"if", "then", "elif", "else", "do", "while", "until", "!", "{"})

_SYSTEMCTL_PATHS = frozenset({"systemctl", "/usr/bin/systemctl", "/bin/systemctl"})


def _is_managed_systemctl(segment):
    """Return True if *segment* is a lifecycle verb on managed units only."""
    tokens = _TOKEN_RE.findall(_REDIRECT_STRIP_RE.sub(" ", segment))
    while tokens and tokens[0] in _SHELL_RESERVED_WORDS:
        tokens = tokens[1:]
    if not tokens or tokens[0] not in _SYSTEMCTL_PATHS:
        return False
    words = []
    for token in tokens[1:]:
        if token.startswith("-"):
            if token not in _SYSTEMCTL_SAFE_OPTS:
                return False
        else:
            words.append(token)
    if len(words) < 2 or words[0] not in _SYSTEMCTL_LIFECYCLE_VERBS:
        return False
    return all((unit if "." in unit else unit + ".service") in SYSTEMCTL_MANAGED_UNITS
               for unit in words[1:])


def check_managed_systemctl(command):
    """Return True if every systemctl write in *command* is on a managed unit."""
    found = _rule_commands(command, SYSTEMCTL_RULE)
    return bool(found) and all(_is_managed_systemctl("".join(parts)) for parts in found)


# ── Linked worktrees ────────────────────────────────────────────────────────
# The Git Branch & History rules protect the repository's real history, above
# all the branch checked out in the main working tree. A linked worktree
# (`git worktree add`, and every worktree CC gives an isolated agent) is a
# workspace of its own: resetting, rebasing or discarding changes there is the
# work, and asking about each step costs an approval per step of an unattended
# run.
#
# A worktree still shares the repository with the main tree and every other
# worktree: all branches, all tags, the stash list, config and remotes. So only
# the rules whose effect stays in the worktree and on its own branch stand down
# there (LINKED_WORKTREE_RULES). Branch and tag deletion, forced branch moves,
# `stash clear` and everything under Git Destructive Remote keep asking. So do
# the forms of the retired rules that reach further:
#
#   - switching the worktree onto an existing branch (`git checkout main`,
#     `git switch main`, `checkout -B`, `switch -C`). A branch checked out
#     nowhere else — which can be the official one, when the main tree is on
#     another branch — could otherwise be reset or rebased from here. Creating
#     a new branch or detaching HEAD stays exempt.
#   - a rebase that checks out another branch (`git rebase <upstream>
#     <branch>`), moves other branches along (`--update-refs`, or
#     rebase.updateRefs), or runs commands of its own (`-x`/`--exec`, and
#     `-i`, whose editor is one).
#   - dropping a stash that was not made on this worktree's branch. The stash
#     list is shared, so `stash@{0}` can be another worktree's; a stash's
#     subject names the branch it was made on, and git refuses to check one
#     branch out in two worktrees unless forced. A drop is judged only when it
#     is the one stash command in the call and nothing repeats it: any other
#     stash command, loop or function can move a different stash into the slot
#     the check looked at.
#
# The uncommitted-work check (Git worktree destruction) stands down in a
# linked worktree too: discarding the worktree's own changes is the trade.
#
# The worktree must not be the checkout this CC session started in. That one
# is the user's own — say, the main checkout of a bare repository set up with
# worktrees — and keeps every prompt. CC files a session's transcripts, its
# subagents' included, under a name made from the start directory; when the
# transcript path does not have that shape, nothing is exempt.
#
# All of this needs every command in the call to provably run inside one
# linked worktree: the one the call starts in, or the one a leading
# `cd <dir> &&` enters. A later `cd` or `git -C` is followed when its target
# is literal — absolute, or relative without `..` — stays inside the worktree,
# and does not enter a repository nested in it. Anything that can move git
# elsewhere less plainly (pushd to a new place, env -C, --git-dir, GIT_DIR,
# CDPATH, source, eval, trap, a variable target) turns the exemption off for
# the whole call, and every rule asks as before.

LinkedWorktree = namedtuple("LinkedWorktree", "top branch")

LINKED_WORKTREE_RULES = frozenset({
    GIT_CHECKOUT_RULE, GIT_SWITCH_RULE, GIT_REBASE_RULE, "git reset --hard",
    GIT_STASH_RULE,
})

# Ways to point git, or cd, somewhere no literal `cd` or `-C` spells out.
_RELOCATE_RE = re.compile(
    r"\bGIT_(?:DIR|WORK_TREE|COMMON_DIR|INDEX_FILE|NAMESPACE)\b"
    r"|--git-dir\b|--work-tree\b|\bCDPATH\b"
)

_ASSIGNMENT_RE = re.compile(r"\w+=")

_DIR_CHANGERS = frozenset({"cd", "pushd", "popd"})

# Commands that run text in THIS shell, where a `cd` would stick. `.` does too,
# but only counts where a command starts; anywhere else it is just the current
# directory (`git add .`).
_SAME_SHELL_RUNNERS = frozenset({"source", "eval", "trap"})

# Words that can stand in front of a command in the same shell.
_COMMAND_PREFIXES = frozenset({
    "if", "then", "else", "elif", "do", "while", "until", "!", "{",
    "command", "builtin", "exec", "time", "nohup",
})

# Anything that can run a command more than once.
_REPEATS_RE = re.compile(
    r"(?:^|[\n;&|(){}`])\s*(?:for|while|until|select|function)\b|\(\s*\)"
)

# Any stash command that can change the stash list; list and show only read it.
_GIT_STASH_ANY_RE = re.compile(_GIT + r"stash\b(?!\s+(?:list|show)\b)")

# A word that means the same thing to bash as it reads here: no expansion,
# no quoting left over.
_LITERAL_WORD_RE = re.compile(r"[^$`~*?\[\]{}'\"\\]+")


def _command_spans(masked):
    """Return (start, end) for each simple command in *masked*: the text between breaks."""
    spans, start = [], 0
    for brk in _COMMAND_BREAK_RE.finditer(masked):
        if brk.start() > start:
            spans.append((start, brk.start()))
        start = brk.end()
    if start < len(masked):
        spans.append((start, len(masked)))
    return spans


def _worktree_at(path):
    """Return the LinkedWorktree containing *path*, or None.

    None for the main working tree (its git dir is the common dir), for a path
    outside any repository, and whenever git does not answer.
    """
    out = _run_git(path, ["rev-parse", "--path-format=absolute",
                          "--show-toplevel", "--git-dir", "--git-common-dir"])
    lines = out.splitlines() if out else []
    if len(lines) != 3:
        return None
    top, git_dir, common_dir = lines
    if os.path.realpath(git_dir) == os.path.realpath(common_dir):
        return None
    # The full ref, not --short: that one says heads/<b> when a tag shares the name.
    ref = (_run_git(top, ["symbolic-ref", "-q", "HEAD"]) or "").strip()
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None
    return LinkedWorktree(os.path.realpath(top), branch)


def _inside(path, top):
    return os.path.commonpath([path, top]) == top


def _nested_repo_between(path, top):
    """Return True if a directory from *path* up to, not including, *top* holds a .git."""
    while path != top and _inside(path, top):
        if os.path.lexists(os.path.join(path, ".git")):
            return True
        path = os.path.dirname(path)
    return False


def _follow_dir(here, target, top):
    """Return where `cd <target>` from *here* lands, or None if not provably in *top*.

    *here* is None once the walk no longer knows the exact directory (after a
    popd): from there only an absolute target can be followed. Landing in a
    repository nested inside the worktree counts as leaving it, since git
    would act on that repository instead.
    """
    if not _LITERAL_WORD_RE.fullmatch(target) or ".." in target.split("/"):
        return None
    if here is None and not os.path.isabs(target):
        return None
    landed = os.path.realpath(os.path.join(here or "/", target))
    if not _inside(landed, top) or _nested_repo_between(landed, top):
        return None
    return landed


def _cd_target(tokens):
    """Return the one directory a `cd`/`pushd` names, "" for none, None if unreadable."""
    args = [token for token in tokens[1:] if token not in ("-L", "-P", "-e", "-@", "--")]
    if not args:
        return ""
    if len(args) > 1 or args[0] == "-":
        return None
    return args[0]


def _leading_cd(command, masked, spans, cwd):
    """Return the directory a leading `cd <dir>` moves the whole call into, or None.

    Only a cd the rest of the call provably runs after: first thing on the
    line, not in a pipeline or in the background (both run it in a subshell),
    and into a directory that exists and can be entered, so that it cannot
    fail and leave the rest running where the call started. No `..`: bash
    resolves it against the path as typed, not the one symlinks lead to.
    """
    if not spans or spans[0][0] != 0:
        return None
    start, end = spans[0]
    tokens = _tokenize_segment(command[start:end])
    if not tokens or tokens[0] != "cd":
        return None
    after = masked[end:end + 2]
    if (after.startswith("|") and after != "||") or (after.startswith("&") and after != "&&"):
        return None
    target = _cd_target(tokens)
    if not target or not _LITERAL_WORD_RE.fullmatch(target) or ".." in target.split("/"):
        return None
    landed = os.path.realpath(os.path.join(cwd, target))
    return landed if os.path.isdir(landed) and os.access(landed, os.X_OK) else None


def _command_worktree(command, cwd):
    """Return the LinkedWorktree every command in *command* runs inside, or None."""
    if not cwd or not os.path.isabs(cwd) or os.environ.get("CDPATH"):
        return None
    command = _command_text(command)
    if _RELOCATE_RE.search(command):
        return None
    masked = _mask_quoted(command)
    spans = _command_spans(masked)
    here = _leading_cd(command, masked, spans, cwd)
    if here:
        spans = spans[1:]  # already followed
    else:
        here = os.path.realpath(cwd)
    worktree = _worktree_at(here)
    if worktree is None or not _inside(here, worktree.top):
        return None
    for start, end in spans:
        tokens = _tokenize_segment(command[start:end])
        while tokens and _ASSIGNMENT_RE.match(tokens[0]):
            tokens.pop(0)
        if _SAME_SHELL_RUNNERS & set(tokens):
            return None
        while tokens and tokens[0] in _COMMAND_PREFIXES:
            tokens.pop(0)
        if not tokens:
            continue
        verb = tokens[0]
        if verb == "." or _DIR_CHANGERS & set(tokens[1:]):
            return None
        if verb in _DIR_CHANGERS:
            target = "" if verb == "popd" else _cd_target(tokens)
            if target is None or (verb == "cd" and target == ""):
                return None  # a bare cd goes to $HOME
            if verb == "popd" or target == "" or re.fullmatch(r"[+-]\d+", target):
                # Back to, or around, places this call already went: all in
                # the worktree, but no longer one this walk can name.
                here = None
            else:
                here = _follow_dir(here, target, worktree.top)
                if here is None:
                    return None
        elif os.path.basename(verb) == "git":
            # `git -C <dir>` moves only this one git; each has to stay inside.
            at, index = here, 1
            while index < len(tokens) and tokens[index].startswith("-"):
                if tokens[index] == "-C" and index + 1 < len(tokens):
                    at = _follow_dir(at, tokens[index + 1], worktree.top)
                    if at is None:
                        return None
                index += 2 if tokens[index] in _GIT_GLOBAL_VALUE_OPTS else 1
    return worktree


def _path_slug(path):
    """Return *path* the way CC names a project directory after it."""
    return re.sub(r"[^A-Za-z0-9-]", "-", path)


def _is_session_checkout(worktree, transcript_path):
    """Return True unless *worktree* is provably not where this session started.

    Transcripts live at <config>/projects/<slug of the start directory>/…,
    subagents' included. A start directory inside the worktree counts too.
    """
    parts = (transcript_path or "").replace("\\", "/").split("/")
    starts = [parts[i + 1] for i in range(len(parts) - 1)
              if parts[i] == "projects" and parts[i + 1].startswith("-")]
    if not starts:
        return True
    start, top = starts[-1], _path_slug(worktree.top)
    return start == top or start.startswith(top + "-")


def _names_other_branch(name, worktree):
    """Return True unless *name* is provably not a branch other than the worktree's own.

    Checking one out moves the worktree onto a shared branch. A name git
    cannot answer for, or one that is not literal, counts as one.
    """
    if name == worktree.branch:
        return False
    if name == "-" or "@{" in name or not _LITERAL_WORD_RE.fullmatch(name):
        return True
    out = _run_git(worktree.top, ["for-each-ref", "--format=%(refname)",
                                  "refs/heads/" + name])
    return out is None or bool(out.strip())


_CHECKOUT_WORKTREE_VALUE_OPTS = _CHECKOUT_VALUE_OPTS | {"-b", "-B", "--orphan"}
_SWITCH_VALUE_OPTS = frozenset({
    "-c", "-C", "--create", "--force-create", "--orphan", "--conflict",
})
_REBASE_VALUE_OPTS = frozenset({
    "--onto", "-s", "--strategy", "-X", "--strategy-option", "-x", "--exec",
})
# Rebase options that reach past the worktree's own branch.
_REBASE_REACHING_OPTS = frozenset({
    "--exec", "--interactive", "--edit-todo", "--update-refs",
})

# A stash subject names the branch it was made on: "On <branch>: <message>",
# or "WIP on <branch>: <sha> <subject>" when no message was given. A branch
# name cannot contain a colon.
_STASH_SUBJECT_RE = re.compile(r"(?:WIP on|On) ([^:]+): ")
_STASH_REF_RE = re.compile(r"stash@\{(\d+)\}|(\d+)")


def _checkout_stays(args, worktree):
    flags, pre, _post, saw_dashdash = _split_operands(args, _CHECKOUT_WORKTREE_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    if "B" in shorts:
        return False
    if "b" in shorts or names & {"--orphan", "--detach"}:
        return True
    # With `--`, what comes first is a tree-ish to restore paths from.
    if saw_dashdash or not pre:
        return True
    return not _names_other_branch(pre[0], worktree)


def _switch_stays(args, worktree):
    flags, pre, _post, _ = _split_operands(args, _SWITCH_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    if "C" in shorts or "--force-create" in names:
        return False
    if "c" in shorts or "d" in shorts or names & {"--create", "--orphan", "--detach"}:
        return True
    return bool(pre) and not _names_other_branch(pre[0], worktree)


def _rebase_stays(args, worktree):
    flags, pre, post, _ = _split_operands(args, _REBASE_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    if names & _REBASE_REACHING_OPTS or "x" in shorts or "i" in shorts:
        return False
    # A second operand, or the only one after --root, is a branch to check out.
    if len(pre) + len(post) >= (1 if "--root" in names else 2):
        return False
    if "--no-update-refs" in names:
        return True
    setting = _run_git(worktree.top, ["config", "--type=bool", "--default=false",
                                      "--get", "rebase.updateRefs"])
    return setting is not None and setting.strip() == "false"


def _stash_drop_is_own(word, args, worktree):
    if "drop" not in word or worktree.branch is None:
        return False
    refs = [arg for arg in args if arg not in ("-q", "--quiet")]
    if len(refs) > 1:
        return False
    match = _STASH_REF_RE.fullmatch(refs[0] if refs else "stash@{0}")
    if not match:
        return False
    ref = "stash@{%s}" % (match.group(1) or match.group(2))
    subject = _run_git(worktree.top, ["log", "-1", "--format=%s", ref, "--"])
    made_on = _STASH_SUBJECT_RE.match(subject or "")
    return bool(made_on) and made_on.group(1) == worktree.branch


def _stash_drop_alone(command):
    """Return True if the drop is the call's one stash change, and nothing repeats it."""
    masked = _mask_quoted(_command_text(command))
    return len(_GIT_STASH_ANY_RE.findall(masked)) == 1 and not _REPEATS_RE.search(masked)


# git options that change nothing about what a command does or where it runs,
# besides `-C`, which _command_worktree follows.
_PLAIN_GIT_OPTS = frozenset({"--no-pager", "-P", "--no-optional-locks", "--no-advice"})


def _plain_git_options(word):
    """Return True if the options between `git` and its subcommand in *word* are harmless.

    `-c` is not: it can set core.worktree, rebase.updateRefs, sequence.editor
    or an alias for the subcommand itself.

    Split as the shell splits, like _command_worktree: split on spaces, the
    `-C a\\ b` of `git -C a\\ b -c core.fsmonitor=x reset --hard` took `b` for
    the next option and let the `-c` through. Text shlex cannot split is not
    read as harmless.
    """
    try:
        tokens = shlex.split(word)[1:]
    except ValueError:
        return False
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        if tokens[index] == "-C":
            index += 2
        elif tokens[index] in _PLAIN_GIT_OPTS:
            index += 1
        else:
            return False
    return True


def check_linked_worktree_rule(description, command, worktree):
    """Return True if every match of rule *description* stays inside *worktree*.

    *worktree* is what _command_worktree found for the whole call. Each match
    has to be a git command at the very start of its simple command — not
    behind an assignment, and not an argument of `find -execdir`, `xargs` or
    `sudo` — whose form reaches no further. Its arguments are read off the
    masked text, so a quoted one is opaque, and a check that needs its value
    does not exempt.
    """
    found = _rule_commands(command, description)
    if not found:
        return False
    if description == GIT_STASH_RULE and not _stash_drop_alone(command):
        return False
    for before, word, after in found:
        if before.strip() or not _plain_git_options(word):
            return False
        args = _TOKEN_RE.findall(_REDIRECT_STRIP_RE.sub(" ", after))
        if description == GIT_CHECKOUT_RULE and not _checkout_stays(args, worktree):
            return False
        if description == GIT_SWITCH_RULE and not _switch_stays(args, worktree):
            return False
        if description == GIT_REBASE_RULE and not _rebase_stays(args, worktree):
            return False
        if description == GIT_STASH_RULE and not _stash_drop_is_own(word, args, worktree):
            return False
    return True


# Rules a more precise check can retire for one command, keyed by the rule's
# description. Each check sees the whole command and returns True only when it
# has cleared every match of its rule.
RULE_EXEMPTIONS = {
    HTTP_SUBMIT_RULE: check_local_http,
    PERMISSION_CHANGE_RULE: check_exec_bit_chmod,
    SYSTEMCTL_RULE: check_managed_systemctl,
}


# ── Sensitive file patterns (for Read/Edit/Write tool guards) ───────────────
# Each is (compiled_regex, description). Matched against the file_path.

SENSITIVE_FILE_PATTERNS = [
    (re.compile(r"~/\.\S*(ssh|aws|gnupg|kube)/"), "sensitive dotfile directory"),
    *(_ENV_FILE_PATTERNS if ENV_PROTECTION else []),
    (re.compile(r"(^|/)(\.netrc|\.npmrc|\.pypirc)$"), "credential file"),
    (re.compile(r"(^|/)id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$"), "SSH key"),
    (re.compile(r"(^|/)credentials(\.json)?$"), "credentials file"),
    (re.compile(r"(^|/)\.git-credentials$"), "git credentials"),
    *(_PGPASS_FILE_PATTERNS if PGPASS_PROTECTION else []),
    (re.compile(r"(^|/)\.my\.cnf$"), "MySQL config (may contain passwords)"),
    (re.compile(r"(^|/)\.docker/config\.json$"), "Docker registry credentials"),
    (re.compile(r"(^|/)\.htpasswd$"), "web server password file"),
    (re.compile(r"\.(pem|key)$"), "TLS certificate/private key"),
]


# ── Command size ────────────────────────────────────────────────────────────
# The checks read a command in time linear in its length, with known
# exceptions that are quadratic: backticks interleaved with the command a rule
# reads (`` git push `git push `git push … ``, see _cmd_arg), and chains of
# assignments behind the command-start anchor (`a=|a=|…`). With a nested shell
# in the call, check_command reads three copies, so the worst of them took
# 3 seconds at 10,000 characters and 12 at 20,000, and a hook that runs past
# Claude Code's timeout decides nothing. A command over this length asks
# before any check reads it. It is counted after heredoc bodies are dropped,
# so a file written through a heredoc does not count; ordinary commands run
# to a few hundred characters.
MAX_CHECKED_COMMAND = 10_000


def check_command_size(command):
    """Return the length of *command* as the checks read it, if that is over the limit.

    Returns None for a command within MAX_CHECKED_COMMAND.
    """
    if len(command) <= MAX_CHECKED_COMMAND:  # dropping bodies only shortens it
        return None
    length = len(_command_text(command))
    return length if length > MAX_CHECKED_COMMAND else None


def check_command(command, skip_descriptions=()):
    """Check command against category rules.

    Quoted text is data, not syntax: a grep whose search pattern contains
    "rm -rf" is not a recursive rm. Every rule in CATEGORIES matches a command
    verb together with its flags or subcommand, never a bare operand, so a
    quoted span can never carry the part a rule needs to match — masking it
    costs the rules nothing and retires a whole class of false positive.
    Nested shell invocations are the exception, since there the quoted string
    IS the command: then the raw text and the nested shell's view
    (_mask_nested_quoted) are read too, and a match in any of them counts.
    check_write_targets and check_exit_code_masking make the same trade with
    the raw text alone.

    The one rule that does read an operand is _ENV_RULES' `> ….env` redirect;
    see the note there before enabling ENV_PROTECTION.

    *skip_descriptions* drops rules a more precise stage has already judged —
    only check_worktree_destruction uses it, to keep the broad checkout rule
    from asking about a restore it has proved is a no-op.

    Returns (description, category, matched_text) or None.
    """
    command = _command_text(command)
    # With a nested shell, the masked copy alone hides the commands in its
    # strings, and the raw copy alone ends a command at any quoted `;` —
    # `eval "$(ssh-agent -s)" && curl -H 'a; b' -X POST …` read no -X. So all
    # three copies are read: masked, raw, and the nested shell's view.
    # Masking is length-preserving, so a match found in any copy slices the
    # real text out of the original for reporting.
    copies = [_mask_quoted(command)]
    if _SHELL_INVOKER_RE.search(command):
        copies += [command, _mask_nested_quoted(command)]
    for compiled_re, description, category in RULES:
        if description in skip_descriptions:
            continue
        for scanned in copies:
            match = compiled_re.search(scanned)
            if match:
                return (description, category, command[match.start():match.end()])
    return None


def check_file_path(file_path):
    """Check if a file path matches sensitive file patterns.

    Returns (description,) or None.
    """
    for compiled_re, description in SENSITIVE_FILE_PATTERNS:
        if compiled_re.search(file_path):
            return (description,)
    return None


# ── Pattern-position exemption ──────────────────────────────────────────────
# This guard strips quotes rather than masking them, so that a quoted path
# (`cat "~/.ssh/id_rsa"`) is still caught. The cost is that a search tool's
# pattern reads as a path: `grep id_rsa src/` searches FOR the name, it does
# not read the key. The discriminator is argument position, not quoting —
# quoting cannot tell a pattern from a path, but position can, and it lands the
# right way round either way: in `grep pattern ~/.ssh/id_rsa` the key is an
# operand and stays guarded, while in `grep ~/.ssh/id_rsa file` the key-shaped
# string really is just the text being searched for.

# Tools whose first non-flag argument is a pattern or script, not a path.
_PATTERN_ARG_TOOLS = re.compile(r"^(?:grep|egrep|fgrep|rg|ag|ack|sed|awk|jq)$")

# Tools whose arguments are all literal data and never paths.
_DATA_ARG_TOOLS = re.compile(r"^(?:echo|printf)$")

# -e/--regexp supplies the pattern itself, so the pattern position moves to
# that flag's value and no positional argument is exempt.
_PATTERN_FLAG_RE = re.compile(r"^(?:-e|--regexp)(?:=|$)")

# -f/--file reads the patterns from a FILE, so that argument is a real path and
# nothing in the segment is exempt.
_PATTERN_FILE_FLAG_RE = re.compile(r"^(?:-f|--file)(?:=|$)")

# Flags whose value is a separate following token, which would otherwise be
# mistaken for the pattern position (`grep -A 5 id_rsa f`). Enumerated rather
# than inferred: guessing "a number is not a pattern" would silently exempt a
# real path in `grep 5 ~/.ssh/id_rsa`.
_VALUE_FLAG_RE = re.compile(
    r"^(?:-[ABCm]|--(?:after-context|before-context|context|max-count))$"
)

# A leading `FOO=1 grep …` assignment belongs to the command that follows it.
_ASSIGN_TOKEN_RE = re.compile(r"^\w+=\S*$")


def _exempt_token_spans(segment, offset):
    """Yield (start, end) spans of tokens in *segment* that hold pattern or
    script data rather than a path.

    Spans are absolute offsets into the command *segment* was sliced from.
    Whole tokens are yielded: a glued `--regexp=~/.ssh/id_rsa` is a pattern in
    its entirety.
    """
    tokens = [(offset + m.start(), offset + m.end(), m.group())
              for m in _TOKEN_RE.finditer(segment)]

    index = 0
    while index < len(tokens) and _ASSIGN_TOKEN_RE.match(tokens[index][2]):
        index += 1
    if index >= len(tokens):
        return

    command_word = os.path.basename(tokens[index][2])
    rest = tokens[index + 1:]

    if _DATA_ARG_TOOLS.match(command_word):
        for start, end, _ in rest:
            yield (start, end)
        return

    if not _PATTERN_ARG_TOOLS.match(command_word):
        return

    # Patterns read from a file: the argument is a path, exempt nothing.
    if any(_PATTERN_FILE_FLAG_RE.match(text) for _, _, text in rest):
        return

    flagged = False
    for position, (start, end, text) in enumerate(rest):
        if not _PATTERN_FLAG_RE.match(text):
            continue
        flagged = True
        if "=" in text:
            yield (start, end)
        elif position + 1 < len(rest):
            yield (rest[position + 1][0], rest[position + 1][1])
    if flagged:
        return

    # No pattern flag, so the first argument that is neither a flag nor a
    # flag's separate value is the pattern.
    position = 0
    while position < len(rest):
        text = rest[position][2]
        if _VALUE_FLAG_RE.match(text):
            position += 2
            continue
        if text.startswith("-") and text != "-":
            position += 1
            continue
        yield (rest[position][0], rest[position][1])
        return


def check_sensitive_in_command(command):
    """Check if a Bash command references sensitive file paths.

    Tokenises the command on whitespace and shell operators, strips quotes
    and shell punctuation, and tests each token against SENSITIVE_FILE_PATTERNS.
    Tokens holding a search pattern or script rather than a path are skipped
    (see _exempt_token_spans); every other token stays guarded.

    Returns (description, matched_path) or None.
    """
    command = _command_text(command)
    # Segment and token boundaries are read off the masked copy so a quoted `;`
    # or a space inside a pattern does not split, but each token is sliced from
    # the original. Nested shell invocations are scanned raw — there the quoted
    # string is itself a command, and its leading word is `bash`, so no
    # exemption applies and every token is checked.
    scanned = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)

    for segment in _SEGMENT_RE.finditer(scanned):
        exempt = set(_exempt_token_spans(segment.group(), segment.start()))
        for match in _TOKEN_RE.finditer(segment.group()):
            span = (segment.start() + match.start(), segment.start() + match.end())
            if span in exempt:
                continue
            token = command[span[0]:span[1]].strip(_TOKEN_STRIP_CHARS)
            if not token:
                continue
            for compiled_re, description in SENSITIVE_FILE_PATTERNS:
                if compiled_re.search(token):
                    return (description, token)
    return None


def _resolved_path_allowed(resolved, project_root):
    """Return True if *resolved* (an already-expanded absolute path) is allowed
    by the out-of-project guard.

    A path is allowed when it is:
      * inside the project root,
      * a known-safe absolute path (/dev/null, /tmp, …), or
      * inside the workspace directory (the parent of the project root) — i.e. a
        sibling project — UNLESS that workspace is ``$HOME`` or the filesystem
        root, where "sibling" would mean "all of $HOME" / "everything" and is
        too broad to allow implicitly.

    Shared by the Read/Edit/Write guard and the Bash write-target guard so that
    ``~/``, ``../`` and absolute paths are judged identically — only the
    description string differs by caller.
    """
    if resolved.startswith(project_root + "/") or resolved == project_root:
        return True
    if any(resolved == safe or resolved.startswith(safe + "/")
           for safe in SAFE_ABSOLUTE_PATHS):
        return True
    workspace = os.path.dirname(project_root)
    if workspace and workspace not in ("/", _HOME_DIR) and resolved.startswith(workspace + "/"):
        return True
    return False


def check_file_outside_project(file_path, project_root):
    """Check if a file path is outside the project root.

    Returns a description string or None. Tilde, parent-traversal and absolute
    paths are each expanded to an absolute path and judged by the shared
    _resolved_path_allowed check; only the description differs. Bare relative
    paths are assumed in-project (CC resolves them against the project-root cwd).
    """
    if not project_root:
        return None

    project_root = project_root.rstrip("/")

    # Claude's own internal files (memory, settings) are always allowed
    if _is_claude_internal(file_path):
        return None

    # Expand ~ and judge the resolved path
    if file_path.startswith("~/") or file_path == "~":
        resolved = os.path.expanduser(file_path)
        if not _resolved_path_allowed(resolved, project_root):
            return f"home directory path: {file_path}"
        return None

    # Parent traversal — resolve to absolute and judge
    if "../" in file_path:
        resolved = os.path.realpath(file_path)
        if not _resolved_path_allowed(resolved, project_root):
            return f"parent directory traversal: {file_path}"
        return None

    # Absolute paths
    if file_path.startswith("/"):
        if not _resolved_path_allowed(file_path, project_root):
            return f"path outside project root: {file_path}"

    return None


def _candidate_write_targets(command):
    """Yield tokens that are genuine write targets in *command*.

    Only these positions can write outside the project, so only these are
    worth checking. A path-shaped substring anywhere else — a grep/sed
    pattern, a regex, a URL, an HTTP request path in a log line — is not a
    write and must not be flagged.

    Sources:
      1. Redirect targets — the file after ``>`` / ``>>`` (fd redirects like
         ``2>`` and fd duplications like ``>&2`` are excluded).
      2. Arguments of file-modifying commands (rm/mv/cp/mkdir/touch/tee),
         scanned per shell-segment (split on ``; | & newline``) so only the
         segment that actually runs the command is examined — a path-pattern
         sitting in an unrelated segment is never treated as a write target.

    Both sources match against the quote-masked command: shell punctuation
    inside a string literal is not shell syntax, so ``sed '/<tag>/,/<\\/tag>/p'``
    yields no redirect and ``git commit -m "rm /etc/x"`` runs no rm. Every
    token is sliced back out of the original command by offset, so a quoted
    write target keeps its real text (spaces included).
    """
    masked = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)

    # 1. Redirect targets (scanned across the whole command)
    for match in _REDIRECT_TARGET_RE.finditer(masked):
        yield command[match.start(1):match.end(1)]

    # 2. File-modifying command arguments (per segment)
    for segment in _SEGMENT_RE.finditer(masked):
        if FILE_MODIFYING_CMDS.search(segment.group()):
            for token in _TOKEN_RE.finditer(segment.group()):
                start = segment.start() + token.start()
                yield command[start:start + len(token.group())]


def check_outside_project(command, project_root):
    """Check if command writes to a path outside the project root.

    Only genuine write targets are examined (see _candidate_write_targets);
    path-shaped substrings elsewhere in the command are ignored.

    Returns (description, matched_path) or None.
    """
    if not project_root:
        return None

    # Strip heredoc bodies so their content isn't parsed as paths
    command = _command_text(command)

    # Normalize project root (remove trailing slash)
    project_root = project_root.rstrip("/")

    for token in _candidate_write_targets(command):
        # Strip quotes and shell punctuation
        token = token.strip(_TOKEN_STRIP_CHARS)
        if not token:
            continue

        # Claude's own internal files (memory, settings) are always allowed
        if _is_claude_internal(token):
            continue

        # Absolute, ~/, and ../ write targets are each expanded to an absolute
        # path and judged by the shared _resolved_path_allowed check; only the
        # description differs.
        if token.startswith("/"):
            # Skip bare slash tokens (e.g. Python's // operator)
            if token.rstrip("/") == "":
                continue
            if not _resolved_path_allowed(token, project_root):
                return (f"path outside project root: {token}", token)

        elif token.startswith("~/") or token == "~":
            resolved = os.path.expanduser(token)
            if not _resolved_path_allowed(resolved, project_root):
                return (f"home directory path: {token}", token)

        elif "../" in token:
            resolved = os.path.realpath(token)
            if not _resolved_path_allowed(resolved, project_root):
                return (f"parent directory traversal: {token}", token)

    return None


# ── Exit code masking detection ─────────────────────────────────────────────
# A pipeline reports the status of its LAST stage, so `pytest | head` exits 0
# however many tests failed. What makes that worth a deny is not the lost number
# but the false green: the run is reported as passing. So the rule is scoped to
# pipes that drop the output which would have shown the failure, in the pipeline
# the pytest run actually belongs to.

# Sinks that pass the stream through whole. The failure summary still reaches
# the transcript, so the lost status hides nothing.
_PASSTHROUGH_SINK = r"(?:tee|cat|less|more|bat)"

# Commands whose arguments are patterns or paths rather than code to run:
# `grep -rn pytest CLAUDE.md | head` searches for the word, it does not run
# tests. Anchored to the head of a stage, the same command-position reasoning
# as _CMD_START, applied one pipeline stage at a time.
_TEXT_TOOL = (
    r"(?:grep|egrep|fgrep|rg|ag|ack|sed|awk|echo|printf|ls|find|cat|head|tail"
    r"|git|jq|wc|sort|uniq|column|man)"
)

# Status kept by hand: `pipefail` makes $? the first failing stage, PIPESTATUS
# reads the producer's status directly. A bare `echo $?` after a pipe is NOT an
# escape — it reports the sink's status, which is the bug itself.
_PIPESTATUS_RE = re.compile(r"\bpipefail\b|\bPIPESTATUS\b")

# Pipeline boundaries. `||` and `&&` are consumed before the single-character
# class so a lone `|` survives — it is the operator this rule is looking for.
# The `&` of a redirect (`2>&1`, `&>log`) is not a separator; splitting there
# would cut the producer off from its own pipe.
_PIPELINE_SPLIT_RE = re.compile(r"\|\||&&|[;\n]|(?<![>&])&(?![>&])")

_PYTEST_WORD_RE = re.compile(r"\bpytest\b")
# A leading assignment prefix (`FOO=1 pytest`) belongs to the command that
# follows it, so step over it before reading the stage's command word.
_ASSIGN_PREFIX = r"^\s*(?:\w+=\S+\s+)*"
_LEADING_TEXT_TOOL_RE = re.compile(_ASSIGN_PREFIX + _TEXT_TOOL + r"\b")
_PASSTHROUGH_SINK_RE = re.compile(_ASSIGN_PREFIX + _PASSTHROUGH_SINK + r"\b")


def check_exit_code_masking(command):
    """Check if a pytest run's output is piped into a stage that hides failures.

    Returns a reason string or None.
    """
    command = _command_text(command)
    # Quoted text is data: a commit message about this rule is not a test run.
    # Nested shell invocations are the exception — there the quoted string IS
    # the command, so scan it raw (same trade as check_write_targets).
    if not _SHELL_INVOKER_RE.search(command):
        command = _mask_quoted(command)

    if _PIPESTATUS_RE.search(command):
        return None

    for pipeline in _PIPELINE_SPLIT_RE.split(command):
        stages = pipeline.split("|")
        # The last stage's status is the pipeline's own, so only a pytest with
        # a pipe downstream of it loses anything.
        for index, stage in enumerate(stages[:-1]):
            if not _PYTEST_WORD_RE.search(stage):
                continue
            if _LEADING_TEXT_TOOL_RE.search(stage):
                continue  # the word is an argument, not an invocation
            downstream = stages[index + 1:]
            if all(_PASSTHROUGH_SINK_RE.search(s) for s in downstream):
                continue  # nothing dropped, so nothing hidden
            return (
                "Exit code masking — use instead: "
                "pytest --tb=short -q --no-header"
            )
    return None


# ── LLM evaluator framework ──────────────────────────────────────────────────
Evaluator = namedtuple("Evaluator", ["name", "gate", "prompt_builder"])


def _extract_transcript_context(event):
    """Parse the JSONL transcript and return last N user/assistant text messages.

    Returns a formatted string. Returns empty string on any failure.
    """
    transcript_path = event.get("transcript_path", "")
    if not transcript_path:
        return ""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except (OSError, IOError):
        return ""

    messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = entry.get("role")
        if role not in ("user", "assistant"):
            continue
        # Extract text content, skip tool_use/tool_result
        content = entry.get("content", "")
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = " ".join(text_parts)
        if not isinstance(content, str) or not content.strip():
            continue
        truncated = content.strip()[:TRANSCRIPT_MSG_MAX_CHARS]
        messages.append(f"{role}: {truncated}")

    return "\n".join(messages[-TRANSCRIPT_CONTEXT_LINES:])


def _find_claude_cli():
    """Locate the claude CLI binary, checking PATH and common install locations."""
    found = shutil.which("claude")
    if found:
        return found
    # Hook subprocesses may have a stripped PATH — check common locations
    for candidate in [
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _call_haiku(prompt):
    """Call the claude CLI with Haiku model. Returns response text or None.

    ``--no-session-persistence`` matters twice over here, since this runs inside
    the latency path of a tool call: without it every evaluator check persists a
    throwaway session transcript under ~/.claude/projects/ (which session
    pickers scanning that directory then read as a real session), and pays the
    session-setup cost — measured at ~3s of the call. Should a CLI ever reject
    the flag, the non-zero exit lands on the ``return None`` below, which the
    evaluator layer treats as "no verdict" and falls through to asking — more
    prompts, never fewer.
    """
    claude_bin = _find_claude_cli()
    if not claude_bin:
        return None
    try:
        result = subprocess.run(
            [claude_bin, "-p", "--model", HAIKU_MODEL, "--output-format", "json",
             "--no-session-persistence"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=HAIKU_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if data.get("is_error"):
        return None
    return data.get("result", "")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _parse_verdict(response_text):
    """Parse JSON verdict from Haiku response.

    Expects {"verdict": "SAFE|UNSURE|DENY", "reason": "..."}.
    Strips markdown code fences if present.
    Returns None if JSON doesn't parse or verdict field is missing/invalid
    — caller treats None as "fall through to user prompt".
    """
    if not response_text:
        return None
    text = response_text.strip()
    # Strip markdown code fences (```json ... ```)
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    verdict = data.get("verdict", "").upper() if isinstance(data, dict) else None
    if verdict in ("SAFE", "UNSURE", "DENY"):
        return verdict
    return None


def run_evaluators(command, event):
    """Run narrowly-scoped LLM evaluators on the command.

    Returns (decision, trace) where decision is "allow"/"ask"/None.
    - "allow" + trace: evaluator said SAFE
    - "ask" + trace: evaluator fired but returned UNSURE/DENY/error
    - (None, None): no evaluator matched
    """
    for evaluator in EVALUATORS:
        if not evaluator.gate(command, event):
            continue
        ctx = _extract_transcript_context(event)
        prompt = evaluator.prompt_builder(command, ctx, event)
        response = _call_haiku(prompt)
        verdict = _parse_verdict(response)
        tag = f"eval:{evaluator.name}"
        if verdict == "SAFE":
            return ("allow", f"[{tag}→SAFE]")
        label = verdict or "no-response"
        return ("ask", f"[{tag}→{label}]")
    return (None, None)


# ── Evaluator definitions ────────────────────────────────────────────────────

_RM_VARIABLE_RE = re.compile(
    _NOT_FLAG + r'\brm\s+(-\S+\s+)*-\S*[rR]\S*\s+.*(\$\w+|\$\{[^}]+\}|\$\([^)]+\))'
)


def _gate_rm_variable_cleanup(command, event):
    """True if command has recursive rm with shell variables that _is_safe_rm can't resolve."""
    if not _RM_VARIABLE_RE.search(command):
        return False
    # If _is_safe_rm already handles it, no need for LLM
    if _is_safe_rm(command):
        return False
    return True


def _resolve_project_root(event):
    """Return the resolved project root, or empty string if unavailable.

    When the install-time PROJECT_ROOT placeholder is unresolved/empty:
      1. Prefer CLAUDE_PROJECT_DIR — the project root CC exports to hooks. It is
         stable regardless of the session's working directory.
      2. Fall back to the event cwd only when the env var is absent.

    Using the event cwd as the root is wrong when the session was launched from
    (or cd'd into) a subdirectory: the guard would then treat the project's own
    files elsewhere in the tree as out-of-project. CLAUDE_PROJECT_DIR always
    points at the real root, so it takes precedence.
    """
    root = PROJECT_ROOT
    # Skip unresolved install-time placeholder
    if not root or root.startswith("{"):
        root = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or event.get("cwd", "")
    return root


def _prompt_rm_variable_cleanup(command, ctx, event):
    """Build a prompt asking Haiku to resolve rm target paths from context."""
    project_root = _resolve_project_root(event)

    safe_dirs = "/tmp/"
    if project_root:
        safe_dirs += f" and {project_root}"

    prompt = f"""You are a security reviewer for a CLI coding assistant. A command contains `rm` with shell variable substitutions. The deterministic safety check could not resolve the variables.

Your job: resolve the shell variables in the rm command to determine the ACTUAL path being deleted. Only answer SAFE if the resolved path is inside one of these safe directories: {safe_dirs}

Command: {command}

"""
    if ctx:
        prompt += f"""Recent conversation context:
{ctx}

"""
    prompt += f"""Instructions:
1. Look at the command for variable assignments (e.g. DIR=/tmp/foo && rm -rf $DIR)
2. Look at the conversation context for variable definitions
3. Resolve the rm target path from the evidence you find

Verdicts:
- SAFE — the resolved path is inside: {safe_dirs}
- UNSURE — you cannot resolve the variable, or cannot confirm the resolved path is inside a safe directory
- DENY — the resolved path is clearly outside the safe directories listed above

Default to UNSURE if there is any doubt.

Respond with ONLY a JSON object, no other text:
{{"verdict": "SAFE|UNSURE|DENY", "resolved_path": "/the/resolved/path", "reason": "brief explanation"}}"""
    return prompt


_RM_RECURSIVE_RE = re.compile(_NOT_FLAG + r'\brm\s+(-\S+\s+)*-\S*[rR]')


def _gate_rm_user_approved(command, event):
    """True if command has recursive rm with literal paths (no variables).

    The rm-variable-cleanup evaluator handles the variable case.
    This evaluator handles literal in-project paths where the user may have
    explicitly approved the deletion in conversation.
    """
    if not _RM_RECURSIVE_RE.search(command):
        return False
    # Variable paths are handled by rm-variable-cleanup
    if _RM_VARIABLE_RE.search(command):
        return False
    # Already safe (temp dirs)
    if _is_safe_rm(command):
        return False
    # Only fire if we have transcript context to check
    if not event.get("transcript_path"):
        return False
    return True


def _prompt_rm_user_approved(command, ctx, event):
    """Build prompt asking Haiku if user explicitly approved this deletion."""
    project_root = _resolve_project_root(event)

    prompt = f"""You are a security reviewer for a CLI coding assistant. A recursive rm command is about to execute. The deterministic safety check flagged it because the target is not a known temp directory.

Your job: check the conversation context to determine if the USER explicitly requested or confirmed this deletion.

Command: {command}
Project root: {project_root}

"""
    if ctx:
        prompt += f"""Recent conversation context:
{ctx}

"""
    prompt += """Instructions:
1. Check if the user explicitly asked for files/directories to be deleted
2. Check if the assistant listed what would be deleted and the user confirmed (e.g. "yes", "go ahead", "do it")
3. Verify the rm targets match what the user approved

Verdicts:
- SAFE — the user explicitly requested or confirmed this exact deletion
- UNSURE — no clear user approval, or the targets don't match what was discussed
- DENY — the deletion contradicts what the user asked for

Default to UNSURE if there is any doubt.

Respond with ONLY a JSON object, no other text:
{"verdict": "SAFE|UNSURE|DENY", "reason": "brief explanation"}"""
    return prompt


EVALUATORS = [
    Evaluator("rm-variable-cleanup", _gate_rm_variable_cleanup, _prompt_rm_variable_cleanup),
    Evaluator("rm-user-approved", _gate_rm_user_approved, _prompt_rm_user_approved),
]


def _decide(reason, decision="ask"):
    """Print a permissionDecision response and exit."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))


def _ask(reason):
    """Print a permissionDecision: ask response and exit."""
    _decide(reason, "ask")


def _deny(reason):
    """Print a permissionDecision: deny response and exit (no user prompt)."""
    _decide(reason, "deny")


# Permission modes in which this guard stands down. It is the user's safety net
# for bypassPermissions (CC approves everything there), so it stays active in
# that mode — and in any unknown/missing mode (fail safe) — but defers to CC's
# native permission flow in the modes below, which already vet tool calls.
_DEFER_PERMISSION_MODES = frozenset({"default", "plan", "acceptEdits", "auto", "dontAsk"})


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # ── Permission-mode gate ────────────────────────────────────────────
    # Active only in bypassPermissions (and any unknown/missing mode — fail
    # safe). In the modes CC vets itself, stand down: returning with no output
    # is the documented neutral "defer to the normal permission flow" signal.
    if event.get("permission_mode") in _DEFER_PERMISSION_MODES:
        return

    # Best-effort: write edit guard state for statusline badge
    _write_edit_guard_bridge(event)

    # ── Pause latch ─────────────────────────────────────────────────────
    # Checked ahead of stage 0 and of the auto-approve window: an armed window
    # returns "allow", which would otherwise swallow the pause. Sticky, so
    # every guarded call in the session tree asks — including calls from
    # sibling subagents that would sail past a one-shot marker.
    latch = check_pause(event.get("transcript_path", ""))
    if latch:
        _ask(_pause_reason(latch))
        return

    # ── Usage gate ──────────────────────────────────────────────────────
    # Also ahead of the auto-approve window: an armed unattended run is exactly
    # the thing that would otherwise burn the last of a window unsupervised.
    usage = check_usage_gate(event.get("transcript_path", ""))
    if usage:
        _ask(_usage_reason(usage))
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    # ── Stage 0: gate emitter scripts (unless preceded by a command) ──
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if _EMIT_SCRIPT_RE.search(command):
            if _emitter_follows_command(event.get("transcript_path", "")):
                # Extract command name: "... emit-context.py AUTO-DOC" → "AUTO-DOC"
                cmd_match = re.search(r'emit-context\.py\s+(\S+)', command)
                ctx_name = cmd_match.group(1).upper() if cmd_match else "UNKNOWN"
                _write_context_sidecar(event.get("transcript_path", ""), ctx_name)
                _decide(
                    "[permission-guard] Session context emitter — "
                    "auto-approved (slash command active)",
                    "allow",
                )
            else:
                _ask("[permission-guard] Session context emitter — requires human approval")
            return

    # ── Command size ────────────────────────────────────────────────────
    # Ahead of every stage that reads the command, the worktree check below
    # included, so it holds inside the auto-approve window too: a command too
    # long to check in time asks (see MAX_CHECKED_COMMAND).
    if tool_name == "Bash" and tool_input.get("command"):
        size = check_command_size(tool_input["command"])
        if size:
            _ask(f"[permission-guard] Command size: {size:,} characters, over the "
                 f"{MAX_CHECKED_COMMAND:,} the guard can check in time")
            return

    # ── Git worktree destruction ────────────────────────────────────────
    # Ahead of the auto-approve window, and for the same reason the pause latch
    # and the usage gate are: the window exists to skip ROUTINE approvals for
    # the duration of a known command, and an unrecoverable loss of uncommitted
    # work is not routine. Everything else in this guard interrupts something
    # that can be retried; this one cannot. The window still covers the common
    # case, because a restore over a clean path clears here and never prompts.
    #
    # A linked worktree is the exception (see the Linked worktrees section):
    # there the changes at stake are the worktree's own. Resolved at most once
    # per call, and only once something has asked for it, since it runs git.
    worktree_memo = []

    def linked_worktree():
        if not worktree_memo:
            worktree = _command_worktree(tool_input.get("command", ""), event.get("cwd", ""))
            if worktree and _is_session_checkout(worktree, event.get("transcript_path", "")):
                worktree = None
            worktree_memo.append(worktree)
        return worktree_memo[0]

    skip_rules = ()
    if tool_name == "Bash" and tool_input.get("command"):
        verdict = check_worktree_destruction(
            tool_input["command"], _resolve_project_root(event)
        )
        if verdict and verdict[0] == "ask":
            if linked_worktree() is None:
                _ask(f"[permission-guard] Git Worktree Destruction: {verdict[1]}")
                return
        elif verdict:
            skip_rules = (GIT_CHECKOUT_RULE,)

    # ── Session context auto-approve ───────────────────────────────────
    ctx_cmd = check_session_context(event.get("transcript_path", ""))
    if ctx_cmd:
        _update_context_timestamp(event.get("transcript_path", ""))
        _decide(
            f"[permission-guard] Auto-approved by session context MG:{ctx_cmd}",
            "allow",
        )
        return

    # ── Edit guard (manual toggle) ──────────────────────────────────────
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        if check_edit_guard(event.get("transcript_path", "")):
            _deny(
                "[permission-guard] Implementation/edits are not approved yet "
                "by the user."
            )
            return

    # ── Read / Edit / Write tool guard ──────────────────────────────────
    if tool_name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            # 1. Sensitive file patterns
            result = check_file_path(file_path)
            if result:
                _ask(f"[permission-guard] Secrets & Credentials: {result[0]} ({file_path})")
                return
            # 2. Out-of-project path guard
            root = _resolve_project_root(event)
            if root:
                desc = check_file_outside_project(file_path, root)
                if desc:
                    _ask(f"[permission-guard] Out-of-project: {desc}")
                    return
        # File passed all safety checks — approve explicitly so the hook
        # doesn't fall through to CC's default permission mode (which prompts).
        _decide("[permission-guard] In-project file", "allow")
        return

    # ── Bash tool guard ─────────────────────────────────────────────────
    if tool_name != "Bash":
        return

    command = tool_input.get("command", "")
    if not command:
        return

    # 0. Allow rm targeting only temp directories
    if _is_safe_rm(command):
        return

    # 0a. LLM evaluator layer (narrowly-scoped Haiku checks)
    eval_decision, eval_trace = run_evaluators(command, event)
    if eval_decision == "allow":
        _decide(f"[permission-guard] {eval_trace}", "allow")
        return

    # 0b. Block exit code masking (pytest piped to tail/head/grep etc.)
    reason = check_exit_code_masking(command)
    if reason:
        _deny(f"[permission-guard] {reason}")
        return

    # Prefix for eval trace when an evaluator fired but didn't approve
    trace_prefix = f"{eval_trace} " if eval_trace else ""

    # 1. Category rules
    result = check_command(command, skip_rules)
    # An exemption retires its rule and only that rule, so the scan runs again
    # for whatever it was standing in front of (a `sudo`, a pipe-to-shell).
    # Each one is tested only once its rule has matched, which keeps
    # check_local_http's name lookup and the worktree's git calls off every
    # other Bash call. The loop ends because a skipped rule cannot match again.
    def exempt(rule):
        if rule in RULE_EXEMPTIONS and RULE_EXEMPTIONS[rule](command):
            return True
        return (rule in LINKED_WORKTREE_RULES and linked_worktree() is not None
                and check_linked_worktree_rule(rule, command, linked_worktree()))

    while result and exempt(result[0]):
        skip_rules += (result[0],)
        result = check_command(command, skip_rules)
    if result:
        description, category, _matched = result
        _ask(f"[permission-guard] {trace_prefix}{category}: {description}")
        return

    # 2. Sensitive file paths in command arguments
    result = check_sensitive_in_command(command)
    if result:
        description, matched_path = result
        _ask(f"[permission-guard] {trace_prefix}Secrets & Credentials: {description} ({matched_path})")
        return

    # 3. Out-of-project path guard
    root = _resolve_project_root(event)
    if root:
        result = check_outside_project(command, root)
        if result:
            description, _matched_path = result
            _ask(f"[permission-guard] {trace_prefix}Out-of-project: {description}")
            return


if __name__ == "__main__":
    main()
