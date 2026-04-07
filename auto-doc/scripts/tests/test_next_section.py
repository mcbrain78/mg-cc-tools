"""Tests for next-section.py -- script-gated section iterator."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "next-section.py")


def _setup_prose_dir(td, sections):
    """Create a prose-verify directory with manifest and per-section JSONs.

    Args:
        td: Temporary directory path.
        sections: List of (slug, refs_as_text) tuples.

    Returns:
        Path to the prose-verify directory.
    """
    prose_dir = os.path.join(td, "prose-verify")
    os.makedirs(prose_dir)

    manifest = {
        "xml_file": "/fake/doc.xml",
        "audience": "glossary",
        "document": "GLOSSARY",
        "sections": [s[0] for s in sections],
    }
    with open(os.path.join(prose_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    for slug, refs_text in sections:
        section_data = {
            "slug": slug,
            "document": "GLOSSARY",
            "audience": "glossary",
            "body": f"## {slug}\n\nSome prose about {slug}.",
            "refs_as_text": refs_text,
        }
        with open(os.path.join(prose_dir, f"{slug}.json"), "w") as f:
            json.dump(section_data, f)

    return prose_dir


def _run(state_file, prose_dir, sections_filter_file=None):
    """Run next-section.py and return parsed JSON output."""
    cmd = [
        sys.executable, SCRIPT,
        "--state-file", state_file,
        "--prose-verify-dir", prose_dir,
    ]
    if sections_filter_file:
        cmd.extend(["--sections-filter", sections_filter_file])
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class TestNextSection:
    """next-section.py feeds sections one at a time."""

    def test_filters_no_ref_sections(self):
        """Sections with '(no refs declared)' are skipped."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("domain-terms", "(no refs declared)"),
                ("system-concepts", "- [code:class] Engine in src/engine.py"),
                ("api-terms", "(no refs declared)"),
                ("technical-terms", "- [code:function] parse in src/parse.py"),
                ("infrastructure-terms", "- [env] PORT"),
            ])
            state_file = os.path.join(td, "state.json")

            out = _run(state_file, prose_dir)
            assert out["done"] is False
            assert out["section"] == "system-concepts"

    def test_returns_sections_in_order(self):
        """Sections with refs are returned in manifest order."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
                ("beta", "(no refs declared)"),
                ("gamma", "- [env] G"),
                ("delta", "- [env] D"),
            ])
            state_file = os.path.join(td, "state.json")

            out1 = _run(state_file, prose_dir)
            assert out1["section"] == "alpha"

            out2 = _run(state_file, prose_dir)
            assert out2["section"] == "gamma"

            out3 = _run(state_file, prose_dir)
            assert out3["section"] == "delta"

            out4 = _run(state_file, prose_dir)
            assert out4["done"] is True

    def test_done_reports_counts(self):
        """Done response includes processed and skipped counts."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("a", "(no refs declared)"),
                ("b", "- [env] B"),
                ("c", "(no refs declared)"),
            ])
            state_file = os.path.join(td, "state.json")

            _run(state_file, prose_dir)  # b
            out = _run(state_file, prose_dir)  # done

            assert out["done"] is True
            assert out["sections_processed"] == 1
            assert out["sections_skipped"] == 2

    def test_all_no_refs_immediate_done(self):
        """If all sections have no refs, first call returns done."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("x", "(no refs declared)"),
                ("y", "(no refs declared)"),
            ])
            state_file = os.path.join(td, "state.json")

            out = _run(state_file, prose_dir)
            assert out["done"] is True
            assert out["sections_processed"] == 0
            assert out["sections_skipped"] == 2

    def test_state_file_persists(self):
        """State file tracks position across calls."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("first", "- [env] F"),
                ("second", "- [env] S"),
            ])
            state_file = os.path.join(td, "state.json")

            _run(state_file, prose_dir)  # first

            with open(state_file) as f:
                state = json.load(f)
            assert state["index"] == 1
            assert state["sections"] == ["first", "second"]

    def test_file_path_is_absolute(self):
        """Returned file path points to actual section JSON."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("only", "- [code:class] Foo"),
            ])
            state_file = os.path.join(td, "state.json")

            out = _run(state_file, prose_dir)
            assert out["file"].endswith("/only.json")
            assert os.path.isfile(out["file"])

    def test_missing_manifest_exits_1(self):
        """Exits with error if manifest.json not found."""
        with tempfile.TemporaryDirectory() as td:
            empty_dir = os.path.join(td, "empty")
            os.makedirs(empty_dir)
            state_file = os.path.join(td, "state.json")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", state_file,
                 "--prose-verify-dir", empty_dir],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "manifest" in result.stderr.lower()

    def test_repeated_done_is_idempotent(self):
        """Calling after done keeps returning done."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("only", "- [env] O"),
            ])
            state_file = os.path.join(td, "state.json")

            _run(state_file, prose_dir)  # only
            done1 = _run(state_file, prose_dir)  # done
            done2 = _run(state_file, prose_dir)  # still done

            assert done1["done"] is True
            assert done2["done"] is True


