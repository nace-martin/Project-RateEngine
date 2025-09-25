from django.db import migrations

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
DROP_SQL = "DROP VIEW IF EXISTS quotes_quoteversion_totals;"

class Migration(migrations.Migration):
    dependencies = [
        ('quotes', '0003_alter_quoteversion_options_and_more'),
    ]
    operations = [
        migrations.RunSQL(VIEW_SQL, reverse_sql=DROP_SQL),
    ]
