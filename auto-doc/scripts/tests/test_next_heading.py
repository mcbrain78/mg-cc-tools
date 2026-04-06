"""Tests for next-heading.py -- script-gated heading iterator.

Covers all 7 HIT requirements via subprocess CLI invocation,
matching the test pattern used in test_next_section.py.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "next-heading.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_TEMPLATE = """\
<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: devops -->

# Operations Guide

<!-- docs-meta: last-updated: 2026-01-01 -->

## Infrastructure Overview
<purpose>Mental model of deployment topology.</purpose>
<example>
### Deployment Topology

| Component | Host |
|-----------|------|
| API | app-01 |
</example>

## Deployment
<purpose>Step-by-step deploy procedure.</purpose>
<example>
### Deploy

```bash
ssh app-01
```

### Rollback

```bash
git checkout PREV
```
</example>
"""

NESTED_TEMPLATE = """\
<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: devops -->

# Operations Guide

<!-- docs-meta: last-updated: 2026-01-01 -->

## Infrastructure Overview
<purpose>System topology overview.</purpose>
<example>
### Topology Table

| Component | Host |
|-----------|------|
| API | app-01 |
</example>

### Deployment Topology
<purpose>Where each component runs.</purpose>
<example>
| Component | Host | Port |
|-----------|------|------|
| API | app-01 | 8080 |
</example>

### External Dependencies
<purpose>Third-party services and fallbacks.</purpose>
<example>
| Service | Purpose |
|---------|---------|
| OpenAI | LLM scoring |
</example>

## Deployment
<purpose>Step-by-step deploy.</purpose>
<example>
### Deploy Steps

1. Pull code
2. Build
</example>
"""

DEEP_TEMPLATE = """\
<!-- DIATAXIS: reference -->
<!-- AUDIENCE: devops -->

# Deep Guide

## Config Reference
<purpose>All config knobs.</purpose>
<example>
### Env Vars Table

| Var | Default |
|-----|---------|
| PORT | 8080 |
</example>

### Environment Variables
<purpose>Env var reference.</purpose>
<example>
| Var | Default |
|-----|---------|
| PORT | 8080 |
</example>

#### Required Variables
<purpose>Must-set vars.</purpose>
<example>
| Var | Description |
|-----|-------------|
| DATABASE_URL | Connection string |
</example>

#### Optional Variables
<purpose>Nice-to-have vars.</purpose>
<example>
| Var | Default |
|-----|---------|
| LOG_LEVEL | INFO |
</example>

### Configuration Files
<purpose>Config file reference.</purpose>
<example>
| File | Purpose |
|------|---------|
| .env | Env vars |
</example>

## Monitoring
<purpose>Key metrics to watch.</purpose>
<example>
### Metrics

| Metric | Threshold |
|--------|-----------|
| p95 latency | 2s |
</example>
"""

EMPTY_TEMPLATE = """\
<!-- DIATAXIS: reference -->
<!-- AUDIENCE: glossary -->

# Glossary

<!-- docs-meta: last-updated: 2026-01-01 -->
"""

SCAN_DATA = {
    "source_material_index": {
        "OPERATIONS/infrastructure-overview": {
            "source_files": ["src/config.py", "src/infra/deploy.py"]
        },
        "OPERATIONS/deployment": {
            "source_files": ["scripts/deploy.sh"]
        },
    }
}


def _write_fixtures(td, template_text=SIMPLE_TEMPLATE, scan=None, document="OPERATIONS"):
    """Write template and scan file to temp dir, return paths dict."""
    template_path = os.path.join(td, "template.md")
    with open(template_path, "w") as f:
        f.write(template_text)

    scan_path = os.path.join(td, "scan.json")
    scan_data = scan if scan is not None else SCAN_DATA
    with open(scan_path, "w") as f:
        json.dump(scan_data, f)

    state_path = os.path.join(td, "state.json")

    return {
        "template": template_path,
        "scan": scan_path,
        "state": state_path,
        "document": document,
    }


def _run(paths) -> dict:
    """Run next-heading.py and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--state-file", paths["state"],
         "--template", paths["template"],
         "--scan-file", paths["scan"],
         "--document", paths["document"]],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return json.loads(result.stdout)


