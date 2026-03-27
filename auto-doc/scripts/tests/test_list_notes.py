"""Tests for list-notes.py -- note query/filter script.

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
    "list-notes.py",
)


def _write_inbox(tmp, notes):
    """Write a notes-inbox.json and return its path."""
    inbox_path = os.path.join(tmp, "notes-inbox.json")
    with open(inbox_path, "w", encoding="utf-8") as f:
        json.dump({"notes": notes}, f)
    return inbox_path


def _run(inbox_path, output_path, audience=None, document=None):
    """Run list-notes.py with given args."""
    cmd = [
        sys.executable, SCRIPT_PATH,
        "--inbox", inbox_path,
        "--output", output_path,
    ]
    if audience:
        cmd.extend(["--audience", audience])
    if document:
        cmd.extend(["--document", document])
    return subprocess.run(cmd, capture_output=True, text=True)


SAMPLE_NOTES = [
    {
        "note_id": "NOTE-001",
        "text": "Document the auth flow",
        "status": "pending",
        "classification": {
            "audience": "developers",
            "document": "ARCHITECTURE",
            "section": "auth-flow",
            "confidence": 0.85,
        },
    },
    {
        "note_id": "NOTE-002",
        "text": "Add CLI flags reference",
        "status": "integrated",
        "classification": {
            "audience": "end-users",
            "document": "USER_GUIDE",
            "section": "getting-started",
            "confidence": 0.72,
        },
    },
    {
        "note_id": "NOTE-003",
        "text": "Deployment rollback steps",
        "status": "pending",
        "classification": {
            "audience": "devops",
            "document": "OPERATIONS",
            "section": "deployment",
            "confidence": 0.90,
        },
    },
    {
        "note_id": "NOTE-004",
        "text": "Unclassified note",
        "status": "pending",
        "classification": None,
    },
    {
        "note_id": "NOTE-005",
        "text": "Another dev note",
        "status": "pending",
        "classification": {
            "audience": "developers",
            "document": "DEVELOPER_GUIDE",
            "section": "setup",
            "confidence": 0.65,
        },
    },
]


class TestListNotes:
    """list-notes.py filtering tests."""

    def test_all_classified_notes(self):
        """No filters returns all classified notes (excludes null classification)."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path)
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert len(notes) == 4  # NOTE-004 excluded (null classification)
            note_ids = [n["note_id"] for n in notes]
            assert "NOTE-004" not in note_ids

    def test_filter_by_audience(self):
        """Filter by audience returns only matching notes."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path, audience="developers")
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert len(notes) == 2
            note_ids = {n["note_id"] for n in notes}
            assert note_ids == {"NOTE-001", "NOTE-005"}

    def test_filter_by_document(self):
        """Filter by document returns only matching notes."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path, document="OPERATIONS")
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert len(notes) == 1
            assert notes[0]["note_id"] == "NOTE-003"

    def test_filter_by_audience_and_document(self):
        """Combined filters return intersection."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(
                inbox_path, output_path,
                audience="developers", document="ARCHITECTURE",
            )
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert len(notes) == 1
            assert notes[0]["note_id"] == "NOTE-001"

    def test_no_match_returns_empty(self):
        """Filters with no match return empty array."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path, audience="agents")
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert notes == []

    def test_missing_inbox_returns_empty(self):
        """Missing inbox file returns empty array."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = os.path.join(tmp, "nonexistent.json")
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path)
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert notes == []

    def test_ignores_status_field(self):
        """Status field is ignored -- both pending and integrated notes returned."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, SAMPLE_NOTES)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path)
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            # NOTE-002 has status "integrated" but should still be returned
            note_ids = [n["note_id"] for n in notes]
            assert "NOTE-002" in note_ids

    def test_empty_inbox(self):
        """Empty notes array returns empty result."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, [])
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path)
            assert result.returncode == 0

            with open(output_path) as f:
                notes = json.load(f)

            assert notes == []

    def test_notes_without_classification_key(self):
        """Notes missing classification key entirely are excluded."""
        notes = [
            {"note_id": "NOTE-001", "text": "No classification key", "status": "pending"},
            {
                "note_id": "NOTE-002",
                "text": "Has classification",
                "status": "pending",
                "classification": {
                    "audience": "developers",
                    "document": "ARCHITECTURE",
                    "section": "overview",
                    "confidence": 0.8,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = _write_inbox(tmp, notes)
            output_path = os.path.join(tmp, "output.json")

            result = _run(inbox_path, output_path)
            assert result.returncode == 0

            with open(output_path) as f:
                filtered = json.load(f)

            assert len(filtered) == 1
            assert filtered[0]["note_id"] == "NOTE-002"
