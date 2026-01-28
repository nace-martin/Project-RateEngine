import { defineConfig, devices } from '@playwright/test';

/**
 * RateEngine E2E Test Configuration
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
    /* Global test timeout */
    timeout: 60 * 1000,
    testDir: './e2e',

    /* Run tests in parallel */
    fullyParallel: true,

    /* Fail the build on CI if you accidentally left test.only in the source code. */
    forbidOnly: !!process.env.CI,

    /* Retry on CI only */
    retries: process.env.CI ? 2 : 0,

    /* Opt out of parallel tests on CI. */
    workers: process.env.CI ? 1 : undefined,

    /* Reporter to use */
    reporter: [
        ['list'],
        ['html', { open: 'never' }],
    ],

    /* Shared settings for all the projects below */
    use: {
        /* Base URL for navigation */
        baseURL: 'http://localhost:3001',

        /* Collect trace when retrying the failed test */
        trace: 'on-first-retry',

        /* Screenshot on failure */
        screenshot: 'only-on-failure',

        /* Navigation timeout for slower dev servers */
        navigationTimeout: 60 * 1000,
    },

    /* Default timeout for assertions */
    expect: {
        timeout: 30 * 1000,
    },

    /* Configure projects for major browsers */
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
        // Uncomment for more browsers:
        // {
        //   name: 'firefox',
        //   use: { ...devices['Desktop Firefox'] },
        // },
        // {
        //   name: 'webkit',
        //   use: { ...devices['Desktop Safari'] },
        // },
    ],

    /* Run local dev server before starting the tests */
    webServer: {
        command: 'npm run dev -- -p 3001',
        url: 'http://localhost:3001',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
    },
});
