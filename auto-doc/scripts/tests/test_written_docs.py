"""Tests for the written-docs ledger and its report.

The defect these replace: auto-doc-generate answered "which files did this run
create" with a glob over the docs directory. So the tests that matter most are the
update-mode ones -- a docs directory holding a previous run's output must not
contribute a single row to this run's report.
"""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
SCRIPT = os.path.join(SCRIPTS_DIR, "written-docs.py")
ASSEMBLE = os.path.join(SCRIPTS_DIR, "assemble-markdown.py")

DOC = """\
# Title

<!-- section: intro -->
## Intro

One two three four five.

<!-- section: usage -->
## Usage

Six seven eight.
"""


def _report(ledger, docs_dir=None):
    args = [sys.executable, SCRIPT, "--ledger", str(ledger)]
    if docs_dir:
        args += ["--docs-dir", str(docs_dir)]
    return subprocess.run(args, capture_output=True, text=True)


def _ledger(path, entries):
    path.write_text(json.dumps({"documents": entries}))
    return path


def _doc(docs_dir, rel, text=DOC):
    target = docs_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def _entry(path, stages=("finalize", "assemble"), audience="", document=""):
    return {
        "path": str(path),
        "audience": audience,
        "document": document,
        "stages": list(stages),
        "sections": None,
    }


