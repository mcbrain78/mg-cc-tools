"""Validation and discharge of malformed typed refs.

Checks required fields per the canonical ref type table
(references/typed-refs-format.md). Refs that fail validation are
reclassified as type ``malformed`` so downstream consumers can handle
them explicitly.
"""


# Required fields per ref type.  If ALL required fields for a type are
# present and non-empty, the ref is valid.
_REQUIRED_FIELDS = {
    "db": ("schema", "table"),
    "code": ("kind", "name"),
    "flow": ("name",),
    "env": ("name",),
    "config": ("path",),
    "enum": ("class", "field", "value"),
    "dep": ("name",),
    "literal": ("name",),
    "ext": ("name",),
}


def ref_has_identifier(ref):
    """Check whether a ref has all required identifier fields.

    Args:
        ref: A flat ref dict with at least a ``type`` key.

    Returns:
        True if the ref has all required fields (non-empty strings),
        or if the type is unknown (don't discharge unknown types).
    """
    ref_type = ref.get("type", "")
    required = _REQUIRED_FIELDS.get(ref_type)
    if required is None:
        # Unknown type — don't discharge
        return True
    return all(ref.get(f, "").strip() for f in required)


def discharge_malformed_refs(typed_refs):
    """Reclassify refs that fail identifier validation.

    Passing refs are returned unchanged.  Failing refs get
    ``type`` set to ``"malformed"`` and ``original_type`` set to the
    original type value, with all other fields preserved.

    Args:
        typed_refs: List of flat ref dicts.

    Returns:
        New list with malformed refs reclassified.
    """
    result = []
    for ref in typed_refs:
        if ref_has_identifier(ref):
            result.append(ref)
        else:
            discharged = dict(ref)
            discharged["original_type"] = discharged.get("type", "")
            discharged["type"] = "malformed"
            result.append(discharged)
    return result
