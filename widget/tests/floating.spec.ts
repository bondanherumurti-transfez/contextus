import { test, expect, type Page } from '@playwright/test';

const URL = '/widget/floating-demo.html';

// ── Shadow DOM helpers ─────────────────────────────────────────────────────────
// `pierce/` CSS engine pierces all shadow roots in the document.

// Playwright's CSS engine pierces open Shadow DOM by default —
// plain class selectors work without any special prefix.
const sel = {
  fab:        '.ctxf-fab',
  panel:      '.ctxf-panel',
  header:     '.ctxf-header',
  messages:   '.ctxf-messages',
  msgsInner:  '.ctxf-messages-inner',
  scrollBtn:  '.ctxf-scroll-btn',
  input:      '.ctxf-input',
  inputArea:  '.ctxf-input-area',
  send:       '.ctxf-send',
  close:      '.ctxf-close-btn',
  back:       '.ctxf-back-btn',
  badge:      '.ctxf-badge',
  pills:      '.ctxf-pills',
  pill:       '.ctxf-pill',
  dots:       '.ctxf-dots',
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
// ctxf-kbd is added when the user focuses the input on mobile.
// WhatsApp-style: header hides, but messages STAY VISIBLE. Messages + input
// push upward together with the keyboard. Input-area does NOT expand to fill
// the panel — it stays flex-shrink:0 at its natural height.
// ctxf-kbd must NOT be triggered by programmatic focus from the widget itself.

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

  test('header hides when ctxf-kbd is active', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    const display = await page.locator(sel.header).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(display).toBe('none');
  });

  test('messages stay visible while ctxf-kbd is active', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    const display = await page.locator(sel.messages).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(display).not.toBe('none');
  });

  test('input-area does not expand to fill panel during ctxf-kbd', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    const flexGrow = await page.locator(sel.inputArea).evaluate(el =>
      getComputedStyle(el).flexGrow
    );
    // Must be '0' — input-area stays at natural height, messages fill the rest
    expect(flexGrow).toBe('0');
  });

  test('ctxf-kbd is gone after agent responds (no refocus bug)', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Got it!');
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).focus();
    await expect(page.locator(sel.panel)).toHaveClass(/ctxf-kbd/);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    // Agent must NOT programmatically refocus input after responding
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Got it!');
    await expect(page.locator(sel.panel)).not.toHaveClass(/ctxf-kbd/);
    const headerDisplay = await page.locator(sel.header).evaluate(el =>
      getComputedStyle(el).display
    );
    expect(headerDisplay).not.toBe('none');
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

// ── Backend error handling ─────────────────────────────────────────────────────
//
// The floating widget renders errors as agent bubbles (no dedicated banner
// element) and re-enables the input so the user can retry.
// Session is fetched lazily on the first sendMessage() call when no
// state.sessionId is set — the demo page has no KB ID so the fetch always runs.

test.describe('Backend error handling', () => {
  test('session 500 → error agent bubble shown', async ({ page }) => {
    await page.route('**/api/session', route => route.fulfill({ status: 500 }));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry, something went wrong');
  });

  test('session 500 → thinking dots removed', async ({ page }) => {
    await page.route('**/api/session', route => route.fulfill({ status: 500 }));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry');
    await expect(page.locator(sel.dots)).not.toBeAttached();
  });

  test('session 500 → input re-enabled so user can retry', async ({ page }) => {
    await page.route('**/api/session', route => route.fulfill({ status: 500 }));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry');
    await expect(page.locator(sel.input)).toBeEnabled();
  });

  test('session network error (abort) → error agent bubble shown', async ({ page }) => {
    await page.route('**/api/session', route => route.abort('failed'));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry');
  });

  test('chat 500 (both attempts) → error agent bubble shown', async ({ page }) => {
    await page.clock.install();
    await mockSession(page);
    await page.route('**/api/chat/**', route => route.abort('failed'));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    // Skip the 2-second silent retry delay
    await page.clock.fastForward(2100);
    await expect(page.locator(sel.bubbleAgent).last()).toContainText("couldn't connect", { timeout: 5000 });
  });

  test('chat 500 → thinking dots removed after both attempts', async ({ page }) => {
    await page.clock.install();
    await mockSession(page);
    await page.route('**/api/chat/**', route => route.abort('failed'));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await page.clock.fastForward(2100);
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry', { timeout: 5000 });
    await expect(page.locator(sel.dots)).not.toBeAttached();
  });

  test('chat 500 → input re-enabled after both attempts', async ({ page }) => {
    await page.clock.install();
    await mockSession(page);
    await page.route('**/api/chat/**', route => route.abort('failed'));
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await page.clock.fastForward(2100);
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry', { timeout: 5000 });
    await expect(page.locator(sel.input)).toBeEnabled();
  });

  test('chat 500 → user can retry and succeed', async ({ page }) => {
    await page.clock.install();
    await mockSession(page);
    let chatCallCount = 0;
    await page.route('**/api/chat/**', route => {
      chatCallCount++;
      if (chatCallCount <= 2) {
        route.abort('failed');
      } else {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' },
          body: `data: ${JSON.stringify({ token: 'Recovery!' })}\n\n`,
        });
      }
    });
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('First try');
    await page.locator(sel.send).click();
    await page.clock.fastForward(2100);
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Sorry', { timeout: 5000 });

    // Retry — should succeed
    await page.locator(sel.input).fill('Retry');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Recovery!');
  });
});

