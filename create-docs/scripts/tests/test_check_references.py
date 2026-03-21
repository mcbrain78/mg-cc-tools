"""Tests for check-references.py -- file path and symbol reference checking."""

import importlib
import json
import os
import sys

import pytest

# Add scripts directory to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import module with hyphenated filename via importlib
_loader = importlib.machinery.SourceFileLoader(
    "check_references",
    os.path.join(os.path.dirname(__file__), "..", "check-references.py"),
)
_spec = importlib.util.spec_from_loader("check_references", _loader)
check_references = importlib.util.module_from_spec(_spec)
_loader.exec_module(check_references)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path):
    """Create a temporary project directory with source files."""
    # Create some source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("class MyClass:\n    def method(self):\n        pass\n")
    (src / "utils.py").write_text("def helper_func():\n    return True\n")
    (src / "models").mkdir()
    (src / "models" / "user.py").write_text("class UserModel:\n    pass\n")

    # Create a docs directory
    docs = tmp_path / "docs"
    docs.mkdir()

    return tmp_path


@pytest.fixture
def docs_dir(project_dir):
    """Return the docs subdirectory of the project."""
    return project_dir / "docs"


# ── File path detection tests ────────────────────────────────────────────────


class TestFilePathDetection:
    """Tests for detecting and validating file path references in markdown."""

    def test_valid_file_path_no_issues(self, project_dir, docs_dir):
        """Markdown referencing an existing file should report 0 issues."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/main.py` for the entry point.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 0

    def test_broken_file_path_reports_issue(self, project_dir, docs_dir):
        """Markdown referencing a non-existent file should report an issue."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 1
        assert broken[0]["reference"] == "src/deleted.py"
        assert broken[0]["type"] == "file_path"
        assert broken[0]["line"] == 1

    def test_multiple_refs_on_same_line(self, project_dir, docs_dir):
        """Multiple file refs on one line should each be checked."""
        doc = docs_dir / "api.md"
        doc.write_text("Compare `src/main.py` and `src/missing.py`\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 1
        assert broken[0]["reference"] == "src/missing.py"

    def test_url_skipped(self, project_dir, docs_dir):
        """URLs (http/https) should not be treated as file paths."""
        doc = docs_dir / "api.md"
        doc.write_text("See `https://example.com/docs/api.py` for info.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 0

    def test_anchor_skipped(self, project_dir, docs_dir):
        """Anchors (#section) should not be treated as file paths."""
        doc = docs_dir / "api.md"
        doc.write_text("See `#installation` section.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 0

    def test_directory_reference_valid(self, project_dir, docs_dir):
        """Referencing an existing directory should be valid."""
        doc = docs_dir / "api.md"
        doc.write_text("Source code is in `src/models`.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 0

    def test_code_block_file_paths_checked(self, project_dir, docs_dir):
        """File paths inside code blocks should be detected."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```\n"
            "# Edit src/main.py\n"
            "# Also check src/nonexistent.py\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        # src/nonexistent.py is broken, src/main.py is valid
        broken_refs = [i["reference"] for i in broken]
        assert "src/nonexistent.py" in broken_refs

    def test_relative_path_resolved_against_project_root(self, project_dir, docs_dir):
        """Relative paths should be resolved against --project-root."""
        doc = docs_dir / "api.md"
        doc.write_text("Main source: `src/utils.py`\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken = [i for i in issues if i["status"] == "broken"]
        assert len(broken) == 0


# ── Symbol detection tests ───────────────────────────────────────────────────


class TestSymbolDetection:
    """Tests for detecting symbol references in code blocks."""

    def test_valid_symbol_no_issue(self, project_dir, docs_dir):
        """Symbol found in source file should not report broken."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "# In src/main.py:\n"
            "obj = MyClass()\n"
            "obj.method()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken_symbols = [
            i for i in issues
            if i["status"] == "broken" and i["type"] == "symbol"
        ]
        assert len(broken_symbols) == 0

    def test_broken_symbol_reports_issue(self, project_dir, docs_dir):
        """Symbol not found in any source file should report issue."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "# In src/main.py:\n"
            "obj = NonExistentClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        broken_symbols = [
            i for i in issues
            if i["status"] == "broken" and i["type"] == "symbol"
        ]
        assert len(broken_symbols) >= 1
        refs = [i["reference"] for i in broken_symbols]
        assert any("NonExistentClass" in r for r in refs)

    def test_skip_symbol_check_marks_unchecked(self, project_dir, docs_dir):
        """With skip_symbol_check=True, symbols should be extracted but status='unchecked'."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "obj = MyClass()\n"
            "bad = NonExistentClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
            skip_symbol_check=True,
        )
        symbol_issues = [i for i in issues if i["type"] == "symbol"]
        assert len(symbol_issues) >= 2
        # All symbols should be "unchecked", not "valid" or "broken"
        for issue in symbol_issues:
            assert issue["status"] == "unchecked"


# ── Output format tests ─────────────────────────────────────────────────────


class TestOutputFormat:
    """Tests for JSON output format and structure."""

    def test_issue_has_required_fields(self, project_dir, docs_dir):
        """Each issue should have file, line, reference, type, status, message."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        assert len(issues) >= 1
        issue = issues[0]
        assert "file" in issue
        assert "line" in issue
        assert "reference" in issue
        assert "type" in issue
        assert "status" in issue
        assert "message" in issue

    def test_empty_docs_returns_empty_list(self, project_dir, docs_dir):
        """Empty docs directory should produce empty issues array."""
        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        assert issues == []

    def test_output_is_json_serializable(self, project_dir, docs_dir):
        """Output should be JSON-serializable."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/main.py` and `src/deleted.py`.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        serialized = json.dumps(issues)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized, list)


# ── CLI tests ────────────────────────────────────────────────────────────────


class TestCLI:
    """Tests for CLI invocation."""

    def test_help_exits_zero(self):
        """--help should exit 0."""
        import subprocess

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_cli_json_output(self, project_dir, docs_dir):
        """CLI should output valid JSON to stdout."""
        import subprocess

        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(project_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_cli_output_file(self, project_dir, docs_dir, tmp_path):
        """CLI --output should write JSON to file."""
        import subprocess

        doc = docs_dir / "api.md"
        doc.write_text("See `src/main.py` for details.\n")
        output_file = tmp_path / "results.json"

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(project_dir),
                "--output", str(output_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert isinstance(data, list)

    def test_cli_output_broken(self, project_dir, docs_dir, tmp_path):
        """CLI --output-broken should write only broken file_path entries."""
        import subprocess

        doc = docs_dir / "api.md"
        doc.write_text(
            "See `src/main.py` and `src/deleted.py` for details.\n"
            "```python\n"
            "obj = MyClass()\n"
            "```\n"
        )
        broken_file = tmp_path / "broken.json"

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(project_dir),
                "--output-broken", str(broken_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert broken_file.exists()
        data = json.loads(broken_file.read_text())
        assert isinstance(data, list)
        # Only broken file_path entries
        for entry in data:
            assert entry["type"] == "file_path"
            assert entry["status"] == "broken"
        # src/deleted.py should appear
        refs = [e["reference"] for e in data]
        assert "src/deleted.py" in refs
        # src/main.py (valid) should NOT appear
        assert "src/main.py" not in refs

    def test_cli_output_symbols(self, project_dir, docs_dir, tmp_path):
        """CLI --output-symbols should write only symbol entries."""
        import subprocess

        doc = docs_dir / "api.md"
        doc.write_text(
            "See `src/deleted.py` for details.\n"
            "```python\n"
            "obj = MyClass()\n"
            "bad = NonExistentClass()\n"
            "```\n"
        )
        symbols_file = tmp_path / "symbols.json"

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(project_dir),
                "--skip-symbol-check",
                "--output-symbols", str(symbols_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert symbols_file.exists()
        data = json.loads(symbols_file.read_text())
        assert isinstance(data, list)
        # Only symbol entries
        for entry in data:
            assert entry["type"] == "symbol"
        # File path entries should NOT appear
        refs = [e["reference"] for e in data]
        assert "src/deleted.py" not in refs

    def test_cli_split_output_both_files(self, project_dir, docs_dir, tmp_path):
        """CLI with both --output-broken and --output-symbols writes two files."""
        import subprocess

        doc = docs_dir / "api.md"
        doc.write_text(
            "See `src/deleted.py` for details.\n"
            "```python\n"
            "obj = NonExistentClass()\n"
            "```\n"
        )
        broken_file = tmp_path / "broken.json"
        symbols_file = tmp_path / "symbols.json"

        script = os.path.join(os.path.dirname(__file__), "..", "check-references.py")
        result = subprocess.run(
            [
                sys.executable, script,
                "--docs-dir", str(docs_dir),
                "--project-root", str(project_dir),
                "--skip-symbol-check",
                "--output-broken", str(broken_file),
                "--output-symbols", str(symbols_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert broken_file.exists()
        assert symbols_file.exists()
        broken_data = json.loads(broken_file.read_text())
        symbols_data = json.loads(symbols_file.read_text())
        # Broken should have file_path entries
        for entry in broken_data:
            assert entry["type"] == "file_path"
        # Symbols should have symbol entries
        for entry in symbols_data:
            assert entry["type"] == "symbol"


# ── Grouped output tests ────────────────────────────────────────────────────


class TestGroupedOutput:
    """Tests for grouped output format (post-processing functions)."""

    def test_broken_file_paths_grouped(self, project_dir, docs_dir):
        """Broken file paths should be grouped by reference."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        grouped = check_references.group_broken_file_paths(issues, str(docs_dir))
        assert len(grouped) == 1
        assert grouped[0]["reference"] == "src/deleted.py"
        assert grouped[0]["type"] == "file_path"
        assert grouped[0]["status"] == "broken"
        assert isinstance(grouped[0]["locations"], list)
        assert len(grouped[0]["locations"]) == 1

    def test_valid_file_paths_excluded(self, project_dir, docs_dir):
        """Valid file paths should not appear in grouped broken output."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/main.py` for the entry point.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        grouped = check_references.group_broken_file_paths(issues, str(docs_dir))
        assert len(grouped) == 0

    def test_deduplication_across_docs(self, project_dir, docs_dir):
        """Same reference from multiple docs should produce one entry with multiple locations."""
        doc1 = docs_dir / "api.md"
        doc1.write_text("See `src/deleted.py` for details.\n")
        doc2 = docs_dir / "guide.md"
        doc2.write_text("Also see `src/deleted.py` here.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        grouped = check_references.group_broken_file_paths(issues, str(docs_dir))
        assert len(grouped) == 1
        assert grouped[0]["reference"] == "src/deleted.py"
        assert len(grouped[0]["locations"]) == 2

    def test_locations_relativized(self, project_dir, docs_dir):
        """Locations should use relative paths (no absolute paths)."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        grouped = check_references.group_broken_file_paths(issues, str(docs_dir))
        assert len(grouped) == 1
        for loc in grouped[0]["locations"]:
            # Should not contain the absolute docs_dir path
            assert str(docs_dir) not in loc
            # Should be like "api.md:1"
            assert "api.md:" in loc

    def test_no_message_field_in_grouped(self, project_dir, docs_dir):
        """Grouped output should not contain a message field."""
        doc = docs_dir / "api.md"
        doc.write_text("See `src/deleted.py` for details.\n")

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
        )
        grouped = check_references.group_broken_file_paths(issues, str(docs_dir))
        for entry in grouped:
            assert "message" not in entry

    def test_symbols_grouped(self, project_dir, docs_dir):
        """Symbols should be grouped by reference."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "obj = MyClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
            skip_symbol_check=True,
        )
        grouped = check_references.group_symbols(issues, str(docs_dir))
        assert len(grouped) >= 1
        refs = [e["reference"] for e in grouped]
        assert "MyClass" in refs
        for entry in grouped:
            assert entry["type"] == "symbol"
            assert "locations" in entry
            assert "message" not in entry

    def test_symbols_deduplication(self, project_dir, docs_dir):
        """Same symbol from multiple docs should produce one entry with multiple locations."""
        doc1 = docs_dir / "api.md"
        doc1.write_text(
            "```python\n"
            "obj = MyClass()\n"
            "```\n"
        )
        doc2 = docs_dir / "guide.md"
        doc2.write_text(
            "```python\n"
            "obj = MyClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
            skip_symbol_check=True,
        )
        grouped = check_references.group_symbols(issues, str(docs_dir))
        myclass_entries = [e for e in grouped if e["reference"] == "MyClass"]
        assert len(myclass_entries) == 1
        assert len(myclass_entries[0]["locations"]) == 2

    def test_symbols_no_message_field(self, project_dir, docs_dir):
        """Grouped symbol output should not contain a message field."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "obj = NonExistentClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
            skip_symbol_check=True,
        )
        grouped = check_references.group_symbols(issues, str(docs_dir))
        for entry in grouped:
            assert "message" not in entry

    def test_symbols_locations_relativized(self, project_dir, docs_dir):
        """Symbol locations should use relative paths."""
        doc = docs_dir / "api.md"
        doc.write_text(
            "```python\n"
            "obj = MyClass()\n"
            "```\n"
        )

        issues = check_references.check_docs(
            docs_dir=str(docs_dir),
            project_root=str(project_dir),
            skip_symbol_check=True,
        )
        grouped = check_references.group_symbols(issues, str(docs_dir))
        for entry in grouped:
            for loc in entry["locations"]:
                assert str(docs_dir) not in loc
                assert "api.md:" in loc
