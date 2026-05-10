"""Tests for fix-queue.py -- script-controlled fix queue for audit findings."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "fix-queue.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.json_io import load_json, save_json  # noqa: E402
from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_xml(xml_dir, audience, doc_name, sections_with_refs):
    """Build a master XML file, return its path."""
    sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
    tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections)
    for slug, _, refs in sections_with_refs:
        if refs:
            update_section_refs(tree, slug, refs)

    doc_dir = os.path.join(xml_dir, audience) if audience != "all" else xml_dir
    os.makedirs(doc_dir, exist_ok=True)
    xml_path = os.path.join(doc_dir, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


def _run(args, check=True):
    """Run fix-queue.py with given args, return CompletedProcess."""
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True,
    )
    if check:
        assert result.returncode == 0, (
            f"fix-queue.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _setup_scenario(td, n_groups=3, empty_groups=None):
    """Create a standard test scenario with N groups.

    Args:
        td: Temp directory.
        n_groups: Number of groups to create.
        empty_groups: Set of group indices that should have no matching XML sections.

    Returns:
        (grouping_file, findings_file, xml_dir, edit_dir, state_file, groups)
    """
    if empty_groups is None:
        empty_groups = set()

    xml_dir = os.path.join(td, "xml-sources")
    edit_dir = os.path.join(td, "edits")
    os.makedirs(edit_dir, exist_ok=True)

    findings = []
    groups = []

    for i in range(n_groups):
        group_id = f"group-{i}"
        doc_name = f"DOC{i}"

        if i not in empty_groups:
            # Build a real XML file with a section
            _build_xml(xml_dir, "devops", doc_name, [(
                f"section-{i}",
                f"<!-- section: section-{i} -->\n## Section {i}\n\nContent {i}.",
                [{"type": "code", "kind": "function", "name": f"func_{i}",
                  "module": f"src/mod{i}.py"}],
            )])
        else:
            # No XML file → extract will produce 0 sections
            os.makedirs(xml_dir, exist_ok=True)

        finding = {
            "document": doc_name,
            "section": f"section-{i}",
            "audience": "devops",
            "check": "reference-integrity",
            "description": f"func_{i} not mentioned in prose",
        }
        findings.append(finding)

        groups.append({
            "group_id": group_id,
            "root_cause_summary": f"Functions in group {i}",
            "finding_indices": [i],
        })

    grouping_file = os.path.join(td, "grouping.json")
    save_json(grouping_file, {"groups": groups})

    findings_file = os.path.join(td, "findings.json")
    save_json(findings_file, findings)

    state_file = os.path.join(td, "state.json")

    return grouping_file, findings_file, xml_dir, edit_dir, state_file, groups


# ---------------------------------------------------------------------------
# init tests
# ---------------------------------------------------------------------------

class TestInit:
    """Tests for the init subcommand."""

    def test_creates_state_file(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--approved", "0,1,2",
                  "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            assert state is not None
            assert state["queue"] == [0, 1, 2]
            assert state["current"] is None
            assert state["completed"] == []
            assert state["skipped"] == []
            assert state["files_modified"] == []

    def test_partial_approval(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--approved", "0,2",
                  "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            assert state["queue"] == [0, 2]

    def test_out_of_range_indices_filtered(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=2)

            result = _run(["init",
                           "--grouping-file", gf,
                           "--findings-file", ff,
                           "--xml-dir", xd,
                           "--edit-dir", ed,
                           "--approved", "0,1,5,99",
                           "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            assert state["queue"] == [0, 1]
            assert "skipping" in result.stderr.lower()

    def test_stdout_is_json(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)

            result = _run(["init",
                           "--grouping-file", gf,
                           "--findings-file", ff,
                           "--xml-dir", xd,
                           "--edit-dir", ed,
                           "--approved", "0,1,2",
                           "--state-file", sf])

            output = json.loads(result.stdout)
            assert output["status"] == "initialized"
            assert output["queue_size"] == 3

    def test_config_has_absolute_paths(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)
            sup = os.path.join(td, "suppressed.json")

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--suppress-file", sup,
                  "--approved", "0",
                  "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            for key, val in state["config"].items():
                assert os.path.isabs(val), f"{key} should be absolute: {val}"

    def test_suppress_file_stored_in_config(self):
        """--suppress-file flag stores absolute path in state config."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)
            sup = os.path.join(td, "auditv2", "suppressed-findings.json")

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--suppress-file", sup,
                  "--approved", "0",
                  "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            assert state["config"]["suppress_file"] == os.path.abspath(sup)

    def test_suppress_file_optional_defaults_empty(self):
        """Tests may omit --suppress-file; stored value is empty string."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td)

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--approved", "0",
                  "--state-file", sf])

            state = load_json(sf)
            assert state is not None
            assert state["config"]["suppress_file"] == ""

    def test_next_output_includes_suppress_file(self):
        """next JSON output propagates suppress_file from state config."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)
            sup = os.path.join(td, "auditv2", "suppressed-findings.json")

            _run(["init",
                  "--grouping-file", gf,
                  "--findings-file", ff,
                  "--xml-dir", xd,
                  "--edit-dir", ed,
                  "--suppress-file", sup,
                  "--approved", "0",
                  "--state-file", sf])

            result = _run(["next", "--state-file", sf])
            output = json.loads(result.stdout)
            assert output["status"] == "next"
            assert output["suppress_file"] == os.path.abspath(sup)


