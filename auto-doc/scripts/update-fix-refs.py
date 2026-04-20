#!/usr/bin/env python3
"""Update refs in edit XML files via validated add/remove operations.

Routes all ref modifications through _parse_refs() / _build_refs_xml()
to ensure canonical form, preventing silent data loss at merge time.

Usage:
    python3 update-fix-refs.py --edit-file PATH --section PATH --add '<xml/>'
    python3 update-fix-refs.py --edit-file PATH --section PATH --remove '<xml/>'

One operation per call. Always writes canonical XML.
"""

import argparse
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.ref_validation import _DB_CHAIN, _REQUIRED_FIELDS, ref_has_identifier
from lib.xml_doc import _build_refs_xml, _parse_refs

from lxml import etree


# ---------------------------------------------------------------------------
# Canonical form helpers
# ---------------------------------------------------------------------------

def _strip_formatting_whitespace(el):
    """Remove whitespace-only text/tail so pretty_print controls formatting.

    When lxml parses existing XML, inter-element whitespace is stored as
    .text/.tail properties.  A freshly built element has none.  Stripping
    these before serializing makes both produce identical pretty_print output.
    """
    if el.text and not el.text.strip():
        el.text = None
    if el.tail and not el.tail.strip():
        el.tail = None
    for child in el:
        _strip_formatting_whitespace(child)


def _serialize_refs_el(refs_el):
    """Serialize a <refs> element to a normalized string for comparison.

    Deep-copies and strips parsed whitespace first so that elements
    read from disk compare equal to freshly built canonical elements.
    """
    el = deepcopy(refs_el)
    _strip_formatting_whitespace(el)
    return etree.tostring(el, encoding="unicode", pretty_print=True).strip()


def _build_canonical_refs_el(refs_el):
    """Parse then rebuild a <refs> element in canonical form."""
    flat = _parse_refs(refs_el)
    new_refs = etree.Element("refs")
    _build_refs_xml(new_refs, flat)
    return new_refs


def is_canonical(refs_el):
    """Check whether a <refs> element is in canonical form.

    Returns True if the element matches what _parse_refs → _build_refs_xml
    would produce, or if refs are empty.
    """
    if refs_el is None or len(refs_el) == 0:
        return True
    original = _serialize_refs_el(refs_el)
    canonical = _serialize_refs_el(_build_canonical_refs_el(refs_el))
    return original == canonical


def _check_tamper(refs_el):
    """Return None if canonical, or an error message if tampered."""
    if is_canonical(refs_el):
        return None
    original = _serialize_refs_el(refs_el)
    canonical = _serialize_refs_el(_build_canonical_refs_el(refs_el))
    return (
        "<refs> was modified directly. Use this script to modify refs.\n"
        f"Current:\n{original}\n\nExpected canonical form:\n{canonical}"
    )


# ---------------------------------------------------------------------------
# Format hints
# ---------------------------------------------------------------------------

_FORMAT_HINTS = {
    "db": (
        '<db name="DB"/>                                       (bare db)\n'
        'or <db name="DB"><schema name="SCHEMA"/></db>            (schema-only)\n'
        'or <db name="DB"><schema name="S"><table name="T"/></schema></db>\n'
        'or full chain: <db name="DB"><schema name="SCHEMA">'
        '<table name="TABLE"><column>COL</column></table>'
        "</schema></db>"
    ),
    "code": (
        '<code><function name="NAME" module="PATH"/></code>\n'
        'or <code><class name="NAME"><attr>ATTR</attr></class></code>\n'
        'or <code><variable name="NAME" module="PATH"/></code>  (module-level constant)'
    ),
    "flow": "<flow>NAME</flow>",
    "env": "<env>NAME</env>",
    "config": "<config>PATH</config>",
    "enum": '<enum class="CLASS" field="FIELD"><value>VAL</value></enum>',
    "dep": "<dep>NAME</dep>",
    "literal": "<literal>NAME</literal>",
    "ext": "<ext>NAME</ext>",
}


def _format_hint(outer_tag):
    """Return a format hint for the given ref type tag."""
    return _FORMAT_HINTS.get(
        outer_tag, f"Unknown ref type: {outer_tag}",
    )


# ---------------------------------------------------------------------------
# Snippet parsing
# ---------------------------------------------------------------------------

def _parse_snippet(xml_snippet):
    """Parse an XML snippet by wrapping in <refs> and calling _parse_refs.

    Returns (flat_refs, error_message). On success error_message is None.
    """
    wrapped = f"<refs>{xml_snippet}</refs>"
    try:
        refs_el = etree.fromstring(wrapped)
    except etree.XMLSyntaxError as e:
        return None, f"Invalid XML: {e}"

    flat = _parse_refs(refs_el)
    if not flat:
        try:
            snippet_el = etree.fromstring(xml_snippet)
            outer_tag = snippet_el.tag
        except Exception:
            outer_tag = None

        hint = _format_hint(outer_tag) if outer_tag else (
            "Could not determine ref type from snippet"
        )
        return None, (
            f"Snippet parsed to 0 refs — format not recognized.\n"
            f"Expected format for <{outer_tag}>: {hint}\n"
            f"See typed-refs-format.md for full specification."
        )

    return flat, None


# ---------------------------------------------------------------------------
# Ref summary (for user-facing messages)
# ---------------------------------------------------------------------------

