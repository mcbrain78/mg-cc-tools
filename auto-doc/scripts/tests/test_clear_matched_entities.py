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

    def test_multi_match_clears_via_identifier(self):
        """Entity matching 2 ref paths clears in identifier pass.

        Even though path resolution would be ambiguous, the identifier
        match fires first and clears the entity.
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
            # Any identifier match clears — duplicate identifiers no longer block
            assert len(uncleared) == 0

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

    def test_db_ancestor_entries_skipped(self):
        """Ancestor-only db entries (display=None) do not emit findings.

        parse_xml_doc._parse_db_refs fans out a nested <db><schema><table>
        element into one ref per hierarchy level. Ancestor entries (db-only,
        db+schema) have display=None per prepare-prose-verify's
        _format_single_ref. Check B must skip them so intermediate hierarchy
        names do not generate spurious "Declared ref None" findings.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": (
                        "## Monitoring\n\n"
                        "The `data_drift_warnings` table tracks incidents."
                    ),
                    "ref_entries": [
                        {"display": None, "identifier": "finance",
                         "path": ["finance"]},
                        {"display": None, "identifier": "public",
                         "path": ["finance", "public"]},
                        {"display": "[db] public.data_drift_warnings",
                         "identifier": "data_drift_warnings",
                         "path": ["finance", "public", "data_drift_warnings"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            # Leaf identifier IS in body, ancestors are skipped — no findings.
            assert not os.path.exists(ff), (
                "Ancestor ref entries with display=None must not trigger "
                "Check B findings"
            )

    def test_db_ancestor_skipped_when_leaf_missing_from_body(self):
        """Ancestor entries stay skipped; only the leaf is checked against body."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nSome unrelated prose.",
                    "ref_entries": [
                        {"display": None, "identifier": "finance",
                         "path": ["finance"]},
                        {"display": None, "identifier": "public",
                         "path": ["finance", "public"]},
                        {"display": "[db] public.data_drift_warnings",
                         "identifier": "data_drift_warnings",
                         "path": ["finance", "public", "data_drift_warnings"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert os.path.exists(ff)
            with open(ff) as f:
                findings = json.load(f)
            # Exactly one finding — for the leaf; not three.
            assert len(findings) == 1
            assert findings[0]["description"].startswith(
                "Declared ref [db] public.data_drift_warnings"
            )

    def test_case_insensitive_dep_match(self):
        """Body uses brand capitalization (`Prefect`), ref identifier is
        lowercase package name (`prefect`) — Check B must pass.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "glossary",
                    "body": (
                        "## Glossary\n\nThe `Prefect` orchestrator runs flows "
                        "atop `SQLAlchemy` models."
                    ),
                    "ref_entries": [
                        {"display": "[dep] prefect", "identifier": "prefect",
                         "path": ["prefect"]},
                        {"display": "[dep] sqlalchemy",
                         "identifier": "sqlalchemy", "path": ["sqlalchemy"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert not os.path.exists(ff), (
                "Case-insensitive identifier match must not produce findings "
                "when prose uses natural capitalization of package names."
            )

    def test_case_sensitive_miss_still_fires(self):
        """Identifier genuinely absent from body at any case → finding fires."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "glossary",
                    "body": "## Glossary\n\nUnrelated prose.",
                    "ref_entries": [
                        {"display": "[dep] prefect", "identifier": "prefect",
                         "path": ["prefect"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert os.path.exists(ff)
            with open(ff) as f:
                findings = json.load(f)
            assert len(findings) == 1
            assert "prefect" in findings[0]["description"]

    def test_prefix_covered_by_child_ref_skipped(self):
        """Table ref + column ref with prose naming only the column —
        table ref is implicitly covered by the column's path extending it.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "metrics",
                    "body": (
                        "## Metrics\n\nThe `price_cagr_10y` column tracks "
                        "the 10-year price growth rate."
                    ),
                    "ref_entries": [
                        {"display": "[db] finance_metrics.finance_metrics",
                         "identifier": "finance_metrics",
                         "path": ["finance", "finance_metrics",
                                  "finance_metrics"]},
                        {"display":
                         "[db] finance_metrics.finance_metrics.price_cagr_10y",
                         "identifier": "price_cagr_10y",
                         "path": ["finance", "finance_metrics",
                                  "finance_metrics", "price_cagr_10y"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert not os.path.exists(ff), (
                "Table ref must be prefix-covered by the column ref under "
                "it; no finding expected."
            )

    def test_prefix_not_covered_when_standalone(self):
        """Table ref alone with no column under it — prefix-skip must NOT
        trigger; integrity check still fires when table name is absent from body.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "metrics",
                    "body": "## Metrics\n\nSome unrelated prose.",
                    "ref_entries": [
                        {"display": "[db] finance_metrics.finance_metrics",
                         "identifier": "finance_metrics",
                         "path": ["finance", "finance_metrics",
                                  "finance_metrics"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert os.path.exists(ff)
            with open(ff) as f:
                findings = json.load(f)
            assert len(findings) == 1
            assert findings[0]["description"].startswith(
                "Declared ref [db] finance_metrics.finance_metrics"
            )

    def test_prefix_skip_parent_mentioned_siblings_not_needed(self):
        """Table + column, prose names the table only. Column fires (its
        path doesn't extend anything declared); table stays skipped because
        the column's path extends it.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "metrics",
                    "body": (
                        "## Metrics\n\nThe `finance_metrics` table holds "
                        "per-ticker derived values."
                    ),
                    "ref_entries": [
                        {"display": "[db] finance_metrics.finance_metrics",
                         "identifier": "finance_metrics",
                         "path": ["finance", "finance_metrics",
                                  "finance_metrics"]},
                        {"display":
                         "[db] finance_metrics.finance_metrics.price_cagr_10y",
                         "identifier": "price_cagr_10y",
                         "path": ["finance", "finance_metrics",
                                  "finance_metrics", "price_cagr_10y"]},
                    ],
                },
            ], [])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0
            assert os.path.exists(ff)
            with open(ff) as f:
                findings = json.load(f)
            # Only the column finding; the table is prefix-covered.
            assert len(findings) == 1
            assert "price_cagr_10y" in findings[0]["description"]


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

    def test_ambiguous_component_clears_via_identifier(self):
        """Entity matching 2 paths clears in identifier pass."""
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
            # Any identifier match clears — duplicate identifiers no longer block
            assert len(uncleared) == 0

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


class TestDotSplitClearingTail:
    """Dotted entity → tail of ref path: handles 3-component db paths etc."""

    def test_schema_qualified_clears_3_component_path(self):
        """finance_metrics.finance_metrics clears against (finance, finance_metrics, finance_metrics).

        The db component (finance) never appears in prose, so the existing
        path resolver cannot match. Tail-match fixes this.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "domain-terms",
                    "body": (
                        "## Domain Terms\n\n"
                        "Metrics persisted in the `finance_metrics.finance_metrics` table."
                    ),
                    "ref_entries": [
                        {
                            "display": "[db] finance_metrics.finance_metrics",
                            "identifier": "finance_metrics",
                            "path": ["finance", "finance_metrics", "finance_metrics"],
                        },
                    ],
                },
            ], [
                {"name": "finance_metrics.finance_metrics", "section": "domain-terms"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_3_component_code_ref_tail_clears(self):
        """User.save clears against (src/models.py, User, save) code path."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "data-model",
                    "body": (
                        "## Data Model\n\n"
                        "Persist via `User.save` method."
                    ),
                    "ref_entries": [
                        {
                            "display": "[code:function] User.save",
                            "identifier": "save",
                            "path": ["src/models.py", "User", "save"],
                        },
                    ],
                },
            ], [
                {"name": "User.save", "section": "data-model"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_head_match_does_not_clear(self):
        """foo.bar does NOT clear against (foo, bar, baz) — tail-anchored only.

        Prose `foo.bar` refers to a 2-segment entity. A ref path ending in `baz`
        is a different entity (baz is the leaf); head-matching would be wrong.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nReferences `foo.bar`.",
                    "ref_entries": [
                        {
                            "display": "[code:function] foo.bar.baz",
                            "identifier": "baz",
                            "path": ["foo", "bar", "baz"],
                        },
                    ],
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

    def test_mismatched_middle_does_not_clear(self):
        """bar.qux does NOT clear against (foo, bar, baz) — segments must contiguously match tail."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nReferences `bar.qux`.",
                    "ref_entries": [
                        {
                            "display": "[code:function] foo.bar.baz",
                            "identifier": "baz",
                            "path": ["foo", "bar", "baz"],
                        },
                    ],
                },
            ], [
                {"name": "bar.qux", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "bar.qux"

    def test_no_matching_ref_stays_uncleared(self):
        """json.loads with no matching ref path stays uncleared (no over-clearing)."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "technical-terms",
                    "body": (
                        "## Technical Terms\n\n"
                        "Parses with `json.loads`."
                    ),
                    "ref_entries": [
                        {
                            "display": "[dep] prefect",
                            "identifier": "prefect",
                            "path": ["prefect"],
                        },
                    ],
                },
            ], [
                {"name": "json.loads", "section": "technical-terms"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "json.loads"


class TestIdentifierClearing:
    """Identifier-based clearing: first pass before path resolution."""

    def test_unique_identifier_clears(self):
        """Entity matches a unique identifier in section → clears without path resolution."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nempty_str_to_none handles nulls.",
                    "ref_entries": [
                        {
                            "display": "[code] config.empty_str_to_none",
                            "identifier": "empty_str_to_none",
                            "path": ["src/road_runner/config.py", "empty_str_to_none"],
                        },
                    ],
                },
            ], [
                {"name": "empty_str_to_none", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_duplicate_identifier_still_clears(self):
        """Entity matches an identifier that appears in 2 refs → clears anyway."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nstatus column used in multiple tables.",
                    "ref_entries": [
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
                {"name": "status", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # Any identifier match clears — duplicate identifiers no longer block
            assert len(uncleared) == 0

    def test_identifier_clear_plus_path_clear(self):
        """Mix of identifier-cleared and path-cleared entities in same section."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nempty_str_to_none and etl_runs.flow_name.",
                    "ref_entries": [
                        {
                            "display": "[code] config.empty_str_to_none",
                            "identifier": "empty_str_to_none",
                            "path": ["src/road_runner/config.py", "empty_str_to_none"],
                        },
                        {
                            "display": "[db] rr.etl_runs.flow_name",
                            "identifier": "flow_name",
                            "path": ["etl_runs", "flow_name"],
                        },
                    ],
                },
            ], [
                # empty_str_to_none: clears via identifier (unique)
                {"name": "empty_str_to_none", "section": "monitoring"},
                # etl_runs + flow_name: clear via path resolution
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "flow_name", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 3" in result.stderr

    def test_no_path_ref_clears_by_identifier(self):
        """Ref with identifier but no path (like bare db name) → clears via identifier."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "monitoring",
                    "body": "## Monitoring\n\nroad_runner_db is the main database.",
                    "ref_entries": [
                        {
                            "display": "[db] road_runner_db",
                            "identifier": "road_runner_db",
                        },
                    ],
                },
            ], [
                {"name": "road_runner_db", "section": "monitoring"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_identifier_clearing_before_path(self):
        """Entity that would fail path resolution clears via identifier.

        The entity matches the identifier but the path contains a component
        (the full module path) that is not in the entity set — path resolution
        alone would fail.
        """
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "config",
                    "body": "## Config\n\nempty_str_to_none normalizes empty strings.",
                    "ref_entries": [
                        {
                            "display": "[code] config.py:empty_str_to_none",
                            "identifier": "empty_str_to_none",
                            "path": ["src/road_runner/config.py", "empty_str_to_none"],
                        },
                    ],
                },
            ], [
                # Only the function name — not the full module path
                {"name": "empty_str_to_none", "section": "config"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            # Would fail path resolution (src/road_runner/config.py not in entity set)
            # but clears via unique identifier match
            assert uncleared == []
            assert "Cleared: 1" in result.stderr


class TestParenthesisNormalization:
    """Parenthesis stripping: trailing () removed before matching."""

    def test_parenthesized_entity_clears(self):
        """Entity compute_price_cagrs() with ref identifier compute_price_cagrs → clears."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "calculations",
                    "body": "## Calculations\n\ncompute_price_cagrs computes growth rates.",
                    "ref_entries": [
                        {
                            "display": "[code] compute_price_cagrs",
                            "identifier": "compute_price_cagrs",
                            "path": ["compute_price_cagrs"],
                        },
                    ],
                },
            ], [
                {"name": "compute_price_cagrs()", "section": "calculations"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr

    def test_non_parenthesized_unchanged(self):
        """Entity compute_price_cagrs without parens → still clears normally."""
        with tempfile.TemporaryDirectory() as td:
            prose_dir, ef, uf, ff = _setup(td, [
                {
                    "path": "calculations",
                    "body": "## Calculations\n\ncompute_price_cagrs computes growth rates.",
                    "ref_entries": [
                        {
                            "display": "[code] compute_price_cagrs",
                            "identifier": "compute_price_cagrs",
                            "path": ["compute_price_cagrs"],
                        },
                    ],
                },
            ], [
                {"name": "compute_price_cagrs", "section": "calculations"},
            ])

            result = _run(prose_dir, ef, uf, ff)
            assert result.returncode == 0

            with open(uf) as f:
                uncleared = json.load(f)
            assert uncleared == []
            assert "Cleared: 1" in result.stderr
