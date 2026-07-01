# Phase 8A Note: Read-only Diagnostics for Structured Table Intake

This document summarizes what was verified in Phase 8A and what remains for Phase 8B.

## What Phase 8A Proves
1. **Row & Block Detection**: We can reliably split incoming text sheets into distinct table blocks.
2. **Column Headers & Roles**: We successfully match column names (e.g. `Per Unit`, `Minimum`, `Unit`, `Charge Description`) to identify which columns contain description, min, rates, and units.
3. **Hierarchy & Context Preservation**:
   - Section headers (e.g., `EXPORT AKL AIRFREIGHT`, `EXPORT`, `Security Screening`) are detected and propagated down through the parsed rows as context.
   - Footnotes starting with `*` or `**` (e.g., screening rules) are successfully matched against preceding lines using asterisks, populating their raw notes and toggling their conditional status correctly.
4. **Target Charge Assertions**: Our intermediate parser accurately extracts values from the test carrier rate sheet fixture, including Airfreight (`NZD`, `per_kg`, min `315.00`, rate `7.30`), AWB/Documentation Fees, Pick Up rates, Fuel Surcharges (percentage `22%`), X-ray (min `45.00`, rate `0.25`, conditional), and Additional Screening (`POA`, conditional).

## What Remains for Phase 8B (Parser Normalization)
1. **Shared Logic Extraction**: Move the diagnostic table parser out of test modules into production packages under a dedicated service file.
2. **Deterministic normalisation**: Implement the mapping flow connecting extracted column rows (`ParsedTableLine`) to candidate canonical `ChargeAlias` and `ProductCode` records without relying purely on LLM fallback.
3. **Integration with `analyze_with_ai` and `analyze_manual`**: Allow the pipeline to run the deterministic table parser first, merging its structural bounds with AI audit reviews.

## Known Limitations
- **Colons in Headers**: If column headers use colons or non-standard double whitespaces, row alignment may need additional heuristics in Phase 8B.
- **Lost Whitespace**: If formatting is copy-pasted without tabs or multiple spaces (e.g., converted to single spaces), we fall back to pattern-based regex matching rather than table matrix extraction.
