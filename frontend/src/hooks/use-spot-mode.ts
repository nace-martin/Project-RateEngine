// frontend/src/hooks/use-spot-mode.ts
/**
 * SPOT Mode State Machine Hook
 * 
 * Manages the SPOT Mode flow state based on backend evaluation.
 * Provides actions for each step: scope check, trigger eval, SPE lifecycle.
 */

import { useState, useCallback, useMemo } from 'react';
import type {
    SpotFlowState,
    SpotModeState,
    TriggerEvaluateRequest,
    CreateSPERequest,
    SpotPricingEnvelope,
    SPEComputeRequest,
    SPEComputeResponse,
} from '@/lib/spot-types';
import {
    validateSpotScope,
    evaluateSpotTrigger,
    createSpotEnvelope,
    manuallyResolveSpotChargeLine,
    updateSpotEnvelope,
    getSpotEnvelope,
    acknowledgeSpotEnvelope,
    reviewSpotSourceBatch as reviewSpotSourceBatchRequest,
    computeSpotQuote,
    createSpotQuote,
} from '@/lib/api';

const initialState: SpotModeState = {
    flowState: 'NORMAL',
    spe: null,
    triggerResult: null,
    error: null,
    isLoading: false,
    quoteResult: null,
};

const resolveSpotFlowState = (spe: SpotPricingEnvelope): SpotFlowState => {
    if (spe.is_expired || spe.status === 'expired') {
        return 'EXPIRED';
    }
    if (spe.status === 'rejected') {
        return 'REVIEW';
    }
    if (spe.status === 'ready' || spe.acknowledgement) {
        return 'READY';
    }
    if (spe.charges.length > 0 || spe.missing_mandatory_fields.length > 0) {
        return 'REVIEW';
    }
    return 'INTAKE';
};

/**
 * useSpotMode - Custom hook for managing SPOT Mode flow
 * 
 * Usage:
 * ```tsx
 * const { state, actions } = useSpotMode();
 * 
 * // Step 1: Check scope
 * const inScope = await actions.checkScope('AU', 'PG');
 * if (!inScope) return; // OUT_OF_SCOPE
 * 
 * // Step 2: Evaluate trigger
 * const isSpot = await actions.evaluateTrigger({ ... });
 * if (!isSpot) return; // NORMAL flow
 * 
 * // Step 3+: SPOT flow continues...
 * ```
 */
