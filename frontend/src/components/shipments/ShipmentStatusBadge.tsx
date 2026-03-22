'use client';

import { Badge } from "@/components/ui/badge";
import type { ShipmentStatus } from "@/lib/shipment-types";

const STATUS_STYLES: Record<ShipmentStatus, string> = {
  DRAFT: "border-amber-200 bg-amber-50 text-amber-700",
  FINALIZED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  CANCELLED: "border-rose-200 bg-rose-50 text-rose-700",
  REISSUED: "border-sky-200 bg-sky-50 text-sky-700",
};

export function ShipmentStatusBadge({ status }: { status: ShipmentStatus }) {
  return (
    <Badge variant="outline" className={STATUS_STYLES[status]}>
      {status.replace("_", " ")}
    </Badge>
  );
}
