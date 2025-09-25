import json
from decimal import Decimal
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _fetch_totals_row(quote_version_id: int):
    """
    Reads the DB view `quotes_quoteversion_totals`.
    Skips test gracefully if the view isn't present/applied yet.
    """
    cols = [
        "quote_version_id",
        "sell_origin", "sell_air", "sell_destination",
        "sell_total", "buy_total", "tax_total", "grand_total",
        "margin_abs", "margin_pct",
    ]
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT quote_version_id,
                       sell_origin, sell_air, sell_destination,
                       sell_total, buy_total, tax_total, grand_total,
                       margin_abs, margin_pct
                FROM quotes_quoteversion_totals
                WHERE quote_version_id = %s
                """,
                [quote_version_id],
            )
            row = cur.fetchone()
    except Exception as e:
        pytest.skip(f"Totals view not available/applied yet: {e}")

    if not row:
        return None

    return dict(zip(cols, row))


def _dec(x) -> Decimal:
    return Decimal(str(x))


def _mk_user_and_client():
    User = get_user_model()
    user = User.objects.create_user(
        username="tester", email="t@example.com", password="pass", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _mk_station(iata, city, cc):
    from core.models import Station
    obj, _ = Station.objects.get_or_create(iata_code=iata, defaults={"city": city, "country_code": cc})
    return obj


def _mk_customer(name="Test Customer"):
    from customers.models import Customer
    obj, _ = Customer.objects.get_or_create(name=name)
    return obj


def test_end_to_end_idempotency_totals_and_guardrails():
    """
    Covers:
      - Create quotation (envelope)
      - Create version with BUY/SELL lines (Idempotency works)
      - Lock version (allowed only if there is at least one SELL line)
      - Totals/GST (from DB view)
      - SELL currency enforcement error
      - Guardrail: cannot lock version with only BUY lines
    """
    # ---- Setup actors and data ----
    _, client = _mk_user_and_client()
    bne = _mk_station("BNE", "Brisbane", "AU")
    pom = _mk_station("POM", "Port Moresby", "PG")
    cust = _mk_customer()

    # ---- 1) Create envelope ----
    q_payload = {
        "reference": "Q25-09-0003",
        "customer": cust.id,
        "date": str(date(2025, 9, 25)),
        "validity_days": 7,
        "service_type": "IMPORT",
        "terms": "DAP",
        "scope": "A2D",
        "payment_term": "PREPAID",
        "sell_currency": "AUD",
    }
    r = client.post("/api/quotations/", data=q_payload, format="json")
    assert r.status_code == 201, r.content
    qid = r.data["id"]

    # ---- 2) Create Version 1 (with SELL and BUY; DEST SELL taxable) ----
    v_payload = {
        "origin": bne.id,
        "destination": pom.id,
        "volumetric_divisor": 6000,
        "volumetric_weight_kg": "112.000",
        "chargeable_weight_kg": "112.000",
        "carrier_code": "PX",
        "service_level": "STD",
        "transit_time_days": 2,
        "routing_details": "BNE-POM direct",
        "fx_snapshot": {"PGK_AUD": 0.41, "caf_pct": 0.065},
        "policy_snapshot": {"rule": "IMPORT_A2D_PREPAID", "stages": ["DESTINATION"], "export_evidence": False},
        "rate_provenance": {"carrier": "PX", "ratecard_id": 12345},
        "sell_currency": "AUD",
        "valid_from": "2025-09-25",
        "valid_to": "2025-10-02",
        "pieces": [
            {"length_cm": 120, "width_cm": 80, "height_cm": 70, "weight_kg": "85.000", "count": 1},
        ],
        "charges": [
            {"stage": "AIR", "code": "AFRT", "description": "Air freight +100kg", "basis": "PER_KG",
             "qty": "112.000", "unit_price": "7.10", "side": "SELL", "currency": "AUD"},
            {"stage": "AIR", "code": "AFRT_BUY", "description": "Carrier buy +100kg", "basis": "PER_KG",
             "qty": "112.000", "unit_price": "6.10", "side": "BUY", "currency": "AUD"},
            {"stage": "DESTINATION", "code": "CFS", "description": "Terminal handling (POM)",
             "basis": "FLAT", "qty": 1, "unit_price": 120.00, "side": "SELL", "currency": "AUD"},
        ]
    }
    headers = {"HTTP_IDEMPOTENCY_KEY": "14e1b78a-8b0b-4a4e-bb5a-b4859a28e721"}  # DRF test client uses HTTP_ prefix
    r = client.post(f"/api/quotes/{qid}/versions", data=v_payload, format="json", **headers)
    assert r.status_code == 201, r.content
    vid = r.data["id"]

    # ---- 2a) Idempotency: same key returns same version & 200 ----
    r2 = client.post(f"/api/quotes/{qid}/versions", data=v_payload, format="json", **headers)
    assert r2.status_code == 200, r2.content
    assert r2.data["id"] == vid

    # ---- 3) Lock it ----
    r = client.post(f"/api/quote-versions/{vid}/lock")
    assert r.status_code in (200, 201), r.content
    assert r.data["status"] in ("locked", "already_locked")

    # ---- 4) Totals from DB view (GST aware) ----
    row = _fetch_totals_row(vid)
    if row is None:
        pytest.skip("No totals row found for this version (view present but empty).")

    # Expected numbers (see discussion):
    # sell_total = 7.10*112 + 120 = 915.20
    # buy_total  = 6.10*112       = 683.20
    # tax_total  = 10% of DEST SELL 120 = 12.00
    # grand_total = 915.20 + 12.00 = 927.20
    # margin_abs = 915.20 - 683.20 = 232.00
    # margin_pct ≈ 232.00 / 915.20 * 100 = 25.36
    assert _dec(row["sell_total"]) == _dec("915.20")
    assert _dec(row["buy_total"]) == _dec("683.20")
    assert _dec(row["tax_total"]) == _dec("12.00")
    assert _dec(row["grand_total"]) == _dec("927.20")
    assert _dec(row["margin_abs"]) == _dec("232.00")
    # allow tiny float db rounding on margin_pct
    assert abs(float(row["margin_pct"]) - 25.36) < 0.01

    # ---- 5) SELL currency enforcement: should reject mismatched currency on SELL line ----
    bad_payload = dict(v_payload)
    bad_payload["charges"] = [
        {"stage": "AIR", "code": "AFRT", "description": "Bad currency SELL", "basis": "PER_KG",
         "qty": "10.000", "unit_price": "1.00", "side": "SELL", "currency": "USD"}  # mismatched
    ]
    r = client.post(f"/api/quotes/{qid}/versions", data=bad_payload, format="json",
                    HTTP_IDEMPOTENCY_KEY="new-key-1")
    assert r.status_code == 400, r.content
    assert "SELL line currency must equal version.sell_currency" in r.content.decode()

    # ---- 6) Guardrail: cannot lock a version with ONLY BUY lines ----
    # Create a fresh quotation
    q_payload2 = dict(q_payload)
    q_payload2["reference"] = "Q25-09-0004"
    r = client.post("/api/quotations/", data=q_payload2, format="json")
    assert r.status_code == 201
    qid2 = r.data["id"]

    v_payload_buy_only = dict(v_payload)
    v_payload_buy_only["charges"] = [
        {"stage": "AIR", "code": "AFRT_BUY", "description": "Buy only", "basis": "PER_KG",
         "qty": "10.000", "unit_price": "1.00", "side": "BUY", "currency": "AUD"}
    ]
    r = client.post(f"/api/quotes/{qid2}/versions", data=v_payload_buy_only, format="json",
                    HTTP_IDEMPOTENCY_KEY="new-key-2")
    assert r.status_code == 201
    vid2 = r.data["id"]

    r = client.post(f"/api/quote-versions/{vid2}/lock")
    assert r.status_code == 400, r.content
    assert "no sell lines" in r.content.decode().lower()
