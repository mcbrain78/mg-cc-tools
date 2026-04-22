"""Tests for dismiss-entity.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "dismiss-entity.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(entity, section, uncleared_file, dismissed_this_run_file,
         audience="devops", document="OPERATIONS",
         protected_entities_file=None, covered_by=None,
         prose_verify_dir=None, covered_entities_file=None):
    cmd = [
        sys.executable, SCRIPT,
        "--entity", entity,
        "--section", section,
        "--uncleared-file", uncleared_file,
        "--dismissed-this-run-file", dismissed_this_run_file,
        "--audience", audience,
        "--document", document,
    ]
    if protected_entities_file:
        cmd.extend(["--protected-entities-file", protected_entities_file])
    if covered_by:
        cmd.extend(["--covered-by", covered_by])
    if prose_verify_dir:
        cmd.extend(["--prose-verify-dir", prose_verify_dir])
    if covered_entities_file:
        cmd.extend(["--covered-entities-file", covered_entities_file])
    return subprocess.run(cmd, capture_output=True, text=True)


class TestDismiss:
    """Entity removal from uncleared and addition to dismissed-this-run."""

    def test_entity_removed_from_all_sections(self):
        """Entity in multiple sections → all removed from uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "bash", "section": "orchestration"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_entity_added_to_dismissed_this_run(self):
        """Dismissed entity appended to dismissed-this-run list."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"
            assert dismissed[0]["sections"] == ["monitoring"]
            assert dismissed[0]["audience"] == "devops"
            assert dismissed[0]["document"] == "OPERATIONS"

    def test_dismiss_captures_all_sections(self):
        """Entity uncleared in multiple sections → sections list contains all."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "bash", "section": "orchestration"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"
            # sorted set of sections where the entity was uncleared
            assert dismissed[0]["sections"] == [
                "deployment", "monitoring", "orchestration"
            ]

    def test_dismiss_single_section_one_element_list(self):
        """Entity uncleared in one section → sections is a one-element list."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert dismissed[0]["sections"] == ["monitoring"]

    def test_dedup_dismissed_this_run(self):
        """Dismissing same entity twice does not duplicate in dismissed-this-run."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [
                {"name": "bash", "sections": ["deployment"],
                 "audience": "devops", "document": "OPERATIONS"},
            ])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["sections"] == ["deployment"]  # original preserved

    def test_entity_not_in_uncleared(self):
        """Entity not in uncleared → no-op on uncleared, still added to dismissed."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("nonexistent", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "nonexistent"

    def test_empty_uncleared(self):
        """Empty uncleared file → no-op on uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_missing_dismissed_file(self):
        """Non-existent dismissed file → created with the entity."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = os.path.join(td, "dismissed-this-run.json")

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"

    def test_missing_uncleared_file(self):
        """Non-existent uncleared file → defaults to empty, created."""
        with tempfile.TemporaryDirectory() as td:
            uf = os.path.join(td, "uncleared.json")
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_summary_on_stderr(self):
        """Summary line printed to stderr."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert "Dismissed: bash" in result.stderr
            assert "3 → 1" in result.stderr


class TestProtected:
    """Protected entity handling."""

    def test_protected_entity_refused(self):
        """Protected entity stays in uncleared, not written to dismissed."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "compute_hash", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            pf = _write_json(td, "protected-entities.json", [
                {"name": "compute_hash", "reason": "Project function"},
            ])

            result = _run(
                "compute_hash", "monitoring", uf, df,
                protected_entities_file=pf,
            )
            assert result.returncode == 0
            assert "PROTECTED: compute_hash" in result.stderr

            # Uncleared unchanged
            uncleared = _read_json(uf)
            assert len(uncleared) == 2

            # Not written to dismissed
            dismissed = _read_json(df)
            assert len(dismissed) == 0

    def test_no_protected_file_means_no_check(self):
        """Omitting --protected-entities-file → dismiss proceeds normally."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0
            assert "PROTECTED" not in result.stderr
            assert "Dismissed: bash" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 0

            dismissed = _read_json(df)
            assert len(dismissed) == 1


