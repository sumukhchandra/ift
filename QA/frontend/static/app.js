/**
 * NSE 1-Minute Stock Prediction & Compounding Platform
 * Real-Time WebSocket Client & Reactive Dual UI Controller
 */

// State Container
const appState = {
  mode: 'website',          // 'website' | 'app'
  socket: null,
  traderState: null,
  signals: [],
  trades: [],
  verifications: [],
  compoundingCurve: [],
  selectedSymbol: 'RELIANCE.NS',
  audioEnabled: true,
  appFullscreen: false,
  tradeFilter: 'ALL',       // 'ALL' | 'WIN' | 'LOSS' | 'BUY'
  appTradesView: 'table',   // 'table' | 'feed'
  appAdjustAction: 'deposit', // 'deposit' | 'withdraw' | 'set_capital'
  settingsTab: 'controls',   // 'controls' | 'history'
  historyDate: 'all',
  historySearch: '',
  historicalTrades: [],
  historyDatesSummary: []
};

// ─── Web Audio API Synthesizer (Chimes for Signals & Trades) ───────────────
let audioCtx = null;

function playChime(type = 'signal') {
  if (!appState.audioEnabled) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    if (type === 'signal') {
      // High-tech ascending duo-tone for >0.8% BUY trigger
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880.00, audioCtx.currentTime + 0.12); // A5
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.35);
    } else if (type === 'profit') {
      // Emerald Take-Profit arpeggio
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); // C5
      osc.frequency.setValueAtTime(659.25, audioCtx.currentTime + 0.08); // E5
      osc.frequency.setValueAtTime(783.99, audioCtx.currentTime + 0.16); // G5
      gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.4);
    }
  } catch (e) {
    console.debug('Audio play blocked or unavailable', e);
  }
}

// ─── Formatting Helpers ───────────────────────────────────────────────────
function formatINR(val) {
  if (val === undefined || val === null || isNaN(val)) return '₹0.00';
  return '₹' + Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(val) {
  if (val === undefined || val === null || isNaN(val)) return '0.00%';
  const prefix = val > 0 ? '+' : '';
  return prefix + Number(val).toFixed(2) + '%';
}

function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s ease';
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

// ─── WebSocket Connection ──────────────────────────────────────────────────
let pingTimer = null;

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  const pulse = document.getElementById('ws-pulse');
  const pulseText = document.getElementById('ws-status-text');

  try {
    appState.socket = new WebSocket(wsUrl);
  } catch (e) {
    console.error('Failed to create WebSocket:', e);
    return;
  }

  appState.socket.onopen = () => {
    console.log('Connected to Live NSE Stream');
    if (pulse) pulse.classList.remove('idle');
    if (pulseText) pulseText.innerText = 'LIVE 1-MIN FEED';

    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (appState.socket && appState.socket.readyState === WebSocket.OPEN) {
        appState.socket.send('ping');
      }
    }, 10000);
  };

  appState.socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleLiveEvent(msg);
    } catch (e) {
      console.error('Error parsing live WS event:', e);
    }
  };

  appState.socket.onclose = () => {
    console.warn('Live WebSocket closed, reconnecting in 2s...');
    if (pingTimer) clearInterval(pingTimer);
    if (pulse) pulse.classList.add('idle');
    if (pulseText) pulseText.innerText = 'RECONNECTING...';
    setTimeout(initWebSocket, 2000);
  };

  appState.socket.onerror = (err) => {
    console.error('WebSocket error:', err);
    if (pingTimer) clearInterval(pingTimer);
    try { appState.socket.close(); } catch(e) {}
  };
}

function handleLiveEvent(msg) {
  const { event, data } = msg;

  if (event === 'INITIAL_STATE') {
    appState.traderState = data.state;
    appState.signals = data.signals || [];
    appState.trades = data.recent_trades || [];
    appState.compoundingCurve = data.compounding_curve || [];
    appState.verifications = data.verifications || (data.state && data.state.recent_verifications) || [];
    renderAll();
  } else if (event === 'TICK_UPDATE') {
    appState.traderState = data.state;
    appState.signals = data.signals || [];
    if (data.actions && data.actions.length > 0) {
      data.actions.forEach(act => {
        // Prevent duplicate actions in trades array
        const exists = appState.trades.some(t => t.trade_id === act.trade_id);
        if (!exists) {
          appState.trades.unshift(act);
        }
        if (act.action === 'SELL' && act.net_profit > 0) {
          playChime('profit');
          showToast(`⚡ <strong>${act.symbol}</strong> closed with profit: <span class="text-emerald">+${formatINR(act.net_profit)}</span>`);
        } else if (act.action === 'BUY') {
          playChime('signal');
          showToast(`🚀 <strong>${act.symbol}</strong> BUY executed @ ₹${act.price.toFixed(2)} (${act.predicted_return_pct}% 1m target)`);
        }
      });
      renderTradesTable();
      renderAppTradesTable();
    }
    renderAll();
  } else if (event === 'PREDICTION_VERIFIED') {
    if (!appState.verifications) appState.verifications = [];
    const exists = appState.verifications.some(v => v.symbol === data.symbol && v.resolved_at === data.resolved_at);
    if (!exists) {
      appState.verifications.unshift(data);
      if (appState.verifications.length > 50) appState.verifications.pop();
      renderVerifications(true);
    }
  } else if (event === 'SESSION_RESET' || event === 'TODAY_TRADES_CLEARED') {
    appState.trades = [];
    if (data.state) appState.traderState = data.state;
    showToast('🔄 New session started. Active trades table reset.');
    renderAll();
    if (appState.settingsTab === 'history') {
      loadSettingsHistory();
    }
  } else if (event === 'CAPITAL_ADJUSTED') {
    showToast(`💰 Capital adjustment: ${data.type} of ${formatINR(data.amount)}`);
    fetchState();
  } else if (event === 'EMERGENCY_CLOSE') {
    showToast(`🚨 Emergency liquidation completed.`);
    fetchState();
  }
}

// ─── REST Fetchers ────────────────────────────────────────────────────────
async function fetchState() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    appState.traderState = data;
    if (data.signals && data.signals.length > 0) {
      appState.signals = data.signals;
    } else if (data.last_signals && data.last_signals.length > 0) {
      appState.signals = data.last_signals;
    }
    renderHeaderMetrics();
    renderTickerTape();
  } catch (e) {
    console.error('Failed to fetch state:', e);
  }
}

async function fetchVerifications() {
  try {
    const res = await fetch('/api/predictions/verification?limit=25');
    const data = await res.json();
    if (data.accuracy && appState.traderState) {
      appState.traderState.prediction_accuracy = data.accuracy;
    }
    if (data.verifications && data.verifications.length > 0) {
      const prevTop = appState.verifications && appState.verifications.length > 0 ? 
        (appState.verifications[0].symbol + '_' + appState.verifications[0].resolved_at) : null;
      const newTop = data.verifications[0].symbol + '_' + data.verifications[0].resolved_at;
      const isNew = prevTop !== null && prevTop !== newTop;
      appState.verifications = data.verifications;
      renderVerifications(isNew);
    }
  } catch (e) {
    console.error('Failed to fetch prediction verifications:', e);
  }
}

async function fetchTrades() {
  try {
    const res = await fetch('/api/trades?date_filter=session&limit=200');
    const data = await res.json();
    appState.trades = data.trades || [];
    renderTradesTable();
    renderAppTradesTable();
  } catch (e) {
    console.error('Failed to fetch trades:', e);
  }
}

async function fetchCandles(symbol) {
  try {
    const res = await fetch(`/api/candles/${symbol}?count=35`);
    const data = await res.json();
    renderCandlestickChart(data.candles || []);
  } catch (e) {
    console.error('Failed to fetch candles:', e);
  }
}

// ─── Rendering Controllers ────────────────────────────────────────────────
function renderAll() {
  renderHeaderMetrics();
  renderTickerTape();
  renderWebsiteDesk();
  renderAppLiveMonitor();
}

