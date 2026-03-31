"""XML document model for auto-doc structured sources.

Provides build/parse/serialize functions for the XML source format that
stores documentation sections alongside typed code references. Uses
lxml.etree for CDATA support (stdlib ElementTree cannot do CDATA).

The XML schema stores:
- Document metadata (audience, diataxis type, generated date)
- A header block (ownership comment, DIATAXIS/AUDIENCE markers, title)
- Ordered sections, each with:
  - A slug identifier
  - Typed code references (<refs>)
  - Body markdown in CDATA (includes <!-- section: slug --> marker)
"""

import os
from datetime import datetime, timezone

from lxml import etree


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_xml_doc(audience, diataxis, header, sections, title=None):
    """Build an XML document tree from section data.

    Args:
        audience: Audience key (e.g. "devops", "end-users").
        diataxis: Diataxis type (e.g. "how-to", "reference").
        header: Raw markdown header string (ownership comment, markers, title).
        sections: List of {"slug": str, "body": str} dicts, in order.
        title: Optional document title. Extracted from header if not given.

    Returns:
        lxml.etree._ElementTree ready for serialization.
    """
    root = etree.Element("document", audience=audience, diataxis=diataxis)

    # <meta>
    meta = etree.SubElement(root, "meta")
    title_el = etree.SubElement(meta, "title")
    title_el.text = title or _extract_title(header)
    generated_el = etree.SubElement(meta, "generated")
    generated_el.text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header_el = etree.SubElement(meta, "header")
    header_el.text = etree.CDATA(header)

    # <section> elements
    for sec in sections:
        section_el = etree.SubElement(root, "section", slug=sec["slug"])
        etree.SubElement(section_el, "refs")
        # refs start empty; populated by finalize when typed_refs present
        body_el = etree.SubElement(section_el, "body")
        body_el.text = etree.CDATA(sec["body"])

    return etree.ElementTree(root)


def _extract_title(header):
    """Extract the first # heading from markdown header text."""
    for line in header.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            return stripped[2:].strip()
    return ""


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def parse_xml_doc(path):
    """Parse an XML document file into a structured dict.

    Args:
        path: Path to the XML file.

    Returns:
        Dict with keys:
        - audience: str
        - diataxis: str
        - meta: {"title": str, "generated": str, "header": str}
        - sections: list of {"slug": str, "body": str, "refs": list[dict]}
    """
    tree = etree.parse(path)
    root = tree.getroot()

    meta_el = root.find("meta")
    meta = {
        "title": _text(meta_el.find("title")),
        "generated": _text(meta_el.find("generated")),
        "header": _text(meta_el.find("header")),
    }

    sections = []
    for section_el in root.findall("section"):
        slug = section_el.get("slug")
        body = _text(section_el.find("body"))
        refs = _parse_refs(section_el.find("refs"))
        sections.append({"slug": slug, "body": body, "refs": refs})

    return {
        "audience": root.get("audience"),
        "diataxis": root.get("diataxis"),
        "meta": meta,
        "sections": sections,
    }


def _text(el):
    """Return element text or empty string."""
    if el is None:
        return ""
    return el.text or ""


def _parse_refs(refs_el):
    """Parse <refs> element into a flat list of ref dicts.

    Each ref dict has a "type" key and type-specific fields matching
    the flat JSON format used by extract-refs.py.
    """
    if refs_el is None or len(refs_el) == 0:
        return []

    result = []
    for child in refs_el:
        tag = child.tag
        if tag == "db":
            result.extend(_parse_db_refs(child))
        elif tag == "code":
            result.extend(_parse_code_refs(child))
        elif tag == "flow":
            result.append({"type": "flow", "name": child.text or ""})
        elif tag == "env":
            result.append({"type": "env", "name": child.text or ""})
        elif tag == "config":
            result.append({"type": "config", "path": child.text or ""})
        elif tag == "enum":
            result.extend(_parse_enum_refs(child))
    return result


def _parse_db_refs(db_el):
    """Parse <db><schema><table><column> hierarchy into flat refs."""
    refs = []
    for schema_el in db_el.findall("schema"):
        schema_name = schema_el.get("name", "")
        for table_el in schema_el.findall("table"):
            table_name = table_el.get("name", "")
            columns = [col.text for col in table_el.findall("column") if col.text]
            if columns:
                for col in columns:
                    refs.append({
                        "type": "db",
                        "schema": schema_name,
                        "table": table_name,
                        "column": col,
                    })
            else:
                refs.append({
                    "type": "db",
                    "schema": schema_name,
                    "table": table_name,
                })
    return refs


