"use client";

import { useState } from "react";
import { V3QuoteComputeResponse } from "@/lib/types";
import { downloadQuotePDF } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Mail, Download, FileText, Loader2 } from "lucide-react";

interface QuoteDocumentPreviewProps {
    quote: V3QuoteComputeResponse;
}

export default function QuoteDocumentPreview({ quote }: QuoteDocumentPreviewProps) {
    const [pdfDownloading, setPdfDownloading] = useState(false);
    const canDownloadPDF = quote.status === "FINALIZED" || quote.status === "SENT";
    const branding = quote.branding;

    const customerDetails =
        quote.customer && typeof quote.customer === "object"
            ? quote.customer
            : null;
    const customerEmail = customerDetails?.email || "billing@customer.example.com";

    // Get origin and destination codes
    const originCode = quote.origin_location?.match(/^([A-Z]{3})/)?.[1] || "---";
    const destCode = quote.destination_location?.match(/^([A-Z]{3})/)?.[1] || "---";

    // Get totals
    const totals = quote.latest_version?.totals;
    const currency = totals?.total_sell_fcy_currency || "PGK";
    const totalAmount = parseFloat(totals?.total_sell_fcy || "0").toLocaleString("en-US", {
        minimumFractionDigits: 2,
    });
    const brandName = branding?.display_name || "RateEngine";
    const brandPrimary = branding?.primary_color || "#2563eb";
    const contactLine = [branding?.support_phone, branding?.support_email].filter(Boolean).join(" • ");

    const handleDownloadPDF = async () => {
        setPdfDownloading(true);
        try {
            await downloadQuotePDF(quote.id, quote.quote_number);
        } catch (err) {
            console.error("PDF download failed:", err);
            alert(err instanceof Error ? err.message : "Failed to download PDF");
        } finally {
            setPdfDownloading(false);
        }
    };

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <FileText className="w-4 h-4 text-slate-400" />
                    Document Preview
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Preview Mockup */}
                <div className="border border-slate-200 rounded-lg p-3 bg-slate-50">
                    <div className="bg-white border border-slate-200 rounded shadow-sm p-3 text-[8px] leading-tight text-slate-600">
                        {/* Mini Document Preview */}
                        <div className="flex justify-between mb-2">
                            <div>
                                <div className="font-bold text-[10px]" style={{ color: brandPrimary }}>{brandName}</div>
                                {contactLine && (
                                    <div className="text-[7px] text-slate-400 mt-0.5">{contactLine}</div>
                                )}
                                <div className="text-slate-400 mt-1">
                                    <div>Bill To:</div>
                                    <div className="font-medium text-slate-600">{customerDetails?.name || "Customer"}</div>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-slate-400">QUOTATION</div>
                                <div className="font-bold text-[9px]">#{quote.quote_number}</div>
                                <div className="text-slate-400 mt-1">Date: {new Date().toLocaleDateString()}</div>
                            </div>
                        </div>
                        <div className="border-t border-slate-200 pt-2 mt-2">
                            <div className="flex gap-2 items-center">
                                <span className="font-bold">{originCode}</span>
                                <span className="text-slate-400">→</span>
                                <span className="font-bold">{destCode}</span>
                                <span className="ml-auto text-slate-400">Airfreight</span>
                            </div>
                        </div>
                        <div className="border-t border-slate-200 pt-2 mt-2 text-right">
                            <div className="text-slate-400">Total Amount</div>
                            <div className="font-bold text-[10px]" style={{ color: brandPrimary }}>{currency} {totalAmount}</div>
                        </div>
                    </div>
                </div>

                {/* Email Recipient */}
                <div>
                    <label className="text-xs font-medium text-slate-500 block mb-1.5">
                        Email Recipient
                    </label>
                    <Input
                        type="email"
                        value={customerEmail}
                        readOnly
                        className="text-sm bg-slate-50"
                    />
                </div>

                {/* Action Buttons */}
                <div className="space-y-2">
                    <Button
                        variant="outline"
                        className="w-full justify-center gap-2 border-slate-300"
                        onClick={() => alert("Email Quote PDF - Coming soon!")}
                    >
                        <Mail className="w-4 h-4" />
                        Email Quote PDF
                    </Button>
                    {canDownloadPDF && (
                        <Button
                            variant="outline"
                            className="w-full justify-center gap-2 border-slate-300"
                            disabled={pdfDownloading}
                            onClick={handleDownloadPDF}
                        >
                            {pdfDownloading ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Download className="w-4 h-4" />
                                    Download PDF
                                </>
                            )}
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

