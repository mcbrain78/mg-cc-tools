"""Tests for lib/ref_validation.py -- malformed ref detection and discharge."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.ref_validation import discharge_malformed_refs, ref_has_identifier


class TestRefHasIdentifier:
    """ref_has_identifier checks required fields per type."""

    # -- Valid refs (all required fields present) --

    def test_db_valid_full_chain(self):
        assert ref_has_identifier({"type": "db", "db": "mydb", "schema": "rr", "table": "runs"})

    def test_db_valid_with_column(self):
        assert ref_has_identifier({"type": "db", "db": "mydb", "schema": "rr", "table": "runs", "column": "id"})

    def test_db_valid_db_only(self):
        assert ref_has_identifier({"type": "db", "db": "mydb"})

    def test_db_valid_db_and_schema(self):
        assert ref_has_identifier({"type": "db", "db": "mydb", "schema": "rr"})

    def test_code_valid_function(self):
        assert ref_has_identifier({"type": "code", "kind": "function", "name": "foo"})

    def test_code_valid_class(self):
        assert ref_has_identifier({"type": "code", "kind": "class", "name": "Bar"})

    def test_flow_valid(self):
        assert ref_has_identifier({"type": "flow", "name": "ingest-data"})

    def test_env_valid(self):
        assert ref_has_identifier({"type": "env", "name": "DATABASE_URL"})

    def test_config_valid(self):
        assert ref_has_identifier({"type": "config", "path": "config.yaml"})

    def test_enum_valid(self):
        assert ref_has_identifier({"type": "enum", "class": "Status", "field": "state", "value": "ok"})

    def test_dep_valid(self):
        assert ref_has_identifier({"type": "dep", "name": "tenacity"})

    def test_literal_valid(self):
        assert ref_has_identifier({"type": "literal", "name": "fmp-api"})

    def test_ext_valid(self):
        assert ref_has_identifier({"type": "ext", "name": "pg_dump"})

    # -- Invalid refs (missing or empty required fields) --

    def test_db_broken_chain_missing_schema(self):
        """table requires schema — gap in chain is invalid."""
        assert not ref_has_identifier({"type": "db", "db": "mydb", "table": "runs"})

    def test_db_broken_chain_missing_table(self):
        """column requires table — gap in chain is invalid."""
        assert not ref_has_identifier({"type": "db", "db": "mydb", "schema": "rr", "column": "id"})

    def test_db_empty_all(self):
        """No levels present at all — invalid."""
        assert not ref_has_identifier({"type": "db"})

    def test_db_empty_db(self):
        """Empty db field counts as missing."""
        assert not ref_has_identifier({"type": "db", "db": "", "schema": "rr"})

    def test_code_empty_name(self):
        assert not ref_has_identifier({"type": "code", "kind": "function", "name": ""})

    def test_code_empty_kind(self):
        assert not ref_has_identifier({"type": "code", "kind": "", "name": "foo"})

    def test_code_missing_name(self):
        assert not ref_has_identifier({"type": "code", "kind": "class"})

    def test_flow_empty_name(self):
        assert not ref_has_identifier({"type": "flow", "name": ""})

    def test_env_empty_name(self):
        assert not ref_has_identifier({"type": "env", "name": ""})

    def test_config_empty_path(self):
        assert not ref_has_identifier({"type": "config", "path": ""})

    def test_enum_empty_class(self):
        assert not ref_has_identifier({"type": "enum", "class": "", "field": "f", "value": "v"})

    def test_enum_empty_field(self):
        assert not ref_has_identifier({"type": "enum", "class": "C", "field": "", "value": "v"})

    def test_enum_empty_value(self):
        assert not ref_has_identifier({"type": "enum", "class": "C", "field": "f", "value": ""})

    def test_dep_empty_name(self):
        assert not ref_has_identifier({"type": "dep", "name": ""})

    def test_literal_empty_name(self):
        assert not ref_has_identifier({"type": "literal", "name": ""})

    def test_ext_empty_name(self):
        assert not ref_has_identifier({"type": "ext", "name": ""})

    def test_whitespace_only_treated_as_empty(self):
        assert not ref_has_identifier({"type": "dep", "name": "  "})

    # -- Unknown types pass through --

    def test_unknown_type_returns_true(self):
        assert ref_has_identifier({"type": "custom", "foo": "bar"})

    def test_empty_type_returns_true(self):
        assert ref_has_identifier({"type": "", "name": "x"})

    def test_missing_type_returns_true(self):
        assert ref_has_identifier({"name": "x"})


class TestDischargeMalformedRefs:
    """discharge_malformed_refs reclassifies invalid refs."""

    def test_valid_refs_unchanged(self):
        refs = [
            {"type": "dep", "name": "tenacity"},
            {"type": "db", "db": "mydb", "schema": "rr", "table": "runs"},
        ]
        result = discharge_malformed_refs(refs)
        assert result == refs

    def test_empty_dep_discharged(self):
        refs = [{"type": "dep", "name": ""}]
        result = discharge_malformed_refs(refs)
        assert len(result) == 1
        assert result[0]["type"] == "malformed"
        assert result[0]["original_type"] == "dep"
        assert result[0]["name"] == ""

    def test_empty_db_discharged(self):
        refs = [{"type": "db"}]
        result = discharge_malformed_refs(refs)
        assert result[0]["type"] == "malformed"
        assert result[0]["original_type"] == "db"

    def test_mixed_valid_and_invalid(self):
        refs = [
            {"type": "dep", "name": "tenacity"},
            {"type": "dep", "name": ""},
            {"type": "code", "kind": "function", "name": "foo"},
            {"type": "code", "kind": "", "name": ""},
        ]
        result = discharge_malformed_refs(refs)
        assert len(result) == 4
        assert result[0]["type"] == "dep"
        assert result[1]["type"] == "malformed"
        assert result[2]["type"] == "code"
        assert result[3]["type"] == "malformed"

    def test_discharged_ref_preserves_all_fields(self):
        ref = {"type": "db", "db": "mydb", "column": "id", "extra": "stuff"}
        result = discharge_malformed_refs([ref])
        r = result[0]
        assert r["type"] == "malformed"
        assert r["original_type"] == "db"
        assert r["db"] == "mydb"
        assert r["column"] == "id"
        assert r["extra"] == "stuff"

    def test_empty_list(self):
        assert discharge_malformed_refs([]) == []

    def test_unknown_type_not_discharged(self):
        refs = [{"type": "custom", "foo": "bar"}]
        result = discharge_malformed_refs(refs)
        assert result[0]["type"] == "custom"
