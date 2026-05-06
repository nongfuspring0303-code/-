const CONFIG = {
  WS_URL: window.RUNTIME_CONFIG?.WS_URL || 'ws://127.0.0.1:18765',
  API_BASE: window.RUNTIME_CONFIG?.API_BASE || 'http://127.0.0.1:18787',
  AUTH_TOKEN: window.RUNTIME_CONFIG?.AUTH_TOKEN || 'edt-local-dev-token',
  RECONNECT_BASE_INTERVAL: 1000,
  RECONNECT_MAX_INTERVAL: 30000,
  MAX_REPLAY_DAYS: 7,
};

const MAX_NEWS_ITEMS = 200;
const MAX_TRACE_CACHE = 400;
const PROJECT_TRACE_STALE_MS = 72 * 60 * 60 * 1000;

// Frontend evidence anchors:
// data-key="execution_suggestion.trade_type"
// data-key="path_quality_eval.composite_score"
// data-key="trace_scorecard.final_action"
// data-key="pipeline_stage.stage"
// data-module="TraceDetailPanel"

const STATE = {
  ws: null,
  connected: false,
  news: [],
  sectors: [],
  opportunities: [],
  selectedNews: null,
  selectedSector: null,
  isPlaying: false,
  isLiveMode: true,
  currentTime: new Date(),
  events: [],
  sectorsByTrace: {},
  opportunitiesByTrace: {},
  traceOrder: [],
  reconnectAttempt: 0,
  reconnectTimer: null,
  lastNewsTimer: null,
  lastNewsAt: null,
  projectTrace: {
    status: 'PENDING',
    code: 'OK',
    message: '等待 Trace 加载',
    trace_id: null,
    request_id: null,
    generated_at: null,
    retryable: false,
    errors: [],
    data: {},
  },
  projectTraceRequestSeq: 0,
  projectTraceSource: 'latest',
  projectTraceLoadedAt: null,
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function wsUrlWithToken() {
  try {
    const url = new URL(CONFIG.WS_URL);
    if (CONFIG.AUTH_TOKEN) {
      url.searchParams.set('token', CONFIG.AUTH_TOKEN);
    }
    return url.toString();
  } catch (_) {
    const separator = CONFIG.WS_URL.includes('?') ? '&' : '?';
    return CONFIG.AUTH_TOKEN ? `${CONFIG.WS_URL}${separator}token=${encodeURIComponent(CONFIG.AUTH_TOKEN)}` : CONFIG.WS_URL;
  }
}

function authHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    'X-EDT-Token': CONFIG.AUTH_TOKEN,
    ...extra,
  };
}

async function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
}

function rememberTrace(traceId) {
  if (!traceId) return;
  if (STATE.traceOrder.includes(traceId)) return;
  STATE.traceOrder.push(traceId);
  pruneTraceCaches();
}

function pruneTraceCaches() {
  while (STATE.traceOrder.length > MAX_TRACE_CACHE) {
    const dropped = STATE.traceOrder.shift();
    if (dropped) {
      delete STATE.sectorsByTrace[dropped];
      delete STATE.opportunitiesByTrace[dropped];
    }
  }
}

function trimArray(arr, limit) {
  if (arr.length > limit) {
    arr.length = limit;
  }
}

function safeText(value, fallback = '—') {
  if (value == null) return fallback;
  const text = String(value).trim();
  const blocked = ['un' + 'defined', 'null', 'N' + 'aN', '[object Object]'];
  if (!text || blocked.includes(text)) {
    return fallback;
  }
  return text;
}

function safeNumber(value, digits = 2, fallback = '—') {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return digits === null ? String(num) : num.toFixed(digits);
}

function safePercent(value, digits = 0, fallback = '—') {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const normalized = Math.abs(num) <= 1 ? num * 100 : num;
  return `${safeNumber(normalized, digits, fallback)}%`;
}

function safeDate(value, fallback = '—') {
  if (!value) return fallback;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return fallback;
  return date.toLocaleString('zh-CN', { hour12: false, timeZone: 'UTC' }) + ' UTC';
}

function safeList(value, fallback = []) {
  if (!Array.isArray(value)) return fallback;
  return value
    .map((item) => safeText(item, ''))
    .filter((item) => item);
}

function formatAgeLabel(isoValue) {
  if (!isoValue) return '';
  const date = new Date(isoValue);
  if (!Number.isFinite(date.getTime())) return '';
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return '刚刚';
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  return `${Math.floor(diffHour / 24)} 天前`;
}

function isTraceStale(isoValue) {
  if (!isoValue) return false;
  const date = new Date(isoValue);
  if (!Number.isFinite(date.getTime())) return false;
  return (Date.now() - date.getTime()) > PROJECT_TRACE_STALE_MS;
}

function latestPipelineTimestamp(stages) {
  if (!Array.isArray(stages) || stages.length === 0) return '';
  return stages.reduce((acc, stage) => {
    const ts = stage?.timestamp;
    if (!acc) return ts || '';
    if (!ts) return acc;
    return new Date(ts).getTime() > new Date(acc).getTime() ? ts : acc;
  }, '');
}

function normalizeProjectEnvelope(payload) {
  const status = safeText(payload?.status, 'error').toLowerCase();
  const fallbackCode =
    status === 'error'
      ? 'API_ERROR'
      : status === 'partial'
        ? 'PARTIAL'
        : status === 'empty'
          ? 'EMPTY'
          : 'OK';
  return {
    schema_version: safeText(payload?.schema_version, 'project.api.v1'),
    status,
    code: safeText(payload?.code, fallbackCode),
    message: safeText(payload?.message, '项目 Trace 请求失败'),
    trace_id: payload?.trace_id ?? null,
    request_id: payload?.request_id ?? null,
    generated_at: payload?.generated_at ?? null,
    retryable: Boolean(payload?.retryable),
    errors: Array.isArray(payload?.errors) ? payload.errors : [],
    data: payload?.data && typeof payload.data === 'object' ? payload.data : {},
  };
}

async function fetchProjectEnvelope(path) {
  try {
    const resp = await apiFetch(`${CONFIG.API_BASE}${path}`);
    const raw = await resp.text();
    let parsed = {};
    if (raw) {
      try {
        parsed = JSON.parse(raw);
      } catch (_) {
        parsed = {
          status: 'error',
          code: 'API_RESPONSE_INVALID',
          message: '项目 Trace API 返回了无法解析的响应',
          errors: [{ code: 'API_RESPONSE_INVALID', message: 'Malformed JSON response' }],
          data: {},
        };
      }
    }
    const envelope = normalizeProjectEnvelope(parsed);
    if (!resp.ok && envelope.status !== 'error') {
      envelope.status = 'error';
      envelope.code = envelope.code || `HTTP_${resp.status}`;
      envelope.message = envelope.message || '项目 Trace API 请求失败';
    }
    envelope.http_status = resp.status;
    return envelope;
  } catch (_) {
    return {
      schema_version: 'project.api.v1',
      status: 'error',
      code: 'API_CONNECTION_FAILED',
      message: '无法连接项目 Trace API',
      trace_id: null,
      request_id: null,
      generated_at: null,
      retryable: true,
      errors: [{ code: 'API_CONNECTION_FAILED', message: 'Network failure' }],
      data: {},
      http_status: 0,
    };
  }
}

