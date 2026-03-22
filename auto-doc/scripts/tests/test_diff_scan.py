"""Tests for diff-scan.py -- deterministic diff scoping for incremental doc scans.

Tests use real git repositories in temporary directories to validate
git-based operations. Direct function imports via importlib for unit
tests, subprocess for CLI integration tests.
"""

import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile

# Import the module under test (hyphenated filename)
_SCRIPT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."
)
SCRIPT_PATH = os.path.join(_SCRIPT_DIR, "diff-scan.py")

_loader = importlib.machinery.SourceFileLoader(
    "diff_scan", SCRIPT_PATH
)
_spec = importlib.util.spec_from_loader("diff_scan", _loader)
diff_scan = importlib.util.module_from_spec(_spec)
_loader.exec_module(diff_scan)


def _git(cwd, *args):
    """Run a git command in the given directory."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, encoding="utf-8", cwd=cwd,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _make_git_repo(tmpdir):
    """Initialize a git repo with one initial commit (backdated for tests)."""
    _git(tmpdir, "init")
    _git(tmpdir, "config", "user.email", "test@example.com")
    _git(tmpdir, "config", "user.name", "Test")
    # Initial commit -- backdated so there is a clear timestamp gap
    # between it and any subsequent commits made "now".
    readme = os.path.join(tmpdir, "README.md")
    with open(readme, "w") as f:
        f.write("# Test\n")
    _git(tmpdir, "add", "README.md")
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = "2025-01-01T00:00:00Z"
    env["GIT_COMMITTER_DATE"] = "2025-01-01T00:00:00Z"
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        capture_output=True, text=True, cwd=tmpdir, env=env,
        check=True,
    )


class TestResolveCommit:
    """resolve_commit resolves ISO timestamp to nearest commit SHA."""

    def test_resolves_to_commit_before_timestamp(self):
        """Given a timestamp after all commits, returns the latest commit."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            head = _git(tmp, "rev-parse", "HEAD")
            result = diff_scan.resolve_commit("2099-01-01T00:00:00Z", tmp)
            assert result == head

    def test_returns_none_when_no_commit_before_timestamp(self):
        """Timestamp before first commit returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            result = diff_scan.resolve_commit("1970-01-01T00:00:00Z", tmp)
            assert result is None


class TestGetChangedFiles:
    """get_changed_files returns files changed between commits."""

    def test_detects_modified_file(self):
        """Modified file appears in changed files list."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            base = _git(tmp, "rev-parse", "HEAD")

            # Create a new file
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "app.py"), "w") as f:
                f.write("print('hello')\n")
            _git(tmp, "add", "src/app.py")
            _git(tmp, "commit", "-m", "Add app.py")

            changed = diff_scan.get_changed_files(base, tmp)
            assert "src/app.py" in changed

    def test_detects_added_file(self):
        """Newly added file appears in changed files list."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            base = _git(tmp, "rev-parse", "HEAD")

            with open(os.path.join(tmp, "new.txt"), "w") as f:
                f.write("new\n")
            _git(tmp, "add", "new.txt")
            _git(tmp, "commit", "-m", "Add new.txt")

            changed = diff_scan.get_changed_files(base, tmp)
            assert "new.txt" in changed

    def test_detects_deleted_file(self):
        """Deleted file appears in changed files list."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            base = _git(tmp, "rev-parse", "HEAD")

            _git(tmp, "rm", "README.md")
            _git(tmp, "commit", "-m", "Delete README")

            changed = diff_scan.get_changed_files(base, tmp)
            assert "README.md" in changed

    def test_paths_normalized_no_leading_dot_slash(self):
        """Paths in changed files have no leading './'."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            base = _git(tmp, "rev-parse", "HEAD")

            os.makedirs(os.path.join(tmp, "sub"))
            with open(os.path.join(tmp, "sub", "file.py"), "w") as f:
                f.write("x = 1\n")
            _git(tmp, "add", "sub/file.py")
            _git(tmp, "commit", "-m", "Add sub/file.py")

            changed = diff_scan.get_changed_files(base, tmp)
            for p in changed:
                assert not p.startswith("./"), f"Path starts with ./: {p}"

    def test_returns_empty_for_same_commit(self):
        """No changes when base is HEAD."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            head = _git(tmp, "rev-parse", "HEAD")
            changed = diff_scan.get_changed_files(head, tmp)
            assert changed == []


