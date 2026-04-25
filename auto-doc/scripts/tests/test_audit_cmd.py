"""Tests for audit-cmd.py gateway wrapper."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "audit-cmd.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _make_session(td, **overrides):
    """Create a session config with sensible defaults under td."""
    prose_dir = os.path.join(td, "prose-verify")
    os.makedirs(prose_dir, exist_ok=True)

    defaults = {
        "workspace": td,
        "document": "OPERATIONS",
        "audience": "devops",
        "wave": 1,
        "prose_verify_dir": prose_dir,
        "uncleared_file": os.path.join(td, "uncleared.json"),
        "findings_file": os.path.join(td, "findings.json"),
        "sections_filter": os.path.join(td, "affected-sections.json"),
        "not_entities_file": os.path.join(td, "not-entities.json"),
        "dismissed_this_run_file": os.path.join(td, "dismissed-this-run.json"),
        "protected_entities_file": os.path.join(td, "protected-entities.json"),
    }
    defaults.update(overrides)
    return _write_json(td, "session.json", defaults), defaults


def _run(session_path, subcommand, extra_args=None):
    cmd = [sys.executable, SCRIPT, "--session", session_path, subcommand]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestNextSection:
    """next-section subcommand delegates correctly."""

    def test_returns_first_section(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)

            # Set up manifest and section files
            prose_dir = sess["prose_verify_dir"]
            _write_json(
                td, "prose-verify/manifest.json",
                {"sections": ["monitoring", "deployment"]},
            )
            _write_json(
                td, "prose-verify/monitoring.json",
                {"refs_as_text": "some refs"},
            )
            _write_json(
                td, "prose-verify/deployment.json",
                {"refs_as_text": "some refs"},
            )
            _write_json(td, "affected-sections.json", ["monitoring", "deployment"])

            result = _run(session_path, "next-section")
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["done"] is False
            assert data["section"] == "monitoring"

    def test_done_when_no_sections(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "prose-verify/manifest.json", {"sections": []})
            _write_json(td, "affected-sections.json", [])

            result = _run(session_path, "next-section")
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["done"] is True


class TestGetEntities:
    """get-entities subcommand resolves uncleared_file from session."""

    def test_returns_entities_for_section(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
                {"name": "celery", "section": "monitoring"},
            ])

            result = _run(session_path, "get-entities", [
                "--section", "monitoring",
            ])
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["count"] == 2
            assert set(data["entities"]) == {"prefect", "celery"}

    def test_zero_entities(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "PORT", "section": "deployment"},
            ])

            result = _run(session_path, "get-entities", [
                "--section", "monitoring",
            ])
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["count"] == 0


class TestFileFinding:
    """file-finding subcommand resolves session paths and passes args."""

    def test_files_finding_with_session_context(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `prefect` without ref",
                "--suggestion", "Add ref: [dep] prefect",
                "--entity", "prefect",
            ])
            assert result.returncode == 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 1
            f = findings[0]
            assert f["document"] == "OPERATIONS"
            assert f["audience"] == "devops"
            assert f["section"] == "monitoring"
            assert f["check"] == "dangling-prose-reference"
            assert f["wave"] == 1

    def test_files_finding_with_entity_and_suppress(self):
        """file-finding passes --entity and --suppress-file through."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(
                td,
                suppress_file=os.path.join(td, "suppressed.json"),
            )
            _write_json(td, "findings.json", [])
            _write_json(td, "suppressed.json", [{
                "section": "monitoring",
                "check": "dangling-prose-reference",
                "entity": "Failed",
            }])

            # This finding matches the suppress entry → should be suppressed
            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `Failed` without ref",
                "--suggestion", "Third-party state",
                "--entity", "Failed",
            ])
            assert result.returncode == 0
            assert "Suppressed:" in result.stderr

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 0

    def test_dangling_prose_reference_without_entity_errors(self):
        """dangling-prose-reference without --entity exits non-zero."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `prefect` without ref",
                "--suggestion", "Add ref: [dep] prefect",
            ])
            assert result.returncode != 0
            assert "--entity" in result.stderr
            assert "dangling-prose-reference" in result.stderr

            # No finding was written
            findings = _read_json(sess["findings_file"])
            assert len(findings) == 0

    def test_dangling_prose_reference_with_entity_succeeds(self):
        """dangling-prose-reference WITH --entity succeeds normally."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `prefect` without ref",
                "--suggestion", "Add ref: [dep] prefect",
                "--entity", "prefect",
            ])
            assert result.returncode == 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 1
            assert findings[0]["check"] == "dangling-prose-reference"

    def test_non_dangling_check_without_entity_succeeds(self):
        """Non-dangling checks don't require --entity."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "internal-contradiction",
                "--description", "Contradiction found",
                "--suggestion", "Fix it",
            ])
            assert result.returncode == 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 1

    def test_files_finding_without_wave(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td, wave=None)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "internal-contradiction",
                "--description", "Contradiction found",
                "--suggestion", "Fix the contradiction",
            ])
            assert result.returncode == 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 1
            assert "wave" not in findings[0]


class TestPropagate:
    """propagate subcommand resolves session paths and passes args."""

    def test_propagates_to_other_sections(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            _write_json(td, "findings.json", [])

            result = _run(session_path, "propagate", [
                "--entity", "prefect",
                "--section", "monitoring",
                "--suggestion", "Add ref: [dep] prefect",
            ])
            assert result.returncode == 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 1
            assert findings[0]["section"] == "deployment"
            assert findings[0]["wave"] == 1

            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"


class TestFileFindingPropagateFlag:
    """file-finding --propagate chains file-finding into propagate."""

    def test_files_originating_finding_and_propagates(self):
        """One call files the originating finding AND propagates to siblings."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "deployment"},
                {"name": "prefect", "section": "alerting"},
                {"name": "PORT", "section": "deployment"},
            ])
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `prefect` without ref",
                "--suggestion", "Add ref: [dep] prefect",
                "--entity", "prefect",
                "--propagate",
            ])
            assert result.returncode == 0, result.stderr

            findings = _read_json(sess["findings_file"])
            # 1 originating + 2 propagated = 3
            assert len(findings) == 3
            sections = sorted(f["section"] for f in findings)
            assert sections == ["alerting", "deployment", "monitoring"]
            for f in findings:
                assert f["entity"] == "prefect"
                assert f["check"] == "dangling-prose-reference"

            # Uncleared retains only PORT — all `prefect` entries removed
            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_propagate_flag_requires_entity(self):
        """--propagate without --entity exits non-zero before filing."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "findings.json", [])

            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "internal-contradiction",
                "--description", "Contradiction",
                "--suggestion", "Fix it",
                "--propagate",
            ])
            assert result.returncode != 0
            assert "--propagate requires --entity" in result.stderr

            # Nothing was filed
            findings = _read_json(sess["findings_file"])
            assert len(findings) == 0

    def test_propagate_skipped_when_filing_fails(self):
        """If file-finding fails, propagate must not run."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "deployment"},
            ])
            _write_json(td, "findings.json", [])

            # Invalid check value -> add-verify-finding.py rejects it
            result = _run(session_path, "file-finding", [
                "--section", "monitoring",
                "--check", "not-a-real-check",
                "--description", "x",
                "--suggestion", "y",
                "--entity", "prefect",
                "--propagate",
            ])
            assert result.returncode != 0

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 0
            # Uncleared is untouched — propagate did not run
            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 2

    def test_propagate_with_dash_dash_entity_via_equals(self):
        """Entities starting with -- are accepted via --entity=value form."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "--run-integration", "section": "monitoring"},
                {"name": "--run-integration", "section": "deployment"},
            ])
            _write_json(td, "findings.json", [])

            cmd = [
                sys.executable, SCRIPT, "--session", session_path,
                "file-finding",
                "--section", "monitoring",
                "--check", "dangling-prose-reference",
                "--description", "Prose mentions `--run-integration` flag",
                "--suggestion", "Add ref: [config] pytest.ini",
                "--entity=--run-integration",
                "--propagate",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr

            findings = _read_json(sess["findings_file"])
            assert len(findings) == 2
            for f in findings:
                assert f["entity"] == "--run-integration"


class TestDismiss:
    """dismiss subcommand resolves session paths and passes args."""

    def test_dismisses_entity(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            _write_json(td, "dismissed-this-run.json", [])
            _write_json(td, "protected-entities.json", [])

            result = _run(session_path, "dismiss", [
                "--entity", "bash",
                "--section", "monitoring",
            ])
            assert result.returncode == 0

            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            dismissed = _read_json(sess["dismissed_this_run_file"])
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"
            assert dismissed[0]["audience"] == "devops"
            assert dismissed[0]["document"] == "OPERATIONS"

    def test_dismiss_protected_entity(self):
        """Protected entity is refused — uncleared unchanged."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "compute_hash", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            _write_json(td, "dismissed-this-run.json", [])
            _write_json(td, "protected-entities.json", [
                {"name": "compute_hash", "reason": "Project function"},
            ])

            result = _run(session_path, "dismiss", [
                "--entity", "compute_hash",
                "--section", "monitoring",
            ])
            assert result.returncode == 0
            assert "PROTECTED: compute_hash" in result.stderr

            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 2

            dismissed = _read_json(sess["dismissed_this_run_file"])
            assert len(dismissed) == 0


    def test_dismiss_covered_by_passes_through(self):
        """--covered-by passes through audit-cmd to dismiss-entity."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(
                td,
                covered_entities_file=os.path.join(td, "covered-entities.json"),
            )
            _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            _write_json(td, "dismissed-this-run.json", [])
            _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            # Create section JSON with the covering ref
            prose_dir = sess["prose_verify_dir"]
            _write_json(
                td, "prose-verify/monitoring.json",
                {
                    "body": "some body",
                    "refs_as_text": "some refs",
                    "ref_entries": [
                        {"identifier": "ResolutionAction", "display": "ResolutionAction"},
                    ],
                },
            )

            result = _run(session_path, "dismiss", [
                "--entity", "accept_new",
                "--section", "monitoring",
                "--covered-by", "ResolutionAction",
            ])
            assert result.returncode == 0
            assert "Covered: accept_new" in result.stderr

            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            # Not in dismissed-this-run
            dismissed = _read_json(sess["dismissed_this_run_file"])
            assert len(dismissed) == 0

            # Recorded in covered-entities
            covered = _read_json(sess["covered_entities_file"])
            assert len(covered) == 1
            assert covered[0]["covered_by"] == "ResolutionAction"

    def test_dismiss_covered_by_invalid_refused(self):
        """Invalid identifier through audit-cmd → refused."""
        with tempfile.TemporaryDirectory() as td:
            session_path, sess = _make_session(td)
            _write_json(td, "uncleared.json", [
                {"name": "accept_new", "section": "monitoring"},
            ])
            _write_json(td, "dismissed-this-run.json", [])
            _write_json(td, "protected-entities.json", [
                {"name": "accept_new", "reason": "Enum value"},
            ])
            # Section has different refs — ResolutionAction not present
            _write_json(
                td, "prose-verify/monitoring.json",
                {
                    "body": "some body",
                    "refs_as_text": "some refs",
                    "ref_entries": [
                        {"identifier": "SomeOtherRef", "display": "SomeOtherRef"},
                    ],
                },
            )

            result = _run(session_path, "dismiss", [
                "--entity", "accept_new",
                "--section", "monitoring",
                "--covered-by", "ResolutionAction",
            ])
            assert result.returncode == 0
            assert "Cannot dismiss accept_new" in result.stderr
            assert "--covered-by failed" in result.stderr

            uncleared = _read_json(sess["uncleared_file"])
            assert len(uncleared) == 1


class TestErrors:
    """Error handling for missing session and args."""

    def test_missing_session_file(self):
        result = _run("/tmp/nonexistent-session.json", "next-section")
        assert result.returncode != 0
        assert "session config not found" in result.stderr

    def test_missing_required_section_arg(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, _ = _make_session(td)
            result = _run(session_path, "get-entities")
            assert result.returncode != 0

    def test_missing_required_entity_arg(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, _ = _make_session(td)
            result = _run(session_path, "propagate", [
                "--section", "monitoring",
                "--suggestion", "fix",
            ])
            assert result.returncode != 0

    def test_missing_subcommand(self):
        with tempfile.TemporaryDirectory() as td:
            session_path, _ = _make_session(td)
            result = subprocess.run(
                [sys.executable, SCRIPT, "--session", session_path],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
