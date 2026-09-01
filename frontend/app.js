/**
 * Melbourne Multimodal Transit Desert & Equity Platform — 3D Geospatial Engine
 * Powered by MapLibre GL JS, DuckDB, r5py, and Uber H3.
 */

// Global State
const state = {
  activeMetric: 'tdi', // 'tdi' | 'vulnerability' | 'accessibility'
  heightScale: 1.5,
  minTDI: 0.34,
  selectedSuburb: '',
  geojsonData: null,
  topSuburbs: [],
  pois: [],
  systemStats: null,
  is3D: true,
  selectedHexId: null
};

// Base Map Configuration (CartoDB Dark Matter)
const CARTODB_DARK_STYLE = {
  version: 8,
  sources: {
    'carto-dark-tiles': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
      ],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors, &copy; CARTO'
    }
  },
  layers: [
    {
      id: 'carto-dark-base',
      type: 'raster',
      source: 'carto-dark-tiles',
      minzoom: 0,
      maxzoom: 20
    }
  ]
};

// Metric Visual Configurations (Color Ramps, Legends, Height Multipliers)
const METRIC_CONFIGS = {
  tdi: {
    title: 'Transit Desert Index (TDI)',
    unit: 'High Disadvantage \u00d7 Low Access',
    baseMultiplier: 2500,
    legendGradient: 'linear-gradient(90deg, #00f5a0 0%, #f6d365 30%, #ff7849 60%, #ff0844 85%, #e024c3 100%)',
    legendLabels: ['Low (0.0)', 'Moderate (0.4)', 'Critical (0.8+)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'tdi'],
      0.00, '#00f5a0',
      0.35, '#f6d365',
      0.50, '#ff7849',
      0.65, '#ff0844',
      0.85, '#e024c3'
    ]
  },
  vulnerability: {
    title: 'Demographic Need / Vulnerability (V_i)',
    unit: '60% SEIFA Disadvantage + 40% Density',
    baseMultiplier: 2500,
    legendGradient: 'linear-gradient(90deg, #38ef7d 0%, #4facfe 35%, #9b51e0 70%, #ff3366 100%)',
    legendLabels: ['Low Need (0.0)', 'Medium (0.4)', 'Severe Need (0.9)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'vulnerability'],
      0.00, '#38ef7d',
      0.25, '#4facfe',
      0.50, '#9b51e0',
      0.80, '#ff3366'
    ]
  },
  accessibility: {
    title: 'Multimodal Transit Accessibility (A_i)',
    unit: 'Linear Decay Travel Time (RMH, Monash, Chadstone)',
    baseMultiplier: 3500,
    legendGradient: 'linear-gradient(90deg, #1e293b 0%, #0284c7 35%, #00f2fe 70%, #00f5a0 100%)',
    legendLabels: ['Isolated (0.0)', 'Moderate (0.2)', 'High Access (0.4+)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'accessibility'],
      0.00, '#1e293b',
      0.05, '#0284c7',
      0.15, '#00f2fe',
      0.35, '#00f5a0'
    ]
  }
};

// Initialize MapLibre GL Map
const map = new maplibregl.Map({
  container: 'map',
  style: CARTODB_DARK_STYLE,
  center: [144.9631, -37.8136], // Central Melbourne
  zoom: 10.2,
  pitch: 45,
  bearing: -15,
  antialias: true
});

// Map Load Event
map.on('load', async () => {
  // Initialize Lucide icons
  if (window.lucide) {
    window.lucide.createIcons();
  }

  // Load API Data in Parallel
  await Promise.all([
    fetchStats(),
    fetchPOIs(),
    fetchTopSuburbs(),
    fetchTransitDeserts()
  ]);

  setupUIListeners();
  setupMapInteractivity();
});

// --- API Data Fetchers ---

async function fetchStats() {
  try {
    const res = await fetch('/api/v1/stats');
    if (!res.ok) throw new Error('Stats API failed');
    const data = await res.json();
    state.systemStats = data;

    // Update Header Badges
    document.getElementById('statAnalyzedCells').textContent = data.total_h3_cells.toLocaleString();
    document.getElementById('statDesertCells').textContent = data.transit_desert_cells_p80.toLocaleString();
    document.getElementById('statDesertPop').textContent = data.deserts_affected_population.toLocaleString();
  } catch (err) {
    console.error('Error fetching stats:', err);
  }
}

