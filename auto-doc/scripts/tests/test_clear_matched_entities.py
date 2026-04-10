"""Tests for clear-matched-entities.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "clear-matched-entities.py")


def _setup(td, sections, entities):
    """Create prose-verify dir with manifest + section JSONs, and entities file.

    Args:
        td: Temporary directory.
        sections: List of dicts with keys: path, body, ref_entries.
            ref_entries is a list of {display, identifier} dicts.
        entities: List of {name, section} dicts.

    Returns:
        Tuple of (prose_dir, entities_file, uncleared_file, findings_file).
    """
    prose_dir = os.path.join(td, "prose-verify")
    os.makedirs(prose_dir)

    manifest = {
        "xml_file": "/fake/doc.xml",
        "audience": "devops",
        "document": "OPERATIONS",
        "sections": [s["path"] for s in sections],
    }
    with open(os.path.join(prose_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    for sec in sections:
        slug = os.path.basename(sec["path"])
        parent = os.path.dirname(sec["path"])
        section_data = {
            "path": sec["path"],
            "slug": slug,
            "document": "OPERATIONS",
            "audience": "devops",
            "body": sec.get("body", f"## {slug}\n\nSome prose."),
            "refs_as_text": "- refs",
            "malformed_refs": [],
            "ref_entries": sec.get("ref_entries", []),
        }
        if parent:
            os.makedirs(os.path.join(prose_dir, parent), exist_ok=True)
            out_path = os.path.join(prose_dir, parent, f"{slug}.json")
        else:
            out_path = os.path.join(prose_dir, f"{slug}.json")
        with open(out_path, "w") as f:
            json.dump(section_data, f)

    entities_file = os.path.join(td, "entities.json")
    with open(entities_file, "w") as f:
        json.dump(entities, f)

    uncleared_file = os.path.join(td, "uncleared.json")
    findings_file = os.path.join(td, "findings.json")
    return prose_dir, entities_file, uncleared_file, findings_file


def _run(prose_dir, entities_file, uncleared_file, findings_file,
         document="OPERATIONS", audience="devops", not_entities_file=None):
    """Run clear-matched-entities.py and return result."""
    cmd = [sys.executable, SCRIPT,
           "--entities-file", entities_file,
           "--prose-verify-dir", prose_dir,
           "--uncleared-file", uncleared_file,
           "--findings-file", findings_file,
           "--document", document,
           "--audience", audience]
    if not_entities_file:
        cmd.extend(["--not-entities-file", not_entities_file])
    return subprocess.run(cmd, capture_output=True, text=True)


class TestClearing:
    """Clearing: entity name matched against ref identifiers."""

    def test_all_entities_clear(self):
        """All entities match exactly one ref → uncleared is empty."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `etl_runs` table has `flow_name`.",
                    "ref_entries": [
                        {"display": "[db] rr.etl_runs", "identifier": "etl_runs",
                         "path": ["road_runner", "etl_runs"]},
                        {"display": "[db] rr.etl_runs.flow_name", "identifier": "flow_name",
                         "path": ["road_runner", "etl_runs", "flow_name"]},
                    ],
                },
            ], [
                {"name": "road_runner", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "flow_name", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 3" in result.stderr

    def test_no_entities_clear(self):
        """No matches → all entities uncleared."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [
                        {"display": "[env] PORT", "identifier": "PORT"},
                    ],
                },
            ], [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "flow_name", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 2

    def test_partial_clearing(self):
        """Mix of cleared and uncleared entities."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `etl_runs` table.",
                    "ref_entries": [
                        {"display": "[dep] etl_runs", "identifier": "etl_runs",
                         "path": ["etl_runs"]},
                    ],
                },
            ], [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "unknown_thing", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "unknown_thing"
            assert "Cleared: 1" in result.stderr

    def test_multi_match_does_not_clear(self):
        """Entity matching 2 fully-present ref paths stays uncleared (ambiguity).

        When two paths share components and all components are present,
        none can uniquely resolve — everything stays uncleared.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe alpha beta field.",
                    "ref_entries": [
                        {"display": "[db] s.t1.alpha", "identifier": "alpha",
                         "path": ["alpha", "beta"]},
                        {"display": "[db] s.t2.alpha", "identifier": "alpha",
                         "path": ["alpha", "gamma"]},
                    ],
                },
            ], [
                {"name": "alpha", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # alpha appears in both paths, neither fully present (beta, gamma missing)
            # → no candidates → stays uncleared
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "alpha"

    def test_empty_entities_file(self):
        """Empty entities list → empty uncleared file."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [
                        {"display": "[env] PORT", "identifier": "PORT"},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []


class TestCheckB:
    """Check B: ref identifier must appear in section body."""

    def test_missing_identifier_emits_finding(self):
        """Ref identifier not in body → reference-integrity finding."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nGeneral info about the system.",
                    "ref_entries": [
                        {"display": "[env] MISSING_VAR", "identifier": "MISSING_VAR"},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(ff) as f:
                findings = json.load(f)
            assert len(findings) == 1
            assert findings[0]["check"] == "reference-integrity"
            assert "MISSING_VAR" in findings[0]["description"]

    def test_present_identifier_no_finding(self):
        """Ref identifier in body → no finding."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nCheck the PORT variable.",
                    "ref_entries": [
                        {"display": "[env] PORT", "identifier": "PORT"},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert not os.path.exists(ff)  # no findings file created

    def test_substring_match_passes(self):
        """Identifier found as substring (e.g. in qualified name)."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `road_runner.etl_runs` table.",
                    "ref_entries": [
                        {"display": "[db] rr.etl_runs", "identifier": "etl_runs"},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert not os.path.exists(ff)

    def test_null_identifier_skipped(self):
        """Ref entry with null identifier does not trigger Check B."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [
                        {"display": "[dep] tenacity", "identifier": None},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert not os.path.exists(ff)


class TestAffectedSections:
    """affected-sections.json tracks sections with uncleared entities."""

    def test_affected_sections_output(self):
        """Only sections with uncleared entities are listed."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `etl_runs` table.",
                    "ref_entries": [
                        {"display": "[dep] etl_runs", "identifier": "etl_runs",
                         "path": ["etl_runs"]},
                    ],
                },
                {
                    "path": "deployment",
                    "body": "## Deployment\n\nDeploy via CI.",
                    "ref_entries": [
                        {"display": "[env] PORT", "identifier": "PORT",
                         "path": ["PORT"]},
                    ],
                },
            ], [
                {"name": "etl_runs", "section": "monitoring"},   # clears
                {"name": "unknown", "section": "deployment"},    # uncleared
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            affected_path = os.path.join(prose_dir, "affected-sections.json")
            with open(affected_path) as f:
                affected = json.load(f)
            assert affected == ["deployment"]

    def test_no_affected_sections(self):
        """All entities clear → affected-sections is empty."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `etl_runs` table.",
                    "ref_entries": [
                        {"display": "[dep] etl_runs", "identifier": "etl_runs",
                         "path": ["etl_runs"]},
                    ],
                },
            ], [
                {"name": "etl_runs", "section": "monitoring"},
            ])

            _run(prose_dir, ef, uf, ff)

            affected_path = os.path.join(prose_dir, "affected-sections.json")
            with open(affected_path) as f:
                affected = json.load(f)
            assert affected == []


