// CairoFlow — clientside helpers. Auto-loaded by Dash from /assets/.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.cf = window.dash_clientside.cf || {};
Object.assign(window.dash_clientside.cf, {
  /**
   * pulseButton(resultData, btnId)
   * On every result-store update, briefly add `cf-btn-success-pulse`
   * to the button so its keyframe fires once. We force a reflow by
   * reading offsetWidth so re-applying the class actually replays
   * the animation (CSS won't replay a class that's already there).
   */
  pulseButton: function (resultData, btnId) {
    if (resultData == null) return null;
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.classList.remove('cf-btn-success-pulse');
      // Trigger reflow so the next add re-runs the animation.
      void btn.offsetWidth;
      btn.classList.add('cf-btn-success-pulse');
      setTimeout(function () {
        btn.classList.remove('cf-btn-success-pulse');
      }, 700);
    }
    return null;
  },

  /**
   * heroPing(_)
   * No-op clientside callback that simply ensures the message
   * listener has been wired exactly once. The actual work happens
   * in the listener installed below.
   */
  heroPing: function () {
    return window.dash_clientside.no_update;
  },

  /**
   * updateMapLibre(data)
   * Sends the live Dash state into the MapLibre iframe(s). The iframes
   * post `cairoflow-map-ready` back when their WebGL maps finish loading;
   * we track that and stop the retry-storm we used to do (4 posts per
   * iframe). Each ready iframe gets exactly one post, each unready
   * iframe gets a single deferred replay once it signals ready.
   */
  updateMapLibre: function (data) {
    if (!data) return null;
    data.ui_theme = window.__cairoFlowTheme || localStorage.getItem('cairoflow-theme') || 'dark';
    window.__cairoFlowLatestMapState = data;
    var root = document.getElementById('cf-root');
    if (root && data.time_of_day) {
      ['tod-morning', 'tod-afternoon', 'tod-evening', 'tod-night'].forEach(function (cls) {
        root.classList.remove(cls);
      });
      root.classList.add('tod-' + String(data.time_of_day).toLowerCase());
    }

    var ready = window.__cairoFlowMapReady || (window.__cairoFlowMapReady = {});

    function postToFrame(frameId, message) {
      var frame = document.getElementById(frameId);
      if (!frame || !frame.contentWindow) return;
      frame.contentWindow.postMessage(message, '*');
    }

    function postOnce(frameId, message) {
      // If the iframe is already ready, post immediately and skip the
      // retry-storm. If not ready yet, schedule two deferred attempts;
      // the install-once message listener below will also flush on
      // the ready handshake.
      if (ready[frameId]) {
        postToFrame(frameId, message);
        return;
      }
      postToFrame(frameId, message);
      setTimeout(function () { postToFrame(frameId, message); }, 350);
      setTimeout(function () { postToFrame(frameId, message); }, 1200);
    }

    postOnce('cairo-maplibre', {
      type: 'cairoflow-map-state',
      data: window.__cairoFlowLatestMapState
    });
    ['dijkstra', 'astar'].forEach(function (panel) {
      postOnce('race-map-' + panel, {
        type: 'cairoflow-race-panel-state',
        panel: panel,
        data: window.__cairoFlowLatestMapState
      });
    });
    return null;
  },
});

// === Iframe ready handshake ===============================================
// Each MapLibre iframe (main map + the two race-panel maps) posts
// `cairoflow-map-ready` when its WebGL map finishes loading. We remember
// which frames are ready so updateMapLibre can stop spamming retries.
// When a frame becomes ready we flush the latest state to it immediately.
(function installMapReadyHandshake() {
  if (window.__cairoFlowMapReadyInstalled) return;
  window.__cairoFlowMapReadyInstalled = true;
  window.__cairoFlowMapReady = window.__cairoFlowMapReady || {};
  window.addEventListener('message', function (event) {
    var msg = event && event.data;
    if (!msg || msg.type !== 'cairoflow-map-ready') return;
    var frameId = msg.panel ? 'race-map-' + msg.panel : 'cairo-maplibre';
    window.__cairoFlowMapReady[frameId] = true;
    var frame = document.getElementById(frameId);
    var state = window.__cairoFlowLatestMapState;
    if (!frame || !frame.contentWindow || !state) return;
    var message = msg.panel
      ? { type: 'cairoflow-race-panel-state', panel: msg.panel, data: state }
      : { type: 'cairoflow-map-state', data: state };
    frame.contentWindow.postMessage(message, '*');
  });
})();

