"""Tests for editorial-orchestrate.py -- multi-doc editorial state machine.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "editorial-orchestrate.py",
)


def _run(args, check=True):
    """Run editorial-orchestrate.py with args, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Script failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout, result.stderr, result.returncode


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _sample_checks():
    """Checks with 2 universal + 1 devops + 1 developers set."""
    return {
        "question_sets": [
            {
                "id": "universal-1",
                "audience": None,
                "checks": [
                    {"check": "filler-content", "description": "test filler"},
                    {"check": "placeholder-content", "description": "test placeholder"},
                ],
            },
            {
                "id": "universal-2",
                "audience": None,
                "checks": [
                    {"check": "heading-content-mismatch", "description": "test heading"},
                ],
            },
            {
                "id": "devops-1",
                "audience": "devops",
                "checks": [
                    {"check": "devops-missing-expected-output", "description": "test devops"},
                ],
            },
            {
                "id": "developers-1",
                "audience": "developers",
                "checks": [
                    {"check": "developer-abstract-architecture", "description": "test dev"},
                ],
            },
        ]
    }


def _sample_manifest():
    """2 docs: OPERATIONS/devops, ARCHITECTURE/developers."""
    return [
        {
            "source": "/fictitious/project/docs/auto-doc/devops/OPERATIONS.md",
            "audience": "devops",
            "review_files": ["/fictitious/project/docs/auto-doc/devops/OPERATIONS.md"],
        },
        {
            "source": "/fictitious/project/docs/auto-doc/developers/ARCHITECTURE.md",
            "audience": "developers",
            "review_files": ["/fictitious/project/docs/auto-doc/developers/ARCHITECTURE.md"],
        },
    ]


def _init(tmp, manifest=None, checks=None):
    """Helper: init state, return (state_path, stdout_parsed)."""
    manifest_path = os.path.join(tmp, "manifest.json")
    checks_path = os.path.join(tmp, "checks.json")
    state_path = os.path.join(tmp, "state.json")
    findings_prefix = os.path.join(tmp, "findings-ed")

    _write_json(manifest_path, _sample_manifest() if manifest is None else manifest)
    _write_json(checks_path, _sample_checks() if checks is None else checks)

    stdout, _, _ = _run([
        "--init",
        "--manifest", manifest_path,
        "--checks", checks_path,
        "--findings-prefix", findings_prefix,
        "--tmp-dir", tmp,
        "--state", state_path,
    ])
    return state_path, json.loads(stdout)


# =============================================================================
# Init mode
# =============================================================================

class TestInit:
    """--init creates state, returns spawn action, writes question files."""

    def test_returns_spawn_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp)
            assert result["action"] == "spawn"

    def test_spawn_lists_all_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp)
            names = [d["name"] for d in result["docs"]]
            assert "OPERATIONS" in names
            assert "ARCHITECTURE" in names

    def test_spawn_docs_have_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp)
            for doc in result["docs"]:
                assert "name" in doc
                assert "source" in doc
                assert "audience" in doc
                assert "question_file" in doc
                assert "findings_file" in doc

    def test_writes_question_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp)
            for doc in result["docs"]:
                assert os.path.isfile(doc["question_file"])
                qdata = _read_json(doc["question_file"])
                assert qdata["set_id"] == "universal-1"

    def test_creates_findings_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp)
            for doc in result["docs"]:
                assert os.path.isfile(doc["findings_file"])
                assert _read_json(doc["findings_file"]) == []

    def test_state_has_all_docs_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init(tmp)
            state = _read_json(state_path)
            for doc in state["docs"]:
                assert doc["active"] is True

    def test_state_has_correct_applicable_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init(tmp)
            state = _read_json(state_path)
            ops = next(d for d in state["docs"] if d["name"] == "OPERATIONS")
            arch = next(d for d in state["docs"] if d["name"] == "ARCHITECTURE")
            # OPERATIONS (devops): 2 universal + 1 devops = 3
            assert len(ops["applicable_sets"]) == 3
            # ARCHITECTURE (developers): 2 universal + 1 developers = 3
            assert len(arch["applicable_sets"]) == 3

    def test_cleans_stale_question_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create a stale question file
            stale = os.path.join(tmp, "ed-questions-STALE.json")
            _write_json(stale, {"set_id": "old"})
            assert os.path.exists(stale)

            _init(tmp)
            assert not os.path.exists(stale)


# =============================================================================
# Next mode
# =============================================================================

class TestNext:
    """--next returns send action, advances question files."""

    def test_returns_send_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init(tmp)
            stdout, _, _ = _run(["--next", "--state", state_path])
            result = json.loads(stdout)
            assert result["action"] == "send"

    def test_advances_question_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, init_result = _init(tmp)

            stdout, _, _ = _run(["--next", "--state", state_path])
            result = json.loads(stdout)

            # Question files should now have universal-2
            for target in result["targets"]:
                qdata = _read_json(target["question_file"])
                assert qdata["set_id"] == "universal-2"

    def test_targets_include_all_active_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init(tmp)
            stdout, _, _ = _run(["--next", "--state", state_path])
            result = json.loads(stdout)
            names = [t["name"] for t in result["targets"]]
            assert "OPERATIONS" in names
            assert "ARCHITECTURE" in names

    def test_targets_have_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init(tmp)
            stdout, _, _ = _run(["--next", "--state", state_path])
            result = json.loads(stdout)
            for target in result["targets"]:
                assert "name" in target
                assert "question_file" in target
                assert "findings_file" in target