def _ref_summary(ref):
    """One-line summary of a ref dict."""
    ref_type = ref.get("type", "?")
    if ref_type == "db":
        parts = [ref.get("db", ""), ref.get("schema", ""), ref.get("table", "")]
        col = ref.get("column")
        if col:
            parts.append(col)
        parts = [p for p in parts if p]
        return f"db:{'.'.join(parts)}"
    elif ref_type == "code":
        kind = ref.get("kind", "")
        name = ref.get("name", "")
        module = ref.get("module", "")
        s = f"code:{kind}:{name}"
        if module:
            s += f" ({module})"
        return s
    elif ref_type in ("flow", "env", "dep", "literal", "ext"):
        return f"{ref_type}:{ref.get('name', '')}"
    elif ref_type == "config":
        return f"config:{ref.get('path', '')}"
    elif ref_type == "enum":
        cls = ref.get("class", "")
        field = ref.get("field", "")
        value = ref.get("value", "")
        return f"enum:{cls}.{field}={value}"
    return f"{ref_type}:{ref}"


# ---------------------------------------------------------------------------
# Core: rebuild refs in canonical form
# ---------------------------------------------------------------------------

def _rebuild_refs(section_el, old_refs_el, flat_refs):
    """Replace the <refs> element with canonical form from flat refs."""
    new_refs = etree.Element("refs")
    _build_refs_xml(new_refs, flat_refs)

    idx = list(section_el).index(old_refs_el)
    section_el.remove(old_refs_el)
    section_el.insert(idx, new_refs)


# ---------------------------------------------------------------------------
# Main operation
# ---------------------------------------------------------------------------

def update_fix_refs(edit_file, section_path, add_snippet=None, remove_snippet=None):
    """Add or remove a ref in an edit XML file.

    Args:
        edit_file: Path to the edit XML file.
        section_path: Section path (matches path= or slug= attribute).
        add_snippet: XML snippet to add (mutually exclusive with remove).
        remove_snippet: XML snippet to remove.

    Returns:
        Success message string.

    Raises:
        SystemExit on validation errors.
    """
    if not os.path.isfile(edit_file):
        print(f"Error: edit file not found: {edit_file}", file=sys.stderr)
        sys.exit(1)

    parser = etree.XMLParser(strip_cdata=False)
    tree = etree.parse(edit_file, parser)
    root = tree.getroot()

    # Find section by path attribute (fall back to slug)
    section_el = None
    for sec in root.findall("section"):
        sec_path = sec.get("path") or sec.get("slug", "")
        if sec_path == section_path:
            section_el = sec
            break

    if section_el is None:
        available = [
            s.get("path") or s.get("slug", "")
            for s in root.findall("section")
        ]
        print(
            f"Error: section '{section_path}' not found in edit file.\n"
            f"Available sections: {', '.join(available)}",
            file=sys.stderr,
        )
        sys.exit(1)

    refs_el = section_el.find("refs")
    if refs_el is None:
        refs_el = etree.SubElement(section_el, "refs")

    # Tamper check
    tamper_err = _check_tamper(refs_el)
    if tamper_err:
        print(f"Error: {tamper_err}", file=sys.stderr)
        sys.exit(1)

    existing_flat = _parse_refs(refs_el)

    if add_snippet:
        new_flat, err = _parse_snippet(add_snippet)
        if err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)

        # Validate required fields
        for ref in new_flat:
            if not ref_has_identifier(ref):
                ref_type = ref.get("type", "unknown")
                if ref_type == "db":
                    required = _DB_CHAIN
                else:
                    required = _REQUIRED_FIELDS.get(ref_type, ())
                present = {
                    k: v for k, v in ref.items() if k != "type" and v
                }
                print(
                    f"Error: ref missing required fields.\n"
                    f"Type: {ref_type}\n"
                    f"Required: {', '.join(required)}\n"
                    f"Present: {present}",
                    file=sys.stderr,
                )
                sys.exit(1)

        combined = existing_flat + new_flat
        _rebuild_refs(section_el, refs_el, combined)
        tree.write(
            edit_file, xml_declaration=True, encoding="utf-8", pretty_print=True,
        )

        names = [_ref_summary(r) for r in new_flat]
        return f"Added {len(new_flat)} ref(s): {', '.join(names)}"

    elif remove_snippet:
        remove_flat, err = _parse_snippet(remove_snippet)
        if err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)

        remaining = list(existing_flat)
        removed = []
        for to_remove in remove_flat:
            found = False
            for i, existing in enumerate(remaining):
                if existing == to_remove:
                    remaining.pop(i)
                    removed.append(to_remove)
                    found = True
                    break
            if not found:
                current = "\n".join(
                    f"  - {_ref_summary(r)}" for r in existing_flat
                )
                print(
                    f"Error: ref not found for removal: "
                    f"{_ref_summary(to_remove)}\n"
                    f"Current refs:\n{current or '  (none)'}",
                    file=sys.stderr,
                )
                sys.exit(1)

        _rebuild_refs(section_el, refs_el, remaining)
        tree.write(
            edit_file, xml_declaration=True, encoding="utf-8", pretty_print=True,
        )

        names = [_ref_summary(r) for r in removed]
        return f"Removed {len(removed)} ref(s): {', '.join(names)}"

    print("Error: specify --add or --remove", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Update refs in edit XML via validated add/remove operations",
    )
    parser.add_argument("--edit-file", required=True)
    parser.add_argument("--section", required=True)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", metavar="XML", help="XML snippet to add")
    group.add_argument("--remove", metavar="XML", help="XML snippet to remove")

    args = parser.parse_args()

    result = update_fix_refs(
        args.edit_file, args.section,
        add_snippet=args.add, remove_snippet=args.remove,
    )
    print(result)


if __name__ == "__main__":
    main()