// === CTOS Hero — postMessage bridge from the iframe ====================
// The hero iframe at /assets/hero.html sends messages of the form
//   { type: 'ctos-hero-dismiss', action: 'start' | 'explore' }
// when the user clicks Start Simulation / Explore Algorithms. We listen
// at the parent level and:
//   1. Add `.dismissed` to the iframe shell (CSS fade-out + scale).
//   2. After the transition, add `.removed` so WebGL is released.
  //   3. If action === 'explore', click the Trace Mode toggle to
//      jump straight into the technical view.
(function installHeroBridge() {
  if (window.__ctosHeroBridgeInstalled) return;
  window.__ctosHeroBridgeInstalled = true;

  function dismiss(action) {
    var shell = document.getElementById('cf-hero-shell');
    if (!shell) return;
    shell.classList.add('dismissed');
    // Match the faster shell transition before removing from layout so the
    // handoff feels like one deliberate move into the control map.
    setTimeout(function () {
      shell.classList.add('removed');
    }, 860);

    if (action === 'explore') {
      // Defer briefly so the dismiss animation reads cleanly, then
      // flip Trace Mode so the user lands directly in the
      // technical view they asked to explore.
      setTimeout(function () {
        var t = document.getElementById('programmer-mode-toggle');
        if (t) t.click();
      }, 420);
    }
  }

  window.addEventListener('message', function (ev) {
    var d = ev && ev.data;
    if (!d || d.type !== 'ctos-hero-dismiss') return;
    dismiss(d.action || 'start');
  });

  // Escape key also dismisses, so power users can skip the hero.
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var shell = document.getElementById('cf-hero-shell');
      if (shell && !shell.classList.contains('dismissed')) {
        dismiss('start');
      }
    }
  });
})();