def _drain_all(paths):
    """Run next-heading.py until done, returning all responses."""
    responses = []
    for _ in range(100):  # safety limit
        out = _run(paths)
        responses.append(out)
        if out.get("done"):
            break
    return responses


# ---------------------------------------------------------------------------
# HIT-01: CLI interface -- four required arguments
# ---------------------------------------------------------------------------

class TestCLI:
    """HIT-01: Script accepts four required arguments."""

    def test_missing_state_file_exits_2(self):
        """Missing --state-file causes argparse error."""
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--template", "/fake",
                 "--scan-file", "/fake",
                 "--document", "DOC"],
                capture_output=True, text=True,
            )
            assert result.returncode == 2

    def test_missing_template_exits_2(self):
        """Missing --template causes argparse error."""
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", "/fake",
                 "--scan-file", "/fake",
                 "--document", "DOC"],
                capture_output=True, text=True,
            )
            assert result.returncode == 2

    def test_missing_scan_file_exits_2(self):
        """Missing --scan-file causes argparse error."""
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", "/fake",
                 "--template", "/fake",
                 "--document", "DOC"],
                capture_output=True, text=True,
            )
            assert result.returncode == 2

    def test_missing_document_exits_2(self):
        """Missing --document causes argparse error."""
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", "/fake",
                 "--template", "/fake",
                 "--scan-file", "/fake"],
                capture_output=True, text=True,
            )
            assert result.returncode == 2

    def test_all_args_present_succeeds(self):
        """All four args present runs successfully."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            out = _run(paths)
            assert "type" in out or "done" in out


# ---------------------------------------------------------------------------
# HIT-02: Template parsing and state persistence
# ---------------------------------------------------------------------------

class TestTemplateParsing:
    """HIT-02: Template parsing and state persistence."""

    def test_first_call_creates_state_file(self):
        """First call parses template and creates state file."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)
            assert os.path.isfile(paths["state"])

    def test_state_has_queue_and_index(self):
        """State file contains queue list and index integer."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)
            with open(paths["state"]) as f:
                state = json.load(f)
            assert "queue" in state
            assert "index" in state
            assert isinstance(state["queue"], list)
            assert isinstance(state["index"], int)

    def test_subsequent_call_uses_state_not_template(self):
        """Second call reads from state, does not re-parse template."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # first call creates state

            # Delete template -- second call should still work from state
            os.remove(paths["template"])
            out = _run(paths)
            assert "type" in out or "done" in out

    def test_multiline_purpose_extracted(self):
        """Multi-line PURPOSE comments are correctly extracted."""
        template = """\
<!-- DIATAXIS: reference -->
# Title

## Test Section
<purpose>This is a multi-line purpose.
     It spans two lines with indentation.</purpose>
<example>
Some example content.
</example>
"""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=template,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            assert len(writes) >= 1
            assert "multi-line purpose" in writes[0]["purpose"].lower()

    def test_headings_in_example_not_treated_as_real(self):
        """Headings inside EXAMPLE blocks are NOT real template headings."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=SIMPLE_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            # SIMPLE_TEMPLATE has 2 ## sections, no real ### headings
            # The ### headings inside <!-- EXAMPLE: --> blocks should NOT be counted
            heading_paths = [w["heading_path"] for w in writes]
            assert len(writes) == 2, f"Expected 2 writes, got {len(writes)}: {heading_paths}"

    def test_template_not_found_exits_1(self):
        """Non-existent template file exits with code 1."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", paths["state"],
                 "--template", os.path.join(td, "nonexistent.md"),
                 "--scan-file", paths["scan"],
                 "--document", paths["document"]],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "template" in result.stderr.lower() or "not found" in result.stderr.lower()

    def test_scan_file_not_found_exits_1(self):
        """Non-existent scan file exits with code 1."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", paths["state"],
                 "--template", paths["template"],
                 "--scan-file", os.path.join(td, "nonexistent.json"),
                 "--document", paths["document"]],
                capture_output=True, text=True,
            )
            assert result.returncode == 1
            assert "scan" in result.stderr.lower() or "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# HIT-03: Orient response
# ---------------------------------------------------------------------------

class TestOrientResponse:
    """HIT-03: Orient response at ## section boundaries."""

    def test_orient_has_required_fields(self):
        """Orient response has type, section, heading_outline, source_files."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            out = _run(paths)
            assert out["type"] == "orient"
            assert "section" in out
            assert "heading_outline" in out
            assert "source_files" in out

    def test_orient_section_is_slug(self):
        """Orient section field is the slugified ## heading."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            out = _run(paths)
            assert out["section"] == "infrastructure-overview"

    def test_orient_source_files_from_scan(self):
        """Orient source_files comes from scan's source_material_index."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            out = _run(paths)
            assert out["source_files"] == ["src/config.py", "src/infra/deploy.py"]

    def test_orient_missing_scan_key_gives_empty_list(self):
        """Missing source_material_index key gives empty source_files."""
        scan = {"source_material_index": {}}
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, scan=scan)
            out = _run(paths)
            assert out["source_files"] == []

    def test_orient_heading_outline_depth_first(self):
        """heading_outline lists all heading_paths for the section."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE)
            out = _run(paths)
            assert out["type"] == "orient"
            assert out["section"] == "infrastructure-overview"
            outline = out["heading_outline"]
            assert "infrastructure-overview" in outline
            assert "infrastructure-overview/deployment-topology" in outline
            assert "infrastructure-overview/external-dependencies" in outline


