import assert from "assert";
import { detectTableStructure } from "./spot-table-parser.ts";

// =============================================================================
// TEST SUITE: SPOT Table Parser
// =============================================================================

// 1. HTML table paste from email
function testHtmlEmailPaste() {
    const rawText = "Hi team, please find the rates below:\n\nFreight charges details.";
    const rawHtml = `
        <p>Hi team, please find the rates below:</p>
        <table border="1">
            <thead>
                <tr>
                    <th>Charge Code</th>
                    <th>Rate</th>
                    <th>Unit</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>EXP-FSC</td>
                    <td>15</td>
                    <td>%</td>
                </tr>
                <tr>
                    <td>EXP-AWB</td>
                    <td>75</td>
                    <td>flat</td>
                </tr>
            </tbody>
        </table>
    `;

    const result = detectTableStructure(rawText, rawHtml);

    assert.strictEqual(result.source_type, "html");
    assert.strictEqual(result.detected_tables.length, 1);
    const table = result.detected_tables[0];
    assert.strictEqual(table.columnCount, 3);
    assert.deepStrictEqual(table.headers, ["Charge Code", "Rate", "Unit"]);
    assert.deepStrictEqual(table.rows[0], ["EXP-FSC", "15", "%"]);
    assert.strictEqual(table.warnings.length, 0);
    console.log("✓ testHtmlEmailPaste passed");
}

// 2. TSV/Excel-style paste
function testTsvExcelPaste() {
    const rawText = "Code\tRate\tUnit\nEXP-PICKUP\t250\tflat\nEXP-HANDLING\t1.50\tper_kg";
    
    const result = detectTableStructure(rawText, null);

    assert.strictEqual(result.source_type, "tsv");
    assert.strictEqual(result.detected_tables.length, 1);
    const table = result.detected_tables[0];
    assert.strictEqual(table.columnCount, 3);
    assert.deepStrictEqual(table.headers, ["Code", "Rate", "Unit"]);
    assert.deepStrictEqual(table.rows[0], ["EXP-PICKUP", "250", "flat"]);
    console.log("✓ testTsvExcelPaste passed");
}

// 3. Markdown pipe table
function testPipeTablePaste() {
    const rawText = `
| Code | Rate | Unit |
|---|---|---|
| EXP-FSC | 22 | % |
| EXP-SEC | 120 | flat |
`;
    const result = detectTableStructure(rawText, null);

    assert.strictEqual(result.source_type, "tsv"); // Treated as TSV/table
    assert.strictEqual(result.detected_tables.length, 1);
    const table = result.detected_tables[0];
    assert.strictEqual(table.columnCount, 3);
    assert.deepStrictEqual(table.headers, ["Code", "Rate", "Unit"]);
    assert.deepStrictEqual(table.rows[0], ["EXP-FSC", "22", "%"]);
    console.log("✓ testPipeTablePaste passed");
}

// 4. Mixed text + table + notes
function testMixedContent() {
    const rawText = `
ORIGIN DETAILS
Origin airport is POM.
The local pick up fees:
Code\tRate\tUnit
EXP-PICKUP\t120\tflat
EXP-CARTAGE\t0.50\tper_kg

Please note that rates are valid until end of month.
`;
    const result = detectTableStructure(rawText, null);

    assert.strictEqual(result.source_type, "tsv");
    assert.strictEqual(result.detected_tables.length, 1);
    assert.deepStrictEqual(result.detected_sections, ["ORIGIN DETAILS"]);
    assert.ok(result.global_notes.includes("Please note that rates are valid until end of month."));
    console.log("✓ testMixedContent passed");
}

// 5. Inconsistent table rows warning
function testInconsistentRows() {
    const rawText = "Code\tRate\tUnit\nEXP-CARTAGE\t2.50\nEXP-FSC\t15\t%\tExtraCell";
    const result = detectTableStructure(rawText, null);

    assert.strictEqual(result.detected_tables.length, 1);
    const table = result.detected_tables[0];
    assert.strictEqual(table.columnCount, 4); // Max row size
    assert.ok(table.warnings.length > 0);
    assert.ok(result.warnings.length > 0);
    console.log("✓ testInconsistentRows passed");
}

// 6. Plain text fallback
function testPlainFallback() {
    const rawText = "Hi, there are no tables here, just raw sentences listing A/F rate.";
    const result = detectTableStructure(rawText, null);

    assert.strictEqual(result.source_type, "plain");
    assert.strictEqual(result.detected_tables.length, 0);
    console.log("✓ testPlainFallback passed");
}

// RUN ALL TESTS
try {
    testHtmlEmailPaste();
    testTsvExcelPaste();
    testPipeTablePaste();
    testMixedContent();
    testInconsistentRows();
    testPlainFallback();
    console.log("\n========================================================");
    console.log("ALL SPOT TABLE PARSER TESTS PASSED SUCCESSFULLY!");
    console.log("========================================================\n");
} catch (error) {
    console.error("Test execution failed:", error);
    process.exit(1);
}