// === Global appearance + logo preview =====================================
(function installAppearanceSystem() {
  if (window.__cairoFlowAppearanceInstalled) return;
  window.__cairoFlowAppearanceInstalled = true;

  function currentTheme() {
    return localStorage.getItem('cairoflow-theme') || 'dark';
  }

  function postTheme(theme) {
    var frame = document.getElementById('cairo-maplibre');
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ type: 'cairoflow-ui-theme', theme: theme }, '*');
    }
    var hero = document.getElementById('cf-hero-iframe');
    if (hero && hero.contentWindow) {
      hero.contentWindow.postMessage({ type: 'cairoflow-ui-theme', theme: theme }, '*');
    }
  }

  function applyTheme(theme) {
    var mode = theme === 'light' ? 'light' : 'dark';
    window.__cairoFlowTheme = mode;
    localStorage.setItem('cairoflow-theme', mode);
    document.documentElement.dataset.cfTheme = mode;
    document.body.dataset.cfTheme = mode;
    var root = document.getElementById('cf-root');
    if (root) {
      root.classList.toggle('cf-theme-light', mode === 'light');
      root.classList.toggle('cf-theme-dark', mode !== 'light');
    }
    var toggle = document.getElementById('cf-theme-toggle');
    if (toggle) {
      toggle.classList.toggle('is-light', mode === 'light');
      toggle.setAttribute('aria-label', 'Switch to ' + (mode === 'light' ? 'dark' : 'light') + ' appearance');
    }
    postTheme(mode);
    if (window.__cairoFlowLatestMapState && window.dash_clientside && window.dash_clientside.cf) {
      window.dash_clientside.cf.updateMapLibre(window.__cairoFlowLatestMapState);
    }
  }

  function showHero() {
    var shell = document.getElementById('cf-hero-shell');
    if (!shell) return;
    shell.classList.remove('removed');
    requestAnimationFrame(function () {
      shell.classList.remove('dismissed');
      postTheme(currentTheme());
    });
  }

  function openLogoPreview() {
    var modal = document.getElementById('cf-logo-preview');
    if (modal) modal.classList.add('open');
  }

  function closeLogoPreview() {
    var modal = document.getElementById('cf-logo-preview');
    if (modal) modal.classList.remove('open');
  }

  function wire() {
    applyTheme(currentTheme());

    var themeToggle = document.getElementById('cf-theme-toggle');
    if (themeToggle && !themeToggle.dataset.cfWired) {
      themeToggle.dataset.cfWired = '1';
      themeToggle.addEventListener('click', function () {
        applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
      });
    }

    var logo = document.getElementById('cf-logo-button');
    if (logo && !logo.dataset.cfWired) {
      logo.dataset.cfWired = '1';
      var timer = null;
      var clickTimer = null;
      var longPressed = false;
      function startPress() {
        longPressed = false;
        clearTimeout(timer);
        timer = setTimeout(function () {
          longPressed = true;
          openLogoPreview();
        }, 520);
      }
      function endPress(event) {
        clearTimeout(timer);
        if (longPressed) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        clearTimeout(clickTimer);
        clickTimer = setTimeout(showHero, 240);
      }
      logo.addEventListener('mousedown', startPress);
      logo.addEventListener('touchstart', startPress, { passive: true });
      logo.addEventListener('mouseup', endPress);
      logo.addEventListener('mouseleave', function () { clearTimeout(timer); });
      logo.addEventListener('touchend', endPress);
      logo.addEventListener('dblclick', function (event) {
        clearTimeout(timer);
        clearTimeout(clickTimer);
        event.preventDefault();
        event.stopPropagation();
        openLogoPreview();
      });
    }

    var close = document.getElementById('cf-logo-preview-close');
    if (close && !close.dataset.cfWired) {
      close.dataset.cfWired = '1';
      close.addEventListener('click', closeLogoPreview);
    }
    var modal = document.getElementById('cf-logo-preview');
    if (modal && !modal.dataset.cfWired) {
      modal.dataset.cfWired = '1';
      modal.addEventListener('click', function (event) {
        if (event.target === modal) closeLogoPreview();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', wire);
  setTimeout(wire, 300);
  setTimeout(wire, 1200);
  window.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeLogoPreview();
  });
})();