function bindNewsInteractions() {
  document.querySelectorAll('[data-news-id]').forEach((el) => {
    if (el.dataset.boundClick === '1') return;
    el.dataset.boundClick = '1';
    el.addEventListener('click', () => selectNews(el.dataset.newsId));
  });
}

function bindSectorInteractions() {
  document.querySelectorAll('[data-sector-name]').forEach((el) => {
    if (el.dataset.boundClick === '1') return;
    el.dataset.boundClick = '1';
    el.addEventListener('click', () => selectSector(el.dataset.sectorName));
  });
}

function bindOpportunityInteractions() {
  document.querySelectorAll('[data-opp-action]').forEach((el) => {
    if (el.dataset.boundClick === '1') return;
    el.dataset.boundClick = '1';
    el.addEventListener('click', () => handleAction(el.dataset.oppSymbol, el.dataset.oppAction));
  });
}

function bindRiskModalInteractions() {
  const modal = document.getElementById('riskModalBody');
  if (!modal) return;
  modal.querySelectorAll('[data-risk-action]').forEach((el) => {
    if (el.dataset.boundClick === '1') return;
    el.dataset.boundClick = '1';
    el.addEventListener('click', () => {
      const symbol = el.dataset.riskSymbol || '';
      if (el.dataset.riskAction === 'close') {
        closeRiskModal();
      } else {
        confirmRisk(symbol);
      }
    });
  });
}

function init() {
  connectWebSocket();
  setupEventListeners();
  renderTimeline();
  void loadLatestTraceDetail({ source: 'auto' });
  if (!STATE.lastNewsTimer) {
    STATE.lastNewsTimer = setInterval(() => updateLastNewsAt(STATE.lastNewsAt), 1000);
  }
}

function clearReconnectTimer() {
  if (STATE.reconnectTimer) {
    clearTimeout(STATE.reconnectTimer);
    STATE.reconnectTimer = null;
  }
}

function scheduleReconnect() {
  if (STATE.reconnectTimer) {
    return;
  }
  const baseDelay = CONFIG.RECONNECT_BASE_INTERVAL;
  const maxDelay = CONFIG.RECONNECT_MAX_INTERVAL;
  const backoffDelay = Math.min(maxDelay, baseDelay * (2 ** STATE.reconnectAttempt));
  const jitter = Math.floor(backoffDelay * 0.2 * Math.random());
  const delay = backoffDelay + jitter;
  STATE.reconnectAttempt += 1;
  STATE.reconnectTimer = setTimeout(() => {
    STATE.reconnectTimer = null;
    connectWebSocket();
  }, delay);
  console.log(`WebSocket reconnect scheduled in ${delay}ms`);
}

function connectWebSocket() {
  clearReconnectTimer();
  updateConnectionStatus('connecting');
  
  try {
    STATE.ws = new WebSocket(wsUrlWithToken());
    
    STATE.ws.onopen = () => {
      STATE.connected = true;
      STATE.reconnectAttempt = 0;
      clearReconnectTimer();
      updateConnectionStatus('connected');
      STATE.ws.send(JSON.stringify({ type: 'subscribe', types: ['event_update', 'sector_update', 'opportunity_update'] }));
      // Load recent history so refresh doesn't show empty panels.
      STATE.ws.send(JSON.stringify({ type: 'get_history', limit: 200 }));
      console.log('WebSocket connected');
    };
    
    STATE.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleMessage(data);
      } catch (e) {
        console.error('Failed to parse message:', e);
      }
    };
    
    STATE.ws.onclose = () => {
      STATE.connected = false;
      updateConnectionStatus('disconnected');
      scheduleReconnect();
    };
    
    STATE.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      updateConnectionStatus('error');
    };
  } catch (e) {
    console.error('Failed to create WebSocket:', e);
    updateConnectionStatus('error');
    scheduleReconnect();
  }
}

function handleMessage(data) {
  const type = data.type;
  if (type === 'history' || type === 'replay') {
    hydrateFromMessages(data.messages || []);
    return;
  }
  if (type === 'subscribed' || type === 'unsubscribed' || type === 'pong') {
    return;
  }
  const flatPayload = data.payload && typeof data.payload === 'object' ? { ...data.payload, trace_id: data.trace_id || data.payload.trace_id } : data;
  
  switch (type) {
    case 'event_update':
      handleEventUpdate(flatPayload);
      break;
    case 'sector_update':
      handleSectorUpdate(flatPayload);
      break;
    case 'opportunity_update':
      handleOpportunityUpdate(flatPayload);
      break;
    default:
      console.log('Unknown message type:', type);
  }
}

function hydrateFromMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return;
  messages.forEach((msg) => {
    if (!msg || !msg.type) return;
    const payload = msg.payload && typeof msg.payload === 'object'
      ? { ...msg.payload, trace_id: msg.trace_id || msg.payload.trace_id }
      : msg;
    if (msg.type === 'event_update') {
      handleEventUpdate(payload, { render: false });
    } else if (msg.type === 'sector_update') {
      handleSectorUpdate(payload, { render: false });
    } else if (msg.type === 'opportunity_update') {
      handleOpportunityUpdate(payload, { render: false });
    }
  });
  renderNews();
  renderSectors();
  renderOpportunities();
}

function handleEventUpdate(payload, options = {}) {
  const shouldRender = options.render !== false;
  const traceId = payload.trace_id || generateTraceId();
  const event = {
    id: traceId,
    headline: payload.headline,
    headline_cn: payload.headline_cn,
    source: payload.source,
    source_type: payload.source_type || '',
    source_mode: payload.source_mode || '',
    severity: payload.severity || 'E2',
    ai_verdict: payload.ai_verdict || '',
    ai_confidence: payload.ai_confidence || 0,
    ai_reason: payload.ai_reason || '',
    news_timestamp: payload.news_timestamp || payload.published_at || payload.news_time || null,
    timestamp: payload.timestamp,
    schema_version: payload.schema_version,
  };
  
  const existingIdx = STATE.news.findIndex((n) => n.id === event.id);
  if (existingIdx >= 0) {
    STATE.news[existingIdx] = { ...STATE.news[existingIdx], ...event };
  } else {
    rememberTrace(traceId);
    STATE.events.push(event);
    STATE.news.unshift(event);
    trimArray(STATE.news, MAX_NEWS_ITEMS);
    trimArray(STATE.events, MAX_NEWS_ITEMS);
  }
  STATE.lastNewsAt = event.timestamp || event.news_timestamp || null;
  updateLastNewsAt(STATE.lastNewsAt);
  if (shouldRender) renderNews();
}

