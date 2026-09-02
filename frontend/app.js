/**
 * Multimodal Transit Desert & Dynamic Equity Platform
 * Global 3D Geospatial Engine (Melbourne & Mumbai 3-Stage Chronological Evaluation)
 * Architecture: MapLibre GL JS + DuckDB + Conveyal r5py + Uber H3
 */

// Global State Store
const state = {
  activeCity: 'mumbai',
  activeMetric: 'tdi',
  mumbaiScenario: 'legacy', // 'legacy', 'current_metro', 'future_2030', 'delta_active', 'delta_future'
  heightScale: 1.0,
  minTDI: 0.0,
  is3D: true,
  selectedSuburb: '',
  onlySlumsFilter: false,
  
  // Layer Visibilities
  metroLinesVisible: true,
  suburbanRailVisible: true,
  metroStationsVisible: true,
  slumsLayerVisible: false,
  wardsLayerVisible: false,

  // GeoJSON / Raw Stores
  hexagonsGeoJSON: null,
  metroTracksGeoJSON: null,
  suburbanRailGeoJSON: null,
  metroStationsGeoJSON: null,
  slumsGeoJSON: null,
  wardsGeoJSON: null,
  poiMarkers: [],
  systemStats: null,
  comparisonStats: null,
  topItems: [],
  citiesConfig: []
};

// Dark Glassmorphism Vector Basemap Style (CARTO Dark Matter GL Vector Style)
function getVectorMapStyleUrl(apiKey = '') {
  const queryParam = (apiKey && apiKey !== 'your_carto_api_key_here') ? `?api_key=${encodeURIComponent(apiKey)}` : '';
  return `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json${queryParam}`;
}

// City Definitions & Viewports
const CITY_METADATA = {
  melbourne: {
    name: 'Greater Melbourne',
    country: 'Australia',
    badge: 'Melbourne',
    subtitle: 'Melbourne Multimodal Transit Equity (121,802 Hexagons &bull; r5py &bull; SEIFA Demographics)',
    center: [144.9631, -37.8136],
    zoom: 10.2,
    pitch: 45,
    bearing: -15,
    endpoints: {
      deserts: '/api/v1/transit-deserts',
      top: '/api/v1/suburbs/top?limit=15&min_pop=500',
      stats: '/api/v1/stats',
      pois: '/api/v1/pois'
    },
    metricMultipliers: { tdi: 2500, vulnerability: 2500, accessibility: 3500 }
  },
  mumbai: {
    name: 'Greater Mumbai',
    country: 'India',
    badge: 'Mumbai (3-Stage Evaluation)',
    subtitle: 'Mumbai Multimodal Transit Equity & 3-Stage Metro Evaluation (10,891 Hexagons &bull; 178 Metro Stations &bull; r5py)',
    center: [72.8777, 19.0760],
    zoom: 10.5,
    pitch: 45,
    bearing: -20,
    endpoints: {
      deserts: '/api/v1/mumbai/transit-deserts',
      top: '/api/v1/mumbai/deserts/top?limit=15',
      stats: '/api/v1/mumbai/stats',
      comparison: '/api/v1/mumbai/comparison-stats',
      pois: '/api/v1/mumbai/pois',
      metro_lines: '/api/v1/mumbai/metro-lines',
      suburban_rail: '/api/v1/mumbai/suburban-rail',
      metro_stations: '/api/v1/mumbai/metro-stations',
      slums: '/api/v1/mumbai/slums?limit=3000',
      wards: '/api/v1/mumbai/wards'
    },
    metricMultipliers: { tdi: 3000, vulnerability: 3000, accessibility: 4000 }
  }
};

// Metric Visual Configurations
const METRIC_CONFIGS = {
  tdi: {
    title: 'Transit Desert Index (TDI)',
    unit: 'High Disadvantage \u00d7 Low Access',
    legendGradient: 'linear-gradient(90deg, #00f5a0 0%, #f6d365 30%, #ff7849 60%, #ff0844 85%, #e024c3 100%)',
    legendLabels: ['Low (0.0)', 'Moderate (0.4)', 'Critical (0.8+)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'tdi'],
      0.00, '#00f5a0',
      0.30, '#f6d365',
      0.50, '#ff7849',
      0.70, '#ff0844',
      0.90, '#e024c3'
    ]
  },
  vulnerability: {
    title: 'Demographic Need / Vulnerability (V_i)',
    unit: 'Need / Slum Vulnerability Proxy',
    legendGradient: 'linear-gradient(90deg, #38ef7d 0%, #4facfe 35%, #9b51e0 70%, #ff3366 100%)',
    legendLabels: ['Low (0.0)', 'Medium (0.4)', 'Severe (0.9+)'],
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
    unit: 'Linear Decay Commute to Mega-Hubs',
    legendGradient: 'linear-gradient(90deg, #111827 0%, #0369a1 30%, #00f2fe 70%, #00f5a0 100%)',
    legendLabels: ['Poor Access (0.0)', 'Medium (0.35)', 'High Access (0.7+)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'accessibility'],
      0.00, '#1e293b',
      0.15, '#0284c7',
      0.35, '#00f2fe',
      0.65, '#00f5a0'
    ]
  },
  delta: {
    title: 'Equity Gain (\u0394 TDI Reduction)',
    unit: 'Reduction in Desert Disadvantage',
    legendGradient: 'linear-gradient(90deg, #64748b 0%, #00f5a0 35%, #00f2fe 70%, #38ef7d 100%)',
    legendLabels: ['No Change (0.00)', 'Modest (+0.02)', 'High Relief (+0.10+)'],
    colorExpression: [
      'interpolate',
      ['linear'],
      ['get', 'delta_tdi'],
      -0.02, '#ff3366',
       0.00, '#334155',
       0.01, '#00f5a0',
       0.04, '#00f2fe',
       0.10, '#38ef7d'
    ]
  }
};

