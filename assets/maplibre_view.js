(function () {
  if (typeof window.maplibregl === "undefined") {
    showWarning("MapLibre failed to load. Check browser internet/CDN access.");
    return;
  }

  const CAIRO = [31.2357, 30.0444];
  const empty = { type: "FeatureCollection", features: [] };
  const cairoLabels = [
    ["Cairo", 31.2357, 30.0444, "capital"],
    ["Downtown Cairo", 31.2388, 30.0478, "district"],
    ["Giza", 31.2089, 30.0131, "city"],
    ["New Cairo", 31.4750, 30.0300, "city"],
    ["Nasr City", 31.3422, 30.0561, "district"],
    ["Maadi", 31.2565, 29.9602, "district"],
    ["6th October", 30.9769, 29.9285, "city"],
    ["Heliopolis", 31.3300, 30.1000, "district"],
    ["Cairo Airport", 31.4056, 30.1115, "facility"],
    ["Ramses Railway Station", 31.2461, 30.0626, "facility"],
    ["Qasr El Aini Hospital", 31.2294, 30.0311, "hospital"]
  ];

  const timeThemes = {
    Morning: {
      className: "tod-morning",
      pitch: 43,
      bearing: -8,
      fog: { color: "rgba(210,232,232,0.42)", "horizon-blend": 0.08, "space-color": "#dcecef", "star-intensity": 0 },
      route: "#079eb0",
      routeGlow: 0.16,
      trafficOpacity: 0.32,
      roadOpacity: 0.20,
      buildingColor: "#d9e0dc",
      buildingOpacity: 0.34,
      labelColor: "#10262d",
      labelHalo: "#ffffff"
    },
    Afternoon: {
      className: "tod-afternoon",
      pitch: 44,
      bearing: -5,
      fog: { color: "rgba(230,238,238,0.24)", "horizon-blend": 0.05, "space-color": "#eef4f4", "star-intensity": 0 },
      route: "#05778a",
      routeGlow: 0.12,
      trafficOpacity: 0.28,
      roadOpacity: 0.22,
      buildingColor: "#e5e4dc",
      buildingOpacity: 0.30,
      labelColor: "#0e232a",
      labelHalo: "#ffffff"
    },
    Evening: {
      className: "tod-evening",
      pitch: 50,
      bearing: -14,
      fog: { color: "rgba(229,168,88,0.32)", "horizon-blend": 0.18, "space-color": "#241710", "star-intensity": 0.08 },
      route: "#25d5df",
      routeGlow: 0.26,
      trafficOpacity: 0.52,
      roadOpacity: 0.18,
      buildingColor: "#7a5a3d",
      buildingOpacity: 0.42,
      labelColor: "#fff2d6",
      labelHalo: "#27160d"
    },
    Night: {
      className: "tod-night",
      pitch: 54,
      bearing: -18,
      fog: { color: "rgba(48,156,176,0.22)", "horizon-blend": 0.22, "space-color": "#020712", "star-intensity": 0.55 },
      route: "#55f4ff",
      routeGlow: 0.38,
      trafficOpacity: 0.44,
      roadOpacity: 0.12,
      buildingColor: "#122a36",
      buildingOpacity: 0.58,
      labelColor: "#eefbff",
      labelHalo: "#041019"
    }
  };

  let latestState = null;
  let map = null;
  let mapReady = false;
  let cameraSettled = false;
  let realBuildingsAvailable = false;
  let currentThemeName = "Morning";
  let customLayerIds = [];
  let vectorSourceLabel = "OpenFreeMap Bright";
  let routeAnimationToken = 0;
  let raceAnimationToken = 0;
  let lastRouteKey = "";
  let lastRaceKey = "";
  let activePopup = null;
  let displayState = loadDisplayState();
  const racePanelKind = new URLSearchParams(window.location.search).get("race_panel");
  if (racePanelKind) {
    document.body.classList.add("race-panel", "race-panel-" + racePanelKind);
  }

  init();

  async function init() {
    const config = await loadMapConfig();
    const styleChoice = chooseStyle(config);
    vectorSourceLabel = styleChoice.label;
    setText("map-source", "Vector style: " + styleChoice.label);
    hideWarning();

    // Race-panel iframes are small. Avoid 3D pitch + globe projection so
    // panning/zooming stays buttery on both mini maps in parallel.
    const flatPanel = Boolean(racePanelKind);
    map = new maplibregl.Map({
      container: "map",
      style: styleChoice.url,
      center: CAIRO,
      zoom: flatPanel ? 10.6 : 10.4,
      pitch: flatPanel ? 0 : 43,
      bearing: flatPanel ? 0 : -8,
      antialias: !flatPanel,
      maxPitch: flatPanel ? 0 : 62,
      attributionControl: false,
      fadeDuration: flatPanel ? 0 : 300
    });

    if (!flatPanel) {
      try { map.setProjection({ type: "globe" }); } catch (_) {}
    }
    map.addControl(new maplibregl.NavigationControl({ showCompass: !flatPanel }), "top-right");

    map.on("load", function () {
      buildOperationalLayers();
      mapReady = true;
      setTimeMode("Morning", false);
      applyDisplayState();
      if (latestState) {
        if (racePanelKind) updateRacePanelMap(latestState, racePanelKind);
        else updateMap(latestState);
      }
      if (!racePanelKind) setTimeout(resetCamera, 250);
      // Notify the parent frame so it can stop the legacy retry-storm.
      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({
            type: "cairoflow-map-ready",
            panel: racePanelKind || null
          }, "*");
        }
      } catch (_) {}
    });

    map.on("error", function (event) {
      const msg = event && event.error && event.error.message ? event.error.message : "";
      if (msg) showWarning("Vector map warning: " + msg);
    });

    installControls();
  }

  async function loadMapConfig() {
    try {
      const res = await fetch("/map-config", { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) {}
    return {};
  }

  function chooseStyle(config) {
    if (config.map_style_url) {
      return { url: config.map_style_url, label: "MAP_STYLE_URL" };
    }
    if (config.maptiler_key) {
      const styleId = config.maptiler_style || "streets-v2";
      return {
        url: "https://api.maptiler.com/maps/" + styleId + "/style.json?key=" + encodeURIComponent(config.maptiler_key),
        label: "MapTiler " + styleId
      };
    }
    if (config.openfreemap_style) {
      return { url: config.openfreemap_style, label: "OpenFreeMap Bright" };
    }
    return { url: "https://tiles.openfreemap.org/styles/bright", label: "OpenFreeMap Bright" };
  }

  function buildOperationalLayers() {
    customLayerIds = [];
    normalizeBaseLabels();
    addRealBuildingLayerIfAvailable();
    addSources();
    addOperationalLayers();
    addCairoLabels();
    installNodeInteractions();
  }

  function addSources() {
    const defs = {
      "cf-route": { lineMetrics: true },
      "cf-scenario-after": { lineMetrics: true },
      "cf-active-route-nodes": {},
      "cf-route-tracer": {},
      "cf-race-dijkstra": { lineMetrics: true },
      "cf-race-astar": { lineMetrics: true },
      "cf-race-explored": {},
      "cf-race-explored-edges": {},
      "cf-race-dijkstra-tracer": {},
      "cf-race-astar-tracer": {},
      "cf-race-labels": {}
    };
    [
      "cf-roads", "cf-route", "cf-start-end", "cf-scenario-before",
      "cf-scenario-after", "cf-nodes", "cf-areas", "cf-facilities",
      "cf-affected", "cf-bus", "cf-metro", "cf-maintain", "cf-labels",
      "cf-active-route-nodes", "cf-route-tracer", "cf-mst",
      "cf-race-dijkstra", "cf-race-astar",
      "cf-race-explored", "cf-race-explored-edges",
      "cf-race-dijkstra-tracer", "cf-race-astar-tracer",
      "cf-race-labels"
    ].forEach(function (id) {
      if (!map.getSource(id)) {
        map.addSource(id, Object.assign({ type: "geojson", data: empty }, defs[id] || {}));
      }
    });
  }

  function addLayer(layer, beforeId) {
    if (map.getLayer(layer.id)) return;
    customLayerIds.push(layer.id);
    try {
      map.addLayer(layer, beforeId && map.getLayer(beforeId) ? beforeId : firstSymbolLayerId());
    } catch (_) {
      map.addLayer(layer);
    }
  }

  function addOperationalLayers() {
    addLayer({
      id: "cf-areas-3d",
      type: "fill-extrusion",
      source: "cf-areas",
      minzoom: 10.5,
      paint: {
        "fill-extrusion-color": [
          "case",
          ["==", ["get", "kind"], "facility"], "#d6a147",
          "#2bb8c6"
        ],
        "fill-extrusion-opacity": 0.20,
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0
      }
    });

    addLayer({
      id: "cf-roads-base",
      type: "line",
      source: "cf-roads",
      paint: {
        "line-color": "#5c747b",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.7, 12, 1.9],
        "line-opacity": 0.20
      }
    });

    addLayer({
      id: "cf-traffic",
      type: "line",
      source: "cf-roads",
      paint: {
        "line-color": [
          "interpolate", ["linear"], ["get", "congestion"],
          0.25, "#18a7b1",
          0.62, "#d5a247",
          0.90, "#e05543",
          1.20, "#ff554a"
        ],
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.8, 12, 3.4],
        "line-opacity": ["interpolate", ["linear"], ["get", "congestion"], 0.25, 0.04, 1.2, 0.46]
      }
    });

    addLayer({
      id: "cf-mst-glow",
      type: "line",
      source: "cf-mst",
      paint: {
        "line-color": "#2bc9d2",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 4.8, 12, 10],
        "line-opacity": 0.16,
        "line-blur": 1.8
      }
    });

    addLayer({
      id: "cf-mst-line",
      type: "line",
      source: "cf-mst",
      paint: {
        "line-color": "#2bc9d2",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.9, 12, 4.2],
        "line-opacity": 0.84
      }
    });

    // Explored-edge dark casing — a thick near-black outline that makes
    // the bright explored-edge line pop against any basemap. No blur.
    addLayer({
      id: "cf-race-explored-edges-casing",
      type: "line",
      source: "cf-race-explored-edges",
      paint: {
        "line-color": "#040a12",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 6.0, 12, 8.0],
        "line-opacity": 0.72
      }
    });

    // Explored-edge bright line — the visible search-tree edges between
    // visited nodes. REAL road-graph edges (filtered from data.roads by
    // visited set). Solid line at high opacity so the professor clearly
    // sees the search expansion shape. No blur to keep cheap.
    addLayer({
      id: "cf-race-explored-edges-line",
      type: "line",
      source: "cf-race-explored-edges",
      paint: {
        "line-color": "#9eefff",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 3.8, 12, 5.0],
        "line-opacity": 0.97
      }
    });

    // Explored-node halo — solid translucent ring, NO circle-blur (blur is
    // expensive on the small race panels). The wider radius + low opacity
    // still reads as a glow, but it costs a single circle layer.
    addLayer({
      id: "cf-race-explored-glow",
      type: "circle",
      source: "cf-race-explored",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 9.5, 12, 16.0],
        "circle-color": "#9eefff",
        "circle-opacity": 0.22
      }
    });

    // Explored-node core dot — bright solid + crisp outline so the
    // professor sees every visited node at a glance.
    addLayer({
      id: "cf-race-explored-dot",
      type: "circle",
      source: "cf-race-explored",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 5.2, 12, 7.6],
        "circle-color": "#9eefff",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.4,
        "circle-opacity": 0.96
      }
    });

    addLayer({
      id: "cf-race-dijkstra-glow",
      type: "line",
      source: "cf-race-dijkstra",
      paint: {
        "line-color": "#2bc9d2",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 6.4, 12, 11.6],
        "line-opacity": 0.32,
        "line-blur": 0.6
      }
    });

    // Dark navy casing — separates the bright Dijkstra line from the
    // pale road basemap and explored edges. Extra-thick so the final
    // path dominates the visual hierarchy. No blur.
    addLayer({
      id: "cf-race-dijkstra-casing",
      type: "line",
      source: "cf-race-dijkstra",
      paint: {
        "line-color": "#031018",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 12.0, 12, 16.0],
        "line-opacity": 0.88
      }
    });

    addLayer({
      id: "cf-race-dijkstra-line",
      type: "line",
      source: "cf-race-dijkstra",
      paint: {
        "line-color": "#2bc9d2",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 7.0, 12, 10.0],
        "line-opacity": 1.0
      }
    });

    addLayer({
      id: "cf-race-astar-glow",
      type: "line",
      source: "cf-race-astar",
      paint: {
        "line-color": "#d7a448",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 6.8, 12, 12.2],
        "line-opacity": 0.34,
        "line-blur": 0.6
      }
    });

    addLayer({
      id: "cf-race-astar-casing",
      type: "line",
      source: "cf-race-astar",
      paint: {
        "line-color": "#1a0e02",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 12.0, 12, 16.0],
        "line-opacity": 0.88
      }
    });

    addLayer({
      id: "cf-race-astar-line",
      type: "line",
      source: "cf-race-astar",
      paint: {
        "line-color": "#ffb524",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 7.0, 12, 10.0],
        "line-opacity": 1.0
      }
    });

    addLayer({
      id: "cf-race-dijkstra-tracer",
      type: "circle",
      source: "cf-race-dijkstra-tracer",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 6.0, 12, 9.2],
        "circle-color": "#fff7df",
        "circle-stroke-color": "#2bc9d2",
        "circle-stroke-width": 3.0,
        "circle-opacity": 0.96
      }
    });

    addLayer({
      id: "cf-race-astar-tracer",
      type: "circle",
      source: "cf-race-astar-tracer",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 6.2, 12, 9.6],
        "circle-color": "#effdff",
        "circle-stroke-color": "#d7a448",
        "circle-stroke-width": 3.0,
        "circle-opacity": 0.98
      }
    });

    addLayer({
      id: "cf-race-labels",
      type: "symbol",
      source: "cf-race-labels",
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11.5, 12, 14.5],
        "text-allow-overlap": true,
        "text-ignore-placement": true,
        "text-offset": [0, -1.35],
        "symbol-sort-key": ["get", "sort"]
      },
      paint: {
        "text-color": [
          "case",
          ["==", ["get", "algorithm"], "Dijkstra"], "#2bc9d2",
          "#d7a448"
        ],
        "text-halo-color": "rgba(3, 9, 14, 0.86)",
        "text-halo-width": 1.6,
        "text-opacity": 0.98
      }
    });

    addLayer({
      id: "cf-scenario-before",
      type: "line",
      source: "cf-scenario-before",
      paint: {
        "line-color": "#7e9198",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.8, 12, 3.2],
        "line-opacity": 0.56,
        "line-dasharray": [1.5, 1.2]
      }
    });

    addLayer({
      id: "cf-affected",
      type: "line",
      source: "cf-affected",
      paint: {
        "line-color": "#e0a13f",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 3.2, 12, 7.0],
        "line-opacity": 0.86,
        "line-blur": 0.8,
        "line-dasharray": [1.2, 0.55]
      }
    });

    addLayer({
      id: "cf-scenario-after",
      type: "line",
      source: "cf-scenario-after",
      paint: {
        "line-color": "#20cad7",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.8, 12, 5.6],
        "line-opacity": 0.94
      }
    });

    addLayer({
      id: "cf-route-glow",
      type: "line",
      source: "cf-route",
      paint: {
        "line-color": "#20cad7",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 5, 12, 12],
        "line-opacity": 0.18,
        "line-blur": 2.0
      }
    });

    addLayer({
      id: "cf-route-line",
      type: "line",
      source: "cf-route",
      paint: {
        "line-color": [
          "interpolate",
          ["linear"],
          ["line-progress"],
          0, "#d7a448",
          0.22, "#2bc9d2",
          1, "#05778a"
        ],
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.8, 12, 5.4],
        "line-opacity": 0.98
      }
    });

    addLayer({
      id: "cf-maintain",
      type: "line",
      source: "cf-maintain",
      paint: {
        "line-color": "#d7a448",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2, 12, 4.8],
        "line-opacity": 0.84,
        "line-dasharray": [1, 0.7]
      }
    });

    addLayer({
      id: "cf-bus",
      type: "line",
      source: "cf-bus",
      paint: {
        "line-color": "#c99633",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 12, 2.4],
        "line-opacity": 0.54,
        "line-dasharray": [1.4, 1.2]
      }
    });

    addLayer({
      id: "cf-metro",
      type: "line",
      source: "cf-metro",
      paint: {
        "line-color": ["get", "color"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.8, 12, 4.0],
        "line-opacity": 0.82
      }
    });

    addLayer({
      id: "cf-start-end-halo",
      type: "circle",
      source: "cf-start-end",
      paint: {
        "circle-radius": ["case", ["==", ["get", "role"], "start"], 12, 14],
        "circle-color": [
          "case",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "start"]], "#29d46f",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "end"]], "#ff5f86",
          ["==", ["get", "role"], "start"], "#1bc7d4",
          "#d7a448"
        ],
        "circle-opacity": 0.18,
        "circle-stroke-width": 1,
        "circle-stroke-color": [
          "case",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "start"]], "#29d46f",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "end"]], "#ff5f86",
          ["==", ["get", "role"], "start"], "#1bc7d4",
          "#d7a448"
        ]
      }
    });

    addLayer({
      id: "cf-start-end",
      type: "circle",
      source: "cf-start-end",
      paint: {
        "circle-radius": ["case", ["==", ["get", "role"], "start"], 5.5, 6.2],
        "circle-color": [
          "case",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "start"]], "#29d46f",
          ["all", ["==", ["get", "race"], true], ["==", ["get", "role"], "end"]], "#ff5f86",
          ["==", ["get", "role"], "start"], "#1bc7d4",
          "#d7a448"
        ],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#ffffff",
        "circle-opacity": 0.96
      }
    });

    addLayer({
      id: "cf-node-halo",
      type: "circle",
      source: "cf-nodes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "importance"], 0, 12, 1, 22],
        "circle-color": "#2bc9d2",
        "circle-opacity": ["interpolate", ["linear"], ["get", "importance"], 0, 0.12, 1, 0.28],
        "circle-blur": 0.72
      }
    });

    addLayer({
      id: "cf-nodes",
      type: "circle",
      source: "cf-nodes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "importance"], 0, 6.4, 1, 10.2],
        "circle-color": "rgba(5, 18, 24, 0.30)",
        "circle-opacity": 0.96,
        "circle-stroke-width": ["case", ["==", ["get", "isCentral"], true], 3.0, 2.2],
        "circle-stroke-color": [
          "case",
          ["==", ["get", "isCentral"], true], "#bffcff",
          "#5bd6d2"
        ]
      }
    });

    addLayer({
      id: "cf-node-core",
      type: "circle",
      source: "cf-nodes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "importance"], 0, 2.0, 1, 3.4],
        "circle-color": ["case", ["==", ["get", "isCentral"], true], "#ecfeff", "#2bc9d2"],
        "circle-stroke-width": 0.7,
        "circle-stroke-color": "rgba(255,255,255,0.78)",
        "circle-opacity": 0.92
      }
    });

    addLayer({
      id: "cf-facility-halo",
      type: "circle",
      source: "cf-facilities",
      paint: {
        "circle-radius": [
          "case",
          ["==", ["get", "isHospital"], true], 24,
          ["==", ["get", "isAirport"], true], 26,
          ["==", ["get", "isTransit"], true], 23,
          18
        ],
        "circle-color": [
          "case",
          ["==", ["get", "isHospital"], true], "#f15b4a",
          ["==", ["get", "isTransit"], true], "#8b78ff",
          ["==", ["get", "isAirport"], true], "#2bc9d2",
          "#d7a448"
        ],
        "circle-opacity": 0.24,
        "circle-blur": 0.58
      }
    });

    addLayer({
      id: "cf-facilities",
      type: "circle",
      source: "cf-facilities",
      paint: {
        "circle-radius": [
          "case",
          ["==", ["get", "isHospital"], true], 10.2,
          ["==", ["get", "isAirport"], true], 11.0,
          ["==", ["get", "isTransit"], true], 9.8,
          8.0
        ],
        "circle-color": "rgba(5, 18, 24, 0.36)",
        "circle-opacity": 0.98,
        "circle-stroke-width": [
          "case",
          ["==", ["get", "isHospital"], true], 3.2,
          ["==", ["get", "isAirport"], true], 3.4,
          ["==", ["get", "isTransit"], true], 3.0,
          2.6
        ],
        "circle-stroke-color": [
          "case",
          ["==", ["get", "isHospital"], true], "#e05543",
          ["==", ["get", "isTransit"], true], "#8bdde5",
          ["==", ["get", "isAirport"], true], "#2bc9d2",
          "#d7a448"
        ]
      }
    });

    addLayer({
      id: "cf-facility-core",
      type: "circle",
      source: "cf-facilities",
      paint: {
        "circle-radius": ["case", ["==", ["get", "isAirport"], true], 4.5, ["==", ["get", "isHospital"], true], 4.2, ["==", ["get", "isTransit"], true], 4.0, 3.4],
        "circle-color": [
          "case",
          ["==", ["get", "isHospital"], true], "#ffe7e2",
          ["==", ["get", "isAirport"], true], "#effdff",
          ["==", ["get", "isTransit"], true], "#effdff",
          "#fff3ce"
        ],
        "circle-stroke-width": 0.8,
        "circle-stroke-color": "rgba(5,18,24,0.52)",
        "circle-opacity": 0.95
      }
    });

    addLayer({
      id: "cf-facility-icons",
      type: "symbol",
      source: "cf-facilities",
      minzoom: 9.2,
      layout: {
        "text-field": ["get", "icon"],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["case", ["==", ["get", "isAirport"], true], 11.6, ["==", ["get", "isHospital"], true], 11.3, 10.6],
        "text-allow-overlap": true,
        "text-ignore-placement": true
      },
      paint: {
        "text-color": "#071015",
        "text-halo-color": "rgba(255,255,255,0.86)",
        "text-halo-width": 0.95,
        "text-opacity": 0.94
      }
    });

    addLayer({
      id: "cf-active-route-nodes-halo",
      type: "circle",
      source: "cf-active-route-nodes",
      paint: {
        "circle-radius": ["case", ["==", ["get", "role"], "middle"], 10, 16],
        "circle-color": ["case", ["==", ["get", "role"], "end"], "#d7a448", "#2bc9d2"],
        "circle-opacity": 0.18,
        "circle-blur": 0.52
      }
    });

    addLayer({
      id: "cf-active-route-nodes",
      type: "circle",
      source: "cf-active-route-nodes",
      paint: {
        "circle-radius": ["case", ["==", ["get", "role"], "middle"], 4.4, 6.8],
        "circle-color": ["case", ["==", ["get", "role"], "end"], "#d7a448", "#2bc9d2"],
        "circle-stroke-width": 2.2,
        "circle-stroke-color": "#ffffff",
        "circle-opacity": 0.98
      }
    });

    addLayer({
      id: "cf-route-tracer",
      type: "circle",
      source: "cf-route-tracer",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 4.5, 12, 7.5],
        "circle-color": "#ffffff",
        "circle-stroke-color": "#2bc9d2",
        "circle-stroke-width": 2.2,
        "circle-opacity": 0.96,
        "circle-blur": 0.05
      }
    });

    addLayer({
      id: "cf-node-labels",
      type: "symbol",
      source: "cf-active-route-nodes",
      minzoom: 10,
      layout: {
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-offset": [0, 1.35],
        "text-anchor": "top",
        "text-allow-overlap": false
      },
      paint: {
        "text-color": "#10262d",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.3
      }
    });
  }

  function addCairoLabels() {
    setSource("cf-labels", featureCollection(cairoLabels.map(function (row) {
      return {
        type: "Feature",
        properties: { name: row[0], kind: row[3] },
        geometry: { type: "Point", coordinates: [row[1], row[2]] }
      };
    })));

    const layer = {
      id: "cf-cairo-labels",
      type: "symbol",
      source: "cf-labels",
      minzoom: 8.2,
      layout: {
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["case", ["==", ["get", "kind"], "capital"], 16, ["==", ["get", "kind"], "city"], 13, 11],
        "text-anchor": "center",
        "text-offset": [0, 0.8],
        "text-allow-overlap": false,
        "text-variable-anchor": ["top", "bottom", "left", "right"]
      },
      paint: {
        "text-color": "#10262d",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.4,
        "text-opacity": 0.92
      }
    };
    if (!map.getLayer(layer.id)) {
      customLayerIds.push(layer.id);
      map.addLayer(layer);
    }
  }

  function normalizeBaseLabels() {
    const style = map.getStyle();
    const layers = style && style.layers ? style.layers : [];
    layers.forEach(function (layer) {
      if (layer.type !== "symbol" || !layer.layout || !layer.layout["text-field"]) return;
      try {
        map.setLayoutProperty(layer.id, "text-field", [
          "coalesce",
          ["get", "name:en"],
          ["get", "name:latin"],
          ""
        ]);
        map.setLayoutProperty(layer.id, "text-font", ["Noto Sans Regular"]);
        map.setPaintProperty(layer.id, "text-halo-width", 1.15);
        map.setPaintProperty(layer.id, "text-halo-blur", 0.15);
      } catch (_) {}
    });
  }

  function installNodeInteractions() {
    ["cf-nodes", "cf-facilities", "cf-facility-icons", "cf-active-route-nodes"].forEach(function (layerId) {
      if (!map.getLayer(layerId)) return;
      map.on("mouseenter", layerId, function () { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", layerId, function () { map.getCanvas().style.cursor = ""; });
      map.on("click", layerId, function (event) {
        const feature = event.features && event.features[0];
        if (!feature) return;
        showNodePopup(feature, event.lngLat);
      });
    });
  }

  function showNodePopup(feature, lngLat) {
    const p = feature.properties || {};
    const type = String(p.type || p.kind || "Node");
    const isHospital = p.isHospital === true || p.isHospital === "true";
    const isAirport = p.isAirport === true || p.isAirport === "true";
    const isTransit = p.isTransit === true || p.isTransit === "true";
    const identity = isHospital ? "Medical priority" : isAirport ? "Airport hub" : isTransit ? "Transit hub" : type;
    const population = Number(p.population || 0);
    const populationText = population > 0 ? "<span>Population</span><strong>" + formatCompact(population) + "</strong>" : "";
    const html = [
      "<div class='cf-node-popup-card'>",
      "<div class='cf-node-popup-kicker'>" + escapeHtml(identity) + "</div>",
      "<div class='cf-node-popup-title'>" + escapeHtml(p.name || "CairoFlow node") + "</div>",
      "<div class='cf-node-popup-grid'>",
      "<span>Node ID</span><strong>" + escapeHtml(p.id || "") + "</strong>",
      populationText,
      "<span>Type</span><strong>" + escapeHtml(type || "network") + "</strong>",
      "</div>",
      "</div>"
    ].join("");
    if (activePopup) activePopup.remove();
    activePopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: true,
      className: "cf-node-popup",
      maxWidth: "260px",
      offset: 14
    }).setLngLat(lngLat).setHTML(html).addTo(map);
  }

  function addRealBuildingLayerIfAvailable() {
    const style = map.getStyle();
    const layers = style && style.layers ? style.layers : [];
    const building = layers.find(function (layer) {
      const sl = String(layer["source-layer"] || layer.id || "").toLowerCase();
      return sl.includes("building") && layer.type !== "symbol" && layer.source;
    });

    if (!building || !building.source || !building["source-layer"]) {
      realBuildingsAvailable = false;
      setText("map-source", "Vector style: " + vectorSourceLabel + " - Operational 3D visualization");
      return;
    }

    realBuildingsAvailable = true;
    setText("map-source", "Vector style: " + vectorSourceLabel + " - Real building layer detected");
    try {
      map.addLayer({
        id: "cf-real-buildings",
        type: "fill-extrusion",
        source: building.source,
        "source-layer": building["source-layer"],
        minzoom: 13,
        paint: {
          "fill-extrusion-color": "#d9e0dc",
          "fill-extrusion-opacity": 0.34,
          "fill-extrusion-height": [
            "case",
            ["has", "render_height"], ["to-number", ["get", "render_height"]],
            ["has", "height"], ["to-number", ["get", "height"]],
            ["has", "building:levels"], ["*", ["to-number", ["get", "building:levels"]], 3],
            12
          ],
          "fill-extrusion-base": [
            "case",
            ["has", "render_min_height"], ["to-number", ["get", "render_min_height"]],
            ["has", "min_height"], ["to-number", ["get", "min_height"]],
            0
          ]
        }
      }, firstSymbolLayerId());
      customLayerIds.push("cf-real-buildings");
    } catch (_) {
      realBuildingsAvailable = false;
      setText("map-source", "Vector style: " + vectorSourceLabel + " - Operational 3D visualization");
    }
  }

  function setTimeMode(label, moveCamera) {
    currentThemeName = label || "Morning";
    const theme = timeThemes[currentThemeName] || timeThemes.Morning;
    const body = document.body;
    Object.values(timeThemes).forEach(function (t) { body.classList.remove(t.className); });
    body.classList.add(theme.className);
    try { map.setFog(theme.fog); } catch (_) {}
    applyBaseStyleTheme(currentThemeName);

    setPaint("cf-route-line", "line-color", [
      "interpolate",
      ["linear"],
      ["line-progress"],
      0, currentThemeName === "Evening" ? "#f1b84f" : "#d7a448",
      0.22, theme.route,
      1, currentThemeName === "Night" ? "#55f4ff" : theme.route
    ]);
    setPaint("cf-route-glow", "line-color", theme.route);
    setPaint("cf-route-glow", "line-opacity", theme.routeGlow);
    setPaint("cf-route-tracer", "circle-stroke-color", theme.route);
    setPaint("cf-mst-line", "line-color", currentThemeName === "Evening" ? "#65e2d4" : theme.route);
    setPaint("cf-mst-glow", "line-color", theme.route);
    setPaint("cf-mst-glow", "line-opacity", currentThemeName === "Night" ? 0.28 : 0.16);
    setPaint("cf-race-dijkstra-glow", "line-opacity", currentThemeName === "Night" ? 0.30 : 0.20);
    setPaint("cf-race-astar-glow", "line-opacity", currentThemeName === "Night" ? 0.32 : 0.22);
    setPaint("cf-roads-base", "line-opacity", theme.roadOpacity);
    setPaint("cf-traffic", "line-opacity", [
      "interpolate", ["linear"], ["get", "congestion"],
      0.25, 0.02,
      0.80, theme.trafficOpacity * 0.55,
      1.20, theme.trafficOpacity
    ]);
    setPaint("cf-areas-3d", "fill-extrusion-opacity", theme.buildingOpacity * 0.72);
    setPaint("cf-real-buildings", "fill-extrusion-color", theme.buildingColor);
    setPaint("cf-real-buildings", "fill-extrusion-opacity", theme.buildingOpacity);
    setPaint("cf-cairo-labels", "text-color", theme.labelColor);
    setPaint("cf-cairo-labels", "text-halo-color", theme.labelHalo);
    setPaint("cf-node-labels", "text-color", theme.labelColor);
    setPaint("cf-node-labels", "text-halo-color", theme.labelHalo);

    if (moveCamera && cameraSettled) {
      map.easeTo({ pitch: theme.pitch, bearing: theme.bearing, duration: 900 });
      updatePresetReadout(currentThemeName);
    }
    syncPresetButtons(currentThemeName);
  }

  function updatePresetReadout(label) {
    const clockByTime = { Morning: "06:00", Afternoon: "13:00", Evening: "18:00", Night: "22:00" };
    const clock = clockByTime[label] || "06:00";
    const mode = latestState && latestState.active_mode ? String(latestState.active_mode).toUpperCase() : "ROUTE";
    const route = latestState && latestState.route && latestState.route.travel_time_min
      ? "ETA " + Number(latestState.route.travel_time_min).toFixed(1) + " min"
      : "network live";
    setText("map-hour", clock);
    setText("map-period", label);
    setText("map-status", clock + " " + label + " - " + mode + " - " + route);
  }

  function applyBaseStyleTheme(label) {
    const palettes = {
      Morning: {
        background: "#e7f1f1",
        land: "#eef1ea",
        park: "#dcebd5",
        water: "#8ccbd2",
        road: "#f4bd64",
        roadMinor: "#f1d6a2",
        boundary: "#b4c5c3",
        label: "#24363b",
        halo: "#ffffff",
        opacity: 0.88
      },
      Afternoon: {
        background: "#eef4f4",
        land: "#f4f2ea",
        park: "#dbead0",
        water: "#88c8d1",
        road: "#eba94e",
        roadMinor: "#f0d29b",
        boundary: "#b4c0bd",
        label: "#1d3035",
        halo: "#ffffff",
        opacity: 0.92
      },
      Evening: {
        background: "#302018",
        land: "#4b3828",
        park: "#485037",
        water: "#356d78",
        road: "#c78f3a",
        roadMinor: "#7f6440",
        boundary: "#7d6550",
        label: "#fff0d4",
        halo: "#24150e",
        opacity: 0.72
      },
      Night: {
        background: "#030910",
        land: "#07131a",
        park: "#0e211c",
        water: "#0b3441",
        road: "#4f6f76",
        roadMinor: "#263943",
        boundary: "#25404a",
        label: "#eefbff",
        halo: "#02070c",
        opacity: 0.64
      }
    };
    const p = palettes[label] || palettes.Morning;
    const layers = (map.getStyle() && map.getStyle().layers) || [];

    layers.forEach(function (layer) {
      if (!layer || customLayerIds.includes(layer.id) || String(layer.id || "").startsWith("cf-")) return;
      const key = (String(layer.id || "") + " " + String(layer["source-layer"] || "")).toLowerCase();
      try {
        if (layer.type === "background") {
          map.setPaintProperty(layer.id, "background-color", p.background);
        } else if (layer.type === "fill") {
          const color = key.includes("water")
            ? p.water
            : key.includes("park") || key.includes("green") || key.includes("wood") || key.includes("landcover")
              ? p.park
              : p.land;
          map.setPaintProperty(layer.id, "fill-color", color);
          if (key.includes("water")) map.setPaintProperty(layer.id, "fill-opacity", label === "Night" ? 0.82 : 0.92);
        } else if (layer.type === "line") {
          const color = key.includes("water")
            ? p.water
            : key.includes("boundary")
              ? p.boundary
              : key.includes("motorway") || key.includes("trunk") || key.includes("primary") || key.includes("road")
                ? p.road
                : p.roadMinor;
          map.setPaintProperty(layer.id, "line-color", color);
          map.setPaintProperty(layer.id, "line-opacity", key.includes("road") || key.includes("transportation") ? p.opacity : Math.max(0.28, p.opacity - 0.18));
        } else if (layer.type === "symbol") {
          if (layer.layout && layer.layout["text-field"]) {
            map.setPaintProperty(layer.id, "text-color", p.label);
            map.setPaintProperty(layer.id, "text-halo-color", p.halo);
            map.setPaintProperty(layer.id, "text-halo-width", label === "Night" ? 1.65 : 1.2);
          }
          if (layer.paint && Object.prototype.hasOwnProperty.call(layer.paint, "icon-opacity")) {
            map.setPaintProperty(layer.id, "icon-opacity", label === "Night" ? 0.74 : 0.86);
          }
        }
      } catch (_) {}
    });
  }

  function updateMap(data) {
    latestState = data;
    if (!mapReady || !data) return;
    setTimeMode(data.time_of_day || "Morning", true);
    const nodeById = Object.fromEntries((data.nodes || []).map(function (n) { return [n.id, n]; }));
    const scenario = data.scenario || null;
    const affectedSet = new Set((scenario && scenario.affected_edges || []).map(edgeKey));
    const factor = scenario && !scenario.closed ? Number(scenario.factor || 1) : 1;
    const timeKey = data.time_key || "morning_peak";

    setSource("cf-roads", featureCollection((data.roads || []).map(function (r) {
      const a = nodeById[r.from];
      const b = nodeById[r.to];
      if (!a || !b) return null;
      const affected = affectedSet.has(edgeKey([r.from, r.to]));
      const flow = Number((r.traffic || {})[timeKey] || 0) * (affected ? factor : 1);
      const cap = Math.max(1, Number(r.capacity || 1));
      return line([a, b], {
        from: r.from,
        to: r.to,
        congestion: flow / cap,
        condition: Number(r.condition || 0),
        affected
      });
    }).filter(Boolean)));

    const heroPath = activePathFor(data, scenario);
    setSource("cf-affected", pathFeaturesFromEdges(scenario && scenario.affected_edges, nodeById, { affected: true }));
    setSource("cf-mst", pathFeaturesFromEdges(data.mst && data.mst.selected_edges, nodeById, { kind: "mst" }));
    updateRouteVisuals(heroPath, nodeById);
    setSource("cf-active-route-nodes", activeRouteNodeFeatures(heroPath, nodeById));
    const raceForMode = data.active_mode === "race_lab" ? data.race : null;
    const markerRoute = data.active_mode === "route"
      ? data.route
      : raceForMode
        ? { src: raceForMode.source, dst: raceForMode.target }
        : null;
    setSource("cf-start-end", startEndFeatures(markerRoute, nodeById, heroPath));
    setSource("cf-scenario-before", pathFeature(scenario && scenario.before_path, nodeById, { kind: "before" }));
    setSource("cf-scenario-after", pathFeature(scenario && scenario.after_path, nodeById, { kind: "after" }));
    setSource("cf-maintain", maintainFeatures(data, nodeById));
    setSource("cf-bus", transitFeatures(data.active_mode === "transit" ? data.bus_routes : [], nodeById, "stops"));
    setSource("cf-metro", metroFeatures(data.active_mode === "transit" ? data.metro_lines : [], nodeById));
    setSource("cf-nodes", pointFeatures((data.nodes || []).filter(function (n) { return n.kind === "neighborhood"; })));
    setSource("cf-facilities", pointFeatures((data.nodes || []).filter(function (n) { return n.kind === "facility"; })));
    setSource("cf-areas", areaFeatures(data.nodes || []));
    if (data.active_mode === "race_lab") {
      updateRaceVisual(data.race, nodeById);
    } else {
      clearRaceVisual();
    }

    updateVisibility(
      data.active_mode,
      Boolean(heroPath && heroPath.length > 1),
      Boolean(scenario),
      Boolean(data.mst && data.mst.selected_edges && data.mst.selected_edges.length),
      Boolean(data.race && data.race.dijkstra && data.race.astar)
    );
    applyModeStyling(data.active_mode, Boolean(scenario));
    applyDisplayState();
    updateStatus(data);
    updateRouteCard(data);
    if (!cameraSettled && data.nodes && data.nodes.length) resetCamera();
  }

  // Cache key for the heavy base-layer (roads/nodes/areas) refresh in
  // race-panel mode. The clientside bridge fan-out fires 4 retries per
  // state change; without this dedup we rebuild ~30 road LineStrings,
  // ~25 nodes, ~25 facilities and ~25 area polygons four times per
  // state change per panel. With this dedup we do it exactly once.
  let lastRacePanelBaseKey = "";
  let lastRacePanelOverlayKey = "";

  function updateRacePanelMap(data, panelKind, forceReplay) {
    latestState = data;
    if (!mapReady || !data) return;
    const panel = panelKind || racePanelKind || "dijkstra";
    setTimeMode(data.time_of_day || "Morning", true);
    setUiTheme(data.ui_theme);
    const nodeById = Object.fromEntries((data.nodes || []).map(function (n) { return [n.id, n]; }));
    const timeKey = data.time_key || "morning_peak";

    const baseKey = [
      timeKey,
      (data.nodes || []).length,
      (data.roads || []).length,
      currentThemeName,
    ].join("|");
    if (forceReplay || baseKey !== lastRacePanelBaseKey) {
      lastRacePanelBaseKey = baseKey;
      setSource("cf-roads", featureCollection((data.roads || []).map(function (r) {
        const a = nodeById[r.from];
        const b = nodeById[r.to];
        if (!a || !b) return null;
        const flow = Number((r.traffic || {})[timeKey] || 0);
        const cap = Math.max(1, Number(r.capacity || 1));
        return line([a, b], {
          from: r.from,
          to: r.to,
          congestion: flow / cap,
          condition: Number(r.condition || 0)
        });
      }).filter(Boolean)));
      setSource("cf-nodes", pointFeatures((data.nodes || []).filter(function (n) { return n.kind === "neighborhood"; })));
      setSource("cf-facilities", pointFeatures((data.nodes || []).filter(function (n) { return n.kind === "facility"; })));
      setSource("cf-areas", areaFeatures(data.nodes || []));
    }

    // Cheap overlay-key short-circuit. If the race bundle, theme, source
    // and target are all unchanged, skip the rest of the work; the
    // animation is already correct on screen.
    const race = data.race || {};
    const overlayRoute = panel === "astar" ? (race.astar || {}) : (race.dijkstra || {});
    const overlayKey = [
      panel,
      (overlayRoute.path || []).join("-"),
      (overlayRoute.explored_nodes || []).join("-"),
      race.source || "",
      race.target || "",
      currentThemeName,
      data.ui_theme || "",
    ].join("|");
    if (!forceReplay && overlayKey === lastRacePanelOverlayKey) {
      return;
    }
    lastRacePanelOverlayKey = overlayKey;

    clearRouteAndScenarioVisuals();

    const route = overlayRoute;
    const sourceId = race.source || (route && route.path && route.path[0]);
    const targetId = race.target || (route && route.path && route.path[route.path.length - 1]);
    setSource("cf-start-end", startEndFeatures({ src: sourceId, dst: targetId, race: true }, nodeById, route && route.path));
    drawRacePanelRoute(panel, route, nodeById, forceReplay);

    updateVisibility(
      "race_panel",
      false,
      false,
      false,
      Boolean(route && route.path && route.path.length > 1)
    );
    setLayerVisibility(["cf-start-end", "cf-start-end-halo"], Boolean(sourceId && targetId));
    applyModeStyling("race_lab", false);
    applyDisplayState();
    updateStatus(data);
    if (route && route.path && route.path.length > 1) {
      fitRacePanelBounds(route.path, exploredIdsFromResult(route), nodeById);
    } else if (!cameraSettled && data.nodes && data.nodes.length) {
      resetCamera();
    }
  }

  function clearRouteAndScenarioVisuals() {
    setSource("cf-route", empty);
    setSource("cf-route-tracer", empty);
    setSource("cf-active-route-nodes", empty);
    setSource("cf-scenario-before", empty);
    setSource("cf-scenario-after", empty);
    setSource("cf-affected", empty);
    setSource("cf-mst", empty);
    setSource("cf-maintain", empty);
    setSource("cf-bus", empty);
    setSource("cf-metro", empty);
  }

  function drawRacePanelRoute(panel, route, nodeById, forceReplay) {
    const ids = route && route.path ? route.path : [];
    const exploredIds = exploredIdsFromResult(route);
    const nodes = pathToNodes(ids, nodeById);
    const exploredCoords = exploredIds.map(function (id) { return nodeById[id]; }).filter(Boolean).map(coord);
    const roads = (latestState && latestState.roads) || [];
    const exploredEdges = computeExploredEdges(roads, exploredIds, nodeById);
    const sourceId = panel === "astar" ? "cf-race-astar" : "cf-race-dijkstra";
    const tracerId = panel === "astar" ? "cf-race-astar-tracer" : "cf-race-dijkstra-tracer";
    const otherSourceId = panel === "astar" ? "cf-race-dijkstra" : "cf-race-astar";
    const otherTracerId = panel === "astar" ? "cf-race-dijkstra-tracer" : "cf-race-astar-tracer";
    if (nodes.length < 2) {
      setSource(sourceId, empty);
      setSource(tracerId, empty);
      setSource(otherSourceId, empty);
      setSource(otherTracerId, empty);
      setSource("cf-race-explored", empty);
      setSource("cf-race-explored-edges", empty);
      setSource("cf-race-labels", empty);
      return;
    }
    const coords = nodes.map(coord);
    const key = panel + "|" + ids.join("-") + "|" + exploredIds.join("-") + "|" + currentThemeName;
    setSource(otherSourceId, empty);
    setSource(otherTracerId, empty);
    setSource("cf-race-labels", racePanelLabel(panel, coords));
    if (!forceReplay && key === lastRaceKey) {
      setSource("cf-race-explored", raceExploredFeatures(exploredCoords, panel));
      setSource("cf-race-explored-edges", raceExploredEdgeFeatures(exploredEdges, panel));
      setSource(sourceId, featureCollection([line(coords, { algorithm: panel === "astar" ? "A*" : "Dijkstra" })]));
      setSource(tracerId, displayState.tracer ? pointFromCoord(coords[coords.length - 1], { algorithm: panel }) : empty);
      return;
    }
    lastRaceKey = key;
    if (!displayState.animations) {
      setSource("cf-race-explored", raceExploredFeatures(exploredCoords, panel));
      setSource("cf-race-explored-edges", raceExploredEdgeFeatures(exploredEdges, panel));
      setSource(sourceId, featureCollection([line(coords, { algorithm: panel === "astar" ? "A*" : "Dijkstra" })]));
      setSource(tracerId, displayState.tracer ? pointFromCoord(coords[coords.length - 1], { algorithm: panel }) : empty);
      return;
    }
    animateRacePanelRoute(coords, exploredCoords, exploredEdges, sourceId, tracerId, panel);
  }

  function animateRacePanelRoute(coords, exploredCoords, exploredEdges, sourceId, tracerId, panel) {
    const token = ++raceAnimationToken;
    const exploreDuration = 3500;
    const routeDuration = 3500;
    const duration = exploreDuration + routeDuration;
    const start = performance.now();
    const algorithm = panel === "astar" ? "A*" : "Dijkstra";
    setSource("cf-race-explored", empty);
    setSource("cf-race-explored-edges", empty);
    setSource(sourceId, empty);
    setSource(tracerId, empty);

    // Throttle setData calls: only push a new GeoJSON when the integer
    // explored-count actually advances, or when the route slice has
    // moved by a meaningful fraction. This drops ~240 setData calls
    // per map down to a few dozen, which is what keeps replay smooth.
    let lastExploredCount = -1;
    let lastRouteStep = -1;
    const ROUTE_STEPS = 36; // ~97 ms per visible step over 3.5 s

    function frame(now) {
      if (token !== raceAnimationToken) return;
      const t = Math.min(1, (now - start) / duration);
      const elapsed = now - start;
      const exploreProgress = Math.min(1, elapsed / exploreDuration);
      const exploredCount = Math.ceil(exploredCoords.length * (1 - Math.pow(1 - exploreProgress, 2.2)));
      if (exploredCount !== lastExploredCount) {
        lastExploredCount = exploredCount;
        setSource("cf-race-explored", raceExploredFeatures(exploredCoords.slice(0, exploredCount), panel));
        // Show only edges whose later-visited endpoint has been
        // revealed by this step. Cheap O(edges) filter.
        const stepEdges = (exploredEdges || []).filter(function (e) { return e.step < exploredCount; });
        setSource("cf-race-explored-edges", raceExploredEdgeFeatures(stepEdges, panel));
      }

      if (elapsed >= exploreDuration) {
        const routeProgress = Math.min(1, (elapsed - exploreDuration) / routeDuration);
        const eased = 1 - Math.pow(1 - routeProgress, 2.4);
        const step = Math.min(ROUTE_STEPS, Math.floor(eased * ROUTE_STEPS));
        if (step !== lastRouteStep) {
          lastRouteStep = step;
          const slice = lineAtProgress(coords, eased);
          setSource(sourceId, featureCollection([{
            type: "Feature",
            properties: { algorithm: algorithm },
            geometry: { type: "LineString", coordinates: slice.coordinates }
          }]));
          setSource(tracerId, displayState.tracer ? pointFromCoord(slice.tracer, { algorithm: algorithm }) : empty);
        }
      }
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        setSource("cf-race-explored", raceExploredFeatures(exploredCoords, panel));
        setSource("cf-race-explored-edges", raceExploredEdgeFeatures(exploredEdges, panel));
        setSource(sourceId, featureCollection([line(coords, { algorithm: algorithm })]));
        setSource(tracerId, displayState.tracer ? pointFromCoord(coords[coords.length - 1], { algorithm: algorithm }) : empty);
      }
    }

    requestAnimationFrame(frame);
  }

  function exploredIdsFromResult(route) {
    if (!route) return [];
    if (Array.isArray(route.explored_nodes) && route.explored_nodes.length) return route.explored_nodes;
    const frames = Array.isArray(route.frames) ? route.frames : [];
    for (let i = frames.length - 1; i >= 0; i -= 1) {
      if (Array.isArray(frames[i].visited) && frames[i].visited.length) return frames[i].visited;
    }
    return [];
  }

  function raceExploredFeatures(coords, panel) {
    return featureCollection((coords || []).map(function (c, idx) {
      return pointCoordFeature(c, {
        algorithm: panel === "astar" ? "A*" : "Dijkstra",
        role: "explored",
        order: idx
      });
    }));
  }

  // Reconstruct REAL road-graph edges between visited nodes. This is
  // honest data — we filter `data.roads` (already in iframe state) to
  // edges whose endpoints are both in the visited set. Each edge is
  // tagged with the step at which the LATER of its two endpoints
  // became visited, so the animation can reveal the search-tree
  // shape in lockstep with the explored-node reveal. No fakes.
  function computeExploredEdges(roads, exploredIds, nodeById) {
    if (!Array.isArray(roads) || !exploredIds || !exploredIds.length) return [];
    const order = {};
    exploredIds.forEach(function (id, i) { order[String(id)] = i; });
    const out = [];
    roads.forEach(function (r) {
      const u = String(r.from);
      const v = String(r.to);
      const i = order[u];
      const j = order[v];
      if (i === undefined || j === undefined) return;
      const a = nodeById[r.from] || nodeById[u];
      const b = nodeById[r.to] || nodeById[v];
      if (!a || !b) return;
      out.push({
        step: Math.max(i, j),
        from: r.from,
        to: r.to,
        a: coord(a),
        b: coord(b)
      });
    });
    out.sort(function (x, y) { return x.step - y.step; });
    return out;
  }

  function raceExploredEdgeFeatures(edges, panel) {
    const algorithm = panel === "astar" ? "A*" : "Dijkstra";
    return featureCollection((edges || []).map(function (e) {
      return {
        type: "Feature",
        properties: {
          algorithm: algorithm,
          role: "explored-edge",
          from: e.from,
          to: e.to,
          step: e.step
        },
        geometry: { type: "LineString", coordinates: [e.a, e.b] }
      };
    }));
  }

  function racePanelLabel(panel, coords) {
    const label = panel === "astar" ? "A* SEARCH" : "DIJKSTRA";
    const algorithm = panel === "astar" ? "A*" : "Dijkstra";
    const c = lineAtProgress(coords, 0.58).tracer || coords[0];
    return featureCollection(c ? [{
      type: "Feature",
      properties: { algorithm: algorithm, label: label, sort: 1 },
      geometry: { type: "Point", coordinates: c }
    }] : []);
  }

  function fitPathBounds(path, nodeById) {
    if (!map || !path || path.length < 2) return;
    const coords = path.map(function (id) { return nodeById[id]; }).filter(Boolean).map(coord);
    if (coords.length < 2) return;
    fitCoordinateBounds(coords);
  }

  function fitRacePanelBounds(path, exploredIds, nodeById) {
    if (!map) return;
    const routeCoords = (path || []).map(function (id) { return nodeById[id]; }).filter(Boolean).map(coord);
    const exploredCoords = (exploredIds || []).map(function (id) { return nodeById[id]; }).filter(Boolean).map(coord);
    const coords = routeCoords.concat(exploredCoords);
    if (coords.length < 2) return;
    fitCoordinateBounds(coords);
  }

  function fitCoordinateBounds(coords) {
    const bounds = coords.reduce(function (b, c) {
      return b.extend(c);
    }, new maplibregl.LngLatBounds(coords[0], coords[0]));
    map.fitBounds(bounds, {
      padding: { top: 54, bottom: 54, left: 54, right: 54 },
      maxZoom: 12.6,
      pitch: (timeThemes[currentThemeName] || timeThemes.Morning).pitch,
      bearing: (timeThemes[currentThemeName] || timeThemes.Morning).bearing,
      duration: cameraSettled ? 900 : 1500,
      essential: true
    });
    cameraSettled = true;
  }

  function updateRouteVisuals(path, nodeById) {
    const ids = path || [];
    const key = ids.join("|") + "|" + currentThemeName;
    if (!ids.length || ids.length < 2) {
      routeAnimationToken += 1;
      lastRouteKey = "";
      setSource("cf-route", empty);
      setSource("cf-route-tracer", empty);
      return;
    }

    const coords = ids.map(function (id) { return nodeById[id]; }).filter(Boolean);
    if (coords.length < 2) {
      setSource("cf-route", empty);
      setSource("cf-route-tracer", empty);
      return;
    }

    if (key === lastRouteKey) {
      setSource("cf-route", featureCollection([line(coords, { kind: "route" })]));
      setSource("cf-route-tracer", displayState.tracer ? tracerFeature(coords[coords.length - 1]) : empty);
      return;
    }

    lastRouteKey = key;
    animateRoute(coords);
  }

  function animateRoute(nodes) {
    const token = ++routeAnimationToken;
    if (!displayState.animations) {
      setSource("cf-route", featureCollection([line(nodes, { kind: "route" })]));
      setSource("cf-route-tracer", displayState.tracer ? pointFromCoord(coord(nodes[nodes.length - 1]), { role: "tracer" }) : empty);
      return;
    }
    const duration = Math.max(2100, Math.min(4200, nodes.length * 620));
    const start = performance.now();
    const segments = [];
    let total = 0;

    for (let i = 0; i < nodes.length - 1; i += 1) {
      const a = coord(nodes[i]);
      const b = coord(nodes[i + 1]);
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      segments.push({ a, b, len });
      total += len;
    }

    function frame(now) {
      if (token !== routeAnimationToken) return;
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const target = total * eased;
      const out = [segments[0].a];
      let walked = 0;
      let tracer = segments[0].a;

      for (const seg of segments) {
        if (walked + seg.len <= target) {
          out.push(seg.b);
          walked += seg.len;
          tracer = seg.b;
          continue;
        }
        const local = seg.len ? (target - walked) / seg.len : 1;
        tracer = [
          seg.a[0] + (seg.b[0] - seg.a[0]) * Math.max(0, Math.min(1, local)),
          seg.a[1] + (seg.b[1] - seg.a[1]) * Math.max(0, Math.min(1, local))
        ];
        out.push(tracer);
        break;
      }

      setSource("cf-route", featureCollection([{
        type: "Feature",
        properties: { kind: "route" },
        geometry: { type: "LineString", coordinates: out }
      }]));
      setSource("cf-route-tracer", displayState.tracer ? pointFromCoord(tracer, { role: "tracer" }) : empty);

      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        setSource("cf-route", featureCollection([line(nodes, { kind: "route" })]));
        setSource("cf-route-tracer", displayState.tracer ? pointFromCoord(coord(nodes[nodes.length - 1]), { role: "tracer" }) : empty);
      }
    }

    requestAnimationFrame(frame);
  }

  function updateRaceVisual(race, nodeById, forceReplay) {
    const dPath = race && race.dijkstra && race.dijkstra.path;
    const aPath = race && race.astar && race.astar.path;
    const dNodes = pathToNodes(dPath, nodeById);
    const aNodes = pathToNodes(aPath, nodeById);
    if (dNodes.length < 2 || aNodes.length < 2) {
      clearRaceVisual();
      return;
    }

    const key = [race.source, race.target, dPath.join("-"), aPath.join("-"), race.winner].join("|");
    const labels = raceLabelFeaturesFromCoords(dNodes.map(coord), aNodes.map(coord));
    setSource("cf-race-labels", labels);
    updateRaceCard(race);
    if (!forceReplay && key === lastRaceKey) {
      setSource("cf-race-dijkstra", featureCollection([line(dNodes, { algorithm: "Dijkstra" })]));
      setSource("cf-race-astar", featureCollection([line(aNodes, { algorithm: "A*" })]));
      setSource("cf-race-dijkstra-tracer", displayState.tracer ? tracerFeature(dNodes[dNodes.length - 1]) : empty);
      setSource("cf-race-astar-tracer", displayState.tracer ? tracerFeature(aNodes[aNodes.length - 1]) : empty);
      styleRaceWinner(race.winner, true);
      return;
    }

    lastRaceKey = key;
    if (!displayState.animations) {
      setSource("cf-race-dijkstra", featureCollection([line(dNodes, { algorithm: "Dijkstra" })]));
      setSource("cf-race-astar", featureCollection([line(aNodes, { algorithm: "A*" })]));
      setSource("cf-race-dijkstra-tracer", displayState.tracer ? tracerFeature(dNodes[dNodes.length - 1]) : empty);
      setSource("cf-race-astar-tracer", displayState.tracer ? tracerFeature(aNodes[aNodes.length - 1]) : empty);
      styleRaceWinner(race.winner, true);
      return;
    }

    animateRace(dNodes.map(coord), aNodes.map(coord), race);
  }

  function animateRace(dCoords, aCoords, race) {
    const token = ++raceAnimationToken;
    const duration = Math.max(2300, Math.min(4700, Math.max(dCoords.length, aCoords.length) * 720));
    const start = performance.now();
    setSource("cf-race-labels", raceLabelFeaturesFromCoords(dCoords, aCoords));
    styleRaceWinner(null, false);

    function frame(now) {
      if (token !== raceAnimationToken) return;
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 2.8);
      const dSlice = lineAtProgress(dCoords, eased);
      const aSlice = lineAtProgress(aCoords, eased);
      setSource("cf-race-dijkstra", featureCollection([{
        type: "Feature",
        properties: { algorithm: "Dijkstra" },
        geometry: { type: "LineString", coordinates: dSlice.coordinates }
      }]));
      setSource("cf-race-astar", featureCollection([{
        type: "Feature",
        properties: { algorithm: "A*" },
        geometry: { type: "LineString", coordinates: aSlice.coordinates }
      }]));
      setSource("cf-race-dijkstra-tracer", displayState.tracer ? pointFromCoord(dSlice.tracer, { algorithm: "Dijkstra" }) : empty);
      setSource("cf-race-astar-tracer", displayState.tracer ? pointFromCoord(aSlice.tracer, { algorithm: "A*" }) : empty);

      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        setSource("cf-race-dijkstra", featureCollection([line(dCoords, { algorithm: "Dijkstra" })]));
        setSource("cf-race-astar", featureCollection([line(aCoords, { algorithm: "A*" })]));
        styleRaceWinner(race && race.winner, true);
      }
    }

    requestAnimationFrame(frame);
  }

  function lineAtProgress(coords, progress) {
    if (!coords || coords.length < 2) return { coordinates: coords || [], tracer: coords && coords[0] };
    const segments = [];
    let total = 0;
    for (let i = 0; i < coords.length - 1; i += 1) {
      const a = coords[i];
      const b = coords[i + 1];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      segments.push({ a, b, len });
      total += len;
    }
    const target = total * Math.max(0, Math.min(1, progress));
    const out = [segments[0].a];
    let walked = 0;
    let tracer = segments[0].a;
    for (const seg of segments) {
      if (walked + seg.len <= target) {
        out.push(seg.b);
        walked += seg.len;
        tracer = seg.b;
        continue;
      }
      const local = seg.len ? (target - walked) / seg.len : 1;
      tracer = [
        seg.a[0] + (seg.b[0] - seg.a[0]) * Math.max(0, Math.min(1, local)),
        seg.a[1] + (seg.b[1] - seg.a[1]) * Math.max(0, Math.min(1, local))
      ];
      out.push(tracer);
      break;
    }
    return { coordinates: out, tracer };
  }

  function pathToNodes(path, nodeById) {
    return (path || []).map(function (id) { return nodeById[id]; }).filter(Boolean);
  }

  function raceLabelFeaturesFromCoords(dCoords, aCoords) {
    const features = [];
    const dLabel = lineAtProgress(dCoords, 0.36).tracer || dCoords[0];
    const aLabel = lineAtProgress(aCoords, 0.64).tracer || aCoords[0];
    if (dLabel) {
      features.push({
        type: "Feature",
        properties: { algorithm: "Dijkstra", label: "Dijkstra - cyan", sort: 1 },
        geometry: { type: "Point", coordinates: dLabel }
      });
    }
    if (aLabel) {
      features.push({
        type: "Feature",
        properties: { algorithm: "A*", label: "A* - gold", sort: 2 },
        geometry: { type: "Point", coordinates: aLabel }
      });
    }
    return featureCollection(features);
  }

  function styleRaceWinner(winner, finished) {
    const w = String(winner || "").toLowerCase();
    const astarWins = w.includes("a*") || w.includes("astar") || w === "a";
    const dijkstraWins = w.includes("dijkstra");
    setPaint("cf-race-dijkstra-line", "line-opacity", !finished || dijkstraWins || !astarWins ? 0.92 : 0.44);
    setPaint("cf-race-dijkstra-glow", "line-opacity", !finished || dijkstraWins ? 0.25 : 0.10);
    setPaint("cf-race-astar-line", "line-opacity", !finished || astarWins || !dijkstraWins ? 0.94 : 0.44);
    setPaint("cf-race-astar-glow", "line-opacity", !finished || astarWins ? 0.30 : 0.10);
  }

  function updateRaceCard(race) {
    const card = document.getElementById("race-card");
    if (card) card.classList.remove("visible");
  }

  function formatRaceMetric(result) {
    const cost = result.cost == null ? "n/a" : Number(result.cost).toFixed(1) + " km";
    const frames = result.n_frames == null ? 0 : Number(result.n_frames);
    return cost + " / " + frames + " steps";
  }

  function clearRaceVisual() {
    raceAnimationToken += 1;
    lastRaceKey = "";
    setSource("cf-race-dijkstra", empty);
    setSource("cf-race-astar", empty);
    setSource("cf-race-explored", empty);
    setSource("cf-race-dijkstra-tracer", empty);
    setSource("cf-race-astar-tracer", empty);
    setSource("cf-race-labels", empty);
    const card = document.getElementById("race-card");
    if (card) card.classList.remove("visible");
  }

  function activePathFor(data, scenario) {
    if (scenario && scenario.after_path) return scenario.after_path;
    if (data.active_mode === "emergency" && data.emergency && data.emergency.path) return data.emergency.path;
    if (data.active_mode === "route" && data.route && data.route.path) return data.route.path;
    return null;
  }

  function updateVisibility(mode, hasRoute, hasScenario, hasMst, hasRace) {
    const inTransit = mode === "transit";
    const inMaintain = mode === "maintain";
    const inRace = mode === "race_lab" || mode === "race_panel";
    const trafficRelevant = mode === "route" || mode === "emergency" || inRace || hasScenario;
    setLayerVisibility(["cf-bus", "cf-metro"], inTransit);
    setLayerVisibility(["cf-maintain"], inMaintain);
    setLayerVisibility(["cf-traffic"], trafficRelevant);
    setLayerVisibility(["cf-mst-line", "cf-mst-glow"], mode === "network" && hasMst);
    setLayerVisibility(["cf-route-glow", "cf-route-line", "cf-route-tracer"], hasRoute);
    setLayerVisibility(["cf-start-end", "cf-start-end-halo"], hasRoute || (inRace && hasRace));
    setLayerVisibility(["cf-active-route-nodes", "cf-active-route-nodes-halo", "cf-node-labels"], hasRoute);
    setLayerVisibility(["cf-scenario-before", "cf-scenario-after", "cf-affected"], hasScenario);
    setLayerVisibility([
      "cf-race-dijkstra-glow", "cf-race-dijkstra-casing", "cf-race-dijkstra-line",
      "cf-race-astar-glow", "cf-race-astar-casing", "cf-race-astar-line",
      "cf-race-explored-glow", "cf-race-explored-dot",
      "cf-race-explored-edges-casing", "cf-race-explored-edges-line",
      "cf-race-dijkstra-tracer", "cf-race-astar-tracer", "cf-race-labels"
    ], inRace && hasRace);
  }

  function applyModeStyling(mode, hasScenario) {
    const theme = timeThemes[currentThemeName] || timeThemes.Morning;
    const isEmergency = mode === "emergency";
    const routeColor = hasScenario
      ? "#2bc9d2"
      : isEmergency
        ? (currentThemeName === "Night" ? "#ff7668" : "#e74f42")
        : theme.route;
    setPaint("cf-route-line", "line-color", [
      "interpolate", ["linear"], ["line-progress"],
      0, isEmergency ? "#ffffff" : "#d7a448",
      0.22, routeColor,
      1, routeColor
    ]);
    setPaint("cf-route-glow", "line-color", routeColor);
    setPaint("cf-route-glow", "line-opacity", isEmergency ? 0.34 : theme.routeGlow);
    setPaint("cf-route-tracer", "circle-stroke-color", routeColor);
    setPaint("cf-roads-base", "line-opacity",
      mode === "route" || mode === "emergency" || mode === "race_lab" ? Math.max(0.09, theme.roadOpacity * 0.72) : theme.roadOpacity);
  }

  function updateStatus(data) {
    const mode = String(data.active_mode || "route");
    const clock = data.clock || "06:00";
    const tod = data.time_of_day || "Morning";
    const route = data.active_mode === "race_lab" && data.race
      ? "race overlay ready"
      : data.route && data.route.travel_time_min
      ? "ETA " + Number(data.route.travel_time_min).toFixed(1) + " min"
      : "network live";
    const scenario = data.scenario ? " - " + data.scenario.label : "";
    setText("map-status", clock + " " + tod + " - " + mode.toUpperCase() + " - " + route + scenario);
    setText("map-hour", clock);
    setText("map-period", tod);
  }

  function updateRouteCard(data) {
    const card = document.getElementById("route-card");
    if (!card) return;
    const route = data.route;
    const scenario = data.scenario;
    const race = data.active_mode === "race_lab" ? data.race : null;
    const emergency = data.active_mode === "emergency" ? data.emergency : null;
    if (scenario) {
      const before = scenario.before_min == null ? "unreachable" : Number(scenario.before_min).toFixed(1) + " min";
      const after = scenario.after_min == null ? "blocked" : Number(scenario.after_min).toFixed(1) + " min";
      setPrimaryCard(
        scenario.label + " - Before / After",
        scenario.src_name + " to " + scenario.dst_name + " - " + before + " -> " + after,
        scenario.delta_min == null ? "Scenario changes active" : signed(scenario.delta_min) + " min",
        "scenario"
      );
      return;
    }
    if (race && race.dijkstra && race.astar) {
      const d = race.dijkstra;
      const a = race.astar;
      setPrimaryCard(
        (race.winner || "Race") + " Wins - Dijkstra vs A*",
        "Cyan Dijkstra: " + formatRaceMetric(d) + " / Gold A*: " + formatRaceMetric(a),
        "Node speedup " + (race.speedup_pct_nodes == null ? "n/a" : Number(race.speedup_pct_nodes).toFixed(1) + "%"),
        "race"
      );
      return;
    }
    if (emergency && emergency.path && emergency.path.length > 1) {
      const names = Object.fromEntries((data.nodes || []).map(function (n) { return [n.id, n.name || n.id]; }));
      const src = emergency.path[0];
      const dst = emergency.path[emergency.path.length - 1];
      const eta = emergency.eta_minutes == null ? "ETA unavailable" : Number(emergency.eta_minutes).toFixed(1) + " min";
      setPrimaryCard(
        "Emergency Dispatch",
        (names[src] || src) + " to " + (names[dst] || dst) + " - " + eta,
        "A* dispatch - " + String(emergency.facility_type || "nearest facility"),
        "emergency"
      );
      return;
    }
    if (data.active_mode === "network" && data.mst && data.mst.selected_edges && data.mst.selected_edges.length) {
      const stats = data.mst.stats || {};
      const cost = stats.total_cost_million_egp == null ? "cost pending" : Number(stats.total_cost_million_egp).toFixed(1) + "M EGP";
      const covered = stats.covered_nodes == null ? "" : " - " + stats.covered_nodes + " nodes covered";
      setPrimaryCard(
        "Network Structure Built",
        String(data.mst.algo || "MST").toUpperCase() + " - " + data.mst.selected_edges.length + " edges" + covered,
        cost,
        "network"
      );
      return;
    }
    if (data.active_mode === "maintain" && data.maintain && data.maintain.selected_roads) {
      const roads = data.maintain.selected_roads.length;
      const value = data.maintain.total_value == null ? "maintenance priorities active" : "benefit " + Number(data.maintain.total_value).toFixed(1);
      setPrimaryCard("Maintenance Priority", roads + " roads selected for repair", value, "maintain");
      return;
    }
    if (data.active_mode === "transit" && data.transit) {
      const kind = String(data.transit.kind || "transit");
      const summary = kind === "multimodal" && data.transit.total_min != null
        ? "Multimodal route - " + Number(data.transit.total_min).toFixed(1) + " min"
        : kind === "transfers" && data.transit.ranking
          ? "Transfer pressure - " + data.transit.ranking.length + " hubs ranked"
          : kind.toUpperCase() + " optimization active";
      setPrimaryCard("Transit Analysis", summary, "Metro / bus overlay active", "transit");
      return;
    }
    if (data.active_mode === "route" && route) {
      setPrimaryCard(
        "Selected Route",
        (route.src || "From") + " to " + (route.dst || "To") + " - " + Number(route.travel_time_min || 0).toFixed(1) + " min",
        data.time_of_day + " traffic overlay active",
        "route"
      );
      return;
    }
    card.classList.remove("visible");
  }

  function setPrimaryCard(title, meta, impact, kind) {
    const card = document.getElementById("route-card");
    if (!card) return;
    card.classList.add("visible");
    card.dataset.kind = kind || "route";
    setText("route-title", title || "CairoFlow Result");
    setText("route-meta", meta || "");
    setText("route-impact", impact || "");
  }

  function installControls() {
    const displayToggle = document.getElementById("display-toggle");
    const displayPanel = document.getElementById("display-panel");
    function setDisplayPanel(open) {
      if (!displayPanel) return;
      displayPanel.classList.toggle("open", Boolean(open));
      if (displayToggle) displayToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
    if (displayToggle && displayPanel) {
      displayToggle.addEventListener("click", function (event) {
        event.stopPropagation();
        setDisplayPanel(!displayPanel.classList.contains("open"));
      });
      displayPanel.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      document.addEventListener("click", function () {
        setDisplayPanel(false);
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") setDisplayPanel(false);
      });
    }
    document.querySelectorAll("[data-camera='cairo']").forEach(function (btn) {
      btn.addEventListener("click", resetCamera);
    });
    document.querySelectorAll("[data-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setTimeMode(btn.dataset.preset, true);
      });
    });
    document.querySelectorAll("[data-display-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setDisplayPreset(btn.dataset.displayPreset || "presentation");
      });
    });
    document.querySelectorAll("[data-display-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const key = btn.dataset.displayToggle;
        displayState[key] = !displayState[key];
        displayState.preset = "custom";
        saveDisplayState();
        refreshDisplayControls();
        if (latestState && mapReady) updateMap(latestState);
        else applyDisplayState();
      });
    });
    refreshDisplayControls();
  }

  function defaultDisplayState() {
    return {
      preset: "presentation",
      hud: true,
      cards: true,
      labels: true,
      districts: true,
      facilities: true,
      graph: true,
      traffic: true,
      animations: true,
      tracer: true,
      scenario: true,
      legend: true
    };
  }

  function loadDisplayState() {
    try {
      const saved = JSON.parse(localStorage.getItem("cairoflow-map-display") || "{}");
      return Object.assign(defaultDisplayState(), saved || {});
    } catch (_) {
      return defaultDisplayState();
    }
  }

  function saveDisplayState() {
    try { localStorage.setItem("cairoflow-map-display", JSON.stringify(displayState)); } catch (_) {}
  }

  function setDisplayPreset(name) {
    const presets = {
      minimal: {
        preset: "minimal",
        hud: false,
        cards: false,
        labels: false,
        districts: false,
        facilities: true,
        graph: false,
        traffic: false,
        animations: false,
        tracer: false,
        scenario: true,
        legend: false
      },
      presentation: defaultDisplayState(),
      analysis: {
        preset: "analysis",
        hud: true,
        cards: true,
        labels: true,
        districts: true,
        facilities: true,
        graph: true,
        traffic: true,
        animations: true,
        tracer: true,
        scenario: true,
        legend: true
      }
    };
    displayState = Object.assign(defaultDisplayState(), presets[name] || presets.presentation);
    saveDisplayState();
    refreshDisplayControls();
    if (latestState && mapReady) updateMap(latestState);
    else applyDisplayState();
  }

  function refreshDisplayControls() {
    const label = document.getElementById("display-mode-label");
    if (label) label.textContent = displayState.preset === "analysis" ? "Analysis" : displayState.preset === "minimal" ? "Minimal" : displayState.preset === "custom" ? "Custom" : "Presentation";
    document.querySelectorAll("[data-display-preset]").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.displayPreset === displayState.preset);
    });
    document.querySelectorAll("[data-display-toggle]").forEach(function (btn) {
      btn.classList.toggle("active", Boolean(displayState[btn.dataset.displayToggle]));
    });
  }

  function applyDisplayState() {
    document.body.classList.toggle("hide-hud", !displayState.hud);
    document.body.classList.toggle("hide-route-card", !displayState.cards);
    document.body.classList.toggle("hide-race-card", !displayState.cards);
    document.body.classList.toggle("hide-legend", !displayState.legend);

    if (!displayState.graph) setLayerVisibility(["cf-roads-base"], false);
    else setLayerVisibility(["cf-roads-base"], true);
    if (!displayState.traffic) setLayerVisibility(["cf-traffic"], false);
    if (!displayState.tracer) setLayerVisibility(["cf-route-tracer", "cf-race-dijkstra-tracer", "cf-race-astar-tracer"], false);
    if (!displayState.facilities) setLayerVisibility(["cf-facility-halo", "cf-facilities", "cf-facility-core", "cf-facility-icons"], false);
    else setLayerVisibility(["cf-facility-halo", "cf-facilities", "cf-facility-core", "cf-facility-icons"], true);
    if (!displayState.districts) {
      setBaseLabelsVisible(false);
      setLayerVisibility(["cf-cairo-labels"], false);
    } else {
      setBaseLabelsVisible(true);
      setLayerVisibility(["cf-cairo-labels"], true);
    }
    if (!displayState.labels) {
      setLayerVisibility(["cf-node-labels", "cf-race-labels"], false);
    }
    if (!displayState.scenario) setLayerVisibility(["cf-scenario-before", "cf-scenario-after", "cf-affected"], false);
    refreshDisplayControls();
  }

  function setBaseLabelsVisible(visible) {
    const layers = (map && map.getStyle() && map.getStyle().layers) || [];
    layers.forEach(function (layer) {
      if (!layer || customLayerIds.includes(layer.id) || String(layer.id || "").startsWith("cf-")) return;
      if (layer.type !== "symbol" || !layer.layout || !layer.layout["text-field"]) return;
      try { map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none"); } catch (_) {}
    });
  }

  function setUiTheme(theme) {
    const mode = theme === "light" ? "light" : "dark";
    document.body.classList.toggle("ui-light", mode === "light");
    document.body.classList.toggle("ui-dark", mode === "dark");
  }

  function resetCamera() {
    if (!map) return;
    const theme = timeThemes[currentThemeName] || timeThemes.Morning;
    map.flyTo({
      center: CAIRO,
      zoom: 10.85,
      pitch: theme.pitch,
      bearing: theme.bearing,
      duration: cameraSettled ? 1100 : 1900,
      essential: true
    });
    cameraSettled = true;
  }

  function syncPresetButtons(label) {
    document.querySelectorAll("[data-preset]").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.preset === label);
    });
  }

  function firstSymbolLayerId() {
    const layers = map.getStyle().layers || [];
    const first = layers.find(function (layer) { return layer.type === "symbol"; });
    return first && first.id;
  }

  function setPaint(layer, prop, value) {
    if (map && map.getLayer(layer)) map.setPaintProperty(layer, prop, value);
  }

  function setLayerVisibility(ids, visible) {
    ids.forEach(function (id) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    });
  }

  function setSource(id, data) {
    const src = map.getSource(id);
    if (src) src.setData(data || empty);
  }

  function featureCollection(features) {
    return { type: "FeatureCollection", features: features || [] };
  }

  function line(nodes, props) {
    return {
      type: "Feature",
      properties: props || {},
      geometry: { type: "LineString", coordinates: nodes.map(coord) }
    };
  }

  function pathFeature(path, nodeById, props) {
    if (!path || path.length < 2) return empty;
    const coords = path.map(function (id) { return nodeById[id]; }).filter(Boolean);
    if (coords.length < 2) return empty;
    return featureCollection([line(coords, props)]);
  }

  function pathFeaturesFromEdges(edges, nodeById, props) {
    return featureCollection((edges || []).map(function (e) {
      const from = Array.isArray(e) ? e[0] : e.from;
      const to = Array.isArray(e) ? e[1] : e.to;
      const a = nodeById[from];
      const b = nodeById[to];
      return a && b ? line([a, b], props) : null;
    }).filter(Boolean));
  }

  function startEndFeatures(route, nodeById, path) {
    const out = [];
    const src = route && route.src ? route.src : path && path[0];
    const dst = route && route.dst ? route.dst : path && path[path.length - 1];
    const race = Boolean(route && route.race);
    if (!src || !dst) return empty;
    if (nodeById[src]) out.push(point(nodeById[src], { role: "start", race: race }));
    if (nodeById[dst]) out.push(point(nodeById[dst], { role: "end", race: race }));
    return featureCollection(out);
  }

  function activeRouteNodeFeatures(path, nodeById) {
    if (!path || path.length < 2) return empty;
    return featureCollection(path.map(function (id, idx) {
      const n = nodeById[id];
      if (!n) return null;
      const role = idx === 0 ? "start" : idx === path.length - 1 ? "end" : "middle";
      return point(n, {
        id: n.id,
        name: n.name,
        type: n.type || n.kind,
        role,
        population: Number(n.population || 0)
      });
    }).filter(Boolean));
  }

  function transitFeatures(routes, nodeById, field) {
    return featureCollection((routes || []).flatMap(function (route) {
      const stops = route[field] || [];
      const out = [];
      for (let i = 0; i < stops.length - 1; i += 1) {
        const a = nodeById[stops[i]];
        const b = nodeById[stops[i + 1]];
        if (a && b) out.push(line([a, b], { id: route.route_id || route.line_id }));
      }
      return out;
    }));
  }

  function metroFeatures(lines, nodeById) {
    const colors = ["#e05543", "#d7a448", "#7d63ff", "#21ad68", "#20cad7"];
    return featureCollection((lines || []).flatMap(function (route, idx) {
      const stops = route.stations || [];
      const out = [];
      for (let i = 0; i < stops.length - 1; i += 1) {
        const a = nodeById[stops[i]];
        const b = nodeById[stops[i + 1]];
        if (a && b) out.push(line([a, b], { id: route.line_id, color: colors[idx % colors.length] }));
      }
      return out;
    }));
  }

  function maintainFeatures(data, nodeById) {
    const selected = data.maintain && data.maintain.selected_roads ? data.maintain.selected_roads : [];
    return pathFeaturesFromEdges(selected.map(function (r) { return [String(r.from), String(r.to)]; }), nodeById, { kind: "maintain" });
  }

  function pointFeatures(nodes) {
    return featureCollection((nodes || []).map(function (n) {
      const type = String(n.type || "").toLowerCase();
      const population = Number(n.population || 0);
      return point(n, {
        id: n.id,
        name: n.name,
        type: n.type,
        kind: n.kind,
        population,
        importance: Math.max(0.18, Math.min(1, population / 2400000)),
        isCentral: ["Downtown Cairo", "Giza", "Nasr City", "Maadi", "New Cairo"].includes(String(n.name || "")),
        isHospital: type.includes("hospital") || type.includes("medical"),
        isTransit: type.includes("transit") || type.includes("rail") || type.includes("metro"),
        isAirport: type.includes("airport") || String(n.name || "").toLowerCase().includes("airport"),
        icon: facilityIcon(n)
      });
    }));
  }

  function facilityIcon(n) {
    const type = String(n.type || "").toLowerCase();
    const name = String(n.name || "").toLowerCase();
    if (type.includes("hospital") || type.includes("medical")) return "H";
    if (type.includes("airport") || name.includes("airport")) return "A";
    if (type.includes("rail") || type.includes("station") || name.includes("ramses")) return "R";
    if (type.includes("metro") || type.includes("transit") || type.includes("bus")) return "T";
    if (type.includes("government") || type.includes("civic")) return "G";
    return "F";
  }

  function point(n, props) {
    return {
      type: "Feature",
      properties: props || {},
      geometry: { type: "Point", coordinates: [Number(n.lon), Number(n.lat)] }
    };
  }

  function pointFromCoord(c, props) {
    if (!c || c.length < 2) return empty;
    return featureCollection([pointCoordFeature(c, props)]);
  }

  function pointCoordFeature(c, props) {
    return {
      type: "Feature",
      properties: props || {},
      geometry: { type: "Point", coordinates: [Number(c[0]), Number(c[1])] }
    };
  }

  function tracerFeature(n) {
    return pointFromCoord(coord(n), { role: "tracer" });
  }

  function coord(n) {
    return Array.isArray(n) ? [Number(n[0]), Number(n[1])] : [Number(n.lon), Number(n.lat)];
  }

  function areaFeatures(nodes) {
    return featureCollection((nodes || []).map(function (n) {
      const radius = n.kind === "facility" ? 0.0038 : 0.0055 + Math.min(0.008, Number(n.population || 0) / 250000000);
      const height = n.kind === "facility" ? 48 : 22 + Math.min(95, Number(n.population || 0) / 18000);
      return {
        type: "Feature",
        properties: { id: n.id, kind: n.kind, height },
        geometry: circlePolygon(Number(n.lon), Number(n.lat), radius, 18)
      };
    }));
  }

  function circlePolygon(lon, lat, radius, steps) {
    const coords = [];
    for (let i = 0; i <= steps; i += 1) {
      const angle = Math.PI * 2 * i / steps;
      coords.push([lon + Math.cos(angle) * radius, lat + Math.sin(angle) * radius]);
    }
    return { type: "Polygon", coordinates: [coords] };
  }

  function edgeKey(edge) {
    return [String(edge[0]), String(edge[1])].sort().join("|");
  }

  function signed(value) {
    const n = Number(value);
    return (n > 0 ? "+" : "") + n.toFixed(1);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function formatCompact(value) {
    return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[ch];
    });
  }

  function showWarning(text) {
    const warning = document.getElementById("map-warning");
    if (warning) {
      warning.textContent = text;
      warning.classList.add("visible");
    }
  }

  function hideWarning() {
    const warning = document.getElementById("map-warning");
    if (warning) warning.classList.remove("visible");
  }

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-map-state") return;
    setUiTheme(msg.data && msg.data.ui_theme);
    if (racePanelKind) {
      updateRacePanelMap(msg.data, racePanelKind);
      return;
    }
    updateMap(msg.data);
  });

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-race-panel-state") return;
    setUiTheme(msg.data && msg.data.ui_theme);
    updateRacePanelMap(msg.data, msg.panel || racePanelKind);
  });

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-ui-theme") return;
    setUiTheme(msg.theme);
  });

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-race-visual") return;
    if (!latestState || !latestState.nodes) return;
    const nodeById = Object.fromEntries((latestState.nodes || []).map(function (n) { return [n.id, n]; }));
    updateRaceVisual(msg.race || (latestState && latestState.race), nodeById, true);
    applyDisplayState();
  });

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-race-panel-replay") return;
    const data = msg.data || latestState;
    if (!data) return;
    updateRacePanelMap(data, msg.panel || racePanelKind, true);
  });

  window.addEventListener("message", function (event) {
    const msg = event && event.data;
    if (!msg || msg.type !== "cairoflow-map-resize") return;
    if (!map) return;
    map.resize();
    setTimeout(function () { if (map) map.resize(); }, 160);
  });
})();