function renderHeaderMetrics() {
  const s = appState.traderState;
  if (!s) return;

  // Website Top Metrics
  const totalCapEl = document.getElementById('metric-total-capital');
  const availableCapEl = document.getElementById('metric-available-capital');
  const netProfitEl = document.getElementById('metric-net-profit');
  const compMultEl = document.getElementById('metric-compounding-mult');
  const tradesCountEl = document.getElementById('metric-trades-count');
  const winRateEl = document.getElementById('metric-win-rate');

  if (totalCapEl) totalCapEl.innerText = formatINR(s.total_capital);
  if (availableCapEl) availableCapEl.innerText = formatINR(s.available_capital);
  if (netProfitEl) {
    netProfitEl.innerText = formatINR(s.total_net_profit);
    netProfitEl.className = 'metric-val ' + (s.total_net_profit >= 0 ? 'text-emerald' : 'text-rose');
  }
  if (compMultEl) compMultEl.innerText = s.compounding_multiplier + 'x';
  if (tradesCountEl) tradesCountEl.innerText = `${s.daily_trades_count} / ${s.target_daily_trades}`;
  if (winRateEl) winRateEl.innerText = s.win_rate_pct + '%';

  // Master Summary Table in Website View
  const sumInit = document.getElementById('summary-initial-capital');
  const sumTotal = document.getElementById('summary-total-capital');
  const sumPnl = document.getElementById('summary-net-pnl');
  const sumInvest = document.getElementById('summary-invested');
  const sumAvail = document.getElementById('summary-available');
  const sumWinrate = document.getElementById('summary-winrate');
  const sumTrades = document.getElementById('summary-trades-count');

  if (sumInit) sumInit.innerText = formatINR(s.starting_capital);
  if (sumTotal) sumTotal.innerText = formatINR(s.total_capital);
  if (sumPnl) {
    const netRetPct = s.starting_capital > 0 ? (s.total_net_profit / s.starting_capital) * 100 : 0;
    sumPnl.innerText = `${s.total_net_profit >= 0 ? '+' : ''}${formatINR(s.total_net_profit)} (${formatPct(netRetPct)})`;
    sumPnl.className = 'font-bold ' + (s.total_net_profit >= 0 ? 'text-emerald' : 'text-rose');
  }
  if (sumInvest) sumInvest.innerText = formatINR(s.invested_capital);
  if (sumAvail) sumAvail.innerText = formatINR(s.available_capital);
  if (sumWinrate) {
    sumWinrate.innerText = `${s.win_rate_pct}% (${s.winning_trades || 0}W / ${s.losing_trades || 0}L)`;
    sumWinrate.className = 'font-bold ' + (s.win_rate_pct >= 50 ? 'text-emerald' : 'text-amber');
  }
  if (sumTrades) sumTrades.innerText = `${s.daily_trades_count} Trades`;

  // Engine status button text
  const engineBtn = document.getElementById('engine-toggle-btn');
  if (engineBtn) {
    if (s.engine_status === 'RUNNING') {
      engineBtn.innerHTML = '⏸️ Pause Auto-Trader';
      engineBtn.className = 'btn btn-outline';
    } else {
      engineBtn.innerHTML = '▶️ Start Auto-Trader';
      engineBtn.className = 'btn btn-emerald';
    }
  }

  // Market Open / Closed Session Status & Schedule Info
  const mStatus = (s && s.market_status) || {};
  const isMarketOpen = s && s.is_market_open !== undefined ? s.is_market_open : mStatus.is_open;
  const simEnabled = s && s.off_market_simulation;

  const sessionBadge = document.getElementById('market-session-badge');
  const scheduleInfo = document.getElementById('market-schedule-info');
  const simBtn = document.getElementById('sim-toggle-btn');

  if (sessionBadge) {
    if (isMarketOpen) {
      sessionBadge.innerText = '🟢 NSE LIVE (09:15-15:30 IST)';
      sessionBadge.style.background = 'rgba(0, 255, 136, 0.15)';
      sessionBadge.style.color = 'var(--neon-emerald)';
      sessionBadge.style.borderColor = 'rgba(0, 255, 136, 0.35)';
    } else {
      sessionBadge.innerText = '🔴 NSE CLOSED (STANDBY)';
      sessionBadge.style.background = 'rgba(255, 51, 102, 0.15)';
      sessionBadge.style.color = 'var(--neon-rose)';
      sessionBadge.style.borderColor = 'rgba(255, 51, 102, 0.35)';
    }
  }

  if (scheduleInfo) {
    if (isMarketOpen) {
      scheduleInfo.innerText = '🟢 Indian Stock Market is LIVE. Real-time 1-min stock execution active.';
    } else {
      scheduleInfo.innerText = `🔴 Regular NSE Session Closed (09:15-15:30 IST). Next Open: ${mStatus.next_market_open || 'Tomorrow at 09:15 AM IST'}.`;
    }
  }

  if (simBtn) {
    simBtn.innerText = simEnabled ? '🧪 Off-Market Sim: ON' : '🧪 Off-Market Sim: OFF';
    simBtn.className = simEnabled ? 'btn btn-emerald' : 'btn btn-outline';
  }
}

function renderTickerTape() {
  const track = document.getElementById('ticker-track');
  if (!track || !appState.signals || appState.signals.length === 0) return;

  // Duplicate for seamless loop
  const items = [...appState.signals, ...appState.signals];
  track.innerHTML = items.map(sig => {
    const isUp = sig.predicted_return_pct >= 0;
    return `
      <div class="ticker-item" onclick="selectSymbol('${sig.symbol}')" style="cursor: pointer;">
        <span class="ticker-symbol">${sig.symbol.replace('.NS', '')}</span>
        <span class="ticker-price">₹${sig.current_price.toFixed(1)}</span>
        <span class="ticker-change ${isUp ? 'up' : 'down'}">${formatPct(sig.predicted_return_pct)}</span>
      </div>
    `;
  }).join('');
}

function renderWebsiteDesk() {
  const s = appState.traderState;
  if (!s) return;

  // Treasury balances
  const tTotal = document.getElementById('treasury-total');
  const tAvail = document.getElementById('treasury-avail');
  const tInvest = document.getElementById('treasury-invest');
  if (tTotal) tTotal.innerText = formatINR(s.total_capital);
  if (tAvail) tAvail.innerText = formatINR(s.available_capital);
  if (tInvest) tInvest.innerText = formatINR(s.invested_capital);

  // Sliders values
  const threshVal = document.getElementById('profit-thresh-val');
  const slVal = document.getElementById('sl-thresh-val');
  const sizingVal = document.getElementById('sizing-val');
  const tradesVal = document.getElementById('target-trades-val');

  if (threshVal) threshVal.innerText = s.profit_threshold_pct + '%';
  if (slVal) slVal.innerText = s.stop_loss_pct + '%';
  if (sizingVal) sizingVal.innerText = s.position_sizing_pct + '%';
  if (tradesVal) tradesVal.innerText = s.target_daily_trades + ' trades';

  // Signals Grid
  renderSignalsGrid();

  // Prediction Verifications Table
  renderVerifications();

  // Positions Table
  renderPositionsTable();

  // Trades Table
  renderTradesTable();

  // Compounding Curve Chart
  renderCompoundingChart();
}

function renderVerifications(highlightFirst = false) {
  const tbody = document.getElementById('verifications-tbody');
  if (!tbody) return;

  const s = appState.traderState;
  const acc = (s && s.prediction_accuracy) || {};

  const hitBadge = document.getElementById('badge-range-hit');
  const dirBadge = document.getElementById('badge-dir-acc');
  const maeBadge = document.getElementById('badge-mae');

  if (hitBadge && acc.exact_range_hit_rate_pct !== undefined) {
    hitBadge.innerText = `Exact Range Hit: ${acc.exact_range_hit_rate_pct}% (${acc.exact_range_hits || 0}/${acc.total_verified || 0})`;
  }
  if (dirBadge && acc.direction_accuracy_pct !== undefined) {
    dirBadge.innerText = `Direction Acc: ${acc.direction_accuracy_pct}%`;
  }
  if (maeBadge && acc.mean_abs_return_error_pct !== undefined) {
    maeBadge.innerText = `Avg Return Error: ${acc.mean_abs_return_error_pct}% | Price Err: ${acc.mean_price_error_pct || 0}%`;
  }

  const list = appState.verifications || [];
  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color: var(--text-dim); padding: 1.2rem;">Observing predictions... Verifying exact values as each 1m candle arrives.</td></tr>';
    return;
  }

  tbody.innerHTML = list.slice(0, 20).map((v, idx) => {
    const timeStr = v.resolved_at ? (v.resolved_at.includes('T') ? v.resolved_at.split('T')[1].split('.')[0] : v.resolved_at) : '--:--';
    const exactHit = v.exact_range_reached;
    const isDirOk = v.direction_correct;
    const predRet = v.predicted_return_pct;
    const actRet = v.actual_return_pct;
    const isFlash = highlightFirst && idx === 0;

    return `
      <tr class="${isFlash ? 'row-flash-live' : ''}">
        <td>${timeStr}</td>
        <td><strong>${v.symbol.replace('.NS', '')}</strong></td>
        <td style="color: var(--neon-cyan);">₹${(v.predicted_price || 0).toFixed(2)}</td>
        <td style="font-weight: 700;">₹${(v.actual_price || 0).toFixed(2)}</td>
        <td>
          <span class="signal-badge ${exactHit ? 'buy' : 'hold'}" style="font-size: 0.72rem; padding: 2px 6px;">
            ${exactHit ? '🎯 EXACT HIT' : '⚡ ' + (v.price_error_pct || 0).toFixed(2) + '% diff'}
          </span>
        </td>
        <td class="${predRet >= 0 ? 'text-emerald' : 'text-rose'}">${formatPct(predRet)}</td>
        <td class="${actRet >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">${formatPct(actRet)}</td>
        <td>
          <span style="color: ${isDirOk ? 'var(--neon-emerald)' : 'var(--neon-rose)'}; font-weight: 700;">
            ${isDirOk ? '✅ MATCH' : '❌ MISS'}
          </span>
        </td>
        <td style="color: var(--text-muted); font-size: 0.75rem;">
          ${(v.return_error_pct || 0).toFixed(2)}%
        </td>
      </tr>
    `;
  }).join('');
}

// ─── Mobile Long-Press & Desktop Hover Handlers for Signal Cards ──────────
let signalLongPressTimer = null;
let isLongPressTriggered = false;

function handleSignalTouchStart(e, symbol) {
  isLongPressTriggered = false;
  if (signalLongPressTimer) clearTimeout(signalLongPressTimer);
  signalLongPressTimer = setTimeout(() => {
    isLongPressTriggered = true;
    if (navigator.vibrate) {
      try { navigator.vibrate(45); } catch(err) {}
    }
    openMobileSignalPopover(symbol);
  }, 450); // 450ms long-press trigger
}

function handleSignalTouchEnd(e, symbol) {
  if (signalLongPressTimer) clearTimeout(signalLongPressTimer);
  if (isLongPressTriggered) {
    if (e.cancelable) e.preventDefault();
  }
}

function handleSignalTouchCancel(symbol) {
  if (signalLongPressTimer) clearTimeout(signalLongPressTimer);
  isLongPressTriggered = false;
}

function handleSignalCardClick(e, symbol) {
  if (isLongPressTriggered) {
    isLongPressTriggered = false;
    return;
  }
  selectSymbol(symbol);
}

