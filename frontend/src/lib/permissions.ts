/**
 * RBAC Permission Utilities
 * 
 * This module provides role-based access control utilities for the frontend.
 * IMPORTANT: These are for UX only - backend enforces actual permissions.
 * 
 * Roles: SALES, MANAGER, FINANCE, ADMIN
 */

// Role constants - must match backend CustomUser.ROLE_*
export const ROLES = {
    SALES: 'sales',
    MANAGER: 'manager',
    FINANCE: 'finance',
    ADMIN: 'admin',
} as const;

export type Role = typeof ROLES[keyof typeof ROLES];

// Permission definitions
export const PERMISSIONS = {
    VIEW_QUOTES: 'view_quotes',
    EDIT_QUOTES: 'edit_quotes',
    FINALIZE_QUOTES: 'finalize_quotes',
    VIEW_COGS: 'view_cogs',
    VIEW_MARGINS: 'view_margins',
    EDIT_RATE_CARDS: 'edit_rate_cards',
    EDIT_FX_RATES: 'edit_fx_rates',
    USE_AI_INTAKE: 'use_ai_intake',
    MANAGE_USERS: 'manage_users',
    SYSTEM_SETTINGS: 'system_settings',
    VIEW_AUDIT_LOGS: 'view_audit_logs',
} as const;

export type Permission = typeof PERMISSIONS[keyof typeof PERMISSIONS];

/**
 * Permission matrix - maps permissions to allowed roles.
 * Based on confirmed business rules.
 */
const PERMISSION_MATRIX: Record<Permission, Role[]> = {
    [PERMISSIONS.VIEW_QUOTES]: [ROLES.SALES, ROLES.MANAGER, ROLES.FINANCE, ROLES.ADMIN],
    [PERMISSIONS.EDIT_QUOTES]: [ROLES.SALES, ROLES.MANAGER, ROLES.ADMIN],
    [PERMISSIONS.FINALIZE_QUOTES]: [ROLES.SALES, ROLES.MANAGER, ROLES.ADMIN],
    [PERMISSIONS.VIEW_COGS]: [ROLES.MANAGER, ROLES.FINANCE, ROLES.ADMIN],
    [PERMISSIONS.VIEW_MARGINS]: [ROLES.MANAGER, ROLES.FINANCE, ROLES.ADMIN],
    [PERMISSIONS.EDIT_RATE_CARDS]: [ROLES.MANAGER, ROLES.ADMIN],
    [PERMISSIONS.EDIT_FX_RATES]: [ROLES.FINANCE, ROLES.ADMIN],
    [PERMISSIONS.USE_AI_INTAKE]: [ROLES.SALES, ROLES.MANAGER, ROLES.ADMIN],
    [PERMISSIONS.MANAGE_USERS]: [ROLES.MANAGER, ROLES.ADMIN],
    [PERMISSIONS.SYSTEM_SETTINGS]: [ROLES.ADMIN],
    [PERMISSIONS.VIEW_AUDIT_LOGS]: [ROLES.MANAGER, ROLES.FINANCE, ROLES.ADMIN],
};

/**
 * Check if a role has a specific permission.
 */
export function hasPermission(role: string | undefined, permission: Permission): boolean {
    if (!role) return false;
    const allowedRoles = PERMISSION_MATRIX[permission];
    return allowedRoles.includes(role as Role);
}

/**
 * Check if a role can view cost data (COGS, buy rates).
 */
export function canViewCOGS(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.VIEW_COGS);
}

/**
 * Check if a role can view margin data.
 */
export function canViewMargins(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.VIEW_MARGINS);
}

/**
 * Check if a role can edit quotes.
 */
export function canEditQuotes(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.EDIT_QUOTES);
}

/**
 * Check if a role can finalize quotes.
 */
export function canFinalizeQuotes(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.FINALIZE_QUOTES);
}

/**
 * Check if a role can use AI intake.
 */
export function canUseAIIntake(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.USE_AI_INTAKE);
}

/**
 * Check if a role can edit rate cards.
 */
export function canEditRateCards(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.EDIT_RATE_CARDS);
}

/**
 * Check if a role can edit FX rates.
 */
export function canEditFXRates(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.EDIT_FX_RATES);
}

/**
 * Check if a role can manage users.
 */
export function canManageUsers(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.MANAGE_USERS);
}

/**
 * Check if a role can access system settings.
 */
export function canAccessSystemSettings(role: string | undefined): boolean {
    return hasPermission(role, PERMISSIONS.SYSTEM_SETTINGS);
}
