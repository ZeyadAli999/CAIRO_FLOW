// CairoFlow BONUS — Dijkstra vs A* race animator (clientside).
// Auto-loaded by Dash from /assets/. The server's `_race_compute`
// callback writes a frames-bundle into the `race-data` Store; this
// file picks it up via the clientside callback at the bottom of the
// file, then animates two side-by-side <canvas> elements in lockstep.
(function () {
  const NS = window.dash_clientside = window.dash_clientside || {};
  NS.cf = NS.cf || {};

  // -- Project node coordinates (lat/lon). Same data the hero uses. --
  const NODE_POS = {
    '1':  [29.96, 31.25], '2':  [30.06, 31.34], '3':  [30.04, 31.24],
    '4':  [30.03, 31.47], '5':  [30.09, 31.32], '6':  [30.06, 31.22],
    '7':  [29.93, 30.98], '8':  [29.99, 31.21], '9':  [30.05, 31.20],
    '10': [30.03, 31.21], '11': [30.11, 31.24], '12': [29.85, 31.33],
    '13': [30.02, 31.80], '14': [30.06, 31.49], '15': [30.01, 30.94],
    'F1': [30.11, 31.41], 'F2': [30.06, 31.25], 'F3': [30.03, 31.21],
    'F4': [30.05, 31.26], 'F5': [30.05, 31.23], 'F6': [30.07, 31.30],
    'F7': [30.07, 30.97], 'F8': [30.03, 31.40], 'F9': [30.03, 31.23],
    'F10':[29.95, 31.25],
  };
  // Existing roads — the connectivity backbone we draw faintly so the
  // graph stays readable even when only a few nodes have been visited.
  const EDGES = [
    ['1','3'],['1','8'],['2','3'],['2','5'],['3','5'],['3','6'],['3','9'],
    ['3','10'],['4','2'],['4','14'],['5','11'],['6','9'],['7','8'],['7','15'],
    ['8','10'],['8','12'],['9','10'],['10','11'],['11','F2'],['12','1'],
    ['13','4'],['14','13'],['F1','5'],['F1','2'],['F2','3'],['F7','15'],['F8','4'],
  ];

  function project(canvas, node) {
    const pos = NODE_POS[node];
    if (!pos) return null;
    const [lat, lon] = pos;
    // Normalise lat/lon to canvas coords. Cairo bbox-ish.
    const minLon = 30.93, maxLon = 31.82;
    const minLat = 29.83, maxLat = 30.13;
    const padX = 14, padY = 16;
    const w = canvas.width  - 2 * padX;
    const h = canvas.height - 2 * padY;
    const x = padX + ((lon - minLon) / (maxLon - minLon)) * w;
    const y = padY + (1 - (lat - minLat) / (maxLat - minLat)) * h;
    return [x, y];
  }

  function clear(ctx, w, h) {
    ctx.fillStyle = '#0e0e10';
    ctx.fillRect(0, 0, w, h);
    // Subtle grid
    ctx.strokeStyle = 'rgba(255,255,255,0.025)';
    ctx.lineWidth = 1;
    for (let x = 0; x <= w; x += 32) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y <= h; y += 32) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
  }

  function drawBaseGraph(ctx, canvas, accent) {
    // Faint base: every edge in dim grey
    ctx.strokeStyle = 'rgba(120,120,135,0.18)';
    ctx.lineWidth = 1;
    EDGES.forEach(([a, b]) => {
      const p1 = project(canvas, a), p2 = project(canvas, b);
      if (!p1 || !p2) return;
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]); ctx.lineTo(p2[0], p2[1]);
      ctx.stroke();
    });
    // Faint base nodes
    Object.keys(NODE_POS).forEach(n => {
      const p = project(canvas, n);
      if (!p) return;
      ctx.fillStyle = 'rgba(150,150,165,0.22)';
      ctx.beginPath();
      ctx.arc(p[0], p[1], 2.5, 0, 2 * Math.PI);
      ctx.fill();
    });
  }

  function drawFrame(canvas, frame, opts) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    clear(ctx, w, h);
    drawBaseGraph(ctx, canvas, opts.accent);
    if (!frame) return;
    const visited = new Set(frame.visited || []);
    const frontier = new Set(frame.frontier || []);
    const current = frame.current;

    // Visited edges: any edge with both endpoints visited.
    ctx.strokeStyle = opts.accent;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = opts.accent;
    ctx.shadowBlur = 4;
    EDGES.forEach(([a, b]) => {
      if (!visited.has(a) || !visited.has(b)) return;
      const p1 = project(canvas, a), p2 = project(canvas, b);
      if (!p1 || !p2) return;
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]); ctx.lineTo(p2[0], p2[1]);
      ctx.stroke();
    });
    ctx.shadowBlur = 0;

    // Visited nodes
    visited.forEach(n => {
      const p = project(canvas, n);
      if (!p) return;
      ctx.fillStyle = opts.accent;
      ctx.shadowColor = opts.accent;
      ctx.shadowBlur = 4;
      ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, 2 * Math.PI); ctx.fill();
    });
    ctx.shadowBlur = 0;

    // Frontier nodes — hollow ring, lower opacity
    frontier.forEach(n => {
      const p = project(canvas, n);
      if (!p) return;
      ctx.strokeStyle = opts.accent;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(p[0], p[1], 6, 0, 2 * Math.PI); ctx.stroke();
      ctx.globalAlpha = 1.0;
    });

    // Current node — bright filled with halo
    if (current) {
      const p = project(canvas, current);
      if (p) {
        ctx.fillStyle = opts.accent;
        ctx.shadowColor = opts.accent;
        ctx.shadowBlur = 12;
        ctx.beginPath(); ctx.arc(p[0], p[1], 6, 0, 2 * Math.PI); ctx.fill();
        ctx.shadowBlur = 0;
        // Outer pulse ring
        ctx.strokeStyle = opts.accent;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.4;
        ctx.beginPath(); ctx.arc(p[0], p[1], 11, 0, 2 * Math.PI); ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }

    // Source/target markers — always drawn last, on top
    const src = (opts.source && project(canvas, opts.source));
    const tgt = (opts.target && project(canvas, opts.target));
    if (src) {
      ctx.strokeStyle = '#22c55e'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(src[0], src[1], 8, 0, 2 * Math.PI); ctx.stroke();
    }
    if (tgt) {
      ctx.strokeStyle = '#ef4444'; ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(tgt[0]-7, tgt[1]); ctx.lineTo(tgt[0]+7, tgt[1]);
      ctx.moveTo(tgt[0], tgt[1]-7); ctx.lineTo(tgt[0], tgt[1]+7);
      ctx.stroke();
    }
  }

  let _raceTimer = null;
  function stopRace() {
    if (_raceTimer) { cancelAnimationFrame(_raceTimer); _raceTimer = null; }
  }

  function startRace(bundle) {
    stopRace();
    if (!bundle || !bundle.dijkstra || !bundle.astar) return;
    const dCanvas = document.getElementById('race-canvas-dijkstra');
    const aCanvas = document.getElementById('race-canvas-astar');
    if (!dCanvas || !aCanvas) return;

    const dFrames = bundle.dijkstra.frames || [];
    const aFrames = bundle.astar.frames || [];
    const total = Math.max(dFrames.length, aFrames.length);
    if (total === 0) return;
    const PER_STEP_MS = 220;

    let started = performance.now();
    function tick(now) {
      const elapsed = now - started;
      const idx = Math.min(total - 1, Math.floor(elapsed / PER_STEP_MS));
      const dFrame = dFrames[Math.min(idx, dFrames.length - 1)];
      const aFrame = aFrames[Math.min(idx, aFrames.length - 1)];
      drawFrame(dCanvas, dFrame, {
        accent: '#00E5FF', source: bundle.source, target: bundle.target,
      });
      drawFrame(aCanvas, aFrame, {
        accent: '#FFB800', source: bundle.source, target: bundle.target,
      });
      const readout = document.getElementById('race-step-readout');
      if (readout) {
        readout.textContent =
          `step ${idx + 1} / ${total}    ·    ` +
          `Dijkstra ${dFrame ? dFrame.visited.length : 0} visited    ·    ` +
          `A* ${aFrame ? aFrame.visited.length : 0} visited`;
      }
      if (idx < total - 1) {
        _raceTimer = requestAnimationFrame(tick);
      } else {
        _raceTimer = null;
      }
    }
    _raceTimer = requestAnimationFrame(tick);
  }

  function postRaceToMap(bundle) {
    const frame = document.getElementById('cairo-maplibre');
    if (!bundle || !frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage({
      type: 'cairoflow-race-visual',
      race: bundle
    }, '*');
  }

  NS.cf.startRace = function (bundle) {
    if (!bundle) return null;
    // Defer one frame so the canvases are mounted in the DOM by Dash.
    requestAnimationFrame(() => startRace(bundle));
    return null;
  };

  NS.cf.replayRace = function (n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;
    // Read the cached bundle from a global the start callback sets.
    if (window.__cfRaceBundle) {
      startRace(window.__cfRaceBundle);
      postRaceToMap(window.__cfRaceBundle);
    }
    return window.dash_clientside.no_update;
  };

  // Hook: every time the race-data Store updates, kick off the animation
  // and stash the bundle for replay.
  NS.cf.onRaceData = function (bundle) {
    if (!bundle) return null;
    window.__cfRaceBundle = bundle;
    postRaceToMap(bundle);
    requestAnimationFrame(() => startRace(bundle));
    return null;
  };
})();
