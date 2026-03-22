"""Tests for staleness-check.py -- git-based section freshness analysis."""

import importlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

# Add scripts directory to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import module with hyphenated filename via importlib
_loader = importlib.machinery.SourceFileLoader(
    "staleness_check",
    os.path.join(os.path.dirname(__file__), "..", "staleness-check.py"),
)
_spec = importlib.util.spec_from_loader("staleness_check", _loader)
staleness_check = importlib.util.module_from_spec(_spec)
_loader.exec_module(staleness_check)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def git_project(tmp_path):
    """Create a temporary git repository with source files and docs."""
    # Initialize a git repo
    subprocess.run(
        ["git", "init"], cwd=str(tmp_path),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(tmp_path),
        capture_output=True, check=True,
    )

    # Create source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text("class Auth:\n    pass\n")
    (src / "models").mkdir()
    (src / "models" / "user.py").write_text("class User:\n    pass\n")

    # Initial commit
    subprocess.run(
        ["git", "add", "."], cwd=str(tmp_path),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial", "--date", "2026-01-01T10:00:00Z"],
        cwd=str(tmp_path), capture_output=True, check=True,
        env={**os.environ, "GIT_COMMITTER_DATE": "2026-01-01T10:00:00Z"},
    )

    # Create docs directory
    docs = tmp_path / "docs"
    docs.mkdir()

    return tmp_path


@pytest.fixture
def docs_dir(git_project):
    """Return the docs subdirectory."""
    return git_project / "docs"


# ── Staleness detection tests ────────────────────────────────────────────────


class TestStalenessDetection:
    """Tests for detecting stale documentation sections."""

    def test_stale_section_detected(self, git_project, docs_dir):
        """Section with timestamp older than source file change shows as stale."""
        # Doc was generated at 2026-01-01, source changed after
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # Authentication API

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/auth.py"]} -->

            Auth module handles login.
        """))

        # Modify the source file and commit with a later date
        (git_project / "src" / "auth.py").write_text("class Auth:\n    def login(self): pass\n")
        subprocess.run(
            ["git", "add", "src/auth.py"], cwd=str(git_project),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update auth", "--date", "2026-03-01T10:00:00Z"],
            cwd=str(git_project), capture_output=True, check=True,
            env={**os.environ, "GIT_COMMITTER_DATE": "2026-03-01T10:00:00Z"},
        )

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) >= 1

    def test_fresh_section_not_reported(self, git_project, docs_dir):
        """Section with timestamp newer than all source changes is fresh (not reported)."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # Authentication API

            <!-- docs-meta: {"last_updated": "2026-12-01T10:00:00Z", "sources": ["src/auth.py"]} -->

            Auth module handles login.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        # Fresh sections should NOT appear in output
        assert len(entries) == 0

    def test_no_docs_meta_reported_as_unknown(self, git_project, docs_dir):
        """Section without docs-meta comment is reported as unknown staleness."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # Authentication API

            This has no docs-meta comment at all.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        unknown = [e for e in entries if "unknown" in e.get("reason", "").lower()]
        assert len(unknown) >= 1

    def test_deleted_source_file_flagged(self, git_project, docs_dir):
        """Source file that no longer exists is flagged as broken reference."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # Authentication API

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/deleted_module.py"]} -->

            This references a deleted file.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        broken = [e for e in entries if e.get("severity") == "high"]
        assert len(broken) >= 1
        assert any("deleted_module.py" in str(e.get("changed_files", [])) for e in broken)

    def test_multiple_sources_some_changed(self, git_project, docs_dir):
        """Section with multiple sources where only some changed is stale."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # User Management

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/auth.py", "src/models/user.py"]} -->

            Manages users and authentication.
        """))

        # Change only one source
        (git_project / "src" / "models" / "user.py").write_text(
            "class User:\n    name: str\n"
        )
        subprocess.run(
            ["git", "add", "src/models/user.py"], cwd=str(git_project),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update user", "--date", "2026-03-01T10:00:00Z"],
            cwd=str(git_project), capture_output=True, check=True,
            env={**os.environ, "GIT_COMMITTER_DATE": "2026-03-01T10:00:00Z"},
        )

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) >= 1


