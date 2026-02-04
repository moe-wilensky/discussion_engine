# AI Agent Operating Protocols: Little Camp Slocan

## 0. Prime Directives
0. **Key Consideration:** All code changes MUST improve maintainability and organization. Always remove code/content made obsolete, unnecessary or duplicate by your changes.
  best option: remvoe code thats casuing the issue
  next best option: reuse existing code to resolve the isse
  last option: add LOC to resolve the isue.

1. **Autonomy:** Solve problems independently. Only ask for clarification if critical blocker (missing credential, ambiguous business requirement) prevents progress.
2. **Testing:** add comprehensive tsting and ensure all tests pass before completing response
3. **testing outputs:** Do not force tests to pass for broken or non-existent code by removing, skipping, or stubbing them out. If a test fails because the underlying code is incorrect or missing, do not modify the test to accommodate the failure. Instead, either identify the necessary architectural changes or implement the fix directly in the codebase.
3. **Output:** minimize none code outptu such as dcuementinos, md files, readmes etc. 

## Enforce Structural Parity:
  Maintain exact string matching for all data identifiers (CSV headers, JSON keys, Django context keys, and database fields) across the stack. To prevent "silent failures" in Django templates or crashes in Numba-optimized logic, follow this hierarchy:

    Reuse over Rename: Always prioritize existing names found in data sources or models.py.

    Centralize Shared Keys: If a key is used in >2 files (e.g., a GIS attribute used in a script, a view, and a template), define it in a constants.py file or a clearly labeled # Global Keys block at the top of the primary logic file.

    Verify Before Execution: Before generating code, cross-reference the consumer (Template/View) with the producer (Script/Model) to ensure 1:1 parity. Never alias or normalize names (e.g., changing lat to latitude) unless explicitly instructed.
