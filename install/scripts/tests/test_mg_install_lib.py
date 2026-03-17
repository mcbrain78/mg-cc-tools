"""Tests for mg-install-lib.py -- unified installer library.

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
    "mg-install-lib.py",
)


def _run(args, **kwargs):
    """Run mg-install-lib.py with given args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _make_tool(parent, name, description="Test tool", exclude=False,
               required=None, optional=None, commands=None):
    """Create a mock tool directory with tool.toml and install.sh.

    Args:
        parent: Parent directory to create the tool in.
        name: Tool directory name.
        description: Tool description for tool.toml.
        exclude: Whether tool is excluded from bulk ops.
        required: List of required preflight check IDs.
        optional: List of optional preflight check IDs.
        commands: List of command filenames to create (default: ["{name}.md"]).

    Returns:
        Path to the created tool directory.
    """
    tool_dir = os.path.join(parent, name)
    os.makedirs(os.path.join(tool_dir, "commands"), exist_ok=True)

    # tool.toml
    toml_lines = ['[tool]', f'description = "{description}"']
    if exclude:
        toml_lines.append("exclude = true")
    if required or optional:
        toml_lines.append("")
        toml_lines.append("[preflight]")
        if required:
            arr = ", ".join(f'"{r}"' for r in required)
            toml_lines.append(f"required = [{arr}]")
        if optional:
            arr = ", ".join(f'"{o}"' for o in optional)
            toml_lines.append(f"optional = [{arr}]")
    with open(os.path.join(tool_dir, "tool.toml"), "w") as f:
        f.write("\n".join(toml_lines) + "\n")

    # install.sh (minimal)
    with open(os.path.join(tool_dir, "install.sh"), "w") as f:
        f.write("#!/bin/bash\necho installed\n")

    # command files
    cmd_names = commands or [f"{name}.md"]
    for cmd in cmd_names:
        with open(os.path.join(tool_dir, "commands", cmd), "w") as f:
            f.write(f"---\nname: mg:{name}\n---\nTest command\n")

    return tool_dir


def _make_pyproject(parent, version="0.1.0"):
    """Create a pyproject.toml with given version."""
    with open(os.path.join(parent, "pyproject.toml"), "w") as f:
        f.write(f'[project]\nversion = "{version}"\n')