// MapLibre Map & Tooltip Instance
let map;
let hoverTooltip;

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
  if (window.lucide) window.lucide.createIcons();

  hoverTooltip = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 12
  });

  // Fetch client configuration (including CartoDB API Key)
  let cartoApiKey = '';
  try {
    const configRes = await fetch('/api/v1/config');
    if (configRes.ok) {
      const configData = await configRes.json();
      cartoApiKey = configData.carto_api_key || '';
    }
  } catch (err) {
    console.warn('Could not fetch /api/v1/config, using default basemap tiles:', err);
  }

  await fetchCitiesMetadata();

  const initialCfg = CITY_METADATA[state.activeCity];
  const vectorStyleUrl = getVectorMapStyleUrl(cartoApiKey);

  map = new maplibregl.Map({
    container: 'map',
    style: vectorStyleUrl,
    center: initialCfg.center,
    zoom: initialCfg.zoom,
    pitch: initialCfg.pitch,
    bearing: initialCfg.bearing,
    antialias: true,
    transformRequest: (url, resourceType) => {
      if (cartoApiKey && cartoApiKey !== 'your_carto_api_key_here' && url.includes('cartocdn.com')) {
        const delimiter = url.includes('?') ? '&' : '?';
        return { url: `${url}${delimiter}api_key=${encodeURIComponent(cartoApiKey)}` };
      }
      return { url };
    }
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 150, unit: 'metric' }), 'bottom-left');

  window.map = map;
  window.state = state;

  map.on('load', async () => {
    // Switch to Mumbai on startup
    await switchCity('mumbai');
  });

  setupUIListeners();
  setupMapInteractivity();
});

// --- Loader Helper ---
function showLoader(text = 'Loading Geospatial Analytics...') {
  const loader = document.getElementById('globalLoader');
  const loaderText = document.getElementById('loaderText');
  if (loaderText) loaderText.textContent = text;
  if (loader) loader.classList.add('active');
}

function hideLoader() {
  const loader = document.getElementById('globalLoader');
  if (loader) loader.classList.remove('active');
}

// --- Multi-City Orchestrator ---

async function fetchCitiesMetadata() {
  try {
    const res = await fetch('/api/v1/cities');
    if (res.ok) {
      const data = await res.json();
      state.citiesConfig = data.cities;
    }
  } catch (err) {
    console.warn('Could not fetch /api/v1/cities, using default definitions:', err);
  }
}

async function switchCity(cityId) {
  state.activeCity = cityId;
  const cfg = CITY_METADATA[cityId];

  // Update UI Switcher buttons
  document.getElementById('btnCityMelbourne').classList.toggle('active', cityId === 'melbourne');
  document.getElementById('btnCityMumbai').classList.toggle('active', cityId === 'mumbai');
  
  // Update Topbar Badge & Subtitle
  document.getElementById('activeCityBadge').textContent = cfg.badge;
  document.getElementById('brandSubtitle').innerHTML = cfg.subtitle;

  // Show / Hide City-Specific Controls & 3-Stage Scenario Switcher
  const melbContainer = document.getElementById('melbFilterContainer');
  const mumbaiContainer = document.getElementById('mumbaiTogglesContainer');
  const scenarioCard = document.getElementById('mumbaiScenarioCard');
  
  if (cityId === 'mumbai') {
    if (melbContainer) melbContainer.style.display = 'none';
    if (mumbaiContainer) mumbaiContainer.style.display = 'flex';
    if (scenarioCard) scenarioCard.style.display = 'flex';
  } else {
    if (melbContainer) melbContainer.style.display = 'flex';
    if (mumbaiContainer) mumbaiContainer.style.display = 'none';
    if (scenarioCard) scenarioCard.style.display = 'none';
  }

  // Clear existing POI markers
  clearPOIMarkers();

  // Reset Inspector
  resetInspector();

  // Fly Camera to New City
  map.flyTo({
    center: cfg.center,
    zoom: cfg.zoom,
    pitch: cfg.pitch,
    bearing: cfg.bearing,
    duration: 2500,
    essential: true
  });

  // Load New City Datasets
  await loadCityData(cityId);
}

async function loadCityData(cityId) {
  showLoader(`Loading ${CITY_METADATA[cityId].name} Analytics...`);
  
  try {
    const cfg = CITY_METADATA[cityId];

    if (cityId === 'mumbai') {
      const desertUrl = `${cfg.endpoints.deserts}?scenario=${state.mumbaiScenario}&limit=15000`;
      
      await Promise.all([
        fetchStats(cfg.endpoints.stats),
        fetchMumbaiComparisonStats(cfg.endpoints.comparison),
        fetchPOIs(cfg.endpoints.pois),
        fetchTopLeaderboard(cfg.endpoints.top),
        fetchHexagons(desertUrl),
        fetchMumbaiSlums(cfg.endpoints.slums),
        fetchMumbaiWards(cfg.endpoints.wards),
        fetchMumbaiSuburbanRail(cfg.endpoints.suburban_rail),
        fetchMumbaiMetroTracks(cfg.endpoints.metro_lines),
        fetchMumbaiMetroStations(cfg.endpoints.metro_stations)
      ]);
      bringTransitLayersToFront();
    } else {
      await Promise.all([
        fetchStats(cfg.endpoints.stats),
        fetchPOIs(cfg.endpoints.pois),
        fetchTopLeaderboard(cfg.endpoints.top),
        fetchHexagons(cfg.endpoints.deserts)
      ]);
      removeMumbaiLayers();
    }
  } catch (err) {
    console.error(`Error loading city data for ${cityId}:`, err);
  } finally {
    hideLoader();
  }
}

function bringTransitLayersToFront() {
  if (!map) return;
  const layerIds = [
    'mumbai-slums-fill',
    'mumbai-slums-line',
    'mumbai-wards-line',
    'h3-3d-deserts',
    'mumbai-suburban-rail-layer',
    'mumbai-metro-glow-layer',
    'mumbai-metro-operational-layer',
    'mumbai-metro-underconstruction-layer',
    'mumbai-metro-stations-halo-layer',
    'mumbai-metro-stations-layer'
  ];
  layerIds.forEach(id => {
    if (map.getLayer(id)) {
      try {
        map.moveLayer(id);
      } catch (e) {}
    }
  });
}

// --- Data Fetchers ---

