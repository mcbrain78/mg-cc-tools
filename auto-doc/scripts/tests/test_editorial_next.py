"""Tests for editorial-next.py -- editorial verification state tracker.

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
    "editorial-next.py",
)


def _run(args, check=True):
    """Run editorial-next.py with args, return (stdout, stderr, returncode)."""
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


def _sample_manifest():
    """Minimal manifest with 2 docs, one with 2 chunks."""
    return [
        {
            "source": "/project/docs/OPERATIONS.md",
            "audience": "devops",
            "review_files": [
                "/project/.mg/docs/tmp/review-chunks/OPERATIONS-01-overview.md",
                "/project/.mg/docs/tmp/review-chunks/OPERATIONS-02-deploy.md",
            ],
        },
        {
            "source": "/project/docs/ARCHITECTURE.md",
            "audience": "developers",
            "review_files": [
                "/project/docs/ARCHITECTURE.md",
            ],
        },
    ]


def _sample_checks():
    """Minimal checks with universal + 2 audience-specific sets."""
    return {
        "question_sets": [
            {
                "id": "universal-1",
                "audience": None,
                "checks": [
                    {"check": "filler-content", "description": "test"},
                    {"check": "placeholder-content", "description": "test"},
                ],
            },
            {
                "id": "devops-1",
                "audience": "devops",
                "checks": [
                    {"check": "devops-missing-expected-output", "description": "test"},
                ],
            },
            {
                "id": "developers-1",
                "audience": "developers",
                "checks": [
                    {"check": "developer-abstract-architecture", "description": "test"},
                ],
            },
        ]
    }


def _init_single(tmp):
    """Helper: init state in single-item mode, return state_path."""
    manifest_path = os.path.join(tmp, "manifest.json")
    checks_path = os.path.join(tmp, "checks.json")
    state_path = os.path.join(tmp, "state.json")

    _write_json(manifest_path, _sample_manifest())
    _write_json(checks_path, _sample_checks())

    _run([
        "--manifest", manifest_path,
        "--checks", checks_path,
        "--state", state_path,
    ])
    return state_path, manifest_path, checks_path


def _init_batch(tmp, batch_size=5):
    """Helper: init state in batch mode, return state_path."""
    manifest_path = os.path.join(tmp, "manifest.json")
    checks_path = os.path.join(tmp, "checks.json")
    state_path = os.path.join(tmp, "state.json")
    findings_prefix = os.path.join(tmp, "findings", "editorial-mini")
    tmp_dir = os.path.join(tmp, "tmp")

    os.makedirs(os.path.join(tmp, "findings"), exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    _write_json(manifest_path, _sample_manifest())
    _write_json(checks_path, _sample_checks())

    stdout, _, _ = _run([
        "--manifest", manifest_path,
        "--checks", checks_path,
        "--state", state_path,
        "--next-batch", "--batch-size", str(batch_size),
        "--findings-prefix", findings_prefix,
        "--tmp-dir", tmp_dir,
    ])
    return state_path, stdout


# =============================================================================
# Single-item mode (legacy)
# =============================================================================

class TestSingleItemInit:
    """First call creates state and returns first work item."""

    def test_first_call_creates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            assert os.path.exists(state_path)

    def test_first_call_returns_first_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")

            _write_json(manifest_path, _sample_manifest())
            _write_json(checks_path, _sample_checks())

            stdout, _, _ = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
            ])

            result = json.loads(stdout)
            assert result["item_index"] == 0
            assert "OPERATIONS--universal-1" in result["item_name"]

    def test_first_call_returns_correct_question_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")

            _write_json(manifest_path, _sample_manifest())
            _write_json(checks_path, _sample_checks())

            stdout, _, _ = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
            ])

            result = json.loads(stdout)
            assert result["question_set"] == "universal-1"

    def test_state_file_has_correct_work_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)

            state = _read_json(state_path)
            # 2 docs × 2 applicable sets each = 4 items
            assert len(state["work_items"]) == 4
            assert all(not item["done"] for item in state["work_items"])

    def test_developer_doc_gets_correct_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)

            state = _read_json(state_path)
            # ARCHITECTURE items are at indices 2 and 3
            arch_items = [i for i in state["work_items"]
                          if "ARCHITECTURE" in i["item_name"]]
            assert len(arch_items) == 2
            arch_sets = {i["question_set"] for i in arch_items}
            assert "universal-1" in arch_sets
            assert "developers-1" in arch_sets
            assert "devops-1" not in arch_sets


class TestSingleItemMarkDone:
    """--mark-done updates state correctly."""

    def test_mark_done_sets_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            _run(["--state", state_path, "--mark-done", "0"])

            state = _read_json(state_path)
            assert state["work_items"][0]["done"] is True
            assert state["work_items"][1]["done"] is False

    def test_mark_done_invalid_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            _, _, rc = _run(
                ["--state", state_path, "--mark-done", "99"],
                check=False,
            )
            assert rc != 0

    def test_mark_done_no_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "nonexistent.json")
            _, _, rc = _run(
                ["--state", state_path, "--mark-done", "0"],
                check=False,
            )
            assert rc != 0


class TestSingleItemNext:
    """Subsequent calls return the next undone work item."""

    def test_next_after_mark_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            _run(["--state", state_path, "--mark-done", "0"])

            stdout, _, _ = _run(["--state", state_path])
            result = json.loads(stdout)
            assert result["item_index"] == 1
            assert "OPERATIONS--devops-1" in result["item_name"]

    def test_done_when_all_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            for i in range(4):
                _run(["--state", state_path, "--mark-done", str(i)])

            stdout, _, _ = _run(["--state", state_path])
            result = json.loads(stdout)
            assert result["status"] == "DONE"
            assert result["processed"] == 4
            assert result["total"] == 4

    def test_skips_done_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)
            _run(["--state", state_path, "--mark-done", "0"])
            _run(["--state", state_path, "--mark-done", "1"])

            stdout, _, _ = _run(["--state", state_path])
            result = json.loads(stdout)
            assert result["item_index"] == 2
            assert "ARCHITECTURE" in result["item_name"]


class TestSingleItemEdgeCases:
    """Edge cases and error handling for single-item mode."""

    def test_empty_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")

            _write_json(manifest_path, [])
            _write_json(checks_path, _sample_checks())

            stdout, _, _ = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
            ])

            result = json.loads(stdout)
            assert result["status"] == "DONE"
            assert result["total"] == 0

    def test_corrupted_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            with open(state_path, "w") as f:
                f.write("{corrupted")
            _, _, rc = _run(["--state", state_path], check=False)
            assert rc != 0

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            _, _, rc = _run(
                [
                    "--manifest", "/nonexistent/manifest.json",
                    "--checks", "/nonexistent/checks.json",
                    "--state", state_path,
                ],
                check=False,
            )
            assert rc != 0

    def test_existing_state_ignores_manifest_checks(self):
        """If state exists, --manifest and --checks are not required."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)

            stdout, _, _ = _run(["--state", state_path])
            result = json.loads(stdout)
            assert result["item_index"] == 0

    def test_doc_with_no_audience_gets_only_universal_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")

            manifest = [{
                "source": "/project/docs/README.md",
                "audience": None,
                "review_files": ["/project/docs/README.md"],
            }]
            _write_json(manifest_path, manifest)
            _write_json(checks_path, _sample_checks())

            stdout, _, _ = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
            ])

            result = json.loads(stdout)
            assert result["question_set"] == "universal-1"
            assert result["item_name"] == "README--universal-1"


