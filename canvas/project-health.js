/**
 * EDT Project Health Console - PR-3 Main Controller
 * Refactored for V2.1 Compliance: 
 * 1. Zero-InnerHTML for report data (XSS protection)
 * 2. Sequential Async loop
 * 3. 10m Stale detection
 * 4. Full KPI Matrix support
 */

const HEALTH_STATE = {
  report: null,
  lastUpdate: null,
  isRefreshing: false,
  config: {
    refreshMs: 5000,
    // V2.1 Compliance: Use centralized API entry point
    reportPath: window.EDT_CONFIG?.API_ROOT ? `${window.EDT_CONFIG.API_ROOT}/project/gap-report` : '../logs/project_gap_report.json',
    staleThresholdMs: 10 * 60 * 1000 
  }
};


document.addEventListener('DOMContentLoaded', () => {
  initHealthDashboard();
});

async function initHealthDashboard() {
  console.log('Initializing Health Dashboard (V2.1 Strict Mode)...');
  
  // Static Event Listeners
  document.getElementById('goHomeBtn')?.addEventListener('click', () => {
    window.location.href = 'index.html';
  });

  const searchInput = document.getElementById('findingSearch');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => renderFindings(e.target.value));
  }

  // Start serial loop
  await safeRefreshLoop();
}

async function safeRefreshLoop() {
  if (HEALTH_STATE.isRefreshing) return;
  
  try {
    HEALTH_STATE.isRefreshing = true;
    await refreshReport();
  } finally {
    HEALTH_STATE.isRefreshing = false;
    setTimeout(safeRefreshLoop, HEALTH_STATE.config.refreshMs);
  }
}

async function refreshReport() {
  try {
    const response = await fetch(HEALTH_STATE.config.reportPath + '?t=' + Date.now());
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const body = await response.json();
    
    // V2.1 Compliance: Support both direct JSON and Envelope structure
    const report = body.data || body; 
    
    if (!report || !report.findings) {
      throw new Error("Invalid report structure");
    }

    HEALTH_STATE.report = report;
    HEALTH_STATE.lastUpdate = new Date();
    
    updateDashboardUI();
  } catch (err) {
    console.warn('Dashboard ingestion warning:', err);
    showDisconnected();
  }
}


function updateDashboardUI() {
  const report = HEALTH_STATE.report;
  if (!report) return;

  const app = document.getElementById('app');
  app.setAttribute('data-state', 'READY');

  // 1. Freshness & Overall Status
  const freshness = getReportFreshnessState(report.generated_at);
  const header = document.getElementById('healthHeader');
  const statusText = document.getElementById('statusText');
  const lastScan = document.getElementById('lastScanAt');

  header.className = `status-bar status-${freshness.state === 'OK' ? report.overall_status : freshness.state}`;
  header.setAttribute('data-state', freshness.state);
  statusText.textContent = `PROJECT STATUS: ${report.overall_status} [${freshness.state}]`;
  lastScan.textContent = `Last Scan: ${report.generated_at || 'MISSING'}`;
  lastScan.className = freshness.state === 'STALE' ? 'text-danger' : '';

  // 2. KPI Updates (Strict textContent)
  updateKPI('p0Count', report.summary?.p0_count, 'health.p0_count');
  updateKPI('p1Count', report.summary?.p1_count, 'health.p1_count');
  updateKPI('p2Count', report.summary?.p2_count, 'health.p2_count');
  updateKPI('currentCommit', report.summary?.current_commit, 'health.current_commit');
  
  // Coverage Metrics (No hardcoding)
  updateKPI('feCoverage', report.metrics?.frontend_coverage, 'health.frontend_coverage', '%');
  updateKPI('contractCoverage', report.metrics?.contract_coverage, 'health.contract_coverage', '%');
  updateKPI('testHealth', report.metrics?.test_success_rate, 'health.test_health', '%');
  updateKPI('hardcodedRisk', report.metrics?.hardcoded_risk_count, 'health.hardcoded_risk');
  
  updateKPI('logFreshness', freshness.state, 'health.log_freshness');


  // Delta
  updateText('newCount', report.delta_vs_prev?.new_count);
  updateText('resolvedCount', report.delta_vs_prev?.resolved_count);
  updateText('unchangedCount', report.delta_vs_prev?.unchanged_count);

  renderFindings();
  renderSuggestions();
  renderP0Blockers();
}


function updateKPI(id, value, dataKey, suffix = '') {
  const el = document.getElementById(id);
  if (!el) return;
  
  if (value === undefined || value === null) {
    el.textContent = 'MISSING';
    el.closest('.kpi-card')?.setAttribute('data-state', 'MISSING');
  } else {
    el.textContent = `${value}${suffix}`;
    el.closest('.kpi-card')?.setAttribute('data-state', 'OK');
  }
}

function updateText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = (value !== undefined && value !== null) ? value : '--';
}

function getReportFreshnessState(generatedAt) {
  if (!generatedAt) return { state: "MISSING", elapsedMs: null };

  const ts = Date.parse(generatedAt);
  if (Number.isNaN(ts)) return { state: "FAILED", elapsedMs: null };

  const elapsedMs = Date.now() - ts;
  if (elapsedMs > HEALTH_STATE.config.staleThresholdMs) return { state: "STALE", elapsedMs };

  return { state: "OK", elapsedMs };
}

