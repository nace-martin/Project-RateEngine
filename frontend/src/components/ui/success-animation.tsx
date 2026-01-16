import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface SuccessAnimationProps {
    className?: string;
    size?: "sm" | "md" | "lg" | "xl";
}

export function SuccessAnimation({ className, size = "md" }: SuccessAnimationProps) {
    const sizeClasses = {
        sm: "w-8 h-8",
        md: "w-16 h-16",
        lg: "w-24 h-24",
        xl: "w-32 h-32",
    };

    const iconSizes = {
        sm: "w-4 h-4",
        md: "w-8 h-8",
        lg: "w-12 h-12",
        xl: "w-16 h-16",
    };

    return (
        <div className={cn("flex flex-col items-center justify-center", className)}>
            <div className={cn(
                "rounded-full bg-emerald-100 flex items-center justify-center animate-in zoom-in duration-500 ease-out",
                sizeClasses[size]
            )}>
                <CheckCircle2
                    className={cn("text-emerald-600 animate-in fade-in duration-700 delay-150", iconSizes[size])}
                    strokeWidth={3}
                />
            </div>
            <div className="mt-4 text-center animate-in slide-in-from-bottom-2 fade-in duration-700 delay-300">
                {/* Content can be placed here by parent */}
            </div>
        </div>
    );
}
