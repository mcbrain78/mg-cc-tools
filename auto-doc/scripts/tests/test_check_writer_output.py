"""Tests for check-writer-output.py.

The check this replaces globbed the docs directory right after the writer agents
returned -- two stages before any document is written. The two tests named
first_run_* and re_run_* pin the opposite failures that produced: it warned when
everything had succeeded, and passed when everything had failed.
"""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
SCRIPT = os.path.join(SCRIPTS_DIR, "check-writer-output.py")


def _run(generate_dir, expect):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--generate-dir", str(generate_dir), "--expect", expect],
        capture_output=True, text=True,
    )


def _state(generate_dir, name, documents):
    generate_dir.mkdir(parents=True, exist_ok=True)
    (generate_dir / f"write-state-{name}.json").write_text(
        json.dumps({"documents": documents})
    )


def _sections(*slugs):
    return {slug: {"content": f"## {slug}\n\nbody\n"} for slug in slugs}


def test_pair_with_sections_passes(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": _sections("a", "b")}})

    r = _run(gen, "devops:OPERATIONS")

    assert r.returncode == 0, r.stdout
    assert "OK" in r.stdout
    assert "2 sections (orient-write)" in r.stdout
    assert "all 1 dispatched document(s) produced sections" in r.stdout


def test_first_run_with_empty_docs_dir_still_passes(tmp_path):
    """The old glob warned here even though every agent had succeeded."""
    gen = tmp_path / "generate"
    docs = tmp_path / "docs"
    docs.mkdir()  # nothing in it yet -- documents are not written until finalize
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": _sections("a")}})
    _state(gen, "agents-SYSTEM_MAP", {"SYSTEM_MAP": {"sections": _sections("a")}})

    r = _run(gen, "devops:OPERATIONS,agents:SYSTEM_MAP")

    assert r.returncode == 0, r.stdout
    assert "produced nothing" not in r.stdout


def test_re_run_with_stale_docs_still_fails(tmp_path):
    """The old glob passed here because last run's files were still on disk."""
    gen = tmp_path / "generate"
    gen.mkdir()
    docs = tmp_path / "docs" / "devops"
    docs.mkdir(parents=True)
    (docs / "OPERATIONS.md").write_text("# from the previous run\n")

    r = _run(gen, "devops:OPERATIONS")

    assert r.returncode == 1
    assert "MISSING" in r.stdout
    assert "no write-state file was produced" in r.stdout


def test_state_file_with_zero_sections_is_a_failure(tmp_path):
    """An agent that initialised state then died leaves the file behind."""
    gen = tmp_path / "generate"
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": {}}})

    r = _run(gen, "devops:OPERATIONS")

    assert r.returncode == 1
    assert "EMPTY" in r.stdout
    assert "recorded 0 sections" in r.stdout


def test_standard_prompt_layout_is_accepted(tmp_path):
    """Documents without a refined template share one per-audience state file."""
    gen = tmp_path / "generate"
    _state(gen, "devops", {
        "OPERATIONS": {"sections": _sections("a")},
        "TROUBLESHOOTING": {"sections": _sections("a", "b")},
    })

    r = _run(gen, "devops:OPERATIONS,devops:TROUBLESHOOTING")

    assert r.returncode == 0, r.stdout
    assert r.stdout.count("(standard)") == 2


def test_per_document_layout_wins_over_per_audience(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops", {"OPERATIONS": {"sections": _sections("a")}})
    _state(gen, "devops-OPERATIONS",
           {"OPERATIONS": {"sections": _sections("a", "b", "c")}})

    r = _run(gen, "devops:OPERATIONS")

    assert "3 sections (orient-write)" in r.stdout


def test_audience_state_exists_but_lacks_the_document(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops", {"OPERATIONS": {"sections": _sections("a")}})

    r = _run(gen, "devops:TROUBLESHOOTING")

    assert r.returncode == 1
    assert "did not reach it" in r.stdout


def test_nested_sections_are_counted(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": {
        "top": {
            "content": "x",
            "sections": {"child": {"content": "y"}, "child2": {"content": "z"}},
        },
    }}})

    r = _run(gen, "devops:OPERATIONS")

    assert r.returncode == 0, r.stdout
    assert "3 sections" in r.stdout


def test_partial_failure_lists_only_the_failed_pairs(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": _sections("a")}})

    r = _run(gen, "devops:OPERATIONS,agents:SYSTEM_MAP")

    assert r.returncode == 1
    assert "1 of 2 dispatched document(s) produced nothing" in r.stdout
    assert "agents/SYSTEM_MAP" in r.stdout.split("produced nothing")[1]


def test_partial_failure_tells_the_caller_to_continue(tmp_path):
    gen = tmp_path / "generate"
    gen.mkdir()

    r = _run(gen, "devops:OPERATIONS")

    assert "Partial generation is acceptable" in r.stdout
    assert "counting the files already in the docs directory" in r.stdout


def test_corrupt_state_file_counts_as_missing(tmp_path):
    gen = tmp_path / "generate"
    gen.mkdir()
    (gen / "write-state-devops-OPERATIONS.json").write_text("{ torn")

    r = _run(gen, "devops:OPERATIONS")

    assert r.returncode == 1
    assert "MISSING" in r.stdout


def test_missing_generate_dir_is_a_usage_error(tmp_path):
    r = _run(tmp_path / "nope", "devops:OPERATIONS")

    assert r.returncode == 2
    assert "generate dir does not exist" in r.stderr


def test_malformed_expect_is_a_usage_error(tmp_path):
    gen = tmp_path / "generate"
    gen.mkdir()

    r = _run(gen, "devops")

    assert r.returncode == 2
    assert "expected <audience>:<DOCUMENT>" in r.stderr


def test_empty_expect_is_a_usage_error(tmp_path):
    gen = tmp_path / "generate"
    gen.mkdir()

    r = _run(gen, " , ")

    assert r.returncode == 2


def test_whitespace_around_pairs_is_tolerated(tmp_path):
    gen = tmp_path / "generate"
    _state(gen, "devops-OPERATIONS", {"OPERATIONS": {"sections": _sections("a")}})

    r = _run(gen, " devops : OPERATIONS ")

    assert r.returncode == 0, r.stdout
