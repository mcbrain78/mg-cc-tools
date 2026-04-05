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


def _make_venv(target):
    """Create a .venv in target that mirrors the test runner's venv.

    Uses a wrapper script that execs the test runner's python, preserving
    its sys.path and installed packages. A plain symlink would resolve to
    the base interpreter and lose access to venv site-packages.
    """
    venv_bin = os.path.join(target, ".venv", "bin")
    os.makedirs(venv_bin, exist_ok=True)
    python_wrapper = os.path.join(venv_bin, "python3")
    if not os.path.exists(python_wrapper):
        with open(python_wrapper, "w") as f:
            f.write(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
        os.chmod(python_wrapper, 0o755)


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

    def test_status_adopted_when_manifest_has_adopted_flag(self):
        """Tool is 'adopted' when manifest entry has adopted=true."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            _make_tool(source, "my-tool")
            _make_pyproject(source, version="0.1.0")

            # Command file exists on disk
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            # Manifest has adopted flag (no version or checksums)
            _make_manifest(target, tools={
                "my-tool": {
                    "adopted": True,
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                }
            })

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tool = data["tools"][0]
            assert tool["status"] == "adopted"

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
        """python3 venv check passes when .venv exists."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            _make_venv(target)

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
            _make_venv(target)

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
            _make_venv(target)

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
            _make_venv(target)

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

    def test_python3_fails_without_venv(self):
        """python3 check fails when target has no .venv."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            # No _make_venv(target) -- deliberately omitted

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

            py_check = None
            for check in data["checks"]:
                if check["id"] == "python3":
                    py_check = check
                    break
            assert py_check is not None
            assert py_check["passed"] is False
            assert ".venv" in py_check["error"]
            assert data["all_passed"] is False

    def test_python_import_passes_with_installed_package(self):
        """python_import check passes when package is in target venv."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            _make_venv(target)

            _make_tool(source, "my-tool", required=["tiktoken"])

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            tk_check = None
            for check in data["checks"]:
                if check["id"] == "tiktoken":
                    tk_check = check
                    break
            assert tk_check is not None
            assert tk_check["passed"] is True
            assert tk_check["version"] is not None

    def test_python_import_fails_without_venv(self):
        """python_import check fails when target has no .venv."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            # No venv

            _make_tool(source, "my-tool", required=["tiktoken"])
            _make_pyproject(source)

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "my-tool",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            tk_check = None
            for check in data["checks"]:
                if check["id"] == "tiktoken":
                    tk_check = check
                    break
            assert tk_check is not None
            assert tk_check["passed"] is False
            assert ".venv" in tk_check["error"]


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
                f.write("Use {MG_INSTALL_SCRIPTS_DIR}/foo.py for analysis\n")

            result = _run([
                "validate", "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            assert len(data["issues"]) > 0
            issue = data["issues"][0]
            assert issue["type"] == "placeholder"
            assert "{MG_INSTALL_SCRIPTS_DIR}" in issue["pattern"]

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
                f.write("line 1\n{MG_INSTALL_SCRIPTS_DIR}\nline 3\n")

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
                f.write("Use {MG_INSTALL_SCRIPTS_DIR}/foo.py\n")

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
                f.write("Use {MG_INSTALL_SCRIPTS_DIR}/foo.py\n")

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
                f.write("Use {MG_INSTALL_SCRIPTS_DIR}/foo.py\n")

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


    def test_non_install_placeholders_ignored(self):
        """Runtime placeholders like {DOCUMENT}, {DISK_PCT} are NOT flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "template.md"), "w") as f:
                f.write("Document: {DOCUMENT}\n")
                f.write("Name: {DOCUMENT_NAME}\n")
                f.write("Stage: {STAGE_LABEL}\n")
                f.write("Disk: {DISK_PCT}\n")
                f.write("Mem: ${MEM_AVAIL}\n")
                f.write("Audience: {AUDIENCE}\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["valid"] is True, f"Should have no issues: {data['issues']}"

    def test_detects_unresolved_relative_references(self):
        """Relative references/foo.md paths are flagged as unresolved."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            with open(os.path.join(cmd_dir, "test-cmd.md"), "w") as f:
                f.write("Read references/schema.md for details\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            ref_issues = [i for i in data["issues"]
                          if i["type"] == "unresolved_reference"]
            assert len(ref_issues) > 0
            assert "references/schema.md" in ref_issues[0]["pattern"]

    def test_resolved_references_not_flagged(self):
        """Absolute reference paths are not flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            ref_file = os.path.join(tmp, "references", "schema.md")
            os.makedirs(cmd_dir, exist_ok=True)
            os.makedirs(os.path.dirname(ref_file), exist_ok=True)
            with open(ref_file, "w") as f:
                f.write("schema\n")

            # Absolute path to references/ -- should NOT be flagged
            with open(os.path.join(cmd_dir, "test-cmd.md"), "w") as f:
                f.write(f"Read {ref_file} for details\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            ref_issues = [i for i in data["issues"]
                          if i["type"] == "unresolved_reference"]
            assert len(ref_issues) == 0, f"Unexpected ref issues: {ref_issues}"

    def test_detects_missing_source_files(self):
        """Source files not present in target are flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            # Create tool with command + agent
            tool_dir = _make_tool(source, "my-tool")
            agents_dir = os.path.join(tool_dir, "agents")
            os.makedirs(agents_dir, exist_ok=True)
            with open(os.path.join(agents_dir, "scanner.md"), "w") as f:
                f.write("agent\n")
            _make_pyproject(source)

            # Install only the command, not the agent
            with open(os.path.join(target, ".claude", "commands", "mg",
                                   "my-tool.md"), "w") as f:
                f.write("installed\n")

            result = _run([
                "validate", "--target", target,
                "--tools", "my-tool", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            missing = [i for i in data["issues"]
                       if i["type"] == "missing_source_file"]
            assert len(missing) > 0
            patterns = {i["pattern"] for i in missing}
            assert "agents/scanner.md" in patterns

    def test_all_source_files_present_no_issue(self):
        """Complete install with all source files has no missing_source_file."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # Create tool with command
            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Install the command to target
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")
            # install.sh exists in source but is skipped by comparison
            # No agents/scripts, so only command needs to be present

            result = _run([
                "validate", "--target", target,
                "--tools", "my-tool", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            missing = [i for i in data["issues"]
                       if i["type"] == "missing_source_file"]
            assert len(missing) == 0, f"Unexpected missing: {missing}"

    def test_scans_tool_specific_agent_dirs(self):
        """Placeholders in .claude/{tool}/agents/ are detected."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            agent_dir = os.path.join(target, ".claude", "my-tool", "agents")
            os.makedirs(cmd_dir, exist_ok=True)
            os.makedirs(agent_dir, exist_ok=True)

            # Clean command
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("No issues.\n")
            # Agent with unresolved placeholder
            with open(os.path.join(agent_dir, "scanner.md"), "w") as f:
                f.write("Run {MG_INSTALL_SCRIPTS_DIR}/scan.py\n")

            result = _run(["validate", "--target", target])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            ph_issues = [i for i in data["issues"]
                         if i["type"] == "placeholder"]
            assert len(ph_issues) > 0
            assert any("scanner.md" in i["file"] for i in ph_issues)

    def test_invalid_sed_target_detected(self):
        """install.sh with bare {SCRIPTS_DIR} sed target is flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(os.path.join(target, ".claude", "commands", "mg"),
                        exist_ok=True)

            # Create tool with install.sh that has bare placeholder target
            tool_dir = _make_tool(source, "bad-sed")
            with open(os.path.join(tool_dir, "install.sh"), "w") as f:
                f.write('#!/bin/bash\n')
                f.write('sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$file"\n')
            _make_pyproject(source)

            result = _run([
                "validate", "--target", target,
                "--tools", "bad-sed", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            sed_issues = [i for i in data["issues"]
                          if i["type"] == "invalid_sed_target"]
            assert len(sed_issues) > 0
            assert "{SCRIPTS_DIR}" in sed_issues[0]["pattern"]

    def test_valid_sed_targets_pass(self):
        """install.sh with MG_INSTALL_ prefixed targets is clean."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)

            # Create tool with properly prefixed install.sh
            tool_dir = _make_tool(source, "good-sed")
            with open(os.path.join(tool_dir, "install.sh"), "w") as f:
                f.write('#!/bin/bash\n')
                f.write('sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$f"\n')
                f.write('sed -i "s|references/schema.md|${ABS}|g" "$f"\n')
            _make_pyproject(source)

            # Install command so no missing_source_file
            with open(os.path.join(cmd_dir, "good-sed.md"), "w") as f:
                f.write("clean\n")

            result = _run([
                "validate", "--target", target,
                "--tools", "good-sed", "--source", source,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)

            sed_issues = [i for i in data["issues"]
                          if i["type"] == "invalid_sed_target"]
            assert len(sed_issues) == 0, f"Unexpected: {sed_issues}"


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

    def test_writes_manifest_adopted_entry(self):
        """Adopt writes manifest with adopted flag, no version or checksums."""
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
            assert entry["adopted"] is True
            assert "version" not in entry
            assert "source_checksums" not in entry
            assert "installed_at" in entry
            assert entry["commands"] == ["my-tool.md"]

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


# ============================================================
# Helpers for renderer tests
# ============================================================


def _make_scan_status_fixture():
    """Create a realistic scan-status JSON for renderer tests.

    Includes:
    - 3 standard tools (statuses: current, update, available)
    - 2 optional tools (statuses: available, corrupt)
    - 1 excluded tool
    """
    return {
        "mg_cc_tools_version": "0.3.0",
        "target": "/home/user/projects/road-runner",
        "manifest_exists": True,
        "tools": [
            {
                "name": "alpha-tool",
                "description": "Alpha tool for testing",
                "status": "current",
                "installed_version": "0.3.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["alpha-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "beta-tool",
                "description": "Beta tool with update available",
                "status": "update",
                "installed_version": "0.2.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["beta-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "gamma-tool",
                "description": "Gamma tool not yet installed",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["gamma-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "delta-optional",
                "description": "Delta optional tool",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["delta-optional.md"],
                "excluded": False,
                "standard": False,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "epsilon-optional",
                "description": "Epsilon optional but corrupt",
                "status": "corrupt",
                "installed_version": "0.2.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["epsilon-optional.md"],
                "excluded": False,
                "standard": False,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "zeta-excluded",
                "description": "Zeta internal excluded tool",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["zeta-excluded.md"],
                "excluded": True,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
        ],
        "summary": {
            "total": 6,
            "installed_total": 3,
            "current": 1,
            "update": 1,
            "modified": 0,
            "corrupt": 1,
            "available": 3,
        },
    }


def _write_scan_status_file(tmpdir, scan_data=None):
    """Write scan-status JSON to a temp file and return the path."""
    if scan_data is None:
        scan_data = _make_scan_status_fixture()
    path = os.path.join(tmpdir, "scan-status.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, indent=2)
    return path


# ============================================================
# render-status-table subcommand
# ============================================================


class TestRenderStatusTable:
    """render-status-table subcommand tests."""

    def test_three_tier_layout(self):
        """Table shows standard, optional (with dot separator), and excluded
        (with dashed separator) sections."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # Standard tools present
            assert "alpha-tool" in out
            assert "beta-tool" in out
            assert "gamma-tool" in out

            # Optional tools present
            assert "delta-optional" in out
            assert "epsilon-optional" in out

            # Excluded tool present
            assert "zeta-excluded" in out

            # Dot separator between standard and optional
            lines = out.split("\n")
            dot_line_found = any("\u00b7" in line for line in lines)
            assert dot_line_found, "Expected dot separator (\u00b7) between standard and optional"

            # Dashed separator before excluded
            dashed_found = any("\u2500 \u2500" in line for line in lines)
            assert dashed_found, "Expected dashed separator (\u2500 \u2500) before excluded section"

    def test_summary_counts_non_excluded(self):
        """Summary line counts only non-excluded tools."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # installed_total=3 from summary, non-excluded total=5
            # Summary should show Installed: 3/5
            assert "3/5" in out

    def test_update_version_annotation(self):
        """Tool with status 'update' shows version annotation."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "Update (0.2.0" in out
            assert "0.3.0)" in out

    def test_current_status_shows_checkmark(self):
        """Tool with status 'current' shows checkmark symbol."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "\u2713 Current" in out

    def test_optional_tools_have_star_marker(self):
        """Optional tools show '*' marker after tool name."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # Find lines with optional tools -- they should have *
            lines = out.split("\n")
            delta_lines = [l for l in lines if "delta-optional" in l]
            assert len(delta_lines) > 0
            assert "*" in delta_lines[0]

            epsilon_lines = [l for l in lines if "epsilon-optional" in l]
            assert len(epsilon_lines) > 0
            assert "*" in epsilon_lines[0]

    def test_column_alignment(self):
        """Column alignment is consistent across all rows."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # Find tool data rows (lines containing tool names)
            tool_names = ["alpha-tool", "beta-tool", "gamma-tool",
                          "delta-optional", "epsilon-optional"]
            tool_lines = []
            for line in out.split("\n"):
                for name in tool_names:
                    if name in line:
                        tool_lines.append(line)
                        break

            # At least 5 tool lines should be present
            assert len(tool_lines) >= 5, f"Expected 5+ tool lines, got {len(tool_lines)}"

    def test_header_line(self):
        """Header shows 'mg-cc-tools vX.Y.Z -> /path/to/target'."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "mg-cc-tools v0.3.0" in out
            assert "/home/user/projects/road-runner" in out
            assert "->" in out

    def test_status_legend(self):
        """Status legend appears at bottom with all status definitions."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # All 6 status types in legend
            assert "\u2713 Current" in out
            assert "Update" in out
            assert "Modified" in out
            assert "Corrupt" in out
            assert "Available" in out
            assert "Excluded" in out

            # Optional marker explanation
            assert "*" in out
            assert "optional" in out.lower()

    def test_cli_invocation_with_input(self):
        """CLI invocation via --input file works (subprocess)."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-status-table", "--input", input_file])
            assert result.returncode == 0, result.stderr
            # Should produce non-empty stdout
            assert len(result.stdout.strip()) > 0


# ============================================================
# render-tool-picker subcommand
# ============================================================


class TestRenderToolPicker:
    """render-tool-picker subcommand tests."""

    def test_section_headers(self):
        """Shows Standard and Optional section headers with separator lines."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "Standard" in out
            assert "Optional" in out

    def test_sequential_numbering(self):
        """Tools numbered sequentially (standard 1..N, then optional N+1..M)."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # 3 standard + 2 optional = 5 tools
            # Numbers 1-5 should appear
            lines = out.split("\n")
            numbered_lines = [l for l in lines if l.strip() and
                              l.strip()[0].isdigit()]
            # Should have exactly 5 numbered tool lines
            assert len(numbered_lines) == 5, \
                f"Expected 5 numbered lines, got {len(numbered_lines)}: {numbered_lines}"

    def test_excluded_tools_filtered(self):
        """Excluded tools are not shown."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "zeta-excluded" not in out

    def test_non_available_status_annotation(self):
        """Tools with non-available status get annotation."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # alpha-tool is "current" -> should show (Current)
            alpha_lines = [l for l in out.split("\n") if "alpha-tool" in l]
            assert len(alpha_lines) > 0
            assert "(Current)" in alpha_lines[0]

            # epsilon-optional is "corrupt" -> should show (Corrupt)
            epsilon_lines = [l for l in out.split("\n") if "epsilon-optional" in l]
            assert len(epsilon_lines) > 0
            assert "(Corrupt)" in epsilon_lines[0]

    def test_available_tools_no_annotation(self):
        """Available tools have no status annotation."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout

            # gamma-tool is "available" -> no annotation
            gamma_lines = [l for l in out.split("\n") if "gamma-tool" in l]
            assert len(gamma_lines) > 0
            # Should NOT have a parenthesized annotation
            assert "(Available)" not in gamma_lines[0]
            assert "(Current)" not in gamma_lines[0]

    def test_footer_line(self):
        """Footer line 'Type numbers, names, or all:' appears."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "Type numbers, names, or" in out
            assert "all" in out

    def test_cli_invocation_with_input(self):
        """CLI invocation via --input file works."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["render-tool-picker", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert len(result.stdout.strip()) > 0


# ============================================================
# resolve-tool-selection subcommand
# ============================================================


class TestResolveToolSelection:
    """resolve-tool-selection subcommand tests."""

    def test_single_number(self):
        """Single number '2' resolves to the second tool name."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "2"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert len(data["tools"]) == 1
            # Second tool in ordered list (standard first, alphabetical)
            assert data["tools"][0] == "beta-tool"

    def test_comma_separated_numbers(self):
        """Comma-separated numbers '2,5' resolves to correct tools."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "2,5"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert len(data["tools"]) == 2
            assert "beta-tool" in data["tools"]
            assert "epsilon-optional" in data["tools"]

    def test_range(self):
        """Range '1-3' resolves to first three tool names."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "1-3"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert len(data["tools"]) == 3
            assert "alpha-tool" in data["tools"]
            assert "beta-tool" in data["tools"]
            assert "gamma-tool" in data["tools"]

    def test_tool_name(self):
        """Tool name 'delta-optional' resolves to ['delta-optional']."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "delta-optional"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert data["tools"] == ["delta-optional"]

    def test_mixed_input(self):
        """Mixed '1-3, delta-optional' resolves to union of range + name."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "1-3, delta-optional"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert len(data["tools"]) == 4
            assert "alpha-tool" in data["tools"]
            assert "beta-tool" in data["tools"]
            assert "gamma-tool" in data["tools"]
            assert "delta-optional" in data["tools"]

    def test_all_keyword(self):
        """'all' resolves to all non-excluded tools."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "all"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data
            assert len(data["tools"]) == 5
            assert "zeta-excluded" not in data["tools"]

    def test_out_of_range_number(self):
        """Out-of-range number returns error JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "99"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "error" in data

    def test_unrecognized_name(self):
        """Unrecognized name returns error JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "nonexistent-tool"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "error" in data

    def test_numbering_matches_picker(self):
        """Numbering matches render-tool-picker output (shared _get_ordered_tools)."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)

            # Get picker output
            picker_result = _run(["render-tool-picker", "--input", input_file])
            assert picker_result.returncode == 0, picker_result.stderr
            picker_out = picker_result.stdout

            # Extract tool at position 1 from picker output
            lines = picker_out.split("\n")
            first_numbered = None
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("1."):
                    first_numbered = stripped
                    break

            assert first_numbered is not None, "No line starting with '1.' in picker output"

            # Resolve number 1
            resolve_result = _run(["resolve-tool-selection",
                                   "--input", input_file,
                                   "--selection", "1"])
            assert resolve_result.returncode == 0, resolve_result.stderr
            data = json.loads(resolve_result.stdout)
            resolved_name = data["tools"][0]

            # The first tool name from picker should match the resolved name
            assert resolved_name in first_numbered

    def test_cli_invocation(self):
        """CLI invocation via --input and --selection args works."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "1"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "tools" in data


# ============================================================
# Shared ordering (_get_ordered_tools)
# ============================================================


class TestGetOrderedTools:
    """Tests for the shared _get_ordered_tools ordering function."""

    def test_standard_before_optional(self):
        """Standard tools come before optional tools."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)

            # Resolve all to get the ordered list
            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "all"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools = data["tools"]

            # Standard tools: alpha-tool, beta-tool, gamma-tool
            # Optional tools: delta-optional, epsilon-optional
            # Standard should come first
            alpha_idx = tools.index("alpha-tool")
            delta_idx = tools.index("delta-optional")
            assert alpha_idx < delta_idx, \
                "Standard tools should come before optional"

    def test_excludes_excluded_tools(self):
        """Excluded tools are not in the ordered list."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)

            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "all"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "zeta-excluded" not in data["tools"]

    def test_alphabetical_within_tier(self):
        """Tools are alphabetical within each tier."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)

            result = _run(["resolve-tool-selection",
                           "--input", input_file,
                           "--selection", "all"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            tools = data["tools"]

            # Standard tier: alpha, beta, gamma (already alphabetical)
            standard = tools[:3]
            assert standard == sorted(standard)

            # Optional tier: delta, epsilon (already alphabetical)
            optional = tools[3:]
            assert optional == sorted(optional)


# ============================================================
# Scenario fixtures for action menu and resolve-action tests
# ============================================================


def _make_scenario_a_fixture():
    """Scenario A: nothing installed (installed_total == 0)."""
    return {
        "mg_cc_tools_version": "0.3.0",
        "target": "/home/user/projects/road-runner",
        "manifest_exists": False,
        "tools": [
            {
                "name": "alpha-tool",
                "description": "Alpha tool",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["alpha-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "beta-tool",
                "description": "Beta tool",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["beta-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "gamma-tool",
                "description": "Gamma optional",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["gamma-tool.md"],
                "excluded": False,
                "standard": False,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "zeta-excluded",
                "description": "Excluded tool",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["zeta-excluded.md"],
                "excluded": True,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
        ],
        "summary": {
            "total": 4,
            "installed_total": 0,
            "current": 0,
            "update": 0,
            "modified": 0,
            "corrupt": 0,
            "adopted": 0,
            "available": 4,
        },
    }


def _make_scenario_b_fixture():
    """Scenario B: some tools need attention (update/modified/corrupt/adopted)."""
    return {
        "mg_cc_tools_version": "0.3.0",
        "target": "/home/user/projects/road-runner",
        "manifest_exists": True,
        "tools": [
            {
                "name": "alpha-tool",
                "description": "Alpha current",
                "status": "current",
                "installed_version": "0.3.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["alpha-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "beta-tool",
                "description": "Beta needs update",
                "status": "update",
                "installed_version": "0.2.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["beta-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "gamma-tool",
                "description": "Gamma available standard",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["gamma-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "delta-tool",
                "description": "Delta adopted",
                "status": "adopted",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["delta-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "epsilon-optional",
                "description": "Epsilon optional available",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["epsilon-optional.md"],
                "excluded": False,
                "standard": False,
                "has_install_sh": True,
                "post_install": None,
            },
        ],
        "summary": {
            "total": 5,
            "installed_total": 3,
            "current": 1,
            "update": 1,
            "modified": 0,
            "corrupt": 0,
            "adopted": 1,
            "available": 2,
        },
    }


def _make_scenario_c_fixture():
    """Scenario C: all installed are current, some still available."""
    return {
        "mg_cc_tools_version": "0.3.0",
        "target": "/home/user/projects/road-runner",
        "manifest_exists": True,
        "tools": [
            {
                "name": "alpha-tool",
                "description": "Alpha current",
                "status": "current",
                "installed_version": "0.3.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["alpha-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "beta-tool",
                "description": "Beta current",
                "status": "current",
                "installed_version": "0.3.0",
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["beta-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "gamma-tool",
                "description": "Gamma available standard",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["gamma-tool.md"],
                "excluded": False,
                "standard": True,
                "has_install_sh": True,
                "post_install": None,
            },
            {
                "name": "delta-optional",
                "description": "Delta optional available",
                "status": "available",
                "installed_version": None,
                "current_version": "0.3.0",
                "changed_files": [],
                "commands": ["delta-optional.md"],
                "excluded": False,
                "standard": False,
                "has_install_sh": True,
                "post_install": None,
            },
        ],
        "summary": {
            "total": 4,
            "installed_total": 2,
            "current": 2,
            "update": 0,
            "modified": 0,
            "corrupt": 0,
            "adopted": 0,
            "available": 2,
        },
    }


# ============================================================
# _determine_scenario shared helper
# ============================================================


class TestDetermineScenario:
    """Tests for _determine_scenario shared helper."""

    def test_returns_a_when_nothing_installed(self):
        """Returns 'A' when installed_total == 0."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            # Use render-action-menu to verify scenario (it prints scenario-specific text)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            # Scenario A has "Install all standard tools"
            assert "Install all standard tools" in result.stdout

    def test_returns_b_when_update(self):
        """Returns 'B' when summary has update > 0."""
        scan_data = _make_scenario_a_fixture()
        scan_data["summary"]["installed_total"] = 1
        scan_data["summary"]["update"] = 1
        scan_data["summary"]["available"] = 3
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "needing attention" in result.stdout

    def test_returns_b_when_modified(self):
        """Returns 'B' when summary has modified > 0."""
        scan_data = _make_scenario_a_fixture()
        scan_data["summary"]["installed_total"] = 1
        scan_data["summary"]["modified"] = 1
        scan_data["summary"]["available"] = 3
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "needing attention" in result.stdout

    def test_returns_b_when_corrupt(self):
        """Returns 'B' when summary has corrupt > 0 (INST-51 behavior change)."""
        scan_data = _make_scenario_a_fixture()
        scan_data["summary"]["installed_total"] = 1
        scan_data["summary"]["corrupt"] = 1
        scan_data["summary"]["available"] = 3
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "needing attention" in result.stdout

    def test_returns_b_when_adopted(self):
        """Returns 'B' when summary has adopted > 0 (INST-51 behavior change)."""
        scan_data = _make_scenario_a_fixture()
        scan_data["summary"]["installed_total"] = 1
        scan_data["summary"]["adopted"] = 1
        scan_data["summary"]["available"] = 3
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "needing attention" in result.stdout

    def test_returns_c_when_all_current(self):
        """Returns 'C' when installed_total > 0 and no attention needed."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            # Scenario C has "Reinstall all" (not in A or B)
            assert "Reinstall all" in result.stdout


# ============================================================
# render-action-menu subcommand
# ============================================================


class TestRenderActionMenu:
    """render-action-menu subcommand tests."""

    def test_scenario_a_three_options(self):
        """Scenario A prints 3 options with standard count."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "What would you like to do?" in out
            assert "[1]" in out
            assert "[2]" in out
            assert "[3]" in out
            # Should NOT have [4] or [5]
            assert "[4]" not in out
            assert "[5]" not in out
            # Standard count: 2 standard tools (alpha, beta)
            assert "2 tools" in out
            assert "Select specific tools" in out
            assert "Type a number, or tool names" in out

    def test_scenario_b_six_options(self):
        """Scenario B prints 6 options with attention count, available count, and select specific."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "What would you like to do?" in out
            assert "[1]" in out
            assert "[2]" in out
            assert "[3]" in out
            assert "[4]" in out
            assert "[5]" in out
            assert "[6]" in out
            assert "needing attention" in out
            assert "Select specific tools" in out
            assert "Type a number, tool names, or 'all':" in out

    def test_scenario_c_five_options(self):
        """Scenario C prints 5 options with remaining standard count and select specific."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            out = result.stdout
            assert "What would you like to do?" in out
            assert "[1]" in out
            assert "[2]" in out
            assert "[3]" in out
            assert "[4]" in out
            assert "[5]" in out
            assert "[6]" not in out
            assert "Reinstall all" in out
            assert "Select specific tools" in out
            assert "Type a number, tool names, or 'all':" in out

    def test_scenario_a_header(self):
        """All scenarios start with 'What would you like to do?'."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["render-action-menu", "--input", input_file])
            assert result.returncode == 0, result.stderr
            lines = result.stdout.strip().split("\n")
            assert lines[0].strip() == "<verbatim>"
            assert lines[1].strip() == "What would you like to do?"

    def test_cli_requires_input(self):
        """render-action-menu requires --input argument."""
        result = _run(["render-action-menu"])
        assert result.returncode != 0


# ============================================================
# resolve-action subcommand
# ============================================================


class TestResolveAction:
    """resolve-action subcommand tests."""

    def test_scenario_a_option_1_select_specific(self):
        """Scenario A option 1: select specific tools."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "1"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "select_specific"

    def test_scenario_a_option_2_install_standard(self):
        """Scenario A option 2: install all standard tools."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "2"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # Should include alpha-tool and beta-tool (standard, non-excluded)
            assert "alpha-tool" in data["tools"]
            assert "beta-tool" in data["tools"]
            # Should NOT include optional gamma-tool
            assert "gamma-tool" not in data["tools"]
            # Should NOT include excluded zeta-excluded
            assert "zeta-excluded" not in data["tools"]

    def test_scenario_a_option_3_edit_standard(self):
        """Scenario A option 3: edit standard."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "3"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "edit_standard"

    def test_scenario_b_option_1_select_specific(self):
        """Scenario B option 1: select specific tools."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "1"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "select_specific"

    def test_scenario_b_option_2_fix_attention(self):
        """Scenario B option 2: fix/update tools needing attention."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "2"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # Tools needing attention: beta-tool (update), delta-tool (adopted)
            assert "beta-tool" in data["tools"]
            assert "delta-tool" in data["tools"]
            # Should NOT include current or available
            assert "alpha-tool" not in data["tools"]
            assert "gamma-tool" not in data["tools"]

    def test_scenario_b_option_3_attention_plus_missing(self):
        """Scenario B option 3: fix/update + install missing standard."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "3"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # Attention tools: beta-tool, delta-tool
            # Missing standard: gamma-tool (available + standard)
            assert "beta-tool" in data["tools"]
            assert "delta-tool" in data["tools"]
            assert "gamma-tool" in data["tools"]
            # NOT current, NOT optional
            assert "alpha-tool" not in data["tools"]
            assert "epsilon-optional" not in data["tools"]

    def test_scenario_b_option_4_missing_standard_only(self):
        """Scenario B option 4: install missing standard only."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "4"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # Only missing standard: gamma-tool
            assert "gamma-tool" in data["tools"]
            assert len(data["tools"]) == 1

    def test_scenario_b_option_5_edit_standard(self):
        """Scenario B option 5: edit standard."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "5"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "edit_standard"

    def test_scenario_b_option_6_check_capabilities(self):
        """Scenario B option 6: check capabilities."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_b_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "6"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "check_capabilities"

    def test_scenario_c_option_1_select_specific(self):
        """Scenario C option 1: select specific tools."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "1"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "select_specific"

    def test_scenario_c_option_2_remaining_standard(self):
        """Scenario C option 2: install remaining available standard."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "2"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # Only gamma-tool is available + standard
            assert "gamma-tool" in data["tools"]
            assert "delta-optional" not in data["tools"]

    def test_scenario_c_option_3_reinstall_all(self):
        """Scenario C option 3: reinstall all non-excluded tools."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "3"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            # All non-excluded tools
            assert "alpha-tool" in data["tools"]
            assert "beta-tool" in data["tools"]
            assert "gamma-tool" in data["tools"]
            assert "delta-optional" in data["tools"]

    def test_scenario_c_option_4_edit_standard(self):
        """Scenario C option 4: edit standard."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "4"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "edit_standard"

    def test_scenario_c_option_5_check_capabilities(self):
        """Scenario C option 5: check capabilities."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_c_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "5"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "check_capabilities"

    def test_non_numeric_delegates_to_resolve_tool_selection(self):
        """Non-numeric input delegates to resolve_tool_selection."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "alpha-tool"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["action"] == "install"
            assert data["tools"] == ["alpha-tool"]

    def test_invalid_menu_number_returns_error(self):
        """Invalid menu number returns error."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scenario_a_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)
            # Scenario A only has options 1-3
            result = _run(["resolve-action", "--input", input_file,
                           "--selection", "4"])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "error" in data

    def test_cli_requires_input_and_selection(self):
        """resolve-action requires both --input and --selection."""
        result = _run(["resolve-action"])
        assert result.returncode != 0


# ============================================================
# scan-status --auto-adopt flag
# ============================================================


class TestScanStatusAutoAdopt:
    """Tests for scan-status --auto-adopt flag."""

    def test_without_flag_no_auto_adopted_field(self):
        """Without --auto-adopt, output has no auto_adopted field."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            result = _run([
                "scan-status", "--source", source, "--target", target,
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "auto_adopted" not in data

    def test_with_flag_and_manifest_exists_no_adoption(self):
        """With --auto-adopt and manifest exists, no adoption happens."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Create manifest (manifest exists)
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")
            _make_manifest(target, tools={
                "my-tool": {
                    "version": "0.1.0",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                    "commands": ["my-tool.md"],
                    "source_checksums": {},
                }
            })

            result = _run([
                "scan-status", "--source", source, "--target", target,
                "--auto-adopt",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            # auto_adopted should be empty (or absent) since manifest exists
            auto = data.get("auto_adopted", [])
            assert len(auto) == 0

    def test_with_flag_no_manifest_adopts_tools(self):
        """With --auto-adopt and no manifest, adopts detected tools."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Place command file in target (pre-manifest installation)
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            result = _run([
                "scan-status", "--source", source, "--target", target,
                "--auto-adopt",
            ])
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "auto_adopted" in data
            assert "my-tool" in data["auto_adopted"]

    def test_auto_adopted_in_compact_output(self):
        """Compact stdout (--output mode) includes auto_adopted field."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)

            _make_tool(source, "my-tool")
            _make_pyproject(source)

            # Place command file for adoption
            cmd_dir = os.path.join(target, ".claude", "commands", "mg")
            os.makedirs(cmd_dir, exist_ok=True)
            with open(os.path.join(cmd_dir, "my-tool.md"), "w") as f:
                f.write("installed\n")

            output_file = os.path.join(tmp, "output.json")
            result = _run([
                "scan-status", "--source", source, "--target", target,
                "--auto-adopt", "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr
            # Check compact stdout
            compact = json.loads(result.stdout)
            assert "auto_adopted" in compact
            assert "my-tool" in compact["auto_adopted"]
            # Check full file output
            with open(output_file) as f:
                full = json.load(f)
            assert "auto_adopted" in full
            assert "my-tool" in full["auto_adopted"]


# ============================================================
# Fixtures for Phase 11 Plan 02
# ============================================================


def _make_preflight_fixture(all_passed=True, include_optional=True):
    """Create a preflight result fixture for renderer tests."""
    checks = [
        {
            "id": "python3",
            "type": "venv_python",
            "passed": True,
            "required": True,
            "version": "3.11.5",
            "error": None,
            "fix": {},
        },
        {
            "id": "git",
            "type": "command",
            "passed": True,
            "required": True,
            "version": "2.43.0",
            "error": None,
            "fix": {},
        },
    ]
    if include_optional:
        checks.extend([
            {
                "id": "lsp",
                "type": "settings_scan",
                "passed": True,
                "required": False,
                "version": "pyright-lsp",
                "error": None,
                "fix": {},
            },
            {
                "id": "ruff",
                "type": "command",
                "passed": False,
                "required": False,
                "version": None,
                "error": "Command not found: ruff",
                "fix": {"general": "pip install ruff"},
            },
        ])
        if not all_passed:
            checks[1]["passed"] = False
            checks[1]["version"] = None
            checks[1]["error"] = "Command not found: git"
            checks[1]["fix"] = {"general": "Install git"}

    return {
        "checks": checks,
        "all_passed": all_passed,
    }


def _make_install_plan_fixture():
    """Create an install plan fixture for record-result and render-summary tests."""
    return [
        {
            "tool": "alpha-tool",
            "pattern": "copy_only",
            "expected_action": "reinstalled",
            "install_cmd": 'bash ./alpha-tool/install.sh --target "/home/user/projects/road-runner/.claude"',
            "post_install": None,
            "commands": ["alpha-tool.md"],
        },
        {
            "tool": "beta-tool",
            "pattern": "copy_configure",
            "expected_action": "updated (configured)",
            "install_cmd": 'bash ./beta-tool/install.sh --target "/home/user/projects/road-runner/.claude"',
            "post_install": "beta-tool/post-install.md",
            "commands": ["beta-tool.md"],
        },
        {
            "tool": "gamma-tool",
            "pattern": "copy_only",
            "expected_action": "installed",
            "install_cmd": 'bash ./gamma-tool/install.sh --target "/home/user/projects/road-runner/.claude"',
            "post_install": None,
            "commands": ["gamma-tool.md"],
        },
    ]


def _make_install_results_fixture():
    """Create install results fixture for render-summary tests."""
    return [
        {"tool": "alpha-tool", "action": "reinstalled", "commands": ["alpha-tool.md"]},
        {"tool": "beta-tool", "action": "updated (configured)", "commands": ["beta-tool.md"]},
        {"tool": "gamma-tool", "action": "failed", "commands": []},
    ]


def _write_json_file(tmpdir, filename, data):
    """Write JSON data to a file, return the path."""
    path = os.path.join(tmpdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


# ============================================================
# _get_temp_dir utility (Phase 11 Plan 02)
# ============================================================


class TestGetTempDir:
    """Tests for per-target temp directory utility."""

    def test_output_creates_parent_directory(self):
        """--output on get-install-plan creates parent dirs."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scan_status_fixture()
            input_file = _write_scan_status_file(tmp, scan_data)

            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
                "--output", os.path.join(tmp, "subdir", "plan.json"),
            ])
            assert result.returncode == 0, result.stderr
            assert os.path.isfile(os.path.join(tmp, "subdir", "plan.json"))

    def test_handles_trailing_slash_in_target(self):
        """get-install-plan handles trailing slash in target path."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scan_status_fixture()
            scan_data["target"] = "/home/user/projects/road-runner/"
            input_file = _write_scan_status_file(tmp, scan_data)

            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
            ])
            assert result.returncode == 0, result.stderr


# ============================================================
# get-install-plan subcommand (Phase 11 Plan 02)
# ============================================================


class TestGetInstallPlan:
    """Tests for get-install-plan subcommand."""

    def test_copy_only_pattern(self):
        """Tool with install.sh and no post_install -> copy_only."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert len(plan) == 1
            assert plan[0]["pattern"] == "copy_only"
            assert plan[0]["install_cmd"] is not None
            assert plan[0]["post_install"] is None

    def test_copy_configure_pattern(self):
        """Tool with install.sh and post_install -> copy_configure."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scan_status_fixture()
            for t in scan_data["tools"]:
                if t["name"] == "beta-tool":
                    t["post_install"] = "post-install.md"
            input_file = _write_scan_status_file(tmp, scan_data)

            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "beta-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert len(plan) == 1
            assert plan[0]["pattern"] == "copy_configure"
            assert plan[0]["post_install"] == "beta-tool/post-install.md"

    def test_execute_only_pattern(self):
        """Tool without install.sh but with post_install -> execute_only."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scan_status_fixture()
            for t in scan_data["tools"]:
                if t["name"] == "gamma-tool":
                    t["has_install_sh"] = False
                    t["post_install"] = "post-install.md"
            input_file = _write_scan_status_file(tmp, scan_data)

            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "gamma-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert len(plan) == 1
            assert plan[0]["pattern"] == "execute_only"
            assert plan[0]["install_cmd"] is None
            assert plan[0]["post_install"] == "gamma-tool/post-install.md"

    def test_expected_action_available(self):
        """Available tool -> expected_action is 'installed'."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "gamma-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert plan[0]["expected_action"] == "installed"

    def test_expected_action_update(self):
        """Update tool -> expected_action is 'updated'."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "beta-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert plan[0]["expected_action"] == "updated"

    def test_expected_action_current(self):
        """Current tool -> expected_action is 'reinstalled'."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert plan[0]["expected_action"] == "reinstalled"

    def test_expected_action_with_configured_suffix(self):
        """copy_configure pattern appends ' (configured)' to action."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_data = _make_scan_status_fixture()
            for t in scan_data["tools"]:
                if t["name"] == "gamma-tool":
                    t["post_install"] = "post-install.md"
                    t["status"] = "available"
            input_file = _write_scan_status_file(tmp, scan_data)

            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "gamma-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert plan[0]["expected_action"] == "installed (configured)"

    def test_includes_commands_from_scan(self):
        """Plan includes commands list from scan-status."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert plan[0]["commands"] == ["alpha-tool.md"]

    def test_includes_install_cmd(self):
        """Plan includes install_cmd with correct path."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert "install.sh" in plan[0]["install_cmd"]
            assert "road-runner" in plan[0]["install_cmd"]

    def test_skips_unknown_tools(self):
        """Tools not in scan-status are gracefully skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "nonexistent-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert len(plan) == 0

    def test_multiple_tools(self):
        """Plan handles multiple tools in comma-separated list."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool,gamma-tool",
            ])
            assert result.returncode == 0, result.stderr
            plan = json.loads(result.stdout)
            assert len(plan) == 2
            assert plan[0]["tool"] == "alpha-tool"
            assert plan[1]["tool"] == "gamma-tool"

    def test_output_writes_file(self):
        """--output writes full plan to file and compact to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = _write_scan_status_file(tmp)
            output_file = os.path.join(tmp, "plan.json")
            result = _run([
                "get-install-plan",
                "--input", input_file,
                "--tools", "alpha-tool,beta-tool",
                "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr
            with open(output_file) as f:
                full_plan = json.load(f)
            assert len(full_plan) == 2
            assert "commands" in full_plan[0]

            compact = json.loads(result.stdout)
            assert isinstance(compact, list)
            for entry in compact:
                assert "tool" in entry
                assert "pattern" in entry


# ============================================================
# preflight --output support (Phase 11 Plan 02)
# ============================================================


class TestPreflightOutput:
    """Tests for preflight --output support."""

    def test_output_writes_file(self):
        """--output writes full result to file."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            _make_venv(target)

            _make_tool(source, "test-tool", required=["python3"])
            output_file = os.path.join(tmp, "out", "preflight.json")

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "test-tool",
                "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr
            assert os.path.isfile(output_file)

            with open(output_file) as f:
                full_result = json.load(f)
            assert "checks" in full_result
            assert "all_passed" in full_result

    def test_output_compact_stdout(self):
        """--output returns compact JSON to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            _make_venv(target)

            _make_tool(source, "test-tool", required=["python3"])
            output_file = os.path.join(tmp, "preflight.json")

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "test-tool",
                "--output", output_file,
            ])
            assert result.returncode == 0, result.stderr
            compact = json.loads(result.stdout)
            assert "all_passed" in compact
            assert "check_count" in compact
            assert "details" in compact

    def test_without_output_unchanged(self):
        """Without --output, behavior is unchanged (full JSON to stdout)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))
            _make_venv(target)

            _make_tool(source, "test-tool", required=["python3"])

            result = _run([
                "preflight",
                "--source", source,
                "--target", target,
                "--tools", "test-tool",
            ])
            assert result.returncode == 0, result.stderr
            full_result = json.loads(result.stdout)
            assert "checks" in full_result
            assert "all_passed" in full_result


# ============================================================
# render-preflight subcommand (Phase 11 Plan 02)
# ============================================================


class TestRenderPreflight:
    """Tests for render-preflight subcommand."""

    def test_pass_fail_markers(self):
        """Output shows [PASS] and [FAIL] markers."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "[PASS]" in result.stdout
            assert "[FAIL]" in result.stdout

    def test_header_line(self):
        """Output starts with 'Preflight checks:' header."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Preflight checks:" in result.stdout

    def test_required_optional_labels(self):
        """Output shows (required) and (optional) labels."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "(required)" in result.stdout
            assert "(optional)" in result.stdout

    def test_summary_counts(self):
        """Output includes Required: N/M passed."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Required: 2/2 passed" in result.stdout
            assert "Optional: 1/2 passed" in result.stdout

    def test_no_optional_line_when_no_optional(self):
        """Optional summary line is omitted when no optional checks exist."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture(include_optional=False)
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Required:" in result.stdout
            assert "Optional:" not in result.stdout

    def test_version_shown_for_passed(self):
        """Version string shown for passed checks."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "3.11.5" in result.stdout

    def test_error_shown_for_failed(self):
        """Error message shown for failed checks."""
        with tempfile.TemporaryDirectory() as tmp:
            preflight_data = _make_preflight_fixture()
            input_file = _write_json_file(tmp, "preflight.json", preflight_data)

            result = _run(["render-preflight", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Command not found: ruff" in result.stdout


# ============================================================
# record-result subcommand (Phase 11 Plan 02)
# ============================================================


class TestRecordResult:
    """Tests for record-result subcommand."""

    def test_creates_file_on_first_call(self):
        """Results file is created with first entry on first call."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = os.path.join(tmp, "results.json")
            plan_file = _write_json_file(tmp, "plan.json", _make_install_plan_fixture())

            result = _run([
                "record-result",
                "--file", results_file,
                "--tool", "alpha-tool",
                "--success",
                "--plan", plan_file,
            ])
            assert result.returncode == 0, result.stderr
            assert os.path.isfile(results_file)

            with open(results_file) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["tool"] == "alpha-tool"
            assert data[0]["action"] == "reinstalled"
            assert data[0]["commands"] == ["alpha-tool.md"]

    def test_appends_on_subsequent_calls(self):
        """Subsequent calls append to existing file."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = os.path.join(tmp, "results.json")
            plan_file = _write_json_file(tmp, "plan.json", _make_install_plan_fixture())

            _run([
                "record-result",
                "--file", results_file,
                "--tool", "alpha-tool",
                "--success",
                "--plan", plan_file,
            ])
            result = _run([
                "record-result",
                "--file", results_file,
                "--tool", "beta-tool",
                "--success",
                "--plan", plan_file,
            ])
            assert result.returncode == 0, result.stderr

            with open(results_file) as f:
                data = json.load(f)
            assert len(data) == 2
            assert data[0]["tool"] == "alpha-tool"
            assert data[1]["tool"] == "beta-tool"
            assert data[1]["action"] == "updated (configured)"

    def test_failed_entry(self):
        """--failed records action as 'failed' with empty commands."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = os.path.join(tmp, "results.json")
            plan_file = _write_json_file(tmp, "plan.json", _make_install_plan_fixture())

            result = _run([
                "record-result",
                "--file", results_file,
                "--tool", "gamma-tool",
                "--failed",
                "--plan", plan_file,
            ])
            assert result.returncode == 0, result.stderr

            with open(results_file) as f:
                data = json.load(f)
            assert data[0]["action"] == "failed"
            assert data[0]["commands"] == []

    def test_success_failed_mutually_exclusive(self):
        """--success and --failed cannot be used together."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = os.path.join(tmp, "results.json")
            plan_file = _write_json_file(tmp, "plan.json", _make_install_plan_fixture())

            result = _run([
                "record-result",
                "--file", results_file,
                "--tool", "alpha-tool",
                "--success",
                "--failed",
                "--plan", plan_file,
            ])
            assert result.returncode != 0


# ============================================================
# render-summary subcommand (Phase 11 Plan 02)
# ============================================================


class TestRenderSummary:
    """Tests for render-summary subcommand."""

    def test_header_and_target(self):
        """Output includes header and target path."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "INSTALL COMPLETE" in result.stdout
            assert "road-runner" in result.stdout

    def test_summary_counts(self):
        """Output includes install/update/fail counts."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "Installed: 1" in result.stdout
            assert "Updated: 1" in result.stdout
            assert "Failed: 1" in result.stdout

    def test_tool_table(self):
        """Output includes tool names, actions, and commands."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "alpha-tool" in result.stdout
            assert "beta-tool" in result.stdout
            assert "gamma-tool" in result.stdout
            assert "reinstalled" in result.stdout
            assert "updated (configured)" in result.stdout
            assert "failed" in result.stdout

    def test_commands_in_table(self):
        """Tool table shows command filenames or '--' for failed."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "alpha-tool.md" in result.stdout
            assert "--" in result.stdout

    def test_preflight_capabilities(self):
        """With --preflight, output includes capabilities section."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)
            preflight_file = _write_json_file(tmp, "preflight.json", _make_preflight_fixture())

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
                "--preflight", preflight_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "Capabilities" in result.stdout

    def test_without_preflight(self):
        """Without --preflight, no capabilities section."""
        with tempfile.TemporaryDirectory() as tmp:
            results_file = _write_json_file(tmp, "results.json", _make_install_results_fixture())
            input_file = _write_scan_status_file(tmp)

            result = _run([
                "render-summary",
                "--results", results_file,
                "--input", input_file,
            ])
            assert result.returncode == 0, result.stderr
            assert "Capabilities" not in result.stdout


# ============================================================
# render-validation subcommand (Phase 11 Plan 02)
# ============================================================


class TestRenderValidation:
    """Tests for render-validation subcommand."""

    def test_all_passed(self):
        """Clean validation shows 'All checks passed' message."""
        with tempfile.TemporaryDirectory() as tmp:
            validate_data = {"valid": True, "issue_count": 0, "issues": []}
            input_file = _write_json_file(tmp, "validate.json", validate_data)

            result = _run(["render-validation", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Post-install validation:" in result.stdout
            assert "All checks passed" in result.stdout

    def test_with_issues(self):
        """Validation with issues shows WARNING lines."""
        with tempfile.TemporaryDirectory() as tmp:
            validate_data = {
                "valid": False,
                "issue_count": 1,
                "issues": [
                    {
                        "file": "/path/to/file.md",
                        "line": 10,
                        "type": "placeholder",
                        "pattern": "{MG_INSTALL_SCRIPTS_DIR}",
                        "message": "Unresolved placeholder: {MG_INSTALL_SCRIPTS_DIR}",
                    },
                ],
            }
            input_file = _write_json_file(tmp, "validate.json", validate_data)

            result = _run(["render-validation", "--input", input_file])
            assert result.returncode == 0, result.stderr
            assert "Post-install validation:" in result.stdout
            assert "WARNING" in result.stdout
            assert "Unresolved placeholder" in result.stdout


# ============================================================
# resolve-target subcommand
# ============================================================


class TestResolveTarget:
    """Tests for resolve-target subcommand."""

    def test_bare_name_resolves_to_sibling(self):
        """Bare name like 'myproject' resolves to ../myproject."""
        with tempfile.TemporaryDirectory() as tmp:
            sibling = os.path.join(tmp, "projects", "myproject")
            cwd = os.path.join(tmp, "projects", "mg-cc-tools")
            os.makedirs(sibling)
            os.makedirs(cwd)

            result = _run(
                ["resolve-target", "--target", "myproject"],
                cwd=cwd,
            )
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["target"] == os.path.realpath(sibling)

    def test_bare_name_not_found(self):
        """Bare name with no matching sibling returns error."""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.path.join(tmp, "projects", "mg-cc-tools")
            os.makedirs(cwd)

            result = _run(
                ["resolve-target", "--target", "nonexistent"],
                cwd=cwd,
            )
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert "error" in data
            assert "does not exist" in data["error"]

    def test_relative_path_passthrough(self):
        """Paths with '/' are used as-is."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "some", "path")
            os.makedirs(target)

            result = _run(
                ["resolve-target", "--target", target],
            )
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["target"] == os.path.realpath(target)

    def test_relative_sibling_path(self):
        """Explicit ../name also works."""
        with tempfile.TemporaryDirectory() as tmp:
            sibling = os.path.join(tmp, "projects", "myproject")
            cwd = os.path.join(tmp, "projects", "mg-cc-tools")
            os.makedirs(sibling)
            os.makedirs(cwd)

            result = _run(
                ["resolve-target", "--target", "../myproject"],
                cwd=cwd,
            )
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data["target"] == os.path.realpath(sibling)
