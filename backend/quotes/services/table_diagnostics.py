import re
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ParsedTableLine(BaseModel):
    raw_label: str
    section_context: Optional[str] = None
    currency_hint: Optional[str] = None
    unit_hint: Optional[str] = None
    raw_unit: Optional[str] = None
    min_amount: Optional[Decimal] = None
    rate_per_unit: Optional[Decimal] = None
    percentage: Optional[Decimal] = None
    is_conditional: bool = False
    is_poa: bool = False
    raw_notes: Optional[str] = None
    source_line_number: int

def parse_decimal_safe(val: Any) -> Optional[Decimal]:
    if val in (None, "", "-"):
        return None
    val_str = str(val).replace(",", "").strip()
    if "poa" in val_str.lower():
        return None
    
    # Extract numeric part
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", val_str)
    if match:
        try:
            return Decimal(match.group(0))
        except (InvalidOperation, ValueError):
            return None
    return None

def detect_probable_table_blocks(text: str) -> List[List[str]]:
    """Split text into blocks of lines that resemble structured table data."""
    if not text:
        return []
    
    blocks: List[List[str]] = []
    current_block: List[str] = []
    
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
        
        # Check if line contains elements of a table row
        # (multiple parts split by tab, multiple spaces, or pipe)
        parts = re.split(r'\t| {2,}|\|', trimmed)
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) > 1:
            current_block.append(line)
        else:
            # If it's a single line, it could be a header or a standalone note.
            # Keep it in block if we are already building one, or split.
            if current_block:
                # If it looks like a separator or footnote, group it
                if trimmed.startswith("*") or trimmed.startswith("-"):
                    current_block.append(line)
                else:
                    blocks.append(current_block)
                    current_block = []
            
    if current_block:
        blocks.append(current_block)
        
    return blocks

def detect_column_headers(parts: List[str]) -> Dict[str, int]:
    """Identify column roles based on header row values."""
    indices = {}
    for idx, col in enumerate(parts):
        col_lower = col.lower().strip()
        if any(term in col_lower for term in ["per unit", "per-unit", "rate", "per kg"]):
            indices["rate"] = idx
        elif any(term in col_lower for term in ["unit", "basis"]):
            indices["unit"] = idx
        elif any(term in col_lower for term in ["description", "charge", "fee"]):
            indices["description"] = idx
        elif any(term in col_lower for term in ["currency", "ccy"]):
            indices["currency"] = idx
        elif any(term in col_lower for term in ["minimum", "min"]):
            indices["minimum"] = idx
    return indices

