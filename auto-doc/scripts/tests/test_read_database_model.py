"""Tests for read-database-model.py -- slice reader for database model.

Uses subprocess to invoke the script as a CLI tool.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "read-database-model.py",
)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_db_model():
    """Build a realistic database-model.json dict."""
    return {
        "engine": "PostgreSQL",
        "orm_framework": "SQLAlchemy 2.0",
        "migration_tool": "Alembic",
        "extracted_at": "2026-04-03T22:00:00Z",
        "schemas": {
            "road_runner": {
                "tables": {
                    "etl_runs": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "flow_name", "type": "String(100)", "primary_key": False, "nullable": False, "foreign_key": None},
                            {"name": "ticker_id", "type": "Integer", "primary_key": False, "nullable": False, "foreign_key": "road_runner.stocks.id"},
                        ]
                    },
                    "stocks": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "ticker", "type": "String(10)", "primary_key": False, "nullable": False, "foreign_key": None},
                        ]
                    },
                }
            },
            "raw_fmp": {
                "tables": {
                    "raw_income": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "revenue", "type": "Numeric", "primary_key": False, "nullable": True, "foreign_key": None},
                        ]
                    }
                }
            }
        }
    }


def _run(db_model_path, tables):
    """Run read-database-model.py and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH,
         "--db-model", db_model_path,
         "--tables", tables],
        capture_output=True, text=True,
    )
    return result.stdout, result.stderr, result.returncode


class TestFiltering:
    """Filters to requested tables only."""

    def test_single_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, rc = _run(db_path, "stocks")
            assert rc == 0
            assert "road_runner.stocks:" in stdout
            assert "ticker" in stdout
            assert "etl_runs" not in stdout

    def test_multiple_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, rc = _run(db_path, "etl_runs,stocks")
            assert rc == 0
            assert "road_runner.etl_runs:" in stdout
            assert "road_runner.stocks:" in stdout

    def test_tables_across_schemas(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, rc = _run(db_path, "stocks,raw_income")
            assert rc == 0
            assert "road_runner.stocks:" in stdout
            assert "raw_fmp.raw_income:" in stdout


class TestOutputFormat:
    """Compact output format with column annotations."""

    def test_pk_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, _ = _run(db_path, "stocks")
            assert "PK" in stdout

    def test_fk_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, _ = _run(db_path, "etl_runs")
            assert "FK(road_runner.stocks.id)" in stdout

    def test_not_null_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, _ = _run(db_path, "etl_runs")
            assert "NOT NULL" in stdout

    def test_schema_qualified_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, _ = _run(db_path, "raw_income")
            assert "raw_fmp.raw_income:" in stdout


class TestEdgeCases:
    """Missing tables, empty input, bad model."""

    def test_missing_table_warns_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, stderr, rc = _run(db_path, "nonexistent_table")
            assert rc == 0
            assert "nonexistent_table" in stderr
            assert stdout.strip() == ""

    def test_empty_tables_returns_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, _, rc = _run(db_path, "")
            assert rc == 0
            assert stdout.strip() == ""

    def test_mixed_found_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, _make_db_model())
            stdout, stderr, rc = _run(db_path, "stocks,bogus")
            assert rc == 0
            assert "road_runner.stocks:" in stdout
            assert "bogus" in stderr

    def test_no_schemas_in_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db-model.json")
            _write_json(db_path, {"extraction": "skipped", "reason": "no ORM"})
            stdout, stderr, rc = _run(db_path, "stocks")
            assert rc == 0
            assert stdout.strip() == ""
