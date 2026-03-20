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
               standard=None, required=None, optional=None, commands=None,
               has_install_sh=True, post_install_script=None,
               detect_paths=None):
    """Create a mock tool directory with tool.toml and optionally install.sh.

    Args:
        parent: Parent directory to create the tool in.
        name: Tool directory name.
        description: Tool description for tool.toml.
        exclude: Whether tool is excluded from bulk ops.
        standard: Whether tool is in standard install (None = omit, uses default true).
        required: List of required preflight check IDs.
        optional: List of optional preflight check IDs.
        commands: List of command filenames to create (default: ["{name}.md"]).
        has_install_sh: Whether to create install.sh (default True).
        post_install_script: If set, add [post_install] section and create the file.
        detect_paths: If set, add [detect] section with these paths.

    Returns:
        Path to the created tool directory.
    """
    tool_dir = os.path.join(parent, name)
    os.makedirs(os.path.join(tool_dir, "commands"), exist_ok=True)

    # tool.toml
    toml_lines = ['[tool]', f'description = "{description}"']
    if exclude:
        toml_lines.append("exclude = true")
    if standard is not None:
        toml_lines.append(f"standard = {'true' if standard else 'false'}")
    if required or optional:
        toml_lines.append("")
        toml_lines.append("[preflight]")
        if required:
            arr = ", ".join(f'"{r}"' for r in required)
            toml_lines.append(f"required = [{arr}]")
        if optional:
            arr = ", ".join(f'"{o}"' for o in optional)
            toml_lines.append(f"optional = [{arr}]")
    if post_install_script:
        toml_lines.append("")
        toml_lines.append("[post_install]")
        toml_lines.append(f'script = "{post_install_script}"')
    if detect_paths:
        toml_lines.append("")
        toml_lines.append("[detect]")
        arr = ", ".join(f'"{p}"' for p in detect_paths)
        toml_lines.append(f"paths = [{arr}]")
    with open(os.path.join(tool_dir, "tool.toml"), "w") as f:
        f.write("\n".join(toml_lines) + "\n")

    # install.sh (minimal) -- only if requested
    if has_install_sh:
        with open(os.path.join(tool_dir, "install.sh"), "w") as f:
            f.write("#!/bin/bash\necho installed\n")

    # post-install.md -- create if specified
    if post_install_script:
        with open(os.path.join(tool_dir, post_install_script), "w") as f:
            f.write("# Post-install instructions\nPOST-INSTALL: SUCCESS\n")

    # command files (commands=[] means no commands; commands=None means default)
    cmd_names = commands if commands is not None else [f"{name}.md"]
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

    def test_discovers_tools_with_toml_only(self):
        """Directories with tool.toml are discovered even without install.sh."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "real-tool")

            # Tool with only tool.toml (no install.sh) -- should now be discovered
            toml_only = _make_tool(source, "toml-only-tool",
                                   has_install_sh=False,
                                   post_install_script="post-install.md")

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
            assert "toml-only-tool" in tool_names

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

            # Simulate install: place command files in target
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            # Update manifest to record current checksums
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

            # Place command file in target so it's not corrupt
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

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

            # Place command file in target so it's not corrupt
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

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

    def test_standard_defaults_true(self):
        """Tools without standard field default to standard=true."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "normal-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["tools"][0]["standard"] is True

    def test_standard_false_in_toml(self):
        """Tools with standard=false are marked in output."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "optional-tool", standard=False)
            _make_tool(source, "standard-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools_by_name = {t["name"]: t for t in data["tools"]}
            assert tools_by_name["optional-tool"]["standard"] is False
            assert tools_by_name["standard-tool"]["standard"] is True

    def test_standard_overrides_from_manifest(self):
        """Manifest standard_overrides take precedence over tool.toml."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "optional-tool", standard=False)
            _make_tool(source, "demoted-tool")
            _make_pyproject(source)

            # Create manifest with standard_overrides
            manifest_path = os.path.join(
                target, ".claude", "mg-cc-tools.manifest.json"
            )
            manifest = {
                "mg_cc_tools_version": "0.1.0",
                "source_path": source,
                "last_updated": "2026-01-01T00:00:00+00:00",
                "tools": {},
                "capabilities": {},
                "standard_overrides": {
                    "optional-tool": True,
                    "demoted-tool": False,
                },
            }
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools_by_name = {t["name"]: t for t in data["tools"]}
            # optional-tool promoted to standard via override
            assert tools_by_name["optional-tool"]["standard"] is True
            # demoted-tool demoted from standard via override
            assert tools_by_name["demoted-tool"]["standard"] is False

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
            assert summary["installed_total"] == 0

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

    def test_reads_post_install_and_detect(self):
        """read_tool_toml() returns post_install_script and detect_paths."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            # Tool with [post_install] and [detect] sections
            _make_tool(source, "configured-tool",
                       post_install_script="post-install.md",
                       detect_paths=[".claude/configured-tool/"])
            # Tool without those sections (defaults)
            _make_tool(source, "plain-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools_by_name = {t["name"]: t for t in data["tools"]}

            # configured-tool should have post_install and has_install_sh
            configured = tools_by_name["configured-tool"]
            assert configured.get("post_install") == "post-install.md"

            # plain-tool should have None/null for post_install
            plain = tools_by_name["plain-tool"]
            assert plain.get("post_install") is None

    def test_scan_status_includes_install_pattern(self):
        """scan-status output includes post_install and has_install_sh fields."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            # Tool with install.sh only (no post-install)
            _make_tool(source, "copy-only")
            # Tool with both install.sh and post-install.md
            _make_tool(source, "copy-configure",
                       post_install_script="post-install.md")
            # Tool with only post-install.md (no install.sh) -- execute-only
            _make_tool(source, "exec-only",
                       has_install_sh=False,
                       post_install_script="post-install.md")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools_by_name = {t["name"]: t for t in data["tools"]}

            # copy-only: has_install_sh=true, post_install=null
            copy_only = tools_by_name["copy-only"]
            assert copy_only["has_install_sh"] is True
            assert copy_only["post_install"] is None

            # copy-configure: has_install_sh=true, post_install="post-install.md"
            copy_cfg = tools_by_name["copy-configure"]
            assert copy_cfg["has_install_sh"] is True
            assert copy_cfg["post_install"] == "post-install.md"

            # exec-only: has_install_sh=false, post_install="post-install.md"
            exec_only = tools_by_name["exec-only"]
            assert exec_only["has_install_sh"] is False
            assert exec_only["post_install"] == "post-install.md"

    def test_no_corrupt_for_empty_commands(self):
        """scan-status does not report corrupt for tools with empty commands list."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            # Execute-only tool: has post-install but no commands
            _make_tool(source, "exec-tool",
                       has_install_sh=False,
                       post_install_script="post-install.md",
                       commands=[])
            _make_pyproject(source, version="0.1.0")

            # Manifest entry with commands=[] (execute-only pattern)
            _make_manifest(target, tools={
                "exec-tool": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": [],
                    "source_checksums": {},
                }
            })

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = [t for t in data["tools"] if t["name"] == "exec-tool"][0]
            # Should NOT be corrupt -- empty commands list is valid for execute-only
            assert tool["status"] != "corrupt"

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

    def test_checksums_include_post_install(self):
        """compute_tool_checksums() includes post-install.md at root."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            # Tool with post-install.md
            tool_dir = _make_tool(source, "my-tool",
                                  post_install_script="post-install.md")
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
            assert "post-install.md" in checksums
            assert checksums["post-install.md"].startswith("sha256:")

    def test_checksums_include_patches(self):
        """compute_tool_checksums() includes patches/**/*.md files."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            tool_dir = _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Create patches directory with .md files
            patches_dir = os.path.join(tool_dir, "patches")
            os.makedirs(patches_dir, exist_ok=True)
            with open(os.path.join(patches_dir, "foo.md"), "w") as f:
                f.write("# Patch content\n")

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
            assert "patches/foo.md" in checksums
            assert checksums["patches/foo.md"].startswith("sha256:")


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

    def test_lsp_settings_scan_no_plugin(self):
        """LSP check fails when no LSP plugin in settings."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            fake_home = os.path.join(tmp, "fakehome")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            os.makedirs(fake_home)

            _make_tool(source, "my-tool", optional=["lsp"])
            _make_pyproject(source)

            # Isolate from real ~/.claude/settings.json
            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ], env={**os.environ, "HOME": fake_home})
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            lsp_check = None
            for check in data["checks"]:
                if check["id"] == "lsp":
                    lsp_check = check
                    break
            assert lsp_check is not None
            assert lsp_check["type"] == "settings_scan"
            assert lsp_check["passed"] is False
            assert data["all_passed"] is True

    def test_lsp_settings_scan_finds_plugin(self):
        """LSP check passes when LSP plugin found in settings."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            fake_home = os.path.join(tmp, "fakehome")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool", optional=["lsp"])
            _make_pyproject(source)

            # Create fake global settings with LSP plugin
            global_claude = os.path.join(fake_home, ".claude")
            os.makedirs(global_claude)
            with open(os.path.join(global_claude, "settings.json"), "w") as f:
                json.dump({"enabledPlugins": {"pyright-lsp@test": True}}, f)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ], env={**os.environ, "HOME": fake_home})
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            lsp_check = None
            for check in data["checks"]:
                if check["id"] == "lsp":
                    lsp_check = check
                    break
            assert lsp_check is not None
            assert lsp_check["passed"] is True
            assert "pyright-lsp" in lsp_check["version"]

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

    def test_valid_field_present(self):
        """Output includes valid boolean."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "clean.md"), "w") as f:
                f.write("No issues here.\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is True
            assert data["issue_count"] == 0

    def test_valid_false_when_issues(self):
        """valid is false when issues exist."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "bad.md"), "w") as f:
                f.write("Use {SCRIPTS_DIR}/foo.py\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is False
            assert data["issue_count"] > 0

    def test_ignores_short_template_vars(self):
        """Short template vars like {N}, {M}, {X} are not flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "template.md"), "w") as f:
                f.write("Phase {N} has {M} tasks and {X} files.\n")
                f.write("Also {XX} and {NN} are fine.\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is True
            assert data["issue_count"] == 0

    def test_tools_scoping(self):
        """--tools flag scopes validation to specified tool's files only."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # Create two tools in source
            _make_tool(source, "clean-tool")
            _make_tool(source, "bad-tool")
            _make_pyproject(source)

            # Install both in target, but bad-tool has issues
            with open(os.path.join(cmd_dir, "clean-tool.md"), "w") as f:
                f.write("No issues.\n")
            with open(os.path.join(cmd_dir, "bad-tool.md"), "w") as f:
                f.write("Use {SCRIPTS_DIR}/foo.py\n")

            # Validate only clean-tool — should find no issues
            result = _run([
                "validate", "--target", target,
                "--tools", "clean-tool", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is True

            # Validate only bad-tool — should find issues
            result = _run([
                "validate", "--target", target,
                "--tools", "bad-tool", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is False

    def test_output_flag_writes_file(self):
        """--output writes full details to file, compact summary to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            output_file = os.path.join(tmp, "validate.json")

            with open(os.path.join(cmd_dir, "bad.md"), "w") as f:
                f.write("Use {SCRIPTS_DIR}/foo.py\n")

            result = _run([
                "validate", "--target", target,
                "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr

            # Stdout has compact summary
            stdout_data = json.loads(result.stdout)
            assert "valid" in stdout_data
            assert "issue_count" in stdout_data
            assert "details" in stdout_data
            assert "issues" not in stdout_data  # Full issues NOT in stdout

            # File has full details
            with open(output_file) as f:
                file_data = json.load(f)
            assert "issues" in file_data
            assert len(file_data["issues"]) > 0


class TestScanStatusOutput:
    """Tests for scan-status --output flag."""

    def test_output_flag_writes_file_compact_stdout(self):
        """--output writes full details to file, compact summary to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            output_file = os.path.join(tmp, "scan.json")

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
                "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr

            # Stdout compact: no source_checksums, no changed_files
            stdout_data = json.loads(result.stdout)
            assert "details" in stdout_data
            tool = stdout_data["tools"][0]
            assert "source_checksums" not in tool
            assert "changed_files" not in tool
            assert "name" in tool
            assert "status" in tool

            # File has full details
            with open(output_file) as f:
                file_data = json.load(f)
            assert "tools" in file_data


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

            assert data["count"] == 1
            assert "my-tool" in data["adopted"]

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

    def test_writes_manifest_with_checksums(self):
        """Adopt writes manifest directly with tool entries and checksums."""
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

            assert data["count"] == 1
            assert "my-tool" in data["adopted"]

            # Verify manifest was written
            manifest_path = os.path.join(
                target, ".claude", "mg-cc-tools.manifest.json"
            )
            assert os.path.isfile(manifest_path)
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert "my-tool" in manifest["tools"]
            entry = manifest["tools"]["my-tool"]
            assert entry["version"] == "0.5.0"
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

    def test_detects_by_detect_paths(self):
        """adopt detects a tool via [detect].paths even when it has no commands."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            # Tool with detect paths but no commands in commands/
            _make_tool(source, "hooks-tool",
                       commands=[],
                       detect_paths=[".claude/hooks-tool/hooks/"])
            _make_pyproject(source)

            # Create the detect path in target
            hooks_dir = os.path.join(target, ".claude", "hooks-tool", "hooks")
            os.makedirs(hooks_dir, exist_ok=True)

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "hooks-tool" in data["adopted"]

    def test_skips_execute_only_tools(self):
        """adopt skips tools with no commands AND no detect paths."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            # Execute-only tool: no commands, no detect paths
            _make_tool(source, "exec-only-tool",
                       has_install_sh=False,
                       post_install_script="post-install.md",
                       commands=[])
            _make_pyproject(source)

            result = _run([
                "adopt",
                "--source", source,
                "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert len(data["adopted"]) == 0
