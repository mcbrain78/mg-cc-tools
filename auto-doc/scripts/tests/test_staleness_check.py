"""Tests for staleness-check.py -- XML-ref-based section freshness analysis."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys

import pytest

# Add scripts directory to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import module with hyphenated filename via importlib
_loader = importlib.machinery.SourceFileLoader(
    "staleness_check",
    os.path.join(os.path.dirname(__file__), "..", "staleness-check.py"),
)
_spec = importlib.util.spec_from_loader("staleness_check", _loader)
assert _spec is not None
staleness_check = importlib.util.module_from_spec(_spec)
_loader.exec_module(staleness_check)


# ── XML fixture helpers ──────────────────────────────────────────────────────


def _xml_doc(audience, sections_xml):
    """Build a minimal XML source document string around one or more
    <section> elements.

    Args:
        audience: Audience attribute value (empty string for shared docs).
        sections_xml: Raw XML string for one or more <section> elements.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<document audience="{audience}" diataxis="how-to">\n'
        '  <meta>\n'
        '    <title>Doc</title>\n'
        '    <generated>2026-01-01</generated>\n'
        '    <header><![CDATA[# Doc]]></header>\n'
        '  </meta>\n'
        f'  {sections_xml}\n'
        '</document>\n'
    )


def _section(slug, last_updated, refs_xml="", body="body", children_xml=""):
    """Build a <section> XML string with the given slug, last-updated,
    inner refs XML, body, and nested section XML."""
    last_updated_attr = f' last-updated="{last_updated}"' if last_updated else ""
    return (
        f'<section slug="{slug}"{last_updated_attr}>'
        f'<refs>{refs_xml}</refs>'
        f'<body><![CDATA[{body}]]></body>'
        f'{children_xml}'
        '</section>'
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def git_project(tmp_path):
    """Create a temporary git repository with source files and xml sources."""
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

    # Source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text("class Auth:\n    pass\n")
    (src / "models").mkdir()
    (src / "models" / "user.py").write_text("class User:\n    pass\n")
    (tmp_path / "prefect.yaml").write_text("version: 0\n")

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

    # XML source directory
    xml_dir = tmp_path / "xml-sources"
    xml_dir.mkdir()

    return tmp_path


@pytest.fixture
def xml_dir(git_project):
    """Return the xml-sources subdirectory."""
    return git_project / "xml-sources"


def _touch_commit(project_root, rel_path, new_text, date_str):
    """Modify a file and commit with a specific date."""
    (project_root / rel_path).write_text(new_text)
    subprocess.run(
        ["git", "add", rel_path], cwd=str(project_root),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"update {rel_path}", "--date", date_str],
        cwd=str(project_root), capture_output=True, check=True,
        env={**os.environ, "GIT_COMMITTER_DATE": date_str},
    )


# ── Staleness detection tests ────────────────────────────────────────────────


