"""Tests for add-verify-finding.py -- validate and append verify findings.

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
    "add-verify-finding.py",
)


def _valid_finding():
    """Return a valid finding dict with all 6 required fields."""
    return {
        "document": "OPERATIONS",
        "section": "deployment-pipeline",
        "audience": "devops",
        "check": "reference-integrity",
        "description": "File path src/deploy/old-pipeline.sh referenced in section does not exist",
        "suggestion": "Update reference to src/deploy/pipeline.sh (renamed in commit abc1234)",
    }


class TestAddVerifyFindingBasic:
    """Core append and validation behavior."""

    def test_valid_finding_appends_to_empty_file(self):
        """Valid finding with all 7 required fields appends to empty findings file, creates file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["document"] == "OPERATIONS"
            assert data[0]["section"] == "deployment-pipeline"
            assert data[0]["check"] == "reference-integrity"

    def test_valid_finding_appends_to_existing_array(self):
        """Valid finding appends to existing findings array (3 entries -> 4 entries)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            # Seed with 3 existing findings
            existing = [_valid_finding() for _ in range(3)]
            with open(findings_file, "w") as f:
                json.dump(existing, f)

            new_finding = _valid_finding()
            new_finding["document"] = "ARCHITECTURE"
            new_finding["section"] = "overview"
            with open(input_file, "w") as f:
                json.dump(new_finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert len(data) == 4
            assert data[3]["document"] == "ARCHITECTURE"

    def test_confirmation_message_on_stderr(self):
        """Confirmation message printed to stderr with document and check type."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "OPERATIONS" in result.stderr
            assert "deployment-pipeline" in result.stderr
            assert "reference-integrity" in result.stderr


