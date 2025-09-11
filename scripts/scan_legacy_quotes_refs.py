import os
import re

PATTERNS = [
    r"backend/quotes",
    r"\bfrom\s+quotes\b",
    r"\bimport\s+quotes\b",
    r"\bquotes\.apps\b",
    r"\bquotes\.models\b",
    r"apps\.get_model\(\s*['\"]quotes['\"]",
]

EXCLUDE_IN_PATH = (
    "\\venv\\",
    "\\.venv\\",
    "\\node_modules\\",
    "__pycache__",
    "\\.pytest_cache\\",
    "\\scripts",
    "/scripts",
)
ALLOWED_EXT = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".mjs", ".js", ".ts", ".tsx"}

def main():
    hits = []
    for root, dirs, files in os.walk("."):
        norm = os.path.normpath(root)
        norm_l = norm.lower()
        if any(ex in norm for ex in EXCLUDE_IN_PATH) or ("scripts" in norm_l):
            continue
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            for pat in PATTERNS:
                if re.search(pat, text):
                    hits.append((path, pat))
    if hits:
        for path, pat in hits:
            print(f"{path} :: {pat}")
    else:
        print("No legacy quotes references found")

if __name__ == "__main__":
    main()