function renderFindings(filter = '') {
  const container = document.getElementById('findingList');
  if (!container || !HEALTH_STATE.report) return;

  const findings = (HEALTH_STATE.report.findings || []).filter(f => f != null);
  const filtered = findings.filter(f => 
    !f.suppressed && 
    ((f.module || '').toLowerCase().includes(filter.toLowerCase()) || 
     (f.message || '').toLowerCase().includes(filter.toLowerCase()))
  );

  container.innerHTML = ''; // Clear for element-based rendering
  
  if (filtered.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.style.height = '100px';
    empty.style.color = 'var(--accent-green)';
    empty.textContent = '✅ No active gaps found.';
    container.appendChild(empty);
    return;
  }

  filtered.forEach(f => {
    const row = document.createElement('div');
    row.className = 'finding-row';

    // Meta Column
    const metaCol = document.createElement('div');
    metaCol.className = 'finding-meta-col';
    
    const tag = document.createElement('span');
    tag.className = `severity-tag severity-${f.severity}`;
    tag.textContent = f.severity;
    
    const stats = document.createElement('div');
    stats.style.fontSize = '10px';
    stats.style.color = 'var(--text-muted)';
    stats.style.marginTop = '4px';
    stats.textContent = `Seen: ${f.seen_days || 0}d / ${f.occurrence_count || 0}x`;
    
    metaCol.appendChild(tag);
    metaCol.appendChild(stats);

    // Category & Module
    const cat = document.createElement('span');
    cat.style.color = 'var(--text-secondary)';
    cat.style.fontSize = '12px';
    cat.textContent = f.category || '-';

    const modBox = document.createElement('div');
    modBox.style.display = 'flex';
    modBox.style.flexDirection = 'column';
    modBox.style.gap = '4px';
    
    const mod = document.createElement('span');
    mod.style.fontFamily = 'monospace';
    mod.style.color = 'var(--accent-blue)';
    mod.textContent = f.module || '-';
    
    const key = document.createElement('span');
    key.style.fontSize = '10px';
    key.style.color = 'var(--accent-purple)';
    key.textContent = `Key: ${f.normalized_field || '-'}`;
    
    modBox.appendChild(mod);
    modBox.appendChild(key);

    // Message
    const msgBox = document.createElement('div');
    msgBox.className = 'finding-msg';
    
    const msgText = document.createElement('div');
    msgText.textContent = f.message || '';
    
    const source = document.createElement('div');
    source.style.fontSize = '0.7rem';
    source.style.color = 'var(--text-muted)';
    source.style.marginTop = '4px';
    source.textContent = `File: ${f.evidence_file || '-'} ${f.line_hint ? ':' + f.line_hint : ''}`;
    
    msgBox.appendChild(msgText);
    msgBox.appendChild(source);

    // Actions
    const actBox = document.createElement('div');
    actBox.className = 'finding-actions';
    actBox.style.display = 'flex';
    actBox.style.flexDirection = 'column';
    actBox.style.gap = '4px';

    if (f.repro_command) {
      const btn = document.createElement('button');
      btn.className = 'btn-suggest';
      btn.textContent = 'Copy Repro';
      btn.addEventListener('click', () => copyToClipboard(f.repro_command));
      actBox.appendChild(btn);
    }

    if (f.evidence_file) {
      const btnPath = document.createElement('button');
      btnPath.className = 'btn-suggest';
      btnPath.style.background = 'var(--bg-tertiary)';
      btnPath.textContent = 'Copy Path';
      btnPath.addEventListener('click', () => copyToClipboard(f.evidence_file));
      actBox.appendChild(btnPath);
    }

    row.appendChild(metaCol);
    row.appendChild(cat);
    row.appendChild(modBox);
    row.appendChild(msgBox);
    row.appendChild(actBox);

    container.appendChild(row);
  });
}

function renderSuggestions() {
  const box = document.getElementById('suggestionBox');
  if (!box || !HEALTH_STATE.report) return;

  const top = HEALTH_STATE.report.top_blockers || [];
  box.innerHTML = ''; // Element-based rendering

  if (top.length === 0) {
    box.textContent = '✅ System health is optimal. Proceed to deployment.';
    box.style.color = 'var(--accent-green)';
    return;
  }

  top.forEach((b, idx) => {
    const item = document.createElement('div');
    item.className = 'suggestion-item';
    item.style.marginBottom = '12px';
    item.style.borderLeft = '2px solid var(--accent-yellow)';
    item.style.paddingLeft = '8px';

    const title = document.createElement('div');
    title.style.fontWeight = 'bold';
    title.style.color = '#eee';
    title.style.fontSize = '11px';
    title.textContent = `[GAP-${idx+1}] ${b.code}`;

    const fix = document.createElement('div');
    fix.style.margin = '4px 0';
    fix.style.fontSize = '12px';
    fix.style.color = 'var(--text-secondary)';
    fix.textContent = b.suggested_fix || 'No recommendation.';

    item.appendChild(title);
    item.appendChild(fix);
    box.appendChild(item);
  });
}

function showDisconnected() {
  const app = document.getElementById('app');
  app.setAttribute('data-state', 'FAILED');
  document.getElementById('statusText').textContent = 'PROJECT STATUS: OFFLINE (SCANNER DOWN)';
  document.getElementById('healthHeader').className = 'status-bar';
}

function copyToClipboard(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    console.log('Copied to clipboard');
  }).catch(err => {
    console.error('Copy failed:', err);
  });
}

function renderP0Blockers() {
  const box = document.getElementById('p0BlockerBox');
  if (!box || !HEALTH_STATE.report) return;

  const p0s = (HEALTH_STATE.report.findings || []).filter(f => f != null && f.severity === 'P0');
  box.innerHTML = '';

  if (p0s.length === 0) {
    box.textContent = '✅ No P0 Blockers';
    box.style.color = 'var(--accent-green)';
    return;
  }

  p0s.forEach(p => {
    const item = document.createElement('div');
    item.className = 'p0-item';
    item.style.color = 'var(--accent-red)';
    item.style.marginBottom = '5px';
    item.textContent = `⚠️ ${p.module}: ${p.code}`;
    box.appendChild(item);
  });
}
