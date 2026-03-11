/**
 * API health and security header E2E tests.
 * Cross-service validation: verifies the API serves correct security headers
 * and health endpoints return valid responses.
 *
 * Uses API_URL (port 8000) directly — not the frontend proxy — to validate
 * headers set by the API CSP middleware without nginx interference.
 */

import { test, expect, request } from '@playwright/test';
import { API_URL } from '../playwright.config';

test.describe('API health endpoint', () => {
  test('health endpoint returns valid JSON', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/health');
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toBeTruthy();
    await ctx.dispose();
  });
});

test.describe('Security headers', () => {
  test('CSP header is present and does not contain unsafe-inline', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/health');

    const csp = response.headers()['content-security-policy'];
    expect(csp).toBeTruthy();
    expect(csp).not.toContain('unsafe-inline');
    expect(csp).toContain("default-src 'self'");
    await ctx.dispose();
  });

  test('X-Content-Type-Options is nosniff', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/health');

    expect(response.headers()['x-content-type-options']).toBe('nosniff');
    await ctx.dispose();
  });

  test('X-Frame-Options is DENY', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/health');

    expect(response.headers()['x-frame-options']).toBe('DENY');
    await ctx.dispose();
  });
});

test.describe('Protected endpoints require authentication', () => {
  test('plans endpoint rejects unauthenticated requests', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/plans');
    // Should be 401 or 403 (not 500).
    expect([401, 403]).toContain(response.status());
    await ctx.dispose();
  });

  test('models endpoint rejects unauthenticated requests', async () => {
    const ctx = await request.newContext({ baseURL: API_URL });
    const response = await ctx.get('/api/v1/models');
    expect([401, 403]).toContain(response.status());
    await ctx.dispose();
  });
});
