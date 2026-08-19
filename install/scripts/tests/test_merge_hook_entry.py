"""Tests for merge-hook-entry.py.

The bugs this script replaces were all invisible because the logic lived in
markdown fences where nothing could run it. So the cases below are written
against the specific failures found in the four hand-rolled merges, not just
against the happy path.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "merge-hook-entry.py"


def run(*args):
    """Invoke the script as a subprocess, the way post-install.md does."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def base_args(settings, mode="project"):
    return [
        "--settings",
        str(settings),
        "--install-mode",
        mode,
        "--hook-rel-path",
        ".claude/transcript/hooks/inject-transcript-path.py",
        "--hook-abs-path",
        "/abs/target/.claude/transcript/hooks/inject-transcript-path.py",
        "--matcher",
        "Bash",
    ]


def entries(settings, event="PreToolUse"):
    return json.loads(Path(settings).read_text())["hooks"][event]


def commands(settings, event="PreToolUse"):
    out = []
    for e in entries(settings, event):
        for hk in e.get("hooks", []):
            out.append(hk.get("command", ""))
    return out


# ── command construction ────────────────────────────────────────────────────


def test_project_mode_roots_command_at_claude_project_dir(tmp_path):
    """The relative-path bug: a plain relative command breaks on mid-session cd."""
    s = tmp_path / "settings.json"
    run(
        "--settings", str(s),
        "--install-mode", "project",
        "--hook-rel-path", ".claude/t/hooks/h.py",
        "--matcher", "Bash",
    )
    assert commands(s) == ['python3 "$CLAUDE_PROJECT_DIR/.claude/t/hooks/h.py"']


def test_project_mode_tolerates_leading_slash_on_rel_path(tmp_path):
    s = tmp_path / "settings.json"
    run(
        "--settings", str(s),
        "--install-mode", "project",
        "--hook-rel-path", "/.claude/t/hooks/h.py",
        "--matcher", "Bash",
    )
    assert commands(s) == ['python3 "$CLAUDE_PROJECT_DIR/.claude/t/hooks/h.py"']


def test_global_mode_bakes_absolute_path(tmp_path):
    s = tmp_path / "settings.json"
    run(
        "--settings", str(s),
        "--install-mode", "global",
        "--hook-abs-path", "/home/u/.claude/t/hooks/h.py",
        "--matcher", "Bash",
    )
    assert commands(s) == ["python3 /home/u/.claude/t/hooks/h.py"]


def test_project_mode_requires_rel_path(tmp_path):
    s = tmp_path / "settings.json"
    r = run(
        "--settings", str(s),
        "--install-mode", "project",
        "--hook-abs-path", "/abs/h.py",
        "--matcher", "Bash",
    )
    assert r.returncode == 2
    assert "--hook-rel-path" in r.stderr


def test_target_mode_requires_abs_path(tmp_path):
    s = tmp_path / "settings.json"
    r = run(
        "--settings", str(s),
        "--install-mode", "target",
        "--hook-rel-path", ".claude/h.py",
        "--matcher", "Bash",
    )
    assert r.returncode == 2
    assert "--hook-abs-path" in r.stderr


# ── result reporting ────────────────────────────────────────────────────────


def test_missing_file_reports_added_and_creates_it(tmp_path):
    s = tmp_path / "settings.json"
    r = run(*base_args(s))
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("ADDED:")
    assert len(commands(s)) == 1


def test_rerun_reports_unchanged_and_does_not_write(tmp_path):
    """The no-op-reported-as-rewrite bug."""
    s = tmp_path / "settings.json"
    run(*base_args(s))
    first = s.read_text()
    r = run(*base_args(s))
    assert r.stdout.startswith("UNCHANGED:"), r.stdout
    assert s.read_text() == first


def test_rerun_does_not_append_duplicate_in_project_mode(tmp_path):
    """The duplicate-append bug: three runs must still leave exactly one entry."""
    s = tmp_path / "settings.json"
    for _ in range(3):
        run(*base_args(s))
    assert len(commands(s)) == 1


def test_stale_absolute_entry_is_replaced_not_duplicated(tmp_path):
    """A project-mode run over a global-mode install must not leave both."""
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /old/abs/inject-transcript-path.py",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    r = run(*base_args(s))
    assert r.stdout.startswith("REWROTE:"), r.stdout
    cmds = commands(s)
    assert len(cmds) == 1
    assert "$CLAUDE_PROJECT_DIR" in cmds[0]


def test_entry_under_a_different_matcher_is_still_cleaned(tmp_path):
    """Matcher-filtered stripping is what let duplicates accumulate."""
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /x/inject-transcript-path.py",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    run(*base_args(s))
    assert len(commands(s)) == 1
    assert entries(s)[0]["matcher"] == "Bash"


