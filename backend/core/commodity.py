"""
Shared commodity codes for standard and SPOT quoting flows.
"""

COMMODITY_CODE_GCR = "GCR"
COMMODITY_CODE_SCR = "SCR"
COMMODITY_CODE_DG = "DG"
COMMODITY_CODE_AVI = "AVI"
COMMODITY_CODE_PER = "PER"
COMMODITY_CODE_HVC = "HVC"
COMMODITY_CODE_HUM = "HUM"
COMMODITY_CODE_OOG = "OOG"
COMMODITY_CODE_VUL = "VUL"
COMMODITY_CODE_TTS = "TTS"
COMMODITY_CODE_OTHER = "OTHER"

DEFAULT_COMMODITY_CODE = COMMODITY_CODE_GCR

COMMODITY_LABELS = {
    COMMODITY_CODE_GCR: "General Cargo",
    COMMODITY_CODE_SCR: "Special Cargo",
    COMMODITY_CODE_DG: "Dangerous Goods",
    COMMODITY_CODE_AVI: "Live Animals",
    COMMODITY_CODE_PER: "Perishables",
    COMMODITY_CODE_HVC: "High Value Cargo",
    COMMODITY_CODE_HUM: "Human Remains",
    COMMODITY_CODE_OOG: "Oversized/Heavy Cargo",
    COMMODITY_CODE_VUL: "Vulnerable Cargo",
    COMMODITY_CODE_TTS: "Time/Temperature Sensitive",
    COMMODITY_CODE_OTHER: "Other Special Cargo",
}

COMMODITY_CHOICES = tuple(
    (code, label) for code, label in COMMODITY_LABELS.items()
)


def normalize_commodity_code(value) -> str:
    if value is None:
        return DEFAULT_COMMODITY_CODE
    code = str(value).strip().upper()
    return code or DEFAULT_COMMODITY_CODE


def is_valid_commodity_code(value) -> bool:
    return normalize_commodity_code(value) in COMMODITY_LABELS


def validate_commodity_code(value) -> str:
    code = normalize_commodity_code(value)
    if code not in COMMODITY_LABELS:
        valid_codes = ", ".join(COMMODITY_LABELS.keys())
        raise ValueError(f"Unsupported commodity_code '{value}'. Valid codes: {valid_codes}.")
    return code


def commodity_label(value) -> str:
    code = normalize_commodity_code(value)
    return COMMODITY_LABELS.get(code, code)
