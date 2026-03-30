"""Tests for lib/symbols.py extended functions -- SQLAlchemy, class attrs, enums, decorators."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.symbols import (
    extract_class_attributes,
    extract_decorated_functions,
    extract_enum_values,
    extract_sqlalchemy_models,
)


class TestExtractSqlalchemyModels:
    """extract_sqlalchemy_models() finds tables, schemas, and columns."""

    def test_basic_model(self):
        source = (
            "from sqlalchemy import Column, Integer, String\n"
            "from sqlalchemy.orm import DeclarativeBase\n\n"
            "class Base(DeclarativeBase): pass\n\n"
            "class EtlRun(Base):\n"
            "    __tablename__ = 'etl_runs'\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    flow_name = Column(String)\n"
            "    status = Column(String)\n"
        )
        models = extract_sqlalchemy_models(source)
        assert "etl_runs" in models
        m = models["etl_runs"]
        assert m["class_name"] == "EtlRun"
        assert "id" in m["columns"]
        assert "flow_name" in m["columns"]
        assert "status" in m["columns"]

    def test_schema_from_table_args_dict(self):
        source = (
            "class Run(Base):\n"
            "    __tablename__ = 'runs'\n"
            "    __table_args__ = {'schema': 'road_runner'}\n"
            "    id = Column(Integer)\n"
        )
        models = extract_sqlalchemy_models(source)
        assert models["runs"]["schema"] == "road_runner"

    def test_schema_from_table_args_tuple(self):
        source = (
            "class Run(Base):\n"
            "    __tablename__ = 'runs'\n"
            "    __table_args__ = (\n"
            "        UniqueConstraint('name'),\n"
            "        {'schema': 'analytics'},\n"
            "    )\n"
            "    id = Column(Integer)\n"
        )
        models = extract_sqlalchemy_models(source)
        assert models["runs"]["schema"] == "analytics"

    def test_mapped_column(self):
        source = (
            "from sqlalchemy.orm import Mapped, mapped_column\n\n"
            "class User(Base):\n"
            "    __tablename__ = 'users'\n"
            "    id: Mapped[int] = mapped_column(primary_key=True)\n"
            "    name: Mapped[str] = mapped_column(String(100))\n"
        )
        models = extract_sqlalchemy_models(source)
        assert "users" in models
        assert "id" in models["users"]["columns"]
        assert "name" in models["users"]["columns"]

    def test_no_tablename_skipped(self):
        source = (
            "class NotAModel:\n"
            "    name = Column(String)\n"
        )
        models = extract_sqlalchemy_models(source)
        assert models == {}

    def test_multiple_models(self):
        source = (
            "class Alpha(Base):\n"
            "    __tablename__ = 'alphas'\n"
            "    id = Column(Integer)\n\n"
            "class Beta(Base):\n"
            "    __tablename__ = 'betas'\n"
            "    id = Column(Integer)\n"
        )
        models = extract_sqlalchemy_models(source)
        assert "alphas" in models
        assert "betas" in models

    def test_syntax_error_returns_empty(self):
        assert extract_sqlalchemy_models("class Broken(:\n") == {}


class TestExtractClassAttributes:
    """extract_class_attributes() finds class-level assignments."""

    def test_basic_class(self):
        source = (
            "class Config:\n"
            "    debug = True\n"
            "    port = 8080\n"
            "    name: str = 'app'\n"
        )
        attrs = extract_class_attributes(source, "Config")
        assert attrs == {"debug", "port", "name"}

    def test_annotated_only(self):
        source = (
            "class Model:\n"
            "    field: int\n"
            "    other: str\n"
        )
        attrs = extract_class_attributes(source, "Model")
        assert attrs == {"field", "other"}

    def test_wrong_class_name(self):
        source = "class Foo:\n    x = 1\n"
        attrs = extract_class_attributes(source, "Bar")
        assert attrs == set()

    def test_class_not_found(self):
        source = "x = 1\n"
        attrs = extract_class_attributes(source, "Missing")
        assert attrs == set()

    def test_syntax_error(self):
        assert extract_class_attributes("class Bad(:", "Bad") == set()


class TestExtractEnumValues:
    """extract_enum_values() finds enum member names and values."""

    def test_string_enum(self):
        source = (
            "from enum import Enum\n\n"
            "class Status(str, Enum):\n"
            "    completed = 'completed'\n"
            "    failed = 'failed'\n"
            "    running = 'running'\n"
        )
        members = extract_enum_values(source, "Status")
        assert members == {
            "completed": "completed",
            "failed": "failed",
            "running": "running",
        }

    def test_int_enum(self):
        source = (
            "from enum import IntEnum\n\n"
            "class Priority(IntEnum):\n"
            "    LOW = 1\n"
            "    HIGH = 2\n"
        )
        members = extract_enum_values(source, "Priority")
        assert members == {"LOW": "1", "HIGH": "2"}

    def test_auto_enum(self):
        source = (
            "from enum import Enum, auto\n\n"
            "class Color(Enum):\n"
            "    RED = auto()\n"
            "    GREEN = auto()\n"
        )
        members = extract_enum_values(source, "Color")
        assert members == {"RED": "RED", "GREEN": "GREEN"}

    def test_wrong_class(self):
        source = "class Foo(Enum):\n    A = 1\n"
        assert extract_enum_values(source, "Bar") == {}

    def test_syntax_error(self):
        assert extract_enum_values("class Broken(:", "Broken") == {}


class TestExtractDecoratedFunctions:
    """extract_decorated_functions() finds @decorator-marked functions."""

    def test_simple_decorator(self):
        source = (
            "from prefect import flow\n\n"
            "@flow\n"
            "def ingest_data():\n"
            "    pass\n\n"
            "@flow\n"
            "def compute_metrics():\n"
            "    pass\n\n"
            "def helper():\n"
            "    pass\n"
        )
        flows = extract_decorated_functions(source, "flow")
        assert flows == ["ingest_data", "compute_metrics"]

    def test_decorator_with_args(self):
        source = (
            '@flow(name="my-flow")\n'
            "def my_flow():\n"
            "    pass\n"
        )
        flows = extract_decorated_functions(source, "flow")
        assert flows == ["my_flow"]

    def test_async_function(self):
        source = (
            "@flow\n"
            "async def async_ingest():\n"
            "    pass\n"
        )
        flows = extract_decorated_functions(source, "flow")
        assert flows == ["async_ingest"]

    def test_attribute_decorator(self):
        source = (
            "@app.route('/api')\n"
            "def api_handler():\n"
            "    pass\n"
        )
        routes = extract_decorated_functions(source, "route")
        assert routes == ["api_handler"]

    def test_no_matching_decorator(self):
        source = (
            "@task\n"
            "def my_task():\n"
            "    pass\n"
        )
        flows = extract_decorated_functions(source, "flow")
        assert flows == []

    def test_syntax_error(self):
        assert extract_decorated_functions("def broken(:", "flow") == []
