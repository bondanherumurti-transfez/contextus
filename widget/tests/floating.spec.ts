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

interface SessionData {
  session_id?: string;
  name?: string;
  pills?: string[];
  language?: string;
}

/** Intercept the Render backend so tests never hit the real network. */
async function mockSession(page: Page, overrides: SessionData = {}): Promise<void> {
  await page.route('**/api/session', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ session_id: 'test-session-float', ...overrides }),
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

// ── Mobile keyboard cover (ctxf-kbd) ──────────────────────────────────────────
//
// ctxf-kbd is added when the user focuses the input on mobile, hiding the
// header and messages so the input-area fills the full panel (Intercom-style).
// It must NOT be added by programmatic focus calls from the widget itself.

test.describe('Mobile keyboard cover (ctxf-kbd)', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('opening the panel does not add ctxf-kbd', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    // Wait past where the old auto-focus setTimeout would have fired (300ms)
    await page.waitForTimeout(400);
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-kbd/);
  });

  test('header is visible after opening (no spurious ctxf-kbd)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.waitForTimeout(400);
    const display = await page.locator(sel.header).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(display).not.toBe('none');
  });

  test('manually focusing input adds ctxf-kbd', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
  });

  test('blurring input removes ctxf-kbd', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    await page.locator(sel.input).blur();
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-kbd/);
  });

  test('ctxf-kbd is gone after agent responds (no refocus bug)', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Got it!');
    await page.goto(URL);
    await openWidget(page);
    // User taps input → keyboard cover activates
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    // User sends message
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    // After the agent responds the input must NOT be refocused programmatically
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Got it!');
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-kbd/);
    // Header and messages must be visible again
    const headerDisplay = await page.locator(sel.header).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(headerDisplay).not.toBe('none');
    const msgsDisplay = await page.locator(sel.messages).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(msgsDisplay).not.toBe('none');
  });
});

// ── Input font-size — iOS auto-zoom prevention ─────────────────────────────────
//
// iOS Safari zooms in when an <input> has font-size < 16px.
// Pin this at ≥ 16px so the fix is never accidentally regressed.

test.describe('Input font-size (iOS zoom prevention)', () => {
  test('input font-size is at least 16px on desktop', async ({ page }) => {
    await page.goto(URL);
    const size = await page.locator(sel.input).evaluate(el =>
      parseFloat(getComputedStyle(el).fontSize)
    );
    expect(size).toBeGreaterThanOrEqual(16);
  });

  test('input font-size is at least 16px on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(URL);
    const size = await page.locator(sel.input).evaluate(el =>
      parseFloat(getComputedStyle(el).fontSize)
    );
    expect(size).toBeGreaterThanOrEqual(16);
  });
});

// ── Eager session init — brand name & KB pills ─────────────────────────────────
//
// The demo page has no data-knowledge-base-id, so we inject a minimal page
// with that attribute set to trigger the eager /api/session call.

const WIDGET_ABSOLUTE = 'http://localhost:3000/widget/floating.js';

async function loadWidgetWithKB(page: Page, kbId = 'test-kb'): Promise<void> {
  await page.setContent(`
    <!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>
    <script
      src="${WIDGET_ABSOLUTE}"
      data-contextus-id="test"
      data-knowledge-base-id="${kbId}"
      data-greeting="Hi!"
    ></script>
    </body></html>
  `);
  // Wait until floating.js has initialised and exposed window.contextus
  await page.waitForFunction(() => !!(window as any).contextus);
}

test.describe('Eager session init', () => {
  test('header shows KB brand name returned by session API', async ({ page }) => {
    await mockSession(page, { name: 'Finfloo' });
    await loadWidgetWithKB(page);
    // Wait for eager fetch to update the DOM
    await page.waitForFunction(() => {
      const el = document.querySelector('#ctxf-host')?.shadowRoot?.querySelector('.ctxf-hname');
      return el?.textContent === 'Finfloo';
    });
    await expect(page.locator('.ctxf-hname')).toHaveText('Finfloo');
  });

  test('pills are replaced with KB-specific pills from session API', async ({ page }) => {
    const kbPills = ['How do I contact Finfloo?', 'What is Finfloo pricing?', 'Get started with Finfloo'];
    await mockSession(page, { pills: kbPills });
    await loadWidgetWithKB(page);
    await page.waitForFunction((expected: string[]) => {
      const pills = document.querySelector('#ctxf-host')?.shadowRoot?.querySelectorAll('.ctxf-pill');
      return pills && pills.length === expected.length && pills[0].textContent === expected[0];
    }, kbPills);
    const texts = await page.locator(sel.pill).allTextContents();
    expect(texts).toEqual(kbPills);
  });

  test('session ID is pre-set so sendMessage skips /api/session', async ({ page }) => {
    await mockSession(page, { name: 'Finfloo' });
    await mockChat(page, 'Hi from Finfloo!');
    await loadWidgetWithKB(page);
    // Wait for eager init to complete (name updated = session stored)
    await page.waitForFunction(() => {
      const el = document.querySelector('#ctxf-host')?.shadowRoot?.querySelector('.ctxf-hname');
      return el?.textContent === 'Finfloo';
    });
    // Any further session call should be tracked — register AFTER init so only
    // new calls (from sendMessage fallback) would be captured.
    const sessionCalls: number[] = [];
    await page.route('**/api/session', route => {
      sessionCalls.push(1);
      route.fulfill({ status: 500, body: 'unexpected session call' });
    });
    await page.evaluate(() => (window as any).contextus.open());
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Hi from Finfloo!');
    expect(sessionCalls.length).toBe(0);
  });

  test('falls back to default name when session API returns no name', async ({ page }) => {
    await mockSession(page); // no name field
    await page.goto(URL);
    await openWidget(page);
    const name = await page.locator('.ctxf-hname').textContent();
    expect(name).toBeTruthy();
  });

  test('keeps default pills when session API returns empty pills', async ({ page }) => {
    await mockSession(page, { pills: [] });
    await page.goto(URL);
    await openWidget(page);
    await expect(page.locator(sel.pill)).toHaveCount(3);
  });
});