# =============================================================================
# Batch mode
# =============================================================================

class TestBatchInit:
    """First batch call creates state, writes work files, returns minimal info."""

    def test_first_batch_creates_state_with_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp)

            state = _read_json(state_path)
            assert "batch_config" in state
            assert "batch_dir" in state["batch_config"]
            assert "checks_path" in state["batch_config"]
            assert "findings_prefix" in state["batch_config"]
            assert "tmp_dir" in state["batch_config"]

    def test_first_batch_returns_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            assert result["status"] == "next"
            assert len(result["items"]) == 4  # all 4 fit in batch_size=5

    def test_batch_items_have_minimal_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            item = result["items"][0]
            # Only item_index, item_name, work_file — no full params
            assert "item_index" in item
            assert "item_name" in item
            assert "work_file" in item
            # Must NOT have full work item fields
            assert "doc_file" not in item
            assert "question_set" not in item
            assert "doc_source" not in item

    def test_work_files_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            for item in result["items"]:
                assert os.path.exists(item["work_file"])

    def test_work_file_contains_all_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            work_data = _read_json(result["items"][0]["work_file"])
            assert "doc_file" in work_data
            assert "doc_source" in work_data
            assert "doc_audience" in work_data
            assert "question_set" in work_data
            assert "item_name" in work_data
            assert "checks_file" in work_data
            assert "findings_file" in work_data
            assert "tmp_dir" in work_data

    def test_work_file_has_correct_question_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            # First item is OPERATIONS--universal-1
            work_data = _read_json(result["items"][0]["work_file"])
            assert work_data["question_set"] == "universal-1"
            assert work_data["doc_audience"] == "devops"

    def test_findings_files_are_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp)

            result = json.loads(stdout)
            findings_files = set()
            for item in result["items"]:
                work_data = _read_json(item["work_file"])
                findings_files.add(work_data["findings_file"])
            # Each item gets a unique findings file
            assert len(findings_files) == 4

    def test_batch_size_limits_items(self):
        """Batch of size 2 returns only 2 items from 4 total."""
        with tempfile.TemporaryDirectory() as tmp:
            _, stdout = _init_batch(tmp, batch_size=2)

            result = json.loads(stdout)
            assert len(result["items"]) == 2

    def test_missing_findings_prefix_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")

            _write_json(manifest_path, _sample_manifest())
            _write_json(checks_path, _sample_checks())

            _, _, rc = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
                "--next-batch",
                "--tmp-dir", tmp,
                # Missing --findings-prefix
            ], check=False)
            assert rc != 0


