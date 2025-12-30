"use client";

/**
 * SpotManagerApproval - Manager approval component for SPOT quotes
 * 
 * Only visible to users with manager role.
 */

import { useState } from "react";
import { Check, X, MessageSquare } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import type { SpotPricingEnvelope } from "@/lib/spot-types";

interface SpotManagerApprovalProps {
    spe: SpotPricingEnvelope;
    onApprove: (approved: boolean, comment?: string) => Promise<void>;
    isLoading?: boolean;
}

export function SpotManagerApproval({
    spe,
    onApprove,
    isLoading = false,
}: SpotManagerApprovalProps) {
    const [comment, setComment] = useState("");
    const [showCommentField, setShowCommentField] = useState(false);

    const handleApprove = async () => {
        await onApprove(true, comment || undefined);
    };

    const handleReject = async () => {
        if (!comment.trim()) {
            setShowCommentField(true);
            return;
        }
        await onApprove(false, comment);
    };

    return (
        <Card className="border-blue-200 bg-blue-50/50">
            <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                    <MessageSquare className="h-5 w-5 text-blue-600" />
                    Manager Approval Required
                    <Badge variant="outline" className="ml-2 text-xs">
                        {spe.shipment.commodity}
                    </Badge>
                </CardTitle>
                <CardDescription>
                    Review this SPOT quote and provide your decision.
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Summary info */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="text-slate-500">Route:</span>{" "}
                        <span className="font-medium">
                            {spe.shipment.origin_code} → {spe.shipment.destination_code}
                        </span>
                    </div>
                    <div>
                        <span className="text-slate-500">Weight:</span>{" "}
                        <span className="font-medium">{spe.shipment.total_weight_kg} kg</span>
                    </div>
                    <div>
                        <span className="text-slate-500">Trigger:</span>{" "}
                        <span className="font-medium">{spe.spot_trigger_reason_code}</span>
                    </div>
                    <div>
                        <span className="text-slate-500">Charges:</span>{" "}
                        <span className="font-medium">{spe.charges.length} lines</span>
                    </div>
                </div>

                {/* Comment field */}
                {showCommentField && (
                    <div className="space-y-2">
                        <Label htmlFor="comment">Comment (required for rejection)</Label>
                        <Textarea
                            id="comment"
                            placeholder="Provide reason for your decision..."
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                            rows={3}
                        />
                    </div>
                )}

                {!showCommentField && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowCommentField(true)}
                        className="text-slate-500"
                    >
                        <MessageSquare className="h-4 w-4 mr-2" />
                        Add comment
                    </Button>
                )}

                {/* Action buttons */}
                <div className="flex gap-3 pt-2">
                    <Button
                        onClick={handleApprove}
                        disabled={isLoading}
                        className="flex-1 bg-green-600 hover:bg-green-700"
                    >
                        <Check className="h-4 w-4 mr-2" />
                        Approve
                    </Button>
                    <Button
                        onClick={handleReject}
                        disabled={isLoading}
                        variant="destructive"
                        className="flex-1"
                    >
                        <X className="h-4 w-4 mr-2" />
                        Reject
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
