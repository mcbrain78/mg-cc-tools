#!/usr/bin/env python3
"""Unused dependency analysis for codebase-health pipeline.

Parses dependency manifests and searches for actual usage of each declared
dependency via import statements, CLI usage in scripts, and config references.

Classifies each dependency as: used, unused, or uncertain.

Usage:
    python3 unused-deps.py --root <path> --output <path> [--ignore-file <path>]

Zero external dependencies — stdlib only.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, walk_source_files, ALL_SOURCE_EXTENSIONS

# ---------------------------------------------------------------------------
# Known package-name → import-name mappings
# ---------------------------------------------------------------------------

# Packages whose import name differs from the pip/npm package name
PYTHON_ALIASES: Dict[str, List[str]] = {
    "pillow": ["PIL"],
    "beautifulsoup4": ["bs4"],
    "python-dateutil": ["dateutil"],
    "pyyaml": ["yaml"],
    "scikit-learn": ["sklearn"],
    "opencv-python": ["cv2"],
    "opencv-python-headless": ["cv2"],
    "python-dotenv": ["dotenv"],
    "pymongo": ["pymongo", "bson", "gridfs"],
    "attrs": ["attr", "attrs"],
    "python-magic": ["magic"],
    "python-multipart": ["multipart"],
    "pyjwt": ["jwt"],
    "python-jose": ["jose"],
    "msgpack-python": ["msgpack"],
    "ruamel.yaml": ["ruamel"],
    "google-cloud-storage": ["google.cloud.storage"],
    "google-cloud-bigquery": ["google.cloud.bigquery"],
    "google-auth": ["google.auth"],
    "protobuf": ["google.protobuf"],
    "grpcio": ["grpc"],
    "websocket-client": ["websocket"],
    "python-rapidjson": ["rapidjson"],
    "ujson": ["ujson"],
    "orjson": ["orjson"],
    "aiohttp": ["aiohttp"],
    "httpx": ["httpx"],
    "requests": ["requests"],
    "flask": ["flask"],
    "django": ["django"],
    "fastapi": ["fastapi"],
    "uvicorn": ["uvicorn"],
    "gunicorn": ["gunicorn"],
    "celery": ["celery"],
    "redis": ["redis"],
    "sqlalchemy": ["sqlalchemy"],
    "alembic": ["alembic"],
    "psycopg2": ["psycopg2"],
    "psycopg2-binary": ["psycopg2"],
    "mysqlclient": ["MySQLdb"],
    "python-telegram-bot": ["telegram"],
    "slack-sdk": ["slack_sdk", "slack"],
    "anthropic": ["anthropic"],
    "openai": ["openai"],
    "langchain": ["langchain"],
    "tiktoken": ["tiktoken"],
    "transformers": ["transformers"],
    "torch": ["torch"],
    "tensorflow": ["tensorflow", "tf"],
    "numpy": ["numpy", "np"],
    "pandas": ["pandas", "pd"],
    "matplotlib": ["matplotlib", "plt"],
    "scipy": ["scipy"],
    "pytest": ["pytest", "_pytest"],
    "pytest-cov": ["pytest_cov"],
    "pytest-asyncio": ["pytest_asyncio"],
    "pytest-mock": ["pytest_mock"],
    "mypy": ["mypy"],
    "black": ["black"],
    "ruff": ["ruff"],
    "isort": ["isort"],
    "flake8": ["flake8"],
    "pylint": ["pylint"],
    "coverage": ["coverage"],
    "tox": ["tox"],
    "sphinx": ["sphinx"],
    "mkdocs": ["mkdocs"],
    "pre-commit": ["pre_commit"],
    "setuptools": ["setuptools", "pkg_resources"],
    "wheel": ["wheel"],
    "twine": ["twine"],
    "build": ["build"],
}

NODE_ALIASES: Dict[str, List[str]] = {
    "@types/node": [],  # Type-only, no runtime import
    "@types/react": [],
    "@types/jest": [],
    "typescript": ["ts"],
    "ts-node": ["ts-node"],
    "eslint": ["eslint"],
    "prettier": ["prettier"],
    "jest": ["jest"],
    "mocha": ["mocha"],
    "chai": ["chai"],
    "webpack": ["webpack"],
    "vite": ["vite"],
    "rollup": ["rollup"],
    "esbuild": ["esbuild"],
    "tailwindcss": ["tailwindcss"],
    "autoprefixer": ["autoprefixer"],
    "postcss": ["postcss"],
    "nodemon": ["nodemon"],
    "concurrently": ["concurrently"],
    "cross-env": ["cross-env"],
    "dotenv": ["dotenv"],
    "rimraf": ["rimraf"],
}


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def _parse_package_json(path: str) -> List[dict]:
    """Parse package.json for dependencies."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return deps

    for section, is_dev in [("dependencies", False), ("devDependencies", True),
                             ("peerDependencies", False), ("optionalDependencies", False)]:
        for name in data.get(section, {}):
            deps.append({
                "name": name,
                "manifest": os.path.basename(path),
                "is_dev": is_dev,
                "ecosystem": "node",
            })
    return deps