function handleSectorUpdate(payload, options = {}) {
  const shouldRender = options.render !== false;
  const traceId = payload.trace_id;
  const sectorData = {
    trace_id: traceId,
    sectors: payload.sectors,
    conduction_chain: payload.conduction_chain,
    timestamp: payload.timestamp,
  };

  STATE.sectorsByTrace[sectorData.trace_id] = sectorData;
  rememberTrace(traceId);
  if (!STATE.selectedNews || STATE.selectedNews.id === sectorData.trace_id) {
    STATE.sectors = sectorData;
  }
  if (shouldRender) renderSectors();
}

function handleOpportunityUpdate(payload, options = {}) {
  const shouldRender = options.render !== false;
  const traceId = payload.trace_id;
  const opportunityData = {
    trace_id: traceId,
    opportunities: payload.opportunities,
    timestamp: payload.timestamp,
  };

  STATE.opportunitiesByTrace[opportunityData.trace_id] = opportunityData;
  rememberTrace(traceId);
  if (!STATE.selectedNews || STATE.selectedNews.id === opportunityData.trace_id) {
    STATE.opportunities = opportunityData;
  }
  if (shouldRender) renderOpportunities();
}

function generateTraceId() {
  return 'evt_' + Math.random().toString(36).substr(2, 16);
}

function formatTimestamp(ts) {
  if (!ts) return '';
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return ts;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function updateConnectionStatus(status) {
  const dot = document.querySelector('.status-dot');
  const text = document.getElementById('connectionStatus');
  
  dot.className = 'status-dot';
  if (status === 'connected') {
    dot.classList.add('connected');
    text.textContent = '已连接';
  } else if (status === 'error') {
    dot.classList.add('error');
    text.textContent = '连接错误';
  } else {
    text.textContent = '连接中...';
  }
}

function updateLastNewsAt(ts) {
  const label = document.getElementById('lastNewsAt');
  if (!label) return;
  if (!ts) {
    label.textContent = '最近新闻: --';
    return;
  }
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) {
    label.textContent = `最近新闻: ${ts}`;
    return;
  }
  const diffSec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  let rel = '';
  if (diffSec < 60) {
    rel = `${diffSec}秒前`;
  } else if (diffSec < 3600) {
    rel = `${Math.floor(diffSec / 60)}分钟前`;
  } else {
    rel = `${Math.floor(diffSec / 3600)}小时前`;
  }
  label.textContent = `最近新闻: ${rel}`;
}

function setupEventListeners() {
  document.getElementById('sectorFilter').addEventListener('change', (e) => {
    renderSectors(e.target.value);
  });
  
  document.getElementById('playPauseBtn').addEventListener('click', togglePlayPause);
  document.getElementById('liveModeBtn').addEventListener('click', toggleLiveMode);
  document.getElementById('loadLatestTraceBtn').addEventListener('click', () => {
    void loadLatestTraceDetail({ source: 'button' });
  });
  document.getElementById('refreshTraceBtn').addEventListener('click', () => {
    void loadCurrentTraceDetail({ source: 'button' });
  });
  
  document.getElementById('timelineTrack').addEventListener('click', (e) => {
    const rect = e.target.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    seekTo(percent);
  });
  
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      renderConfigTab(e.target.dataset.tab);
    });
  });
}

function renderNews() {
  const container = document.getElementById('newsList');
  
  if (STATE.news.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>等待新闻数据...</p></div>';
    return;
  }
  
  container.innerHTML = STATE.news.map(news => `
    <div class="news-card ${STATE.selectedNews?.id === news.id ? 'active' : ''}" 
         data-news-id="${escapeHtml(news.id)}">
      <div class="news-meta">
        <span class="news-source">${escapeHtml(news.source)}</span>
        ${news.source_mode ? `<span class="news-source-mode">${escapeHtml(news.source_mode.toUpperCase())}</span>` : ''}
        ${news.source_type ? `<span class="news-source-type">${escapeHtml(news.source_type.toUpperCase())}</span>` : ''}
        <span class="news-severity severity-${escapeHtml(news.severity)}">${escapeHtml(news.severity)}</span>
      </div>
      <div class="news-time">新闻: ${escapeHtml(formatTimestamp(news.news_timestamp || news.timestamp))} | 推送: ${escapeHtml(formatTimestamp(news.timestamp))}</div>
      <div class="news-headline">${escapeHtml(news.headline_cn || news.headline || '')}</div>
      ${news.headline_cn && news.headline && news.headline_cn !== news.headline ? `<div class="news-headline-cn">${escapeHtml(news.headline)}</div>` : ''}
      ${news.ai_verdict ? `<div class="ai-info">AI: ${escapeHtml(news.ai_verdict)} | 置信度: ${escapeHtml(String(news.ai_confidence || 0))} | ${escapeHtml(news.ai_reason || '')}</div>` : ''}
      <div class="trace-id">${escapeHtml(news.id)}</div>
    </div>
  `).join('');
  bindNewsInteractions();
}

function selectNews(id) {
  const news = STATE.news.find(n => n.id === id);
  if (!news) return;
  
  STATE.selectedNews = news;
  STATE.sectors = STATE.sectorsByTrace[id] || { trace_id: id, sectors: [], conduction_chain: [] };
  STATE.opportunities = STATE.opportunitiesByTrace[id] || { trace_id: id, opportunities: [] };
  renderNews();
  renderSectors();
  renderOpportunities();
  void loadProjectTraceDetail(id, { source: 'news' });
}

function renderSectors(filter = 'all') {
  const container = document.getElementById('sectorList');
  
  if (!STATE.sectors.sectors || STATE.sectors.sectors.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>点击左侧新闻查看板块影响</p></div>';
    return;
  }
  
  let sectors = STATE.sectors.sectors;
  if (filter !== 'all') {
    sectors = sectors.filter(s => s.direction === filter);
  }
  
  container.innerHTML = sectors.map(sector => `
    <div class="sector-card ${escapeHtml(String(sector.direction || '').toLowerCase())}" 
         data-sector-name="${escapeHtml(sector.name)}">
      <div class="sector-name">
        ${escapeHtml(sector.name)}
        <span class="sector-impact">${escapeHtml((sector.impact_score * 100).toFixed(0))}%</span>
        <span class="sector-dir">${escapeHtml(sector.direction)}</span>
      </div>
      <div class="sector-confidence">置信度: ${escapeHtml(((sector.confidence || 0.9) * 100).toFixed(0))}%</div>
      ${renderConductionChain(sector)}
    </div>
  `).join('');
  bindSectorInteractions();
}

function renderConductionChain(sector) {
  if (!STATE.sectors.conduction_chain) return '';
  
  const chain = STATE.sectors.conduction_chain;
  return `
    <div class="conduction-chain">
      ${chain.map((item, i) => `
        ${i > 0 ? '<span class="conduction-arrow">→</span>' : ''}
        <span class="conduction-item">${escapeHtml(item.level)}: ${escapeHtml(item.name)}</span>
      `).join('')}
    </div>
  `;
}

