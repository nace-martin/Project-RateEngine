"use client";

/**
 * SpotModeBanner - Entry banner when SPOT mode is required
 * 
 * Shows the trigger reason and provides entry point to SPOT flow.
 */

import { AlertTriangle, ArrowRight, Clock, Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { TriggerResult } from "@/lib/spot-types";

interface SpotModeBannerProps {
    triggerResult: TriggerResult;
    onEnterSpotMode: () => void;
    isLoading?: boolean;
}

/**
 * Displays when SPOT mode is required for a shipment.
 * 
 * Shows:
 * - Warning icon and "SPOT Mode Required" title
 * - Trigger reason from backend
 * - "Enter SPOT Rates" CTA button
 */
export function SpotModeBanner({
    triggerResult,
    onEnterSpotMode,
    isLoading = false,
}: SpotModeBannerProps) {
    return (
        <Alert className="border-amber-500 bg-amber-50 dark:bg-amber-950/20">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <AlertTitle className="text-amber-800 dark:text-amber-200 flex items-center gap-2">
                SPOT Mode Required
                <Badge variant="outline" className="text-xs font-mono text-amber-700 border-amber-400">
                    {triggerResult.code}
                </Badge>
            </AlertTitle>
            <AlertDescription className="mt-2 space-y-3">
                <p className="text-amber-700 dark:text-amber-300">
                    {triggerResult.text}
                </p>
                <div className="flex items-center gap-3 text-sm text-amber-600 dark:text-amber-400">
                    <Info className="h-4 w-4" />
                    <span>
                        Deterministic pricing is not available. You will need to manually source rates.
                    </span>
                </div>
                <div className="flex items-center gap-4 pt-2">
                    <Button
                        onClick={onEnterSpotMode}
                        disabled={isLoading}
                        className="bg-amber-600 hover:bg-amber-700 text-white"
                    >
                        {isLoading ? (
                            <Clock className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <ArrowRight className="h-4 w-4 mr-2" />
                        )}
                        Enter SPOT Rates
                    </Button>
                </div>
            </AlertDescription>
        </Alert>
    );
}

/**
 * Out of scope error banner - hard block
 */
interface OutOfScopeBannerProps {
    error: string;
}

export function OutOfScopeBanner({ error }: OutOfScopeBannerProps) {
    return (
        <Alert variant="destructive" className="border-red-500">
            <AlertTriangle className="h-5 w-5" />
            <AlertTitle>Quote Not Supported</AlertTitle>
            <AlertDescription className="mt-2">
                <p>{error}</p>
                <p className="mt-2 text-sm opacity-80">
                    RateEngine only supports shipments to or from Papua New Guinea (PG).
                </p>
            </AlertDescription>
        </Alert>
    );
}

/**
 * SPE Expired banner - requires new SPE
 */
interface ExpiredBannerProps {
    expiresAt: string;
    onClone: () => void;
}

export function ExpiredBanner({ expiresAt, onClone }: ExpiredBannerProps) {
    return (
        <Alert variant="destructive" className="border-red-500 bg-red-50 dark:bg-red-950/20">
            <Clock className="h-5 w-5" />
            <AlertTitle>SPOT Quote Expired</AlertTitle>
            <AlertDescription className="mt-2 space-y-3">
                <p>
                    This SPOT quote expired at {new Date(expiresAt).toLocaleString()}.
                </p>
                <p className="text-sm opacity-80">
                    SPOT quotes are non-reusable after expiry. You need to create a new quote with fresh rates.
                </p>
                <Button onClick={onClone} variant="outline" className="mt-2">
                    Clone & Refresh Rates
                </Button>
            </AlertDescription>
        </Alert>
    );
}

/**
 * Manager Rejected banner
 */
interface RejectedBannerProps {
    comment?: string;
    onRevise: () => void;
}

export function RejectedBanner({ comment, onRevise }: RejectedBannerProps) {
    return (
        <Alert variant="destructive" className="border-red-500 bg-red-50 dark:bg-red-950/20">
            <AlertTriangle className="h-5 w-5" />
            <AlertTitle>SPOT Quote Rejected</AlertTitle>
            <AlertDescription className="mt-2 space-y-3">
                <p>
                    Manager has rejected this SPOT quote.
                </p>
                {comment && (
                    <p className="text-sm italic">
                        &ldquo;{comment}&rdquo;
                    </p>
                )}
                <Button onClick={onRevise} variant="outline" className="mt-2">
                    Revise Quote
                </Button>
            </AlertDescription>
        </Alert>
    );
}

/**
 * Awaiting Manager Approval banner
 */
interface AwaitingManagerBannerProps {
    speId: string;
}

export function AwaitingManagerBanner({ speId }: AwaitingManagerBannerProps) {
    return (
        <Alert className="border-blue-500 bg-blue-50 dark:bg-blue-950/20">
            <Clock className="h-5 w-5 text-blue-600" />
            <AlertTitle className="text-blue-800 dark:text-blue-200">
                Awaiting Manager Approval
            </AlertTitle>
            <AlertDescription className="mt-2 text-blue-700 dark:text-blue-300">
                <p>
                    This SPOT quote requires manager approval before pricing can proceed.
                </p>
                <p className="text-sm mt-1 font-mono">
                    SPE ID: {speId}
                </p>
            </AlertDescription>
        </Alert>
    );
}
