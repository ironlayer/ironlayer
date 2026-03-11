/**
 * Model catalog E2E tests.
 * Covers unauthenticated redirect and authenticated rendering.
 */

import { test, expect } from '@playwright/test';

test.describe('Model catalog', () => {
  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/models');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  test('authenticated render does not show ErrorBoundary', async ({ page }) => {
    // This test requires E2E_USERNAME and E2E_PASSWORD environment variables.
    // Skip gracefully when credentials are not configured.
    const username = process.env.E2E_USERNAME;
    const password = process.env.E2E_PASSWORD;
    if (!username || !password) {
      test.skip();
      return;
    }

    // Log in first.
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    const emailField = page.locator('input[type="email"], input[name="email"]').first();
    const passwordField = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await emailField.fill(username);
    await passwordField.fill(password);
    await submitBtn.click();

    // Wait for redirect after login.
    await page.waitForURL(/^(?!.*\/login)/, { timeout: 15_000 });

    // Navigate to models page.
    await page.goto('/models');
    await page.waitForLoadState('networkidle');

    // Should NOT show ErrorBoundary fallback text.
    const body = await page.textContent('body');
    expect(body).not.toContain('Something went wrong');
    expect(body).not.toContain('ErrorBoundary');
  });
});
