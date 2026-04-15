(function () {
  'use strict';

  // ── Config from script tag ────────────────────────────────────────────────────

  var scriptEl = (function () {
    var scripts = document.querySelectorAll('script[src*="floating.js"]');
    return scripts[scripts.length - 1] || null;
  })();

  // Reads an attribute by name, falling back to a trimmed-name scan so that
  // stray leading/trailing spaces in the attribute name (common with copy-paste
  // into site builders or tag managers) don't silently drop the value.
  function attr(el, name) {
    if (!el) return null;
    var val = el.getAttribute(name);
    if (val !== null) return val;
    var attrs = el.attributes;
    for (var i = 0; i < attrs.length; i++) {
      if (attrs[i].name.trim() === name) return attrs[i].value;
    }
    return null;
  }

  var cfg = {
    id:              attr(scriptEl, 'data-contextus-id')      || '',
    position:        attr(scriptEl, 'data-position')           || 'bottom-right',
    offset:          parseInt(attr(scriptEl, 'data-offset') || '20', 10),
    greeting:        attr(scriptEl, 'data-greeting')           || 'Hi! 👋 How can I help you today?',
    badge:           attr(scriptEl, 'data-badge')              || '',
    color:           attr(scriptEl, 'data-color')              || '#000000',
    lang:            attr(scriptEl, 'data-lang')               || 'en',
    autoOpen:        attr(scriptEl, 'data-open') === 'true',
    name:            attr(scriptEl, 'data-name')               || 'contextus',
    apiUrl:          attr(scriptEl, 'data-api-url')            || 'https://contextus-2d16.onrender.com',
    knowledgeBaseId: attr(scriptEl, 'data-knowledge-base-id') || '',
    appearance:      attr(scriptEl, 'data-appearance')         || 'default',
  };

  // ── Analytics ─────────────────────────────────────────────────────────────────

  var CONTEXTUS_DOMAINS = ['getcontextus.dev', 'contextus-2d16.onrender.com', 'localhost'];

  function trackEvent(name) {
    if (!cfg.apiUrl || !cfg.knowledgeBaseId) return;
    var sourceDomain = window.location.hostname;
    var sourceType = CONTEXTUS_DOMAINS.some(function (d) { return sourceDomain.indexOf(d) !== -1; })
      ? 'contextus'
      : 'tenant';
    try {
      fetch(cfg.apiUrl + '/api/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          kb_id: cfg.knowledgeBaseId,
          session_id: state.sessionId || null,
          source_domain: sourceDomain,
          source_type: sourceType,
        }),
        keepalive: true,
      }).catch(function () {});
    } catch (_) {}
  }

  // ── Translations / content ────────────────────────────────────────────────────

  var PILLS = {
    en: ['What do you do?', 'Pricing', 'Get started'],
    id: ['Apa yang Anda lakukan?', 'Harga', 'Mulai sekarang'],
  };

  function getPills() {
    return PILLS[cfg.lang] || PILLS.en;
  }

  // ── State ─────────────────────────────────────────────────────────────────────

  var state = {
    open: false,
    phase: 'idle',   // idle | active | thinking
    pillsVisible: true,
    greeted: false,
    sessionId: null,
    savedScrollY: 0,
    fabBubblesConvoStarted: false, // once true, bubbles never re-appear
  };

  // ── Event emitter ─────────────────────────────────────────────────────────────

  var listeners = {};
  function emit(event, data) {
    (listeners[event] || []).forEach(function (fn) { fn(data); });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Inlined CSS ───────────────────────────────────────────────────────────────

  var CSS = [
    "@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=DM+Mono:wght@400;500&display=swap');",

    '*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}',

    // Shadow host — covers viewport, passes clicks through
    ':host{all:initial;display:block;position:fixed;inset:0;pointer-events:none;z-index:2147483640;-webkit-font-smoothing:antialiased;color-scheme:light}',
    '@media(max-width:479px){:host{z-index:2147483647}}',

    // ── FAB ──
    '.ctxf-fab{position:absolute;width:56px;height:56px;border-radius:16px;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.15);transition:transform .2s ease,box-shadow .2s ease;pointer-events:auto;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-fab:hover{transform:scale(1.05);box-shadow:0 6px 20px rgba(0,0,0,.2)}',
    '.ctxf-fab:active{transform:scale(.98)!important}',

    // FAB icon crossfade
    '.ctxf-fab svg{width:24px;height:24px;fill:#fff;transition:opacity .2s ease,transform .2s ease;position:absolute}',
    '.ctxf-icon-close{opacity:0;transform:rotate(-90deg)}',
    '.ctxf-fab.ctxf-open .ctxf-icon-chat{opacity:0;transform:rotate(90deg)}',
    '.ctxf-fab.ctxf-open .ctxf-icon-close{opacity:1;transform:rotate(0deg)}',

    // Notification badge
    '.ctxf-badge{position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;background:#e53935;border-radius:9px;border:2px solid #fff;font-size:10px;font-weight:600;color:#fff;display:flex;align-items:center;justify-content:center;padding:0 3px;pointer-events:none;font-family:"DM Sans",sans-serif;animation:ctxf-badge-pulse 2s ease-in-out infinite}',
    '.ctxf-badge.ctxf-hidden{display:none}',
    '@keyframes ctxf-badge-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}',

    // Pulse rings (hidden on desktop, shown on mobile via media query)
    '.ctxf-pulse-ring{display:none;position:absolute;inset:0;border-radius:16px;background:inherit;pointer-events:none}',
    '.ctxf-pulse-ring:nth-child(1){animation:ctxf-pulse-ring 2s ease-out infinite}',
    '.ctxf-pulse-ring:nth-child(2){animation:ctxf-pulse-ring 2s ease-out infinite 1s}',
    '@keyframes ctxf-pulse-ring{0%{transform:scale(1);opacity:.5}100%{transform:scale(1.6);opacity:0}}',

    // Back button (hidden on desktop, shown on mobile via media query)
    '.ctxf-back-btn{width:44px;height:44px;border:none;background:transparent;cursor:pointer;display:none;align-items:center;justify-content:center;border-radius:8px;flex-shrink:0;-webkit-tap-highlight-color:transparent;outline:none;margin-left:-6px}',
    '.ctxf-back-btn svg{width:20px;height:20px;fill:#fff}',

    // ── Panel ──
    '.ctxf-panel{position:absolute;width:380px;max-width:calc(100vw - 40px);max-height:min(600px,80vh);background:#fff;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.12),0 2px 8px rgba(0,0,0,.08);overflow:hidden;display:flex;flex-direction:column;opacity:0;transform:translateY(20px) scale(.95);transform-origin:bottom right;transition:opacity .25s ease,transform .25s ease;pointer-events:none}',
    '.ctxf-panel.ctxf-open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto}',
    '.ctxf-panel.ctxf-pos-bl{transform-origin:bottom left}',

    // Panel header
    '.ctxf-header{padding:14px 16px;background:#fff;border-bottom:.5px solid #e0e0e0;display:flex;align-items:center;gap:10px;flex-shrink:0}',
    '.ctxf-avatar{width:32px;height:32px;background:#000;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;color:#fff;flex-shrink:0;font-family:"DM Sans",sans-serif;line-height:1}',
    '.ctxf-header-info{flex:1;min-width:0}',
    '.ctxf-hname{font-size:14px;font-weight:500;color:#000;line-height:1.3;font-family:"DM Sans",sans-serif}',
    '.ctxf-hstatus{font-size:11px;color:#888;line-height:1.3;font-family:"DM Sans",sans-serif}',
    '.ctxf-close-btn{width:28px;height:28px;border:none;background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;border-radius:6px;transition:background .15s;flex-shrink:0;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-close-btn:hover{background:#f0f0f0}',
    '.ctxf-close-btn svg{width:16px;height:16px;fill:#888}',

    // Messages area — wrap provides the positioning context for the scroll button
    '.ctxf-messages-wrap{flex:1;position:relative;min-height:0;display:flex;flex-direction:column;overflow:hidden}',
    '.ctxf-messages{flex:1;overflow-y:auto;padding:16px;min-height:0;scrollbar-width:thin;scrollbar-color:#e0e0e0 transparent;overscroll-behavior:contain;display:flex;flex-direction:column}',
    '.ctxf-messages::-webkit-scrollbar{width:4px}',
    '.ctxf-messages::-webkit-scrollbar-thumb{background:#e0e0e0;border-radius:2px}',
    '.ctxf-messages-inner{display:flex;flex-direction:column;margin-top:auto;width:100%}',

    // Message rows
    '.ctxf-msg{display:flex;gap:8px;align-items:flex-start;margin-bottom:12px;animation:ctxf-msg-in .15s ease forwards}',
    '.ctxf-msg-visitor{justify-content:flex-end}',
    '@keyframes ctxf-msg-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}',
    '.ctxf-msg-avatar{width:24px;height:24px;background:#000;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0;font-family:"DM Sans",sans-serif;line-height:1}',
    '.ctxf-bubble{max-width:75%;font-size:13px;line-height:1.5;color:#222;font-family:"DM Sans",sans-serif}',
    '.ctxf-bubble-agent{padding:2px 0}',
    '.ctxf-bubble-visitor{background:#000;color:#fff;padding:10px 14px;border-radius:14px;border-bottom-right-radius:4px}',

    // Typing dots
    '.ctxf-dots{display:flex;gap:4px;padding:8px 0}',
    '.ctxf-dots span{width:6px;height:6px;background:#bbb;border-radius:50%;animation:ctxf-dot-bounce 1.2s infinite}',
    '.ctxf-dots span:nth-child(2){animation-delay:.15s}',
    '.ctxf-dots span:nth-child(3){animation-delay:.3s}',
    '@keyframes ctxf-dot-bounce{0%,60%,100%{opacity:.4;transform:scale(.85)}30%{opacity:1;transform:scale(1)}}',

    // Input area
    '.ctxf-input-area{padding:12px 16px 16px;border-top:.5px solid #e0e0e0;flex-shrink:0;background:#fff}',
    '.ctxf-input-wrap{display:flex;align-items:center;gap:10px;background:#f0f0f0;border:.5px solid #e0e0e0;border-radius:16px;padding:10px 10px 10px 16px}',
    '.ctxf-input{flex:1;border:none;background:transparent;font-size:16px;font-family:"DM Sans",sans-serif;color:#000;outline:none;min-width:0}',
    '.ctxf-input::placeholder{color:#bbb}',
    '.ctxf-send{width:34px;height:34px;border:none;background:#e0e0e0;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s,transform .15s;flex-shrink:0;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-send svg{width:16px;height:16px;fill:#999;transition:fill .15s}',
    '.ctxf-send.ctxf-active{background:#000}',
    '.ctxf-send.ctxf-active svg{fill:#fff}',
    '.ctxf-send.ctxf-active:hover{transform:scale(1.05)}',

    // Scroll-to-bottom button (absolute inside messages-wrap — no layout impact, always in messages zone)
    '.ctxf-scroll-btn{position:absolute;right:16px;bottom:10px;width:28px;height:28px;border-radius:50%;border:.5px solid #e0e0e0;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.12);cursor:pointer;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .2s ease;z-index:5;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-scroll-btn.ctxf-visible{opacity:1;pointer-events:auto}',
    '.ctxf-scroll-btn svg{width:16px;height:16px;fill:#888}',

    // ── FAB bubble pills (appearance="bubbles") ──
    '.ctxf-fab-bubbles{position:absolute;display:flex;flex-direction:column;align-items:flex-end;gap:8px;pointer-events:auto}',
    '.ctxf-fab-bubble{font-size:13px;color:#222;padding:12px 16px;background:#fff;border:.5px solid rgba(0,0,0,.06);border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.06);cursor:pointer;font-family:"DM Sans",sans-serif;text-align:left;line-height:1.4;max-width:260px;-webkit-tap-highlight-color:transparent;outline:none;opacity:0;transform:translateY(12px);transition:opacity .2s ease,transform .2s ease,box-shadow .15s ease}',
    '.ctxf-fab-bubble:focus-visible{outline:2px solid #2563eb;outline-offset:2px;box-shadow:0 0 0 3px rgba(37,99,235,.25),0 4px 20px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.06)}',
    '.ctxf-fab-bubble::before{content:"→";margin-right:7px;opacity:.4;font-size:12px}',
    '.ctxf-fab-bubble.ctxf-bubble-visible{opacity:1;transform:translateY(0)}',
    '.ctxf-fab-bubble:hover{box-shadow:0 8px 28px rgba(0,0,0,.16),0 2px 6px rgba(0,0,0,.08);transform:translateY(-2px) scale(1.02)}',
    '.ctxf-fab-bubble:active{transform:scale(.97)!important}',
    '.ctxf-fab-bubble.ctxf-bubble-hiding{opacity:0!important;transform:translateY(10px)!important;pointer-events:none}',
    '@keyframes ctxf-fab-bubbles-in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}',

    // Quick reply pills
    '.ctxf-pills{display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start;margin-top:10px}',
    '.ctxf-pill{font-size:11px;color:#666;padding:6px 12px;border:.5px solid #e0e0e0;border-radius:16px;background:#fff;cursor:pointer;transition:background .15s,border-color .15s;font-family:"DM Sans",sans-serif;-webkit-tap-highlight-color:transparent;outline:none;text-align:left}',
    '.ctxf-pill:hover{background:#f8f8f8;border-color:#ccc}',

    // Footer
    '.ctxf-footer{padding:8px 16px;background:#fafafa;border-top:.5px solid #e0e0e0;text-align:center;flex-shrink:0}',
    '.ctxf-powered{font-family:"DM Mono",monospace;font-size:10px;color:#bbb;letter-spacing:.3px}',
    '.ctxf-powered a{color:#888;text-decoration:none}',
    '.ctxf-powered a:hover{color:#000}',

    // ── Mobile: full-screen takeover (<480px) ──
    '@media(max-width:479px){',

      // Panel: slide up from bottom.
      // No bottom constraint — height is set by 100dvh (+ JS visualViewport override)
      // so the keyboard shrinks the panel instead of hiding under it.
      '.ctxf-panel{position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:auto!important;width:100%!important;max-width:100%!important;height:100dvh!important;max-height:none!important;border-radius:0!important;opacity:1!important;transform:translateY(100%)!important;transition:transform .3s ease-out!important;z-index:2147483647!important}',
      '.ctxf-panel.ctxf-open{transform:translateY(0)!important}',

      // FAB: scale down + fade out when panel opens
      '.ctxf-fab.ctxf-open{opacity:0;transform:scale(.8);pointer-events:none;transition:transform .2s ease,opacity .2s ease,box-shadow .2s ease}',

      // Pulse rings: show on mobile
      '.ctxf-pulse-ring{display:block}',

      // Back button: show on mobile
      '.ctxf-back-btn{display:flex}',

      // Dark header
      '.ctxf-header{background:#1a1a1a;border-bottom:1px solid #333;padding:44px 12px 12px}',
      '.ctxf-avatar{background:#333;border:1px solid #444}',
      '.ctxf-hname{color:#fff}',
      '.ctxf-hstatus{color:#888}',
      '.ctxf-close-btn svg{fill:#fff}',
      '.ctxf-close-btn:hover{background:#2a2a2a}',

      // Dark messages area
      '.ctxf-messages{background:#1a1a1a;scrollbar-color:#444 transparent}',
      '.ctxf-messages::-webkit-scrollbar-thumb{background:#444}',

      // Message avatar: dark
      '.ctxf-msg-avatar{background:#333;border:1px solid #444}',

      // Agent bubble: dark bg, white text, top-left corner
      '.ctxf-bubble-agent{background:#2a2a2a;color:#fff;padding:12px 14px;border-radius:16px;border-top-left-radius:4px}',

      // Visitor bubble: white bg, black text (inverted from desktop)
      '.ctxf-bubble-visitor{background:#fff;color:#000;border-bottom-right-radius:14px;border-top-right-radius:14px;border-top-left-radius:14px}',

      // Typing dots: lighter on dark bg
      '.ctxf-dots span{background:#666}',

      // Dark input area
      '.ctxf-input-area{background:#1a1a1a;border-top:1px solid #333;padding-bottom:max(16px,env(safe-area-inset-bottom,16px))}',
      '.ctxf-input-wrap{background:#2a2a2a;border:1px solid #333}',
      '.ctxf-input{color:#fff;font-size:16px}',
      '.ctxf-input::placeholder{color:#666}',
      '.ctxf-send{background:#333;width:36px;height:36px}',
      '.ctxf-send svg{fill:#666;width:18px;height:18px}',
      '.ctxf-send.ctxf-active{background:#fff}',
      '.ctxf-send.ctxf-active svg{fill:#000}',

      // Dark panel background (fixes overscroll/rubber-band white leak)
      '.ctxf-panel{background:#1a1a1a!important}',

      // Dark pills
      '.ctxf-pills{margin-top:12px}',
      '.ctxf-pill{background:#2a2a2a;color:#aaa;border:.5px solid #444}',
      '.ctxf-pill:hover{background:#333;border-color:#555;color:#fff}',

      // Dark footer
      '.ctxf-footer{background:#1a1a1a;border-top:1px solid #333}',
      '.ctxf-powered{color:#666}',
      '.ctxf-powered a{color:#888}',
      '.ctxf-powered a:hover{color:#fff}',

      // Scroll button: dark theme on mobile
      '.ctxf-scroll-btn{background:#2a2a2a;border-color:#444}',
      '.ctxf-scroll-btn svg{fill:#aaa}',

      // Keyboard-open state: header hides, messages shrink to fill remaining space,
      // input stays pinned at the bottom just above the keyboard.
      '.ctxf-panel.ctxf-kbd .ctxf-header{display:none}',
      '.ctxf-panel.ctxf-kbd .ctxf-input-area{flex-shrink:0;border-top:none}',

      // FAB bubble pills: white on dark background for contrast
      '.ctxf-fab-bubble{background:#fff;color:#222;border:.5px solid rgba(0,0,0,.06);box-shadow:0 4px 24px rgba(0,0,0,.45),0 1px 6px rgba(0,0,0,.25)}',
      '.ctxf-fab-bubble:hover{box-shadow:0 8px 32px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.3)}',
    '}',
  ].join('');

  // ── Init ──────────────────────────────────────────────────────────────────────

  function init() {
    var isLeft = cfg.position === 'bottom-left';
    var offset = cfg.offset;
    var panelBottom = offset + 56 + 14; // FAB height (56) + gap (14)

    // ── Shadow DOM host ──────────────────────────────────────────────────────────

    var host = document.createElement('div');
    host.id = 'ctxf-host';
    document.body.appendChild(host);

    var shadow = host.attachShadow({ mode: 'open' });

    var styleEl = document.createElement('style');
    styleEl.textContent = CSS;
    shadow.appendChild(styleEl);

    // ── FAB ──────────────────────────────────────────────────────────────────────

    var fabEl = document.createElement('button');
    fabEl.id = 'ctxf-fab';
    fabEl.className = 'ctxf-fab';
    fabEl.setAttribute('aria-label', 'Open chat');
    fabEl.style.background = cfg.color;
    fabEl.style[isLeft ? 'left' : 'right'] = offset + 'px';
    fabEl.style.bottom = offset + 'px';
    fabEl.innerHTML = [
      '<span class="ctxf-pulse-ring"></span>',
      '<span class="ctxf-pulse-ring"></span>',
      '<svg class="ctxf-icon-chat" viewBox="0 0 24 24"><path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2ZM20 16H6L4 18V4H20V16Z"/></svg>',
      '<svg class="ctxf-icon-close" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5L12 10.59L6.41 5L5 6.41L10.59 12L5 17.59L6.41 19L12 13.41L17.59 19L19 17.59L13.41 12L19 6.41Z"/></svg>',
      '<div id="ctxf-badge" class="ctxf-badge' + (cfg.badge ? '' : ' ctxf-hidden') + '">' + esc(cfg.badge || '1') + '</div>',
    ].join('');
    shadow.appendChild(fabEl);

    // ── Panel ─────────────────────────────────────────────────────────────────────

    var panelEl = document.createElement('div');
    panelEl.id = 'ctxf-panel';
    panelEl.className = 'ctxf-panel' + (isLeft ? ' ctxf-pos-bl' : '');
    panelEl.setAttribute('role', 'dialog');
    panelEl.setAttribute('aria-label', 'Chat with ' + cfg.name);
    panelEl.style[isLeft ? 'left' : 'right'] = offset + 'px';
    panelEl.style.bottom = panelBottom + 'px';

    var pillsHTML = getPills().map(function (p) {
      return '<button class="ctxf-pill" data-msg="' + esc(p) + '">' + esc(p) + '</button>';
    }).join('');

    panelEl.innerHTML = [
      '<div class="ctxf-header">',
        '<button class="ctxf-back-btn" id="ctxf-back" aria-label="Go back">',
          '<svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>',
        '</button>',
        '<div class="ctxf-avatar">C</div>',
        '<div class="ctxf-header-info">',
          '<div class="ctxf-hname">' + esc(cfg.name) + '</div>',
          '<div class="ctxf-hstatus">Powered by AI</div>',
        '</div>',
        '<button class="ctxf-close-btn" id="ctxf-close" aria-label="Close chat">',
          '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5L12 10.59L6.41 5L5 6.41L10.59 12L5 17.59L6.41 19L12 13.41L17.59 19L19 17.59L13.41 12L19 6.41Z"/></svg>',
        '</button>',
      '</div>',
      '<div class="ctxf-messages-wrap">',
        '<div class="ctxf-messages" id="ctxf-messages"><div class="ctxf-messages-inner" id="ctxf-messages-inner"></div></div>',
        '<button class="ctxf-scroll-btn" id="ctxf-scroll-btn" aria-label="Scroll to latest"><svg viewBox="0 0 24 24"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg></button>',
      '</div>',
      '<div class="ctxf-input-area">',
        '<div class="ctxf-input-wrap">',
          '<input class="ctxf-input" id="ctxf-input" type="text" placeholder="Type a message..." autocomplete="off">',
          '<button class="ctxf-send" id="ctxf-send" aria-label="Send">',
            '<svg viewBox="0 0 16 16"><path d="M2.5 8L13.5 2.5L10 8L13.5 13.5L2.5 8Z"/></svg>',
          '</button>',
        '</div>',
        '<div class="ctxf-pills" id="ctxf-pills">' + pillsHTML + '</div>',
      '</div>',
      '<div class="ctxf-footer">',
        '<div class="ctxf-powered">powered by <a href="https://getcontextus.dev" target="_blank">contextus</a></div>',
      '</div>',
    ].join('');
    shadow.appendChild(panelEl);

    // ── Element refs ──────────────────────────────────────────────────────────────

    var badgeEl      = shadow.getElementById('ctxf-badge');
    var closeBtn     = shadow.getElementById('ctxf-close');
    var backBtn      = shadow.getElementById('ctxf-back');
    var inputEl      = shadow.getElementById('ctxf-input');
    var sendBtn      = shadow.getElementById('ctxf-send');
    var messagesEl   = shadow.getElementById('ctxf-messages');
    var msgsInnerEl  = shadow.getElementById('ctxf-messages-inner');
    var scrollBtnEl  = shadow.getElementById('ctxf-scroll-btn');
    var pillsEl      = shadow.getElementById('ctxf-pills');

    // ── FAB bubble pills (appearance="bubbles") ───────────────────────────────────

    var fabBubblesEl = null;
    var showFabBubbles = function () {};
    var renderFabBubbles = function () {};

    if (cfg.appearance === 'bubbles') {
      fabBubblesEl = document.createElement('div');
      fabBubblesEl.className = 'ctxf-fab-bubbles';
      fabBubblesEl.style[isLeft ? 'left' : 'right'] = offset + 'px';
      fabBubblesEl.style.bottom = (offset + 56 + 14) + 'px'; // 56 = FAB height, 14 = gap

      renderFabBubbles = function (pills) {
        fabBubblesEl.innerHTML = (pills || getPills()).map(function (p) {
          return '<button class="ctxf-fab-bubble" data-msg="' + esc(p) + '">' + esc(p) + '</button>';
        }).join('');
      };

      showFabBubbles = function () {
        if (state.fabBubblesConvoStarted) return;
        fabBubblesEl.style.pointerEvents = 'auto'; // restore before re-entrance
        var btns = fabBubblesEl.querySelectorAll('.ctxf-fab-bubble');
        var i;
        for (i = 0; i < btns.length; i++) {
          btns[i].classList.remove('ctxf-bubble-visible', 'ctxf-bubble-hiding');
        }
        // Stagger bottom-first (pill[2] animates at 80ms, pill[0] last)
        for (i = 0; i < btns.length; i++) {
          (function (btn, reverseIndex) {
            setTimeout(function () { btn.classList.add('ctxf-bubble-visible'); }, 80 + reverseIndex * 110);
          })(btns[i], btns.length - 1 - i);
        }
      };

      renderFabBubbles();
      shadow.appendChild(fabBubblesEl);

      // Pill click — open panel and auto-send the tapped message
      fabBubblesEl.addEventListener('click', function (e) {
        var btn = e.target.closest('.ctxf-fab-bubble');
        if (!btn) return;
        var msg = btn.getAttribute('data-msg');
        if (!msg || !msg.trim()) return; // guard against empty data-msg
        state.fabBubblesConvoStarted = true;
        openPanel();
        setTimeout(function () { sendMessage(msg); }, 120);
      });

      // Staggered entrance on load
      setTimeout(showFabBubbles, 400);
    }

    // ── Scroll management ─────────────────────────────────────────────────────────

    var scrollPinned = true; // true = auto-scroll new messages to bottom

    function scrollToBottom() {
      messagesEl.scrollTop = messagesEl.scrollHeight;
      scrollPinned = true;
      scrollBtnEl.classList.remove('ctxf-visible');
    }

    messagesEl.addEventListener('scroll', function () {
      var nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 50;
      scrollPinned = nearBottom;
      if (nearBottom) {
        scrollBtnEl.classList.remove('ctxf-visible');
      } else {
        scrollBtnEl.classList.add('ctxf-visible');
      }
    });

    scrollBtnEl.addEventListener('click', scrollToBottom);

    // ── Open / close ──────────────────────────────────────────────────────────────

    function isMobile() {
      return window.innerWidth < 480;
    }

    function openPanel() {
      if (state.open) return;
      state.open = true;
      fabEl.classList.add('ctxf-open');
      panelEl.classList.add('ctxf-open');
      badgeEl.classList.add('ctxf-hidden');

      // Hide fab bubbles with exit animation; disable pointer events on container
      // so it doesn't intercept clicks on the panel (e.g. the send button).
      if (fabBubblesEl) {
        fabBubblesEl.style.pointerEvents = 'none';
        var fabBubbleButtons = fabBubblesEl.querySelectorAll('.ctxf-fab-bubble');
        for (var i = 0; i < fabBubbleButtons.length; i++) {
          fabBubbleButtons[i].classList.remove('ctxf-bubble-visible');
          fabBubbleButtons[i].classList.add('ctxf-bubble-hiding');
        }
      }

      // Lock body scroll on mobile — save scroll position first so page doesn't jump
      if (isMobile()) {
        state.savedScrollY = window.scrollY;
        document.body.style.overflow = 'hidden';
        document.body.style.position = 'fixed';
        document.body.style.top = '-' + state.savedScrollY + 'px';
        document.body.style.width = '100%';
        adjustPanel();
      }

      if (!state.greeted) {
        state.greeted = true;
        appendMessage({ role: 'agent', text: cfg.greeting });
      }

      // Only auto-focus on desktop — on mobile, programmatic focus would
      // immediately trigger the virtual keyboard and hide the panel header.
      if (!isMobile()) setTimeout(function () { inputEl.focus(); }, 300);
      trackEvent('fab_open');
      emit('open', null);
    }

    function closePanel() {
      if (!state.open) return;
      state.open = false;
      fabEl.classList.remove('ctxf-open');
      panelEl.classList.remove('ctxf-open');

      // Restore body scroll and scroll position
      if (isMobile()) {
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.top = '';
        document.body.style.width = '';
        window.scrollTo(0, state.savedScrollY || 0);
        panelEl.style.removeProperty('top');
        panelEl.style.removeProperty('height');
      }

      // Re-show fab bubbles if conversation hasn't started yet
      if (fabBubblesEl && !state.fabBubblesConvoStarted) {
        setTimeout(showFabBubbles, 300);
      }

      trackEvent('fab_close');
      emit('close', null);
    }

    // ── Messages ──────────────────────────────────────────────────────────────────

    function appendMessage(msg) {
      var row = document.createElement('div');
      row.className = 'ctxf-msg' + (msg.role === 'visitor' ? ' ctxf-msg-visitor' : '');

      if (msg.role === 'agent') {
        var av = document.createElement('div');
        av.className = 'ctxf-msg-avatar';
        av.textContent = 'C';
        row.appendChild(av);
      }

      var bubble = document.createElement('div');
      bubble.className = 'ctxf-bubble ' + (msg.role === 'agent' ? 'ctxf-bubble-agent' : 'ctxf-bubble-visitor');

      if (msg.isThinking) {
        bubble.innerHTML = '<div class="ctxf-dots"><span></span><span></span><span></span></div>';
        row.dataset.thinking = '1';
      } else {
        bubble.textContent = msg.text;
      }

      row.appendChild(bubble);
      msgsInnerEl.appendChild(row);
      if (scrollPinned) scrollToBottom();
      return row;
    }

    function removeThinking() {
      var el = msgsInnerEl.querySelector('[data-thinking]');
      if (el) el.remove();
    }

    // ── Send logic ────────────────────────────────────────────────────────────────

    function sendMessage(text) {
      text = text && text.trim();
      if (!text || state.phase === 'thinking') return;

      // Mark conversation started so bubbles stay hidden regardless of how the
      // first message was sent (bubble click, typed input, or in-panel pill).
      if (fabBubblesEl) state.fabBubblesConvoStarted = true;

      state.phase = 'active';
      state.pillsVisible = false;
      pillsEl.style.display = 'none';

      appendMessage({ role: 'visitor', text: text });
      inputEl.value = '';
      updateSend();
      emit('message', { role: 'visitor', text: text });

      // Show thinking
      state.phase = 'thinking';
      inputEl.disabled = true;
      appendMessage({ role: 'agent', isThinking: true });

      // Real backend call with SSE streaming
      (async function callBackend() {
        // Lazily create a session on the first message
        if (!state.sessionId) {
          try {
            var sr = await fetch(cfg.apiUrl + '/api/session', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ knowledge_base_id: cfg.knowledgeBaseId }),
            });
            if (!sr.ok) throw new Error(sr.status);
            state.sessionId = (await sr.json()).session_id;
          } catch (_) {
            removeThinking();
            appendMessage({ role: 'agent', text: 'Sorry, something went wrong. Please try again.' });
            state.phase = 'active';
            inputEl.disabled = false;
            return;
          }
        }

        var agentMsg   = { role: 'agent', text: '' };
        var streamRow  = null;
        var streamBubble = null;
        var succeeded  = false;

        for (var attempt = 0; attempt < 2; attempt++) {
          try {
            var res = await fetch(cfg.apiUrl + '/api/chat/' + state.sessionId, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message: text }),
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);

            var reader  = res.body.getReader();
            var decoder = new TextDecoder();
            var buf     = '';

            while (true) {
              var chunk = await reader.read();
              if (chunk.done) break;
              buf += decoder.decode(chunk.value, { stream: true });
              var lines = buf.split('\n');
              buf = lines.pop(); // hold incomplete line
              for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (!line.startsWith('data: ')) continue;
                var payload;
                try { payload = JSON.parse(line.slice(6)); } catch (e) { continue; }
                if (payload.token) {
                  // First token: swap thinking dots → streaming bubble
                  if (!streamBubble) {
                    removeThinking();
                    streamRow    = appendMessage(agentMsg);
                    streamBubble = streamRow.querySelector('.ctxf-bubble-agent');
                  }
                  agentMsg.text += payload.token;
                  if (streamBubble) {
                    streamBubble.textContent = agentMsg.text;
                    if (scrollPinned) scrollToBottom();
                  }
                }
              }
            }

            succeeded = true;
            emit('message', { role: 'agent', text: agentMsg.text });
            break;
          } catch (_) {
            if (attempt === 0) {
              // Silent retry after 2 s — reset partial state, keep dots visible
              agentMsg.text = '';
              if (streamRow) { streamRow.remove(); streamRow = null; streamBubble = null; }
              if (!msgsInnerEl.querySelector('[data-thinking]')) {
                appendMessage({ role: 'agent', isThinking: true });
              }
              await new Promise(function (r) { setTimeout(r, 2000); });
            }
          }
        }

        if (!succeeded) {
          removeThinking();
          if (streamRow) streamRow.remove();
          appendMessage({ role: 'agent', text: 'Sorry, I couldn\'t connect. Please try again.' });
        }

        state.phase = 'active';
        inputEl.disabled = false;
        // Only refocus on desktop — on mobile, programmatic focus re-adds
        // ctxf-kbd and hides header/messages even when keyboard is not open.
        if (!isMobile()) inputEl.focus();
      })();
    }

    // ── Input helpers ─────────────────────────────────────────────────────────────

    function updateSend() {
      if (inputEl.value.trim()) {
        sendBtn.classList.add('ctxf-active');
      } else {
        sendBtn.classList.remove('ctxf-active');
      }
    }

    inputEl.addEventListener('input', updateSend);

    // ── Mobile: keyboard open/close — input-area covers full panel ────────────────

    inputEl.addEventListener('focus', function () {
      if (isMobile()) {
        panelEl.classList.add('ctxf-kbd');
        // Keyboard is appearing — always scroll to latest so user can see context
        requestAnimationFrame(scrollToBottom);
      }
    });

    inputEl.addEventListener('blur', function () {
      panelEl.classList.remove('ctxf-kbd');
    });

    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (sendBtn.classList.contains('ctxf-active')) sendMessage(inputEl.value);
      }
    });

    sendBtn.addEventListener('click', function () {
      if (sendBtn.classList.contains('ctxf-active')) sendMessage(inputEl.value);
    });

    // ── FAB / close ───────────────────────────────────────────────────────────────

    var pageTouchMoved = false;
    var pageTouchMovedTime = 0;
    var pageTouchStartX = 0;
    var pageTouchStartY = 0;
    document.addEventListener('touchstart', function (e) {
      pageTouchMoved = false;
      pageTouchStartX = e.touches[0].clientX;
      pageTouchStartY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
      var dx = Math.abs(e.touches[0].clientX - pageTouchStartX);
      var dy = Math.abs(e.touches[0].clientY - pageTouchStartY);
      if (dx > 5 || dy > 5) {
        pageTouchMoved = true;
        pageTouchMovedTime = Date.now();
      }
    }, { passive: true });

    fabEl.addEventListener('click', function () {
      var now = Date.now();
      if (pageTouchMoved && now - pageTouchMovedTime < 300) return;
      if (state.open) closePanel(); else openPanel();
    });

    closeBtn.addEventListener('click', closePanel);
    backBtn.addEventListener('click', closePanel);

    // ── Pills ─────────────────────────────────────────────────────────────────────

    pillsEl.addEventListener('click', function (e) {
      var pill = e.target.closest('.ctxf-pill');
      if (pill) sendMessage(pill.dataset.msg);
    });

    // ── Mobile: visual viewport adjustment (keyboard show/hide) ──────────────────
    // Sets panel top + height to exactly the visible area so the input always
    // sits just above the keyboard and messages fill the remaining space.

    function adjustPanel() {
      if (!isMobile() || !state.open) return;
      var vv = window.visualViewport;
      if (vv) {
        panelEl.style.setProperty('top',    Math.round(vv.offsetTop) + 'px', 'important');
        panelEl.style.setProperty('height', Math.round(vv.height)    + 'px', 'important');
      } else {
        panelEl.style.setProperty('height', window.innerHeight + 'px', 'important');
      }
      // After panel resizes (keyboard show/hide), re-pin scroll to latest message
      requestAnimationFrame(scrollToBottom);
    }

    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', adjustPanel);
      window.visualViewport.addEventListener('scroll', adjustPanel);
    }

    // ── Eager session init — fetch name + pills + lang from backend ───────────────

    if (cfg.apiUrl && cfg.knowledgeBaseId) {
      (async function initSession() {
        try {
          var sr = await fetch(cfg.apiUrl + '/api/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ knowledge_base_id: cfg.knowledgeBaseId }),
          });
          if (!sr.ok) return;
          var data = await sr.json();

          // Store session so sendMessage skips the lazy fetch
          state.sessionId = data.session_id;

          // Update brand name in header
          if (data.name) {
            cfg.name = data.name;
            var hnameEl = shadow.querySelector('.ctxf-hname');
            if (hnameEl) hnameEl.textContent = data.name;
          }

          // Update language
          if (data.language) cfg.lang = data.language;

          // Replace pills with KB-specific ones (only if user hasn't sent a message yet)
          if (data.pills && data.pills.length && state.pillsVisible) {
            pillsEl.innerHTML = data.pills.map(function (p) {
              return '<button class="ctxf-pill" data-msg="' + esc(p) + '">' + esc(p) + '</button>';
            }).join('');
          }

          // Also refresh fab bubble pills if still visible
          if (fabBubblesEl && data.pills && data.pills.length && !state.fabBubblesConvoStarted) {
            renderFabBubbles(data.pills);
            showFabBubbles();
          }
        } catch (_) { /* fall through — sendMessage will create session lazily */ }
      })();
    }

    // ── Auto-open ─────────────────────────────────────────────────────────────────

    if (cfg.autoOpen) openPanel();

    // ── window.contextus public API ───────────────────────────────────────────────

    window.contextus = {
      open:   openPanel,
      close:  closePanel,
      toggle: function () { if (state.open) closePanel(); else openPanel(); },
      setBadge: function (val) {
        badgeEl.textContent = val;
        badgeEl.classList.remove('ctxf-hidden');
      },
      clearBadge: function () {
        badgeEl.classList.add('ctxf-hidden');
      },
      on: function (event, fn) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(fn);
      },
      off: function (event, fn) {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter(function (f) { return f !== fn; });
      },
    };
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