async function fetchPOIs() {
  try {
    const res = await fetch('/api/v1/pois');
    if (!res.ok) throw new Error('POIs API failed');
    const pois = await res.json();
    state.pois = pois;

    // Add 3D Glowing POI Markers on Map
    pois.forEach(poi => {
      const el = document.createElement('div');
      const catClass = poi.category === 'Healthcare' ? 'hospital' : (poi.category === 'Commercial' ? 'retail' : '');
      el.className = `poi-marker ${catClass}`;
      
      const icon = poi.category === 'Healthcare' ? '&#x1F3E5;' : (poi.category === 'Commercial' ? '&#x1F6CD;' : '&#x1F393;');
      el.innerHTML = `<span>${icon}</span>`;

      const popup = new maplibregl.Popup({ offset: 25, closeButton: false })
        .setHTML(`
          <div style="padding: 6px; font-family: sans-serif; color: #fff; background: #121826;">
            <strong style="color: #00f2fe;">${poi.name}</strong><br/>
            <span style="font-size: 11px; color: #94a3b8;">${poi.category} Hub</span><br/>
            <span style="font-size: 11px; color: #00f5a0;">${poi.reachable_h3_count.toLocaleString()} reachable hex cells</span>
          </div>
        `);

      new maplibregl.Marker({ element: el })
        .setLngLat([poi.lon, poi.lat])
        .setPopup(popup)
        .addTo(map);
    });
  } catch (err) {
    console.error('Error fetching POIs:', err);
  }
}

async function fetchTopSuburbs() {
  try {
    const res = await fetch('/api/v1/suburbs/top?limit=15&min_pop=500');
    if (!res.ok) throw new Error('Top Suburbs API failed');
    const suburbs = await res.json();
    state.topSuburbs = suburbs;

    renderLeaderboard(suburbs);
    populateSuburbDropdown(suburbs);
  } catch (err) {
    console.error('Error fetching top suburbs:', err);
    document.getElementById('leaderboardList').innerHTML = `<div class="loading-state">Failed to load suburb ranking.</div>`;
  }
}

async function fetchTransitDeserts() {
  try {
    const res = await fetch('/api/v1/transit-deserts?only_deserts=true&limit=25000');
    if (!res.ok) throw new Error('Transit Deserts GeoJSON API failed');
    const geojson = await res.json();
    state.geojsonData = geojson;

    addHexagonLayer(geojson);
  } catch (err) {
    console.error('Error loading transit deserts GeoJSON:', err);
  }
}

// --- Map Layer Setup ---

function addHexagonLayer(geojson) {
  if (map.getSource('transit-deserts-source')) {
    map.getSource('transit-deserts-source').setData(geojson);
    return;
  }

  // 1. Add GeoJSON Source
  map.addSource('transit-deserts-source', {
    type: 'geojson',
    data: geojson,
    generateId: true
  });

  const cfg = METRIC_CONFIGS[state.activeMetric];

  // 2. Add 3D Fill Extrusion Layer
  map.addLayer({
    id: 'h3-3d-deserts',
    type: 'fill-extrusion',
    source: 'transit-deserts-source',
    paint: {
      'fill-extrusion-color': cfg.colorExpression,
      'fill-extrusion-height': [
        '*',
        ['get', state.activeMetric],
        cfg.baseMultiplier * state.heightScale
      ],
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.85,
      'fill-extrusion-vertical-gradient': true
    }
  });

  // Apply Initial Filter
  applyFilters();
}

function updateLayerStyling() {
  if (!map.getLayer('h3-3d-deserts')) return;

  const cfg = METRIC_CONFIGS[state.activeMetric];

  // Update Extrusion Color
  map.setPaintProperty('h3-3d-deserts', 'fill-extrusion-color', cfg.colorExpression);

  // Update Extrusion Height
  map.setPaintProperty('h3-3d-deserts', 'fill-extrusion-height', [
    '*',
    ['get', state.activeMetric],
    cfg.baseMultiplier * state.heightScale
  ]);

  // Update Legend
  document.getElementById('legendTitle').textContent = cfg.title;
  document.getElementById('legendUnit').textContent = cfg.unit;
  document.getElementById('legendBar').style.background = cfg.legendGradient;
  document.getElementById('legendLabels').innerHTML = `
    <span>${cfg.legendLabels[0]}</span>
    <span>${cfg.legendLabels[1]}</span>
    <span>${cfg.legendLabels[2]}</span>
  `;
}