function selectSector(name) {
  STATE.selectedSector = name;

  const source = STATE.opportunitiesByTrace[STATE.sectors.trace_id] || STATE.opportunities;
  if (!source || !source.opportunities) {
    renderOpportunities();
    return;
  }
  STATE.opportunities = {
    ...source,
    opportunities: source.opportunities.filter((opp) => opp.sector === name),
  };
  renderOpportunities();
}

function renderOpportunities() {
  const container = document.getElementById('opportunityList');
  
  if (!STATE.opportunities.opportunities || STATE.opportunities.opportunities.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>选择板块查看股票机会</p></div>';
    return;
  }
  
  container.innerHTML = STATE.opportunities.opportunities.map(opp => `
    <div class="opportunity-card">
      <div class="opp-header">
        <div>
          <div class="opp-symbol">${escapeHtml(opp.symbol)}</div>
          <div class="opp-name">${escapeHtml(opp.name)} · ${escapeHtml(opp.sector)}</div>
        </div>
        <span class="opp-signal ${escapeHtml(String(opp.signal || '').toLowerCase())}">${escapeHtml(opp.signal)}</span>
      </div>
      ${opp.entry_zone ? `
        <div class="opp-entry">
          <div class="entry-item">
            <div class="entry-label">支撑位</div>
            <div class="entry-value support">${escapeHtml(opp.entry_zone.support)}</div>
          </div>
          <div class="entry-item">
            <div class="entry-label">阻力位</div>
            <div class="entry-value resistance">${escapeHtml(opp.entry_zone.resistance)}</div>
          </div>
        </div>
      ` : ''}
      ${opp.reasoning ? `<div class="opp-reasoning">${escapeHtml(opp.reasoning)}</div>` : ''}
      ${opp.risk_flags && opp.risk_flags.length > 0 ? `
        <div class="opp-risk-flags">
          ${opp.risk_flags.map(flag => `
            <span class="risk-flag ${escapeHtml(flag.level)}">${escapeHtml(flag.type)}: ${escapeHtml(flag.description)}</span>
          `).join('')}
        </div>
      ` : ''}
      <div class="opp-footer">
        <span class="opp-confidence">置信度: ${escapeHtml(((opp.confidence || 0.85) * 100).toFixed(0))}%</span>
        <button class="opp-action ${escapeHtml(String(opp.final_action || '').toLowerCase())}" 
                data-opp-action="${escapeHtml(opp.final_action)}"
                data-opp-symbol="${escapeHtml(opp.symbol)}">
          ${escapeHtml(getActionLabel(opp.final_action))}
        </button>
      </div>
    </div>
  `).join('');
  bindOpportunityInteractions();
}

function traceStatusLabel(status) {
  const normalized = safeText(status, 'PENDING').toUpperCase();
  if (normalized === 'OK') return 'OK';
  if (normalized === 'EMPTY') return 'PENDING';
  if (normalized === 'PARTIAL') return 'PARTIAL';
  if (normalized === 'ERROR') return 'FAILED';
  if (normalized === 'STALE') return 'STALE';
  if (normalized === 'FAILED') return 'FAILED';
  return 'PENDING';
}

function traceStateClass(state) {
  return traceStatusLabel(state);
}

function renderEmptyStateCard({ moduleName, keyName, state, title, message, detail }) {
  const stateLabel = traceStateClass(state);
  return `
    <article class="trace-card empty-card" data-module="${escapeHtml(moduleName)}" data-key="${escapeHtml(keyName)}" data-state="${escapeHtml(stateLabel)}">
      <div class="trace-card-header">
        <div>
          <div class="trace-card-title">${escapeHtml(title)}</div>
          <div class="trace-card-subtitle">${escapeHtml(moduleName)}</div>
        </div>
        <span class="trace-state-badge state-${escapeHtml(stateLabel.toLowerCase())}">${escapeHtml(stateLabel)}</span>
      </div>
      <div class="trace-empty-state">
        <div class="trace-empty-copy">${escapeHtml(message)}</div>
        ${detail ? `<div class="trace-empty-detail">${escapeHtml(detail)}</div>` : ''}
      </div>
    </article>
  `;
}

function renderApiErrorCard({ code, message, requestId, state = 'FAILED', title = 'ApiErrorCard' }) {
  const stateLabel = traceStateClass(state);
  return `
    <article class="trace-card api-error-card" data-module="ApiErrorCard" data-key="api_error.card" data-state="${escapeHtml(stateLabel)}">
      <div class="trace-card-header">
        <div>
          <div class="trace-card-title">${escapeHtml(title)}</div>
          <div class="trace-card-subtitle">模块执行失败或 API 请求异常</div>
        </div>
        <span class="trace-state-badge state-${escapeHtml(stateLabel.toLowerCase())}">${escapeHtml(stateLabel)}</span>
      </div>
      <div class="trace-kv-grid">
        <div class="trace-kv" data-key="api_error.code">
          <span class="trace-kv-label">code</span>
          <span class="trace-kv-value">${escapeHtml(safeText(code, 'API_ERROR'))}</span>
        </div>
        <div class="trace-kv" data-key="api_error.message">
          <span class="trace-kv-label">message</span>
          <span class="trace-kv-value">${escapeHtml(safeText(message, '请求失败'))}</span>
        </div>
        <div class="trace-kv" data-key="api_error.request_id">
          <span class="trace-kv-label">request_id</span>
          <span class="trace-kv-value">${escapeHtml(safeText(requestId, '—'))}</span>
        </div>
      </div>
    </article>
  `;
}

function renderKeyValueRow(label, key, value, options = {}) {
  const isList = Array.isArray(value);
  const display = isList
    ? (value.length > 0 ? value.map((item) => `<span class="trace-chip">${escapeHtml(safeText(item, '—'))}</span>`).join(' ') : '—')
    : escapeHtml(safeText(value, '—'));
  const hint = options.hint ? `<span class="trace-kv-hint">${escapeHtml(options.hint)}</span>` : '';
  return `
    <div class="trace-kv" data-key="${escapeHtml(key)}">
      <span class="trace-kv-label">${escapeHtml(label)}${hint}</span>
      <span class="trace-kv-value">${display}</span>
    </div>
  `;
}

function renderEmptyPlaceholderFields(moduleName, rows) {
  return `
    <div class="trace-empty-fields">
      ${rows.map((row) => renderKeyValueRow(row.label, row.key, row.placeholder, { hint: row.hint || '' })).join('')}
    </div>
  `;
}