class TestReport:
    def test_previous_run_files_are_absent_from_the_report(self, tmp_path):
        """The whole point: a glob would list all four, the ledger lists one."""
        docs = tmp_path / "docs"
        for rel in ("end-users/USER_GUIDE.md", "agents/SYSTEM_MAP.md",
                    "GLOSSARY.md"):
            _doc(docs, rel)
        this_run = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(this_run)])

        r = _report(ledger, docs)

        assert r.returncode == 0, r.stderr
        assert "devops/OPERATIONS.md" in r.stdout
        assert "USER_GUIDE" not in r.stdout
        assert "SYSTEM_MAP" not in r.stdout
        assert "GLOSSARY" not in r.stdout
        assert "Total: 1 files" in r.stdout

    def test_counts_sections_and_words_from_the_file(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc)])

        r = _report(ledger, docs)

        # Two <!-- section: --> markers; markers themselves excluded from words.
        assert "| 2 " in r.stdout
        assert "Total: 1 files, 2 sections" in r.stdout
        assert "<!--" not in r.stdout

    def test_paths_are_relative_to_docs_dir(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc)])

        r = _report(ledger, docs)

        assert "devops/OPERATIONS.md" in r.stdout
        assert str(tmp_path) not in r.stdout

    def test_absolute_path_kept_when_outside_docs_dir(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        stray = tmp_path / "elsewhere" / "STRAY.md"
        stray.parent.mkdir()
        stray.write_text(DOC)
        ledger = _ledger(tmp_path / "l.json", [_entry(stray)])

        r = _report(ledger, docs)

        assert str(stray) in r.stdout

    def test_empty_ledger_says_nothing_was_written(self, tmp_path):
        ledger = _ledger(tmp_path / "l.json", [])

        r = _report(ledger)

        assert r.returncode == 0
        assert "WROTE: 0 documents" in r.stdout
        assert "Generation Summary" not in r.stdout

    def test_missing_ledger_is_treated_as_nothing_written(self, tmp_path):
        r = _report(tmp_path / "never-created.json")

        assert r.returncode == 0
        assert "WROTE: 0 documents" in r.stdout

    def test_empty_ledger_warns_against_falling_back_to_the_glob(self, tmp_path):
        """The failure mode the fix exists to prevent, spelled out for the caller."""
        r = _report(_ledger(tmp_path / "l.json", []))

        assert "docs directory" in r.stdout
        assert "earlier runs" in r.stdout

    def test_finalize_only_document_is_flagged_incomplete(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc, stages=("finalize",))])

        r = _report(ledger, docs)

        assert "INCOMPLETE: 1 document(s)" in r.stdout
        assert "finalize-only" in r.stdout

    def test_complete_document_is_not_flagged(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc)])

        r = _report(ledger, docs)

        assert "INCOMPLETE" not in r.stdout

    def test_assemble_only_document_is_not_flagged(self, tmp_path):
        """XML is a document's source of truth, so re-assembling from it is fine.

        Warning here would put this report back in the business of crying wolf --
        the defect it replaced.
        """
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc, stages=("assemble",))])

        r = _report(ledger, docs)

        assert r.returncode == 0, r.stderr
        assert "INCOMPLETE" not in r.stdout
        assert "devops/OPERATIONS.md" in r.stdout

    def test_entry_with_no_stages_is_flagged(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(docs, "devops/OPERATIONS.md")
        ledger = _ledger(tmp_path / "l.json", [_entry(doc, stages=())])

        r = _report(ledger, docs)

        assert "INCOMPLETE" in r.stdout
        assert "no-stage-recorded" in r.stdout

    def test_recorded_but_deleted_file_is_reported_unreadable(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        ledger = _ledger(
            tmp_path / "l.json", [_entry(docs / "devops" / "GONE.md")]
        )

        r = _report(ledger, docs)

        assert "UNREADABLE: 1 recorded document(s)" in r.stdout
        assert "| ?" in r.stdout

    def test_rows_are_sorted_and_totals_add_up(self, tmp_path):
        docs = tmp_path / "docs"
        entries = [
            _entry(_doc(docs, "b/SECOND.md")),
            _entry(_doc(docs, "a/FIRST.md")),
        ]
        ledger = _ledger(tmp_path / "l.json", entries)

        r = _report(ledger, docs)

        assert r.stdout.index("a/FIRST.md") < r.stdout.index("b/SECOND.md")
        assert "Total: 2 files, 4 sections" in r.stdout

    def test_frontmatter_and_comments_excluded_from_word_count(self, tmp_path):
        docs = tmp_path / "docs"
        doc = _doc(
            docs, "X.md",
            text="---\ntitle: excluded words here\n---\n"
                 "<!-- also excluded -->\nreal words only\n",
        )
        ledger = _ledger(tmp_path / "l.json", [_entry(doc)])

        r = _report(ledger, docs)

        assert "Total: 1 files, 0 sections, ~3 words" in r.stdout


class TestLedgerRecording:
    """assemble-markdown.py must record only what it actually wrote."""

    def _xml(self, tmp_path, doc_name="OPERATIONS"):
        xml = tmp_path / f"{doc_name}.xml"
        # <section> elements are direct children of the root -- see
        # lib/xml_doc.parse_xml_doc, which uses root.findall("section").
        xml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<document name="{doc_name}">\n'
            "  <meta><header><![CDATA[# Title\n]]></header></meta>\n"
            '  <section slug="intro">\n'
            "    <body><![CDATA[<!-- section: intro -->\n## Intro\n\nText here.\n]]></body>\n"
            "  </section>\n"
            '  <section slug="usage">\n'
            "    <body><![CDATA[<!-- section: usage -->\n## Usage\n\nMore text.\n]]></body>\n"
            "  </section>\n"
            "</document>\n"
        )
        return xml

    def test_assemble_records_the_written_path(self, tmp_path):
        xml = self._xml(tmp_path)
        out = tmp_path / "docs" / "devops" / "OPERATIONS.md"
        ledger = tmp_path / "l.json"

        r = subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(out), "--ledger", str(ledger),
             "--audience", "devops", "--document", "OPERATIONS"],
            capture_output=True, text=True,
        )

        assert r.returncode == 0, r.stderr
        entries = json.loads(ledger.read_text())["documents"]
        assert len(entries) == 1
        assert entries[0]["path"] == str(out)
        assert entries[0]["stages"] == ["assemble"]
        assert entries[0]["audience"] == "devops"
        assert entries[0]["document"] == "OPERATIONS"

    def test_nothing_recorded_when_the_xml_is_missing(self, tmp_path):
        ledger = tmp_path / "l.json"

        r = subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(tmp_path / "nope.xml"),
             "--output", str(tmp_path / "out.md"), "--ledger", str(ledger)],
            capture_output=True, text=True,
        )

        assert r.returncode == 1
        assert not ledger.exists(), "a failed run must not claim a written file"

    def test_ledger_is_optional(self, tmp_path):
        xml = self._xml(tmp_path)
        out = tmp_path / "OPERATIONS.md"

        r = subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(out)],
            capture_output=True, text=True,
        )

        assert r.returncode == 0, r.stderr
        assert out.is_file()

    def test_document_defaults_to_the_output_basename(self, tmp_path):
        xml = self._xml(tmp_path)
        out = tmp_path / "GLOSSARY.md"
        ledger = tmp_path / "l.json"

        subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(out), "--ledger", str(ledger)],
            capture_output=True, text=True, check=True,
        )

        assert json.loads(ledger.read_text())["documents"][0]["document"] == "GLOSSARY"

    def test_two_stages_on_one_path_merge_into_one_entry(self, tmp_path):
        """finalize then assemble is the normal sequence; it is one document."""
        xml = self._xml(tmp_path)
        out = tmp_path / "OPERATIONS.md"
        ledger = tmp_path / "l.json"
        _ledger(ledger, [_entry(out, stages=("finalize",), document="OPERATIONS")])

        subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(out), "--ledger", str(ledger)],
            capture_output=True, text=True, check=True,
        )

        entries = json.loads(ledger.read_text())["documents"]
        assert len(entries) == 1
        assert entries[0]["stages"] == ["finalize", "assemble"]

    def test_re_running_assemble_does_not_duplicate_the_stage(self, tmp_path):
        xml = self._xml(tmp_path)
        out = tmp_path / "OPERATIONS.md"
        ledger = tmp_path / "l.json"
        for _ in range(2):
            subprocess.run(
                [sys.executable, ASSEMBLE, "--xml-file", str(xml),
                 "--output", str(out), "--ledger", str(ledger)],
                capture_output=True, text=True, check=True,
            )

        entries = json.loads(ledger.read_text())["documents"]
        assert len(entries) == 1
        assert entries[0]["stages"] == ["assemble"]

    def test_corrupt_ledger_is_replaced_not_crashed_on(self, tmp_path):
        xml = self._xml(tmp_path)
        ledger = tmp_path / "l.json"
        ledger.write_text("{ not json")

        r = subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(tmp_path / "OPERATIONS.md"),
             "--ledger", str(ledger)],
            capture_output=True, text=True,
        )

        assert r.returncode == 0, r.stderr
        assert len(json.loads(ledger.read_text())["documents"]) == 1

    def test_recorded_section_count_matches_what_was_assembled(self, tmp_path):
        """Guards the fixture too: a malformed XML would silently record 0."""
        xml = self._xml(tmp_path)
        out = tmp_path / "OPERATIONS.md"
        ledger = tmp_path / "l.json"

        r = subprocess.run(
            [sys.executable, ASSEMBLE, "--xml-file", str(xml),
             "--output", str(out), "--ledger", str(ledger)],
            capture_output=True, text=True,
        )

        assert r.returncode == 0, r.stderr
        assert "Assembled 2 sections" in r.stderr
        assert json.loads(ledger.read_text())["documents"][0]["sections"] == 2
        assert out.read_text().count("<!-- section:") == 2
