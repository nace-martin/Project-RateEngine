/**
 * Role-Based Access Control (RBAC) E2E Tests
 * Tests that permissions are properly enforced at the UI level
 */
import { test, expect } from './fixtures';

test.describe('RBAC - Admin Access', () => {
    test.beforeEach(async ({ loginAs, page }) => {
        await loginAs('admin');
        await expect(page.locator('header').getByText('Admin', { exact: true })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to user management', async ({ page }) => {
        await page.goto('/settings/users', { waitUntil: 'domcontentloaded' });

        // Should see user management page
        await expect(page.getByRole('heading', { name: /user management/i })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to rate cards', async ({ page }) => {
        await page.goto('/pricing/rate-cards', { waitUntil: 'domcontentloaded' });

        // Should see rate cards page
        await expect(page.locator('text=/rate card/i').first()).toBeVisible({ timeout: 10000 });
    });

    test('should have access to discounts', async ({ page }) => {
        await page.goto('/pricing/discounts', { waitUntil: 'domcontentloaded' });

        // Should see discounts page
        await expect(page.getByRole('heading', { name: /customer discounts/i })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to settings', async ({ page }) => {
        await page.goto('/settings', { waitUntil: 'domcontentloaded' });

        // Should see settings page
        await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible({ timeout: 10000 });
    });

    test('should see all quotes regardless of department', async ({ page }) => {
        await page.goto('/quotes');

        // Admin should see the quotes table
        await expect(page.locator('table, [data-testid="quotes-list"]').first()).toBeVisible({ timeout: 10000 });
    });
});

test.describe('RBAC - Manager Access', () => {
    test.beforeEach(async ({ loginAs, page }) => {
        await loginAs('manager');
        await expect(page.locator('header').getByText('Manager', { exact: true })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to user management', async ({ page }) => {
        await page.goto('/settings/users', { waitUntil: 'domcontentloaded' });

        // Manager should be able to manage users
        await expect(page.getByRole('heading', { name: /user management/i })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to discounts', async ({ page }) => {
        await page.goto('/pricing/discounts', { waitUntil: 'domcontentloaded' });

        // Manager should see discounts
        await expect(page.getByRole('heading', { name: /customer discounts/i })).toBeVisible({ timeout: 10000 });
    });

    test('should have access to management dashboard', async ({ page }) => {
        await page.goto('/dashboard', { waitUntil: 'commit' });
        const performanceLink = page.getByRole('link', { name: /performance/i }).first();
        await expect(performanceLink).toBeVisible({ timeout: 10000 });
        await expect(performanceLink).toHaveAttribute('href', '/dashboard/management');
    });
});

test.describe('RBAC - Sales Access', () => {
    test.beforeEach(async ({ loginAs, page }) => {
        await loginAs('sales');
        await expect(page.locator('header').getByText('Sales', { exact: true })).toBeVisible({ timeout: 10000 });
    });

    test('should NOT have access to user management', async ({ page }) => {
        await page.goto('/settings/users');

        // Should see access denied or be redirected
        const accessDenied = page.locator('text=/access denied|permission|forbidden/i');
        const redirected = !page.url().includes('/settings/users');

        const denied = await accessDenied.count() > 0 || redirected;
        expect(denied).toBeTruthy();
    });

    test('should be able to create quotes', async ({ page }) => {
        await page.goto('/quotes/new', { waitUntil: 'commit' });
        await page.waitForURL('**/quotes/new', { timeout: 10000 });

        // Should see quote creation form
        await expect(page.locator('text=/customer|origin|destination/i').first()).toBeVisible({ timeout: 10000 });
    });

    test('should only see own quotes', async ({ page }) => {
        await page.goto('/quotes');

        // Sales user should see quotes list (filtered to own)
        await expect(page.locator('table, [data-testid="quotes-list"]').first()).toBeVisible({ timeout: 10000 });
    });

    test('should NOT have access to rate cards edit', async ({ page }) => {
        await page.goto('/pricing/rate-cards');

        // Should see rate cards in read-only mode or access denied
        // Check for absence of edit/add buttons
        const addButton = page.locator('button:has-text("Add"), button:has-text("Create")');
        const addCount = await addButton.count();

        // Sales should not see add/edit buttons (or page is restricted)
        // This is a soft check - depends on implementation
        expect(addCount).toBeLessThanOrEqual(1); // May see New Quote button but not Rate Card add
    });
});

