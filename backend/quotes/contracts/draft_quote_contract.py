from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceSchema(BaseModel):
    source_text: str = Field(..., description="Exact matched text from source document")
    page: Optional[int] = Field(None, description="1-based page number")
    section: Optional[str] = Field(None, description="Section heading or context")
    row_index: Optional[int] = Field(None, description="Row index in a table")
    table_index: Optional[int] = Field(None, description="Table index in document")
    document_reference: Optional[str] = Field(None, description="Identifier of the source document")
    bounding_box: Optional[List[float]] = Field(None, description="[x_min, y_min, x_max, y_max] bbox coordinates")
    extraction_note: Optional[str] = Field(None, description="Qualitative note from parsing system")


class DraftChargeSchema(BaseModel):
    id: str = Field(..., description="Unique stable ID or hash of the charge")
    status: str = Field(..., description="Status must be one of: suggested, needs_review, unclassified, ignored, accepted_by_user")
    display_label: str = Field(..., description="Human-friendly charge label")
    raw_label: str = Field(..., description="Raw text label from document")
    suggested_product_code: Optional[str] = Field(None, description="Inferred ERP product code")
    product_code_conflict: bool = Field(False, description="True if product code mapping is ambiguous")
    approved_product_code: Optional[str] = Field(None, description="Approved ProductCode code from request")
    approved_product_code_id: Optional[int] = Field(None, description="Approved ProductCode ID from request")
    product_code_request_id: Optional[int] = Field(None, description="ID of the active ProductCodeCreationRequest")
    rejected_product_code: Optional[str] = Field(None, description="Rejected proposed ProductCode code/name from request")
    rejected_product_code_name: Optional[str] = Field(None, description="Rejected proposed ProductCode display name from request")
    product_code_rejection_reason: Optional[str] = Field(None, description="Reason the ProductCode request was rejected")
    product_code_rejected_at: Optional[str] = Field(None, description="ISO timestamp when the ProductCode request was rejected")
    bucket: str = Field(..., description="Category bucket: airfreight, origin_charges, destination_charges, or other/unclassified")
    currency: str = Field(..., description="3-letter currency code (e.g., USD)")
    amount: Decimal = Field(..., description="Charge monetary amount")
    rate: Optional[Decimal] = Field(None, description="Unit rate")
    unit: Optional[str] = Field(None, description="Unit basis, e.g., per_kg, flat")
    calculation_basis: Optional[str] = Field(None, description="Calculation basis")
    minimum_charge: Optional[Decimal] = Field(None, description="Minimum charge limit")
    percentage_base: Optional[str] = Field(None, description="Base charge target for percentage surcharges")
    quantity: Optional[Decimal] = Field(None, description="Multiplier quantity")
    include_in_totals: bool = Field(True, description="Whether to include this charge in calculated totals")
    conditions: Optional[List[str]] = Field(default_factory=list, description="Extracted conditions")
    warnings: Optional[List[str]] = Field(default_factory=list, description="Validation warnings specific to this charge")
    review_reason: Optional[str] = Field(None, description="Explanation of why manual review is needed")
    evidence: Optional[EvidenceSchema] = Field(None, description="Source document evidence")
    similarity_group_id: Optional[str] = Field(None, description="ID for grouping identical charges across variants")
    correction_actions: Optional[List[str]] = Field(default_factory=list, description="Suggested correction actions")

    @model_validator(mode="after")
    def validate_charge_rules(self) -> DraftChargeSchema:
        valid_statuses = {"suggested", "needs_review", "unclassified", "ignored", "accepted_by_user"}
        if self.status not in valid_statuses:
            raise ValueError(f"Status '{self.status}' is not valid. Must be one of: {valid_statuses}")
        
        # Every suggested charge must have evidence and source_text
        if self.status == "suggested":
            if not self.evidence or not self.evidence.source_text:
                raise ValueError("Suggested charges must have evidence containing source_text.")
            
        return self


class CommercialTermSchema(BaseModel):
    type: str = Field(..., description="Type of commercial term (e.g. validity, density_ratio)")
    text: str = Field(..., description="Raw text of the commercial term")
    normalized_value: Optional[Any] = Field(None, description="Parsed value")
    status: str = Field("suggested", description="Workflow status")
    evidence: Optional[EvidenceSchema] = Field(None, description="Traceability evidence")
    review_reason: Optional[str] = Field(None, description="Explanation of why review is needed")


class UnclassifiedItemSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for unclassified item")
    raw_text: str = Field(..., description="Text segment looking commercial but not parsed")
    evidence: Optional[EvidenceSchema] = Field(None, description="Traceability evidence")
    review_reason: str = Field("Unclassified commercial-looking item requires operator classification", description="Reason for review")


class IgnoredItemSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for ignored item")
    raw_text: str = Field(..., description="Text segment ignored")
    ignored_reason: str = Field(..., description="Reason why the item was ignored (must not be empty)")
    evidence: Optional[EvidenceSchema] = Field(None, description="Traceability evidence")


class TotalsValidationSchema(BaseModel):
    math_balances: bool = Field(..., description="True if calculated_total matches extracted_total")
    currency_consistent: bool = Field(..., description="True if all active charges share the same currency")
    extracted_total: Optional[Decimal] = Field(None, description="Total extracted from the document")
    calculated_total: Optional[Decimal] = Field(None, description="Sum of active suggested charges")
    difference: Optional[Decimal] = Field(None, description="Calculated - Extracted total")
    tolerance: Decimal = Field(Decimal("0.00"), description="Acceptable calculation tolerance")
    warnings: List[str] = Field(default_factory=list, description="Totals-related warnings")


class DraftQuoteReviewSessionSchema(BaseModel):
    status: str = Field("draft", description="Review status: draft, in_review, finalized")
    finalized_by: Optional[int] = Field(None, description="User ID that finalized this review")
    finalized_at: Optional[str] = Field(None, description="ISO timestamp when review was finalized")
    remaining_blockers: int = Field(0, description="Critical blockers that must be cleared before finalization")
    available_actions: List[str] = Field(default_factory=list, description="Available review session actions")

    @model_validator(mode="after")
    def validate_review_status(self) -> DraftQuoteReviewSessionSchema:
        if self.status not in {"draft", "in_review", "finalized"}:
            raise ValueError("Review status must be draft, in_review, or finalized.")
        return self


class DraftQuoteSchema(BaseModel):
    contract_version: str = Field(..., description="Version of the draft quote contract")
    quote_summary: str = Field(..., description="Summary overview of the draft quote")
    shipment_context: Dict[str, Any] = Field(..., description="Shipment metrics and route parameters")
    supplier_context: Dict[str, Any] = Field(..., description="Vendor/Agent identification context")
    freight: Dict[str, Any] = Field(..., description="Main leg freight details")
    suggested_charges: List[DraftChargeSchema] = Field(default_factory=list, description="Extracted charge suggestions")
    commercial_terms: List[CommercialTermSchema] = Field(default_factory=list, description="Extracted commercial terms")
    warnings: List[str] = Field(default_factory=list, description="Top-level validation warnings")
    unclassified_items: List[UnclassifiedItemSchema] = Field(default_factory=list, description="Unclassified commercial items")
    ignored_items: List[IgnoredItemSchema] = Field(default_factory=list, description="Ignored document segments")
    totals_validation: TotalsValidationSchema = Field(..., description="Mathematical comparison of totals")
    review_queue: List[Dict[str, Any]] = Field(default_factory=list, description="Items queued for manual operator review")
    correction_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Action descriptors to correct validation issues")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata and sender-based memory placeholders")
    review_session: DraftQuoteReviewSessionSchema = Field(default_factory=DraftQuoteReviewSessionSchema, description="Draft Quote review session state")

    @model_validator(mode="after")
    def validate_draft_quote(self) -> DraftQuoteSchema:
        # Check that ignored items have non-empty ignored_reason
        for item in self.ignored_items:
            if not item.ignored_reason or not item.ignored_reason.strip():
                raise ValueError(f"Ignored item {item.id} requires a non-empty ignored_reason.")

        # Ensure no suggested charge has status accepted_by_user on initial intake
        # Verify that unclassified and needs_review charges are correctly referenced in the review_queue
        review_ids = {item.get("id") for item in self.review_queue if item.get("id")}
        
        for charge in self.suggested_charges:
            if charge.status == "needs_review":
                if charge.id not in review_ids:
                    raise ValueError(f"Charge {charge.id} requires review but is not in the review_queue.")
        
        for item in self.unclassified_items:
            if item.id not in review_ids:
                raise ValueError(f"Unclassified item {item.id} is not present in the review_queue.")

        return self