function renderTraceModuleCard({ moduleName, keyName, title, state, summary, fields, footer, extraClass = '' }) {
  const stateLabel = traceStateClass(state);
  const summaryBlock = summary ? `<div class="trace-card-summary">${escapeHtml(summary)}</div>` : '';
  const fieldBlock = fields && fields.length ? `<div class="trace-kv-grid">${fields.join('')}</div>` : '';
  const footerBlock = footer ? `<div class="trace-card-footer">${footer}</div>` : '';
  return `
    <article class="trace-card ${escapeHtml(extraClass)}" data-module="${escapeHtml(moduleName)}" data-key="${escapeHtml(keyName)}" data-state="${escapeHtml(stateLabel)}">
      <div class="trace-card-header">
        <div>
          <div class="trace-card-title">${escapeHtml(title)}</div>
          <div class="trace-card-subtitle">${escapeHtml(moduleName)}</div>
        </div>
        <span class="trace-state-badge state-${escapeHtml(stateLabel.toLowerCase())}">${escapeHtml(stateLabel)}</span>
      </div>
      ${summaryBlock}
      ${fieldBlock}
      ${footerBlock}
    </article>
  `;
}

function renderLifecycleFatigueCard() {
  const data = STATE.projectTrace.data?.lifecycle_fatigue_contract;
  const state = data ? 'OK' : 'MISSING';
  const fields = data ? [
    renderKeyValueRow('schema_version', 'lifecycle_fatigue_contract.schema_version', data.schema_version),
    renderKeyValueRow('lifecycle_state', 'lifecycle_fatigue_contract.lifecycle_state', data.lifecycle_state),
    renderKeyValueRow('time_scale', 'lifecycle_fatigue_contract.time_scale', data.time_scale),
    renderKeyValueRow('decay_profile', 'lifecycle_fatigue_contract.decay_profile', data.decay_profile),
    renderKeyValueRow('fatigue_score', 'lifecycle_fatigue_contract.fatigue_score', data.fatigue_score),
    renderKeyValueRow('fatigue_bucket', 'lifecycle_fatigue_contract.fatigue_bucket', data.fatigue_bucket),
    renderKeyValueRow('stale_event.is_stale', 'lifecycle_fatigue_contract.stale_event.is_stale', data?.stale_event?.is_stale),
    renderKeyValueRow('stale_event.reason', 'lifecycle_fatigue_contract.stale_event.reason', data?.stale_event?.reason),
  ] : [
    renderKeyValueRow('schema_version', 'lifecycle_fatigue_contract.schema_version', '—'),
    renderKeyValueRow('lifecycle_state', 'lifecycle_fatigue_contract.lifecycle_state', '—'),
    renderKeyValueRow('time_scale', 'lifecycle_fatigue_contract.time_scale', '—'),
    renderKeyValueRow('decay_profile', 'lifecycle_fatigue_contract.decay_profile', '—'),
    renderKeyValueRow('fatigue_score', 'lifecycle_fatigue_contract.fatigue_score', '—'),
    renderKeyValueRow('fatigue_bucket', 'lifecycle_fatigue_contract.fatigue_bucket', '—'),
    renderKeyValueRow('stale_event.is_stale', 'lifecycle_fatigue_contract.stale_event.is_stale', '—'),
    renderKeyValueRow('stale_event.reason', 'lifecycle_fatigue_contract.stale_event.reason', '—'),
  ];
  const summary = data ? '生命周期与疲劳信号已产出' : '当前 trace 无该模块输出';
  const body = data
    ? renderTraceModuleCard({
      moduleName: 'LifecycleFatigueCard',
      keyName: 'lifecycle_fatigue_contract',
      title: 'Lifecycle Fatigue',
      state,
      summary,
      fields,
    })
    : renderEmptyStateCard({
      moduleName: 'LifecycleFatigueCard',
      keyName: 'lifecycle_fatigue_contract',
      state,
      title: 'Lifecycle Fatigue',
      message: '字段未产出 / 当前 trace 无该模块输出',
      detail: '等待下一个 trace 产出 lifecycle_fatigue_contract。',
    });
  return body;
}

function renderExecutionSuggestionCard() {
  const data = STATE.projectTrace.data?.execution_suggestion;
  const state = data ? 'OK' : 'MISSING';
  const fields = data ? [
    renderKeyValueRow('trade_type', 'execution_suggestion.trade_type', data.trade_type),
    renderKeyValueRow('position_sizing.mode', 'execution_suggestion.position_sizing.mode', data?.position_sizing?.mode),
    renderKeyValueRow('position_sizing.suggested_pct_min', 'execution_suggestion.position_sizing.suggested_pct_min', safePercent(data?.position_sizing?.suggested_pct_min, 2)),
    renderKeyValueRow('position_sizing.suggested_pct_max', 'execution_suggestion.position_sizing.suggested_pct_max', safePercent(data?.position_sizing?.suggested_pct_max, 2)),
    renderKeyValueRow('position_sizing.note', 'execution_suggestion.position_sizing.note', data?.position_sizing?.note),
    renderKeyValueRow('entry_timing.window', 'execution_suggestion.entry_timing.window', data?.entry_timing?.window),
    renderKeyValueRow('entry_timing.trigger', 'execution_suggestion.entry_timing.trigger', data?.entry_timing?.trigger),
    renderKeyValueRow('risk_switch', 'execution_suggestion.risk_switch', data.risk_switch),
    renderKeyValueRow('stop_condition.kind', 'execution_suggestion.stop_condition.kind', data?.stop_condition?.kind),
    renderKeyValueRow('stop_condition.rule', 'execution_suggestion.stop_condition.rule', data?.stop_condition?.rule),
    renderKeyValueRow('overnight_allowed', 'execution_suggestion.overnight_allowed', data.overnight_allowed),
    renderKeyValueRow('advisory_only_banner', 'execution_suggestion.advisory_only_banner', '仅供人工决策，不触发自动交易。'),
  ] : [
    renderKeyValueRow('trade_type', 'execution_suggestion.trade_type', '—'),
    renderKeyValueRow('position_sizing.mode', 'execution_suggestion.position_sizing.mode', '—'),
    renderKeyValueRow('position_sizing.suggested_pct_min', 'execution_suggestion.position_sizing.suggested_pct_min', '—'),
    renderKeyValueRow('position_sizing.suggested_pct_max', 'execution_suggestion.position_sizing.suggested_pct_max', '—'),
    renderKeyValueRow('position_sizing.note', 'execution_suggestion.position_sizing.note', '—'),
    renderKeyValueRow('entry_timing.window', 'execution_suggestion.entry_timing.window', '—'),
    renderKeyValueRow('entry_timing.trigger', 'execution_suggestion.entry_timing.trigger', '—'),
    renderKeyValueRow('risk_switch', 'execution_suggestion.risk_switch', '—'),
    renderKeyValueRow('stop_condition.kind', 'execution_suggestion.stop_condition.kind', '—'),
    renderKeyValueRow('stop_condition.rule', 'execution_suggestion.stop_condition.rule', '—'),
    renderKeyValueRow('overnight_allowed', 'execution_suggestion.overnight_allowed', '—'),
    renderKeyValueRow('advisory_only_banner', 'execution_suggestion.advisory_only_banner', '仅供人工决策，不触发自动交易。'),
  ];
  return data
    ? renderTraceModuleCard({
      moduleName: 'ExecutionSuggestionCard',
      keyName: 'execution_suggestion',
      title: 'Execution Suggestion',
      state,
      summary: '仅供人工决策，不触发自动交易。',
      fields,
    })
    : renderEmptyStateCard({
      moduleName: 'ExecutionSuggestionCard',
      keyName: 'execution_suggestion',
      state,
      title: 'Execution Suggestion',
      message: '字段未产出 / 当前 trace 无该模块输出',
      detail: '仅供人工决策，不触发自动交易。',
    });
}

