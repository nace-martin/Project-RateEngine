"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    DialogClose,
} from "@/components/ui/dialog";
import { Loader2, Lock, Send, CheckCircle, Copy, XCircle, Trophy, Ban } from "lucide-react";
import { cloneQuote } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import { useToast } from "@/context/toast-context";
import { getEffectiveQuoteStatus } from "@/lib/quote-helpers";

// Status color configuration
const STATUS_CONFIG: Record<string, {
    label: string;
    bgColor: string;
    textColor: string;
    borderColor?: string;
}> = {
    DRAFT: {
        label: "Draft",
        bgColor: "bg-amber-500",
        textColor: "text-white",
        borderColor: "border-amber-600",
    },
    INCOMPLETE: {
        label: "Incomplete",
        bgColor: "bg-red-50",
        textColor: "text-red-700",
        borderColor: "border-red-200",
    },
    FINALIZED: {
        label: "Finalized",
        bgColor: "bg-emerald-600",
        textColor: "text-white",
        borderColor: "border-emerald-700",
    },
    SENT: {
        label: "Pending",
        bgColor: "bg-blue-600",
        textColor: "text-white",
        borderColor: "border-blue-700",
    },
    // Post-MVP states (kept for future)
    ACCEPTED: {
        label: "Accepted",
        bgColor: "bg-emerald-700",
        textColor: "text-white",
        borderColor: "border-emerald-800",
    },
    LOST: {
        label: "Lost",
        bgColor: "bg-gray-200",
        textColor: "text-gray-700",
        borderColor: "border-gray-300",
    },
    EXPIRED: {
        label: "Expired",
        bgColor: "bg-rose-600",
        textColor: "text-white",
        borderColor: "border-rose-700",
    },
};

interface QuoteStatusBadgeProps {
    status: string;
    size?: "sm" | "default" | "lg";
}

export function QuoteStatusBadge({ status, size = "default" }: QuoteStatusBadgeProps) {
    const normalizedStatus = status?.toUpperCase?.() ?? "";
    const config = STATUS_CONFIG[normalizedStatus] || {
        label: status,
        bgColor: "bg-gray-100",
        textColor: "text-gray-600",
    };

    const sizeClasses = {
        sm: "text-xs px-2 py-0.5",
        default: "text-xs px-2.5 py-1",
        lg: "text-sm px-3 py-1.5",
    };

    return (
        <Badge
            variant="outline"
            className={`
        ${config.bgColor} 
        ${config.textColor} 
        ${config.borderColor || "border-transparent"}
        ${sizeClasses[size]}
        font-medium
      `}
            title={status === "INCOMPLETE" ? "Missing required rates. Click to resolve." : undefined}
        >
            {config.label}
        </Badge>
    );
}

// API function to transition quote status
async function transitionQuoteStatus(quoteId: string, action: "finalize" | "send" | "cancel" | "mark_won" | "mark_lost" | "mark_expired"): Promise<{ success: boolean; error?: string }> {
    try {
        const token = localStorage.getItem("authToken");
        const response = await fetch(`${API_BASE_URL}/api/v3/quotes/${quoteId}/transition/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Token ${token}`,
            },
            body: JSON.stringify({ action }),
        });

        if (!response.ok) {
            const data = await response.json();
            return { success: false, error: data.detail || "Failed to update status" };
        }

        return { success: true };
    } catch (error) {
        return { success: false, error: error instanceof Error ? error.message : "Network error" };
    }
}

interface QuoteStatusActionsProps {
    quoteId: string;
    status: string;
    validUntil?: string | null;
    hasMissingRates?: boolean;
    onStatusChange?: () => void;
}