# ---------------------------------------------------------------------------
# HIT-04: Write response
# ---------------------------------------------------------------------------

class TestWriteResponse:
    """HIT-04: Write response for every heading."""

    def test_write_has_required_fields(self):
        """Write response has type, heading_path, level, title, heading_line, purpose, example."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # first write
            assert out["type"] == "write"
            assert "heading_path" in out
            assert "level" in out
            assert "title" in out
            assert "heading_line" in out
            assert "purpose" in out
            assert "example" in out

    def test_write_title_matches_template_heading(self):
        """Write response title is the original heading text from template."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write
            assert out["title"] == "Infrastructure Overview"

    def test_write_heading_line_format(self):
        """heading_line is '#' * level + ' ' + title."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write
            assert out["heading_line"] == "## Infrastructure Overview"

    def test_child_write_heading_line_level_3(self):
        """### child has heading_line with 3 hashes."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            child_writes = [r for r in responses
                           if r.get("type") == "write" and r.get("level") == 3]
            assert len(child_writes) > 0
            for cw in child_writes:
                assert cw["heading_line"].startswith("### ")
                assert cw["heading_line"] == "### " + cw["title"]

    def test_grandchild_write_heading_line_level_4(self):
        """#### grandchild has heading_line with 4 hashes."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=DEEP_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="DEEP")
            responses = _drain_all(paths)
            grandchild_writes = [r for r in responses
                                if r.get("type") == "write" and r.get("level") == 4]
            assert len(grandchild_writes) > 0
            for gw in grandchild_writes:
                assert gw["heading_line"].startswith("#### ")
                assert gw["heading_line"] == "#### " + gw["title"]

    def test_section_level_write_omits_parent_path(self):
        """## level write has NO parent_path key (not null, absent)."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # ## write
            assert out["level"] == 2
            assert "parent_path" not in out

    def test_child_write_has_parent_path(self):
        """### level write has parent_path."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE)
            responses = _drain_all(paths)
            child_writes = [r for r in responses
                           if r.get("type") == "write" and r.get("level") == 3]
            assert len(child_writes) > 0
            for cw in child_writes:
                assert "parent_path" in cw

    def test_write_purpose_content(self):
        """Write response purpose contains extracted PURPOSE text."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write
            assert "mental model" in out["purpose"].lower() or "topology" in out["purpose"].lower()

    def test_write_example_content(self):
        """Write response example contains extracted EXAMPLE content."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write
            assert "Deployment Topology" in out["example"] or "Component" in out["example"]

    def test_heading_level_2_for_section(self):
        """## headings have level=2."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write for ##
            assert out["level"] == 2

    def test_heading_level_3_for_child(self):
        """### headings have level=3."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE)
            responses = _drain_all(paths)
            child_writes = [r for r in responses
                           if r.get("type") == "write" and r.get("level") == 3]
            assert len(child_writes) > 0

    def test_heading_level_4_for_grandchild(self):
        """#### headings have level=4."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=DEEP_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="DEEP")
            responses = _drain_all(paths)
            grandchild_writes = [r for r in responses
                                if r.get("type") == "write" and r.get("level") == 4]
            assert len(grandchild_writes) > 0