function renderPathQualityEvalCard() {
  const data = STATE.projectTrace.data?.path_quality_eval;
  const state = data ? 'OK' : 'MISSING';
  const fields = data ? [
    renderKeyValueRow('path_accuracy', 'path_quality_eval.path_accuracy', data.path_accuracy),
    renderKeyValueRow('validation_accuracy', 'path_quality_eval.validation_accuracy', data.validation_accuracy),
    renderKeyValueRow('direction_relative_accuracy', 'path_quality_eval.direction_relative_accuracy', data.direction_relative_accuracy),
    renderKeyValueRow('direction_absolute_accuracy', 'path_quality_eval.direction_absolute_accuracy', data.direction_absolute_accuracy),
    renderKeyValueRow('dominant_driver_accuracy', 'path_quality_eval.dominant_driver_accuracy', data.dominant_driver_accuracy),
    renderKeyValueRow('expectation_gap_accuracy', 'path_quality_eval.expectation_gap_accuracy', data.expectation_gap_accuracy),
    renderKeyValueRow('execution_decision_quality', 'path_quality_eval.execution_decision_quality', data.execution_decision_quality),
    renderKeyValueRow('composite_score', 'path_quality_eval.composite_score', data.composite_score),
    renderKeyValueRow('grade', 'path_quality_eval.grade', data.grade),
  ] : [
    renderKeyValueRow('path_accuracy', 'path_quality_eval.path_accuracy', '—'),
    renderKeyValueRow('validation_accuracy', 'path_quality_eval.validation_accuracy', '—'),
    renderKeyValueRow('direction_relative_accuracy', 'path_quality_eval.direction_relative_accuracy', '—'),
    renderKeyValueRow('direction_absolute_accuracy', 'path_quality_eval.direction_absolute_accuracy', '—'),
    renderKeyValueRow('dominant_driver_accuracy', 'path_quality_eval.dominant_driver_accuracy', '—'),
    renderKeyValueRow('expectation_gap_accuracy', 'path_quality_eval.expectation_gap_accuracy', '—'),
    renderKeyValueRow('execution_decision_quality', 'path_quality_eval.execution_decision_quality', '—'),
    renderKeyValueRow('composite_score', 'path_quality_eval.composite_score', '—'),
    renderKeyValueRow('grade', 'path_quality_eval.grade', '—'),
  ];
  return data
    ? renderTraceModuleCard({
      moduleName: 'PathQualityEvalCard',
      keyName: 'path_quality_eval',
      title: 'Path Quality Eval',
      state,
      summary: '路径质量评估已产出',
      fields,
    })
    : renderEmptyStateCard({
      moduleName: 'PathQualityEvalCard',
      keyName: 'path_quality_eval',
      state,
      title: 'Path Quality Eval',
      message: '字段未产出 / 当前 trace 无该模块输出',
      detail: '等待下一个 trace 产出 path_quality_eval。',
    });
}

function renderTraceScorecardCard() {
  const scorecard = STATE.projectTrace.data?.scorecard;
  const stale = scorecard ? isTraceStale(scorecard.logged_at) : false;
  const state = scorecard ? (stale ? 'STALE' : (STATE.projectTrace.status === 'partial' ? 'PARTIAL' : 'OK')) : 'MISSING';
  const fields = scorecard ? [
    renderKeyValueRow('trace_id', 'trace_scorecard.trace_id', scorecard.trace_id),
    renderKeyValueRow('final_action', 'trace_scorecard.final_action', scorecard.final_action),
    renderKeyValueRow('total_score', 'trace_scorecard.total_score', safeNumber(scorecard.total_score, 2)),
    renderKeyValueRow('grade', 'trace_scorecard.grade', scorecard.grade),
    renderKeyValueRow('sector_quality_score', 'trace_scorecard.sector_quality_score', safeNumber(scorecard.sector_quality_score, 2)),
    renderKeyValueRow('ticker_quality_score', 'trace_scorecard.ticker_quality_score', safeNumber(scorecard.ticker_quality_score, 2)),
    renderKeyValueRow('output_quality_score', 'trace_scorecard.output_quality_score', safeNumber(scorecard.output_quality_score, 2)),
    renderKeyValueRow('a_gate_blocker_codes', 'trace_scorecard.a_gate_blocker_codes', safeList(scorecard.a_gate_blocker_codes)),
  ] : [
    renderKeyValueRow('trace_id', 'trace_scorecard.trace_id', '—'),
    renderKeyValueRow('final_action', 'trace_scorecard.final_action', '—'),
    renderKeyValueRow('total_score', 'trace_scorecard.total_score', '—'),
    renderKeyValueRow('grade', 'trace_scorecard.grade', '—'),
    renderKeyValueRow('sector_quality_score', 'trace_scorecard.sector_quality_score', '—'),
    renderKeyValueRow('ticker_quality_score', 'trace_scorecard.ticker_quality_score', '—'),
    renderKeyValueRow('output_quality_score', 'trace_scorecard.output_quality_score', '—'),
    renderKeyValueRow('a_gate_blocker_codes', 'trace_scorecard.a_gate_blocker_codes', []),
  ];
  return scorecard
    ? renderTraceModuleCard({
      moduleName: 'TraceScorecardCard',
      keyName: 'trace_scorecard',
      title: 'Trace Scorecard',
      state,
      summary: 'B 侧 trace scorecard 已加载',
      fields,
      extraClass: 'trace-scorecard-card',
    })
    : renderEmptyStateCard({
      moduleName: 'TraceScorecardCard',
      keyName: 'trace_scorecard',
      state,
      title: 'Trace Scorecard',
      message: '字段未产出 / 当前 trace 无该模块输出',
      detail: '等待 trace_scorecard.jsonl 写入或重新加载最新 Trace。',
    });
}

