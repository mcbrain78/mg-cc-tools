"""Tests for post-install-configure.py.

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
    "post-install-configure.py",
)


def _run(args, **kwargs):
    """Run post-install-configure.py with given args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
        **kwargs,
    )


# ── Permission tests ──────────────────────────────────────────────


class TestPermissions:
    """Tests for settings.local.json permission configuration."""

    def test_creates_settings_file_when_missing(self, tmp_path):
        """Creates settings.local.json with permissions when file doesn't exist."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "permissions=ADDED" in result.stdout
        assert settings.exists()

        data = json.loads(settings.read_text())
        allow = data["permissions"]["allow"]
        assert "Write(path:.mg/)" in allow
        assert "Write(path:docs/auto-doc/)" in allow

    def test_adds_to_existing_settings(self, tmp_path):
        """Adds permissions to existing settings.local.json without clobbering."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)

        existing = {
            "permissions": {
                "allow": ["Bash(ls:*)"]
            }
        }
        settings.write_text(json.dumps(existing))

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "permissions=ADDED" in result.stdout

        data = json.loads(settings.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(ls:*)" in allow  # preserved
        assert "Write(path:.mg/)" in allow
        assert "Write(path:docs/auto-doc/)" in allow

    def test_idempotent_when_already_present(self, tmp_path):
        """Returns OK when permissions already exist."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)

        existing = {
            "permissions": {
                "allow": [
                    "Write(path:.mg/)",
                    "Write(path:docs/auto-doc/)",
                ]
            }
        }
        settings.write_text(json.dumps(existing))

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "permissions=OK" in result.stdout

    def test_adds_only_missing_permission(self, tmp_path):
        """Adds only the permission that's missing, not duplicates."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)

        existing = {
            "permissions": {
                "allow": ["Write(path:.mg/)"]
            }
        }
        settings.write_text(json.dumps(existing))

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "permissions=ADDED" in result.stdout

        data = json.loads(settings.read_text())
        allow = data["permissions"]["allow"]
        # Should have exactly one .mg/ entry (not duplicated)
        assert allow.count("Write(path:.mg/)") == 1
        assert "Write(path:docs/auto-doc/)" in allow

    def test_preserves_other_keys(self, tmp_path):
        """Preserves non-permissions keys in settings.local.json."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)

        existing = {
            "someOtherKey": True,
            "permissions": {"allow": []}
        }
        settings.write_text(json.dumps(existing))

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        data = json.loads(settings.read_text())
        assert data["someOtherKey"] is True


# ── Gitignore tests ───────────────────────────────────────────────


class TestGitignore:
    """Tests for .gitignore configuration."""

    def test_creates_gitignore_when_missing(self, tmp_path):
        """Creates .gitignore with .mg/ entry when file doesn't exist."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "gitignore=ADDED" in result.stdout

        gitignore = project / ".gitignore"
        assert gitignore.exists()
        assert ".mg/" in gitignore.read_text()

    def test_appends_to_existing_gitignore(self, tmp_path):
        """Appends .mg/ to existing .gitignore without clobbering."""
        project = tmp_path / "project"
        project.mkdir()
        gitignore = project / ".gitignore"
        gitignore.write_text("node_modules/\n.env\n")

        settings = project / ".claude" / "settings.local.json"

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "gitignore=ADDED" in result.stdout

        content = gitignore.read_text()
        assert "node_modules/" in content  # preserved
        assert ".env" in content  # preserved
        assert ".mg/" in content  # added

    def test_idempotent_when_already_present(self, tmp_path):
        """Returns OK when .mg/ already in .gitignore."""
        project = tmp_path / "project"
        project.mkdir()
        gitignore = project / ".gitignore"
        gitignore.write_text("node_modules/\n.mg/\n")

        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({
            "permissions": {
                "allow": [
                    "Write(path:.mg/)",
                    "Write(path:docs/auto-doc/)",
                ]
            }
        }))

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        assert "gitignore=OK" in result.stdout

    def test_handles_missing_trailing_newline(self, tmp_path):
        """Appends correctly when .gitignore doesn't end with newline."""
        project = tmp_path / "project"
        project.mkdir()
        gitignore = project / ".gitignore"
        gitignore.write_text("node_modules/")  # no trailing newline

        settings = project / ".claude" / "settings.local.json"

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode == 0
        content = gitignore.read_text()
        # Should have proper newline separation
        lines = content.splitlines()
        assert "node_modules/" in lines
        assert ".mg/" in lines


# ── Error handling tests ──────────────────────────────────────────


class TestErrors:
    """Tests for error handling."""

    def test_fails_for_missing_project_root(self, tmp_path):
        """Exits with error when project root doesn't exist."""
        result = _run([
            "--project-root", str(tmp_path / "nonexistent"),
            "--settings-path", str(tmp_path / "settings.json"),
        ])

        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_fails_for_invalid_json(self, tmp_path):
        """Exits with error when settings.local.json contains invalid JSON."""
        project = tmp_path / "project"
        project.mkdir()
        settings = project / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{ invalid json !!!")

        result = _run([
            "--project-root", str(project),
            "--settings-path", str(settings),
        ])

        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_fails_without_required_args(self):
        """Exits with error when required arguments are missing."""
        result = _run([])
        assert result.returncode != 0