def _parse_requirements_txt(path: str) -> List[dict]:
    """Parse requirements.txt for dependencies."""
    deps = []
    is_dev = "dev" in os.path.basename(path).lower()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Extract package name (before any version specifier)
                name = re.split(r"[>=<!\[;@\s]", line)[0].strip()
                if name:
                    deps.append({
                        "name": name,
                        "manifest": os.path.basename(path),
                        "is_dev": is_dev,
                        "ecosystem": "python",
                    })
    except OSError:
        pass
    return deps


def _parse_pyproject_toml(path: str) -> List[dict]:
    """Parse pyproject.toml for dependencies (basic regex, no toml lib)."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps

    # Match dependencies = [...] sections
    in_deps = False
    in_dev = False
    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()
            in_deps = "dependencies" in section
            in_dev = "dev" in section or "optional" in section or "test" in section
            continue

        if in_deps and stripped and not stripped.startswith("#"):
            # Handle both `name = "version"` and `"name>=version"` styles
            if "=" in stripped and not stripped.startswith('"'):
                name = stripped.split("=")[0].strip().strip('"').strip("'")
            elif stripped.startswith('"') or stripped.startswith("'"):
                raw = stripped.strip('",\' ')
                name = re.split(r"[>=<!\[;@\s]", raw)[0].strip()
            else:
                name = re.split(r"[>=<!\[;@\s]", stripped)[0].strip()

            if name and not name.startswith("["):
                deps.append({
                    "name": name,
                    "manifest": "pyproject.toml",
                    "is_dev": in_dev,
                    "ecosystem": "python",
                })

    return deps


def _parse_setup_py(path: str) -> List[dict]:
    """Parse setup.py for install_requires (regex-based, best effort)."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps

    # Look for install_requires=[...] and extras_require={...}
    for m in re.finditer(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL):
        for dep in re.findall(r'["\']([^"\']+)["\']', m.group(1)):
            name = re.split(r"[>=<!\[;@\s]", dep)[0].strip()
            if name:
                deps.append({
                    "name": name,
                    "manifest": "setup.py",
                    "is_dev": False,
                    "ecosystem": "python",
                })

    for m in re.finditer(r'tests_require\s*=\s*\[(.*?)\]', content, re.DOTALL):
        for dep in re.findall(r'["\']([^"\']+)["\']', m.group(1)):
            name = re.split(r"[>=<!\[;@\s]", dep)[0].strip()
            if name:
                deps.append({
                    "name": name,
                    "manifest": "setup.py",
                    "is_dev": True,
                    "ecosystem": "python",
                })

    return deps


def _parse_pipfile(path: str) -> List[dict]:
    """Parse Pipfile for dependencies (basic, no toml lib)."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps

    in_section = False
    is_dev = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.lower()
            in_section = "packages" in section
            is_dev = "dev" in section
            continue
        if in_section and "=" in stripped and not stripped.startswith("#"):
            name = stripped.split("=")[0].strip().strip('"').strip("'")
            if name:
                deps.append({
                    "name": name,
                    "manifest": "Pipfile",
                    "is_dev": is_dev,
                    "ecosystem": "python",
                })

    return deps


def _parse_go_mod(path: str) -> List[dict]:
    """Parse go.mod for dependencies."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps

    in_require = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require and stripped == ")":
            in_require = False
            continue
        if stripped.startswith("require ") and "(" not in stripped:
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append({
                    "name": parts[1],
                    "manifest": "go.mod",
                    "is_dev": False,
                    "ecosystem": "go",
                })
        elif in_require and stripped and not stripped.startswith("//"):
            parts = stripped.split()
            if parts:
                name = parts[0]
                deps.append({
                    "name": name,
                    "manifest": "go.mod",
                    "is_dev": "// indirect" in line,
                    "ecosystem": "go",
                })

    return deps


