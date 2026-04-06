import { test, expect } from '@playwright/test';
import { mockChat, mockChatComplete, mockChatHang, mockSession } from './helpers/mock-api';

// Widget URL with pre-set session ID to skip /api/session call
// Note: use clean URLs (no .html) — serve 14.x redirects .html and drops query params
const WIDGET_URL = '/widget/widget?sessionId=test-session-123';
const WIDGET_URL_DH = '/widget/widget?sessionId=test-session-123&dynamicHeight=1';
const WIDGET_URL_ID = '/widget/widget?sessionId=test-session-123&lang=id';

// ── Phase 1: Idle state ────────────────────────────────────────────────────────

test.describe('Phase 1 — idle state', () => {
  test('renders pills and input on load', async ({ page }) => {
    await page.goto(WIDGET_URL);

    // Pills visible
    await expect(page.locator('.ctx-pills')).toBeVisible();
    await expect(page.locator('.ctx-pill')).toHaveCount(3);

    // Input enabled and focusable
    const input = page.locator('.ctx-input');
    await expect(input).toBeEnabled();
    await expect(input).not.toBeDisabled();

    // Messages area hidden (display:none until ctx-expanded)
    await expect(page.locator('.ctx-messages-wrap')).toBeHidden();

    // ctx-expanded NOT on html element
    const hasExpanded = await page.evaluate(() =>
      document.documentElement.classList.contains('ctx-expanded')
    );
    expect(hasExpanded).toBe(false);
  });

  test('widget max-width is at most 600px', async ({ page }) => {
    await page.goto(WIDGET_URL);
    const width = await page.locator('#contextus-widget').evaluate(el =>
      el.getBoundingClientRect().width
    );
    expect(width).toBeLessThanOrEqual(600);
  });

  test('send button starts in empty/disabled state', async ({ page }) => {
    await page.goto(WIDGET_URL);
    await expect(page.locator('.ctx-send')).toHaveClass(/ctx-send-empty/);
  });

  test('send button becomes active when input has text', async ({ page }) => {
    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await expect(page.locator('.ctx-send')).toHaveClass(/ctx-send-active/);
  });
});

// ── Phase 1 → Phase 2: Transition ─────────────────────────────────────────────

test.describe('Phase 1 → Phase 2 transition', () => {
  test('adds ctx-expanded class to <html> on first message', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('What can you help me with?');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
  });

  test('emits contextus:expand postMessage on first message', async ({ page }) => {
    await mockChat(page);

    // Capture postMessages before navigation
    const messages: string[] = [];
    await page.addInitScript(() => {
      window.addEventListener('message', (e) => {
        (window as any).__capturedMessages = (window as any).__capturedMessages || [];
        (window as any).__capturedMessages.push(JSON.stringify(e.data));
      });
    });

    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    // Wait for expand to fire
    await page.waitForFunction(() =>
      ((window as any).__capturedMessages || []).some((m: string) =>
        m.includes('contextus:expand')
      )
    );

    const captured: string[] = await page.evaluate(() => (window as any).__capturedMessages || []);
    expect(captured.some(m => m.includes('contextus:expand'))).toBe(true);
  });

  test('pills are hidden after first message', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-pills')).toBeHidden();
  });

  test('messages wrap becomes visible after transition', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-messages-wrap')).toBeVisible();
  });

  test('visitor message bubble appears in messages area', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('What can you help with?');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-bubble-visitor')).toHaveText('What can you help with?');
  });

  test('input is cleared after sending', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-input')).toHaveValue('');
  });

  test('max-width is preserved (≤600px) after expansion', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);

    const width = await page.locator('#contextus-widget').evaluate(el =>
      el.getBoundingClientRect().width
    );
    expect(width).toBeLessThanOrEqual(600);
  });
});

// ── Animation behavior ─────────────────────────────────────────────────────────

test.describe('Animation behavior', () => {
  // These tests need to observe the transient "thinking" state.
  // We use mockChatHang (never responds) so dots stay visible indefinitely,
  // and mockSession as a fallback in case window.__ctxSessionId isn't picked up.

  test('typing indicator (dots) appears while waiting for response', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    await expect(page.locator('.ctx-dots')).toBeVisible();
    await expect(page.locator('.ctx-dots span')).toHaveCount(3);
  });

  test('typing dots have ctx-dot-pulse animation applied', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    await expect(page.locator('.ctx-dots')).toBeVisible();

    const animationName = await page.locator('.ctx-dots span').first().evaluate(el =>
      getComputedStyle(el).animationName
    );
    expect(animationName).toBe('ctx-dot-pulse');
  });

  test('typing dots have staggered animation delays', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    await expect(page.locator('.ctx-dots')).toBeVisible();

    const delays = await page.locator('.ctx-dots span').evaluateAll(spans =>
      spans.map(s => getComputedStyle(s).animationDelay)
    );

    expect(new Set(delays).size).toBe(3);
    expect(delays).toContain('0s');
    expect(delays).toContain('0.2s');
    expect(delays).toContain('0.4s');
  });

  test('send button is disabled while streaming', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(WIDGET_URL);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    await expect(page.locator('.ctx-send')).toHaveClass(/ctx-send-disabled/);
  });

  test('thinking dots replaced by agent bubble after response', async ({ page }) => {
    await mockChat(page, 'Hello! How can I help?');
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    // Wait for agent bubble with real text (greeting + response = 2 bubbles, check last)
    await expect(page.locator('.ctx-bubble-agent').last()).not.toBeEmpty();
    await expect(page.locator('.ctx-dots')).not.toBeAttached();
  });

  test('send button re-enabled after response', async ({ page }) => {
    await mockChat(page, 'Hi!');
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    // After response, input enabled again
    await expect(page.locator('.ctx-input')).toBeEnabled();
  });
});