# ── Severity tests ───────────────────────────────────────────────────────────


class TestSeverity:
    """Tests for severity assignment."""

    def test_deleted_source_is_high_severity(self, git_project, docs_dir):
        """Broken reference (deleted file) should be high severity."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # API

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/gone.py"]} -->

            References deleted file.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        assert len(entries) >= 1
        assert entries[0]["severity"] == "high"

    def test_unknown_is_low_severity(self, git_project, docs_dir):
        """Unknown staleness (no docs-meta) should be low severity."""
        doc = docs_dir / "api.md"
        doc.write_text("# API\n\nNo docs-meta here.\n")

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        unknown = [e for e in entries if "unknown" in e.get("reason", "").lower()]
        assert len(unknown) >= 1
        assert unknown[0]["severity"] == "low"


# ── Output format tests ─────────────────────────────────────────────────────


class TestOutputFormat:
    """Tests for JSON output format."""

    def test_entry_has_required_fields(self, git_project, docs_dir):
        """Each entry should have document, section, reason, changed_files, severity, suggested_action."""
        doc = docs_dir / "api.md"
        doc.write_text(textwrap.dedent("""\
            # API

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/gone.py"]} -->

            Content.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        assert len(entries) >= 1
        entry = entries[0]
        assert "document" in entry
        assert "section" in entry
        assert "reason" in entry
        assert "changed_files" in entry
        assert "severity" in entry
        assert "suggested_action" in entry

    def test_empty_docs_returns_empty_list(self, git_project, docs_dir):
        """Empty docs directory should produce empty staleness array."""
        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        assert entries == []

    def test_output_is_json_serializable(self, git_project, docs_dir):
        """Output should be JSON-serializable."""
        doc = docs_dir / "api.md"
        doc.write_text("# API\n\nNo metadata.\n")

        entries = staleness_check.check_staleness(
            docs_dir=str(docs_dir),
            project_root=str(git_project),
        )
        serialized = json.dumps(entries)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized, list)


# ── Non-git handling tests ───────────────────────────────────────────────────


class TestNonGitHandling:
    """Tests for graceful handling of non-git directories."""

    def test_non_git_reports_unknown(self, tmp_path):
        """Non-git directory should report all sections as unknown."""
        docs = tmp_path / "docs"
        docs.mkdir()
        doc = docs / "api.md"
        doc.write_text(textwrap.dedent("""\
            # API

            <!-- docs-meta: {"last_updated": "2026-01-01T10:00:00Z", "sources": ["src/auth.py"]} -->

            Content.
        """))

        entries = staleness_check.check_staleness(
            docs_dir=str(docs),
            project_root=str(tmp_path),
        )
        assert len(entries) >= 1
        assert all("unknown" in e.get("reason", "").lower() or
                    "not a git" in e.get("reason", "").lower()
                    for e in entries)


# ── CLI tests ────────────────────────────────────────────────────────────────


class TestCLI:
    """Tests for CLI invocation."""

    def test_help_exits_zero(self):
        """--help should exit 0."""
        script = os.path.join(os.path.dirname(__file__), "..", "staleness-check.py")
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_cli_json_output(self, git_project, docs_dir):
        """CLI should output valid JSON to stdout."""
        doc = docs_dir / "api.md"
        doc.write_text("# API\n\nNo metadata.\n")

        script = os.path.join(os.path.dirname(__file__), "..", "staleness-check.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(git_project),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "staleness_report" in data
        assert isinstance(data["staleness_report"], list)

    def test_cli_output_file(self, git_project, docs_dir, tmp_path):
        """CLI --output should write JSON to file."""
        doc = docs_dir / "api.md"
        doc.write_text("# API\n\nNo metadata.\n")
        output_file = tmp_path / "results.json"

        script = os.path.join(os.path.dirname(__file__), "..", "staleness-check.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(git_project),
                "--output", str(output_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert isinstance(data, dict)
        assert "staleness_report" in data
        assert isinstance(data["staleness_report"], list)