def _parse_code_refs(code_el):
    """Parse <code><class>/<function>/<variable> hierarchy into flat refs."""
    refs = []
    for cls_el in code_el.findall("class"):
        cls_name = cls_el.get("name", "")
        attrs = [a.text for a in cls_el.findall("attr") if a.text]
        if attrs:
            for attr in attrs:
                refs.append({
                    "type": "code",
                    "kind": "class",
                    "name": cls_name,
                    "attr": attr,
                })
        else:
            refs.append({"type": "code", "kind": "class", "name": cls_name})
    for func_el in code_el.findall("function"):
        func_name = func_el.get("name", "")
        module = func_el.get("module", "")
        params = [p.text for p in func_el.findall("param") if p.text]
        ref = {"type": "code", "kind": "function", "name": func_name}
        if module:
            ref["module"] = module
        if params:
            for param in params:
                r = dict(ref)
                r["param"] = param
                refs.append(r)
        else:
            refs.append(ref)
    for var_el in code_el.findall("variable"):
        var_name = var_el.get("name", "")
        module = var_el.get("module", "")
        ref = {"type": "code", "kind": "variable", "name": var_name}
        if module:
            ref["module"] = module
        refs.append(ref)
    return refs


def _parse_enum_refs(enum_el):
    """Parse <enum class=X field=Y><value> into flat refs."""
    cls = enum_el.get("class", "")
    field = enum_el.get("field", "")
    refs = []
    for val_el in enum_el.findall("value"):
        refs.append({
            "type": "enum",
            "class": cls,
            "field": field,
            "value": val_el.text or "",
        })
    return refs


# ---------------------------------------------------------------------------
# Serialize
# ---------------------------------------------------------------------------