export function QuoteStatusActions({
    quoteId,
    status,
    validUntil,
    hasMissingRates = false,
    onStatusChange
}: QuoteStatusActionsProps) {
    const normalizedStatus = status?.toUpperCase?.() ?? "";
    const effectiveStatus = getEffectiveQuoteStatus(normalizedStatus, validUntil);
    const router = useRouter();
    const [loading, setLoading] = useState(false);
    const [cloning, setCloning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [sendDialogOpen, setSendDialogOpen] = useState(false);
    const [cloneDialogOpen, setCloneDialogOpen] = useState(false);
    const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
    const [outcomeDialogOpen, setOutcomeDialogOpen] = useState(false);
    const [pendingOutcome, setPendingOutcome] = useState<"mark_won" | "mark_lost" | null>(null);

    const { toast } = useToast();

    const handleTransition = async (action: "finalize" | "send" | "cancel" | "mark_won" | "mark_lost" | "mark_expired") => {
        setLoading(true);
        setError(null);

        const result = await transitionQuoteStatus(quoteId, action);

        if (result.success) {
            setDialogOpen(false);
            setSendDialogOpen(false);
            setCancelDialogOpen(false);
            setOutcomeDialogOpen(false);
            onStatusChange?.();

            const messages: Record<string, { title: string; description: string }> = {
                finalize: { title: 'Quote Finalized', description: 'Quote has been locked.' },
                send: { title: 'Quote Sent', description: 'Quote marked as sent.' },
                cancel: { title: 'Quote Cancelled', description: 'Quote has been archived.' },
                mark_won: { title: 'Quote Won!', description: 'Quote marked as accepted.' },
                mark_lost: { title: 'Quote Lost', description: 'Quote marked as lost.' },
                mark_expired: { title: 'Quote Expired', description: 'Quote marked as expired.' },
            };

            toast({
                title: messages[action]?.title || 'Status Updated',
                description: messages[action]?.description || 'Quote status updated.',
                variant: action === 'mark_won' ? 'success' : (action === 'cancel' || action === 'mark_lost' || action === 'mark_expired' ? 'default' : 'success')
            });
        } else {
            setError(result.error || "Failed to update status");
        }

        setLoading(false);
    };

    const handleClone = async () => {
        setCloning(true);
        setError(null);

        try {
            const result = await cloneQuote(quoteId);
            setCloneDialogOpen(false);

            toast({
                title: 'Quote Cloned',
                description: 'New draft created successfully.',
                variant: 'success'
            });

            // Navigate to the new cloned quote
            router.push(`/quotes/${result.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to clone quote");
        }

        setCloning(false);
    };

    // FINALIZED and SENT quotes can be cloned
    const canClone = effectiveStatus === "FINALIZED" || effectiveStatus === "SENT" || effectiveStatus === "EXPIRED";

    // Terminal states that show only Clone button
    if (effectiveStatus === "ACCEPTED" || effectiveStatus === "LOST" || effectiveStatus === "EXPIRED") {
        return (
            <div className="flex items-center gap-3">
                {error && (
                    <span className="text-sm text-red-400">{error}</span>
                )}
                {canClone && (
                    <Dialog open={cloneDialogOpen} onOpenChange={setCloneDialogOpen}>
                        <DialogTrigger asChild>
                            <Button
                                variant="outline"
                                size="sm"
                                disabled={cloning}
                            >
                                {cloning ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Copy className="mr-2 h-4 w-4" />
                                )}
                                Clone Quote
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Clone this quote?</DialogTitle>
                                <DialogDescription>
                                    This will create a new DRAFT quote with the same details and charges.
                                    You can then edit and recalculate the new quote.
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Cancel</Button>
                                </DialogClose>
                                <Button
                                    onClick={handleClone}
                                    disabled={cloning}
                                >
                                    {cloning && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Clone Quote
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                )}
                <div className="flex items-center gap-2 text-sm text-slate-400">
                    <Lock className="h-4 w-4" />
                    <span>Quote is {effectiveStatus.toLowerCase()}</span>
                </div>
            </div>
        );
    }

    // INCOMPLETE quotes need to be completed first
    if (effectiveStatus === "INCOMPLETE") {
        return (
            <div className="text-sm text-slate-400">
                Complete all required rates to finalize
            </div>
        );
    }

    return (
        <div className="flex items-center gap-3">
            {error && (
                <span className="text-sm text-red-400">{error}</span>
            )}

            {/* DRAFT → FINALIZED + Cancel */}
            {effectiveStatus === "DRAFT" && (
                <>
                    {/* Cancel Quote Button */}
                    <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
                        <DialogTrigger asChild>
                            <Button
                                variant="outline"
                                size="sm"
                                disabled={loading}
                                className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                            >
                                <XCircle className="mr-2 h-4 w-4" />
                                Cancel
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Cancel this quote?</DialogTitle>
                                <DialogDescription>
                                    This will archive the quote and remove it from your active list.
                                    You can restore it later if needed.
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Back</Button>
                                </DialogClose>
                                <Button
                                    onClick={() => handleTransition("cancel")}
                                    disabled={loading}
                                    variant="destructive"
                                >
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Cancel Quote
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>

                    {/* Finalize Quote Button */}
                    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                        <DialogTrigger asChild>
                            <Button
                                variant="default"
                                size="sm"
                                disabled={loading || hasMissingRates}
                                className="bg-green-600 hover:bg-green-700"
                            >
                                {loading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <CheckCircle className="mr-2 h-4 w-4" />
                                )}
                                Finalize Quote
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Finalize this quote?</DialogTitle>
                                <DialogDescription>
                                    Once finalized, the quote will be locked and cannot be edited.
                                    You can still mark it as sent to the customer.
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Cancel</Button>
                                </DialogClose>
                                <Button
                                    onClick={() => handleTransition("finalize")}
                                    disabled={loading}
                                    className="bg-green-600 hover:bg-green-700"
                                >
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Finalize Quote
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </>
            )}

            {/* FINALIZED → SENT */}
            {effectiveStatus === "FINALIZED" && (
                <Dialog open={sendDialogOpen} onOpenChange={setSendDialogOpen}>
                    <DialogTrigger asChild>
                        <Button
                            variant="default"
                            size="sm"
                            disabled={loading}
                            className="bg-blue-600 hover:bg-blue-700"
                        >
                            {loading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <Send className="mr-2 h-4 w-4" />
                            )}
                            Send Quote
                        </Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Mark this quote as sent?</DialogTitle>
                            <DialogDescription>
                                This will update the quote status to SENT so you can record outcomes.
                            </DialogDescription>
                        </DialogHeader>
                        <DialogFooter>
                            <DialogClose asChild>
                                <Button variant="outline">Cancel</Button>
                            </DialogClose>
                            <Button
                                onClick={() => handleTransition("send")}
                                disabled={loading}
                                className="bg-blue-600 hover:bg-blue-700"
                            >
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Mark as Sent
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* SENT → Won/Lost */}
            {effectiveStatus === "SENT" && (
                <>
                    {/* Clone Button */}
                    <Dialog open={cloneDialogOpen} onOpenChange={setCloneDialogOpen}>
                        <DialogTrigger asChild>
                            <Button
                                variant="outline"
                                size="sm"
                                disabled={cloning}
                            >
                                {cloning ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Copy className="mr-2 h-4 w-4" />
                                )}
                                Clone
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Clone this quote?</DialogTitle>
                                <DialogDescription>
                                    This will create a new DRAFT quote with the same details and charges.
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Cancel</Button>
                                </DialogClose>
                                <Button
                                    onClick={handleClone}
                                    disabled={cloning}
                                >
                                    {cloning && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Clone Quote
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>

                    {/* Outcome Actions */}
                    <Dialog open={outcomeDialogOpen} onOpenChange={setOutcomeDialogOpen}>
                        <DialogTrigger asChild>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={loading}
                                    className="text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50 border-emerald-200"
                                    onClick={() => {
                                        setPendingOutcome("mark_won");
                                        setOutcomeDialogOpen(true);
                                    }}
                                >
                                    <Trophy className="mr-2 h-4 w-4" />
                                    Won
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={loading}
                                    className="text-slate-600 hover:text-slate-700 hover:bg-slate-50"
                                    onClick={() => {
                                        setPendingOutcome("mark_lost");
                                        setOutcomeDialogOpen(true);
                                    }}
                                >
                                    <Ban className="mr-2 h-4 w-4" />
                                    Lost
                                </Button>
                            </div>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>
                                    Mark quote as {pendingOutcome === 'mark_won' ? 'Won' : 'Lost'}?
                                </DialogTitle>
                                <DialogDescription>
                                    {pendingOutcome === 'mark_won'
                                        ? "Great! Marking this quote as ACCEPTED. This will be recorded in your win count."
                                        : "Marking this quote as LOST. You can still clone it later if the customer returns."
                                    }
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Cancel</Button>
                                </DialogClose>
                                <Button
                                    onClick={() => pendingOutcome && handleTransition(pendingOutcome)}
                                    disabled={loading}
                                    className={pendingOutcome === 'mark_won' ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-600 hover:bg-slate-700"}
                                >
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Confirm
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </>
            )}
        </div>
    );
}

// Utility to check if quote is editable
export function isQuoteEditable(status: string): boolean {
    return status === "DRAFT" || status === "INCOMPLETE";
}