class TestSectionsFilter:
    """--sections-filter restricts which sections are visited."""

    def _write_filter(self, td, sections):
        """Write a sections filter JSON file and return its path."""
        path = os.path.join(td, "filter.json")
        with open(path, "w") as f:
            json.dump(sections, f)
        return path

    def test_filter_restricts_iteration(self):
        """Only sections in the filter list are visited."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
                ("beta", "- [env] B"),
                ("gamma", "- [env] G"),
                ("delta", "- [env] D"),
            ])
            state_file = os.path.join(td, "state.json")
            filter_file = self._write_filter(td, ["beta", "delta"])

            out1 = _run(state_file, prose_dir, filter_file)
            assert out1["section"] == "beta"

            out2 = _run(state_file, prose_dir, filter_file)
            assert out2["section"] == "delta"

            out3 = _run(state_file, prose_dir, filter_file)
            assert out3["done"] is True
            assert out3["sections_processed"] == 2

    def test_filter_intersects_with_no_refs(self):
        """Filter cannot force visit of a no-ref section."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
                ("beta", "(no refs declared)"),
                ("gamma", "- [env] G"),
            ])
            state_file = os.path.join(td, "state.json")
            filter_file = self._write_filter(td, ["beta", "gamma"])

            out1 = _run(state_file, prose_dir, filter_file)
            assert out1["section"] == "gamma"

            out2 = _run(state_file, prose_dir, filter_file)
            assert out2["done"] is True

    def test_empty_filter_means_done(self):
        """Empty filter list → immediate done."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
                ("beta", "- [env] B"),
            ])
            state_file = os.path.join(td, "state.json")
            filter_file = self._write_filter(td, [])

            out = _run(state_file, prose_dir, filter_file)
            assert out["done"] is True
            assert out["sections_processed"] == 0

    def test_missing_filter_file_exits_1(self):
        """Non-existent filter file exits with error."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
            ])
            state_file = os.path.join(td, "state.json")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", state_file,
                 "--prose-verify-dir", prose_dir,
                 "--sections-filter", "/nonexistent/filter.json"],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "not found" in result.stderr

    def test_no_filter_is_backward_compatible(self):
        """Omitting --sections-filter visits all sections with refs."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir = _setup_prose_dir(td, [
                ("alpha", "- [env] A"),
                ("beta", "- [env] B"),
                ("gamma", "(no refs declared)"),
            ])
            state_file = os.path.join(td, "state.json")

            out1 = _run(state_file, prose_dir)
            assert out1["section"] == "alpha"

            out2 = _run(state_file, prose_dir)
            assert out2["section"] == "beta"

            out3 = _run(state_file, prose_dir)
            assert out3["done"] is True
            assert out3["sections_processed"] == 2