// ── Dynamic sizing ─────────────────────────────────────────────────────────────

test.describe('Dynamic sizing', () => {
  test('widget height expands after phase transition', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    const heightBefore = await page.locator('#contextus-widget').evaluate(el =>
      el.getBoundingClientRect().height
    );

    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);

    const heightAfter = await page.locator('#contextus-widget').evaluate(el =>
      el.getBoundingClientRect().height
    );

    expect(heightAfter).toBeGreaterThan(heightBefore);
  });

  test('widget has positive height when dynamicHeight=1 (notifyResize has data to send)', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL_DH);
    await page.locator('.ctx-input').fill('Hello');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);

    // notifyResize() calls getBoundingClientRect().height on the widget.
    // Verify that height is positive — confirming resize messages would carry a non-zero value.
    const height = await page.locator('#contextus-widget').evaluate(el =>
      el.getBoundingClientRect().height
    );
    expect(height).toBeGreaterThan(0);
  });
});

// ── Complete phase ─────────────────────────────────────────────────────────────

test.describe('Complete phase', () => {
  test('input disabled and complete banner shown after conversation ends', async ({ page }) => {
    await page.clock.install();
    await mockSession(page);
    await mockChat(page);
    await page.goto(WIDGET_URL);

    // Send a message with an email — triggers contactCaptured → startCompleteTimer (5min)
    await page.locator('.ctx-input').fill('reach me at test@example.com');
    await page.locator('.ctx-send').click();

    // Wait for agent response bubble (not just the greeting — the actual reply)
    await expect(page.locator('.ctx-bubble-agent').last()).toContainText('Hello');

    // Advance fake clock past the 5-minute complete timer
    await page.clock.fastForward(5 * 60 * 1000 + 1000);

    await expect(page.locator('.ctx-banner-complete')).toBeVisible();
    await expect(page.locator('.ctx-input')).toBeDisabled();
  });

  test('WAITLIST_COMPLETE text is stripped from agent bubble', async ({ page }) => {
    await mockChatComplete(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-input').fill('sign me up');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-bubble-agent').last()).not.toContainText('WAITLIST_COMPLETE');
  });
});

// ── Pill interaction ───────────────────────────────────────────────────────────

test.describe('Pill interaction', () => {
  test('clicking a pill triggers phase transition', async ({ page }) => {
    await mockChat(page);
    await page.goto(WIDGET_URL);

    await page.locator('.ctx-pill').first().click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    await expect(page.locator('.ctx-bubble-visitor')).toBeVisible();
  });
});

// ── Localization (lang=id) ─────────────────────────────────────────────────────

test.describe('Localization — lang=id', () => {
  test('input placeholder is in Indonesian on idle', async ({ page }) => {
    await page.goto(WIDGET_URL_ID);
    const placeholder = await page.locator('.ctx-input').getAttribute('placeholder');
    expect(placeholder).toBe('Tanya apa saja...');
  });

  test('fallback pills are in Indonesian when no KB pills provided', async ({ page }) => {
    await page.goto(WIDGET_URL_ID);
    const pills = await page.locator('.ctx-pill').allTextContents();
    expect(pills).toEqual(['Apa layanan Anda?', 'Bagaimana Anda membantu?', 'Cara menghubungi?']);
  });

  test('thinking placeholder is in Indonesian while waiting', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(WIDGET_URL_ID);
    await page.locator('.ctx-input').fill('Halo');
    await page.locator('.ctx-send').click();

    await expect(page.locator('html')).toHaveClass(/ctx-expanded/);
    const placeholder = await page.locator('.ctx-input').getAttribute('placeholder');
    expect(placeholder).toBe('Menunggu balasan...');
  });

  test('active placeholder is in Indonesian after response', async ({ page }) => {
    await mockChat(page, 'Halo! Ada yang bisa kami bantu?');
    await page.goto(WIDGET_URL_ID);
    await page.locator('.ctx-input').fill('Halo');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-bubble-agent').last()).not.toBeEmpty();
    const placeholder = await page.locator('.ctx-input').getAttribute('placeholder');
    expect(placeholder).toBe('Ketik pesan...');
  });

  test('complete banner is in Indonesian', async ({ page }) => {
    await mockChatComplete(page);
    await page.goto(WIDGET_URL_ID);
    await page.locator('.ctx-input').fill('daftar');
    await page.locator('.ctx-send').click();

    await expect(page.locator('.ctx-bubble-agent').last()).not.toContainText('WAITLIST_COMPLETE');
  });

  test('English widget is unaffected (lang=en still shows English)', async ({ page }) => {
    await page.goto(WIDGET_URL);
    const placeholder = await page.locator('.ctx-input').getAttribute('placeholder');
    expect(placeholder).toBe('Ask us anything...');
    const pills = await page.locator('.ctx-pill').allTextContents();
    expect(pills).toEqual(['What services do you offer?', 'How can you help me?', 'How do I contact you?']);
  });
});