// ── Messages: bottom-anchored layout ──────────────────────────────────────────
//
// Messages start from the bottom (WhatsApp / Google Chat style).
// .ctxf-messages is display:flex + flex-direction:column.
// .ctxf-messages-inner has margin-top:auto so a short conversation
// gravity-sticks to the bottom. Scroll stays pinned after each append.

test.describe('Messages: bottom-anchored layout', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('messages container is a flex column', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const flexDir = await page.evaluate(() => {
      const el = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-messages') as HTMLElement | null;
      return el ? getComputedStyle(el).flexDirection : null;
    });
    expect(flexDir).toBe('column');
  });

  test('inner wrapper exists as child of messages container', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const exists = await page.evaluate(() => {
      const root = document.querySelector('#ctxf-host')?.shadowRoot;
      return !!root?.querySelector('.ctxf-messages > .ctxf-messages-inner');
    });
    expect(exists).toBe(true);
  });

  test('greeting message is inside the inner wrapper (not directly in container)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const count = await page.evaluate(() => {
      const root = document.querySelector('#ctxf-host')?.shadowRoot;
      return root?.querySelector('.ctxf-messages-inner')?.querySelectorAll('.ctxf-msg').length ?? 0;
    });
    expect(count).toBeGreaterThan(0);
  });

  test('first message is anchored near the bottom (gap above inner wrapper)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    // With only the greeting, margin-top:auto should push the inner wrapper down
    const gap = await page.evaluate(() => {
      const root = document.querySelector('#ctxf-host')?.shadowRoot;
      const msgs  = root?.querySelector('.ctxf-messages')?.getBoundingClientRect();
      const inner = root?.querySelector('.ctxf-messages-inner')?.getBoundingClientRect();
      if (!msgs || !inner) return -1;
      return inner.top - msgs.top;
    });
    expect(gap).toBeGreaterThan(0);
  });

  test('scroll is pinned to bottom after a message is sent', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Response!');
    await page.goto(URL);
    await openWidget(page);
    await page.locator(sel.input).fill('Hello');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('Response!');
    const atBottom = await page.evaluate(() => {
      const el = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-messages') as HTMLElement | null;
      if (!el) return false;
      return Math.round(el.scrollHeight - el.scrollTop - el.clientHeight) < 5;
    });
    expect(atBottom).toBe(true);
  });
});

// ── Scroll-to-bottom button ────────────────────────────────────────────────────
//
// A small button (position:absolute, outside flex flow) appears when the user
// scrolls up to read history. It has zero layout impact when hidden — no gap
// between the last message and input area. Clicking it scrolls to bottom.
// Auto-scroll is suppressed while scrollPinned=false (user reading history).