class AuditMetadataSchema(BaseModel):
    user_id: int = Field(..., description="ID of the user making the decision")
    timestamp: str = Field(..., description="ISO timestamp of when decision was recorded")


class MapToProductCodeDetails(BaseModel):
    product_code: str = Field(..., description="Master catalog product code string")


class RequestProductCodeDetails(BaseModel):
    proposed_code: str = Field(..., description="Proposed code string")
    description: str = Field(..., description="Proposed code description")
    category: str = Field(..., description="Target category (freight, etc.)")
    domain: str = Field(..., description="Target domain (IMPORT, EXPORT, DOMESTIC)")
    reason: str = Field(..., description="Operator justification for request")


class UseApprovedProductCodeDetails(BaseModel):
    product_code_request_id: int = Field(..., description="ID of the approved ProductCodeCreationRequest")
    product_code_id: int = Field(..., description="ID of the approved ProductCode")


class IgnoreDetails(BaseModel):
    reason: str = Field(..., description="Reason why item is ignored (must not be empty)")


class ChargeValuesSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    display_label: Optional[str] = Field(None, description="Human-friendly charge label")
    description: Optional[str] = Field(None, description="Human-friendly charge description")
    amount: Optional[Decimal] = Field(None, description="Monetary amount value")
    currency: Optional[str] = Field(None, description="3-letter currency code")
    rate: Optional[Decimal] = Field(None, description="Monetary rate per unit")
    unit: Optional[str] = Field(None, description="Charge unit basis")
    calculation_basis: Optional[str] = Field(None, description="Calculation basis")
    minimum_charge: Optional[Decimal] = Field(None, description="Minimum charge limit")
    include_in_totals: Optional[bool] = Field(None, description="Whether to include this charge in calculated totals")
    conditions: Optional[List[str]] = Field(None, description="Charge conditions")
    notes: Optional[str] = Field(None, description="Charge notes")


class EditChargeDetails(BaseModel):
    original_values: ChargeValuesSchema = Field(..., description="Original field values")
    updated_values: ChargeValuesSchema = Field(..., description="Updated field values")

    @model_validator(mode="after")
    def validate_updated_values(self) -> EditChargeDetails:
        if not self.updated_values.model_dump(exclude_none=True):
            raise ValueError("edit_charge requires at least one updated value.")
        return self


class ClassifyUnclassifiedDetails(BaseModel):
    classification: str = Field("charge", description="charge or ignored")
    bucket: str = Field(..., description="Target bucket for classification")
    display_label: str = Field(..., description="Display label for the new charge line")
    product_code: str = Field(..., description="Target product code for classification")
    amount: Decimal = Field(..., description="Parsed amount")
    currency: str = Field(..., description="3-letter currency code")
    rate: Optional[Decimal] = Field(None, description="Parsed rate")
    unit: Optional[str] = Field(None, description="Parsed unit")
    minimum_charge: Optional[Decimal] = Field(None, description="Parsed minimum limit")
    reason: Optional[str] = Field(None, description="Operator reason")


class IgnoreUnclassifiedDetails(BaseModel):
    classification: str = Field(..., description="ignored/non-commercial classification")
    reason: str = Field(..., description="Reason why item is ignored")


