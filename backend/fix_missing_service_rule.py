import os
import django
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from services.models import ServiceRule, ServiceComponent, ServiceRuleComponent

def fix_missing_service_rule():
    with open('fix_output.txt', 'w') as f:
        def log(msg):
            print(msg)
            f.write(str(msg) + '\n')
            f.flush()
            
        log("Fixing Missing Service Rule for EXW Export D2D...")
        
        # Target criteria
        mode = 'AIR'
        direction = 'EXPORT'
        service_scope = 'D2D'
        payment_term = 'PREPAID'
        incoterm = 'EXW'
        
        # Check if exists
        rule = ServiceRule.objects.filter(
            mode=mode,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
            incoterm=incoterm
        ).first()
        
        if rule:
            log(f"Rule already exists: {rule.id}")
            if rule.output_currency_type != 'PGK':
                log(f"Updating output currency to PGK (was {rule.output_currency_type})")
                rule.output_currency_type = 'PGK'
                rule.save()
            if not rule.is_active:
                log("Activating rule")
                rule.is_active = True
                rule.save()
                
        else:
            log("Rule not found. Creating it...")
            # Find a template rule (e.g. DAP)
            template = ServiceRule.objects.filter(
                mode=mode,
                direction=direction,
                service_scope=service_scope,
                payment_term=payment_term,
                incoterm='DAP' # Try DAP first
            ).first()
            
            if not template:
                log("No DAP template found. Trying generic...")
                template = ServiceRule.objects.filter(
                    mode=mode,
                    direction=direction,
                    service_scope=service_scope,
                    payment_term=payment_term
                ).first()
                
            if template:
                log(f"Using template rule: {template.id} ({template.incoterm})")
                new_rule = ServiceRule.objects.create(
                    mode=mode,
                    direction=direction,
                    service_scope=service_scope,
                    payment_term=payment_term,
                    incoterm=incoterm,
                    output_currency_type='PGK',
                    description=f"Export D2D Prepaid {incoterm} (Auto-Created)",
                    is_active=True
                )
                
                # Copy components
                components = template.rule_components.all()
                log(f"Copying {components.count()} components...")
                for rc in components:
                    ServiceRuleComponent.objects.create(
                        service_rule=new_rule,
                        service_component=rc.service_component,
                        sequence=rc.sequence,
                        leg_owner=rc.leg_owner,
                        is_mandatory=rc.is_mandatory,
                        notes=rc.notes
                    )
                log(f"Created new rule: {new_rule.id}")
            else:
                log("CRITICAL: No template rule found! Cannot create.")

if __name__ == "__main__":
    fix_missing_service_rule()