/** Inject N overflow messages and scroll to the top to trigger the button. */
async function triggerScrollButton(page: Page, count = 20): Promise<void> {
  await page.evaluate((n: number) => {
    const root  = document.querySelector('#ctxf-host')?.shadowRoot;
    const inner = root?.querySelector('.ctxf-messages-inner');
    const msgs  = root?.querySelector('.ctxf-messages') as HTMLElement | null;
    for (let i = 0; i < n; i++) {
      const row    = document.createElement('div');
      row.className = 'ctxf-msg';
      const bubble = document.createElement('div');
      bubble.className = 'ctxf-bubble ctxf-bubble-agent';
      bubble.textContent = `Overflow message ${i}`;
      row.appendChild(bubble);
      inner?.appendChild(row);
    }
    if (msgs) msgs.scrollTop = 0;
    msgs?.dispatchEvent(new Event('scroll'));
  }, count);
  await page.waitForTimeout(100);
}

test.describe('Scroll-to-bottom button', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('scroll button exists in shadow DOM', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const exists = await page.evaluate(() =>
      !!document.querySelector('#ctxf-host')?.shadowRoot?.querySelector('.ctxf-scroll-btn')
    );
    expect(exists).toBe(true);
  });

  test('scroll button is hidden initially (no ctxf-visible class)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const hasVisible = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-scroll-btn')?.classList.contains('ctxf-visible') ?? false
    );
    expect(hasVisible).toBe(false);
  });

  test('scroll button has position:absolute (no layout impact when hidden)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    const pos = await page.evaluate(() => {
      const el = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-scroll-btn') as HTMLElement | null;
      return el ? getComputedStyle(el).position : null;
    });
    expect(pos).toBe('absolute');
  });

  test('scroll button is inside the messages wrap (not inside the scroll container)', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    // Button must be inside .ctxf-messages-wrap but NOT inside .ctxf-messages (scroll container)
    const [insideWrap, insideScrollContainer] = await page.evaluate(() => {
      const shadow = document.querySelector('#ctxf-host')?.shadowRoot;
      const wrap = shadow?.querySelector('.ctxf-messages-wrap');
      const msgs = shadow?.querySelector('.ctxf-messages');
      return [
        !!wrap?.querySelector('.ctxf-scroll-btn'),
        !!msgs?.querySelector('.ctxf-scroll-btn'),
      ];
    });
    expect(insideWrap).toBe(true);
    expect(insideScrollContainer).toBe(false);
  });

  test('scroll button appears when user scrolls up', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await triggerScrollButton(page);
    const isVisible = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-scroll-btn')?.classList.contains('ctxf-visible') ?? false
    );
    expect(isVisible).toBe(true);
  });

  test('clicking scroll button scrolls to bottom', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await triggerScrollButton(page);
    await page.locator(sel.scrollBtn).click();
    await page.waitForTimeout(100);
    const atBottom = await page.evaluate(() => {
      const msgs = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-messages') as HTMLElement | null;
      return msgs ? Math.round(msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight) < 5 : false;
    });
    expect(atBottom).toBe(true);
  });

  test('clicking scroll button hides the button', async ({ page }) => {
    await page.goto(URL);
    await openWidget(page);
    await triggerScrollButton(page);
    await page.locator(sel.scrollBtn).click();
    await page.waitForTimeout(100);
    const isVisible = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-scroll-btn')?.classList.contains('ctxf-visible') ?? true
    );
    expect(isVisible).toBe(false);
  });

  test('auto-scroll does not fire when user has scrolled up (scrollPinned=false)', async ({ page }) => {
    // Must use desktop viewport: on mobile the input focus handler always calls
    // scrollToBottom() (by design — keyboard appears, pin to latest). On desktop
    // the focus handler is a no-op for scrollPinned, so the flag stays false.
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockSession(page);
    await mockChat(page, 'New reply!');
    await page.goto(URL);
    await openWidget(page);
    // Overflow + scroll to top — sets scrollPinned=false internally
    await triggerScrollButton(page);
    // Send a message — agent responds, but scrollPinned=false so no auto-scroll
    await page.locator(sel.input).fill('Hi');
    await page.locator(sel.send).click();
    await expect(page.locator(sel.bubbleAgent).last()).toContainText('New reply!');
    // Container should NOT have jumped to the bottom
    const atBottom = await page.evaluate(() => {
      const msgs = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-messages') as HTMLElement | null;
      return msgs ? Math.round(msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight) < 5 : true;
    });
    expect(atBottom).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// data-appearance="bubbles"
// ══════════════════════════════════════════════════════════════════════════════

const BUBBLES_URL = '/widget/floating-bubbles-demo.html';

// Extend sel with bubbles-specific selectors
const bsel = {
  ...sel,
  fabBubbles: '.ctxf-fab-bubbles',
  fabBubble:  '.ctxf-fab-bubble',
};

/** Wait for fab bubbles to finish their staggered entrance by observing visible-state classes. */
async function waitForBubblesVisible(page: Page): Promise<void> {
  await expect(page.locator(`${bsel.fabBubble}.ctxf-bubble-visible`)).toHaveCount(3);
}

test.describe('appearance=bubbles — initial render', () => {
  test('renders .ctxf-fab-bubbles container in shadow DOM', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    const count = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelectorAll('.ctxf-fab-bubbles').length ?? 0
    );
    expect(count).toBe(1);
  });

  test('renders exactly 3 .ctxf-fab-bubble buttons', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    const count = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelectorAll('.ctxf-fab-bubble').length ?? 0
    );
    expect(count).toBe(3);
  });

  test('all bubble buttons have ctxf-bubble-visible class after entrance', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    const allVisible = await page.evaluate(() => {
      const btns = document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelectorAll('.ctxf-fab-bubble') ?? [];
      return Array.from(btns).every(b => b.classList.contains('ctxf-bubble-visible'));
    });
    expect(allVisible).toBe(true);
  });

  test('each bubble button has a non-empty data-msg attribute', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    const msgs = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).map(b => (b as HTMLElement).dataset.msg ?? '')
    );
    expect(msgs).toHaveLength(3);
    msgs.forEach(m => expect(m.length).toBeGreaterThan(0));
  });

  test('bubbles are positioned above the FAB (lower y value)', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    const fabBox     = await page.locator(bsel.fab).boundingBox();
    const bubblesBox = await page.locator(bsel.fabBubbles).boundingBox();
    expect(fabBox).not.toBeNull();
    expect(bubblesBox).not.toBeNull();
    // bubbles container bottom edge must sit above (smaller y) than FAB top edge
    expect(bubblesBox!.y + bubblesBox!.height).toBeLessThan(fabBox!.y);
  });

  test('default mode (no data-appearance) does NOT render .ctxf-fab-bubbles', async ({ page }) => {
    await page.goto(URL);
    await page.waitForTimeout(500);
    const count = await page.evaluate(() =>
      document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelectorAll('.ctxf-fab-bubbles').length ?? 0
    );
    expect(count).toBe(0);
  });
});

