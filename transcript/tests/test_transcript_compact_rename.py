"""Verify compactor renamed from cc_session_compactor.py to cc_transcript_compactor.py."""
import importlib.machinery
import importlib.util
from pathlib import Path


_TRANSCRIPT_DIR = Path(__file__).parent.parent
_COMPACTOR_PATH = _TRANSCRIPT_DIR / "cc_transcript_compactor.py"


def _load_compactor():
    loader = importlib.machinery.SourceFileLoader("cc_transcript_compactor", str(_COMPACTOR_PATH))
    spec = importlib.util.spec_from_loader("cc_transcript_compactor", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compactor_file_exists():
    assert _COMPACTOR_PATH.exists()


def test_compactor_importable():
    mod = _load_compactor()
    assert mod is not None


def test_compactor_has_expected_functions():
    mod = _load_compactor()
    assert callable(getattr(mod, "slim", None))
    assert callable(getattr(mod, "validate_schema", None))
    assert callable(getattr(mod, "main", None))


def test_old_filename_does_not_exist():
    old = _TRANSCRIPT_DIR / "cc_session_compactor.py"
    assert not old.exists(), f"Old filename still present: {old}"