class TestGetRenames:
    """get_renames returns old_path -> new_path for renamed files."""

    def test_detects_rename(self):
        """Renamed file detected with old -> new mapping."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            # Create a file with enough content for rename detection
            with open(os.path.join(tmp, "old_name.py"), "w") as f:
                f.write("def function_one():\n    pass\n\ndef function_two():\n    pass\n")
            _git(tmp, "add", "old_name.py")
            _git(tmp, "commit", "-m", "Add old_name.py")
            base = _git(tmp, "rev-parse", "HEAD")

            # Rename it
            _git(tmp, "mv", "old_name.py", "new_name.py")
            _git(tmp, "commit", "-m", "Rename old_name.py -> new_name.py")

            renames = diff_scan.get_renames(base, tmp)
            assert "old_name.py" in renames
            assert renames["old_name.py"] == "new_name.py"

    def test_no_renames_returns_empty_dict(self):
        """No renames returns empty dict."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            base = _git(tmp, "rev-parse", "HEAD")

            with open(os.path.join(tmp, "added.py"), "w") as f:
                f.write("x = 1\n")
            _git(tmp, "add", "added.py")
            _git(tmp, "commit", "-m", "Add file (no rename)")

            renames = diff_scan.get_renames(base, tmp)
            assert renames == {}


class TestBuildFileToSectionsIndex:
    """build_file_to_sections_index creates reverse index from manifests."""

    def test_builds_index_from_single_manifest(self):
        """Single manifest produces correct file -> sections mapping."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "audience": "developers",
                "generated": "2026-03-22T14:30:00Z",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["App"],
                            "file_paths": ["src/app.ts"],
                        }
                    }
                },
            }
            with open(os.path.join(tmp, "developers.json"), "w") as f:
                json.dump(manifest, f)

            index = diff_scan.build_file_to_sections_index(tmp)
            assert "src/app.ts" in index
            assert len(index["src/app.ts"]) == 1
            entry = index["src/app.ts"][0]
            assert entry["audience"] == "developers"
            assert entry["document"] == "ARCHITECTURE"
            assert entry["section"] == "overview"

    def test_builds_index_from_multiple_manifests(self):
        """Multiple manifests create combined index."""
        with tempfile.TemporaryDirectory() as tmp:
            dev_manifest = {
                "audience": "developers",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["App"],
                            "file_paths": ["src/app.ts"],
                        }
                    }
                },
            }
            user_manifest = {
                "audience": "end-users",
                "documents": {
                    "USER_GUIDE": {
                        "getting-started": {
                            "symbols": [],
                            "file_paths": ["src/app.ts"],
                        }
                    }
                },
            }
            with open(os.path.join(tmp, "developers.json"), "w") as f:
                json.dump(dev_manifest, f)
            with open(os.path.join(tmp, "end-users.json"), "w") as f:
                json.dump(user_manifest, f)

            index = diff_scan.build_file_to_sections_index(tmp)
            # src/app.ts should appear in both audiences
            assert len(index["src/app.ts"]) == 2
            audiences = {e["audience"] for e in index["src/app.ts"]}
            assert audiences == {"developers", "end-users"}

    def test_skips_written_sections_metadata(self):
        """_written_sections entries are skipped during index build."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "audience": "developers",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["App"],
                            "file_paths": ["src/app.ts"],
                        },
                        "_written_sections": {
                            "sections_written": ["overview"],
                            "symbols": [],
                            "file_paths": [],
                        },
                    }
                },
            }
            with open(os.path.join(tmp, "developers.json"), "w") as f:
                json.dump(manifest, f)

            index = diff_scan.build_file_to_sections_index(tmp)
            # Should only index src/app.ts, not any _written_sections paths
            assert "src/app.ts" in index
            assert len(index) == 1

    def test_empty_dir_returns_empty_index(self):
        """Empty manifests directory returns empty index."""
        with tempfile.TemporaryDirectory() as tmp:
            index = diff_scan.build_file_to_sections_index(tmp)
            assert index == {}

    def test_corrupt_manifest_skipped(self):
        """Corrupt (invalid JSON) manifest is skipped, others still indexed."""
        with tempfile.TemporaryDirectory() as tmp:
            # Valid manifest
            valid = {
                "audience": "developers",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["App"],
                            "file_paths": ["src/app.ts"],
                        }
                    }
                },
            }
            with open(os.path.join(tmp, "developers.json"), "w") as f:
                json.dump(valid, f)
            # Corrupt manifest
            with open(os.path.join(tmp, "corrupt.json"), "w") as f:
                f.write("{not valid json")

            index = diff_scan.build_file_to_sections_index(tmp)
            assert "src/app.ts" in index


