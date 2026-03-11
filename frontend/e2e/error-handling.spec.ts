/**
 * Error handling E2E tests.
 * Verifies the application handles unknown routes gracefully without
 * white-screening or crashing the React root.
 */

import { test, expect } from '@playwright/test';

test.describe('Error handling', () => {
  test('unknown route does not crash the app', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-12345');
    await page.waitForLoadState('networkidle');

    // The React root should still be mounted (no white-screen).
    const root = page.locator('#root');
    await expect(root).toBeAttached({ timeout: 10_000 });

    // Should NOT show a raw error stack trace.
    const body = await page.textContent('body');
    expect(body).not.toContain('Uncaught');
    expect(body).not.toContain('Cannot read properties');
  });

  test('root element stays mounted on bad navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Navigate to a non-existent path via client-side routing.
    await page.evaluate(() => window.history.pushState({}, '', '/bogus-path'));
    // Give React a moment to re-render.
    await page.waitForTimeout(1000);

    const root = page.locator('#root');
    await expect(root).toBeAttached();
  });
});