test.describe('appearance=bubbles — hide on panel open', () => {
  test('bubbles get ctxf-bubble-hiding class when FAB is clicked', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    await page.locator(bsel.fab).click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
    const anyHiding = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).some(b => b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(anyHiding).toBe(true);
  });

  test('bubbles hide when panel is opened via JS API', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);
    await page.evaluate(() => (window as any).contextus.open());
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
    const noneVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).every(b => !b.classList.contains('ctxf-bubble-visible') || b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(noneVisible).toBe(true);
  });
});

test.describe('appearance=bubbles — re-appear after close (no conversation)', () => {
  test('bubbles re-appear after panel is closed without sending a message', async ({ page }) => {
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    // Open and immediately close without sending
    await page.evaluate(() => (window as any).contextus.open());
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
    await page.evaluate(() => (window as any).contextus.close());
    await expect(page.locator(bsel.panel)).not.toHaveClass(/ctxf-open/);

    // Wait for re-entrance animation (300ms delay + stagger)
    await page.waitForTimeout(800);

    const allVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).every(b => b.classList.contains('ctxf-bubble-visible') && !b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(allVisible).toBe(true);
  });
});

test.describe('appearance=bubbles — bubble click opens panel and sends message', () => {
  test('clicking a bubble opens the panel', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Thanks for reaching out!');
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    await page.locator(bsel.fabBubble).first().click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
  });

  test('clicking a bubble auto-sends its text as a visitor message', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Thanks for reaching out!');
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    // Grab the pill text before clicking
    const pillText = await page.evaluate(() =>
      (document.querySelector('#ctxf-host')?.shadowRoot
        ?.querySelector('.ctxf-fab-bubble') as HTMLElement | null)
        ?.dataset.msg ?? ''
    );
    expect(pillText.length).toBeGreaterThan(0);

    await page.locator(bsel.fabBubble).first().click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);

    // Visitor bubble should contain the pill text
    await expect(page.locator(bsel.bubbleVisitor).first()).toContainText(pillText);
  });

  test('bubbles stay hidden after conversation starts (panel re-closed)', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Got it!');
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    // Click bubble → sends message → conversation started
    await page.locator(bsel.fabBubble).first().click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
    await expect(page.locator(bsel.bubbleVisitor).first()).toBeVisible();

    // Close the panel
    await page.evaluate(() => (window as any).contextus.close());
    await expect(page.locator(bsel.panel)).not.toHaveClass(/ctxf-open/);

    // Wait longer than the re-entrance delay
    await page.waitForTimeout(800);

    // Bubbles must NOT have re-appeared
    const anyVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).some(b => b.classList.contains('ctxf-bubble-visible') && !b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(anyVisible).toBe(false);
  });

  test('bubbles stay hidden after conversation started by typing (not bubble click)', async ({ page }) => {
    await mockSession(page);
    await mockChat(page, 'Got it!');
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    // Open via FAB click, type and send a message manually
    await page.locator(bsel.fab).click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);
    await page.locator(bsel.input).fill('Hello from typed input');
    await page.locator(bsel.send).click();
    await expect(page.locator(bsel.bubbleVisitor).first()).toBeVisible();

    // Close the panel
    await page.evaluate(() => (window as any).contextus.close());
    await expect(page.locator(bsel.panel)).not.toHaveClass(/ctxf-open/);

    // Wait longer than the re-entrance delay — bubbles must NOT re-appear
    await page.waitForTimeout(800);

    const anyVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).some(b => b.classList.contains('ctxf-bubble-visible') && !b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(anyVisible).toBe(false);
  });
});

