"""Tests for lib/ref_utils.identifier_for_ref and path_for_ref."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.ref_utils import identifier_for_ref, path_for_ref


# -- code refs ---------------------------------------------------------------

def test_code_plain():
    ref = {"type": "code", "kind": "function", "name": "start_run"}
    assert identifier_for_ref(ref) == "start_run"


def test_code_with_attr():
    ref = {"type": "code", "kind": "class", "name": "Settings", "attr": "timeout"}
    assert identifier_for_ref(ref) == "timeout"


def test_code_with_param():
    ref = {"type": "code", "kind": "function", "name": "start_run", "param": "flow_name"}
    assert identifier_for_ref(ref) == "flow_name"


def test_code_attr_takes_precedence_over_param():
    ref = {"type": "code", "kind": "class", "name": "X", "attr": "a", "param": "p"}
    assert identifier_for_ref(ref) == "a"


def test_code_empty_name():
    ref = {"type": "code", "kind": "function", "name": ""}
    assert identifier_for_ref(ref) is None


def test_code_empty_kind():
    ref = {"type": "code", "kind": "", "name": "foo"}
    assert identifier_for_ref(ref) is None


def test_code_with_module():
    ref = {"type": "code", "kind": "function", "name": "run", "module": "src.pipeline"}
    assert identifier_for_ref(ref) == "run"


# -- db refs -----------------------------------------------------------------

def test_db_full_chain_returns_column():
    ref = {"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"}
    assert identifier_for_ref(ref) == "flow_name"


def test_db_table_level():
    ref = {"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs"}
    assert identifier_for_ref(ref) == "etl_runs"


def test_db_schema_level():
    ref = {"type": "db", "db": "mydb", "schema": "road_runner"}
    assert identifier_for_ref(ref) == "road_runner"


def test_db_db_only():
    ref = {"type": "db", "db": "mydb"}
    assert identifier_for_ref(ref) == "mydb"


def test_db_empty_all():
    ref = {"type": "db"}
    assert identifier_for_ref(ref) is None


# -- simple name-based refs --------------------------------------------------

def test_flow():
    ref = {"type": "flow", "name": "ingest_fmp_data"}
    assert identifier_for_ref(ref) == "ingest_fmp_data"


def test_dep():
    ref = {"type": "dep", "name": "requests"}
    assert identifier_for_ref(ref) == "requests"


def test_ext():
    ref = {"type": "ext", "name": "alembic"}
    assert identifier_for_ref(ref) == "alembic"


def test_literal():
    ref = {"type": "literal", "name": "DRIFT_THRESHOLD"}
    assert identifier_for_ref(ref) == "DRIFT_THRESHOLD"


def test_env():
    ref = {"type": "env", "name": "PREFECT_API_URL"}
    assert identifier_for_ref(ref) == "PREFECT_API_URL"


def test_name_based_empty():
    for ref_type in ("flow", "dep", "ext", "literal", "env"):
        ref = {"type": ref_type, "name": ""}
        assert identifier_for_ref(ref) is None, f"{ref_type} with empty name should be None"


# -- config refs -------------------------------------------------------------

def test_config_with_path():
    ref = {"type": "config", "path": "config/field-mapping.yaml"}
    assert identifier_for_ref(ref) == "field-mapping.yaml"


def test_config_bare_filename():
    ref = {"type": "config", "path": "settings.yaml"}
    assert identifier_for_ref(ref) == "settings.yaml"


def test_config_dotslash():
    ref = {"type": "config", "path": "./settings.yaml"}
    assert identifier_for_ref(ref) == "settings.yaml"


def test_config_empty_path():
    ref = {"type": "config", "path": ""}
    assert identifier_for_ref(ref) is None


# -- enum refs ---------------------------------------------------------------

def test_enum():
    ref = {"type": "enum", "class": "RunStatus", "field": "status", "value": "COMPLETED"}
    assert identifier_for_ref(ref) == "COMPLETED"


def test_enum_empty_value():
    ref = {"type": "enum", "class": "RunStatus", "field": "status", "value": ""}
    assert identifier_for_ref(ref) is None


def test_enum_empty_class():
    ref = {"type": "enum", "class": "", "field": "status", "value": "COMPLETED"}
    assert identifier_for_ref(ref) is None


def test_enum_empty_field():
    ref = {"type": "enum", "class": "RunStatus", "field": "", "value": "COMPLETED"}
    assert identifier_for_ref(ref) is None


# -- malformed refs ----------------------------------------------------------

def test_malformed():
    ref = {"type": "malformed", "original_type": "code", "name": "foo"}
    assert identifier_for_ref(ref) is None


# -- unknown type ------------------------------------------------------------

def test_unknown_type():
    ref = {"type": "unknown", "name": "foo"}
    assert identifier_for_ref(ref) is None


def test_empty_type():
    ref = {"type": "", "name": "foo"}
    assert identifier_for_ref(ref) is None


def test_missing_type():
    ref = {"name": "foo"}
    assert identifier_for_ref(ref) is None


# -- path_for_ref: db refs ---------------------------------------------------

def test_path_db_full_chain():
    ref = {"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"}
    assert path_for_ref(ref) == ("mydb", "road_runner", "etl_runs", "flow_name")


def test_path_db_table_level():
    ref = {"type": "db", "schema": "road_runner", "table": "etl_runs"}
    assert path_for_ref(ref) == ("road_runner", "etl_runs")


def test_path_db_schema_only():
    ref = {"type": "db", "schema": "road_runner"}
    assert path_for_ref(ref) == ("road_runner",)


def test_path_db_empty():
    ref = {"type": "db"}
    assert path_for_ref(ref) == ()


def test_path_db_includes_db_name():
    """db name is included as first component."""
    ref = {"type": "db", "db": "mydb", "schema": "s", "table": "t"}
    assert path_for_ref(ref) == ("mydb", "s", "t")


# -- path_for_ref: code refs -------------------------------------------------

def test_path_code_plain():
    ref = {"type": "code", "kind": "function", "name": "start_run"}
    assert path_for_ref(ref) == ("start_run",)


def test_path_code_with_module():
    ref = {"type": "code", "kind": "function", "name": "run", "module": "src.pipeline"}
    assert path_for_ref(ref) == ("src.pipeline", "run")


def test_path_code_with_attr():
    ref = {"type": "code", "kind": "class", "name": "Settings", "attr": "timeout"}
    assert path_for_ref(ref) == ("Settings", "timeout")


def test_path_code_with_module_and_attr():
    ref = {"type": "code", "kind": "class", "name": "Settings", "module": "src/config.py", "attr": "timeout"}
    assert path_for_ref(ref) == ("src/config.py", "Settings", "timeout")


def test_path_code_with_param():
    ref = {"type": "code", "kind": "function", "name": "start_run", "param": "flow_name"}
    assert path_for_ref(ref) == ("start_run", "flow_name")


def test_path_code_empty_name():
    ref = {"type": "code", "kind": "function", "name": ""}
    assert path_for_ref(ref) == ()


def test_path_code_empty_kind():
    ref = {"type": "code", "kind": "", "name": "foo"}
    assert path_for_ref(ref) == ()


# -- path_for_ref: simple name-based refs ------------------------------------

def test_path_flow():
    ref = {"type": "flow", "name": "ingest_fmp_data"}
    assert path_for_ref(ref) == ("ingest_fmp_data",)


def test_path_dep():
    ref = {"type": "dep", "name": "requests"}
    assert path_for_ref(ref) == ("requests",)


def test_path_ext():
    ref = {"type": "ext", "name": "alembic"}
    assert path_for_ref(ref) == ("alembic",)


def test_path_literal():
    ref = {"type": "literal", "name": "DRIFT_THRESHOLD"}
    assert path_for_ref(ref) == ("DRIFT_THRESHOLD",)


def test_path_env():
    ref = {"type": "env", "name": "PREFECT_API_URL"}
    assert path_for_ref(ref) == ("PREFECT_API_URL",)


def test_path_name_based_empty():
    for ref_type in ("flow", "dep", "ext", "literal", "env"):
        assert path_for_ref({"type": ref_type, "name": ""}) == ()


# -- path_for_ref: config refs -----------------------------------------------

def test_path_config():
    ref = {"type": "config", "path": "config/field-mapping.yaml"}
    assert path_for_ref(ref) == ("config/field-mapping.yaml",)


def test_path_config_empty():
    ref = {"type": "config", "path": ""}
    assert path_for_ref(ref) == ()


# -- path_for_ref: enum refs -------------------------------------------------

def test_path_enum():
    ref = {"type": "enum", "class": "RunStatus", "field": "status", "value": "COMPLETED"}
    assert path_for_ref(ref) == ("RunStatus", "status", "COMPLETED")


def test_path_enum_empty_value():
    ref = {"type": "enum", "class": "RunStatus", "field": "status", "value": ""}
    assert path_for_ref(ref) == ()


# -- path_for_ref: edge cases ------------------------------------------------

def test_path_malformed():
    ref = {"type": "malformed", "original_type": "code", "name": "foo"}
    assert path_for_ref(ref) == ()


def test_path_unknown_type():
    ref = {"type": "unknown", "name": "foo"}
    assert path_for_ref(ref) == ()


def test_path_missing_type():
    ref = {"name": "foo"}
    assert path_for_ref(ref) == ()
