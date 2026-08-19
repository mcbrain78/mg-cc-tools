"""Tests for write-session-config.py.

The key names and layout asserted here are the contract audit-cmd.py indexes
directly, so they are pinned deliberately -- a rename that looks harmless in this
script silently breaks every resolution wave.
"""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "write-session-config.py")

# Every key audit-cmd.py reads out of the session file.
AUDIT_CMD_KEYS = {
    "document",
    "audience",
    "wave",
    "prose_verify_dir",
    "sections_filter",
    "uncleared_file",
    "findings_file",
    "suppress_file",
    "dismissed_this_run_file",
    "protected_entities_file",
    "covered_entities_file",
    "not_entities_file",
}


def _run(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )


def _write(workspace, audience="devops", document="OPERATIONS", wave=1, output=None):
    args = [
        "--workspace", workspace,
        "--audience", audience,
        "--document", document,
        "--wave", wave,
    ]
    if output:
        args += ["--output", output]
    return _run(*args)


def test_writes_to_the_conventional_path(tmp_path):
    r = _write(tmp_path)

    assert r.returncode == 0, r.stderr
    expected = tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json"
    assert expected.is_file()
    assert str(expected) in r.stdout


def test_every_key_audit_cmd_reads_is_present(tmp_path):
    _write(tmp_path)
    session = json.loads(
        (tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json").read_text()
    )

    assert AUDIT_CMD_KEYS <= set(session), AUDIT_CMD_KEYS - set(session)


def test_paths_land_in_the_right_layer(tmp_path):
    """Per-run state under run/, state that outlives a run one level above it."""
    _write(tmp_path)
    session = json.loads(
        (tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json").read_text()
    )
    run_dir = os.path.join(str(tmp_path), "auditv2", "run")
    auditv2 = os.path.join(str(tmp_path), "auditv2")

    for key in ("prose_verify_dir", "uncleared_file", "findings_file",
                "dismissed_this_run_file", "sections_filter"):
        assert session[key].startswith(run_dir), key
    for key in ("not_entities_file", "protected_entities_file", "suppress_file",
                "covered_entities_file"):
        assert os.path.dirname(session[key]) == auditv2, key


def test_sections_filter_lives_inside_the_prose_verify_dir(tmp_path):
    """affected-sections.py writes it there; the two must agree."""
    _write(tmp_path)
    session = json.loads(
        (tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json").read_text()
    )

    assert session["sections_filter"] == os.path.join(
        session["prose_verify_dir"], "affected-sections.json"
    )


def test_audience_and_document_appear_in_derived_filenames(tmp_path):
    _write(tmp_path, audience="end-users", document="GETTING_STARTED")
    session = json.loads(
        (tmp_path / "auditv2" / "run"
         / "session-end-users-GETTING_STARTED.json").read_text()
    )

    assert session["audience"] == "end-users"
    assert session["document"] == "GETTING_STARTED"
    assert session["uncleared_file"].endswith(
        "uncleared-end-users-GETTING_STARTED.json"
    )
    assert session["prose_verify_dir"].endswith("prose-verify-end-users-GETTING_STARTED")


def test_wave_is_written_as_an_integer(tmp_path):
    _write(tmp_path, wave=3)
    session = json.loads(
        (tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json").read_text()
    )

    assert session["wave"] == 3
    assert isinstance(session["wave"], int)


def test_wave_below_one_is_rejected(tmp_path):
    r = _write(tmp_path, wave=0)

    assert r.returncode == 2
    assert "--wave" in r.stderr


def test_explicit_output_overrides_the_default(tmp_path):
    out = tmp_path / "elsewhere" / "s.json"

    r = _write(tmp_path, output=out)

    assert r.returncode == 0, r.stderr
    assert out.is_file()
    assert not (tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json").exists()


def test_missing_inputs_produce_a_warning_not_a_failure(tmp_path):
    r = _write(tmp_path)

    assert r.returncode == 0
    assert "WARNING" in r.stderr
    assert "uncleared_file" in r.stderr


def test_no_warning_once_the_inputs_exist(tmp_path):
    stem = "devops-OPERATIONS"
    run = tmp_path / "auditv2" / "run"
    prose = run / f"prose-verify-{stem}"
    prose.mkdir(parents=True)
    (prose / "affected-sections.json").write_text("[]")
    (run / f"uncleared-{stem}.json").write_text("[]")

    r = _write(tmp_path)

    assert r.returncode == 0, r.stderr
    assert "WARNING" not in r.stderr


def test_rewriting_for_the_next_wave_replaces_the_file(tmp_path):
    path = tmp_path / "auditv2" / "run" / "session-devops-OPERATIONS.json"
    _write(tmp_path, wave=1)
    _write(tmp_path, wave=2)

    assert json.loads(path.read_text())["wave"] == 2
