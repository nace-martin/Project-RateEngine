import math
from typing import List, Dict, Any
from bs4 import BeautifulSoup

# A simple cache so we don't re-read files multiple times during one request
_CARD_CACHE = {}

def parse_html_rate_card(file_path: str) -> Dict[str, Any]:
    """
    Parses a given HTML rate card file into a structured dictionary.
    This acts as our "Reading Assistant".
    """
    if file_path in _CARD_CACHE:
        return _CARD_CACHE[file_path]

    with open(file_path, 'r') as f:
        soup = BeautifulSoup(f, 'lxml')

    data = {"lanes": [], "fees": {}}
    
    for table in soup.find_all("table"):
        headers = [th.text.strip().lower() for th in table.find_all("th")]
        
        # Check for fee table
        if "item code" in headers:
            for row in table.find("tbody").find_all("tr") if table.find("tbody") else []:
                cells = [td.text.strip() for td in row.find_all("td")]
                if not cells:
                    continue
                
                row_data = dict(zip(headers, cells))
                item_code = row_data.get("item code")
                
                if item_code:
                    data["fees"][item_code] = {
                        "description": row_data.get("item name", ""),
                        "basis": row_data.get("cost per", "FLAT").upper(),
                        "rate": float(row_data.get("pgk", row_data.get("aud", 0.0))),
                        "minimum": float(row_data.get("min", 0.0))
                    }
        # Check for lane table
        elif "origin" in headers and "destination" in headers:
             for row in table.find("tbody").find_all("tr") if table.find("tbody") else []:
                cells = [td.text.strip() for td in row.find_all("td")]
                if not cells:
                    continue
                
                row_data = dict(zip(headers, cells))

                # Extract lane details
                lane = {
                    "origin": row_data.get("origin"),
                    "dest": row_data.get("destination"),
                    "min_charge": float(row_data.get("min", 0.0)),
                    "breaks": []
                }

                # Extract rate breaks
                for header, value in row_data.items():
                    if header.startswith('+'): # e.g. +45, +100
                        try:
                            from_kg = int(header[1:])
                            rate_per_kg = float(value)
                            lane["breaks"].append({"from_kg": from_kg, "rate_per_kg": rate_per_kg})
                        except ValueError:
                            continue # Ignore headers that are not valid numbers
                
                data["lanes"].append(lane)


    _CARD_CACHE[file_path] = data
    return data

def chargeable_kg(pieces: List[Dict], divisor: int = 6000) -> int:
    """
    Air volumetric kg using cm and IATA divisor (default 6000 => ~167 kg/m³).
    Returns CEILING to whole kg (business rule).
    """
    total_volume_cm3 = 0
    total_weight_kg = 0
    for piece in pieces:
        total_volume_cm3 += piece.get('length_cm', 0) * piece.get('width_cm', 0) * piece.get('height_cm', 0)
        total_weight_kg += piece.get('weight_kg', 0)

    volumetric_weight_kg = total_volume_cm3 / divisor
    
    chargeable_weight = max(total_weight_kg, volumetric_weight_kg)
    
    return math.ceil(chargeable_weight)