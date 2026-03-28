"""Tests for verify-references.py -- deterministic reference integrity checker.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "verify-references.py",
)


def _make_manifest(audience, documents):
    """Build a manifest dict with the given audience and documents."""
    return {"audience": audience, "documents": documents}


def _write_scan(path, source_material_index=None):
    """Write a minimal scan JSON file with a source_material_index."""
    data = {"source_material_index": source_material_index or {}}
    with open(path, "w") as f:
        json.dump(data, f)


def _run(manifests_dir, project_root, findings_file, scan_file):
    """Run verify-references.py and return the subprocess result."""
    return subprocess.run(
        [sys.executable, SCRIPT_PATH,
         "--manifests-dir", manifests_dir,
         "--project-root", project_root,
         "--scan-file", scan_file,
         "--findings-file", findings_file],
        capture_output=True, text=True,
    )


def _load(path):
    """Load JSON from path."""
    with open(path) as f:
        return json.load(f)


class TestVerifyReferencesHappyPath:
    """Valid references produce no findings."""

    def test_existing_file_with_defined_symbol(self):
        """Valid file + defined symbol → 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Create a Python file with a defined symbol
            src_dir = os.path.join(project, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "models.py"), "w") as f:
                f.write("class User:\n    pass\n\ndef get_user():\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["User", "get_user"],
                        "file_paths": ["src/models.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "developers.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/models.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_directory_reference(self):
        """Empty directory → no .py files, symbol check skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Create a directory referenced in the manifest
            os.makedirs(os.path.join(project, "src", "utils"))

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["something"],
                        "file_paths": ["src/utils"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/utils"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            # Dir exists → no missing-file finding; symbol check skipped for dirs
            data = _load(findings)
            assert len(data) == 0

    def test_directory_with_py_files_resolves_symbols(self):
        """Dir has .py files defining symbols → 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Create a directory with .py files defining symbols
            pkg = os.path.join(project, "src", "models")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "user.py"), "w") as f:
                f.write("class User:\n    pass\n")
            with open(os.path.join(pkg, "config.py"), "w") as f:
                f.write("class Settings:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["User", "Settings"],
                        "file_paths": ["src/models"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/models"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_nested_directory_symbol_found(self):
        """Symbol in src/db/sub/deep.py, dir is src/db → 0 findings via recursion."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Create nested directory structure
            deep = os.path.join(project, "src", "db", "sub")
            os.makedirs(deep)
            with open(os.path.join(deep, "deep.py"), "w") as f:
                f.write("class DeepModel:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "data": {
                        "symbols": ["DeepModel"],
                        "file_paths": ["src/db"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/data": {"source_files": ["src/db"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_directory_mixed_with_file_paths(self):
        """Entry has file + dir in file_paths, symbols split across both → 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Symbol A in a standalone file
            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "main.py"), "w") as f:
                f.write("def run_app():\n    pass\n")

            # Symbol B in a directory's .py file
            pkg = os.path.join(project, "src", "core")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "engine.py"), "w") as f:
                f.write("class Engine:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["run_app", "Engine"],
                        "file_paths": ["src/main.py", "src/core"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/main.py", "src/core"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_symbol_found_in_any_file(self):
        """Symbol in file B but not file A → valid (checked across all entry files)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            # File A: no matching symbol
            with open(os.path.join(src, "a.py"), "w") as f:
                f.write("x = 1\n")
            # File B: has the symbol
            with open(os.path.join(src, "b.py"), "w") as f:
                f.write("class Config:\n    pass\n")

            manifest = _make_manifest("developers", {
                "SETUP": {
                    "config": {
                        "symbols": ["Config"],
                        "file_paths": ["src/a.py", "src/b.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "SETUP/config": {"source_files": ["src/a.py", "src/b.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_scan_source_resolves_symbols(self):
        """Manifest file_paths has infra files (no Python symbols), scan source_files
        has Python source defining the symbols → 0 high findings.

        This is the exact bug scenario: infrastructure docs reference infra files
        but symbols come from Python source modules recorded in the scan.
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Infra files (manifest file_paths) — no Python symbols
            deploy = os.path.join(project, "deploy")
            os.makedirs(deploy)
            with open(os.path.join(deploy, "prefect.yaml"), "w") as f:
                f.write("name: pipeline\n")
            with open(os.path.join(deploy, "service.conf"), "w") as f:
                f.write("[Unit]\nDescription=app\n")

            # Python source (scan source_files) — where symbols are defined
            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "models.py"), "w") as f:
                f.write("class RoadRunnerBase:\n    pass\n")
            with open(os.path.join(src, "client.py"), "w") as f:
                f.write("class FMPClient:\n    pass\n")

            manifest = _make_manifest("devops", {
                "OPERATIONS": {
                    "infrastructure-overview": {
                        "symbols": ["RoadRunnerBase", "FMPClient"],
                        "file_paths": ["deploy/prefect.yaml", "deploy/service.conf"],
                    }
                }
            })
            with open(os.path.join(manifests, "devops.json"), "w") as f:
                json.dump(manifest, f)

            # Scan points to the actual Python sources
            _write_scan(scan, {
                "OPERATIONS/infrastructure-overview": {
                    "source_files": ["src/models.py", "src/client.py"],
                },
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_scan_key_missing_uses_manifest_fallback(self):
        """Manifest has entry with symbols but scan has no matching key →
        symbol resolved via manifest file_paths fallback, 0 high findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "api.py"), "w") as f:
                f.write("def handler():\n    pass\n")

            manifest = _make_manifest("developers", {
                "API_REF": {
                    "endpoints": {
                        "symbols": ["handler"],
                        "file_paths": ["src/api.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            # Scan has NO key for API_REF/endpoints
            _write_scan(scan, {})

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_symbol_found_via_manifest_fallback(self):
        """Symbol in manifest file_paths but not scan source_files → 0 findings.

        Scan source_files point to files that DON'T define the symbol,
        but manifest file_paths point to the file that DOES. The merged
        check_paths resolves the symbol via the manifest fallback.
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            # Scan source file — defines OtherClass, NOT TargetClass
            with open(os.path.join(src, "other.py"), "w") as f:
                f.write("class OtherClass:\n    pass\n")
            # Manifest file_path — defines TargetClass
            with open(os.path.join(src, "target.py"), "w") as f:
                f.write("class TargetClass:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["TargetClass"],
                        "file_paths": ["src/target.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            # Scan points to different file that does NOT define TargetClass
            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/other.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0


class TestVerifyReferencesFindings:
    """Invalid references produce correct findings."""

    def test_missing_file(self):
        """Missing file → high finding with path and context in description."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            manifest = _make_manifest("devops", {
                "OPERATIONS": {
                    "deploy": {
                        "symbols": [],
                        "file_paths": ["scripts/old-deploy.sh"],
                    }
                }
            })
            with open(os.path.join(manifests, "devops.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan)

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 1
            f = data[0]
            assert f["check"] == "reference-integrity"
            assert "scripts/old-deploy.sh" in f["description"]
            assert "1 missing file" in f["description"]

    def test_undefined_symbol(self):
        """Symbol not in any referenced file → high finding with symbol name."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "api.py"), "w") as f:
                f.write("def existing_func():\n    pass\n")

            manifest = _make_manifest("developers", {
                "API_REF": {
                    "endpoints": {
                        "symbols": ["nonexistent_handler"],
                        "file_paths": ["src/api.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "API_REF/endpoints": {"source_files": ["src/api.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 1
            f = data[0]
            assert "nonexistent_handler" in f["description"]
            assert "1 undefined symbol" in f["description"]
            assert f["group_id"] == "API_REF/endpoints"

    def test_non_python_file_skips_symbol_check(self):
        """Existing non-.py file with symbols listed → 0 findings (symbol check skipped)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "config.yaml"), "w") as f:
                f.write("key: value\n")

            manifest = _make_manifest("devops", {
                "OPS": {
                    "config": {
                        "symbols": ["some_setting"],
                        "file_paths": ["src/config.yaml"],
                    }
                }
            })
            with open(os.path.join(manifests, "devops.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "OPS/config": {"source_files": ["src/config.yaml"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Non-py file → all symbol sets empty → symbol check skipped
            assert len(data) == 0

    def test_non_python_file_missing(self):
        """Missing non-.py file → high finding (existence still checked)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            manifest = _make_manifest("devops", {
                "OPS": {
                    "deploy": {
                        "symbols": [],
                        "file_paths": ["deploy/Dockerfile"],
                    }
                }
            })
            with open(os.path.join(manifests, "devops.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan)

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 1
            assert "Dockerfile" in data[0]["description"]
            assert "1 missing file" in data[0]["description"]

    def test_directory_symbol_not_found(self):
        """Dir has .py files but symbol not defined → high finding."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            pkg = os.path.join(project, "src", "handlers")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "auth.py"), "w") as f:
                f.write("class AuthHandler:\n    pass\n")

            manifest = _make_manifest("developers", {
                "API_REF": {
                    "auth": {
                        "symbols": ["NonExistentMiddleware"],
                        "file_paths": ["src/handlers"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "API_REF/auth": {"source_files": ["src/handlers"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 1
            assert "NonExistentMiddleware" in data[0]["description"]
            assert "1 undefined symbol" in data[0]["description"]

    def test_directory_syntax_error_in_dir(self):
        """Dir has good.py (defines helper) + broken.py (SyntaxError).
        Manifest wants helper → 1 info finding for broken.py, 0 high findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            pkg = os.path.join(project, "src", "utils")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "good.py"), "w") as f:
                f.write("def helper():\n    pass\n")
            with open(os.path.join(pkg, "broken.py"), "w") as f:
                f.write("def oops(\n")  # SyntaxError

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "utils": {
                        "symbols": ["helper"],
                        "file_paths": ["src/utils"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/utils": {"source_files": ["src/utils"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # 1 info finding for broken.py SyntaxError, 0 high findings
            info_findings = [f for f in data if "SyntaxError" in f["description"]]
            high_findings = [f for f in data if "SyntaxError" not in f["description"]]
            assert len(info_findings) == 1
            assert "broken.py" in info_findings[0]["description"]
            assert "SyntaxError" in info_findings[0]["description"]
            assert len(high_findings) == 0

    def test_syntax_error_produces_info_finding(self):
        """Broken .py file → info finding for SyntaxError, no high finding for symbols."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "broken.py"), "w") as f:
                f.write("def foo(\n")  # SyntaxError

            manifest = _make_manifest("developers", {
                "ARCH": {
                    "core": {
                        "symbols": ["foo"],
                        "file_paths": ["src/broken.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCH/core": {"source_files": ["src/broken.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Should have info finding for SyntaxError, NOT high for undefined symbol
            assert len(data) == 1
            assert "SyntaxError" in data[0]["description"]
            assert "broken.py" in data[0]["description"]

    def test_scan_source_symbol_not_found(self):
        """Scan source_files has Python but symbol not defined → high finding."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Python source exists but doesn't define the symbol
            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "models.py"), "w") as f:
                f.write("class OtherModel:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["MissingClass"],
                        "file_paths": ["deploy/config.yaml"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            # Scan points to Python source that doesn't have the symbol
            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/models.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Missing file finding for deploy/config.yaml + undefined symbol finding
            symbol_findings = [f for f in data if "undefined symbol" in f["description"]]
            assert len(symbol_findings) == 1
            assert "1 undefined symbol" in symbol_findings[0]["description"]

    def test_scan_file_existence_still_uses_manifest(self):
        """Manifest file_paths has a missing file, scan source_files are fine →
        still produces missing-file high finding. Proves file existence and
        symbol verification are decoupled."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Python source exists with valid symbol
            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "models.py"), "w") as f:
                f.write("class ValidModel:\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["ValidModel"],
                        # This file doesn't exist — should produce missing-file finding
                        "file_paths": ["docs/deleted-file.md"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            # Scan source_files point to valid Python with the symbol
            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/models.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Should have exactly 1 missing-file finding (from manifest file_paths)
            # but 0 symbol findings (scan source_files resolve correctly)
            missing = [f for f in data if "missing file" in f["description"]]
            symbol = [f for f in data if "undefined symbol" in f["description"]]
            assert len(missing) == 1
            assert "deleted-file.md" in missing[0]["description"]
            assert len(symbol) == 0


class TestVerifyReferencesConsolidation:
    """Consolidation: multiple issues per section → one finding each."""

    def test_multiple_undefined_symbols_consolidated(self):
        """3 undefined symbols in 1 section → 1 finding with all 3 names."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "api.py"), "w") as f:
                f.write("def existing_func():\n    pass\n")

            manifest = _make_manifest("developers", {
                "API_REF": {
                    "endpoints": {
                        "symbols": ["missing_one", "missing_two", "missing_three"],
                        "file_paths": ["src/api.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "API_REF/endpoints": {"source_files": ["src/api.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Should be exactly 1 consolidated finding, not 3
            assert len(data) == 1
            f = data[0]
            assert "3 undefined symbol" in f["description"]
            assert "missing_one" in f["description"]
            assert "missing_two" in f["description"]
            assert "missing_three" in f["description"]

    def test_multiple_missing_files_consolidated(self):
        """3 missing files in 1 section → 1 finding with all 3 paths."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            manifest = _make_manifest("devops", {
                "OPERATIONS": {
                    "deploy": {
                        "symbols": [],
                        "file_paths": [
                            "scripts/deploy.sh",
                            "scripts/rollback.sh",
                            "config/prod.yaml",
                        ],
                    }
                }
            })
            with open(os.path.join(manifests, "devops.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan)

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # Should be exactly 1 consolidated finding, not 3
            assert len(data) == 1
            f = data[0]
            assert "3 missing file" in f["description"]
            assert "scripts/deploy.sh" in f["description"]
            assert "scripts/rollback.sh" in f["description"]
            assert "config/prod.yaml" in f["description"]

    def test_mixed_issues_produce_two_findings(self):
        """1 missing file + 2 undefined symbols in same section → 2 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "api.py"), "w") as f:
                f.write("def existing_func():\n    pass\n")

            manifest = _make_manifest("developers", {
                "API_REF": {
                    "endpoints": {
                        "symbols": ["missing_a", "missing_b"],
                        "file_paths": ["src/api.py", "no/such/file.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "API_REF/endpoints": {"source_files": ["src/api.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            # 1 missing-file finding + 1 undefined-symbols finding
            assert len(data) == 2
            missing = [f for f in data if "missing file" in f["description"]]
            symbols = [f for f in data if "undefined symbol" in f["description"]]
            assert len(missing) == 1
            assert len(symbols) == 1
            assert "2 undefined symbol" in symbols[0]["description"]


class TestVerifyReferencesEdgeCases:
    """Edge cases: empty dirs, no manifests, existing findings, metadata."""

    def test_no_manifests_dir(self):
        """Missing manifests directory → exit 0, 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")
            nonexistent = os.path.join(tmp, "no-such-dir")

            _write_scan(scan)

            result = _run(nonexistent, tmp, findings, scan)
            assert result.returncode == 0
            # No findings file created (nothing to write)
            assert not os.path.exists(findings)

    def test_empty_manifests_dir(self):
        """Empty manifests directory → exit 0, 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            manifests = os.path.join(tmp, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            _write_scan(scan)

            result = _run(manifests, tmp, findings, scan)
            assert result.returncode == 0
            assert not os.path.exists(findings)

    def test_existing_findings_preserved(self):
        """Seed file with 2 findings, script adds 1 → 3 total."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            # Seed with 2 existing findings
            existing = [
                {
                    "document": "PREV1", "section": "s1", "audience": "dev",
                    "check": "link-integrity",
                    "description": "old1", "suggestion": "fix1",
                },
                {
                    "document": "PREV2", "section": "s2", "audience": "dev",
                    "check": "cross-doc",
                    "description": "old2", "suggestion": "fix2",
                },
            ]
            with open(findings, "w") as f:
                json.dump(existing, f)

            # Manifest with 1 missing file → 1 new finding
            manifest = _make_manifest("developers", {
                "DOC": {
                    "sec": {
                        "symbols": [],
                        "file_paths": ["no/such/file.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan)

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 3
            # First 2 preserved
            assert data[0]["document"] == "PREV1"
            assert data[1]["document"] == "PREV2"
            # New one appended
            assert data[2]["check"] == "reference-integrity"

    def test_written_sections_skipped(self):
        """_written_sections metadata entry → no findings from it."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "_written_sections": {
                        "symbols": [],
                        "file_paths": [],
                        "sections_written": ["overview", "data-model"],
                    },
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan)

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0


class TestVerifyReferencesCallsChecking:
    """Calls field verification against actual function signatures."""

    def test_valid_calls_no_finding(self):
        """Calls with correct kwargs produce 0 findings."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "helpers.py"), "w") as f:
                f.write("def cache_or_call(prompt, model, ttl):\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "caching": {
                        "symbols": ["cache_or_call"],
                        "file_paths": ["src/helpers.py"],
                        "calls": [
                            {"symbol": "cache_or_call", "kwargs": ["prompt", "model"]}
                        ],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/caching": {"source_files": ["src/helpers.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_invalid_kwargs_flagged(self):
        """Calls with non-existent kwargs produce high finding."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "helpers.py"), "w") as f:
                f.write("def cache_or_call(prompt, model, ttl):\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "caching": {
                        "symbols": ["cache_or_call"],
                        "file_paths": ["src/helpers.py"],
                        "calls": [
                            {"symbol": "cache_or_call", "kwargs": ["prompt", "timeout", "retries"]}
                        ],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/caching": {"source_files": ["src/helpers.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            call_findings = [f for f in data if "invalid keyword" in f["description"]]
            assert len(call_findings) == 1
            assert "timeout" in call_findings[0]["description"]
            assert "retries" in call_findings[0]["description"]

    def test_missing_function_skipped_gracefully(self):
        """Calls referencing a function not in source are skipped (no finding)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "helpers.py"), "w") as f:
                f.write("def other_func():\n    pass\n")

            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "caching": {
                        "symbols": [],
                        "file_paths": ["src/helpers.py"],
                        "calls": [
                            {"symbol": "nonexistent_func", "kwargs": ["x"]}
                        ],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/caching": {"source_files": ["src/helpers.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_var_kwargs_skips_validation(self):
        """Functions accepting **kwargs skip keyword validation — any kwarg is valid."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "tests")
            os.makedirs(src)
            with open(os.path.join(src, "db_helpers.py"), "w") as f:
                f.write("def make_income_statement(db, **kw):\n    pass\n")

            manifest = _make_manifest("agents", {
                "TESTING": {
                    "test-data": {
                        "symbols": ["make_income_statement"],
                        "file_paths": ["tests/db_helpers.py"],
                        "calls": [
                            {"symbol": "make_income_statement", "kwargs": ["ticker", "period_date"]}
                        ],
                    }
                }
            })
            with open(os.path.join(manifests, "agents.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "TESTING/test-data": {"source_files": ["tests/db_helpers.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0

    def test_calls_absent_backwards_compatible(self):
        """Manifest without calls field produces no calls findings (backwards compat)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            manifests = os.path.join(project, "manifests")
            os.makedirs(manifests)
            findings = os.path.join(tmp, "findings.json")
            scan = os.path.join(tmp, "scan.json")

            src = os.path.join(project, "src")
            os.makedirs(src)
            with open(os.path.join(src, "models.py"), "w") as f:
                f.write("class User:\n    pass\n")

            # No calls field at all
            manifest = _make_manifest("developers", {
                "ARCHITECTURE": {
                    "overview": {
                        "symbols": ["User"],
                        "file_paths": ["src/models.py"],
                    }
                }
            })
            with open(os.path.join(manifests, "devs.json"), "w") as f:
                json.dump(manifest, f)

            _write_scan(scan, {
                "ARCHITECTURE/overview": {"source_files": ["src/models.py"]},
            })

            result = _run(manifests, project, findings, scan)
            assert result.returncode == 0

            data = _load(findings)
            assert len(data) == 0