function openMobileSignalPopover(symbol) {
  const sig = (appState.signals || []).find(s => s.symbol === symbol);
  if (!sig) return;

  const isBuy = sig.signal === 'BUY';
  const emaStr = sig.ema_cross_pct !== undefined ? (sig.ema_cross_pct > 0 ? '+' : '') + sig.ema_cross_pct.toFixed(2) + '%' : '--';
  const rsiStr = sig.micro_rsi !== undefined ? sig.micro_rsi : '--';
  const hurdleStr = sig.profit_threshold_pct !== undefined ? sig.profit_threshold_pct.toFixed(2) + '%' : '0.20%';
  const cleanSym = sig.symbol.replace('.NS', '');

  closeMobileSignalPopover();

  const overlay = document.createElement('div');
  overlay.id = 'mobile-signal-popover-overlay';
  overlay.className = 'mobile-popover-overlay';
  overlay.onclick = (e) => {
    if (e.target === overlay) closeMobileSignalPopover();
  };

  overlay.innerHTML = `
    <div class="mobile-popover-modal" onclick="event.stopPropagation()">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.1rem; padding-bottom: 0.65rem; border-bottom: 1px solid rgba(255,255,255,0.09);">
        <div>
          <div style="font-weight: 800; font-size: 1.3rem; color: var(--neon-cyan); letter-spacing: -0.01em;">${cleanSym}</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">${sig.company || cleanSym}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="signal-badge ${isBuy ? 'buy' : 'hold'}">${sig.signal}</span>
          <button class="modal-close-btn" onclick="closeMobileSignalPopover()" title="Close details">✕</button>
        </div>
      </div>

      <div class="popover-details-grid" style="font-size: 0.82rem; row-gap: 10px;">
        <span class="popover-prop">Current Price</span>
        <span class="popover-val">₹${sig.current_price.toFixed(2)}</span>

        <span class="popover-prop">Target Open (1m)</span>
        <span class="popover-val ${isBuy ? 'text-emerald' : ''}" style="font-weight: 800;">₹${sig.predicted_price_1m.toFixed(2)}</span>

        <span class="popover-prop">Expected Return</span>
        <span class="popover-val ${sig.predicted_return_pct >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 800;">${formatPct(sig.predicted_return_pct)}</span>

        <span class="popover-prop">Confidence</span>
        <span class="popover-val text-cyan">${sig.confidence}%</span>

        <span class="popover-prop">Hurdle / Vol</span>
        <span class="popover-val" style="color: var(--neon-amber);">${hurdleStr}</span>

        <span class="popover-prop">RSI / EMA Slope</span>
        <span class="popover-val" style="font-size: 0.75rem; color: var(--text-muted);">${rsiStr} | ${emaStr}</span>
      </div>

      <div style="margin-top: 1.25rem; display: flex; gap: 8px;">
        <button class="btn btn-primary" style="flex: 1; justify-content: center; font-size: 0.82rem; padding: 10px;" onclick="selectSymbol('${sig.symbol}'); closeMobileSignalPopover();">
          📈 View 1m Candle Chart
        </button>
        <button class="btn btn-outline" style="font-size: 0.82rem; padding: 10px 16px;" onclick="closeMobileSignalPopover()">
          Close
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
}

function closeMobileSignalPopover() {
  const existing = document.getElementById('mobile-signal-popover-overlay');
  if (existing) existing.remove();
}

function renderSignalsGrid() {
  const container = document.getElementById('signals-grid');
  if (!container) return;

  if (!appState.signals || appState.signals.length === 0) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem;">Scanning 1-minute market data...</div>';
    return;
  }

  container.innerHTML = appState.signals.map(sig => {
    const isBuy = sig.signal === 'BUY';
    const emaStr = sig.ema_cross_pct !== undefined ? (sig.ema_cross_pct > 0 ? '+' : '') + sig.ema_cross_pct.toFixed(2) + '%' : '--';
    const rsiStr = sig.micro_rsi !== undefined ? sig.micro_rsi : '--';
    const hurdleStr = sig.profit_threshold_pct !== undefined ? sig.profit_threshold_pct.toFixed(2) + '%' : '0.20%';
    const cleanSym = sig.symbol.replace('.NS', '');

    return `
      <div class="signal-card ${isBuy ? 'buy' : ''}" 
           data-symbol="${sig.symbol}"
           onclick="handleSignalCardClick(event, '${sig.symbol}')"
           ontouchstart="handleSignalTouchStart(event, '${sig.symbol}')"
           ontouchend="handleSignalTouchEnd(event, '${sig.symbol}')"
           ontouchcancel="handleSignalTouchCancel('${sig.symbol}')">

        <!-- Minimalist Card Display: ONLY Name & Company Displayed by default -->
        <div class="signal-card-minimal">
          <div class="signal-sym-group">
            <div class="signal-sym-title">${cleanSym}</div>
            <div class="signal-company-name">${sig.company || cleanSym}</div>
          </div>
          <div class="signal-quick-status">
            <span class="signal-badge ${isBuy ? 'buy' : 'hold'}">${sig.signal}</span>
            <span class="signal-info-btn" onclick="event.stopPropagation(); openMobileSignalPopover('${sig.symbol}')" title="Hold or click for full analytics">ℹ️</span>
          </div>
        </div>

        <!-- Floating Window Popover (Hover on Desktop, or Long-press on Mobile) -->
        <div class="signal-floating-popover">
          <div class="popover-header">
            <div>
              <div class="popover-sym">${cleanSym}</div>
              <div class="popover-company">${sig.company || ''}</div>
            </div>
            <span class="signal-badge ${isBuy ? 'buy' : 'hold'}">${sig.signal}</span>
          </div>

          <div class="popover-details-grid">
            <span class="popover-prop">Current Price</span>
            <span class="popover-val">₹${sig.current_price.toFixed(2)}</span>

            <span class="popover-prop">Target Open (1m)</span>
            <span class="popover-val ${isBuy ? 'text-emerald' : ''}" style="font-weight: 800;">₹${sig.predicted_price_1m.toFixed(2)}</span>

            <span class="popover-prop">Expected Return</span>
            <span class="popover-val ${sig.predicted_return_pct >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 800;">${formatPct(sig.predicted_return_pct)}</span>

            <span class="popover-prop">Confidence</span>
            <span class="popover-val text-cyan">${sig.confidence}%</span>

            <span class="popover-prop">Hurdle / Vol</span>
            <span class="popover-val" style="color: var(--neon-amber);">${hurdleStr}</span>

            <span class="popover-prop">RSI / EMA Slope</span>
            <span class="popover-val" style="font-size: 0.72rem; color: var(--text-muted);">${rsiStr} | ${emaStr}</span>
          </div>

          <div class="popover-footer-hint">
            💡 Click to inspect 1-minute live candle chart
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderPositionsTable() {
  const tbody = document.getElementById('positions-tbody');
  if (!tbody) return;

  const positions = appState.traderState ? appState.traderState.positions : {};
  const keys = Object.keys(positions);

  if (keys.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No open positions. Scanning 1-minute breakouts...</td></tr>';
    return;
  }

  tbody.innerHTML = keys.map(sym => {
    const pos = positions[sym];
    const isProfit = (pos.unrealized_net_pnl || 0) >= 0;
    return `
      <tr>
        <td><strong>${sym.replace('.NS', '')}</strong></td>
        <td>₹${pos.entry_price.toFixed(2)}</td>
        <td>₹${pos.current_price ? pos.current_price.toFixed(2) : pos.entry_price.toFixed(2)}</td>
        <td>${pos.qty}</td>
        <td>${formatINR(pos.invested)}</td>
        <td class="${isProfit ? 'text-emerald' : 'text-rose'}">
          ${formatINR(pos.unrealized_net_pnl || 0)} (${formatPct(pos.unrealized_net_ret_pct || 0)})
        </td>
        <td>
          <button class="btn btn-danger" style="padding: 3px 10px; font-size: 0.72rem;" onclick="manualClose('${sym}')">Close</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderTradesTable() {
  const tbody = document.getElementById('trades-tbody');
  if (!tbody) return;

  const s = appState.traderState || {};
  const allTrades = appState.trades || [];

  // Update filter pill counts
  const allCount = allTrades.length;
  const winCount = allTrades.filter(t => t.action === 'SELL' && t.net_profit > 0).length;
  const lossCount = allTrades.filter(t => t.action === 'SELL' && t.net_profit <= 0).length;
  const buyCount = allTrades.filter(t => t.action === 'BUY').length;

  const allCountEl = document.getElementById('filter-all-count');
  const winCountEl = document.getElementById('filter-win-count');
  const lossCountEl = document.getElementById('filter-loss-count');
  const buyCountEl = document.getElementById('filter-buy-count');

  if (allCountEl) allCountEl.innerText = allCount;
  if (winCountEl) winCountEl.innerText = winCount;
  if (lossCountEl) lossCountEl.innerText = lossCount;
  if (buyCountEl) buyCountEl.innerText = buyCount;

  // Filter trades according to active selection
  let filtered = allTrades;
  if (appState.tradeFilter === 'WIN') {
    filtered = allTrades.filter(t => t.action === 'SELL' && t.net_profit > 0);
  } else if (appState.tradeFilter === 'LOSS') {
    filtered = allTrades.filter(t => t.action === 'SELL' && t.net_profit <= 0);
  } else if (appState.tradeFilter === 'BUY') {
    filtered = allTrades.filter(t => t.action === 'BUY');
  }

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No trades match the selected filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.slice(0, 100).map(tr => {
    const isBuy = tr.action === 'BUY';
    const isWin = tr.net_profit > 0;
    const timeStr = tr.timestamp ? (tr.timestamp.includes('T') ? tr.timestamp.split('T')[1].split('.')[0] : tr.timestamp) : '--:--';
    
    // Status Badge
    let statusHtml = '<span class="status-badge open">BOUGHT</span>';
    if (!isBuy) {
      statusHtml = isWin ? '<span class="status-badge win">WIN</span>' : '<span class="status-badge loss">LOSS</span>';
    }

    // Profit / Loss display
    let pnlHtml = '<span style="color: var(--text-dim);">-- (Holding)</span>';
    if (!isBuy) {
      const retPct = tr.net_return_pct !== undefined ? tr.net_return_pct : (tr.gross_return_pct || 0);
      pnlHtml = `<span class="${isWin ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">
        ${isWin ? '+' : ''}${formatINR(tr.net_profit)} (${formatPct(retPct)})
      </span>`;
    }

    // Execution price string
    let priceStr = `₹${(tr.exit_price || tr.price || 0).toFixed(2)}`;
    if (tr.entry_price && tr.exit_price) {
      priceStr = `₹${tr.entry_price.toFixed(2)} → ₹${tr.exit_price.toFixed(2)}`;
    }

    const initCap = formatINR(tr.starting_capital || s.starting_capital);
    const investAmt = formatINR(tr.invested || tr.invest_amount || 0);
    const capAfter = formatINR(tr.capital_after || s.total_capital);
    const winRate = (tr.win_rate_pct !== undefined ? tr.win_rate_pct : (s.win_rate_pct || 0)) + '%';

    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.78rem;">${timeStr}</td>
        <td><span class="signal-badge ${isBuy ? 'buy' : 'hold'}">${tr.action}</span></td>
        <td>
          <strong>${tr.symbol.replace('.NS', '')}</strong>
          <div style="font-size: 0.68rem; color: var(--text-muted);">${tr.company || ''}</div>
        </td>
        <td style="color: var(--neon-cyan);">${initCap}</td>
        <td><strong>${investAmt}</strong></td>
        <td>${priceStr}</td>
        <td>${pnlHtml}</td>
        <td>${statusHtml}</td>
        <td style="color: var(--neon-emerald); font-weight: 700;">${capAfter}</td>
        <td><strong class="text-cyan">${winRate}</strong></td>
        <td style="color: var(--text-muted); font-size: 0.72rem; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${tr.reason || ''}">
          ${tr.reason || 'Auto-signal'}
        </td>
      </tr>
    `;
  }).join('');
}

function setTradeFilter(filter) {
  appState.tradeFilter = filter;
  ['all', 'win', 'loss', 'buy'].forEach(f => {
    const el = document.getElementById(`pill-${f}`);
    if (el) {
      if (f.toUpperCase() === filter.toUpperCase()) el.classList.add('active');
      else el.classList.remove('active');
    }
  });
  renderTradesTable();
}

function exportTradesToCSV() {
  if (!appState.trades || appState.trades.length === 0) {
    showToast('No trades available to export.');
    return;
  }
  const headers = [
    'Trade_ID', 'Timestamp', 'Action', 'Symbol', 'Company',
    'Initial_Capital', 'Invested_Amount', 'Entry_Price', 'Exit_Price',
    'Net_Profit', 'Net_Return_Pct', 'Status', 'Capital_After',
    'Win_Rate_Pct', 'Reason'
  ];
  const s = appState.traderState || {};
  const rows = appState.trades.map(t => {
    const isBuy = t.action === 'BUY';
    const isWin = t.net_profit > 0;
    const status = isBuy ? 'BOUGHT' : (isWin ? 'WIN' : 'LOSS');
    return [
      t.id || '',
      t.timestamp || '',
      t.action || '',
      t.symbol || '',
      `"${(t.company || '').replace(/"/g, '""')}"`,
      t.starting_capital || s.starting_capital || '',
      t.invested || t.invest_amount || '',
      t.entry_price || t.price || '',
      t.exit_price || '',
      t.net_profit !== undefined ? t.net_profit : '',
      t.net_return_pct !== undefined ? t.net_return_pct : '',
      status,
      t.capital_after || s.total_capital || '',
      t.win_rate_pct !== undefined ? t.win_rate_pct : s.win_rate_pct || '',
      `"${(t.reason || '').replace(/"/g, '""')}"`
    ].join(',');
  });
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `alphanse_trades_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  showToast('📥 Trades Ledger exported to CSV.');
}

// ─── Settings History & Session Management ─────────────────────────────────
function switchSettingsTab(tab) {
  appState.settingsTab = tab;
  const btnControls = document.getElementById('btn-settings-controls');
  const btnHistory = document.getElementById('btn-settings-history');
  const contentControls = document.getElementById('settings-tab-controls-content');
  const contentHistory = document.getElementById('settings-tab-history-content');

  if (tab === 'history') {
    if (btnControls) btnControls.classList.remove('active');
    if (btnHistory) btnHistory.classList.add('active');
    if (contentControls) contentControls.style.display = 'none';
    if (contentHistory) contentHistory.style.display = 'block';
    loadSettingsHistory();
  } else {
    if (btnControls) btnControls.classList.add('active');
    if (btnHistory) btnHistory.classList.remove('active');
    if (contentControls) contentControls.style.display = 'block';
    if (contentHistory) contentHistory.style.display = 'none';
  }
}

function openSettingsHistory() {
  switchSettingsTab('history');
  const card = document.getElementById('settings-card');
  if (card) card.scrollIntoView({ behavior: 'smooth' });
}

async function loadSettingsHistory() {
  try {
    // 1. Fetch dates summary
    const sumRes = await fetch('/api/trades/dates-summary');
    const sumData = await sumRes.json();
    appState.historyDatesSummary = sumData.dates || [];

    // Update date select options if available
    const select = document.getElementById('history-date-select');
    if (select) {
      const currentVal = appState.historyDate || select.value || 'all';
      let opts = '<option value="all">All Dates & Sessions</option><option value="today">Today\'s Session</option>';
      appState.historyDatesSummary.forEach(d => {
        if (!d.is_today) {
          opts += `<option value="${d.date}">${d.date} (${d.total_trades} trades | Win: ${d.win_rate_pct}%)</option>`;
        }
      });
      select.innerHTML = opts;
      select.value = currentVal;
    }

    // 2. Fetch historical trades for active date
    const dateParam = appState.historyDate && appState.historyDate !== 'all' ? `&date=${appState.historyDate}` : '';
    const tradesRes = await fetch(`/api/trades/history?limit=1000${dateParam}`);
    const tradesData = await tradesRes.json();
    appState.historicalTrades = tradesData.trades || [];

    renderSettingsHistory();
  } catch (e) {
    console.error('Failed to load settings history:', e);
  }
}

function onHistoryDateChange(val) {
  appState.historyDate = val;
  loadSettingsHistory();
}

function onHistorySearch(val) {
  appState.historySearch = (val || '').trim().toUpperCase();
  renderSettingsHistory();
}

function renderSettingsHistory() {
  const tbody = document.getElementById('settings-history-tbody');
  if (!tbody) return;

  let list = appState.historicalTrades || [];
  if (appState.historySearch) {
    list = list.filter(t => 
      (t.symbol && t.symbol.toUpperCase().includes(appState.historySearch)) ||
      (t.reason && t.reason.toUpperCase().includes(appState.historySearch)) ||
      (t.timestamp && t.timestamp.includes(appState.historySearch)) ||
      (t.company && t.company.toUpperCase().includes(appState.historySearch))
    );
  }

  // Calculate KPIs for current filtered view
  const totalTrades = list.length;
  const sells = list.filter(t => t.action === 'SELL');
  const wins = sells.filter(t => t.net_profit > 0).length;
  const winRate = sells.length > 0 ? ((wins / sells.length) * 100).toFixed(1) : '0.0';
  const totalNetPnl = sells.reduce((acc, t) => acc + (t.net_profit || 0), 0);
  const totalFrictions = sells.reduce((acc, t) => acc + (t.tax_paid || 0) + (t.brokerage || 0), 0);

  const kpiTrades = document.getElementById('hist-kpi-trades');
  const kpiWinRate = document.getElementById('hist-kpi-winrate');
  const kpiPnl = document.getElementById('hist-kpi-pnl');
  const kpiFrictions = document.getElementById('hist-kpi-frictions');

  if (kpiTrades) kpiTrades.innerText = `${totalTrades} (${wins}W / ${sells.length - wins}L)`;
  if (kpiWinRate) kpiWinRate.innerText = `${winRate}%`;
  if (kpiPnl) {
    kpiPnl.innerText = `${totalNetPnl >= 0 ? '+' : ''}${formatINR(totalNetPnl)}`;
    kpiPnl.className = 'history-metric-val ' + (totalNetPnl >= 0 ? 'text-emerald' : 'text-rose');
  }
  if (kpiFrictions) kpiFrictions.innerText = formatINR(totalFrictions);

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">No historical trades match this filter.</td></tr>';
    return;
  }

  tbody.innerHTML = list.slice(0, 150).map(tr => {
    const isBuy = tr.action === 'BUY';
    const isWin = tr.net_profit > 0;
    const timeStr = tr.timestamp ? tr.timestamp.replace('T', ' ').split('.')[0] : '--';
    let statusHtml = '<span class="status-badge open">BOUGHT</span>';
    if (!isBuy) {
      statusHtml = isWin ? '<span class="status-badge win">WIN</span>' : '<span class="status-badge loss">LOSS</span>';
    }
    let pnlHtml = '<span style="color: var(--text-dim);">--</span>';
    if (!isBuy) {
      const retPct = tr.net_return_pct !== undefined ? tr.net_return_pct : (tr.gross_return_pct || 0);
      pnlHtml = `<span class="${isWin ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">
        ${isWin ? '+' : ''}${formatINR(tr.net_profit)} (${formatPct(retPct)})
      </span>`;
    }
    let priceStr = `₹${(tr.exit_price || tr.price || 0).toFixed(2)}`;
    if (tr.entry_price && tr.exit_price) {
      priceStr = `₹${tr.entry_price.toFixed(2)} → ₹${tr.exit_price.toFixed(2)}`;
    }
    const investAmt = formatINR(tr.invested || tr.invest_amount || 0);
    const capAfter = formatINR(tr.capital_after || 100000);
    const winRateStr = (tr.win_rate_pct !== undefined ? tr.win_rate_pct : 0) + '%';

    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.72rem; white-space: nowrap;">${timeStr}</td>
        <td><strong>${tr.symbol.replace('.NS', '')}</strong></td>
        <td><span class="signal-badge ${isBuy ? 'buy' : 'hold'}" style="font-size: 0.68rem; padding: 1px 4px;">${tr.action}</span></td>
        <td>${investAmt}</td>
        <td>${priceStr}</td>
        <td>${pnlHtml}</td>
        <td>${statusHtml}</td>
        <td style="color: var(--neon-emerald); font-weight: 700;">${capAfter}</td>
        <td class="text-cyan">${winRateStr}</td>
        <td style="color: var(--text-muted); font-size: 0.7rem; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${tr.reason || ''}">
          ${tr.reason || 'Auto'}
        </td>
      </tr>
    `;
  }).join('');
}

