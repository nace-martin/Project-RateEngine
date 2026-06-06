import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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
        <Card className="mb-6">
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold">Shipment Summary</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4 xl:grid-cols-7">
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Customer</span>
                        <span className="font-bold text-slate-900">{customerName}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Route</span>
                        <span className="font-bold text-slate-900">
                            {originCode} {"->"} {destinationCode}
                        </span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Commodity</span>
                        <span className="font-bold text-slate-900">{commodity}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Weight</span>
                        <span className="font-bold text-slate-900">{weightKg} kg</span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Pieces</span>
                        <span className="font-bold text-slate-900">{pieces}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Service Scope</span>
                        <span className="font-bold text-slate-900">{serviceScope}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground font-medium">Payment Terms</span>
                        <span className="font-bold text-slate-900">{paymentTerms}</span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
