"""XML document model for auto-doc structured sources.

Provides build/parse/serialize functions for the XML source format that
stores documentation sections alongside typed code references. Uses
lxml.etree for CDATA support (stdlib ElementTree cannot do CDATA).

The XML schema stores:
- Document metadata (audience, diataxis type, generated date)
- A header block (ownership comment, DIATAXIS/AUDIENCE markers, title)
- Recursively nested sections, each with:
  - A slug identifier (unique among siblings)
  - Typed code references (<refs>)
  - Body markdown in CDATA (includes <!-- section: slug --> marker)
  - Zero or more child <section> elements (recursive nesting)

Sections mirror the markdown heading hierarchy: ## -> ### -> #### each
produce a nested <section>. A section's body contains only the prose
between its heading and the first child heading. A section's refs
declare only entities mentioned in its own body.

Path-based addressing uses slash-separated paths (e.g.
"monitoring-alerting/etl-run-logging/artifact-format") to identify
sections at any depth. Bare slugs are valid single-segment paths
for backward compatibility with top-level sections.
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
        sections: List of section dicts with keys:
            - slug: str (required)
            - body: str (required)
            - children: list of section dicts (optional, defaults to [])
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

    # <section> elements -- recursive
    for sec in sections:
        _build_section(root, sec)

    return etree.ElementTree(root)


def _build_section(parent_el, section):
    """Build a <section> XML element with refs, body, and children.

    Adds refs and body BEFORE recursing into children so element order
    is always: <refs>, <body>, then child <section> elements.

    Args:
        parent_el: Parent XML element to append the section to.
        section: Section dict with slug, body, and optional children.
    """
    section_el = etree.SubElement(parent_el, "section", slug=section["slug"])
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(section["body"])
    for child in section.get("children", []):
        _build_section(section_el, child)


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
        - sections: list of nested section dicts, each with:
            - slug: str
            - body: str
            - refs: list[dict]
            - children: list of section dicts (recursive, [] for leaves)
    """
    tree = etree.parse(path)
    root = tree.getroot()

    meta_el = root.find("meta")
    meta = {
        "title": _text(meta_el.find("title")),
        "generated": _text(meta_el.find("generated")),
        "header": _text(meta_el.find("header")),
    }

    sections = [_parse_section(el) for el in root.findall("section")]

    return {
        "audience": root.get("audience"),
        "diataxis": root.get("diataxis"),
        "meta": meta,
        "sections": sections,
    }


def _parse_section(section_el):
    """Parse a <section> element into a dict with children.

    Uses findall("section") which returns only direct children,
    ensuring each level is parsed independently.

    Args:
        section_el: lxml Element with tag "section".

    Returns:
        Dict with slug, body, refs, and children keys.
    """
    slug = section_el.get("slug")
    body = _text(section_el.find("body"))
    refs = _parse_refs(section_el.find("refs"))
    children = [_parse_section(child) for child in section_el.findall("section")]
    return {"slug": slug, "body": body, "refs": refs, "children": children}


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
        elif tag == "dep":
            result.append({"type": "dep", "name": child.text or ""})
        elif tag == "literal":
            result.append({"type": "literal", "name": child.text or ""})
        elif tag == "ext":
            result.append({"type": "ext", "name": child.text or ""})
        elif tag == "malformed":
            ref = {"type": "malformed"}
            for attr_name, attr_val in child.attrib.items():
                if attr_name == "original-type":
                    ref["original_type"] = attr_val
                else:
                    ref[attr_name] = attr_val
            result.append(ref)
    return result


