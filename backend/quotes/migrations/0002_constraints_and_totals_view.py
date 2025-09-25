from django.db import migrations

CHECK_SQL = r"""
ALTER TABLE quotes_charge
  ADD CONSTRAINT charge_nonneg_ck
  CHECK (qty >= 0 AND unit_price >= 0 AND extended_price >= 0);

ALTER TABLE quotes_charge
  ADD CONSTRAINT charge_gst_range_ck
  CHECK (gst_percentage >= 0 AND gst_percentage <= 20);

ALTER TABLE quotes_quoteversion
  ADD CONSTRAINT qv_weights_ck
  CHECK (volumetric_weight_kg >= 0 AND chargeable_weight_kg >= 0 AND volumetric_divisor >= 1000);
"""

DROP_CHECKS = r"""
ALTER TABLE IF EXISTS quotes_charge DROP CONSTRAINT IF EXISTS charge_nonneg_ck;
ALTER TABLE IF EXISTS quotes_charge DROP CONSTRAINT IF EXISTS charge_gst_range_ck;
ALTER TABLE IF EXISTS quotes_quoteversion DROP CONSTRAINT IF EXISTS qv_weights_ck;
"""

VIEW_SQL = r"""
CREATE OR REPLACE VIEW quotes_quoteversion_totals AS
SELECT
  qv.id AS quote_version_id,

  COALESCE(SUM(CASE WHEN c.side='SELL' AND c.stage='ORIGIN'      THEN c.extended_price ELSE 0 END),0)::numeric(18,2) AS sell_origin,
  COALESCE(SUM(CASE WHEN c.side='SELL' AND c.stage='AIR'         THEN c.extended_price ELSE 0 END),0)::numeric(18,2) AS sell_air,
  COALESCE(SUM(CASE WHEN c.side='SELL' AND c.stage='DESTINATION' THEN c.extended_price ELSE 0 END),0)::numeric(18,2) AS sell_destination,

  COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0)::numeric(18,2) AS sell_total,
  COALESCE(SUM(CASE WHEN c.side='BUY'  THEN c.extended_price ELSE 0 END),0)::numeric(18,2) AS buy_total,

  COALESCE(SUM(CASE WHEN c.side='SELL' AND c.is_taxable
                    THEN ROUND(c.extended_price * (c.gst_percentage/100.0), 2)
                    ELSE 0 END),0)::numeric(18,2) AS tax_total,

  (
    COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0)
    + COALESCE(SUM(CASE WHEN c.side='SELL' AND c.is_taxable
                        THEN ROUND(c.extended_price * (c.gst_percentage/100.0), 2)
                        ELSE 0 END),0)
  )::numeric(18,2) AS grand_total,

  (COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0)
   - COALESCE(SUM(CASE WHEN c.side='BUY'  THEN c.extended_price ELSE 0 END),0))::numeric(18,2) AS margin_abs,

  CASE
    WHEN COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0) > 0
    THEN ROUND(
      100.0 * (
        COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0)
        - COALESCE(SUM(CASE WHEN c.side='BUY' THEN c.extended_price ELSE 0 END),0)
      )
      / NULLIF(COALESCE(SUM(CASE WHEN c.side='SELL' THEN c.extended_price ELSE 0 END),0),0)
    , 2)
    ELSE 0
  END::numeric(6,2) AS margin_pct

FROM quotes_quoteversion qv
JOIN quotes_charge c ON c.version_id = qv.id
GROUP BY qv.id;
"""

DROP_VIEW_SQL = "DROP VIEW IF EXISTS quotes_quoteversion_totals;"

class Migration(migrations.Migration):
    dependencies = [
        ('quotes', '0001_initial'),
    ]
    operations = [
        migrations.RunSQL(DROP_CHECKS, CHECK_SQL),
        migrations.RunSQL(VIEW_SQL, DROP_VIEW_SQL),
    ]
