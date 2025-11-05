import os
import re

# --- PATTERN SETS (v4) ---
# We now have two sets of patterns.

# 1. ABSOLUTE_PATTERNS:
# We scan for these in ALL files. An app like 'core' importing
# 'from quotes.views' is exactly the kind of cross-boundary
# violation we need to find.
ABSOLUTE_PATTERNS = [
    r"from\s+quotes\.views_v3\b",
    r"from\s+quotes\.serializers_v3\b",
    
    r"from\s+parties\.views_v3\b",
    r"from\s+parties\.serializers_v3\b",
]

# 2. RELATIVE_PATTERNS:
# We ONLY scan for these *inside* their own apps.
# e.g., We only look for 'from .views' inside the 'quotes' app.
# This will find 'quotes/urls.py' but ignore 'accounts/urls.py'.
RELATIVE_PATTERNS = [
    r"from\s+\.views_v3\b",
    r"from\s+\.serializers_v3\b",
]
# --- END PATTERN SETS ---

# --- UPDATED EXCLUDES (v3) ---
# Using raw strings (r"...") to fix SyntaxWarning.
EXCLUDE_IN_PATH = (
    r".venv\\", r"venv\\", r"node_modules\\", r"__pycache__",
    r".pytest_cache\\", r"scripts\\",
    
    r".venv/", r"venv/", r"node_modules/", r"__pycache__/",
    r".pytest_cache/", r"scripts/",

    # Exclude the files themselves
    "quotes/views.py", "quotes\\views.py",
    "quotes/serializers.py", "quotes\\serializers.py",
    "quotes/views_v3.py", "quotes\\views_v3.py",
    "quotes/serializers_v3.py", "quotes\\serializers_v3.py",
    
    "parties/views.py", "parties\\views.py",
    "parties/serializers.py", "parties\\serializers.py",
    "parties/views_v3.py", "parties\\views_v3.py",
    "parties/serializers_v3.py", "parties\\serializers_v3.py",
)
# --- END UPDATED EXCLUDES ---

ALLOWED_EXT = {'.py'} # Only need to scan python files

def main():
    hits = {} 
    
    for root, dirs, files in os.walk("."):
        norm_root = os.path.normpath(root).lower()
        
        # Exclude directories
        if any(ex in norm_root for ex in EXCLUDE_IN_PATH):
            dirs[:] = [] # Don't look any deeper
            continue
            
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
                
            path = os.path.join(root, fn)
            norm_path_l = os.path.normpath(path).lower()

            # Exclude specific files
            if any(ex in norm_path_l for ex in EXCLUDE_IN_PATH):
                continue
                
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            
            # --- NEW SMART LOGIC (v4) ---
            patterns_to_check = []
            
            # 1. Always check for absolute imports everywhere
            patterns_to_check.extend(ABSOLUTE_PATTERNS)
            
            # 2. Check for relative imports ONLY if we are
            #    inside the 'quotes' or 'parties' app.
            if "backend\\quotes" in norm_path_l or "backend/quotes" in norm_path_l:
                patterns_to_check.extend(RELATIVE_PATTERNS)
            elif "backend\\parties" in norm_path_l or "backend/parties" in norm_path_l:
                patterns_to_check.extend(RELATIVE_PATTERNS)
            # --- END NEW SMART LOGIC ---

            for pat in patterns_to_check:
                if re.search(pat, text):
                    # Store the path and the pattern that matched
                    hits[path] = pat 
                    break # Move to the next file

    if hits:
        print("Found legacy references (File :: Pattern Matched):")
        print("--------------------------------------------------")
        for path, pat in sorted(hits.items()): # Print sorted list
            print(f"{path} :: {pat}")
        print("--------------------------------------------------")
        print(f"Total files to refactor: {len(hits)}")
    else:
        print("No legacy quotes or parties references found.")

if __name__ == "__main__":
    main()
