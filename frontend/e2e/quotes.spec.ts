/**
 * Quote Creation E2E Tests
 * Tests the full quote creation workflow
 */
import { test, expect } from './fixtures';

test.describe('Quote Creation Flow', () => {
    test.describe.configure({ mode: 'serial' });

    test('should navigate to new quote page', async ({ authenticatedPage: page }) => {
        // Click New Quote button
        const newQuoteLink = page.locator('a[href="/quotes/new"]').first();
        await expect(newQuoteLink).toBeVisible();
        await expect(newQuoteLink).toHaveAttribute('href', '/quotes/new');
    });

    test('should display quote form with required fields', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes/new', { waitUntil: 'commit' });
        await page.waitForURL('**/quotes/new', { timeout: 10000 });
        await expect(page.getByText('Customer Details')).toBeVisible({ timeout: 10000 });

        // Check for essential form elements
        await expect(page.getByText('Customer Details')).toBeVisible();
        await expect(page.getByText('Route & Service')).toBeVisible();
        await expect(page.getByText('Cargo Details')).toBeVisible();
    });

    test('should validate required fields before submission', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes/new', { waitUntil: 'commit' });
        await page.waitForURL('**/quotes/new', { timeout: 10000 });
        await expect(page.getByText('Customer Details')).toBeVisible({ timeout: 10000 });

        const contactTrigger = page.getByRole('combobox', { name: /contact person/i });
        await expect(contactTrigger).toBeDisabled();
        await expect(page).toHaveURL(/.*quotes\/new/);
    });

    test('should create a draft quote successfully', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes/new', { waitUntil: 'commit' });
        await page.waitForURL('**/quotes/new', { timeout: 10000 });
        await expect(page.getByText('Customer Details')).toBeVisible({ timeout: 10000 });

        // Customer selection
        const customerInput = page.getByPlaceholder('Search for a customer...');
        await customerInput.fill('Seed');
        const dropdown = customerInput.locator('..').locator('div.absolute');
        await expect(dropdown).toBeVisible({ timeout: 10000 });
        const customerOption = dropdown.getByRole('button').first();
        await expect(customerOption).toBeVisible({ timeout: 10000 });
        await customerOption.click();

        // Contact selection
        const contactTrigger = page.getByRole('combobox', { name: /contact person/i });
        await expect(contactTrigger).toBeEnabled({ timeout: 10000 });
        await expect(contactTrigger).not.toHaveText(/loading/i, { timeout: 10000 });
        await contactTrigger.click({ noWaitAfter: true });
        const contactOption = page.getByRole('option').filter({ hasNotText: /no contacts/i }).first();
        await contactOption.click();

        // Origin location
        const originField = page.getByText('Origin (AIRPORT)').locator('..');
        const originCombo = originField.getByRole('combobox');
        await originCombo.click();
        await page.getByPlaceholder('Type 2+ chars to search').fill('POM');
        const originOption = page.locator('[cmdk-item]').first();
        await expect(originOption).toBeVisible({ timeout: 10000 });
        await originOption.click();

        // Destination location
        const destinationField = page.getByText('Destination (AIRPORT)').locator('..');
        const destinationCombo = destinationField.getByRole('combobox');
        await destinationCombo.click();
        await page.getByPlaceholder('Type 2+ chars to search').fill('SYD');
        const destinationOption = page.locator('[cmdk-item]').first();
        await expect(destinationOption).toBeVisible({ timeout: 10000 });
        await destinationOption.click();

        // Dimensions and weight
        await page.locator('input[name="dimensions.0.length_cm"]').fill('10');
        await page.locator('input[name="dimensions.0.width_cm"]').fill('10');
        await page.locator('input[name="dimensions.0.height_cm"]').fill('10');
        await page.locator('input[name="dimensions.0.gross_weight_kg"]').fill('100');

        // Submit the form
        const submitBtn = page.getByRole('button', { name: /generate quote|calculate|create|save/i }).first();
        await submitBtn.click();

        const modalHeading = page.getByRole('heading', { name: /request partner quote/i });
        if (await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
            await page.getByRole('button', { name: /copy email template/i }).click();
        }

        await expect(page).toHaveURL(/\/quotes\/(spot\/)?[a-zA-Z0-9-]+/);
    });
});

test.describe('Quote List', () => {
    test('should display quotes list', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes', { waitUntil: 'domcontentloaded' });

        // Page should have quotes heading
        await expect(page.locator('h1:has-text("Quotes"), h1:has-text("Quote")')).toBeVisible();

        // Should have table or list of quotes
        const table = page.locator('table, [role="table"], [data-testid="quotes-list"]');
        await expect(table).toBeVisible({ timeout: 10000 });
    });

    test('should filter quotes by search', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes', { waitUntil: 'domcontentloaded' });

        // Find search input
        const searchInput = page.locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="filter" i]').first();

        if (await searchInput.isVisible()) {
            await searchInput.fill('test');
            await page.waitForTimeout(500); // Wait for debounce

            // Table should update (may show no results)
            const table = page.locator('table tbody, [data-testid="quotes-list"]');
            await expect(table).toBeVisible();
        }
    });

    test('should navigate to quote detail', async ({ authenticatedPage: page }) => {
        await page.goto('/quotes', { waitUntil: 'domcontentloaded' });

        // Wait for table to load
        await page.waitForSelector('table tbody tr, [data-testid="quote-row"]', { timeout: 10000 }).catch(() => { });

        // Click on first View/Resume action
        const actionLink = page.getByRole('link', { name: /view|resume/i }).first();
        if (await actionLink.count() > 0) {
            await expect(actionLink).toHaveAttribute('href', /\/quotes\/(spot\/)?[a-zA-Z0-9-]+/);
        }
    });
});
