# Git Worktrees for Parallel Agentic Development

## Problem

Working on multiple tasks in parallel with Claude Code means multiple agents committing to the same branch. Commits from different tasks interleave, making history unreadable and bisection useless. Stashing or sequencing work wastes the parallelism that multiple CC sessions enable.

Git worktrees solve this at the filesystem level — each agent gets an isolated working directory with its own branch — but they need workflow tooling to keep branches synchronized without manual intervention.

## Solution

Three bash scripts + a guard integrated into the existing permission-guard hook:

1. **`worktree-setup.sh`** — creates worktrees from the current branch
2. **`agent-sync.sh`** — bidirectional sync between worktree branch and base branch
3. **`worktree-teardown.sh`** — closes worktrees after work is complete
4. **Worktree guard in `permission-guard.py`** — hard-denies direct git push/pull/merge/checkout in worktrees, forcing agents to use the sync script

## Workflow

### 1. Create — human, from the main worktree

You're on branch `v2` and want to parallelize two tasks.

```bash
./worktree-setup.sh 1 2
```

The script:
- Reads current branch as the base (e.g., `v2`)
- Creates worktrees as sibling directories:
  ```
  git worktree add ../mg-cc-tools-v2-1 -b v2-1 v2
  git worktree add ../mg-cc-tools-v2-2 -b v2-2 v2
  ```