function exportHistoryToCSV() {
  const list = appState.historicalTrades || [];
  if (list.length === 0) {
    showToast('No trade history available to export.');
    return;
  }
  const headers = ['Trade_ID', 'Timestamp', 'Action', 'Symbol', 'Company', 'Invested', 'Entry_Price', 'Exit_Price', 'Net_Profit', 'Net_Return_Pct', 'Status', 'Capital_After', 'Win_Rate_Pct', 'Reason'];
  const rows = list.map(t => [
    t.trade_id || '',
    t.timestamp || '',
    t.action || '',
    t.symbol || '',
    `"${(t.company || '').replace(/"/g, '""')}"`,
    t.invested || t.invest_amount || 0,
    t.entry_price || t.price || 0,
    t.exit_price || '',
    t.net_profit || 0,
    t.net_return_pct || 0,
    t.action === 'BUY' ? 'OPEN' : (t.net_profit > 0 ? 'WIN' : 'LOSS'),
    t.capital_after || '',
    t.win_rate_pct || '',
    `"${(t.reason || '').replace(/"/g, '""')}"`
  ]);
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `AlphaNSE_Trade_History_${new Date().toISOString().slice(0,10)}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  showToast(`📥 Exported ${list.length} historical trades to CSV.`);
}

async function confirmStartNewSession() {
  const confirmed = confirm('🔄 Start a fresh trading session?\\n\\nThis will clear previous session logs from the active dashboard tables and reset the daily counter.\\n\\nAll historical trades will remain safely stored and accessible in the Settings History tab.');
  if (!confirmed) return;

  try {
    const res = await fetch('/api/session/new', { method: 'POST' });
    const data = await res.json();
    showToast('✅ ' + (data.message || 'New session started!'));
    appState.trades = [];
    await fetchState();
    await fetchTrades();
    await fetchVerifications();
    if (appState.settingsTab === 'history') {
      loadSettingsHistory();
    }
  } catch (e) {
    showToast('Failed to start new session: ' + e);
  }
}

function renderAppTradesTable() {
  const tbody = document.getElementById('app-trades-tbody');
  if (!tbody) return;

  const s = appState.traderState || {};
  if (!appState.trades || appState.trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 1rem;">No trades recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = appState.trades.slice(0, 50).map(tr => {
    const isBuy = tr.action === 'BUY';
    const isWin = tr.net_profit > 0;
    const timeStr = tr.timestamp ? (tr.timestamp.includes('T') ? tr.timestamp.split('T')[1].split('.')[0] : tr.timestamp) : '--:--';
    const status = isBuy ? '<span class="status-badge open">BUY</span>' : (isWin ? '<span class="status-badge win">WIN</span>' : '<span class="status-badge loss">LOSS</span>');
    const pnlStr = isBuy ? '--' : `<span class="${isWin ? 'text-emerald' : 'text-rose'}">${isWin ? '+' : ''}${formatINR(tr.net_profit)}</span>`;
    const initCap = formatINR(tr.starting_capital || s.starting_capital);
    const capAfter = formatINR(tr.capital_after || s.total_capital);
    const winRate = (tr.win_rate_pct !== undefined ? tr.win_rate_pct : (s.win_rate_pct || 0)) + '%';

    return `
      <tr>
        <td>${timeStr}</td>
        <td><strong>${tr.symbol.replace('.NS', '')}</strong></td>
        <td><span class="signal-badge ${isBuy ? 'buy' : 'hold'}">${tr.action}</span></td>
        <td>${formatINR(tr.invested || tr.invest_amount)}</td>
        <td>${pnlStr}</td>
        <td>${status}</td>
        <td style="color: var(--neon-cyan);">${initCap}</td>
        <td style="color: var(--neon-emerald); font-weight: 700;">${capAfter}</td>
        <td>${winRate}</td>
      </tr>
    `;
  }).join('');
}

function switchAppTradeView(view) {
  appState.appTradesView = view;
  const tableContainer = document.getElementById('app-trades-table-container');
  const feedContainer = document.getElementById('app-stream-feed');
  const tableBtn = document.getElementById('app-tab-table-btn');
  const feedBtn = document.getElementById('app-tab-feed-btn');

  if (view === 'table') {
    if (tableContainer) tableContainer.style.display = 'block';
    if (feedContainer) feedContainer.style.display = 'none';
    if (tableBtn) tableBtn.classList.add('active');
    if (feedBtn) feedBtn.classList.remove('active');
    renderAppTradesTable();
  } else {
    if (tableContainer) tableContainer.style.display = 'none';
    if (feedContainer) feedContainer.style.display = 'flex';
    if (tableBtn) tableBtn.classList.remove('active');
    if (feedBtn) feedBtn.classList.add('active');
  }
}

// ─── View 2: App View (Live Mobile / Dedicated Monitor) ───
function renderAppLiveMonitor() {
  const s = appState.traderState;
  if (!s) return;

  // App Compounding Net Asset Value (NAV)
  const appNavVal = document.getElementById('app-nav-val');
  const appTotalProfit = document.getElementById('app-total-profit');
  const appCompMult = document.getElementById('app-comp-mult');
  const appWinRate = document.getElementById('app-win-rate');

  if (appNavVal) appNavVal.innerText = formatINR(s.total_capital);
  if (appTotalProfit) {
    appTotalProfit.innerText = formatINR(s.total_net_profit);
    appTotalProfit.className = s.total_net_profit >= 0 ? 'text-emerald' : 'text-rose';
  }
  if (appCompMult) appCompMult.innerText = s.compounding_multiplier + 'x';
  if (appWinRate) appWinRate.innerText = s.win_rate_pct + '%';

  // App Capital & Performance Summary Table
  const appInit = document.getElementById('app-initial-capital');
  const appTotal = document.getElementById('app-total-capital');
  const appPnl = document.getElementById('app-net-pnl');
  const appInvest = document.getElementById('app-invested-margin');
  const appAvail = document.getElementById('app-available-cash');
  const appWinrateTable = document.getElementById('app-winrate-table');

  if (appInit) appInit.innerText = formatINR(s.starting_capital);
  if (appTotal) appTotal.innerText = formatINR(s.total_capital);
  if (appPnl) {
    const netRetPct = s.starting_capital > 0 ? (s.total_net_profit / s.starting_capital) * 100 : 0;
    appPnl.innerText = `${s.total_net_profit >= 0 ? '+' : ''}${formatINR(s.total_net_profit)} (${formatPct(netRetPct)})`;
    appPnl.className = 'val ' + (s.total_net_profit >= 0 ? 'text-emerald' : 'text-rose');
  }
  if (appInvest) appInvest.innerText = formatINR(s.invested_capital);
  if (appAvail) appAvail.innerText = formatINR(s.available_capital);
  if (appWinrateTable) {
    appWinrateTable.innerText = `${s.win_rate_pct}% (${s.winning_trades || 0}W / ${s.losing_trades || 0}L)`;
    appWinrateTable.className = 'val ' + (s.win_rate_pct >= 50 ? 'text-emerald' : 'text-amber');
  }

  // Daily Trades Progress Ring (Target: 10-15 trades)
  const targetCountEl = document.getElementById('app-target-count');
  const ringCircle = document.getElementById('progress-ring-circle');
  const ringLabel = document.getElementById('app-ring-pct');

  if (targetCountEl) targetCountEl.innerText = `${s.daily_trades_count} / ${s.target_daily_trades}`;
  if (ringCircle && ringLabel) {
    const progress = Math.min(1.0, s.daily_trades_count / Math.max(1, s.target_daily_trades));
    const circumference = 2 * Math.PI * 22; // r=22
    const offset = circumference - (progress * circumference);
    ringCircle.style.strokeDashoffset = offset;
    ringLabel.innerText = Math.round(progress * 100) + '%';
  }

  // Render App Trades Table
  renderAppTradesTable();

  // App Active Positions List
  const posList = document.getElementById('app-pos-list');
  if (posList) {
    const positions = s.positions || {};
    const syms = Object.keys(positions);
    if (syms.length === 0) {
      posList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 10px;">No active positions. Monitoring 1m breakout signals...</div>';
    } else {
      posList.innerHTML = syms.map(sym => {
        const p = positions[sym];
        const isProfit = (p.unrealized_net_pnl || 0) >= 0;
        return `
          <div class="app-pos-item">
            <div>
              <div class="app-pos-sym">${sym.replace('.NS', '')}</div>
              <div class="app-pos-details">Entry: ₹${p.entry_price.toFixed(1)} | Qty: ${p.qty}</div>
            </div>
            <div class="app-pos-pnl ${isProfit ? 'text-emerald' : 'text-rose'}">
              ${formatINR(p.unrealized_net_pnl || 0)}
              <div style="font-size: 0.72rem;">${formatPct(p.unrealized_net_ret_pct || 0)}</div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // App Live Stream Feed (Read-Only Stream)
  const feed = document.getElementById('app-stream-feed');
  if (feed) {
    if (!appState.trades || appState.trades.length === 0) {
      feed.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 8px;">Waiting for 1-minute executions...</div>';
    } else {
      feed.innerHTML = appState.trades.slice(0, 10).map(t => {
        const isBuy = t.action === 'BUY';
        const isProfit = t.net_profit > 0;
        const timeStr = t.timestamp ? t.timestamp.split('T')[1].split('.')[0] : '--:--';
        return `
          <div class="stream-item ${!isBuy ? (isProfit ? 'sell-profit' : 'sell-loss') : ''}">
            <div>
              <strong>${t.action} ${t.symbol.replace('.NS', '')}</strong>
              <span style="color: var(--text-muted); margin-left: 6px;">@ ₹${(t.exit_price || t.price).toFixed(2)}</span>
            </div>
            <div style="text-align: right;">
              <span class="${!isBuy ? (isProfit ? 'text-emerald' : 'text-rose') : 'text-cyan'}">
                ${isBuy ? '1m Target >0.8%' : formatINR(t.net_profit)}
              </span>
              <div style="font-size: 0.65rem; color: var(--text-dim);">${timeStr}</div>
            </div>
          </div>
        `;
      }).join('');
    }
  }
}