async function fetchStats(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Stats API failed');
    const data = await res.json();
    state.systemStats = data;

    // Update Header Badges
    document.getElementById('statAnalyzedCells').textContent = (data.total_h3_cells || data.total_cells || 0).toLocaleString();
    
    if (state.activeCity === 'mumbai') {
      if (state.mumbaiScenario.startsWith('delta')) {
        document.getElementById('statDesertLabel').textContent = 'Max Equity Gain';
        document.getElementById('statDesertCells').textContent = state.comparisonStats ? `+${state.comparisonStats.max_delta_tdi_reduction.toFixed(3)}` : '+0.119';
        document.getElementById('statSecondaryLabel').textContent = 'Cells Improved';
        document.getElementById('statSecondaryVal').textContent = state.comparisonStats ? `${state.comparisonStats.pct_cells_improved}%` : '31.9%';
      } else if (state.mumbaiScenario === 'future_2030') {
        document.getElementById('statDesertLabel').textContent = '2030 Deserts';
        document.getElementById('statDesertCells').textContent = (48).toLocaleString();
        document.getElementById('statSecondaryLabel').textContent = 'Slum Hexagons';
        document.getElementById('statSecondaryVal').textContent = (data.slum_cluster_cells || 360).toLocaleString();
      } else if (state.mumbaiScenario === 'current_metro') {
        document.getElementById('statDesertLabel').textContent = 'Active Deserts';
        document.getElementById('statDesertCells').textContent = (194).toLocaleString();
        document.getElementById('statSecondaryLabel').textContent = 'Slum Hexagons';
        document.getElementById('statSecondaryVal').textContent = (data.slum_cluster_cells || 360).toLocaleString();
      } else {
        document.getElementById('statDesertLabel').textContent = 'Legacy Deserts';
        document.getElementById('statDesertCells').textContent = (data.severe_desert_cells || 205).toLocaleString();
        document.getElementById('statSecondaryLabel').textContent = 'Slum Hexagons';
        document.getElementById('statSecondaryVal').textContent = (data.slum_cluster_cells || 360).toLocaleString();
      }
    } else {
      document.getElementById('statDesertLabel').textContent = 'Priority Deserts';
      document.getElementById('statDesertCells').textContent = (data.transit_desert_cells_p80 || 12959).toLocaleString();
      document.getElementById('statSecondaryLabel').textContent = 'Impacted Population';
      document.getElementById('statSecondaryVal').textContent = (data.deserts_affected_population || 0).toLocaleString();
    }
  } catch (err) {
    console.error('Error fetching stats:', err);
  }
}

async function fetchMumbaiComparisonStats(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    state.comparisonStats = data;
  } catch (err) {
    console.warn('Could not fetch comparison stats:', err);
  }
}

async function fetchTopLeaderboard(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Top leaderboard failed');
    const data = await res.json();
    state.topItems = data;

    if (state.activeCity === 'melbourne') {
      populateSuburbDropdown(data);
    }
    renderLeaderboard(data);
  } catch (err) {
    console.error('Error fetching leaderboard:', err);
  }
}

async function fetchPOIs(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('POIs API failed');
    const pois = await res.json();

    clearPOIMarkers();

    pois.forEach(poi => {
      const el = document.createElement('div');
      el.className = 'poi-marker';
      el.innerHTML = `
        <div class="poi-icon-pin">
          <span class="poi-emoji">${getCategoryEmoji(poi.category)}</span>
        </div>
      `;

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([poi.lon, poi.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 25, closeButton: false }).setHTML(`
            <div class="poi-popup">
              <div class="poi-title">${poi.name}</div>
              <div class="poi-meta">Category: <strong>${poi.category}</strong></div>
              <div class="poi-meta">Reachable Origins: <strong>${(poi.reachable_h3_2030 || poi.reachable_h3_count || 0).toLocaleString()}</strong></div>
              <div class="poi-meta">Avg Commute: <strong>${poi.avg_travel_time_2030 || poi.avg_travel_time_p50 || 0} min</strong></div>
            </div>
          `)
        )
        .addTo(map);

      state.poiMarkers.push(marker);
    });
  } catch (err) {
    console.error('Error fetching POIs:', err);
  }
}

function clearPOIMarkers() {
  state.poiMarkers.forEach(m => m.remove());
  state.poiMarkers = [];
}

function getCategoryEmoji(cat) {
  switch (cat) {
    case 'Healthcare': return '&#x1F3E5;';
    case 'Education': return '&#x1F393;';
    case 'Commercial': return '&#x1F6CD;';
    case 'Employment': return '&#x1F3E2;';
    default: return '&#x1F3AF;';
  }
}

// --- Hexagon 3D Layer Rendering ---

async function fetchHexagons(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Hexagons API failed');
    const geojson = await res.json();
    state.hexagonsGeoJSON = geojson;

    renderHexagonLayer(geojson);
  } catch (err) {
    console.error('Error loading hexagons:', err);
  }
}

function getActiveMetricConfig() {
  if (state.activeCity === 'mumbai' && state.mumbaiScenario.startsWith('delta')) {
    return METRIC_CONFIGS.delta;
  }
  return METRIC_CONFIGS[state.activeMetric] || METRIC_CONFIGS.tdi;
}

function renderHexagonLayer(geojson) {
  const sourceName = 'h3-hexagons-source';
  const layerName = 'h3-3d-deserts';

  if (map.getSource(sourceName)) {
    map.getSource(sourceName).setData(geojson);
    updateLayerStyling();
    applyFilters();
    bringTransitLayersToFront();
    return;
  }

  map.addSource(sourceName, {
    type: 'geojson',
    data: geojson
  });

  const cfg = getActiveMetricConfig();

  map.addLayer({
    id: layerName,
    type: 'fill-extrusion',
    source: sourceName,
    paint: {
      'fill-extrusion-color': cfg.colorExpression,
      'fill-extrusion-height': [
        '*',
        ['get', 'tdi'],
        state.is3D ? 3000 * state.heightScale : 0
      ],
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.72
    }
  });

  updateLayerStyling();
  applyFilters();
  bringTransitLayersToFront();
}

