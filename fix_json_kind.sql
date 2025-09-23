UPDATE ratecard_fees SET applies_if = '{"kind": "always"}' WHERE applies_if = '{}';
UPDATE service_items SET conditions_json = '{"kind": "always"}' WHERE conditions_json = '{}';