# =============================================================================
# Finishing behavior
# =============================================================================

class TestFinishing:
    """Docs with fewer sets finish before others."""

    def test_doc_finishes_when_no_more_sets(self):
        """Use manifest where one doc has fewer applicable sets."""
        with tempfile.TemporaryDirectory() as tmp:
            # 1 doc with no audience-specific sets (2 universal only)
            # 1 doc with devops (2 universal + 1 devops = 3)
            manifest = [
                {
                    "source": "/fictitious/docs/shared/OVERVIEW.md",
                    "audience": "shared",
                    "review_files": ["/fictitious/docs/shared/OVERVIEW.md"],
                },
                {
                    "source": "/fictitious/docs/devops/OPERATIONS.md",
                    "audience": "devops",
                    "review_files": ["/fictitious/docs/devops/OPERATIONS.md"],
                },
            ]
            # Use checks with only 1 shared-specific set but no "shared" sets in our sample
            # shared audience only gets universal sets (2), devops gets 3
            state_path, _ = _init(tmp, manifest=manifest)

            # After init: both at index 0 (universal-1)
            # Next 1: both advance to universal-2 (index 1)
            stdout, _, _ = _run(["--next", "--state", state_path])
            r1 = json.loads(stdout)
            assert r1["action"] == "send"
            assert len(r1["targets"]) == 2

            # Next 2: OVERVIEW finishes (only 2 sets), OPERATIONS advances to devops-1
            stdout, _, _ = _run(["--next", "--state", state_path])
            r2 = json.loads(stdout)
            assert r2["action"] == "send"
            assert "OVERVIEW" in r2["finished_this_round"]
            target_names = [t["name"] for t in r2["targets"]]
            assert "OPERATIONS" in target_names
            assert "OVERVIEW" not in target_names

            # Next 3: OPERATIONS finishes
            stdout, _, _ = _run(["--next", "--state", state_path])
            r3 = json.loads(stdout)
            assert r3["action"] == "done"
            assert r3["docs_processed"] == 2


# =============================================================================
# Full cycle
# =============================================================================

class TestFullCycle:
    """Init + N next calls → all docs finish → done action."""

    def test_full_cycle_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, init_result = _init(tmp)
            assert init_result["action"] == "spawn"

            rounds = 0
            while True:
                stdout, _, _ = _run(["--next", "--state", state_path])
                result = json.loads(stdout)
                rounds += 1
                if result["action"] == "done":
                    break
                assert result["action"] == "send"
                assert rounds < 20, "Too many rounds — infinite loop?"

            assert result["docs_processed"] == 2

    def test_cycle_visits_all_question_sets(self):
        """Track set_ids written to question files across rounds."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, init_result = _init(tmp)

            # Collect set_ids from question files after init
            ops_qfile = next(
                d["question_file"] for d in init_result["docs"]
                if d["name"] == "OPERATIONS"
            )
            seen_sets_ops = [_read_json(ops_qfile)["set_id"]]

            while True:
                stdout, _, _ = _run(["--next", "--state", state_path])
                result = json.loads(stdout)
                if result["action"] == "done":
                    break
                for target in result["targets"]:
                    if target["name"] == "OPERATIONS":
                        seen_sets_ops.append(
                            _read_json(target["question_file"])["set_id"]
                        )

            # OPERATIONS (devops): universal-1, universal-2, devops-1
            assert seen_sets_ops == ["universal-1", "universal-2", "devops-1"]


# =============================================================================
# Edge cases
# =============================================================================

class TestEdgeCases:
    """Error handling and boundary conditions."""

    def test_next_without_init_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--next",
                "--state", os.path.join(tmp, "nonexistent.json"),
            ], check=False)
            assert rc != 0

    def test_empty_manifest_returns_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = _init(tmp, manifest=[])
            assert result["action"] == "done"
            assert result["docs_processed"] == 0

    def test_no_mode_flag_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--state", os.path.join(tmp, "state.json"),
            ], check=False)
            assert rc != 0

    def test_init_missing_required_args_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--init",
                "--state", os.path.join(tmp, "state.json"),
                # Missing --manifest, --checks, etc.
            ], check=False)
            assert rc != 0

    def test_single_doc_completes(self):
        """Single doc manifest completes correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [
                {
                    "source": "/fictitious/docs/devops/DEPLOY.md",
                    "audience": "devops",
                    "review_files": ["/fictitious/docs/devops/DEPLOY.md"],
                },
            ]
            state_path, init_result = _init(tmp, manifest=manifest)
            assert init_result["action"] == "spawn"
            assert len(init_result["docs"]) == 1

            # Advance through all sets
            rounds = 0
            while True:
                stdout, _, _ = _run(["--next", "--state", state_path])
                result = json.loads(stdout)
                rounds += 1
                if result["action"] == "done":
                    break

            assert result["docs_processed"] == 1
