/**
 * Navigation E2E tests.
 * Verifies public routes render and protected routes redirect
 * unauthenticated users to the login page.
 */

import { test, expect } from '@playwright/test';

test.describe('Public routes', () => {
  test('login page renders without error', async ({ page }) => {
    const response = await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Should not be a server error.
    expect(response?.status()).toBeLessThan(500);

    // Page should contain a form element.
    const form = page.locator('form, [role="form"]');
    await expect(form.first()).toBeAttached({ timeout: 10_000 });
  });

  test('signup page renders without error', async ({ page }) => {
    const response = await page.goto('/signup');
    await page.waitForLoadState('networkidle');

    expect(response?.status()).toBeLessThan(500);
  });
});

test.describe('Protected routes redirect to login', () => {
  const protectedPaths = [
    '/',
    '/models',
    '/usage',
    '/billing',
    '/environments',
    '/settings',
  ];

  for (const path of protectedPaths) {
    test(`${path} redirects unauthenticated to /login`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState('networkidle');

      // Should redirect to login (URL contains /login).
      await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    });
  }
});
