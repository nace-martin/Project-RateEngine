// frontend/src/hooks/use-spot-mode.ts
/**
 * SPOT Mode State Machine Hook
 * 
 * Manages the SPOT Mode flow state based on backend evaluation.
 * Provides actions for each step: scope check, trigger eval, SPE lifecycle.
 */

import { useState, useCallback } from 'react';
import type {
    SpotFlowState,
    SpotModeState,
    TriggerResult,
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
    getSpotEnvelope,
    acknowledgeSpotEnvelope,
    approveSpotEnvelope,
    computeSpotQuote,
} from '@/lib/api';

const initialState: SpotModeState = {
    flowState: 'NORMAL',
    spe: null,
    triggerResult: null,
    error: null,
    isLoading: false,
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
                flowState: 'RATE_ENTRY',
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
    // Load SPE by ID
    // ==========================================================================
    const loadSPE = useCallback(async (
        id: string
    ): Promise<SpotPricingEnvelope | null> => {
        updateState({ isLoading: true, error: null });

        try {
            const spe = await getSpotEnvelope(id);

            // Determine flow state from SPE status
            let flowState: SpotFlowState;
            if (spe.is_expired) {
                flowState = 'EXPIRED';
            } else if (spe.status === 'rejected') {
                flowState = 'REJECTED';
            } else if (spe.status === 'ready') {
                flowState = 'READY';
            } else if (spe.acknowledgement && spe.requires_manager_approval && !spe.manager_approval) {
                flowState = 'AWAITING_MANAGER';
            } else if (!spe.acknowledgement) {
                flowState = 'AWAITING_ACK';
            } else {
                flowState = 'RATE_ENTRY';
            }

            updateState({
                flowState,
                spe,
                triggerResult: { code: spe.trigger_code, text: spe.trigger_text },
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

            if (result.requires_manager_approval) {
                updateState({ flowState: 'AWAITING_MANAGER', isLoading: false });
            } else if (result.status === 'ready') {
                updateState({ flowState: 'READY', isLoading: false });
            }

            return true;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Acknowledgement failed',
                isLoading: false,
            });
            return false;
        }
    }, [state.spe, updateState, loadSPE]);

    // ==========================================================================
    // STEP 5: Manager Approval
    // ==========================================================================
    const submitManagerApproval = useCallback(async (
        approved: boolean,
        comment?: string
    ): Promise<boolean> => {
        if (!state.spe) {
            updateState({ error: 'No SPE loaded' });
            return false;
        }

        updateState({ isLoading: true, error: null });

        try {
            const result = await approveSpotEnvelope(state.spe.id, approved, comment);

            // Reload SPE to get updated state
            await loadSPE(state.spe.id);

            if (result.approved) {
                updateState({ flowState: 'READY', isLoading: false });
            } else {
                updateState({ flowState: 'REJECTED', isLoading: false });
            }

            return result.approved;
        } catch (err) {
            updateState({
                error: err instanceof Error ? err.message : 'Approval failed',
                isLoading: false,
            });
            return false;
        }
    }, [state.spe, updateState, loadSPE]);

    // ==========================================================================
    // STEP 6: Compute SPOT Quote
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
                });
                return result;
            }

            updateState({ isLoading: false });
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
    // Reset
    // ==========================================================================
    const reset = useCallback(() => {
        setState(initialState);
    }, []);

    // ==========================================================================
    // Derived state
    // ==========================================================================
    const canProceedToPricing =
        state.flowState === 'READY' &&
        state.spe !== null &&
        !state.spe.is_expired;

    const blockedReason = (() => {
        switch (state.flowState) {
            case 'OUT_OF_SCOPE':
                return state.error || 'Shipment is out of scope';
            case 'EXPIRED':
                return 'SPE has expired - please create a new one';
            case 'REJECTED':
                return state.spe?.manager_approval?.comment || 'Manager rejected this quote';
            case 'AWAITING_ACK':
                return 'Acknowledgement required';
            case 'AWAITING_MANAGER':
                return 'Awaiting manager approval';
            default:
                return null;
        }
    })();

    return {
        state,
        actions: {
            checkScope,
            evaluateTrigger,
            createSPE,
            loadSPE,
            submitAcknowledgement,
            submitManagerApproval,
            computeQuote,
            reset,
        },
        derived: {
            canProceedToPricing,
            blockedReason,
        },
    };
}