function applyFilters() {
  if (!map.getLayer('h3-3d-deserts')) return;

  const filters = ['all'];

  // Min TDI filter
  if (state.minTDI > 0) {
    filters.push(['>=', ['get', 'tdi'], state.minTDI]);
  }

  // Suburb filter
  if (state.selectedSuburb) {
    filters.push(['==', ['get', 'suburb_name'], state.selectedSuburb]);
  }

  if (filters.length > 1) {
    map.setFilter('h3-3d-deserts', filters);
  } else {
    map.setFilter('h3-3d-deserts', null);
  }
}

// --- Interactivity & Inspector ---

function setupMapInteractivity() {
  // Cursor pointer on hover
  map.on('mouseenter', 'h3-3d-deserts', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'h3-3d-deserts', () => {
    map.getCanvas().style.cursor = '';
  });

  // Click on hexagon
  map.on('click', 'h3-3d-deserts', (e) => {
    if (!e.features || !e.features[0]) return;
    const props = e.features[0].properties;
    renderInspector(props);
  });

  // Hover on hexagon (update inspector if open)
  map.on('mousemove', 'h3-3d-deserts', (e) => {
    if (!e.features || !e.features[0]) return;
    const props = e.features[0].properties;
    renderInspector(props);
  });
}

function renderInspector(props) {
  const container = document.getElementById('inspectorBody');
  const tdiPercent = (props.tdi * 100).toFixed(1);
  const vulnPercent = (props.vulnerability * 100).toFixed(1);
  const accessPercent = (props.accessibility * 100).toFixed(1);

  container.innerHTML = `
    <div class="inspector-suburb-title">${props.suburb_name || 'Melbourne SA2'}</div>
    <div class="inspector-sa1">SA1: <code>${props.sa1_code || 'N/A'}</code> &bull; H3: <code>${props.h3_index}</code></div>

    <div class="gauge-row">
      <div class="gauge-card">
        <span class="gauge-label">Transit Desert</span>
        <div class="gauge-val text-neon-red">${props.tdi.toFixed(3)}</div>
      </div>
      <div class="gauge-card">
        <span class="gauge-label">Vulnerability</span>
        <div class="gauge-val text-neon-purple">${props.vulnerability.toFixed(3)}</div>
      </div>
      <div class="gauge-card">
        <span class="gauge-label">Accessibility</span>
        <div class="gauge-val text-neon-cyan">${props.accessibility.toFixed(3)}</div>
      </div>
    </div>

    <div style="display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; color: #94a3b8; margin-bottom: 12px;">
      <div style="display: flex; justify-content: space-between;">
        <span>SEIFA Disadvantage Decile:</span>
        <strong style="color: ${props.seifa_irsd_decile <= 2 ? '#ff3366' : '#00f5a0'};">Decile ${props.seifa_irsd_decile || 'N/A'} (1=Worst)</strong>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span>Population Density:</span>
        <strong style="color: #fff;">${Number(props.pop_density).toLocaleString()} / km&sup2;</strong>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span>Estimated Population:</span>
        <strong style="color: #fff;">${Number(props.population).toLocaleString()} residents</strong>
      </div>
    </div>

    <div class="poi-travel-times">
      <span style="font-size: 0.72rem; font-weight: 600; text-transform: uppercase; color: #64748b;">Transit Travel Times (08:00 AM Peak)</span>
      
      <div class="poi-row">
        <span class="poi-badge">&#x1F3E5; Royal Melb Hospital</span>
        <span class="poi-time">${props.tt_rmh < 45 ? `${props.tt_rmh} min` : '<span style="color:#ff3366;">&gt;45 min (Cutoff)</span>'}</span>
      </div>

      <div class="poi-row">
        <span class="poi-badge">&#x1F393; Monash Univ Clayton</span>
        <span class="poi-time">${props.tt_monash < 45 ? `${props.tt_monash} min` : '<span style="color:#ff3366;">&gt;45 min (Cutoff)</span>'}</span>
      </div>

      <div class="poi-row">
        <span class="poi-badge">&#x1F6CD; Chadstone Shopping Ctr</span>
        <span class="poi-time">${props.tt_chadstone < 45 ? `${props.tt_chadstone} min` : '<span style="color:#ff3366;">&gt;45 min (Cutoff)</span>'}</span>
      </div>
    </div>
  `;
}

// --- Leaderboard Rendering ---

