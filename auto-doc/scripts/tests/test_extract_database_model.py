"""Tests for extract-database-model.py -- deterministic SQLAlchemy metadata extraction.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).

Each test creates a temp directory with minimal SQLAlchemy model files
and a project-model.json, then runs the script and checks the output.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "extract-database-model.py",
)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))


def _run(project_root, search_paths, pm_path, output_path,
         summary_output=None, usage_output=None):
    """Run extract-database-model.py and return (result_dict, returncode, stderr)."""
    cmd = [
        sys.executable, SCRIPT_PATH,
        "--project-root", project_root,
        "--search-paths", search_paths,
        "--project-model", pm_path,
        "--output", output_path,
    ]
    if summary_output:
        cmd.extend(["--summary-output", summary_output])
    if usage_output:
        cmd.extend(["--usage-output", usage_output])
    result = subprocess.run(cmd, capture_output=True, text=True)
    data: dict = (
        _read_json(output_path) if os.path.isfile(output_path) else {}
    )
    return data, result.returncode, result.stderr


def _make_project_model(orm="SQLAlchemy 2.0", engine="PostgreSQL",
                        migration_tool="Alembic"):
    """Build a minimal project-model.json dict."""
    return {
        "tech_stack": ["python"],
        "entry_points": [],
        "components": [],
        "infrastructure": {"deployment": "pip", "ci": "none", "config_files": []},
        "database": {
            "orm_framework": orm,
            "engine": engine,
            "migration_tool": migration_tool,
        },
    }


class TestSkipCases:
    """Script exits 0 with skip marker when extraction is not applicable."""

    def test_no_database_in_project_model(self):
        """database: null -> exits 0, extraction skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            pm = _make_project_model()
            pm["database"] = None
            _write_json(pm_path, pm)
            output = os.path.join(tmp, "database-model.json")

            data, rc, _ = _run(tmp, "src", pm_path, output)
            assert rc == 0
            assert data["extraction"] == "skipped"

    def test_non_sqlalchemy_orm(self):
        """orm_framework: Django -> exits 0, skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            pm = _make_project_model(orm="Django")
            _write_json(pm_path, pm)
            output = os.path.join(tmp, "database-model.json")

            data, rc, _ = _run(tmp, "src", pm_path, output)
            assert rc == 0
            assert data["extraction"] == "skipped"

    def test_missing_project_model(self):
        """project-model.json not found -> exits 0, skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "nonexistent.json")
            output = os.path.join(tmp, "database-model.json")

            data, rc, _ = _run(tmp, "src", pm_path, output)
            assert rc == 0
            assert data["extraction"] == "skipped"

    def test_no_python_files(self):
        """Empty search paths -> exits 0, skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            # Create empty src dir
            os.makedirs(os.path.join(tmp, "src"))
            output = os.path.join(tmp, "database-model.json")

            data, rc, _ = _run(tmp, "src", pm_path, output)
            assert rc == 0
            assert data["extraction"] == "skipped"


class TestExtraction:
    """Full extraction with real SQLAlchemy model files."""

    def test_extracts_schema_from_table_args(self):
        """Model with __table_args__ = {'schema': 'road_runner'} -> correct schema key."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import String, Integer

                class Base(DeclarativeBase):
                    pass

                class EtlRun(Base):
                    __tablename__ = "etl_runs"
                    __table_args__ = {"schema": "road_runner"}

                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    flow_name: Mapped[str] = mapped_column(String(100), nullable=False)
                    status: Mapped[str] = mapped_column(String(20), nullable=False)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, stderr = _run(tmp, "src", pm_path, output)

            assert rc == 0, f"stderr: {stderr}"
            assert "schemas" in data
            assert "road_runner" in data["schemas"], f"got schemas: {list(data['schemas'].keys())}"
            tables = data["schemas"]["road_runner"]["tables"]
            assert "etl_runs" in tables

    def test_multiple_schemas(self):
        """Models in different schemas -> each in correct bucket."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import String, Integer

                class Base(DeclarativeBase):
                    pass

                class EtlRun(Base):
                    __tablename__ = "etl_runs"
                    __table_args__ = {"schema": "road_runner"}
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)

                class RawIncome(Base):
                    __tablename__ = "raw_income_statements"
                    __table_args__ = {"schema": "raw_fmp"}
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src", pm_path, output)

            assert rc == 0
            assert "road_runner" in data["schemas"]
            assert "raw_fmp" in data["schemas"]
            assert "etl_runs" in data["schemas"]["road_runner"]["tables"]
            assert "raw_income_statements" in data["schemas"]["raw_fmp"]["tables"]

    def test_default_schema(self):
        """Model with no __table_args__ -> appears under 'public'."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class User(Base):
                    __tablename__ = "users"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src", pm_path, output)

            assert rc == 0
            assert "public" in data["schemas"]
            assert "users" in data["schemas"]["public"]["tables"]

    def test_foreign_key_extraction(self):
        """FK column -> foreign_key field has target."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer, ForeignKey

                class Base(DeclarativeBase):
                    pass

                class Parent(Base):
                    __tablename__ = "parents"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)

                class Child(Base):
                    __tablename__ = "children"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    parent_id: Mapped[int] = mapped_column(
                        Integer, ForeignKey("parents.id"), nullable=False
                    )
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src", pm_path, output)

            assert rc == 0
            children = data["schemas"]["public"]["tables"]["children"]
            parent_id_col = next(
                c for c in children["columns"] if c["name"] == "parent_id"
            )
            assert parent_id_col["foreign_key"] == "parents.id"

    def test_columns_complete(self):
        """All column attributes captured: name, type, pk, nullable, fk."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import String, Integer

                class Base(DeclarativeBase):
                    pass

                class Item(Base):
                    __tablename__ = "items"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    name: Mapped[str] = mapped_column(String(200), nullable=False)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src", pm_path, output)

            assert rc == 0
            columns = data["schemas"]["public"]["tables"]["items"]["columns"]
            id_col = next(c for c in columns if c["name"] == "id")
            assert id_col["primary_key"] is True
            assert id_col["nullable"] is False
            assert id_col["foreign_key"] is None
            assert "INTEGER" in id_col["type"].upper()

            name_col = next(c for c in columns if c["name"] == "name")
            assert name_col["primary_key"] is False
            assert name_col["nullable"] is False
            assert name_col["foreign_key"] is None

    def test_import_error_resilience(self):
        """File with bad import -> warning logged, other files still extracted."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            # Good model file
            _write_file(os.path.join(tmp, "src", "good_models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class GoodTable(Base):
                    __tablename__ = "good_table"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            # Bad model file with import error
            _write_file(os.path.join(tmp, "src", "bad_models.py"), """\
                import nonexistent_module_that_does_not_exist
                x = 1
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, stderr = _run(tmp, "src", pm_path, output)

            assert rc == 0
            assert "Warning" in stderr
            assert "public" in data["schemas"]
            assert "good_table" in data["schemas"]["public"]["tables"]

    def test_metadata_fields_from_project_model(self):
        """Top-level metadata fields come from project model."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model(
                orm="SQLAlchemy 2.0", engine="PostgreSQL",
                migration_tool="Alembic",
            ))

            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class Item(Base):
                    __tablename__ = "items"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src", pm_path, output)

            assert rc == 0
            assert data["engine"] == "PostgreSQL"
            assert data["orm_framework"] == "SQLAlchemy 2.0"
            assert data["migration_tool"] == "Alembic"
            assert "extracted_at" in data

    def test_multiple_search_paths(self):
        """Comma-separated search paths all get scanned."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "db", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class TableA(Base):
                    __tablename__ = "table_a"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            _write_file(os.path.join(tmp, "lib", "models.py"), """\
                from src.db.models import Base
                from sqlalchemy.orm import Mapped, mapped_column
                from sqlalchemy import Integer

                class TableB(Base):
                    __tablename__ = "table_b"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            output = os.path.join(tmp, "database-model.json")
            data, rc, _ = _run(tmp, "src/db,lib", pm_path, output)

            assert rc == 0
            tables = data["schemas"]["public"]["tables"]
            assert "table_a" in tables
            assert "table_b" in tables


class TestSummaryOutput:
    """--summary-output flag produces compact summary alongside full model."""

    def test_summary_file_created(self):
        """Summary file is created when --summary-output is provided."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer, String
                class Base(DeclarativeBase):
                    pass
                class Item(Base):
                    __tablename__ = "items"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    name: Mapped[str] = mapped_column(String(50), nullable=False)
            """)
            output = os.path.join(tmp, "database-model.json")
            summary = os.path.join(tmp, "database-model-summary.json")
            data, rc, _ = _run(tmp, "src", pm_path, output, summary_output=summary)
            assert rc == 0
            assert os.path.isfile(summary)

    def test_summary_has_column_counts(self):
        """Summary tables have column count instead of full column list."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer, String
                class Base(DeclarativeBase):
                    pass
                class Item(Base):
                    __tablename__ = "items"
                    __table_args__ = {"schema": "road_runner"}
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    name: Mapped[str] = mapped_column(String(50), nullable=False)
                    desc: Mapped[str] = mapped_column(String(200), nullable=True)
            """)
            output = os.path.join(tmp, "database-model.json")
            summary_path = os.path.join(tmp, "database-model-summary.json")
            _run(tmp, "src", pm_path, output, summary_output=summary_path)
            summary = _read_json(summary_path)
            table = summary["schemas"]["road_runner"]["tables"]["items"]
            assert table["columns"] == 3
            assert isinstance(table["fks"], list)

    def test_summary_has_fk_targets(self):
        """Summary FK list contains target fullnames."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer, ForeignKey
                class Base(DeclarativeBase):
                    pass
                class Parent(Base):
                    __tablename__ = "parents"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                class Child(Base):
                    __tablename__ = "children"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
                    parent_id: Mapped[int] = mapped_column(
                        Integer, ForeignKey("parents.id"), nullable=False
                    )
            """)
            output = os.path.join(tmp, "database-model.json")
            summary_path = os.path.join(tmp, "database-model-summary.json")
            _run(tmp, "src", pm_path, output, summary_output=summary_path)
            summary = _read_json(summary_path)
            child_table = summary["schemas"]["public"]["tables"]["children"]
            assert "parents.id" in child_table["fks"]

    def test_summary_has_same_metadata(self):
        """Summary has same top-level metadata as full model."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer
                class Base(DeclarativeBase):
                    pass
                class Item(Base):
                    __tablename__ = "items"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)
            output = os.path.join(tmp, "database-model.json")
            summary_path = os.path.join(tmp, "database-model-summary.json")
            _run(tmp, "src", pm_path, output, summary_output=summary_path)
            full = _read_json(output)
            summary = _read_json(summary_path)
            assert summary["engine"] == full["engine"]
            assert summary["orm_framework"] == full["orm_framework"]
            assert summary["migration_tool"] == full["migration_tool"]
            assert summary["extracted_at"] == full["extracted_at"]

    def test_no_summary_without_flag(self):
        """Summary file NOT created when --summary-output is omitted."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())
            _write_file(os.path.join(tmp, "src", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer
                class Base(DeclarativeBase):
                    pass
                class Item(Base):
                    __tablename__ = "items"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)
            output = os.path.join(tmp, "database-model.json")
            summary_path = os.path.join(tmp, "database-model-summary.json")
            _run(tmp, "src", pm_path, output)  # no summary_output
            assert not os.path.isfile(summary_path)


class TestUsageIndex:
    """--usage-output flag produces file-level usage index."""

    def _model_and_usage_files(self, tmp):
        """Create model file + usage file, return (pm_path, output, usage_path)."""
        pm_path = os.path.join(tmp, "project-model.json")
        _write_json(pm_path, _make_project_model())

        _write_file(os.path.join(tmp, "src", "db", "models.py"), """\
            from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
            from sqlalchemy import String, Integer

            class Base(DeclarativeBase):
                pass

            class EtlRun(Base):
                __tablename__ = "etl_runs"
                __table_args__ = {"schema": "road_runner"}
                id: Mapped[int] = mapped_column(Integer, primary_key=True)
                flow_name: Mapped[str] = mapped_column(String(100), nullable=False)

            class Stock(Base):
                __tablename__ = "stocks"
                __table_args__ = {"schema": "road_runner"}
                id: Mapped[int] = mapped_column(Integer, primary_key=True)
                ticker: Mapped[str] = mapped_column(String(10), nullable=False)
        """)

        _write_file(os.path.join(tmp, "src", "services", "monitoring.py"), """\
            from src.db.models import EtlRun, Stock

            def check_quarterly_staleness(session):
                runs = session.query(EtlRun).all()
                return runs

            def check_missing_tickers(session):
                stocks = session.query(Stock).all()
                return stocks
        """)

        output = os.path.join(tmp, "database-model.json")
        usage_path = os.path.join(tmp, "db-usage-index.json")
        return pm_path, output, usage_path

    def test_usage_output_created(self):
        """Usage index file is created when --usage-output is provided."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path, output, usage_path = self._model_and_usage_files(tmp)
            _, rc, stderr = _run(tmp, "src/db", pm_path, output,
                                 usage_output=usage_path)
            assert rc == 0, f"stderr: {stderr}"
            assert os.path.isfile(usage_path)

    def test_no_output_without_flag(self):
        """Usage index NOT created when --usage-output is omitted."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path, output, usage_path = self._model_and_usage_files(tmp)
            _run(tmp, "src/db", pm_path, output)
            assert not os.path.isfile(usage_path)

    def test_table_definitions_populated(self):
        """table_definitions maps table_name to schema, model_class, source_file."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path, output, usage_path = self._model_and_usage_files(tmp)
            _run(tmp, "src/db", pm_path, output, usage_output=usage_path)
            usage = _read_json(usage_path)
            defs = usage["table_definitions"]
            assert "etl_runs" in defs
            assert defs["etl_runs"]["schema"] == "road_runner"
            assert defs["etl_runs"]["model_class"] == "EtlRun"
            assert "models.py" in defs["etl_runs"]["source_file"]

    def test_tracks_function_level_references(self):
        """file_usage tracks which functions use which tables."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path, output, usage_path = self._model_and_usage_files(tmp)
            _run(tmp, "src/db", pm_path, output, usage_output=usage_path)
            usage = _read_json(usage_path)
            fu = usage["file_usage"]
            # Find monitoring.py entry
            monitoring_key = [k for k in fu if "monitoring" in k]
            assert len(monitoring_key) == 1, f"Expected monitoring in {list(fu.keys())}"
            monitoring = fu[monitoring_key[0]]
            assert "etl_runs" in monitoring["check_quarterly_staleness"]
            assert "stocks" in monitoring["check_missing_tickers"]

    def test_aliased_imports_tracked(self):
        """Aliased imports (from X import Y as Z) are tracked correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "db", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class EtlRun(Base):
                    __tablename__ = "etl_runs"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            _write_file(os.path.join(tmp, "src", "consumer.py"), """\
                from src.db.models import EtlRun as Run

                def process(session):
                    return session.query(Run).first()
            """)

            output = os.path.join(tmp, "database-model.json")
            usage_path = os.path.join(tmp, "db-usage-index.json")
            _run(tmp, "src/db", pm_path, output, usage_output=usage_path)
            usage = _read_json(usage_path)
            fu = usage["file_usage"]
            consumer_key = [k for k in fu if "consumer" in k]
            assert len(consumer_key) == 1
            assert "etl_runs" in fu[consumer_key[0]]["process"]

    def test_star_imports_skipped(self):
        """Star imports do not produce usage entries."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path = os.path.join(tmp, "project-model.json")
            _write_json(pm_path, _make_project_model())

            _write_file(os.path.join(tmp, "src", "db", "models.py"), """\
                from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
                from sqlalchemy import Integer

                class Base(DeclarativeBase):
                    pass

                class EtlRun(Base):
                    __tablename__ = "etl_runs"
                    id: Mapped[int] = mapped_column(Integer, primary_key=True)
            """)

            _write_file(os.path.join(tmp, "src", "star_user.py"), """\
                from src.db.models import *

                def do_something():
                    return 42
            """)

            output = os.path.join(tmp, "database-model.json")
            usage_path = os.path.join(tmp, "db-usage-index.json")
            _run(tmp, "src/db", pm_path, output, usage_output=usage_path)
            usage = _read_json(usage_path)
            fu = usage["file_usage"]
            star_keys = [k for k in fu if "star_user" in k]
            assert len(star_keys) == 0

    def test_parse_errors_handled_gracefully(self):
        """Files with syntax errors are skipped without crashing."""
        with tempfile.TemporaryDirectory() as tmp:
            pm_path, output, usage_path = self._model_and_usage_files(tmp)

            # Add a file with a syntax error
            _write_file(os.path.join(tmp, "src", "bad_syntax.py"),
                        "def broken(\n")

            _, rc, stderr = _run(tmp, "src/db", pm_path, output,
                                 usage_output=usage_path)
            assert rc == 0
            assert os.path.isfile(usage_path)
            # Good files should still be tracked
            usage = _read_json(usage_path)
            assert len(usage["table_definitions"]) > 0