# ---------------------------------------------------------------------------
# HIT-05: Done response
# ---------------------------------------------------------------------------

class TestDoneResponse:
    """HIT-05: Done response after all headings processed."""

    def test_done_after_all_headings(self):
        """Last response is done with correct count."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            responses = _drain_all(paths)
            done = responses[-1]
            assert done["done"] is True
            assert "headings_processed" in done

    def test_done_count_matches_writes(self):
        """headings_processed equals number of write responses."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            done = responses[-1]
            assert done["headings_processed"] == len(writes)

    def test_done_idempotent(self):
        """Calling after done keeps returning done."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            responses = _drain_all(paths)
            done1 = responses[-1]
            assert done1["done"] is True

            done2 = _run(paths)
            assert done2["done"] is True

    def test_empty_template_immediate_done(self):
        """Template with no ## headings returns immediate done."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=EMPTY_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="GLOSSARY")
            out = _run(paths)
            assert out["done"] is True
            assert out["headings_processed"] == 0


# ---------------------------------------------------------------------------
# HIT-06: Depth-first ordering
# ---------------------------------------------------------------------------

class TestDepthFirstOrdering:
    """HIT-06: Depth-first ordering with source files only in orient."""

    def test_orient_before_writes_per_section(self):
        """Each ## section starts with orient, then writes."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)

            # Find orient indices
            orient_indices = [i for i, r in enumerate(responses)
                             if r.get("type") == "orient"]
            assert len(orient_indices) == 2  # 2 ## sections

            # After first orient, next should be write
            for idx in orient_indices:
                if idx + 1 < len(responses) - 1:  # not the done response
                    assert responses[idx + 1].get("type") == "write"

    def test_depth_first_section_then_children(self):
        """## write comes before ### writes in the same section."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]

            # First section writes: infrastructure-overview, then children
            section_writes = []
            for w in writes:
                if w["heading_path"].startswith("infrastructure-overview"):
                    section_writes.append(w)
                elif section_writes:
                    break  # moved to next section

            assert section_writes[0]["level"] == 2
            assert section_writes[0]["heading_path"] == "infrastructure-overview"
            # Children follow
            for sw in section_writes[1:]:
                assert sw["level"] == 3

    def test_source_files_only_in_orient(self):
        """Write responses never have source_files."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            for w in writes:
                assert "source_files" not in w

    def test_full_sequence_nested(self):
        """Full sequence: orient, write(##), write(###), write(###), orient, write(##), done."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            types = [r.get("type", "done") for r in responses]
            # Expected: orient, write, write, write, orient, write, done
            assert types == ["orient", "write", "write", "write", "orient", "write", "done"]

    def test_deep_nesting_depth_first(self):
        """#### grandchildren come after their ### parent, before next ### sibling."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=DEEP_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="DEEP")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]

            # Config Reference section: ##, ###(env-vars), ####(required), ####(optional), ###(config-files)
            config_writes = [w for w in writes
                            if w["heading_path"].startswith("config-reference")]
            paths_order = [w["heading_path"] for w in config_writes]
            assert paths_order == [
                "config-reference",
                "config-reference/environment-variables",
                "config-reference/environment-variables/required-variables",
                "config-reference/environment-variables/optional-variables",
                "config-reference/configuration-files",
            ]


# ---------------------------------------------------------------------------
# HIT-07: heading_path convention
# ---------------------------------------------------------------------------

class TestHeadingPathConvention:
    """HIT-07: heading_path slug convention for write-section.py compatibility."""

    def test_section_heading_no_slash(self):
        """## heading_path has no slash."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            _run(paths)  # orient
            out = _run(paths)  # write
            assert "/" not in out["heading_path"]

    def test_child_heading_one_slash(self):
        """### heading_path has one slash: section/child."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            child_writes = [r for r in responses
                           if r.get("type") == "write" and r.get("level") == 3]
            for cw in child_writes:
                parts = cw["heading_path"].split("/")
                assert len(parts) == 2

    def test_grandchild_heading_two_slashes(self):
        """#### heading_path has two slashes: section/child/grandchild."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=DEEP_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="DEEP")
            responses = _drain_all(paths)
            grandchild_writes = [r for r in responses
                                if r.get("type") == "write" and r.get("level") == 4]
            for gw in grandchild_writes:
                parts = gw["heading_path"].split("/")
                assert len(parts) == 3

    def test_last_segment_is_section_slug(self):
        """Last segment of heading_path is the heading's own slug."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=NESTED_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            for w in writes:
                last = w["heading_path"].split("/")[-1]
                # Should be a valid slug (lowercase, hyphens)
                assert last == last.lower()
                assert " " not in last

    def test_parent_path_is_preceding_segments(self):
        """parent_path is everything before the last slash."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=DEEP_TEMPLATE,
                                    scan={"source_material_index": {}},
                                    document="DEEP")
            responses = _drain_all(paths)
            child_writes = [r for r in responses
                           if r.get("type") == "write" and "/" in r.get("heading_path", "")]
            for cw in child_writes:
                expected_parent = cw["heading_path"].rsplit("/", 1)[0]
                assert cw["parent_path"] == expected_parent


