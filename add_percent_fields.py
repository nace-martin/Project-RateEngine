# Quick script to add percentage surcharge fields to ServiceComponent model

import re

# Read the file
with open('backend/services/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the location to insert (right before is_active)
pattern = r'(    tax_rate = models\.DecimalField\(max_digits=5, decimal_places=4, default=Decimal\("0\.0"\)\)\r?\n)(    is_active = models\.BooleanField\(default=True\)\r?\n)'

replacement = r'''\1    
    # --- Percentage Surcharge Support ---
    percent_of_component = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surcharges',
        help_text="If this is a percentage surcharge, reference the base component (e.g., Fuel Surcharge = 10%% of Cartage)"
    )
    percent_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage value (e.g., 10.00 for 10%%). Only used if percent_of_component is set."
    )
    # ---
    
\2'''

# Apply the replacement
new_content = re.sub(pattern, replacement, content)

# Write back
with open('backend/services/models.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("[OK] Added percentage surcharge fields to ServiceComponent model")