class TestMultiComponentClearing:
    """Conservative path resolver for multi-component refs."""

    def test_all_path_components_clear(self):
        """All components of a ref path clear when path is present."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe road_runner.etl_runs.flow_name column.",
                    "ref_entries": [
                        {
                            "display": "[db] road_runner.etl_runs.flow_name",
                            "identifier": "flow_name",
                            "path": ["road_runner", "etl_runs", "flow_name"],
                        },
                    ],
                },
            ], [
                {"name": "road_runner", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "flow_name", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 3" in result.stderr

    def test_ambiguous_component_stays_uncleared(self):
        """Entity matching 2 paths stays uncleared."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe status field.",
                    "ref_entries": [
                        {
                            "display": "[db] rr.etl_runs.status",
                            "identifier": "status",
                            "path": ["road_runner", "etl_runs", "status"],
                        },
                        {
                            "display": "[db] rr.jobs.status",
                            "identifier": "status",
                            "path": ["road_runner", "jobs", "status"],
                        },
                    ],
                },
            ], [
                {"name": "status", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "status"

    def test_disambiguation_via_context(self):
        """Sibling entity disambiguates which path status belongs to."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe etl_runs table has status.",
                    "ref_entries": [
                        {
                            "display": "[db] rr.etl_runs.status",
                            "identifier": "status",
                            "path": ["road_runner", "etl_runs", "status"],
                        },
                        {
                            "display": "[db] rr.jobs.status",
                            "identifier": "status",
                            "path": ["road_runner", "jobs", "status"],
                        },
                    ],
                },
            ], [
                {"name": "road_runner", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "status", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # etl_runs is only in one path, so it resolves that path,
            # which then clears road_runner and status too
            assert uncleared == []
            assert "Cleared: 3" in result.stderr

    def test_fixed_point_iteration(self):
        """Earlier clearings disambiguate later entities across iterations.

        flow_name is unique to the etl_runs path → resolves it (iteration 1).
        This disambiguates status: the jobs path needs `jobs` which is absent
        from entity set, so only the etl_runs path survives → resolves (iteration 2).
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nflow_name and status in etl_runs.",
                    "ref_entries": [
                        {
                            "display": "[db] rr.etl_runs.flow_name",
                            "identifier": "flow_name",
                            "path": ["etl_runs", "flow_name"],
                        },
                        {
                            "display": "[db] rr.etl_runs.status",
                            "identifier": "status",
                            "path": ["etl_runs", "status"],
                        },
                        {
                            "display": "[db] rr.jobs.status",
                            "identifier": "status",
                            "path": ["jobs", "status"],
                        },
                    ],
                },
            ], [
                {"name": "flow_name", "section": "monitoring"},
                {"name": "status", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # Iteration 1: flow_name uniquely in etl_runs path → clears etl_runs, flow_name
            # Iteration 2: status has two candidates, but jobs path needs `jobs`
            # (not in entity set) → only etl_runs path survives → clears status
            assert uncleared == []
            assert "Cleared: 3" in result.stderr

    def test_no_path_field_falls_through(self):
        """Ref entries without path field → entities stay uncleared."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe etl_runs table.",
                    "ref_entries": [
                        {"display": "[db] rr.etl_runs", "identifier": "etl_runs"},
                    ],
                },
            ], [
                {"name": "road_runner", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "road_runner"

    def test_single_component_path_clears(self):
        """Single-component path (e.g. config basename) still clears."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nConfig in settings.yaml.",
                    "ref_entries": [
                        {
                            "display": "[config] config/settings.yaml",
                            "identifier": "settings.yaml",
                            "path": ["settings.yaml"],
                        },
                    ],
                },
            ], [
                {"name": "settings.yaml", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []


class TestCheckBWave:
    """Check B findings have wave=0 metadata."""

    def test_check_b_findings_have_wave_zero(self):
        """Reference-integrity findings from Check B have wave=0."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nGeneral info.",
                    "ref_entries": [
                        {"display": "[env] MISSING_VAR", "identifier": "MISSING_VAR"},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(ff) as f:
                findings = json.load(f)
            assert len(findings) == 1
            assert findings[0]["wave"] == 0


class TestSummary:
    """Summary output on stderr."""

    def test_summary_on_stderr(self):
        """Summary line printed to stderr."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nThe `etl_runs` table.",
                    "ref_entries": [
                        {"display": "[dep] etl_runs", "identifier": "etl_runs",
                         "path": ["etl_runs"]},
                    ],
                },
            ], [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "unknown", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert "Extracted: 2" in result.stderr
            assert "Cleared: 1" in result.stderr
            assert "Uncleared: 1" in result.stderr


class TestNotEntitiesFilter:
    """Pre-filtering entities against not-entities list."""

    def test_not_entities_filtered_before_clearing(self):
        """Entities in not-entities list are excluded before clearing."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "bash", "section": "monitoring"},
                {"name": "python3", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
            ])

            nf = os.path.join(td, "not-entities.json")
            with open(nf, "w") as f:
                json.dump([
                    {"name": "bash", "dismissed_in": "deployment"},
                    {"name": "python3", "dismissed_in": "deployment"},
                ], f)

            result = _run(prose_dir, ef, uf, ff, not_entities_file=nf)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # bash and python3 filtered out, only etl_runs remains
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "etl_runs"
            # Extracted count reflects post-filter
            assert "Extracted: 1" in result.stderr

    def test_not_entities_plain_string_format(self):
        """Not-entities list with plain string entries works."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "bash", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
            ])

            nf = os.path.join(td, "not-entities.json")
            with open(nf, "w") as f:
                json.dump(["bash"], f)

            result = _run(prose_dir, ef, uf, ff, not_entities_file=nf)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "etl_runs"

    def test_without_not_entities_file_unchanged(self):
        """Without --not-entities-file, behavior is unchanged."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "bash", "section": "monitoring"},
                {"name": "etl_runs", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # Both entities uncleared (no refs to match)
            assert len(uncleared) == 2

    def test_empty_not_entities_file(self):
        """Empty not-entities list has no effect."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "bash", "section": "monitoring"},
            ])

            nf = os.path.join(td, "not-entities.json")
            with open(nf, "w") as f:
                json.dump([], f)

            result = _run(prose_dir, ef, uf, ff, not_entities_file=nf)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1