def _parse_db_refs(db_el):
    """Parse <db name=X><schema><table><column> hierarchy into flat refs.

    Emits a ref at every named level in the chain: db, schema, table, column.
    """
    refs = []
    db_name = db_el.get("name", "")
    if db_name:
        refs.append({"type": "db", "db": db_name})
    for schema_el in db_el.findall("schema"):
        schema_name = schema_el.get("name", "")
        refs.append({"type": "db", "db": db_name, "schema": schema_name})
        for table_el in schema_el.findall("table"):
            table_name = table_el.get("name", "")
            refs.append({
                "type": "db", "db": db_name,
                "schema": schema_name, "table": table_name,
            })
            for col_el in table_el.findall("column"):
                if col_el.text:
                    refs.append({
                        "type": "db", "db": db_name,
                        "schema": schema_name, "table": table_name,
                        "column": col_el.text,
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
# Tree navigation
# ---------------------------------------------------------------------------

def _find_section_by_path(root, path):
    """Resolve a slash-separated section path to an XML element.

    Walks the tree level by level, matching each slug segment against
    direct child <section> elements. Returns None on miss.

    Args:
        root: XML element to start searching from (typically document root).
        path: Slash-separated path (e.g. "parent/child/grandchild").

    Returns:
        The matching <section> element, or None if any segment is missing.
    """
    node = root
    for slug in path.split("/"):
        match = None
        for child in node.findall("section"):
            if child.get("slug") == slug:
                match = child
                break
        if match is None:
            return None
        node = match
    return node


def _find_section(tree, path):
    """Find a <section> element by path, or raise ValueError.

    Wraps _find_section_by_path with error raising for mandatory lookups.

    Args:
        tree: lxml.etree._ElementTree
        path: Slash-separated section path (bare slug for top-level).

    Returns:
        The matching <section> element.

    Raises:
        ValueError: If path not found.
    """
    root = tree.getroot()
    el = _find_section_by_path(root, path)
    if el is None:
        raise ValueError(f"Section not found: {path}")
    return el


# ---------------------------------------------------------------------------
# Walk / enumerate
# ---------------------------------------------------------------------------

def walk_sections(sections, prefix=""):
    """Yield (path, section_dict) for all sections in depth-first order.

    Paths are slash-separated. Top-level sections have bare slugs as paths.
    Nested sections have paths like "parent/child/grandchild".

    Args:
        sections: List of section dicts (each with slug, body, refs, children).
        prefix: Path prefix for recursion (empty for top-level).

    Yields:
        Tuples of (path: str, section: dict).
    """
    for section in sections:
        path = f"{prefix}/{section['slug']}" if prefix else section["slug"]
        yield path, section
        yield from walk_sections(section.get("children", []), path)


def get_section_paths(tree):
    """Return ordered list of slash-separated section paths at all depths.

    Top-level sections return bare slugs. Nested sections return
    slash-separated paths (e.g. "parent/child").

    Args:
        tree: lxml.etree._ElementTree

    Returns:
        List of path strings in depth-first document order.
    """
    root = tree.getroot()
    paths = []
    _collect_paths(root, "", paths)
    return paths


def _collect_paths(parent, prefix, paths):
    """Recursively collect slash-separated paths from XML tree.

    Args:
        parent: XML element whose child sections to enumerate.
        prefix: Path prefix for current level.
        paths: Accumulator list to append paths to.
    """
    for el in parent.findall("section"):
        slug = el.get("slug")
        path = f"{prefix}/{slug}" if prefix else slug
        paths.append(path)
        _collect_paths(el, path, paths)


def get_section_slugs(tree):
    """Return ordered list of top-level section slugs in the document.

    Backward-compatibility alias. For new code, use get_section_paths()
    which returns paths at all depths.

    Args:
        tree: lxml.etree._ElementTree

    Returns:
        List of slug strings for top-level sections in document order.
    """
    root = tree.getroot()
    return [el.get("slug") for el in root.findall("section")]


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

def update_section_refs(tree, path, flat_refs):
    """Replace the <refs> element for a section with structured refs.

    Args:
        tree: lxml.etree._ElementTree
        path: Slash-separated section path (bare slug for top-level).
        flat_refs: List of flat ref dicts (same format as extract-refs.py output).

    Returns:
        The tree (mutated in place).

    Raises:
        ValueError: If path not found.
    """
    section_el = _find_section(tree, path)
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


def update_section_body(tree, path, new_body):
    """Replace the CDATA body for a section.

    Args:
        tree: lxml.etree._ElementTree
        path: Slash-separated section path (bare slug for top-level).
        new_body: New markdown body text.

    Returns:
        The tree (mutated in place).

    Raises:
        ValueError: If path not found.
    """
    section_el = _find_section(tree, path)
    body_el = section_el.find("body")
    if body_el is None:
        body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(new_body)
    return tree


def add_section(tree, slug, body, parent_path=None):
    """Append a new section element to the document or a parent section.

    Args:
        tree: lxml.etree._ElementTree
        slug: Section slug identifier.
        body: Markdown body text (stored as CDATA).
        parent_path: Optional slash-separated path to parent section.
            If None, appends to document root.

    Returns:
        The tree (mutated in place).

    Raises:
        ValueError: If parent_path is given but not found.
        ValueError: If a sibling with the same slug already exists.
    """
    root = tree.getroot()
    if parent_path:
        parent_el = _find_section_by_path(root, parent_path)
        if parent_el is None:
            raise ValueError(f"Parent section not found: {parent_path}")
    else:
        parent_el = root

    # Enforce sibling slug uniqueness
    for existing in parent_el.findall("section"):
        if existing.get("slug") == slug:
            raise ValueError(
                f"Duplicate sibling slug: {slug} already exists under "
                f"{parent_path or 'root'}"
            )

    section_el = etree.SubElement(parent_el, "section", slug=slug)
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(body)
    return tree


# ---------------------------------------------------------------------------
# Ref XML builders (internal)
# ---------------------------------------------------------------------------

def _build_refs_xml(refs_el, flat_refs):
    """Build nested XML ref elements from a flat refs list."""
    # Group refs by type, then build nested structure
    db_refs = [r for r in flat_refs if r.get("type") == "db"]
    code_refs = [r for r in flat_refs if r.get("type") == "code"]
    flow_refs = [r for r in flat_refs if r.get("type") == "flow"]
    env_refs = [r for r in flat_refs if r.get("type") == "env"]
    config_refs = [r for r in flat_refs if r.get("type") == "config"]
    enum_refs = [r for r in flat_refs if r.get("type") == "enum"]
    dep_refs = [r for r in flat_refs if r.get("type") == "dep"]
    literal_refs = [r for r in flat_refs if r.get("type") == "literal"]
    ext_refs = [r for r in flat_refs if r.get("type") == "ext"]

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
    for ref in dep_refs:
        el = etree.SubElement(refs_el, "dep")
        el.text = ref.get("name", "")
    for ref in literal_refs:
        el = etree.SubElement(refs_el, "literal")
        el.text = ref.get("name", "")
    for ref in ext_refs:
        el = etree.SubElement(refs_el, "ext")
        el.text = ref.get("name", "")

    # Malformed refs — preserve all fields as attributes
    malformed_refs = [r for r in flat_refs if r.get("type") == "malformed"]
    for ref in malformed_refs:
        attrs = {}
        for k, v in ref.items():
            if k == "type":
                continue
            if k == "original_type":
                attrs["original-type"] = str(v)
            else:
                attrs[k] = str(v)
        etree.SubElement(refs_el, "malformed", **attrs)


def _build_db_xml(refs_el, db_refs):
    """Build <db name=X><schema><table><column> from flat db refs."""
    # Determine db name from refs
    db_name = ""
    for ref in db_refs:
        if ref.get("db"):
            db_name = ref["db"]
            break

    db_el = etree.SubElement(refs_el, "db")
    if db_name:
        db_el.set("name", db_name)

    # Group by schema, then table — skip db-only and schema-only refs
    # (they exist for declaration but don't add XML children beyond
    # what the table/column refs already produce)
    schemas = {}
    for ref in db_refs:
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        if not schema:
            continue  # db-level-only ref, already handled by <db name>
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
        if table:  # skip schema-only entries
            schema_groups[schema].append((table, cols))
        elif schema not in schema_groups:
            schema_groups[schema] = []

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
