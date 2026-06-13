import { test, expect } from "./fixtures";

test.describe("SPOT Validation Dashboard - Access Controls", () => {
  test("Sales user should be blocked from validation dashboard and sidebar/header", async ({ loginAs, page }) => {
    await loginAs("sales");
    
    // Header More button should either not exist or not contain SPOT Analytics
    const moreButton = page.getByRole('button', { name: /more/i });
    const count = await moreButton.count();
    if (count > 0) {
      await moreButton.click();
      const analyticsLink = page.locator('a:has-text("SPOT Analytics")');
      await expect(analyticsLink).toHaveCount(0);
    }

    // Direct access should show Access Denied
    await page.goto("/dashboard/management/spot-validation", { waitUntil: "domcontentloaded" });
    await expect(page.locator("text=/Access Denied/i")).toBeVisible({ timeout: 10000 });
  });

  test("Manager user should see sidebar/header link and access validation dashboard", async ({ loginAs, page }) => {
    // Mock successful API responses to avoid hitting real backend during visual check
    await page.route("**/api/v3/spot/template-validation/snapshot-metrics/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_snapshots: 45,
          unique_envelopes_count: 12,
          validation_status_breakdown: { passed: 20, warnings: 15, review: 10 }
        })
      });
    });

    await page.route("**/api/v3/spot/template-validation/comparison-metrics/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          summary: {
            total_envelopes_with_snapshots: 12,
            total_envelopes_with_reviews: 6,
            global_review_rate_percentage: 50.0
          },
          finding_code_comparison: [
            { finding_code: "expected_charge_missing", envelopes_with_snapshot_count: 8, envelopes_reviewed_count: 4, review_rate_percentage: 50.0 }
          ],
          canonical_type_comparison: [
            { canonical_type: "AWB", envelopes_with_snapshot_count: 8, envelopes_reviewed_count: 4, review_rate_percentage: 50.0 }
          ]
        })
      });
    });

    await page.route("**/api/v3/spot/template-validation/maintenance-insights/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          insights: [
            {
              template_id: 1,
              template_name: "Test Template A",
              snapshot_count: 5,
              warnings_count: 3,
              review_count: 1,
              issue_ratio_percentage: 60.0,
              unreviewed_ratio_percentage: 40.0,
              review_rate_percentage: 60.0,
              average_findings_per_snapshot: 1.5,
              maintenance_priority_score: 75.0,
              high_maintenance_pressure: true,
              sample_warning: false,
              finding_codes_breakdown: [],
              canonical_types_breakdown: []
            }
          ]
        })
      });
    });

    await loginAs("manager");

    // Click More button to find SPOT Analytics link
    await page.getByRole('button', { name: /more/i }).first().click();
    const analyticsLink = page.locator('a:has-text("SPOT Analytics")').first();
    await expect(analyticsLink).toBeVisible({ timeout: 10000 });
    await analyticsLink.click();

    // Verify page title and header
    await expect(page.locator("h1:has-text('SPOT Validation Intelligence')")).toBeVisible({ timeout: 15000 });

    // Verify statistics cards are populated
    await expect(page.locator("text=/Total Captured Snapshots/i")).toBeVisible();
    await expect(page.locator("div.text-indigo-600:has-text('45')").first()).toBeVisible();

    // Verify maintenance Insights table renders data
    await expect(page.locator("text=Test Template A")).toBeVisible();
    await expect(page.locator("text=High Pressure")).toBeVisible();

    // Verify comparison table renders data
    await expect(page.locator("text=expected_charge_missing")).toBeVisible();
  });

  test("Manager user sees friendly 503 disabled message if backend toggle is disabled", async ({ loginAs, page }) => {
    // Intercept with 503 Service Unavailable
    await page.route("**/api/v3/spot/template-validation/**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "SPOT validation metrics are temporarily disabled."
        })
      });
    });

    await loginAs("manager");

    await page.goto("/dashboard/management/spot-validation", { waitUntil: "domcontentloaded" });

    // Expect friendly message to be visible
    await expect(page.locator("text=/Metrics Temporarily Offline/i")).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=/SPOT validation metrics are temporarily disabled/i")).toBeVisible();
  });
});
