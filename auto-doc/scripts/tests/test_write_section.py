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
from lib.xml_doc import parse_xml_doc, walk_sections

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "write-section.py",
)
ASSEMBLE_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "assemble-markdown.py",
)
SYNC_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "sync-edits-to-xml.py",
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
                 project_root=None, typed_refs=None, parent=None,
                 heading_state=None):
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
    if parent:
        cmd.extend(["--parent", parent])
    if heading_state:
        cmd.extend(["--heading-state", heading_state])
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
                {"type": "db", "db": "mydb", "schema": "public", "table": "users"},
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

    def test_finalize_preserves_state_file(self):
        """State file preserved after finalize (generate-setup cleans tmp/)."""
        with tempfile.TemporaryDirectory() as tmp:
            sections = [
                ("overview", "## Overview\n\nText", [], ["a.py"]),
            ]
            state_file = self._build_state(tmp, sections)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            _run_finalize(state_file, docs_dir, "developers", manifest_file)
            assert os.path.exists(state_file)

    def test_finalize_accumulates_manifest_across_calls(self):
        """Two finalize calls to same manifest file accumulate documents."""
        with tempfile.TemporaryDirectory() as tmp:
            # First state file: OPERATIONS document
            state1 = os.path.join(tmp, "state-ops.json")
            with open(state1, "w", encoding="utf-8") as f:
                json.dump({
                    "documents": {
                        "OPERATIONS": {
                            "header": "# Operations\n",
                            "sections_order": ["deployment"],
                            "sections": {
                                "deployment": {
                                    "content": "## Deployment\n\nDeploy text",
                                    "symbols": ["deploy"],
                                    "file_paths": ["ops.py"],
                                    "typed_refs": _make_typed_refs(
                                        ["deploy"], ["ops.py"]
                                    ),
                                }
                            },
                        }
                    }
                }, f)

            # Second state file: TROUBLESHOOTING document
            state2 = os.path.join(tmp, "state-triage.json")
            with open(state2, "w", encoding="utf-8") as f:
                json.dump({
                    "documents": {
                        "TROUBLESHOOTING": {
                            "header": "# Troubleshooting\n",
                            "sections_order": ["triage"],
                            "sections": {
                                "triage": {
                                    "content": "## Triage\n\nTriage text",
                                    "symbols": ["triage"],
                                    "file_paths": ["triage.py"],
                                    "typed_refs": _make_typed_refs(
                                        ["triage"], ["triage.py"]
                                    ),
                                }
                            },
                        }
                    }
                }, f)

            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest-devops.json")

            # Finalize first state -> creates manifest with OPERATIONS
            r1 = _run_finalize(state1, docs_dir, "devops", manifest_file)
            assert r1.returncode == 0

            # Finalize second state -> accumulates TROUBLESHOOTING
            r2 = _run_finalize(state2, docs_dir, "devops", manifest_file)
            assert r2.returncode == 0

            with open(manifest_file) as f:
                manifest = json.load(f)

            assert "OPERATIONS" in manifest["documents"]
            assert "TROUBLESHOOTING" in manifest["documents"]
            assert "deployment" in manifest["documents"]["OPERATIONS"]
            assert "triage" in manifest["documents"]["TROUBLESHOOTING"]

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

    def test_merge_xml_preserves_existing_sections(self):
        """Merge mode with --xml-dir updates changed sections and preserves others."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create existing .md doc (needed for md merge)
            existing_content = (
                "<!-- DIATAXIS: reference -->\n"
                "<!-- AUDIENCE: all -->\n\n"
                "# Glossary\n\n"
                "## System Concepts\n\nExisting system concepts\n\n"
                "## Domain Terms\n\nExisting domain terms\n\n"
                "## Technical Terms\n\nExisting technical terms\n"
            )
            self._write_existing_doc(tmp, "", "GLOSSARY", existing_content)

            # Create existing XML with 3 sections
            from lib.xml_doc import build_xml_doc, serialize_xml_doc, parse_xml_doc

            xml_dir = os.path.join(tmp, "xml-sources")
            os.makedirs(xml_dir, exist_ok=True)
            xml_path = os.path.join(xml_dir, "GLOSSARY.xml")
            tree = build_xml_doc(
                audience="",
                diataxis="reference",
                header="<!-- DIATAXIS: reference -->\n# Glossary\n",
                sections=[
                    {"slug": "system-concepts",
                     "body": "<!-- section: system-concepts -->\n## System Concepts\n\nExisting system concepts"},
                    {"slug": "domain-terms",
                     "body": "<!-- section: domain-terms -->\n## Domain Terms\n\nExisting domain terms"},
                    {"slug": "technical-terms",
                     "body": "<!-- section: technical-terms -->\n## Technical Terms\n\nExisting technical terms"},
                ],
            )
            serialize_xml_doc(tree, xml_path)

            # State has 1 updated section + 1 new section (only 2 of 4 total)
            sections = [
                ("domain-terms",
                 "<!-- section: domain-terms -->\n## Domain Terms\n\nUpdated domain terms",
                 [], []),
                ("infrastructure-terms",
                 "<!-- section: infrastructure-terms -->\n## Infrastructure Terms\n\nNew infra terms",
                 [], []),
            ]
            state_file = self._build_state(
                tmp, sections, doc_name="GLOSSARY",
            )
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "", manifest_file,
                mode="update", merge=True, xml_dir=xml_dir,
            )
            assert result.returncode == 0

            # Verify XML has all 4 sections (3 original + 1 new)
            doc = parse_xml_doc(xml_path)
            slugs = [s["slug"] for s in doc["sections"]]
            assert slugs == [
                "system-concepts", "domain-terms", "technical-terms",
                "infrastructure-terms",
            ]
            # Updated section has new content
            domain = next(s for s in doc["sections"] if s["slug"] == "domain-terms")
            assert "Updated domain terms" in domain["body"]
            # Preserved section has old content
            system = next(s for s in doc["sections"] if s["slug"] == "system-concepts")
            assert "Existing system concepts" in system["body"]
            # New section appended
            infra = next(s for s in doc["sections"] if s["slug"] == "infrastructure-terms")
            assert "New infra terms" in infra["body"]


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
                {"type": "db", "db": "mydb", "schema": "public",
                 "table": "etl_runs", "column": "status"},
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
            # 4 db (db + schema + table + column) + 1 code + 1 env = 6
            assert len(refs) == 6
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


class TestNestedSectionWrite:
    """Section-write mode with --parent for nested sections."""

    def test_parent_single_slug_places_child(self):
        """--parent as single slug places child under existing top-level section."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write top-level parent first
            result = _run_section(
                tmp, state_file, "OPS", "monitoring-alerting",
                "## Monitoring & Alerting\n\nIntro text\n",
            )
            assert result.returncode == 0

            # Write child under parent
            result = _run_section(
                tmp, state_file, "OPS", "etl-run-logging",
                "### ETL Run Logging\n\nLog details\n",
                parent="monitoring-alerting",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            parent_sec = state["documents"]["OPS"]["sections"]["monitoring-alerting"]
            assert "subsections" in parent_sec
            assert "subsections_order" in parent_sec
            assert "etl-run-logging" in parent_sec["subsections"]
            assert parent_sec["subsections_order"] == ["etl-run-logging"]
            child = parent_sec["subsections"]["etl-run-logging"]
            assert "Log details" in child["content"]

    def test_parent_slash_path_places_grandchild(self):
        """--parent as slash path (a/b) places child at resolved position."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write top-level
            _run_section(
                tmp, state_file, "OPS", "monitoring-alerting",
                "## Monitoring & Alerting\n\nIntro\n",
            )
            # Write child
            _run_section(
                tmp, state_file, "OPS", "health-artifact",
                "### Health Artifact\n\nArtifact overview\n",
                parent="monitoring-alerting",
            )
            # Write grandchild
            result = _run_section(
                tmp, state_file, "OPS", "artifact-format",
                "#### Artifact Format\n\nJSON schema\n",
                parent="monitoring-alerting/health-artifact",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            parent_sec = state["documents"]["OPS"]["sections"]["monitoring-alerting"]
            child_sec = parent_sec["subsections"]["health-artifact"]
            assert "artifact-format" in child_sec["subsections"]
            grandchild = child_sec["subsections"]["artifact-format"]
            assert "JSON schema" in grandchild["content"]

    def test_no_parent_creates_toplevel_with_subsections_keys(self):
        """Omitting --parent creates top-level section with subsections={}, subsections_order=[]."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            result = _run_section(
                tmp, state_file, "OPS", "deployment",
                "## Deployment\n\nDeploy info\n",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            section = state["documents"]["OPS"]["sections"]["deployment"]
            assert section["subsections"] == {}
            assert section["subsections_order"] == []

    def test_nonexistent_parent_exits_error(self):
        """Referencing a non-existent parent path exits with error."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write a top-level section first (so doc exists)
            _run_section(
                tmp, state_file, "OPS", "deployment",
                "## Deployment\n\nText\n",
            )

            # Try to write child under non-existent parent
            result = _run_section(
                tmp, state_file, "OPS", "child-section",
                "### Child\n\nText\n",
                parent="nonexistent",
            )
            assert result.returncode == 1
            assert "not found" in result.stderr

    def test_overwrite_child_preserves_subsections(self):
        """Overwriting existing child preserves its subsections and subsections_order."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write parent
            _run_section(
                tmp, state_file, "OPS", "monitoring-alerting",
                "## Monitoring\n\nIntro\n",
            )
            # Write child
            _run_section(
                tmp, state_file, "OPS", "etl-logging",
                "### ETL Logging\n\nOriginal\n",
                parent="monitoring-alerting",
            )
            # Write grandchild under the child
            _run_section(
                tmp, state_file, "OPS", "log-format",
                "#### Log Format\n\nJSON\n",
                parent="monitoring-alerting/etl-logging",
            )

            # Overwrite the child (etl-logging) with new content
            result = _run_section(
                tmp, state_file, "OPS", "etl-logging",
                "### ETL Logging\n\nUpdated content\n",
                parent="monitoring-alerting",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            child = state["documents"]["OPS"]["sections"]["monitoring-alerting"]["subsections"]["etl-logging"]
            # Content updated
            assert "Updated content" in child["content"]
            # Grandchild preserved
            assert "log-format" in child["subsections"]
            assert child["subsections_order"] == ["log-format"]


class TestNestedFinalize:
    """Finalize mode with nested state tree."""

    def _build_nested_state(self, tmp, doc_name="OPS",
                            header="<!-- DIATAXIS: how-to -->\n# Ops\n"):
        """Build a state with 2-level nesting for testing."""
        state_file = os.path.join(tmp, "state.json")
        state = {
            "documents": {
                doc_name: {
                    "header": header,
                    "sections_order": ["monitoring-alerting", "deployment"],
                    "sections": {
                        "monitoring-alerting": {
                            "content": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nIntro text",
                            "symbols": ["AlertManager"],
                            "file_paths": ["src/alerts.py"],
                            "typed_refs": [
                                {"type": "code", "kind": "class", "name": "AlertManager",
                                 "module": "src/alerts.py"},
                            ],
                            "subsections": {
                                "etl-run-logging": {
                                    "content": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\nLog details",
                                    "symbols": ["EtlLogger"],
                                    "file_paths": ["src/etl.py"],
                                    "typed_refs": [
                                        {"type": "code", "kind": "class", "name": "EtlLogger",
                                         "module": "src/etl.py"},
                                    ],
                                    "subsections": {},
                                    "subsections_order": [],
                                },
                            },
                            "subsections_order": ["etl-run-logging"],
                        },
                        "deployment": {
                            "content": "<!-- section: deployment -->\n## Deployment\n\nDeploy info",
                            "symbols": [],
                            "file_paths": [],
                            "typed_refs": [],
                            "subsections": {},
                            "subsections_order": [],
                        },
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def test_nested_finalize_xml_structure(self):
        """Finalize converts nested state to nested <section> XML elements."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                xml_dir=xml_dir,
            )
            assert result.returncode == 0

            xml_path = os.path.join(xml_dir, "devops", "OPS.xml")
            doc = parse_xml_doc(xml_path)

            # Top-level: 2 sections
            assert len(doc["sections"]) == 2
            assert doc["sections"][0]["slug"] == "monitoring-alerting"
            assert doc["sections"][1]["slug"] == "deployment"

            # Nested: monitoring-alerting has 1 child
            monitoring = doc["sections"][0]
            assert len(monitoring["children"]) == 1
            assert monitoring["children"][0]["slug"] == "etl-run-logging"
            assert "Log details" in monitoring["children"][0]["body"]

    def test_nested_finalize_refs_at_paths(self):
        """Finalize populates refs at correct paths for nested sections."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                xml_dir=xml_dir,
            )
            assert result.returncode == 0

            xml_path = os.path.join(xml_dir, "devops", "OPS.xml")
            doc = parse_xml_doc(xml_path)

            # Walk all sections and check refs
            path_refs = {}
            for path, section in walk_sections(doc["sections"]):
                path_refs[path] = section["refs"]

            # Top-level section has AlertManager ref
            assert len(path_refs["monitoring-alerting"]) == 1
            assert path_refs["monitoring-alerting"][0]["name"] == "AlertManager"

            # Child section has EtlLogger ref
            assert len(path_refs["monitoring-alerting/etl-run-logging"]) == 1
            assert path_refs["monitoring-alerting/etl-run-logging"][0]["name"] == "EtlLogger"

    def test_nested_finalize_markdown_assembly(self):
        """Finalize assembles nested sections in depth-first order for markdown."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
            )
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "devops", "OPS.md")
            with open(doc_path) as f:
                content = f.read()

            # All sections present in order: monitoring -> etl-logging -> deployment
            assert "## Monitoring & Alerting" in content
            assert "### ETL Run Logging" in content
            assert "## Deployment" in content

            # Depth-first: monitoring before etl-logging before deployment
            assert content.index("Monitoring & Alerting") < content.index("ETL Run Logging")
            assert content.index("ETL Run Logging") < content.index("Deployment")

    def test_nested_manifest_has_path_keys(self):
        """Manifest includes entries for nested sections with slash-separated path keys."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                manifest = json.load(f)

            ops = manifest["documents"]["OPS"]
            # Top-level section with refs
            assert "monitoring-alerting" in ops
            assert ops["monitoring-alerting"]["symbols"] == ["AlertManager"]
            # Nested section with refs -- key is slash-separated path
            assert "monitoring-alerting/etl-run-logging" in ops
            assert ops["monitoring-alerting/etl-run-logging"]["symbols"] == ["EtlLogger"]

    def test_nested_written_sections_all_paths(self):
        """_written_sections.sections_written includes all paths recursively."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                mode="initial",
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                manifest = json.load(f)

            ws = manifest["documents"]["OPS"]["_written_sections"]
            written = ws["sections_written"]
            assert "monitoring-alerting" in written
            assert "monitoring-alerting/etl-run-logging" in written
            assert "deployment" in written
            assert len(written) == 3

    def test_nested_total_sections_count(self):
        """Finalize summary counts all nested sections, not just top-level."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
            )
            assert result.returncode == 0
            # Should report 3 sections total (2 top-level + 1 child)
            assert "3 sections" in result.stderr


class TestNestedMergeMode:
    """Merge mode with nested sections (markdown and XML)."""

    def _build_nested_state(self, tmp, doc_name="ARCHITECTURE"):
        """Build a nested state with update sections for merge testing."""
        state_file = os.path.join(tmp, "state.json")
        state = {
            "documents": {
                doc_name: {
                    "header": "",
                    "sections_order": ["monitoring-alerting"],
                    "sections": {
                        "monitoring-alerting": {
                            "content": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nUpdated intro",
                            "symbols": [],
                            "file_paths": [],
                            "typed_refs": [],
                            "subsections": {
                                "etl-run-logging": {
                                    "content": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\nUpdated logging",
                                    "symbols": [],
                                    "file_paths": [],
                                    "typed_refs": [],
                                    "subsections": {},
                                    "subsections_order": [],
                                },
                                "new-child": {
                                    "content": "<!-- section: new-child -->\n### New Child\n\nBrand new section",
                                    "symbols": [],
                                    "file_paths": [],
                                    "typed_refs": [],
                                    "subsections": {},
                                    "subsections_order": [],
                                },
                            },
                            "subsections_order": ["etl-run-logging", "new-child"],
                        },
                    },
                }
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state_file

    def _write_existing_doc(self, tmp, audience, doc_name, content):
        """Write an existing document file and return its path."""
        doc_dir = os.path.join(tmp, "docs", audience) if audience else os.path.join(tmp, "docs")
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f"{doc_name}.md")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(content)
        return doc_path

    def test_merge_markdown_nested_sections(self):
        """Merge mode reads existing doc with ### headings, matches by path."""
        with tempfile.TemporaryDirectory() as tmp:
            existing_content = (
                "# Ops\n\n"
                "## Monitoring & Alerting\n\nOld monitoring intro\n\n"
                "### ETL Run Logging\n\nOld etl logging\n\n"
                "### Health Check\n\nExisting health check content\n\n"
                "## Deployment\n\nExisting deployment\n"
            )
            self._write_existing_doc(
                tmp, "devops", "ARCHITECTURE", existing_content,
            )

            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                mode="update", merge=True,
            )
            assert result.returncode == 0

            doc_path = os.path.join(docs_dir, "devops", "ARCHITECTURE.md")
            with open(doc_path) as f:
                content = f.read()

            # Replaced sections have new content
            assert "Updated intro" in content
            assert "Updated logging" in content
            # Unmatched sections preserved
            assert "Existing health check content" in content
            assert "Existing deployment" in content
            # New nested section appended
            assert "Brand new section" in content

    def test_merge_xml_nested_sections(self):
        """Merge XML mode uses get_section_paths, updates nested, adds new nested."""
        with tempfile.TemporaryDirectory() as tmp:
            from lib.xml_doc import build_xml_doc, serialize_xml_doc

            # Create existing XML with nested structure
            xml_dir = os.path.join(tmp, "xml-sources", "devops")
            os.makedirs(xml_dir, exist_ok=True)
            xml_path = os.path.join(xml_dir, "ARCHITECTURE.xml")
            tree = build_xml_doc(
                audience="devops",
                diataxis="how-to",
                header="# Ops\n",
                sections=[
                    {
                        "slug": "monitoring-alerting",
                        "body": "<!-- section: monitoring-alerting -->\n## Monitoring\n\nOld intro",
                        "children": [
                            {
                                "slug": "etl-run-logging",
                                "body": "<!-- section: etl-run-logging -->\n### ETL Logging\n\nOld logging",
                            },
                        ],
                    },
                    {
                        "slug": "deployment",
                        "body": "<!-- section: deployment -->\n## Deployment\n\nExisting deploy",
                    },
                ],
            )
            serialize_xml_doc(tree, xml_path)

            # Also create existing .md doc (finalize needs it for md merge)
            self._write_existing_doc(
                tmp, "devops", "ARCHITECTURE",
                "# Ops\n\n## Monitoring\n\nOld\n\n## Deployment\n\nExisting\n",
            )

            state_file = self._build_nested_state(tmp)
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                mode="update", merge=True,
                xml_dir=os.path.join(tmp, "xml-sources"),
            )
            assert result.returncode == 0

            # Verify XML
            doc = parse_xml_doc(xml_path)

            # monitoring-alerting still exists at top level
            monitoring = next(s for s in doc["sections"] if s["slug"] == "monitoring-alerting")
            assert "Updated intro" in monitoring["body"]

            # etl-run-logging is updated child (not duplicated at root)
            etl = next(c for c in monitoring["children"] if c["slug"] == "etl-run-logging")
            assert "Updated logging" in etl["body"]

            # new-child added as child of monitoring-alerting
            new_child = next(c for c in monitoring["children"] if c["slug"] == "new-child")
            assert "Brand new section" in new_child["body"]

            # deployment preserved
            deploy = next(s for s in doc["sections"] if s["slug"] == "deployment")
            assert "Existing deploy" in deploy["body"]


class TestParseExistingSectionsNested:
    """parse_existing_sections handles ##-##### headings with path-based output."""

    def test_parse_multi_level_headings(self):
        """parse_existing_sections splits on ##-#### headings with correct paths."""
        # We need to import the function directly
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        import importlib.machinery
        loader = importlib.machinery.SourceFileLoader(
            "write_section", SCRIPT_PATH,
        )
        mod = loader.load_module()

        content = (
            "# Doc Title\n\nSome header text\n\n"
            "## Monitoring & Alerting\n\nMonitoring intro\n\n"
            "### ETL Run Logging\n\nETL details\n\n"
            "#### Artifact Format\n\nJSON format\n\n"
            "### Health Check\n\nHealth details\n\n"
            "## Deployment\n\nDeploy info\n"
        )

        header, sections = mod.parse_existing_sections(content)

        assert "# Doc Title" in header
        assert len(sections) == 5

        # Verify paths are slash-separated
        paths = [s[0] for s in sections]
        assert paths == [
            "monitoring-alerting",
            "monitoring-alerting/etl-run-logging",
            "monitoring-alerting/etl-run-logging/artifact-format",
            "monitoring-alerting/health-check",
            "deployment",
        ]

        # Verify heading_line preserved
        assert sections[0][1] == "## Monitoring & Alerting"
        assert sections[1][1] == "### ETL Run Logging"
        assert sections[2][1] == "#### Artifact Format"


class TestPerHeadingEmission:
    """Integration tests for per-heading ref scoping and full pipeline round-trip."""

    # -- Shared refs for each nesting level --
    PARENT_REFS = [
        {"type": "code", "kind": "class", "name": "MonitorService",
         "module": "src/monitor.py"},
    ]
    CHILD_REFS = [
        {"type": "code", "kind": "function", "name": "check_etl_health",
         "module": "src/etl.py"},
    ]
    GRANDCHILD_REFS = [
        {"type": "config", "path": "config/alerts.yaml"},
    ]

    def _build_nested_state_via_cli(self, tmp, levels=2):
        """Build a nested state via CLI calls.

        levels=2: parent + child
        levels=3: parent + child + grandchild

        Returns (state_file, doc_name).
        """
        state_file = os.path.join(tmp, "state.json")
        doc_name = "OPS"

        # Write parent (## level) with its own refs
        result = _run_section(
            tmp, state_file, doc_name, "monitoring-alerting",
            "## Monitoring & Alerting\n<!-- docs-meta: ... -->\n\nParent intro text\n",
            header_text="<!-- DIATAXIS: how-to -->\n# Ops\n",
            typed_refs=self.PARENT_REFS,
        )
        assert result.returncode == 0, f"Parent section failed: {result.stderr}"

        # Write child (### level)
        result = _run_section(
            tmp, state_file, doc_name, "etl-logging",
            "### ETL Logging\n<!-- docs-meta: ... -->\n\nChild content about ETL\n",
            typed_refs=self.CHILD_REFS,
            parent="monitoring-alerting",
        )
        assert result.returncode == 0, f"Child section failed: {result.stderr}"

        if levels >= 3:
            # Write grandchild (#### level)
            result = _run_section(
                tmp, state_file, doc_name, "alert-config",
                "#### Alert Config\n<!-- docs-meta: ... -->\n\nGrandchild config details\n",
                typed_refs=self.GRANDCHILD_REFS,
                parent="monitoring-alerting/etl-logging",
            )
            assert result.returncode == 0, f"Grandchild section failed: {result.stderr}"

        return state_file, doc_name

    def _finalize_to_xml(self, tmp, state_file, doc_name="OPS"):
        """Finalize state to XML and return (xml_path, docs_dir, manifest_file)."""
        docs_dir = os.path.join(tmp, "docs")
        manifest_file = os.path.join(tmp, "manifest.json")
        xml_dir = os.path.join(tmp, "xml-sources")

        result = _run_finalize(
            state_file, docs_dir, "devops", manifest_file,
            xml_dir=xml_dir,
        )
        assert result.returncode == 0, f"Finalize failed: {result.stderr}"

        xml_path = os.path.join(xml_dir, "devops", f"{doc_name}.xml")
        assert os.path.isfile(xml_path), f"XML not created at {xml_path}"
        return xml_path, docs_dir, manifest_file

    def test_ref_scoping_parent_vs_child(self):
        """Parent intro refs symbol A, child refs symbol B -- no cross-contamination."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file, doc_name = self._build_nested_state_via_cli(tmp, levels=2)
            xml_path, _, _ = self._finalize_to_xml(tmp, state_file, doc_name)

            doc = parse_xml_doc(xml_path)
            path_refs = {}
            for path, section in walk_sections(doc["sections"]):
                path_refs[path] = section["refs"]

            # Parent has only MonitorService
            parent_refs = path_refs["monitoring-alerting"]
            parent_names = [r.get("name", r.get("path", "")) for r in parent_refs]
            assert "MonitorService" in parent_names
            assert "check_etl_health" not in parent_names

            # Child has only check_etl_health
            child_refs = path_refs["monitoring-alerting/etl-logging"]
            child_names = [r.get("name", r.get("path", "")) for r in child_refs]
            assert "check_etl_health" in child_names
            assert "MonitorService" not in child_names

    def test_ref_scoping_grandchild(self):
        """3-level nesting: each level has exactly its own refs, no leaking."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file, doc_name = self._build_nested_state_via_cli(tmp, levels=3)
            xml_path, _, _ = self._finalize_to_xml(tmp, state_file, doc_name)

            doc = parse_xml_doc(xml_path)
            path_refs = {}
            for path, section in walk_sections(doc["sections"]):
                path_refs[path] = section["refs"]

            # Parent: only MonitorService
            parent_refs = path_refs["monitoring-alerting"]
            assert len(parent_refs) == 1
            assert parent_refs[0]["name"] == "MonitorService"

            # Child: only check_etl_health
            child_refs = path_refs["monitoring-alerting/etl-logging"]
            assert len(child_refs) == 1
            assert child_refs[0]["name"] == "check_etl_health"

            # Grandchild: only config/alerts.yaml
            gc_refs = path_refs["monitoring-alerting/etl-logging/alert-config"]
            assert len(gc_refs) == 1
            assert gc_refs[0]["path"] == "config/alerts.yaml"

    def test_round_trip_build_finalize_assemble(self):
        """Build nested state -> finalize -> assemble: all headings in depth-first order."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            doc_name = "OPS"

            # Build: parent with 2 children, one child with a grandchild
            _run_section(
                tmp, state_file, doc_name, "monitoring-alerting",
                "## Monitoring & Alerting\n<!-- docs-meta: ... -->\n\nIntro\n",
                header_text="<!-- DIATAXIS: how-to -->\n# Ops\n",
                typed_refs=self.PARENT_REFS,
            )
            _run_section(
                tmp, state_file, doc_name, "etl-logging",
                "### ETL Logging\n<!-- docs-meta: ... -->\n\nETL details\n",
                typed_refs=self.CHILD_REFS,
                parent="monitoring-alerting",
            )
            _run_section(
                tmp, state_file, doc_name, "alert-config",
                "#### Alert Config\n<!-- docs-meta: ... -->\n\nAlert config\n",
                typed_refs=self.GRANDCHILD_REFS,
                parent="monitoring-alerting/etl-logging",
            )
            _run_section(
                tmp, state_file, doc_name, "health-checks",
                "### Health Checks\n<!-- docs-meta: ... -->\n\nHealth check info\n",
                typed_refs=[],
                parent="monitoring-alerting",
            )

            # Finalize to XML
            xml_path, _, _ = self._finalize_to_xml(tmp, state_file, doc_name)

            # Assemble to markdown
            md_out = os.path.join(tmp, "assembled.md")
            result = subprocess.run(
                [sys.executable, ASSEMBLE_SCRIPT,
                 "--xml-file", xml_path,
                 "--output", md_out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"Assemble failed: {result.stderr}"

            with open(md_out) as f:
                content = f.read()

            # All headings present
            assert "## Monitoring & Alerting" in content
            assert "### ETL Logging" in content
            assert "#### Alert Config" in content
            assert "### Health Checks" in content

            # Depth-first order: ## monitoring > ### etl > #### alert > ### health
            idx_monitoring = content.index("## Monitoring & Alerting")
            idx_etl = content.index("### ETL Logging")
            idx_alert = content.index("#### Alert Config")
            idx_health = content.index("### Health Checks")
            assert idx_monitoring < idx_etl < idx_alert < idx_health

            # Section markers present
            assert "<!-- section: monitoring-alerting -->" in content
            assert "<!-- section: etl-logging -->" in content
            assert "<!-- section: alert-config -->" in content
            assert "<!-- section: health-checks -->" in content

    def test_round_trip_sync_edits(self):
        """Build -> finalize -> assemble -> sync-edits: section paths survive round-trip."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            doc_name = "OPS"

            # Build nested state
            _run_section(
                tmp, state_file, doc_name, "monitoring-alerting",
                "## Monitoring & Alerting\n<!-- docs-meta: ... -->\n\nIntro\n",
                header_text="<!-- DIATAXIS: how-to -->\n# Ops\n",
                typed_refs=self.PARENT_REFS,
            )
            _run_section(
                tmp, state_file, doc_name, "etl-logging",
                "### ETL Logging\n<!-- docs-meta: ... -->\n\nETL details\n",
                typed_refs=self.CHILD_REFS,
                parent="monitoring-alerting",
            )
            _run_section(
                tmp, state_file, doc_name, "alert-config",
                "#### Alert Config\n<!-- docs-meta: ... -->\n\nAlert config\n",
                typed_refs=self.GRANDCHILD_REFS,
                parent="monitoring-alerting/etl-logging",
            )

            # Finalize to XML
            xml_path, _, _ = self._finalize_to_xml(tmp, state_file, doc_name)

            # Collect original paths from XML
            doc_before = parse_xml_doc(xml_path)
            original_paths = [p for p, _ in walk_sections(doc_before["sections"])]

            # Assemble to markdown
            md_out = os.path.join(tmp, "assembled.md")
            subprocess.run(
                [sys.executable, ASSEMBLE_SCRIPT,
                 "--xml-file", xml_path,
                 "--output", md_out],
                capture_output=True, text=True,
            )

            # Sync edits back to XML (no actual edits, just round-trip)
            result = subprocess.run(
                [sys.executable, SYNC_SCRIPT,
                 "--md-file", md_out,
                 "--xml-file", xml_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"Sync failed: {result.stderr}"

            # Parse synced XML and verify paths match exactly
            doc_after = parse_xml_doc(xml_path)
            synced_paths = [p for p, _ in walk_sections(doc_after["sections"])]
            assert synced_paths == original_paths, (
                f"Paths changed after sync: {synced_paths} != {original_paths}"
            )

    def test_empty_intro_with_children(self):
        """Parent ## has minimal content but ### children have real content."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            doc_name = "OPS"

            # Parent with minimal intro (heading + docs-meta only)
            _run_section(
                tmp, state_file, doc_name, "monitoring-alerting",
                "## Monitoring & Alerting\n<!-- docs-meta: ... -->\n",
                header_text="<!-- DIATAXIS: how-to -->\n# Ops\n",
                typed_refs=[],
            )

            # Child with substantial content
            _run_section(
                tmp, state_file, doc_name, "etl-logging",
                "### ETL Logging\n<!-- docs-meta: ... -->\n\nDetailed ETL logging content here.\n\nThis section covers log formats, rotation, and retention policies.\n",
                typed_refs=self.CHILD_REFS,
                parent="monitoring-alerting",
            )

            # Another child with substantial content
            _run_section(
                tmp, state_file, doc_name, "health-checks",
                "### Health Checks\n<!-- docs-meta: ... -->\n\nComprehensive health check documentation.\n\nCovers endpoint monitoring, database checks, and alerting thresholds.\n",
                typed_refs=[],
                parent="monitoring-alerting",
            )

            # Finalize
            docs_dir = os.path.join(tmp, "docs")
            manifest_file = os.path.join(tmp, "manifest.json")
            xml_dir = os.path.join(tmp, "xml-sources")

            result = _run_finalize(
                state_file, docs_dir, "devops", manifest_file,
                xml_dir=xml_dir,
            )
            assert result.returncode == 0, f"Finalize failed: {result.stderr}"

            xml_path = os.path.join(xml_dir, "devops", f"{doc_name}.xml")
            doc = parse_xml_doc(xml_path)

            # Parent section exists
            monitoring = doc["sections"][0]
            assert monitoring["slug"] == "monitoring-alerting"

            # Parent has children
            assert len(monitoring["children"]) == 2
            child_slugs = [c["slug"] for c in monitoring["children"]]
            assert "etl-logging" in child_slugs
            assert "health-checks" in child_slugs

            # Children have real content
            etl = next(c for c in monitoring["children"] if c["slug"] == "etl-logging")
            assert "log formats, rotation" in etl["body"]

            health = next(c for c in monitoring["children"] if c["slug"] == "health-checks")
            assert "endpoint monitoring" in health["body"]

            # Assemble to markdown and verify structure
            md_out = os.path.join(tmp, "assembled.md")
            result = subprocess.run(
                [sys.executable, ASSEMBLE_SCRIPT,
                 "--xml-file", xml_path,
                 "--output", md_out],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(md_out) as f:
                content = f.read()

            # Parent heading exists
            assert "## Monitoring & Alerting" in content
            # Children headings exist with real content
            assert "### ETL Logging" in content
            assert "### Health Checks" in content
            assert "log formats, rotation" in content
            assert "endpoint monitoring" in content


class TestHeadingInjection:
    """Deterministic heading injection via --heading-state."""

    def _make_heading_state(self, tmp, entries):
        """Write a heading state file with given write entries."""
        state = {
            "queue": entries + [{"done": True, "headings_processed": len(entries)}],
            "index": 0,
        }
        path = os.path.join(tmp, "heading-state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return path

    def test_heading_injected(self):
        """Content without heading gets heading prepended after section marker."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            heading_state = self._make_heading_state(tmp, [
                {"type": "write", "heading_path": "overview",
                 "level": 2, "title": "Overview",
                 "heading_line": "## Overview", "purpose": "", "example": ""},
            ])

            result = _run_section(
                tmp, state_file, "DOC", "overview",
                "Some body text without a heading.\n",
                heading_state=heading_state,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            content = state["documents"]["DOC"]["sections"]["overview"]["content"]
            assert "<!-- section: overview -->" in content
            assert "## Overview" in content
            # Heading comes after marker
            lines = content.split("\n")
            assert lines[0] == "<!-- section: overview -->"
            assert lines[1] == "## Overview"

    def test_duplicate_heading_stripped(self):
        """Agent-written heading is stripped when --heading-state provides it."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            heading_state = self._make_heading_state(tmp, [
                {"type": "write", "heading_path": "quick-diagnosis",
                 "level": 2, "title": "Quick Diagnosis",
                 "heading_line": "## Quick Diagnosis", "purpose": "", "example": ""},
            ])

            result = _run_section(
                tmp, state_file, "DOC", "quick-diagnosis",
                "## Quick Diagnosis\nBody text here.\n",
                heading_state=heading_state,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            content = state["documents"]["DOC"]["sections"]["quick-diagnosis"]["content"]
            # Should have exactly one heading
            assert content.count("## Quick Diagnosis") == 1
            assert "Body text here." in content

    def test_child_heading_injected(self):
        """Nested heading injection uses parent/child path."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            # Write parent first
            _run_section(
                tmp, state_file, "DOC", "infrastructure",
                "## Infrastructure\n\nIntro text.\n",
            )

            heading_state = self._make_heading_state(tmp, [
                {"type": "write", "heading_path": "infrastructure/topology",
                 "level": 3, "title": "Deployment Topology",
                 "heading_line": "### Deployment Topology", "purpose": "", "example": ""},
            ])

            result = _run_section(
                tmp, state_file, "DOC", "topology",
                "Network diagram and details.\n",
                parent="infrastructure",
                heading_state=heading_state,
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            child = state["documents"]["DOC"]["sections"]["infrastructure"]["subsections"]["topology"]
            assert "### Deployment Topology" in child["content"]
            assert "Network diagram" in child["content"]

    def test_no_heading_state_backward_compat(self):
        """Without --heading-state, content is unchanged (backward compat)."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")

            result = _run_section(
                tmp, state_file, "DOC", "overview",
                "## Overview\n\nBody text.\n",
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            content = state["documents"]["DOC"]["sections"]["overview"]["content"]
            assert "## Overview" in content
            assert "Body text." in content


class TestMalformedRefDischarge:
    """write-section.py discharges malformed refs via ref_validation."""

    def test_empty_dep_stored_as_malformed(self):
        """A dep ref with empty name is stored with type='malformed'."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "DOC", "glossary",
                "## Glossary\n\nTerms.\n",
                typed_refs=[
                    {"type": "dep", "name": ""},
                    {"type": "dep", "name": "tenacity"},
                ],
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            refs = state["documents"]["DOC"]["sections"]["glossary"]["typed_refs"]
            assert len(refs) == 2
            assert refs[0]["type"] == "malformed"
            assert refs[0]["original_type"] == "dep"
            assert refs[1]["type"] == "dep"
            assert refs[1]["name"] == "tenacity"

    def test_valid_refs_unchanged(self):
        """Valid refs pass through discharge unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "DOC", "section",
                "## Section\n\nContent.\n",
                typed_refs=[
                    {"type": "dep", "name": "tenacity"},
                    {"type": "db", "db": "mydb", "schema": "rr", "table": "runs"},
                ],
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            refs = state["documents"]["DOC"]["sections"]["section"]["typed_refs"]
            assert all(r["type"] != "malformed" for r in refs)

    def test_malformed_ref_not_in_symbols(self):
        """Malformed refs are not counted as symbols or file_paths."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            result = _run_section(
                tmp, state_file, "DOC", "section",
                "## Section\n\nContent.\n",
                typed_refs=[
                    {"type": "code", "kind": "", "name": ""},
                    {"type": "code", "kind": "function", "name": "real_func",
                     "module": "src/mod.py"},
                ],
            )
            assert result.returncode == 0

            with open(state_file) as f:
                state = json.load(f)

            section = state["documents"]["DOC"]["sections"]["section"]
            assert section["symbols"] == ["real_func"]
            assert section["file_paths"] == ["src/mod.py"]