# ---------------------------------------------------------------------------
# XML format-specific tests
# ---------------------------------------------------------------------------

class TestXMLFormat:
    """Tests specific to the XML tag annotation format."""

    def test_evidence_not_served_to_writer(self):
        """Evidence tag content is stripped — not included in purpose field."""
        template = """\
<!-- DIATAXIS: how-to -->
# Title

## Deploy Steps
<purpose>Step-by-step deployment procedure covering dependency installation
and service restarts.</purpose>
<evidence>uv sync for dependencies. 2 Alembic chains (alembic_road_runner.ini,
alembic_archive.ini). 3 systemd services with Requires ordering.</evidence>
<example>
1. ...
</example>
"""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=template,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            assert len(writes) == 1
            # Purpose should contain the scope text, not the evidence values
            assert "deployment procedure" in writes[0]["purpose"].lower()
            assert "alembic" not in writes[0]["purpose"].lower()
            assert "systemd" not in writes[0]["purpose"].lower()

    def test_inline_optional_stripped_from_title(self):
        """Inline <!-- optional --> is stripped from heading title and slug."""
        template = """\
<!-- DIATAXIS: reference -->
# Title

## Main Section
<purpose>Main section.</purpose>

### Sub Section <!-- optional -->
<purpose>Optional subsection.</purpose>
"""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=template,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            child_writes = [w for w in writes if w.get("level") == 3]
            assert len(child_writes) == 1
            # Slug should be clean — no "optional" artifact
            slug = child_writes[0]["heading_path"].split("/")[-1]
            assert slug == "sub-section"

    def test_headings_inside_xml_example_not_treated_as_real(self):
        """Headings inside <example> tags are not treated as real headings."""
        template = """\
<!-- DIATAXIS: how-to -->
# Title

## Overview
<purpose>System overview.</purpose>
<example>
### Fake Heading Inside Example

| Col | Val |
|-----|-----|
| A | B |
</example>
"""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td, template_text=template,
                                    scan={"source_material_index": {}},
                                    document="TEST")
            responses = _drain_all(paths)
            writes = [r for r in responses if r.get("type") == "write"]
            # Only 1 real heading (## Overview), the ### inside <example> is excluded
            assert len(writes) == 1
            assert writes[0]["heading_path"] == "overview"


