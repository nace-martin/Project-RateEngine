import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

export type KPIStatus = "info" | "success" | "warning" | "danger" | "neutral";

interface KPICardProps {
    title: string;
    value: React.ReactNode | string | number;
    icon?: LucideIcon;
    status?: KPIStatus;
    trend?: {
        value: React.ReactNode | string | number;
        label?: string;
        positive?: boolean; // If true, green; if false, red; if undefined, neutral
    };
    description?: string;
    className?: string;
    action?: React.ReactNode;
    children?: React.ReactNode;
}

const statusConfig: Record<KPIStatus, {
    accentBorder: string;
    iconColor: string;
    iconBg: string;
}> = {
    info: {
        accentBorder: "border-l-primary",
        iconColor: "text-primary",
        iconBg: "bg-blue-50",
    },
    success: {
        accentBorder: "border-l-success",
        iconColor: "text-success",
        iconBg: "bg-green-50",
    },
    warning: {
        accentBorder: "border-l-warning",
        iconColor: "text-warning", // Golden Orange
        iconBg: "bg-amber-50",
    },
    danger: {
        accentBorder: "border-l-destructive",
        iconColor: "text-destructive", // Dark Red
        iconBg: "bg-red-50",
    },
    neutral: {
        accentBorder: "border-l-slate-300",
        iconColor: "text-slate-500",
        iconBg: "bg-slate-50",
    },
};

export function KPICard({
    title,
    value,
    icon: Icon,
    status = "info",
    trend,
    description,
    className,
    action,
    children
}: KPICardProps) {
    const config = statusConfig[status];

    return (
        <Card className={cn(
            "relative overflow-hidden border-slate-200 shadow-sm hover:shadow-md transition-shadow bg-white",
            "border-l-4", // Semantic left border
            config.accentBorder,
            className
        )}>
            <CardContent className="p-6">
                <div className="flex justify-between items-start mb-4">
                    <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">
                            {title}
                        </p>
                        <div className="flex items-baseline gap-2">
                            <h3 className="text-3xl font-bold text-slate-900 tracking-tight">
                                {value}
                            </h3>
                            {trend && (
                                <span className={cn(
                                    "text-sm font-medium flex items-center",
                                    trend.positive === true ? "text-success" :
                                        trend.positive === false ? "text-destructive" :
                                            "text-slate-500"
                                )}>
                                    {trend.value}
                                    {trend.label && <span className="ml-1 text-slate-400 font-normal">{trend.label}</span>}
                                </span>
                            )}
                        </div>
                        {description && (
                            <p className="text-sm text-slate-500 mt-1">
                                {description}
                            </p>
                        )}
                    </div>

                    <div className="flex flex-col items-end gap-2">
                        {Icon && (
                            <div className={cn("p-2 rounded-xl", config.iconBg, config.iconColor)}>
                                <Icon className="h-5 w-5" />
                            </div>
                        )}
                        {action}
                    </div>

                </div>
                {children}
            </CardContent>
        </Card>
    );
}
