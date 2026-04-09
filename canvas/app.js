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
    severity: payload.severity || 'E2',
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
  if (Number.isNaN(date.getTime())) return ts;
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

function setupEventListeners() {
  document.getElementById('sectorFilter').addEventListener('change', (e) => {
    renderSectors(e.target.value);
  });
  
  document.getElementById('playPauseBtn').addEventListener('click', togglePlayPause);
  document.getElementById('liveModeBtn').addEventListener('click', toggleLiveMode);
  
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
        <span class="news-severity severity-${escapeHtml(news.severity)}">${escapeHtml(news.severity)}</span>
      </div>
      <div class="news-time">新闻: ${escapeHtml(formatTimestamp(news.news_timestamp || news.timestamp))} | 推送: ${escapeHtml(formatTimestamp(news.timestamp))}</div>
      <div class="news-headline">${escapeHtml(news.headline || '')}</div>
      ${news.headline_cn ? `<div class="news-headline-cn">${escapeHtml(news.headline_cn)}</div>` : ''}
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
