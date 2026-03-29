(function () {
  'use strict';

  var WIDGET_BASE = (function () {
    var scripts = document.querySelectorAll('script[src*="embed.js"]');
    if (scripts.length) {
      return scripts[scripts.length - 1].src.replace(/embed\.js.*$/, '');
    }
    return '';
  })();

  function loadStyles(shadowRoot) {
    var style = document.createElement('link');
    style.rel = 'stylesheet';
    style.href = WIDGET_BASE + 'widget.css';
    shadowRoot.appendChild(style);

    // Reset to prevent host page styles bleeding in
    var reset = document.createElement('style');
    reset.textContent = ':host { all: initial; display: block; color-scheme: light; }';
    shadowRoot.appendChild(reset);
  }

  function loadScript(callback) {
    if (window.ContextusWidget) {
      callback();
      return;
    }
    var script = document.createElement('script');
    script.src = WIDGET_BASE + 'widget.js';
    script.onload = callback;
    document.head.appendChild(script);
  }

  function initElement(el) {
    if (el.dataset.contextusInit) return;
    el.dataset.contextusInit = '1';

    var shadow = el.attachShadow({ mode: 'open' });
    loadStyles(shadow);

    var root = document.createElement('div');
    root.id = 'contextus-root';
    shadow.appendChild(root);

    loadScript(function () {
      ContextusWidget.init({
        root: root,
        name: el.dataset.name || 'contextus',
        greeting: el.dataset.greeting || 'Ask us anything...',
        lang: el.dataset.lang || 'auto',
        dynamicHeight: false, // inline embed handles its own height
      });
    });
  }

  function scanAndInit() {
    document.querySelectorAll('[data-contextus]').forEach(initElement);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scanAndInit);
  } else {
    scanAndInit();
  }
})();