# ---------------------------------------------------------------------------
# DB table map injection
# ---------------------------------------------------------------------------

class TestDbTableMap:
    """--db-table-map injects relevant_tables into orient responses."""

    def test_orient_includes_relevant_tables_when_map_provided(self):
        """Orient response includes relevant_tables when section is in map."""
        db_table_map = {
            "OPERATIONS/infrastructure-overview": ["etl_runs", "stocks"],
        }
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            # Write db-table-map file
            map_path = os.path.join(td, "db-table-map.json")
            with open(map_path, "w") as f:
                json.dump(db_table_map, f)
            # Run with --db-table-map
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", paths["state"],
                 "--template", paths["template"],
                 "--scan-file", paths["scan"],
                 "--document", paths["document"],
                 "--db-table-map", map_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            out = json.loads(result.stdout)
            assert out["type"] == "orient"
            assert out["relevant_tables"] == ["etl_runs", "stocks"]

    def test_orient_omits_relevant_tables_when_no_map(self):
        """Orient response has no relevant_tables when --db-table-map not provided."""
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            out = _run(paths)  # no --db-table-map
            assert out["type"] == "orient"
            assert "relevant_tables" not in out

    def test_orient_omits_relevant_tables_when_section_not_in_map(self):
        """Orient response has no relevant_tables when section is not in map."""
        db_table_map = {
            "OPERATIONS/other-section": ["some_table"],
        }
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            map_path = os.path.join(td, "db-table-map.json")
            with open(map_path, "w") as f:
                json.dump(db_table_map, f)
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--state-file", paths["state"],
                 "--template", paths["template"],
                 "--scan-file", paths["scan"],
                 "--document", paths["document"],
                 "--db-table-map", map_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            out = json.loads(result.stdout)
            assert out["type"] == "orient"
            assert "relevant_tables" not in out

    def test_second_orient_gets_its_own_tables(self):
        """Each orient response gets its own relevant_tables from the map."""
        db_table_map = {
            "OPERATIONS/infrastructure-overview": ["etl_runs"],
            "OPERATIONS/deployment": ["stocks"],
        }
        with tempfile.TemporaryDirectory() as td:
            paths = _write_fixtures(td)
            map_path = os.path.join(td, "db-table-map.json")
            with open(map_path, "w") as f:
                json.dump(db_table_map, f)

            # Drain all responses
            responses = []
            for _ in range(20):
                result = subprocess.run(
                    [sys.executable, SCRIPT,
                     "--state-file", paths["state"],
                     "--template", paths["template"],
                     "--scan-file", paths["scan"],
                     "--document", paths["document"],
                     "--db-table-map", map_path],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0
                out = json.loads(result.stdout)
                responses.append(out)
                if out.get("done"):
                    break

            orients = [r for r in responses if r.get("type") == "orient"]
            assert len(orients) == 2
            assert orients[0].get("relevant_tables") == ["etl_runs"]
            assert orients[1].get("relevant_tables") == ["stocks"]


# ---------------------------------------------------------------------------
# DB model for init mode tests
# ---------------------------------------------------------------------------

DB_MODEL = {
    "schemas": {
        "road_runner": {
            "tables": {
                "etl_runs": {
                    "columns": [
                        {"name": "id", "type": "Integer", "primary_key": True,
                         "nullable": False, "foreign_key": None},
                        {"name": "flow_name", "type": "String(100)", "primary_key": False,
                         "nullable": False, "foreign_key": None},
                    ]
                },
                "stocks": {
                    "columns": [
                        {"name": "id", "type": "Integer", "primary_key": True,
                         "nullable": False, "foreign_key": None},
                        {"name": "ticker", "type": "String(10)", "primary_key": False,
                         "nullable": False, "foreign_key": None},
                    ]
                },
            }
        }
    }
}


def _write_init_fixtures(td, template_text=SIMPLE_TEMPLATE, scan=None,
                         document="OPERATIONS", db_table_map=None, db_model=None):
    """Write fixtures for init mode tests. Returns dict of paths."""
    template_path = os.path.join(td, "template.md")
    with open(template_path, "w") as f:
        f.write(template_text)

    scan_path = os.path.join(td, "scan.json")
    scan_data = scan if scan is not None else SCAN_DATA
    with open(scan_path, "w") as f:
        json.dump(scan_data, f)

    state_path = os.path.join(td, f"heading-state-devops-{document}.json")

    result = {
        "template": template_path,
        "scan": scan_path,
        "state": state_path,
        "document": document,
    }

    if db_table_map is not None:
        map_path = os.path.join(td, "db-table-map.json")
        with open(map_path, "w") as f:
            json.dump(db_table_map, f)
        result["db_table_map"] = map_path

    if db_model is not None:
        model_path = os.path.join(td, "database-model.json")
        with open(model_path, "w") as f:
            json.dump(db_model, f)
        result["db_model"] = model_path

    return result


def _run_init(fixtures):
    """Run next-heading.py --init and return (returncode, stderr)."""
    cmd = [
        sys.executable, SCRIPT, "--init",
        "--state-file", fixtures["state"],
        "--template", fixtures["template"],
        "--scan-file", fixtures["scan"],
        "--document", fixtures["document"],
    ]
    if "db_table_map" in fixtures:
        cmd.extend(["--db-table-map", fixtures["db_table_map"]])
    if "db_model" in fixtures:
        cmd.extend(["--db-model", fixtures["db_model"]])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def _run_runtime(generate_dir, audience, document):
    """Run next-heading.py in runtime mode and return parsed JSON."""
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--generate-dir", generate_dir,
         "--audience", audience,
         "--document", document],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return json.loads(result.stdout)


