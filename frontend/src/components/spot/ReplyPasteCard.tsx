"use client";

/**
 * ReplyPasteCard - Text area for pasting agent rate replies
 * 
 * Features:
 * - Line numbers for reference
 * - Preview of pasted text
 * - Submit to analysis
 */

import { useState } from "react";
import { Mail, ArrowRight, FileText } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface ReplyPasteCardProps {
    onSubmit: (text: string) => void;
    isLoading?: boolean;
}

export function ReplyPasteCard({ onSubmit, isLoading }: ReplyPasteCardProps) {
    const [text, setText] = useState("");
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = () => {
        setError(null);

        if (!text.trim()) {
            setError("Please paste the agent reply text");
            return;
        }

        if (text.trim().length < 20) {
            setError("Reply seems too short. Please paste the complete email.");
            return;
        }

        onSubmit(text);
    };

    const lineCount = text.split('\n').length;

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Mail className="h-5 w-5 text-slate-600" />
                    Paste Agent Reply
                </CardTitle>
                <CardDescription>
                    Paste the rate reply you received from the agent or carrier.
                    The system will help you extract and classify the information.
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {error && (
                    <Alert variant="destructive">
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                <div className="relative">
                    {/* Line numbers */}
                    <div className="absolute left-0 top-0 bottom-0 w-10 bg-slate-50 rounded-l-md border-r border-slate-200 overflow-hidden pointer-events-none">
                        <div className="pt-2 px-2 text-xs text-slate-400 font-mono leading-6">
                            {Array.from({ length: Math.max(lineCount, 10) }, (_, i) => (
                                <div key={i}>{i + 1}</div>
                            ))}
                        </div>
                    </div>

                    {/* Text area */}
                    <Textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        placeholder={`Hi,

Please see our rate for the shipment:

A/F: USD 10.20/kg
Valid until: 31 Dec 2024
Routing: SYD-SIN-POM
Subject to space availability

Best regards,
Agent Name`}
                        rows={12}
                        className="pl-12 font-mono text-sm resize-none"
                    />
                </div>

                <div className="flex justify-between items-center">
                    <div className="text-sm text-muted-foreground flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        {text ? `${lineCount} lines, ${text.length} characters` : "No text pasted"}
                    </div>

                    <Button
                        onClick={handleSubmit}
                        disabled={isLoading || !text.trim()}
                    >
                        {isLoading ? "Analyzing..." : (
                            <>
                                Analyze Reply
                                <ArrowRight className="h-4 w-4 ml-2" />
                            </>
                        )}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
