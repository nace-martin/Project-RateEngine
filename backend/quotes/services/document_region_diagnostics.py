import re
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

class DetectedRegion(BaseModel):
    detected_region_type: str = Field(..., description="shipment_context_table, freight_rate_table, charges_table, free_text_charge_block, notes_terms_block, signature_or_contact_block, unknown_structured_region")
    raw_text: str
    line_range: Tuple[int, int]
    confidence: float
    section_heading: Optional[str] = None
    table_dimensions: Optional[Dict[str, int]] = None  # e.g. {"rows": 5, "cols": 4}
    warnings: List[str] = Field(default_factory=list)
    inherited_context_candidates: Dict[str, Any] = Field(default_factory=dict) # e.g. {"currency": "SGD", "pol": "HKG"}

def is_header_row_candidate(row: List[str]) -> bool:
    # A header row should not contain numeric rate expressions
    for cell in row:
        cell_lower = cell.lower().strip()
        if re.search(r'\b(usd|sgd|aud|pgk|nzd)?\s*[0-9]+', cell_lower):
            return False
    header_keywords = ["description", "charge description", "currency", "ccy", "unit", "minimum", "min", "per unit", "rate"]
    return any(any(kw in cell.lower() for kw in header_keywords) for cell in row)

def detect_regions(text: str) -> List[DetectedRegion]:
    """Segment a document into logical regions based on structures and terms."""
    if not text:
        return []

    lines = text.splitlines()
    regions: List[DetectedRegion] = []
    
    # Let's group lines into blocks first
    # A block can be a table (structured) or non-table (paragraphs, free text, notes)
    # We can group contiguous lines that have table-like properties or are separated by headers
    
    current_block_lines: List[Tuple[int, str]] = []  # List of (original_line_num, line_text)
    
    def process_block(block_lines: List[Tuple[int, str]]):
        if not block_lines:
            return
        
        start_line = block_lines[0][0]
        end_line = block_lines[-1][0]
        raw_block_text = "\n".join(b[1] for b in block_lines)
        
        # Analyze block structured-ness
        # Check if most lines in the block are split by tab, multiple spaces, or pipe
        is_tabular_list = []
        parsed_rows = []
        for _, line_text in block_lines:
            trimmed = line_text.strip()
            if not trimmed:
                continue
            parts = re.split(r'\t| {2,}|\|', trimmed)
            parts = [p.strip() for p in parts if p.strip()]
            parsed_rows.append(parts)
            is_tabular_list.append(len(parts) > 1)
            
        is_table = len(is_tabular_list) > 0 and sum(is_tabular_list) / len(is_tabular_list) >= 0.5
        
        # If it is structured
        if is_table:
            # We want to identify the type of table
            # Check keywords in all cells
            all_tokens = " ".join(" ".join(row).lower() for row in parsed_rows)
            
            # Count columns in each row to check for uneven rows
            row_lengths = [len(r) for r in parsed_rows if r]
            col_count = max(row_lengths) if row_lengths else 0
            warnings = []
            if len(set(row_lengths)) > 1:
                warnings.append("Table has row alignment inconsistencies or merged cells.")
                
            # Classify table type
            region_type = "unknown_structured_region"
            confidence = 0.5
            
            # Heuristics:
            # 1. shipment_context_table
            context_keys = ["pcs", "g.w", "c.w.", "density ratio", "volume", "gross weight", "chargeable weight", "cut off", "validity day"]
            context_matches = sum(1 for key in context_keys if key in all_tokens)
            
            # 2. freight_rate_table
            freight_keys = ["pol", "pod", "service level", "ata", "weight break", "airfreight rate", "air freight", "direct flight"]
            freight_matches = sum(1 for key in freight_keys if key in all_tokens)
            
            # 3. charges_table
            charges_keys = ["description", "amount", "fee", "charge", "terminal fee", "clearance", "doc fee", "permit", "handling", "surcharge", "gst"]
            charges_matches = sum(1 for key in charges_keys if key in all_tokens)
            
            if context_matches > freight_matches and context_matches > charges_matches:
                region_type = "shipment_context_table"
                confidence = 0.8 + (0.02 * context_matches)
            elif freight_matches > context_matches and freight_matches > charges_matches:
                region_type = "freight_rate_table"
                confidence = 0.8 + (0.02 * freight_matches)
            elif charges_matches > 0:
                has_headers = any(is_header_row_candidate(row) for row in parsed_rows[:2])
                if col_count <= 2 and not has_headers:
                    region_type = "free_text_charge_block"
                    confidence = 0.85
                else:
                    region_type = "charges_table"
                    confidence = 0.8 + (0.01 * charges_matches)
                
            # Extract inherited context candidates
            inherited = {}
            # POL / POD detection
            pol_pod_matches = re.findall(r"\b([A-Z]{3})\b", all_tokens.upper())
            # filter out non-airport codes (like KGS, G.W, C.W, PCS, etc. that could match)
            valid_airports = {"HKG", "POM", "BNE", "SIN", "SYD", "MEL", "AKL", "LAE"}
            airports = [code for code in pol_pod_matches if code in valid_airports]
            if airports:
                if len(airports) >= 2:
                    inherited["pol"] = airports[0]
                    inherited["pod"] = airports[1]
                elif len(airports) == 1:
                    inherited["pol_or_pod"] = airports[0]
                    
            # Currency detection
            currencies = ["SGD", "USD", "AUD", "PGK", "NZD", "EUR"]
            detected_ccy = []
            for ccy in currencies:
                if ccy in all_tokens.upper() or f"({ccy})" in all_tokens.upper() or f"sgd" in all_tokens.lower():
                    detected_ccy.append(ccy)
            if detected_ccy:
                inherited["currency"] = detected_ccy[0]
                
            # Weight Break or Rate detection from freight_rate_table
            if region_type == "freight_rate_table":
                # look for rate
                rate_match = re.search(r"(?:usd|sgd|aud|pgk|nzd)?\s*([0-9]+\.[0-9]+)\s*(?:/kg|per kg)", all_tokens)
                if rate_match:
                    inherited["airfreight_rate"] = rate_match.group(1)
                
                wb_match = re.search(r"(\+\s*[0-9]+)\s*kg", all_tokens)
                if wb_match:
                    inherited["weight_break"] = wb_match.group(1)
                    
            regions.append(DetectedRegion(
                detected_region_type=region_type,
                raw_text=raw_block_text,
                line_range=(start_line, end_line),
                confidence=min(confidence, 1.0),
                table_dimensions={"rows": len(parsed_rows), "cols": col_count},
                warnings=warnings,
                inherited_context_candidates=inherited
            ))
            
        else:
            # Unstructured block: block_lines
            # Let's split into separate blocks if we see contact information vs terms vs free text charges
            all_text_lower = raw_block_text.lower()
            
            # Check if this is a signature/contact block
            contact_terms = ["email", "tel:", "phone", "contact", "@", "www.", "fax", "sales@"]
            is_contact = any(term in all_text_lower for term in contact_terms) or re.search(r"\+?[0-9]{3,}[-\s]?[0-9]{3,}", all_text_lower)
            
            # Check if this block contains free text charges
            charge_regexes = [
                r"\bcharges\b", r"\bfee\b", r"\bsurcharge\b",
                r"\b(usd|sgd|aud|pgk|nzd)\s*[0-9]+",
                r"[0-9]+\.[0-9]+\s*/\s*kg",
                r"min\s*(usd|sgd|aud|pgk|nzd)?\s*[0-9]+",
                r"per\s*(shipment|shpt|set|trip|awb|kg)"
            ]
            has_free_text_charges = any(re.search(reg, all_text_lower) for reg in charge_regexes)
            
            if is_contact:
                regions.append(DetectedRegion(
                    detected_region_type="signature_or_contact_block",
                    raw_text=raw_block_text,
                    line_range=(start_line, end_line),
                    confidence=0.9,
                    warnings=[]
                ))
            elif has_free_text_charges:
                # Inherit context from free text
                inherited = {}
                currencies = ["SGD", "USD", "AUD", "PGK", "NZD"]
                for ccy in currencies:
                    if ccy in raw_block_text.upper():
                        inherited["currency"] = ccy
                        break
                regions.append(DetectedRegion(
                    detected_region_type="free_text_charge_block",
                    raw_text=raw_block_text,
                    line_range=(start_line, end_line),
                    confidence=0.85,
                    warnings=[],
                    inherited_context_candidates=inherited
                ))
            else:
                # Default to notes_terms_block
                regions.append(DetectedRegion(
                    detected_region_type="notes_terms_block",
                    raw_text=raw_block_text,
                    line_range=(start_line, end_line),
                    confidence=0.8,
                    warnings=[]
                ))

    # Parse and group text lines into contiguous blocks
    # Blank lines trigger a block split
    for idx, line in enumerate(lines, start=1):
        trimmed = line.strip()
        if not trimmed:
            if current_block_lines:
                process_block(current_block_lines)
                current_block_lines = []
            continue
            
        current_block_lines.append((idx, line))
        
    if current_block_lines:
        process_block(current_block_lines)
        
    return regions