def _make_manifest(target, tools=None, version="0.1.0", source_path="/src"):
    """Create a manifest file in target/.claude/."""
    manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    data = {
        "mg_cc_tools_version": version,
        "source_path": source_path,
        "last_updated": "2026-01-01T00:00:00+00:00",
        "tools": tools or {},
        "capabilities": {},
    }
    with open(manifest_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return manifest_path


# ============================================================
# scan-status subcommand
# ============================================================


class TestScanStatus:
    """scan-status subcommand tests."""

    def test_discovers_tools_with_toml_and_install_sh(self):
        """Only directories with both tool.toml and install.sh are discovered."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "real-tool")

            # Missing install.sh -- should be ignored
            incomplete = os.path.join(source, "incomplete")
            os.makedirs(incomplete)
            with open(os.path.join(incomplete, "tool.toml"), "w") as f:
                f.write('[tool]\ndescription = "Incomplete"\n')

            _make_pyproject(source)

            result = _run([
                "scan-status",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool_names = [t["name"] for t in data["tools"]]
            assert "real-tool" in tool_names
            assert "incomplete" not in tool_names

    def test_ignores_dirs_with_only_install_sh(self):
        """Directories with install.sh but no tool.toml are ignored."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            # Only install.sh, no tool.toml
            no_toml = os.path.join(source, "no-toml")
            os.makedirs(no_toml)
            with open(os.path.join(no_toml, "install.sh"), "w") as f:
                f.write("#!/bin/bash\necho hi\n")

            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert len(data["tools"]) == 0

    def test_reads_toml_fields(self):
        """Reads tool.toml description, exclude, preflight fields."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", description="My great tool",
                       required=["python3"], optional=["ruff"])
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["description"] == "My great tool"
            assert tool["excluded"] is False

    def test_status_available_when_no_manifest(self):
        """Tool is 'available' when no manifest entry exists."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "new-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "available"
            assert tool["installed_version"] is None

    def test_status_current_when_versions_and_checksums_match(self):
        """Tool is 'current' when version and all checksums match."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # First, update manifest to record current checksums
            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", os.path.join(source, "my-tool"),
            ])
            assert result.returncode == 0, result.stderr

            # Now scan-status should show "current"
            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "current"

    def test_status_update_when_version_differs(self):
        """Tool is 'update' when manifest version differs from pyproject."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source, version="0.1.0")

            # Record with old version
            _make_manifest(target, tools={
                "my-tool": {
                    "version": "0.0.9",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                    "source_checksums": {},
                }
            })

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "update"
            assert tool["installed_version"] == "0.0.9"
            assert tool["current_version"] == "0.1.0"

    def test_status_modified_when_checksums_differ(self):
        """Tool is 'modified' when same version but checksums differ."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source, version="0.1.0")

            # Record with matching version but wrong checksums
            _make_manifest(target, tools={
                "my-tool": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                    "source_checksums": {"install.sh": "sha256:wrong"},
                }
            })

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "modified"
            assert len(tool["changed_files"]) > 0

    def test_status_corrupt_when_commands_missing_in_target(self):
        """Tool is 'corrupt' when manifest exists but commands missing."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            _make_tool(source, "my-tool")
            _make_pyproject(source, version="0.1.0")

            # Manifest says installed but command files are missing in target
            _make_manifest(target, tools={
                "my-tool": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                    "source_checksums": {},
                }
            })
            # Note: we deliberately do NOT put my-tool.md in target

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "corrupt"

    def test_excluded_tools_marked_in_output(self):
        """Excluded tools have excluded=true in output."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "normal-tool")
            _make_tool(source, "excluded-tool", exclude=True)
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools_by_name = {t["name"]: t for t in data["tools"]}
            assert tools_by_name["normal-tool"]["excluded"] is False
            assert tools_by_name["excluded-tool"]["excluded"] is True

    def test_output_has_required_top_level_fields(self):
        """Output JSON has mg_cc_tools_version, target, manifest_exists, tools, summary."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "a-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "mg_cc_tools_version" in data
            assert "target" in data
            assert "manifest_exists" in data
            assert "tools" in data
            assert "summary" in data

    def test_summary_counts(self):
        """Summary counts reflect tool statuses correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "tool-a")
            _make_tool(source, "tool-b")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            summary = data["summary"]
            assert summary["available"] == 2
            assert summary["total"] == 2
            assert summary["installed"] == 0

    def test_version_from_pyproject(self):
        """mg_cc_tools_version comes from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "t")
            _make_pyproject(source, version="1.2.3")

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["mg_cc_tools_version"] == "1.2.3"

    def test_checksum_excludes_test_dirs(self):
        """Checksums exclude tests/ and __pycache__/ directories."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            tool_dir = _make_tool(source, "my-tool")

            # Add a scripts dir with a .py file and a tests/ dir
            scripts_dir = os.path.join(tool_dir, "scripts")
            os.makedirs(os.path.join(scripts_dir, "tests"), exist_ok=True)
            with open(os.path.join(scripts_dir, "real.py"), "w") as f:
                f.write("# real script\n")
            with open(os.path.join(scripts_dir, "tests", "test_it.py"), "w") as f:
                f.write("# test\n")

            # Add __pycache__
            os.makedirs(os.path.join(scripts_dir, "__pycache__"), exist_ok=True)
            with open(os.path.join(scripts_dir, "__pycache__", "cache.pyc"), "w") as f:
                f.write("bytecode\n")

            _make_pyproject(source)

            # Update manifest to get checksums
            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            # Read manifest and check checksums keys
            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            checksums = manifest["tools"]["my-tool"]["source_checksums"]
            # real.py should be included
            assert any("real.py" in k for k in checksums)
            # test file and pycache should NOT be included
            assert not any("test_it" in k for k in checksums)
            assert not any("__pycache__" in k for k in checksums)
            assert not any(".pyc" in k for k in checksums)


# ============================================================
# update-manifest subcommand
# ============================================================


class TestUpdateManifest:
    """update-manifest subcommand tests."""

    def test_creates_manifest_if_not_exists(self):
        """Creates manifest file if it does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            assert os.path.exists(manifest_path)

            with open(manifest_path) as f:
                data = json.load(f)
            assert "my-tool" in data["tools"]

    def test_updates_existing_manifest_preserves_other_tools(self):
        """Updating one tool preserves other tools' entries."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "tool-b")
            _make_pyproject(source)

            # Pre-existing manifest with tool-a
            _make_manifest(target, tools={
                "tool-a": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["tool-a.md"],
                    "source_checksums": {"install.sh": "sha256:abc"},
                }
            })

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "tool-b",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                data = json.load(f)

            assert "tool-a" in data["tools"]
            assert "tool-b" in data["tools"]
            # tool-a data preserved
            assert data["tools"]["tool-a"]["version"] == "0.1.0"

    def test_records_version_and_commands(self):
        """Records version, installed_at, commands list."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool",
                                  commands=["my-tool.md", "my-tool-scan.md"])
            _make_pyproject(source, version="2.0.0")

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                data = json.load(f)

            entry = data["tools"]["my-tool"]
            assert entry["version"] == "2.0.0"
            assert "installed_at" in entry
            assert "T" in entry["installed_at"]  # ISO 8601
            assert set(entry["commands"]) == {"my-tool.md", "my-tool-scan.md"}

    def test_records_source_checksums(self):
        """Records SHA256 checksums of source files."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                data = json.load(f)

            checksums = data["tools"]["my-tool"]["source_checksums"]
            assert len(checksums) > 0
            # All values should have sha256: prefix
            for val in checksums.values():
                assert val.startswith("sha256:")

    def test_sets_top_level_version_and_source_path(self):
        """Sets mg_cc_tools_version and source_path at top level."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool")
            _make_pyproject(source, version="3.0.0")

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                data = json.load(f)

            assert data["mg_cc_tools_version"] == "3.0.0"
            assert data["source_path"] == source

    def test_checksum_keys_are_relative_paths(self):
        """Source checksum keys are relative to tool directory."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "update-manifest",
                "--target", target,
                "--tool", "my-tool",
                "--source", tool_dir,
            ])
            assert result.returncode == 0, result.stderr

            manifest_path = os.path.join(target, ".claude", "mg-cc-tools.manifest.json")
            with open(manifest_path) as f:
                data = json.load(f)

            checksums = data["tools"]["my-tool"]["source_checksums"]
            for key in checksums:
                # Keys should be relative, not absolute
                assert not key.startswith("/")
                assert not key.startswith(tmp)


# ============================================================
# preflight subcommand
# ============================================================


class TestPreflight:
    """preflight subcommand tests."""

    def test_command_check_passes_for_python3(self):
        """python3 command check passes (we know it's installed)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", required=["python3"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            # Find python3 check
            py_check = None
            for check in data["checks"]:
                if check["id"] == "python3":
                    py_check = check
                    break
            assert py_check is not None
            assert py_check["passed"] is True
            assert py_check["version"] is not None

    def test_command_check_passes_for_git(self):
        """git command check passes (we know it's installed)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", required=["git"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            git_check = None
            for check in data["checks"]:
                if check["id"] == "git":
                    git_check = check
                    break
            assert git_check is not None
            assert git_check["passed"] is True

    def test_path_exists_check_for_gsd(self):
        """gsd path-exists check fails when .claude/get-shit-done doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", required=["gsd"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            gsd_check = None
            for check in data["checks"]:
                if check["id"] == "gsd":
                    gsd_check = check
                    break
            assert gsd_check is not None
            assert gsd_check["passed"] is False

    def test_path_exists_check_passes_when_dir_exists(self):
        """gsd path-exists check passes when directory exists."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude", "get-shit-done"),
                        exist_ok=True)

            _make_tool(source, "my-tool", required=["gsd"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            gsd_check = None
            for check in data["checks"]:
                if check["id"] == "gsd":
                    gsd_check = check
                    break
            assert gsd_check is not None
            assert gsd_check["passed"] is True

    def test_skips_claude_probe_checks(self):
        """claude_probe type checks (lsp) are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", optional=["lsp"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            # lsp should be skipped, not in checks list
            check_ids = [c["id"] for c in data["checks"]]
            assert "lsp" not in check_ids

    def test_aggregates_checks_from_multiple_tools(self):
        """Checks from multiple tools are aggregated (deduplicated)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "tool-a", required=["python3"])
            _make_tool(source, "tool-b", required=["python3", "git"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "tool-a,tool-b",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            # python3 and git should each appear once
            check_ids = [c["id"] for c in data["checks"]]
            assert check_ids.count("python3") == 1
            assert check_ids.count("git") == 1

    def test_distinguishes_required_vs_optional(self):
        """Checks have required field based on tool declarations."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", required=["python3"], optional=["ruff"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            checks_by_id = {c["id"]: c for c in data["checks"]}
            assert checks_by_id["python3"]["required"] is True
            # ruff may or may not be installed, but should be optional
            if "ruff" in checks_by_id:
                assert checks_by_id["ruff"]["required"] is False

    def test_failed_check_has_fix_instructions(self):
        """Failed checks include fix instructions."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            # gsd check will fail (no .claude/get-shit-done)
            _make_tool(source, "my-tool", required=["gsd"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            gsd_check = None
            for check in data["checks"]:
                if check["id"] == "gsd":
                    gsd_check = check
                    break
            assert gsd_check is not None
            assert gsd_check["passed"] is False
            assert "fix" in gsd_check
            assert isinstance(gsd_check["fix"], dict)

    def test_output_has_all_passed_field(self):
        """Output has all_passed boolean summarizing results."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", required=["python3"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "all_passed" in data
            assert isinstance(data["all_passed"], bool)


# ============================================================
# validate subcommand
# ============================================================


class TestValidate:
    """validate subcommand tests."""

    def test_detects_unresolved_placeholders(self):
        """Finds unresolved {PLACEHOLDER} patterns in installed files."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # File with unresolved placeholder
            with open(os.path.join(cmd_dir, "test-cmd.md"), "w") as f:
                f.write("Use {SCRIPTS_DIR}/foo.py for analysis\n")

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["issues"]) > 0
            issue = data["issues"][0]
            assert issue["type"] == "placeholder"
            assert "{SCRIPTS_DIR}" in issue["pattern"]

    def test_detects_missing_resolved_paths(self):
        """Finds resolved absolute paths that don't exist on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # File with a resolved absolute path that doesn't exist
            with open(os.path.join(cmd_dir, "test-cmd.md"), "w") as f:
                f.write(f"Use {tmp}/nonexistent/path/script.py for analysis\n")

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            path_issues = [i for i in data["issues"] if i["type"] == "missing_path"]
            assert len(path_issues) > 0

    def test_clean_install_has_no_issues(self):
        """A clean install with no placeholders or bad paths has zero issues."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # Clean file
            with open(os.path.join(cmd_dir, "clean.md"), "w") as f:
                f.write("---\nname: mg:clean\n---\nNo placeholders here.\n")

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert len(data["issues"]) == 0

    def test_detects_missing_workspace_dirs(self):
        """Detects missing workspace directories for tools that scaffold them."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            os.makedirs(os.path.join(target, ".claude"), exist_ok=True)

            # Create manifest with tools that need workspaces
            _make_manifest(target, tools={
                "codebase-health": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["codebase-health.md"],
                    "source_checksums": {},
                },
            })

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            workspace_issues = [i for i in data["issues"]
                                if i["type"] == "missing_workspace"]
            assert len(workspace_issues) > 0

    def test_returns_file_and_line_for_issues(self):
        """Issues include file and line number."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "test-cmd.md"), "w") as f:
                f.write("line 1\n{SCRIPTS_DIR}\nline 3\n")

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["issues"]) > 0
            issue = data["issues"][0]
            assert "file" in issue
            assert "line" in issue
            assert issue["line"] == 2


# ============================================================
# adopt subcommand
# ============================================================


class TestAdopt:
    """adopt subcommand tests."""

    def test_detects_installed_tool_by_command_presence(self):
        """Detects tool as installed when all its commands exist in target."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            # Create source tool
            _make_tool(source, "my-tool", commands=["my-tool.md", "my-tool-scan.md"])
            _make_pyproject(source)

            # Simulate pre-existing install in target (files exist, no manifest)
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed content\n")
            with open(os.path.join(cmd_dir, "my-tool-scan.md"), "w") as f:
                f.write("installed content\n")

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["adopted"]) == 1
            assert data["adopted"][0]["name"] == "my-tool"

    def test_ignores_partial_installs(self):
        """Tool is NOT detected if only some commands exist in target."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool", commands=["my-tool.md", "my-tool-scan.md"])
            _make_pyproject(source)

            # Only one of two commands exists
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed content\n")
            # my-tool-scan.md is missing

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["adopted"]) == 0

    def test_builds_manifest_entries_with_current_checksums(self):
        """Adopted tools have manifest entries with current source checksums."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source, version="0.5.0")

            # Simulate install
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["adopted"]) == 1
            entry = data["adopted"][0]["manifest_entry"]
            assert entry["version"] == "0.5.0"
            assert "source_checksums" in entry
            assert len(entry["source_checksums"]) > 0
            for val in entry["source_checksums"].values():
                assert val.startswith("sha256:")

    def test_returns_empty_when_nothing_installed(self):
        """Returns empty adopted list when no tools are detected."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert len(data["adopted"]) == 0

    def test_skips_tools_already_in_manifest(self):
        """Tools already in manifest are not re-adopted."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Tool exists in target commands
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            # And also exists in manifest already
            _make_manifest(target, tools={
                "my-tool": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                    "source_checksums": {},
                }
            })

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert len(data["adopted"]) == 0
