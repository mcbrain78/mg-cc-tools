"""Tests for prepare-doc-review.py -- doc chunking for review.

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
    "prepare-doc-review.py",
)


def _small_doc(audience="developer"):
    """Return a small doc under any reasonable token limit."""
    return f"""# Small Doc
<!-- AUDIENCE: {audience} -->

Short introduction.

## Section One

Some content here.

## Section Two

More content here.
"""


def _large_doc(audience="agent", section_count=10, words_per_section=300):
    """Return a large doc that exceeds a low token limit."""
    lines = [
        "# Large Document",
        f"<!-- AUDIENCE: {audience} -->",
        "",
        "This is the introduction with important context.",
        "",
    ]
    for i in range(1, section_count + 1):
        lines.append(f"## Section {i}: Topic {i}")
        lines.append("")
        # Generate enough content to push over token limits
        lines.append(" ".join([f"word{j}" for j in range(words_per_section)]))
        lines.append("")
        lines.append(f"### Subsection {i}.1")
        lines.append("")
        lines.append("Subsection content that stays with parent.")
        lines.append("")
    return "\n".join(lines)


class TestPrepareDocReviewSmallFile:
    """Small file behavior -- no chunking."""

    def test_small_file_single_entry_manifest(self):
        """File under limit -> manifest points to original, no chunks written."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)

            doc_path = os.path.join(docs_dir, "SMALL.md")
            with open(doc_path, "w") as f:
                f.write(_small_doc())

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert len(manifest) == 1
            entry = manifest[0]
            assert entry["source"] == doc_path
            assert entry["review_files"] == [doc_path]
            assert entry["audience"] == "developer"

            # No chunk files should be created (only manifest.json)
            output_files = [f for f in os.listdir(output_dir) if f != "manifest.json"]
            assert len(output_files) == 0


class TestPrepareDocReviewLargeFile:
    """Large file behavior -- chunking."""

    def test_large_file_chunked_at_headings(self):
        """File over limit -> chunks split at ##, front matter prepended to each."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)

            doc_path = os.path.join(docs_dir, "SYSTEM_MAP.md")
            with open(doc_path, "w") as f:
                f.write(_large_doc())

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "500"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert len(manifest) == 1
            entry = manifest[0]
            assert entry["source"] == doc_path
            assert len(entry["review_files"]) == 10  # 10 sections

            # Each chunk should exist and contain front matter
            for chunk_path in entry["review_files"]:
                assert os.path.exists(chunk_path)
                with open(chunk_path) as f:
                    content = f.read()
                # Front matter (title + audience comment) prepended
                assert "# Large Document" in content
                assert "<!-- AUDIENCE: agent -->" in content
                # Each chunk has a ## heading
                assert "## Section" in content

    def test_chunk_respects_heading_hierarchy(self):
        """### subsections stay with their parent ## section."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)

            doc_path = os.path.join(docs_dir, "HIERARCHY.md")
            with open(doc_path, "w") as f:
                f.write(_large_doc(section_count=5))

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "500"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            # Read first chunk -- should contain ### subsection
            first_chunk = manifest[0]["review_files"][0]
            with open(first_chunk) as f:
                content = f.read()
            assert "### Subsection 1.1" in content
            assert "Subsection content that stays with parent." in content


class TestPrepareDocReviewAudience:
    """Audience detection."""

    def test_audience_detected_from_comment(self):
        """Audience field populated from <!-- AUDIENCE: ... --> comment."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)

            for aud in ["end-user", "developer", "agent", "devops"]:
                doc_path = os.path.join(docs_dir, f"{aud.upper()}.md")
                with open(doc_path, "w") as f:
                    f.write(_small_doc(audience=aud))

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            audiences = {e["audience"] for e in manifest}
            assert audiences == {"end-user", "developer", "agent", "devops"}

    def test_no_audience_comment_returns_none(self):
        """File without audience comment has audience=None in manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)

            doc_path = os.path.join(docs_dir, "PLAIN.md")
            with open(doc_path, "w") as f:
                f.write("# Plain doc\n\nNo audience comment.\n")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert manifest[0]["audience"] is None


class TestAudienceFilter:
    """--audience filter scopes which docs are included."""

    def _create_multi_audience_docs(self, docs_dir):
        """Create docs for devops, developer, and end-user audiences."""
        for aud in ["devops", "developer", "end-user"]:
            doc_path = os.path.join(docs_dir, f"{aud.upper()}.md")
            with open(doc_path, "w") as f:
                f.write(_small_doc(audience=aud))

    def test_filter_single_audience(self):
        """--audience devops includes only devops docs."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)
            self._create_multi_audience_docs(docs_dir)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000",
                 "--audience", "devops"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert len(manifest) == 1
            assert manifest[0]["audience"] == "devops"

    def test_filter_multiple_audiences(self):
        """--audience devops,end-user includes both."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)
            self._create_multi_audience_docs(docs_dir)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000",
                 "--audience", "devops,end-user"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            audiences = {e["audience"] for e in manifest}
            assert audiences == {"devops", "end-user"}

    def test_no_filter_includes_all(self):
        """Omitting --audience includes everything."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)
            self._create_multi_audience_docs(docs_dir)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert len(manifest) == 3

    def test_filter_excludes_non_matching(self):
        """devops filter excludes developer docs."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)
            self._create_multi_audience_docs(docs_dir)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000",
                 "--audience", "devops"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            audiences = {e["audience"] for e in manifest}
            assert "developer" not in audiences
            assert "end-user" not in audiences

    def test_filter_includes_shared_docs_without_audience_tag(self):
        """Docs with no AUDIENCE comment (shared docs) are included when filtering."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(docs_dir)
            self._create_multi_audience_docs(docs_dir)

            # Add a shared doc with no audience tag (like GLOSSARY)
            glossary_path = os.path.join(docs_dir, "GLOSSARY.md")
            with open(glossary_path, "w") as f:
                f.write("# Glossary\n\nNo audience comment.\n\n## Terms\n\nSome terms.\n")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "5000",
                 "--audience", "devops"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            sources = {os.path.basename(e["source"]) for e in manifest}
            assert "GLOSSARY.md" in sources
            assert "DEVOPS.md" in sources
            assert "DEVELOPER.md" not in sources


class TestPrepareDocReviewManifest:
    """Manifest structure."""

    def test_manifest_structure(self):
        """Verify JSON shape matches expected schema."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            subdir = os.path.join(docs_dir, "agents")
            output_dir = os.path.join(tmp, "chunks")
            os.makedirs(subdir)

            # One small, one large
            small_path = os.path.join(docs_dir, "SMALL.md")
            with open(small_path, "w") as f:
                f.write(_small_doc())

            large_path = os.path.join(subdir, "BIG.md")
            with open(large_path, "w") as f:
                f.write(_large_doc())

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--docs-dir", docs_dir,
                 "--output-dir", output_dir,
                 "--token-limit", "500"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            assert isinstance(manifest, list)
            assert len(manifest) == 2

            for entry in manifest:
                assert "source" in entry
                assert "audience" in entry
                assert "review_files" in entry
                assert isinstance(entry["review_files"], list)
                assert len(entry["review_files"]) >= 1
