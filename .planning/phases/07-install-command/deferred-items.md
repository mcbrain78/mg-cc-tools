# Deferred Items - Phase 07

## Pre-existing Issues (Out of Scope)

### 1. permission-hooks test import failure
- **File:** permission-hooks/hooks/tests/test_permission_guard.py
- **Error:** `ModuleNotFoundError: No module named 'tests.test_permission_guard'` -- namespace collision between multiple `tests/__init__.py` packages
- **Cause:** Uncommitted changes to permission-guard.py and test_permission_guard.py (adding `_is_safe_rm` and `_strip_heredocs`) that pre-date phase 07
- **Workaround:** Run pytest with `--ignore=permission-hooks/hooks/tests/` until the namespace collision is resolved
- **Suggested fix:** Add a conftest.py at project root or use unique package names for test directories
