"""Utilities for working with parsed ref dicts.

Provides identifier extraction from flat ref dicts as produced by
``xml_doc.parse_xml_doc``.  The identifier is the primary name string
used for deterministic matching (clearing and Check B) in the audit
pipeline.
"""

import os


def identifier_for_ref(ref):
    """Return the primary identifier string for a ref, or *None*.

    The identifier follows the D9/D10 design rules:

    * **code** with ``attr`` → ``attr``; with ``param`` → ``param``;
      otherwise → ``name``
    * **db** with ``column`` → ``column``; otherwise → ``table``
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
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        if not schema or not table:
            return None
        column = ref.get("column", "")
        if column:
            return column
        return table

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
