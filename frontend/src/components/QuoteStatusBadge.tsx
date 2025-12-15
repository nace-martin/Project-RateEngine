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
import { Loader2, Lock, Send, CheckCircle, Copy } from "lucide-react";
import { cloneQuote } from "@/lib/api";

// Status color configuration
const STATUS_CONFIG: Record<string, {
    label: string;
    bgColor: string;
    textColor: string;
    borderColor?: string;
}> = {
    DRAFT: {
        label: "Draft",
        bgColor: "bg-blue-100",
        textColor: "text-blue-700",
        borderColor: "border-blue-200",
    },
    INCOMPLETE: {
        label: "Incomplete",
        bgColor: "bg-red-100",
        textColor: "text-red-700",
        borderColor: "border-red-200",
    },
    FINALIZED: {
        label: "Finalized",
        bgColor: "bg-green-100",
        textColor: "text-green-700",
        borderColor: "border-green-200",
    },
    SENT: {
        label: "Sent",
        bgColor: "bg-orange-600",
        textColor: "text-white",
        borderColor: "border-orange-700",
    },
    // Post-MVP states (kept for future)
    ACCEPTED: {
        label: "Accepted",
        bgColor: "bg-emerald-100",
        textColor: "text-emerald-700",
    },
    LOST: {
        label: "Lost",
        bgColor: "bg-gray-100",
        textColor: "text-gray-600",
    },
    EXPIRED: {
        label: "Expired",
        bgColor: "bg-amber-100",
        textColor: "text-amber-700",
    },
};

interface QuoteStatusBadgeProps {
    status: string;
    size?: "sm" | "default" | "lg";
}

export function QuoteStatusBadge({ status, size = "default" }: QuoteStatusBadgeProps) {
    const config = STATUS_CONFIG[status] || {
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
        >
            {config.label}
        </Badge>
    );
}

// API function to transition quote status
async function transitionQuoteStatus(quoteId: string, action: "finalize" | "send"): Promise<{ success: boolean; error?: string }> {
    try {
        const token = localStorage.getItem("authToken");
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v3/quotes/${quoteId}/transition/`, {
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
    hasMissingRates?: boolean;
    onStatusChange?: () => void;
}

export function QuoteStatusActions({
    quoteId,
    status,
    hasMissingRates = false,
    onStatusChange
}: QuoteStatusActionsProps) {
    const router = useRouter();
    const [loading, setLoading] = useState(false);
    const [cloning, setCloning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [cloneDialogOpen, setCloneDialogOpen] = useState(false);

    const handleTransition = async (action: "finalize" | "send") => {
        setLoading(true);
        setError(null);

        const result = await transitionQuoteStatus(quoteId, action);

        if (result.success) {
            setDialogOpen(false);
            onStatusChange?.();
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
            // Navigate to the new cloned quote
            router.push(`/quotes/${result.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to clone quote");
        }

        setCloning(false);
    };

    // FINALIZED and SENT quotes can be cloned
    const canClone = status === "FINALIZED" || status === "SENT";

    // Terminal states that show only Clone button
    if (status === "SENT" || status === "ACCEPTED" || status === "LOST" || status === "EXPIRED") {
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
                    <span>Quote is {status.toLowerCase()}</span>
                </div>
            </div>
        );
    }

    // INCOMPLETE quotes need to be completed first
    if (status === "INCOMPLETE") {
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

            {/* DRAFT → FINALIZED */}
            {status === "DRAFT" && (
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
            )}

            {/* FINALIZED → SENT + Clone */}
            {status === "FINALIZED" && (
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

                    {/* Mark as Sent Button */}
                    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                        <DialogTrigger asChild>
                            <Button
                                variant="default"
                                size="sm"
                                disabled={loading}
                                className="bg-orange-600 hover:bg-orange-700"
                            >
                                {loading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Send className="mr-2 h-4 w-4" />
                                )}
                                Mark as Sent
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Mark quote as sent?</DialogTitle>
                                <DialogDescription>
                                    This indicates the quote has been delivered to the customer.
                                    This action cannot be undone.
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <DialogClose asChild>
                                    <Button variant="outline">Cancel</Button>
                                </DialogClose>
                                <Button
                                    onClick={() => handleTransition("send")}
                                    disabled={loading}
                                    className="bg-orange-600 hover:bg-orange-700"
                                >
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Mark as Sent
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
