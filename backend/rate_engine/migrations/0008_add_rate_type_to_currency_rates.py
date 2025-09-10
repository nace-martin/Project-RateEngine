from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rate_engine", "0007_ensure_rate_strategy_column"),
    ]

    # Safe to run inside a transaction; no CONCURRENT operations
    atomic = True

    operations = [
        migrations.RunSQL(
            sql=r"""
            -- 1) Add column if missing
            ALTER TABLE currency_rates
            ADD COLUMN IF NOT EXISTS rate_type VARCHAR(8) NOT NULL DEFAULT 'BUY';

            -- 2) Drop existing unique(as_of_ts, base_ccy, quote_ccy) constraint if present
            DO $$
            DECLARE conname text;
            BEGIN
              SELECT c.conname INTO conname
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
              WHERE t.relname = 'currency_rates'
                AND c.contype = 'u'
                AND (
                  SELECT array_agg(a.attname ORDER BY a.attnum)
                  FROM unnest(c.conkey) k(attnum)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                ) = ARRAY['as_of_ts','base_ccy','quote_ccy'];
              IF conname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE currency_rates DROP CONSTRAINT %I', conname);
              END IF;
            END$$;

            -- 3) Add new unique(as_of_ts, base_ccy, quote_ccy, rate_type) if missing
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'currency_rates'
                  AND c.contype = 'u'
                  AND c.conname = 'currency_rates_asof_base_quote_type_key'
              ) THEN
                ALTER TABLE currency_rates
                  ADD CONSTRAINT currency_rates_asof_base_quote_type_key
                  UNIQUE (as_of_ts, base_ccy, quote_ccy, rate_type);
              END IF;
            END$$;
            """,
            reverse_sql=r"""
            -- Reverse: drop 4-col unique, restore 3-col unique, drop column
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'currency_rates'
                  AND c.contype = 'u'
                  AND c.conname = 'currency_rates_asof_base_quote_type_key'
              ) THEN
                ALTER TABLE currency_rates DROP CONSTRAINT currency_rates_asof_base_quote_type_key;
              END IF;
            END$$;

            DO $$
            DECLARE conname text;
            BEGIN
              -- Recreate a 3-column unique if it does not exist
              SELECT c.conname INTO conname
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
              WHERE t.relname = 'currency_rates'
                AND c.contype = 'u'
                AND (
                  SELECT array_agg(a.attname ORDER BY a.attnum)
                  FROM unnest(c.conkey) k(attnum)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                ) = ARRAY['as_of_ts','base_ccy','quote_ccy'];
              IF conname IS NULL THEN
                ALTER TABLE currency_rates
                  ADD CONSTRAINT currency_rates_as_of_ts_base_ccy_quote_ccy_key
                  UNIQUE (as_of_ts, base_ccy, quote_ccy);
              END IF;
            END$$;

            ALTER TABLE currency_rates DROP COLUMN IF EXISTS rate_type;
            """,
        ),
    ]