class TestClassifyChanges:
    """classify_changes produces affected_sections, new_file_candidates, deleted_files."""

    def _make_index(self):
        """Create a sample file-to-sections index."""
        return {
            "src/app.ts": [
                {"audience": "developers", "document": "ARCHITECTURE", "section": "overview"},
            ],
            "src/models.py": [
                {"audience": "developers", "document": "ARCHITECTURE", "section": "data-model"},
                {"audience": "end-users", "document": "USER_GUIDE", "section": "getting-started"},
            ],
        }

    def test_changed_file_in_manifest_produces_affected_section(self):
        """Changed file found in manifest creates affected_sections entries."""
        index = self._make_index()
        result = diff_scan.classify_changes(
            changed_files=["src/app.ts"],
            renames={},
            file_index=index,
            deleted_check_fn=lambda f: False,
        )
        assert len(result["affected_sections"]) == 1
        section = result["affected_sections"][0]
        assert section["audience"] == "developers"
        assert section["document"] == "ARCHITECTURE"
        assert section["section"] == "overview"
        assert "src/app.ts" in section["changed_files"]

    def test_new_file_not_in_manifest_becomes_candidate(self):
        """File not in any manifest becomes new_file_candidate."""
        index = self._make_index()
        result = diff_scan.classify_changes(
            changed_files=["src/brand_new.ts"],
            renames={},
            file_index=index,
            deleted_check_fn=lambda f: False,
        )
        assert len(result["new_file_candidates"]) == 1
        assert result["new_file_candidates"][0]["file"] == "src/brand_new.ts"

    def test_deleted_file_in_manifest_listed(self):
        """Deleted file still in manifests appears in deleted_files."""
        index = self._make_index()
        result = diff_scan.classify_changes(
            changed_files=["src/models.py"],
            renames={},
            file_index=index,
            deleted_check_fn=lambda f: f == "src/models.py",
        )
        assert len(result["deleted_files"]) == 1
        deleted = result["deleted_files"][0]
        assert deleted["file"] == "src/models.py"
        assert len(deleted["referenced_in"]) == 2

    def test_rename_produces_single_entry_with_mapping(self):
        """Renamed files produce single affected_sections entry with renames dict."""
        index = {
            "src/old.py": [
                {"audience": "developers", "document": "ARCHITECTURE", "section": "overview"},
            ],
        }
        result = diff_scan.classify_changes(
            changed_files=["src/new.py"],
            renames={"src/old.py": "src/new.py"},
            file_index=index,
            deleted_check_fn=lambda f: False,
        )
        # Should have affected section from the rename, not a new_file_candidate
        assert len(result["affected_sections"]) == 1
        section = result["affected_sections"][0]
        assert section["renames"] == {"src/old.py": "src/new.py"}
        assert len(result["new_file_candidates"]) == 0

    def test_cross_audience_fanout(self):
        """File in multiple audience manifests creates entries for each."""
        index = self._make_index()
        result = diff_scan.classify_changes(
            changed_files=["src/models.py"],
            renames={},
            file_index=index,
            deleted_check_fn=lambda f: False,
        )
        # src/models.py is in developers AND end-users manifests
        assert len(result["affected_sections"]) == 2
        audiences = {s["audience"] for s in result["affected_sections"]}
        assert audiences == {"developers", "end-users"}

    def test_deduplicates_sections(self):
        """Multiple changed files in same section produce one section entry."""
        index = {
            "src/a.py": [
                {"audience": "developers", "document": "ARCHITECTURE", "section": "overview"},
            ],
            "src/b.py": [
                {"audience": "developers", "document": "ARCHITECTURE", "section": "overview"},
            ],
        }
        result = diff_scan.classify_changes(
            changed_files=["src/a.py", "src/b.py"],
            renames={},
            file_index=index,
            deleted_check_fn=lambda f: False,
        )
        assert len(result["affected_sections"]) == 1
        section = result["affected_sections"][0]
        assert set(section["changed_files"]) == {"src/a.py", "src/b.py"}


