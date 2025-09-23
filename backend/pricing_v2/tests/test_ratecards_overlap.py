import datetime as dt
import pytest
from django.db import connection, IntegrityError, transaction

pytestmark = pytest.mark.django_db

def _mk_ratecard(provider_id, audience_id, name, start, end=None):
    with connection.cursor() as cur:
        cur.execute("""
          INSERT INTO ratecards(provider_id,audience_id,name,role,scope,direction,
                                commodity_code,rate_strategy,currency,source,status,
                                effective_date,expiry_date,meta,created_at,updated_at)
          VALUES (%s,%s,%s,'SELL','A2D','IMPORT','GEN','STD','PGK','seed','ACTIVE',
                  %s,%s,'{}', now(), now())
          RETURNING id
        """, [provider_id, audience_id, name, start, end])
        return cur.fetchone()[0]

def test_ratecards_overlap_blocked():
    # assumes provider 1 and audience 1 exist in seed data
    p, a = 1, 1
    rc1 = _mk_ratecard(p, a, "PX-AUD-IMPORT", dt.date(2025,1,1), dt.date(2025,3,31))
    assert rc1

    # Overlapping window should violate EXCLUDE constraint
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _mk_ratecard(p, a, "PX-AUD-IMPORT", dt.date(2025,3,15), dt.date(2025,6,30))