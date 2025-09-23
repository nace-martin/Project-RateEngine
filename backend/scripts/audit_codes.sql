-- List unknown currency codes in quotes
SELECT DISTINCT currency FROM quotes
WHERE currency NOT IN (SELECT code FROM currencies);

-- List unknown currency codes in quote_lines
SELECT DISTINCT currency FROM quote_lines
WHERE currency NOT IN (SELECT code FROM currencies);

-- List unknown unit codes in quote_lines
SELECT DISTINCT unit FROM quote_lines
WHERE unit NOT IN (SELECT code FROM units);

-- List unknown audience codes in organizations (assuming audiences table has 'code' column)
SELECT DISTINCT audience FROM organizations
WHERE audience NOT IN (SELECT code FROM audiences);

-- List unknown audience codes in pricing_policy (assuming audiences table has 'code' column)
SELECT DISTINCT audience FROM pricing_policy
WHERE audience NOT IN (SELECT code FROM audiences);