- For each worktree:
  - **Fixes hardcoded absolute paths** in `.claude/` (see [Path Fixup](#path-fixup))
  - Symlinks `temp/` and `data/` back to the main worktree (if they exist) — avoids copying large binary/data files
  - Symlinks `.serena/` back to the main worktree (if it exists) — shares project config and memories (see [Serena Handling](#serena-handling))
  - Runs `uv sync` to create an independent `.venv`
  - Creates `.worktree` marker file (activates the permission-guard worktree rules)
  - Places `agent-sync.sh` at the worktree root
  - Writes worktree instructions into `.worktree` marker file (see [Agent Discovery](#agent-discovery))

You then launch a separate Claude Code session in each worktree directory.

### 2. Work — agent, in the worktree

Normal development. The agent commits to its own branch (`v2-1` or `v2-2`) using standard `git add` + `git commit`. No special workflow.

### 3. Sync — agent, after each logical unit of work

The agent runs `./agent-sync.sh` after every coherent commit or batch of related commits. At minimum every ~15 minutes of active work.

```
Syncing v2-1 → v2

1. git merge v2            ← picks up other agents' work
2. git fetch . v2-1:v2     ← fast-forwards v2 to include this agent's work

SUCCESS: v2 updated with v2-1 changes.
```

**Failure modes the agent handles autonomously:**

| Failure | Cause | Agent action |
|---------|-------|--------------|
| Merge conflict at step 1 | Other agent changed same files | Resolve conflicts, commit, re-run `./agent-sync.sh` |
| Non-fast-forward at step 2 | Other agent updated `v2` between steps 1 and 2 | Re-run `./agent-sync.sh` (step 1 merges the new state) |

Both failures produce clear error messages that tell the agent exactly what to do.

### 4. Close — human (or agent on final task completion)

```bash
./worktree-teardown.sh 1
```

The script:
- Verifies `v2-1` is fully merged into `v2`
- `git worktree remove ../mg-cc-tools-v2-1`
- `git branch -d v2-1` (safe delete — branch is merged)

Symlinks disappear with the directory. No cleanup needed.

### 5. Push to remote — human, from the main worktree

```bash
git push origin v2
```

Always a human decision. Agents never touch the remote.

### How external changes flow in

If someone pushes to `origin/v2`:
1. You pull in the main worktree: `git pull origin v2`
2. Agents pick up changes on their next sync (step 1 merges `v2`)

## The Sync Script

```bash
#!/bin/bash
# agent-sync.sh — Sync current worktree branch with base branch

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH="${CURRENT_BRANCH%-*}"  # v2-1 → v2, v2-2 → v2

if [ "$CURRENT_BRANCH" = "$BASE_BRANCH" ]; then
    echo "ERROR: You are on the base branch ($BASE_BRANCH). Switch to a worktree branch."
    exit 1
fi

# Guard: no uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: Uncommitted changes detected. Commit your work first, then sync."
    exit 1
fi

echo "Syncing $CURRENT_BRANCH → $BASE_BRANCH"

# Merge base into current (pick up other agents' work)
if ! git merge "$BASE_BRANCH" -m "chore: sync $BASE_BRANCH into $CURRENT_BRANCH"; then
    echo "ERROR: Merge conflict! Resolve conflicts, commit, then run ./agent-sync.sh again."
    exit 1
fi

# Fast-forward base to include our work (uses fetch to avoid receive.denyCurrentBranch)
if git fetch . "$CURRENT_BRANCH:$BASE_BRANCH"; then
    echo "SUCCESS: $BASE_BRANCH updated with $CURRENT_BRANCH changes."
else
    echo "ERROR: $BASE_BRANCH has advanced since merge. Run ./agent-sync.sh again to pick up new changes."
    exit 1
fi
```

### Base branch derivation

`${CURRENT_BRANCH%-*}` strips the last `-N` suffix: `v2-1` becomes `v2`, `feature-auth-1` becomes `feature-auth`. This convention means any branch can be parallelized — not just milestone branches.

## Path Fixup

Installed mg-cc-tools commands contain hardcoded absolute paths baked in at install time (e.g., `/home/user/projects/foo/.claude/auto-doc/scripts/add-note.py`). These break when `.claude/` is checked out in a worktree at a different filesystem path.

Rather than rearchitecting the install system, the setup script performs a brute-force fixup after creating each worktree:

```bash
MAIN_ROOT=$(cd "$MAIN_WORKTREE" && pwd)    # e.g., /home/user/projects/foo
WT_ROOT=$(cd "$WORKTREE_DIR" && pwd)       # e.g., /home/user/projects/foo-v2-1

find "$WORKTREE_DIR/.claude" -type f \( -name "*.md" -o -name "*.py" -o -name "*.json" \) \
  -exec sed -i "s|${MAIN_ROOT}|${WT_ROOT}|g" {} +
```

This rewrites every occurrence of the main worktree's absolute path to the new worktree's path. It covers:
- Script invocation paths in command/agent `.md` files (~200 occurrences in a typical install)
- `PROJECT_ROOT` in `permission-guard.py`
- Hook command paths in `settings.json`

What it doesn't need to cover:
- `manifest.json` `source_path` — points to the mg-cc-tools source repo, not the target project. Unchanged.
- Python `__file__` / `sys.path` usage in scripts — these resolve at runtime relative to the script's actual location. Already correct.

### Why this is safe

The replacement is a simple string substitution of one absolute path prefix with another. Both paths share the same parent directory (worktrees are siblings). No regex, no partial matches — the full project root path is unique enough to avoid false positives.

### Teardown: no reverse fixup needed

When a worktree is removed, its entire directory tree is deleted. The rewritten files disappear with it. The main worktree's `.claude/` is untouched.

## Serena Handling

Serena (MCP semantic code server) stores project config, memories, and LSP cache in `.serena/` — which is gitignored and therefore absent in worktrees.

The setup script symlinks `.serena/` back to the main worktree:

```bash
ln -s "$MAIN_WORKTREE/.serena" "$WORKTREE_DIR/.serena"
```

This shares project config (`project.yml`), memories, and LSP cache. The risk of two LSP instances hitting the same cache is low — Serena's cache is read-heavy and regenerated on miss. If cache corruption occurs in practice, the fix is to restart the language server (`restart_language_server` tool) or just accept cold starts per worktree.

Serena's `projects` list in `~/.serena/serena_config.yml` registers projects by absolute path. The worktree path won't be registered. This is acceptable — Serena falls back to the working directory for project detection. If that proves insufficient, the setup script can append the worktree path to the projects list and teardown can remove it.

## Agent Discovery

The `.worktree` marker file doubles as an instruction file. The setup script writes sync workflow instructions into it:

```
This is a git worktree. Branch: v2-1, Base: v2.

RULES:
- Do NOT use git push, git pull, git merge, git rebase, git checkout <branch>, or git switch directly.
- After completing a coherent unit of work, run: ./agent-sync.sh
- Sync at minimum every ~15 minutes of active work.
- If agent-sync.sh reports a merge conflict, resolve it, commit, then run ./agent-sync.sh again.
```

The permission guard reads this file to detect worktree mode. The agent sees these instructions via CLAUDE.md (which can include a note to read `.worktree` if it exists) or through the deny messages from the permission guard when it first attempts a blocked command.

## Permission Guard Integration

The worktree guard integrates into the existing `permission-guard.py` hook. No new hook registration needed.

### Detection

The setup script creates a `.worktree` marker file (gitignored) in each worktree. The hook checks for this file. The marker's existence IS the worktree indicator — no configuration, no settings files.

### Pipeline position

The worktree check runs **before** the existing category checks. The existing categories `_ask()` for commands like `git merge` (user gets an approval prompt). In worktree mode, we want a hard `_deny()` with an instructive error message instead. Early placement prevents the category checks from offering a bypass.

### Blocked commands (hard deny)

| Pattern | Reason | Error message |
|---------|--------|---------------|
| `git push` | Must go through sync script | "Use ./agent-sync.sh" |
| `git pull` | Sync script handles integration | "Use ./agent-sync.sh" |
| `git merge` | Must go through sync script | "Use ./agent-sync.sh" |
| `git rebase` | Would rewrite shared history | "Forbidden in worktrees" |
| `git checkout` (branch form) | Must stay on worktree branch | "Forbidden in worktrees" |
| `git switch` | Same as above | "Forbidden in worktrees" |

### Allowed commands (no change)

`git add`, `git commit`, `git status`, `git diff`, `git log`, `git blame`, `git show`, `git stash`, `git fetch`, `git checkout -- <file>` (file restore).

`git fetch` is read-only (updates remote tracking refs without touching the working directory) and harmless in worktrees.

The existing pattern `r"\bgit\s+checkout\s+(?!--)"` already distinguishes branch checkout from file restore. The worktree guard reuses this distinction.

### Why the sync script isn't blocked

The hook intercepts Bash **tool calls** — the top-level command CC executes. When the agent runs `./agent-sync.sh`, the hook sees `./agent-sync.sh` as the command. The `git merge` and `git fetch .` inside the script are subprocesses — they never pass through the hook.

## Symlink Strategy

**Positive list only.** The setup script symlinks these directories back to the main worktree if they exist:

| Directory | Rationale |
|-----------|-----------|
| `temp/` | Scratch/binary files, often large, read-heavy |
| `data/` | Data files, often large, read-heavy |
| `.serena/` | Project config, memories, LSP cache — see [Serena Handling](#serena-handling) |

Everything else is independent per worktree. In particular:

| Directory | Why NOT symlinked |
|-----------|-------------------|
| `.venv/` | Embeds absolute paths in shebangs and activation scripts — must be per-worktree |
| `node_modules/` | Same path-embedding issue |
| `.claude/` | Tracked in git — worktrees get their own copy automatically. Hardcoded paths are fixed up by the setup script (see [Path Fixup](#path-fixup)). Not symlinked because agents write to settings/tasks concurrently. |

## What the History Looks Like

```
v2:    A ── B ── C ── merge ── F ── G ── merge ── ...
                 ↑                       ↑
v2-1:  A ── B ── C                       G    (agent 1's work)
v2-2:  A ── D ── E ── merge ──── F             (agent 2's work)
```

Each commit on `v2` is attributable to exactly one agent. Merge commits are the sync points. `v2` is always the union of all completed work.

## Files Changed

| File | Change |
|------|--------|
| `worktree/worktree-setup.sh` | **New.** Create worktrees, symlinks, venv, marker, sync script. |
| `worktree/agent-sync.sh` | **New.** Bidirectional sync with base branch. |
| `worktree/worktree-teardown.sh` | **New.** Verify merged, remove worktree, delete branch. |
| `permission-hooks/hooks/permission-guard.py` | **Modified.** Add worktree guard block (marker detection + blocked patterns + `_deny()`). |
| `permission-hooks/hooks/tests/test_permission_guard.py` | **Modified.** Tests for worktree guard. |
| `.gitignore` | **Modified.** Add `.worktree` marker file and `agent-sync.sh`. |

## Design Decisions

### D1: Bash scripts, not Python

The setup, sync, and teardown scripts are short, linear, git-command-heavy sequences. Bash is the natural fit — no parsing, no data structures, just sequential commands with error handling. The guard logic is Python because it's a new function in an existing Python file.

### D2: Hard deny, not ask

The existing permission-guard uses `_ask()` for dangerous git commands (user gets an approval prompt). For worktrees, we use `_deny()` — a hard block with no override. Rationale: the agent should never directly merge or push in a worktree, even if the user clicks "approve." The sync script is the only correct path. A `_deny()` with a clear error message is more helpful than an `_ask()` that leads to broken state if approved.

### D3: Marker file, not CLAUDE.md modification

Options considered:
1. Append rules to CLAUDE.md + `git update-index --skip-worktree` — works but magical, easy to forget the skip-worktree flag
2. Write to `.claude/settings.local.json` — requires knowing the exact settings schema, fragile
3. **Marker file (`.worktree`) detected by existing hook** — no tracked files modified, no settings changes, the hook's presence in all installs means it just works

Option 3 is the simplest and most transparent.

### D4: Symlink positive list, not negative list

Only symlink explicitly listed directories (`temp/`, `data/`). Default is "don't symlink." This avoids accidentally sharing directories that embed paths (`.venv`), have concurrent write issues (`.claude`), or contain platform-specific artifacts (`node_modules`).

### D5: Base branch derived from branch name, not stored

`${CURRENT_BRANCH%-*}` strips the last `-N` suffix. No config file, no marker content, no setup-time recording. The convention is: `<base>-<N>` is a worktree branch for `<base>`. This means worktree branches must follow this naming convention — enforced by the setup script.

### D6: `git fetch .` instead of `git push .` for base branch update

The sync script uses `git fetch . v2-1:v2` instead of `git push . v2-1:v2`. Both update a local ref, but `git push .` goes through the receive-side machinery and is blocked by `receive.denyCurrentBranch` when the target branch is checked out in another worktree (which `v2` always is — it's checked out in the main worktree). `git fetch .` bypasses this check because it operates on the fetch side. The fast-forward safety is preserved: `git fetch` refuses non-fast-forward updates by default.

The trade-off: updating `v2`'s ref while the main worktree has it checked out means the main worktree's working directory falls behind its own HEAD. This is harmless — the human isn't actively developing in the main worktree during parallel work, and `git status` will show the state clearly. A `git checkout v2` or `git reset --hard v2` in the main worktree after teardown brings everything in sync.

### D7: Path fixup over install architecture change

The install scripts bake absolute paths into `.claude/` files at install time. Rather than changing this to relative paths (which would require validating that CC always runs from project root, updating every install script, and changing how scripts resolve imports), the setup script does a single `sed` pass replacing the main worktree's path with the new worktree's path. This is a 3-line fix that handles ~200+ path occurrences and requires zero changes to existing tooling.

### D8: Merge-heavy history, squash on merge to main

The sync workflow creates merge commits at each sync point. With 2 agents syncing every ~15 minutes over a 2-hour session, that's ~16 merge commits. This is a conscious trade-off: merge commits preserve the exact point where agents integrated, making the parallel workflow auditable. The expected cleanup path is squash-merge when the feature branch merges to `main`.

## Out of Scope

- **Remote push from agents** — always a human action from the main worktree
- **Automatic sync scheduling** — agents sync manually; a cron/timer would add complexity without clear benefit since agents need to commit before syncing anyway
- **More than ~3 parallel worktrees** — merge frequency increases quadratically; the workflow is designed for 2-3 concurrent agents, not 10
- **Cross-repository worktrees** — worktrees are for branches within one repo
- **Claude Code command wrapper** — the scripts are standalone bash; no `/mg:worktree` command needed in v1
