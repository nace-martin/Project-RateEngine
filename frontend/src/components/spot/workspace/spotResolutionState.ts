import { DraftCharge, DraftChargeStatus, Evidence, DraftQuote } from "../../../lib/draft-quote-types";

export interface Decision {
    id: string; // charge id or item id
    type: "map" | "request" | "ignore" | "accept" | "add";
    description: string;
    originalState: {
        suggestedCharges: DraftCharge[];
        reviewQueue: Array<{ id: string; type: string; message: string }>;
        unclassifiedItems: Array<{ id: string; raw_text: string; evidence: Evidence | null; review_reason: string }>;
        ignoredItems: Array<{ id: string; raw_text: string; ignored_reason: string; evidence: Evidence | null }>;
    };
}

export type SpotWorkspaceIssue =
    | {
          type: "review_item";
          id: string;
          title: string;
          problem: string;
          evidence: Evidence | null;
          charge: DraftCharge;
      }
    | {
          type: "unknown_charge";
          id: string;
          title: string;
          problem: string;
          evidence: Evidence | null;
          itemDetails: { id: string; raw_text: string; evidence: Evidence | null; review_reason: string };
      };

export interface SpotResolutionState {
    suggestedCharges: DraftCharge[];
    reviewQueue: Array<{ id: string; type: string; message: string }>;
    unclassifiedItems: Array<{ id: string; raw_text: string; evidence: Evidence | null; review_reason: string }>;
    ignoredItems: Array<{ id: string; raw_text: string; ignored_reason: string; evidence: Evidence | null }>;
    decisions: Decision[];
    reviewSession: {
        status: "draft" | "finalized" | "in_review";
        finalized_by: number | null;
        finalized_at: string | null;
        remaining_blockers: number;
        available_actions: string[];
    };
    activeIssueId: string | null;
    selectedActionType: string | null;
    showHelpText: boolean;
    requestForm: {
        label: string;
        source: string;
        currency: string;
        amount: string;
        bucket: string;
        unit: string;
    };
    unknownWizard: {
        step: number;
        classification: string | null;
    };
    addChargeForm: {
        name: string;
        bucket: string;
        currency: string;
        amount: string;
        unit: string;
        productCode: string;
    };
    actionMessage: string | null;
    prototypeOverride: boolean;
}

export type SpotResolutionAction =
    | { type: "RESET_FROM_SERVER"; payload: DraftQuote }
    | { type: "SELECT_ISSUE"; payload: { issueId: string | null } }
    | { type: "OPEN_MAP_EXISTING" }
    | { type: "OPEN_REQUEST_PRODUCT_CODE"; payload: { label: string; source: string; currency: string; amount: string; bucket?: string; unit?: string } }
    | { type: "OPEN_ADD_UNKNOWN_CHARGE"; payload: { name: string; amount: string } }
    | { type: "CANCEL_ACTION" }
    | { type: "UPDATE_REQUEST_FORM"; payload: Partial<SpotResolutionState["requestForm"]> }
    | { type: "UPDATE_ADD_CHARGE_FORM"; payload: Partial<SpotResolutionState["addChargeForm"]> }
    | { type: "CLASSIFY_UNKNOWN"; payload: { classification: string | null; step: number } }
    | { type: "MAP_PRODUCT_CODE"; payload: { chargeId: string; productCode: string; displayLabel: string } }
    | { type: "SUBMIT_PRODUCT_CODE_REQUEST"; payload: { chargeId: string; proposedCode: string; sourceText: string } }
    | { type: "USE_APPROVED_PRODUCT_CODE"; payload: { chargeId: string; code: string; displayLabel: string } }
    | { type: "ACCEPT_SUGGESTED_MAPPING"; payload: { chargeId: string; displayLabel: string; suggestedCode: string } }
    | { type: "IGNORE_CHARGE"; payload: { chargeId: string; displayLabel: string; rawLabel: string; evidence: Evidence | null } }
    | { type: "IGNORE_UNKNOWN_CHARGE"; payload: { itemId: string; rawText: string; evidence: Evidence | null } }
    | { type: "APPROVE_UNKNOWN_NOTE"; payload: { itemId: string; rawText: string } }
    | { type: "ADD_UNKNOWN_AS_CHARGE"; payload: { itemId: string; newChargeId: string; chargeName: string; chargeBucket: string; chargeCurrency: string; chargeAmount: number; chargeUnit: string; chargeProductCode: string; evidence: Evidence | null } }
    | { type: "TOGGLE_INCLUDE_IN_TOTALS"; payload: { chargeId: string } }
    | { type: "UNDO_DECISION"; payload: { decisionId: string } }
    | { type: "FINALIZE_REVIEW"; payload: { status: "draft" | "finalized" | "in_review"; finalized_by: number | null; finalized_at: string | null; remaining_blockers: number; available_actions: string[] } }
    | { type: "DISMISS_ACTION_MESSAGE" }
    | { type: "TOGGLE_PROTOTYPE_OVERRIDE" }
    | { type: "TOGGLE_HELP_TEXT" }
    | { type: "SET_ACTION_MESSAGE"; payload: string };

