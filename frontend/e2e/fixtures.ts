/**
 * E2E Test Fixtures and Helpers
 * Provides authentication and common utilities for all tests
 */
import { test as base, expect, Page, request } from '@playwright/test';

// Test user credentials (ensure these exist in test environment)
const TEST_USERS = {
    admin: { username: 'admin', password: 'admin123' },
    manager: { username: 'manager', password: 'manager123' },
    sales: { username: 'sales', password: 'sales123' },
};

export type TestRole = keyof typeof TEST_USERS;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type AuthPayload = {
    token: string;
    role: string;
    username: string;
};

const authCache: Partial<Record<TestRole, AuthPayload>> = {};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function getAuth(role: TestRole): Promise<AuthPayload> {
    const cached = authCache[role];
    if (cached) {
        return cached;
    }

    const creds = TEST_USERS[role];
    const context = await request.newContext({ baseURL: API_BASE_URL });

    let attempt = 0;
    while (true) {
        const response = await context.post('/api/auth/login/', { data: creds });
        if (response.ok()) {
            const data = await response.json();
            const auth = {
                token: data.token as string,
                role: (data.role as string) || role,
                username: (data.username as string) || creds.username,
            };
            authCache[role] = auth;
            await context.dispose();
            return auth;
        }

        if (response.status() === 429 && attempt < 5) {
            attempt += 1;
            await sleep(12000);
            continue;
        }

        const body = await response.text();
        await context.dispose();
        throw new Error(`Login failed for ${role}: ${response.status()} ${body}`);
    }
}

// Extended test fixture with authentication helpers
export const test = base.extend<{
    authenticatedPage: Page;
    loginAs: (role: TestRole) => Promise<void>;
}>({
    // Authenticated page fixture
    authenticatedPage: async ({ page }, use) => {
        // Default login as sales user
        await loginToApp(page, 'sales');
        await use(page);
    },

    // Login helper function
    loginAs: async ({ page }, use) => {
        const login = async (role: TestRole) => {
            await loginToApp(page, role);
        };
        await use(login);
    },
});

// Helper function to perform login
async function loginToApp(page: Page, role: TestRole) {
    const auth = await getAuth(role);

    await page.addInitScript((payload: AuthPayload) => {
        localStorage.setItem('authToken', payload.token);
        localStorage.setItem('userRole', payload.role);
        localStorage.setItem('username', payload.username);
    }, auth);

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForURL('**/dashboard', { timeout: 30000, waitUntil: 'domcontentloaded' });
}

// Re-export expect
export { expect };

// Common test utilities
export const helpers = {
    /**
     * Wait for page to be fully loaded
     */
    async waitForPageLoad(page: Page) {
        await page.waitForLoadState('networkidle');
    },

    /**
     * Clear any toast notifications
     */
    async dismissToasts(page: Page) {
        const closeButtons = page.locator('[data-dismiss="toast"]');
        const count = await closeButtons.count();
        for (let i = 0; i < count; i++) {
            await closeButtons.nth(i).click();
        }
    },

    /**
     * Take a screenshot with a descriptive name
     */
    async screenshot(page: Page, name: string) {
        await page.screenshot({ path: `e2e/screenshots/${name}.png`, fullPage: true });
    },
};
