'use client';

/**
 * usePermissions Hook
 * 
 * React hook for checking user permissions based on their role.
 * Uses the auth context to get the current user's role.
 * 
 * IMPORTANT: These are for UX only - backend enforces actual permissions.
 */

import { useAuth } from '@/context/auth-context';
import {
    hasPermission,
    canViewCOGS,
    canViewMargins,
    canEditQuotes,
    canFinalizeQuotes,
    canUseAIIntake,
    canEditRateCards,
    canEditFXRates,
    canManageUsers,
    canAccessSystemSettings,
    Permission,
    PERMISSIONS
} from '@/lib/permissions';

interface UsePermissionsReturn {
    // Check any permission
    hasPermission: (permission: Permission) => boolean;

    // Specific permission checks
    canViewCOGS: boolean;
    canViewMargins: boolean;
    canEditQuotes: boolean;
    canFinalizeQuotes: boolean;
    canUseAIIntake: boolean;
    canEditRateCards: boolean;
    canEditFXRates: boolean;
    canManageUsers: boolean;
    canAccessSystemSettings: boolean;

    // Role info
    role: string | undefined;
    isAdmin: boolean;
    isManager: boolean;
    isFinance: boolean;
    isSales: boolean;
}

export function usePermissions(): UsePermissionsReturn {
    const { user } = useAuth();
    const role = user?.role;

    return {
        // Generic permission check
        hasPermission: (permission: Permission) => hasPermission(role, permission),

        // Specific permission checks
        canViewCOGS: canViewCOGS(role),
        canViewMargins: canViewMargins(role),
        canEditQuotes: canEditQuotes(role),
        canFinalizeQuotes: canFinalizeQuotes(role),
        canUseAIIntake: canUseAIIntake(role),
        canEditRateCards: canEditRateCards(role),
        canEditFXRates: canEditFXRates(role),
        canManageUsers: canManageUsers(role),
        canAccessSystemSettings: canAccessSystemSettings(role),

        // Role info
        role,
        isAdmin: role === 'admin',
        isManager: role === 'manager',
        isFinance: role === 'finance',
        isSales: role === 'sales',
    };
}

// Re-export PERMISSIONS for convenience
export { PERMISSIONS };