function updateLayerStyling() {
  if (!map.getLayer('h3-3d-deserts')) return;

  const cfg = getActiveMetricConfig();
  const cityCfg = CITY_METADATA[state.activeCity];
  const isDelta = (state.activeCity === 'mumbai' && state.mumbaiScenario.startsWith('delta'));
  const metricKey = isDelta ? 'delta_tdi' : state.activeMetric;
  const multiplier = isDelta ? 4000 : (cityCfg.metricMultipliers[state.activeMetric] || 2500);

  // Update Color & Height
  map.setPaintProperty('h3-3d-deserts', 'fill-extrusion-color', cfg.colorExpression);
  map.setPaintProperty('h3-3d-deserts', 'fill-extrusion-height', [
    '*',
    ['get', metricKey],
    state.is3D ? multiplier * state.heightScale : 0
  ]);

  updateLegendUI(cfg);
}

function updateLegendUI(cfg) {
  const legendTitle = document.getElementById('legendTitle');
  const legendUnit = document.getElementById('legendUnit');
  const legendBar = document.getElementById('legendBar');
  const legendLabels = document.getElementById('legendLabels');

  if (legendTitle) legendTitle.textContent = cfg.title;
  if (legendUnit) legendUnit.textContent = cfg.unit;
  if (legendBar) legendBar.style.background = cfg.legendGradient;

  if (legendLabels) {
    legendLabels.innerHTML = cfg.legendLabels.map(l => `<span>${l}</span>`).join('');
  }
}

function applyFilters() {
  if (!map.getLayer('h3-3d-deserts')) return;

  const filters = ['all'];

  // Min TDI cutoff filter
  if (state.minTDI > 0) {
    const metricFilter = (state.activeCity === 'mumbai' && state.mumbaiScenario.startsWith('delta')) ? 'delta_tdi' : 'tdi';
    filters.push(['>=', ['get', metricFilter], state.minTDI]);
  }

  // Melbourne Suburb filter
  if (state.activeCity === 'melbourne' && state.selectedSuburb) {
    filters.push(['==', ['get', 'suburb_name'], state.selectedSuburb]);
  }

  // Mumbai Slum Only filter
  if (state.activeCity === 'mumbai' && state.onlySlumsFilter) {
    filters.push(['==', ['get', 'is_slum'], 1]);
  }

  map.setFilter('h3-3d-deserts', filters.length > 1 ? filters : null);
}

// --- Strict Transit Vector Layer Visual Hierarchy & Overlays ---

async function fetchMumbaiSuburbanRail(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Suburban rail fetch failed: ${res.status}`);
    const geojson = await res.json();
    state.suburbanRailGeoJSON = geojson;

    const sourceName = 'mumbai-suburban-rail-source';
    const layerName = 'mumbai-suburban-rail-layer';

    if (map.getSource(sourceName)) {
      map.getSource(sourceName).setData(geojson);
      return;
    }

    map.addSource(sourceName, { type: 'geojson', data: geojson });

    // Suburban Rail: Thin, solid Dark Slate/Grey (#546E7A)
    map.addLayer({
      id: layerName,
      type: 'line',
      source: sourceName,
      layout: {
        'line-join': 'round',
        'line-cap': 'round',
        'visibility': state.suburbanRailVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': '#546E7A',
        'line-width': 2.0,
        'line-opacity': 0.85
      }
    });
    bringTransitLayersToFront();
  } catch (err) {
    console.warn('Could not load Suburban Rail lines:', err);
  }
}

async function fetchMumbaiMetroTracks(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Metro tracks fetch failed: ${res.status}`);
    const geojson = await res.json();
    state.metroTracksGeoJSON = geojson;

    const sourceName = 'mumbai-metro-tracks-source';
    const layerGlow = 'mumbai-metro-glow-layer';
    const layerSolid = 'mumbai-metro-operational-layer';
    const layerDashed = 'mumbai-metro-underconstruction-layer';

    if (map.getSource(sourceName)) {
      map.getSource(sourceName).setData(geojson);
      bringTransitLayersToFront();
      return;
    }

    map.addSource(sourceName, { type: 'geojson', data: geojson });

    // 0. Metro Ambient Glow Layer
    map.addLayer({
      id: layerGlow,
      type: 'line',
      source: sourceName,
      layout: {
        'line-join': 'round',
        'line-cap': 'round',
        'visibility': state.metroLinesVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 7.0,
        'line-blur': 2.5,
        'line-opacity': 0.35
      }
    });

    // 1. Operational Metro: Thick, solid lines (MMRDA official hex colors)
    map.addLayer({
      id: layerSolid,
      type: 'line',
      source: sourceName,
      filter: ['==', ['get', 'is_operational'], true],
      layout: {
        'line-join': 'round',
        'line-cap': 'round',
        'visibility': state.metroLinesVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 4.5,
        'line-opacity': 0.95
      }
    });

    // 2. Under-Construction Metro: Dashed lines (line-dasharray: [2, 2])
    map.addLayer({
      id: layerDashed,
      type: 'line',
      source: sourceName,
      filter: ['==', ['get', 'is_operational'], false],
      layout: {
        'line-join': 'round',
        'line-cap': 'round',
        'visibility': state.metroLinesVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 3.5,
        'line-dasharray': [2, 2],
        'line-opacity': 0.90
      }
    });
    bringTransitLayersToFront();
  } catch (err) {
    console.warn('Could not load Mumbai Metro tracks:', err);
  }
}