class TestPatternBlocked:
    """Pattern guard blocks dismissal of structurally ref-like entities."""

    def test_file_path_blocked(self):
        """Entity with / is blocked as file path, stays in uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "src/road_runner/flows/ingestion.py", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("src/road_runner/flows/ingestion.py", "monitoring", uf, df)
            assert result.returncode == 0
            assert "Cannot dismiss" in result.stderr
            assert "file path" in result.stderr

            # Entity stays in uncleared
            uncleared = _read_json(uf)
            assert len(uncleared) == 2

            # Not added to dismissed
            dismissed = _read_json(df)
            assert len(dismissed) == 0

    def test_file_extension_blocked(self):
        """Entity ending with .py is blocked as file reference."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "config.py", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("config.py", "monitoring", uf, df)
            assert result.returncode == 0
            assert "Cannot dismiss" in result.stderr
            assert "file reference (.py)" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_schema_qualified_blocked(self):
        """Schema-qualified name like raw_fmp.income_statements is blocked."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "raw_fmp.income_statements", "section": "data"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("raw_fmp.income_statements", "data", uf, df)
            assert result.returncode == 0
            assert "Cannot dismiss" in result.stderr
            assert "schema-qualified name" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_generic_tool_not_blocked(self):
        """Generic tool name like bash passes through pattern guard."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0
            assert "Cannot dismiss" not in result.stderr
            assert "Dismissed: bash" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 0

    def test_short_dotted_not_blocked(self):
        """Short dotted names like os.path pass through (segments < 3 chars)."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "os.path", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("os.path", "monitoring", uf, df)
            assert result.returncode == 0
            assert "Cannot dismiss" not in result.stderr
            assert "Dismissed: os.path" in result.stderr

    def test_pattern_blocked_stderr_message(self):
        """Pattern blocked message includes entity name and 'File a finding instead'."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "public.stocks", "section": "data"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("public.stocks", "data", uf, df)
            assert "Cannot dismiss public.stocks" in result.stderr
            assert "File a finding instead" in result.stderr


def _make_section_json(td, section_path, ref_identifiers):
    """Create a section JSON file with ref_entries under prose-verify dir."""
    prose_dir = os.path.join(td, "prose-verify")
    slug = os.path.basename(section_path)
    parent = os.path.dirname(section_path)
    if parent:
        section_file = os.path.join(prose_dir, parent, f"{slug}.json")
    else:
        section_file = os.path.join(prose_dir, f"{slug}.json")
    os.makedirs(os.path.dirname(section_file), exist_ok=True)
    data = {
        "body": "some body text",
        "refs_as_text": "some refs",
        "ref_entries": [
            {"identifier": ident, "display": ident}
            for ident in ref_identifiers
        ],
    }
    with open(section_file, "w") as f:
        json.dump(data, f)
    return prose_dir


