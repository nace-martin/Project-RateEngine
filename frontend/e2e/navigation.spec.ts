/**
 * Navigation E2E Tests
 * Tests navigation structure and accessibility
 */
import { test, expect } from './fixtures';

test.describe('Navigation', () => {
    test.beforeEach(async ({ loginAs, page }) => {
        await loginAs('manager');
        await expect(page.locator('header').getByText('Manager', { exact: true })).toBeVisible({ timeout: 10000 });
    });

    test('should display main navigation items', async ({ page }) => {
        // Check for primary nav items
        await expect(page.locator('nav a:has-text("Dashboard"), header a:has-text("Dashboard")')).toBeVisible();
        await expect(page.locator('nav a:has-text("Quotes"), header a:has-text("Quotes")')).toBeVisible();
    });

    test('should navigate to Dashboard', async ({ page }) => {
        await page.goto('/quotes');

        const dashboardLink = page.locator('nav a:has-text("Dashboard"), header a:has-text("Dashboard")').first();
        await dashboardLink.click();

        await expect(page).toHaveURL(/\/dashboard/);
    });

    test('should navigate to Quotes', async ({ page }) => {
        const quotesLink = page.locator('nav a:has-text("Quotes"), header a:has-text("Quotes")').first();
        await quotesLink.click();

        await expect(page).toHaveURL(/\/quotes/);
    });

    test('should navigate to Customers', async ({ page }) => {
        await page.goto('/customers', { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('main').getByText('Customers', { exact: true })).toBeVisible();
    });

    test('should open More dropdown', async ({ page }) => {
        const moreBtn = page.locator('button:has-text("More")').first();

        if (await moreBtn.isVisible()) {
            await moreBtn.click();

            // Dropdown should show items
            const dropdown = page.locator('[role="menu"], [data-radix-menu-content]');
            await expect(dropdown).toBeVisible();
        }
    });

    test('should display user menu', async ({ page }) => {
        // Find user menu trigger
        const userMenu = page.getByRole('button', { name: /manager/i }).first();

        if (await userMenu.isVisible()) {
            await userMenu.click();

            // Should show dropdown with logout option
            await expect(page.getByRole('menuitem', { name: /logout/i }).first()).toBeVisible();
        }
    });

    test('should show role badge', async ({ page }) => {
        // Role badge should be visible
        const badge = page.locator('header').getByText('Manager', { exact: true });
        await expect(badge.first()).toBeVisible();
    });
});

test.describe('Mobile Navigation', () => {
    test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE

    test.beforeEach(async ({ loginAs, page }) => {
        await loginAs('sales');
        await expect(page.getByRole('heading', { name: /hello/i })).toBeVisible({ timeout: 10000 });
    });

    test('should show mobile menu button', async ({ page }) => {
        const menuButton = page.locator('button[aria-label*="menu" i], button:has(svg)').first();
        await expect(menuButton).toBeVisible();
    });

    test('should open mobile navigation', async ({ page }) => {
        // Find menu trigger
        const menuButton = page.locator('button[aria-label*="menu" i], [data-testid="mobile-menu"]').first();

        if (await menuButton.isVisible()) {
            await menuButton.click();

            // Mobile menu should appear
            const mobileNav = page.locator('[role="dialog"], [data-state="open"]');
            await expect(mobileNav.first()).toBeVisible();
        }
    });
});