async function fetchMumbaiMetroStations(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Metro stations fetch failed: ${res.status}`);
    const geojson = await res.json();
    state.metroStationsGeoJSON = geojson;

    const sourceName = 'mumbai-metro-stations-source';
    const haloLayer = 'mumbai-metro-stations-halo-layer';
    const stationLayer = 'mumbai-metro-stations-layer';

    if (map.getSource(sourceName)) {
      map.getSource(sourceName).setData(geojson);
      bringTransitLayersToFront();
      return;
    }

    map.addSource(sourceName, { type: 'geojson', data: geojson });

    // Station Colored Halo
    map.addLayer({
      id: haloLayer,
      type: 'circle',
      source: sourceName,
      layout: {
        'visibility': state.metroStationsVisible ? 'visible' : 'none'
      },
      paint: {
        'circle-radius': 6.0,
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.85
      }
    });

    // Station White Core (Radius 4)
    map.addLayer({
      id: stationLayer,
      type: 'circle',
      source: sourceName,
      layout: {
        'visibility': state.metroStationsVisible ? 'visible' : 'none'
      },
      paint: {
        'circle-radius': 4.0,
        'circle-color': '#ffffff',
        'circle-stroke-color': '#0a0f1c',
        'circle-stroke-width': 1.5,
        'circle-opacity': 1.0,
        'circle-stroke-opacity': 1.0
      }
    });
    bringTransitLayersToFront();
  } catch (err) {
    console.warn('Could not load Mumbai Metro stations:', err);
  }
}

async function fetchMumbaiSlums(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const geojson = await res.json();
    state.slumsGeoJSON = geojson;

    const sourceName = 'mumbai-slums-source';
    if (map.getSource(sourceName)) {
      map.getSource(sourceName).setData(geojson);
      return;
    }

    map.addSource(sourceName, { type: 'geojson', data: geojson });

    map.addLayer({
      id: 'mumbai-slums-fill',
      type: 'fill',
      source: sourceName,
      layout: {
        'visibility': state.slumsLayerVisible ? 'visible' : 'none'
      },
      paint: {
        'fill-color': '#ff7849',
        'fill-opacity': 0.35
      }
    });

    map.addLayer({
      id: 'mumbai-slums-line',
      type: 'line',
      source: sourceName,
      layout: {
        'visibility': state.slumsLayerVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': '#ff7849',
        'line-width': 1.2,
        'line-opacity': 0.85
      }
    });
  } catch (err) {
    console.warn('Could not load Slum polygons:', err);
  }
}

async function fetchMumbaiWards(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const geojson = await res.json();
    state.wardsGeoJSON = geojson;

    const sourceName = 'mumbai-wards-source';
    if (map.getSource(sourceName)) {
      map.getSource(sourceName).setData(geojson);
      return;
    }

    map.addSource(sourceName, { type: 'geojson', data: geojson });

    map.addLayer({
      id: 'mumbai-wards-line',
      type: 'line',
      source: sourceName,
      layout: {
        'visibility': state.wardsLayerVisible ? 'visible' : 'none'
      },
      paint: {
        'line-color': '#00f2fe',
        'line-width': 1.5,
        'line-dasharray': [3, 2],
        'line-opacity': 0.6
      }
    });
  } catch (err) {
    console.warn('Could not load BMC Wards:', err);
  }
}

function removeMumbaiLayers() {
  [
    'mumbai-metro-stations-layer',
    'mumbai-metro-stations-halo-layer',
    'mumbai-metro-operational-layer',
    'mumbai-metro-underconstruction-layer',
    'mumbai-metro-glow-layer',
    'mumbai-suburban-rail-layer',
    'mumbai-slums-fill',
    'mumbai-slums-line',
    'mumbai-wards-line'
  ].forEach(id => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  
  [
    'mumbai-metro-stations-source',
    'mumbai-metro-tracks-source',
    'mumbai-suburban-rail-source',
    'mumbai-slums-source',
    'mumbai-wards-source'
  ].forEach(id => {
    if (map.getSource(id)) map.removeSource(id);
  });
}

// --- Leaderboard ---

function renderLeaderboard(items) {
  const container = document.getElementById('leaderboardList');
  if (!container) return;

  const isMumbai = state.activeCity === 'mumbai';
  const headerLabel = document.getElementById('leaderboardHeaderLabel');
  const desc = document.getElementById('leaderboardDesc');

  if (isMumbai) {
    if (state.mumbaiScenario.startsWith('delta')) {
      if (headerLabel) headerLabel.textContent = 'Top Equity Improvements';
      if (desc) desc.textContent = 'Hexagons with greatest Transit Desert Index (\u0394 TDI) reduction:';
    } else if (state.mumbaiScenario === 'future_2030') {
      if (headerLabel) headerLabel.textContent = '2030 Remaining Deserts';
      if (desc) desc.textContent = 'High-disadvantage cells remaining after full Metro network:';
    } else if (state.mumbaiScenario === 'current_metro') {
      if (headerLabel) headerLabel.textContent = 'Active Metro Deserts';
      if (desc) desc.textContent = 'Current high-disadvantage cells with 79 active metro stations:';
    } else {
      if (headerLabel) headerLabel.textContent = 'Legacy Network Deserts';
      if (desc) desc.textContent = 'Historical high-disadvantage informal settlements lacking transit:';
    }
  } else {
    if (headerLabel) headerLabel.textContent = 'Worst Suburban Deserts';
    if (desc) desc.textContent = 'Click any corridor to fly directly to its high-disadvantage hexagon:';
  }

  if (!items || items.length === 0) {
    container.innerHTML = `<div class="loading-state">No priority areas found for filter criteria.</div>`;
    return;
  }

  container.innerHTML = '';

  if (isMumbai) {
    items.forEach((item, idx) => {
      const el = document.createElement('div');
      el.className = 'leaderboard-item';
      const isSlum = item.is_slum_cluster === 1;

      el.innerHTML = `
        <div class="item-rank">#${idx + 1}</div>
        <div class="item-details">
          <span class="item-name">${isSlum ? '&#x1F3D8; Informal Slum Corridor' : 'Urban Hex Corridor'}</span>
          <span class="item-meta">H3: ${item.h3_index.substring(0, 10)}... &bull; Vuln: ${Number(item.vulnerability_score).toFixed(2)}</span>
        </div>
        <div class="item-score">
          <span class="score-val text-neon-red">${Number(item.tdi_score).toFixed(3)}</span>
          <span class="score-label">TDI</span>
        </div>
      `;

      el.addEventListener('click', () => {
        map.flyTo({
          center: [item.lon, item.lat],
          zoom: 13.5,
          pitch: 55,
          speed: 1.2
        });
      });

      container.appendChild(el);
    });
  } else {
    items.forEach((sub, idx) => {
      const el = document.createElement('div');
      el.className = 'leaderboard-item';
      el.innerHTML = `
        <div class="item-rank">#${idx + 1}</div>
        <div class="item-details">
          <span class="item-name">${sub.suburb_name}</span>
          <span class="item-meta">Decile ${sub.avg_seifa_decile} &bull; ${sub.estimated_resident_pop.toLocaleString()} pop</span>
        </div>
        <div class="item-score">
          <span class="score-val text-neon-red">${Number(sub.avg_desert_index).toFixed(3)}</span>
          <span class="score-label">TDI</span>
        </div>
      `;

      el.addEventListener('click', () => {
        map.flyTo({
          center: [sub.centroid_lng, sub.centroid_lat],
          zoom: 12.8,
          pitch: 55,
          speed: 1.2
        });

        const select = document.getElementById('selectSuburbFilter');
        if (select) select.value = sub.suburb_name;
        state.selectedSuburb = sub.suburb_name;
        applyFilters();
      });

      container.appendChild(el);
    });
  }
}

function populateSuburbDropdown(suburbs) {
  const select = document.getElementById('selectSuburbFilter');
  if (!select) return;
  select.innerHTML = '<option value="">All Greater Melbourne Suburbs</option>';
  suburbs.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.suburb_name;
    opt.textContent = `${s.suburb_name} (${s.desert_hex_count} desert hexes)`;
    select.appendChild(opt);
  });
}

// --- Interactivity & Hexagon Inspector ---

function setupMapInteractivity() {
  // Hexagon Interactivity
  map.on('mouseenter', 'h3-3d-deserts', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'h3-3d-deserts', () => {
    map.getCanvas().style.cursor = '';
  });

  map.on('click', 'h3-3d-deserts', (e) => {
    if (!e.features || !e.features[0]) return;
    renderInspector(e.features[0].properties);
  });

  map.on('mousemove', 'h3-3d-deserts', (e) => {
    if (!e.features || !e.features[0]) return;
    renderInspector(e.features[0].properties);
  });

  // Metro Station Hover Tooltips
  map.on('mouseenter', 'mumbai-metro-stations-layer', (e) => {
    if (!e.features || !e.features[0]) return;
    map.getCanvas().style.cursor = 'pointer';
    const p = e.features[0].properties;
    const coords = e.features[0].geometry.coordinates.slice();

    const html = `
      <div style="padding: 4px 6px; font-family: sans-serif; font-size: 0.78rem;">
        <div style="font-weight: 700; color: #fff; font-size: 0.86rem; margin-bottom: 3px;">${p.station_name}</div>
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
          <span style="display:inline-block; width:9px; height:9px; border-radius:50%; background-color:${p.color || '#00AEEF'};"></span>
          <span style="color:${p.color || '#00AEEF'}; font-weight: 600;">${p.line_name}</span>
        </div>
        <div style="color: #94a3b8; font-size: 0.72rem;">
          Status: <strong style="color:${p.status === 'operational' ? '#00f5a0' : '#f6d365'};">${p.status === 'operational' ? 'Operational' : 'Under Construction'}</strong>
          &bull; Seq: <strong>#${p.stop_sequence || p.sequence}</strong>
        </div>
      </div>
    `;

    hoverTooltip.setLngLat(coords).setHTML(html).addTo(map);
  });

  map.on('mouseleave', 'mumbai-metro-stations-layer', () => {
    map.getCanvas().style.cursor = '';
    hoverTooltip.remove();
  });

  // Metro Track Lines Hover Tooltips
  ['mumbai-metro-operational-layer', 'mumbai-metro-underconstruction-layer'].forEach(layerId => {
    map.on('mouseenter', layerId, (e) => {
      if (!e.features || !e.features[0]) return;
      map.getCanvas().style.cursor = 'pointer';
      const p = e.features[0].properties;
      const html = `
        <div style="padding: 4px 6px; font-family: sans-serif; font-size: 0.78rem;">
          <div style="font-weight: 700; color: ${p.color || '#00AEEF'}; font-size: 0.86rem; margin-bottom: 2px;">${p.line_name}</div>
          <div style="color: #cbd5e1; font-size: 0.74rem;">
            ${p.start_station} &harr; ${p.end_station} (${p.station_count} Stations)
          </div>
          <div style="color: #94a3b8; font-size: 0.72rem; margin-top: 2px;">
            Status: <strong style="color:${p.status === 'operational' ? '#00f5a0' : '#f6d365'};">${p.status === 'operational' ? 'Operational' : 'Under Construction'}</strong>
          </div>
        </div>
      `;
      hoverTooltip.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });

    map.on('mouseleave', layerId, () => {
      map.getCanvas().style.cursor = '';
      hoverTooltip.remove();
    });
  });
}

function renderInspector(props) {
  const container = document.getElementById('inspectorBody');
  const isMumbai = state.activeCity === 'mumbai';

  if (isMumbai) {
    const isSlum = props.is_slum === 1;
    
    // 3-Stage TDI Values
    const legTDI = Number(props.legacy_tdi || props.tdi || 0.0).toFixed(3);
    const curTDI = Number(props.current_tdi || props.tdi || 0.0).toFixed(3);
    const futTDI = Number(props.future_tdi || props.tdi || 0.0).toFixed(3);
    
    // Deltas
    const deltaActive = Number(props.delta_active_metro || 0.0).toFixed(3);
    const deltaFuture = Number(props.delta_future_expansion || 0.0).toFixed(3);
    const deltaTotal = Number(props.delta_total_metro || 0.0).toFixed(3);

    container.innerHTML = `
      <div class="inspector-suburb-title">${isSlum ? '&#x1F3D8; Informal Slum Cluster' : 'Mumbai Urban Hexagon'}</div>
      <div class="inspector-sa1">H3: <code>${props.h3_index}</code> &bull; (${Number(props.centroid_lat).toFixed(4)}, ${Number(props.centroid_lng).toFixed(4)})</div>

      <!-- 3-Stage TDI Progression -->
      <div style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: #64748b; margin-top: 8px; margin-bottom: 4px;">
        3-Stage Transit Desert Index (TDI)
      </div>
      <div class="gauge-row">
        <div class="gauge-card">
          <span class="gauge-label">1. Legacy</span>
          <div class="gauge-val text-neon-red">${legTDI}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">2. Active Metro</span>
          <div class="gauge-val text-neon-amber">${curTDI}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">3. 2030 Full</span>
          <div class="gauge-val text-neon-cyan">${futTDI}</div>
        </div>
      </div>

      <!-- Equity Impact Gains (\u0394 TDI) -->
      <div style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: #64748b; margin-top: 10px; margin-bottom: 4px;">
        Equity Relief & Impact (\u0394 TDI Reduction)
      </div>
      <div class="gauge-row">
        <div class="gauge-card">
          <span class="gauge-label">\u0394 Active Metro</span>
          <div class="gauge-val ${Number(deltaActive) > 0 ? 'text-neon-cyan' : 'text-muted'}">${Number(deltaActive) > 0 ? `+${deltaActive}` : deltaActive}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">\u0394 Future 2030</span>
          <div class="gauge-val ${Number(deltaFuture) > 0 ? 'text-neon-cyan' : 'text-muted'}">${Number(deltaFuture) > 0 ? `+${deltaFuture}` : deltaFuture}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">\u0394 Total Gain</span>
          <div class="gauge-val text-neon-emerald">${Number(deltaTotal) > 0 ? `+${deltaTotal}` : deltaTotal}</div>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; color: #94a3b8; margin: 10px 0;">
        <div style="display: flex; justify-content: space-between;">
          <span>Settlement Fabric:</span>
          <strong style="color: ${isSlum ? '#ff7849' : '#00f5a0'};">${isSlum ? 'Slum Cluster Corridor' : 'Standard Urban Fabric'}</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span>Vulnerability Weight:</span>
          <strong style="color: #fff;">${isSlum ? '1.0 (Critical Priority)' : '0.2 (Baseline)'}</strong>
        </div>
      </div>

      <div class="poi-travel-times">
        <span style="font-size: 0.72rem; font-weight: 600; text-transform: uppercase; color: #64748b;">
          Commute Progression (Legacy &rarr; Active &rarr; 2030)
        </span>
        
        <div class="poi-row">
          <span class="poi-badge">&#x1F3E2; BKC</span>
          <span class="poi-time">
            ${props.legacy_time_bkc ? `${props.legacy_time_bkc}m &rarr; ${props.current_time_bkc}m &rarr; <strong style="color:#00f5a0;">${props.future_time_bkc}m</strong>` : `${props.tt_bkc} min`}
          </span>
        </div>

        <div class="poi-row">
          <span class="poi-badge">&#x1F3E5; KEM Hospital</span>
          <span class="poi-time">
            ${props.legacy_time_kem ? `${props.legacy_time_kem}m &rarr; ${props.current_time_kem}m &rarr; <strong style="color:#00f5a0;">${props.future_time_kem}m</strong>` : `${props.tt_kem} min`}
          </span>
        </div>

        <div class="poi-row">
          <span class="poi-badge">&#x1F393; IIT Bombay</span>
          <span class="poi-time">
            ${props.legacy_time_iit ? `${props.legacy_time_iit}m &rarr; ${props.current_time_iit}m &rarr; <strong style="color:#00f5a0;">${props.future_time_iit}m</strong>` : `${props.tt_iit} min`}
          </span>
        </div>

        <div class="poi-row">
          <span class="poi-badge">&#x1F6CD; Palladium</span>
          <span class="poi-time">
            ${props.legacy_time_pal ? `${props.legacy_time_pal}m &rarr; ${props.current_time_pal}m &rarr; <strong style="color:#00f5a0;">${props.future_time_pal}m</strong>` : `${props.tt_pal} min`}
          </span>
        </div>
      </div>
    `;
  } else {
    // Melbourne Inspector
    container.innerHTML = `
      <div class="inspector-suburb-title">${props.suburb_name || 'Melbourne SA2'}</div>
      <div class="inspector-sa1">SA1: <code>${props.sa1_code || 'N/A'}</code> &bull; H3: <code>${props.h3_index}</code></div>

      <div class="gauge-row">
        <div class="gauge-card">
          <span class="gauge-label">Transit Desert</span>
          <div class="gauge-val text-neon-red">${Number(props.tdi).toFixed(3)}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">Vulnerability</span>
          <div class="gauge-val text-neon-purple">${Number(props.vulnerability).toFixed(3)}</div>
        </div>
        <div class="gauge-card">
          <span class="gauge-label">Accessibility</span>
          <div class="gauge-val text-neon-cyan">${Number(props.accessibility).toFixed(3)}</div>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; color: #94a3b8; margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between;">
          <span>SEIFA Disadvantage Decile:</span>
          <strong style="color: ${props.seifa_irsd_decile <= 2 ? '#ff3366' : '#00f5a0'};">Decile ${props.seifa_irsd_decile || 'N/A'} (1=Worst)</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span>Population Density:</span>
          <strong style="color: #fff;">${Number(props.pop_density || 0).toLocaleString()} / km&sup2;</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span>Estimated Population:</span>
          <strong style="color: #fff;">${Number(props.population || 0).toLocaleString()} residents</strong>
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
}