def _drain_runtime(generate_dir, audience, document):
    """Drain all responses from runtime mode."""
    responses = []
    for _ in range(100):
        out = _run_runtime(generate_dir, audience, document)
        responses.append(out)
        if out.get("done"):
            break
    return responses


# ---------------------------------------------------------------------------
# Init mode tests
# ---------------------------------------------------------------------------

class TestInitMode:
    """--init mode: builds queue and saves state without stdout."""

    def test_init_creates_state_file(self):
        """--init creates the state file."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            rc, stdout, stderr = _run_init(fixtures)
            assert rc == 0, f"stderr: {stderr}"
            assert os.path.isfile(fixtures["state"])

    def test_init_no_stdout(self):
        """--init produces no stdout output."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            rc, stdout, stderr = _run_init(fixtures)
            assert rc == 0
            assert stdout.strip() == ""

    def test_init_state_has_queue(self):
        """State file from --init contains queue and index."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            _run_init(fixtures)
            with open(fixtures["state"]) as f:
                state = json.load(f)
            assert "queue" in state
            assert state["index"] == 0
            assert len(state["queue"]) > 0

    def test_init_requires_state_file(self):
        """--init without --state-file exits with error."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--init",
             "--template", "/fake", "--scan-file", "/fake",
             "--document", "DOC"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_init_requires_template(self):
        """--init without --template exits with error."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--init",
             "--state-file", "/fake", "--scan-file", "/fake",
             "--document", "DOC"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_init_requires_scan_file(self):
        """--init without --scan-file exits with error."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--init",
             "--state-file", "/fake", "--template", "/fake",
             "--document", "DOC"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_init_with_db_model_injects_column_detail(self):
        """--init with --db-model injects db_column_detail into orient responses."""
        db_table_map = {
            "OPERATIONS/infrastructure-overview": ["etl_runs", "stocks"],
        }
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(
                td, db_table_map=db_table_map, db_model=DB_MODEL,
            )
            rc, _, stderr = _run_init(fixtures)
            assert rc == 0, f"stderr: {stderr}"

            with open(fixtures["state"]) as f:
                state = json.load(f)
            orients = [e for e in state["queue"] if e.get("type") == "orient"]
            # First orient (infrastructure-overview) should have db_column_detail
            assert "db_column_detail" in orients[0]
            assert "road_runner.etl_runs:" in orients[0]["db_column_detail"]
            assert "road_runner.stocks:" in orients[0]["db_column_detail"]

    def test_init_without_db_model_no_column_detail(self):
        """--init without --db-model: no db_column_detail in orients."""
        db_table_map = {
            "OPERATIONS/infrastructure-overview": ["etl_runs"],
        }
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td, db_table_map=db_table_map)
            _run_init(fixtures)
            with open(fixtures["state"]) as f:
                state = json.load(f)
            orients = [e for e in state["queue"] if e.get("type") == "orient"]
            assert "db_column_detail" not in orients[0]

    def test_init_orient_without_tables_no_column_detail(self):
        """Orient for section with no relevant_tables gets no db_column_detail."""
        db_table_map = {
            "OPERATIONS/deployment": ["stocks"],
        }
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(
                td, db_table_map=db_table_map, db_model=DB_MODEL,
            )
            _run_init(fixtures)
            with open(fixtures["state"]) as f:
                state = json.load(f)
            orients = [e for e in state["queue"] if e.get("type") == "orient"]
            # First orient (infrastructure-overview) has no tables in map
            assert "db_column_detail" not in orients[0]
            # Second orient (deployment) has tables
            assert "db_column_detail" in orients[1]


