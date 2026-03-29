#!/usr/bin/env python3
"""Prepare documentation files for review by splitting large docs into chunks.

Large documentation files can exceed subagent Read limits. This script
splits them at ## headings, prepending front matter to each chunk, and
produces a manifest for all docs (small files get a 1-entry manifest
pointing to the original).

Usage:
    python3 prepare-doc-review.py \
        --docs-dir docs/auto-doc \
        --output-dir .mg/docs/tmp/review-chunks \
        --token-limit 5000

Dependencies: tiktoken (for token counting).
"""

import argparse
import glob
import os
import re
import sys

import tiktoken

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import save_json

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    """Count tokens using cl100k_base encoding."""
    return len(_ENCODING.encode(text))


def detect_audience(content):
    """Detect audience from <!-- AUDIENCE: ... --> comment."""
    match = re.search(r"<!--\s*AUDIENCE:\s*(\S+)\s*-->", content)
    return match.group(1) if match else None


def slugify(heading):
    """Convert a heading to a filename-safe slug."""
    text = heading.strip().lstrip("#").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50]


def split_at_headings(content):
    """Split content into front matter and ## sections.

    Returns:
        (front_matter, sections) where sections is a list of
        (heading_text, section_content) tuples.
    """
    lines = content.split("\n")
    front_matter_lines = []
    sections = []
    current_heading = None
    current_lines = []

    for line in lines:
        if re.match(r"^## ", line):
            if current_heading is not None:
                sections.append((current_heading, "\n".join(current_lines)))
            elif current_lines or front_matter_lines:
                # Everything before first ## is front matter
                front_matter_lines.extend(current_lines)
            current_heading = line
            current_lines = [line]
        else:
            if current_heading is None:
                front_matter_lines.append(line)
            else:
                current_lines.append(line)

    # Don't forget the last section
    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_lines)))

    front_matter = "\n".join(front_matter_lines)
    return front_matter, sections


def main():
    parser = argparse.ArgumentParser(
        description="Prepare doc files for review with chunking"
    )
    parser.add_argument(
        "--docs-dir", required=True,
        help="Path to docs directory to scan",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Path to write chunk files and manifest",
    )
    parser.add_argument(
        "--token-limit", type=int, default=5000,
        help="Token limit for chunking (default: 5000)",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Comma-separated audience filter (e.g., 'devops,end-users'). Only include matching docs.",
    )

    args = parser.parse_args()
    docs_dir = os.path.abspath(args.docs_dir)
    output_dir = os.path.abspath(args.output_dir)
    token_limit = args.token_limit
    audience_filter = set(re.split(r"[,\s]+", args.audience.strip())) - {""} if args.audience else None

    os.makedirs(output_dir, exist_ok=True)

    # Discover all .md files
    doc_files = sorted(glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True))

    manifest = []

    for doc_path in doc_files:
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        tokens = count_tokens(content)
        audience = detect_audience(content)

        # Skip docs that don't match the audience filter.
        # Docs with no audience tag (audience=None) are shared/cross-audience
        # (e.g. GLOSSARY) and should always be included.
        if audience_filter is not None and audience is not None and audience not in audience_filter:
            continue

        basename = os.path.splitext(os.path.basename(doc_path))[0]

        if tokens <= token_limit:
            # Small file: point to original
            manifest.append({
                "source": doc_path,
                "audience": audience,
                "review_files": [doc_path],
            })
        else:
            # Large file: split at ## headings
            front_matter, sections = split_at_headings(content)
            chunk_paths = []

            for i, (heading, section_content) in enumerate(sections, 1):
                slug = slugify(heading)
                chunk_name = f"{basename}-{i:02d}-{slug}.md"
                chunk_path = os.path.join(output_dir, chunk_name)

                # Prepend front matter to each chunk
                chunk_content = front_matter.rstrip("\n") + "\n\n" + section_content
                with open(chunk_path, "w", encoding="utf-8") as f:
                    f.write(chunk_content)

                chunk_paths.append(chunk_path)

            manifest.append({
                "source": doc_path,
                "audience": audience,
                "review_files": chunk_paths,
            })

    manifest_path = os.path.join(output_dir, "manifest.json")
    save_json(manifest_path, manifest)
    print(
        f"Prepared {len(doc_files)} docs ({sum(len(e['review_files']) for e in manifest)} review files)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
