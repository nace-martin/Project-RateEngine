import { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
    title: string;
    description: string;
    icon?: LucideIcon;
    actionLabel?: string;
    onAction?: () => void;
    className?: string;
}

export function EmptyState({
    title,
    description,
    icon: Icon,
    actionLabel,
    onAction,
    className,
}: EmptyStateProps) {
    return (
        <div
            className={cn(
                "flex flex-col items-center justify-center p-8 text-center border-2 border-dashed rounded-lg bg-slate-50 border-slate-200",
                className
            )}
        >
            {Icon && (
                <div className="flex items-center justify-center w-12 h-12 mb-4 rounded-full bg-slate-100">
                    <Icon className="w-6 h-6 text-slate-400" />
                </div>
            )}
            <h3 className="mb-2 text-lg font-semibold text-slate-900">{title}</h3>
            <p className="max-w-sm mb-6 text-sm text-slate-500">{description}</p>
            {actionLabel && onAction && (
                <Button onClick={onAction} variant="outline">
                    {actionLabel}
                </Button>
            )}
        </div>
    );
}