class TestDiscoverGsdPhases:
    """discover_gsd_phases finds and parses GSD summary files."""

    def test_returns_empty_when_gsd_dir_none(self):
        """None gsd_dir returns empty list."""
        result = diff_scan.discover_gsd_phases(None, "2026-01-01T00:00:00Z", "/tmp")
        assert result == []

    def test_returns_empty_when_gsd_dir_missing(self):
        """Non-existent gsd_dir returns empty list."""
        result = diff_scan.discover_gsd_phases(
            "/nonexistent/path", "2026-01-01T00:00:00Z", "/tmp"
        )
        assert result == []

    def test_finds_summary_files_since_timestamp(self):
        """Discovers SUMMARY.md files modified since timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            # Create a GSD phases directory structure
            gsd_dir = os.path.join(tmp, ".planning", "phases")
            phase_dir = os.path.join(gsd_dir, "06-fix-verify")
            os.makedirs(phase_dir)

            summary = os.path.join(phase_dir, "06-01-SUMMARY.md")
            with open(summary, "w") as f:
                f.write("---\nphase: 06-fix-verify\nplan: 01\n")
                f.write("key-decisions:\n  - replaced route_model\n---\n")
                f.write("# Phase 6: Fix Verify Summary\n")

            _git(tmp, "add", "-A")
            _git(tmp, "commit", "-m", "Add phase 06 summary")

            result = diff_scan.discover_gsd_phases(
                gsd_dir, "2020-01-01T00:00:00Z", tmp
            )
            assert len(result) >= 1
            phase = result[0]
            assert phase["phase"] == "06"


class TestMainCLI:
    """CLI integration tests for diff-scan.py main()."""

    def test_produces_valid_diff_scope_json(self):
        """Full CLI run produces valid diff-scope.json with expected structure."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            # Create initial file and commit
            os.makedirs(os.path.join(tmp, "src"))
            with open(os.path.join(tmp, "src", "app.ts"), "w") as f:
                f.write("export class App {}\n")
            _git(tmp, "add", "src/app.ts")
            _git(tmp, "commit", "-m", "Add app.ts")

            # Use timestamp between initial commit (2025-01-01) and now
            since = "2025-06-01T00:00:00Z"

            # Create manifests dir with a manifest
            manifests_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifests_dir)
            manifest = {
                "audience": "developers",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["App"],
                            "file_paths": ["src/app.ts"],
                        }
                    }
                },
            }
            with open(os.path.join(manifests_dir, "developers.json"), "w") as f:
                json.dump(manifest, f)

            # Create docs dir
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)

            # Output path
            output = os.path.join(tmp, "diff-scope.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--project-root", tmp,
                 "--manifests-dir", manifests_dir,
                 "--docs-dir", docs_dir,
                 "--since", since,
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            assert os.path.isfile(output)

            with open(output) as f:
                scope = json.load(f)

            # Validate top-level structure
            assert "since" in scope
            assert "summary" in scope
            assert "affected_sections" in scope
            assert "new_file_candidates" in scope
            assert "deleted_files" in scope
            assert "gsd_phases_since" in scope

            # Summary should have counts
            summary = scope["summary"]
            assert "files_changed" in summary
            assert "sections_affected" in summary
            assert "new_file_candidates" in summary

    def test_gsd_dir_omitted_produces_empty_gsd_context(self):
        """Without --gsd-dir, gsd_phases_since is empty, gsd_context is null."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            # Setup minimal structure
            manifests_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifests_dir)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)
            output = os.path.join(tmp, "diff-scope.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--project-root", tmp,
                 "--manifests-dir", manifests_dir,
                 "--docs-dir", docs_dir,
                 "--since", "2025-06-01T00:00:00Z",
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"CLI failed: {result.stderr}"

            with open(output) as f:
                scope = json.load(f)

            assert scope["gsd_phases_since"] == []

    def test_nonexistent_gsd_dir_produces_empty_gsd(self):
        """--gsd-dir pointing to nonexistent path produces empty GSD."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            manifests_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifests_dir)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)
            output = os.path.join(tmp, "diff-scope.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--project-root", tmp,
                 "--manifests-dir", manifests_dir,
                 "--docs-dir", docs_dir,
                 "--since", "2025-06-01T00:00:00Z",
                 "--gsd-dir", os.path.join(tmp, "nonexistent"),
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            with open(output) as f:
                scope = json.load(f)
            assert scope["gsd_phases_since"] == []

    def test_timestamp_before_first_commit_produces_empty_scope(self):
        """Timestamp before first commit produces graceful empty scope."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)

            manifests_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifests_dir)
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)
            output = os.path.join(tmp, "diff-scope.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--project-root", tmp,
                 "--manifests-dir", manifests_dir,
                 "--docs-dir", docs_dir,
                 "--since", "1950-01-01T00:00:00Z",
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            with open(output) as f:
                scope = json.load(f)
            assert scope["summary"]["files_changed"] == 0
            assert scope["summary"]["sections_affected"] == 0

    def test_no_manifests_all_files_become_candidates(self):
        """With no manifests, all changed files become new_file_candidates."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_git_repo(tmp)
            # Initial commit is backdated to 2025-01-01.
            # Add a file after the initial commit (committed "now").
            with open(os.path.join(tmp, "new_file.py"), "w") as f:
                f.write("x = 1\n")
            _git(tmp, "add", "new_file.py")
            _git(tmp, "commit", "-m", "Add new file")

            # Use a since timestamp that resolves to the initial commit
            # (2025-01-01), so the diff shows new_file.py.
            since = "2025-06-01T00:00:00Z"

            manifests_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifests_dir)  # empty dir
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)
            output = os.path.join(tmp, "diff-scope.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--project-root", tmp,
                 "--manifests-dir", manifests_dir,
                 "--docs-dir", docs_dir,
                 "--since", since,
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            with open(output) as f:
                scope = json.load(f)
            # All changed files should be new_file_candidates
            candidate_files = [c["file"] for c in scope["new_file_candidates"]]
            assert "new_file.py" in candidate_files
