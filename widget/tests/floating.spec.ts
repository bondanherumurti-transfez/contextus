import { test, expect, type Page } from '@playwright/test';

const URL = '/widget/floating-demo.html';

// ── Shadow DOM helpers ─────────────────────────────────────────────────────────
// `pierce/` CSS engine pierces all shadow roots in the document.

// Playwright's CSS engine pierces open Shadow DOM by default —
// plain class selectors work without any special prefix.
const sel = {
  fab:      '.ctxf-fab',
  panel:    '.ctxf-panel',
  header:   '.ctxf-header',
  messages: '.ctxf-messages',
  input:    '.ctxf-input',
  send:     '.ctxf-send',
  close:    '.ctxf-close-btn',
  back:     '.ctxf-back-btn',
  badge:    '.ctxf-badge',
  pills:    '.ctxf-pills',
  pill:     '.ctxf-pill',
  dots:     '.ctxf-dots',
  bubbleAgent:   '.ctxf-bubble-agent',
  bubbleVisitor: '.ctxf-bubble-visitor',
};

/** Intercept the Render backend so tests never hit the real network. */
async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/session', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ session_id: 'test-session-float' }),
    })
  );
}

async function mockChat(page: Page, reply = 'Hello! How can I help you?'): Promise<void> {
  await page.route('**/api/chat/**', route =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache' },
      body: `data: ${JSON.stringify({ token: reply })}\n\n`,
    })
  );
}

async function mockChatHang(page: Page): Promise<void> {
  await page.route('**/api/chat/**', () => { /* never fulfill — keeps dots visible */ });
}

/** Open the panel via JS API (avoids FAB click timing issues). */
async function openWidget(page: Page): Promise<void> {
  await page.evaluate(() => (window as any).contextus.open());
  await expect(page.locator(sel.panel)).toHaveClass(/ctxf-open/);
}

// ── FAB: visibility & positioning ─────────────────────────────────────────────

test.describe('FAB — visibility & position', () => {
  test('FAB is visible on page load', async ({ page }) => {
    await page.goto(URL);
    await expect(page.locator(sel.fab)).toBeVisible();
  });

  test('FAB is positioned at bottom-right by default', async ({ page }) => {
    await page.goto(URL);
    const box = await page.locator(sel.fab).boundingBox();
    const vp  = page.viewportSize()!;
    expect(box).not.toBeNull();
    // FAB right edge should be near the right of the viewport
    expect(box!.x + box!.width).toBeGreaterThan(vp.width * 0.7);
    // FAB bottom edge near the bottom
    expect(box!.y + box!.height).toBeGreaterThan(vp.height * 0.7);
  });

  test('FAB is 56 × 56 px', async ({ page }) => {
    await page.goto(URL);
    const box = await page.locator(sel.fab).boundingBox();
    expect(box!.width).toBeCloseTo(56, 0);
    expect(box!.height).toBeCloseTo(56, 0);
  });
});

// ── Panel: closed by default ───────────────────────────────────────────────────

test.describe('Panel — initial state', () => {
  test('panel does not have ctxf-open on load', async ({ page }) => {
    await page.goto(URL);
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-open/);
  });

  test('panel is not visible before FAB click', async ({ page }) => {
    await page.goto(URL);
    // opacity:0 + pointer-events:none → not interactable; check class rather than visibility
    const hasOpen = await page.locator(sel.panel).evaluate(el => el.classList.contains('ctxf-open'));
    expect(hasOpen).toBe(false);
  });
});

// ── Open / Close ───────────────────────────────────────────────────────────────

test.describe('Open / close', () => {
  test('FAB click opens the panel', async ({ page }) => {
    await page.goto(URL);
    await page.locator(sel.fab).click();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-open/);
  });

  test('close button closes the panel', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.close).click();
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-open/);
  });

  test('FAB gets ctxf-open class when panel is open', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.fab)).toHaveClass(/ctxf-open/);
  });

  test('FAB loses ctxf-open class when panel is closed', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.close).click();
    await expect(page.locator(sel.fab)).not.toHaveClass(/ctxf-open/);
  });
});