export function createSpotResolutionState(initialData: DraftQuote): SpotResolutionState {
    const reviewQueue = initialData.review_queue || [];
    return {
        suggestedCharges: initialData.suggested_charges || [],
        reviewQueue,
        unclassifiedItems: initialData.unclassified_items || [],
        ignoredItems: initialData.ignored_items || [],
        decisions: [],
        reviewSession: initialData.review_session || {
            status: "draft",
            finalized_by: null,
            finalized_at: null,
            remaining_blockers: reviewQueue.length,
            available_actions: []
        },
        activeIssueId: reviewQueue[0]?.id || initialData.unclassified_items?.[0]?.id || null,
        selectedActionType: null,
        showHelpText: false,
        requestForm: {
            label: "",
            source: "",
            currency: "",
            amount: "",
            bucket: "",
            unit: "flat"
        },
        unknownWizard: {
            step: 1,
            classification: null
        },
        addChargeForm: {
            name: "New Charge",
            bucket: "",
            currency: initialData.suggested_charges?.find(charge => charge.currency)?.currency || "",
            amount: "0",
            unit: "flat",
            productCode: ""
        },
        actionMessage: null,
        prototypeOverride: false
    };
}

function captureSnapshotHelper(state: SpotResolutionState, id: string, type: Decision["type"], desc: string): Decision {
    return {
        id,
        type,
        description: desc,
        originalState: {
            suggestedCharges: JSON.parse(JSON.stringify(state.suggestedCharges)),
            reviewQueue: JSON.parse(JSON.stringify(state.reviewQueue)),
            unclassifiedItems: JSON.parse(JSON.stringify(state.unclassifiedItems)),
            ignoredItems: JSON.parse(JSON.stringify(state.ignoredItems))
        }
    };
}

