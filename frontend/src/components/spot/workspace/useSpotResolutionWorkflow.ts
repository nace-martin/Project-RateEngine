import { useEffect, useReducer, useState } from "react";
import { DraftCharge, DraftQuote } from "../../../lib/draft-quote-types";
import {
    createSpotResolutionState,
    spotResolutionReducer,
    selectCombinedUnresolved,
    selectCurrentIssue,
    selectActiveCharges,
    selectUniqueCurrencies,
    selectSubtotals,
    selectChecklistIssuesResolved,
    selectChecklistNoUnknown,
    selectChecklistProductCodesVerified,
    selectCanFinishReview,
    selectIsReviewLocked,
    selectCanUsePrototypeOverride,
    selectNextStepGuidance,
    SpotResolutionState
} from "./spotResolutionState";

interface ProductCodeSelectorOption {
    code: string;
    description: string;
    domain: string;
}

const PRODUCT_CODE_DOMAINS = new Set(["IMPORT", "EXPORT", "DOMESTIC"]);

interface UseSpotResolutionWorkflowProps {
    initialData: DraftQuote;
    isLive: boolean;
    envelopeId?: string;
}

export function useSpotResolutionWorkflow({ initialData, isLive, envelopeId }: UseSpotResolutionWorkflowProps) {
    const [state, dispatch] = useReducer(spotResolutionReducer, initialData, createSpotResolutionState);
    const [productCodes, setProductCodes] = useState<ProductCodeSelectorOption[]>([]);
    const [isLoadingProductCodes, setIsLoadingProductCodes] = useState(false);
    const [productCodeLoadError, setProductCodeLoadError] = useState<string | null>(null);
    const [productCodeRetryNonce, setProductCodeRetryNonce] = useState(0);

    const shipmentDirection = String(initialData.shipment_context.direction || "").toUpperCase();
    const productCodeDomain = PRODUCT_CODE_DOMAINS.has(shipmentDirection) ? shipmentDirection : null;

    useEffect(() => {
        let cancelled = false;

        if (!productCodeDomain) {
            setProductCodes([]);
            setProductCodeLoadError("Draft Quote shipment direction is missing; ProductCode selection is disabled.");
            setIsLoadingProductCodes(false);
            return;
        }

        setIsLoadingProductCodes(true);
        setProductCodeLoadError(null);

        import("../../../lib/api")
            .then(({ getProductCodes }) => getProductCodes({ domain: productCodeDomain }))
            .then((codes) => {
                if (cancelled) return;
                setProductCodes(codes.map((code) => ({
                    code: code.code,
                    description: code.description,
                    domain: code.domain
                })));
            })
            .catch((error) => {
                if (cancelled) return;
                const message = error instanceof Error ? error.message : "Failed to fetch ProductCodes";
                setProductCodes([]);
                setProductCodeLoadError(message);
            })
            .finally(() => {
                if (!cancelled) {
                    setIsLoadingProductCodes(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [productCodeDomain, productCodeRetryNonce]);

    const refreshLiveDraftQuote = async () => {
        if (!isLive || !envelopeId) {
            return;
        }
        const { getDraftQuote } = await import("../../../lib/api");
        const refreshed = await getDraftQuote(envelopeId);
        dispatch({ type: "RESET_FROM_SERVER", payload: refreshed });
    };

    // API submission helper
    const submitLiveDecision = async (decisionItem: {
        decision_id: string;
        type: string;
        target_id: string;
        details: Record<string, unknown>;
        audit_metadata: { user_id: number; timestamp: string };
    }) => {
        if (state.reviewSession.status === "finalized") {
            throw new Error("Draft Quote review is finalized and locked.");
        }
        if (!isLive || !envelopeId) {
            return;
        }
        const { resolveDraftQuoteDecisions } = await import("../../../lib/api");
        const cryptoObj = typeof window !== "undefined" ? window.crypto : null;
        const idempotencyKey = cryptoObj && cryptoObj.randomUUID 
            ? cryptoObj.randomUUID() 
            : "3b128522-a89e-4055-bf51-199eecc5628b";

        await resolveDraftQuoteDecisions(envelopeId, {
            idempotency_key: idempotencyKey,
            decisions: [decisionItem]
        });
    };

    // Actions
    const selectIssue = (issueId: string | null) => {
        dispatch({ type: "SELECT_ISSUE", payload: { issueId } });
    };

    const openMapExisting = () => {
        dispatch({ type: "OPEN_MAP_EXISTING" });
    };

    const retryProductCodeLoad = () => {
        setProductCodeRetryNonce((value) => value + 1);
    };

    const openRequestProductCode = (charge: DraftCharge) => {
        dispatch({
            type: "OPEN_REQUEST_PRODUCT_CODE",
            payload: {
                label: charge.display_label,
                source: charge.evidence?.source_text || charge.raw_label,
                currency: charge.currency,
                amount: String(charge.amount)
            }
        });
    };

    const openUnknownProductCodeRequest = (rawText: string) => {
        dispatch({
            type: "OPEN_REQUEST_PRODUCT_CODE",
            payload: {
                label: "Unknown Charge Item",
                source: rawText,
                currency: state.addChargeForm.currency,
                amount: state.addChargeForm.amount,
                bucket: state.addChargeForm.bucket,
                unit: state.addChargeForm.unit
            }
        });
    };

    const openAddUnknownCharge = (name: string, amount: string) => {
        dispatch({
            type: "OPEN_ADD_UNKNOWN_CHARGE",
            payload: { name, amount }
        });
    };

    const cancelAction = () => {
        dispatch({ type: "CANCEL_ACTION" });
    };

    const updateRequestForm = (fields: Partial<SpotResolutionState["requestForm"]>) => {
        dispatch({ type: "UPDATE_REQUEST_FORM", payload: fields });
    };

    const updateAddChargeForm = (fields: Partial<SpotResolutionState["addChargeForm"]>) => {
        dispatch({ type: "UPDATE_ADD_CHARGE_FORM", payload: fields });
    };

    const classifyUnknown = (classification: string | null) => {
        dispatch({
            type: "CLASSIFY_UNKNOWN",
            payload: { classification, step: 2 }
        });
    };

    const returnToUnknownClassification = () => {
        dispatch({
            type: "CLASSIFY_UNKNOWN",
            payload: { classification: null, step: 1 }
        });
    };

    const mapProductCode = async (chargeId: string, productCode: string, displayLabel: string) => {
        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "map_to_product_code",
            target_id: chargeId,
            details: { product_code: productCode },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
        } catch (err) {
            console.error("Failed to submit resolve decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error resolving mapping: ${errMsg}` });
            return;
        }

        dispatch({
            type: "MAP_PRODUCT_CODE",
            payload: { chargeId, productCode, displayLabel }
        });
    };

    const classifyUnknownAsExistingCharge = async (itemId: string, productCode: string, displayLabel: string) => {
        if (selectIsReviewLocked(state)) return;
        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "classify_unclassified",
            target_id: itemId,
            details: {
                classification: "charge",
                product_code: productCode,
                display_label: displayLabel,
                bucket: state.addChargeForm.bucket,
                currency: state.addChargeForm.currency,
                amount: state.addChargeForm.amount,
                unit: state.addChargeForm.unit
            },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
            await refreshLiveDraftQuote();
        } catch (err) {
            console.error("Failed to submit unclassified charge mapping:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error classifying unknown item: ${errMsg}` });
        }
    };

    const submitProductCodeRequest = async (chargeId: string) => {
        const isUnknownItem = state.unclassifiedItems.some(item => item.id === chargeId);
        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "request_product_code",
            target_id: chargeId,
            details: {
                proposed_code: state.requestForm.label,
                description: state.requestForm.source || state.requestForm.label,
                display_label: state.requestForm.label,
                bucket: isUnknownItem ? state.requestForm.bucket : undefined,
                currency: isUnknownItem ? state.requestForm.currency : undefined,
                amount: isUnknownItem ? state.requestForm.amount : undefined,
                unit: isUnknownItem ? state.requestForm.unit : undefined,
                reason: "Operator requested ProductCode review"
            },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
            if (isLive) {
                await refreshLiveDraftQuote();
                return;
            }
        } catch (err) {
            console.error("Failed to submit ProductCode request:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error submitting ProductCode request: ${errMsg}` });
            return;
        }

        dispatch({
            type: "SUBMIT_PRODUCT_CODE_REQUEST",
            payload: { chargeId, proposedCode: state.requestForm.label, sourceText: state.requestForm.source }
        });
    };

    const useApprovedProductCode = async (chargeId: string, charge: DraftCharge) => {
        const reqId = charge.product_code_request_id;
        const pcId = charge.approved_product_code_id;
        const code = charge.approved_product_code || charge.suggested_product_code || "";

        if (!reqId || !pcId) {
            dispatch({ type: "SET_ACTION_MESSAGE", payload: "Missing approved ProductCode request metadata." });
            return;
        }

        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "use_approved_product_code",
            target_id: chargeId,
            details: {
                product_code_request_id: Number(reqId),
                product_code_id: Number(pcId)
            },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
        } catch (err) {
            console.error("Failed to submit resolve decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error resolving mapping: ${errMsg}` });
            return;
        }

        dispatch({
            type: "USE_APPROVED_PRODUCT_CODE",
            payload: { chargeId, code, displayLabel: charge.display_label }
        });
    };

    const acceptSuggestedMapping = async (chargeId: string, displayLabel: string, suggestedCode: string) => {
        if (selectIsReviewLocked(state)) return;
        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "accept_suggestion",
            target_id: chargeId,
            details: {},
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
        } catch (err) {
            console.error("Failed to submit accept suggestion decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error accepting suggested mapping: ${errMsg}` });
            return;
        }

        dispatch({
            type: "ACCEPT_SUGGESTED_MAPPING",
            payload: { chargeId, displayLabel, suggestedCode }
        });
    };

    const ignoreCharge = async (chargeId: string, charge: DraftCharge) => {
        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "ignore",
            target_id: chargeId,
            details: { reason: "Operator ignored rejected ProductCode blocker as non-commercial" },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
        } catch (err) {
            console.error("Failed to submit ignore decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error ignoring charge: ${errMsg}` });
            return;
        }

        dispatch({
            type: "IGNORE_CHARGE",
            payload: { chargeId, displayLabel: charge.display_label, rawLabel: charge.raw_label, evidence: charge.evidence || null }
        });
    };

    const ignoreUnknownCharge = async (itemId: string, rawText: string) => {
        if (selectIsReviewLocked(state)) return;
        const evidence = state.unclassifiedItems.find(i => i.id === itemId)?.evidence || null;
        if (isLive) {
            const decisionId = `dec-${Date.now()}`;
            try {
                await submitLiveDecision({
                    decision_id: decisionId,
                    type: "classify_unclassified",
                    target_id: itemId,
                    details: { classification: "ignored", reason: "Operator ignored unknown item as non-commercial" },
                    audit_metadata: { user_id: 1, timestamp: new Date().toISOString() }
                });
                await refreshLiveDraftQuote();
            } catch (err) {
                const errMsg = err instanceof Error ? err.message : String(err);
                dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error ignoring unknown item: ${errMsg}` });
            }
            return;
        }
        dispatch({
            type: "IGNORE_UNKNOWN_CHARGE",
            payload: { itemId, rawText, evidence }
        });
    };

    const approveUnknownNote = async (itemId: string, rawText: string) => {
        if (isLive) {
            const decisionId = `dec-${Date.now()}`;
            try {
                await submitLiveDecision({
                    decision_id: decisionId,
                    type: "classify_unclassified",
                    target_id: itemId,
                    details: { classification: "note", reason: "Operator approved unknown item as commercial note" },
                    audit_metadata: { user_id: 1, timestamp: new Date().toISOString() }
                });
                await refreshLiveDraftQuote();
            } catch (err) {
                const errMsg = err instanceof Error ? err.message : String(err);
                dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error approving unknown note: ${errMsg}` });
            }
            return;
        }
        dispatch({
            type: "APPROVE_UNKNOWN_NOTE",
            payload: { itemId, rawText }
        });
    };

    const addUnknownAsCharge = async (itemId: string) => {
        if (selectIsReviewLocked(state)) return;
        const evidence = state.unclassifiedItems.find(i => i.id === itemId)?.evidence || null;
        if (isLive) {
            if (!state.addChargeForm.productCode) {
                dispatch({ type: "SET_ACTION_MESSAGE", payload: "Choose an approved ProductCode before adding this unknown charge." });
                return;
            }
            const decisionId = `dec-${Date.now()}`;
            try {
                await submitLiveDecision({
                    decision_id: decisionId,
                    type: "classify_unclassified",
                    target_id: itemId,
                    details: {
                        classification: "charge",
                        product_code: state.addChargeForm.productCode,
                        display_label: state.addChargeForm.name,
                        bucket: state.addChargeForm.bucket,
                        currency: state.addChargeForm.currency,
                        amount: state.addChargeForm.amount,
                        unit: state.addChargeForm.unit
                    },
                    audit_metadata: { user_id: 1, timestamp: new Date().toISOString() }
                });
                await refreshLiveDraftQuote();
            } catch (err) {
                const errMsg = err instanceof Error ? err.message : String(err);
                dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error adding unknown charge: ${errMsg}` });
            }
            return;
        }
        const newChargeId = `chg-new-${Date.now()}`;
        dispatch({
            type: "ADD_UNKNOWN_AS_CHARGE",
            payload: {
                itemId,
                newChargeId,
                chargeName: state.addChargeForm.name,
                chargeBucket: state.addChargeForm.bucket,
                chargeCurrency: state.addChargeForm.currency,
                chargeAmount: Number(state.addChargeForm.amount) || 0,
                chargeUnit: state.addChargeForm.unit,
                chargeProductCode: state.addChargeForm.productCode,
                evidence
            }
        });
    };

    const toggleIncludeInTotals = (chargeId: string) => {
        if (selectIsReviewLocked(state)) return;
        dispatch({ type: "TOGGLE_INCLUDE_IN_TOTALS", payload: { chargeId } });
    };

    const undoDecision = (decisionId: string) => {
        dispatch({ type: "UNDO_DECISION", payload: { decisionId } });
    };

    const finalizeReview = async () => {
        const canFinalize = selectCanFinishReview(state);
        const isLocked = selectIsReviewLocked(state);
        if (!canFinalize || isLocked) {
            return;
        }

        if (isLive && envelopeId) {
            try {
                const { finalizeDraftQuoteReview } = await import("../../../lib/api");
                const cryptoObj = typeof window !== "undefined" ? window.crypto : null;
                const idempotencyKey = cryptoObj && cryptoObj.randomUUID 
                    ? cryptoObj.randomUUID() 
                    : "47c7fa2d-8a4f-4cdb-9fbf-a396ed7f7f88";

                const result = await finalizeDraftQuoteReview(envelopeId, idempotencyKey);
                dispatch({
                    type: "FINALIZE_REVIEW",
                    payload: {
                        status: result.review_status,
                        finalized_by: result.finalized_by ?? null,
                        finalized_at: result.finalized_at ?? null,
                        remaining_blockers: result.remaining_blockers,
                        available_actions: ["reopen"]
                    }
                });
            } catch (err) {
                const errMsg = err instanceof Error ? err.message : String(err);
                dispatch({ type: "SET_ACTION_MESSAGE", payload: `API error finalizing review: ${errMsg}` });
                return;
            }
        } else {
            dispatch({
                type: "FINALIZE_REVIEW",
                payload: {
                    status: "finalized",
                    finalized_by: null,
                    finalized_at: new Date().toISOString(),
                    remaining_blockers: 0,
                    available_actions: ["reopen"]
                }
            });
        }
    };

    const dismissActionMessage = () => {
        dispatch({ type: "DISMISS_ACTION_MESSAGE" });
    };

    const togglePrototypeOverride = () => {
        dispatch({ type: "TOGGLE_PROTOTYPE_OVERRIDE" });
    };

    const toggleHelpText = () => {
        dispatch({ type: "TOGGLE_HELP_TEXT" });
    };

    // Derived State Computations
    const combinedUnresolved = selectCombinedUnresolved(state);
    const currentIssue = selectCurrentIssue(state);
    const activeCharges = selectActiveCharges(state);
    const uniqueCurrencies = selectUniqueCurrencies(state);
    const subtotals = selectSubtotals(state);
    const checklistIssuesResolved = selectChecklistIssuesResolved(state);
    const checklistNoUnknown = selectChecklistNoUnknown(state);
    const checklistProductCodesVerified = selectChecklistProductCodesVerified(state);
    const canFinishReview = selectCanFinishReview(state);
    const isReviewLocked = selectIsReviewLocked(state);
    const canUsePrototypeOverride = selectCanUsePrototypeOverride(state, isLive);
    const nextStepGuidance = selectNextStepGuidance(state);

    return {
        state: {
            suggestedCharges: state.suggestedCharges,
            reviewQueue: state.reviewQueue,
            unclassifiedItems: state.unclassifiedItems,
            ignoredItems: state.ignoredItems,
            decisions: state.decisions,
            reviewSession: state.reviewSession,
            activeIssueId: state.activeIssueId,
            selectedActionType: state.selectedActionType,
            requestForm: state.requestForm,
            unknownWizard: state.unknownWizard,
            addChargeForm: state.addChargeForm,
            actionMessage: state.actionMessage,
            prototypeOverride: state.prototypeOverride,
            showHelpText: state.showHelpText,
            productCodes,
            isLoadingProductCodes,
            productCodeLoadError
        },
        derived: {
            combinedUnresolved,
            currentIssue,
            activeCharges,
            uniqueCurrencies,
            subtotals,
            checklistIssuesResolved,
            checklistNoUnknown,
            checklistProductCodesVerified,
            canFinishReview,
            isReviewLocked,
            canUsePrototypeOverride,
            nextStepGuidance
        },
        actions: {
            selectIssue,
            openMapExisting,
            retryProductCodeLoad,
            openRequestProductCode,
            openUnknownProductCodeRequest,
            openAddUnknownCharge,
            cancelAction,
            updateRequestForm,
            updateAddChargeForm,
            classifyUnknown,
            returnToUnknownClassification,
            mapProductCode,
            classifyUnknownAsExistingCharge,
            submitProductCodeRequest,
            useApprovedProductCode,
            acceptSuggestedMapping,
            ignoreCharge,
            ignoreUnknownCharge,
            approveUnknownNote,
            addUnknownAsCharge,
            toggleIncludeInTotals,
            undoDecision,
            finalizeReview,
            dismissActionMessage,
            togglePrototypeOverride,
            toggleHelpText
        }
    };
}