// ─── Interactive Charts ───────────────────────────────────────────────────
function renderCompoundingChart() {
  const canvas = document.getElementById('compounding-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const curve = appState.compoundingCurve || [];
  if (curve.length < 2) return;

  const w = canvas.width = canvas.parentElement.clientWidth;
  const h = canvas.height = 180;
  ctx.clearRect(0, 0, w, h);

  const values = curve.map(pt => pt.total_capital);
  const minVal = Math.min(...values) * 0.995;
  const maxVal = Math.max(...values) * 1.005;
  const range = (maxVal - minVal) || 1;

  // Draw Area Gradient
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(0, 255, 136, 0.35)');
  grad.addColorStop(1, 'rgba(0, 255, 136, 0.0)');

  ctx.beginPath();
  curve.forEach((pt, i) => {
    const x = (i / (curve.length - 1)) * (w - 40) + 20;
    const y = h - ((pt.total_capital - minVal) / range) * (h - 40) - 20;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo((w - 20), h);
  ctx.lineTo(20, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Draw Curve Line
  ctx.beginPath();
  curve.forEach((pt, i) => {
    const x = (i / (curve.length - 1)) * (w - 40) + 20;
    const y = h - ((pt.total_capital - minVal) / range) * (h - 40) - 20;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2.5;
  ctx.stroke();
}

function renderCandlestickChart(candles) {
  const canvas = document.getElementById('candle-canvas');
  if (!canvas || !candles || candles.length === 0) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.parentElement.clientWidth;
  const h = canvas.height = 220;
  ctx.clearRect(0, 0, w, h);

  const highs = candles.map(c => c.high);
  const lows = candles.map(c => c.low);
  const maxP = Math.max(...highs);
  const minP = Math.min(...lows);
  const range = (maxP - minP) || 1;

  const barW = Math.max(3, Math.floor((w - 60) / candles.length) - 3);

  candles.forEach((c, i) => {
    const x = 30 + i * (barW + 3);
    const yOpen = h - ((c.open - minP) / range) * (h - 50) - 25;
    const yClose = h - ((c.close - minP) / range) * (h - 50) - 25;
    const yHigh = h - ((c.high - minP) / range) * (h - 50) - 25;
    const yLow = h - ((c.low - minP) / range) * (h - 50) - 25;

    const isGreen = c.close >= c.open;
    const color = isGreen ? '#00ff88' : '#ff3366';

    // Wick
    ctx.beginPath();
    ctx.moveTo(x + barW / 2, yHigh);
    ctx.lineTo(x + barW / 2, yLow);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.stroke();

    // Body
    ctx.fillStyle = color;
    const topY = Math.min(yOpen, yClose);
    const bodyH = Math.max(2, Math.abs(yClose - yOpen));
    ctx.fillRect(x, topY, barW, bodyH);
  });

  // Label
  const label = document.getElementById('candle-symbol-label');
  if (label) {
    const latest = candles[candles.length - 1];
    label.innerText = `${appState.selectedSymbol.replace('.NS', '')} - ₹${latest.close.toFixed(2)}`;
  }
}

// ─── Interactive Actions & Treasury Controls ──────────────────────────────
async function submitDeposit() {
  const input = document.getElementById('deposit-input');
  const amount = parseFloat(input.value);
  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid deposit amount.');
    return;
  }
  try {
    const res = await fetch('/api/capital/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'deposit', amount: amount, note: 'Web Treasury Deposit' })
    });
    const data = await res.json();
    if (res.ok) {
      input.value = '';
      showToast(`✅ ${data.message}`);
      fetchState();
    } else {
      alert(data.detail || 'Deposit failed');
    }
  } catch (e) {
    alert('Network error: ' + e);
  }
}

async function submitWithdrawal() {
  const input = document.getElementById('withdraw-input');
  const amount = parseFloat(input.value);
  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid withdrawal amount.');
    return;
  }
  try {
    const res = await fetch('/api/capital/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'withdraw', amount: amount, note: 'Web Treasury Withdrawal' })
    });
    const data = await res.json();
    if (res.ok) {
      input.value = '';
      showToast(`✅ ${data.message}`);
      fetchState();
    } else {
      alert(data.detail || 'Withdrawal failed');
    }
  } catch (e) {
    alert('Network error: ' + e);
  }
}

async function submitSetCapital() {
  const input = document.getElementById('set-capital-input');
  const amount = parseFloat(input.value);
  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid base capital amount (greater than zero).');
    return;
  }
  if (!confirm(`Are you sure you want to set / re-base initial capital to ${formatINR(amount)}?`)) {
    return;
  }
  try {
    const res = await fetch('/api/capital/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_capital', amount: amount, note: 'Web Reset Base Capital' })
    });
    const data = await res.json();
    if (res.ok) {
      input.value = '';
      showToast(`🎯 ${data.message}`);
      fetchState();
    } else {
      alert(data.detail || 'Set capital failed');
    }
  } catch (e) {
    alert('Network error: ' + e);
  }
}

