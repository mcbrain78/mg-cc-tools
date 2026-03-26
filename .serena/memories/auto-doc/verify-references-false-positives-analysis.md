# Verify-References False Positive Analysis (road-runner)

## Problem Summary
- **17 findings** reporting **37 "undefined" symbols**
- **ALL 37 are false positives** — 100% exist in codebase
- **0 true positives** — nothing genuinely missing

## Root Cause

**NOT a bug in symbol extraction.** The issue is:

1. **Scan phase** produces `source_material_index[doc/section].source_files` (narrow list)
2. **Manifest** has `documents[doc][section].file_paths` (comprehensive list)
3. **verify-references.py** checks symbols ONLY against source_files from scan
4. When definition file is in manifest but NOT in scan's source_files → false positive

Example: `ScoredField` is in manifest but `src/road_runner/field_mapping/loader.py` (where it's defined) is not in the scan's source_files list.

## Key Files Involved

- Definition: `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/verify-references.py`
- Problem area: `check_manifest()` function, lines 187-210 (symbol verification)
- The critical line: `check_paths = scan_entry.get("source_files", [])`

## Recommended Fix: Option B

**Use manifest file_paths as fallback when source_material_index.source_files is empty/missing:**

```python
check_paths = scan_entry.get("source_files", [])
if not check_paths:
    check_paths = entry_file_paths  # Fall back to manifest
```

**Why Option B is best:**
- Fixes all 37 false positives
- Doesn't hide real issues (true positives)
- Minimal code change (isolated to verify-references.py)
- Respects manifest as a contract (symbols + files come together)
- Doesn't require scanning pipeline changes

**Alternatives rejected:**
- Option A (global symbol set): Masks hallucinations
- Option C (fix scan): Requires upstream changes, higher complexity

## Related Files Affected

All 14 unique definition files ARE in manifest file_paths:
- src/road_runner/field_mapping/loader.py
- src/road_runner/sec/sec_def14a_extractor.py
- src/road_runner/common/raw_data_readers.py
- src/road_runner/finra/client.py
- src/road_runner/llm/archive_models.py
- src/road_runner/services/drift_service.py
- src/road_runner/db/connection.py
- src/road_runner/llm/archive.py
- tests/conftest.py
- src/road_runner/finra/storage.py
- src/road_runner/flows/ingestion.py
- src/road_runner/flows/compute.py
- src/road_runner/db/models.py
- src/road_runner/config.py

## Follow-up

After implementing Option B fix:
1. Consider improving scan to explicitly document why source_files narrows manifest file_paths
2. Add tests for symbol verification with manifest fallback
3. Monitor for any real issues (true positives) that Option B might catch