def parse_table_text_to_intermediate(text: str) -> List[ParsedTableLine]:
    """Parse structured table text into intermediate ParsedTableLine objects."""
    if not text:
        return []

    lines = text.splitlines()
    parsed_lines: List[ParsedTableLine] = []
    current_section = None
    column_indices: Dict[str, int] = {}
    marker_candidates: Dict[str, List[ParsedTableLine]] = {}
    
    for idx, line in enumerate(lines, start=1):
        trimmed = line.strip()
        if not trimmed:
            continue
            
        parts = re.split(r'\t| {2,}|\|', trimmed)
        parts = [p.strip() for p in parts if p.strip()]
        
        # 1. Handle footnote or separator rows inside a table
        if (trimmed.startswith("*") or trimmed.startswith("-")) and len(parts) <= 1:
            # Separator/Footnote line
            marker = "**" if trimmed.startswith("**") else "*"
            note_text = trimmed.lstrip("*- ").strip()
            is_cond_note = any(term in note_text.lower() for term in ["if required", "optional", "subject to", "screening"])
            
            matched = marker_candidates.get(marker, [])
            if not matched and parsed_lines:
                matched = [parsed_lines[-1]]
                
            for pl in matched:
                if pl.raw_notes:
                    pl.raw_notes += f"; {note_text}"
                else:
                    pl.raw_notes = note_text
                if is_cond_note:
                    pl.is_conditional = True
            continue
            
        # 2. Section Header detection
        # Upper case, relatively short, no table markers, not a data row
        if len(parts) == 1:
            val = parts[0]
            # Exclude header labels, notes, or charge lines from section detection
            if not any(kw in val.lower() for kw in ["currency", "minimum", "per unit", "%", "poa", "usd", "nzd", "pgk"]):
                current_section = val
            continue
            
        # 3. Column Header detection
        is_header = False
        lower_parts = [p.lower() for p in parts]
        if any(re.search(r'\b(charge|description)\b', lp) for lp in lower_parts) or \
           any(re.search(r'\b(currency|ccy)\b', lp) for lp in lower_parts) or \
           any(re.search(r'\bunit\b', lp) for lp in lower_parts) or \
           any(re.search(r'\b(minimum|min)\b', lp) for lp in lower_parts):
            is_header = True
            
        if is_header:
            column_indices = detect_column_headers(parts)
            continue

        # 4. Data Row parsing
        # Retrieve values using the detected column indices or fallback positions
        desc_idx = column_indices.get("description", 0)
        ccy_idx = column_indices.get("currency", 1 if len(parts) > 1 else 0)
        unit_idx = column_indices.get("unit", 2 if len(parts) > 2 else 0)
        min_idx = column_indices.get("minimum", 3 if len(parts) > 3 else 0)
        rate_idx = column_indices.get("rate", 4 if len(parts) > 4 else 0)
        
        raw_label = parts[desc_idx] if desc_idx < len(parts) else ""
        raw_ccy = parts[ccy_idx] if ccy_idx < len(parts) else None
        raw_unit = parts[unit_idx] if unit_idx < len(parts) else None
        raw_min = parts[min_idx] if min_idx < len(parts) else None
        raw_rate = parts[rate_idx] if rate_idx < len(parts) else None
        
        # Sparse row heuristic adjustments
        if len(parts) < 5:
            remaining = parts[1:]
            detected_ccy = None
            for p in remaining[:]:
                if len(p) == 3 and p.isupper():
                    detected_ccy = p
                    remaining.remove(p)
                    break
            detected_unit = None
            for p in remaining[:]:
                if any(u in p.lower() for u in ["kg", "awb", "shipment", "entry", "trip", "cbm"]):
                    detected_unit = p
                    remaining.remove(p)
                    break
            detected_min = None
            detected_rate = None
            if remaining:
                if len(remaining) == 1:
                    detected_min = remaining[0]
                else:
                    detected_min = remaining[0]
                    detected_rate = remaining[1]
            raw_ccy = detected_ccy or (raw_ccy if raw_ccy and raw_ccy not in [detected_unit, detected_min, detected_rate] else None)
            raw_unit = detected_unit or (raw_unit if raw_unit and raw_unit not in [detected_ccy, detected_min, detected_rate] else None)
            raw_min = detected_min or (raw_min if raw_min and raw_min not in [detected_ccy, detected_unit, detected_rate] else None)
            raw_rate = detected_rate or (raw_rate if raw_rate and raw_rate not in [detected_ccy, detected_unit, detected_min] else None)

        if not raw_label:
            continue
            
        # Determine is_poa
        is_poa = "poa" in trimmed.lower()
        
        # Check percentage/surcharge
        is_percentage = "%" in trimmed
        
        # Check conditional checks
        is_cond = any(term in raw_label.lower() for term in ["subject to", "optional", "if application", "if required", "if applicable"])
        if not is_cond and raw_unit:
            is_cond = any(term in raw_unit.lower() for term in ["subject to", "optional", "if application", "if required", "if applicable"])
            
        # Parse numeric amounts
        min_amount = parse_decimal_safe(raw_min)
        rate_amount = parse_decimal_safe(raw_rate)
        percentage_val = None
        
        if is_percentage:
            pct_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", trimmed)
            if pct_match:
                percentage_val = Decimal(pct_match.group(1))
                
        # Handle unit text normalization
        unit_hint = None
        if raw_unit:
            u_lower = raw_unit.lower()
            if "per kg" in u_lower or "per_kg" in u_lower or u_lower == "kg":
                unit_hint = "per_kg"
            elif "per awb" in u_lower or "awb" in u_lower:
                unit_hint = "per_awb"
            elif "per entry" in u_lower or "entry" in u_lower:
                unit_hint = "per_entry"
            elif "per shipment" in u_lower or "shipment" in u_lower or "flat" in u_lower:
                unit_hint = "per_shipment"
            elif "%" in u_lower or "percentage" in u_lower:
                unit_hint = "percentage"
                
        line_item = ParsedTableLine(
            raw_label=raw_label,
            section_context=current_section,
            currency_hint=raw_ccy.strip() if raw_ccy else None,
            unit_hint=unit_hint or (raw_unit.strip() if raw_unit else None),
            raw_unit=raw_unit.strip() if raw_unit else None,
            min_amount=min_amount,
            rate_per_unit=rate_amount,
            percentage=percentage_val,
            is_conditional=is_cond,
            is_poa=is_poa,
            source_line_number=idx,
        )
        parsed_lines.append(line_item)
        
        # Check marker prefix on raw label
        if raw_label.startswith("**"):
            marker_candidates.setdefault("**", []).append(line_item)
        elif raw_label.startswith("*"):
            marker_candidates.setdefault("*", []).append(line_item)
            
    return parsed_lines