class TestStalenessDetection:
    """Tests for detecting stale sections via XML ref anchors."""

    def test_config_ref_stale_section_detected(self, git_project, xml_dir):
        """config.path ref whose source changed after last_updated -> stale."""
        section = _section(
            slug="auth",
            last_updated="2026-01-01",
            refs_xml='<config>src/auth.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        _touch_commit(
            git_project, "src/auth.py",
            "class Auth:\n    def login(self): pass\n",
            "2026-03-01T10:00:00Z",
        )

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) == 1
        assert stale[0]["section"] == "auth"

    def test_code_module_ref_stale_section_detected(self, git_project, xml_dir):
        """code.function ref with module attr triggers staleness the same way.

        Only function refs carry a module attribute in the XML schema;
        class refs do not (see lib/xml_doc.py::_parse_code_refs). This is
        the anchor the staleness check relies on for code refs.
        """
        section = _section(
            slug="users",
            last_updated="2026-02-01",
            refs_xml=(
                '<code>'
                '<function name="login" module="src/auth.py" />'
                '</code>'
            ),
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        _touch_commit(
            git_project, "src/auth.py",
            "class Auth:\n    def login(self): pass\n",
            "2026-03-01T10:00:00Z",
        )

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) == 1
        assert "src/auth.py" in stale[0]["changed_files"]

    def test_fresh_section_not_reported(self, git_project, xml_dir):
        """Section whose last_updated is newer than all sources -> not reported."""
        section = _section(
            slug="auth",
            last_updated="2026-12-01",
            refs_xml='<config>src/auth.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert entries == []

    def test_section_without_last_updated_reported_as_unknown(self, git_project, xml_dir):
        """Section with no last-updated attribute -> unknown staleness."""
        section = _section(
            slug="auth",
            last_updated="",
            refs_xml='<config>src/auth.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        unknown = [e for e in entries if "unknown" in e.get("reason", "").lower()]
        assert len(unknown) == 1
        assert unknown[0]["severity"] == "low"

    def test_section_without_file_refs_is_fresh(self, git_project, xml_dir):
        """Section with only db/enum/env/literal refs has no anchor -> fresh (not reported)."""
        section = _section(
            slug="concepts",
            last_updated="2026-01-01",
            refs_xml='<literal>example</literal><env>API_KEY</env>',
        )
        (xml_dir / "glossary.xml").write_text(_xml_doc("", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert entries == []

    def test_deleted_source_file_flagged(self, git_project, xml_dir):
        """Source file that no longer exists -> broken / high severity."""
        section = _section(
            slug="gone",
            last_updated="2026-01-01",
            refs_xml='<config>src/deleted_module.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert len(entries) == 1
        assert entries[0]["severity"] == "high"
        assert "src/deleted_module.py" in entries[0]["changed_files"]

    def test_multiple_sources_some_changed(self, git_project, xml_dir):
        """Section with multiple refs where only some changed -> stale."""
        section = _section(
            slug="users",
            last_updated="2026-02-01",
            refs_xml=(
                '<config>src/auth.py</config>'
                '<code><function name="get_user" module="src/models/user.py" /></code>'
            ),
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        _touch_commit(
            git_project, "src/models/user.py",
            "class User:\n    name: str\n",
            "2026-03-01T10:00:00Z",
        )

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) == 1
        assert stale[0]["changed_files"] == ["src/models/user.py"]

    def test_nested_section_path_is_slash_separated(self, git_project, xml_dir):
        """Nested child section is reported with slash-separated path."""
        child = _section(
            slug="login",
            last_updated="2026-01-01",
            refs_xml='<config>src/auth.py</config>',
        )
        parent = _section(
            slug="auth",
            last_updated="2026-12-01",
            refs_xml="",
            children_xml=child,
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", parent))

        _touch_commit(
            git_project, "src/auth.py",
            "class Auth:\n    def login(self): pass\n",
            "2026-03-01T10:00:00Z",
        )

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) == 1
        assert stale[0]["section"] == "auth/login"


# ── Severity tests ───────────────────────────────────────────────────────────


class TestSeverity:
    """Tests for severity assignment."""

    def test_deleted_source_is_high_severity(self, git_project, xml_dir):
        section = _section(
            slug="gone",
            last_updated="2026-01-01",
            refs_xml='<config>src/gone.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert len(entries) == 1
        assert entries[0]["severity"] == "high"

    def test_unknown_is_low_severity(self, git_project, xml_dir):
        section = _section(slug="empty", last_updated="")
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        unknown = [e for e in entries if "unknown" in e.get("reason", "").lower()]
        assert len(unknown) == 1
        assert unknown[0]["severity"] == "low"

    def test_three_changed_sources_is_high_severity(self, git_project, xml_dir):
        """>= 3 changed source files -> high severity."""
        (git_project / "src" / "extra.py").write_text("x = 1\n")
        subprocess.run(
            ["git", "add", "src/extra.py"], cwd=str(git_project),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add extra", "--date", "2026-01-01T10:00:00Z"],
            cwd=str(git_project), capture_output=True, check=True,
            env={**os.environ, "GIT_COMMITTER_DATE": "2026-01-01T10:00:00Z"},
        )

        section = _section(
            slug="wide",
            last_updated="2026-02-01",
            refs_xml=(
                '<config>src/auth.py</config>'
                '<config>src/extra.py</config>'
                '<code><function name="get_user" module="src/models/user.py" /></code>'
            ),
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        for rel in ["src/auth.py", "src/extra.py", "src/models/user.py"]:
            _touch_commit(
                git_project, rel, "# changed\n", "2026-03-01T10:00:00Z",
            )

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        stale = [e for e in entries if "stale" in e.get("reason", "").lower()]
        assert len(stale) == 1
        assert stale[0]["severity"] == "high"
        assert len(stale[0]["changed_files"]) == 3


# ── Output format tests ─────────────────────────────────────────────────────


class TestOutputFormat:
    def test_entry_has_required_fields(self, git_project, xml_dir):
        section = _section(
            slug="gone",
            last_updated="2026-01-01",
            refs_xml='<config>src/gone.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert len(entries) == 1
        entry = entries[0]
        for key in (
            "document", "section", "reason",
            "changed_files", "severity", "suggested_action",
        ):
            assert key in entry

    def test_empty_xml_dir_returns_empty_list(self, git_project, xml_dir):
        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        assert entries == []

    def test_output_is_json_serializable(self, git_project, xml_dir):
        section = _section(slug="empty", last_updated="")
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(git_project)
        )
        data = {"staleness_report": entries}
        assert json.loads(json.dumps(data)) == data


# ── Non-git handling ─────────────────────────────────────────────────────────


class TestNonGitHandling:
    def test_non_git_reports_unknown(self, tmp_path):
        xml_dir = tmp_path / "xml-sources"
        xml_dir.mkdir()
        section = _section(
            slug="auth",
            last_updated="2026-01-01",
            refs_xml='<config>src/auth.py</config>',
        )
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        entries = staleness_check.check_staleness(
            xml_dir=str(xml_dir), project_root=str(tmp_path)
        )
        assert len(entries) == 1
        assert "not a git" in entries[0]["reason"].lower()
        assert entries[0]["severity"] == "low"


# ── CLI tests ────────────────────────────────────────────────────────────────


class TestCLI:
    def test_cli_json_output(self, git_project, xml_dir):
        section = _section(slug="empty", last_updated="")
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))

        script = os.path.join(os.path.dirname(__file__), "..", "staleness-check.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--xml-dir", str(xml_dir),
                "--project-root", str(git_project),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "staleness_report" in data
        assert isinstance(data["staleness_report"], list)

    def test_cli_output_file(self, git_project, xml_dir, tmp_path):
        section = _section(slug="empty", last_updated="")
        (xml_dir / "api.xml").write_text(_xml_doc("end-users", section))
        output_file = tmp_path / "results.json"

        script = os.path.join(os.path.dirname(__file__), "..", "staleness-check.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--xml-dir", str(xml_dir),
                "--project-root", str(git_project),
                "--output", str(output_file),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "staleness_report" in data
