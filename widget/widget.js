(function () {
  'use strict';

  // ── SVG assets ──────────────────────────────────────────────────────────────

  const LOGO_SVG = `<svg width="24" height="24" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <rect width="64" height="64" rx="12" fill="#000000"/>
    <text x="32" y="32" text-anchor="middle" dominant-baseline="central"
      font-family="'DM Sans',sans-serif" font-size="34" font-weight="700" fill="#ffffff">C</text>
  </svg>`;

  const LOGO_SVG_SMALL = `<svg width="18" height="18" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <rect width="64" height="64" rx="12" fill="#000000"/>
    <text x="32" y="32" text-anchor="middle" dominant-baseline="central"
      font-family="'DM Sans',sans-serif" font-size="34" font-weight="700" fill="#ffffff">C</text>
  </svg>`;

  const SEND_ICON = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M5.694 12 2.299 3.272c-.236-.607.356-1.188.942-.982l.093.04 18 9a.75.75 0 0 1 .097 1.283l-.097.058-18 9c-.619.31-1.263-.277-1.035-.916l.035-.084L5.694 12 2.3 3.272 5.694 12ZM4.402 4.54l2.61 6.71h6.627a.75.75 0 0 1 .102 1.493l-.102.007H7.01l-2.609 6.71L19.322 12 4.401 4.54Z"/>
  </svg>`;

  const CLOCK_ICON = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888888" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
  </svg>`;

  function detectContact(message) {
    const emailRe = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
    const phoneRe = /(\+?62|0)[0-9\s\-]{8,14}/;
    const waRe = /wa\.me\/|whatsapp/i;
    return emailRe.test(message) || phoneRe.test(message) || waRe.test(message);
  }

  // ── Widget ───────────────────────────────────────────────────────────────────

  function createWidget(config) {
    const cfg = Object.assign({
      root: document.getElementById('contextus-root') || document.body,
      name: 'contextus',
      greeting: 'Ask us anything...',
      lang: 'auto',
      transparent: false,
      dynamicHeight: false,
      pills: ['How can you help?', 'Pricing & plans', 'How do I embed this?'],
      apiUrl: '',           // e.g. 'https://api.contextus.ai'
      knowledgeBaseId: '',  // job_id from POST /api/crawl
    }, config);

    // ── State ────────────────────────────────────────────────────────────────

    const state = {
      phase: 'idle',      // idle | active | complete
      messages: [],       // { role: 'agent'|'visitor', text, isThinking, isError, isBoundary }
      contactCaptured: false,
      nudgeSent: false,
      pillsVisible: true,
      errorMessage: null,
      returningHistory: null, // messages from previous session (in-memory only)
      sessionId: null,        // assigned after POST /api/session

      // Timers
      idleTimer: null,
      completeTimer: null,
      softResetTimer: null,
    };

    // ── DOM ──────────────────────────────────────────────────────────────────

    const root = cfg.root;
    root.innerHTML = '';

    const widget = el('div', { id: 'contextus-widget' });
    root.appendChild(widget);

    // Header
    const header = el('div', { className: 'ctx-header' });
    header.innerHTML = LOGO_SVG_SMALL + `<span class="ctx-header-name">${esc(cfg.name)}</span><span class="ctx-header-powered">powered by contextus</span>`;
    widget.appendChild(header);

    // Messages
    const msgArea = el('div', { className: 'ctx-messages' });
    widget.appendChild(msgArea);

    // Input area
    const inputArea = el('div', { className: 'ctx-input-area' });
    const inputWrapper = el('div', { className: 'ctx-input-wrapper' });
    const input = el('input', { className: 'ctx-input', type: 'text', placeholder: cfg.greeting });
    const sendBtn = el('button', { className: 'ctx-send ctx-send-empty', type: 'button', 'aria-label': 'Send' });
    sendBtn.innerHTML = SEND_ICON;
    inputWrapper.appendChild(input);
    inputWrapper.appendChild(sendBtn);
    inputArea.appendChild(inputWrapper);

    const pillsContainer = el('div', { className: 'ctx-pills' });
    cfg.pills.forEach(label => {
      const pill = el('button', { className: 'ctx-pill', type: 'button' });
      pill.textContent = label;
      pill.addEventListener('click', () => sendMessage(label));
      pillsContainer.appendChild(pill);
    });
    inputArea.appendChild(pillsContainer);
    widget.appendChild(inputArea);

    // ── Render helpers ───────────────────────────────────────────────────────

    function renderMessages() {
      msgArea.innerHTML = '';

      // Returning visitor history
      if (state.returningHistory && state.returningHistory.length > 0) {
        const label = el('div', { className: 'ctx-returning-label' });
        label.innerHTML = CLOCK_ICON + ' Previous conversation';
        msgArea.appendChild(label);
        const histBlock = el('div', { className: 'ctx-returning-history' });
        state.returningHistory.forEach(m => histBlock.appendChild(renderMsg(m)));
        msgArea.appendChild(histBlock);
      }

      // Current messages
      let lastAgentEl = null;
      state.messages.forEach(m => {
        const el = renderMsg(m);
        msgArea.appendChild(el);
        if (m.role === 'agent' && !m.isThinking) lastAgentEl = el;
      });

      // Nudge
      if (state.nudgeSent && state.phase === 'active') {
        const nudge = el('div', { className: 'ctx-nudge' });
        nudge.textContent = 'Still there? No rush — I\'m here whenever you\'re ready.';
        msgArea.appendChild(nudge);
      }

      // Only scroll internally if content exceeds the visible messages area.
      // When content fits, leave scrollTop at 0 so everything is visible.
      if (msgArea.scrollHeight > msgArea.clientHeight) {
        msgArea.scrollTop = msgArea.scrollHeight;
      }

      notifyResize();
    }

    function renderMsg(m) {
      if (m.role === 'visitor') {
        const row = el('div', { className: 'ctx-msg ctx-msg-visitor' });
        const bubble = el('div', { className: 'ctx-bubble ctx-bubble-visitor' });
        bubble.textContent = m.text;
        row.appendChild(bubble);
        return row;
      }

      const row = el('div', { className: 'ctx-msg' });
      const avatar = el('div', { className: 'ctx-avatar' });
      avatar.innerHTML = LOGO_SVG;
      row.appendChild(avatar);

      const bubble = el('div', { className: 'ctx-bubble ctx-bubble-agent' });

      if (m.isThinking) {
        bubble.innerHTML = `<div class="ctx-dots"><span></span><span></span><span></span></div>`;
      } else if (m.isError) {
        const errBanner = el('div', { className: 'ctx-banner-error' });
        errBanner.textContent = m.text;
        msgArea.appendChild(errBanner);
        return document.createDocumentFragment(); // error shown as banner not bubble
      } else {
        bubble.textContent = m.text;
      }

      row.appendChild(bubble);

      // Boundary banner below bubble
      if (m.isBoundary) {
        const banner = el('div', { className: 'ctx-banner-boundary' });
        banner.innerHTML = `<strong>Connect with team:</strong> "Would you like to reach the contextus team directly? WhatsApp or email?"`;
        row.appendChild(banner);
      }

      return row;
    }

    function renderBanners() {
      // Remove old banners
      msgArea.querySelectorAll('.ctx-banner-error, .ctx-banner-complete').forEach(b => b.remove());

      if (state.errorMessage) {
        const errBanner = el('div', { className: 'ctx-banner-error' });
        errBanner.textContent = state.errorMessage;
        msgArea.appendChild(errBanner);
      }

      if (state.phase === 'complete') {
        const completeBanner = el('div', { className: 'ctx-banner-complete' });
        completeBanner.innerHTML = `Conversation ended — <span>lead brief sent</span>`;
        msgArea.appendChild(completeBanner);
      }

      if (msgArea.scrollHeight > msgArea.clientHeight) {
        msgArea.scrollTop = msgArea.scrollHeight;
      }
      notifyResize();
    }

    function updateInput() {

      const isThinking = state.messages.some(m => m.isThinking);
      const isComplete = state.phase === 'complete';
      const isDisabled = isThinking || isComplete;

      input.disabled = isDisabled;

      if (isComplete) {
        input.placeholder = 'Start a new conversation...';
      } else if (isThinking) {
        input.placeholder = 'Waiting for response...';
      } else if (state.phase === 'idle') {
        input.placeholder = cfg.greeting;
      } else {
        input.placeholder = state.errorMessage ? 'Try again...' : 'Type a message...';
      }

      updateSendBtn();

      // Pills
      pillsContainer.style.display = state.pillsVisible && state.phase === 'idle' ? 'flex' : 'none';
    }

    function updateSendBtn() {
      const isThinking = state.messages.some(m => m.isThinking);
      sendBtn.className = 'ctx-send';

      if (isThinking) {
        sendBtn.classList.add('ctx-send-disabled');
        sendBtn.disabled = true;
      } else if (input.value.trim().length > 0) {
        sendBtn.classList.add('ctx-send-active');
        sendBtn.disabled = false;
      } else {
        sendBtn.classList.add('ctx-send-empty');
        sendBtn.disabled = false;
      }
    }

    function render() {
      renderMessages();
      renderBanners();
      updateInput();
    }

    // ── Dynamic height ───────────────────────────────────────────────────────

    function notifyResize() {
      if (!cfg.dynamicHeight) return;
      const height = Math.ceil(widget.getBoundingClientRect().height);
      window.parent.postMessage({ type: 'contextus:resize', height }, '*');
    }

    if (cfg.dynamicHeight) {
      // Remove max-height cap so msgArea grows freely and the iframe expands to fit.
      // In fixed-height mode, max-height is needed for internal scroll; in dynamic mode it
      // creates artificial overflow that forces scrollTop to bottom on every render.
      msgArea.style.maxHeight = 'none';
      new ResizeObserver(() => notifyResize()).observe(widget);
    }

    // ── Send logic ───────────────────────────────────────────────────────────

    function sendMessage(text) {
      if (!text || !text.trim()) return;
      if (state.messages.some(m => m.isThinking)) return;
      if (state.phase === 'complete') return;

      clearTimers();
      state.errorMessage = null;
      state.pillsVisible = false;
      state.phase = 'active';

      // Prepend greeting on first message
      if (state.messages.length === 0) {
        state.messages.push({ role: 'agent', text: 'Hi! How can I help you today?' });
      }

      const visitorMsg = { role: 'visitor', text: text.trim() };
      state.messages.push(visitorMsg);

      if (detectContact(text)) {
        state.contactCaptured = true;
      }

      const thinkingMsg = { role: 'agent', isThinking: true };
      state.messages.push(thinkingMsg);

      input.value = '';
      render();

      // Real backend call with SSE streaming
      (async function callBackend() {
        // Lazily create a chat session on first message
        if (!state.sessionId) {
          try {
            const sr = await fetch(`${cfg.apiUrl}/api/session`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ knowledge_base_id: cfg.knowledgeBaseId }),
            });
            if (!sr.ok) throw new Error(`${sr.status}`);
            state.sessionId = (await sr.json()).session_id;
          } catch (err) {
            const tidx = state.messages.indexOf(thinkingMsg);
            if (tidx > -1) state.messages.splice(tidx, 1);
            state.errorMessage = 'Could not start session. Please try again.';
            render();
            return;
          }
        }

        // agentMsg is prepared but NOT added to state yet — thinkingMsg stays visible
        // until the first token arrives, keeping the dots throughout the entire wait.
        const agentMsg = { role: 'agent', text: '' };
        let streamBubble = null;
        let succeeded = false;

        for (let attempt = 0; attempt < 2; attempt++) {
          try {
            const res = await fetch(`${cfg.apiUrl}/api/chat/${state.sessionId}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message: text }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop(); // hold incomplete line
              for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let payload;
                try { payload = JSON.parse(line.slice(6)); } catch { continue; }
                if (payload.token) {
                  // First token: swap thinking dots → agent bubble
                  if (!streamBubble) {
                    const tidx = state.messages.indexOf(thinkingMsg);
                    if (tidx > -1) state.messages.splice(tidx, 1);
                    state.messages.push(agentMsg);
                    render();
                    const allBubbles = msgArea.querySelectorAll('.ctx-bubble-agent');
                    streamBubble = allBubbles[allBubbles.length - 1] || null;
                  }
                  agentMsg.text += payload.token;
                  if (streamBubble) {
                    streamBubble.textContent = agentMsg.text;
                    if (msgArea.scrollHeight > msgArea.clientHeight) {
                      msgArea.scrollTop = msgArea.scrollHeight;
                    }
                    notifyResize();
                  }
                }
              }
            }

            succeeded = true;
            state.errorMessage = null;
            break;
          } catch (err) {
            if (attempt === 0) {
              // Silent auto-retry after 2s — keep dots visible, reset partial text
              agentMsg.text = '';
              if (streamBubble) {
                // Re-show thinking dots if we already transitioned
                const aidx = state.messages.indexOf(agentMsg);
                if (aidx > -1) state.messages.splice(aidx, 1);
                state.messages.push(thinkingMsg);
                streamBubble = null;
                render();
              }
              await new Promise(r => setTimeout(r, 2000));
            }
          }
        }

        if (!succeeded) {
          // Clean up any partial state
          const aidx = state.messages.indexOf(agentMsg);
          if (aidx > -1) state.messages.splice(aidx, 1);
          const tidx = state.messages.indexOf(thinkingMsg);
          if (tidx > -1) state.messages.splice(tidx, 1);
          state.errorMessage = 'Something went wrong. Please try again.';
        }

        if (state.contactCaptured) {
          startCompleteTimer();
        } else {
          startIdleTimer();
        }

        render();
      })();
    }

    // ── Timers ───────────────────────────────────────────────────────────────

    function clearTimers() {
      clearTimeout(state.idleTimer);
      clearTimeout(state.completeTimer);
      clearTimeout(state.softResetTimer);
      state.idleTimer = null;
      state.completeTimer = null;
      state.softResetTimer = null;
    }

    function startIdleTimer() {
      clearTimeout(state.idleTimer);
      state.idleTimer = setTimeout(() => {
        if (!state.nudgeSent && state.phase === 'active') {
          state.nudgeSent = true;
          renderMessages();
          // 5 min after nudge — end conversation
          state.completeTimer = setTimeout(() => endConversation(), 5 * 60 * 1000);
        }
      }, 60 * 1000);
    }

    function startCompleteTimer() {
      clearTimeout(state.completeTimer);
      // 5 min idle after contact captured
      state.completeTimer = setTimeout(() => endConversation(), 5 * 60 * 1000);
    }

    function endConversation() {
      state.phase = 'complete';
      const signOff = { role: 'agent', text: "You're all set! The team has been notified and will follow up shortly. Have a great day." };
      state.messages.push(signOff);
      render();

      // Soft-reset placeholder after 30s
      state.softResetTimer = setTimeout(() => {
        input.placeholder = 'Start a new conversation...';
      }, 30 * 1000);
    }

    // ── Event listeners ──────────────────────────────────────────────────────

    input.addEventListener('input', () => updateSendBtn());

    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input.value);
      }
    });

    sendBtn.addEventListener('click', () => {
      if (!sendBtn.classList.contains('ctx-send-active')) return;
      sendMessage(input.value);
    });

    // ── Initial render ───────────────────────────────────────────────────────

    render();
  }

  // ── Utilities ────────────────────────────────────────────────────────────────

  function el(tag, attrs) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === 'className') node.className = v;
      else node.setAttribute(k, v);
    });
    return node;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Public API ───────────────────────────────────────────────────────────────

  window.ContextusWidget = { init: createWidget };

})();
