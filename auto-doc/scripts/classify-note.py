#!/usr/bin/env python3
"""Classify a note into audience/document/section with confidence score.

Deterministic keyword-based classification. Counts keyword matches per
audience category and picks the top scorer. Confidence is derived from
the ratio of top score to second-best score.

Usage:
    python3 classify-note.py --text "Deploy the server with new config"
    python3 classify-note.py --text "Deploy..." --note-id NOTE-001 --inbox inbox.json

Output (stdout):
    {"audience": "devops", "document": "OPERATIONS", "section": "general", "confidence": 0.85}

If --note-id and --inbox are provided, also updates the note's classification
in the inbox file.

Zero external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

# Keyword dictionaries mapping terms to audiences.
# Each keyword is matched case-insensitively as a word boundary pattern.
AUDIENCE_KEYWORDS = {
    "devops": [
        "deploy", "server", "config", "environment", "docker", "k8s",
        "ci", "cd", "pipeline", "monitoring", "logs", "restart", "scale",
        "terraform", "ansible", "nginx", "port", "ssl", "certificate",
        "uptime",
    ],
    "developers": [
        "api", "function", "class", "import", "module", "interface",
        "type", "return", "async", "callback", "error handling",
        "refactor", "dependency", "package", "library", "test", "mock",
        "stub",
    ],
    "end-users": [
        "click", "button", "user", "login", "signup", "dashboard",
        "settings", "profile", "navigate", "menu", "page", "screen",
        "form", "submit", "download", "install", "start", "guide",
        "tutorial",
    ],
    "agents": [
        "path", "convention", "pattern", "file", "directory", "structure",
        "naming", "format", "rule", "constraint", "invariant", "absolute",
        "frontmatter", "schema",
    ],
}

# Map audience to first document (most likely default document).
AUDIENCE_DOCUMENT_MAP = {
    "devops": "OPERATIONS",
    "developers": "ARCHITECTURE",
    "end-users": "USER_GUIDE",
    "agents": "SYSTEM_MAP",
}


def count_keyword_matches(text, keywords):
    """Count how many keywords appear in text (case-insensitive).

    Multi-word keywords (e.g. 'error handling') are matched as substrings.
    Single-word keywords are matched as substrings too for simplicity.
    """
    text_lower = text.lower()
    count = 0
    for kw in keywords:
        if kw.lower() in text_lower:
            count += 1
    return count


def classify(text):
    """Classify text into audience/document/section/confidence.

    Returns a dict with audience, document, section, confidence.
    """
    scores = {}
    for audience, keywords in AUDIENCE_KEYWORDS.items():
        matches = count_keyword_matches(text, keywords)
        # Normalize by category size for fair comparison
        scores[audience] = matches / len(keywords) if keywords else 0

    # Sort by score descending
    sorted_audiences = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_audience, top_score = sorted_audiences[0]
    second_score = sorted_audiences[1][1] if len(sorted_audiences) > 1 else 0

    # Compute confidence based on dominance of top score over all others
    total_score = sum(s for _, s in sorted_audiences)
    if top_score == 0:
        # No keywords matched at all -- very low confidence
        confidence = 0.1
    elif total_score > top_score:
        # Multiple audiences have scores -- confidence is how dominant the top is
        confidence = top_score / total_score
    else:
        # Only one audience matched -- high confidence
        confidence = 0.9

    # Round to 2 decimal places
    confidence = round(confidence, 2)

    document = AUDIENCE_DOCUMENT_MAP.get(top_audience, "OVERVIEW")
    section = "general"

    return {
        "audience": top_audience,
        "document": document,
        "section": section,
        "confidence": confidence,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Classify a note into audience/document/section"
    )
    parser.add_argument(
        "--text", required=True,
        help="Note text to classify"
    )
    parser.add_argument(
        "--inbox", default=None,
        help="Path to notes-inbox.json (optional, for updating note)"
    )
    parser.add_argument(
        "--note-id", default=None,
        help="Note ID to update in inbox (requires --inbox)"
    )

    args = parser.parse_args()

    classification = classify(args.text)

    # Output classification to stdout
    print(json.dumps(classification, indent=2))

    # If note-id and inbox provided, update the note's classification
    if args.note_id and args.inbox:
        inbox_path = os.path.abspath(args.inbox)
        inbox = load_json(inbox_path)
        if inbox and "notes" in inbox:
            for note in inbox["notes"]:
                if note["note_id"] == args.note_id:
                    note["classification"] = classification
                    break
            save_json(inbox_path, inbox)
            print(f"Updated classification for {args.note_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
