(function () {
  'use strict';

  // ── Config from script tag ────────────────────────────────────────────────────

  var scriptEl = (function () {
    var scripts = document.querySelectorAll('script[src*="floating.js"]');
    return scripts[scripts.length - 1] || null;
  })();

  var cfg = {
    id:       scriptEl && scriptEl.getAttribute('data-contextus-id')  || '',
    position: scriptEl && scriptEl.getAttribute('data-position')       || 'bottom-right',
    offset:   parseInt(scriptEl && scriptEl.getAttribute('data-offset') || '20', 10),
    greeting: scriptEl && scriptEl.getAttribute('data-greeting')       || 'Hi! 👋 How can I help you today?',
    badge:    scriptEl && scriptEl.getAttribute('data-badge')          || '',
    color:    scriptEl && scriptEl.getAttribute('data-color')          || '#000000',
    lang:     scriptEl && scriptEl.getAttribute('data-lang')           || 'en',
    autoOpen: scriptEl && scriptEl.getAttribute('data-open') === 'true',
    name:     scriptEl && scriptEl.getAttribute('data-name')           || 'contextus',
  };

  // ── Translations / content ────────────────────────────────────────────────────

  var PILLS = {
    en: ['What do you do?', 'Pricing', 'Get started'],
    id: ['Apa yang Anda lakukan?', 'Harga', 'Mulai sekarang'],
  };

  var MOCK_RESPONSES = [
    "Thanks for reaching out! I'd be happy to help you with that.",
    "Great question! contextus is an AI-powered chat widget that captures leads and answers questions automatically.",
    "We offer flexible pricing plans. Would you like to know more details?",
    "I can definitely help with that. Could you tell me a bit more about your use case?",
    "Of course! Let me explain how contextus works for your business needs.",
  ];

  var mockIndex = 0;
  function getMockResponse() {
    return MOCK_RESPONSES[mockIndex++ % MOCK_RESPONSES.length];
  }

  function getPills() {
    return PILLS[cfg.lang] || PILLS.en;
  }

  // ── State ─────────────────────────────────────────────────────────────────────

  var state = {
    open: false,
    phase: 'idle',   // idle | active | thinking
    pillsVisible: true,
    greeted: false,
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

    // Messages area
    '.ctxf-messages{flex:1;overflow-y:auto;padding:16px;min-height:0;scrollbar-width:thin;scrollbar-color:#e0e0e0 transparent}',
    '.ctxf-messages::-webkit-scrollbar{width:4px}',
    '.ctxf-messages::-webkit-scrollbar-thumb{background:#e0e0e0;border-radius:2px}',

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
    '.ctxf-input{flex:1;border:none;background:transparent;font-size:14px;font-family:"DM Sans",sans-serif;color:#000;outline:none;min-width:0}',
    '.ctxf-input::placeholder{color:#bbb}',
    '.ctxf-send{width:34px;height:34px;border:none;background:#e0e0e0;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s,transform .15s;flex-shrink:0;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-send svg{width:16px;height:16px;fill:#999;transition:fill .15s}',
    '.ctxf-send.ctxf-active{background:#000}',
    '.ctxf-send.ctxf-active svg{fill:#fff}',
    '.ctxf-send.ctxf-active:hover{transform:scale(1.05)}',

    // Quick reply pills
    '.ctxf-pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}',
    '.ctxf-pill{font-size:11px;color:#666;padding:6px 12px;border:.5px solid #e0e0e0;border-radius:16px;background:#fff;cursor:pointer;transition:background .15s,border-color .15s;font-family:"DM Sans",sans-serif;-webkit-tap-highlight-color:transparent;outline:none}',
    '.ctxf-pill:hover{background:#f8f8f8;border-color:#ccc}',

    // Footer
    '.ctxf-footer{padding:8px 16px;background:#fafafa;border-top:.5px solid #e0e0e0;text-align:center;flex-shrink:0}',
    '.ctxf-powered{font-family:"DM Mono",monospace;font-size:10px;color:#bbb;letter-spacing:.3px}',
    '.ctxf-powered a{color:#888;text-decoration:none}',
    '.ctxf-powered a:hover{color:#000}',

    // ── Mobile: full-screen takeover (<480px) ──
    '@media(max-width:479px){',
      '.ctxf-panel{inset:0;width:100%;max-width:100%;max-height:100%;border-radius:0;transform-origin:bottom center;padding-bottom:env(safe-area-inset-bottom,0px)}',
      '.ctxf-fab.ctxf-open{opacity:0;pointer-events:none;transition:transform .2s ease,box-shadow .2s ease,opacity .2s ease}',
      '.ctxf-input-area{padding-bottom:max(16px,env(safe-area-inset-bottom,16px))}',
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
        '<div class="ctxf-avatar">C</div>',
        '<div class="ctxf-header-info">',
          '<div class="ctxf-hname">' + esc(cfg.name) + '</div>',
          '<div class="ctxf-hstatus">Powered by AI</div>',
        '</div>',
        '<button class="ctxf-close-btn" id="ctxf-close" aria-label="Close chat">',
          '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5L12 10.59L6.41 5L5 6.41L10.59 12L5 17.59L6.41 19L12 13.41L17.59 19L19 17.59L13.41 12L19 6.41Z"/></svg>',
        '</button>',
      '</div>',
      '<div class="ctxf-messages" id="ctxf-messages"></div>',
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

    var badgeEl   = shadow.getElementById('ctxf-badge');
    var closeBtn  = shadow.getElementById('ctxf-close');
    var inputEl   = shadow.getElementById('ctxf-input');
    var sendBtn   = shadow.getElementById('ctxf-send');
    var messagesEl= shadow.getElementById('ctxf-messages');
    var pillsEl   = shadow.getElementById('ctxf-pills');

    // ── Open / close ──────────────────────────────────────────────────────────────

    function openPanel() {
      if (state.open) return;
      state.open = true;
      fabEl.classList.add('ctxf-open');
      panelEl.classList.add('ctxf-open');
      badgeEl.classList.add('ctxf-hidden');

      if (!state.greeted) {
        state.greeted = true;
        appendMessage({ role: 'agent', text: cfg.greeting });
      }

      setTimeout(function () { inputEl.focus(); }, 300);
      emit('open', null);
    }

    function closePanel() {
      if (!state.open) return;
      state.open = false;
      fabEl.classList.remove('ctxf-open');
      panelEl.classList.remove('ctxf-open');
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
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return row;
    }

    function removeThinking() {
      var el = messagesEl.querySelector('[data-thinking]');
      if (el) el.remove();
    }

    // ── Send logic ────────────────────────────────────────────────────────────────

    function sendMessage(text) {
      text = text && text.trim();
      if (!text || state.phase === 'thinking') return;

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

      // Mock response
      var delay = 800 + Math.random() * 1200;
      setTimeout(function () {
        removeThinking();
        var response = getMockResponse();
        appendMessage({ role: 'agent', text: response });
        state.phase = 'active';
        inputEl.disabled = false;
        inputEl.focus();
        emit('message', { role: 'agent', text: response });
      }, delay);
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

    fabEl.addEventListener('click', function () {
      if (state.open) closePanel(); else openPanel();
    });

    closeBtn.addEventListener('click', closePanel);

    // ── Pills ─────────────────────────────────────────────────────────────────────

    pillsEl.addEventListener('click', function (e) {
      var pill = e.target.closest('.ctxf-pill');
      if (pill) sendMessage(pill.dataset.msg);
    });

    // ── Mobile: virtual keyboard adjustment ───────────────────────────────────────

    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', function () {
        if (window.innerWidth < 480 && state.open) {
          panelEl.style.height = window.visualViewport.height + 'px';
        } else {
          panelEl.style.height = '';
        }
      });
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
