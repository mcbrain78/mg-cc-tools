"""Record which document files a generate run actually wrote.

auto-doc-generate used to answer "which files were created" with a glob over the
docs directory. A glob cannot answer it: in update mode the docs directory is
already full of the previous run's output, so the glob reports files this run
never touched, and it stays silent about a document whose writer died because the
stale copy is still sitting there.

The information is not missing, it is just held by the wrong party. The two
scripts that write documents -- write-section.py --finalize and
assemble-markdown.py -- each know the exact path at the moment they write it. This
module is where they put it, so the report is emitted by the code doing the work
instead of inferred afterwards from the filesystem.

One entry per path, with a `stages` list rather than one row per write, because
both writers touch the same file in sequence: finalize assembles it from the
accumulated sections, then assemble-markdown rewrites it from the XML once refs
are resolved. A document showing `["finalize"]` alone is therefore a real signal
-- assembly did not complete for it -- and that distinction is lost if the two
writes are collapsed or recorded separately.

Read-modify-write with no locking is deliberate: writer AGENTS run in parallel,
but finalize and assemble are invoked by the orchestrator sequentially, after all
agents have returned. Nothing else holds this file open.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.json_io import load_json, save_json  # noqa: E402


def _empty():
    return {"documents": []}


def read(ledger_path):
    """Return the ledger, or an empty one if this run has not written anything.

    A malformed ledger degrades to empty rather than raising. This file is a
    reporting artifact: a torn copy left by a killed run must not be able to abort
    the writer that is trying to append to it, because that would turn a lost
    summary line into a lost document.
    """
    try:
        data = load_json(ledger_path, default=None)
    except (json.JSONDecodeError, OSError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        return _empty()
    return data


def record(ledger_path, doc_path, stage, audience=None, document=None,
           sections=None):
    """Note that `stage` wrote `doc_path`. Idempotent per (path, stage).

    `sections` is kept from the most recent stage that reported one, so the
    number in the report is the one describing the file as it now stands.
    """
    if not ledger_path:
        return
    ledger = read(ledger_path)
    abs_path = os.path.abspath(doc_path)

    for entry in ledger["documents"]:
        if entry.get("path") == abs_path:
            if stage not in entry.setdefault("stages", []):
                entry["stages"].append(stage)
            # A later stage may know a path's audience/document when an earlier
            # one did not, so fill gaps without overwriting what is already set.
            if audience is not None and not entry.get("audience"):
                entry["audience"] = audience
            if document is not None and not entry.get("document"):
                entry["document"] = document
            if sections is not None:
                entry["sections"] = sections
            break
    else:
        ledger["documents"].append({
            "path": abs_path,
            "audience": audience or "",
            "document": document or "",
            "stages": [stage],
            "sections": sections,
        })

    save_json(ledger_path, ledger)
