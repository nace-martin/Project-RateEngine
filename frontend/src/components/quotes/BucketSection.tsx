"use client";

import { useState } from "react";
import { CanonicalQuoteResult } from "@/lib/types";
import { BreakdownLine, SUBCATEGORY_ORDER, calculateBucketTotal, formatAmount } from "@/lib/quote-financial-helpers";
import ChargeCard from "./ChargeCard";
import { ChevronDown, ChevronRight } from "lucide-react";

function getSectionStyle() {
    return {
        wrapper: "rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden",
        header: "bg-white hover:bg-slate-50 border-b border-slate-100 transition-colors cursor-pointer",
        title: "text-slate-900",
        iconBg: "bg-blue-50 text-blue-600",
        borderLeft: "border-l-[4px] border-l-blue-500"
    };
}

export default function BucketSection({
    title,
    lines,
    displayCurrency,
    isShowingFCY,
    globalFx,
    icon,
}: {
    title: string;
    lines: BreakdownLine[];
    displayCurrency: string;
    isShowingFCY: boolean;
    globalFx?: CanonicalQuoteResult["fx_applied"];
    icon: React.ReactNode;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const styles = getSectionStyle();

    const bucketTotal = isShowingFCY
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    // Grouping logic within the bucket
    const groups: Record<string, BreakdownLine[]> = {};
    lines.forEach(line => {
        const sub = line.canonical_item?.subcategory || line.subcategory || 'Other Charges';
        if (!groups[sub]) groups[sub] = [];
        groups[sub].push(line);
    });

    const sortedGroups = Object.keys(groups).sort((a, b) => {
        const orderA = SUBCATEGORY_ORDER.indexOf(a);
        const orderB = SUBCATEGORY_ORDER.indexOf(b);
        const finalA = orderA === -1 ? 999 : orderA;
        const finalB = orderB === -1 ? 999 : orderB;
        return finalA - finalB;
    });

    return (
        <div className={styles.wrapper}>
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full flex items-center justify-between p-5 ${styles.header} ${styles.borderLeft}`}
            >
                <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${styles.iconBg}`}>
                        {icon}
                    </div>
                    <div className="text-left">
                        <div className="flex items-center gap-3">
                            <h3 className={`text-base font-bold tracking-tight ${styles.title}`}>
                                {title}
                            </h3>
                            <span className="flex items-center justify-center bg-slate-100 text-slate-500 text-[11px] font-semibold h-6 px-2 rounded-full">
                                {lines.length} {lines.length === 1 ? 'charge' : 'charges'}
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-0.5">Subtotal</p>
                        <p className="text-base font-bold text-slate-900 mono-font">
                            {formatAmount(bucketTotal, displayCurrency)}
                        </p>
                    </div>
                    {isExpanded ? (
                        <ChevronDown className="w-5 h-5 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-5 h-5 text-slate-400" />
                    )}
                </div>
            </button>

            {isExpanded && (
                <div className="p-4 bg-slate-50/30 flex flex-col gap-6">
                    {sortedGroups.map(groupName => (
                        <div key={groupName} className="space-y-3">
                            <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest pl-1">
                                {groupName}
                            </h4>
                            <div className="flex flex-col gap-2">
                                {groups[groupName].map((line, index) => (
                                    <ChargeCard
                                        key={index}
                                        line={line}
                                        displayCurrency={displayCurrency}
                                        isShowingFCY={isShowingFCY}
                                        globalFx={globalFx}
                                    />
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
