"""Tests for archive-verify.py -- verify run archival.

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
    "archive-verify.py",
)


def _run(args, check=True, cwd=None):
    """Run archive-verify.py with args, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Script failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout, result.stderr, result.returncode


def _make_project(tmp):
    """Create minimal project with verify outputs.

    Returns project_root path.
    """
    project_root = os.path.join(tmp, "project")
    mg_docs = os.path.join(project_root, ".mg", "docs")
    verify_dir = os.path.join(mg_docs, "verify")
    os.makedirs(verify_dir)

    with open(os.path.join(verify_dir, "findings.json"), "w") as f:
        json.dump([{"check": "test", "description": "test finding"}], f)

    with open(os.path.join(verify_dir, "report.md"), "w") as f:
        f.write("# Verify Report\n\n1 issue found.\n")

    return project_root


def _make_context_file(tmp, name="rr1-602-verify3.txt"):
    """Create a dummy context file."""
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write("Claude Code transcript content...\n")
    return path


# =============================================================================
# Core functionality
# =============================================================================

class TestArchiveVerify:
    """Happy-path: creates archive with all expected files."""

    def test_creates_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "rr1-602-verify3",
            )
            assert os.path.isdir(run_dir)

    def test_copies_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "rr1-602-verify3",
            )
            findings = os.path.join(run_dir, "findings.json")
            assert os.path.isfile(findings)
            with open(findings) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["check"] == "test"

    def test_copies_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "rr1-602-verify3",
            )
            report = os.path.join(run_dir, "report.md")
            assert os.path.isfile(report)
            with open(report) as f:
                content = f.read()
            assert "1 issue found" in content

    def test_copies_context_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "rr1-602-verify3",
            )
            assert os.path.isfile(os.path.join(run_dir, "rr1-602-verify3.txt"))

    def test_folder_name_from_context_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp, name="my-custom-run.txt")

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "my-custom-run",
            )
            assert os.path.isdir(run_dir)

    def test_auto_detects_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run(
                ["--context-file", context],
                cwd=project_root,
            )

            run_dir = os.path.join(
                project_root, ".mg", "docs", "verify-runs", "rr1-602-verify3",
            )
            assert os.path.isdir(run_dir)


# =============================================================================
# Error cases
# =============================================================================

class TestArchiveVerifyErrors:
    """Error handling and boundary conditions."""

    def test_missing_context_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)

            _, stderr, rc = _run([
                "--context-file", os.path.join(tmp, "nonexistent.txt"),
                "--project-root", project_root,
            ], check=False)
            assert rc != 0
            assert "context file not found" in stderr.lower()

    def test_missing_findings_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            mg_docs = os.path.join(project_root, ".mg", "docs")
            verify_dir = os.path.join(mg_docs, "verify")
            os.makedirs(verify_dir)
            # Only create report, no findings
            with open(os.path.join(verify_dir, "report.md"), "w") as f:
                f.write("# Report\n")
            context = _make_context_file(tmp)

            _, stderr, rc = _run([
                "--context-file", context,
                "--project-root", project_root,
            ], check=False)
            assert rc != 0
            assert "missing verify outputs" in stderr.lower()

    def test_missing_report_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = os.path.join(tmp, "project")
            mg_docs = os.path.join(project_root, ".mg", "docs")
            verify_dir = os.path.join(mg_docs, "verify")
            os.makedirs(verify_dir)
            # Only create findings, no report
            with open(os.path.join(verify_dir, "findings.json"), "w") as f:
                json.dump([], f)
            context = _make_context_file(tmp)

            _, stderr, rc = _run([
                "--context-file", context,
                "--project-root", project_root,
            ], check=False)
            assert rc != 0
            assert "missing verify outputs" in stderr.lower()

    def test_duplicate_archive_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = _make_project(tmp)
            context = _make_context_file(tmp)

            _run([
                "--context-file", context,
                "--project-root", project_root,
            ])

            _, stderr, rc = _run([
                "--context-file", context,
                "--project-root", project_root,
            ], check=False)
            assert rc != 0
            assert "already exists" in stderr.lower()

    def test_no_mg_docs_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = _make_context_file(tmp)

            _, stderr, rc = _run([
                "--context-file", context,
                "--project-root", tmp,
            ], check=False)
            assert rc != 0
            assert "missing verify outputs" in stderr.lower()
