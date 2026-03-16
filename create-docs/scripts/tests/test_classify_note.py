"""Tests for classify-note.py -- deterministic keyword-based note classification.

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
    "classify-note.py",
)


class TestClassifyNoteAudiences:
    """Classification to correct audiences based on keywords."""

    def test_devops_classification(self):
        """Note mentioning deploy/config/server classifies to devops."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "Need to deploy the server with new config"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["audience"] == "devops"

    def test_developers_classification(self):
        """Note mentioning API/function/import/class classifies to developers."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "The API function needs a new class interface"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["audience"] == "developers"

    def test_end_users_classification(self):
        """Note mentioning click/button/user classifies to end-users."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "User can click the button to submit the form"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["audience"] == "end-users"

    def test_agents_classification(self):
        """Note mentioning path/convention/pattern classifies to agents."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "Follow the file path naming convention and pattern for directory structure"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["audience"] == "agents"


class TestClassifyNoteConfidence:
    """Confidence scoring behavior."""

    def test_ambiguous_note_low_confidence(self):
        """Ambiguous note gets confidence < 0.5."""
        # Text with keywords from all 4 audiences in similar proportions
        # deploy+server (devops), API+function (dev), click+button (end-users), path+convention (agents)
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "deploy server API function click button path convention"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["confidence"] < 0.5

    def test_clear_match_high_confidence(self):
        """Clear match with dominant audience gets confidence >= 0.7."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "deploy server config environment docker pipeline monitoring logs"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["confidence"] >= 0.7


class TestClassifyNoteOutput:
    """Output format validation."""

    def test_output_contains_all_fields(self):
        """Output includes audience, document, section, confidence fields."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "The server deployment needs configuration"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "audience" in data
        assert "document" in data
        assert "section" in data
        assert "confidence" in data
        assert isinstance(data["confidence"], (int, float))

    def test_document_maps_to_audience(self):
        """Document field maps to first document in audience's config."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "deploy server config environment docker"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["audience"] == "devops"
        assert data["document"] == "OPERATIONS"

    def test_section_defaults_to_general(self):
        """Section defaults to general."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--text", "deploy server config environment"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["section"] == "general"


class TestClassifyNoteInboxUpdate:
    """Updating note classification in inbox file."""

    def test_update_note_in_inbox(self):
        """When --note-id and --inbox provided, updates note's classification."""
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "notes-inbox.json")
            inbox_data = {"notes": [
                {"id": "NOTE-001", "text": "Deploy the server",
                 "added": "2025-01-01T00:00:00+00:00",
                 "context": {"phase": None, "file": None},
                 "classification": None, "status": "pending"},
            ]}
            with open(inbox, "w") as f:
                json.dump(inbox_data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--text", "Deploy the server",
                 "--note-id", "NOTE-001",
                 "--inbox", inbox],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(inbox) as f:
                updated = json.load(f)

            note = updated["notes"][0]
            assert note["classification"] is not None
            assert note["classification"]["audience"] == "devops"
            assert "confidence" in note["classification"]


class TestClassifyNoteMissingArgs:
    """Argument validation."""

    def test_missing_text_fails(self):
        """Missing --text causes non-zero exit."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
