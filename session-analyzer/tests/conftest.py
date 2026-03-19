"""Test infrastructure for session-analyzer tests.

Provides:
- --slow CLI flag for large-sample tests
- Sample file path fixtures (skip if missing)
- Sample data fixtures (loaded JSON with chunks dropped)
- Import helpers using importlib.machinery.SourceFileLoader (project convention)

Import helpers are available both as module-level functions (load_analyzer,
load_compactor) and as pytest fixtures (analyzer_mod, compactor_mod).
Tests in this directory can use sys.path to import conftest directly:

    import sys; sys.path.insert(0, str(Path(__file__).parent))
    from conftest import load_analyzer

Or preferably use the analyzer_mod / compactor_mod fixtures.
"""
import json
import sys
from pathlib import Path

import pytest

# Make conftest importable from test files in this directory
sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--slow", action="store_true", default=False,
        help="Run tests marked @pytest.mark.slow (require large sample files)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip_slow = pytest.mark.skip(reason="need --slow flag to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_SAMPLES_DIR = Path(__file__).parent.parent / "samples"
_ANALYZER_PATH = Path(__file__).parent.parent / "cc_session_analyzer.py"
_COMPACTOR_PATH = Path(__file__).parent.parent / "cc_session_compactor.py"


# ---------------------------------------------------------------------------
# Import helpers (importlib.machinery.SourceFileLoader -- Phase 1 convention)
# ---------------------------------------------------------------------------

def load_analyzer():
    """Import cc_session_analyzer.py as a module."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("cc_session_analyzer", str(_ANALYZER_PATH))
    spec = importlib.util.spec_from_loader("cc_session_analyzer", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_compactor():
    """Import cc_session_compactor.py as a module."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("cc_session_compactor", str(_COMPACTOR_PATH))
    spec = importlib.util.spec_from_loader("cc_session_compactor", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures -- sample paths
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_1mb_path():
    p = _SAMPLES_DIR / "sample-1mb-no-agents.json"
    if not p.exists():
        pytest.skip(f"Sample file not found: {p}")
    return p


@pytest.fixture
def sample_75mb_path():
    p = _SAMPLES_DIR / "sample-75mb-216-agents.json"
    if not p.exists():
        pytest.skip(f"Sample file not found: {p}")
    return p


# ---------------------------------------------------------------------------
# Fixtures -- loaded data (chunks dropped)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_1mb_data(sample_1mb_path):
    with open(sample_1mb_path) as f:
        data = json.load(f)
    data.pop("chunks", None)
    return data


@pytest.fixture
def sample_75mb_data(sample_75mb_path):
    """Load 75MB sample. Tests using this should be marked @pytest.mark.slow."""
    with open(sample_75mb_path) as f:
        data = json.load(f)
    data.pop("chunks", None)
    return data


# ---------------------------------------------------------------------------
# Fixtures -- script paths
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer_path():
    return _ANALYZER_PATH


@pytest.fixture
def compactor_path():
    return _COMPACTOR_PATH