function resetInspector() {
  document.getElementById('inspectorBody').innerHTML = `
    <div class="empty-inspector">
      <i data-lucide="mouse-pointer-click" class="icon-lg text-muted"></i>
      <p>Hover or click on any 3D hexagon to inspect its multimodal accessibility and transit travel times.</p>
    </div>
  `;
  if (window.lucide) window.lucide.createIcons();
}

// --- UI Event Listeners ---

function setupUIListeners() {
  // City Switcher Buttons
  document.getElementById('btnCityMelbourne').addEventListener('click', () => switchCity('melbourne'));
  document.getElementById('btnCityMumbai').addEventListener('click', () => switchCity('mumbai'));

  // 5-Option Chronological Scenario Switcher Buttons
  const scenarioBtns = [
    { btn: document.getElementById('btnScenarioLegacy'), scenario: 'legacy', label: 'Legacy Network (Without Metro)' },
    { btn: document.getElementById('btnScenarioCurrent'), scenario: 'current_metro', label: 'Current Network (Active Metro)' },
    { btn: document.getElementById('btnScenarioFuture'), scenario: 'future_2030', label: '2030 Network (Full Expansion)' },
    { btn: document.getElementById('btnScenarioDeltaActive'), scenario: 'delta_active', label: 'Impact of Active Metro' },
    { btn: document.getElementById('btnScenarioDeltaFuture'), scenario: 'delta_future', label: 'Impact of Future Expansion' }
  ];

  scenarioBtns.forEach(({ btn, scenario, label }) => {
    if (!btn) return;
    btn.addEventListener('click', async () => {
      scenarioBtns.forEach(b => {
        if (b.btn) {
          b.btn.classList.remove('active');
          b.btn.setAttribute('aria-selected', 'false');
        }
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      state.mumbaiScenario = scenario;
      
      showLoader(`Evaluating ${label}...`);
      const cfg = CITY_METADATA.mumbai;
      const url = `${cfg.endpoints.deserts}?scenario=${state.mumbaiScenario}&limit=15000`;
      await fetchHexagons(url);
      await fetchStats(cfg.endpoints.stats);
      hideLoader();
    });
  });

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

  // Melbourne Suburb Filter Dropdown
  const selectSuburb = document.getElementById('selectSuburbFilter');
  if (selectSuburb) {
    selectSuburb.addEventListener('change', (e) => {
      state.selectedSuburb = e.target.value;
      applyFilters();

      if (state.selectedSuburb) {
        const match = state.topItems.find(s => s.suburb_name === state.selectedSuburb);
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
  }

  // Mumbai Thematic Layer Toggles
  const toggleMetroLinesBtn = document.getElementById('toggleMetroLines');
  if (toggleMetroLinesBtn) {
    toggleMetroLinesBtn.addEventListener('click', () => {
      state.metroLinesVisible = !state.metroLinesVisible;
      toggleMetroLinesBtn.classList.toggle('active', state.metroLinesVisible);
      const vis = state.metroLinesVisible ? 'visible' : 'none';
      
      ['mumbai-metro-operational-layer', 'mumbai-metro-underconstruction-layer', 'mumbai-metro-glow-layer'].forEach(lid => {
        if (map.getLayer(lid)) map.setLayoutProperty(lid, 'visibility', vis);
      });
    });
  }

  const toggleSuburbanRailBtn = document.getElementById('toggleSuburbanRail');
  if (toggleSuburbanRailBtn) {
    toggleSuburbanRailBtn.addEventListener('click', () => {
      state.suburbanRailVisible = !state.suburbanRailVisible;
      toggleSuburbanRailBtn.classList.toggle('active', state.suburbanRailVisible);
      const vis = state.suburbanRailVisible ? 'visible' : 'none';
      if (map.getLayer('mumbai-suburban-rail-layer')) {
        map.setLayoutProperty('mumbai-suburban-rail-layer', 'visibility', vis);
      }
    });
  }

  const toggleMetroStationsBtn = document.getElementById('toggleMetroStations');
  if (toggleMetroStationsBtn) {
    toggleMetroStationsBtn.addEventListener('click', () => {
      state.metroStationsVisible = !state.metroStationsVisible;
      toggleMetroStationsBtn.classList.toggle('active', state.metroStationsVisible);
      const vis = state.metroStationsVisible ? 'visible' : 'none';
      ['mumbai-metro-stations-layer', 'mumbai-metro-stations-halo-layer'].forEach(lid => {
        if (map.getLayer(lid)) map.setLayoutProperty(lid, 'visibility', vis);
      });
    });
  }

  const toggleSlumsBtn = document.getElementById('toggleSlums');
  if (toggleSlumsBtn) {
    toggleSlumsBtn.addEventListener('click', () => {
      state.slumsLayerVisible = !state.slumsLayerVisible;
      toggleSlumsBtn.classList.toggle('active', state.slumsLayerVisible);
      const vis = state.slumsLayerVisible ? 'visible' : 'none';
      ['mumbai-slums-fill', 'mumbai-slums-line'].forEach(lid => {
        if (map.getLayer(lid)) map.setLayoutProperty(lid, 'visibility', vis);
      });
    });
  }

  const toggleWardsBtn = document.getElementById('toggleWards');
  if (toggleWardsBtn) {
    toggleWardsBtn.addEventListener('click', () => {
      state.wardsLayerVisible = !state.wardsLayerVisible;
      toggleWardsBtn.classList.toggle('active', state.wardsLayerVisible);
      const vis = state.wardsLayerVisible ? 'visible' : 'none';
      if (map.getLayer('mumbai-wards-line')) {
        map.setLayoutProperty('mumbai-wards-line', 'visibility', vis);
      }
    });
  }

  const toggleOnlySlumHexBtn = document.getElementById('toggleOnlySlumHex');
  if (toggleOnlySlumHexBtn) {
    toggleOnlySlumHexBtn.addEventListener('click', () => {
      state.onlySlumsFilter = !state.onlySlumsFilter;
      toggleOnlySlumHexBtn.classList.toggle('active', state.onlySlumsFilter);
      applyFilters();
    });
  }

  // Reset Camera View
  document.getElementById('btnResetView').addEventListener('click', () => {
    state.selectedSuburb = '';
    if (selectSuburb) selectSuburb.value = '';
    state.onlySlumsFilter = false;
    if (toggleOnlySlumHexBtn) toggleOnlySlumHexBtn.classList.remove('active');
    applyFilters();
    
    const cfg = CITY_METADATA[state.activeCity];
    map.flyTo({
      center: cfg.center,
      zoom: cfg.zoom,
      pitch: cfg.pitch,
      bearing: cfg.bearing,
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
      updateLayerStyling();
    } else {
      map.easeTo({ pitch: 50, bearing: -15, duration: 800 });
      labelPitch.textContent = '3D';
      state.is3D = true;
      updateLayerStyling();
    }
  });

  // Zoom In / Out
  document.getElementById('btnZoomIn').addEventListener('click', () => map.zoomIn({ duration: 300 }));
  document.getElementById('btnZoomOut').addEventListener('click', () => map.zoomOut({ duration: 300 }));

  // Close Inspector
  document.getElementById('btnCloseInspector').addEventListener('click', resetInspector);
}