# ── preserving what belongs to others ───────────────────────────────────────


def test_unrelated_tool_entry_is_preserved(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "python3 /x/other-tool.py"}
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    run(*base_args(s))
    assert "python3 /x/other-tool.py" in commands(s)


def test_sibling_hook_inside_a_shared_entry_survives(tmp_path):
    """Only our hook is stripped, not the entry it happens to share."""
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "python3 /x/other.py"},
                                {
                                    "type": "command",
                                    "command": "python3 /x/inject-transcript-path.py",
                                },
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    run(*base_args(s))
    cmds = commands(s)
    assert "python3 /x/other.py" in cmds
    assert sum("inject-transcript-path" in c for c in cmds) == 1


def test_unrelated_settings_keys_are_preserved(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "opus", "env": {"A": "1"}}, indent=2) + "\n")
    run(*base_args(s))
    d = json.loads(s.read_text())
    assert d["model"] == "opus"
    assert d["env"] == {"A": "1"}


def test_other_hook_events_are_untouched(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    run(*base_args(s))
    d = json.loads(s.read_text())
    assert d["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "x"


# ── multi-matcher (permission-hooks shape) ──────────────────────────────────


def test_four_matchers_produce_four_entries(tmp_path):
    s = tmp_path / "settings.json"
    args = [
        "--settings",
        str(s),
        "--install-mode",
        "project",
        "--hook-rel-path",
        ".claude/permission-hooks/hooks/permission-guard.py",
        "--matcher",
        "Bash",
        "--matcher",
        "Read",
        "--matcher",
        "Edit",
        "--matcher",
        "Write",
    ]
    r = run(*args)
    assert r.stdout.startswith("ADDED:")
    assert [e["matcher"] for e in entries(s)] == ["Bash", "Read", "Edit", "Write"]
    r2 = run(*args)
    assert r2.stdout.startswith("UNCHANGED:"), r2.stdout


def test_strip_then_readd_identical_is_unchanged_not_rewrote(tmp_path):
    """The exact case that misreported REWROTE on a byte-identical file."""
    s = tmp_path / "settings.json"
    args = [
        "--settings",
        str(s),
        "--install-mode",
        "project",
        "--hook-rel-path",
        ".claude/permission-hooks/hooks/permission-guard.py",
        "--matcher",
        "Bash",
        "--matcher",
        "Read",
    ]
    run(*args)
    r = run(*args)
    assert "UNCHANGED" in r.stdout
    assert "REWROTE" not in r.stdout


# ── malformed input ─────────────────────────────────────────────────────────


def test_corrupt_json_is_backed_up_not_discarded(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("{ this is not json")
    r = run(*base_args(s))
    assert r.returncode == 0, r.stderr
    assert "backed up" in r.stdout
    assert (tmp_path / "settings.json.bak").read_text() == "{ this is not json"
    assert len(commands(s)) == 1


def test_non_object_json_is_an_error(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("[1, 2, 3]\n")
    r = run(*base_args(s))
    assert r.returncode == 2
    assert "does not contain a JSON object" in r.stderr


def test_non_dict_entries_are_left_alone(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps({"hooks": {"PreToolUse": ["junk", 7]}}, indent=2) + "\n"
    )
    r = run(*base_args(s))
    assert r.returncode == 0, r.stderr
    kept = json.loads(s.read_text())["hooks"]["PreToolUse"]
    assert "junk" in kept and 7 in kept


# ── marker derivation and dry-run ───────────────────────────────────────────


def test_marker_defaults_to_hook_filename(tmp_path):
    s = tmp_path / "settings.json"
    run(*base_args(s))
    run(*base_args(s, mode="global"))
    # The global-mode run must recognise the project-mode entry as ours and
    # replace it, which only works because the marker is the bare filename.
    assert len(commands(s)) == 1
    assert commands(s)[0] == (
        "python3 /abs/target/.claude/transcript/hooks/inject-transcript-path.py"
    )


def test_explicit_marker_overrides_filename(tmp_path):
    s = tmp_path / "settings.json"
    r = run(*base_args(s), "--marker", "custom-marker")
    assert r.returncode == 0
    assert "custom-marker" in r.stdout


def test_dry_run_reports_without_writing(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "opus"}, indent=2) + "\n")
    original = s.read_text()
    r = run(*base_args(s), "--dry-run")
    assert r.stdout.startswith("ADDED:")
    assert s.read_text() == original


def test_trailing_newline_is_always_written(tmp_path):
    s = tmp_path / "settings.json"
    run(*base_args(s))
    assert s.read_text().endswith("}\n")


def test_custom_event_name(tmp_path):
    s = tmp_path / "settings.json"
    r = run(*base_args(s), "--event", "PostToolUse")
    assert r.returncode == 0
    assert len(commands(s, "PostToolUse")) == 1
