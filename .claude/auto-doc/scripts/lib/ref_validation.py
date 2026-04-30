"""Validation and discharge of malformed typed refs.

Checks required fields per the canonical ref type table
(references/typed-refs-format.md). Refs that fail validation are
reclassified as type ``malformed`` so downstream consumers can handle
them explicitly.
"""


# Required fields per ref type.  If ALL required fields for a type are
# present and non-empty, the ref is valid.
# Note: "db" uses chain validation (see _db_ref_valid), not this table.
_REQUIRED_FIELDS = {
    "code": ("kind", "name"),
    "flow": ("name",),
    "env": ("name",),
    "config": ("path",),
    "enum": ("class", "field", "value"),
    "dep": ("name",),
    "literal": ("name",),
    "ext": ("name",),
}

# Chain order for db refs: column requires table, table requires schema,
# schema requires db.
_DB_CHAIN = ("db", "schema", "table", "column")


def _db_ref_valid(ref):
    """Validate a db ref using chain completeness rules.

    A db ref is valid when:
    - At least one level is present and non-empty
    - The chain is contiguous: column requires table, table requires
      schema, schema requires db
    """
    # Find which levels are present and non-empty
    present = [field for field in _DB_CHAIN if ref.get(field, "").strip()]
    if not present:
        return False
    # Check contiguity: all levels from the first to the deepest must be present
    deepest_idx = max(_DB_CHAIN.index(f) for f in present)
    for i in range(deepest_idx + 1):
        if _DB_CHAIN[i] not in present:
            return False
    return True


def ref_has_identifier(ref):
    """Check whether a ref has all required identifier fields.

    Args:
        ref: A flat ref dict with at least a ``type`` key.

    Returns:
        True if the ref has all required fields (non-empty strings),
        or if the type is unknown (don't discharge unknown types).
    """
    ref_type = ref.get("type", "")
    if ref_type == "db":
        return _db_ref_valid(ref)
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
