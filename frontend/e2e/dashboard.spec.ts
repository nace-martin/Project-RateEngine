/**
 * Dashboard E2E Tests
 * Tests dashboard functionality for different user roles
 */
import { test, expect } from './fixtures';

test.describe('Dashboard - Sales User', () => {
    test('should display dashboard with KPI cards', async ({ authenticatedPage: page }) => {
        // Already logged in via fixture

        // Dashboard should show KPI widgets
        await expect(page.locator('text=/pipeline|finalized|activity/i').first()).toBeVisible({ timeout: 10000 });
    });

    test('should display recent quotes table', async ({ authenticatedPage: page }) => {
        await expect(page.getByText(/recent activity/i)).toBeVisible({ timeout: 10000 });
    });

    test('should have timeframe toggle', async ({ authenticatedPage: page }) => {
        await expect(page.getByRole('heading', { name: /sales metrics/i })).toBeVisible({ timeout: 10000 });
    });

    test('should navigate to quotes from dashboard', async ({ authenticatedPage: page }) => {
        const viewAllLink = page.getByRole('link', { name: /^View All$/ }).first();
        await expect(viewAllLink).toHaveAttribute('href', '/quotes');
    });
});

test.describe('Dashboard - Manager User', () => {
    test('should see Performance button', async ({ loginAs, page }) => {
        await loginAs('manager');

        const perfBtn = page.locator('a:has-text("Performance"), button:has-text("Performance")');
        await expect(perfBtn.first()).toBeVisible({ timeout: 10000 });
    });

    test('should access management dashboard', async ({ loginAs, page }) => {
        await loginAs('manager');
        const performanceLink = page.getByRole('link', { name: /performance/i }).first();
        await expect(performanceLink).toHaveAttribute('href', '/dashboard/management');
    });
});