function renderLeaderboard(suburbs) {
  const container = document.getElementById('leaderboardList');
  container.innerHTML = '';

  suburbs.forEach((sub, idx) => {
    const el = document.createElement('div');
    el.className = 'leader-item';
    el.innerHTML = `
      <div class="leader-rank-title">
        <span class="rank-badge">#${idx + 1}</span>
        <div class="suburb-meta">
          <span class="suburb-name">${sub.suburb_name}</span>
          <span class="suburb-pop">${Number(sub.estimated_resident_pop).toLocaleString()} pop &bull; Decile ${sub.avg_seifa_decile}</span>
        </div>
      </div>
      <div class="tdi-pill">${sub.avg_desert_index.toFixed(3)}</div>
    `;

    el.addEventListener('click', () => {
      // Fly map camera to suburb centroid
      map.flyTo({
        center: [sub.centroid_lng, sub.centroid_lat],
        zoom: 12.8,
        pitch: 55,
        bearing: -20,
        speed: 1.2,
        curve: 1.4
      });

      // Highlight in dropdown
      document.getElementById('selectSuburbFilter').value = sub.suburb_name;
      state.selectedSuburb = sub.suburb_name;
      applyFilters();
    });

    container.appendChild(el);
  });
}

function populateSuburbDropdown(suburbs) {
  const select = document.getElementById('selectSuburbFilter');
  suburbs.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.suburb_name;
    opt.textContent = `${s.suburb_name} (${s.desert_hex_count} desert hexes)`;
    select.appendChild(opt);
  });
}

// --- UI Event Listeners ---

function setupUIListeners() {
  // Metric Switcher Buttons
  const metricBtns = [
    { btn: document.getElementById('btnMetricTDI'), metric: 'tdi' },
    { btn: document.getElementById('btnMetricVuln'), metric: 'vulnerability' },
    { btn: document.getElementById('btnMetricAccess'), metric: 'accessibility' }
  ];

  metricBtns.forEach(({ btn, metric }) => {
    btn.addEventListener('click', () => {
      metricBtns.forEach(b => {
        b.btn.classList.remove('active');
        b.btn.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      state.activeMetric = metric;
      updateLayerStyling();
    });
  });

  // Height Scale Slider
  const sliderHeight = document.getElementById('sliderHeightScale');
  sliderHeight.addEventListener('input', (e) => {
    state.heightScale = parseFloat(e.target.value);
    document.getElementById('valHeightScale').textContent = `${state.heightScale.toFixed(1)}\u00d7`;
    updateLayerStyling();
  });

  // Min TDI Filter Slider
  const sliderTDI = document.getElementById('sliderMinTDI');
  sliderTDI.addEventListener('input', (e) => {
    state.minTDI = parseFloat(e.target.value);
    document.getElementById('valMinTDI').textContent = state.minTDI.toFixed(2);
    applyFilters();
  });

  // Suburb Filter Dropdown
  const selectSuburb = document.getElementById('selectSuburbFilter');
  selectSuburb.addEventListener('change', (e) => {
    state.selectedSuburb = e.target.value;
    applyFilters();

    if (state.selectedSuburb) {
      const match = state.topSuburbs.find(s => s.suburb_name === state.selectedSuburb);
      if (match) {
        map.flyTo({
          center: [match.centroid_lng, match.centroid_lat],
          zoom: 12.8,
          pitch: 55,
          speed: 1.2
        });
      }
    }
  });

  // Reset Camera View
  document.getElementById('btnResetView').addEventListener('click', () => {
    state.selectedSuburb = '';
    selectSuburb.value = '';
    applyFilters();
    map.flyTo({
      center: [144.9631, -37.8136],
      zoom: 10.2,
      pitch: 45,
      bearing: -15,
      speed: 1.2
    });
  });

  // 2D / 3D Pitch Toggle Button
  const btnPitch = document.getElementById('btnPitchToggle');
  const labelPitch = document.getElementById('labelPitch');
  btnPitch.addEventListener('click', () => {
    if (state.is3D) {
      map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
      labelPitch.textContent = '2D';
      state.is3D = false;
    } else {
      map.easeTo({ pitch: 50, bearing: -15, duration: 800 });
      labelPitch.textContent = '3D';
      state.is3D = true;
    }
  });

  // Zoom In / Out
  document.getElementById('btnZoomIn').addEventListener('click', () => map.zoomIn({ duration: 300 }));
  document.getElementById('btnZoomOut').addEventListener('click', () => map.zoomOut({ duration: 300 }));

  // Close Inspector
  document.getElementById('btnCloseInspector').addEventListener('click', () => {
    document.getElementById('inspectorBody').innerHTML = `
      <div class="empty-inspector">
        <i data-lucide="mouse-pointer-click" class="icon-lg text-muted"></i>
        <p>Hover or click on any 3D hexagon to inspect its demographic need and transit travel times.</p>
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
  });
}