# ---------------------------------------------------------------------------
# Runtime mode tests (--generate-dir + --audience)
# ---------------------------------------------------------------------------

class TestRuntimeMode:
    """Runtime mode: derives state path from convention."""

    def test_runtime_reads_pre_initialized_state(self):
        """Runtime mode reads from pre-initialized state file."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            _run_init(fixtures)
            # Now call in runtime mode
            out = _run_runtime(td, "devops", "OPERATIONS")
            assert out["type"] == "orient"

    def test_runtime_convention_path(self):
        """State file path follows {generate_dir}/heading-state-{audience}-{document}.json."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            _run_init(fixtures)
            # Verify the convention path works
            expected = os.path.join(td, "heading-state-devops-OPERATIONS.json")
            assert os.path.isfile(expected)
            out = _run_runtime(td, "devops", "OPERATIONS")
            assert "type" in out or "done" in out

    def test_runtime_full_drain(self):
        """Runtime mode can drain all responses from pre-initialized state."""
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(td)
            _run_init(fixtures)
            responses = _drain_runtime(td, "devops", "OPERATIONS")
            assert responses[-1].get("done") is True
            writes = [r for r in responses if r.get("type") == "write"]
            assert len(writes) > 0

    def test_runtime_with_db_column_detail(self):
        """Runtime mode returns orient responses with db_column_detail from init."""
        db_table_map = {
            "OPERATIONS/infrastructure-overview": ["etl_runs"],
        }
        with tempfile.TemporaryDirectory() as td:
            fixtures = _write_init_fixtures(
                td, db_table_map=db_table_map, db_model=DB_MODEL,
            )
            _run_init(fixtures)
            out = _run_runtime(td, "devops", "OPERATIONS")
            assert out["type"] == "orient"
            assert "db_column_detail" in out
            assert "road_runner.etl_runs:" in out["db_column_detail"]

    def test_runtime_without_generate_dir_and_state_file_fails(self):
        """Missing both --generate-dir and --state-file exits with error."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--document", "DOC"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
