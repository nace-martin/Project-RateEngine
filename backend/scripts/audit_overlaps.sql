SELECT a.id, b.id
FROM ratecards a
JOIN ratecards b ON a.provider_id=b.provider_id
AND a.audience_id=b.audience_id
AND a.name=b.name
AND daterange(a.effective_date, COALESCE(a.expiry_date,'9999-12-31')) && daterange(b.effective_date, COALESCE(b.expiry_date,'9999-12-31'))
AND a.id < b.id;