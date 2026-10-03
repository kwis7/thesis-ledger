'use strict';

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const pages = {today: 'Today', research: 'Company Research', lab: 'Research Lab', monitor: 'Monitor & Timeline', alerts: 'Alerts', library: 'Research Library', workspace: 'My Workspace'};
  const ui = {state: null, page: 'today', symbol: null, tab: 'thesis', filter: 'all', details: new Map(), reports: [], busy: false, loadingDetail: false, detailError: '', tourVisible: true, connected: true, accessToken: '', authPending: null, candidateReview: null,
    lab: {symbol: null, data: null, parameters: [], values: {}, loading: false, error: '', calculationError: '', revision: 0, timer: null, inFlight: false, queued: false, dirty: false, runs: [], runsSkipped: 0, runsError: '', run: null, runBusy: false, runError: '', verification: null}};
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[character]));
  const e = escape;
  const array = value => Array.isArray(value) ? value : [];
  const human = value => String(value ?? '').replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  const number = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const money = (value, digits = 2) => number(value) === null ? 'Unavailable' : '$' + Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const num = (value, digits = 1) => number(value) === null ? 'Unavailable' : Number(value).toLocaleString('en-US', {maximumFractionDigits: digits});
  const percent = (value, digits = 1) => number(value) === null ? 'Unavailable' : (Number(value) * 100).toFixed(digits) + '%';
  const date = (value, full = false) => {
    if (!value) return 'Not yet checked';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleDateString('en-US', {month: 'short', day: 'numeric', ...(full ? {year: 'numeric'} : {}), timeZone: 'UTC'});
  };
  const datetime = value => {
    if (!value) return 'Not yet checked';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString('en-US', {month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC'}) + ' UTC';
  };
  const icon = (name, cls = '') => {
    const paths = {arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>', replay:'<path d="m9 5 11 7-11 7zM4 5v14"/>', check:'<path d="m5 12 4 4L19 6"/>', bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>', company:'<path d="M4 21V8h7v13M11 21V3h9v18M2 21h20M7 11v2m0 3v2m8-12v2m3-2v2m-3 3v2m3-2v2m-3 3v2m3-2v2"/>', chart:'<path d="M4 3v17h17M7 14l4-5 4 3 5-7"/>', source:'<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 4h5"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>', warning:'<path d="m12 3 10 17H2zM12 9v4m0 3v.1"/>', search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>', download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>', pause:'<path d="M8 5v14M16 5v14"/>', play:'<path d="m7 4 14 8-14 8z"/>', mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>', gap:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4v.1"/>', book:'<path d="M12 5C8 2 3 3 3 3v17s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2zM12 5v17"/>'};
    return '<svg class="' + e(cls) + '" viewBox="0 0 24 24" aria-hidden="true">' + (paths[name] || paths.source) + '</svg>';
  };
  const button = (label, action, attrs = '', cls = '', name = '') => '<button type="button" class="button ' + cls + '" data-action="' + action + '" ' + attrs + (ui.busy ? ' disabled' : '') + '>' + (name ? icon(name) : '') + e(label) + '</button>';
  const badge = (text, style = '') => '<span class="badge ' + style + '">' + e(text) + '</span>';
  const thesisBadge = company => company.thesis_status === 'review_required' ? badge('Review required', 'warning') : company.thesis_status === 'updated' ? badge('Thesis updated', 'info') : badge('Thesis unchanged');
  const logo = (company, index = 0) => '<span class="company-logo ' + (index % 3 === 1 ? 'blue' : index % 3 === 2 ? 'plum' : '') + '" aria-hidden="true">' + e((company.symbol || company.name || 'T').slice(0, 1)) + '</span>';
  const sectionHeading = (title, description = '', action = '') => '<div class="section-heading"><div><h2>' + e(title) + '</h2>' + (description ? '<p>' + e(description) + '</p>' : '') + '</div>' + action + '</div>';
  const unavailable = (title, message) => '<div class="unavailable">' + icon('gap') + '<div><h3>' + e(title) + '</h3><p>' + e(message) + '</p></div></div>';
  const textOf = value => Array.isArray(value) ? value.map(textOf).join(' ') : typeof value === 'object' && value !== null ? String(value.label || value.statement || value.description || value.reason || value.summary || value.title || JSON.stringify(value)) : String(value ?? '');
  const safeUrl = value => {
    try {const parsed = new URL(String(value), location.origin); return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;} catch {return null;}
  };
  const activeCompany = () => ui.details.get(ui.symbol) || array(ui.state?.companies).find(company => company.symbol === ui.symbol) || null;
  const companies = () => array(ui.state?.companies);
  const alerts = () => array(ui.state?.alerts);
  const sourceStatusAlert = alert => {const event=array(ui.state?.events).find(item => item.id === alert.event_id);return event?.source_status === true || ['source_failure','source_recovered'].includes(event?.kind);};
  const alertBadge = alert => sourceStatusAlert(alert) ? badge('Source status','warning') : badge(alert.verification === 'verified' ? 'Evidence verified' : 'Needs verification', alert.verification === 'verified' ? 'info' : 'warning');
  const isSynthetic = () => ui.state?.meta?.mode === 'synthetic_replay' || ui.state?.meta?.synthetic === true;
  const selectedValuation = company => company.valuation || {};
  const baseValue = valuation => number(valuation?.base) ?? scenarioValue(scenarios(valuation).find(scenario => String(scenario.name).toLowerCase() === 'base'));
  const scenarios = valuation => {
    if (Array.isArray(valuation?.scenarios)) return valuation.scenarios;
    if (valuation?.scenarios && typeof valuation.scenarios === 'object') return Object.entries(valuation.scenarios).map(([name, values]) => ({name, ...values}));
    return ['bear', 'base', 'bull'].filter(name => number(valuation?.[name]) !== null).map(name => ({name, value: valuation[name]}));
  };
  const scenarioValue = scenario => number(scenario?.value_per_share ?? scenario?.value);
  const validModel = valuation => baseValue(valuation) !== null && !['unavailable', 'unsupported'].includes(valuation?.state);
  const valueLabel = (value, unit) => {
    if (number(value) === null) return e(textOf(value) || 'Unavailable');
    if (/ratio|fraction|percent|%/.test(unit || '')) return e(percent(value));
    if (unit === 'million customers' && Number(value) < 1) return e(num(Number(value) * 1000000,0) + ' customers');
    return e(num(value, Number(value) < 1 ? 4 : 2) + (unit ? ' ' + unit : ''));
  };

  async function request(path, options = {}) {
    const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', ...(ui.accessToken ? {'Authorization':'Bearer ' + ui.accessToken} : {}), ...options.headers}});
    let data;
    try {data = await response.json();} catch {throw new Error('The workspace returned an unreadable response. Try refreshing the saved state.');}
    if (response.status === 401) {
      ui.accessToken = '';
      await requireAuthentication(data.message || 'This workbench requires an access token.');
      return request(path, options);
    }
    if (!response.ok || data.error) throw new Error(data.message || data.error || 'The request did not complete.');
    return data;
  }
  function requireAuthentication(message) {
    if (ui.authPending) return ui.authPending.promise;
    let resolve, reject;
    const promise = new Promise((yes,no) => {resolve=yes;reject=no;});
    ui.authPending = {promise,resolve,reject};
    dialog('Connect to your protected workbench.', '<p>' + e(message) + '</p><form class="settings-form" id="auth-form"><div class="field"><label for="workbench-token">Workbench access token</label><input id="workbench-token" name="access_token" type="password" autocomplete="off" spellcheck="false" required><small>The token is held only in this page\'s memory and sent to this workbench. It is never saved in browser storage or the URL.</small></div><div class="action-row"><button type="submit" class="button primary">Connect workspace</button></div></form>', 'WORKSPACE ACCESS');
    $('#workbench-token')?.focus();
    return promise;
  }
  function toast(message, error = false) {
    const element = document.createElement('div');
    element.className = 'toast' + (error ? ' error' : '');
    element.textContent = message;
    $('#toast-region').append(element);
    setTimeout(() => element.remove(), error ? 9000 : 5500);
  }
  function connection(message = '') {
    const banner = $('#connection-banner');
    banner.hidden = !message;
    banner.replaceChildren();
    if (message) {
      const text = document.createElement('span');text.textContent = message;banner.append(text);
      const retry = document.createElement('button');retry.type = 'button';retry.dataset.action = 'refresh';retry.textContent = 'Try again';banner.append(retry);
    }
  }
  function updateChrome() {
    const state = ui.state;
    $$('#navigation a').forEach(link => {const active = link.dataset.page === ui.page;link.classList.toggle('active', active);active ? link.setAttribute('aria-current','page') : link.removeAttribute('aria-current');});
    $('#page-label').textContent = pages[ui.page];
    document.title = 'ThesisLedger | ' + pages[ui.page];
    const count = state?.overview?.unread_alerts ?? alerts().filter(alert => alert.review_state === 'new').length;
    $('#alert-count').textContent = String(count);$('#alert-count').hidden = count === 0;
    $('#sidebar-workspace').textContent = state?.settings?.name || 'Personal workspace';
    $('#mode-badge').innerHTML = '<span></span>' + (isSynthetic() ? 'Synthetic replay' : 'Local workspace');
    $('#sidebar-mode').textContent = isSynthetic() ? 'Synthetic replay, no live feeds' : 'Saved local research';
  }
  function heading(title, subtitle, actions = '', kicker = '') {
    return '<div class="page-heading"><div>' + (kicker ? '<span class="eyebrow">' + e(kicker) + '</span>' : '') + '<h1>' + e(title) + '</h1><p>' + e(subtitle) + '</p></div>' + (actions ? '<div class="heading-actions">' + actions + '</div>' : '') + '</div>';
  }
  function updateTableCues(root = document) {
    $$('.table-scroll', root).forEach(region => {
      const overflowing = region.scrollWidth > region.clientWidth + 1;
      let cue = region.previousElementSibling;
      if (!cue?.classList.contains('table-scroll-cue')) {
        cue = document.createElement('p');cue.className = 'table-scroll-cue';
        cue.textContent = 'Scroll horizontally to compare values →';region.before(cue);
      }
      cue.hidden = !overflowing;
      region.setAttribute('aria-label', overflowing ? 'Research data table. Scroll horizontally to compare values.' : 'Research data table');
    });
  }
  function render() {
    if (!ui.state) return;
    updateChrome();
    const views = {today: renderToday, research: renderResearch, lab: renderLab, monitor: renderMonitor, alerts: renderAlerts, library: renderLibrary, workspace: renderWorkspace};
    $('#main').innerHTML = views[ui.page]();
    $('#main').setAttribute('aria-busy', String(ui.busy || (ui.page === 'research' && ui.loadingDetail) || (ui.page === 'lab' && ui.lab.loading)));
    updateTableCues($('#main'));
  }
  function setState(state) {
    const lab = ui.lab;
    const savedBaseline = snapshot => array(snapshot?.companies).find(company => company.symbol === lab.symbol)?.history?.[0]?.input_hash;
    if (lab.symbol && savedBaseline(ui.state) !== savedBaseline(state)) {
      clearTimeout(lab.timer);lab.revision++;
      Object.assign(lab, {data:null, parameters:[], values:{}, loading:false, error:'', calculationError:'', dirty:false, queued:false, run:null, runError:'', verification:null});
    }
    ui.state = state;
    if (!ui.symbol || !companies().some(company => company.symbol === ui.symbol)) ui.symbol = companies()[0]?.symbol || null;
    ui.details.clear();
    ui.connected = true;
    connection();
  }
  async function refresh(showToast = false) {
    try {
      const labSymbol = ui.lab.symbol || preferredLabSymbol();
      const state = await request('/api/state');
      setState(state);render();
      if (ui.page === 'research') await loadCompany(ui.symbol);
      if (ui.page === 'library') await loadReports();
      if (ui.page === 'lab') {
        const symbol = companies().some(company => company.symbol === labSymbol) ? labSymbol : preferredLabSymbol();
        if (!ui.lab.data || symbol !== ui.lab.symbol) await loadLab(symbol, true);
        else await loadLabRuns();
      }
      if (showToast) toast('Saved workspace refreshed.');
    } catch (error) {
      ui.connected = false;
      connection((ui.state ? 'Saved evidence remains visible. The connection failed, so freshness cannot be confirmed. ' : 'The local workspace could not be reached. ') + error.message);
      if (!ui.state) $('#main').innerHTML = '<div class="loading-shell">' + icon('gap') + '<h1>Your desk is temporarily unavailable</h1><p>Start the local ThesisLedger server, then try again.</p>' + button('Try again', 'refresh', '', 'primary') + '</div>';
      $('#main').setAttribute('aria-busy','false');
      if (showToast) toast(error.message, true);
    }
  }
  async function mutate(path, body, successMessage) {
    if (ui.busy) return null;
    ui.busy = true;
    $$('button[data-action],button[type="submit"]').forEach(element => element.disabled = true);
    $('#main').setAttribute('aria-busy','true');
    try {
      const result = await request(path, {method:'POST', body:JSON.stringify(body)});
      if (result.state) setState(result.state);
      else setState(await request('/api/state'));
      toast(result.message || successMessage || 'Workspace updated.');
      return result;
    } catch (error) {toast(error.message, true);return null;}
    finally {
      ui.busy = false;render();
      $$('button[data-action],button[type="submit"]').forEach(element => element.disabled = false);
      if (ui.page === 'research' && ui.symbol) await loadCompany(ui.symbol);
    }
  }
  async function loadCompany(symbol) {
    if (!symbol || ui.details.has(symbol)) return;
    ui.loadingDetail = true;ui.detailError = '';render();
    try {const detail = await request('/api/company/' + encodeURIComponent(symbol));ui.details.set(symbol, detail.company || detail);}
    catch (error) {ui.detailError = error.message;}
    finally {ui.loadingDetail = false;if (ui.page === 'research') render();}
  }
  async function loadReports() {
    try {const response = await request('/api/reports');ui.reports = array(response.items);if (ui.page === 'library') render();}
    catch (error) {toast('Reports could not be loaded. ' + error.message, true);}
  }
  async function navigate(page, symbol = null) {
    ui.page = pages[page] ? page : 'today';
    if (symbol) ui.symbol = symbol;
    if (location.hash !== '#' + ui.page) history.replaceState(null, '', '#' + ui.page);
    closeMenu();render();window.scrollTo({top:0, behavior:'instant'});$('#main').focus({preventScroll:true});
    if (ui.page === 'research') await loadCompany(ui.symbol);
    if (ui.page === 'library') await loadReports();
    if (ui.page === 'lab') await loadLab(symbol || ui.lab.symbol || preferredLabSymbol());
  }
  function tour() {
    return ui.tourVisible ? '<div class="tour-strip"><span class="tour-icon" aria-hidden="true">01</span><div><strong>Your first useful research loop</strong><p>Read a thesis, replay an update, then review what changed.</p></div>' + button('Take the 3-step tour', 'onboarding', '', 'subtle') + '<button type="button" class="icon-button" data-action="dismiss-tour" aria-label="Dismiss tour prompt">×</button></div>' : '';
  }
  function renderToday() {
    const state = ui.state, overview = state.overview || {}, watched = companies().filter(company => company.watched);
    const pending = overview.status === 'data_pending' || (overview.data_gaps || 0) > 0;
    const needsReview = overview.status === 'review_required' || (overview.review_required || 0) > 0;
    const paused = state.settings?.paused || state.meta?.paused;
    const baselineReady = companies().length > 0 && array(state.events).length === 0;
    const title = !companies().length ? 'No company inputs loaded' : pending ? 'Source gaps need verification' : needsReview ? 'Operating assumptions need review' : paused ? 'Monitoring paused' : baselineReady ? 'Baseline loaded' : 'No material change in the saved check';
    const reason = !companies().length ? 'Import a sourced company packet to start a thesis.' : pending ? 'Inspect the affected source before using its conclusion.' : needsReview ? 'Compare the update with the accepted model before revising assumptions.' : paused ? 'Read saved research, or resume from Monitor & Timeline.' : baselineReady ? 'Read an accepted thesis, then replay an update to compare assumptions.' : 'Review the next dated update when it is available.';
    const attention = alerts().filter(alert => alert.review_state !== 'reviewed').slice(0,3);
    const exe = companies().find(company => company.symbol === 'EXE');
    const companyNeeds = watched.filter(company => company.thesis_status === 'review_required');
    const priority = attention.length ? attention.map(priorityCard).join('') : companyNeeds.length ? companyNeeds.slice(0,3).map(priorityCompany).join('') : '';
    const metric = (label, value, warning = false) => '<div class="metric' + (warning ? ' warning' : '') + '"><span>' + e(label) + '</span><strong>' + e(value) + '</strong></div>';
    return heading('Research desk', 'Review saved evidence, open a thesis, or compare the next update.', isSynthetic() ? button('Replay next update', 'replay-next', '', 'primary', 'replay') : button('Open company research', 'navigate', 'data-page="research"', 'primary', 'search'), 'SAVED WORKSPACE / ' + date(state.meta?.as_of, true)) +
      '<div class="verdict"><div class="verdict-symbol">' + icon(pending ? 'warning' : needsReview ? 'chart' : paused ? 'pause' : 'check') + '</div><div class="verdict-copy"><h2>' + e(title) + '</h2><p>' + e(reason) + '</p></div><div class="verdict-side"><span class="eyebrow">LAST SAVED CHECK</span><strong>' + e(date(overview.last_checked || state.meta?.updated_at,true)) + '</strong><small>' + (isSynthetic() ? 'Synthetic evidence' : 'Saved evidence') + '</small></div></div>' +
      '<div class="metrics-grid">' + metric('Companies followed', overview.watched ?? watched.length) + metric('Review required', overview.review_required ?? companyNeeds.length, needsReview) + metric('Unread alerts', overview.unread_alerts ?? attention.length) + metric('Source gaps', overview.data_gaps ?? 0, pending) + '</div>' +
      (exe ? '<section class="lab-entry"><span class="lab-entry-icon">' + icon('chart') + '</span><div><span class="eyebrow">EXE / PUBLIC-SOURCE CASE</span><h2>Test the gas-to-cash-flow bridge</h2><p>Change an educational assumption, trace the value effect, then run a saved evidence review.</p></div>' + button('Open EXE Research Lab', 'lab-open', 'data-symbol="EXE"', '', 'arrow') + '</section>' : '') +
      (priority ? '<section class="section">' + sectionHeading('Priority review', '', button('All alerts', 'navigate', 'data-page="alerts"', 'subtle', 'arrow')) + '<div class="priority-list">' + priority + '</div></section>' : '') +
      '<section class="section">' + sectionHeading('Watchlist', 'Saved prices and conditional model values.', button('Manage tracking', 'navigate', 'data-page="monitor"', 'subtle', 'arrow')) + (watched.length ? watchTable(watched) : emptyState('No companies followed', 'Open an imported company and choose a tracking tier in Monitor & Timeline.', 'Open company research', 'research')) + '</section>' +
      '<div class="today-grid"><section>' + sectionHeading('Recent material changes', 'Dated updates in the saved timeline.', button('Research methods', 'navigate', 'data-page="library"', 'subtle', 'arrow')) + '<div class="panel timeline-list">' + renderTimeline(array(state.events).slice(0,3)) + '</div></section><section class="evidence-section">' + sectionHeading('Evidence status') + '<div class="evidence-card"><div class="mini-status-list"><div><span>Inputs</span><strong>' + (isSynthetic() ? 'Synthetic snapshots' : 'Local saved inputs') + '</strong></div><div><span>Monitoring</span><strong>' + (paused ? 'Paused' : isSynthetic() ? 'Manual replay' : 'User controlled') + '</strong></div><div><span>External email</span><strong>Preview only in this UI</strong></div></div><p class="card-footnote">Browsing does not fetch live data or send email.</p></div></section></div>';
  }
  function priorityCard(alert, index) {
    const company = companies().find(item => item.symbol === alert.symbol) || {symbol: alert.symbol};
    return '<article class="priority-card">' + logo(company,index) + '<div class="priority-body"><div class="card-kicker"><strong>' + e(alert.symbol) + '</strong><span>·</span>' + alertBadge(alert) + '</div><h3>' + e(alert.title) + '</h3><p>' + e(alert.reason) + '</p><div class="card-bottom"><small>' + e(date(alert.occurred_at,true)) + ' · ' + e(human(alert.severity)) + ' materiality</small>' + button('Review update', 'open-alert', 'data-id="' + e(alert.id) + '"', 'subtle', 'arrow') + '</div></div></article>';
  }
  function priorityCompany(company, index) {
    return '<article class="priority-card">' + logo(company,index) + '<div class="priority-body"><div class="card-kicker"><strong>' + e(company.symbol) + '</strong>' + thesisBadge(company) + '</div><h3>Revisit the operating assumptions</h3><p>' + e(company.latest_change?.summary || 'A saved update affects this company thesis. Compare the evidence and the candidate model.') + '</p><div class="card-bottom">' + button('Open company desk', 'company', 'data-symbol="' + e(company.symbol) + '"', 'subtle', 'arrow') + '</div></div></article>';
  }
  function sparkline(company, index) {
    const values = array(ui.details.get(company.symbol)?.prices || company.prices).map(point => number(typeof point === 'number' ? point : point.close ?? point.price)).filter(value => value !== null);
    if (values.length < 2) return '<span class="muted" style="font-size:12px">Dated snapshot</span>';
    const min = Math.min(...values), max = Math.max(...values), points = values.map((value, position) => (position / (values.length - 1) * 80 + 1).toFixed(1) + ',' + (24 - (value-min)/(max-min || 1)*21).toFixed(1)).join(' ');
    return '<svg class="sparkline" viewBox="0 0 82 28" role="img" aria-label="Saved synthetic price history"><polyline points="' + points + '" fill="none" stroke="' + (index % 2 ? '#7b91a3' : '#609985') + '" stroke-width="1.4"/></svg>';
  }
  function watchTable(items, editable = false) {
    return '<div class="panel"><div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="research-table"><thead><tr><th>Company</th><th>Thesis</th><th>Saved price</th><th class="value-col">Base value</th><th class="technical-col">Technical</th><th class="' + (editable ? '' : 'tier-col') + '">Tracking</th>' + (editable ? '<th>Follow</th>' : '<th class="spark-col">History</th>') + '</tr></thead><tbody>' + items.map((company,index) => {
      const valuation = selectedValuation(company), base = baseValue(valuation), tech = company.technical || {};
      return '<tr><td><div class="company-cell">' + logo(company,index) + '<button type="button" data-action="company" data-symbol="' + e(company.symbol) + '"><strong>' + e(company.symbol) + '</strong><small>' + e(company.name) + '</small></button></div></td><td>' + thesisBadge(company) + '</td><td class="numeric">' + e(money(company.price)) + '<small class="value-date">' + e(date(company.price_as_of,true)) + ' · USD/share</small></td><td class="numeric value-col">' + (validModel(valuation) ? e(money(base)) : '<span class="muted" style="font-size:12px">Model unavailable</span>') + '<small class="value-date">' + e(human(valuation.state || 'pending')) + ' · ' + e(date(company.as_of,true)) + '</small></td><td class="technical-col"><span class="muted" style="font-size:12px">' + e(human(tech.trend || tech.state || 'Unavailable')) + '</span><small class="value-date">' + e(date(tech.as_of,true)) + '</small></td><td class="' + (editable ? '' : 'tier-col') + '">' + (editable ? '<label class="visually-hidden" for="tier-' + e(company.symbol) + '">Tracking tier for ' + e(company.symbol) + '</label><select class="watch-choice" id="tier-' + e(company.symbol) + '" data-watch-symbol="' + e(company.symbol) + '">' + ['focused','observe','discover'].map(tier => '<option value="' + tier + '"' + (tier === company.watch_tier ? ' selected' : '') + '>' + e({focused:'Focused tracking',observe:'Observe',discover:'Discover'}[tier]) + '</option>').join('') + '</select>' : '<span class="muted" style="font-size:12px">' + e(human(company.watch_tier)) + '</span>') + '</td>' + (editable ? '<td><label class="follow-toggle"><input type="checkbox" aria-label="Follow ' + e(company.symbol) + '" data-watch-toggle="' + e(company.symbol) + '"' + (company.watched ? ' checked' : '') + '></label></td>' : '<td class="spark-col">' + sparkline(company,index) + '</td>') + '</tr>';
    }).join('') + '</tbody></table></div><div class="table-footnote">' + (isSynthetic() ? 'All companies and prices in this replay are synthetic. ' : '') + 'Scenario values are conditional model outputs in USD per share. Technical conditions describe a dated snapshot.</div></div>';
  }
  function renderTimeline(events) {
    if (!events.length) return '<div class="timeline-item"><span class="timeline-dot"></span><div><h3>No material update in the saved timeline</h3><p>The baseline remains available for your next review.</p></div></div>';
    return events.map(event => '<article class="timeline-item"><span class="timeline-dot' + (['review_required','needs_verification','failed','data_pending','coverage_degraded'].includes(event.state) ? ' warning' : '') + '"></span><div><h3>' + e(event.title || 'Research update') + '</h3><p>' + e(event.symbol || '') + (event.symbol ? ' · ' : '') + e(event.summary || human(event.state || 'Saved event')) + '</p></div><time datetime="' + e(event.published_at || event.at) + '">' + e(date(event.published_at || event.at,true)) + '</time></article>').join('');
  }
  function emptyState(title, description, action = '', page = '') {
    return '<div class="empty-state"><span class="empty-icon">' + icon('book') + '</span><h2>' + e(title) + '</h2><p>' + e(description) + '</p>' + (action ? '<div class="action-row">' + button(action, 'navigate', 'data-page="' + e(page) + '"', 'primary', 'arrow') + '</div>' : '') + '</div>';
  }
  const preferredLabSymbol = () => companies().find(company => company.symbol === 'EXE')?.symbol || ui.symbol || companies()[0]?.symbol;
  const labParameters = () => array(ui.lab.parameters).filter(item => /^[a-z_][a-z0-9_]*$/i.test(item.key) && number(item.value) !== null);
  const labParameterValue = (value, parameter) => /fraction|ratio/.test(parameter?.unit || '') ? percent(value,1) : num(value,3);
  function labFirstYear(valuation) {
    const base = scenarios(valuation).find(item => String(item.name).toLowerCase() === 'base') || {};
    return array(base.forecast || base.cash_flows)[0] || {};
  }
  function labPipeline(which) {
    const data = ui.lab.data || {}, valuation = data[which] || (which === 'candidate' ? data.baseline : {});
    const row = labFirstYear(valuation), supplied = data.pipeline?.[which] || {};
    const production = labParameters().find(item => item.key === 'annual_production');
    return {
      production: supplied.production ?? row.production ?? (which === 'candidate' ? ui.lab.values.annual_production : production?.value),
      revenue: supplied.revenue ?? row.revenue, cash_cost: supplied.cash_cost ?? row.cash_cost ?? row.cash_operating_cost,
      capex: supplied.capex ?? row.capex, fcff: supplied.fcff ?? row.fcff ?? row.free_cash_flow,
      value: supplied.value ?? baseValue(valuation), year: supplied.year ?? row.year
    };
  }
  async function loadLab(symbol, force = false) {
    const lab = ui.lab;
    if (!symbol || (!force && lab.symbol === symbol && (lab.data || lab.loading))) return;
    clearTimeout(lab.timer);
    const revision = ++lab.revision;
    Object.assign(lab, {symbol, data:null, parameters:[], values:{}, loading:true, error:'', calculationError:'', dirty:false, queued:false, run:null, runError:'', verification:null});
    render();
    try {
      const data = await request('/api/company/' + encodeURIComponent(symbol) + '/lab');
      if (revision !== lab.revision || symbol !== lab.symbol) return;
      lab.data = data;
      lab.parameters = array(data.parameters).map(item => ({...item}));
      lab.values = Object.fromEntries(labParameters().map(item => [item.key,Number(item.value)]));
    } catch (error) {if (revision === lab.revision) lab.error = error.message;}
    finally {if (revision === lab.revision) {lab.loading=false;if (ui.page === 'lab') render();}}
    await loadLabRuns();
  }
  async function loadLabRuns() {
    try {const response = await request('/api/runs');ui.lab.runs=array(response.runs);ui.lab.runsSkipped=Number(response.skipped) || 0;ui.lab.runsError='';}
    catch (error) {ui.lab.runsError=error.message;}
    if (ui.page === 'lab') render();
  }
  function updateLabOutputs() {
    const region = $('#lab-results');
    if (ui.page !== 'lab' || !region) return;
    region.innerHTML=renderLabResults();
    region.setAttribute('aria-busy', String(ui.lab.dirty || ui.lab.inFlight));
    updateTableCues(region);
    const limitations=$('#lab-limit-details');
    if (limitations) limitations.innerHTML=bulletList(labLimitations(), 'No limitations are attached. Confirm input and model coverage before using the output.');
    const reset = $('[data-action="lab-reset"]');
    if (reset) reset.disabled=ui.busy || !labParameters().some(item => ui.lab.values[item.key] !== Number(item.value));
  }
  function scheduleLabCalculation() {
    const lab=ui.lab;
    clearTimeout(lab.timer);lab.revision++;lab.dirty=true;lab.calculationError='';
    updateLabOutputs();
    lab.timer=setTimeout(calculateLab,300);
  }
  async function calculateLab() {
    const lab=ui.lab;
    if (!lab.data || lab.loading) return;
    if (lab.inFlight) {lab.queued=true;return;}
    const symbol=lab.symbol, revision=lab.revision;
    const overrides=Object.fromEntries(labParameters().filter(item => lab.values[item.key] !== Number(item.value)).map(item => [item.key,lab.values[item.key]]));
    lab.inFlight=true;lab.queued=false;updateLabOutputs();
    try {
      const data=await request('/api/company/' + encodeURIComponent(symbol) + '/lab', {method:'POST',body:JSON.stringify({overrides})});
      if (symbol === lab.symbol && revision === lab.revision) {lab.data=data;lab.dirty=false;lab.calculationError='';}
    } catch (error) {if (symbol === lab.symbol && revision === lab.revision) {lab.calculationError=error.message;lab.dirty=false;}}
    finally {
      lab.inFlight=false;updateLabOutputs();
      if (lab.queued || (lab.dirty && revision !== lab.revision)) {lab.queued=false;clearTimeout(lab.timer);lab.timer=setTimeout(calculateLab,100);}
    }
  }
  function labControl(parameter) {
    const id='lab-' + parameter.key, value=ui.lab.values[parameter.key], fractional=/fraction|ratio/.test(parameter.unit || '');
    const unit=fractional ? 'decimal fraction' : parameter.unit;
    return '<div class="lab-control"><div class="lab-control-heading"><label for="' + id + '">' + e(parameter.label || human(parameter.key)) + '</label><output id="' + id + '-display" for="' + id + ' ' + id + '-number">' + e(labParameterValue(value,parameter)) + '</output></div><small id="' + id + '-unit">' + e(unit) + '</small><div class="lab-control-inputs"><input id="' + id + '" type="range" data-lab-parameter="' + e(parameter.key) + '" min="' + e(parameter.min) + '" max="' + e(parameter.max) + '" step="' + e(parameter.step || 'any') + '" value="' + e(value) + '" aria-describedby="' + id + '-unit" aria-valuetext="' + e(labParameterValue(value,parameter) + ' ' + (fractional ? '' : unit)) + '"><input id="' + id + '-number" type="number" data-lab-parameter="' + e(parameter.key) + '" min="' + e(parameter.min) + '" max="' + e(parameter.max) + '" step="' + e(parameter.step || 'any') + '" value="' + e(value) + '" aria-label="' + e(parameter.label || human(parameter.key)) + ' exact value" aria-describedby="' + id + '-unit"></div><div class="lab-control-bounds"><span>' + e(labParameterValue(parameter.min,parameter)) + '</span><span>Baseline ' + e(labParameterValue(parameter.value,parameter)) + '</span><span>' + e(labParameterValue(parameter.max,parameter)) + '</span></div></div>';
  }
  function labLimitations() {
    const data=ui.lab.data || {};
    return Array.from(new Set([...array(data.limitations), ...array(data.candidate?.data_gaps || data.baseline?.data_gaps)].map(textOf)));
  }
  function renderLab() {
    const lab=ui.lab, data=lab.data, company=companies().find(item => item.symbol === lab.symbol);
    const intro=heading('Research Lab', 'Trace an operating assumption through cash flow, per-share value, and a source-linked review.', '', 'OFFLINE RESEARCH WORKFLOW') +
      '<div class="lab-case-bar"><div><span class="eyebrow">PUBLIC-SOURCE CASE</span><strong>' + e(company?.name || lab.symbol || 'Choose a company') + '</strong></div><label for="lab-symbol">Case<select id="lab-symbol">' + companies().map(item => '<option value="' + e(item.symbol) + '"' + (item.symbol === (lab.symbol || preferredLabSymbol()) ? ' selected' : '') + '>' + e(item.symbol) + ' · ' + e(item.name) + '</option>').join('') + '</select></label>' + badge('Offline research workflow','neutral') + '</div>';
    if (lab.loading) return intro + '<div class="panel panel-padding" role="status"><h2>Opening the research case</h2><p class="small-note">Loading saved public-source evidence and model assumptions.</p></div>';
    if (lab.error) return intro + unavailable('This research case could not be opened.', lab.error) + '<div class="action-row lab-error-actions">' + button('Try this case again','lab-reload','','','replay') + '</div>';
    if (!data) return intro + unavailable('No Research Lab case is loaded.', 'Choose an imported company. A supported operating model and a public-source packet are required.');
    const parameters=labParameters(), primary=['annual_production','realized_price','cash_cost','annual_capex'];
    const main=parameters.filter(item => primary.includes(item.key)), advanced=parameters.filter(item => !primary.includes(item.key));
    const cutoff=data.cutoff || data.baseline?.as_of || company?.as_of;
    return intro + '<div class="lab-context"><span>' + e(data.case_label || 'Saved public-source research case') + '</span><p>Historical source facts' + (cutoff ? ' · model cutoff ' + e(date(cutoff,true)) : '') + '. Forward parameters are educational assumptions. A current market quote is not supplied.</p>' + (lab.symbol === 'EXE' ? '<p class="lab-comparability">2024 includes only a partial year of the Southwestern merger contribution. Reported growth is not organic growth.</p>' : '') + '</div>' + renderSECStatus() +
      '<div class="lab-workbench"><section class="panel lab-assumptions" aria-labelledby="lab-assumptions-title"><div class="panel-head"><div><span class="eyebrow">01 / TEST AN ASSUMPTION</span><h2 id="lab-assumptions-title">Operating sandbox</h2></div></div><div class="lab-controls">' + (main.length ? main : parameters).map(labControl).join('') + (main.length && advanced.length ? '<details class="lab-advanced"><summary>Capital, horizon & growth assumptions</summary>' + advanced.map(labControl).join('') + '</details>' : '') + '<p class="small-note">Values recalculate after a brief pause. Changes stay in this sandbox.</p>' + button('Reset to baseline','lab-reset', parameters.some(item => lab.values[item.key] !== Number(item.value)) ? '' : 'disabled', 'subtle','replay') + '</div></section><div id="lab-results" aria-busy="' + lab.dirty + '">' + renderLabResults() + '</div></div>' +
      '<section class="section lab-review" aria-labelledby="lab-review-title"><div class="section-heading"><div><span class="eyebrow">03 / REVIEW THE EVIDENCE</span><h2 id="lab-review-title">Agent evidence review</h2><p>Run the deterministic planner on the saved case. Inspect its tools, source references, and model result.</p></div>' + button(lab.runBusy ? 'Review running…' : 'Run evidence review','lab-run',lab.runBusy ? 'disabled' : '', 'primary','play') + '</div><p class="small-note lab-review-note">This offline workflow uses saved case inputs. Sandbox changes are not submitted to the review. Suggestions require a human decision.</p>' + (lab.runError ? '<div class="lab-inline-error" role="alert">' + e(lab.runError) + '</div>' : '') + '<div class="lab-review-grid"><div id="lab-run-detail">' + renderLabRun() + '</div><aside class="panel lab-saved-runs"><div class="panel-head"><h3>Saved research runs</h3>' + button('Refresh','lab-runs','','subtle') + '</div>' + renderLabRuns() + '</aside></div></section>' +
      '<section class="section lab-evidence" aria-labelledby="lab-evidence-title">' + sectionHeading('Historical source facts', 'Reported amounts preserve their fiscal periods. They do not establish forward model inputs.') + '<div class="panel"><div class="panel-head"><h2 id="lab-evidence-title">Key reported metrics</h2><small>Historical comparison</small></div>' + labFactsComparison(data.facts) + '<details class="lab-raw-evidence"><summary>Inspect all ' + array(data.facts).length + ' source records, original units & accessions</summary>' + labFactsTable(data.facts) + '</details></div></section>' +
      '<section class="panel panel-padding lab-limits"><span class="eyebrow">MODEL LIMITATIONS</span><h2>Keep the missing bridge visible</h2><div id="lab-limit-details">' + bulletList(labLimitations(), 'No limitations are attached. Confirm input and model coverage before using the output.') + '</div></section>';
  }
  function renderLabResults() {
    const lab=ui.lab, data=lab.data || {}, baseline=baseValue(data.baseline), candidate=baseValue(data.candidate || data.baseline);
    const pending=lab.dirty, failed=!!lab.calculationError, changed=labParameters().filter(item => lab.values[item.key] !== Number(item.value));
    const delta=number(candidate) !== null && number(baseline) !== null ? candidate-baseline : null;
    const status=pending ? 'Recalculating the sandbox…' : failed ? 'Calculation failed. Displayed outputs are from the last successful calculation.' : changed.length ? changed.length + ' sandbox assumption' + (changed.length === 1 ? '' : 's') + ' changed. Baseline remains saved.' : 'Baseline assumptions. Move a slider to inspect the economic effect.';
    const b=labPipeline('baseline'), c=labPipeline('candidate');
    const pipeline=[['production','Production','million Mcfe/year'],['revenue','Revenue','USD millions'],['cash_cost','Cash cost','USD millions'],['capex','Capex','USD millions'],['fcff','FCFF','USD millions']];
    const pipelineValue=(value,key) => number(value) === null ? 'Unavailable' : (key === 'production' ? num(value,0) : money(value,0));
    return '<section class="panel lab-value"><div class="panel-head"><div><span class="eyebrow">02 / FOLLOW THE CASH FLOW</span><h2>Conditional per-share value</h2></div>' + badge('Educational model','neutral') + '</div><div class="lab-value-body"><div class="lab-value-comparison"><div><span>Saved baseline</span><strong>' + e(money(baseline)) + '</strong><small>USD/share</small></div><span class="lab-value-arrow" aria-hidden="true">→</span><div class="lab-candidate-value"><span>Sandbox result</span><strong>' + e(pending ? 'Pending' : money(candidate)) + '</strong><small>USD/share</small></div><div class="lab-value-delta"><span>Value change</span><strong>' + e(pending ? 'Pending' : delta === null ? 'Unavailable' : (delta > 0 ? '+' : delta < 0 ? '−' : '') + money(Math.abs(delta))) + '</strong><small>Conditional effect</small></div></div><p class="lab-calculation-status" role="status">' + e(status) + '</p>' + (failed ? '<div class="lab-inline-error" role="alert">' + e(lab.calculationError) + ' ' + button('Retry calculation','lab-calculate','','subtle') + '</div>' : '') + '</div><div class="lab-pipeline">' + pipeline.map(([key,label,unit]) => '<div><span>' + label + '</span><strong>' + e(pending ? 'Pending' : pipelineValue(c[key],key)) + '</strong><small>' + unit + '</small><small>Baseline ' + e(pipelineValue(b[key],key)) + '</small></div>').join('') + '</div><p class="table-footnote">First forecast year' + (c.year ? ' · ' + e(c.year) : '') + '. FCFF is cash flow to the firm after modeled tax and reinvestment. Net debt and diluted shares complete the per-share bridge.</p>' + labBridgeTable(data.baseline,data.candidate || data.baseline,pending) + '</section><section class="panel lab-sensitivity"><div class="panel-head"><h2>One-assumption sensitivity</h2><small>USD/share</small></div>' + (pending ? '<div class="panel-padding"><p class="small-note">The curve will update with the latest sandbox inputs.</p></div>' : renderLabCurve()) + '</section>';
  }
  function labBridgeTable(baseline,candidate,pending) {
    const base=valuation => scenarios(valuation).find(item => String(item.name).toLowerCase() === 'base') || {};
    const b=base(baseline), c=base(candidate);
    return '<details class="lab-bridge"><summary>Inspect the enterprise-to-equity bridge</summary><div class="table-scroll" tabindex="0" role="region"><table class="mini-table"><caption class="visually-hidden">Baseline and sandbox value bridge in millions</caption><thead><tr><th>Value bridge</th><th>Baseline</th><th>Sandbox</th></tr></thead><tbody>' + [['Enterprise value','enterprise_value','USD millions'],['Equity value','equity_value','USD millions'],[ui.lab.symbol === 'EXE' ? 'Annual weighted diluted EPS share proxy' : 'Diluted shares','shares','millions']].map(([label,key,unit]) => '<tr><th scope="row">' + label + '<small>' + unit + '</small></th><td>' + e(num(b[key],1)) + '</td><td>' + e(pending ? 'Pending' : num(c[key],1)) + '</td></tr>').join('') + '</tbody></table></div>' + (ui.lab.symbol === 'EXE' ? '<p class="table-footnote">The annual EPS share proxy is not a current fully diluted share count.</p>' : '') + '</details>';
  }
  function renderLabCurve() {
    const data=ui.lab.data || {}, key=typeof data.parameter === 'object' ? data.parameter.key : data.parameter || 'realized_price';
    const parameter=labParameters().find(item => item.key === key) || {label:human(key),unit:''};
    const curve=array(data.curve), points=curve.map(item => ({x:number(item.input ?? item.value),y:number(item.per_share_value),state:item.state}));
    const valid=points.filter(item => item.x !== null && item.y !== null && !['unavailable','unsupported'].includes(item.state));
    const description='Only ' + (parameter.label || human(key)).toLowerCase() + ' varies. Other sandbox inputs stay fixed. Values are conditional model outputs.';
    if (valid.length < 2) return '<div class="panel-padding">' + unavailable('A sensitivity curve is not available.', 'The model needs at least two supported values for this assumption.') + '</div>' + (curve.length ? labCurveTable(curve,parameter) : '');
    const minX=Math.min(...valid.map(item => item.x)), maxX=Math.max(...valid.map(item => item.x)), minY=Math.min(...valid.map(item => item.y)), maxY=Math.max(...valid.map(item => item.y));
    const spanY=maxY-minY || Math.max(Math.abs(maxY)*.1,1), low=minY-spanY*.12, high=maxY+spanY*.12;
    const x=value => 60+(value-minX)/(maxX-minX || 1)*510, y=value => 195-(value-low)/(high-low)*155;
    const grid=[0,1,2,3].map(index => {const value=low+(high-low)*index/3;return '<line x1="60" x2="570" y1="' + y(value).toFixed(1) + '" y2="' + y(value).toFixed(1) + '" stroke="#e2e4df"/><text x="48" y="' + (y(value)+4).toFixed(1) + '" text-anchor="end" class="chart-label">' + e(money(value,0)) + '</text>';}).join('');
    let start=true;
    const path=points.map(item => {if (item.x === null || item.y === null || ['unavailable','unsupported'].includes(item.state)) {start=true;return '';}const part=(start ? 'M' : 'L') + x(item.x).toFixed(1) + ',' + y(item.y).toFixed(1);start=false;return part;}).join(' ');
    const currentX=number(ui.lab.values[key]), currentY=baseValue(data.candidate || data.baseline);
    const selected=currentX !== null && currentY !== null && currentX >= minX && currentX <= maxX ? {x:currentX,y:currentY} : null;
    const labels=[minX,(minX+maxX)/2,maxX].map(value => '<text x="' + x(value).toFixed(1) + '" y="220" text-anchor="middle" class="chart-label">' + e(labParameterValue(value,parameter)) + '</text>').join('');
    return '<div class="lab-curve chart-wrap"><svg viewBox="0 0 620 242" role="img" aria-labelledby="lab-curve-title lab-curve-desc"><title id="lab-curve-title">' + e(parameter.label) + ' sensitivity</title><desc id="lab-curve-desc">' + e(description + ' Exact values are in the data table below.') + '</desc>' + grid + '<path d="' + path + '" fill="none" stroke="#117c71" stroke-width="3"/>' + (selected ? '<circle cx="' + x(selected.x).toFixed(1) + '" cy="' + y(selected.y).toFixed(1) + '" r="5" fill="#101927" stroke="#fff" stroke-width="2"/>' : '') + labels + '</svg><div class="chart-legend"><span><i class="legend-dot"></i>' + e(parameter.label + (parameter.unit ? ' · ' + parameter.unit : '')) + '</span>' + (selected ? '<span><i class="legend-dot lab-selected-dot"></i>Current sandbox input</span>' : '') + '</div><p class="chart-caption">' + e(description) + '</p></div><details class="lab-curve-data"><summary>View the sensitivity data table</summary>' + labCurveTable(curve,parameter) + '</details>';
  }
  function labCurveTable(curve,parameter) {
    return '<div class="table-scroll" tabindex="0" role="region"><table class="mini-table"><caption class="visually-hidden">Sensitivity data for ' + e(parameter.label) + '</caption><thead><tr><th>' + e(parameter.label) + '</th><th>Value (USD/share)</th><th>Model state</th></tr></thead><tbody>' + curve.map(item => '<tr><td>' + e(labParameterValue(item.input ?? item.value,parameter)) + '</td><td>' + e(money(item.per_share_value)) + '</td><td>' + e(human(item.state || 'Not supplied')) + '</td></tr>').join('') + '</tbody></table></div>';
  }
  function labFactLinks(ids) {
    const facts=array(ui.lab.data?.facts);
    return array(ids).map(id => {const fact=facts.find(item => item.id === id), url=safeUrl(fact?.url || fact?.source_url);return url ? '<a href="' + e(url) + '" target="_blank" rel="noopener noreferrer">' + e(id) + ' ↗</a>' : '<span>' + e(id) + '</span>';}).join(', ');
  }
  const labMetricLabels = {production:'Annual production', capex:'Cash capital expenditures', cfo:'Cash from operations (CFO)', revenue:'Total revenues and other', cash:'Cash and cash equivalents', debt:'Debt including current maturities', diluted_shares:'Annual weighted diluted EPS shares', proved_reserves:'Proved reserves at year end', production_revenue:'Revenue from producing activities', debt_current:'Current debt maturities', debt_noncurrent:'Noncurrent debt', basic_shares:'Annual weighted basic EPS shares', issued_shares:'Year-end issued shares', common_outstanding_shares:'Cover-page common shares outstanding', production_cost:'Production and lifting expense', transportation_cost:'Gathering, processing and transportation expense', production_taxes:'Production taxes', dda:'Depreciation, depletion and amortization'};
  const labFactLabel = fact => labMetricLabels[fact.metric] || (fact.metric ? human(fact.metric) : fact.label || human(String(fact.concept || fact.id).replace(/([a-z])([A-Z])/g,'$1 $2')));
  function labFactsComparison(facts) {
    const keys=['production','capex','cfo','revenue','cash','debt','diluted_shares','proved_reserves'];
    const rows=array(facts).filter(fact => keys.includes(fact.metric));
    const years=Array.from(new Set(rows.map(fact => String(fact.end || '').slice(0,4)).filter(year => /^\d{4}$/.test(year)))).sort();
    if (!years.length) return '<div class="panel-padding"><p class="small-note">Key metrics are not available. Inspect the full source records below.</p></div>';
    const cell=(fact,label,year) => {
      if (!fact) return '<td>Unavailable</td>';
      const raw=number(fact.val ?? fact.value), amount=fact.unit === 'USD' || fact.unit === 'shares' ? raw === null ? null : raw/1000000 : raw;
      const value=fact.unit === 'USD' ? money(amount,0) : num(amount,fact.unit === 'shares' ? 3 : 0);
      const url=safeUrl(fact.url || fact.source_url);
      return '<td>' + (url ? '<a href="' + e(url) + '" target="_blank" rel="noopener noreferrer" aria-label="' + e(label + ', ' + year + ', ' + value + '. Open source filing.') + '">' + e(value) + ' <span aria-hidden="true">↗</span></a>' : e(value)) + '</td>';
    };
    return '<div class="table-scroll" tabindex="0" role="region"><table class="mini-table lab-facts-comparison"><caption class="visually-hidden">Key historical reported metrics, with source filing links</caption><thead><tr><th>Reported metric</th>' + years.map(year => '<th>' + e(year) + '</th>').join('') + '</tr></thead><tbody>' + keys.map(key => {
      const selected=rows.filter(fact => fact.metric === key), sample=selected[0];if (!sample) return '';
      const unit=sample.unit === 'USD' ? 'USD millions' : sample.unit === 'shares' ? 'million shares' : sample.unit;
      const label=labMetricLabels[key];
      return '<tr><th scope="row">' + e(label) + '<small>' + e(unit) + '</small></th>' + years.map(year => cell(selected.filter(fact => String(fact.end).startsWith(year)).sort((a,b) => String(b.filed).localeCompare(String(a.filed)))[0],label,year)).join('') + '</tr>';
    }).join('') + '</tbody></table></div><p class="table-footnote">CFO includes working-capital changes. Annual EPS shares are a weighted share proxy. Proved reserves do not establish a production horizon.</p>';
  }
  function labFactsTable(facts) {
    if (!array(facts).length) return '<div class="panel-padding">' + unavailable('Source facts are not attached.', 'An educational assumption does not become an observed fact. Complete the source packet before relying on this case.') + '</div>';
    return '<div class="table-scroll" tabindex="0" role="region"><table class="mini-table lab-facts-table"><caption class="visually-hidden">Historical public-source facts with original units and filing dates</caption><thead><tr><th>Reported fact</th><th>Original reported value</th><th>Fiscal period</th><th>Filed</th><th>Source</th></tr></thead><tbody>' + array(facts).map(fact => {const url=safeUrl(fact.url || fact.source_url);return '<tr><th scope="row">' + e(labFactLabel(fact)) + '<small>' + e(fact.concept) + '</small><small>' + e(fact.id) + '</small></th><td>' + e(num(fact.val ?? fact.value,3)) + '<small>' + e(fact.unit) + '</small></td><td>' + e(fact.start ? date(fact.start,true) + ' to ' + date(fact.end,true) : date(fact.end,true)) + '</td><td>' + e(date(fact.filed,true)) + '</td><td>' + (url ? '<a href="' + e(url) + '" target="_blank" rel="noopener noreferrer">' + e(fact.form || 'Source') + ' ↗</a>' : 'Link unavailable') + '<small>' + e(fact.accn || 'Historical record') + '</small></td></tr>';}).join('') + '</tbody></table></div>';
  }
  function renderLabRun() {
    const lab=ui.lab, run=lab.run;
    if (!run) return '<div class="panel panel-padding lab-run-empty"><span class="eyebrow">DETERMINISTIC PLANNER</span><h3>Make the review inspectable</h3><p>Read saved evidence, recompute the model, identify gaps, and preserve a reproducible run.</p><ol><li>Tool calls carry their inputs and results.</li><li>Suggestions point back to source facts.</li><li>A saved manifest records input, code, and output hashes.</li></ol><small>No live LLM connection is required for this workflow.</small></div>';
    const output=run.output || run, manifest=run.manifest || {}, mode=run.planner_mode || manifest.planner?.mode || 'deterministic';
    const trace=array(output.trace), suggestions=array(output.suggestions), runId=run.run_id || manifest.run_id;
    const verification=lab.verification?.run_id === runId ? lab.verification : null;
    const traceHtml=trace.map((step,index) => '<details class="lab-trace-step"><summary><span class="lab-step-number">' + String(index+1).padStart(2,'0') + '</span><strong>' + e(step.tool || 'Tool call') + '</strong></summary><div class="lab-trace-body"><span class="eyebrow">ARGUMENTS</span><pre>' + e(JSON.stringify(step.arguments || {},null,2)) + '</pre><span class="eyebrow">RESULT</span><pre>' + e(JSON.stringify(step.result ?? step.output ?? {},null,2)) + '</pre></div></details>').join('');
    return '<article class="panel lab-run-panel"><div class="panel-head"><div><span class="eyebrow">' + e(/deterministic|offline/i.test(mode) ? 'DETERMINISTIC PLANNER' : human(mode)) + '</span><h3>Saved evidence review</h3></div>' + badge(human(output.status || run.status || 'Saved'),'neutral') + '</div><div class="lab-run-meta"><span>Cutoff ' + e(date(manifest.cutoff,true)) + '</span><span>' + e(runId || 'Run identifier unavailable') + '</span></div>' + (output.summary ? '<div class="lab-run-summary"><span class="eyebrow">UNVERIFIED PLANNER SUMMARY</span><p>' + e(textOf(output.summary)) + '</p></div>' : '') + '<div class="lab-run-value"><span>Python model result</span><strong>' + e(money(baseValue(output.model_result))) + '</strong><small>USD/share · saved case inputs</small></div><div class="lab-run-section"><h3>Review suggestions</h3>' + (suggestions.length ? '<div class="lab-suggestions">' + suggestions.map(item => '<article><span class="eyebrow">' + e(item.parameter ? human(item.parameter) : 'Evidence review') + '</span>' + (item.parameter ? '<div class="lab-suggestion-change">' + (typeof item.new === 'number' && Number.isFinite(item.new) ? e(num(item.old,4)) + ' → ' + e(num(item.new,4)) : 'Saved assumption: ' + e(num(item.old,4)) + '<small>Review requested. No replacement value proposed.</small>') + '</div>' : '') + '<p>' + e(item.reason || textOf(item)) + '</p>' + (array(item.evidence_ids).length ? '<div class="lab-source-links">Source facts: ' + labFactLinks(item.evidence_ids) + '</div>' : '<small>No source fact references supplied.</small>') + '<small>Human decision pending</small></article>').join('') + '</div>' : '<p class="small-note">No suggestions were returned.</p>') + (array(output.data_gaps).length ? '<h3 class="lab-gaps-title">Open research gaps</h3>' + bulletList(output.data_gaps,'') : '') + '</div><div class="lab-run-section"><h3>Tool trace</h3>' + (trace.length ? traceHtml : '<p class="small-note">No tool trace was returned.</p>') + '</div><div class="lab-run-section"><h3>Reproduce this run</h3><p class="small-note">Recompute saved inputs with the recorded runtime and compare the output hash.</p>' + (runId ? button(lab.runBusy ? 'Verification running…' : 'Verify saved run','lab-verify','data-id="' + e(runId) + '"' + (lab.runBusy ? ' disabled' : ''),'','shield') : '') + (verification ? '<p class="lab-verification ' + (verification.verified ? 'positive' : 'negative') + '" role="status">' + e(verification.verified ? 'Verified: the saved output hash matches the recomputed result.' : 'Verification failed: the saved run could not be reproduced.') + '</p>' : '') + '<details class="lab-manifest"><summary>View the run manifest</summary><pre>' + e(JSON.stringify(manifest,null,2)) + '</pre></details></div></article>';
  }
  function renderSECStatus() {
    if (isSynthetic() || !companies().some(company => company.case_id === 'exe-sec-2024-2025')) return '';
    const sec=ui.state.meta?.sec_monitor, issuer=ui.state.meta?.ir_monitor;
    if (!sec && !issuer) return '<div class="sec-check-note"><strong>Offline case</strong><span>Saved public filings are ready. No official-source network check has been recorded in this workspace.</span></div>';
    const providers=[{label:'SEC direct',status:sec},{label:'Official company site',status:issuer}];
    return providers.filter(provider => provider.status || provider.label === 'SEC direct').map(provider => {
      const status=provider.status, failed=status?.status === 'unavailable', available=status?.status === 'available';
      const title=provider.label + (failed ? ' unavailable' : available ? ' · last check succeeded' : status ? ' · check needs review' : ' · no check recorded');
      const detail=!status ? 'The company-site alternative does not establish SEC API recovery.' : status.reason || 'Saved filings and model assumptions remain available.';
      const latest=status?.latest_filing;
      const link=latest && safeUrl(latest.source_url) ? '<a href="' + e(safeUrl(latest.source_url)) + '" target="_blank" rel="noopener noreferrer">' + e(latest.form + ' · filed ' + latest.filingDate) + ' ↗</a>' : '';
      return '<div class="sec-check-note' + (failed ? ' sec-check-failed' : available ? ' sec-check-available' : '') + '" role="status"><strong>' + e(title) + '</strong><span>' + e(detail) + (failed ? ' Collection stopped. Saved assumptions remain available.' : '') + '</span>' + link + (status ? '<small>Last attempt: ' + e(datetime(status.checked_at)) + (status.last_success_at ? ' · Last success: ' + e(datetime(status.last_success_at)) : '') + '</small>' : '') + '</div>';
    }).join('');
  }
  function renderLabRuns() {
    const lab=ui.lab, runs=lab.runs.filter(run => run.symbol === lab.symbol);
    if (lab.runsError) return '<div class="panel-padding"><p class="lab-inline-error" role="alert">' + e(lab.runsError) + '</p></div>';
    const skipped=lab.runsSkipped ? '<p class="panel-padding small-note">' + e(lab.runsSkipped) + ' saved file(s) could not be validated and were omitted. Other runs remain available.</p>' : '';
    return skipped + (runs.length ? '<ul class="lab-run-list">' + runs.slice(0,12).map(run => '<li><button type="button" data-action="lab-run-open" data-id="' + e(run.run_id) + '"' + (lab.runBusy ? ' disabled' : '') + '><strong>' + e(run.symbol) + ' · ' + e(date(run.cutoff,true)) + '</strong><span>' + e(/deterministic|offline/i.test(run.planner_mode || '') ? 'Deterministic planner' : human(run.planner_mode || 'Saved workflow')) + '</span><code>' + e(run.run_id) + '</code></button></li>').join('') + '</ul>' : '<p class="panel-padding small-note">No saved runs for this case. Run an evidence review to create the first record.</p>');
  }
  async function runLabReview() {
    const lab=ui.lab;if (lab.runBusy || !lab.data) return;
    const symbol=lab.symbol;lab.runBusy=true;lab.runError='';lab.verification=null;render();
    try {
      const response=await request('/api/company/' + encodeURIComponent(symbol) + '/agent',{method:'POST',body:'{}'});
      if (symbol === lab.symbol) lab.run=response.run ? {...response.run,run_id:response.run_id || response.run.run_id} : response;
      try {setState(await request('/api/state'));render();}
      catch (error) {
        const message='The evidence review was saved, but workspace freshness could not be confirmed. ' + error.message;
        ui.connected=false;connection(message);toast(message,true);
        if (symbol === lab.symbol) lab.runError=message;
      }
      await loadLabRuns();
    }
    catch (error) {if (symbol === lab.symbol) lab.runError=error.message;toast('Evidence review failed. ' + error.message,true);}
    finally {lab.runBusy=false;if (ui.page === 'lab') render();}
  }
  async function openLabRun(id) {
    const lab=ui.lab;if (lab.runBusy) return;
    const symbol=lab.symbol;lab.runBusy=true;lab.runError='';lab.verification=null;render();
    try {const response=await request('/api/runs/' + encodeURIComponent(id));if (symbol === lab.symbol) lab.run={...(response.run || response),run_id:id};}
    catch (error) {lab.runError=error.message;}
    finally {lab.runBusy=false;if (ui.page === 'lab') render();}
  }
  async function verifyLabRun(id) {
    const lab=ui.lab;if (lab.runBusy) return;
    lab.runBusy=true;lab.runError='';render();
    try {const response=await request('/api/runs/' + encodeURIComponent(id) + '/replay',{method:'POST',body:'{}'});lab.verification={...response,run_id:id};}
    catch (error) {lab.runError='Saved-run verification failed. ' + error.message;}
    finally {lab.runBusy=false;if (ui.page === 'lab') render();}
  }

  function renderResearch() {
    const company = activeCompany();
    const content = heading('Company research', 'Inspect an imported company’s thesis, evidence, and conditional model.', company ? button('Save research report', 'research', 'data-symbol="' + e(company.symbol) + '"', 'primary', 'source') : '', 'ACCEPTED BASELINE & REVIEW') +
      '<form class="search-form" id="research-form"><label for="research-symbol">Imported symbol</label><input id="research-symbol" name="symbol" placeholder="e.g. ASTER" list="imported-symbols" autocomplete="off" maxlength="20" required aria-describedby="research-help"><datalist id="imported-symbols">' + companies().map(item => '<option value="' + e(item.symbol) + '">' + e(item.name) + '</option>').join('') + '</datalist><button type="submit" class="button">' + icon('source') + 'Open report</button></form><p class="form-note" id="research-help">Saves the current snapshot of an imported company. No ticker lookup or live data fetch.</p>' +
      '<div class="company-tabs" aria-label="Select a company">' + companies().map((item,index) => '<button type="button" class="company-tab ' + (company?.symbol === item.symbol ? 'active' : '') + '" data-action="company" data-symbol="' + e(item.symbol) + '" aria-pressed="' + (company?.symbol === item.symbol) + '">' + logo(item,index) + '<span><strong>' + e(item.symbol) + '</strong><small>' + e(item.name) + '</small></span></button>').join('') + '</div>';
    if (!company) return content + emptyState('No company inputs loaded', 'Import a sourced company packet or open the synthetic replay. Live adapters require separate setup.', 'View workspace setup', 'workspace');
    const valuation = selectedValuation(company), technical = company.technical || {}, base = baseValue(valuation), drivers = array(company.thesis?.drivers);
    const businessHeading = company.thesis_status === 'review_required' ? 'Assumptions under review' : 'Operating thesis on file';
    const valueHeading = validModel(valuation) ? money(base) + ' base value' : 'Model unavailable';
    return content + '<div class="company-heading">' + logo(company) + '<div><h2>' + e(company.name) + '</h2><p>' + e(company.symbol) + ' · ' + e(company.sector) + ' · ' + e(human(company.archetype)) + '</p></div><div class="company-price"><strong>' + e(money(company.price)) + '</strong><small>' + (isSynthetic() ? 'Synthetic price' : 'Saved price') + ' · ' + e(date(company.price_as_of,true)) + ' · USD/share</small></div></div><p class="company-description">' + e(company.description) + '</p>' +
      '<div class="pillar-grid"><article class="pillar"><div class="pillar-heading"><span class="eyebrow">BUSINESS & THESIS</span>' + thesisBadge(company) + '</div><h3>' + e(businessHeading) + '</h3><p>' + drivers.length + ' accepted operating drivers.</p><small>Sources and review conditions below.</small></article><article class="pillar"><div class="pillar-heading"><span class="eyebrow">CONDITIONAL VALUE</span>' + badge(validModel(valuation) ? 'Model available' : 'Data pending', validModel(valuation) ? 'info' : 'warning') + '</div><h3>' + e(valueHeading) + '</h3><p>' + (validModel(valuation) ? e(money(valuation.bear)) + ' bear · ' + e(money(valuation.bull)) + ' bull' : e(array(valuation.data_gaps).map(textOf).join(' ') || 'Inputs do not support a value estimate.')) + '</p><small>USD/share · model cutoff ' + e(date(company.as_of,true)) + '</small></article><article class="pillar"><div class="pillar-heading"><span class="eyebrow">TECHNICAL SNAPSHOT</span>' + badge('Dated', 'neutral') + '</div><h3>' + e(human(technical.trend || technical.state || 'Unavailable')) + '</h3><p>RSI 14: ' + e(num(technical.rsi14)) + ' · Drawdown: ' + e(percent(technical.max_drawdown)) + '</p><small>As of ' + e(date(technical.as_of,true)) + ' · descriptive</small></article></div>' +
      (company.candidate_valuation ? candidateBanner(company) : '') +
      '<div class="tabs" role="tablist" aria-label="Company research views">' + [{id:'thesis',label:'Thesis & evidence'},{id:'valuation',label:'Model & scenarios'},{id:'history',label:'Timeline & forecasts'}].map(tab => '<button type="button" role="tab" id="tab-' + tab.id + '" aria-controls="company-panel" aria-selected="' + (ui.tab === tab.id) + '" tabindex="' + (ui.tab === tab.id ? '0' : '-1') + '" class="' + (ui.tab === tab.id ? 'active' : '') + '" data-action="company-tab" data-tab="' + tab.id + '">' + tab.label + '</button>').join('') + '</div>' +
      (ui.loadingDetail ? '<p class="small-note" role="status">Loading the saved model details…</p>' : '') + (ui.detailError ? unavailable('The complete model could not be loaded.', ui.detailError + ' The saved company overview remains visible.') + '<br>' : '') +
      '<div id="company-panel" role="tabpanel" tabindex="0" aria-labelledby="tab-' + ui.tab + '">' + (ui.tab === 'valuation' ? renderValuation(company) : ui.tab === 'history' ? renderHistory(company) : renderThesis(company)) + '</div>';
  }
  function candidateBanner(company) {
    const oldValue = baseValue(company.valuation), newValue = baseValue(company.candidate_valuation);
    return '<div class="candidate-banner"><h3>A revised model is ready for your review</h3><p>The event produced a candidate set of assumptions. Your accepted baseline stays intact until you compare and accept the revision.</p><div class="comparison"><div><small>ACCEPTED BASELINE</small><strong>' + e(money(oldValue)) + '</strong></div><span class="compare-arrow" aria-hidden="true">→</span><div><small>CANDIDATE BASE VALUE</small><strong>' + e(money(newValue)) + '</strong></div></div><div class="action-row">' + button('Compare revised assumptions', 'candidate', 'data-symbol="' + e(company.symbol) + '"', 'warn', 'arrow') + '</div></div>';
  }
  function renderThesis(company) {
    const thesis = company.thesis || {}, drivers = array(thesis.drivers), evidence = array(company.evidence);
    return '<div class="detail-two-grid"><div><section class="panel panel-padding"><span class="eyebrow">THE OPERATING CASE</span><p class="thesis-statement">' + e(thesis.statement || 'No accepted thesis statement is available.') + '</p><div class="driver-grid">' + drivers.map((driver,index) => '<button type="button" class="driver" data-action="driver" data-id="' + e(driver.id) + '"><span class="driver-number">DRIVER 0' + (index+1) + '</span><h3>' + e(driver.label) + '</h3><span class="driver-value">' + valueLabel(driver.value,driver.unit) + '</span><small>' + e(driver.watch_condition || 'Review on the next material evidence update.') + '</small><span class="driver-link">Trace assumption to evidence ↗</span></button>').join('') + '</div></section><section class="panel panel-padding"><span class="eyebrow">A WAY TO BE WRONG</span><h2 style="margin-top:8px">What would invalidate this case?</h2>' + bulletList(thesis.falsifiers, 'No observable invalidation condition is recorded yet.') + '</section><section class="panel panel-padding"><span class="eyebrow">KEEP THE CHALLENGE CLOSE</span><h2 style="margin-top:8px">Strongest contrary evidence</h2>' + bulletList(thesis.counterevidence, 'No contrary evidence has been recorded. This is a research gap, not confirmation.') + '</section></div><aside><div class="next-review"><span class="eyebrow">NEXT THESIS REVIEW</span><strong>' + e(typeof thesis.next_review === 'object' ? textOf(thesis.next_review) : date(thesis.next_review,true)) + '</strong><p>Revisit earlier if a defined operating condition changes.</p></div><section class="panel"><div class="panel-head"><h2>Evidence notebook</h2><small>' + evidence.length + ' saved sources</small></div>' + (evidence.length ? evidence.map(sourceCard).join('') : '<div class="panel-padding small-note">No source records have been attached yet.</div>') + '</section></aside></div>';
  }
  function bulletList(items, empty) {
    return array(items).length ? '<ul class="list-clean">' + array(items).map(item => '<li>' + e(textOf(item)) + '</li>').join('') + '</ul>' : '<p class="small-note" style="margin-top:12px">' + e(empty) + '</p>';
  }
  function sourceCard(source) {
    return '<article class="source-card"><div class="source-title"><span>' + e(source.title || source.source || source.id || 'Evidence record') + '</span>' + button('↗', 'evidence', 'data-id="' + e(source.id) + '" aria-label="Open evidence record ' + e(source.title || source.id) + '"', 'subtle') + '</div><p>' + e(source.claim || source.content || source.summary || source.description || source.locator || 'A dated input preserved with its evidence context.') + '</p><div class="source-meta"><span>' + e(date(source.published_at || source.publication_time || source.as_of,true)) + '</span><span>' + e(source.unit || source.period || source.source_type || (isSynthetic() ? 'Synthetic evidence' : 'Saved source')) + '</span>' + (source.verification ? '<span>' + e(human(source.verification)) + '</span>' : '') + '</div></article>';
  }
  function renderValuation(company) {
    const valuation = company.valuation || {};
    if (!validModel(valuation)) return unavailable('This model is not available.', array(valuation.data_gaps).map(textOf).join(' ') || 'This company archetype does not have the decisive inputs needed for a supported valuation. Complete the research inputs before treating a value as usable.') + '<div style="margin-top:22px">' + renderTechnical(company) + '</div>';
    const present = scenarios(valuation);
    const cases = ['Bear','Base','Bull'].map(name => present.find(item => String(item.name).toLowerCase() === name.toLowerCase()) || {name, state:'unavailable', notes:array(valuation.data_gaps).filter(item => textOf(item).toLowerCase().startsWith(name.toLowerCase()))});
    const sensitivity = valuation.sensitivity || company.sensitivity;
    return '<div class="scenario-grid">' + cases.map(scenario => '<article class="scenario-card ' + (String(scenario.name).toLowerCase() === 'base' ? 'base' : '') + '"><span class="eyebrow">' + e(scenario.name) + ' SCENARIO</span><strong>' + e(money(scenarioValue(scenario))) + '</strong><small>USD per diluted share</small><p>' + e(scenario.state === 'unavailable' ? 'This scenario needs an identified funding or operating bridge.' : String(scenario.name).toLowerCase() === 'base' ? 'The accepted operating assumptions.' : 'Conditional operating and capital assumptions.') + '</p><details><summary>Assumptions and limits</summary><p>' + e(textOf(scenario.notes)) + '</p></details></article>').join('') + '</div>' +
      '<div class="detail-two-grid"><div><section class="panel" style="margin-bottom:21px"><div class="panel-head"><h2>From operating drivers to cash flow</h2><small>Accepted model</small></div>' + forecastChart(cases) + forecastTable(cases) + '</section><section class="panel panel-padding"><span class="eyebrow">RECONCILE THE PER-SHARE BRIDGE</span>' + valueBridge(cases) + '</section><section class="panel"><div class="panel-head"><h2>Sensitivity to the assumptions</h2><small>Conditional values</small></div>' + renderSensitivity(sensitivity) + '</section><section class="panel panel-padding"><span class="eyebrow">MODEL LIMITATIONS</span><h2 style="margin-top:10px">Available does not mean complete.</h2>' + bulletList(valuation.data_gaps, 'No limitations have been attached. Verify model coverage before relying on the output.') + '</section></div><aside><section class="panel panel-padding"><span class="eyebrow">REVERSE EXPECTATIONS</span><h2 style="margin-top:10px">What does this price require?</h2>' + reverseBlock(valuation.reverse || company.reverse, company.price) + '</section><section class="panel panel-padding"><span class="eyebrow">SECOND METHOD</span><h2 style="margin-top:10px">Cross-check the conclusion</h2>' + crossCheckBlock(valuation.cross_check || company.cross_check) + '</section><section class="panel panel-padding"><span class="eyebrow">ACCEPTED INPUTS</span>' + assumptionsBlock(company.assumptions || valuation.assumptions) + '</section>' + renderTechnical(company) + '</aside></div>';
  }
  function forecastRows(cases) {
    const scenario = cases.find(item => String(item.name).toLowerCase() === 'base') || cases[0] || {};
    return array(scenario.forecast || scenario.cash_flows);
  }
  function forecastChart(cases) {
    const forecast = forecastRows(cases), values = forecast.map(row => number(row.free_cash_flow ?? row.fcff ?? row.fcf ?? row.cash_flow));
    if (!forecast.length || values.some(value => value === null)) return '<div class="panel-padding">' + unavailable('Cash-flow detail is pending.', 'The value range is available, but a yearly cash-flow series has not been supplied.') + '</div>';
    const w = 620, h = 225, padding = 45, max = Math.max(...values,0), min = Math.min(...values,0), span = max-min || 1;
    const y = value => 180-(value-min)/span*145, barWidth = Math.min(40,420/values.length), step = 500/values.length;
    const grid = [0,1,2,3].map(index => {const value = min+span*index/3;return '<line x1="45" y1="' + y(value).toFixed(1) + '" x2="600" y2="' + y(value).toFixed(1) + '" stroke="#e8ede3" stroke-dasharray="3 4"/><text x="33" y="' + (y(value)+3).toFixed(1) + '" text-anchor="end" class="chart-label">' + e(num(value,0)) + '</text>';}).join('');
    const bars = values.map((value,index) => {const x = padding+24+step*index, zero = y(0), top = Math.min(y(value),zero), height = Math.max(2,Math.abs(zero-y(value)));return '<rect x="' + x.toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + barWidth + '" height="' + height.toFixed(1) + '" fill="' + (index === values.length-1 ? '#117c71' : '#b9d9c4') + '" rx="3"/><text x="' + (x+barWidth/2).toFixed(1) + '" y="205" text-anchor="middle" class="chart-label">' + e(forecast[index].year || forecast[index].period || ('Y'+(index+1))) + '</text>';}).join('');
    return '<div class="chart-wrap"><svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="Base scenario yearly free cash flow, in USD millions">' + grid + bars + '</svg><div class="chart-legend"><span><i class="legend-dot"></i>Base scenario free cash flow</span></div><p class="chart-caption">USD millions. Growth includes reinvestment and working-capital needs. The forecast is conditional, not an observed outcome.</p></div>';
  }
  function forecastTable(cases) {
    const rows = forecastRows(cases);
    if (!rows.length) return '';
    const keys = [{key:'year',label:'Year'}, {key:'revenue',label:'Revenue'}, {key:'operating_profit',label:'Operating profit'}, {key:'capex',label:'Capex'}, {key:'working_capital_change',label:'Working capital'}, {key:'free_cash_flow',label:'Free cash flow'}];
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="mini-table"><thead><tr>' + keys.map(item => '<th>' + item.label + '</th>').join('') + '</tr></thead><tbody>' + rows.map(row => '<tr>' + keys.map(item => '<td>' + (item.key === 'year' ? e(row.year || row.period) : e(num(row[item.key] ?? (item.key === 'free_cash_flow' ? row.fcff ?? row.fcf : item.key === 'operating_profit' ? row.ebit : item.key === 'working_capital_change' ? row.delta_nwc ?? row.delta_working_capital ?? row.change_nwc : null),1))) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div><div class="table-footnote">Financial values in USD millions. See source assumptions before using the output.</div>';
  }
  function valueBridge(cases) {
    const base = cases.find(item => String(item.name).toLowerCase() === 'base') || cases[0] || {};
    const entries = [['Enterprise value',base.enterprise_value],['Equity value',base.equity_value],['Diluted shares',base.shares]];
    return '<div class="value-key-grid" style="margin-top:17px">' + entries.map(([label,value]) => '<div><span>' + label + '</span><strong>' + e(num(value,1)) + '</strong></div>').join('') + '</div><p class="small-note" style="margin-top:13px">Enterprise value reconciles to equity after net debt and other claims. Divide by diluted shares to get per-share value. All bridge amounts are in millions.</p>';
  }
  function assumptionsBlock(assumptions) {
    if (!assumptions || typeof assumptions !== 'object') return '<p class="small-note" style="margin-top:15px">The accepted assumptions have not been attached.</p>';
    const entries = Array.isArray(assumptions) ? assumptions.map(item => [item.label || item.name || item.parameter, item.value]) : Object.entries(assumptions);
    return '<div class="data-list">' + entries.filter(([,value]) => typeof value !== 'object').map(([key,value]) => '<div><span>' + e(human(key)) + '</span><strong class="mono">' + e(number(value) !== null ? num(value,4) : value) + '</strong></div>').join('') + '</div><p class="small-note">Ratios use decimal form. These are assumptions, with dates and evidence maintained in the thesis.</p>';
  }
  function reverseBlock(reverse, price) {
    if (!reverse || typeof reverse !== 'object') return '<p class="small-note" style="margin-top:15px">A reverse solution is not available for the current inputs. A market price alone does not establish the needed operating outcome.</p>';
    const value = reverse.required_value ?? reverse.solved_value ?? reverse.solution ?? reverse.required_utilization ?? reverse.implied_growth ?? reverse.required_retention;
    const target = reverse.target_price ?? reverse.price ?? price;
    const solved = reverse.parameter || reverse.solved_parameter || reverse.driver || 'Operating requirement';
    return '<p class="small-note" style="margin-top:12px">At the dated price of ' + e(money(target)) + ', hold the stated assumptions fixed and solve for one operating requirement.</p><div class="data-list"><div><span>' + e(human(solved)) + '</span><strong>' + e(number(value) !== null && number(value) <= 1 ? percent(value) : num(value,3)) + '</strong></div><div><span>Forward recomputation</span><strong>' + e(money(reverse.recomputed_price ?? reverse.forward_value ?? reverse.recomputed_value)) + '</strong></div></div>' + (reverse.state === 'unavailable' ? '<p class="small-note">The current price has no supported solution within the model\'s feasible range.</p>' : '') + (reverse.held_assumptions ? '<p class="small-note">Held fixed: ' + e(Array.isArray(reverse.held_assumptions) ? reverse.held_assumptions.join(', ') : typeof reverse.held_assumptions === 'object' ? Object.keys(reverse.held_assumptions).map(human).join(', ') : reverse.held_assumptions) + '.</p>' : '') + '<p class="small-note">' + e(textOf(reverse.interpretation || reverse.note || reverse.notes) || 'The result is conditional on the model and held inputs. It is not a market forecast.') + '</p>';
  }
  function crossCheckBlock(check) {
    if (!check) return '<p class="small-note" style="margin-top:15px">A second valuation method is not supplied. The base case should be challenged before using it.</p>';
    const checkValue = check.value_per_share ?? check.value ?? check.base;
    return '<p class="small-note" style="margin-top:13px">' + e(human(check.method || check.name || 'Valuation cross-check')) + '</p><strong style="font-size:25px;font-weight:550;display:block;margin:10px 0">' + e(money(checkValue)) + '</strong><p class="small-note">' + e(textOf(check.explanation || check.note || check.notes || check.disagreement) || 'The second method shares some assumptions with the primary model. Agreement is not independent proof.') + '</p>';
  }
  function renderSensitivity(sensitivity) {
    if (!sensitivity) return '<div class="panel-padding">' + unavailable('Sensitivity detail is unavailable.', 'The model has not supplied the values for a conditional input grid.') + '</div>';
    let rows = sensitivity.rows || sensitivity.row_values || sensitivity.discount_rates, columns = sensitivity.columns || sensitivity.column_values || sensitivity.terminal_growth_rates, values = sensitivity.values || sensitivity.grid || sensitivity.matrix;
    if (Array.isArray(sensitivity) && sensitivity.length && typeof sensitivity[0] === 'object') return '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="mini-table"><thead><tr><th>Changed input</th><th>Input value</th><th>Value / share</th><th>Model state</th></tr></thead><tbody>' + sensitivity.map(row => '<tr><td>' + e(human(row.parameter)) + '</td><td>' + e(/rate|retention|utilization/.test(row.parameter || '') ? percent(row.value) : num(row.value,3)) + '</td><td>' + e(money(row.per_share_value ?? row.value_per_share)) + '</td><td>' + badge(human(row.state || 'Available'),row.state === 'unavailable' ? 'warning' : 'neutral') + '</td></tr>').join('') + '</tbody></table></div><div class="table-footnote">Change one input at a time. Other assumptions and the operating constraints stay fixed.</div>';
    if (!Array.isArray(rows) || !Array.isArray(columns) || !Array.isArray(values)) return '<div class="panel-padding">' + assumptionsBlock(sensitivity) + '</div>';
    const allValues = values.flat().map(number).filter(value => value !== null), minimum = Math.min(...allValues), maximum = Math.max(...allValues), middle = (minimum+maximum)/2;
    const label = input => typeof input === 'object' ? textOf(input) : number(input) !== null && number(input) < 1 ? percent(input) : String(input);
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="mini-table sensitivity"><thead><tr><th>' + e(human(sensitivity.row_label || sensitivity.row_parameter || 'Discount rate')) + ' / ' + e(human(sensitivity.column_label || sensitivity.column_parameter || 'Terminal growth')) + '</th>' + columns.map(column => '<th>' + e(label(column)) + '</th>').join('') + '</tr></thead><tbody>' + rows.map((row,index) => '<tr><th>' + e(label(row)) + '</th>' + array(values[index]).map(value => '<td class="' + (Number(value) > middle ? 'heat-high' : Number(value) < minimum+(maximum-minimum)/3 ? 'heat-low' : 'heat-mid') + '">' + e(money(value)) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div><div class="table-footnote">USD/share. Change one input at a time and keep feasibility constraints in view.</div>';
  }
  function renderTechnical(company) {
    const technical = company.technical || {};
    return '<section class="panel panel-padding"><span class="eyebrow">DATED TECHNICAL SNAPSHOT</span><h2 style="margin-top:10px">' + e(human(technical.trend || technical.state || 'Unavailable')) + '</h2><div class="data-list">' + [['20-day average',money(technical.ma20)],['60-day average',money(technical.ma60)],['200-day average',money(technical.ma200)],['RSI 14',num(technical.rsi14)],['Maximum drawdown',percent(technical.max_drawdown)]].map(([key,value]) => '<div><span>' + key + '</span><strong>' + e(value) + '</strong></div>').join('') + '</div><p class="small-note">As of ' + e(date(technical.as_of,true)) + '. Descriptive price conditions stay separate from business quality and value.</p></section>';
  }
  function renderHistory(company) {
    const history = array(company.history), cohorts = array(company.forecast_cohorts), events = array(ui.state.events).filter(event => event.symbol === company.symbol);
    const revisions = history.map(item => '<article class="panel-padding" style="border-top:1px solid #e5e8e3"><div class="card-kicker"><strong>' + e(item.id) + '</strong>' + badge('Saved version','neutral') + '</div><p>' + e(item.reason) + '</p><p class="small-note">Evidence cutoff ' + e(datetime(item.company?.as_of)) + ' · Base value ' + e(money(item.valuation?.base)) + '</p><details><summary>Inspect saved assumptions</summary>' + assumptionsBlock(item.company?.assumptions || {}) + '</details></article>').join('');
    const forecastTable = cohorts.length ? '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data" style="margin-top:18px"><table class="mini-table"><thead><tr><th>Metric / revision</th><th>Frozen</th><th>Horizon ends</th><th>Expected</th><th>Observed</th><th>Evaluation</th></tr></thead><tbody>' + cohorts.map(cohort => '<tr><td>' + e(human(cohort.metric || cohort.label || cohort.id)) + '<br><small>' + e(cohort.revision_id || '') + '</small></td><td>' + e(date(cohort.frozen_at || cohort.created_at || cohort.as_of,true)) + '</td><td>' + e(cohort.due_at || cohort.due_date ? date(cohort.due_at || cohort.due_date,true) : /^\d{4}-\d{2}-\d{2}$/.test(String(cohort.horizon)) ? date(cohort.horizon, true) : 'Year ' + (cohort.horizon || '?')) + '</td><td>' + e(num(cohort.predicted ?? cohort.expected ?? cohort.forecast_value)) + '</td><td>' + e(num(cohort.actual ?? cohort.observed ?? cohort.observed_value)) + '</td><td>' + badge(cohort.observed != null ? 'Observation recorded' : 'Awaiting observation', 'neutral') + '</td></tr>').join('') + '</tbody></table></div>' : '<div style="margin-top:17px">' + unavailable('No forecast cohort is attached yet.', 'An accepted dated forecast is required before later observations can be evaluated.') + '</div>';
    return '<div class="detail-two-grid"><div><section class="panel"><div class="panel-head"><h2>Evidence and thesis timeline</h2><small>Baselines preserved</small></div>' + renderTimeline(events) + '</section><section class="panel" style="margin-top:21px"><div class="panel-head"><h2>Accepted thesis versions</h2><small>' + history.length + ' saved</small></div>' + revisions + '</section><section class="panel panel-padding"><span class="eyebrow">FORECAST ACCOUNTABILITY</span><h2 style="margin-top:10px">Compare forecasts with later observations</h2><p class="small-note" style="margin-top:10px">Predictions stay frozen in USD millions. Later observations must follow their horizon and freeze date.</p>' + forecastTable + '</section></div><aside><section class="panel panel-padding"><span class="eyebrow">RESEARCH HISTORY</span><h2 style="margin-top:10px">The record stays inspectable.</h2><p class="small-note" style="margin-top:12px">Opening an alert or marking it reviewed does not change the accepted financial assumptions. A revision requires an explicit comparison and acceptance.</p>' + button('Save the current research', 'research', 'data-symbol="' + e(company.symbol) + '"', 'subtle', 'arrow') + '</section>' + renderTechnical(company) + '</aside></div>';
  }

  function renderMonitor() {
    const paused = ui.state.settings?.paused || ui.state.meta?.paused, replay = ui.state.replay || {}, events = array(ui.state.events), gaps = ui.state.overview?.data_gaps || 0;
    return heading('Monitor & timeline', 'Set tracking tiers, replay dated events, and inspect saved activity.', button(paused ? 'Resume monitoring' : 'Pause monitoring', 'pause', '', paused ? 'primary' : '', paused ? 'play' : 'pause'), 'TRACKING & SAVED EVENTS') + renderSECStatus() +
      '<div class="monitor-hero"><div><span class="eyebrow">' + (isSynthetic() ? 'MANUAL SYNTHETIC REPLAY' : 'LOCAL WORKSPACE') + '</span><h2 style="margin-top:7px">' + (paused ? 'Monitoring paused' : gaps ? 'Source coverage needs review' : isSynthetic() ? 'Ready for the next saved event' : 'Saved inputs available') + '</h2><p>' + (paused ? 'Saved evidence and history remain available. Resume before replaying a new check.' : isSynthetic() ? 'Replay dated fixtures to compare an affected assumption and review the resulting local alert.' : 'Monitoring uses configured evidence inputs. Live adapters and background scheduling require separate activation.') + '</p></div><div class="action-row">' + (isSynthetic() ? button('Replay next update', 'replay-next', '', 'primary', 'replay') : button('View workspace setup','navigate','data-page="workspace"','','arrow')) + '</div></div>' +
      '<section class="section">' + sectionHeading('Your tracking scope', 'Choose attention based on research priority, with the same evidence discipline.') + (companies().length ? watchTable(companies(),true) : emptyState('Nothing is tracked yet.', 'Add a supported company after reviewing its thesis and operating model.', 'Start company research','research')) + '</section>' +
      (isSynthetic() ? '<section class="section panel panel-padding">' + sectionHeading('Explore the update scenarios', 'Try a material change, an ambiguous input, or replay the same event to inspect deduplication.') + '<div class="replay-form"><label class="visually-hidden" for="replay-event">Choose a replay event</label><select id="replay-event">' + array(replay.available_events).map(event => '<option value="' + e(event.id) + '">' + e(event.title) + (event.symbol ? ' · ' + e(event.symbol) : '') + '</option>').join('') + '</select>' + button('Replay selected event', 'replay-selected', '', '', 'replay') + (replay.last_event_id ? button('Replay same event', 'replay-same', '', '', 'clock') : '') + '</div><p class="small-note" style="margin-top:12px">Replay is a local simulation. It does not collect live sources, schedule future checks, or send email.</p></section>' : '') +
      '<div class="split-grid"><section>' + sectionHeading('Event timeline', 'Events, review states, and evidence vintages.') + '<div class="panel">' + renderTimeline(events) + '</div></section><section>' + sectionHeading('Workspace activity', 'A saved record of the research loop.') + '<div class="panel">' + renderTimeline(array(ui.state.activity).slice(0,10).map(item => ({...item,published_at:item.at,summary:human(item.kind)}))) + '</div></section></div>';
  }
  function renderAlerts() {
    const filtered = alerts().filter(alert => ui.filter === 'all' || alert.review_state === ui.filter), newCount = alerts().filter(alert => alert.review_state === 'new').length;
    return heading('Alerts', 'Review the evidence and affected assumptions before accepting a revision.', button('Monitoring settings', 'navigate', 'data-page="workspace"', '', 'bell'), 'LOCAL REVIEW INBOX') +
      '<div class="filter-row" aria-label="Filter alerts">' + [{id:'all',label:'All alerts'},{id:'new',label:'Needs review'},{id:'reviewed',label:'Reviewed'},{id:'deferred',label:'Deferred'}].map(filter => '<button type="button" class="' + (ui.filter === filter.id ? 'active' : '') + '" data-action="alert-filter" data-filter="' + filter.id + '" aria-pressed="' + (ui.filter === filter.id) + '">' + filter.label + (filter.id === 'new' ? ' (' + newCount + ')' : '') + '</button>').join('') + '<small>Local inbox delivery only · email previews are not sent</small></div><div class="alert-list">' + (filtered.length ? filtered.map(renderAlert).join('') : emptyState('No alerts in this view.', alerts().length ? 'Choose another filter to inspect the saved review history.' : 'The baseline does not create an alert. Replay a material update to see the evidence-to-review loop.', isSynthetic() && !alerts().length ? 'Explore update scenarios' : '', 'monitor')) + '</div>';
  }
  function renderAlert(alert,index) {
    const company = companies().find(item => item.symbol === alert.symbol) || {symbol:alert.symbol}, changes = array(alert.changes);
    return '<article class="alert-card ' + (alert.review_state === 'new' ? 'new' : '') + '"><div class="alert-head">' + logo(company,index) + '<div><div class="alert-meta"><strong>' + e(alert.symbol) + '</strong>' + alertBadge(alert) + badge(human(alert.review_state), alert.review_state === 'new' ? 'warning' : 'neutral') + '</div><h3>' + e(alert.title) + '</h3></div><time class="alert-time" datetime="' + e(alert.occurred_at) + '">' + e(datetime(alert.occurred_at)) + '</time></div><p class="alert-reason">' + e(alert.reason) + '</p>' + ((changes.length || number(alert.candidate_value) !== null) ? '<div class="change-strip">' + changes.map(change => '<div><span>' + e(human(change.parameter)) + '</span><strong>' + e(num(change.old,4)) + ' → ' + e(num(change.new,4)) + '</strong></div>').join('') + (number(alert.baseline_value) !== null ? '<div><span>Accepted base value</span><strong>' + e(money(alert.baseline_value)) + '</strong></div>' : '') + (number(alert.candidate_value) !== null ? '<div><span>Candidate base value</span><strong>' + e(money(alert.candidate_value)) + '</strong></div><div><span>Conditional value change</span><strong class="' + (alert.value_delta_pct < 0 ? 'negative' : 'positive') + '">' + e(num(alert.value_delta_pct,1)) + '%</strong></div>' : '') + '</div>' : '') + '<div class="alert-actions">' + button('Open evidence & review', 'open-alert', 'data-id="' + e(alert.id) + '"', '', 'arrow') + (alert.review_state !== 'reviewed' ? button('Mark reviewed', 'review-alert', 'data-id="' + e(alert.id) + '"', 'subtle', 'check') : '') + (alert.review_state === 'new' ? button('Defer', 'defer-alert', 'data-id="' + e(alert.id) + '"', 'subtle', 'clock') : '') + button('Email preview', 'email-preview', 'data-id="' + e(alert.id) + '"', 'subtle', 'mail') + '<span class="delivery-label">Delivered to local inbox · assumptions require separate acceptance</span></div></article>';
  }
  function renderLibrary() {
    return heading('Research library', 'Read saved reports with their original evidence cutoff and assumptions.', button('Open company research', 'navigate', 'data-page="research"', 'primary', 'source'), 'REPORTS & RESEARCH METHODS') + '<section class="section">' + sectionHeading('Saved research reports', 'Dated snapshots preserve what was known at the time.') + (ui.reports.length ? '<div class="library-grid">' + ui.reports.map(report => '<article class="report-card"><span class="report-icon">' + icon('source') + '</span><div class="card-kicker"><strong>' + e(report.symbol) + '</strong>' + badge(human(report.status || 'Saved report'), report.status === 'partial' ? 'warning' : 'neutral') + '</div><h3>' + e(report.title) + '</h3><p>Saved ' + e(datetime(report.created_at)) + '<br>Evidence and assumptions at this research vintage.</p>' + button('Read report', 'report', 'data-id="' + e(report.id) + '"', 'subtle', 'arrow') + '</article>').join('') + '</div>' : emptyState('No saved research reports', 'Save an imported company’s current thesis, scenario model, and evidence from Company Research.', 'Open company research','research')) + '</section><section>' + sectionHeading('Research methods', 'Checks for evidence, model assumptions, and forecast accountability.') + '<div class="methods-grid">' + [{name:'Understand the operating mechanism',text:'Separate announced capacity from qualified capacity, utilization, shipments, and revenue. Follow the real constraints.'},{name:'Build the cash-flow bridge',text:'Connect operating drivers to margins, working capital, reinvestment, funding, diluted shares, and per-share value.'},{name:'Challenge the base case',text:'Compare feasible scenarios, a second method, and the operating expectations implied by a dated price.'},{name:'Keep evidence point in time',text:'Preserve source, publication time, fiscal period, unit, and evidence cutoff. Later knowledge does not rewrite history.'},{name:'Give the thesis a failure condition',text:'State what you would observe if the thesis were wrong. Map a supported update to the affected assumption.'},{name:'Evaluate the original forecast',text:'Keep dated forecasts unchanged and compare them with later observations. Report gaps and unavailable models plainly.'}].map((method,index) => '<article class="method-card"><span>METHOD 0' + (index+1) + '</span><h3>' + method.name + '</h3><p>' + method.text + '</p></article>').join('') + '</div></section>';
  }
  function renderWorkspace() {
    const settings = ui.state.settings || {};
    return heading('My workspace', 'Configure local preferences and inspect which capabilities are active.', button('Research loop guide','onboarding','','','arrow'), 'SETTINGS & CAPABILITIES') + `
      <div class="workspace-grid"><section class="panel panel-padding">
        ${sectionHeading('Workspace & notification preferences', 'Saved locally. External delivery requires a separately activated worker.')}
        <form class="settings-form" id="settings-form">
          <div class="field"><label for="workspace-name">Workspace name</label><input id="workspace-name" name="name" value="${e(settings.name || 'Personal workspace')}" maxlength="80" required><small>Shown in the navigation sidebar.</small></div>
          <div class="form-row">
            <div class="field"><label for="language">Language preference</label><select id="language" name="language"><option value="en"${settings.language !== 'zh-CN' ? ' selected' : ''}>English</option><option value="zh-CN"${settings.language === 'zh-CN' ? ' selected' : ''}>中文 / Chinese</option></select><small>Saved for research configuration. The current workbench uses English.</small></div>
            <div class="field"><label for="materiality">Value change threshold (%)</label><input id="materiality" name="value_change_threshold_pct" type="number" min="0" max="100" step="0.1" value="${e(settings.value_change_threshold_pct ?? 5)}" required><small>Minimum absolute base-value change for a numerical alert.</small></div>
          </div>
          <div class="form-row">
            <div class="field"><label for="timezone">Quiet-hours timezone</label><input id="timezone" name="timezone" value="${e(settings.timezone || 'UTC')}" required><small>IANA name, for example America/Chicago or UTC.</small></div>
            <div class="field"><label for="cooldown">Email reminder cooldown</label><input id="cooldown" name="cooldown_hours" type="number" min="0" max="720" step="1" value="${e(settings.cooldown_hours ?? 24)}" required><small>Spacing between external reminder queues for the same company.</small></div>
          </div>
          <div class="form-row"><div class="field"><label for="quiet-start">Quiet hours start</label><input id="quiet-start" name="quiet_start" type="time" value="${e(settings.quiet_start || '22:00')}" required></div><div class="field"><label for="quiet-end">Quiet hours end</label><input id="quiet-end" name="quiet_end" type="time" value="${e(settings.quiet_end || '07:00')}" required></div></div>
          <div class="toggle-row"><input type="checkbox" id="email-enabled" name="email_enabled"${settings.email_enabled ? ' checked' : ''}${isSynthetic() ? ' disabled' : ''}><label for="email-enabled">Queue eligible email reminders<small>${isSynthetic() ? 'Synthetic replay never queues external email.' : 'Queues future eligible alerts. This page never sends; configure and explicitly activate the delivery worker separately.'}</small></label></div>
          <div class="toggle-row"><input type="checkbox" id="digest" name="digest_enabled"${settings.digest_enabled ? ' checked' : ''}><label for="digest">Prefer a daily digest<small>Save a preference for future delivery setup. Local daily and weekly summaries are available separately.</small></label></div>
          <div class="toggle-row"><input type="checkbox" id="paused" name="paused"${settings.paused ? ' checked' : ''}><label for="paused">Pause monitoring<small>Keep research and history readable while new checks are paused.</small></label></div>
          <div class="action-row" style="margin-top:7px"><button type="submit" class="button primary">Save preferences</button><span class="small-note">No credentials are requested.</span></div>
        </form></section><aside><section class="panel panel-padding">${sectionHeading('Your workspace capabilities')}
          <div class="setup-row"><div class="setup-status"><span>Local research & inputs</span>${badge(isSynthetic() ? 'Synthetic replay' : 'Local workspace', 'info')}</div><p>Supported financial models, dated evidence, persistent reports and a local alert inbox.</p></div>
          <div class="setup-row"><div class="setup-status"><span>Live data sources</span>${badge('Not connected','neutral')}</div><p>The workbench reads saved state. Your own public-source collector can supply JSON events for continuous directory monitoring.</p></div>
          <div class="setup-row"><div class="setup-status"><span>Model assistant</span>${badge('Not connected','neutral')}</div><p>The numerical model works without an LLM. Use the portable agent guide and reviewed research packets with your chosen assistant.</p></div>
          <div class="setup-row"><div class="setup-status"><span>External delivery & hosting</span>${badge('Not activated','neutral')}</div><p>Email previews stay local. The operator activates a worker and private hosting separately.</p></div>
        </section></aside></div>`;
  }

  function dialog(title, content, eyebrow = 'RESEARCH DETAIL') {
    $('#dialog-title').textContent = title;$('#dialog-eyebrow').textContent = eyebrow;$('#dialog-content').innerHTML = content;
    const element = $('#detail-dialog');if (!element.open) element.showModal();
    updateTableCues(element);
    $('#dialog-title').focus({preventScroll:true});
  }
  function closeDialog() {$('#detail-dialog').close();}
  function openOnboarding() {
    dialog('Read, replay, review.', '<p>Inspect the saved baseline, replay an evidence update, then compare the candidate assumptions before accepting a revision.</p><div class="onboarding-steps"><article class="onboarding-step"><span>01 / UNDERSTAND</span><h3>Read a company thesis.</h3><p>Inspect the operating drivers, source records, scenario values, and observable failure conditions.</p></article><article class="onboarding-step"><span>02 / OBSERVE</span><h3>Replay a material update.</h3><p>Follow a saved synthetic event into an affected assumption, candidate model, and local inbox alert.</p></article><article class="onboarding-step"><span>03 / DECIDE</span><h3>Review, then revise.</h3><p>Open the evidence. Mark the alert reviewed. Compare revised assumptions before accepting a new baseline.</p></article></div><p class="small-note">' + (isSynthetic() ? 'This is a synthetic replay with invented companies and dated prices. ' : 'This is a local workspace. ') + 'No provider call, live scheduler, external email, or trade is activated by browsing.</p><div class="action-row">' + button('Start with company research','tour-start','','primary','arrow') + button('Set up my workspace','tour-workspace','','','company') + '</div>', 'WELCOME TO YOUR RESEARCH DESK');
  }
  async function openAlert(id) {
    const alert = alerts().find(item => item.id === id);if (!alert) return;
    const company = companies().find(item => item.symbol === alert.symbol), event = array(ui.state.events).find(item => item.id === alert.event_id);
    const records = Array.from(new Map([...array(company?.evidence), ...array(event?.evidence)].filter(source => array(alert.evidence_ids).includes(source.id)).map(source => [source.id,source])).values());
    dialog(alert.title, '<div class="action-row">' + alertBadge(alert) + badge(human(alert.review_state),'neutral') + '</div><p>' + e(alert.reason) + '</p>' + (array(alert.changes).length ? changesTable(alert.changes) : '') + '<h3>' + (sourceStatusAlert(alert) ? 'Recorded source status' : 'Evidence behind the update') + '</h3>' + (sourceStatusAlert(alert) ? '<p class="small-note">This records the collector outcome. It supplies no new filing facts or financial assumptions.</p>' : records.length ? records.map(sourceCard).join('') : '<p class="small-note">Evidence references: ' + e(array(alert.evidence_ids).join(', ') || 'Not attached. Verification remains open.') + '</p>') + '<p class="small-note">Opening or marking this alert reviewed does not accept financial assumptions. A revised baseline requires a separate explicit action in the company desk.</p><div class="action-row">' + button('Open company desk','dialog-company','data-symbol="' + e(alert.symbol) + '"','primary','arrow') + (alert.review_state !== 'reviewed' ? button('Mark reviewed','review-alert-dialog','data-id="' + e(id) + '"','','check') : '') + button('Email preview','email-preview','data-id="' + e(id) + '"','','mail') + '</div>', e(alert.symbol) + ' / LOCAL ALERT');
  }
  function changesTable(changes) {
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="mini-table"><thead><tr><th>Affected assumption</th><th>Accepted</th><th>Candidate</th></tr></thead><tbody>' + changes.map(change => '<tr><td>' + e(human(change.parameter || change.label)) + '</td><td>' + e(num(change.old,5)) + '</td><td>' + e(num(change.new,5)) + '</td></tr>').join('') + '</tbody></table></div><p class="small-note" style="margin-top:9px">Ratio inputs are shown in decimal form. Candidate assumptions remain unaccepted.</p>';
  }
  async function openCandidate(symbol) {
    await loadCompany(symbol);const company = ui.details.get(symbol) || companies().find(item => item.symbol === symbol);if (!company?.candidate_valuation) return toast('No candidate revision is available.',true);
    const candidate = company.candidate_valuation, old = company.valuation || {}, changes = array(company.candidate_changes);
    ui.candidateReview = {symbol,event_id:company.candidate_event_id,baseline_hash:company.candidate_baseline_hash,candidate_hash:company.candidate_hash};
    const pinned = Object.values(ui.candidateReview).every(Boolean);
    const candidateEvent = array(ui.state.events).find(event => event.id === company.candidate_event_id);
    dialog('Compare before accepting the revision.', '<p>The accepted thesis remains the baseline. Review the source evidence and the economic effect of the supported assumption change.</p>' + (changes.length ? changesTable(changes) : '<p class="small-note">Review the candidate assumption set in the saved model below.</p>') + '<div class="comparison" style="margin:23px 0"><div><small>ACCEPTED BASE VALUE</small><strong>' + e(money(baseValue(old))) + '</strong></div><span class="compare-arrow">→</span><div><small>CANDIDATE BASE VALUE</small><strong>' + e(money(baseValue(candidate))) + '</strong></div></div>' + '<h3>Evidence for this candidate</h3>' + array(candidateEvent?.evidence).map(sourceCard).join('') + assumptionsBlock(candidate.assumptions || scenarios(candidate).find(item => String(item.name).toLowerCase() === 'base')?.assumptions) + '<p class="small-note">Accepting preserves the prior revision and forecast history. This action updates the accepted financial assumptions for ' + e(symbol) + '.</p><div class="action-row">' + (pinned ? button('Accept revised assumptions','accept','data-symbol="' + e(symbol) + '"','primary','check') : '<p class="small-note negative">Refresh and compare a fully identified candidate before accepting.</p>') + button('Keep the current baseline','close-dialog') + '</div>', e(symbol) + ' / ASSUMPTION REVIEW');
  }
  function openDriver(id) {
    const company = activeCompany(), driver = array(company?.thesis?.drivers).find(item => item.id === id);if (!driver) return;
    const evidence = array(company.evidence).filter(item => array(driver.evidence_ids).includes(item.id));
    dialog(driver.label, '<span class="eyebrow">ACCEPTED DRIVER</span><h3 style="font-size:30px;margin:9px 0 15px">' + valueLabel(driver.value,driver.unit) + '</h3><p>' + e(driver.watch_condition || 'Review this driver with the next material evidence update.') + '</p><h3>Source and calculation context</h3>' + (evidence.length ? evidence.map(sourceCard).join('') : '<p>Evidence references: ' + e(array(driver.evidence_ids).join(', ') || 'No source is attached. This assumption needs verification.') + '</p>') + '<p class="small-note">An operating fact can support a driver input. Its conversion into revenue, capital requirements, cash flow, and per-share value still depends on the accepted model.</p>', e(company.symbol) + ' / EVIDENCE TO VALUE');
  }
  function openEvidence(id) {
    const company = activeCompany(), source = array(company?.evidence).find(item => item.id === id) || companies().flatMap(item => array(item.evidence)).find(item => item.id === id) || array(ui.state.events).flatMap(item => array(item.evidence)).find(item => item.id === id);if (!source) return;
    const verification = source.verification ? human(source.verification) : source.verified === true ? 'Verified record' : source.verified === false ? 'Needs verification' : 'Verification not attached';
    const fields = [['Evidence ID',source.id],['Source',source.source || (source.source_type === 'synthetic' ? 'Synthetic fixture' : source.source_type)],[source.source_type === 'issuer_ir' ? 'Date-only availability bound' : 'Published',datetime(source.published_at || source.publication_time)],['Usable as of',datetime(source.usable_at || source.as_of || source.published_at)],['Fiscal period',source.period || source.fiscal_period],['Unit',source.unit],['Currency',source.currency],['Source locator',source.locator],['Classification',human(source.classification)],['Verification',verification]];
    const url = safeUrl(source.url);
    dialog(source.title || source.source || source.id, '<p>' + e(source.claim || source.content || source.summary || source.description || 'Saved evidence record.') + '</p>' + (source.source_type === 'issuer_ir' ? '<p class="small-note">The issuer lists a filing date. Publication time is unknown; the availability bound uses the next Eastern midnight. Usable as of records actual acquisition time.</p>' : '') + '<div class="data-list">' + fields.filter(([,value]) => value).map(([label,value]) => '<div><span>' + label + '</span><strong>' + e(value) + '</strong></div>').join('') + '</div>' + (url ? '<a class="button" href="' + e(url) + '" target="_blank" rel="noopener noreferrer">Open source ↗</a>' : '<p class="small-note">' + (source.source_type === 'synthetic' ? 'This is a synthetic fixture record. ' : 'This is a locally saved source record. ') + 'No public source link is attached.</p>'), 'DATED EVIDENCE RECORD');
  }
  async function emailPreview(id) {
    try {const preview = await request('/api/alerts/' + encodeURIComponent(id) + '/preview');dialog('Email preview. Nothing sent.', '<div class="action-row">' + badge('Preview only','neutral') + '</div><h3>' + e(preview.subject || 'Research update') + '</h3><pre>' + e(preview.text || '') + '</pre><p class="small-note">This preview is rendered locally. It does not queue or send an email, and it is not delivery confirmation.</p>', 'LOCAL EMAIL PREVIEW');}
    catch (error) {toast(error.message,true);}
  }
  function inlineMarkdown(text) {
    return e(text).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }
  function renderMarkdown(markdown) {
    const lines = String(markdown || '').split('\n'), output = [];let list = null, paragraph = [], code = [], inCode = false;
    const flush = () => {if (paragraph.length) {output.push('<p>' + inlineMarkdown(paragraph.join(' ')) + '</p>');paragraph = [];}if (list) {output.push('</' + list + '>');list = null;}};
    for (let i=0;i<lines.length;i++) {
      const line = lines[i];
      if (line.startsWith('```')) {flush();if (inCode) {output.push('<pre>' + e(code.join('\n')) + '</pre>');code = [];}inCode = !inCode;continue;}
      if (inCode) {code.push(line);continue;}
      if (/^\s*\|/.test(line) && /^\s*\|?[\s:|\-]+\|\s*$/.test(lines[i+1] || '')) {
        flush();const headers = line.trim().replace(/^\||\|$/g,'').split('|').map(cell => cell.trim());i+=1;const rows = [];
        while (/^\s*\|/.test(lines[i+1] || '')) {i+=1;rows.push(lines[i].trim().replace(/^\||\|$/g,'').split('|').map(cell => cell.trim()));}
        output.push('<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable research data"><table class="mini-table"><thead><tr>' + headers.map(cell => '<th>' + inlineMarkdown(cell) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(row => '<tr>' + row.map(cell => '<td>' + inlineMarkdown(cell) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>');continue;
      }
      const headingMatch = /^(#{1,3})\s+(.+)$/.exec(line), bullet = /^\s*[-*]\s+(.+)$/.exec(line), ordered = /^\s*\d+\.\s+(.+)$/.exec(line);
      if (headingMatch) {flush();output.push('<h' + headingMatch[1].length + '>' + inlineMarkdown(headingMatch[2]) + '</h' + headingMatch[1].length + '>');}
      else if (bullet || ordered) {if (paragraph.length) {output.push('<p>' + inlineMarkdown(paragraph.join(' ')) + '</p>');paragraph=[];}const nextList = bullet ? 'ul' : 'ol';if (list !== nextList) {if (list) output.push('</' + list + '>');list=nextList;output.push('<' + list + '>');}output.push('<li>' + inlineMarkdown((bullet || ordered)[1]) + '</li>');}
      else if (/^\s*---+\s*$/.test(line)) {flush();output.push('<hr>');}
      else if (!line.trim()) flush();
      else {if (list) {output.push('</' + list + '>');list=null;}paragraph.push(line);}
    }
    flush();if (code.length) output.push('<pre>' + e(code.join('\n')) + '</pre>');return '<article class="report-markdown">' + output.join('') + '</article>';
  }
  async function openReport(id) {
    try {const report = await request('/api/reports/' + encodeURIComponent(id));dialog(report.title || 'Saved research report',renderMarkdown(report.markdown), 'RESEARCH REPORT / DATED SNAPSHOT');}
    catch (error) {toast(error.message,true);}
  }
  const mobileNavigation = window.matchMedia('(max-width:760px)');
  function closeMenu(restoreFocus = false) {
    const wasOpen = $('#sidebar').classList.contains('open');
    $('#sidebar').classList.remove('open');$('#sidebar').removeAttribute('role');$('#sidebar').removeAttribute('aria-modal');
    $('#sidebar-scrim').hidden=true;$('#menu-button').setAttribute('aria-expanded','false');$('.main-shell').inert=false;
    if (restoreFocus && wasOpen && mobileNavigation.matches) $('#menu-button').focus();
  }
  document.addEventListener('click', async event => {
    const nav = event.target.closest('a[data-page]');if (nav) {event.preventDefault();await navigate(nav.dataset.page);return;}
    const trigger = event.target.closest('[data-action]');if (!trigger || trigger.disabled) return;
    const action = trigger.dataset.action;
    if (action === 'navigate') await navigate(trigger.dataset.page);
    else if (action === 'lab-open') await navigate('lab',trigger.dataset.symbol);
    else if (action === 'lab-reload') await loadLab(ui.lab.symbol,true);
    else if (action === 'lab-runs') await loadLabRuns();
    else if (action === 'lab-run') await runLabReview();
    else if (action === 'lab-run-open') await openLabRun(trigger.dataset.id);
    else if (action === 'lab-verify') await verifyLabRun(trigger.dataset.id);
    else if (action === 'lab-calculate') {ui.lab.revision++;ui.lab.dirty=true;await calculateLab();}
    else if (action === 'lab-reset') {
      ui.lab.values=Object.fromEntries(labParameters().map(item => [item.key,Number(item.value)]));
      clearTimeout(ui.lab.timer);ui.lab.revision++;ui.lab.dirty=true;ui.lab.calculationError='';render();await calculateLab();
    }
    else if (action === 'refresh') await refresh(true);
    else if (action === 'company') {ui.tab = 'thesis';await navigate('research',trigger.dataset.symbol);}
    else if (action === 'company-tab') {ui.tab=trigger.dataset.tab;render();$('.tabs button[aria-selected="true"]')?.focus();}
    else if (action === 'alert-filter') {ui.filter=trigger.dataset.filter;render();$('.filter-row [data-filter="' + ui.filter + '"]')?.focus();}
    else if (action === 'onboarding') openOnboarding();
    else if (action === 'dismiss-tour') {ui.tourVisible=false;render();}
    else if (action === 'tour-start' || action === 'tour-workspace') {ui.tourVisible=false;closeDialog();await navigate(action === 'tour-start' ? 'research' : 'workspace');}
    else if (action === 'close-dialog') closeDialog();
    else if (action === 'replay-next' || action === 'replay-selected' || action === 'replay-same') {
      const id = action === 'replay-selected' ? $('#replay-event')?.value : action === 'replay-same' ? ui.state.replay?.last_event_id : null;
      await mutate('/api/replay',id ? {event_id:id} : {},'Replay processed.');
    }
    else if (action === 'pause') await mutate('/api/settings',{paused:!ui.state.settings?.paused},'Monitoring preference saved.');
    else if (action === 'open-alert') await openAlert(trigger.dataset.id);
    else if (action === 'review-alert' || action === 'defer-alert' || action === 'review-alert-dialog') {
      const reviewed = action !== 'defer-alert';if (action === 'review-alert-dialog') closeDialog();
      await mutate('/api/alerts/' + encodeURIComponent(trigger.dataset.id) + '/review',{action:reviewed ? 'reviewed' : 'deferred'},'Alert review saved. Financial assumptions are unchanged.');
    }
    else if (action === 'dialog-company') {closeDialog();ui.tab='thesis';await navigate('research',trigger.dataset.symbol);}
    else if (action === 'candidate') await openCandidate(trigger.dataset.symbol);
    else if (action === 'accept') {
      const snapshot = ui.candidateReview;
      if (!snapshot || snapshot.symbol !== trigger.dataset.symbol || !snapshot.event_id || !snapshot.baseline_hash || !snapshot.candidate_hash) return toast('Refresh and compare the candidate revision before accepting it.',true);
      const {event_id,baseline_hash,candidate_hash} = snapshot;
      const result = await mutate('/api/company/' + encodeURIComponent(snapshot.symbol) + '/accept',{event_id,baseline_hash,candidate_hash},'Revised assumptions accepted.');
      if (result) {ui.candidateReview=null;closeDialog();}
    }
    else if (action === 'driver') openDriver(trigger.dataset.id);
    else if (action === 'evidence') openEvidence(trigger.dataset.id);
    else if (action === 'email-preview') await emailPreview(trigger.dataset.id);
    else if (action === 'report') await openReport(trigger.dataset.id);
    else if (action === 'research') {const result = await mutate('/api/research',{symbol:trigger.dataset.symbol},'Research snapshot saved.');if (result?.report_id) await openReport(result.report_id);}
  });
  document.addEventListener('submit', async event => {
    if (event.target.id === 'auth-form') {
      event.preventDefault();const token = String(new FormData(event.target).get('access_token') || '').trim();if (!token) return;
      ui.accessToken=token;const pending=ui.authPending;ui.authPending=null;$('#workbench-token').value='';closeDialog();pending?.resolve();return;
    }
    if (event.target.id === 'research-form') {
      event.preventDefault();const symbol = String(new FormData(event.target).get('symbol') || '').trim().toUpperCase();if (!symbol) return;
      const result = await mutate('/api/research',{symbol},'Research snapshot saved.');
      if (result) {ui.symbol = symbol;await navigate('research',symbol);if (result.report_id) await openReport(result.report_id);}
    }
    if (event.target.id === 'settings-form') {
      event.preventDefault();const form = new FormData(event.target);
      await mutate('/api/settings',{name:String(form.get('name')).trim(),language:form.get('language'),timezone:String(form.get('timezone')).trim(),value_change_threshold_pct:Number(form.get('value_change_threshold_pct')),email_enabled:form.has('email_enabled'),cooldown_hours:Number(form.get('cooldown_hours')),quiet_start:form.get('quiet_start'),quiet_end:form.get('quiet_end'),digest_enabled:form.has('digest_enabled'),paused:form.has('paused')},'Workspace preferences saved locally.');
    }
  });
  document.addEventListener('change', async event => {
    const element = event.target;
    if (element.id === 'lab-symbol') await navigate('lab',element.value);
    if (element.dataset.watchSymbol) {const company = companies().find(item => item.symbol === element.dataset.watchSymbol);if (company) await mutate('/api/watchlist',{symbol:company.symbol,tier:element.value,watched:company.watched},'Tracking tier updated.');}
    if (element.dataset.watchToggle) {const company = companies().find(item => item.symbol === element.dataset.watchToggle);if (company) await mutate('/api/watchlist',{symbol:company.symbol,tier:company.watch_tier || 'observe',watched:element.checked},'Watchlist updated.');}
  });
  document.addEventListener('input', event => {
    const element=event.target, key=element.dataset.labParameter;
    if (!key) return;
    const parameter=labParameters().find(item => item.key === key), value=number(element.value);
    if (!parameter || value === null || !element.validity.valid) return;
    ui.lab.values[key]=value;
    $$('[data-lab-parameter]').filter(input => input.dataset.labParameter === key).forEach(input => {
      if (input !== element) input.value=String(value);
      if (input.type === 'range') input.setAttribute('aria-valuetext',labParameterValue(value,parameter) + ' ' + (/fraction|ratio/.test(parameter.unit || '') ? '' : parameter.unit));
    });
    const output=$('#lab-' + key + '-display');if (output) output.textContent=labParameterValue(value,parameter);
    scheduleLabCalculation();
  });
  document.addEventListener('keydown', event => {
    const tab = event.target.closest('[role="tab"]');
    if (tab && ['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) {
      event.preventDefault();const tabs = $$('.tabs [role="tab"]'), index = tabs.indexOf(tab), next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length)%tabs.length;
      ui.tab = tabs[next].dataset.tab;render();$('.tabs [aria-selected="true"]')?.focus();
    }
    if (event.key === 'Tab' && $('#sidebar').classList.contains('open')) {
      const controls = $$('a[href],button:not([disabled])', $('#sidebar')).filter(element => element.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && event.target === first) {event.preventDefault();last?.focus();}
      else if (!event.shiftKey && event.target === last) {event.preventDefault();first?.focus();}
    }
    if (event.key === 'Escape') closeMenu(true);
  });
  $('#menu-button').addEventListener('click',() => {
    const open = !$('#sidebar').classList.contains('open');
    if (!open) return closeMenu(true);
    $('#sidebar').classList.add('open');$('#sidebar').setAttribute('role','dialog');$('#sidebar').setAttribute('aria-modal','true');
    $('#sidebar-scrim').hidden=false;$('#menu-button').setAttribute('aria-expanded','true');$('.main-shell').inert=true;
    $('#navigation a.active')?.focus();
  });
  $('#sidebar-scrim').addEventListener('click',() => closeMenu(true));
  mobileNavigation.addEventListener('change',() => {if (!mobileNavigation.matches) closeMenu();});
  $('#detail-dialog').addEventListener('click',event => {if (event.target === $('#detail-dialog')) {const rect = event.target.getBoundingClientRect();if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeDialog();}});
  $('#detail-dialog').addEventListener('close',() => {if (ui.authPending) {const pending=ui.authPending;ui.authPending=null;pending.reject(new Error('Workspace authentication was not completed.'));}});
  window.addEventListener('hashchange',() => navigate(location.hash.slice(1)));
  window.addEventListener('resize',() => updateTableCues());
  ui.page = pages[location.hash.slice(1)] ? location.hash.slice(1) : 'today';
  refresh();
})();
