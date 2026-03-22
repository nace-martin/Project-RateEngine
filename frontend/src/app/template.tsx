"use client";

export default function Template({ children }: { children: React.ReactNode }) {
    // We can add a small delay or state if needed, but simple CSS animation on mount works best with template.tsx
    // The key is that template.tsx remounts on navigation.

    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 ease-in-out">
            {children}
        </div>
    );
}