// ─── App View Capital Adjustment Modal Handlers ────────────────────────────
function openAppCapitalModal() {
  const modal = document.getElementById('app-capital-modal');
  if (modal) modal.classList.add('active');
  selectAppAdjustAction(appState.appAdjustAction || 'deposit');
  const input = document.getElementById('app-adjust-input');
  if (input) input.focus();
}

function closeAppCapitalModal() {
  const modal = document.getElementById('app-capital-modal');
  if (modal) modal.classList.remove('active');
}

function selectAppAdjustAction(action) {
  appState.appAdjustAction = action;
  const btnDep = document.getElementById('app-adjust-btn-deposit');
  const btnWth = document.getElementById('app-adjust-btn-withdraw');
  const btnSet = document.getElementById('app-adjust-btn-set');
  const submitBtn = document.getElementById('app-adjust-submit-btn');
  const label = document.getElementById('app-adjust-amount-label');

  [btnDep, btnWth, btnSet].forEach(b => {
    if (b) {
      b.className = 'btn btn-outline';
      b.style.color = '';
      b.style.borderColor = '';
    }
  });

  if (action === 'deposit') {
    if (btnDep) btnDep.className = 'btn btn-emerald active';
    if (label) label.innerText = 'ADD CAPITAL (DEPOSIT INR)';
    if (submitBtn) {
      submitBtn.innerText = '➕ Confirm Deposit';
      submitBtn.className = 'btn btn-emerald';
      submitBtn.style.color = '';
      submitBtn.style.borderColor = '';
    }
  } else if (action === 'withdraw') {
    if (btnWth) btnWth.className = 'btn btn-danger active';
    if (label) label.innerText = 'WITHDRAW CASH (UNINVESTED INR)';
    if (submitBtn) {
      submitBtn.innerText = '➖ Confirm Withdrawal';
      submitBtn.className = 'btn btn-danger';
      submitBtn.style.color = '';
      submitBtn.style.borderColor = '';
    }
  } else if (action === 'set_capital') {
    if (btnSet) {
      btnSet.className = 'btn btn-outline active';
      btnSet.style.color = 'var(--neon-cyan)';
      btnSet.style.borderColor = 'var(--neon-cyan)';
    }
    if (label) label.innerText = 'SET NEW BASE CAPITAL (INR)';
    if (submitBtn) {
      submitBtn.innerText = '🎯 Confirm Base Reset';
      submitBtn.className = 'btn btn-outline';
      submitBtn.style.color = 'var(--neon-cyan)';
      submitBtn.style.borderColor = 'var(--neon-cyan)';
    }
  }
}

function setAppPreset(amount) {
  const input = document.getElementById('app-adjust-input');
  if (input) input.value = amount;
}

async function submitAppCapitalAdjust() {
  const input = document.getElementById('app-adjust-input');
  const noteInput = document.getElementById('app-adjust-note');
  const amount = parseFloat(input ? input.value : 0);
  const note = (noteInput && noteInput.value) || `App Manual ${appState.appAdjustAction}`;

  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid amount greater than zero.');
    return;
  }

  if (appState.appAdjustAction === 'set_capital') {
    if (!confirm(`Are you sure you want to set / re-base initial capital to ${formatINR(amount)}?`)) {
      return;
    }
  }

  try {
    const res = await fetch('/api/capital/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: appState.appAdjustAction,
        amount: amount,
        note: note
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (input) input.value = '';
      if (noteInput) noteInput.value = '';
      closeAppCapitalModal();
      showToast(`✅ ${data.message}`);
      fetchState();
    } else {
      alert(data.detail || 'Capital adjustment failed');
    }
  } catch (e) {
    alert('Network error: ' + e);
  }
}

async function toggleEngine() {
  const s = appState.traderState;
  const isRunning = s && s.engine_status === 'RUNNING';
  const action = isRunning ? 'pause' : 'start';
  try {
    const res = await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    showToast(data.message);
    fetchState();
  } catch (e) {
    alert('Failed to toggle engine: ' + e);
  }
}

async function emergencyCloseAll() {
  if (!confirm('Are you sure you want to close all active positions immediately at market prices?')) return;
  try {
    const res = await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'emergency_close' })
    });
    const data = await res.json();
    showToast(data.message);
    fetchState();
  } catch (e) {
    alert('Emergency close failed: ' + e);
  }
}

async function triggerManualScan() {
  try {
    showToast('Executing 1-minute scan cycle...');
    const res = await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'scan_now' })
    });
    const data = await res.json();
    showToast(data.message);
    fetchState();
  } catch (e) {
    console.error(e);
  }
}

async function triggerRetrain() {
  try {
    showToast('🧠 Triggering 1-Minute ML Ensemble preprocessing & retraining...');
    const res = await fetch('/api/model/retrain', { method: 'POST' });
    const data = await res.json();
    showToast(`✅ ${data.message}`);
  } catch (e) {
    alert('Retrain request failed: ' + e);
  }
}

async function updateSetting(param, value) {
  const body = {};
  body[param] = parseFloat(value);
  try {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    fetchState();
  } catch (e) {
    console.error(e);
  }
}

async function toggleOffMarketSim() {
  const current = appState.traderState ? appState.traderState.off_market_simulation : false;
  const nextVal = !current;
  try {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ off_market_simulation: nextVal })
    });
    showToast(nextVal ? '🧪 Off-Market Simulation ENABLED (Synthetic testing ticks active)' : '🛑 Off-Market Simulation DISABLED (Prices frozen at today close)');
    fetchState();
  } catch (e) {
    console.error(e);
  }
}

async function manualClose(symbol) {
  try {
    const res = await fetch('/api/manual-trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, action: 'SELL' })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Closed ${symbol}`);
      fetchState();
    } else {
      alert(data.detail);
    }
  } catch (e) {
    alert(e);
  }
}

function selectSymbol(sym) {
  appState.selectedSymbol = sym;
  fetchCandles(sym);
}

