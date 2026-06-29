import { Card, CardContent } from "@/components/ui/card";

export interface SpotWorkspaceSummaryProps {
    customerName: string;
    originCode: string;
    destinationCode: string;
    commodity: string;
    weightKg: number;
    pieces: number;
    serviceScope: string;
    paymentTerms: string;
}

export function SpotWorkspaceSummary({
    customerName,
    originCode,
    destinationCode,
    commodity,
    weightKg,
    pieces,
    serviceScope,
    paymentTerms,
}: SpotWorkspaceSummaryProps) {
    return (
        <Card className="mb-6 border-slate-200 bg-slate-50/70 shadow-sm">
            <CardContent className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Customer</span>
                        <span className="font-semibold text-slate-900">{customerName}</span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Route</span>
                        <span className="font-semibold text-slate-900">
                            {originCode} {"→"} {destinationCode}
                        </span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Commodity</span>
                        <span className="font-semibold text-slate-900">{commodity}</span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Weight</span>
                        <span className="font-semibold text-slate-900">{weightKg} kg</span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Pcs</span>
                        <span className="font-semibold text-slate-900">{pieces}</span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Scope</span>
                        <span className="font-semibold text-slate-900">{serviceScope}</span>
                    </div>
                    <span className="hidden text-slate-300 sm:inline" aria-hidden="true">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-500">Payment</span>
                        <span className="font-semibold text-slate-900">{paymentTerms}</span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