export function useSpotMode() {
    const [state, setState] = useState<SpotModeState>(initialState);

    // Helper to update state
    const updateState = useCallback((updates: Partial<SpotModeState>) => {
        setState(prev => ({ ...prev, ...updates }));
    }, []);

    // ==========================================================================
    // STEP 1: Scope Validation
    // ==========================================================================
    const checkScope = useCallback(async (
        originCountry: string,
        destinationCountry: string
    ): Promise<boolean> => {
        updateState({ isLoading: true, error: null });

        try {
            const result = await validateSpotScope({
                origin_country: originCountry,
                destination_country: destinationCountry,
            });

            if (!result.is_valid) {
                updateState({
                    flowState: 'OUT_OF_SCOPE',
                    error: result.error,
                    isLoading: false,
                });
                return false;
            }

            updateState({ isLoading: false });
            return true;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Scope validation failed',
                isLoading: false,
            });
            return false;
        }
    }, [updateState]);

    // ==========================================================================
    // STEP 2: Trigger Evaluation
    // ==========================================================================
    const evaluateTrigger = useCallback(async (
        request: TriggerEvaluateRequest
    ): Promise<boolean> => {
        updateState({ isLoading: true, error: null });

        try {
            const result = await evaluateSpotTrigger(request);

            if (result.is_spot_required) {
                updateState({
                    flowState: 'SPOT_REQUIRED',
                    triggerResult: result.trigger,
                    isLoading: false,
                });
                return true;
            }

            updateState({
                flowState: 'NORMAL',
                isLoading: false,
            });
            return false;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Trigger evaluation failed',
                isLoading: false,
            });
            return false;
        }
    }, [updateState]);

    // ==========================================================================
    // STEP 3: Create SPE
    // ==========================================================================
    const createSPE = useCallback(async (
        request: CreateSPERequest
    ): Promise<SpotPricingEnvelope | null> => {
        updateState({ isLoading: true, error: null });

        try {
            const spe = await createSpotEnvelope(request);
            updateState({
                flowState: resolveSpotFlowState(spe),
                spe,
                isLoading: false,
            });
            return spe;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Failed to create SPE',
                isLoading: false,
            });
            return null;
        }
    }, [updateState]);

    // ==========================================================================
    // STEP 3.5: Update SPE (Draft)
    // ==========================================================================
    const updateSPE = useCallback(async (
        id: string,
        data: {
            charges?: Array<Omit<import('@/lib/spot-types').SPEChargeLine, 'id'> & { charge_line_id?: string }>;
            conditions?: Partial<import('@/lib/spot-types').SPEConditions>;
        }
    ): Promise<SpotPricingEnvelope | null> => {
        updateState({ isLoading: true, error: null });

        try {
            const spe = await updateSpotEnvelope(id, data);
            updateState({
                flowState: resolveSpotFlowState(spe),
                spe,
                isLoading: false,
            });
            return spe;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Failed to update SPE',
                isLoading: false,
            });
            return null;
        }
    }, [updateState]);

    const manuallyResolveChargeLine = useCallback(async (
        chargeLineId: string,
        request: { product_code_id: number | string }
    ): Promise<import('@/lib/spot-types').SPEChargeLine | null> => {
        if (!state.spe) {
            updateState({ error: 'No SPE loaded' });
            return null;
        }

        updateState({ isLoading: true, error: null });

        try {
            const updatedChargeLine = await manuallyResolveSpotChargeLine(state.spe.id, chargeLineId, request);
            updateState({
                isLoading: false,
                spe: state.spe
                    ? {
                        ...state.spe,
                        charges: state.spe.charges.map((charge) =>
                            charge.id === updatedChargeLine.id ? updatedChargeLine : charge
                        ),
                    }
                    : null,
            });
            return updatedChargeLine;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Manual charge review failed',
                isLoading: false,
            });
            return null;
        }
    }, [state.spe, updateState]);

    // ==========================================================================
    // Load SPE by ID
    // ==========================================================================
    const loadSPE = useCallback(async (
        id: string
    ): Promise<SpotPricingEnvelope | null> => {
        updateState({ isLoading: true, error: null });

        try {
            const spe = await getSpotEnvelope(id);

            // Determine flow state from SPE status
            const flowState = resolveSpotFlowState(spe);

            updateState({
                flowState,
                spe,
                triggerResult: {
                    code: spe.spot_trigger_reason_code,
                    text: spe.spot_trigger_reason_text
                },
                isLoading: false,
            });
            return spe;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Failed to load SPE',
                isLoading: false,
            });
            return null;
        }
    }, [updateState]);

    // ==========================================================================
    // STEP 4: Sales Acknowledgement
    // ==========================================================================
    const submitAcknowledgement = useCallback(async (): Promise<boolean> => {
        if (!state.spe) {
            updateState({ error: 'No SPE loaded' });
            return false;
        }

        updateState({ isLoading: true, error: null });

        try {
            const result = await acknowledgeSpotEnvelope(state.spe.id);

            // Reload SPE to get updated state
            await loadSPE(state.spe.id);
            return result.success;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Acknowledgement failed',
                isLoading: false,
            });
            return false;
        }
    }, [state.spe, updateState, loadSPE]);

    const reviewSourceBatch = useCallback(async (
        sourceBatchId: string,
        request: { reviewed_safe_to_quote: boolean; review_note?: string }
    ): Promise<SpotPricingEnvelope | null> => {
        if (!state.spe) {
            updateState({ error: 'No SPE loaded' });
            return null;
        }

        updateState({ isLoading: true, error: null });

        try {
            const spe = await reviewSpotSourceBatchRequest(state.spe.id, sourceBatchId, request);
            updateState({
                flowState: resolveSpotFlowState(spe),
                spe,
                isLoading: false,
            });
            return spe;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Source review failed',
                isLoading: false,
            });
            return null;
        }
    }, [state.spe, updateState]);

    // ==========================================================================
    // STEP 5: Compute SPOT Quote
    // ==========================================================================
    const computeQuote = useCallback(async (
        request: SPEComputeRequest
    ): Promise<SPEComputeResponse | null> => {
        if (!state.spe) {
            updateState({ error: 'No SPE loaded' });
            return null;
        }

        updateState({ isLoading: true, error: null });

        try {
            const result = await computeSpotQuote(state.spe.id, request);

            if (!result.is_complete) {
                updateState({
                    error: result.reason || 'Quote computation incomplete',
                    isLoading: false,
                    quoteResult: result,
                });
                return result;
            }

            updateState({
                isLoading: false,
                quoteResult: result,
            });
            return result;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Quote computation failed',
                isLoading: false,
            });
            return null;
        }
    }, [state.spe, updateState]);

    // ==========================================================================
    // STEP 6: Create Final Quote
    // ==========================================================================
    const createQuote = useCallback(async (
        request: {
            payment_term: string;
            service_scope: string;
            output_currency: string;
            customer_id?: string;
        }
    ): Promise<{ success: boolean; quote_id: string } | null> => {
        if (!state.spe) return null;
        updateState({ isLoading: true, error: null });
        try {
            const result = await createSpotQuote(state.spe.id, request);
            updateState({ isLoading: false });
            return result;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Failed to create quote',
                isLoading: false,
            });
            return null;
        }
    }, [state.spe, updateState]);

    // ==========================================================================
    // Reset
    // ==========================================================================
    const reset = useCallback(() => {
        setState(initialState);
    }, []);

    // ==========================================================================
    // Derived state
    // ==========================================================================
    const canProceedToPricing =
        state.spe !== null &&
        state.spe.status === 'ready' &&
        state.spe.can_proceed &&
        !state.spe.is_expired;

    const blockedReason = (() => {
        if (state.flowState === 'OUT_OF_SCOPE') {
            return state.error || 'Shipment is out of scope';
        }
        if (state.flowState === 'EXPIRED') {
            return 'SPE has expired - please create a new one';
        }
        if (state.spe?.status === 'rejected') {
            return 'This SPOT quote is no longer active';
        }
        if (state.flowState === 'REVIEW' && state.spe && !state.spe.acknowledgement) {
            return 'Acknowledgement required';
        }
        return null;
    })();

    const actions = useMemo(() => ({
        checkScope,
        evaluateTrigger,
        createSPE,
        updateSPE,
        loadSPE,
        manuallyResolveChargeLine,
        submitAcknowledgement,
        reviewSourceBatch,
        computeQuote,
        createQuote,
        reset,
    }), [
        checkScope,
        evaluateTrigger,
        createSPE,
        updateSPE,
        loadSPE,
        manuallyResolveChargeLine,
        submitAcknowledgement,
        reviewSourceBatch,
        computeQuote,
        createQuote,
        reset
    ]);

    const derived = useMemo(() => ({
        canProceedToPricing,
        blockedReason,
    }), [canProceedToPricing, blockedReason]);

    return {
        state,
        actions,
        derived,
    };
}