def _parse_cargo_toml(path: str) -> List[dict]:
    """Parse Cargo.toml for dependencies (basic, no toml lib)."""
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps

    in_deps = False
    is_dev = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()
            in_deps = "dependencies" in section
            is_dev = "dev" in section or "build" in section
            continue
        if in_deps and "=" in stripped and not stripped.startswith("#"):
            name = stripped.split("=")[0].strip()
            if name and not name.startswith("["):
                deps.append({
                    "name": name,
                    "manifest": "Cargo.toml",
                    "is_dev": is_dev,
                    "ecosystem": "rust",
                })

    return deps


# ---------------------------------------------------------------------------
# Manifest discovery
# ---------------------------------------------------------------------------

MANIFEST_PARSERS = {
    "package.json": _parse_package_json,
    "requirements.txt": _parse_requirements_txt,
    "requirements-dev.txt": _parse_requirements_txt,
    "requirements_dev.txt": _parse_requirements_txt,
    "dev-requirements.txt": _parse_requirements_txt,
    "test-requirements.txt": _parse_requirements_txt,
    "pyproject.toml": _parse_pyproject_toml,
    "setup.py": _parse_setup_py,
    "Pipfile": _parse_pipfile,
    "go.mod": _parse_go_mod,
    "Cargo.toml": _parse_cargo_toml,
}


def discover_manifests(root: str) -> List[dict]:
    """Find and parse all dependency manifests at the project root."""
    all_deps = []
    for filename, parser in MANIFEST_PARSERS.items():
        path = os.path.join(root, filename)
        if os.path.isfile(path):
            all_deps.extend(parser(path))
    return all_deps


# ---------------------------------------------------------------------------
# Usage searching
# ---------------------------------------------------------------------------


def _get_import_names(dep: dict) -> List[str]:
    """Get the list of possible import names for a dependency."""
    name = dep["name"]
    ecosystem = dep["ecosystem"]
    names = []

    if ecosystem == "python":
        aliases = PYTHON_ALIASES.get(name.lower(), None)
        if aliases:
            names.extend(aliases)
        else:
            # Default: replace hyphens with underscores
            names.append(name.replace("-", "_"))
    elif ecosystem == "node":
        aliases = NODE_ALIASES.get(name, None)
        if aliases:
            names.extend(aliases)
        else:
            names.append(name)
    elif ecosystem == "go":
        # Go imports use the full module path
        names.append(name)
        # Also check the last path component
        parts = name.split("/")
        if len(parts) > 1:
            names.append(parts[-1])
    elif ecosystem == "rust":
        # Rust crate names use underscores in code
        names.append(name.replace("-", "_"))

    return names


def _search_in_source_files(
    root: str, ignore_patterns: List[str], import_names: List[str], ecosystem: str,
) -> List[str]:
    """Search source files for import/usage of given names."""
    evidence = []
    extensions = None

    if ecosystem == "python":
        extensions = {".py"}
    elif ecosystem == "node":
        extensions = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    elif ecosystem == "go":
        extensions = {".go"}
    elif ecosystem == "rust":
        extensions = {".rs"}

    for fpath in walk_source_files(root, ignore_patterns, extensions):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, IOError):
            continue

        rel = os.path.relpath(fpath, root)

        for import_name in import_names:
            if import_name in content:
                evidence.append(f"import found in {rel}")
                break

    return evidence


def _search_in_scripts_and_ci(root: str, dep_name: str) -> List[str]:
    """Search for CLI usage of a dependency in scripts, Makefiles, CI configs."""
    evidence = []
    search_files = []

    # Collect script and config files
    for pattern_path in [
        "Makefile", "makefile", "Justfile",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".github/workflows/*.yml", ".github/workflows/*.yaml",
        ".gitlab-ci.yml", "Jenkinsfile",
        "tox.ini", ".pre-commit-config.yaml",
        "package.json",  # scripts section
    ]:
        if "*" in pattern_path:
            # Glob-like — scan the directory
            dir_part = os.path.dirname(pattern_path)
            full_dir = os.path.join(root, dir_part)
            if os.path.isdir(full_dir):
                for f in os.listdir(full_dir):
                    ext = os.path.splitext(f)[1]
                    name_part = os.path.splitext(os.path.basename(pattern_path))[0]
                    if ext in (".yml", ".yaml"):
                        search_files.append(os.path.join(full_dir, f))
        else:
            full = os.path.join(root, pattern_path)
            if os.path.isfile(full):
                search_files.append(full)

    # Also check scripts/ and bin/ directories
    for script_dir in ["scripts", "bin", "script", "tools"]:
        sdir = os.path.join(root, script_dir)
        if os.path.isdir(sdir):
            for f in os.listdir(sdir):
                search_files.append(os.path.join(sdir, f))

    for fpath in search_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, IOError):
            continue

        if dep_name in content:
            rel = os.path.relpath(fpath, root)
            evidence.append(f"CLI/config reference in {rel}")

    return evidence