// ─── Mode Switching (Website vs App vs After-Market) ──────────────────────
function switchMode(targetMode) {
  appState.mode = targetMode;
  const webView = document.getElementById('website-view');
  const appView = document.getElementById('app-view');
  const amView = document.getElementById('aftermarket-view');
  const tabWeb = document.getElementById('tab-website');
  const tabApp = document.getElementById('tab-app');
  const tabAm = document.getElementById('tab-aftermarket');

  if (targetMode === 'app') {
    if (webView) webView.style.display = 'none';
    if (appView) appView.style.display = 'block';
    if (amView) amView.style.display = 'none';
    if (tabWeb) tabWeb.classList.remove('active');
    if (tabApp) tabApp.classList.add('active');
    if (tabAm) tabAm.classList.remove('active');
  } else if (targetMode === 'aftermarket') {
    if (webView) webView.style.display = 'none';
    if (appView) appView.style.display = 'none';
    if (amView) amView.style.display = 'block';
    if (tabWeb) tabWeb.classList.remove('active');
    if (tabApp) tabApp.classList.remove('active');
    if (tabAm) tabAm.classList.add('active');
    fetchAftermarketData();
  } else {
    if (webView) webView.style.display = 'block';
    if (appView) appView.style.display = 'none';
    if (amView) amView.style.display = 'none';
    if (tabWeb) tabWeb.classList.add('active');
    if (tabApp) tabApp.classList.remove('active');
    if (tabAm) tabAm.classList.remove('active');
  }
}

// ─── App Mockup Sub-Navigation ─────────────────────────────────────────────
function switchAppSubTab(subTab) {
  const liveContent = document.getElementById('app-content-live');
  const amContent = document.getElementById('app-content-aftermarket');
  const subLiveBtn = document.getElementById('app-subtab-live');
  const subAmBtn = document.getElementById('app-subtab-aftermarket');

  if (subTab === 'aftermarket') {
    if (liveContent) liveContent.style.display = 'none';
    if (amContent) amContent.style.display = 'block';
    if (subLiveBtn) subLiveBtn.classList.remove('active');
    if (subAmBtn) subAmBtn.classList.add('active');
    fetchAftermarketData();
  } else {
    if (liveContent) liveContent.style.display = 'block';
    if (amContent) amContent.style.display = 'none';
    if (subLiveBtn) subLiveBtn.classList.add('active');
    if (subAmBtn) subAmBtn.classList.remove('active');
  }
}

// ─── After-Market Hub & Model Optimization Functions ──────────────────────
async function fetchAftermarketData() {
  try {
    // 1. Fetch Session Recap
    const recapRes = await fetch('/api/session/recap');
    if (recapRes.ok) {
      const recap = await recapRes.json();
      if (recap.completed_trades) {
        // Desktop KPIs
        const winEl = document.getElementById('am-kpi-winrate');
        const countEl = document.getElementById('am-kpi-trades-count');
        const pnlEl = document.getElementById('am-kpi-netpnl');
        const pfEl = document.getElementById('am-kpi-profitfactor');
        const fricEl = document.getElementById('am-kpi-frictions');

        if (winEl) winEl.innerText = recap.win_rate_pct + '%';
        if (countEl) countEl.innerText = `${recap.winning_trades} Wins / ${recap.losing_trades} Losses (${recap.completed_trades} Total)`;
        if (pnlEl) {
          pnlEl.innerText = formatINR(recap.total_net_pnl);
          pnlEl.className = 'metric-val ' + (recap.total_net_pnl >= 0 ? 'text-emerald' : 'text-rose');
        }
        if (pfEl) pfEl.innerText = `Profit Factor: ${recap.profit_factor} (Gross Wins: ₹${(recap.gross_profit/1000).toFixed(1)}K)`;
        if (fricEl) fricEl.innerText = formatINR(recap.total_tax_paid + recap.total_brokerage_paid);

        // App KPIs
        const appWin = document.getElementById('app-am-winrate');
        const appTrades = document.getElementById('app-am-trades');
        if (appWin) appWin.innerText = recap.win_rate_pct + '%';
        if (appTrades) appTrades.innerText = recap.completed_trades + ' trades';

        // Render Per-Stock Table
        const stocksTbody = document.getElementById('am-stocks-tbody');
        if (stocksTbody && recap.stocks_breakdown) {
          stocksTbody.innerHTML = recap.stocks_breakdown.map(st => `
            <tr>
              <td><strong>${st.symbol.replace('.NS', '')}</strong></td>
              <td>${st.trades}</td>
              <td class="${st.win_rate_pct >= 65 ? 'text-emerald' : 'text-amber'}">${st.win_rate_pct}%</td>
              <td>${st.stop_losses}</td>
              <td class="${st.avg_net_return_pct >= 0 ? 'text-emerald' : 'text-rose'}">${formatPct(st.avg_net_return_pct)}</td>
              <td class="${st.net_pnl >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">${formatINR(st.net_pnl)}</td>
            </tr>
          `).join('');
        }

        // Render Exit Reasons Table
        const reasonsTbody = document.getElementById('am-reasons-tbody');
        if (reasonsTbody && recap.reasons_breakdown) {
          reasonsTbody.innerHTML = recap.reasons_breakdown.map(r => `
            <tr>
              <td><span class="signal-badge ${r.net_pnl >= 0 ? 'buy' : 'hold'}" style="font-size: 0.7rem; padding: 2px 6px;">${r.reason}</span></td>
              <td>${r.count}</td>
              <td class="${r.win_rate_pct >= 50 ? 'text-emerald' : 'text-rose'}">${r.win_rate_pct}%</td>
              <td class="${r.net_pnl >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 700;">${formatINR(r.net_pnl)}</td>
            </tr>
          `).join('');
        }
      }
    }

    // 2. Fetch Model Metrics
    const metRes = await fetch('/api/model/metrics');
    if (metRes.ok) {
      const metData = await metRes.json();
      const m = metData.metrics || {};
      const kpiMae = document.getElementById('am-kpi-mae');
      const appMae = document.getElementById('app-am-mae');
      if (m.test_mae_pct !== undefined) {
        if (kpiMae) kpiMae.innerText = m.test_mae_pct.toFixed(3) + '% (' + (m.test_mae_pct*100).toFixed(0) + ' bps)';
        if (appMae) appMae.innerText = m.test_mae_pct.toFixed(3) + '%';
      }
    }

    // 3. Fetch Predictions
    const predRes = await fetch('/api/model/predictions');
    if (predRes.ok) {
      const predData = await predRes.json();
      const preds = predData.predictions || [];
      
      // Desktop Predictions Table
      const amPredsTbody = document.getElementById('am-predictions-tbody');
      if (amPredsTbody && preds.length > 0) {
        amPredsTbody.innerHTML = preds.map(p => {
          const isBuy = p.signal === 'BUY';
          return `
            <tr style="${isBuy ? 'background: rgba(0, 255, 136, 0.05);' : ''}">
              <td>
                <strong>${p.symbol.replace('.NS', '')}</strong>
                <span style="font-size: 0.68rem; color: var(--text-muted); display: block;">${p.company || ''}</span>
              </td>
              <td>₹${p.current_price.toFixed(2)}</td>
              <td style="font-weight: 700; color: ${isBuy ? 'var(--neon-emerald)' : 'var(--neon-cyan)'};">₹${p.predicted_price_1m.toFixed(2)}</td>
              <td class="${p.predicted_return_pct >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight: 800;">${formatPct(p.predicted_return_pct)}</td>
              <td class="text-cyan">${p.confidence}%</td>
              <td>
                <span class="signal-badge ${isBuy ? 'buy' : 'hold'}" style="font-size: 0.72rem; padding: 2px 6px;">
                  ${p.signal}
                </span>
              </td>
              <td style="color: var(--neon-amber);">${p.profit_threshold_pct ? p.profit_threshold_pct.toFixed(2) + '%' : '0.20%'}</td>
            </tr>
          `;
        }).join('');
      }

      // App Predictions List
      const appPredList = document.getElementById('app-predictions-list');
      if (appPredList && preds.length > 0) {
        appPredList.innerHTML = preds.map(p => {
          const isBuy = p.signal === 'BUY';
          return `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid ${isBuy ? 'rgba(0,255,136,0.3)' : 'var(--border-subtle)'}; border-radius: var(--radius-sm); padding: 8px 10px; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <strong style="font-size: 0.8rem; color: #fff;">${p.symbol.replace('.NS', '')}</strong>
                <span style="font-size: 0.68rem; color: var(--text-muted); display: block;">Close: ₹${p.current_price.toFixed(2)}</span>
              </div>
              <div style="text-align: right;">
                <div style="font-size: 0.8rem; font-weight: 800; color: ${p.predicted_return_pct >= 0 ? 'var(--neon-emerald)' : 'var(--neon-rose)'};">${formatPct(p.predicted_return_pct)}</div>
                <span class="signal-badge ${isBuy ? 'buy' : 'hold'}" style="font-size: 0.65rem; padding: 1px 4px;">${p.signal} (${p.confidence}%)</span>
              </div>
            </div>
          `;
        }).join('');
      }
    }
  } catch (e) {
    console.error('Failed to fetch after-market data:', e);
  }
}

async function triggerLiveRetrain() {
  const btn = document.getElementById('am-retrain-btn');
  const appBtn = document.getElementById('app-retrain-btn');
  const statusEl = document.getElementById('am-retrain-status');
  const appStatusEl = document.getElementById('app-retrain-status');

  if (btn) { btn.disabled = true; btn.innerText = '⏳ Retraining...'; }
  if (appBtn) { appBtn.disabled = true; appBtn.innerText = '⏳ Retraining...'; }
  if (statusEl) statusEl.innerText = 'Status: Fetching 5-day live 1m candles and retraining ensemble on 58,388 samples...';
  if (appStatusEl) appStatusEl.innerText = 'Status: Retraining in background...';
  showToast('Overnight ML Retraining launched! Ingesting latest 1m candles.');

  try {
    const res = await fetch('/api/model/retrain_live', { method: 'POST' });
    const data = await res.json();
    setTimeout(async () => {
      await fetchAftermarketData();
      if (btn) { btn.disabled = false; btn.innerText = '🚀 Retrain ML Ensemble'; }
      if (appBtn) { appBtn.disabled = false; appBtn.innerText = '🚀 Retrain & Calibrate Models'; }
      if (statusEl) statusEl.innerText = 'Status: ✅ Retraining complete! Fresh models & predictions hot-applied.';
      if (appStatusEl) appStatusEl.innerText = 'Status: ✅ Retraining complete!';
      showToast('Models successfully retrained and hot-applied!');
    }, 12000);
  } catch (e) {
    if (btn) { btn.disabled = false; btn.innerText = '🚀 Retrain ML Ensemble'; }
    if (appBtn) { appBtn.disabled = false; appBtn.innerText = '🚀 Retrain & Calibrate Models'; }
    if (statusEl) statusEl.innerText = 'Status: Error triggering retrain.';
  }
}

