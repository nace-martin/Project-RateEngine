# Air Freight Pilot Environment Verification and Seeding

This guide details how to verify the health/readiness of the pilot environment and verify seed data.

## 1. Health Verification Script / Command

To verify backend configuration health, database connections, and basic system routing:

```bash
# Check Django configuration and system checks
python backend/manage.py check

# Run pilot readiness verification checks (running all tests)
pytest backend/quotes/tests
```

## 2. Seed Data Auditing

Verify that the following core seeds exist before starting the pilot:

### 2.1 EFM Operating Entity Verification
Run these commands in the Django shell (`python backend/manage.py shell`) to check canonical entities:

```python
from parties.models import OperatingEntity
entities = OperatingEntity.objects.filter(name__in=['EFM PNG', 'EFM Australia', 'EFM Fiji', 'EFM Solomon Islands'])
for e in entities:
    print(e.code, e.name, e.country_code)
```

### 2.2 Air Freight Product Codes Verification
Ensure that Air Freight product codes are seeded:

```python
from pricing_v4.models import ProductCode
products = ProductCode.objects.filter(code__icontains='AIR') | ProductCode.objects.filter(code__startswith='FSC') | ProductCode.objects.filter(code__startswith='SSC')
for p in products:
    print(p.id, p.code, p.description, p.domain, p.category)
```

If these are not present, they must be seeded from the master reference data template before testing.

## 3. Deployment Safety Check

Verify container environment dynamic port binding and static/database migrations execution:

- Ensure no container entrypoint executes `python manage.py migrate` directly at startup. Always use `backend/entrypoint.migrate.sh` during deployment tasks.
- Verify configured secret-management mechanism is available.
- Run static checks locally before pushing changes:
  ```bash
  git diff --check
  ```
