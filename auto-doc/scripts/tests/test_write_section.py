"""Tests for write-section.py -- per-section write tool with accumulation + finalize.

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
    "write-section.py",
)


def _write_content(tmp, name, text):
    """Write a temp file and return its path."""
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _write_refs(tmp, name, symbols=None, file_paths=None):
    """Write a refs JSON file and return its path."""
    refs = {"symbols": symbols or [], "file_paths": file_paths or []}
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(refs, f)
    return path


def _run_section(tmp, state_file, document, section, content_text,
                 symbols=None, file_paths=None, header_text=None,
                 project_root=None):
    """Helper: write content + refs files and call write-section.py in section mode."""
    content_file = _write_content(
        tmp, f"section-{document}-{section}.md", content_text
    )
    refs_file = _write_refs(
        tmp, f"refs-{document}-{section}.json", symbols, file_paths
    )
    cmd = [
        sys.executable, SCRIPT_PATH,
        "--state-file", state_file,
        "--document", document,
        "--section", section,
        "--content-file", content_file,
        "--refs-file", refs_file,
    ]
    if header_text is not None:
        header_file = _write_content(tmp, f"header-{document}.md", header_text)
        cmd.extend(["--header-file", header_file])
    if project_root:
        cmd.extend(["--project-root", project_root])
    return subprocess.run(cmd, capture_output=True, text=True)


def _run_finalize(state_file, docs_dir, audience, manifest_file, mode="initial"):
    """Helper: call write-section.py in finalize mode."""
    cmd = [
        sys.executable, SCRIPT_PATH,
        "--finalize",
        "--state-file", state_file,
        "--docs-dir", docs_dir,
        "--audience", audience,
        "--manifest-file", manifest_file,
        "--mode", mode,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestSectionWrite:
    """Section-write mode: accumulating sections into state."""

    def test_single_section_creates_state(self):
        """Write one section, verify state structure."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "system-overview",
                "## System Overview\n\nThe system is...\n",
                symbols=["Pipeline"], file_paths=["src/app.ts"],
            )
            assert result.returncode == 0
            assert "Wrote section ARCHITECTURE/system-overview" in result.stderr

            with open(state_file) as f:
                state = json.load(f)

            assert "ARCHITECTURE" in state["documents"]
            doc = state["documents"]["ARCHITECTURE"]
            assert doc["sections_order"] == ["system-overview"]
            assert "system-overview" in doc["sections"]
            section = doc["sections"]["system-overview"]
            assert "The system is" in section["content"]
            assert section["symbols"] == ["Pipeline"]
            assert section["file_paths"] == ["src/app.ts"]

    def test_multiple_sections_accumulate(self):
        """Write 3 sections, verify order preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            sections = [
                ("system-overview", "## System Overview\n\nOverview text\n"),
                ("data-model", "## Data Model\n\nModel text\n"),
                ("design-decisions", "## Design Decisions\n\nDecisions text\n"),
            ]
            for slug, content in sections:
                result = _run_section(
                    tmp, state_file, "ARCHITECTURE", slug, content,
                    symbols=[f"Sym_{slug}"], file_paths=[f"src/{slug}.py"],
                )
                assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            doc = state["documents"]["ARCHITECTURE"]
            assert doc["sections_order"] == [
                "system-overview", "data-model", "design-decisions",
            ]
            assert len(doc["sections"]) == 3

    def test_idempotent_overwrite(self):
        """Same section twice, content replaced, order preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write initial
            _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nOriginal\n",
                symbols=["OldSym"], file_paths=["old.py"],
            )
            # Write another section
            _run_section(
                tmp, state_file, "ARCHITECTURE", "data-model",
                "## Data Model\n\nModel\n",
            )
            # Overwrite first section
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nUpdated\n",
                symbols=["NewSym"], file_paths=["new.py"],
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            doc = state["documents"]["ARCHITECTURE"]
            # Order preserved: overview still first
            assert doc["sections_order"] == ["overview", "data-model"]
            # Content updated
            assert "Updated" in doc["sections"]["overview"]["content"]
            assert doc["sections"]["overview"]["symbols"] == ["NewSym"]

    def test_header_stored(self):
        """--header-file content stored in state."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            header = "<!-- auto-generated -->\n# Architecture\n"

            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nText\n",
                header_text=header,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            assert state["documents"]["ARCHITECTURE"]["header"] == header

    def test_missing_content_file_exits_1(self):
        """Content file absent exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            refs_file = _write_refs(tmp, "refs.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--state-file", state_file,
                 "--document", "DOC",
                 "--section", "sec",
                 "--content-file", os.path.join(tmp, "nonexistent.md"),
                 "--refs-file", refs_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "not found" in result.stderr

    def test_empty_content_file_exits_1(self):
        """Content file empty exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            content_file = _write_content(tmp, "empty.md", "   \n  \n")
            refs_file = _write_refs(tmp, "refs.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--state-file", state_file,
                 "--document", "DOC",
                 "--section", "sec",
                 "--content-file", content_file,
                 "--refs-file", refs_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "empty" in result.stderr

    def test_invalid_refs_json_exits_1(self):
        """Refs file not valid JSON exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            content_file = _write_content(tmp, "content.md", "## Heading\n\nText\n")
            refs_file = _write_content(tmp, "refs.json", "{not valid json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--state-file", state_file,
                 "--document", "DOC",
                 "--section", "sec",
                 "--content-file", content_file,
                 "--refs-file", refs_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "invalid JSON" in result.stderr

    def test_missing_refs_keys_exits_1(self):
        """Refs file lacks required keys exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            content_file = _write_content(tmp, "content.md", "## Heading\n\nText\n")
            refs_file = _write_content(tmp, "refs.json", '{"symbols": []}')

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--state-file", state_file,
                 "--document", "DOC",
                 "--section", "sec",
                 "--content-file", content_file,
                 "--refs-file", refs_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "file_paths" in result.stderr


class TestFinalize:
    """Finalize mode: assemble documents and generate manifests."""

    def _build_state(self, tmp, sections, header="# Doc\n", doc_name="ARCHITECTURE"):
        """Build a state file with given sections, return state_file path."""
        state_file = os.path.join(tmp, "state.json")
        state = {
            "documents": {
                doc_name: {
                    "header": header,
                    "sections_order": [s[0] for s in sections],
                    "sections": {
                        slug: {
                            "content": content,
                            "symbols": symbols,
                            "file_paths": fps,
                        }
                        for slug, content, symbols, fps in sections
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def test_finalize_assembles_document(self):
        """Header + 3 sections -> correct markdown file."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- auto-generated -->\n# Architecture\n"
            sections = [
                ("overview", "## Overview\n\nOverview text", ["Sym1"], ["a.py"]),
                ("data-model", "## Data Model\n\nModel text", ["Sym2"], ["b.py"]),
                ("decisions", "## Decisions\n\nDecision text", [], []),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            assert os.path.isfile(doc_path)
            with open(doc_path) as f:
                content = f.read()
            assert content.startswith("<!-- auto-generated -->")
            assert "# Architecture" in content
            assert "## Overview" in content
            assert "## Data Model" in content
            assert "## Decisions" in content
            # Sections in correct order
            assert content.index("## Overview") < content.index("## Data Model")
            assert content.index("## Data Model") < content.index("## Decisions")

    def test_finalize_generates_manifest(self):
        """Manifest matches merge-manifests.py input format."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", ["Pipeline"], ["src/app.ts"]),
                ("config", "## Config\n\nText", ["Config"], ["src/config.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file)

            with open(manifest_file) as f:
                manifest = json.load(f)

            assert "documents" in manifest
            arch = manifest["documents"]["ARCHITECTURE"]
            assert arch["overview"]["symbols"] == ["Pipeline"]
            assert arch["overview"]["file_paths"] == ["src/app.ts"]
            assert arch["config"]["symbols"] == ["Config"]

    def test_finalize_written_sections_initial(self):
        """_written_sections present in initial mode."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", ["Sym"], ["a.py"]),
                ("data-model", "## Data Model\n\nText", [], ["b.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file,
                          mode="initial")

            with open(manifest_file) as f:
                manifest = json.load(f)

            ws = manifest["documents"]["ARCHITECTURE"]["_written_sections"]
            assert ws["sections_written"] == ["overview", "data-model"]
            assert ws["symbols"] == []
            assert ws["file_paths"] == []

    def test_finalize_no_written_sections_update(self):
        """_written_sections absent in update mode."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", ["Sym"], ["a.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file,
                          mode="update")

            with open(manifest_file) as f:
                manifest = json.load(f)

            assert "_written_sections" not in manifest["documents"]["ARCHITECTURE"]

    def test_finalize_skips_empty_refs(self):
        """Sections with no symbols/file_paths omitted from manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", ["Sym"], ["a.py"]),
                ("concepts", "## Concepts\n\nPure prose", [], []),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file,
                          mode="update")

            with open(manifest_file) as f:
                manifest = json.load(f)

            arch = manifest["documents"]["ARCHITECTURE"]
            assert "overview" in arch
            assert "concepts" not in arch

    def test_finalize_cleans_state_file(self):
        """State file deleted after finalize."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", [], ["a.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert not os.path.exists(state_file)

    def test_finalize_missing_state_exits_1(self):
        """No state file exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "nonexistent.json")
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert result.returncode == 1
            assert "not found" in result.stderr

    def test_two_documents_one_audience(self):
        """Two docs in same state, finalize produces two files."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            state = {
                "documents": {
                    "ARCHITECTURE": {
                        "header": "# Architecture\n",
                        "sections_order": ["overview"],
                        "sections": {
                            "overview": {
                                "content": "## Overview\n\nArch text",
                                "symbols": ["Sym1"],
                                "file_paths": ["a.py"],
                            }
                        },
                    },
                    "DEVELOPER_GUIDE": {
                        "header": "# Developer Guide\n",
                        "sections_order": ["setup"],
                        "sections": {
                            "setup": {
                                "content": "## Setup\n\nSetup text",
                                "symbols": ["Sym2"],
                                "file_paths": ["b.py"],
                            }
                        },
                    },
                }
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)

            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert result.returncode == 0

            assert os.path.isfile(
                os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            )
            assert os.path.isfile(
                os.path.join(docs_dir, "developers", "DEVELOPER_GUIDE.md")
            )

            with open(manifest_file) as f:
                manifest = json.load(f)
            assert "ARCHITECTURE" in manifest["documents"]
            assert "DEVELOPER_GUIDE" in manifest["documents"]


class TestSymbolValidation:
    """Advisory symbol validation with --project-root."""

    def test_symbol_found_no_warning(self):
        """Matching symbols, no WARNING."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Create a Python file with the symbol
            src_dir = os.path.join(tmp, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "models.py"), "w") as f:
                f.write("class Pipeline:\n    pass\n")

            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nUses Pipeline\n",
                symbols=["Pipeline"], file_paths=["src/models.py"],
                project_root=tmp,
            )
            assert result.returncode == 0
            assert "WARNING" not in result.stderr

    def test_symbol_not_found_warns(self):
        """Missing symbol, WARNING on stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Create a Python file WITHOUT the referenced symbol
            src_dir = os.path.join(tmp, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "models.py"), "w") as f:
                f.write("class User:\n    pass\n")

            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nUses ArchiveBase\n",
                symbols=["ArchiveBase"], file_paths=["src/models.py"],
                project_root=tmp,
            )
            assert result.returncode == 0
            assert "WARNING" in result.stderr
            assert "ArchiveBase" in result.stderr
            # State should still be written (advisory only)
            assert os.path.isfile(state_file)
