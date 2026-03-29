"""Tests for editorial-questions.py -- turn-based question manager.

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
    "editorial-questions.py",
)


def _run(args, check=True):
    """Run editorial-questions.py with args, return (stdout, stderr, returncode)."""
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


def _init(tmp, audience="devops"):
    """Helper: init state, return (state_path, question_file, stdout)."""
    checks_path = os.path.join(tmp, "checks.json")
    state_path = os.path.join(tmp, "state.json")
    question_file = os.path.join(tmp, "questions.json")

    _write_json(checks_path, _sample_checks())

    stdout, _, _ = _run([
        "--init",
        "--checks", checks_path,
        "--audience", audience,
        "--state", state_path,
        "--question-file", question_file,
    ])
    return state_path, question_file, stdout


# =============================================================================
# Init mode
# =============================================================================

class TestInitMode:
    """--init creates state, writes question file with first set."""

    def test_creates_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp)
            assert os.path.exists(state_path)

    def test_writes_question_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, question_file, _ = _init(tmp)
            assert os.path.exists(question_file)

    def test_question_file_has_first_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, question_file, _ = _init(tmp)
            qdata = _read_json(question_file)
            assert qdata["set_id"] == "universal-1"
            assert len(qdata["checks"]) == 2
            assert qdata["checks"][0]["check"] == "filler-content"

    def test_stdout_has_continue_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, stdout = _init(tmp)
            result = json.loads(stdout)
            assert result["status"] == "continue"
            assert result["set_id"] == "universal-1"

    def test_stdout_has_correct_remaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            # devops audience: 2 universal + 1 devops = 3 sets, remaining = 2
            _, _, stdout = _init(tmp, audience="devops")
            result = json.loads(stdout)
            assert result["remaining"] == 2

    def test_state_has_current_index_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp)
            state = _read_json(state_path)
            assert state["current_index"] == 0

    def test_devops_audience_gets_3_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp, audience="devops")
            state = _read_json(state_path)
            assert len(state["applicable_sets"]) == 3
            set_ids = [s["id"] for s in state["applicable_sets"]]
            assert "universal-1" in set_ids
            assert "universal-2" in set_ids
            assert "devops-1" in set_ids
            assert "developers-1" not in set_ids

    def test_developers_audience_gets_3_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp, audience="developers")
            state = _read_json(state_path)
            assert len(state["applicable_sets"]) == 3
            set_ids = [s["id"] for s in state["applicable_sets"]]
            assert "universal-1" in set_ids
            assert "universal-2" in set_ids
            assert "developers-1" in set_ids
            assert "devops-1" not in set_ids

    def test_state_stores_full_set_definitions(self):
        """State includes checks arrays so --advance doesn't need checks file."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp)
            state = _read_json(state_path)
            first_set = state["applicable_sets"][0]
            assert "id" in first_set
            assert "checks" in first_set
            assert len(first_set["checks"]) > 0


# =============================================================================
# Advance mode
# =============================================================================