def _search_in_config_files(root: str, dep_name: str) -> List[str]:
    """Search config files for plugin/tool references."""
    evidence = []
    config_files = []

    for name in [
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml",
        "eslint.config.js", "eslint.config.mjs",
        ".babelrc", "babel.config.js", "babel.config.json",
        "webpack.config.js", "webpack.config.ts",
        "vite.config.js", "vite.config.ts",
        "rollup.config.js", "rollup.config.mjs",
        "jest.config.js", "jest.config.ts", "jest.config.json",
        "vitest.config.js", "vitest.config.ts",
        "tsconfig.json", "jsconfig.json",
        ".prettierrc", ".prettierrc.js", ".prettierrc.json",
        "tailwind.config.js", "tailwind.config.ts",
        "postcss.config.js", "postcss.config.cjs",
        "next.config.js", "next.config.mjs",
        "nuxt.config.js", "nuxt.config.ts",
        "pyproject.toml", "setup.cfg", "mypy.ini", ".flake8",
        "pytest.ini", "conftest.py",
    ]:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            config_files.append(path)

    for fpath in config_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, IOError):
            continue

        if dep_name in content:
            rel = os.path.relpath(fpath, root)
            evidence.append(f"config reference in {rel}")

    return evidence


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_dependency(dep: dict, evidence: List[str]) -> str:
    """Classify a dependency as used, unused, or uncertain."""
    if not evidence:
        return "unused"

    # If we have import evidence, it's used
    import_evidence = [e for e in evidence if e.startswith("import found")]
    if import_evidence:
        return "used"

    # Config/CLI references without imports → uncertain
    # (could be a build tool, plugin, or CLI-only tool)
    return "uncertain"


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def analyze(root: str, ignore_file: Optional[str] = None) -> dict:
    """Run full unused dependency analysis."""
    patterns = load_ignore_patterns(ignore_file)

    # Discover dependencies
    all_deps = discover_manifests(root)

    # Deduplicate by name+ecosystem
    seen: Set[Tuple[str, str]] = set()
    unique_deps = []
    for dep in all_deps:
        key = (dep["name"].lower(), dep["ecosystem"])
        if key not in seen:
            seen.add(key)
            unique_deps.append(dep)

    # Analyze each dependency
    results = []
    for dep in unique_deps:
        import_names = _get_import_names(dep)

        evidence = []

        # Search source files for imports
        if import_names:
            evidence.extend(
                _search_in_source_files(root, patterns, import_names, dep["ecosystem"])
            )

        # Search scripts and CI for CLI usage
        evidence.extend(_search_in_scripts_and_ci(root, dep["name"]))

        # Search config files for plugin/tool references
        evidence.extend(_search_in_config_files(root, dep["name"]))

        classification = classify_dependency(dep, evidence)

        results.append({
            "name": dep["name"],
            "ecosystem": dep["ecosystem"],
            "manifest": dep["manifest"],
            "is_dev": dep["is_dev"],
            "classification": classification,
            "import_names_checked": import_names,
            "evidence": evidence[:10],  # Cap evidence to keep output manageable
        })

    # Summary
    by_classification = {"used": 0, "unused": 0, "uncertain": 0}
    for r in results:
        by_classification[r["classification"]] += 1

    return {
        "summary": {
            "total_dependencies": len(results),
            "by_classification": by_classification,
        },
        "dependencies": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze unused dependencies in a codebase"
    )
    parser.add_argument(
        "--root", required=True, help="Project root directory"
    )
    parser.add_argument(
        "--output", required=True, help="Output JSON file path"
    )
    parser.add_argument(
        "--ignore-file", default=None, help="Path to .health-ignore file"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Auto-detect .health-ignore if not specified (lives in .health-scan/)
    if args.ignore_file is None:
        default_ignore = os.path.join(root, ".health-scan", ".health-ignore")
        if os.path.isfile(default_ignore):
            args.ignore_file = default_ignore

    result = analyze(root, args.ignore_file)

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Print summary to stderr
    s = result["summary"]["by_classification"]
    print(f"Analyzed {result['summary']['total_dependencies']} dependencies: "
          f"{s['used']} used, {s['unused']} unused, {s['uncertain']} uncertain",
          file=sys.stderr)


if __name__ == "__main__":
    main()
