const CONFIG = {
  WS_URL: 'ws://127.0.0.1:8765',
  API_BASE: 'http://127.0.0.1:8787',
  RECONNECT_INTERVAL: 3000,
  MAX_REPLAY_DAYS: 7,
};

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
};

function init() {
  connectWebSocket();
  setupEventListeners();
  renderTimeline();
}

function connectWebSocket() {
  updateConnectionStatus('connecting');
  
  try {
    STATE.ws = new WebSocket(CONFIG.WS_URL);
    
    STATE.ws.onopen = () => {
      STATE.connected = true;
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
      setTimeout(connectWebSocket, CONFIG.RECONNECT_INTERVAL);
    };
    
    STATE.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      updateConnectionStatus('error');
    };
  } catch (e) {
    console.error('Failed to create WebSocket:', e);
    updateConnectionStatus('error');
    setTimeout(connectWebSocket, CONFIG.RECONNECT_INTERVAL);
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
  const event = {
    id: payload.trace_id || generateTraceId(),
    headline: payload.headline,
    source: payload.source,
    severity: payload.severity || 'E2',
    timestamp: payload.timestamp,
    schema_version: payload.schema_version,
  };
  
  const existingIdx = STATE.news.findIndex((n) => n.id === event.id);
  if (existingIdx >= 0) {
    STATE.news[existingIdx] = { ...STATE.news[existingIdx], ...event };
  } else {
    STATE.events.push(event);
    STATE.news.unshift(event);
  }
  if (shouldRender) renderNews();
}

function handleSectorUpdate(payload, options = {}) {
  const shouldRender = options.render !== false;
  const sectorData = {
    trace_id: payload.trace_id,
    sectors: payload.sectors,
    conduction_chain: payload.conduction_chain,
    timestamp: payload.timestamp,
  };

  STATE.sectorsByTrace[sectorData.trace_id] = sectorData;
  if (!STATE.selectedNews || STATE.selectedNews.id === sectorData.trace_id) {
    STATE.sectors = sectorData;
  }
  if (shouldRender) renderSectors();
}

function handleOpportunityUpdate(payload, options = {}) {
  const shouldRender = options.render !== false;
  const opportunityData = {
    trace_id: payload.trace_id,
    opportunities: payload.opportunities,
    timestamp: payload.timestamp,
  };

  STATE.opportunitiesByTrace[opportunityData.trace_id] = opportunityData;
  if (!STATE.selectedNews || STATE.selectedNews.id === opportunityData.trace_id) {
    STATE.opportunities = opportunityData;
  }
  if (shouldRender) renderOpportunities();
}

function generateTraceId() {
  return 'evt_' + Math.random().toString(36).substr(2, 16);
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
         onclick="selectNews('${news.id}')">
      <div class="news-meta">
        <span class="news-source">${news.source}</span>
        <span class="news-severity severity-${news.severity}">${news.severity}</span>
      </div>
      <div class="news-headline">${news.headline}</div>
      <div class="trace-id">${news.id}</div>
    </div>
  `).join('');
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
    <div class="sector-card ${sector.direction.toLowerCase()}" 
         onclick="selectSector('${sector.name}')">
      <div class="sector-name">
        ${sector.name}
        <span class="sector-impact">${(sector.impact_score * 100).toFixed(0)}%</span>
        <span class="sector-dir">${sector.direction}</span>
      </div>
      <div class="sector-confidence">置信度: ${((sector.confidence || 0.9) * 100).toFixed(0)}%</div>
      ${renderConductionChain(sector)}
    </div>
  `).join('');
}

function renderConductionChain(sector) {
  if (!STATE.sectors.conduction_chain) return '';
  
  const chain = STATE.sectors.conduction_chain;
  return `
    <div class="conduction-chain">
      ${chain.map((item, i) => `
        ${i > 0 ? '<span class="conduction-arrow">→</span>' : ''}
        <span class="conduction-item">${item.level}: ${item.name}</span>
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
          <div class="opp-symbol">${opp.symbol}</div>
          <div class="opp-name">${opp.name} · ${opp.sector}</div>
        </div>
        <span class="opp-signal ${opp.signal.toLowerCase()}">${opp.signal}</span>
      </div>
      ${opp.entry_zone ? `
        <div class="opp-entry">
          <div class="entry-item">
            <div class="entry-label">支撑位</div>
            <div class="entry-value support">${opp.entry_zone.support}</div>
          </div>
          <div class="entry-item">
            <div class="entry-label">阻力位</div>
            <div class="entry-value resistance">${opp.entry_zone.resistance}</div>
          </div>
        </div>
      ` : ''}
      ${opp.reasoning ? `<div class="opp-reasoning">${opp.reasoning}</div>` : ''}
      ${opp.risk_flags && opp.risk_flags.length > 0 ? `
        <div class="opp-risk-flags">
          ${opp.risk_flags.map(flag => `
            <span class="risk-flag ${flag.level}">${flag.type}: ${flag.description}</span>
          `).join('')}
        </div>
      ` : ''}
      <div class="opp-footer">
        <span class="opp-confidence">置信度: ${((opp.confidence || 0.85) * 100).toFixed(0)}%</span>
        <button class="opp-action ${opp.final_action.toLowerCase()}" 
                onclick="handleAction('${opp.symbol}', '${opp.final_action}')">
          ${getActionLabel(opp.final_action)}
        </button>
      </div>
    </div>
  `).join('');
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
    <p>股票 <strong>${symbol}</strong> 存在风险因素，需要人工确认。</p>
    <div style="margin-top: 20px; display: flex; gap: 12px;">
      <button class="opp-action watch" onclick="closeRiskModal()">取消</button>
      <button class="opp-action execute" onclick="confirmRisk('${symbol}')">确认执行</button>
    </div>
  `;
  
  modal.classList.add('active');
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
  const resp = await fetch(`${CONFIG.API_BASE}/api/trade/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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

  const resp = await fetch(`${CONFIG.API_BASE}/api/trade/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
