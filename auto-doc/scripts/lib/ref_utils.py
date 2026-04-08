"""Utilities for working with parsed ref dicts.

Provides identifier extraction and path decomposition from flat ref dicts
as produced by ``xml_doc.parse_xml_doc``.  The identifier is the primary
name string used for deterministic matching (clearing and Check B) in the
audit pipeline.  The path tuple lists all non-empty components from root
to leaf, used by the conservative path resolver in multi-component
clearing.
"""

import os


def identifier_for_ref(ref):
    """Return the primary identifier string for a ref, or *None*.

    The identifier follows the D9/D10 design rules:

    * **code** with ``attr`` → ``attr``; with ``param`` → ``param``;
      otherwise → ``name``
    * **db** cascades ``column`` → ``table`` → ``schema`` → ``db``
    * **flow / dep / ext / literal / env** → ``name``
    * **config** → basename of ``path``
    * **enum** → ``value``
    * **malformed** → ``None`` (excluded from clearing)

    Empty-string required fields are treated as missing (returns *None*).
    """
    ref_type = ref.get("type", "")

    if ref_type == "malformed":
        return None

    if ref_type == "code":
        kind = ref.get("kind", "")
        name = ref.get("name", "")
        if not kind or not name:
            return None
        attr = ref.get("attr", "")
        if attr:
            return attr
        param = ref.get("param", "")
        if param:
            return param
        return name

    if ref_type == "db":
        # Cascade: column → table → schema → db
        column = ref.get("column", "")
        if column:
            return column
        table = ref.get("table", "")
        if table:
            return table
        schema = ref.get("schema", "")
        if schema:
            return schema
        db = ref.get("db", "")
        if db:
            return db
        return None

    if ref_type in ("flow", "dep", "ext", "literal", "env"):
        name = ref.get("name", "")
        return name or None

    if ref_type == "config":
        path = ref.get("path", "")
        if not path:
            return None
        return os.path.basename(path)

    if ref_type == "enum":
        cls = ref.get("class", "")
        field = ref.get("field", "")
        value = ref.get("value", "")
        if not cls or not field or not value:
            return None
        return value

    return None


def path_for_ref(ref):
    """Return all non-empty path components as a tuple, root to leaf.

    Used by the conservative path resolver to match entities against
    multi-component ref paths.  Returns an empty tuple for ref types
    that cannot produce meaningful components (malformed, unknown).

    Component selection per type:

    * **db** → ``(schema, table)`` or ``(schema, table, column)``
      — db name is skipped (rarely mentioned in prose)
    * **code** → ``(module_basename, name)`` plus ``attr`` or ``param``
      if present; bare ``(name,)`` when module is absent
    * **config** → ``(basename,)``
    * **flow / dep / ext / literal / env** → ``(name,)``
    * **enum** → ``(class, field, value)``
    """
    ref_type = ref.get("type", "")

    if ref_type == "malformed":
        return ()

    if ref_type == "db":
        parts = []
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        column = ref.get("column", "")
        if schema:
            parts.append(schema)
        if table:
            parts.append(table)
        if column:
            parts.append(column)
        return tuple(parts) if parts else ()

    if ref_type == "code":
        kind = ref.get("kind", "")
        name = ref.get("name", "")
        if not kind or not name:
            return ()
        parts = []
        module = ref.get("module", "")
        if module:
            # Module can be dotted (src.pipeline) or path (src/pipeline.py)
            # Use the file basename for paths, last dotted segment for modules
            if os.sep in module or "/" in module:
                parts.append(os.path.basename(module))
            else:
                parts.append(module.rsplit(".", 1)[-1])
        parts.append(name)
        attr = ref.get("attr", "")
        if attr:
            parts.append(attr)
        else:
            param = ref.get("param", "")
            if param:
                parts.append(param)
        return tuple(parts)

    if ref_type == "config":
        path = ref.get("path", "")
        if not path:
            return ()
        return (os.path.basename(path),)

    if ref_type in ("flow", "dep", "ext", "literal", "env"):
        name = ref.get("name", "")
        return (name,) if name else ()

    if ref_type == "enum":
        cls = ref.get("class", "")
        field = ref.get("field", "")
        value = ref.get("value", "")
        if not cls or not field or not value:
            return ()
        return (cls, field, value)

    return ()
