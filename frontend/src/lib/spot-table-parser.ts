export interface DetectedTable {
    headers: string[];
    rows: string[][];
    columnCount: number;
    sourceIndex: number;
    warnings: string[];
}

export interface StructuredPreview {
    source_type: 'html' | 'tsv' | 'plain';
    raw_text: string;
    raw_html_present: boolean;
    detected_tables: DetectedTable[];
    detected_sections: string[];
    global_notes: string;
    warnings: string[];
}

/** Helper to strip HTML tags from a string */
export function stripHtmlTags(html: string): string {
    return html
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
        .replace(/<\/?[^>]+(>|$)/g, " ")
        .replace(/&nbsp;/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

/** Detect common currencies in text */
export function detectCurrencies(text: string): string[] {
    const curRegex = /\b(USD|PGK|AUD|SGD|NZD|FJD|EUR|GBP|HKD|CNY)\b|[$K]/gi;
    const matches = text.match(curRegex) || [];
    const normalized = matches.map(m => {
        const val = m.toUpperCase();
        if (val === "$") return "USD/AUD";
        if (val === "K") return "PGK";
        return val;
    });
    return Array.from(new Set(normalized)).sort();
}

/** Detect common units in text */
export function detectUnits(text: string): string[] {
    const units: string[] = [];
    const lower = text.toLowerCase();
    if (lower.includes("/kg") || lower.includes("per kg") || lower.includes("per_kg")) units.push("Per KG");
    if (lower.includes("min") || lower.includes("minimum")) units.push("Minimum");
    if (lower.includes("flat") || lower.includes("lump")) units.push("Flat");
    if (lower.includes("awb") || lower.includes("per awb")) units.push("Per AWB");
    if (lower.includes("shipment") || lower.includes("per shipment")) units.push("Per Shipment");
    if (lower.includes("%") || lower.includes("percent") || lower.includes("fsc")) units.push("Percentage");
    return units;
}

/** Extract tables from HTML content using regex for environmental independence (browser/node) */
export function parseHtmlTables(html: string): DetectedTable[] {
    const tables: DetectedTable[] = [];
    const tableRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
    let tableMatch;
    let sourceIndex = 0;

    while ((tableMatch = tableRegex.exec(html)) !== null) {
        const tableContent = tableMatch[1];
        const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
        let rowMatch;
        const rawRows: string[][] = [];

        while ((rowMatch = rowRegex.exec(tableContent)) !== null) {
            const rowContent = rowMatch[1];
            const cellRegex = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
            let cellMatch;
            const cells: string[] = [];

            while ((cellMatch = cellRegex.exec(rowContent)) !== null) {
                cells.push(stripHtmlTags(cellMatch[1]));
            }
            if (cells.length > 0) {
                rawRows.push(cells);
            }
        }

        if (rawRows.length > 0) {
            // Find max column count
            const columnCount = Math.max(...rawRows.map(r => r.length));
            const headers = rawRows[0] || [];
            const rows = rawRows.slice(1);
            const warnings: string[] = [];

            // Consistency checks
            rawRows.forEach((r, idx) => {
                if (r.length !== columnCount) {
                    warnings.push(`Row ${idx + 1} has mismatched column count (${r.length} vs expected ${columnCount})`);
                }
            });

            tables.push({
                headers,
                rows,
                columnCount,
                sourceIndex: sourceIndex++,
                warnings
            });
        }
    }

    return tables;
}

/** Extract tables from Tab-Separated Values (TSV) plain text */
export function parseTsvTables(text: string): DetectedTable[] {
    const lines = text.split(/\r?\n/);
    const tables: DetectedTable[] = [];
    let currentTableRows: string[][] = [];
    let sourceIndex = 0;

    const finalizeTable = () => {
        if (currentTableRows.length > 1) {
            const columnCount = Math.max(...currentTableRows.map(r => r.length));
            const headers = currentTableRows[0].map(h => h.trim());
            const rows = currentTableRows.slice(1).map(r => r.map(c => c.trim()));
            const warnings: string[] = [];

            currentTableRows.forEach((r, idx) => {
                if (r.length !== columnCount) {
                    warnings.push(`Row ${idx + 1} has mismatched column count (${r.length} vs expected ${columnCount})`);
                }
            });

            tables.push({
                headers,
                rows,
                columnCount,
                sourceIndex: sourceIndex++,
                warnings
            });
        }
        currentTableRows = [];
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
            finalizeTable();
            continue;
        }

        // Split by tabs or markdown pipes
        let cells: string[] = [];
        if (line.includes('\t')) {
            cells = line.split('\t');
        } else if (trimmed.startsWith('|') || (trimmed.includes('|') && trimmed.split('|').length > 2)) {
            // Markdown pipe table
            cells = line.split('|').map(c => c.trim()).filter((_, idx, arr) => {
                // Remove first and last empty cells if row started/ended with pipes
                if (idx === 0 && !arr[idx]) return false;
                if (idx === arr.length - 1 && !arr[idx]) return false;
                return true;
            });
            // Skip markdown divider row (e.g. |---|---|)
            if (cells.every(c => /^[-:\s]+$/.test(c))) {
                continue;
            }
        }

        if (cells.length > 1) {
            currentTableRows.push(cells);
        } else {
            finalizeTable();
        }
    }
    finalizeTable();

    return tables;
}

export function detectTableStructure(text: string, html?: string | null): StructuredPreview {
    const rawHtmlPresent = Boolean(html && html.includes("<table"));
    let source_type: 'html' | 'tsv' | 'plain' = 'plain';
    let detected_tables: DetectedTable[] = [];
    const warnings: string[] = [];

    if (rawHtmlPresent && html) {
        detected_tables = parseHtmlTables(html);
        if (detected_tables.length > 0) {
            source_type = 'html';
        }
    }

    if (detected_tables.length === 0) {
        detected_tables = parseTsvTables(text);
        if (detected_tables.length > 0) {
            source_type = 'tsv';
        }
    }

    // Extraction of global notes and detected headings
    const lines = text.split(/\r?\n/);
    const detected_sections: string[] = [];
    const nonTableLines: string[] = [];

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        // Check if line looks like a header/section title
        if (
            trimmed.toUpperCase() === trimmed && 
            trimmed.length > 3 && 
            trimmed.length < 50 &&
            !trimmed.includes('\t') &&
            !trimmed.includes('|')
        ) {
            detected_sections.push(trimmed);
        }

        // Keep lines that aren't part of any table for global notes
        const looksLikeTsv = line.includes('\t') || (trimmed.startsWith('|') && trimmed.split('|').length > 2);
        if (!looksLikeTsv) {
            nonTableLines.push(trimmed);
        }
    }

    // If tables have warnings, bubble them to global
    detected_tables.forEach(t => {
        if (t.warnings.length > 0) {
            warnings.push(`Table ${t.sourceIndex + 1} has row alignment inconsistencies.`);
        }
    });

    return {
        source_type,
        raw_text: text,
        raw_html_present: rawHtmlPresent,
        detected_tables,
        detected_sections,
        global_notes: nonTableLines.slice(0, 15).join("\n"), // first 15 lines of notes
        warnings
    };
}
