// frontend/src/data/hardCaseAirImport.ts
import { DraftQuote } from "../lib/draft-quote-types";

export const hardCaseAirImportData: DraftQuote = {
  "contract_version": "1.0.0",
  "quote_summary": "Draft Quote Suggestion for Air Freight Import - Singapore (SIN) to Port Moresby (POM) via Qantas Air",
  "shipment_context": {
    "origin": "SIN",
    "destination": "POM",
    "mode": "AIR",
    "pieces": 3,
    "actual_weight_kg": 150.0,
    "volumetric_weight_kg": 200.0,
    "chargeable_weight_kg": 200.0,
    "commodity": "GCR"
  },
  "supplier_context": {
    "supplier_name": "Qantas Air Cargo",
    "agent_code": "QAN-SIN"
  },
  "freight": {
    "carrier": "Qantas",
    "service_type": "Standard Air Freight"
  },
  "suggested_charges": [
    {
      "id": "chg-001",
      "status": "suggested",
      "display_label": "Air Freight Weight Charge",
      "raw_label": "Air Freight SIN-POM @ USD 4.50/kg, Min USD 150.00",
      "suggested_product_code": "AF-FREIGHT",
      "product_code_conflict": false,
      "bucket": "airfreight",
      "currency": "USD",
      "amount": 900.00,
      "rate": 4.50,
      "unit": "per_kg",
      "calculation_basis": "chargeable_weight",
      "minimum_charge": 150.00,
      "percentage_base": null,
      "quantity": 200.0,
      "include_in_totals": true,
      "conditions": [
        "Subject to carrier flight availability"
      ],
      "warnings": [],
      "review_reason": null,
      "evidence": {
        "source_text": "Air Freight rate to POM is USD 4.50 per kg (chargeable weight), minimum USD 150.00.",
        "page": 1,
        "section": "Freight charges",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 50.0, 300.0, 70.0],
        "extraction_note": "Extracted rate and minimum successfully"
      },
      "similarity_group_id": "sim-freight-charges",
      "correction_actions": []
    },
    {
      "id": "chg-002",
      "status": "needs_review",
      "display_label": "Fuel Surcharge",
      "raw_label": "FSC USD 0.85/kg",
      "suggested_product_code": null,
      "product_code_conflict": true,
      "bucket": "airfreight",
      "currency": "USD",
      "amount": 170.00,
      "rate": 0.85,
      "unit": "per_kg",
      "calculation_basis": "chargeable_weight",
      "minimum_charge": null,
      "percentage_base": null,
      "quantity": 200.0,
      "include_in_totals": true,
      "conditions": [],
      "warnings": [
        "Ambiguous product code match: could map to FSC-AIR or SUR-FUEL"
      ],
      "review_reason": "Ambiguous ProductCode mapping due to multiple matching catalog rules.",
      "evidence": {
        "source_text": "FSC rate: USD 0.85 per kg",
        "page": 1,
        "section": "Freight surcharges",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 75.0, 200.0, 95.0],
        "extraction_note": "Uncertain whether FSC maps to FSC-AIR or generic FUEL"
      },
      "similarity_group_id": "sim-surcharges",
      "correction_actions": [
        "Select product code from matches: FSC-AIR, SUR-FUEL"
      ]
    },
    {
      "id": "chg-003",
      "status": "needs_review",
      "display_label": "Security Charge",
      "raw_label": "Security Surcharge USD 0.15/kg",
      "suggested_product_code": "SEC-SUR",
      "product_code_conflict": false,
      "bucket": "airfreight",
      "currency": "USD",
      "amount": 30.00,
      "rate": 0.15,
      "unit": "per_kg",
      "calculation_basis": "chargeable_weight",
      "minimum_charge": null,
      "percentage_base": null,
      "quantity": 200.0,
      "include_in_totals": true,
      "conditions": [],
      "warnings": [
        "Currency USD inherited from freight block but not explicitly declared for this line."
      ],
      "review_reason": "Inherited currency warning: currency was assumed from context rather than stated.",
      "evidence": {
        "source_text": "Security Surcharge: 0.15/kg",
        "page": 1,
        "section": "Freight surcharges",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 100.0, 200.0, 120.0],
        "extraction_note": "No currency symbol found next to 0.15, inherited USD from freight line"
      },
      "similarity_group_id": "sim-surcharges",
      "correction_actions": [
        "Confirm currency USD or edit manually"
      ]
    },
    {
      "id": "chg-004",
      "status": "suggested",
      "display_label": "War Risk Surcharge",
      "raw_label": "War Risk Surcharge 5% of Freight Charge",
      "suggested_product_code": "WAR-RISK",
      "product_code_conflict": false,
      "bucket": "airfreight",
      "currency": "USD",
      "amount": 45.00,
      "rate": 5.00,
      "unit": "percentage",
      "calculation_basis": "percentage_base",
      "minimum_charge": null,
      "percentage_base": "chg-001",
      "quantity": null,
      "include_in_totals": true,
      "conditions": [],
      "warnings": [],
      "review_reason": null,
      "evidence": {
        "source_text": "War Risk Surcharge: 5% of air freight base charge",
        "page": 1,
        "section": "Freight surcharges",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 125.0, 200.0, 145.0],
        "extraction_note": "Calculated 5% of 900.00 USD = 45.00 USD"
      },
      "similarity_group_id": null,
      "correction_actions": []
    },
    {
      "id": "chg-005",
      "status": "suggested",
      "display_label": "Origin Handling Fee",
      "raw_label": "Origin Handling SGD 50.00 flat",
      "suggested_product_code": "ORG-HANDLING",
      "product_code_conflict": false,
      "bucket": "origin_charges",
      "currency": "SGD",
      "amount": 50.00,
      "rate": 50.00,
      "unit": "flat",
      "calculation_basis": "flat",
      "minimum_charge": null,
      "percentage_base": null,
      "quantity": 1.0,
      "include_in_totals": true,
      "conditions": [],
      "warnings": [
        "Mixed currency: This charge is in SGD, which differs from the primary shipment currency USD."
      ],
      "review_reason": null,
      "evidence": {
        "source_text": "Origin Handling charge: SGD 50.00 flat fee",
        "page": 1,
        "section": "Origin charges",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 150.0, 200.0, 170.0],
        "extraction_note": "Correctly extracted SGD currency"
      },
      "similarity_group_id": null,
      "correction_actions": []
    }
  ],
  "commercial_terms": [
    {
      "type": "validity",
      "text": "Validity of rates: rates valid from 2026-07-01 until 2026-07-31",
      "normalized_value": "2026-07-31",
      "status": "suggested",
      "evidence": {
        "source_text": "valid from 2026-07-01 until 2026-07-31",
        "page": 1,
        "section": "Validity",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 200.0, 300.0, 220.0],
        "extraction_note": "Extracted validity end date"
      },
      "review_reason": null
    },
    {
      "type": "density_ratio",
      "text": "Volumetric ratio: 1:6000 density rule applies to air freight",
      "normalized_value": "6000",
      "status": "suggested",
      "evidence": {
        "source_text": "density ratio 1:6000",
        "page": 1,
        "section": "Freight calculation details",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 225.0, 300.0, 245.0],
        "extraction_note": "Used for chargeable weight conversion verification"
      },
      "review_reason": null
    },
    {
      "type": "carrier_acceptance",
      "text": "All shipments subject to carrier space and booking acceptance",
      "normalized_value": null,
      "status": "suggested",
      "evidence": {
        "source_text": "subject to carrier space and booking acceptance",
        "page": 2,
        "section": "Standard terms and conditions",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 30.0, 300.0, 50.0],
        "extraction_note": "General operational disclaimer"
      },
      "review_reason": null
    },
    {
      "type": "exclusion",
      "text": "Excludes customs clearance, duties, and local delivery in Port Moresby",
      "normalized_value": null,
      "status": "suggested",
      "evidence": {
        "source_text": "Excludes destination local charges, customs clearance, and duty/taxes",
        "page": 2,
        "section": "Standard terms and conditions",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 60.0, 300.0, 80.0],
        "extraction_note": "Parsed local delivery and clearance exclusions"
      },
      "review_reason": null
    }
  ],
  "warnings": [
    "Mixed currency warning: Multiple currencies (USD, SGD) found in charge items. Totals validation comparison requires single currency.",
    "Totals mismatch warning: Extracted total from document does not match sum of suggested charges."
  ],
  "unclassified_items": [
    {
      "id": "unclass-001",
      "raw_text": "Possible cartage / transfer charge: SGD 120.00 might apply if transferred to secondary warehouse",
      "evidence": {
        "source_text": "SGD 120.00 cartage to CFS in case of cargo split",
        "page": 1,
        "section": "Warehouse instructions",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": [10.0, 180.0, 250.0, 195.0],
        "extraction_note": "Looks like a conditional local origin charge but details are ambiguous"
      },
      "review_reason": "Unclassified commercial-looking item requires operator classification"
    }
  ],
  "ignored_items": [
    {
      "id": "ign-001",
      "raw_text": "This email and any attachments are confidential and intended solely for the addressee.",
      "ignored_reason": "Standard boilerplate email confidentiality disclaimer",
      "evidence": {
        "source_text": "This email and any attachments are confidential...",
        "page": 2,
        "section": "Boilerplate",
        "row_index": null,
        "table_index": null,
        "document_reference": "QAN-QUOTE-9912.pdf",
        "bounding_box": null,
        "extraction_note": "Standard email signature disclaimer ignored"
      }
    }
  ],
  "totals_validation": {
    "math_balances": false,
    "currency_consistent": false,
    "extracted_total": 1100.00,
    "calculated_total": 1145.00,
    "difference": 45.00,
    "tolerance": 0.00,
    "warnings": [
      "Extracted total USD 1100.00 is different from calculated total USD 1145.00 (sum of USD charges only, excluding SGD Origin Handling)."
    ]
  },
  "review_queue": [
    {
      "id": "chg-002",
      "type": "charge_needs_review",
      "message": "Product code mapping is ambiguous for Fuel Surcharge"
    },
    {
      "id": "chg-003",
      "type": "charge_needs_review",
      "message": "Currency USD was inherited by context for Security Charge"
    },
    {
      "id": "unclass-001",
      "type": "unclassified_item",
      "message": "Unclassified commercial-looking item requires operator classification"
    }
  ],
  "correction_actions": [
    {
      "charge_id": "chg-002",
      "action_type": "RESOLVE_PRODUCT_CODE",
      "options": ["FSC-AIR", "SUR-FUEL"]
    },
    {
      "charge_id": "chg-003",
      "action_type": "CONFIRM_INHERITED_CURRENCY",
      "options": ["USD", "SGD", "PGK"]
    },
    {
      "item_id": "unclass-001",
      "action_type": "CLASSIFY_ITEM",
      "options": ["ADD_AS_CHARGE", "IGNORE_ITEM"]
    }
  ],
  "metadata": {
    "sender_domain": "qantas.com.au",
    "historical_override_rules": {}
  }
};
