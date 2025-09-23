import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

def test_quotes_incomplete_defaults_false_and_reason_nullable():
    with connection.cursor() as cur:
        cur.execute("""
          INSERT INTO quotes(status, request_snapshot, buy_total, sell_total,
                             currency, created_at, updated_at, organization_id, payment_term)
          VALUES ('NEW','{}',0,0,'PGK', now(), now(), 1, 'PREPAID')
          RETURNING is_incomplete, incomplete_reason
        """)
        is_incomplete, reason = cur.fetchone()
        assert is_incomplete is False
        assert reason is None

def test_quotes_incomplete_settable():
    with connection.cursor() as cur:
        cur.execute("""
          INSERT INTO quotes(status, request_snapshot, buy_total, sell_total,
                             currency, created_at, updated_at, organization_id, payment_term,
                             is_incomplete, incomplete_reason)
          VALUES ('NEW','{}',0,0,'PGK', now(), now(), 1, 'PREPAID', TRUE, 'Missing BUY rate')
          RETURNING is_incomplete, incomplete_reason
        """)
        inc, reason = cur.fetchone()
        assert inc is True and reason == 'Missing BUY rate'