export function spotResolutionReducer(state: SpotResolutionState, action: SpotResolutionAction): SpotResolutionState {
    switch (action.type) {
        case "RESET_FROM_SERVER":
            return createSpotResolutionState(action.payload);

        case "SELECT_ISSUE":
            return {
                ...state,
                activeIssueId: action.payload.issueId,
                selectedActionType: null,
                unknownWizard: { ...state.unknownWizard, step: 1 }
            };

        case "OPEN_MAP_EXISTING":
            return {
                ...state,
                selectedActionType: "map_existing"
            };

        case "OPEN_REQUEST_PRODUCT_CODE":
            return {
                ...state,
                requestForm: {
                    label: action.payload.label,
                    source: action.payload.source,
                    currency: action.payload.currency,
                    amount: action.payload.amount,
                    bucket: action.payload.bucket || state.requestForm.bucket,
                    unit: action.payload.unit || state.requestForm.unit
                },
                selectedActionType: "request_product_code"
            };

        case "OPEN_ADD_UNKNOWN_CHARGE":
            return {
                ...state,
                addChargeForm: {
                    ...state.addChargeForm,
                    name: action.payload.name,
                    amount: action.payload.amount
                },
                selectedActionType: "add_charge"
            };

        case "CANCEL_ACTION":
            return {
                ...state,
                selectedActionType: null
            };

        case "UPDATE_REQUEST_FORM":
            return {
                ...state,
                requestForm: {
                    ...state.requestForm,
                    ...action.payload
                }
            };

        case "UPDATE_ADD_CHARGE_FORM":
            return {
                ...state,
                addChargeForm: {
                    ...state.addChargeForm,
                    ...action.payload
                }
            };

        case "CLASSIFY_UNKNOWN":
            return {
                ...state,
                unknownWizard:
                    action.payload.step === 1
                        ? { ...state.unknownWizard, step: 1 }
                        : {
                              step: action.payload.step,
                              classification: action.payload.classification
                          }
            };

        case "MAP_PRODUCT_CODE": {
            const { chargeId, productCode, displayLabel } = action.payload;
            const snapshot = captureSnapshotHelper(state, chargeId, "map", `Mapped ${displayLabel} to billing code ${productCode}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== chargeId), snapshot],
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === chargeId ? { ...c, suggested_product_code: productCode, status: "accepted_by_user" as DraftChargeStatus } : c
                ),
                reviewQueue: state.reviewQueue.filter(q => q.id !== chargeId),
                actionMessage: `${displayLabel} mapped to billing code ${productCode}. Resolved and included in draft.`,
                selectedActionType: null
            };
        }

        case "SUBMIT_PRODUCT_CODE_REQUEST": {
            const { chargeId, proposedCode } = action.payload;
            const snapshot = captureSnapshotHelper(state, chargeId, "request", `Requested new billing code for ${proposedCode}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== chargeId), snapshot],
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === chargeId ? { ...c, status: "pending_product_code" as DraftChargeStatus } : c
                ),
                reviewQueue: state.reviewQueue.filter(q => q.id !== chargeId),
                actionMessage: `New ProductCode request created for ${proposedCode}. Resolved locally and pending approval.`,
                selectedActionType: null
            };
        }

        case "USE_APPROVED_PRODUCT_CODE": {
            const { chargeId, code, displayLabel } = action.payload;
            const snapshot = captureSnapshotHelper(state, chargeId, "map", `Used approved billing code ${code} for ${displayLabel}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== chargeId), snapshot],
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === chargeId ? { ...c, suggested_product_code: code, status: "accepted_by_user" as DraftChargeStatus } : c
                ),
                reviewQueue: state.reviewQueue.filter(q => q.id !== chargeId),
                actionMessage: `Approved billing code ${code} applied successfully to ${displayLabel}.`,
                selectedActionType: null
            };
        }

        case "ACCEPT_SUGGESTED_MAPPING": {
            const { chargeId, displayLabel, suggestedCode } = action.payload;
            const snapshot = captureSnapshotHelper(state, chargeId, "accept", `Accepted code ${suggestedCode} for ${displayLabel}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== chargeId), snapshot],
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === chargeId ? { ...c, status: "accepted_by_user" as DraftChargeStatus } : c
                ),
                reviewQueue: state.reviewQueue.filter(q => q.id !== chargeId),
                actionMessage: `Accepted suggested mapping ${suggestedCode} for ${displayLabel}.`,
                selectedActionType: null
            };
        }

        case "IGNORE_CHARGE": {
            const { chargeId, displayLabel, rawLabel, evidence } = action.payload;
            const snapshot = captureSnapshotHelper(state, chargeId, "ignore", `Ignored ${displayLabel}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== chargeId), snapshot],
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === chargeId ? { ...c, status: "ignored" as DraftChargeStatus, include_in_totals: false } : c
                ),
                ignoredItems: [
                    ...state.ignoredItems,
                    {
                        id: chargeId,
                        raw_text: rawLabel,
                        ignored_reason: "Ignored by operator during quote review",
                        evidence: evidence
                    }
                ],
                reviewQueue: state.reviewQueue.filter(q => q.id !== chargeId),
                actionMessage: `${displayLabel} ignored and excluded from totals.`,
                selectedActionType: null
            };
        }

        case "IGNORE_UNKNOWN_CHARGE": {
            const { itemId, rawText, evidence } = action.payload;
            const snapshot = captureSnapshotHelper(state, itemId, "ignore", "Ignored unknown text block");
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== itemId), snapshot],
                ignoredItems: [
                    ...state.ignoredItems,
                    {
                        id: itemId,
                        raw_text: rawText,
                        ignored_reason: "Operator ignored text block as non-commercial text",
                        evidence: evidence
                    }
                ],
                unclassifiedItems: state.unclassifiedItems.filter(i => i.id !== itemId),
                actionMessage: `Ignored unknown text block. Excluded from draft.`,
                selectedActionType: null,
                unknownWizard: { ...state.unknownWizard, step: 1 }
            };
        }

        case "APPROVE_UNKNOWN_NOTE": {
            const { itemId, rawText } = action.payload;
            const snapshot = captureSnapshotHelper(state, itemId, "accept", `Accepted condition note: ${rawText}`);
            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== itemId), snapshot],
                unclassifiedItems: state.unclassifiedItems.filter(i => i.id !== itemId),
                actionMessage: "Note resolved and archived in quote details.",
                selectedActionType: null,
                unknownWizard: { ...state.unknownWizard, step: 1 }
            };
        }

        case "ADD_UNKNOWN_AS_CHARGE": {
            const { itemId, newChargeId, chargeName, chargeBucket, chargeCurrency, chargeAmount, chargeUnit, chargeProductCode, evidence } = action.payload;
            const snapshot = captureSnapshotHelper(state, itemId, "add", `Added unknown block as charge ${chargeName}`);
            const newCharge: DraftCharge = {
                id: newChargeId,
                status: (chargeProductCode ? "accepted_by_user" : "suggested") as DraftChargeStatus,
                display_label: chargeName,
                raw_label: chargeName,
                suggested_product_code: chargeProductCode || null,
                product_code_conflict: !chargeProductCode,
                bucket: chargeBucket,
                currency: chargeCurrency,
                amount: chargeAmount,
                rate: null,
                unit: chargeUnit,
                calculation_basis: null,
                minimum_charge: null,
                percentage_base: null,
                quantity: 1,
                include_in_totals: true,
                conditions: [],
                warnings: [],
                review_reason: null,
                evidence: evidence,
                similarity_group_id: null,
                correction_actions: []
            };

            const updatedReviewQueue = [...state.reviewQueue];
            if (!chargeProductCode) {
                updatedReviewQueue.push({
                    id: newChargeId,
                    type: "charge_needs_review",
                    message: "Newly added charge line requires a valid ProductCode mapping."
                });
            }

            return {
                ...state,
                decisions: [...state.decisions.filter(d => d.id !== itemId), snapshot],
                suggestedCharges: [...state.suggestedCharges, newCharge],
                unclassifiedItems: state.unclassifiedItems.filter(i => i.id !== itemId),
                reviewQueue: updatedReviewQueue,
                actionMessage: `Unknown block added as draft charge line: "${chargeName}".`,
                selectedActionType: null,
                unknownWizard: { ...state.unknownWizard, step: 1 }
            };
        }

        case "TOGGLE_INCLUDE_IN_TOTALS":
            return {
                ...state,
                suggestedCharges: state.suggestedCharges.map(c =>
                    c.id === action.payload.chargeId ? { ...c, include_in_totals: !c.include_in_totals } : c
                )
            };

        case "UNDO_DECISION": {
            const targetDecision = state.decisions.find(d => d.id === action.payload.decisionId);
            if (!targetDecision) {
                return state;
            }
            return {
                ...state,
                suggestedCharges: targetDecision.originalState.suggestedCharges,
                reviewQueue: targetDecision.originalState.reviewQueue,
                unclassifiedItems: targetDecision.originalState.unclassifiedItems,
                ignoredItems: targetDecision.originalState.ignoredItems,
                decisions: state.decisions.filter(d => d.id !== action.payload.decisionId),
                actionMessage: `Undone decision for ${targetDecision.description}.`,
                activeIssueId: action.payload.decisionId,
                selectedActionType: null,
                unknownWizard: { ...state.unknownWizard, step: 1 }
            };
        }

        case "FINALIZE_REVIEW":
            return {
                ...state,
                reviewSession: {
                    status: action.payload.status,
                    finalized_by: action.payload.finalized_by,
                    finalized_at: action.payload.finalized_at,
                    remaining_blockers: action.payload.remaining_blockers,
                    available_actions: action.payload.available_actions
                },
                actionMessage: "Draft Quote review finalized and locked."
            };

        case "DISMISS_ACTION_MESSAGE":
            return {
                ...state,
                actionMessage: null
            };

        case "TOGGLE_PROTOTYPE_OVERRIDE":
            return {
                ...state,
                prototypeOverride: !state.prototypeOverride
            };

        case "TOGGLE_HELP_TEXT":
            return {
                ...state,
                showHelpText: !state.showHelpText
            };

        case "SET_ACTION_MESSAGE":
            return {
                ...state,
                actionMessage: action.payload
            };

        default:
            return state;
    }
}

// Derivations & Selectors
export function selectCombinedUnresolved(state: SpotResolutionState): SpotWorkspaceIssue[] {
    return [
        ...state.reviewQueue.map(item => {
            const charge = state.suggestedCharges.find(c => c.id === item.id);
            return {
                id: item.id,
                type: "review_item" as const,
                title: charge?.display_label || "Needs Review",
                problem: charge?.review_reason || item.message || "Requires validation.",
                evidence: charge?.evidence || null,
                charge: charge!
            };
        }),
        ...state.unclassifiedItems.map(item => ({
            id: item.id,
            type: "unknown_charge" as const,
            title: "Unknown Charge Block",
            problem: "Commercial text block extracted from quote document could not be safely mapped to a standard charge line.",
            evidence: item.evidence || null,
            itemDetails: item
        }))
    ];
}

export function selectCurrentIssue(state: SpotResolutionState): SpotWorkspaceIssue | null {
    const combined = selectCombinedUnresolved(state);
    if (combined.length === 0) return null;
    return combined.find(i => i.id === state.activeIssueId) || combined[0] || null;
}

export function selectActiveCharges(state: SpotResolutionState): DraftCharge[] {
    return state.suggestedCharges.filter(c => c.include_in_totals && c.status !== "ignored");
}

export function selectUniqueCurrencies(state: SpotResolutionState): string[] {
    const active = selectActiveCharges(state);
    return Array.from(new Set(active.map(c => c.currency)));
}

export function selectSubtotals(state: SpotResolutionState): Record<string, number> {
    const active = selectActiveCharges(state);
    const unique = selectUniqueCurrencies(state);
    return unique.reduce((acc, curr) => {
        acc[curr] = active.filter(c => c.currency === curr).reduce((sum, c) => sum + c.amount, 0);
        return acc;
    }, {} as Record<string, number>);
}

export function selectChecklistIssuesResolved(state: SpotResolutionState): boolean {
    return selectCombinedUnresolved(state).length === 0;
}

export function selectChecklistNoUnknown(state: SpotResolutionState): boolean {
    return state.unclassifiedItems.length === 0;
}

export function selectChecklistProductCodesVerified(state: SpotResolutionState): boolean {
    const active = selectActiveCharges(state);
    return active.every(c => c.suggested_product_code !== null && c.status !== "pending_product_code");
}

export function selectCanFinishReview(state: SpotResolutionState): boolean {
    return (
        selectChecklistIssuesResolved(state) &&
        selectChecklistNoUnknown(state) &&
        selectChecklistProductCodesVerified(state)
    );
}

export function selectIsReviewLocked(state: SpotResolutionState): boolean {
    return state.reviewSession.status === "finalized";
}

export function selectCanUsePrototypeOverride(state: SpotResolutionState, isLive: boolean): boolean {
    return !isLive && state.prototypeOverride;
}

export function selectNextStepGuidance(state: SpotResolutionState): string {
    const unresolved = selectCombinedUnresolved(state);
    if (unresolved.length > 0) {
        const first = unresolved[0];
        if (first.type === "review_item") {
            return `Next step: Choose a ProductCode for ${first.title}.`;
        } else {
            return "Next step: Decide whether this unknown text is a real charge.";
        }
    }
    return "Review the remaining commercial term before finishing.";
}