class TestAdvanceMode:
    """--advance writes next set, increments index."""

    def test_advance_writes_second_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)

            stdout, _, _ = _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])

            qdata = _read_json(question_file)
            assert qdata["set_id"] == "universal-2"

    def test_advance_increments_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)

            _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])

            state = _read_json(state_path)
            assert state["current_index"] == 1

    def test_advance_remaining_decreases(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp, audience="devops")
            # After init: remaining=2 (3 sets total)

            stdout, _, _ = _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])
            result = json.loads(stdout)
            assert result["remaining"] == 1

    def test_advance_returns_finished_after_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp, audience="devops")
            # 3 sets: init writes first, need 2 advances

            _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])
            _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])
            # Now at index 2 (last), next advance should finish
            stdout, _, _ = _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])
            result = json.loads(stdout)
            assert result["status"] == "finished"
            assert result["sets_evaluated"] == 3

    def test_full_cycle(self):
        """Init + N advances covers all sets."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, stdout = _init(tmp, audience="devops")

            seen_sets = []
            result = json.loads(stdout)
            seen_sets.append(result["set_id"])

            while result["status"] == "continue":
                stdout, _, _ = _run([
                    "--advance", "--no-findings",
                    "--state", state_path,
                    "--question-file", question_file,
                ])
                result = json.loads(stdout)
                if result["status"] == "continue":
                    seen_sets.append(result["set_id"])

            assert result["status"] == "finished"
            assert result["sets_evaluated"] == 3
            assert seen_sets == ["universal-1", "universal-2", "devops-1"]


# =============================================================================
# Edge cases
# =============================================================================

class TestEdgeCases:
    """Error handling and boundary conditions."""

    def test_advance_without_init_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "nonexistent.json")
            question_file = os.path.join(tmp, "questions.json")

            _, _, rc = _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
            ], check=False)
            assert rc != 0

    def test_missing_checks_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--init",
                "--checks", "/fictitious/nonexistent/checks.json",
                "--audience", "devops",
                "--state", os.path.join(tmp, "state.json"),
                "--question-file", os.path.join(tmp, "questions.json"),
            ], check=False)
            assert rc != 0

    def test_corrupted_state_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            question_file = os.path.join(tmp, "questions.json")
            with open(state_path, "w") as f:
                f.write("{corrupted")

            _, _, rc = _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
            ], check=False)
            assert rc != 0

    def test_none_audience_gets_only_universal(self):
        """When audience is None/unset, only universal sets apply."""
        with tempfile.TemporaryDirectory() as tmp:
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")
            question_file = os.path.join(tmp, "questions.json")

            _write_json(checks_path, _sample_checks())

            # No --audience flag
            _run([
                "--init",
                "--checks", checks_path,
                "--state", state_path,
                "--question-file", question_file,
            ])

            state = _read_json(state_path)
            assert len(state["applicable_sets"]) == 2
            set_ids = [s["id"] for s in state["applicable_sets"]]
            assert "universal-1" in set_ids
            assert "universal-2" in set_ids
            assert "devops-1" not in set_ids
            assert "developers-1" not in set_ids

    def test_no_mode_flag_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--state", os.path.join(tmp, "state.json"),
                "--question-file", os.path.join(tmp, "questions.json"),
            ], check=False)
            assert rc != 0

    def test_init_missing_checks_arg_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, rc = _run([
                "--init",
                "--audience", "devops",
                "--state", os.path.join(tmp, "state.json"),
                "--question-file", os.path.join(tmp, "questions.json"),
            ], check=False)
            assert rc != 0

    def test_init_state_has_findings_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init(tmp)
            state = _read_json(state_path)
            assert state["findings_count"] == 0


# =============================================================================
# Finding gate
# =============================================================================

class TestFindingGate:
    """Finding-gate prevents advancing without evaluation evidence."""

    def test_advance_without_gate_args_fails(self):
        """No --findings-file, no --no-findings → exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)

            _, stderr, rc = _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
            ], check=False)
            assert rc != 0
            assert "must pass" in stderr.lower()

    def test_advance_with_no_findings_flag_succeeds(self):
        """--no-findings → advances normally."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)

            stdout, _, rc = _run([
                "--advance", "--no-findings",
                "--state", state_path,
                "--question-file", question_file,
            ])
            assert rc == 0
            result = json.loads(stdout)
            assert result["status"] == "continue"

    def test_advance_with_new_findings_succeeds(self):
        """findings file has entries > stored count → advances."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)
            findings_file = os.path.join(tmp, "findings.json")
            _write_json(findings_file, [{"check": "test", "description": "test finding"}])

            stdout, _, rc = _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
                "--findings-file", findings_file,
            ])
            assert rc == 0
            result = json.loads(stdout)
            assert result["status"] == "continue"

    def test_advance_with_unchanged_findings_fails(self):
        """findings file count == stored count, no --no-findings → exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)
            findings_file = os.path.join(tmp, "findings.json")
            # First advance with 1 finding — succeeds and stores count=1
            _write_json(findings_file, [{"check": "test", "description": "finding 1"}])
            _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
                "--findings-file", findings_file,
            ])

            # Second advance with same count (still 1) — should fail
            _, stderr, rc = _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
                "--findings-file", findings_file,
            ], check=False)
            assert rc != 0
            assert "findings file has 1 entries" in stderr.lower()

    def test_findings_count_updates_in_state(self):
        """After advance with findings, state has new count."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, question_file, _ = _init(tmp)
            findings_file = os.path.join(tmp, "findings.json")
            _write_json(findings_file, [
                {"check": "a", "description": "finding 1"},
                {"check": "b", "description": "finding 2"},
            ])

            _run([
                "--advance",
                "--state", state_path,
                "--question-file", question_file,
                "--findings-file", findings_file,
            ])

            state = _read_json(state_path)
            assert state["findings_count"] == 2
