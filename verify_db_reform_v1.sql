\echo === Extensions ===
SELECT 'btree_gist installed? ' || EXISTS (SELECT 1 FROM pg_extension WHERE extname='btree_gist') AS ext_ok;

\echo === Lookup tables exist ===
SELECT 'currencies exists? ' || (to_regclass('public.currencies') IS NOT NULL) AS ok1;
SELECT 'units exists? '      || (to_regclass('public.units')      IS NOT NULL) AS ok2;

\echo === New columns present ===
SELECT 'quotes.is_incomplete present? ' || EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_name='quotes' AND column_name='is_incomplete'
) AS ok3;

SELECT 'quote_lines.side present? ' || EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_name='quote_lines' AND column_name='side'
) AS ok4;

\echo === Money precision normalized (quote_lines) ===
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name='quote_lines'
  AND column_name IN ('unit_price','extended_price','side')
ORDER BY column_name;

\echo === Audience FKs added & backfilled ===
SELECT 'orgs.audience_id NULL rows = ' || COUNT(*) FROM organizations WHERE audience_id IS NULL;
SELECT 'policy.audience_id NULL rows = ' || COUNT(*) FROM pricing_policy WHERE audience_id IS NULL;

\echo === Foreign keys present ===
SELECT conname FROM pg_constraint
WHERE conname IN (
  'fk_quotes_currency','fk_quote_lines_currency','fk_quote_lines_unit',
  'fk_orgs_audience','fk_policy_audience',
  'fk_ratecard_fees_currency','fk_service_items_currency'
)
ORDER BY conname;

\echo === Exclusion constraints (no overlaps) ===
SELECT conrelid::regclass AS table, conname
FROM pg_constraint
WHERE contype='x' AND conrelid::regclass::text IN ('ratecards','cartage_ladders','storage_tiers')
ORDER BY conrelid::regclass::text, conname;

\echo === Unique route_legs(route_id,sequence) ===
SELECT conname FROM pg_constraint
WHERE conrelid='route_legs'::regclass AND conname='route_legs_route_id_sequence_uniq';

\echo === JSONB speed-ups (GIN indexes) ===
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename='quotes' AND indexname='quotes_req_snapshot_gin';
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename='ratecard_fees' AND indexname='ratecard_fees_applies_if_gin';
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename='service_items' AND indexname='service_items_conditions_gin';

\echo === JSON presence checks (NOT VALID) present? ===
SELECT conname, convalidated
FROM pg_constraint
WHERE conname IN ('chk_applies_if_has_kind','chk_conditions_has_kind')
ORDER BY conname;

\echo === Stations IATA normalized & check in place ===
SELECT 'stations iata bad rows = ' || COUNT(*)
FROM stations
WHERE (length(iata)<>3 OR iata<>upper(iata));

SELECT conname, convalidated
FROM pg_constraint
WHERE conname='chk_stations_iata_len';

\echo === Sanity: zero overlaps currently in data ===
-- ratecards window overlap
WITH rc AS (
  SELECT id, provider_id, audience_id, name,
         daterange(effective_date, COALESCE(expiry_date,'9999-12-31')) AS dr
  FROM ratecards
)
SELECT 'ratecards overlap pairs = ' || COUNT(*)
FROM rc a JOIN rc b
  ON a.provider_id=b.provider_id AND a.audience_id=b.audience_id AND a.name=b.name
 AND a.id<b.id AND a.dr && b.dr;

-- cartage ladders overlap per ratecard
WITH cl AS (
  SELECT id, ratecard_id, numrange(min_weight_kg,max_weight_kg,'[]') AS rr
  FROM cartage_ladders
)
SELECT 'cartage_ladders overlaps = ' || COUNT(*)
FROM cl a JOIN cl b
  ON a.ratecard_id=b.ratecard_id AND a.id<b.id AND a.rr && b.rr;

-- storage tiers overlap per (ratecard, group_code)
WITH st AS (
  SELECT id, ratecard_id, group_code, int4range(week_from,week_to,'[]') AS rr
  FROM storage_tiers
)
SELECT 'storage_tiers overlaps = ' || COUNT(*)
FROM st a JOIN st b
  ON a.ratecard_id=b.ratecard_id AND a.group_code=b.group_code
 AND a.id<b.id AND a.rr && b.rr;
