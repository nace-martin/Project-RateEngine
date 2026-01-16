'use client';

import { useToast } from "@/context/toast-context";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";
import { useEffect, useState } from "react";

export function Toaster() {
    const { toasts, dismiss } = useToast();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) return null;

    return (
        <div className="fixed bottom-0 right-0 z-[100] flex flex-col gap-2 p-4 w-full max-w-[420px]">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className={`
            group pointer-events-auto relative flex w-full items-start gap-2 overflow-hidden rounded-md border p-6 pr-8 shadow-lg transition-all
            ${toast.variant === 'destructive' ? 'border-red-200 bg-red-50 text-red-900' :
                            toast.variant === 'success' ? 'border-green-200 bg-green-50 text-green-900' :
                                'border-slate-200 bg-white text-slate-900'}
          `}
                >
                    {toast.variant === 'success' && <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />}
                    {toast.variant === 'destructive' && <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />}
                    {toast.variant === 'default' && <Info className="h-5 w-5 text-slate-600 mt-0.5" />}

                    <div className="grid gap-1">
                        {toast.title && <div className="text-sm font-semibold">{toast.title}</div>}
                        {toast.description && (
                            <div className="text-sm opacity-90">{toast.description}</div>
                        )}
                    </div>

                    <button
                        onClick={() => dismiss(toast.id)}
                        className="absolute right-2 top-2 rounded-md p-1 opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100 hover:bg-black/5"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>
            ))}
        </div>
    );
}