class TestAddVerifyFindingRejection:
    """Invalid input rejection with .rejected files."""

    def test_missing_required_field_rejects(self):
        """Missing required field (e.g., no 'section') exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            del finding["section"]
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "reason" in rejected
            assert "section" in rejected["reason"]

    def test_invalid_check_rejects(self):
        """Invalid check value (e.g., 'spelling') exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["check"] = "spelling"
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "check" in rejected["reason"].lower()

    def test_invalid_json_in_input_rejects(self):
        """Invalid JSON in --input file exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                f.write("{not valid json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)


EDITORIAL_CHECKS = [
    # Universal (7)
    "filler-content", "heading-content-mismatch",
    "dangling-prose-reference",
    "unexplained-code-block", "internal-contradiction",
    "malformed-table", "placeholder-content",
    # End-user (4)
    "end-user-jargon", "end-user-missing-expected-result",
    "end-user-implementation-leak", "end-user-missing-goal",
    # Developer (3)
    "developer-abstract-architecture", "developer-missing-types",
    "developer-adr-missing-alternatives",
    # Agent (3)
    "agent-ambiguous-constraint", "agent-missing-negative-examples",
    "agent-missing-consequences",
    # DevOps (3)
    "devops-missing-expected-output", "devops-missing-rollback",
    "devops-placeholder-in-command",
    # Shared (1)
    "overview-missing-audience",
]

FACT_CHECKER_CHECKS = [
    "code-example-fact-check",
    "data-model-fact-check",
    "cross-doc-inconsistency",
]

MALFORMED_REF_CHECKS = [
    "malformed-ref-unresolved",
]


class TestAddVerifyFindingEditorialChecks:
    """Editorial check types accepted by add-verify-finding.py."""

    def test_all_editorial_checks_accepted(self):
        """Each of the 22 editorial check types is accepted (exit code 0)."""
        for check in EDITORIAL_CHECKS:
            with tempfile.TemporaryDirectory() as tmp:
                findings_file = os.path.join(tmp, "findings.json")
                input_file = os.path.join(tmp, "input.json")

                finding = _valid_finding()
                finding["check"] = check
                with open(input_file, "w") as f:
                    json.dump(finding, f)

                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH,
                     "--input", input_file,
                     "--findings-file", findings_file],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0, (
                    f"Editorial check '{check}' rejected: {result.stderr}"
                )

                with open(findings_file) as f:
                    data = json.load(f)
                assert len(data) == 1
                assert data[0]["check"] == check


class TestAddVerifyFindingFactCheckerChecks:
    """Fact-checker check types accepted by add-verify-finding.py."""

    def test_all_fact_checker_checks_accepted(self):
        """Each of the 3 fact-checker check types is accepted (exit code 0)."""
        for check in FACT_CHECKER_CHECKS:
            with tempfile.TemporaryDirectory() as tmp:
                findings_file = os.path.join(tmp, "findings.json")
                input_file = os.path.join(tmp, "input.json")

                finding = _valid_finding()
                finding["check"] = check
                with open(input_file, "w") as f:
                    json.dump(finding, f)

                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH,
                     "--input", input_file,
                     "--findings-file", findings_file],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0, (
                    f"Fact-checker check '{check}' rejected: {result.stderr}"
                )

                with open(findings_file) as f:
                    data = json.load(f)
                assert len(data) == 1
                assert data[0]["check"] == check


class TestAddVerifyFindingMalformedRefChecks:
    """Malformed ref check types accepted by add-verify-finding.py."""

    def test_malformed_ref_unresolved_accepted(self):
        """The malformed-ref-unresolved check type is accepted (exit code 0)."""
        for check in MALFORMED_REF_CHECKS:
            with tempfile.TemporaryDirectory() as tmp:
                findings_file = os.path.join(tmp, "findings.json")
                input_file = os.path.join(tmp, "input.json")

                finding = _valid_finding()
                finding["check"] = check
                with open(input_file, "w") as f:
                    json.dump(finding, f)

                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH,
                     "--input", input_file,
                     "--findings-file", findings_file],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0, (
                    f"Malformed ref check '{check}' rejected: {result.stderr}"
                )

                with open(findings_file) as f:
                    data = json.load(f)
                assert len(data) == 1
                assert data[0]["check"] == check


class TestAddVerifyFindingNormalization:
    """Document normalization and group_id computation."""

    def test_md_extension_stripped(self):
        """Input with document: 'OPERATIONS.md' → stored as 'OPERATIONS'."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["document"] = "OPERATIONS.md"
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["document"] == "OPERATIONS"

    def test_document_without_md_unchanged(self):
        """Input with document: 'OPERATIONS' (no .md) → stored unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["document"] == "OPERATIONS"

    def test_group_id_always_present(self):
        """Every finding has group_id = '{document}/{section}'."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["group_id"] == "OPERATIONS/deployment-pipeline"

    def test_group_id_uses_normalized_document(self):
        """group_id uses the normalized (stripped) document name."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["document"] = "ARCHITECTURE.md"
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["document"] == "ARCHITECTURE"
            assert data[0]["group_id"] == "ARCHITECTURE/deployment-pipeline"

    def test_singular_audience_normalized_to_plural(self):
        """Singular audience values are normalized to plural config keys."""
        cases = [
            ("end-user", "end-users"),
            ("developer", "developers"),
            ("agent", "agents"),
        ]
        for singular, expected_plural in cases:
            with tempfile.TemporaryDirectory() as tmp:
                findings_file = os.path.join(tmp, "findings.json")
                input_file = os.path.join(tmp, "input.json")

                finding = _valid_finding()
                finding["audience"] = singular
                with open(input_file, "w") as f:
                    json.dump(finding, f)

                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH,
                     "--input", input_file,
                     "--findings-file", findings_file],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0, f"Failed for {singular}: {result.stderr}"

                with open(findings_file) as f:
                    data = json.load(f)

                assert data[0]["audience"] == expected_plural, (
                    f"Expected '{expected_plural}' but got '{data[0]['audience']}' for input '{singular}'"
                )

    def test_plural_audience_unchanged(self):
        """Plural audience values pass through unchanged."""
        for audience in ["end-users", "developers", "agents", "devops", "shared", "all"]:
            with tempfile.TemporaryDirectory() as tmp:
                findings_file = os.path.join(tmp, "findings.json")
                input_file = os.path.join(tmp, "input.json")

                finding = _valid_finding()
                finding["audience"] = audience
                with open(input_file, "w") as f:
                    json.dump(finding, f)

                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH,
                     "--input", input_file,
                     "--findings-file", findings_file],
                    capture_output=True, text=True,
                )
                assert result.returncode == 0

                with open(findings_file) as f:
                    data = json.load(f)

                assert data[0]["audience"] == audience


class TestAddVerifyFindingCLI:
    """CLI argument validation."""

    def test_no_input_and_no_inline_fails(self):
        """No --input and no inline args exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_findings_file_arg_fails(self):
        """Missing --findings-file arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0


class TestAddVerifyFindingInlineMode:
    """Inline CLI args mode (no temp file needed)."""

    def _inline_args(self, finding=None, **overrides):
        """Build inline CLI args list from a finding dict."""
        f = finding or _valid_finding()
        f.update(overrides)
        args = []
        for key in ["document", "section", "audience", "check",
                     "description", "suggestion"]:
            if key in f:
                args.extend([f"--{key}", f[key]])
        return args

    def test_inline_appends_to_empty_file(self):
        """Inline args create finding and append to new findings file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args()],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"

            with open(findings_file) as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["document"] == "OPERATIONS"
            assert data[0]["section"] == "deployment-pipeline"
            assert data[0]["check"] == "reference-integrity"
            assert data[0]["group_id"] == "OPERATIONS/deployment-pipeline"

    def test_inline_appends_to_existing(self):
        """Inline args append to existing findings array."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            # Seed with 2 existing findings
            existing = [_valid_finding() for _ in range(2)]
            with open(findings_file, "w") as f:
                json.dump(existing, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args(document="GLOSSARY",
                                    section="system-concepts")],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert len(data) == 3
            assert data[2]["document"] == "GLOSSARY"

    def test_inline_missing_field_fails(self):
        """Inline mode with missing field exits with code 2."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            # Omit --suggestion
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--section", "deployment",
                 "--audience", "devops",
                 "--check", "reference-integrity",
                 "--description", "test"],
                capture_output=True, text=True,
            )
            assert result.returncode == 2
            assert "suggestion" in result.stderr

    def test_inline_invalid_check_fails(self):
        """Inline mode with invalid check type exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args(check="spelling")],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_inline_normalizes_document(self):
        """Inline mode strips .md from document name."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args(document="OPERATIONS.md")],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["document"] == "OPERATIONS"

    def test_inline_normalizes_audience(self):
        """Inline mode normalizes singular audience to plural."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args(audience="developer")],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["audience"] == "developers"

    def test_inline_confirmation_on_stderr(self):
        """Inline mode prints confirmation to stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args()],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "OPERATIONS" in result.stderr
            assert "reference-integrity" in result.stderr


