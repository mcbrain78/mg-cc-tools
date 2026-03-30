"""Tests for write-section.py -- per-section write tool with accumulation + finalize.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.xml_doc import parse_xml_doc

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


def _write_refs(tmp, name, typed_refs=None):
    """Write a refs JSON file and return its path."""
    refs = {"typed_refs": typed_refs or []}
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(refs, f)
    return path


def _make_typed_refs(symbols=None, file_paths=None):
    """Build typed_refs from simple symbols/file_paths for backward-compat in tests."""
    refs = []
    file_paths = file_paths or []
    # Create code refs for each symbol, associating with first .py file_path
    py_module = next((fp for fp in file_paths if fp.endswith(".py")), "")
    for sym in (symbols or []):
        ref = {"type": "code", "kind": "class", "name": sym}
        if py_module:
            ref["module"] = py_module
        refs.append(ref)
    # Add config refs for non-.py file_paths
    for fp in file_paths:
        if not fp.endswith(".py"):
            refs.append({"type": "config", "path": fp})
    return refs


def _run_section(tmp, state_file, document, section, content_text,
                 symbols=None, file_paths=None, header_text=None,
                 project_root=None, typed_refs=None):
    """Helper: write content + refs files and call write-section.py in section mode."""
    content_file = _write_content(
        tmp, f"section-{document}-{section}.md", content_text
    )
    if typed_refs is None:
        typed_refs = _make_typed_refs(symbols, file_paths)
    refs_file = _write_refs(
        tmp, f"refs-{document}-{section}.json", typed_refs
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


def _run_finalize(state_file, docs_dir, audience, manifest_file, mode="initial",
                   merge=False, xml_dir=None):
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
    if merge:
        cmd.append("--merge")
    if xml_dir:
        cmd.extend(["--xml-dir", xml_dir])
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
            assert "typed_refs" in section

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

    def test_typed_refs_derives_symbols_and_file_paths(self):
        """typed_refs with code and config refs derive correct symbols/file_paths."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            typed_refs = [
                {"type": "code", "kind": "function", "name": "load_json",
                 "module": "lib/json_io.py"},
                {"type": "code", "kind": "class", "name": "Pipeline",
                 "module": "src/pipeline.py"},
                {"type": "config", "path": "config/settings.yaml"},
                {"type": "db", "schema": "public", "table": "users"},
                {"type": "env", "name": "DATABASE_URL"},
            ]
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nText\n",
                typed_refs=typed_refs,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            section = state["documents"]["ARCHITECTURE"]["sections"]["overview"]
            assert section["symbols"] == ["load_json", "Pipeline"]
            assert section["file_paths"] == [
                "lib/json_io.py", "src/pipeline.py", "config/settings.yaml",
            ]
            assert section["typed_refs"] == typed_refs

    def test_empty_typed_refs(self):
        """Empty typed_refs results in empty symbols/file_paths."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                "## Overview\n\nText\n",
                typed_refs=[],
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            section = state["documents"]["ARCHITECTURE"]["sections"]["overview"]
            assert section["symbols"] == []
            assert section["file_paths"] == []
            assert section["typed_refs"] == []

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

    def test_missing_typed_refs_exits_1(self):
        """Refs file without typed_refs key exits 1."""
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
            assert "typed_refs" in result.stderr


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
                            "typed_refs": _make_typed_refs(symbols, fps),
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

    def test_finalize_manifest_from_typed_refs(self):
        """Manifest symbols/file_paths come from typed_refs derivation."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            typed_refs = [
                {"type": "code", "kind": "function", "name": "load_json",
                 "module": "lib/json_io.py"},
                {"type": "config", "path": "config/app.yaml"},
            ]
            state = {
                "documents": {
                    "ARCHITECTURE": {
                        "header": "# Arch\n",
                        "sections_order": ["overview"],
                        "sections": {
                            "overview": {
                                "content": "## Overview\n\nText",
                                "symbols": ["load_json"],
                                "file_paths": ["lib/json_io.py", "config/app.yaml"],
                                "typed_refs": typed_refs,
                            }
                        },
                    }
                }
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)

            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert result.returncode == 0

            with open(manifest_file) as f:
                manifest = json.load(f)

            entry = manifest["documents"]["ARCHITECTURE"]["overview"]
            assert entry["symbols"] == ["load_json"]
            assert entry["file_paths"] == ["lib/json_io.py", "config/app.yaml"]
            assert "calls" not in entry

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
                                "typed_refs": _make_typed_refs(["Sym1"], ["a.py"]),
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
                                "typed_refs": _make_typed_refs(["Sym2"], ["b.py"]),
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