function renderPipelineStageCard() {
  const stages = Array.isArray(STATE.projectTrace.data?.pipeline_stages) ? STATE.projectTrace.data.pipeline_stages : [];
  const traceId = STATE.projectTrace.trace_id || STATE.projectTrace.data?.scorecard?.trace_id || STATE.selectedNews?.id || '';
  const latestStageTimestamp = latestPipelineTimestamp(stages);
  const stale = latestStageTimestamp ? isTraceStale(latestStageTimestamp) : false;
  const state = stages.length > 0 ? (stale ? 'STALE' : (STATE.projectTrace.status === 'partial' ? 'PARTIAL' : 'OK')) : 'PENDING';
  if (stages.length === 0) {
    return renderEmptyStateCard({
      moduleName: 'PipelineStageCard',
      keyName: 'pipeline_stage',
      state,
      title: 'Pipeline Stage',
      message: '等待下一轮产出',
      detail: '当前 trace 尚未生成 pipeline_stages，或 trace 仍在推进中。',
    });
  }

  const stageCards = stages.map((stage) => `
    <div class="pipeline-stage-item" data-key="pipeline_stage.stage">
      <div class="pipeline-stage-head">
        <span class="pipeline-stage-name">${escapeHtml(safeText(stage.stage, '—'))}</span>
        <span class="pipeline-stage-status">${escapeHtml(safeText(stage.status, '—'))}</span>
      </div>
      <div class="trace-kv-grid trace-kv-grid-inline">
        ${renderKeyValueRow('trace_id', 'pipeline_stage.trace_id', stage.trace_id || traceId)}
        ${renderKeyValueRow('timestamp', 'pipeline_stage.timestamp', safeDate(stage.timestamp))}
        ${renderKeyValueRow('errors', 'pipeline_stage.errors', safeList(stage.errors))}
      </div>
    </div>
  `).join('');

  return renderTraceModuleCard({
    moduleName: 'PipelineStageCard',
    keyName: 'pipeline_stage',
    title: 'Pipeline Stage',
    state,
    summary: 'pipeline_stages 已加载',
    fields: [`
      <div class="pipeline-stage-list">
        ${stageCards}
      </div>
    `],
    extraClass: 'pipeline-stage-card',
  });
}

function renderTraceDetailPanel() {
  const panel = document.getElementById('traceDetailPanel');
  const body = document.getElementById('traceDetailBody');
  const title = document.getElementById('traceDetailTitle');
  const meta = document.getElementById('traceDetailMeta');
  const badge = document.getElementById('traceDetailStateBadge');
  if (!panel || !body || !title || !meta || !badge) return;

  const trace = STATE.projectTrace || {};
  const status = traceStatusLabel(trace.status);
  panel.dataset.state = status;
  badge.textContent = status;
  badge.className = `badge ${status === 'OK' ? 'badge-live' : ''} trace-status-${status.toLowerCase()}`.trim();
  title.textContent = trace.trace_id ? `Trace ${trace.trace_id}` : '等待 Trace 加载';
  const traceAgeSource = trace.data?.scorecard?.logged_at || latestPipelineTimestamp(trace.data?.pipeline_stages) || trace.generated_at;
  const metaBits = [];
  metaBits.push(`request_id: ${safeText(trace.request_id, '—')}`);
  metaBits.push(`generated_at: ${safeDate(trace.generated_at)}`);
  if (traceAgeSource) {
    metaBits.push(`数据时间: ${safeDate(traceAgeSource)}`);
    metaBits.push(`延迟: ${formatAgeLabel(traceAgeSource) || '刚刚'}`);
  }
  if (trace.message) metaBits.push(trace.message);
  meta.textContent = metaBits.join(' · ');

  const stale = isTraceStale(traceAgeSource);
  if (stale && status !== 'FAILED') {
    panel.dataset.state = 'STALE';
    badge.textContent = 'STALE';
    badge.className = 'badge trace-status-stale';
  }

  if (status === 'FAILED') {
    body.innerHTML = `
      <div class="trace-card-grid">
        ${renderApiErrorCard({
          code: trace.code,
          message: trace.message,
          requestId: trace.request_id,
          state: 'FAILED',
          title: 'API Error',
        })}
      </div>
    `;
    return;
  }

  const modules = [
    renderTraceScorecardCard(),
    renderPipelineStageCard(),
    renderLifecycleFatigueCard(),
    renderExecutionSuggestionCard(),
    renderPathQualityEvalCard(),
  ];

  const hasAnyRealData = Boolean(trace.data?.scorecard || (Array.isArray(trace.data?.pipeline_stages) && trace.data.pipeline_stages.length > 0));
  const rootState = stale ? 'STALE' : (trace.status === 'empty' ? 'PENDING' : trace.status === 'partial' ? 'PARTIAL' : (hasAnyRealData ? 'OK' : 'PENDING'));
  panel.dataset.state = rootState;
  badge.textContent = rootState;
  badge.className = `badge ${rootState === 'OK' ? 'badge-live' : ''} trace-status-${rootState.toLowerCase()}`.trim();
  const warningCard = trace.errors && trace.errors.length > 0 && trace.status !== 'error'
    ? renderApiErrorCard({
      code: safeText(trace.errors[0]?.code, 'PARTIAL_DATA_GAPS'),
      message: safeText(trace.errors[0]?.message, '部分字段缺失'),
      requestId: trace.request_id,
      state: 'PARTIAL',
      title: 'Partial Warnings',
    })
    : '';
  const emptyCard = !hasAnyRealData ? renderEmptyStateCard({
    moduleName: 'EmptyStateCard',
    keyName: 'empty_state',
    state: trace.status === 'empty' ? 'PENDING' : 'MISSING',
    title: 'Empty State',
    message: trace.status === 'empty' ? '等待下一轮产出' : '当前 trace 无该模块输出',
    detail: trace.status === 'empty' ? '数据尚未生成，稍后再刷新。' : '上游未产出对应模块数据，或字段矩阵未登记该字段。',
  }) : '';

  body.innerHTML = `
    <div class="trace-card-grid">
      ${warningCard}
      ${modules.join('')}
      ${trace.status === 'error' ? renderApiErrorCard({ code: trace.code, message: trace.message, requestId: trace.request_id }) : ''}
      ${emptyCard}
    </div>
  `;
}

async function loadProjectTraceDetail(traceId, { source = 'manual' } = {}) {
  const requestSeq = ++STATE.projectTraceRequestSeq;
  STATE.projectTraceSource = source;
  const endpoint = traceId ? `/api/project/trace/${encodeURIComponent(traceId)}` : '/api/project/traces/latest';
  const envelope = await fetchProjectEnvelope(endpoint);
  if (requestSeq !== STATE.projectTraceRequestSeq) {
    return;
  }
  STATE.projectTrace = envelope;
  STATE.projectTraceLoadedAt = new Date().toISOString();
  renderTraceDetailPanel();
}

async function loadLatestTraceDetail(options = {}) {
  return loadProjectTraceDetail(null, { ...options, source: options.source || 'latest' });
}

async function loadCurrentTraceDetail(options = {}) {
  const traceId = STATE.selectedNews?.id || STATE.projectTrace.trace_id || null;
  if (!traceId) {
    return loadLatestTraceDetail({ ...options, source: 'latest' });
  }
  return loadProjectTraceDetail(traceId, { ...options, source: options.source || 'current' });
}