class TestCoveredBy:
    """--covered-by routes to covered-entities regardless of protection state."""

    def test_covered_by_bypasses_protected(self):
        """Valid covered-by + protected entity → removed from uncleared,
        recorded in covered-entities, NOT in dismissed-this-run."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            cf = os.path.join(td, "covered-entities.json")
            pf = _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            prose_dir = _make_section_json(
                td, "monitoring", ["ResolutionAction", "PORT"],
            )

            result = _run(
                "accept_new", "monitoring", uf, df,
                protected_entities_file=pf,
                covered_by="ResolutionAction",
                prose_verify_dir=prose_dir,
                covered_entities_file=cf,
            )
            assert result.returncode == 0
            assert "Covered: accept_new (by ResolutionAction)" in result.stderr

            # Removed from uncleared
            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            # NOT in dismissed-this-run
            dismissed = _read_json(df)
            assert len(dismissed) == 0

            # Recorded in covered-entities with full scope
            covered = _read_json(cf)
            assert len(covered) == 1
            assert covered[0]["name"] == "accept_new"
            assert covered[0]["section"] == "monitoring"
            assert covered[0]["document"] == "OPERATIONS"
            assert covered[0]["audience"] == "devops"
            assert covered[0]["covered_by"] == "ResolutionAction"

    def test_covered_by_non_protected_routes_to_coverage(self):
        """Non-protected entity + valid covered-by → covered-entities,
        NOT dismissed-this-run. This is the durability fix: coverage assertion
        is honored regardless of whether the entity has been classified
        protected yet."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "@flow", "section": "technical-terms"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            cf = os.path.join(td, "covered-entities.json")
            pf = _write_json(td, "protected-entities.json", [])
            prose_dir = _make_section_json(
                td, "technical-terms", ["prefect"],
            )

            result = _run(
                "@flow", "technical-terms", uf, df,
                protected_entities_file=pf,
                covered_by="prefect",
                prose_verify_dir=prose_dir,
                covered_entities_file=cf,
            )
            assert result.returncode == 0
            assert "Covered: @flow (by prefect)" in result.stderr

            # Removed from uncleared
            uncleared = _read_json(uf)
            assert len(uncleared) == 0

            # NOT in dismissed-this-run
            dismissed = _read_json(df)
            assert len(dismissed) == 0

            # Recorded in covered-entities
            covered = _read_json(cf)
            assert len(covered) == 1
            assert covered[0]["name"] == "@flow"
            assert covered[0]["covered_by"] == "prefect"

    def test_covered_by_invalid_identifier_refused(self):
        """Invalid identifier → refused, uncleared unchanged. Applies
        regardless of protection state."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            pf = _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            prose_dir = _make_section_json(
                td, "monitoring", ["SomeOtherRef"],
            )

            result = _run(
                "accept_new", "monitoring", uf, df,
                protected_entities_file=pf,
                covered_by="ResolutionAction",
                prose_verify_dir=prose_dir,
            )
            assert result.returncode == 0
            assert "Cannot dismiss accept_new" in result.stderr
            assert "--covered-by failed" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_covered_by_missing_section_json_refused(self):
        """Section file doesn't exist → refused."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "nonexistent"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            pf = _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            prose_dir = os.path.join(td, "prose-verify")
            os.makedirs(prose_dir, exist_ok=True)

            result = _run(
                "accept_new", "nonexistent", uf, df,
                protected_entities_file=pf,
                covered_by="ResolutionAction",
                prose_verify_dir=prose_dir,
            )
            assert result.returncode == 0
            assert "Cannot dismiss accept_new" in result.stderr
            assert "--covered-by failed" in result.stderr
            assert "section JSON not found" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_covered_by_dedup(self):
        """Same (name, section, doc, aud) covered twice → one entry."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            cf = _write_json(td, "covered-entities.json", [
                {"name": "accept_new", "section": "monitoring",
                 "audience": "devops", "document": "OPERATIONS",
                 "covered_by": "ResolutionAction"},
            ])
            pf = _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            prose_dir = _make_section_json(
                td, "monitoring", ["ResolutionAction"],
            )

            result = _run(
                "accept_new", "monitoring", uf, df,
                protected_entities_file=pf,
                covered_by="ResolutionAction",
                prose_verify_dir=prose_dir,
                covered_entities_file=cf,
            )
            assert result.returncode == 0

            covered = _read_json(cf)
            assert len(covered) == 1


def _make_section_json_with_paths(td, section_path, ref_entries):
    """Create a section JSON with full ref_entries including path arrays.

    Each entry in ``ref_entries`` should be a dict with at least an
    ``identifier`` and a ``path`` list.
    """
    prose_dir = os.path.join(td, "prose-verify")
    slug = os.path.basename(section_path)
    parent = os.path.dirname(section_path)
    if parent:
        section_file = os.path.join(prose_dir, parent, f"{slug}.json")
    else:
        section_file = os.path.join(prose_dir, f"{slug}.json")
    os.makedirs(os.path.dirname(section_file), exist_ok=True)
    data = {
        "body": "some body text",
        "refs_as_text": "some refs",
        "ref_entries": ref_entries,
    }
    with open(section_file, "w") as f:
        json.dump(data, f)
    return prose_dir


class TestSchemaQualifiedContextAware:
    """Schema-qualified pattern block is context-aware when prose-verify-dir is passed."""

    def test_dismiss_stdlib_dotted_name_allowed(self):
        """json.loads with no matching ref path → dismissal allowed.

        Without a declared ref whose path ends in (json, loads), the pattern
        block falls through and the agent can classify the entity as
        not-entity (the stdlib case).
        """
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "json.loads", "section": "technical-terms"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            prose_dir = _make_section_json_with_paths(
                td, "technical-terms",
                [
                    {
                        "display": "[dep] prefect",
                        "identifier": "prefect",
                        "path": ["prefect"],
                    },
                ],
            )

            result = _run(
                "json.loads", "technical-terms", uf, df,
                prose_verify_dir=prose_dir,
            )
            assert result.returncode == 0
            assert "Cannot dismiss" not in result.stderr
            assert "Dismissed: json.loads" in result.stderr

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_dismiss_schema_qualified_with_matching_ref_blocked(self):
        """finance_metrics.finance_metrics with matching path → block (file finding instead)."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "finance_metrics.finance_metrics", "section": "domain-terms"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            prose_dir = _make_section_json_with_paths(
                td, "domain-terms",
                [
                    {
                        "display": "[db] finance_metrics.finance_metrics",
                        "identifier": "finance_metrics",
                        "path": ["finance", "finance_metrics", "finance_metrics"],
                    },
                ],
            )

            result = _run(
                "finance_metrics.finance_metrics", "domain-terms", uf, df,
                prose_verify_dir=prose_dir,
            )
            assert result.returncode == 0
            assert "Cannot dismiss" in result.stderr
            assert "schema-qualified name matching declared ref" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_dismiss_schema_qualified_without_matching_ref_allowed(self):
        """public.stocks with only unrelated refs → dismissal allowed.

        Section declares an unrelated db ref for (finance, raw_fmp, income_statements).
        Entity public.stocks does not tail-match that path, so the pattern
        block does not apply.
        """
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "public.stocks", "section": "data-sources"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            prose_dir = _make_section_json_with_paths(
                td, "data-sources",
                [
                    {
                        "display": "[db] finance.raw_fmp.income_statements",
                        "identifier": "income_statements",
                        "path": ["finance", "raw_fmp", "income_statements"],
                    },
                ],
            )

            result = _run(
                "public.stocks", "data-sources", uf, df,
                prose_verify_dir=prose_dir,
            )
            assert result.returncode == 0
            assert "Cannot dismiss" not in result.stderr
            assert "Dismissed: public.stocks" in result.stderr

            uncleared = _read_json(uf)
            assert uncleared == []