class DecisionItemSchema(BaseModel):
    decision_id: str = Field(..., description="Stable client decision ID")
    type: str = Field(..., description="Decision action type")
    target_id: str = Field(..., description="Target charge or unclassified block ID")
    details: Dict[str, Any] = Field(default_factory=dict, description="Action-specific options")
    audit_metadata: AuditMetadataSchema = Field(..., description="Operator audit trail metadata")

    @model_validator(mode="after")
    def validate_details_by_type(self) -> DecisionItemSchema:
        valid_types = {
            "accept_suggestion",
            "map_to_product_code",
            "request_product_code",
            "ignore",
            "edit_charge",
            "classify_unclassified",
            "use_approved_product_code",
        }
        if self.type not in valid_types:
            raise ValueError(f"Invalid decision type: {self.type}")

        if self.type == "map_to_product_code":
            MapToProductCodeDetails(**self.details)
        elif self.type == "request_product_code":
            RequestProductCodeDetails(**self.details)
        elif self.type == "use_approved_product_code":
            UseApprovedProductCodeDetails(**self.details)
        elif self.type == "ignore":
            IgnoreDetails(**self.details)
            if not self.details.get("reason") or not str(self.details["reason"]).strip():
                raise ValueError("Ignored decisions must carry a non-empty reason.")
        elif self.type == "edit_charge":
            EditChargeDetails(**self.details)
        elif self.type == "classify_unclassified":
            classification = str(self.details.get("classification") or "charge").lower()
            if classification in {"ignored", "ignore", "non_commercial", "non-commercial"}:
                IgnoreUnclassifiedDetails(**self.details)
            else:
                ClassifyUnclassifiedDetails(**self.details)
        
        return self


class DraftQuoteResolveSchema(BaseModel):
    idempotency_key: UUID = Field(..., description="UUID token ensuring transaction idempotency")
    decisions: List[DecisionItemSchema] = Field(default_factory=list, description="List of operator decisions")


class DecisionResultSchema(BaseModel):
    decision_id: str = Field(..., description="Client decision ID reference")
    target_id: str = Field(..., description="Target charge or unclassified block ID")
    type: str = Field(..., description="Decision action type")
    status: str = Field(..., description="Application status: applied, rejected, skipped")
    message: str = Field(..., description="Descriptive status note")
    error_code: Optional[str] = Field(None, description="Optional programmatic error code")

    @model_validator(mode="after")
    def validate_result_status(self) -> DecisionResultSchema:
        valid_statuses = {"applied", "rejected", "skipped"}
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid result status: {self.status}")
        return self


class DraftQuoteResolveResponseSchema(BaseModel):
    status: str = Field(..., description="Overall resolve status: accepted, partially_accepted, rejected, not_implemented")
    idempotency_key: UUID = Field(..., description="The transaction idempotency key")
    applied_decisions: List[DecisionResultSchema] = Field(default_factory=list, description="List of successfully applied decisions")
    rejected_decisions: List[DecisionResultSchema] = Field(default_factory=list, description="List of rejected decisions")
    validation_errors: List[str] = Field(default_factory=list, description="Validations/errors preventing apply")
    unresolved_items_remaining: Optional[int] = Field(None, description="Count of remaining blocker items needing attention")
    envelope_id: Optional[UUID] = Field(None, description="Target SPOT envelope ID")
    message: str = Field(..., description="Overall summary status message")

    @model_validator(mode="after")
    def validate_response_status(self) -> DraftQuoteResolveResponseSchema:
        valid_statuses = {"accepted", "partially_accepted", "rejected", "not_implemented"}
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid response status: {self.status}")
        return self


class DraftQuoteFinalizeSchema(BaseModel):
    idempotency_key: UUID = Field(..., description="UUID token ensuring finalize idempotency")
    audit_metadata: Dict[str, Any] = Field(default_factory=dict, description="Operator audit metadata")


class DraftQuoteFinalizeResponseSchema(BaseModel):
    status: str = Field(..., description="accepted or rejected")
    idempotency_key: UUID = Field(..., description="The finalize idempotency key")
    envelope_id: UUID = Field(..., description="Target SPOT envelope ID")
    review_status: str = Field(..., description="Current review status")
    remaining_blockers: int = Field(..., description="Critical blockers remaining")
    blockers: List[Dict[str, Any]] = Field(default_factory=list, description="Blocking items preventing finalization")
    finalized_by: Optional[int] = Field(None, description="User ID that finalized this review")
    finalized_at: Optional[str] = Field(None, description="ISO timestamp when review was finalized")
    message: str = Field(..., description="Finalize result message")


class DraftQuoteReopenResponseSchema(BaseModel):
    status: str = Field(..., description="accepted or rejected")
    envelope_id: UUID = Field(..., description="Target SPOT envelope ID")
    review_status: str = Field(..., description="Current review status")
    message: str = Field(..., description="Reopen result message")