test.describe('appearance=bubbles — session pill refresh', () => {
  test('bubbles update text when session returns custom pills', async ({ page }) => {
    const customPills = ['Custom pill one', 'Custom pill two', 'Custom pill three'];
    await mockSession(page, { session_id: 'test-bubbles', pills: customPills });
    await page.goto(BUBBLES_URL);

    // Wait for session fetch + re-render + entrance animation
    await page.waitForTimeout(1000);

    const msgs = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).map(b => (b as HTMLElement).dataset.msg ?? '')
    );
    expect(msgs).toEqual(customPills);
  });

  test('refreshed bubble buttons still have ctxf-bubble-visible after session update', async ({ page }) => {
    const customPills = ['Pill A', 'Pill B', 'Pill C'];
    await mockSession(page, { session_id: 'test-bubbles', pills: customPills });
    await page.goto(BUBBLES_URL);
    await page.waitForTimeout(1000);

    const allVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).every(b => b.classList.contains('ctxf-bubble-visible'))
    );
    expect(allVisible).toBe(true);
  });

  test('session pills do NOT update bubbles if conversation already started', async ({ page }) => {
    // Slow session so we can click a bubble before it resolves
    let resolveSession!: (value: unknown) => void;
    await page.route('**/api/session', async route => {
      await new Promise(r => { resolveSession = r; });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ session_id: 'late-session', pills: ['Late pill 1', 'Late pill 2', 'Late pill 3'] }),
      });
    });
    await mockChat(page, 'Hi!');
    await page.goto(BUBBLES_URL);
    await waitForBubblesVisible(page);

    // Click bubble before session resolves — starts conversation
    await page.locator(bsel.fabBubble).first().click();
    await expect(page.locator(bsel.panel)).toHaveClass(/ctxf-open/);

    // Now let the session resolve with new pills
    await page.evaluate(() => {}); // flush microtasks
    resolveSession(undefined);
    await page.waitForTimeout(400);

    // Bubbles should still be hidden (convoStarted=true), not re-rendered
    const anyVisible = await page.evaluate(() =>
      Array.from(
        document.querySelector('#ctxf-host')?.shadowRoot
          ?.querySelectorAll('.ctxf-fab-bubble') ?? []
      ).some(b => b.classList.contains('ctxf-bubble-visible') && !b.classList.contains('ctxf-bubble-hiding'))
    );
    expect(anyVisible).toBe(false);
  });
});