def serialize_xml_doc(tree, path):
    """Atomically write an XML document tree to a file.

    Uses temp file + os.replace() pattern matching lib/json_io.py.
    Creates parent directories if needed.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    tree.write(
        tmp,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=True,
    )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

def update_section_refs(tree, slug, flat_refs):
    """Replace the <refs> element for a section with structured refs.

    Args:
        tree: lxml.etree._ElementTree
        slug: Section slug to update.
        flat_refs: List of flat ref dicts (same format as extract-refs.py output).

    Returns:
        The tree (mutated in place).

    Raises:
        ValueError: If slug not found.
    """
    section_el = _find_section(tree, slug)
    old_refs = section_el.find("refs")
    if old_refs is not None:
        section_el.remove(old_refs)

    refs_el = etree.SubElement(section_el, "refs")
    _build_refs_xml(refs_el, flat_refs)

    # Move <refs> before <body>
    body_el = section_el.find("body")
    if body_el is not None:
        section_el.remove(refs_el)
        section_el.insert(list(section_el).index(body_el), refs_el)

    return tree


def update_section_body(tree, slug, new_body):
    """Replace the CDATA body for a section.

    Args:
        tree: lxml.etree._ElementTree
        slug: Section slug to update.
        new_body: New markdown body text.

    Returns:
        The tree (mutated in place).

    Raises:
        ValueError: If slug not found.
    """
    section_el = _find_section(tree, slug)
    body_el = section_el.find("body")
    if body_el is None:
        body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(new_body)
    return tree


def add_section(tree, slug, body):
    """Append a new section element to the document.

    Args:
        tree: lxml.etree._ElementTree
        slug: Section slug identifier.
        body: Markdown body text (stored as CDATA).

    Returns:
        The tree (mutated in place).
    """
    root = tree.getroot()
    section_el = etree.SubElement(root, "section", slug=slug)
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(body)
    return tree


def get_section_slugs(tree):
    """Return ordered list of section slugs in the document.

    Args:
        tree: lxml.etree._ElementTree

    Returns:
        List of slug strings in document order.
    """
    root = tree.getroot()
    return [el.get("slug") for el in root.findall("section")]


def _find_section(tree, slug):
    """Find a <section> element by slug, or raise ValueError."""
    root = tree.getroot()
    for el in root.findall("section"):
        if el.get("slug") == slug:
            return el
    raise ValueError(f"Section not found: {slug}")


def _build_refs_xml(refs_el, flat_refs):
    """Build nested XML ref elements from a flat refs list."""
    # Group refs by type, then build nested structure
    db_refs = [r for r in flat_refs if r.get("type") == "db"]
    code_refs = [r for r in flat_refs if r.get("type") == "code"]
    flow_refs = [r for r in flat_refs if r.get("type") == "flow"]
    env_refs = [r for r in flat_refs if r.get("type") == "env"]
    config_refs = [r for r in flat_refs if r.get("type") == "config"]
    enum_refs = [r for r in flat_refs if r.get("type") == "enum"]

    if db_refs:
        _build_db_xml(refs_el, db_refs)
    if code_refs:
        _build_code_xml(refs_el, code_refs)
    for ref in flow_refs:
        el = etree.SubElement(refs_el, "flow")
        el.text = ref.get("name", "")
    for ref in env_refs:
        el = etree.SubElement(refs_el, "env")
        el.text = ref.get("name", "")
    for ref in config_refs:
        el = etree.SubElement(refs_el, "config")
        el.text = ref.get("path", "")
    if enum_refs:
        _build_enum_xml(refs_el, enum_refs)


def _build_db_xml(refs_el, db_refs):
    """Build <db><schema><table><column> from flat db refs."""
    db_el = etree.SubElement(refs_el, "db")
    # Group by schema, then table
    schemas = {}
    for ref in db_refs:
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        col = ref.get("column")
        key = (schema, table)
        if key not in schemas:
            schemas[key] = []
        if col:
            schemas[key].append(col)

    # Build nested elements, grouped by schema name
    schema_groups = {}
    for (schema, table), cols in schemas.items():
        if schema not in schema_groups:
            schema_groups[schema] = []
        schema_groups[schema].append((table, cols))

    for schema_name, tables in schema_groups.items():
        schema_el = etree.SubElement(db_el, "schema", name=schema_name)
        for table_name, cols in tables:
            table_el = etree.SubElement(schema_el, "table", name=table_name)
            for col in cols:
                col_el = etree.SubElement(table_el, "column")
                col_el.text = col


def _build_code_xml(refs_el, code_refs):
    """Build <code><class>/<function>/<variable> from flat code refs."""
    code_el = etree.SubElement(refs_el, "code")

    # Group classes: collect attrs per class name
    classes = {}
    for ref in code_refs:
        if ref.get("kind") == "class":
            name = ref.get("name", "")
            if name not in classes:
                classes[name] = []
            attr = ref.get("attr")
            if attr and attr not in classes[name]:
                classes[name].append(attr)

    for cls_name, attrs in classes.items():
        cls_el = etree.SubElement(code_el, "class", name=cls_name)
        for attr in attrs:
            attr_el = etree.SubElement(cls_el, "attr")
            attr_el.text = attr

    # Group functions: collect params per (name, module)
    functions = {}
    for ref in code_refs:
        if ref.get("kind") == "function":
            name = ref.get("name", "")
            module = ref.get("module", "")
            key = (name, module)
            if key not in functions:
                functions[key] = []
            param = ref.get("param")
            if param and param not in functions[key]:
                functions[key].append(param)

    for (func_name, module), params in functions.items():
        attrs = {"name": func_name}
        if module:
            attrs["module"] = module
        func_el = etree.SubElement(code_el, "function", **attrs)
        for param in params:
            param_el = etree.SubElement(func_el, "param")
            param_el.text = param

    # Variables: simple name + optional module
    for ref in code_refs:
        if ref.get("kind") == "variable":
            name = ref.get("name", "")
            module = ref.get("module", "")
            attrs = {"name": name}
            if module:
                attrs["module"] = module
            etree.SubElement(code_el, "variable", **attrs)


def _build_enum_xml(refs_el, enum_refs):
    """Build <enum class=X field=Y><value> from flat enum refs."""
    # Group by (class, field)
    groups = {}
    for ref in enum_refs:
        key = (ref.get("class", ""), ref.get("field", ""))
        if key not in groups:
            groups[key] = []
        val = ref.get("value", "")
        if val and val not in groups[key]:
            groups[key].append(val)

    for (cls, field), values in groups.items():
        enum_el = etree.SubElement(refs_el, "enum")
        enum_el.set("class", cls)
        enum_el.set("field", field)
        for val in values:
            val_el = etree.SubElement(enum_el, "value")
            val_el.text = val
