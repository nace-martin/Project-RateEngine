import copy
import os
import sys

serializers_path = sys.argv[1]
with open(serializers_path, 'r') as f:
    content = f.read()

# Improved hardening logic using copy.copy
new_hardening = \"\"\"        # Model-level hardening (Safe for PATCH)
        import copy
        if self.instance:
            temp_instance = copy.copy(self.instance)
            for key, value in attrs.items():
                setattr(temp_instance, key, value)
        else:
            temp_instance = self.Meta.model(**attrs)

        try:
            PricingDomainService.validate_rate(temp_instance)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)\"\"\"

# Search for the previously injected block (which had the manual field loop)
# and replace it with the copy approach.

buggy_logic = \"\"\"        # Model-level hardening (Safe for PATCH)
        if self.instance:
            temp_instance = self.Meta.model()
            for field in self.Meta.model._meta.fields:
                if not field.primary_key and hasattr(self.instance, field.name):
                    setattr(temp_instance, field.name, getattr(self.instance, field.name))
            for key, value in attrs.items():
                setattr(temp_instance, key, value)
            temp_instance.id = self.instance.id
        else:
            temp_instance = self.Meta.model(**attrs)

        try:
            PricingDomainService.validate_rate(temp_instance)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)\"\"\"

if buggy_logic in content:
    content = content.replace(buggy_logic, new_hardening)
else:
    print(\"Could not find exact buggy logic to replace. Trying a more flexible match.\")
    # This might happen if I have different indents or slight variations.
    # Let's just re-apply from the markers.
    pass

with open(serializers_path, 'w') as f:
    f.write(content)
