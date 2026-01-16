'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';

type ToastVariant = 'default' | 'destructive' | 'success';

interface Toast {
    id: string;
    title?: string;
    description?: string;
    variant?: ToastVariant;
}

interface ToastContextType {
    toast: (props: Omit<Toast, 'id'>) => void;
    toasts: Toast[];
    dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const toast = ({ title, description, variant = 'default' }: Omit<Toast, 'id'>) => {
        const id = Math.random().toString(36).substring(2, 9);
        setToasts((prev) => [...prev, { id, title, description, variant }]);

        // Auto dismiss
        setTimeout(() => {
            dismiss(id);
        }, 5000);
    };

    const dismiss = (id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    };

    return (
        <ToastContext.Provider value={{ toast, toasts, dismiss }}>
            {children}
        </ToastContext.Provider>
    );
}

export function useToast() {
    const context = useContext(ToastContext);
    if (context === undefined) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
}
