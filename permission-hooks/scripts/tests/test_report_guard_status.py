"""Tests for report-guard-status.py.

The inline version this replaced reached the guard through
`sys.path.insert(0, target_hooks_dir)` plus `importlib.import_module` on the
hyphenated name `permission-guard`. Two of the tests below pin what that bought:
loading by path takes the file it was given, and does not put the hook's directory
on `sys.path` where a same-named module could win instead.
"""

import os
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
SCRIPT = os.path.join(SCRIPTS_DIR, "report-guard-status.py")
REAL_GUARD = os.path.join(
    os.path.dirname(SCRIPTS_DIR), "hooks", "permission-guard.py"
)

FAKE_GUARD = '''\
PROJECT_ROOT = "{root}"
CATEGORIES = {{
    "Git Branch & History": ["a", "b", "c"],
    "Destructive Filesystem": ["d", "e"],
}}


def main():
    raise SystemExit("main() must not run on import")


if __name__ == "__main__":
    main()
'''


def _run(hook_path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--hook", str(hook_path)],
        capture_output=True,
        text=True,
    )


def _fake(tmp_path, root='{MG_INSTALL_PROJECT_ROOT}', name="permission-guard.py"):
    path = tmp_path / name
    path.write_text(FAKE_GUARD.format(root=root))
    return path


def test_reports_per_category_counts_and_total(tmp_path):
    r = _run(_fake(tmp_path))

    assert r.returncode == 0, r.stderr
    assert "Git Branch & History: 3 rules" in r.stdout
    assert "Destructive Filesystem: 2 rules" in r.stdout
    assert "Total: 5 rules + out-of-project path guard" in r.stdout


def test_unresolved_placeholder_is_called_out(tmp_path):
    r = _run(_fake(tmp_path))

    assert "PROJECT_ROOT: '{MG_INSTALL_PROJECT_ROOT}'" in r.stdout
    assert "unresolved placeholder" in r.stdout


def test_resolved_absolute_path_is_reported_without_the_placeholder_note(tmp_path):
    r = _run(_fake(tmp_path, root="/home/someone/projects/demo"))

    assert "PROJECT_ROOT: '/home/someone/projects/demo'" in r.stdout
    assert "unresolved placeholder" not in r.stdout


def test_empty_project_root_is_treated_as_unresolved(tmp_path):
    r = _run(_fake(tmp_path, root=""))

    assert r.returncode == 0, r.stderr
    assert "unresolved placeholder" in r.stdout


def test_missing_file_is_an_error(tmp_path):
    r = _run(tmp_path / "not-installed.py")

    assert r.returncode == 1
    assert "no such file" in r.stderr


def test_unimportable_hook_is_an_error(tmp_path):
    broken = tmp_path / "permission-guard.py"
    broken.write_text("CATEGORIES = {\n")  # truncated mid-literal

    r = _run(broken)

    assert r.returncode == 1
    assert "could not import" in r.stderr


def test_hook_without_categories_is_an_error(tmp_path):
    wrong = tmp_path / "permission-guard.py"
    wrong.write_text("PROJECT_ROOT = '/x'\n")

    r = _run(wrong)

    assert r.returncode == 1
    assert "CATEGORIES" in r.stderr


def test_loads_the_file_it_was_given_not_one_from_sys_path(tmp_path):
    """A module of the same name elsewhere on sys.path must not win."""
    decoy_dir = tmp_path / "decoy"
    decoy_dir.mkdir()
    (decoy_dir / "mg_permission_guard.py").write_text(
        'PROJECT_ROOT = "/wrong"\nCATEGORIES = {"Decoy": ["x"] * 99}\n'
    )
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = _fake(target_dir)

    r = subprocess.run(
        [sys.executable, SCRIPT, "--hook", str(target)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(decoy_dir)},
    )

    assert r.returncode == 0, r.stderr
    assert "Decoy" not in r.stdout
    assert "Total: 5 rules" in r.stdout


def test_module_body_runs_but_main_does_not(tmp_path):
    """The fake's main() raises; reaching it would fail the import."""
    r = _run(_fake(tmp_path))

    assert r.returncode == 0
    assert "must not run on import" not in r.stderr


def test_works_against_the_real_shipped_guard():
    r = _run(REAL_GUARD)

    assert r.returncode == 0, r.stderr
    assert "Permission Guard -- Rule Categories:" in r.stdout
    assert "out-of-project path guard" in r.stdout
    # The source copy always carries the placeholder; install.sh/post-install
    # decide whether to resolve it per install mode.
    assert "unresolved placeholder" in r.stdout