// ── JS API ─────────────────────────────────────────────────────────────────────

test.describe('JS API', () => {
  test('contextus.open() opens the panel', async ({ page }) => {
    await page.goto(URL);
    await page.evaluate(() => (window as any).contextus.open());
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-open/);
  });

  test('contextus.close() closes the panel', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.evaluate(() => (window as any).contextus.close());
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-open/);
  });

  test('contextus.toggle() toggles open→close→open', async ({ page }) => {
    await page.goto(URL);
    await page.evaluate(() => (window as any).contextus.toggle());
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-open/);
    await page.evaluate(() => (window as any).contextus.toggle());
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-open/);
  });

  test('contextus.setBadge() shows badge with value', async ({ page }) => {
    await page.goto(URL);
    await page.evaluate(() => (window as any).contextus.setBadge('7'));
    await expect(page.locator(sel.badge)).not.toHaveClass(/ctxf-hidden/);
    await expect(page.locator(sel.badge)).toHaveText('7');
  });

  test('contextus.clearBadge() hides the badge', async ({ page }) => {
    await page.goto(URL);
    await page.evaluate(() => (window as any).contextus.clearBadge());
    await expect(page.locator(sel.badge)).toHaveClass(/ctxf-hidden/);
  });

  test('badge is hidden when panel opens', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.badge)).toHaveClass(/ctxf-hidden/);
  });

  test('on("open") fires when panel opens', async ({ page }) => {
    await page.goto(URL);
    await page.evaluate(() => {
      (window as any).__openFired = false;
      (window as any).contextus.on('open', () => { (window as any).__openFired = true; });
    });
    await page.evaluate(() => (window as any).contextus.open());
    const fired = await page.evaluate(() => (window as any).__openFired);
    expect(fired).toBe(true);
  });

  test('on("close") fires when panel closes', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.evaluate(() => {
      (window as any).__closeFired = false;
      (window as any).contextus.on('close', () => { (window as any).__closeFired = true; });
    });
    await page.evaluate(() => (window as any).contextus.close());
    const fired = await page.evaluate(() => (window as any).__closeFired);
    expect(fired).toBe(true);
  });
});

// ── Greeting & pills ───────────────────────────────────────────────────────────

test.describe('Greeting & pills', () => {
  test('greeting message appears on first open', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.bubbleAgent).first()).toBeVisible();
    await expect(page.locator(sel.bubbleAgent).first()).not.toBeEmpty();
  });

  test('greeting is not repeated on re-open', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const countAfterFirst = await page.locator(sel.bubbleAgent).count();
    await page.evaluate(() => (window as any).contextus.close());
    await page.evaluate(() => (window as any).contextus.open());
    const countAfterSecond = await page.locator(sel.bubbleAgent).count();
    expect(countAfterSecond).toBe(countAfterFirst);
  });

  test('pills (3) are visible on first open', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.pill)).toHaveCount(3);
  });

  test('pills disappear after sending a message', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.pills)).toBeHidden();
  });

  test('clicking a pill sends its text as a message', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    const pillText = await page.locator(sel.pill).first().innerText();
    await page.locator(sel.pill).first().click();
    await expect(page.locator(sel.bubbleVisitor)).toHaveText(pillText);
  });
});

// ── Messaging & streaming ──────────────────────────────────────────────────────

