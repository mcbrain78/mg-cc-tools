"""Tests for add-note.py -- atomic note append to notes-inbox.json.

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
    "add-note.py",
)


class TestAddNoteBasic:
    """Core append behavior."""

    def test_append_to_empty_inbox(self):
        """Appending to empty inbox creates NOTE-001 with correct schema."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            with open(inbox, "w") as f:
                json.dump({"notes": []}, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "First test note"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(inbox) as f:
                data = json.load(f)

            assert len(data["notes"]) == 1
            note = data["notes"][0]
            assert note["id"] == "NOTE-001"
            assert note["text"] == "First test note"
            assert note["status"] == "pending"
            assert note["classification"] is None
            # ISO 8601 timestamp should contain T and timezone info
            assert "T" in note["added"]
            # Context should default to nulls
            assert note["context"]["phase"] is None
            assert note["context"]["file"] is None

    def test_sequential_id_with_existing_notes(self):
        """Appending to inbox with 3 existing notes creates NOTE-004."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            existing = {"notes": [
                {"id": "NOTE-001", "text": "one", "added": "2025-01-01T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
                {"id": "NOTE-002", "text": "two", "added": "2025-01-02T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
                {"id": "NOTE-003", "text": "three", "added": "2025-01-03T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
            ]}
            with open(inbox, "w") as f:
                json.dump(existing, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "Fourth note"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(inbox) as f:
                data = json.load(f)

            assert len(data["notes"]) == 4
            assert data["notes"][3]["id"] == "NOTE-004"

    def test_context_args_populate_context_object(self):
        """--phase and --file args populate the context object."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            with open(inbox, "w") as f:
                json.dump({"notes": []}, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "Contextual note",
                 "--phase", "01-foundation",
                 "--file", "src/main.py"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(inbox) as f:
                data = json.load(f)

            note = data["notes"][0]
            assert note["context"]["phase"] == "01-foundation"
            assert note["context"]["file"] == "src/main.py"


class TestAddNoteEdgeCases:
    """Edge cases and error handling."""

    def test_missing_inbox_arg_fails(self):
        """Missing --inbox causes non-zero exit."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--text", "No inbox"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_missing_text_arg_fails(self):
        """Missing --text causes non-zero exit."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_inbox_created_if_not_exists(self):
        """Inbox file is created if it doesn't exist (defaults to empty)."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            # File does not exist yet
            assert not os.path.exists(inbox)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "First note to new inbox"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert os.path.exists(inbox)

            with open(inbox) as f:
                data = json.load(f)

            assert len(data["notes"]) == 1
            assert data["notes"][0]["id"] == "NOTE-001"

    def test_handles_id_gaps(self):
        """Uses max+1 for IDs, not length+1 (handles gaps in numbering)."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            # Note with gap: NOTE-001 and NOTE-005 (missing 002-004)
            existing = {"notes": [
                {"id": "NOTE-001", "text": "one", "added": "2025-01-01T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
                {"id": "NOTE-005", "text": "five", "added": "2025-01-05T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
            ]}
            with open(inbox, "w") as f:
                json.dump(existing, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "After gap"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(inbox) as f:
                data = json.load(f)

            # Should be NOTE-006 (max existing 5 + 1), not NOTE-003 (length 2 + 1)
            assert data["notes"][2]["id"] == "NOTE-006"

    def test_stderr_confirmation_message(self):
        """Print confirmation to stderr with note ID and truncated text."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            with open(inbox, "w") as f:
                json.dump({"notes": []}, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--inbox", inbox,
                 "--text", "A short note"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "NOTE-001" in result.stderr
            assert "A short note" in result.stderr
