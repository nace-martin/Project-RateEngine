/**
 * Authentication E2E Tests
 * Tests login flow, session management, and role-based access
 */
import { test, expect } from '@playwright/test';

test.describe.serial('Authentication', () => {
    test.beforeEach(async ({ page }) => {
        // Clear any existing auth state
        await page.context().clearCookies();
        await page.goto('/login');
        await page.evaluate(() => localStorage.clear());
    });

    test('should display login page for unauthenticated users', async ({ page }) => {
        await page.goto('/login', { waitUntil: 'domcontentloaded' });

        // Should stay on login
        await expect(page).toHaveURL(/\/login/);

        // Login form should be visible
        await expect(page.locator('input[name="username"], input[id="username"]')).toBeVisible();
        await expect(page.locator('input[name="password"], input[id="password"]')).toBeVisible();
        await expect(page.locator('button[type="submit"]')).toBeVisible();
    });

    test('should login successfully with valid credentials', async ({ page }) => {
        await page.goto('/login');

        // Fill in credentials (use test user)
        await page.fill('input[name="username"], input[id="username"]', 'admin');
        await page.fill('input[name="password"], input[id="password"]', 'admin123');
        await page.click('button[type="submit"]');

        // Should redirect to dashboard
        await page.waitForURL('**/dashboard', { timeout: 30000 });

        // Dashboard content should be visible
        await expect(page.getByRole('heading', { name: /hello|welcome back/i }).first()).toBeVisible({ timeout: 10000 });
    });

    test('should show error for invalid credentials', async ({ page }) => {
        await page.goto('/login');

        await page.fill('input[name="username"], input[id="username"]', 'wronguser');
        await page.fill('input[name="password"], input[id="password"]', 'wrongpass');
        await page.click('button[type="submit"]');

        // Should show error message
        await expect(page.getByText(/login failed|invalid|incorrect/i)).toBeVisible({ timeout: 10000 });

        // Should stay on login page
        await expect(page).toHaveURL(/\/login/);
    });

    test('should logout successfully', async ({ page }) => {
        // First login
        await page.goto('/login');
        await page.fill('input[name="username"], input[id="username"]', 'admin');
        await page.fill('input[name="password"], input[id="password"]', 'admin123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard', { timeout: 30000 });

        // Find and click logout button (in user dropdown)
        const userMenu = page.getByRole('button', { name: /admin/i }).first();
        await userMenu.click();

        const logoutButton = page.getByRole('menuitem', { name: /logout/i }).first();
        await expect(logoutButton).toBeVisible();
        await logoutButton.click();

        // Should redirect to login
        await expect(page).toHaveURL(/\/login/);
    });

    test('should protect routes from unauthorized access', async ({ page }) => {
        // Try to access protected route without auth
        await page.goto('/quotes');

        // Should redirect to login
        await expect(page).toHaveURL(/\/login/);
    });
});