test.describe('Messaging & streaming', () => {
  test('visitor bubble appears after sending', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('What do you do?');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleVisitor)).toHaveText('What do you do?');
  });

  test('input is cleared after sending', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.input)).toHaveValue('');
  });

  test('thinking dots appear while waiting for response', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.dots)).toBeVisible();
    await expect(page.locator('.ctxf-dots span')).toHaveCount(3);
  });

  test('input is disabled while response is streaming', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.dots)).toBeVisible();
    await expect(page.locator(sel.input)).toBeDisabled();
  });

  test('thinking dots replaced by agent bubble after response', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'I can help with that!');
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('I can help with that!');
    await expect(page.locator(sel.dots)).not.toBeAttached();
  });

  test('input re-enabled after response completes', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Done!');
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).not.toBeEmpty();
    await expect(page.locator(sel.input)).toBeEnabled();
  });

  test('send button activates when input has text', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.send)).not.toHaveClass(/ctxf-active/);
    await page.locator(sel.input).fill('Hello');
    await expect(page.locator(sel.send)).toHaveClass(/ctxf-active/);
  });

  test('on("message") fires with visitor role on send', async ({ page }) => {
    await mockSession(page);
    await mockChatHang(page);
    await page.goto(URL);
    await openWidget(page);
    await page.evaluate(() => {
      (window as any).__msgs = [];
      (window as any).contextus.on('message', (d: any) => (window as any).__msgs.push(d));
    });
    await page.locator(sel.input).fill('Test message');
    await page.locator(sel.send).click();
    const msgs = await page.evaluate(() => (window as any).__msgs);
    expect(msgs.some((m: any) => m.role === 'visitor' && m.text === 'Test message')).toBe(true);
  });

  test('on("message") fires with agent role after response', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Agent reply here');
    await page.goto(URL);
    await openWidget(page);
    await page.evaluate(() => {
      (window as any).__msgs = [];
      (window as any).contextus.on('message', (d: any) => (window as any).__msgs.push(d));
    });
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await page.waitForFunction(() =>
      ((window as any).__msgs || []).some((m: any) => m.role === 'agent')
    );
    const msgs = await page.evaluate(() => (window as any).__msgs);
    expect(msgs.some((m: any) => m.role === 'agent' && m.text === 'Agent reply here')).toBe(true);
  });
});

// ── Desktop design integrity ───────────────────────────────────────────────────

test.describe('Desktop design', () => {
  test('panel is desktop-width (not full-screen) on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(URL);
    await openWidget(page);
    const box = await page.locator(sel.panel).boundingBox();
    // Panel should be ≤380px and well under the full viewport width
    expect(box!.width).toBeLessThanOrEqual(380);
    expect(box!.width).toBeGreaterThanOrEqual(300);
  });

  test('back button is hidden on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(URL);
    await openWidget(page);
    const display = await page.locator(sel.back).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(display).toBe('none');
  });

  test('panel has white background on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(URL);
    await openWidget(page);
    const bg = await page.locator(sel.panel).evaluate(el =>
      getComputedStyle(el).backgroundColor
    );
    // rgb(255, 255, 255) = white
    expect(bg).toBe('rgb(255, 255, 255)');
  });
});

// ── Mobile design integrity ────────────────────────────────────────────────────

test.describe('Mobile design (<480px)', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('panel takes full viewport width on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const box = await page.locator(sel.panel).boundingBox();
    expect(box!.width).toBeCloseTo(375, 1);
  });

  test('panel takes full viewport height on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const box = await page.locator(sel.panel).boundingBox();
    expect(Math.round(box!.height)).toBe(812);
  });

  test('panel background is dark (#1a1a1a) on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const bg = await page.locator(sel.panel).evaluate(el =>
      getComputedStyle(el).backgroundColor
    );
    expect(bg).toBe('rgb(26, 26, 26)');
  });

  test('header background is dark on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const bg = await page.locator(sel.header).evaluate(el =>
      getComputedStyle(el).backgroundColor
    );
    expect(bg).toBe('rgb(26, 26, 26)');
  });

  test('back button is visible on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const display = await page.locator(sel.back).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(display).toBe('flex');
  });

  test('back button closes the panel', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.back).click();
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-open/);
  });

  test('pills have dark background on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const bg = await page.locator(sel.pill).first().evaluate(el =>
      getComputedStyle(el).backgroundColor
    );
    // rgb(42, 42, 42) = #2a2a2a
    expect(bg).toBe('rgb(42, 42, 42)');
  });

  test('FAB fades out and scales down when panel opens on mobile', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.fab)).toHaveClass(/ctxf-open/);
    const opacity = await page.locator(sel.fab).evaluate(el =>
      parseFloat(getComputedStyle(el).opacity)
    );
    expect(opacity).toBeLessThan(1);
  });
});