class TestDotSplitClearing:
    """Dot-split preprocessing: compound dotted entities clear via segments."""

    def test_schema_qualified_clears(self):
        """raw_fmp.income_statements with path (raw_fmp, income_statements) → cleared."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "data-sources",
                    "body": "## Data Sources\n\nThe income_statements table in raw_fmp.",
                    "ref_entries": [
                        {
                            "display": "[db] raw_fmp.income_statements",
                            "identifier": "income_statements",
                            "path": ["raw_fmp", "income_statements"],
                        },
                    ],
                },
            ], [
                {"name": "raw_fmp.income_statements", "section": "data-sources"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_dotted_dep_clears(self):
        """httpx.TimeoutException with dep path (httpx, TimeoutException) → compound clears."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "dependencies",
                    "body": "## Dependencies\n\nUses httpx for HTTP calls.",
                    "ref_entries": [
                        {
                            "display": "[dep] httpx",
                            "identifier": "httpx",
                            "path": ["httpx", "TimeoutException"],
                        },
                    ],
                },
            ], [
                {"name": "httpx.TimeoutException", "section": "dependencies"},
                {"name": "TimeoutException", "section": "dependencies"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # httpx.TimeoutException clears (both segments match the path)
            # TimeoutException alone also clears (it's a path component)
            assert uncleared == []

    def test_dotted_no_ref_stays_uncleared(self):
        """foo.bar with no matching refs → stays uncleared."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "foo.bar", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "foo.bar"

    def test_short_dotted_no_false_clear(self):
        """os.path with no refs → stays uncleared (no false positives)."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome prose.",
                    "ref_entries": [
                        {
                            "display": "[env] PORT",
                            "identifier": "PORT",
                            "path": ["PORT"],
                        },
                    ],
                },
            ], [
                {"name": "os.path", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "os.path"

    def test_mixed_dotted_and_plain(self):
        """Dotted entity clears + plain entity stays → correct mix."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "data-sources",
                    "body": "## Data Sources\n\nThe income_statements in raw_fmp.",
                    "ref_entries": [
                        {
                            "display": "[db] raw_fmp.income_statements",
                            "identifier": "income_statements",
                            "path": ["raw_fmp", "income_statements"],
                        },
                    ],
                },
            ], [
                {"name": "raw_fmp.income_statements", "section": "data-sources"},
                {"name": "unknown_thing", "section": "data-sources"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "unknown_thing"
            assert "Cleared: 1" in result.stderr

    def test_dot_split_segments_not_in_uncleared(self):
        """Synthetic segments from dot-split do NOT appear in uncleared output."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "data-sources",
                    "body": "## Data Sources\n\nSome prose.",
                    "ref_entries": [],
                },
            ], [
                {"name": "foo.bar", "section": "data-sources"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # Only the original dotted entity in output, not "foo" or "bar"
            names = [e["name"] for e in uncleared]
            assert names == ["foo.bar"]
