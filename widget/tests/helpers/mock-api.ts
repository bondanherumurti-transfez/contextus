import type { Page } from '@playwright/test';

/**
 * Intercepts POST /api/session and returns a test session ID.
 * Use alongside mockChat when window.__ctxSessionId may not be set
 * (e.g. when the route handler delays the chat response).
 */
export async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/session', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ session_id: 'test-session-123' }),
    })
  );
}

/**
 * Intercepts POST /api/chat/* and returns a minimal SSE stream
 * with the given reply text as a single token.
 */
export async function mockChat(page: Page, reply: string = 'Hello! How can I help you today?'): Promise<void> {
  await page.route('**/api/chat/**', route => {
    const sseBody = `data: ${JSON.stringify({ token: reply })}\n\n`;
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache' },
      body: sseBody,
    });
  });
}

/**
 * Intercepts POST /api/chat/* and never responds.
 * Keeps the widget in the "thinking" (dots) state indefinitely.
 * Useful for asserting transient loading states.
 */
export async function mockChatHang(page: Page): Promise<void> {
  await page.route('**/api/chat/**', () => { /* never fulfill */ });
}

/**
 * Intercepts POST /api/chat/* and returns a WAITLIST_COMPLETE signal
 * to trigger the complete phase.
 */
export async function mockChatComplete(page: Page): Promise<void> {
  await page.route('**/api/chat/**', route => {
    const sseBody = `data: ${JSON.stringify({ token: 'Thank you! WAITLIST_COMPLETE' })}\n\n`;
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache' },
      body: sseBody,
    });
  });
}
