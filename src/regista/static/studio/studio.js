// Regista Studio: the control room. Plain script, no build step; needs /static/shared/regista.js first.
//
// Tabs are hash-routed (#overview, #review/<match>, #whos-who/<match>, #claims/<match>, #training, #runs/<match>, #jobs/<job>, #console/<match>)
// so the overview's to-do links land on the right place. Every read sends the Studio key (view or admin) in the
// key header through Regista.api; every write control is disabled, with the reason as a tooltip, unless the
// key is the admin key. The key never appears in a URL or in the page.
//
// Markup: everything that reaches the page as HTML is built with the html`` tag below, which escapes every value it
// interpolates (Regista.esc) unless that value is itself an html`` fragment. put() is the only place innerHTML is
// written, and it refuses anything that is not an html`` fragment. Raw text (logs, JSON) goes in through textContent.
(function () {
  'use strict';
  const R = window.Regista;
  const { esc, api, key } = R;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;

  // ------------------------------------------------------------------------------------------------ safe markup
  class Safe { constructor(s) { this.s = s; } toString() { return this.s; } }
  const show = (v) => (v instanceof Safe ? v.s : Array.isArray(v) ? v.map(show).join('') : esc(v));
  function html(strings, ...vals) {
    let out = strings[0];
    vals.forEach((v, i) => { out += show(v) + strings[i + 1]; });
    return new Safe(out);
  }
  function put(el, frag) {
    if (!(frag instanceof Safe)) throw new TypeError('put() takes an html`` fragment');
    el.innerHTML = frag.s;
  }
  const NOTHING = html``;

  // ------------------------------------------------------------------------------------------------ state and formatting
  // rvView: the review queue shows clips flagged unsure, or every clip (flagged first). noIdentity: vision matches whose
  // identity result is not on this server (a 409 on answering), remembered for the session.
  const S = { role: null, caps: {}, matches: null, tab: null, arg: null, poll: 0, crops: [], whos: null, pending: new Map(),
              chat: { state: null, history: [] }, overview: null, rvView: 'flagged', noIdentity: new Set(), whosDone: null };
  const MIN_VERDICTS = 8;  // regista.feedback.MIN_SAMPLES: the watchability model trains on at least this many reviewed clips

  const canWrite = () => S.caps.writes !== 'read-only' && (S.role === 'admin' || S.role === 'open');
  const whyNoWrite = () => (S.caps.writes === 'read-only' ? 'This deployment is read-only (REGISTA_READONLY=1).'
    : 'Needs the admin key: the view key can read but not write.');
  const w = () => (canWrite() ? NOTHING : html` disabled title="${whyNoWrite()}"`);

  const num = (n) => (n === null || n === undefined ? '–' : typeof n === 'number' ? n.toLocaleString('en-GB') : String(n));
  // "1 answer", "3 answers", "1 replay", "2 replays"; irregular plurals are passed in.
  const plural = (n, word, many) => `${num(n)} ${n === 1 ? word : many || `${word}s`}`;
  const pct = (x) => (x === null || x === undefined ? '–' : `${Math.round(x * 1000) / 10}%`);
  const score = (x) => (typeof x === 'number' ? x.toFixed(2) : '–');
  const ms = (x) => (typeof x === 'number' ? (x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${Math.round(x)} ms`) : '–');
  function bytes(b) {
    if (typeof b !== 'number') return '–';
    const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return `${b.toFixed(i ? 1 : 0)} ${u[i]}`;
  }
  function when(iso) {
    if (!iso) return '–';
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return String(iso);
    const s = Math.round((Date.now() - t) / 1000);
    const ago = s < 60 ? `${s} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
    return `${new Date(t).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'medium' })} (${ago})`;
  }
  const clock = (t) => (typeof t === 'number' ? R.fmtTime(t) : '–');
  const ID = /^[A-Za-z0-9_.\-]{1,120}$/;
  const ANNOTATOR = /^[A-Za-z0-9_ .\-]{1,40}$/;
  // Only our own API paths become a video or image source.
  const apiPath = (u) => (typeof u === 'string' && /^\/api\/[A-Za-z0-9_.\-/]+$/.test(u) && !u.includes('..') ? u : null);

  const STATUS_CLASS = { ok: 'ok', none: 'none', paused: 'paused', failed: 'failed', running: 'running', lost: 'lost', waiting: 'paused',
                         skipped: 'muted', dead_letter: 'failed', error: 'failed' };
  const chip = (status) => html`<span class="chip ${STATUS_CLASS[status] || 'muted'}">${status ?? '–'}</span>`;
  const tags = (list) => (list || []).map((t) => html`<span class="tag">${R.tagLabel(t)}</span>`);
  const kv = (pairs) => html`<dl class="kv">${pairs.map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>`;
  const jsonBlock = (v) => html`<pre class="log json">${JSON.stringify(v, null, 2)}</pre>`;

  function errText(e) {
    const d = e && e.detail !== undefined ? e.detail : e && e.message;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x && x.msg ? `${(x.loc || []).join('.')}: ${x.msg}` : JSON.stringify(x))).join('; ');
    if (d && typeof d === 'object') {
      if (d.message) return d.message + (Array.isArray(d.problems) ? `: ${d.problems.slice(0, 8).map((p) => (typeof p === 'string' ? p : JSON.stringify(p))).join('; ')}` : '');
      return JSON.stringify(d);
    }
    return String(e);
  }
  // A 401 means the key was rotated or forgotten: back to the gate. Anything else is shown where it happened.
  function fail(el, e, extra) {
    if (e && e.status === 401) { lockOut('That key is no longer accepted.'); return; }
    put(el, html`<div class="err">${e && e.status ? `HTTP ${e.status}: ` : ''}${errText(e)}${extra ? html`<br>${extra}` : NOTHING}</div>`);
  }
  const studioGet = (path) => api(path, { auth: true });
  const write = (path, body, method = 'POST') => api(path, { method, body, auth: true });

  async function matches(force) {
    if (!S.matches || force) S.matches = await api('/api/matches');
    return S.matches;
  }
  const matchLabel = (m) => {
    const t = (m.teams || []).map((x) => x.short_name).join(' v ');
    const sc = m.score ? Object.values(m.score).join('-') : '';
    return `${m.match_id}${t ? ` · ${t}` : ''}${sc ? ` ${sc}` : ''}${m.source === 'cosmos' ? ' · Cosmos DB only' : ''}`;
  };
  const options = (list, selected, first) => html`${first ? html`<option value="">${first}</option>` : NOTHING}${list.map(
    (m) => html`<option value="${m.value}"${m.value === selected ? html` selected` : NOTHING}>${m.label}</option>`)}`;

  // ------------------------------------------------------------------------------------------------ the key gate
  function lockOut(msg) {
    key.clear(); stopPolling();
    $('studio').hidden = true; $('gate').hidden = false; put($('role'), NOTHING);
    $('gateMsg').textContent = msg || '';
  }

  async function openStudio() {
    let s;
    try { s = await api('/api/studio/session', { auth: true }); } catch (e) {
      lockOut(e.status === 401 && key.get() ? 'That key was not accepted.' : e.status === 401 ? '' : `The Studio is unreachable: ${errText(e)}`);
      return;
    }
    S.role = s.role; S.caps = s.capabilities || {};
    $('gate').hidden = true; $('studio').hidden = false;
    const label = s.role === 'admin' ? 'admin key' : s.role === 'view' ? 'view key (read-only)' : 'open (no keys configured)';
    put($('role'), html`<span class="badge ${s.role}">${label}</span>${s.role !== 'open' ? html` · <a href="#" id="signOut">forget key</a>` : NOTHING}`);
    if ($('signOut')) $('signOut').onclick = (e) => { e.preventDefault(); key.clear(); location.reload(); };
    applyWriteGates();
    route();
    if (S.tab !== 'overview') refreshOverview(false);
  }

  function applyWriteGates() {
    const note = $('writeNote');
    note.hidden = canWrite();
    note.textContent = canWrite() ? '' : `${whyNoWrite()} You can see everything; every control that changes something is disabled.`;
    for (const el of document.querySelectorAll('[data-write]')) {
      el.disabled = !canWrite();
      el.title = canWrite() ? '' : whyNoWrite();
    }
  }

  $('gate').onsubmit = (e) => {
    e.preventDefault();
    const v = $('keyIn').value.trim();
    if (v) { key.set(v); $('keyIn').value = ''; openStudio(); }
  };

  // ------------------------------------------------------------------------------------------------ routing
  const TABS = { overview: loadOverview, review: loadReview, 'whos-who': loadWhos, claims: loadClaims, training: loadTraining, runs: loadRuns, jobs: loadJobs, console: loadConsole };

  function stopPolling() { S.poll++; }  // any running poll loop sees the counter move and stops

  function route() {
    if ($('studio').hidden) return;
    const m = /^#([a-z-]+)(?:\/(.*))?$/.exec(location.hash);
    const tab = m && TABS[m[1]] ? m[1] : 'overview';
    let arg = null;
    try { arg = m && m[2] ? decodeURIComponent(m[2]) : null; } catch (e) { arg = null; }
    if (arg !== null && !ID.test(arg)) arg = null;
    stopPolling();
    if (tab !== S.tab || arg !== S.arg) window.scrollTo(0, 0);
    S.tab = tab; S.arg = arg;
    for (const sec of document.querySelectorAll('section[data-view]')) sec.hidden = sec.dataset.view !== tab;
    for (const a of document.querySelectorAll('nav.tabs a')) a.classList.toggle('on', a.dataset.tab === tab);
    TABS[tab](arg);
  }
  window.addEventListener('hashchange', route);
  const go = (tab, arg) => { location.hash = arg ? `#${tab}/${enc(arg)}` : `#${tab}`; };

  // Every 30 s while the tab is visible: the overview (and the counts on the tabs, which come from it).
  setInterval(() => { if (!$('studio').hidden && document.visibilityState === 'visible') refreshOverview(S.tab === 'overview'); }, 30000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !$('studio').hidden && S.tab === 'overview') refreshOverview(true);
  });

  // ------------------------------------------------------------------------------------------------ 1. overview
  const TODO_TAB = { failed_run: 'runs', workflow_review: 'review', whos_who: 'whos-who', pending_claims: 'claims', unsure_clips: 'review', stale_model: 'training' };
  const TODO_LABEL = { failed_run: 'failed run', workflow_review: 'paused workflow', whos_who: "who's who", pending_claims: 'claims', unsure_clips: 'unsure clips', stale_model: 'stale model' };
  const TODO_CLASS = { failed_run: 'failed', workflow_review: 'paused', whos_who: 'warn', pending_claims: 'warn', unsure_clips: 'warn', stale_model: 'muted' };

  function todoHref(t) {
    const anchor = String(t.link || '').split('#')[1] || '';
    const [tab, arg] = anchor.split('/');
    if (TABS[tab] && (arg === undefined || ID.test(arg))) return `#${tab}${arg ? `/${enc(arg)}` : ''}`;
    const fallback = TODO_TAB[t.kind] || 'overview';
    return `#${fallback}${t.match_id && ID.test(t.match_id) ? `/${enc(t.match_id)}` : ''}`;
  }

  function setCount(id, n, hot) {
    const el = $(id);
    el.textContent = n ? String(n) : '';
    el.classList.toggle('hot', !!(n && hot));
  }

  async function refreshOverview(render) {
    let o;
    try { o = await studioGet('/api/studio/overview'); } catch (e) {
      if (render) fail($('ovTodo'), e);
      else if (e.status === 401) lockOut('That key is no longer accepted.');
      return;
    }
    S.overview = o;
    S.caps = o.capabilities || S.caps;
    const sum = (kinds) => (o.todo || []).filter((t) => kinds.includes(t.kind)).reduce((a, t) => a + (t.count || 0), 0);
    setCount('nReview', sum(['unsure_clips', 'workflow_review']), true);
    setCount('nWhos', sum(['whos_who']), true);
    setCount('nClaims', sum(['pending_claims']), true);
    setCount('nRuns', sum(['failed_run']), true);
    if (render) renderOverview(o);
  }

  function loadOverview() {
    put($('ovTodo'), html`<div class="muted">Loading…</div>`);
    refreshOverview(true);
  }

  function tile(label, value, cls) { return html`<div class="tile ${cls || ''}"><b>${label}</b><span>${value}</span></div>`; }

  function meter(label, n, max, text) {
    const p = max ? Math.min(1, (n || 0) / max) : 0;
    const cls = p >= 0.9 ? 'bad' : p >= 0.6 ? 'warn' : '';
    return html`<div class="meter"><span class="muted">${label}</span><span class="track"><span class="fill ${cls}" style="display:block;width:${Math.round(p * 100)}%"></span></span><span class="mono">${text ?? `${num(n)} / ${num(max)}`}</span></div>`;
  }

  function renderOverview(o) {
    $('ovStamp').textContent = `generated ${when(o.generated_at)} · refreshes every 30 s while this tab is visible`;
    const todo = o.todo || [];
    put($('ovTodo'), todo.length ? html`<div class="todo">${todo.map((t) => html`<a href="${todoHref(t)}">
        <span class="n">${t.count ?? ''}</span>
        <span><span class="chip ${TODO_CLASS[t.kind] || 'muted'}">${TODO_LABEL[t.kind] || t.kind}</span> <b class="mono">${t.match_id || ''}</b><br>
          <span class="small">${t.detail}</span> <span class="muted small mono">${t.api || ''}</span></span></a>`)}</div>`
      : html`<div class="empty">Nothing waiting: no failed or paused run, no open Who's who question, no unsure clip without a verdict, and the model is current.</div>`);

    const h = o.health || {}, c = h.cloud || {};
    put($('ovHealth'), html`
      ${tile('Microsoft Foundry', c.foundry ? `on · ${c.model || 'model ?'}` : 'not configured', c.foundry ? 'ok' : 'off')}
      ${tile('Cosmos DB', c.cosmos ? 'on' : 'not configured', c.cosmos ? 'ok' : 'off')}
      ${tile('Azure AI Search', c.search ? 'on' : 'not configured', c.search ? 'ok' : 'off')}
      ${tile('Azure MCP Server', h.azure_mcp ? 'azmcp installed' : 'not installed', h.azure_mcp ? 'ok' : 'off')}
      ${tile('Tracing', h.tracing ? 'App Insights connected' : 'off', h.tracing ? 'ok' : 'off')}
      ${tile('Librarian', h.librarian || '–')}
      ${tile('Writes', h.writes || '–', h.writes === 'read-only' ? 'warn' : '')}
      ${tile('Image', h.image || 'not set (IMAGE_TAG)', h.image ? '' : 'off')}
      ${tile('Revision', h.revision || 'not set (local)', h.revision ? '' : 'off')}
      ${tile('Version', h.version || '–')}
      ${tile('API', h.ok ? 'ok' : 'not ok', h.ok ? 'ok' : 'bad')}`);

    const u = o.usage || {}, lim = u.limits || {};
    put($('ovUsage'), html`
      ${u.foundry ? NOTHING : html`<div class="note small">Foundry is not configured here, so Ask and Foundry Chat are answered by rules.
        Each of those requests still counts against these limits.</div>`}
      ${meter('last hour', u.last_hour, lim.total_per_hour)}
      ${meter('last day', u.last_day, lim.total_per_day)}
      ${meter('in flight', u.in_flight, lim.concurrent)}
      ${kv([['last minute', num(u.last_minute)], ['visitors (hour)', num(u.visitors_last_hour)],
            ['remaining', `${num((u.remaining || {}).hour)} this hour · ${num((u.remaining || {}).day)} today`],
            ['per visitor', `${num(lim.per_visitor_per_min)}/min · ${num(lim.per_visitor_per_hour)}/hour`]])}
      <p class="muted small">${u.scope || ''}</p>`);

    const d = o.data || {}, cos = d.cosmos || {}, se = d.search || {};
    put($('ovData'), html`
      <table class="grid"><tr><th>Store</th><th>Documents</th></tr>
      ${cos.configured ? Object.entries(cos.containers || {}).map(([k, n]) => html`<tr><td>Cosmos DB <span class="mono">${cos.database || ''}/${k}</span></td><td class="mono">${n === null ? '?' : num(n)}</td></tr>`)
        : html`<tr><td>Cosmos DB</td><td class="muted">not configured</td></tr>`}
      ${se.configured ? html`<tr><td>AI Search <span class="mono">${se.index || ''}</span></td><td class="mono">${se.documents === null ? '?' : num(se.documents)}</td></tr>`
        : html`<tr><td>AI Search</td><td class="muted">not configured</td></tr>`}
      </table>
      ${cos.error ? html`<div class="err small">Cosmos DB: ${cos.error}</div>` : NOTHING}
      ${se.error ? html`<div class="err small">AI Search: ${se.error}</div>` : NOTHING}
      <p class="muted small">counted ${when(d.checked_at)}; cached 60 s</p>`);

    const ca = o.cache || {}, pr = ca.prerender || {};
    put($('ovCache'), html`
      ${kv([['files', `${num(ca.files)} · ${bytes(ca.bytes)}`], ['render slots', num(ca.render_concurrency)]])}
      ${pr.enabled ? html`${meter('prerender', pr.rendered, pr.total, `${num(pr.rendered)} / ${num(pr.total)}${pr.failed ? ` · ${pr.failed} failed` : ''}`)}
        <p class="muted small">${pr.running ? 'rendering now' : pr.finished_at ? `finished ${when(pr.finished_at)}` : 'not started'}${pr.started_at ? ` · started ${when(pr.started_at)}` : ''}</p>`
        : html`<p class="muted small">Prerender is off (REGISTA_PRERENDER is not 1): clips render on first request.</p>`}
      ${(ca.matches || []).length ? html`<table class="grid"><tr><th>Match</th><th>Files</th><th>Size</th><th>Partial</th></tr>
        ${ca.matches.map((m) => html`<tr><td class="mono">${m.match_id}</td><td>${num(m.files)}</td><td>${bytes(m.bytes)}</td><td class="${m.partial ? 'warn' : 'muted'}">${num(m.partial)}</td></tr>`)}</table>` : NOTHING}`);

    const caps = o.capabilities || {};
    put($('ovCaps'), html`${Object.entries(caps).map(([k, v]) => tile(k.replace(/_/g, ' '), v === true ? 'yes' : v === false ? 'no' : v, v === true ? 'ok' : v === false ? 'off' : ''))}`);
  }
  $('ovRefresh').onclick = () => refreshOverview(true);

  // ------------------------------------------------------------------------------------------------ 2. review queue
  const previewer = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const v = e.target; previewer.unobserve(v);
      const src = apiPath(v.dataset.src);
      if (src) { v.preload = 'metadata'; v.src = src; }
    }
  }, { rootMargin: '200px' }) : null;
  function lazyVideos(root) {
    for (const v of root.querySelectorAll('video[data-src]')) {
      if (previewer) previewer.observe(v);
      else { const src = apiPath(v.dataset.src); if (src) v.src = src; }
    }
  }

  function scorePair(watch, prior) {
    if (prior === null || prior === undefined) return html`<span class="score">${score(watch)}</span>`;
    const d = watch - prior;
    return html`<span class="score">${score(watch)} <span class="muted">vs prior ${score(prior)}</span> <span class="delta ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d >= 0 ? '+' : ''}${d.toFixed(2)}</span></span>`;
  }

  function verdictLine(v) {
    if (!v) return NOTHING;
    return html`<span class="${v.keep ? 'ok' : 'bad'}"><b>${v.keep ? 'Kept' : 'Dropped'}</b>${v.annotator ? ` by ${v.annotator}` : ''}${v.created_at ? ` · ${when(v.created_at)}` : ''}</span>${v.note ? html` <span class="muted small">“${v.note}”</span>` : NOTHING}`;
  }

  function clipCard(mid, c) {
    const lb = c.label || {};
    const src = apiPath(c.video_url);
    return html`<div class="card${c.verdict ? ' decided' : ''}" data-match="${mid}" data-clip="${c.id}">
      ${src ? html`<video preload="none" controls muted playsinline data-src="${src}"></video>` : html`<div class="novideo">no video on this replica (${c.source || 'cosmos'})</div>`}
      <div class="body">
        <span class="title">${lb.title || c.id}</span>
        <span class="muted small mono">${c.id} · ${R.reasonLabel(c.reason)} · ${clock(c.t)}–${clock(c.t_end)} · ${lb.model || '?'}</span>
        <span>${scorePair(lb.watchability, lb.prior_watchability)}</span>
        ${c.review ? html`<span class="why">Unsure: ${c.review}</span>` : NOTHING}
        <span>${tags(lb.tags)}</span>
        <span class="small">${lb.explanation || ''}</span>
      </div>
      <div class="acts" data-acts>
        ${c.verdict ? verdictLine(c.verdict) : html`<button class="keep" data-v="keep"${w()}>Keep</button><button class="drop" data-v="drop"${w()}>Drop</button>`}
        <span class="small" data-msg></span>
      </div></div>`;
  }

  function pausedBlock(mid, p) {
    const items = (p.request && p.request.items) || [];
    S.pending.set(`${mid}|${p.request_id}`, p);
    return html`<div class="paused" data-match="${mid}" data-req="${p.request_id}">
      <div class="bar"><b>Workflow paused: ${(p.request && p.request.question) || 'waiting for a human'}</b>
        <span class="muted small mono">${mid} · request ${p.request_id}</span>
        <a class="small" href="#runs/${enc(mid)}">run trace</a></div>
      <div class="tableWrap"><table class="grid"><tr><th>Clip</th><th>Title</th><th>Score / prior</th><th>Why unsure</th><th>Verdict</th></tr>
        ${items.map((it) => html`<tr><td class="mono">${it.clip_id}<br><span class="muted">${clock(it.t)}–${clock(it.t_end)}</span></td>
          <td>${it.title || ''}<br>${tags(it.tags)}</td><td>${scorePair(it.watchability, it.prior_watchability)}</td><td class="small">${it.reason || ''}</td>
          <td><select data-clip="${it.clip_id}" aria-label="Verdict"><option value="">no verdict</option><option value="keep">keep</option><option value="drop">drop</option></select></td></tr>`)}
      </table></div>
      <div class="bar" style="margin-top:8px"><button data-act="resume"${w()}>Send verdicts and resume the workflow</button><span class="small" data-msg></span></div>
      <div data-result></div></div>`;
  }

  // Flagged clips first (the Label agent asked), then the rest in match order; decided ones last.
  const reviewOrder = (a, b) => (!!a.verdict - !!b.verdict) || (!!b.review - !!a.review) || ((a.t || 0) - (b.t || 0));

  // How far the verdicts are from a retrain, under the queue's controls.
  async function reviewProgress() {
    let f;
    try { f = await studioGet('/api/feedback'); } catch (e) { $('rvProgress').textContent = ''; return; }
    const n = f.clips_reviewed || 0;
    put($('rvProgress'), n >= MIN_VERDICTS
      ? html`${plural(n, 'clip')} reviewed: enough to retrain. <a href="#training">Retrain in Training</a>.`
      : html`${plural(n, 'clip')} reviewed. The watchability model retrains from ${MIN_VERDICTS}: ${S.rvView === 'all' ? 'keep or drop' : html`<a href="#" data-view-all>show all clips</a> and keep or drop`} ${MIN_VERDICTS - n} more.`);
  }

  async function loadReview(arg) {
    const sel = $('rvMatch');
    $('rvView').value = S.rvView;
    $('rvHeading').textContent = S.rvView === 'all' ? 'All clips (flagged unsure first)' : 'Clips flagged unsure';
    put($('rvPaused'), NOTHING);
    put($('rvClips'), html`<div class="muted">Loading…</div>`);
    reviewProgress();
    let all;
    try { all = await matches(); } catch (e) { fail($('rvClips'), e); return; }
    put(sel, options(all.map((m) => ({ value: m.match_id, label: matchLabel(m) })), arg || '', 'All matches'));
    const targets = arg ? all.filter((m) => m.match_id === arg) : all;
    if (arg && !targets.length) { fail($('rvClips'), { detail: `no match ${arg}` }); return; }
    const showDecided = $('rvDecided').checked, everyClip = S.rvView === 'all';
    S.pending.clear();
    const results = await Promise.all(targets.map(async (m) => {
      const [rv, cl] = await Promise.allSettled([
        m.source === 'local' ? studioGet(`/api/matches/${enc(m.match_id)}/review`) : Promise.resolve({ pending: [] }),
        studioGet(`/api/matches/${enc(m.match_id)}/clips`)]);
      return { m, rv, cl };
    }));
    if (results.some((r) => (r.rv.status === 'rejected' && r.rv.reason.status === 401) || (r.cl.status === 'rejected' && r.cl.reason.status === 401))) {
      lockOut('That key is no longer accepted.'); return;
    }
    const paused = [];
    for (const r of results) {
      if (r.rv.status === 'fulfilled') for (const p of r.rv.value.pending || []) paused.push(pausedBlock(r.m.match_id, p));
    }
    put($('rvPaused'), paused.length ? html`<h3>Paused workflow reviews</h3>${paused}` : NOTHING);

    let total = 0;
    const showAll = html` <a href="#" data-view-all>Show all clips</a> to keep or drop any of them.`;
    const groups = results.map((r) => {
      if (r.cl.status === 'rejected') return html`<h3 class="mono">${r.m.match_id}</h3><div class="err">${errText(r.cl.reason)}</div>`;
      const list = r.cl.value.filter((c) => (everyClip || c.review) && (showDecided || !c.verdict)).sort(reviewOrder);
      total += list.filter((c) => !c.verdict).length;
      if (!list.length) {
        if (!arg) return NOTHING;
        const none = everyClip ? (r.cl.value.length ? 'Every clip of this match has a verdict.' : 'This match has no clips yet.')
          : `No clip of this match is flagged unsure${showDecided ? '' : ' without a verdict'}.`;
        return html`<h3 class="mono">${r.m.match_id}</h3><div class="empty">${none}${everyClip ? NOTHING : showAll}</div>`;
      }
      const flagged = list.filter((c) => c.review && !c.verdict).length;
      return html`<h3><span class="mono">${r.m.match_id}</span> · ${plural(list.length, 'clip')}${everyClip && flagged ? ` · ${flagged} flagged unsure` : ''}</h3>
        <div class="cards">${list.map((c) => clipCard(r.m.match_id, c))}</div>`;
    });
    const nothing = everyClip ? html`<div class="empty">Every clip has a verdict. Tick “show decided” to see them.</div>`
      : html`<div class="empty">Nothing to review: every clip flagged unsure has a verdict.${showAll}</div>`;
    put($('rvClips'), total || showDecided || arg ? html`${groups}` : html`${groups}${nothing}`);
    lazyVideos($('rvClips'));
  }

  // "show all clips" links, wherever they are rendered (the queue, its progress line, the Training tab)
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-view-all]');
    if (!a) return;
    e.preventDefault();
    S.rvView = 'all';
    if (S.tab === 'review') loadReview(S.arg); else go('review', a.dataset.viewAll || null);
  });

  function annotator() {
    const a = $('rvAnnotator').value.trim() || 'zaid';
    if (!ANNOTATOR.test(a)) throw new Error('Reviewer: letters, digits, space, _ . - (at most 40).');
    return a;
  }

  $('rvClips').addEventListener('click', async (e) => {
    const b = e.target.closest('button[data-v]');
    if (!b || b.disabled) return;
    const card = b.closest('.card'), acts = card.querySelector('[data-acts]'), msg = card.querySelector('[data-msg]');
    let who;
    try { who = annotator(); } catch (err) { msg.textContent = err.message; return; }
    for (const x of acts.querySelectorAll('button')) x.disabled = true;
    msg.textContent = 'Saving…';
    try {
      const out = await write(`/api/matches/${enc(card.dataset.match)}/clips/${enc(card.dataset.clip)}/verdict`, { verdict: b.dataset.v, annotator: who });
      const a = out.annotation || {};
      card.classList.add('decided');
      put(acts, html`${verdictLine({ keep: b.dataset.v === 'keep', annotator: a.annotator || who })}
        <span class="muted small">${a.id || ''} · ${out.stored_in_cosmos ? 'stored in Cosmos DB' : 'stored locally'}</span>`);
      refreshOverview(false);
      reviewProgress();
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      for (const x of acts.querySelectorAll('button')) x.disabled = !canWrite();
      msg.textContent = errText(err);
    }
  });

  $('rvPaused').addEventListener('click', async (e) => {
    const b = e.target.closest('button[data-act="resume"]');
    if (!b || b.disabled) return;
    const box = b.closest('.paused'), msg = box.querySelector('[data-msg]');
    let who;
    try { who = annotator(); } catch (err) { msg.textContent = err.message; return; }
    const verdicts = [...box.querySelectorAll('select[data-clip]')].filter((s) => s.value).map((s) => ({ clip_id: s.dataset.clip, verdict: s.value }));
    if (!verdicts.length && !confirm('Resume the workflow without any verdict?')) return;
    b.disabled = true; msg.textContent = 'Resuming the workflow from its checkpoint…';
    try {
      const out = await write(`/api/matches/${enc(box.dataset.match)}/review`, { request_id: box.dataset.req, verdicts, annotator: who });
      msg.textContent = 'Done.';
      put(box.querySelector('[data-result]'), runSummary(out));
      refreshOverview(false);
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      b.disabled = !canWrite(); msg.textContent = errText(err);
    }
  });

  $('rvMatch').onchange = () => go('review', $('rvMatch').value);
  $('rvView').onchange = () => { S.rvView = $('rvView').value === 'all' ? 'all' : 'flagged'; loadReview(S.arg); };
  $('rvDecided').onchange = () => loadReview(S.arg);
  $('rvRefresh').onclick = async () => { S.matches = null; loadReview(S.arg); };

  // ------------------------------------------------------------------------------------------------ 3. who's who
  // Vision matches, and whether each still has the identity result an answer rewrites (identity_result false: a copy
  // without it, like the live app's; answering there would end in a 409 after the work of answering).
  async function visionMatches() {
    const runs = await studioGet('/api/studio/runs');
    const vision = runs.filter((r) => r.kind === 'vision');
    for (const r of vision) if (r.identity_result === false) S.noIdentity.add(r.match_id);
    return vision.map((r) => r.match_id);
  }

  const NO_IDENTITY = "Read-only here: answers need the vision layer's identity result, which stays on the machine that ran it. "
    + 'The questions and crops are shown so you can see what the identity agent asks.';
  const canAnswer = (mid) => canWrite() && !S.noIdentity.has(mid);
  const wa = (mid) => (canAnswer(mid) ? NOTHING : html` disabled title="${canWrite() ? NO_IDENTITY : whyNoWrite()}"`);

  // What the last save did, shown above the reloaded list (the answered cards are gone from it).
  function savedBox(out) {
    return html`<div class="okbox">Saved ${plural(out.answers, 'answer')} by ${out.annotator}: ${plural((out.renamed || []).length, 'track')} renamed,
      ${plural((out.cutaways || []).length, 'replay')} set, and possession, events and clips recomputed.${out.next_questions ? ` ${plural(out.next_questions, 'new question')}.` : ''}</div>
      <details><summary>what the server returned</summary>${jsonBlock(out)}</details>`;
  }

  function dropCrops() { for (const u of S.crops) URL.revokeObjectURL(u); S.crops = []; }

  async function loadWhos(arg) {
    const body = $('wwBody');
    put(body, html`<div class="muted">Loading…</div>`);
    dropCrops();
    let ids;
    try { ids = await visionMatches(); } catch (e) { fail(body, e); return; }
    if (arg && !ids.includes(arg)) ids.unshift(arg);
    put($('wwMatch'), options(ids.map((id) => ({ value: id, label: id })), arg || ids[0] || '', ids.length ? null : 'no vision match'));
    const mid = arg || ids[0];
    if (!mid) { put(body, html`<div class="empty">No match on this deployment was written by the vision layer.</div>`); return; }
    let out;
    try { out = await studioGet(`/api/matches/${enc(mid)}/identity-review`); } catch (e) { fail(body, e); return; }
    S.whos = { mid, items: out.items || [], teams: out.teams || {}, answers: {} };
    renderWhos(out);
  }

  function playerName(pid) {
    for (const ps of Object.values(S.whos.teams)) { const p = ps.find((x) => x.player_id === pid); if (p) return `${p.name} (${p.kit_number})`; }
    return pid;
  }

  function renderWhos(out) {
    const { mid, items, teams } = S.whos;
    const body = $('wwBody');
    dropCrops();
    const done = S.whosDone && S.whosDone.mid === mid ? savedBox(S.whosDone.out) : NOTHING;
    S.whosDone = null;
    if (!items.length) { put(body, html`${done}<div class="empty">No open identity questions for this match.</div>`); return; }
    const off = wa(mid);
    put(body, html`${done}${S.noIdentity.has(mid) ? html`<div class="note small">${NO_IDENTITY}</div>` : NOTHING}
      <p><b>${plural(items.length, 'call')} the identity agent is unsure of</b> <span class="muted small mono">${mid}</span></p>
      <div class="qgrid">${items.map((it, i) => {
        const pool = it.kind === 'track' ? (teams[it.team_id] || []) : Object.values(teams).flat();
        const now = it.kind === 'track' ? (it.current ? playerName(it.current) : 'unnamed') : ((it.current || []).length ? it.current.map(playerName).join(', ') : 'nobody');
        return html`<div class="q" data-i="${i}">
          <img class="crop" alt="${it.question || ''}" data-crop="${apiPath(it.image_url) || ''}">
          <b>${it.question || ''}</b>
          <span class="muted small mono">${it.item_id} · ${it.kind}${it.segment_kind ? ` (${it.segment_kind})` : ''} · ${clock(it.t0)}–${clock(it.t1)}${typeof it.confidence === 'number' ? ` · conf ${score(it.confidence)}` : ''}</span>
          <span class="small">now: ${now}</span>
          <div class="opts">
            ${(it.candidates || []).map((c) => html`<button type="button" class="opt" data-pid="${c.player_id}"${off}>${c.name} (${c.kit_number}) <span class="p">${Math.round((c.p || 0) * 100)}%</span></button>`)}
            ${it.kind === 'track' ? html`<button type="button" class="opt" data-pid="not_a_player"${off}>Not a player</button><button type="button" class="opt" data-pid="unknown"${off}>Can't tell</button>`
              : html`<button type="button" class="opt" data-pid="__nobody"${off}>Nobody</button>`}
          </div>
          <select aria-label="Another player"${off}><option value="">${it.kind === 'track' ? 'Someone else…' : 'Add a player…'}</option>
            ${pool.map((p) => html`<option value="${p.player_id}">${p.name} (${p.kit_number})</option>`)}</select>
        </div>`;
      })}</div>
      <div class="bar" style="margin-top:12px"><button id="wwSave"${off}>Save answers and recompute the match</button>
        <span class="small" id="wwMsg"></span></div>
      <div id="wwResult"></div>`);
    for (const img of body.querySelectorAll('img[data-crop]')) {
      const path = apiPath(img.dataset.crop);
      if (!path) continue;
      R.authedObjectUrl(path).then((u) => { S.crops.push(u); img.src = u; }).catch(() => { img.alt = 'crop unavailable'; });
    }
  }

  function markWhos(i) {
    const it = S.whos.items[i], a = S.whos.answers[it.item_id];
    for (const b of $('wwBody').querySelectorAll(`.q[data-i="${i}"] .opt`)) {
      const pid = b.dataset.pid;
      b.classList.toggle('on', !!a && (it.kind === 'track' ? a.player_id === pid : (pid === '__nobody' ? a.players.length === 0 : a.players.includes(pid))));
    }
  }
  function answerWhos(i, pid, toggle) {
    const it = S.whos.items[i];
    if (it.kind === 'track') S.whos.answers[it.item_id] = { item_id: it.item_id, player_id: pid };
    else {
      const a = S.whos.answers[it.item_id] || { item_id: it.item_id, players: [] };
      if (pid === '__nobody') a.players = [];
      else if (a.players.includes(pid)) { if (toggle) a.players = a.players.filter((x) => x !== pid); }
      else a.players = [...a.players, pid].slice(0, 6);
      S.whos.answers[it.item_id] = a;
    }
    markWhos(i);
  }

  $('wwBody').addEventListener('click', async (e) => {
    const opt = e.target.closest('.opt');
    if (opt && opt.disabled) return;
    if (opt) { answerWhos(+opt.closest('.q').dataset.i, opt.dataset.pid, true); return; }
    if (e.target.id !== 'wwSave' || e.target.disabled) return;
    const answers = Object.values(S.whos.answers);
    if (!answers.length) { $('wwMsg').textContent = 'Pick at least one answer.'; return; }
    e.target.disabled = true;
    $('wwMsg').textContent = 'Correcting identity and recomputing possession, events and clips…';
    try {
      const mid = S.whos.mid;
      const out = await write(`/api/matches/${enc(mid)}/identity-review`, { answers, annotator: annotator() });
      S.matches = null;
      refreshOverview(false);
      S.whosDone = { mid, out };  // the reloaded list shows it on top; the answered cards are gone, new questions appear
      if (S.tab === 'whos-who' && S.arg === mid) loadWhos(mid); else go('whos-who', mid);
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      $('wwMsg').textContent = '';
      if (err.status === 409 && /identity result/i.test(errText(err))) {
        S.noIdentity.add(S.whos.mid);  // read-only for the rest of the session, said up front from now on
        renderWhos({});
        return;
      }
      e.target.disabled = !canAnswer(S.whos.mid);
      fail($('wwResult'), err);
    }
  });
  $('wwBody').addEventListener('change', (e) => {
    const sel = e.target.closest('.q select');
    if (sel && sel.value) answerWhos(+sel.closest('.q').dataset.i, sel.value, false);
  });
  $('wwMatch').onchange = () => go('whos-who', $('wwMatch').value);
  $('wwRefresh').onclick = () => loadWhos(S.arg);

  // ------------------------------------------------------------------------------------------------ 4. training
  async function loadTraining() {
    put($('trFeedback'), html`<div class="muted">Loading…</div>`);
    put($('trVision'), html`<div class="muted">Loading…</div>`);
    try { renderFeedback(await studioGet('/api/feedback')); } catch (e) { fail($('trFeedback'), e); }
    let jobs = null, vision = [];
    try { [jobs, vision] = await Promise.all([studioGet('/api/studio/jobs'), visionMatches()]); } catch (e) { fail($('trVision'), e); return; }
    renderVision(jobs, vision);
  }

  function evaluationTable(ev) {
    if (!ev || !ev.n) return html`<div class="empty">No verdicts yet: agreement is measured once people have kept or dropped clips.</div>`;
    const scorers = Object.entries(ev).filter(([, v]) => v && typeof v === 'object' && 'agreement' in v);
    const NAMES = { as_reviewed: 'label as reviewed', rules_prior: 'rules prior' };
    return html`<table class="grid"><tr><th>Scorer</th><th>Agreement with people</th><th>Mean abs. error</th></tr>
      ${scorers.map(([k, v]) => html`<tr><td>${NAMES[k] || k}</td><td class="mono">${pct(v.agreement)}</td><td class="mono">${score(v.mean_abs_error)}</td></tr>`)}</table>
      <p class="muted small">on ${plural(ev.n, 'reviewed clip')}${ev.as_reviewed_by_model ? `; labelled by ${Object.entries(ev.as_reviewed_by_model).map(([m, n]) => `${m} (${n})`).join(', ')}` : ''}</p>`;
  }

  function renderFeedback(f) {
    const m = f.model || {};
    const feats = Object.entries(m.features || {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const metrics = Object.entries(m.metrics || {}).filter(([, v]) => v === null || typeof v !== 'object');
    put($('trFeedback'), html`
      ${kv([['verdicts', num(f.verdicts)], ['clips reviewed', `${num(f.clips_reviewed)} (${num(f.keep)} kept, ${num((f.clips_reviewed || 0) - (f.keep || 0))} dropped)`],
            ['annotators', (f.annotators || []).length ? f.annotators.join(', ') : 'nobody yet'],
            ['model', f.model_name || 'none trained yet: the Label agent uses the rules prior'],
            ['version', m.version ?? '–'], ['trained', when(m.trained_at)], ['samples', num(m.n_samples)], ['writes', f.writes || '–']])}
      ${metrics.length ? html`<h3>Training metrics</h3>${kv(metrics.map(([k, v]) => [k, typeof v === 'number' ? (Number.isInteger(v) ? num(v) : score(v)) : v]))}` : NOTHING}
      <h3>Agreement per scorer</h3>${evaluationTable(f.evaluation)}
      ${feats.length ? html`<details><summary>${feats.length} feature weights</summary><table class="grid">${feats.map(([k, v]) => html`<tr><td class="mono">${k}</td><td class="mono">${score(v)}</td></tr>`)}
        <tr><td class="mono muted">intercept</td><td class="mono">${score(m.intercept)}</td></tr></table></details>` : NOTHING}
      <div class="bar" style="margin-top:10px"><button id="trRetrain"${w()}>Retrain from every verdict</button><span class="small" id="trMsg"></span></div>
      ${(f.clips_reviewed || 0) < MIN_VERDICTS ? html`<p class="small muted">Retraining needs ${MIN_VERDICTS} reviewed clips; ${num(f.clips_reviewed || 0)} so far.
        <a href="#" data-view-all>Keep or drop ${MIN_VERDICTS - (f.clips_reviewed || 0)} more in the Review queue</a>.</p>` : NOTHING}
      <div id="trResult"></div>`);
    $('trRetrain').onclick = async () => {
      $('trRetrain').disabled = true; $('trMsg').textContent = 'Training…';
      try {
        const out = await write('/api/feedback/train');
        refreshOverview(false);
        try { renderFeedback(await studioGet('/api/feedback')); } catch (e) { /* the result below still shows */ }
        put($('trResult'), html`<div class="okbox">Trained ${out.model_name}. The Label agent uses it as its prior from the next run.</div>
          <h3>Training metrics</h3>${jsonBlock(out.metrics)}`);
      } catch (e) {
        $('trRetrain').disabled = !canWrite(); $('trMsg').textContent = '';
        fail($('trResult'), e);
      }
    };
  }

  function renderVision(jobs, vision) {
    const caps = S.caps;
    put($('trVision'), html`
      ${kv([['vision models', caps.vision_models ? 'found on this machine' : 'not here'], ['jobs', jobs.available ? 'available' : 'unavailable'],
            ['vision matches', vision.length ? vision.join(', ') : 'none']])}
      ${jobs.available ? NOTHING : html`<div class="note small" style="margin-top:8px">${jobs.reason || 'Vision jobs are unavailable here.'}</div>`}
      <h3>Learn from Who's who answers</h3>
      <p class="muted small">${(jobs.kinds && jobs.kinds['learn-from-reviews'] && jobs.kinds['learn-from-reviews'].help) || 'fine-tune the kit-number reader on answered reviews'}.
        Runs as a job; follow it in <a href="#jobs">Jobs</a>.</p>
      <form id="trLearn" class="jobform">
        <div class="opts">${vision.map((id) => html`<label class="small"><input type="checkbox" value="${id}" checked> <span class="mono">${id}</span></label>`)}</div>
        <div class="bar"><button${jobs.available && !jobs.running ? w() : html` disabled title="${jobs.running ? 'A job is running.' : jobs.reason || 'unavailable'}"`}>Start learn-from-reviews</button>
          <span class="small" id="trLearnMsg"></span></div>
      </form>
      ${jobs.running ? html`<p class="small">Running now: <a href="#jobs/${enc(jobs.running.id)}" class="mono">${jobs.running.id}</a></p>` : NOTHING}`);
    $('trLearn').onsubmit = async (e) => {
      e.preventDefault();
      const ids = [...$('trLearn').querySelectorAll('input:checked')].map((x) => x.value);
      if (!ids.length) { $('trLearnMsg').textContent = 'Pick at least one match.'; return; }
      try {
        const job = await write('/api/studio/jobs', { kind: 'learn-from-reviews', args: { match_ids: ids } });
        go('jobs', job.id);
      } catch (err) { $('trLearnMsg').textContent = errText(err); }
    };
  }
  $('trRefresh').onclick = () => loadTraining();

  // ------------------------------------------------------------------------------------------------ 5. runs and upload
  function runSummary(out) {
    if (!out || typeof out !== 'object') return NOTHING;
    const statuses = Object.entries(out.statuses || {});
    const mid = out.match_id && ID.test(out.match_id) ? out.match_id : null;
    return html`<div class="panel" style="margin-top:8px">
      <div class="bar"><b>Run summary</b> ${chip(out.paused ? 'paused' : out.pipeline_ok ? 'ok' : 'failed')} <span class="mono">${out.match_id || ''}</span>
        <span class="muted small">${out.engine || ''}</span></div>
      ${kv([['players', (out.players || []).join(', ') || '–'], ['clips', Object.entries(out.clips || {}).map(([p, n]) => `${p}: ${n}`).join(', ') || '–'],
            ['label models', (out.label_models || []).join(', ') || '–'], ['Cosmos DB', out.cosmos ? JSON.stringify(out.cosmos) : '–'],
            ['Search index', out.search_index ? JSON.stringify(out.search_index) : '–']])}
      ${statuses.length ? html`<div class="tableWrap"><table class="grid"><tr><th>Agent</th><th>Status</th></tr>${statuses.map(([a, s]) => html`<tr><td>${a}</td><td>${chip(s)}</td></tr>`)}</table></div>` : NOTHING}
      ${(out.dead_letters || []).length ? html`<div class="err small">Dead letters: ${out.dead_letters.map((d) => `${d.agent}: ${d.error}`).join(' · ')}</div>` : NOTHING}
      ${out.paused && mid ? html`<div class="note small">The workflow paused for a human: <a href="#review/${enc(mid)}">answer it in the Review queue</a>.</div>` : NOTHING}
      ${out.review_log ? html`<details><summary>review log</summary>${jsonBlock(out.review_log)}</details>` : NOTHING}
      ${mid ? html`<p class="small"><a href="#runs/${enc(mid)}">open the run</a> · <a href="#review/${enc(mid)}">review queue</a> · <a href="/">see it on Home</a></p>` : NOTHING}
    </div>`;
  }

  async function loadRuns(arg) {
    put($('ruList'), html`<div class="muted">Loading…</div>`);
    put($('ruDetail'), NOTHING);
    let runs;
    try { runs = await studioGet('/api/studio/runs'); } catch (e) { fail($('ruList'), e); return; }
    const failed = runs.filter((r) => r.status === 'failed').length;
    setCount('nRuns', failed, true);
    const ran = runs.filter((r) => r.has_run).length;
    put($('ruList'), runs.length ? html`${ran ? NOTHING : html`<div class="empty">No workflow runs on this server yet: uploads and jobs appear here.
        The matches below came with the app, so they have no run recorded on this server.</div>`}<div class="tableWrap"><table class="grid">
      <tr><th>Match</th><th>Kind</th><th>Status</th><th>Finished</th><th>Agents</th><th>Dead letters</th><th>Label models</th><th>Review</th><th>Source</th></tr>
      ${runs.map((r) => {
        const ok = (r.agents || []).filter((a) => a.status === 'ok').length;
        return html`<tr class="click${r.match_id === arg ? ' sel' : ''}" data-match="${r.match_id}">
          <td class="mono">${r.match_id}</td><td class="nowrap">${r.kind || '–'}</td><td>${chip(r.status)}</td><td class="small">${r.finished_at ? when(r.finished_at) : '–'}</td>
          <td>${(r.agents || []).length ? `${ok} / ${r.agents.length} ok` : '–'}</td>
          <td class="${(r.dead_letters || []).length ? 'bad' : 'muted'}">${num((r.dead_letters || []).length)}</td>
          <td class="small">${Object.entries(r.label_models || {}).map(([m, n]) => `${m} (${n})`).join(', ') || '–'}</td>
          <td class="small">${(r.review || {}).pending_items ? `${plural(r.review.pending_items, 'clip')} waiting` : '–'}</td>
          <td class="small">${r.source || ''}</td></tr>`;
      })}</table></div>` : html`<div class="empty">No workflow runs on this server yet: uploads and jobs appear here.</div>`);
    if (arg) loadRunDetail(arg);
  }

  $('ruList').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-match]');
    if (tr) go('runs', tr.dataset.match);
  });

  async function loadRunDetail(mid) {
    const el = $('ruDetail');
    put(el, html`<div class="muted">Loading ${mid}…</div>`);
    let r;
    try { r = await studioGet(`/api/studio/runs/${enc(mid)}`); } catch (e) { fail(el, e); return; }
    const rv = r.review || {};
    put(el, html`<h3>Run · <span class="mono">${r.match_id}</span> ${chip(r.status)}</h3>
      ${kv([['kind', r.kind || '–'], ['finished', when(r.finished_at)], ['source', r.source || '–'],
            ['label models', Object.entries(r.label_models || {}).map(([m, n]) => `${m}: ${plural(n, 'label')}`).join(', ') || '–'],
            ['review', rv.pending_requests ? `${plural(rv.pending_requests, 'request')}, ${plural(rv.pending_items, 'clip')} waiting` : 'nothing waiting']])}
      ${rv.pending_requests ? html`<p class="small"><a href="#review/${enc(r.match_id)}">Answer it in the Review queue</a></p>` : NOTHING}
      ${r.has_run ? NOTHING : html`<div class="note small" style="margin-top:8px">No pipeline run is recorded on this replica for this match.
        Runs are kept in the match's agents/ folder, which the container image does not ship; a match uploaded here gets one.</div>`}
      ${(r.agents || []).length ? html`<h3>Agents</h3><div class="tableWrap"><table class="grid"><tr><th>Agent</th><th>Status</th><th>Attempts</th><th>Time</th><th>Error / note</th></tr>
        ${r.agents.map((a) => html`<tr><td>${a.agent}</td><td>${chip(a.status)}</td><td>${num(a.attempts)}</td><td class="mono">${ms(a.elapsed_ms)}</td>
          <td class="small">${a.error ? html`<span class="bad">${a.error}</span>` : NOTHING}${a.note ? html` <span class="muted">${a.note}</span>` : NOTHING}</td></tr>`)}</table></div>` : NOTHING}
      ${(r.dead_letters || []).length ? html`<h3>Dead letters</h3><table class="grid"><tr><th>Agent</th><th>Error</th><th>Attempts</th><th>At</th></tr>
        ${r.dead_letters.map((d) => html`<tr><td>${d.agent}</td><td class="bad small">${d.error}</td><td>${num(d.attempts)}</td><td class="small">${when(d.at)}</td></tr>`)}</table>` : NOTHING}
      ${rv.log ? html`<details><summary>review log</summary>${jsonBlock(rv.log)}</details>` : NOTHING}
      ${(r.rows || []).length ? html`<details><summary>every attempt (${r.rows.length} trace rows)</summary><div class="tableWrap"><table class="grid">
        <tr><th>At</th><th>Agent</th><th>Attempt</th><th>Status</th><th>Time</th><th>Error / note</th></tr>
        ${r.rows.map((x) => html`<tr><td class="small mono">${x.at || ''}</td><td>${x.agent}</td><td>${num(x.attempt)}</td><td>${chip(x.status)}</td><td class="mono">${ms(x.elapsed_ms)}</td>
          <td class="small">${x.error ? html`<span class="bad">${x.error}</span>` : NOTHING} <span class="muted">${x.note || ''}</span></td></tr>`)}</table></div></details>` : NOTHING}`);
  }
  $('ruRefresh').onclick = () => { S.matches = null; loadRuns(S.arg); };

  // Upload: drop or pick events.jsonl (+ tracks.jsonl); the player list comes from the match header on the file's first line.
  const up = { events: null, tracks: null, header: null };
  async function setUploadFile(kind, file) {
    up[kind] = file || null;
    if (kind !== 'events') return;
    up.header = null;
    const sel = $('upPlayer');
    if (!file) { put(sel, html`<option value="">pick events.jsonl first</option>`); sel.disabled = true; return; }
    try {
      const text = await file.slice(0, 32 * 1024 * 1024).text();
      const lines = text.split('\n');
      const h = JSON.parse(lines[0]);
      if (!h || h.type !== 'match' || !Array.isArray(h.players)) throw new Error('the first line is not a match header');
      up.header = h;
      const team = Object.fromEntries((h.teams || []).map((t) => [t.team_id, t.short_name || t.team_id]));
      const players = [...h.players].sort((a, b) => (b.starter ? 1 : 0) - (a.starter ? 1 : 0));
      // The file's featured player: the one with the most possessions and events (as the cut-clips job picks), not
      // the first starter, who is usually the goalkeeper.
      const active = new Map();
      for (const line of lines.slice(1)) {
        if (!line.includes('"player_id"')) continue;
        let r; try { r = JSON.parse(line); } catch (e) { continue; }
        if (r && (r.type === 'possession' || r.type === 'event') && r.player_id) active.set(r.player_id, (active.get(r.player_id) || 0) + 1);
      }
      const most = h.players.reduce((best, p) => ((active.get(p.player_id) || 0) > (active.get(best && best.player_id) || 0) ? p : best), null);
      const first = (most && active.get(most.player_id) ? most : null) || players.find((p) => p.starter) || players[0];
      put(sel, html`${players.map((p) => html`<option value="${p.player_id}"${first && p.player_id === first.player_id ? html` selected` : NOTHING}>${p.name} (${p.kit_number}) · ${team[p.team_id] || p.team_id}${p.starter ? '' : ' · sub'}</option>`)}`);
      sel.disabled = false;
      $('upMatchId').placeholder = h.match_id || 'from the file';
      $('upMsg').textContent = `${file.name}: match ${h.match_id}, ${h.players.length} players.`;
    } catch (e) {
      put(sel, html`<option value="">could not read the header</option>`); sel.disabled = true;
      $('upMsg').textContent = `${file.name}: ${e.message}`;
    }
  }
  $('upEvents').onchange = () => setUploadFile('events', $('upEvents').files[0]);
  $('upTracks').onchange = () => setUploadFile('tracks', $('upTracks').files[0]);
  const drop = $('upDrop');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('over');
    for (const f of e.dataTransfer.files) {
      if (/track/i.test(f.name)) setUploadFile('tracks', f);
      else setUploadFile('events', f);
    }
    const names = [up.events && `events: ${up.events.name}`, up.tracks && `tracks: ${up.tracks.name}`].filter(Boolean).join(' · ');
    if (names) $('upMsg').textContent = names;
  });
  $('upForm').onsubmit = async (e) => {
    e.preventDefault();
    if (!canWrite()) return;
    if (!up.events) { $('upMsg').textContent = 'Pick events.jsonl first.'; return; }
    const mid = $('upMatchId').value.trim();
    if (mid && (!ID.test(mid) || mid.includes('..'))) { $('upMsg').textContent = 'Match id: letters, digits, _ . - only.'; return; }
    const fd = new FormData();
    fd.append('events', up.events, 'events.jsonl');
    if (up.tracks) fd.append('tracks', up.tracks, 'tracks.jsonl');
    const qs = new URLSearchParams();
    if ($('upPlayer').value) qs.set('player', $('upPlayer').value);
    if (mid) qs.set('match_id', mid);
    if ($('upReview').checked) qs.set('review', 'true');
    try { qs.set('annotator', annotator()); } catch (err) { $('upMsg').textContent = err.message; return; }
    $('upGo').disabled = true; $('upMsg').textContent = 'Validating and running the Agent Framework workflow…';
    try {
      const out = await api(`/api/matches?${qs}`, { method: 'POST', body: fd, auth: true });
      $('upMsg').textContent = '';
      put($('upResult'), runSummary(out));
      S.matches = null;
      refreshOverview(false);
      loadRuns(S.arg);
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      $('upMsg').textContent = '';
      fail($('upResult'), err);
    } finally { $('upGo').disabled = !canWrite(); }
  };

  // ------------------------------------------------------------------------------------------------ claims
  // "That's me" claims from the Add-a-match form on player profiles (regista.claims_api). #claims/<match> filters by match.
  const CLAIM_CLASS = { pending: 'warn', confirmed: 'ok', rejected: 'bad' };  // not 'paused': .paused is the paused-workflow box

  function claimCard(c) {
    const p = c.player || {}, who = c.person || {};
    const links = c.links || {};
    const dec = c.decision;
    const kit = c.kit_matches === false ? html` <span class="warn small">number ${p.kit_number} here, ${who.kit_number} in the league</span>` : NOTHING;
    const acts = c.status === 'pending'
      ? html`<button class="keep" data-decide="confirm"${w()}>Confirm</button><button class="drop" data-decide="reject"${w()}>Reject</button>`
      : c.status === 'confirmed' ? html`<button class="alt small" data-decide="reject"${w()}>Withdraw (reject)</button>`
        : html`<button class="alt small" data-decide="confirm"${w()}>Confirm after all</button>`;
    return html`<div class="claim ${c.status}" data-claim="${c.claim_id}" data-match="${c.match_id}" data-player="${c.player_id}">
      <div class="bar"><span class="chip ${CLAIM_CLASS[c.status] || 'muted'}">${c.status}</span>
        <span class="muted small mono">${c.claim_id}</span></div>
      <dl class="who">
        <dt>In match</dt><dd><a href="${apiPathOrPage(links.match)}">${c.match_id}</a> · <a href="#runs/${enc(c.match_id)}">run</a></dd>
        <dt>Player there</dt><dd>${p.name || c.player_id} (${p.kit_number ?? '?'}) · ${p.team || p.team_id || ''} <span class="muted mono">${c.player_id}</span>${kit}</dd>
        <dt>Says they are</dt><dd><a href="${apiPathOrPage(links.profile)}">${who.name || c.global_id}</a> (${who.kit_number ?? '?'}) · ${who.club || ''} · ${who.position || ''} <span class="muted mono">${c.global_id}</span></dd>
        <dt>Claimed by</dt><dd>${c.claimant} · ${when(c.claimed_at)}${c.note ? html`<br><span class="muted">“${c.note}”</span>` : NOTHING}</dd>
        ${dec ? html`<dt>Decision</dt><dd>${dec.decision} by ${dec.by} · ${when(dec.at)}${dec.note ? html`<br><span class="muted">“${dec.note}”</span>` : NOTHING}</dd>` : NOTHING}
      </dl>
      <div data-clip><button type="button" class="alt small" data-show-clip>Show a clip of ${p.name || c.player_id}</button></div>
      <div class="acts">${acts}<input data-note maxlength="300" placeholder="note (optional)" aria-label="Decision note"><span class="small" data-msg></span></div>
      <div data-result></div></div>`;
  }
  // Links into our own pages (the Clip view, a profile): same-origin paths only.
  const apiPathOrPage = (u) => (typeof u === 'string' && /^\/[A-Za-z0-9_.\-/?=&%]*$/.test(u) && !u.startsWith('//') && !u.includes('..') ? u : '#');

  async function loadClaims(arg) {
    const status = $('clStatus').value;
    put($('clList'), html`<div class="muted">Loading…</div>`);
    const qs = new URLSearchParams();
    if (status) qs.set('status', status);
    if (arg) qs.set('match_id', arg);
    let out;
    try { out = await studioGet(`/api/claims${qs.toString() ? `?${qs}` : ''}`); } catch (e) { fail($('clList'), e); return; }
    const n = out.counts || {};
    setCount('nClaims', n.pending || 0, true);
    put($('clCounts'), html`${plural(n.pending || 0, 'pending claim')} · ${num(n.confirmed || 0)} confirmed · ${num(n.rejected || 0)} rejected${arg ? html` · match <b class="mono">${arg}</b> (<a href="#claims">all matches</a>)` : NOTHING}`);
    const list = out.claims || [];
    put($('clList'), list.length ? html`<div class="claims">${list.map(claimCard)}</div>`
      : html`<div class="empty">${status === 'pending' ? 'No claim is waiting. Claims come from "Add a match" on a player profile (/players/…).' : 'No claims.'}</div>`);
  }

  $('clStatus').onchange = () => loadClaims(S.arg);
  $('clRefresh').onclick = () => loadClaims(S.arg);
  $('clList').addEventListener('click', async (e) => {
    const card = e.target.closest('[data-claim]');
    if (!card) return;
    if (e.target.matches('[data-show-clip]')) {
      const box = card.querySelector('[data-clip]');
      put(box, html`<span class="muted small">Finding clips…</span>`);
      let clips;
      try { clips = await studioGet(`/api/matches/${enc(card.dataset.match)}/clips?player=${enc(card.dataset.player)}`); } catch (err) { fail(box, err); return; }
      const c = (clips || []).find((x) => apiPath(x.video_url));
      put(box, c ? html`<video controls muted playsinline preload="metadata" src="${apiPath(c.video_url)}"></video>
          <span class="small">${(c.label || {}).title || c.id} · ${clock(c.t)}–${clock(c.t_end)} · ${plural(clips.length, 'clip')} of this player</span>`
        : html`<div class="empty">No clip with video for this player here${(clips || []).length ? ' (Cosmos DB only)' : ''}.</div>`);
      return;
    }
    const btn = e.target.closest('[data-decide]');
    if (!btn || btn.disabled) return;
    const decision = btn.dataset.decide, msg = card.querySelector('[data-msg]');
    const annotator = $('clAnnotator').value.trim() || 'zaid';
    if (!ANNOTATOR.test(annotator)) { msg.textContent = 'Decided by: letters, digits, spaces, . _ - (up to 40).'; return; }
    for (const b of card.querySelectorAll('[data-decide]')) b.disabled = true;
    msg.textContent = decision === 'confirm' ? 'Confirming: the workflow cuts and labels this player’s moments, then the Profile agent refreshes the profile…' : 'Rejecting…';
    try {
      const out = await write(`/api/claims/${enc(card.dataset.claim)}/decision`, { decision, annotator, note: card.querySelector('[data-note]').value.trim() });
      const prof = ((out.profiles || {}).profiles || [])[0];
      const run = out.run;
      put(card.querySelector('[data-result]'), html`<div class="okbox small">${out.claim.status}${prof ? html` · profile ${prof.name || prof.global_id}: ${plural(prof.appearances, 'appearance')}, ${num(prof.minutes)} min` : NOTHING}
        ${run ? html` · workflow ${chip(run.pipeline_ok ? 'ok' : 'failed')} <a href="#runs/${enc(card.dataset.match)}">trace</a>` : NOTHING}</div>`);
      msg.textContent = '';
      refreshOverview(false);
      setTimeout(() => loadClaims(S.arg), 1500);
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      msg.textContent = errText(err);
      for (const b of card.querySelectorAll('[data-decide]')) b.disabled = !canWrite();
    }
  });

  // ------------------------------------------------------------------------------------------------ 6. jobs
  // Each kind's fields come from the API's allow-list; known fields get a typed control, anything new is typed from its
  // description (bool, int, list), so the form never takes free-form arguments the server would refuse.
  const FRESH_WARNING = 'The fresh matches (seeds 301-303) are scored with frozen models only and never tuned on. Run this only to report '
    + 'a final number, and never change a model because of what it shows: make a new fresh set instead.';

  function field(kind, name, desc, list) {
    const id = `jf-${kind}-${name}`;
    const d = String(desc || '');
    let control;
    if (name === 'roster' || name === 'match') control = html`<select id="${id}" data-name="${name}" data-type="str">${options(list, '', 'pick a match')}</select>`;
    else if (name === 'set') control = html`<select id="${id}" data-name="${name}" data-type="str" data-fresh><option value="dev" selected>dev (seeds 201-206, tuned against)</option><option value="fresh">fresh (301-303, frozen models only)</option></select>
      <div class="note small" data-fresh-warning hidden>${FRESH_WARNING}</div>`;
    else if (name === 'match_ids') control = html`<div class="opts" id="${id}" data-name="${name}" data-type="list-check">${list.map((m) => html`<label class="small"><input type="checkbox" value="${m.value}"> <span class="mono">${m.value}</span></label>`)}</div>`;
    else if (/^bool/i.test(d)) control = html`<label class="small"><input type="checkbox" id="${id}" data-name="${name}" data-type="bool"${/default true/i.test(d) ? html` checked` : NOTHING}> ${name}</label>`;
    else if (/^int/i.test(d)) control = html`<input type="number" id="${id}" data-name="${name}" data-type="int" min="1" max="99999" step="1" placeholder="${/optional/i.test(d) ? 'optional' : ''}">`;
    else if (/^list/i.test(d)) control = html`<input id="${id}" data-name="${name}" data-type="list" placeholder="comma-separated">`;
    else control = html`<input id="${id}" data-name="${name}" data-type="str" maxlength="500" placeholder="${name === 'out' ? 'new match id' : name === 'video' ? '/path/to/video.mp4' : name === 'player' ? 'optional, e.g. t_home_09' : ''}">`;
    return html`<div class="field"><span><b class="mono">${name}</b> · ${d}</span>${control}</div>`;
  }

  function collect(form) {
    const args = {};
    for (const el of form.querySelectorAll('[data-name]')) {
      const name = el.dataset.name, type = el.dataset.type;
      if (type === 'bool') args[name] = el.checked;
      else if (type === 'int') { if (el.value !== '') args[name] = parseInt(el.value, 10); }
      else if (type === 'list') { const v = el.value.split(',').map((x) => x.trim()).filter(Boolean); if (v.length) args[name] = v; }
      else if (type === 'list-check') { const v = [...el.querySelectorAll('input:checked')].map((x) => x.value); if (v.length) args[name] = v; }
      else if (el.value.trim() !== '') args[name] = el.value.trim();
    }
    return args;
  }

  // "video=…/match.mp4 roster=syn_0294 out=vis_0002": paths by their file name; the cell ellipsises the rest.
  const argsShort = (args) => Object.entries(args || {}).map(([k, v]) => {
    const t = Array.isArray(v) ? v.join(',') : String(v);
    return `${k}=${/[\\/]/.test(t) ? `…/${t.split(/[\\/]/).pop()}` : t}`;
  }).join(' ') || '–';

  async function loadJobs(arg) {
    stopPolling();
    put($('jbState'), html`<div class="muted">Loading…</div>`);
    let j, all;
    try { [j, all] = await Promise.all([studioGet('/api/studio/jobs'), matches()]); } catch (e) { fail($('jbState'), e); return; }
    const local = all.filter((m) => m.source === 'local').map((m) => ({ value: m.match_id, label: matchLabel(m) }));
    setCount('nJobs', j.running ? 1 : 0, false);
    const startGate = !j.available ? html` disabled title="${j.reason || 'unavailable'}"` : j.running ? html` disabled title="A job is running: one at a time."` : w();
    put($('jbState'), html`${j.available ? NOTHING : html`<div class="note">Jobs are unavailable on this deployment: ${j.reason || 'no reason given'}.</div>`}
      ${j.running ? html`<div class="note">Running: <a class="mono" href="#jobs/${enc(j.running.id)}">${j.running.id}</a> (${j.running.kind}), started ${when(j.running.started_at)}.</div>` : NOTHING}`);
    put($('jbForms'), html`<h3>Start a job</h3>${Object.entries(j.kinds || {}).map(([kind, spec]) => html`<form class="jobform panel" data-kind="${kind}">
        <h4 class="mono">${kind}</h4><span class="muted small">${spec.help || ''}</span>
        ${Object.entries(spec.args || {}).map(([name, desc]) => field(kind, name, desc, local))}
        <div class="bar"><button${startGate}>Start ${kind}</button><span class="small" data-msg></span></div></form>`)}`);
    const jobs = j.jobs || [];
    put($('jbList'), jobs.length ? html`<div class="tableWrap"><table class="grid"><tr><th>Job</th><th>Kind</th><th>Status</th><th>Started</th><th>Ended</th><th>Exit</th><th>Args</th><th>Log</th></tr>
      ${jobs.map((x) => html`<tr class="click${x.id === arg ? ' sel' : ''}" data-job="${x.id}"><td class="mono small">${x.id}</td><td>${x.kind}</td><td>${chip(x.status)}</td>
        <td class="small">${when(x.started_at)}</td><td class="small">${x.ended_at ? when(x.ended_at) : '–'}</td><td class="mono">${x.returncode ?? '–'}</td>
        <td class="mono small args" title="${JSON.stringify(x.args || {})}">${argsShort(x.args)}</td><td class="small">${bytes(x.log_bytes)}</td></tr>`)}</table></div>`
      : html`<div class="empty">No jobs yet.</div>`);
    const show = arg || (j.running && j.running.id);
    if (show) followJob(show); else { $('jbLog').textContent = 'Pick a job.'; $('jbLogWho').textContent = ''; put($('jbResult'), NOTHING); }
  }

  $('jbForms').addEventListener('change', (e) => {
    if (!e.target.matches('select[data-fresh]')) return;
    e.target.closest('.field').querySelector('[data-fresh-warning]').hidden = e.target.value !== 'fresh';
  });
  $('jbForms').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target, btn = form.querySelector('button'), msg = form.querySelector('[data-msg]');
    if (btn.disabled) return;
    const args = collect(form);
    if (args.set === 'fresh' && !confirm(`${FRESH_WARNING}\n\nScore the frozen models on the fresh matches now?`)) return;
    btn.disabled = true; msg.textContent = 'Starting…';
    try {
      const job = await write('/api/studio/jobs', { kind: form.dataset.kind, args });
      go('jobs', job.id);
    } catch (err) {
      if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
      btn.disabled = !canWrite(); msg.textContent = errText(err);
    }
  });
  $('jbList').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-job]'); if (tr) go('jobs', tr.dataset.job); });
  $('jbRefresh').onclick = () => loadJobs(S.arg);

  // The log, from byte 0, then every 2 s from next_offset while the job runs. A newer route() stops the loop.
  async function followJob(id) {
    const ticket = S.poll;
    const pre = $('jbLog');
    pre.textContent = '';
    $('jbLogWho').textContent = id;
    put($('jbResult'), NOTHING);
    let offset = 0, sawRunning = false;
    for (;;) {
      if (ticket !== S.poll) return;
      let out;
      try { out = await studioGet(`/api/studio/jobs/${enc(id)}/log?offset=${offset}`); } catch (e) { fail($('jbResult'), e); return; }
      if (ticket !== S.poll) return;
      const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
      if (out.text) {
        pre.textContent += out.text;
        if (pre.textContent.length > 400000) pre.textContent = `[earlier output trimmed]\n${pre.textContent.slice(-300000)}`;
        if (atBottom) pre.scrollTop = pre.scrollHeight;
      }
      offset = out.next_offset;
      $('jbLogWho').textContent = `${id} · ${out.status} · ${bytes(out.size)}`;
      if (out.status === 'running') { sawRunning = true; await new Promise((r) => setTimeout(r, 2000)); continue; }
      if (sawRunning) { S.matches = null; loadJobs(id); return; }  // it just ended: refresh the banner, the forms (a new match?) and the list once
      if (offset < out.size) continue;  // a finished job: read the rest without waiting
      break;
    }
    try {
      const job = await studioGet(`/api/studio/jobs/${enc(id)}`);
      if (ticket !== S.poll) return;
      put($('jbResult'), html`<h3>Job ${chip(job.status)} <span class="muted small">exit ${job.returncode ?? '–'}</span></h3>
        ${kv([['argv', (job.argv || []).join(' ')], ['started', when(job.started_at)], ['ended', when(job.ended_at)]])}
        ${job.result ? html`<h3>Result</h3>${jsonBlock(job.result)}` : NOTHING}
        <div id="jbNext"></div>`);
      setCount('nJobs', 0, false);
      if (job.status === 'ok') nextSteps(job, ticket);
    } catch (e) { fail($('jbResult'), e); }
  }

  // After a vision run: the new match, and a Cut clips job so the Product has something to show (vision-run writes the
  // event stream, not clips). After cut-clips: where the clips are.
  async function nextSteps(job, ticket) {
    const el = $('jbNext');
    const mid = job.kind === 'vision-run' ? (job.args || {}).out : job.kind === 'cut-clips' ? (job.args || {}).match : null;
    if (!el || !mid || !ID.test(mid)) return;
    S.matches = null;
    let m;
    try { m = await api(`/api/matches/${enc(mid)}`); } catch (e) { if (ticket === S.poll) fail(el, e); return; }
    if (ticket !== S.poll) return;
    const links = html`<a href="#runs/${enc(mid)}">its run</a> · <a href="#review/${enc(mid)}" data-view-all="${mid}">its clips in the Review queue</a>
      ${job.kind === 'vision-run' ? html` · <a href="#whos-who/${enc(mid)}">Who's who</a>` : NOTHING} · <a href="/">Home</a>`;
    if (job.kind === 'cut-clips' || m.clip_count) {
      put(el, html`<div class="okbox newMatch"><span>Match <b class="mono">${mid}</b> has ${plural(m.clip_count || 0, 'clip')}${(m.players_with_clips || []).length ? ` for ${m.players_with_clips.join(', ')}` : ''}.</span><span class="small">${links}</span></div>`);
      return;
    }
    const players = [...(m.players || [])].sort((a, b) => (b.starter ? 1 : 0) - (a.starter ? 1 : 0));
    const gate = canWrite() ? NOTHING : html` disabled title="${whyNoWrite()}"`;
    put(el, html`<div class="okbox newMatch"><span>New match <b class="mono">${mid}</b>: the vision layer wrote its event stream. It has no clips yet,
        so the Product has nothing to show for it until clips are cut.</span><span class="small">${links}</span></div>
      <form class="jobform panel" id="jbCut"><h4>Cut clips for <span class="mono">${mid}</span></h4>
        <label class="small">Player <select id="jbCutPlayer"><option value="">the featured or most active player</option>
          ${players.map((p) => html`<option value="${p.player_id}">${p.name} (${p.kit_number})${p.starter ? '' : ' · sub'}</option>`)}</select></label>
        <div class="bar"><button${gate}>Cut clips</button><span class="small" data-msg></span></div></form>`);
    $('jbCut').onsubmit = async (e) => {
      e.preventDefault();
      const btn = $('jbCut').querySelector('button'), msg = $('jbCut').querySelector('[data-msg]');
      if (btn.disabled) return;
      const args = { match: mid };
      if ($('jbCutPlayer').value) args.player = $('jbCutPlayer').value;
      btn.disabled = true; msg.textContent = 'Starting…';
      try { go('jobs', (await write('/api/studio/jobs', { kind: 'cut-clips', args })).id); } catch (err) {
        if (err.status === 401) { lockOut('That key is no longer accepted.'); return; }
        btn.disabled = !canWrite(); msg.textContent = errText(err);
      }
    };
  }

  // ------------------------------------------------------------------------------------------------ 7. console
  const ENGINE_NOTE = {
    search: 'GET /api/matches/{id}/search: the rule-based Librarian. No model, no limits, no trace.',
    ask: 'POST /api/matches/{id}/ask: the Foundry Librarian (Agent Framework, Regista MCP + Azure MCP). Spends Foundry credit and counts against the shared limits.',
    'chat-rules': 'POST /api/matches/{id}/chat with engine=rules: the conversational Librarian; follow-ups merge into the query so far.',
    'chat-foundry': 'POST /api/matches/{id}/chat with engine=foundry: a Foundry model writes the reply. Spends Foundry credit and counts against the shared limits.',
  };

  async function loadConsole(arg) {
    let all;
    try { all = await matches(); } catch (e) { fail($('coTrace'), e); return; }
    const local = all.filter((m) => m.source === 'local');
    const cur = arg || $('coMatch').value || (local[0] && local[0].match_id) || '';
    put($('coMatch'), options(local.map((m) => ({ value: m.match_id, label: matchLabel(m) })), cur));
    $('coNote').textContent = ENGINE_NOTE[$('coEngine').value];
  }
  function resetChat() { S.chat = { state: null, history: [] }; $('coState').textContent = 'New conversation.'; }
  $('coEngine').onchange = () => { $('coNote').textContent = ENGINE_NOTE[$('coEngine').value]; resetChat(); };
  $('coMatch').onchange = resetChat;
  $('coReset').onclick = resetChat;

  $('coForm').onsubmit = async (e) => {
    e.preventDefault();
    const q = $('coQ').value.trim(), mid = $('coMatch').value, engine = $('coEngine').value;
    if (!q || !ID.test(mid)) return;
    const base = `/api/matches/${enc(mid)}`;
    let method = 'POST', path, body;
    if (engine === 'search') { method = 'GET'; path = `${base}/search?${new URLSearchParams({ q, limit: '10' })}`; }
    else if (engine === 'ask') { path = `${base}/ask`; body = { q }; }
    else { path = `${base}/chat`; body = { message: q, state: S.chat.state, history: S.chat.history, engine: engine === 'chat-foundry' ? 'foundry' : 'rules' }; }
    $('coStatus').textContent = `${method} ${path} · sending…`;
    $('coRaw').textContent = '';
    const t0 = performance.now();
    let status = 0, text = '';
    try {
      const r = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
      status = r.status; text = await r.text();
    } catch (err) { text = String(err); }
    const took = performance.now() - t0;
    let out = null;
    try { out = JSON.parse(text); } catch (err) { out = null; }
    $('coStatus').textContent = `${method} ${path} · HTTP ${status || 'error'} · ${ms(took)}`;
    $('coRaw').textContent = out === null ? text : JSON.stringify(out, null, 2);
    renderTrace(out, engine, body);
    if (out && status === 200 && engine.startsWith('chat')) {
      S.chat = { state: out.state || null, history: out.history || [] };
      $('coState').textContent = JSON.stringify(S.chat.state, null, 2);
    }
  };

  function renderTrace(out, engine, body) {
    const el = $('coTrace');
    if (!out || typeof out !== 'object') { put(el, html`<div class="muted">No JSON came back.</div>`); return; }
    const trace = Array.isArray(out.trace) ? out.trace : [];
    const SERVER = { 'regista-mcp': 'Regista MCP server', 'azure-mcp': 'Azure MCP Server' };
    put(el, html`
      ${kv([['answered by', out.answered_by || (engine === 'search' ? 'rules (search)' : '–')], ['tools used', (out.tools_used || []).join(', ') || '–'],
            ['results', Array.isArray(out.results) ? `${out.results.length}${out.total !== undefined ? ` of ${out.total}` : ''}` : '–'],
            ['understood', out.understood || out.parsed ? JSON.stringify(out.understood || out.parsed) : '–']])}
      ${trace.length ? html`<table class="grid" style="margin-top:8px"><tr><th>#</th><th>Step</th><th>Kind</th><th>Server</th><th>Time</th></tr>
        ${trace.map((s, i) => html`<tr><td class="muted">${i + 1}</td><td class="mono">${s.name}</td><td>${s.kind}</td><td>${SERVER[s.server] || s.server || '–'}</td><td class="mono">${ms(s.ms)}</td></tr>`)}</table>`
        : html`<p class="muted small">${engine === 'search' ? 'GET /search returns no trace.' : 'No trace in this response.'}</p>`}
      ${out.trace_note ? html`<p class="note small">${out.trace_note}</p>` : NOTHING}
      ${out.reply || out.answer || out.message ? html`<h3>Reply</h3><p>${out.reply || out.answer || out.message}</p>` : NOTHING}
      ${body ? html`<details><summary>request body</summary>${jsonBlock(body)}</details>` : NOTHING}`);
  }

  // ------------------------------------------------------------------------------------------------ start
  openStudio();
})();