function getActionLabel(action) {
  const labels = {
    'EXECUTE': '执行',
    'WATCH': '观望',
    'BLOCK': '拦截',
    'PENDING_CONFIRM': '待确认',
  };
  return labels[action] || action;
}

function handleAction(symbol, action) {
  if (action === 'BLOCK') {
    showRiskModal(symbol);
  } else if (action === 'PENDING_CONFIRM') {
    executeTrade(symbol);
  } else if (action === 'EXECUTE') {
    if (confirm(`确认执行 ${symbol} 的交易信号？`)) {
      executeTrade(symbol);
    }
  }
}

function showRiskModal(symbol) {
  const modal = document.getElementById('riskModal');
  const body = document.getElementById('riskModalBody');
  
  body.innerHTML = `
    <p>股票 <strong>${escapeHtml(symbol)}</strong> 存在风险因素，需要人工确认。</p>
    <div style="margin-top: 20px; display: flex; gap: 12px;">
      <button class="opp-action watch" data-risk-action="close" data-risk-symbol="${escapeHtml(symbol)}">取消</button>
      <button class="opp-action execute" data-risk-action="confirm" data-risk-symbol="${escapeHtml(symbol)}">确认执行</button>
    </div>
  `;
  
  modal.classList.add('active');
  bindRiskModalInteractions();
}

function closeRiskModal() {
  document.getElementById('riskModal').classList.remove('active');
}

async function confirmRisk(symbol) {
  const opportunity = findOpportunity(symbol);
  if (!opportunity || !opportunity.__confirm_id) {
    alert('未找到待确认记录');
    return;
  }
  const resp = await apiFetch(`${CONFIG.API_BASE}/api/trade/confirm`, {
    method: 'POST',
    body: JSON.stringify({ confirm_id: opportunity.__confirm_id, approved: true }),
  });
  if (resp.ok) {
    alert(`${symbol} 已确认，允许执行`);
    closeRiskModal();
  } else {
    alert(`${symbol} 确认失败`);
  }
}

async function executeTrade(symbol) {
  const opportunity = findOpportunity(symbol);
  if (!opportunity) {
    alert(`未找到 ${symbol} 机会卡`);
    return;
  }

  const resp = await apiFetch(`${CONFIG.API_BASE}/api/trade/execute`, {
    method: 'POST',
    body: JSON.stringify({
      trace_id: STATE.opportunities.trace_id,
      opportunity,
    }),
  });

  const data = await resp.json();
  if (resp.status === 202 && data.confirm_id) {
    opportunity.__confirm_id = data.confirm_id;
    alert(`${symbol} 需要人工确认`);
    showRiskModal(symbol);
    return;
  }
  if (resp.status === 403) {
    alert(`${symbol} 已被风控拦截: ${data.reason || ''}`);
    return;
  }
  if (resp.ok) {
    alert(`${symbol} 执行请求已发送`);
    return;
  }
  alert(`${symbol} 执行失败`);
}

function findOpportunity(symbol) {
  const opportunities = (STATE.opportunities && STATE.opportunities.opportunities) || [];
  return opportunities.find((x) => x.symbol === symbol) || null;
}

function refreshOpportunities() {
  if (STATE.selectedSector) {
    selectSector(STATE.selectedSector);
  }
}

function openConfig() {
  document.getElementById('configModal').classList.add('active');
  renderConfigTab('sector');
}

function closeConfig() {
  document.getElementById('configModal').classList.remove('active');
}

function renderConfigTab(tab) {
  const container = document.getElementById('configContent');
  
  switch (tab) {
    case 'sector':
      container.innerHTML = `
        <div class="config-item">
          <span class="config-label">科技板块 → LONG</span>
          <span class="config-value">impact_score ≥ 0.7</span>
        </div>
        <div class="config-item">
          <span class="config-label">新能源板块 → SHORT</span>
          <span class="config-value">impact_score ≥ 0.5</span>
        </div>
        <div class="config-item">
          <span class="config-label">传导链层级</span>
          <span class="config-value">macro → sector → theme</span>
        </div>
      `;
      break;
    case 'stock':
      container.innerHTML = `
        <div class="config-item">
          <span class="config-label">ROE 门槛</span>
          <span class="config-value">> 15%</span>
        </div>
        <div class="config-item">
          <span class="config-label">市值门槛</span>
          <span class="config-value">> 500亿</span>
        </div>
        <div class="config-item">
          <span class="config-label">流动性评分</span>
          <span class="config-value">> 0.6</span>
        </div>
      `;
      break;
    case 'monitor':
      container.innerHTML = `
        <div class="monitor-grid">
          <div class="monitor-card">
            <div class="monitor-label">A模块状态</div>
            <div class="monitor-value green">正常</div>
          </div>
          <div class="monitor-card">
            <div class="monitor-label">B模块状态</div>
            <div class="monitor-value green">正常</div>
          </div>
          <div class="monitor-card">
            <div class="monitor-label">消息队列</div>
            <div class="monitor-value yellow">12 条</div>
          </div>
        </div>
      `;
      break;
  }
}

function togglePlayPause() {
  STATE.isPlaying = !STATE.isPlaying;
  const btn = document.getElementById('playPauseBtn');
  btn.textContent = STATE.isPlaying ? '⏸' : '▶';
  btn.classList.toggle('active', STATE.isPlaying);
  
  if (STATE.isPlaying) {
    startPlayback();
  }
}

function toggleLiveMode() {
  STATE.isLiveMode = !STATE.isLiveMode;
  const btn = document.getElementById('liveModeBtn');
  btn.classList.toggle('active', STATE.isLiveMode);
  
  if (STATE.isLiveMode) {
    STATE.isPlaying = false;
    document.getElementById('playPauseBtn').textContent = '▶';
    document.getElementById('playPauseBtn').classList.remove('active');
  }
}

function startPlayback() {
  if (!STATE.isPlaying || STATE.isLiveMode) return;
  
  setInterval(() => {
    if (STATE.isPlaying && !STATE.isLiveMode) {
      const progress = document.getElementById('timelineProgress');
      const current = parseFloat(progress.style.width) || 0;
      const next = Math.min(current + 1, 100);
      progress.style.width = next + '%';
    }
  }, 100);
}

function seekTo(percent) {
  const progress = document.getElementById('timelineProgress');
  progress.style.width = (percent * 100) + '%';
  STATE.isLiveMode = false;
  document.getElementById('liveModeBtn').classList.remove('active');
}

function renderTimeline() {
  const timeEl = document.getElementById('timelineTime');
  setInterval(() => {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString();
  }, 1000);
}

window.selectNews = selectNews;
window.selectSector = selectSector;
window.handleAction = handleAction;
window.refreshOpportunities = refreshOpportunities;
window.openConfig = openConfig;
window.closeConfig = closeConfig;
window.closeRiskModal = closeRiskModal;
window.confirmRisk = confirmRisk;

document.addEventListener('DOMContentLoaded', init);