class TestMergeMode:
    """Finalize with --merge: merge new sections into existing documents."""

    def _build_state(self, tmp, sections, header="", doc_name="ARCHITECTURE"):
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
                            "typed_refs": _make_typed_refs(symbols, fps),
                        }
                        for slug, content, symbols, fps in sections
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def _write_existing_doc(self, tmp, audience, doc_name, content):
        """Write an existing document file and return its path."""
        doc_dir = os.path.join(tmp, "docs", audience)
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f"{doc_name}.md")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(content)
        return doc_path

    def test_merge_replaces_matching_section(self):
        """Existing section replaced, others preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            existing_content = (
                "<!-- auto-generated -->\n# Architecture\n\n"
                "## Overview\n\nOld overview text\n\n"
                "## Data Model\n\nExisting data model\n\n"
                "## Auth Flow\n\nExisting auth flow\n\n"
                "## Config\n\nExisting config\n\n"
                "## Deployment\n\nExisting deployment\n"
            )
            self._write_existing_doc(
                tmp, "developers", "ARCHITECTURE", existing_content,
            )

            # State has 1 replacement (overview) + 1 new section (testing)
            sections = [
                ("overview", "## Overview\n<!-- docs-meta: ... -->\n\nUpdated overview text",
                 ["Sym1"], ["a.py"]),
                ("testing", "## Testing\n<!-- docs-meta: ... -->\n\nBrand new testing section",
                 ["Sym2"], ["b.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                mode="update", merge=True,
            )
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            with open(doc_path) as f:
                content = f.read()

            # Header preserved
            assert "<!-- auto-generated -->" in content
            assert "# Architecture" in content
            # Replaced section has new content
            assert "Updated overview text" in content
            assert "Old overview text" not in content
            # Unmodified sections preserved
            assert "Existing data model" in content
            assert "Existing auth flow" in content
            assert "Existing config" in content
            assert "Existing deployment" in content
            # New section appended
            assert "Brand new testing section" in content
            # Total: 6 sections (5 existing + 1 new)
            assert content.count("\n## ") == 6

    def test_merge_preserves_order(self):
        """Section order from existing doc preserved, new sections appended."""
        with tempfile.TemporaryDirectory() as tmp:
            existing_content = (
                "# Doc\n\n"
                "## Alpha\n\nAlpha content\n\n"
                "## Beta\n\nBeta content\n\n"
                "## Gamma\n\nGamma content\n"
            )
            self._write_existing_doc(
                tmp, "developers", "ARCHITECTURE", existing_content,
            )

            sections = [
                ("beta", "## Beta\n\nUpdated Beta", [], []),
                ("delta", "## Delta\n\nNew Delta", [], []),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                mode="update", merge=True,
            )
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            with open(doc_path) as f:
                content = f.read()

            # Check order: Alpha < Beta < Gamma < Delta
            assert content.index("## Alpha") < content.index("## Beta")
            assert content.index("## Beta") < content.index("## Gamma")
            assert content.index("## Gamma") < content.index("## Delta")
            # Beta has updated content
            assert "Updated Beta" in content
            assert "Beta content" not in content

    def test_merge_no_existing_doc_falls_back_to_assembly(self):
        """When no existing doc, merge behaves like standard assembly."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "# Architecture\n"
            sections = [
                ("overview", "## Overview\n\nNew overview", ["S"], ["a.py"]),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                mode="update", merge=True,
            )
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            assert os.path.isfile(doc_path)
            with open(doc_path) as f:
                content = f.read()
            assert "# Architecture" in content
            assert "New overview" in content

    def test_merge_generates_manifest(self):
        """Merge mode still produces correct manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            existing_content = (
                "# Doc\n\n"
                "## Overview\n\nOld content\n"
            )
            self._write_existing_doc(
                tmp, "developers", "ARCHITECTURE", existing_content,
            )

            sections = [
                ("overview", "## Overview\n\nNew content",
                 ["Pipeline"], ["src/app.ts"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                mode="update", merge=True,
            )

            with open(manifest_file) as f:
                manifest = json.load(f)

            assert "ARCHITECTURE" in manifest["documents"]
            assert manifest["documents"]["ARCHITECTURE"]["overview"]["symbols"] == ["Pipeline"]


class TestSectionMarkerInjection:
    """Section-write mode injects <!-- section: slug --> markers."""

    def test_marker_injected(self):
        """Content without marker gets one prepended."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "system-overview",
                "## System Overview\n\nThe system is...\n",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            content = state["documents"]["ARCHITECTURE"]["sections"]["system-overview"]["content"]
            assert content.startswith("<!-- section: system-overview -->")
            assert "## System Overview" in content

    def test_marker_not_duplicated(self):
        """Content that already has the marker is not modified."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            content_with_marker = (
                "<!-- section: overview -->\n"
                "## Overview\n\nText.\n"
            )
            result = _run_section(
                tmp, state_file, "ARCHITECTURE", "overview",
                content_with_marker,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            content = state["documents"]["ARCHITECTURE"]["sections"]["overview"]["content"]
            assert content.count("<!-- section: overview -->") == 1


class TestFinalizeXmlOutput:
    """Finalize with --xml-dir produces XML source files."""

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
                            "typed_refs": _make_typed_refs(symbols, fps),
                        }
                        for slug, content, symbols, fps in sections
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def test_xml_file_created(self):
        """Finalize with --xml-dir produces XML file."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- DIATAXIS: explanation -->\n<!-- AUDIENCE: developers -->\n\n# Architecture\n"
            sections = [
                ("overview", "<!-- section: overview -->\n## Overview\n\nText", ["Sym"], ["a.py"]),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                xml_dir=xml_dir,
            )
            assert result.returncode == 0

            xml_path = os.path.join(xml_dir, "developers", "ARCHITECTURE.xml")
            assert os.path.isfile(xml_path)

            doc = parse_xml_doc(xml_path)
            assert doc["audience"] == "developers"
            assert doc["diataxis"] == "explanation"
            assert len(doc["sections"]) == 1
            assert doc["sections"][0]["slug"] == "overview"
            assert "Text" in doc["sections"][0]["body"]

    def test_xml_sections_have_markers(self):
        """XML section bodies include the <!-- section: --> marker."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- DIATAXIS: how-to -->\n# Ops\n"
            sections = [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nContent", [], []),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                xml_dir=xml_dir,
            )

            xml_path = os.path.join(xml_dir, "developers", "ARCHITECTURE.xml")
            doc = parse_xml_doc(xml_path)
            assert "<!-- section: monitoring -->" in doc["sections"][0]["body"]

    def test_finalize_xml_has_populated_refs(self):
        """Finalize populates XML <refs> from typed_refs."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- DIATAXIS: reference -->\n# Ref\n"
            typed_refs = [
                {"type": "code", "kind": "function", "name": "run_etl",
                 "module": "src/etl.py"},
                {"type": "db", "schema": "public", "table": "etl_runs",
                 "column": "status"},
                {"type": "env", "name": "ETL_WORKERS"},
            ]
            state_file = os.path.join(tmp, "state.json")
            state = {
                "documents": {
                    "ARCHITECTURE": {
                        "header": header,
                        "sections_order": ["overview"],
                        "sections": {
                            "overview": {
                                "content": "<!-- section: overview -->\n## Overview\n\nText",
                                "symbols": ["run_etl"],
                                "file_paths": ["src/etl.py"],
                                "typed_refs": typed_refs,
                            }
                        },
                    }
                }
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)

            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                xml_dir=xml_dir,
            )
            assert result.returncode == 0

            xml_path = os.path.join(xml_dir, "developers", "ARCHITECTURE.xml")
            doc = parse_xml_doc(xml_path)
            refs = doc["sections"][0]["refs"]
            assert len(refs) == 3
            ref_types = {r["type"] for r in refs}
            assert ref_types == {"code", "db", "env"}

    def test_xml_and_md_both_produced(self):
        """Both XML and .md files are produced."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- DIATAXIS: reference -->\n# Ref\n"
            sections = [
                ("items", "<!-- section: items -->\n## Items\n\nStuff", [], []),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            _run_finalize(
                state_file, docs_dir, "developers", manifest_file,
                xml_dir=xml_dir,
            )

            md_path = os.path.join(docs_dir, "developers", "ARCHITECTURE.md")
            xml_path = os.path.join(xml_dir, "developers", "ARCHITECTURE.xml")
            assert os.path.isfile(md_path)
            assert os.path.isfile(xml_path)

    def test_no_xml_dir_no_xml(self):
        """Without --xml-dir, no XML files are produced."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", [], []),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file)

            # No xml-sources dir should be created
            assert not os.path.exists(os.path.join(tmp, "xml-sources"))