class TestBatchMarkDone:
    """--mark-done-batch marks multiple items at once."""

    def test_mark_done_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp)

            _run(["--state", state_path, "--mark-done-batch", "0,1"])

            state = _read_json(state_path)
            assert state["work_items"][0]["done"] is True
            assert state["work_items"][1]["done"] is True
            assert state["work_items"][2]["done"] is False

    def test_mark_done_batch_invalid_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp)

            _, _, rc = _run(
                ["--state", state_path, "--mark-done-batch", "0,99"],
                check=False,
            )
            assert rc != 0

    def test_mark_done_batch_idempotent(self):
        """Marking an already-done item again is fine."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp)

            _run(["--state", state_path, "--mark-done-batch", "0"])
            _run(["--state", state_path, "--mark-done-batch", "0"])

            state = _read_json(state_path)
            assert state["work_items"][0]["done"] is True


class TestBatchNext:
    """Subsequent batch calls return correct batches."""

    def test_next_batch_after_mark_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, stdout = _init_batch(tmp, batch_size=2)

            # First batch has items 0, 1
            result = json.loads(stdout)
            assert len(result["items"]) == 2
            assert result["items"][0]["item_index"] == 0

            # Mark first batch done
            _run(["--state", state_path, "--mark-done-batch", "0,1"])

            # Get next batch
            stdout, _, _ = _run([
                "--state", state_path,
                "--next-batch", "--batch-size", "2",
            ])
            result = json.loads(stdout)
            assert result["status"] == "next"
            assert len(result["items"]) == 2  # items 2 and 3 left
            assert result["items"][0]["item_index"] == 2

    def test_done_when_all_batches_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp)

            # Mark all done
            _run(["--state", state_path, "--mark-done-batch", "0,1,2,3"])

            stdout, _, _ = _run([
                "--state", state_path,
                "--next-batch", "--batch-size", "5",
            ])
            result = json.loads(stdout)
            assert result["status"] == "DONE"
            assert result["processed"] == 4
            assert result["total"] == 4

    def test_subsequent_batch_no_manifest_needed(self):
        """After init, --manifest and --checks are not required."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _ = _init_batch(tmp, batch_size=1)
            _run(["--state", state_path, "--mark-done", "0"])

            stdout, _, _ = _run([
                "--state", state_path,
                "--next-batch", "--batch-size", "1",
            ])
            result = json.loads(stdout)
            assert result["status"] == "next"
            assert result["items"][0]["item_index"] == 1

    def test_work_files_written_each_batch(self):
        """Each batch writes fresh work files."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, stdout = _init_batch(tmp, batch_size=1)

            first_result = json.loads(stdout)
            first_work_file = first_result["items"][0]["work_file"]
            assert os.path.exists(first_work_file)

            _run(["--state", state_path, "--mark-done", "0"])

            stdout, _, _ = _run([
                "--state", state_path,
                "--next-batch", "--batch-size", "1",
            ])
            second_result = json.loads(stdout)
            second_work_file = second_result["items"][0]["work_file"]
            assert os.path.exists(second_work_file)
            assert first_work_file != second_work_file


class TestBatchEdgeCases:
    """Edge cases for batch mode."""

    def test_empty_manifest_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, "manifest.json")
            checks_path = os.path.join(tmp, "checks.json")
            state_path = os.path.join(tmp, "state.json")
            findings_prefix = os.path.join(tmp, "findings", "mini")
            tmp_dir = os.path.join(tmp, "tmp")

            os.makedirs(os.path.join(tmp, "findings"), exist_ok=True)
            os.makedirs(tmp_dir, exist_ok=True)

            _write_json(manifest_path, [])
            _write_json(checks_path, _sample_checks())

            stdout, _, _ = _run([
                "--manifest", manifest_path,
                "--checks", checks_path,
                "--state", state_path,
                "--next-batch", "--batch-size", "5",
                "--findings-prefix", findings_prefix,
                "--tmp-dir", tmp_dir,
            ])

            result = json.loads(stdout)
            assert result["status"] == "DONE"
            assert result["total"] == 0

    def test_batch_on_state_without_batch_config_fails(self):
        """Calling --next-batch on state created in single-item mode fails."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path, _, _ = _init_single(tmp)

            _, _, rc = _run(
                ["--state", state_path, "--next-batch", "--batch-size", "5"],
                check=False,
            )
            assert rc != 0

    def test_corrupted_state_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            with open(state_path, "w") as f:
                f.write("{corrupted")
            _, _, rc = _run(
                ["--state", state_path, "--next-batch"],
                check=False,
            )
            assert rc != 0