// === Sidebar collapse + live resize ========================================
(function installSidebarControls() {
  if (window.__cairoFlowSidebarControlsInstalled) return;
  window.__cairoFlowSidebarControlsInstalled = true;

  var WIDTH_KEY = 'cairoflow-sidebar-width';
  var COLLAPSED_KEY = 'cairoflow-sidebar-collapsed';
  var MIN_WIDTH = 292;
  var MAX_WIDTH = 520;
  var DEFAULT_WIDTH = 360;
  var COLLAPSED_WIDTH = 68;
  var dragging = false;
  var startX = 0;
  var startWidth = DEFAULT_WIDTH;

  function clampWidth(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return DEFAULT_WIDTH;
    return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.round(n)));
  }

  function savedWidth() {
    return clampWidth(localStorage.getItem(WIDTH_KEY) || DEFAULT_WIDTH);
  }

  function isCollapsed() {
    return localStorage.getItem(COLLAPSED_KEY) === '1';
  }

  function postMapResize() {
    var frame = document.getElementById('cairo-maplibre');
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ type: 'cairoflow-map-resize' }, '*');
    }
    window.dispatchEvent(new Event('resize'));
  }

  function notifyResize() {
    postMapResize();
    requestAnimationFrame(postMapResize);
    setTimeout(postMapResize, 180);
    setTimeout(postMapResize, 320);
  }

  function applyLayout() {
    var root = document.getElementById('cf-root');
    if (!root) return;
    var collapsed = isCollapsed();
    var width = collapsed ? COLLAPSED_WIDTH : savedWidth();
    root.style.setProperty('--cf-sidebar-width', width + 'px');
    root.classList.toggle('cf-sidebar-collapsed', collapsed);
    root.classList.toggle('cf-sidebar-expanded', !collapsed);

    var toggle = document.getElementById('cf-sidebar-toggle');
    if (toggle) {
      toggle.textContent = collapsed ? '>' : '<';
      toggle.setAttribute('aria-label', collapsed ? 'Expand controls sidebar' : 'Collapse controls sidebar');
      toggle.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
    notifyResize();
  }

  function toggleSidebar(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    localStorage.setItem(COLLAPSED_KEY, isCollapsed() ? '0' : '1');
    applyLayout();
  }

  function wireSidebarShell() {
    var root = document.getElementById('cf-root');
    var sidebar = document.querySelector('.cf-sidebar');
    if (!root || !sidebar) return;

    var existingToggle = document.getElementById('cf-sidebar-toggle');
    if (existingToggle && !existingToggle.dataset.cfSidebarToggleWired) {
      existingToggle.dataset.cfSidebarToggleWired = '1';
      existingToggle.addEventListener('click', toggleSidebar);
      existingToggle.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') toggleSidebar(event);
      });
    }

    if (!document.body.dataset.cfSidebarToggleDelegated) {
      document.body.dataset.cfSidebarToggleDelegated = '1';
      document.addEventListener('click', function (event) {
        var target = event.target && event.target.closest ? event.target.closest('#cf-sidebar-toggle') : null;
        if (!target) return;
        toggleSidebar(event);
      });
    }

    var handle = document.getElementById('cf-sidebar-resize-handle');
    if (handle && !handle.dataset.cfSidebarResizeWired) {
      handle.dataset.cfSidebarResizeWired = '1';
      handle.addEventListener('pointerdown', function (event) {
        event.preventDefault();
        dragging = true;
        startX = event.clientX;
        startWidth = savedWidth();
        localStorage.setItem(COLLAPSED_KEY, '0');
        document.body.classList.add('cf-sidebar-resizing');
        try { handle.setPointerCapture(event.pointerId); } catch (_) {}
        applyLayout();
      });

      window.addEventListener('pointermove', function (event) {
        if (!dragging) return;
        var next = clampWidth(startWidth + (event.clientX - startX));
        localStorage.setItem(WIDTH_KEY, String(next));
        localStorage.setItem(COLLAPSED_KEY, '0');
        applyLayout();
      });

      window.addEventListener('pointerup', function () {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove('cf-sidebar-resizing');
        applyLayout();
      });
    }

    applyLayout();
  }

  document.addEventListener('DOMContentLoaded', wireSidebarShell);
  setTimeout(wireSidebarShell, 250);
  setTimeout(wireSidebarShell, 1000);
  setTimeout(wireSidebarShell, 2200);
})();

// === Action feedback / duplicate-click guard ==============================
(function installActionFeedback() {
  if (window.__cairoFlowActionFeedbackInstalled) return;
  window.__cairoFlowActionFeedbackInstalled = true;
  var ids = [
    'route-find', 'mst-compute', 'em-dispatch', 'race-run', 'route-ml', 'race-replay',
    'maintain-optimize', 'transit-bus-optimize', 'transit-metro-optimize',
    'transit-mm-find', 'transit-trf-analyze', 'reset-what-if'
  ];

  function wire() {
    ids.forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn || btn.dataset.cfFeedbackWired) return;
      btn.dataset.cfFeedbackWired = '1';
      btn.addEventListener('click', function (event) {
        if (btn.dataset.cfBusy === '1') {
          event.preventDefault();
          event.stopImmediatePropagation();
          return;
        }
        btn.dataset.cfBusy = '1';
        btn.classList.add('cf-btn-loading');
        btn.setAttribute('aria-busy', 'true');
        setTimeout(function () {
          btn.dataset.cfBusy = '0';
          btn.classList.remove('cf-btn-loading');
          btn.removeAttribute('aria-busy');
        }, id === 'race-run' ? 1800 : 950);
      }, true);
    });
  }

  document.addEventListener('DOMContentLoaded', wire);
  setTimeout(wire, 400);
  setTimeout(wire, 1400);
})();