class TestFinalizeEmptyAudience:
    """Finalize with empty audience writes to docs root, not a subdirectory."""

    def _build_state(self, tmp, sections, header="# Doc\n", doc_name="GLOSSARY"):
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
                            "typed_refs": _make_typed_refs(symbols, fps),
                        }
                        for slug, content, symbols, fps in sections
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def test_empty_audience_writes_to_docs_root(self):
        """Empty audience writes doc to docs_dir/DOCUMENT.md, not docs_dir//DOCUMENT.md."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- auto-generated -->\n# Glossary\n"
            sections = [
                ("system-concepts", "## System Concepts\n\nTerms", [], []),
                ("domain-terms", "## Domain Terms\n\nMore terms", [], []),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir, exist_ok=True)
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "", manifest_file)
            assert result.returncode == 0

            # File should be at docs_dir/GLOSSARY.md (no subdirectory)
            doc_path = os.path.join(docs_dir, "GLOSSARY.md")
            assert os.path.isfile(doc_path)
            with open(doc_path) as f:
                content = f.read()
            assert "# Glossary" in content
            assert "## System Concepts" in content
            assert "## Domain Terms" in content

            # Only the file should exist in docs_dir (no subdirectories)
            entries = os.listdir(docs_dir)
            assert entries == ["GLOSSARY.md"]

    def test_empty_audience_xml_writes_to_xml_root(self):
        """Empty audience writes XML to xml_dir/DOCUMENT.xml, not xml_dir//DOCUMENT.xml."""
        with tempfile.TemporaryDirectory() as tmp:
            header = "<!-- DIATAXIS: reference -->\n<!-- AUDIENCE: all -->\n\n# Glossary\n"
            sections = [
                ("system-concepts", "<!-- section: system-concepts -->\n## System Concepts\n\nTerms", [], []),
            ]
            state_file = self._build_state(tmp, sections, header)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(state_file, docs_dir, "", manifest_file,
                                   xml_dir=xml_dir)
            assert result.returncode == 0

            # XML should be at xml_dir/GLOSSARY.xml (no subdirectory)
            xml_path = os.path.join(xml_dir, "GLOSSARY.xml")
            assert os.path.isfile(xml_path)

            doc = parse_xml_doc(xml_path)
            assert doc["diataxis"] == "reference"
            assert len(doc["sections"]) == 1
            assert doc["sections"][0]["slug"] == "system-concepts"

    def test_empty_audience_manifest_correct(self):
        """Empty audience still produces correct manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("system-concepts", "## System Concepts\n\nTerms", ["Term1"], ["glossary.md"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir, exist_ok=True)
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "", manifest_file)
            assert result.returncode == 0

            with open(manifest_file) as f:
                manifest = json.load(f)
            assert "GLOSSARY" in manifest["documents"]
            assert manifest["documents"]["GLOSSARY"]["system-concepts"]["symbols"] == ["Term1"]

    def test_empty_audience_stderr_label(self):
        """Empty audience prints 'standalone' in summary."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("terms", "## Terms\n\nText", [], []),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir, exist_ok=True)
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(state_file, docs_dir, "", manifest_file)
            assert result.returncode == 0
            assert "standalone" in result.stderr