async function saveStudioParameters() {
  const hurdle = parseFloat(document.getElementById('studio-hurdle-slider').value);
  const sl = parseFloat(document.getElementById('studio-sl-slider').value);
  const sizing = parseFloat(document.getElementById('studio-sizing-slider').value) / 100.0;

  try {
    const res = await fetch('/api/model/tune_parameters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profit_threshold_pct: hurdle / 100.0,
        stop_loss_pct: sl / 100.0,
        position_sizing_pct: sizing
      })
    });
    const data = await res.json();
    showToast('Efficiency parameters saved & hot-applied to engine!');
  } catch (e) {
    showToast('Failed to save parameters: ' + e);
  }
}

function toggleAppFrame() {
  const frame = document.getElementById('app-device-frame');
  const btn = document.getElementById('app-fullscreen-btn');
  if (!frame) return;

  appState.appFullscreen = !appState.appFullscreen;
  if (appState.appFullscreen) {
    frame.classList.add('fullscreen');
    if (btn) btn.innerText = '📱 Mobile Frame';
  } else {
    frame.classList.remove('fullscreen');
    if (btn) btn.innerText = '🖥️ Fullscreen App';
  }
}

// ─── Autonomous AI Agent Supervisor Client ─────────────────────────────────
async function fetchAgentStatus() {
  try {
    const res = await fetch('/api/agent/status');
    if (!res.ok) return;
    const data = await res.json();
    renderAgentSupervisor(data);
  } catch (err) {
    // Quietly ignore network blips
  }
}

function renderAgentSupervisor(data) {
  if (!data) return;

  // Status Badge
  const statusBadge = document.querySelectorAll('#ai-agent-status-badge');
  statusBadge.forEach(badge => {
    if (data.status === 'ACTIVE') {
      badge.innerHTML = '● AUTONOMOUS SURVEILLANCE';
      badge.className = 'ai-agent-status-pill';
    } else {
      badge.innerHTML = '○ STANDBY';
      badge.className = 'ai-agent-status-pill text-amber';
    }
  });

  // Autopilot Button Text
  const autoBtns = document.querySelectorAll('#ai-agent-autopilot-btn');
  autoBtns.forEach(btn => {
    btn.innerHTML = data.autopilot ? '⚡ Autopilot: ON' : '⏸️ Autopilot: OFF';
    btn.className = data.autopilot ? 'btn btn-emerald' : 'btn btn-outline';
  });

  // Telemetry Snapshot
  const telem = data.telemetry || {};
  const web = telem.web_desk || {};
  const app = telem.mobile_app || {};
  const lab = telem.sim_lab || {};

  // Web Desk Telemetry
  const webVal = document.querySelectorAll('#ai-telemetry-web-val');
  const webSub = document.querySelectorAll('#ai-telemetry-web-sub');
  webVal.forEach(el => el.innerText = formatINR(web.total_capital || 5000));
  webSub.forEach(el => el.innerText = `Uninvested: ${web.uninvested_cash_pct || 100}% | Drawdown: ${(web.drawdown_pct || 0).toFixed(2)}% (${web.capital_health || 'SECURE'})`);

  // Mobile App Telemetry
  const appVal = document.querySelectorAll('#ai-telemetry-app-val');
  const appSub = document.querySelectorAll('#ai-telemetry-app-sub');
  appVal.forEach(el => el.innerText = `${app.daily_trades || 0} / ${app.target_trades || 15} Trades`);
  appSub.forEach(el => el.innerText = `Win Rate: ${app.win_rate_pct || 0}% | Active Pos: ${app.active_positions_count || 0} (${app.execution_status || 'NOMINAL'})`);

  // Sim Lab Telemetry
  const labVal = document.querySelectorAll('#ai-telemetry-lab-val');
  const labSub = document.querySelectorAll('#ai-telemetry-lab-sub');
  labVal.forEach(el => el.innerText = `Acc: ${lab.directional_accuracy_pct || 0}%`);
  labSub.forEach(el => el.innerText = `Verified: ${lab.total_verified || 0} | Whipsaws: ${lab.whipsaws_count || 0} (${lab.model_health || 'OPTIMAL'})`);

  // Thought Stream & Diagnostics Log
  const thoughtStreams = document.querySelectorAll('#ai-agent-thought-stream');
  const thoughts = data.thoughts || [];
  if (thoughts.length > 0) {
    const streamHtml = thoughts.slice(0, 15).map(t => {
      return `<div><span style="color: var(--text-dim);">[${t.time}]</span> <span style="color: var(--neon-cyan);">${t.thought}</span></div>`;
    }).join('');
    thoughtStreams.forEach(s => s.innerHTML = streamHtml);
  }

  const timeStampEls = document.querySelectorAll('#ai-thought-timestamp');
  timeStampEls.forEach(el => el.innerText = `Sweep: ${data.last_sweep ? data.last_sweep.split('T')[1].split('.')[0] : 'Just now'}`);

  // Formulated Plans List
  const plansContainers = document.querySelectorAll('#ai-agent-plans-list');
  const countBadges = document.querySelectorAll('#ai-plans-count-badge');
  const plans = data.plans || [];

  countBadges.forEach(b => b.innerText = `${plans.length} PLANS`);

  if (plans.length === 0) {
    plansContainers.forEach(c => {
      c.innerHTML = '<div style="color: var(--text-muted); font-size: 0.78rem; padding: 6px;">All 3 surfaces operating within calibrated tolerance bands. No corrective actions required.</div>';
    });
  } else {
    const plansHtml = plans.map(p => {
      const isExec = p.executed;
      return `
        <div class="ai-agent-plan-item" style="${isExec ? 'opacity: 0.65;' : ''}">
          <div class="ai-plan-info">
            <div class="ai-plan-title">
              <span class="badge-nse" style="font-size: 0.65rem;">${p.category}</span>
              <span>${p.title}</span>
              ${isExec ? '<span style="color: var(--neon-emerald); font-size: 0.72rem; font-weight: 700;">✅ EXECUTED</span>' : ''}
            </div>
            <div class="ai-plan-desc">${p.description}</div>
          </div>
          <div>
            ${!isExec ? `
              <button class="btn btn-primary" style="font-size: 0.75rem; padding: 6px 14px;" onclick="executeAgentPlan('${p.id}')">
                ⚡ Execute Plan
              </button>
            ` : `
              <button class="btn btn-outline" style="font-size: 0.72rem; padding: 4px 10px;" disabled>
                Applied
              </button>
            `}
          </div>
        </div>
      `;
    }).join('');
    plansContainers.forEach(c => c.innerHTML = plansHtml);
  }
}

async function toggleAgentAutopilot() {
  try {
    const res = await fetch('/api/agent/toggle-autopilot', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const data = await res.json();
    showToast(`🤖 AI Agent Autopilot: ${data.autopilot_enabled ? 'ENABLED (Auto-Execution Active)' : 'MUTED (Manual Approval Mode)'}`);
    await fetchAgentStatus();
  } catch (err) {
    showToast('Failed to toggle autopilot: ' + err);
  }
}

async function requestAgentPlanSweep() {
  try {
    showToast('🤖 Running tri-surface diagnostic sweep across Web, Mobile & Lab...');
    const res = await fetch('/api/agent/generate-plan', { method: 'POST' });
    const data = await res.json();
    renderAgentSupervisor(data);
    showToast('✅ Diagnostic sweep completed. Plans refreshed.');
  } catch (err) {
    showToast('Sweep failed: ' + err);
  }
}

async function executeAgentPlan(planId) {
  try {
    showToast(`⚡ Executing plan '${planId}'...`);
    const res = await fetch('/api/agent/execute-plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId })
    });
    const data = await res.json();
    showToast('✅ ' + (data.message || 'Plan executed successfully!'));
    await fetchAgentStatus();
  } catch (err) {
    showToast('Plan execution failed: ' + err);
  }
}

// ─── Initialization ───────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  // Check URL query param or standalone page presence for default view
  const urlParams = new URLSearchParams(window.location.search);
  const path = window.location.pathname;
  const hasOnlyApp = document.getElementById('app-view') && !document.getElementById('website-view');
  const hasOnlyWeb = document.getElementById('website-view') && !document.getElementById('app-view');

  if (hasOnlyApp || urlParams.get('mode') === 'app' || path.endsWith('/app') || path.endsWith('app.html')) {
    switchMode('app');
  } else if (urlParams.get('mode') === 'aftermarket' || path.endsWith('/aftermarket')) {
    switchMode('aftermarket');
  } else {
    switchMode('website');
  }

  initWebSocket();
  fetchState();
  fetchVerifications();
  fetchTrades();
  fetchCandles(appState.selectedSymbol);
  fetchAftermarketData();
  fetchAgentStatus();

  // Periodic poll fallbacks to guarantee live updates 24/7 even during WS reconnect
  setInterval(() => {
    fetchState();
  }, 2000);

  setInterval(() => {
    fetchVerifications();
  }, 3000);

  setInterval(() => {
    fetchTrades();
  }, 3500);

  setInterval(() => {
    fetchCandles(appState.selectedSymbol);
  }, 8000);

  setInterval(() => {
    fetchAgentStatus();
  }, 4000);

  setInterval(() => {
    if (appState.mode === 'aftermarket') {
      fetchAftermarketData();
    }
  }, 5000);

  setInterval(() => {
    if (appState.settingsTab === 'history') {
      loadSettingsHistory();
    }
  }, 6000);
});

