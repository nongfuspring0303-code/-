const CONFIG = {
  WS_URL: window.RUNTIME_CONFIG?.WS_URL || 'ws://127.0.0.1:18765',
  API_BASE: window.RUNTIME_CONFIG?.API_BASE || 'http://127.0.0.1:18787',
  AUTH_TOKEN: window.RUNTIME_CONFIG?.AUTH_TOKEN || 'edt-local-dev-token',
};

const MAX_NEWS_ITEMS = 50;
const MAX_TRACE_CACHE = 100;

const STATE = {
  ws: null,
  connected: false,
  news: [],
  selectedNews: null,
  sectorsByTrace: {},
  opportunitiesByTrace: {},
  traceOrder: [],
  lastNewsAt: null,
};

function escapeHtml(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function wsUrlWithToken() {
  const url = new URL(CONFIG.WS_URL);
  if (CONFIG.AUTH_TOKEN) url.searchParams.set('token', CONFIG.AUTH_TOKEN);
  return url.toString();
}

function init() {
  connectWebSocket();
  setupEventListeners();
  setInterval(() => updateHUDTime(), 1000);
}

function connectWebSocket() {
  updateConnectionStatus('connecting');
  try {
    STATE.ws = new WebSocket(wsUrlWithToken());
    STATE.ws.onopen = () => {
      STATE.connected = true;
      updateConnectionStatus('connected');
      STATE.ws.send(JSON.stringify({ type: 'subscribe', types: ['event_update', 'sector_update', 'opportunity_update'] }));
      STATE.ws.send(JSON.stringify({ type: 'get_history', limit: 50 }));
    };
    STATE.ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
    STATE.ws.onclose = () => { STATE.connected = false; updateConnectionStatus('disconnected'); setTimeout(connectWebSocket, 3000); };
  } catch (e) {
    updateConnectionStatus('error');
    setTimeout(connectWebSocket, 3000);
  }
}

function handleMessage(data) {
  if (data.type === 'history' || data.type === 'replay') {
    (data.messages || []).forEach(msg => processPayload(msg.type, msg.payload, msg.trace_id, false));
    renderAll();
    return;
  }
  processPayload(data.type, data.payload, data.trace_id, true);
}

function processPayload(type, payload, traceId, shouldRender) {
  const tId = traceId || payload?.trace_id;
  if (!tId) return;

  switch (type) {
    case 'event_update':
      handleEventUpdate(payload, tId);
      break;
    case 'sector_update':
      STATE.sectorsByTrace[tId] = payload;
      break;
    case 'opportunity_update':
      STATE.opportunitiesByTrace[tId] = payload;
      break;
  }
  
  if (!STATE.traceOrder.includes(tId)) {
    STATE.traceOrder.unshift(tId);
    if (STATE.traceOrder.length > MAX_TRACE_CACHE) STATE.traceOrder.pop();
    updateTicker();
  }

  if (shouldRender) {
    if (STATE.selectedNews?.id === tId) {
      renderAnalysis();
      renderOpportunities();
    }
    renderNews();
  }
}

function handleEventUpdate(payload, traceId) {
  const event = {
    id: traceId,
    headline: payload.headline_cn || payload.headline,
    source: payload.source,
    severity: payload.severity || 'E2',
    ai_verdict: payload.ai_verdict,
    ai_confidence: payload.ai_confidence,
    ai_reason: payload.ai_reason,
    timestamp: payload.timestamp || new Date().toISOString(),
  };
  const idx = STATE.news.findIndex(n => n.id === traceId);
  if (idx >= 0) STATE.news[idx] = event;
  else STATE.news.unshift(event);
  if (STATE.news.length > MAX_NEWS_ITEMS) STATE.news.pop();
  STATE.lastNewsAt = event.timestamp;
}

function renderNews() {
  const container = document.getElementById('newsList');
  document.getElementById('newsCount').textContent = STATE.news.length;
  container.innerHTML = STATE.news.map(n => `
    <div class="signal-card ${STATE.selectedNews?.id === n.id ? 'active' : ''}" onclick="selectNews('${n.id}')">
      <div class="signal-meta">
        <span>${escapeHtml(n.source)}</span>
        <span class="signal-severity sev-${n.severity}">${n.severity}</span>
      </div>
      <div class="signal-headline">${escapeHtml(n.headline)}</div>
      <div style="font-size: 9px; color: var(--text-muted); margin-top: 6px;">${n.id}</div>
    </div>
  `).join('');
}

function selectNews(id) {
  STATE.selectedNews = STATE.news.find(n => n.id === id);
  renderNews();
  renderAnalysis();
  renderOpportunities();
}

function renderAnalysis() {
  const n = STATE.selectedNews;
  const traceIdEl = document.getElementById('currentTraceId');
  const verdictBox = document.getElementById('aiVerdictBox');
  const confContainer = document.getElementById('confidenceContainer');
  const confFill = document.getElementById('confidenceFill');
  const sectorList = document.getElementById('sectorList');

  if (!n) return;

  traceIdEl.textContent = `TRACE: ${n.id}`;
  verdictBox.innerHTML = `
    <div style="color: var(--accent-ai); font-weight: 700; margin-bottom: 8px;">VERDICT: ${escapeHtml(n.ai_verdict || 'PENDING')}</div>
    <div style="font-size: 12px; opacity: 0.8;">${escapeHtml(n.ai_reason || 'No detailed reasoning available.')}</div>
  `;

  if (n.ai_confidence) {
    confContainer.style.display = 'block';
    confFill.style.width = `${n.ai_confidence * 100}%`;
  } else {
    confContainer.style.display = 'none';
  }

  const sectors = STATE.sectorsByTrace[n.id]?.sectors || [];
  if (sectors.length > 0) {
    sectorList.innerHTML = sectors.map(s => `
      <div class="conduction-step">
        <div class="step-level">${s.direction}</div>
        <div class="step-name">${escapeHtml(s.name)}</div>
        <div style="margin-left: auto; font-family: monospace; color: var(--accent-bull);">${(s.impact_score * 100).toFixed(0)}%</div>
      </div>
    `).join('');
  } else {
    sectorList.innerHTML = '<div class="empty-state">等待传导数据注入...</div>';
  }
}

function renderOpportunities() {
  const container = document.getElementById('opportunityList');
  const n = STATE.selectedNews;
  if (!n) return;

  const opps = STATE.opportunitiesByTrace[n.id]?.opportunities || [];
  document.getElementById('oppCount').textContent = opps.length;
  
  if (opps.length === 0) {
    container.innerHTML = '<div class="empty-state">该信号暂无匹配的执行机会</div>';
    return;
  }

  container.innerHTML = opps.map(o => `
    <div class="opp-card">
      <div class="opp-header">
        <div class="opp-id">
          <span class="opp-symbol">${o.symbol}</span>
          <span class="opp-name">${escapeHtml(o.name)}</span>
        </div>
        <span class="opp-badge badge-${o.signal.toLowerCase()}">${o.signal}</span>
      </div>
      <div class="opp-stats">
        <div class="stat-item"><div class="stat-label">CONFIDENCE</div><div class="stat-value">${(o.confidence * 100).toFixed(0)}%</div></div>
        <div class="stat-item"><div class="stat-label">ACTION</div><div class="stat-value" style="color: var(--accent-info)">${o.final_action}</div></div>
      </div>
      <button class="opp-action" onclick="handleTrade('${o.symbol}', '${o.final_action}')">INITIATE EXECUTION</button>
    </div>
  `).join('');
}

function updateTicker() {
  const ticker = document.getElementById('tickerTraces');
  ticker.textContent = STATE.traceOrder.slice(0, 5).join('  |  ') + '  |  ' + (STATE.traceOrder.length > 0 ? 'SYSTEM ACTIVE' : 'AWAITING DATA');
}

function updateHUDTime() {
  const lastAt = document.getElementById('lastNewsAt');
  if (STATE.lastNewsAt) {
    const diff = Math.floor((Date.now() - new Date(STATE.lastNewsAt).getTime()) / 1000);
    lastAt.textContent = `LATEST: ${diff}s AGO`;
  }
}

function updateConnectionStatus(status) {
  const el = document.getElementById('connectionStatus');
  el.textContent = status === 'connected' ? 'CONNECTED' : status.toUpperCase();
}

function setupEventListeners() {
  document.getElementById('liveModeBtn').onclick = () => alert('Live Mode Synchronized');
}

function renderAll() {
  renderNews();
  if (STATE.selectedNews) {
    renderAnalysis();
    renderOpportunities();
  }
}

window.selectNews = selectNews;
window.handleTrade = (s, a) => alert(`Executing ${a} for ${s}`);

document.addEventListener('DOMContentLoaded', init);