# ---------------------------------------------------------------------------
# next tests — basic flow
# ---------------------------------------------------------------------------

class TestNextBasic:
    """Tests for the next subcommand — extraction and status."""

    def test_first_next_extracts_group(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            result = _run(["next", "--state-file", sf])
            output = json.loads(result.stdout)

            assert output["status"] == "next"
            assert output["group_index"] == 0
            assert output["group_id"] == "group-0"
            assert output["section_count"] == 1
            assert os.path.isfile(output["edit_file"])

    def test_state_updated_after_extract(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=2)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            _run(["next", "--state-file", sf])
            state = load_json(sf)
            assert state is not None

            assert state["current"] == 0
            assert state["queue"] == [1]

    def test_done_after_single_group(self):
        """After extracting and calling next again, should merge and finish."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            # First next → extracts group 0
            _run(["next", "--state-file", sf])

            # Second next → merges group 0 (no edits), queue empty → done
            result = _run(["next", "--state-file", sf])
            output = json.loads(result.stdout)

            assert output["status"] == "done"
            assert output["completed"] == 1
            assert output["skipped"] == 0


# ---------------------------------------------------------------------------
# next tests — merge-before-extract sequentiality
# ---------------------------------------------------------------------------

class TestMergeBeforeExtract:
    """Verify that next merges the previous group before extracting."""

    def test_merge_happens_before_next_extract(self):
        """Two groups touching different files — verify first is merged before
        second is extracted (second extraction should see merged state)."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, groups = _setup_scenario(td, n_groups=2)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            # Extract group 0
            result1 = _run(["next", "--state-file", sf])
            out1 = json.loads(result1.stdout)
            assert out1["status"] == "next"
            assert out1["group_index"] == 0

            # State: current=0, queue=[1]
            state = load_json(sf)
            assert state is not None
            assert state["current"] == 0

            # Call next again → should merge group 0, then extract group 1
            result2 = _run(["next", "--state-file", sf])
            out2 = json.loads(result2.stdout)
            assert out2["status"] == "next"
            assert out2["group_index"] == 1

            # State: group 0 completed, current=1
            state = load_json(sf)
            assert state is not None
            assert 0 in state["completed"]
            assert state["current"] == 1

    def test_final_merge_on_done(self):
        """Last group's merge happens when next is called after final edit."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=2)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            _run(["next", "--state-file", sf])  # extract 0
            _run(["next", "--state-file", sf])  # merge 0, extract 1
            result = _run(["next", "--state-file", sf])  # merge 1, done

            output = json.loads(result.stdout)
            assert output["status"] == "done"
            assert output["completed"] == 2

            state = load_json(sf)
            assert state is not None
            assert 0 in state["completed"]
            assert 1 in state["completed"]
            assert state["current"] is None


# ---------------------------------------------------------------------------
# next tests — auto-skip empty groups
# ---------------------------------------------------------------------------

class TestAutoSkip:
    """Groups with 0 XML sections are automatically skipped."""

    def test_empty_group_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(
                td, n_groups=3, empty_groups={1},
            )

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1,2", "--state-file", sf])

            # First next → group 0
            result1 = _run(["next", "--state-file", sf])
            out1 = json.loads(result1.stdout)
            assert out1["group_index"] == 0

            # Second next → merge 0, skip 1 (empty), extract 2
            result2 = _run(["next", "--state-file", sf])
            out2 = json.loads(result2.stdout)
            assert out2["group_index"] == 2

            state = load_json(sf)
            assert state is not None
            assert 1 in state["skipped"]

    def test_all_empty_goes_to_done(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(
                td, n_groups=2, empty_groups={0, 1},
            )

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            result = _run(["next", "--state-file", sf])
            output = json.loads(result.stdout)
            assert output["status"] == "done"
            assert output["completed"] == 0
            assert output["skipped"] == 2

    def test_skip_in_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(
                td, n_groups=2, empty_groups={0},
            )

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            result = _run(["next", "--state-file", sf])
            assert "skipping" in result.stderr.lower()


# ---------------------------------------------------------------------------
# next tests — files_modified accumulation
# ---------------------------------------------------------------------------

class TestFilesModified:
    """files_modified accumulates across merges and is deduplicated."""

    def test_files_modified_in_done(self):
        """After processing all groups, done output lists all modified files."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=2)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            # Extract group 0
            r1 = _run(["next", "--state-file", sf])
            edit0 = json.loads(r1.stdout)["edit_file"]

            # Simulate an edit by modifying the body in the edit XML
            _modify_edit_body(edit0, "section-0", "Modified content 0.")

            # Merge 0, extract 1
            r2 = _run(["next", "--state-file", sf])
            edit1 = json.loads(r2.stdout)["edit_file"]

            _modify_edit_body(edit1, "section-1", "Modified content 1.")

            # Merge 1, done
            r3 = _run(["next", "--state-file", sf])
            output = json.loads(r3.stdout)

            assert output["status"] == "done"
            assert len(output["files_modified"]) == 2


def _modify_edit_body(edit_file, slug, new_text):
    """Modify body text in an edit XML file to simulate agent edits."""
    from lxml import etree
    tree = etree.parse(edit_file)
    for section in tree.getroot().findall("section"):
        if section.get("slug") == slug:
            body = section.find("body")
            assert body is not None
            body.text = etree.CDATA(
                f"<!-- section: {slug} -->\n## {slug}\n\n{new_text}"
            )
    tree.write(edit_file, xml_declaration=True, encoding="utf-8",
               pretty_print=True)


# ---------------------------------------------------------------------------
# Diff generation tests
# ---------------------------------------------------------------------------

class TestDiffs:
    """Per-group diffs are saved for audit trail."""

    def test_orig_file_saved_after_extract(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            r = _run(["next", "--state-file", sf])
            edit_file = json.loads(r.stdout)["edit_file"]
            orig_file = edit_file.replace(".xml", ".orig.xml")

            assert os.path.isfile(orig_file)

    def test_diff_file_created_on_merge(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            r = _run(["next", "--state-file", sf])
            edit_file = json.loads(r.stdout)["edit_file"]

            # Simulate agent edit
            _modify_edit_body(edit_file, "section-0", "Agent-modified content.")

            # Merge triggers diff
            _run(["next", "--state-file", sf])

            diff_file = os.path.join(ed, "group-0.diff")
            assert os.path.isfile(diff_file)

            with open(diff_file) as f:
                diff_content = f.read()
            assert "Agent-modified content" in diff_content
            assert "---" in diff_content  # unified diff header

    def test_no_edit_produces_empty_diff(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            _run(["next", "--state-file", sf])
            # No edit — just merge
            _run(["next", "--state-file", sf])

            diff_file = os.path.join(ed, "group-0.diff")
            assert os.path.isfile(diff_file)

            with open(diff_file) as f:
                diff_content = f.read()
            assert "No changes" in diff_content

    def test_diffs_in_done_output(self):
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=2)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1", "--state-file", sf])

            r1 = _run(["next", "--state-file", sf])
            _modify_edit_body(
                json.loads(r1.stdout)["edit_file"], "section-0", "Edit 0.",
            )

            r2 = _run(["next", "--state-file", sf])
            _modify_edit_body(
                json.loads(r2.stdout)["edit_file"], "section-1", "Edit 1.",
            )

            r3 = _run(["next", "--state-file", sf])
            output = json.loads(r3.stdout)

            assert output["status"] == "done"
            assert len(output["diffs"]) == 2
            assert all(os.path.isfile(d) for d in output["diffs"])

    def test_diff_shows_actual_changes(self):
        """Diff content reflects the specific text the agent changed."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0", "--state-file", sf])

            r = _run(["next", "--state-file", sf])
            edit_file = json.loads(r.stdout)["edit_file"]

            _modify_edit_body(edit_file, "section-0", "Now mentions `func_0`.")

            _run(["next", "--state-file", sf])

            diff_file = os.path.join(ed, "group-0.diff")
            with open(diff_file) as f:
                diff_content = f.read()

            # Should show the old content being replaced
            assert "-" in diff_content  # removed lines
            assert "+" in diff_content  # added lines
            assert "func_0" in diff_content


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    """End-to-end CLI invocation tests."""

    def test_full_cycle(self):
        """init → next → next → done for a single group."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(td, n_groups=1)

            # init
            r_init = _run(["init", "--grouping-file", gf, "--findings-file", ff,
                           "--xml-dir", xd, "--edit-dir", ed,
                           "--approved", "0", "--state-file", sf])
            init_out = json.loads(r_init.stdout)
            assert init_out["status"] == "initialized"

            # next → extract
            r_next1 = _run(["next", "--state-file", sf])
            next1_out = json.loads(r_next1.stdout)
            assert next1_out["status"] == "next"

            # next → merge + done
            r_next2 = _run(["next", "--state-file", sf])
            next2_out = json.loads(r_next2.stdout)
            assert next2_out["status"] == "done"

    def test_missing_state_file(self):
        result = _run(["next", "--state-file", "/nonexistent/state.json"])
        output = json.loads(result.stdout)
        assert output["status"] == "error"

    def test_three_groups_with_one_empty(self):
        """Full cycle: 3 groups, middle one empty, verify correct flow."""
        with tempfile.TemporaryDirectory() as td:
            gf, ff, xd, ed, sf, _ = _setup_scenario(
                td, n_groups=3, empty_groups={1},
            )

            _run(["init", "--grouping-file", gf, "--findings-file", ff,
                  "--xml-dir", xd, "--edit-dir", ed,
                  "--approved", "0,1,2", "--state-file", sf])

            # next → group 0
            r1 = _run(["next", "--state-file", sf])
            assert json.loads(r1.stdout)["group_index"] == 0

            # next → merge 0, skip 1, extract 2
            r2 = _run(["next", "--state-file", sf])
            assert json.loads(r2.stdout)["group_index"] == 2

            # next → merge 2, done
            r3 = _run(["next", "--state-file", sf])
            out3 = json.loads(r3.stdout)
            assert out3["status"] == "done"
            assert out3["completed"] == 2
            assert out3["skipped"] == 1
