"use client";

import { useEffect } from "react";

type KeyCombo = {
    key: string;
    ctrl?: boolean;
    meta?: boolean; // Command on Mac
    shift?: boolean;
    alt?: boolean;
    action: (e: KeyboardEvent) => void;
};

export function useKeyboardShortcuts(shortcuts: KeyCombo[]) {
    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            shortcuts.forEach(({ key, ctrl, meta, shift, alt, action }) => {
                const matchesKey = event.key.toLowerCase() === key.toLowerCase();

                // Flexible modifier check:
                // If modifier is explicitly requested (true), it MUST be pressed.
                // If modifier is undefined/false, it DOES NOT matter (usually).
                // But for strict shortcuts, we might want strict matching.
                // Let's stick to: if prop is true, it must be pressed. if false/undefined, it must NOT be pressed.

                const propCtrl = !!ctrl;
                const propMeta = !!meta;
                const propShift = !!shift;
                const propAlt = !!alt;

                const pressedCtrl = event.ctrlKey;
                const pressedMeta = event.metaKey;
                const pressedShift = event.shiftKey;
                const pressedAlt = event.altKey;

                // Adjust logic: Command/Ctrl are often interchangeable for cross-platform "Primary" modifier
                const isPrimary = propCtrl || propMeta;
                const pressedPrimary = pressedCtrl || pressedMeta;

                if (
                    matchesKey &&
                    (isPrimary ? pressedPrimary : !pressedPrimary) &&
                    (propShift === pressedShift) &&
                    (propAlt === pressedAlt)
                ) {
                    event.preventDefault();
                    action(event);
                }
            });
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [shortcuts]);
}
