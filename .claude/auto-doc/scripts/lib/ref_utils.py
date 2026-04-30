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

    * **db** → ``(db, schema, table)`` or ``(db, schema, table, column)``
    * **code** → ``(module, name)`` plus ``attr`` or ``param``
      if present; bare ``(name,)`` when module is absent
    * **config** → ``(path,)`` (full path, not basename)
    * **flow / dep / ext / literal / env** → ``(name,)``
    * **enum** → ``(class, field, value)``
    """
    ref_type = ref.get("type", "")

    if ref_type == "malformed":
        return ()

    if ref_type == "db":
        parts = []
        db = ref.get("db", "")
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        column = ref.get("column", "")
        if db:
            parts.append(db)
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
            parts.append(module)
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
        return (path,)

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


def path_components_for_ref(ref):
    """Return all implicit path components a ref covers, as a sorted tuple.

    Combines the semantic identity path (from ``path_for_ref``) with file-path
    segments split on ``/`` for config and code refs.  Used to build the
    per-section implicit-components set for clearing prose mentions of parent
    directories, module names, and other path-prefix tokens.

    Component sources per type:

    * **db, enum** → semantic path components (already hierarchical)
    * **code** → semantic path (name, attr/param) + module path segments
    * **config** → path segments (split on ``/``); the unsplit full path is
      not retained
    * **flow, dep, env, ext, literal** → ``(name,)``
    * **malformed** → ``()``
    """
    ref_type = ref.get("type", "")
    if ref_type == "malformed":
        return ()

    components = set()

    for c in path_for_ref(ref):
        if c:
            components.add(c)

    if ref_type == "config":
        path = ref.get("path", "")
        if path:
            components.discard(path)
            for seg in path.split("/"):
                if seg:
                    components.add(seg)

    if ref_type == "code":
        module = ref.get("module", "")
        if module:
            for seg in module.split("/"):
                if seg:
                    components.add(seg)

    return tuple(sorted(components))
