from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rate_engine", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                """
                -- Ensure currency_rates can store distinct BUY/SELL per timestamp
                DO $$
                BEGIN
                    -- Drop old unique constraint if it exists (without rate_type)
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint c
                        JOIN pg_class t ON c.conrelid = t.oid
                        WHERE t.relname = 'currency_rates'
                          AND c.conname = 'currency_rates_as_of_ts_base_ccy_quote_ccy_key'
                    ) THEN
                        ALTER TABLE currency_rates
                        DROP CONSTRAINT currency_rates_as_of_ts_base_ccy_quote_ccy_key;
                    END IF;

                    -- Add new unique constraint including rate_type
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint c
                        JOIN pg_class t ON c.conrelid = t.oid
                        WHERE t.relname = 'currency_rates'
                          AND c.conname = 'currency_rates_as_of_ts_base_ccy_quote_ccy_rate_type_key'
                    ) THEN
                        ALTER TABLE currency_rates
                        ADD CONSTRAINT currency_rates_as_of_ts_base_ccy_quote_ccy_rate_type_key
                        UNIQUE (as_of_ts, base_ccy, quote_ccy, rate_type);
                    END IF;
                END$$;
                """
            ),
            reverse_sql=(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint c
                        JOIN pg_class t ON c.conrelid = t.oid
                        WHERE t.relname = 'currency_rates'
                          AND c.conname = 'currency_rates_as_of_ts_base_ccy_quote_ccy_rate_type_key'
                    ) THEN
                        ALTER TABLE currency_rates
                        DROP CONSTRAINT currency_rates_as_of_ts_base_ccy_quote_ccy_rate_type_key;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint c
                        JOIN pg_class t ON c.conrelid = t.oid
                        WHERE t.relname = 'currency_rates'
                          AND c.conname = 'currency_rates_as_of_ts_base_ccy_quote_ccy_key'
                    ) THEN
                        ALTER TABLE currency_rates
                        ADD CONSTRAINT currency_rates_as_of_ts_base_ccy_quote_ccy_key
                        UNIQUE (as_of_ts, base_ccy, quote_ccy);
                    END IF;
                END$$;
                """
            ),
        ),
    ]