class TestAddVerifyFindingWave:
    """Wave metadata field."""

    def test_wave_stored_when_provided_inline(self):
        """--wave N stores wave field in finding."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--section", "monitoring",
                 "--audience", "devops",
                 "--check", "dangling-prose-reference",
                 "--description", "test",
                 "--suggestion", "fix it",
                 "--wave", "2"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["wave"] == 2

    def test_wave_absent_when_not_provided(self):
        """Without --wave, finding has no wave field."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--section", "monitoring",
                 "--audience", "devops",
                 "--check", "dangling-prose-reference",
                 "--description", "test",
                 "--suggestion", "fix it"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert "wave" not in data[0]

    def test_wave_stored_in_file_mode(self):
        """Wave field in file-mode JSON is preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["wave"] = 3
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["wave"] == 3

    def test_wave_zero(self):
        """--wave 0 stores wave=0 (used by clearing step)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--section", "monitoring",
                 "--audience", "devops",
                 "--check", "reference-integrity",
                 "--description", "test",
                 "--suggestion", "fix it",
                 "--wave", "0"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert data[0]["wave"] == 0


class TestAddVerifyFindingSuppression:
    """Suppress-file integration."""

    def _inline_args(self, finding=None, **overrides):
        f = finding or _valid_finding()
        f.update(overrides)
        args = []
        for key in ["document", "section", "audience", "check",
                     "description", "suggestion"]:
            if key in f:
                args.extend([f"--{key}", f[key]])
        return args

    def test_suppressed_finding_skipped(self):
        """Finding matching suppress entry is not written."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            suppress_file = os.path.join(tmp, "suppressed.json")

            with open(suppress_file, "w") as f:
                json.dump([{
                    "section": "deployment-pipeline",
                    "check": "dangling-prose-reference",
                    "entity": "Failed",
                }], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--suppress-file", suppress_file,
                 "--entity", "Failed",
                 *self._inline_args(
                     check="dangling-prose-reference",
                     description="Prose mentions `Failed` without ref",
                 )],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Suppressed:" in result.stderr

            # No findings written
            assert not os.path.exists(findings_file) or (
                json.load(open(findings_file)) == []
            )

    def test_non_matching_suppress_still_writes(self):
        """Finding not matching suppress entry is written normally."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            suppress_file = os.path.join(tmp, "suppressed.json")

            with open(suppress_file, "w") as f:
                json.dump([{
                    "section": "other-section",
                    "check": "dangling-prose-reference",
                    "entity": "Failed",
                }], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--suppress-file", suppress_file,
                 "--entity", "Failed",
                 *self._inline_args(
                     check="dangling-prose-reference",
                     description="Prose mentions `Failed` without ref",
                 )],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Suppressed:" not in result.stderr

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1

    def test_no_suppress_file_writes_normally(self):
        """Without --suppress-file, finding is written normally."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--entity", "etl_runs",
                 *self._inline_args()],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1

    def test_suppress_without_entity_writes_normally(self):
        """With --suppress-file but no --entity, finding is written."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            suppress_file = os.path.join(tmp, "suppressed.json")

            with open(suppress_file, "w") as f:
                json.dump([{
                    "section": "deployment-pipeline",
                    "check": "dangling-prose-reference",
                    "entity": "Failed",
                }], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--suppress-file", suppress_file,
                 *self._inline_args()],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1


class TestAddVerifyFindingEntityPersistence:
    """Inline --entity and file-mode entity field round-trip into the record."""

    def _inline_args(self, **overrides):
        f = _valid_finding()
        f.update(overrides)
        args = []
        for key in ["document", "section", "audience", "check",
                    "description", "suggestion"]:
            args.extend([f"--{key}", f[key]])
        return args

    def test_inline_entity_persists_in_record(self):
        """Inline --entity is written onto the appended finding."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--entity", "etl_runs",
                 *self._inline_args(
                     check="dangling-prose-reference",
                     description="Prose mentions `etl_runs` without ref",
                 )],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["entity"] == "etl_runs"

    def test_file_mode_preserves_existing_entity(self):
        """File-mode finding with entity pre-set keeps the field."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            payload = _valid_finding()
            payload["check"] = "dangling-prose-reference"
            payload["entity"] = "FMPRateLimitError"
            with open(input_file, "w") as f:
                json.dump(payload, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["entity"] == "FMPRateLimitError"

    def test_no_entity_omits_field(self):
        """Without --entity and no entity in input, field is not synthesized."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 *self._inline_args()],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr

            with open(findings_file) as f:
                data = json.load(f)
            assert len(data) == 1
            assert "entity" not in data[0]
