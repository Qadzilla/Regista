// The Scout terminal: the Terminal section of /scout (#terminal), ported from the sandbox design Zaid approved
// (ux/sandbox, sandbox/terminal.js). A command line with Bloomberg-style mnemonics (TOURE <GO>, RANK FW npxg, CMP, SCAT,
// SIM, SHOT, FORM, TEAM, HELP) over linked panels: screener, player, radar or pizza vs position peers, clips, shot map,
// heat map, form, scatter and team style. Selecting a player in any panel updates the others; every number opens the
// moments behind it, all of them (the API's evidence, paged until complete), and they play in the clips panel.
//
// LIVE, from the API (regista.terminal_api and the season API), read only: the metric catalogue (/api/metrics), the
// screener's columns (/api/terminal/screen), one player's every metric (/api/players/{id}/metrics), the evidence behind a
// number (?evidence=KEY&evidence_offset=N), form, similar players, shots, the league-only touch grid (/heatmap), the scatter,
// team style and team shots, the league (/api/season). The terminal writes nothing to the server.
// PER VISITOR, in this browser only: three workspaces (panels, players, columns, axes) and the command history, through
// Regista.store (shared/regista.js), never storage directly; Reset puts a workspace back to its defaults.
//
// Plain script on window.Regista, loaded after scout.js. The page runs under a Content Security Policy: no inline
// handlers and no style attributes in markup, so shading, colours and widths are data attributes applied through
// element.style after rendering (styleUp). Every API value that reaches innerHTML goes through esc().
(function () {
  'use strict';
  const R = window.Regista;
  const esc = R.esc;
  const PV = R.profileView;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  if (!$('txForm')) return;

  const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const ord = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const POS = ['GK', 'DF', 'MF', 'FW'];
  const POSN = { GK: 'goalkeepers', DF: 'defenders', MF: 'midfielders', FW: 'forwards' };
  const POS1 = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };
  const POS_WORDS = { GK: 'GK', GOALKEEPER: 'GK', GOALKEEPERS: 'GK', KEEPER: 'GK', KEEPERS: 'GK', DF: 'DF', DEF: 'DF', DEFENDER: 'DF', DEFENDERS: 'DF',
    MF: 'MF', MID: 'MF', MIDFIELDER: 'MF', MIDFIELDERS: 'MF', FW: 'FW', FWD: 'FW', FORWARD: 'FW', FORWARDS: 'FW', ALL: 'ALL' };
  const CMP_COL = ['#ffcd28', '#4cc9f0', '#f472b6'];
  const GROUP_COL = { shooting: '#ffcd28', creation: '#ff9f43', passes: '#4cc9f0', carrying: '#5ad17a', defence: '#ff6b6b',
    goalkeeping: '#2dd4bf', physical: '#a3a9b8', value: '#c084fc' };
  const GID = /^pl_[a-z0-9_]{1,40}$/;
  const CLUBID = /^cl_[a-z0-9_]{1,40}$/;
  const KEY = /^[a-z0-9_]{1,40}$/;
  const HEX = /^#[0-9a-f]{6}$/i;
  const VIDEO = /^\/api\/[A-Za-z0-9_./?=&%-]+$/;     // video urls from the API are relative; anything else is not played
  const COLS_PER_CALL = 16;                          // what /api/terminal/screen takes in one call
  const SCREEN_PAGE = 200;                           // and how many rows a page
  const EVIDENCE_PAGE = 500;                         // and /api/players/{id}/metrics?evidence=KEY a page
  const MAX_COLS = 40;
  // F-key order. Sizes span 4, 6, 8 or 12 of the workspace's 12 columns (S, M, L, XL).
  const PANELS = [
    { id: 'scrn', key: 'SCRN', title: 'Screener', size: 'L' },
    { id: 'plyr', key: 'PLYR', title: 'Player', size: 'S' },
    { id: 'radar', key: 'RDR', title: 'Radar vs peers', size: 'S' },
    { id: 'clips', key: 'CLIP', title: 'Clips', size: 'S' },
    { id: 'shot', key: 'SHOT', title: 'Shot map', size: 'S' },
    { id: 'heat', key: 'HEAT', title: 'Heat map', size: 'S' },
    { id: 'form', key: 'FORM', title: 'Form', size: 'S' },
    { id: 'scat', key: 'SCAT', title: 'Scatter', size: 'S' },
    { id: 'team', key: 'TEAM', title: 'Team style', size: 'XL' },
  ];
  // The default layout: the screener with the clips beside it (a number clicked plays in view), then the player, radar
  // and form it drives, then the pitch charts and the scatter, then the team.
  const DEFAULT_ORDER = ['scrn', 'clips', 'plyr', 'radar', 'form', 'shot', 'heat', 'scat', 'team'];
  const SIZES = ['S', 'M', 'L', 'XL'];
  const SIZE_NEXT = { S: 'M', M: 'L', L: 'XL', XL: 'S' };
  const COMMANDS = {
    RANK: { args: '<position> <metric>', help: 'Rank a position on any metric; the screener sorts by it.', ex: 'RANK FW npxg' },
    CMP: { args: '<player> <player> [<player>]', help: 'Compare two or three players on the radar and side by side.', ex: 'CMP Femi Toure Amari Ustinov' },
    SCAT: { args: '<metricX> <metricY> [<position>]', help: 'Plot one metric against another.', ex: 'SCAT npxg xa FW' },
    SIM: { args: '<player>', help: 'The five most similar players (cosine on the position template).', ex: 'SIM TOURE' },
    SHOT: { args: '<player>', help: 'Every shot, sized by xG; each plays its clip.', ex: 'SHOT TOURE' },
    FORM: { args: '<player>', help: 'Match by match, any metric.', ex: 'FORM TOURE' },
    HEAT: { args: '<player>', help: 'Where the player touches the ball.', ex: 'HEAT TOURE' },
    RDR: { args: '<player>', help: 'Pizza chart vs position peers.', ex: 'RDR TOURE' },
    TEAM: { args: '<club>', help: 'Team style: possession, pressing, directness, chances.', ex: 'TEAM BRO' },
    HELP: { args: '', help: 'Commands, keys and what the numbers mean.', ex: 'HELP' },
  };
  const STORE_KEY = 'terminal';      // Regista.store: regista.demo.v1.terminal, this browser only

  // ------------------------------------------------------------------ the data, from the API
  let CAT = null, SEASON = null, TEAMS_ALL = null, METRICS = [];
  let loading = false, ready = false, wantFocus = false;
  const MK = new Map(), TK = new Map(), PID = new Map(), CID = new Map(), TEAMS = new Map(), MATCH = new Map();
  let PLAYERS = [];
  const CELLS = new Map();           // player id -> { metric key: cell } (screener columns, and every metric once loaded)
  const COLS = new Set(), colsPending = new Set();
  let colsErr = null;
  const C = new Map();               // request cache: key -> { st: wait | ok | err, v, e, p }
  let store = { cur: 0, ws: [null, null, null], hist: [] }, S = null, storageOK = true, saveT = 0;
  let reel = null, histAt = -1, histDraft = '', acItems = [], acAt = -1, scatCur = null, scrAct = null, tipFor = null;

  function fetchOnce(key, fn) {
    let c = C.get(key);
    if (!c) {
      c = { st: 'wait' };
      C.set(key, c);
      c.p = Promise.resolve().then(fn).then((v) => { c.st = 'ok'; c.v = v; return v; }, (e) => { c.st = 'err'; c.e = e; throw e; });
      c.p.catch(() => {});
    }
    return c;
  }
  // A value a panel needs: returned once loaded; until then it starts the request and repaints the panel when it lands.
  function want(key, fn, panel) {
    const c = fetchOnce(key, fn);
    if (c.st === 'wait' && panel) {
      (c.panels || (c.panels = new Set())).add(panel);
      c.p.then(() => repaintSoon(panel), () => repaintSoon(panel));
    }
    return c;
  }
  // One frame later (or 100 ms, where a hidden page gets no frames): a repaint asked for before this has been drawn.
  const nextFrame = () => new Promise((res) => { let done = false; const f = () => { if (!done) { done = true; res(); } }; requestAnimationFrame(f); setTimeout(f, 100); });
  // Wait until every shown panel has its data and has been drawn with it (at most `ms`). A command calls this before it
  // scrolls: on a phone the panels are stacked, and one above the subject that is still "Loading…" grows by hundreds of
  // pixels when its data lands, pushing the subject below the fold after the scroll.
  async function panelsSettled(ms = 6000) {
    const end = Date.now() + ms;
    for (;;) {
      await nextFrame(); await nextFrame();         // repaints already asked for land; they may start more requests
      const w = [...C.values()].filter(c => c.st === 'wait' && c.panels && [...c.panels].some(visible));
      const cols = colsPending.size > 0 && visible('scrn');
      if (!w.length && !cols) return;
      const left = end - Date.now();
      if (left <= 0) return;
      await Promise.race([Promise.all(w.map(c => c.p.catch(() => {}))), new Promise(r => setTimeout(r, cols ? Math.min(left, 120) : left))]);
    }
  }
  const pending = new Set();
  let raf = 0;
  function repaintSoon(id) {
    pending.add(id);
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const ids = [...pending]; pending.clear();
      if (!ready) return;
      if (ids.includes('sel')) renderSel();
      for (const id of ids) if (id !== 'sel' && visible(id) && RENDER[id]) RENDER[id]();
    });
  }
  const errText = (e) => (e && typeof e.detail === 'string') ? e.detail : (e instanceof R.ApiError ? (e.message || 'error') : 'Regista could not be reached');
  function waitHtml(c, what) {
    if (c.st === 'err') return `<p class="tx-dim">Could not load ${esc(what)}: ${esc(errText(c.e))}. <button type="button" class="tx-mini" data-act="retry" data-key="${esc(keyOf(c))}">Retry</button></p>`;
    return `<p class="tx-dim tx-wait">Loading ${esc(what)}…</p>`;
  }
  const keyOf = (c) => { for (const [k, v] of C) if (v === c) return k; return ''; };

  function addPlayers(rows) {
    for (const r of rows) {
      if (!r || !GID.test(String(r.global_id || ''))) continue;
      const id = r.global_id;
      let p = PID.get(id);
      if (!p) { p = { id }; PID.set(id, p); PLAYERS.push(p); }
      for (const k of ['name', 'club_id', 'club', 'short_name', 'kit', 'kit_number', 'position', 'role', 'age', 'height_cm',
        'preferred_foot', 'nationality', 'minutes', 'appearances', 'qualified', 'profile_url']) if (r[k] !== undefined) p[k] = r[k];
      if (r.values) { const cs = CELLS.get(id) || {}; Object.assign(cs, r.values); CELLS.set(id, cs); }
    }
  }
  // Screener columns for every player who played, paged and in calls of 16 metrics, cached per metric.
  async function screenCols(keys) {
    let offset = 0, total = Infinity;
    while (offset < total) {
      const q = `/api/terminal/screen?min_minutes=0&limit=${SCREEN_PAGE}&offset=${offset}&sort=${enc(keys[0])}&metrics=${keys.map(enc).join(',')}`;
      const j = await R.api(q);
      addPlayers(j.players || []);
      total = j.total;
      if (!j.players || !j.players.length) break;
      offset += j.players.length;
    }
  }
  // Whether every key has its column loaded; loads the missing ones and repaints the screener when they land.
  function ensureCols(keys) {
    const missing = keys.filter(k => MK.has(k) && !COLS.has(k) && !colsPending.has(k));
    for (let i = 0; i < missing.length; i += COLS_PER_CALL) {
      const chunk = missing.slice(i, i + COLS_PER_CALL);
      chunk.forEach(k => colsPending.add(k));
      screenCols(chunk).then(() => { chunk.forEach(k => { colsPending.delete(k); COLS.add(k); }); colsErr = null; repaintSoon('scrn'); },
        (e) => { chunk.forEach(k => colsPending.delete(k)); colsErr = e; repaintSoon('scrn'); });
    }
    return keys.every(k => COLS.has(k) || !MK.has(k));
  }
  // One player's every metric (the cells), merged into the screener's table of cells.
  const fullKey = (pid) => 'full|' + pid;
  const fullFn = (pid) => () => R.api(`/api/players/${enc(pid)}/metrics?evidence_limit=0`).then(j => {
    const cs = CELLS.get(pid) || {};
    for (const [k, c] of Object.entries(j.metrics || {})) { const { evidence, ...cell } = c; cs[k] = cell; }
    CELLS.set(pid, cs); addPlayers([j]); return true;
  });
  const full = (pid, panel) => want(fullKey(pid), fullFn(pid), panel);
  const similar = (pid, panel) => want('sim|' + pid, () => R.api(`/api/players/${enc(pid)}/similar`), panel);
  const shotsOf = (pid, panel) => want('shots|' + pid, () => R.api(`/api/players/${enc(pid)}/shots`), panel);
  // The heat map's grid counts league fixtures only, like every other terminal number (the profile's grid adds uploads).
  const heatOf = (pid, panel) => want('heat|' + pid, () => R.api(`/api/players/${enc(pid)}/heatmap`), panel);
  function formOf(pid, keys, panel) {
    const ks = [...new Set(keys)].filter(k => MK.has(k)).slice(0, COLS_PER_CALL);
    return want('form|' + pid + '|' + ks.join(','), () => R.api(`/api/players/${enc(pid)}/form?metrics=${ks.map(enc).join(',')}`), panel);
  }
  const scatOf = (x, y, pos, panel) => want(`scat|${x}|${y}|${pos || ''}`,
    () => R.api(`/api/terminal/scatter?x=${enc(x)}&y=${enc(y)}&min_minutes=0${pos ? `&position=${enc(pos)}` : ''}`), panel);
  const styleOf = (cid, panel) => want('style|' + cid, () => R.api(`/api/teams/${enc(cid)}/style`), panel);
  const teamShotsOf = (cid, side) => fetchOnce(`tshots|${cid}|${side}`, () => R.api(`/api/teams/${enc(cid)}/shots?side=${enc(side)}`));
  // Every moment behind one number: the API pages its evidence (500 a page); read page after page until all are in.
  const evidenceOf = (pid, mk) => fetchOnce(`ev|${pid}|${mk}`, async () => {
    let offset = 0, out = null;
    for (;;) {
      const j = await R.api(`/api/players/${enc(pid)}/metrics?evidence=${enc(mk)}&evidence_limit=${EVIDENCE_PAGE}&evidence_offset=${offset}`);
      const ev = j.evidence || { items: [], total: 0 };
      if (!out) out = { ...ev, items: [] };
      out.items.push(...(ev.items || []));
      offset += (ev.items || []).length;
      if (!(ev.items || []).length || offset >= ev.total) break;
    }
    out.complete = out.items.length >= out.total;
    return out;
  });
  const settle = (c) => c.p.then(() => c.v, () => null);

  // ------------------------------------------------------------------ loading (the first time the section opens)
  const onTerminal = () => decodeURIComponent(location.hash.replace(/^#/, '')).split('/')[0] === 'terminal';
  function onRoute() {
    if (!onTerminal()) { const v = clipVideo(); if (v) v.pause(); hideTip(); return; }
    if (!ready && !loading) load();
    else if (ready) { renderLayout(); renderAll(); }
  }
  async function load() {
    loading = true;
    out('Loading the Regista League…');
    try {
      const [cat, season, teams] = await Promise.all([R.api('/api/metrics'), R.api('/api/season'), R.api('/api/teams')]);
      CAT = cat; SEASON = season; TEAMS_ALL = teams;
      for (const m of cat.metrics || []) {
        const rel = m.reliability || {};
        const x = { ...m, has_percentile: m.kind !== 'total', noisy: !!rel.noisy, reliability_r: rel.r ?? null };
        MK.set(m.key, x); METRICS.push(x);
      }
      for (const m of cat.team_metrics || []) TK.set(m.key, m);
      for (const c of season.clubs || []) CID.set(c.club_id, c);
      for (const t of teams.teams || []) TEAMS.set(t.club_id, t);
      for (const r of season.rounds || []) for (const m of r.matches || []) MATCH.set(m.match_id, { ...m, round: r.round });
      const base = ((cat.default_columns || {}).all || []).filter(k => MK.has(k));
      await screenCols(base);
      base.forEach(k => COLS.add(k));
    } catch (e) {
      loading = false;
      out(`The league did not load (${errText(e)}).`, 'err', `${esc(`The league did not load (${errText(e)}).`)} <button type="button" class="tx-mini" data-act="reload">Retry</button>`);
      return;
    }
    readStore();
    loading = false; ready = true;
    paintMeta(); renderLayout(); renderAll();
    out(`Ready: ${PLAYERS.length} players, ${METRICS.length} metrics, ${MATCH.size} matches. Type a name, a command or HELP, then Enter.`);
    if (onTerminal() && wantFocus) $('txIn').focus();
    if (document.activeElement === $('txIn') && $('txIn').value) suggest();   // typed while the league loaded
  }

  // ------------------------------------------------------------------ workspaces, per visitor (Regista.store)
  function defaults() {
    const f = PID.has('pl_bro_09') ? 'pl_bro_09' : (PLAYERS.find(p => p.minutes > 0) || PLAYERS[0]).id, fp = PID.get(f);
    const cols = (CAT.default_columns[fp.position] || CAT.default_columns.all).filter(k => MK.has(k));
    return { v: 2, panels: DEFAULT_ORDER.map(id => PANELS.find(p => p.id === id)).map(p => ({ id: p.id, on: true, size: p.size })), focus: f, compare: [], club: fp.club_id,
      scr: { pos: fp.position, cols, sort: { k: cols[0], dir: -1 }, qual: true, mode: 'val', q: '' },
      scat: { x: 'npxg', y: 'xa', pos: fp.position, all: false }, form: { k: null }, radar: { tpl: 'pos' } };
  }
  // A saved workspace is checked before use: unknown players, metrics and panels are dropped.
  function clean(s) {
    const o = defaults();
    if (!s || typeof s !== 'object' || s.v !== 2) return o;
    if (Array.isArray(s.panels)) {
      const seen = new Set(), ps = [];
      for (const p of s.panels) {
        const def = p && PANELS.find(x => x.id === p.id);
        if (def && !seen.has(p.id)) { seen.add(p.id); ps.push({ id: p.id, on: p.on !== false, size: SIZES.includes(p.size) ? p.size : def.size }); }
      }
      for (const p of o.panels) if (!seen.has(p.id)) ps.push(p);
      o.panels = ps;
    }
    if (PID.has(s.focus)) o.focus = s.focus;
    if (Array.isArray(s.compare)) o.compare = [...new Set(s.compare.filter(id => PID.has(id)))].slice(0, 3);
    if (CID.has(s.club)) o.club = s.club;
    const sc = s.scr || {};
    if (sc.pos === null || POS.includes(sc.pos)) o.scr.pos = sc.pos;
    if (Array.isArray(sc.cols)) o.scr.cols = [...new Set(sc.cols.filter(k => MK.has(k)))].slice(0, MAX_COLS);
    if (sc.sort && (MK.has(sc.sort.k) || ['name', 'club', 'min'].includes(sc.sort.k))) o.scr.sort = { k: sc.sort.k, dir: sc.sort.dir === 1 ? 1 : -1 };
    o.scr.qual = sc.qual !== false; o.scr.mode = sc.mode === 'pct' ? 'pct' : 'val';
    o.scr.q = typeof sc.q === 'string' ? sc.q.slice(0, 40) : '';
    const sp = s.scat || {};
    if (MK.has(sp.x)) o.scat.x = sp.x;
    if (MK.has(sp.y)) o.scat.y = sp.y;
    if (sp.pos === null || POS.includes(sp.pos)) o.scat.pos = sp.pos;
    o.scat.all = sp.all === true;
    if (s.form && MK.has(s.form.k)) o.form.k = s.form.k;
    if (s.radar && s.radar.tpl === 'all') o.radar.tpl = 'all';
    return o;
  }
  function readStore() {
    storageOK = R.store.persistent();
    const s = R.store.get(STORE_KEY, null);
    if (s && typeof s === 'object' && Array.isArray(s.ws)) {
      store.cur = [0, 1, 2].includes(s.cur) ? s.cur : 0;
      store.ws = [0, 1, 2].map(i => s.ws[i] || null);
      store.hist = Array.isArray(s.hist) ? s.hist.filter(h => typeof h === 'string').map(h => h.slice(0, 200)).slice(-50) : [];
    } else {
      // Nothing saved (first visit, or "Reset this demo" in this tab or another): start from the defaults, never from
      // the workspaces and history still held in memory, and drop a pending save, which would write them back.
      clearTimeout(saveT);
      store = { cur: 0, ws: [null, null, null], hist: [] };
    }
    S = store.ws[store.cur] = clean(store.ws[store.cur]);
  }
  function save() {
    clearTimeout(saveT);
    saveT = setTimeout(() => { if (!R.store.set(STORE_KEY, store) && storageOK) { storageOK = false; paintMeta(); } }, 120);
  }
  function switchWs(i) {
    store.cur = i; S = store.ws[i] = clean(store.ws[i]);
    save(); paintMeta(); renderLayout(); renderAll();
    out(`Workspace ${i + 1}.`);
  }
  function resetWs() {
    S = store.ws[store.cur] = defaults();
    reel = null; save(); paintMeta(); renderLayout(); renderAll();
    out(`Workspace ${store.cur + 1} reset to its defaults.`);
  }

  // ------------------------------------------------------------------ formatting
  const club = (cid) => CID.get(cid) || { name: 'Unknown club', short_name: '?', kit: { primary: '#555555', secondary: '#ffffff', gk: '#111111' } };
  const short = (cid) => club(cid).short_name;
  function fmt(m, v) {
    if (v == null || Number.isNaN(Number(v))) return '–';
    const d = m && Number.isInteger(m.digits) ? m.digits : 2;
    return Number(v).toFixed(d) + (m && m.unit === '%' ? '%' : '');
  }
  const unitText = (m) => m.kind === 'per90' ? `${m.unit} per 90` : m.kind === 'padj' ? `${m.unit} per 90, possession-adjusted`
    : m.kind === 'ratio' ? (m.unit === '%' ? 'percentage' : `${m.unit}, average`) : m.kind === 'max' ? `${m.unit}, season peak`
    : m.kind === 'mean' ? `${m.unit}, mean of matches` : `${m.unit}, season total`;
  const noisy = (m) => m.noisy ? '<span class="tx-noisy" aria-hidden="true">≈</span><span class="sr">, noisy</span>' : '';
  // Shading: a data attribute (the CSP allows no style attributes in markup), applied by styleUp after rendering.
  function shade(m, pct) {
    if (pct == null) return '';
    const a = (0.05 + 0.4 * pct / 100).toFixed(3);
    return ` data-bg="${m.higher_is_better === null ? 'b' : 'y'}:${a}"`;
  }
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Number(v) || 0));
  function styleUp(root) {
    if (!root) return;
    for (const el of root.querySelectorAll('[data-bg]')) {
      const [t, a] = el.dataset.bg.split(':'), n = clamp(a, 0, 1).toFixed(3);
      el.style.background = t === 'b' ? `rgba(110,140,200,${n})` : `rgba(255,205,40,${n})`;
    }
    for (const el of root.querySelectorAll('[data-c]')) if (HEX.test(el.dataset.c)) el.style.setProperty('--c', el.dataset.c);
    for (const el of root.querySelectorAll('[data-g]')) if (HEX.test(el.dataset.g)) el.style.setProperty('--g', el.dataset.g);
    for (const el of root.querySelectorAll('[data-fg]')) if (HEX.test(el.dataset.fg)) el.style.color = el.dataset.fg;
    for (const el of root.querySelectorAll('[data-w]')) el.style.width = `${clamp(el.dataset.w, 0, 100)}%`;
    for (const el of root.querySelectorAll('[data-l]')) el.style.left = `${clamp(el.dataset.l, 0, 100)}%`;
  }
  const cellOf = (p, k) => (p && CELLS.get(p.id) && CELLS.get(p.id)[k]) || null;
  const pctOf = (p, k) => { const c = cellOf(p, k); return c ? c.percentile : null; };
  const minMinutes = () => Math.ceil(Number(CAT.season.min_minutes) || 0);
  // Why a value has no percentile, as the engine decides it (metrics.py _percentiles): the metric has no percentiles at all
  // (a season count), it is not scored for the player's position, the player is under the qualifying minutes, a ratio has
  // too few attempts, or the player is the only qualified peer. `small` marks a small sample (the screener's italics).
  function noPct(p, m, c) {
    if (!c || c.value == null || c.percentile != null) return null;
    if (!m.has_percentile) return { text: 'no percentile: a season count, ranked by value only', small: false };
    if (!m.positions.includes(p.position)) return { text: `no percentile: not scored for ${POSN[p.position]} (scored for ${m.positions.join(' ')})`, small: false };
    if (!p.qualified) return { text: `no percentile: under ${minMinutes()} minutes`, small: true };
    if (!c.qualified) return { text: `no percentile: below the minimum attempts${c.den != null && m.min_attempts ? ` (${c.den} attempts, needs ${m.min_attempts})` : ''}`, small: true };
    return { text: `no percentile: the only qualified ${POS1[p.position].toLowerCase()} on this metric, so no peers to rank against`, small: false };
  }
  const initials = (p) => { const w = String(p.name).split(' '); return w.length > 1 ? `${w[0][0]}. ${w.slice(1).join(' ')}` : p.name; };
  const lastName = (p) => String(p.name).split(' ').slice(-1)[0];
  function surname(p) { const w = norm(p.name).split(' '); return w.slice(1).join(' ') || w[0]; }
  const shirt = (p, w = 46) => PV && PV.shirtSvg ? PV.shirtSvg(club(p.club_id).kit, p.kit_number, p.position, w) : '';
  const words = (k) => { const s = String(k || '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
  const metricOrKey = (k) => MK.get(k) || { key: k, label: words(k), unit: '', digits: 2 };
  function evText(m, v) {
    if (v == null) return '';
    if (v === 1 && !['xG', 'xT', 'm', 'km/h'].includes(m.unit)) return '';
    const n = Number(v);
    const s = Number.isInteger(n) ? String(n) : (Math.abs(n) < 1 ? n.toFixed(3) : n.toFixed(1));
    return ['xG', 'xT'].includes(m.unit) ? `${m.unit} ${s}` : ['m', 'km/h'].includes(m.unit) ? `${s} ${m.unit}` : s;
  }
  // "R5 v ASH" / "R5 at ASH" for a club's match.
  function matchFor(mid, cid) {
    const mt = MATCH.get(mid);
    if (!mt) return { when: '', opp: null, home: true, round: null };
    const home = mt.home === cid, opp = home ? mt.away : mt.home;
    return { when: `R${mt.round} ${home ? 'v' : 'at'} ${short(opp)}`, opp, home, round: mt.round, mt };
  }

  // ------------------------------------------------------------------ output line
  function out(msg, kind, html) {
    const o = $('txOut'); if (!o) return;
    o.className = 'tx-out' + (kind === 'err' ? ' err' : '');
    if (html) o.innerHTML = html; else o.textContent = msg;
  }

  // ------------------------------------------------------------------ static pieces: meta strip, function keys, layout
  function paintMeta() {
    const sm = CAT.season.sample || {}, rel = CAT.season.reliability || {};
    const first = String(CAT.season.note || CAT.note || '').split('. ')[0].replace(/^Synthetic data:\s*/i, '').replace(/\.$/, '');
    $('txMeta').innerHTML = `<p class="tx-syn"><b>SYNTHETIC DATA</b> ${esc(first.charAt(0).toUpperCase() + first.slice(1))}.</p>
      <details class="tx-about"><summary>Small sample · <span class="tx-noisy" aria-hidden="true">≈</span> noisy</summary>
        <p>${esc(sm.note || '')}</p>
        <p><span class="tx-noisy" aria-hidden="true">≈</span> Noisy: split-half reliability within a role below ${esc(rel.noise_r)}, so one season cannot yet separate players on this metric.</p>
        <p>Percentiles: ${esc(CAT.season.percentile_rule)}. Peers: ${esc(CAT.season.peer_groups)}. Qualified: at least ${esc(minMinutes())} minutes.</p>
        <p>Every number opens every moment behind it: the events it counts, each with its clip; physical numbers open one value per match.</p></details>
      <div class="tx-ws" role="group" aria-label="Workspaces"><span class="tx-wsl">WS</span>
        ${[0, 1, 2].map(i => `<button type="button" data-act="ws" data-i="${i}" aria-pressed="${store.cur === i}" aria-label="Workspace ${i + 1}">${i + 1}</button>`).join('')}
        <button type="button" data-act="reset" class="tx-reset">Reset</button>
        ${storageOK ? '' : '<span class="tx-warn" title="This browser blocks storage, so workspaces last until you leave the page.">not saved: storage blocked</span>'}</div>`;
  }
  function paintKeys() {
    $('txKeys').innerHTML = PANELS.map((p, i) => {      // in F-key order, whatever the layout
      const pp = S.panels.find(x => x.id === p.id) || { on: false }, n = i + 1;
      // Not a toggle: an F-key always shows its panel and moves to it, so it says whether the panel is hidden instead.
      return `<button type="button" class="tx-fkey" data-act="fkey" data-id="${p.id}" data-on="${pp.on}" aria-label="F${n} ${esc(p.key)} ${esc(p.title)}${pp.on ? '' : ', hidden: show it'}" title="${esc(p.title)}${pp.on ? '' : ' (hidden)'}: go to it (Alt+${n})"><b>F${n}</b> ${esc(p.key)}<span>${esc(p.title)}</span></button>`;
    }).join('') + '<button type="button" class="tx-fkey help" data-act="help" aria-haspopup="dialog"><b>?</b> HELP<span>Commands and keys</span></button>';
  }
  function renderLayout() {
    const g = $('txGrid');
    const keepClips = $('txClipBody');
    g.innerHTML = S.panels.filter(p => p.on).map((pp) => {
      const p = PANELS.find(x => x.id === pp.id), n = PANELS.indexOf(p) + 1;
      return `<section class="tx-panel s-${pp.size}" id="tx-p-${p.id}" data-txp="${p.id}" aria-labelledby="tx-h-${p.id}">
        <header class="tx-ph"><h2 id="tx-h-${p.id}" tabindex="-1"><span class="tx-fk">F${n}</span> ${esc(p.key)} <span class="tx-pt">${esc(p.title)}</span></h2>
          <span class="tx-pctx" data-ctx></span>
          <span class="tx-pbtns"><button type="button" data-act="pmove" data-id="${p.id}" data-d="-1" aria-label="Move ${esc(p.title)} earlier" title="Move earlier">&#9664;</button><button type="button" data-act="pmove" data-id="${p.id}" data-d="1" aria-label="Move ${esc(p.title)} later" title="Move later">&#9654;</button><button type="button" data-act="psize" data-id="${p.id}" aria-label="${esc(p.title)} size ${pp.size}, change" title="Size: S, M, L or XL">${pp.size}</button><button type="button" data-act="pclose" data-id="${p.id}" aria-label="Hide ${esc(p.title)}" title="Hide (F-key brings it back)">&times;</button></span></header>
        <div class="tx-pb" data-body></div></section>`;
    }).join('') || '<p class="tx-empty">Every panel is hidden. Press a function key above to bring one back.</p>';
    const cb = document.querySelector('#tx-p-clips [data-body]');
    if (cb) cb.appendChild(keepClips || buildClipBody());
    paintKeys();
  }
  const visible = (id) => !!S && S.panels.some(p => p.id === id && p.on);
  // Show a panel and bring what the command is about into view: its chart or table (or `sel` inside it, a selector or an
  // element), not just its top edge, since a panel whose header peeks in at the bottom of the screen hides the chart.
  function showPanel(id, scroll = true, sel) {
    const pp = S.panels.find(p => p.id === id);
    if (pp && !pp.on) { pp.on = true; save(); renderLayout(); renderAll(); }
    if (!scroll) return;
    const el = $('tx-p-' + id);
    if (!el) return;
    const body = el.querySelector('[data-body]');
    const target = (sel instanceof Element ? sel : sel && el.querySelector(sel)) || (body && body.querySelector('svg.tx-svg, .tx-tablewrap')) || body || el;
    if (!inViewFit(target, 0.6)) scrollToShow(el, target);
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }
  function renderAll() {
    if (!ready) return;
    renderSel();
    for (const p of S.panels) if (p.on && RENDER[p.id]) RENDER[p.id]();
  }
  // Repaint one panel body, keeping keyboard focus and scroll position where they were.
  function paint(id, html, ctx) {
    const sec = $('tx-p-' + id); if (!sec) return null;
    const body = sec.querySelector('[data-body]');
    const a = document.activeElement, fid = a && body.contains(a) ? a.dataset.fid : null;
    const scs = [...body.querySelectorAll('.tx-scroll')].map(s => [s.scrollTop, s.scrollLeft]);
    if (tipFor && body.contains(tipFor)) hideTip();
    body.innerHTML = html;
    styleUp(body);
    [...body.querySelectorAll('.tx-scroll')].forEach((s, i) => { if (scs[i]) { s.scrollTop = scs[i][0]; s.scrollLeft = scs[i][1]; } });
    if (fid) {
      const el = body.querySelector(`[data-fid="${CSS.escape(fid)}"]`);
      if (el) { el.focus({ preventScroll: true }); if (el.tagName === 'INPUT' && el.type === 'search') el.setSelectionRange(el.value.length, el.value.length); }
    }
    if (ctx !== undefined) sec.querySelector('[data-ctx]').innerHTML = ctx;
    return body;
  }

  const listText = (xs) => xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : xs.join('');
  // About how wide a number is at a font size (digits are tabular; points and signs narrower): enough to skip labels
  // that would collide.
  const textW = (t, px) => [...String(t)].reduce((w, c) => w + (/[0-9]/.test(c) ? 0.56 : c === '.' ? 0.28 : c === '-' || c === '+' ? 0.36 : 0.6), 0) * px;
  // The width a chart gets in a panel body, so it can be drawn one unit to one pixel (labels keep their CSS size).
  function svgWidth(id, min) {
    const b = document.querySelector(`#tx-p-${id} [data-body]`);
    return Math.max(min, Math.floor((b ? b.clientWidth : 0) - 16));
  }

  // ------------------------------------------------------------------ the selection (linked across panels)
  // Select a player: every panel follows. What the panels need loads in the background (they say "Loading…" meanwhile).
  function select(pid, quiet) {
    const p = PID.get(pid); if (!p) return;
    S.focus = pid; S.club = p.club_id; scatCur = null;
    save(); renderAll();
    if (!quiet) out(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`);
  }
  // The same, waiting for the player's numbers first, so a command can bring them into view once they are drawn.
  async function selectReady(pid) {
    await Promise.all([settle(full(pid)), settle(similar(pid))]);
    select(pid, true);
  }
  function renderSel() {
    const f = PID.get(S.focus);
    const chips = S.compare.map((id, i) => { const p = PID.get(id); return `<span class="tx-chip" data-c="${CMP_COL[i]}"><button type="button" data-act="sel" data-pid="${esc(id)}" data-fid="chip-${esc(id)}">${esc(p.name)}</button><button type="button" class="tx-x" data-act="cmprm" data-pid="${esc(id)}" aria-label="Remove ${esc(p.name)} from the comparison">&times;</button></span>`; }).join('');
    $('txSel').innerHTML = `<span class="tx-sl">FOCUS</span><button type="button" class="tx-focus" data-act="pane" data-id="plyr">${esc(f.name)} <span>${esc(f.short_name)} ${esc(f.position)} #${esc(f.kit_number)}</span></button>
      <span class="tx-sl">CMP</span>${chips || '<span class="tx-dim">none</span>'}
      ${S.compare.includes(S.focus) || S.compare.length >= 3 ? '' : `<button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(S.focus)}">+ add ${esc(lastName(f))}</button>`}
      ${S.compare.length ? '<button type="button" class="tx-mini" data-act="cmpclear">Clear</button>' : ''}`;
    styleUp($('txSel'));
  }
  function addCompare(pid) {
    if (S.compare.includes(pid)) return;
    if (S.compare.length >= 3) S.compare.shift();
    S.compare.push(pid); save(); renderAll();
  }

  // ------------------------------------------------------------------ evidence into the clips panel
  // A metric built from several keys (a ratio's top and bottom, or a sum) lists each event once per key; merge them so
  // each event is one row that says which keys it counts toward (a ratio's "8 of 19" reads as 19 rows, 8 ticked).
  function mergeEvidence(ev) {
    const ki = new Map((ev.keys || []).map((k, i) => [k, i])), rows = [], at = new Map();
    for (const it of ev.items) {
      const id = `${it.match_id}|${it.event_id || 't' + it.t}`;
      let g = at.get(id);
      if (!g) { g = { it, in: [], v: [], notes: [] }; at.set(id, g); rows.push(g); }
      g.in.push(ki.has(it.metric) ? ki.get(it.metric) : 0); g.v.push(it.value);
      if (it.note && !g.notes.includes(it.note)) g.notes.push(it.note);
      if (!g.it.video_url && it.video_url) g.it = { ...g.it, video_url: it.video_url };
    }
    return rows;
  }
  function cellSub(m, c) {
    if (!c) return 'No minutes this season';
    return `${fmt(m, c.value)}${m.kind === 'ratio' && m.unit === '%' ? '' : ' ' + unitText(m)}${c.num != null ? ` · ${c.num} of ${c.den}` : c.total != null && m.kind !== 'total' ? ` · ${c.total} in total` : ''}${c.percentile != null ? ` · ${ord(c.percentile)} pctl` : ''}`;
  }
  function evidenceReel(pid, mk, ev, match) {
    const p = PID.get(pid), m = MK.get(mk), c = cellOf(p, mk);
    const r = { title: `${p.name} · ${m.label}${m.noisy ? ' ≈' : ''}`, sub: cellSub(m, c), items: [], i: -1, pid, mk, match: match || null, note: '' };
    if (!ev) { r.note = 'The moments behind this number did not load. Pick the number again to retry.'; return r; }
    const when = (it) => matchFor(it.match_id, p.club_id).when;
    if (ev.per_match) {
      r.items = ev.items.map(it => ({ when: when(it), minute: null, val: `${fmt(m, it.value)}${['m', 'km/h'].includes(m.unit) ? ' ' + m.unit : ''}`, note: `${Math.round(it.minutes)} min`, video: null, match_id: it.match_id }));
      r.unit = 'match';
      r.note = 'Physical numbers come from the 10 Hz motion record: one value per match, no single clip.';
    } else if ((ev.keys || []).length > 1) {
      const km = ev.keys.map(metricOrKey);
      const ratio = m.kind === 'ratio' && m.components && m.components[0] === ev.keys[0], count0 = evText(km[0], 1) === '';
      r.items = mergeEvidence(ev).map(g => {
        const parts = g.in.map((ki, j) => ({ m: km[ki], v: g.v[j], ki })), n = parts.find(x => x.ki === 0);
        let val, note;
        if (ratio && count0) { val = n ? '✓' : '✗'; note = n ? km[0].label : `${km[1].label} only`; }
        else if (ratio) { val = n ? evText(km[0], n.v) : '–'; note = n ? '' : `${km[1].label} only`; }
        else { val = parts.map(x => evText(x.m, x.v)).filter(Boolean).join(' · '); note = parts.map(x => x.m.label).join(' + '); }
        return { when: when(g.it), minute: g.it.minute, val, note: [note, ...g.notes.map(words)].filter(Boolean).join(' · '), video: g.it.video_url || null, match_id: g.it.match_id };
      });
      r.legend = ratio && count0 ? `One row per event: ✓ counts toward ${km[0].label} (the top of the ratio), ✗ only toward ${km[1].label}.`
        : ratio ? `One row per event, with its ${km[0].label}.` : 'One row per event, with what it counts toward.';
    } else {
      r.items = ev.items.map(it => ({ when: when(it), minute: it.minute, val: evText(m, it.value), note: it.note ? words(it.note) : '', video: it.video_url || null, match_id: it.match_id }));
    }
    if (!ev.complete) r.note = [r.note, 'Some moments did not load; pick the number again to retry.'].filter(Boolean).join(' ');
    if (match) {
      // The whole list is in (every page), so filtering it by match gives that match's moments, all of them.
      r.items = r.items.filter(it => it.match_id === match);
      const mf = matchFor(match, p.club_id);
      if (mf.mt) r.sub = `Round ${mf.round} ${mf.home ? 'v' : 'at'} ${club(mf.opp).name} · season ${r.sub}`;
      if (!r.items.length) r.note = 'No moments behind this number in this match.';
    }
    return r;
  }
  function openReel(r, startAt = 0) {
    reel = r;
    if (!visible('clips')) showPanel('clips', false);
    renderClips();
    const first = r.items.findIndex((it, i) => i >= startAt && it.video);
    if (first >= 0) play(first, true); else if (r.items.length) { reel.i = startAt; renderClips(); stopVideo(r.items[startAt] ? 'nolink' : ''); }
    else stopVideo('');
    revealClips();
  }
  // The scout must see the clip start: if most of the video (or, with nothing to play, the list) is out of view, behind
  // the sticky command bar or below the fold, bring the clips panel up.
  function revealClips() {
    const el = $('tx-p-clips');
    if (!el) return;
    const scr = el.querySelector('.tx-screen'), target = scr && !scr.hidden ? scr : el.querySelector('.tx-cliphead') || el;
    if (!inView(target, 0.75)) scrollToShow(el, el);
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }
  // While the moments load, the clips panel says so (a long list comes in pages of 500).
  function reelLoading(title) {
    reel = { title, sub: '', items: [], i: -1, note: 'Loading every moment behind this number…', loading: true };
    if (!visible('clips')) showPanel('clips', false);
    stopVideo('');
    renderClips();
  }
  async function openEvidence(pid, mk, match) {
    const p = PID.get(pid), m = MK.get(mk);
    if (!p || !m) return;
    const c = evidenceOf(pid, mk);
    if (c.st !== 'ok') { reelLoading(`${p.name} · ${m.label}`); revealClips(); }
    const ev = await settle(c);
    if (!ev) C.delete(`ev|${pid}|${mk}`);
    openReel(evidenceReel(pid, mk, ev, match));
  }
  // The bottom of what stays on top while scrolling: the sticky command bar (its height changes with the output line);
  // where the bar scrolls away (a phone), the site header when it sticks.
  function barBottom() {
    const bar = document.querySelector('.tx-top');
    if (bar && getComputedStyle(bar).position === 'sticky') return bar.getBoundingClientRect().bottom;
    const top = document.querySelector('header.top');
    return top && /sticky|fixed/.test(getComputedStyle(top).position) ? Math.max(0, top.getBoundingClientRect().bottom) : 0;
  }
  // At least `frac` of the element is on screen, below the sticky command bar.
  function inView(node, frac) {
    const r = node.getBoundingClientRect(); if (!r.height) return false;
    return Math.min(r.bottom, window.innerHeight) - Math.max(r.top, barBottom()) >= r.height * frac;
  }
  // At least `frac` of the element is on screen below the command bar, or of the screen's height when the element is taller.
  function inViewFit(node, frac) {
    const r = node.getBoundingClientRect(); if (!r.height) return false;
    const room = window.innerHeight - barBottom();
    return Math.min(r.bottom, window.innerHeight) - Math.max(r.top, barBottom()) >= Math.min(r.height, room) * frac;
  }
  // Scroll so the panel's top sits just below the command bar, unless that leaves the target running off the bottom: then
  // the target's own top goes there.
  function scrollToShow(el, target) {
    const bar = barBottom(), room = window.innerHeight - bar - 8;
    const pt = el.getBoundingClientRect().top, tr = target.getBoundingClientRect();
    const by = tr.bottom - pt <= room ? pt : tr.top;
    window.scrollTo({ top: Math.max(0, by + window.scrollY - bar - 8), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }

  // ------------------------------------------------------------------ CLIP: the clips panel (its video stays put)
  function buildClipBody() {
    const b = document.createElement('div');
    b.id = 'txClipBody';
    b.innerHTML = `<div class="tx-cliphead" data-r="head"></div>
      <div class="tx-screen"><video data-r="video" controls playsinline preload="none"></video><p class="tx-vmsg" data-r="msg" hidden></p></div>
      <div class="tx-clipctl"><button type="button" class="tx-mini" data-act="cprev" aria-label="Previous moment">&#9664; Prev</button><button type="button" class="tx-mini" data-act="cnext" aria-label="Next moment">Next &#9654;</button>
        <label class="tx-chk"><input type="checkbox" data-r="auto" checked> Play all</label></div>
      <ol class="tx-cliplist tx-scroll" data-r="list"></ol>`;
    const v = b.querySelector('video');
    v.addEventListener('error', () => { if (v.getAttribute('src')) msg('This moment could not be played just now. Try again in a moment.'); });
    v.addEventListener('playing', () => msg(''));
    v.addEventListener('ended', () => {
      if (!reel || !b.querySelector('[data-r="auto"]').checked) return;
      const nx = reel.items.findIndex((it, i) => i > reel.i && it.video);
      if (nx >= 0) play(nx, true);
    });
    return b;
  }
  const clipVideo = () => document.querySelector('#txClipBody video');
  function msg(t) { const m = document.querySelector('#txClipBody [data-r="msg"]'); if (!m) return; m.textContent = t; m.hidden = !t; }
  function renderClips() {
    const b = $('txClipBody'); if (!b) return;
    const head = b.querySelector('[data-r="head"]'), list = b.querySelector('[data-r="list"]');
    const ctx = document.querySelector('#tx-p-clips [data-ctx]');
    b.querySelector('.tx-screen').hidden = !reel || reel.loading;
    b.querySelector('.tx-clipctl').hidden = !reel || reel.loading;
    if (!reel) {
      head.innerHTML = '<p class="tx-dim">Pick any number in any panel: the moments behind it play here.</p>';
      list.innerHTML = ''; if (ctx) ctx.textContent = ''; return;
    }
    const n = reel.items.length, unit = reel.unit === 'match' ? (n === 1 ? 'match' : 'matches') : (n === 1 ? 'moment' : 'moments');
    head.innerHTML = `<p class="tx-ct">${esc(reel.title)}</p>${reel.sub ? `<p class="tx-cs">${esc(reel.sub)}</p>` : ''}
      ${reel.loading ? '' : `<p class="tx-cs">${reel.match ? `${esc(n)} in this match` : `${esc(n)} ${unit}`}</p>`}
      ${reel.legend ? `<p class="tx-cs tx-dim">${esc(reel.legend)}</p>` : ''}${reel.note ? `<p class="tx-cs tx-dim">${esc(reel.note)}</p>` : ''}`;
    if (ctx) ctx.textContent = n ? `${Math.max(0, reel.i) + 1}/${n}` : '';
    list.innerHTML = reel.items.map((it, i) => `<li><button type="button" class="tx-clip${i === reel.i ? ' on' : ''}" data-act="clip" data-i="${i}" data-fid="clip-${i}"${i === reel.i ? ' aria-current="true"' : ''}>
        <span class="tx-cw">${esc(it.when)}${it.minute != null ? ` <b>${esc(it.minute)}'</b>` : ''}</span><span class="tx-cv">${esc(it.val)}</span><span class="tx-cn">${esc(it.note)}${it.video ? '' : ' <i>no clip</i>'}</span></button></li>`).join('');
  }
  function play(i, auto) {
    if (!reel || !reel.items[i]) return;
    reel.i = i; renderClips();
    const it = reel.items[i], v = clipVideo(); if (!v) return;
    if (!it.video || !VIDEO.test(String(it.video))) { stopVideo('nolink'); return; }
    msg('');
    if (v.getAttribute('src') !== it.video) { v.setAttribute('src', it.video); v.load(); } else v.currentTime = 0;
    if (auto) { const pr = v.play(); if (pr && pr.catch) pr.catch(() => { if (v.getAttribute('src') === it.video && v.paused) msg('Cutting the clip… press play in a moment.'); }); }
  }
  function stopVideo(why) {
    const v = clipVideo(); if (!v) return;
    v.pause(); v.removeAttribute('src'); v.load();
    msg(why === 'nolink' ? (reel && reel.note) || 'This moment has no video.' : '');
  }

  // ------------------------------------------------------------------ SCRN: the screener
  function screenRows() {
    const sc = S.scr, q = norm(sc.q);
    const rows = PLAYERS.filter(p => p.minutes > 0 && (!sc.pos || p.position === sc.pos) && (!sc.qual || p.qualified)
      && (!q || norm(p.name).includes(q) || norm(p.club).includes(q) || norm(p.short_name) === q));
    const k = sc.sort.k, dir = sc.sort.dir;
    const m = MK.get(k);
    rows.sort((a, b) => {
      if (k === 'name') return dir * a.name.localeCompare(b.name);
      if (k === 'club') return dir * a.club.localeCompare(b.club) || a.name.localeCompare(b.name);
      if (k === 'min') return dir * (a.minutes - b.minutes);
      const ca = cellOf(a, k), cb = cellOf(b, k);
      const qa = rankable(m, ca), qb = rankable(m, cb);
      if (qa !== qb) return qa ? -1 : 1;
      const va = ca ? ca.value : null, vb = cb ? cb.value : null;
      if (va == null || vb == null) return va == null ? (vb == null ? 0 : 1) : -1;
      return dir * (va - vb) || tieBreak(m, dir, a, ca, b, cb) || a.name.localeCompare(b.name);
    });
    return rows;
  }
  // Values come rounded, so equal values may hide different true rates. Break the tie as the engine orders it (by the
  // unrounded value), in the sort direction: the unrounded rate where the counts give it, else the percentile (which the
  // engine computed from the unrounded values; it runs the metric's better way, so it flips for lower-is-better).
  function rawOf(m, p, c) {
    if (!c) return null;
    if (m.kind === 'ratio' && c.num != null && c.den) return c.num / c.den;
    if (m.kind === 'per90' && c.total != null && p.minutes > 0) return c.total / p.minutes;
    return null;
  }
  function tieBreak(m, dir, a, ca, b, cb) {
    const ra = rawOf(m, a, ca), rb = rawOf(m, b, cb);
    if (ra != null && rb != null && ra !== rb) return dir * (ra - rb);
    const pa = ca && ca.percentile, pb = cb && cb.percentile;
    if (pa == null || pb == null || pa === pb || a.position !== b.position) return 0;   // percentiles compare only within one pool
    return (m.higher_is_better === false ? -dir : dir) * (pa - pb);
  }
  // Ranked as the engine's /api/terminal/rank ranks: by value, every player in the metric's qualifying pool (enough
  // minutes, and for a ratio enough attempts) whatever their position; season counts rank whenever they have a value. The
  // percentile is a separate thing (position peers only) and only the shading and the Pctl view show it.
  const rankable = (m, c) => !!(c && c.value != null && (c.qualified || m.kind === 'total'));
  // Rows with the same shown value share a rank (1, 2, 2, 4); rows outside the pool are listed after, unranked.
  function screenRanks(rows) {
    const k = S.scr.sort.k, m = MK.get(k);
    if (!m) return rows.map((_, i) => i + 1);
    let prev = null, place = 0;
    return rows.map((p, i) => {
      const c = cellOf(p, k);
      if (!rankable(m, c)) return null;
      const v = fmt(m, c.value);
      if (v !== prev) { place = i + 1; prev = v; }
      return place;
    });
  }
  function metricOptions(sel, filter) {
    return (CAT.groups || []).map(g => {
      const ms = METRICS.filter(m => m.group === g.key && (!filter || filter(m)));
      return ms.length ? `<optgroup label="${esc(g.label)}">${ms.map(m => `<option value="${esc(m.key)}"${m.key === sel ? ' selected' : ''}>${esc(m.label)}${m.noisy ? ' ≈' : ''}</option>`).join('')}</optgroup>` : '';
    }).join('');
  }
  function renderScrn() {
    const sc = S.scr, cols = sc.cols.filter(k => MK.has(k));
    const sortCols = MK.has(sc.sort.k) ? [...new Set([...cols, sc.sort.k])] : cols;
    const all = ensureCols(sortCols);
    const rows = screenRows();
    const sortAttr = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? 'descending' : 'ascending') : 'none';
    const arrow = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? ' ▼' : ' ▲') : '';
    if (!scrAct || !rows.some(p => p.id === scrAct.pid)) scrAct = { pid: rows.some(p => p.id === S.focus) ? S.focus : (rows[0] && rows[0].id), c: 0 };
    if (scrAct.c > cols.length) scrAct.c = 0;
    const cell = (p, k, ci) => {
      const m = MK.get(k), act = scrAct.pid === p.id && scrAct.c === ci + 1, c = cellOf(p, k);
      if (!COLS.has(k) && !c) return `<td class="num"><span class="tx-dim" aria-label="loading">…</span></td>`;
      if (!c) return '<td class="num"><span class="tx-dim">–</span></td>';
      const txt = sc.mode === 'pct' ? (c.percentile == null ? '–' : c.percentile) : fmt(m, c.value);
      const np = noPct(p, m, c);
      const lab = `${p.name}, ${m.label} ${fmt(m, c.value)}${c.percentile != null ? `, ${ord(c.percentile)} percentile` : np ? `, ${np.text}` : ''}. Open its moments`;
      return `<td class="num"><button type="button" class="tx-n${np && np.small ? ' uq' : ''}"${shade(m, c.percentile)} data-act="ev" data-sel="1" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-nav data-fid="c-${esc(p.id)}-${esc(k)}" tabindex="${act ? 0 : -1}" aria-label="${esc(lab)}">${esc(txt)}</button></td>`;
    };
    const head = `<tr><th class="tx-stk" aria-sort="${sortAttr('name')}"><button type="button" data-act="sort" data-k="name" data-fid="h-name">Player${arrow('name')}</button></th>
      <th aria-sort="${sortAttr('club')}"><button type="button" data-act="sort" data-k="club" data-fid="h-club">Club${arrow('club')}</button></th><th>Pos</th>
      <th class="num" aria-sort="${sortAttr('min')}"><button type="button" data-act="sort" data-k="min" data-fid="h-min">Min${arrow('min')}</button></th>
      ${cols.map(k => { const m = MK.get(k); return `<th class="num" aria-sort="${sortAttr(k)}"><span class="tx-th"><button type="button" data-act="sort" data-k="${esc(k)}" data-mk="${esc(k)}" data-fid="h-${esc(k)}">${esc(m.label)}${noisy(m)}${arrow(k)}</button><button type="button" class="tx-x" data-act="rmcol" data-k="${esc(k)}" aria-label="Remove the ${esc(m.label)} column">&times;</button></span></th>`; }).join('')}</tr>`;
    const ranks = all ? screenRanks(rows) : rows.map(() => null);
    const body = rows.map((p, r) => {
      const ci = S.compare.indexOf(p.id), act = scrAct.pid === p.id && scrAct.c === 0;
      return `<tr class="${p.id === S.focus ? 'on' : ''}${ci >= 0 ? ' cmp' : ''}"${ci >= 0 ? ` data-c="${CMP_COL[ci]}"` : ''}>
        <th class="tx-stk" scope="row"><span class="tx-rk">${ranks[r] == null ? '–' : ranks[r]}</span><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-nav data-fid="n-${esc(p.id)}" tabindex="${act ? 0 : -1}"${p.id === S.focus ? ' aria-current="true"' : ''}>${esc(p.name)}</button></th>
        <td>${esc(p.short_name)}</td><td>${esc(p.position)} <span class="tx-dim">${esc(p.role)}</span></td><td class="num">${esc(Math.round(p.minutes))}</td>
        ${cols.map((k, i) => cell(p, k, i)).join('')}</tr>`;
    }).join('');
    const status = colsErr ? ` · <span class="tx-bad">a column did not load (${esc(errText(colsErr))})</span> <button type="button" class="tx-mini" data-act="colsretry">Retry</button>`
      : all ? '' : ' · <span class="tx-wait">loading columns…</span>';
    const html = `<div class="tx-ctls">
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scrpos" data-v="${v || ''}" aria-pressed="${sc.pos === v}">${v || 'ALL'}</button>`).join('')}</div>
        <label class="tx-ctl"><span class="sr">Filter by name or club</span><input type="search" data-r="scrq" data-fid="scr-q" value="${esc(sc.q)}" placeholder="Filter name / club" autocomplete="off" maxlength="40"></label>
        <label class="tx-chk"><input type="checkbox" data-r="scrqual" data-fid="scr-qual"${sc.qual ? ' checked' : ''}> Qualified (${esc(minMinutes())}+ min)</label>
        <div class="tx-seg" role="group" aria-label="Show"><button type="button" data-act="scrmode" data-v="val" aria-pressed="${sc.mode === 'val'}">Value</button><button type="button" data-act="scrmode" data-v="pct" aria-pressed="${sc.mode === 'pct'}">Pctl</button></div>
        <label class="tx-ctl"><span class="sr">Add a column</span><select data-r="addcol" data-fid="scr-add"${cols.length >= MAX_COLS ? ' disabled' : ''}><option value="">+ Add column…</option>${metricOptions(null, m => !cols.includes(m.key))}</select></label>
        <button type="button" class="tx-mini" data-act="scrdef">Default columns</button></div>
      <p class="tx-cap">${rows.length} ${esc(sc.pos ? POSN[sc.pos] : 'players')}${sc.qual ? ', qualified' : ''} · ranked by value (ratios need the minimum attempts) · shading = percentile vs position peers, where the metric is scored for that position · Alt+1 enters the table, arrow keys move, Enter opens${status}</p>
      <div class="tx-scroll tx-tablewrap"><table class="tx-table"><thead>${head}</thead><tbody data-r="grid">${body || `<tr><td colspan="${4 + cols.length}" class="tx-dim">No players match.</td></tr>`}</tbody></table></div>`;
    paint('scrn', html, esc(sc.sort.k && MK.has(sc.sort.k) ? `sorted by ${MK.get(sc.sort.k).label}` : ''));
  }
  // Alt+1 / F1: straight into the screener's table, on its active cell (one tab stop; arrows move from there).
  function focusGrid() {
    const cellEl = document.querySelector('#tx-p-scrn tbody[data-r="grid"] [data-nav][tabindex="0"]') || document.querySelector('#tx-p-scrn tbody[data-r="grid"] [data-nav]');
    if (cellEl) { cellEl.focus({ preventScroll: true }); cellEl.scrollIntoView({ block: 'nearest', inline: 'nearest' }); return true; }
    return false;
  }

  // ------------------------------------------------------------------ PLYR: the player card, top numbers, similar players
  function renderPlyr() {
    const p = PID.get(S.focus);
    const fc = full(p.id, 'plyr'), sm = similar(p.id, 'plyr');
    const bio = [['Age', p.age], ['Height', p.height_cm ? p.height_cm + ' cm' : '–'], ['Foot', p.preferred_foot ? p.preferred_foot.charAt(0).toUpperCase() + p.preferred_foot.slice(1) : '–'], ['Nation', p.nationality],
      ['Minutes', Math.round(p.minutes)], ['Apps', p.appearances]];
    let best;
    if (fc.st !== 'ok') best = waitHtml(fc, `${p.name}'s numbers`);
    else {
      const strengths = METRICS.filter(m => m.positions.includes(p.position) && m.has_percentile && m.higher_is_better !== null && pctOf(p, m.key) != null)
        .sort((a, b) => pctOf(p, b.key) - pctOf(p, a.key)).slice(0, 6);
      best = p.minutes > 0 ? `<h3 class="tx-h3">Best vs ${esc(POSN[p.position])}</h3>
        <table class="tx-mt tx-best"><tbody>${strengths.map(m => mrow(p, m)).join('') || '<tr><td class="tx-dim">No percentiles yet (too few minutes).</td></tr>'}</tbody></table>` : '<p class="tx-dim">No minutes this season.</p>';
    }
    let sim;
    if (sm.st !== 'ok') sim = waitHtml(sm, 'similar players');
    else {
      const list = sm.v.similar || [];
      sim = list.length ? `<ol class="tx-sim">${list.map(s => `<li><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(s.global_id)}" data-fid="sim-${esc(s.global_id)}">${esc(s.name)}</button>
        <span class="tx-dim">${esc(s.short_name)} ${esc(s.position)}</span><span class="tx-simbar" aria-label="similarity ${esc(s.similarity)}"><i data-w="${Math.max(2, Math.round(s.similarity * 100))}"></i></span><span class="num">${esc(Number(s.similarity).toFixed(2))}</span>
        <span class="tx-shared">${(s.shared_strengths || []).filter(k => MK.has(k)).map(k => `<button type="button" class="tx-kchip" data-act="ev" data-pid="${esc(s.global_id)}" data-mk="${esc(k)}" data-fid="sim-${esc(s.global_id)}-${esc(k)}">${esc(MK.get(k).label)}</button>`).join('')}</span></li>`).join('')}</ol>
        <p class="tx-cap">Cosine similarity on the ${esc(p.position === 'GK' ? 'goalkeeper' : 'outfield')} template among qualified ${esc(POSN[p.position])}; chips are shared strengths (open them for that player).${list.every(s => s.similarity < 0.5) ? ' No close match: every similarity is under 0.50.' : ''}</p>` : '<p class="tx-dim">No similar players (too few minutes).</p>';
    }
    const html = `<div class="tx-card"><span class="tx-shirt" aria-hidden="true">${shirt(p)}</span>
        <div><p class="tx-name">${esc(p.name)}</p><p class="tx-line">${esc(p.club)} · ${esc(POS1[p.position])} (${esc(p.role)}) · #${esc(p.kit_number)}
          ${p.qualified ? '<span class="tx-tag">QUALIFIED</span>' : `<span class="tx-tag dim">UNDER ${esc(minMinutes())} MIN</span>`}</p></div></div>
      <dl class="tx-bio">${bio.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v ?? '–')}</dd></div>`).join('')}</dl>
      <div class="tx-acts"><button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(p.id)}"${S.compare.includes(p.id) ? ' disabled' : ''}>+ Compare</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="SHOT ${esc(p.name)}">Shots</button><button type="button" class="tx-mini" data-act="run" data-cmd="FORM ${esc(p.name)}">Form</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="TEAM ${esc(p.short_name)}">Team</button>
        <a class="tx-mini tx-link" href="/players/${enc(p.id)}">Profile</a></div>
      ${best}
      <h3 class="tx-h3" id="txSimHead" tabindex="-1">SIM · most similar</h3>${sim}`;
    paint('plyr', html, esc(p.short_name));
  }
  // One metric row: label (definition on hover), value button (evidence), percentile bar.
  function mrow(p, m, opts = {}) {
    const c = cellOf(p, m.key);
    const val = c ? `<button type="button" class="tx-n"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(m.key)}" data-fid="${esc((opts.fid || 'm') + '-' + p.id + '-' + m.key)}" aria-label="${esc(`${m.label} ${fmt(m, c.value)}, open its moments`)}">${esc(fmt(m, c.value))}</button>` : '<span class="tx-dim">–</span>';
    const pc = c ? c.percentile : null;
    return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(m.key)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span></th><td class="num">${val}</td>
      <td class="tx-pbar"><span class="tx-bar" data-g="${GROUP_COL[m.group] || '#ffcd28'}"><i data-w="${pc == null ? 0 : Math.max(2, pc)}"></i></span></td><td class="num tx-pc">${pc == null ? '–' : esc(pc)}</td></tr>`;
  }

  // ------------------------------------------------------------------ RDR: pizza (one player) or radar (compare)
  const polar = (cx, cy, r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)];
  function wedge(cx, cy, r0, r1, a0, a1) {
    const [x0, y0] = polar(cx, cy, r1, a0), [x1, y1] = polar(cx, cy, r1, a1), [x2, y2] = polar(cx, cy, r0, a1), [x3, y3] = polar(cx, cy, r0, a0);
    const f = (n) => n.toFixed(2);
    return `M${f(x0)},${f(y0)} A${r1},${r1} 0 0 1 ${f(x1)},${f(y1)} L${f(x2)},${f(y2)} A${r0},${r0} 0 0 0 ${f(x3)},${f(y3)} Z`;
  }
  function axisLabels(keys, cx, cy, R) {
    const n = keys.length;
    return keys.map((k, i) => {
      const a = (i + 0.5) * 2 * Math.PI / n, [x, y] = polar(cx, cy, R + 10, a), s = Math.sin(a);
      const lab = MK.get(k).label, t = lab.length > 16 ? lab.slice(0, 15) + '…' : lab;
      return `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${s > 0.25 ? 'start' : s < -0.25 ? 'end' : 'middle'}" class="tx-axl">${esc(t)}</text>`;
    }).join('');
  }
  // A player's outline on the radar. A metric with no percentile is a gap in the outline, never a point at the centre
  // (which would read as the 0th percentile): the outline breaks there, and a lone point between two gaps is a dot.
  function outline(pts, attrs, fill) {
    const f = (q) => q.map(v => v.toFixed(1)).join(',');
    if (pts.every(Boolean)) return `<polygon points="${pts.map(f).join(' ')}" ${fill} ${attrs}/>`;
    const n = pts.length, start = pts.findIndex(q => !q);
    let svg = '', run = [];
    const flush = () => {
      if (run.length > 1) svg += `<polyline points="${run.map(f).join(' ')}" fill="none" ${attrs}/>`;
      else if (run.length === 1) svg += `<circle cx="${run[0][0].toFixed(1)}" cy="${run[0][1].toFixed(1)}" r="3" ${attrs}/>`;
      run = [];
    };
    for (let j = 1; j <= n; j++) { const q = pts[(start + j) % n]; if (q) run.push(q); else flush(); }
    flush();
    return svg;
  }
  function renderRadar() {
    const f = PID.get(S.focus);
    const players = S.compare.length >= 2 ? S.compare.map(id => PID.get(id)) : [f];
    const base = players[0], outsider = players.length > 1 && !S.compare.includes(f.id) ? f : null;
    const loads = [...players, ...(outsider ? [outsider] : [])].map(p => full(p.id, 'radar'));
    const waiting = loads.find(c => c.st !== 'ok');
    if (waiting) { paint('radar', waitHtml(waiting, 'the percentiles'), players.length > 1 ? 'CMP' : esc(base.short_name)); return; }
    const keys = (S.radar.tpl === 'all' ? CAT.default_columns.all : (CAT.default_columns[base.position] || CAT.default_columns.all)).filter(k => MK.has(k));
    const n = keys.length, cx = 180, cy = 158, R = 96, r0 = 14;
    let svg = '<svg viewBox="0 0 360 316" class="tx-svg tx-radar" aria-hidden="true">';
    for (const q of [25, 50, 75, 100]) svg += `<circle cx="${cx}" cy="${cy}" r="${(r0 + (R - r0) * q / 100).toFixed(1)}" class="tx-ring"/>`;
    let gaps = false, outsiderNote = '';
    const blank = [];      // compared players with no percentile at all on this template: not drawn, and the note says why
    const whyBlank = (p) => p.position !== base.position && keys.every(k => !MK.get(k).positions.includes(p.position))
      ? `${POSN[p.position]} are not scored on the ${base.position} template`
      : (noPct(p, MK.get(keys[0]), cellOf(p, keys[0])) || { text: 'no percentile on this template' }).text.replace(/^no percentile: /, '');
    if (players.length === 1) {
      keys.forEach((k, i) => {
        const a0 = i * 2 * Math.PI / n + 0.01, a1 = (i + 1) * 2 * Math.PI / n - 0.01, pc = pctOf(base, k), m = MK.get(k);
        const r1 = r0 + (R - r0) * (pc == null ? 0 : Math.max(3, pc)) / 100;
        svg += `<path d="${wedge(cx, cy, r0, R, a0, a1)}" class="tx-wbg"/>`;
        if (pc != null) svg += `<path d="${wedge(cx, cy, r0, r1, a0, a1)}" fill="${GROUP_COL[m.group] || '#ffcd28'}" fill-opacity="${m.higher_is_better === null ? 0.45 : 0.85}" class="tx-wedge" data-act="ev" data-pid="${esc(base.id)}" data-mk="${esc(k)}"><title>${esc(m.label)}: ${esc(fmt(m, cellOf(base, k).value))}, ${esc(ord(pc))} percentile</title></path>`;
        else gaps = true;
        // The value sits inside its wedge when the wedge has room (black on a solid wedge, white on a style marker's paler
        // one), else just outside it in light text on the dark ring: each choice is at least 4.5:1.
        const inside = r1 - r0 >= 18, [tx, ty] = polar(cx, cy, inside ? r1 - 9 : r1 + 9, (a0 + a1) / 2);
        const tone = !inside ? 'out' : m.higher_is_better === null ? 'lt' : '';
        svg += `<text x="${tx.toFixed(1)}" y="${(ty + 4).toFixed(1)}" text-anchor="middle" class="tx-wv ${tone}">${pc == null ? '–' : esc(pc)}</text>`;
      });
    } else {
      keys.forEach((k, i) => { const [x, y] = polar(cx, cy, R, (i + 0.5) * 2 * Math.PI / n); svg += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="tx-ring"/>`; });
      const ptsOf = (p) => keys.map((k, i) => { const pc = pctOf(p, k); return pc == null ? null : polar(cx, cy, r0 + (R - r0) * pc / 100, (i + 0.5) * 2 * Math.PI / n); });
      players.forEach((p, j) => {
        const pts = ptsOf(p);
        if (!pts.some(Boolean)) { blank.push(p); return; }
        if (pts.some(q => !q)) gaps = true;
        svg += outline(pts, `stroke="${CMP_COL[j]}" stroke-width="2"`, `fill="${CMP_COL[j]}" fill-opacity=".14"`);
      });
      // The focus player, when not one of the compared, is a dashed outline so selecting a player still moves RDR; with
      // no percentile on this template at all (a keeper on a forward template), it is not drawn and the note says why.
      if (outsider) {
        const pts = ptsOf(outsider);
        if (pts.some(Boolean)) {
          if (pts.some(q => !q)) gaps = true;
          svg += outline(pts, 'stroke="#fff" stroke-width="1.5" stroke-dasharray="4 3" class="tx-rfocus"', 'fill="none"');
        } else {
          outsiderNote = `${outsider.name} is not drawn: ${whyBlank(outsider)}.`;
        }
      }
    }
    svg += axisLabels(keys, cx, cy, R) + '</svg>';
    const legend = players.map((p, j) => `<button type="button" class="tx-leg" data-c="${CMP_COL[players.length > 1 ? j : 0]}" data-act="sel" data-pid="${esc(p.id)}" data-fid="rl-${esc(p.id)}">${esc(p.name)} <span class="tx-dim">${esc(p.short_name)} ${esc(p.position)}</span></button>`).join('')
      + (outsider && !outsiderNote ? `<span class="tx-leg tx-legf">${esc(outsider.name)} <span class="tx-dim">${esc(outsider.short_name)} ${esc(outsider.position)} · focus, dashed</span></span>` : '');
    const outLine = outsider ? `<p class="tx-cap tx-rnote">${outsiderNote ? esc(outsiderNote) : `Comparing ${players.length}; ${esc(outsider.name)} (the focus) is the dashed outline, not in the table.`} <button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(outsider.id)}" data-fid="r-add">+ add${players.length >= 3 ? ` (replaces ${esc(lastName(players[0]))})` : ''}</button></p>` : '';
    const tbl = players.length === 1 ? `<table class="tx-mt"><tbody>${keys.map(k => mrow(base, MK.get(k), { fid: 'r' })).join('')}</tbody></table>`
      : `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cmp"><thead><tr><th>Metric</th>${players.map((p, j) => `<th class="num" data-fg="${CMP_COL[j]}">${esc(initials(p))}</th>`).join('')}</tr></thead><tbody>
        ${keys.map(k => { const m = MK.get(k); return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(k)}">${esc(m.label)}${noisy(m)}</span></th>${players.map(p => { const c = cellOf(p, k); return `<td class="num">${c ? `<button type="button" class="tx-n"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="rc-${esc(p.id)}-${esc(k)}" aria-label="${esc(`${p.name}, ${m.label} ${fmt(m, c.value)}, ${c.percentile == null ? (noPct(p, m, c) || { text: 'no percentile' }).text : ord(c.percentile) + ' percentile'}, open its moments`)}">${esc(fmt(m, c.value))}</button><span class="tx-pc"> ${c.percentile == null ? '–' : esc(c.percentile)}</span>` : '<span class="tx-dim">–</span>'}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div>`;
    const html = `<div class="tx-ctls"><div class="tx-seg" role="group" aria-label="Metrics"><button type="button" data-act="rtpl" data-v="pos" aria-pressed="${S.radar.tpl === 'pos'}">${esc(base.position)} template</button><button type="button" data-act="rtpl" data-v="all" aria-pressed="${S.radar.tpl === 'all'}">All-round</button></div></div>
      <div class="tx-legs">${legend}</div>${outLine}${blank.map(p => `<p class="tx-cap tx-rnote">${esc(`${p.name} has no outline: ${whyBlank(p)}. The table has the values.`)}</p>`).join('')}${svg}
      <p class="tx-cap">Percentile vs qualified ${esc(players.length > 1 ? 'peers in each player’s own position' : POSN[base.position])}${players.length > 1 ? '' : '; blue-grey wedges are style markers (ranked, not judged)'}.${gaps ? ` ${players.length > 1 ? 'A gap in an outline' : 'An empty wedge'} is a metric with no percentile for that player (the table and its tips say why), never the 0th.` : ''} Values open their moments.</p>${tbl}`;
    paint('radar', html, players.length > 1 ? (outsider ? `CMP + ${esc(lastName(outsider))}` : 'CMP') : esc(base.short_name));
  }

  // ------------------------------------------------------------------ SHOT and HEAT: pitch charts
  const PL = '<g class="tx-lines">';
  function halfPitch() {
    return `<rect x="52.5" y="0" width="52.5" height="68" class="tx-turf"/>${PL}<rect x="52.5" y="0" width="52.5" height="68"/>
      <path d="M52.5,24.85 A9.15,9.15 0 0 1 52.5,43.15"/><rect x="88.5" y="13.84" width="16.5" height="40.32"/><rect x="99.5" y="24.84" width="5.5" height="18.32"/>
      <path d="M88.5,26.69 A9.15,9.15 0 0 0 88.5,41.31"/><circle cx="94" cy="34" r=".3"/><line x1="105" y1="30.34" x2="105" y2="37.66" class="tx-goal"/></g>`;
  }
  function fullPitch() {
    return `${PL}<rect x="0" y="0" width="105" height="68"/><line x1="52.5" y1="0" x2="52.5" y2="68"/><circle cx="52.5" cy="34" r="9.15"/>
      <rect x="0" y="13.84" width="16.5" height="40.32"/><rect x="88.5" y="13.84" width="16.5" height="40.32"/><rect x="0" y="24.84" width="5.5" height="18.32"/><rect x="99.5" y="24.84" width="5.5" height="18.32"/></g>`;
  }
  const OUTC = { goal: 'Goal', saved: 'Saved', blocked: 'Blocked', off_target: 'Off target' };
  const OUTCLASS = (o) => Object.prototype.hasOwnProperty.call(OUTC, o) ? o : 'other';
  const bodyText = (b) => String(b || 'unknown').replace(/_/g, ' ');
  function numBtn(p, k, fid) {
    const m = MK.get(k), c = cellOf(p, k); if (!m) return '';
    return `<span class="tx-stat"><span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${c ? `<button type="button" class="tx-n"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="${esc(fid + k)}" aria-label="${esc(`${m.label} ${fmt(m, c.value)}, open its moments`)}">${esc(fmt(m, c.value))}</button>${c.total != null && m.kind !== 'total' && m.kind !== 'ratio' ? `<span class="tx-dim">${esc(c.total)} tot</span>` : ''}` : '<span class="tx-dim">–</span>'}</span>`;
  }
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
  function renderShot() {
    const p = PID.get(S.focus), fc = full(p.id, 'shot'), sc = shotsOf(p.id, 'shot');
    if (fc.st !== 'ok' || sc.st !== 'ok') { paint('shot', waitHtml(fc.st !== 'ok' ? fc : sc, `${p.name}'s shots`), esc(p.short_name)); return; }
    const shots = sc.v.shots || [];
    const playing = reel && reel.kind === 'shots' && reel.pid === p.id ? reel.i : -1;
    let svg = `<svg viewBox="51.5 -1.5 55 71" class="tx-svg tx-pitchsvg" role="group" aria-label="Shot map, ${shots.length} shots; each plays its clip">${halfPitch()}`;
    shots.forEach((s, i) => {
      const x = num(s.x), y = num(s.y);
      if (x == null || y == null) return;
      const r = (0.9 + Math.sqrt(Math.max(0, num(s.xg) || 0)) * 3.4).toFixed(2);
      const mf = matchFor(s.match_id, s.club_id);
      const lab = `${mf.when} ${s.minute}', ${bodyText(s.body_part)}, xG ${Number(s.xg).toFixed(2)}, ${OUTC[s.outcome] || 'Shot'}${s.penalty ? ', penalty' : ''}. Play`;
      svg += `<g class="tx-shot o-${OUTCLASS(s.outcome)}${i === playing ? ' on' : ''}" role="button" tabindex="0" data-act="shot" data-i="${i}" data-fid="shot-${i}" aria-label="${esc(lab)}"><circle cx="${x}" cy="${y}" r="${r}"/><title>${esc(lab)}</title></g>`;
    });
    if (!shots.length) svg += '<text x="78" y="36" text-anchor="middle" class="tx-axl tx-noshots">No shots</text>';
    svg += '</svg>';
    const nps = shots.filter(s => !s.penalty);
    const html = shots.length || p.minutes ? `<div class="tx-stats">${['shots', 'goals', 'npxg', 'npxg_per_shot', 'shots_on_target'].map(k => numBtn(p, k, 'sh-')).join('')}</div>${svg}
      <p class="tx-legend"><span class="o-goal">● Goal</span> <span class="o-saved">● Saved</span> <span class="o-blocked">● Blocked</span> <span class="o-off_target">○ Off target</span> · size = xG · ${nps.length} non-penalty, ${shots.length - nps.length} penalty${shots.length - nps.length ? ' (on the map; Shots and npxG leave penalties out, Goals counts them)' : ''}</p>`
      : '<p class="tx-dim">No minutes this season.</p>';
    paint('shot', html, esc(`${p.short_name} · ${shots.length}`));
  }
  function shotReel(p, start) {
    const c = shotsOf(p.id);
    if (c.st !== 'ok') return;
    const shots = c.v.shots || [];
    const r = { kind: 'shots', pid: p.id, title: `${p.name} · Shots`, sub: `${shots.length} shots, penalties included`, i: -1, note: '',
      items: shots.map(s => ({ when: matchFor(s.match_id, s.club_id).when, minute: s.minute, val: `xG ${Number(s.xg).toFixed(2)}`, note: `${OUTC[s.outcome] || 'Shot'}${s.penalty ? ' · pen' : ''} · ${bodyText(s.body_part)}`, video: s.video_url, match_id: s.match_id })) };
    openReel(r, start);
    if (visible('shot')) renderShot();
  }
  function renderHeat() {
    const p = PID.get(S.focus), fc = full(p.id, 'heat'), pc = heatOf(p.id, 'heat');
    if (fc.st !== 'ok' || pc.st !== 'ok') { paint('heat', waitHtml(fc.st !== 'ok' ? fc : pc, `${p.name}'s touches`), esc(p.short_name)); return; }
    const hm = Array.isArray(pc.v.grid) ? pc.v.grid : [];
    const [cols, rows] = (CAT.pitch && CAT.pitch.heatmap_grid) || [12, 8], cw = 105 / cols, ch = 68 / rows;
    const flat = hm.flat().map(v => Number(v) || 0);
    const max = Math.max(1, ...flat), total = flat.reduce((a, b) => a + b, 0);
    let cells = '';
    hm.forEach((row, y) => (row || []).forEach((v0, x) => { const v = Number(v0) || 0; if (v) cells += `<rect x="${(x * cw).toFixed(2)}" y="${(y * ch).toFixed(2)}" width="${cw.toFixed(2)}" height="${ch.toFixed(2)}" fill="#ffcd28" fill-opacity="${(0.08 + 0.8 * v / max).toFixed(3)}"><title>${v} on-ball action${v === 1 ? '' : 's'}</title></rect>`; }));
    const EVN = { touch: 'touches', pass: 'passes', cross: 'crosses', carry: 'carries', take_on: 'take-ons', shot: 'shots', tackle: 'tackles', interception: 'interceptions', recovery: 'recoveries', clearance: 'clearances' };
    const evs = ((CAT.pitch && CAT.pitch.heatmap_events) || []).map(e => EVN[e] || words(e).toLowerCase());
    const html = `<div class="tx-stats">${['touches', 'touches_in_box', 'progressive_passes_received'].map(k => numBtn(p, k, 'ht-')).join('')}</div>
      <svg viewBox="-1.5 -1.5 108 71" class="tx-svg tx-pitchsvg" role="img" aria-label="Heat map: ${total} on-ball actions, attacking left to right"><rect x="0" y="0" width="105" height="68" class="tx-turf"/>${cells}${fullPitch()}<path d="M44,70 L61,70" class="tx-dir"/></svg>
      <p class="tx-cap">${esc(total)} on-ball actions in league matches this season (${esc(listText(evs))}), so more than the Touches count, which is touch records only. Attacking left to right, ${esc(cols)} by ${esc(rows)} cells. The map has no clip per cell; the numbers above open their moments.</p>`;
    paint('heat', html, esc(p.short_name));
  }

  // ------------------------------------------------------------------ FORM: match by match
  const FORM_UNIT = {
    per90: 'Per 90 of each match; dashed line = the season per 90',
    padj: 'Per 90 of each match, possession-adjusted; dashed line = the season',
    ratio: "Each match's own ratio; dashed line = the season's (all attempts pooled)",
    max: "Each match's peak; dashed line = the season peak",
    mean: "Each match's value; dashed line = the season mean",
    total: 'Count in each match; dashed line = the season count divided by matches played',
  };
  const formKey = (p) => { const defs = (CAT.default_columns[p.position] || CAT.default_columns.all).filter(k => MK.has(k)); return S.form.k && MK.has(S.form.k) ? S.form.k : defs[0]; };
  function renderForm() {
    const p = PID.get(S.focus);
    const defs = (CAT.default_columns[p.position] || CAT.default_columns.all).filter(k => MK.has(k));
    const k = formKey(p), m = MK.get(k);
    const fc = formOf(p.id, [...defs, k], 'form');
    if (fc.st !== 'ok') { paint('form', waitHtml(fc, `${p.name}'s matches`), esc(p.short_name)); return; }
    const fm = fc.v, matches = fm.matches || [];
    if (!matches.length) { paint('form', '<p class="tx-dim">No matches this season.</p>', esc(p.short_name)); return; }
    const fk = (fm.metrics || {})[k] || {}, vals = fk.values || [];
    // The dashed line is in the bars' unit: a season count (clean sheets, cards) is drawn as its average per match played,
    // never as the season total over bars that count one match each.
    const isTotal = m.kind === 'total';
    const sv = fk.season;
    const season = sv != null ? { value: isTotal ? sv / matches.length : sv } : null;
    const seasonLab = season ? (isTotal ? `season ${Number(season.value).toFixed(2)} a match (${fmt(m, sv)} in ${matches.length})` : `season ${fmt(m, season.value)}`) : '';
    // Drawn at the panel's own width (one unit = one pixel) so the labels stay at their CSS size; the scale always holds
    // zero, so negative values (xT added, goals minus xG, on-pitch differences) hang below a zero line inside the chart.
    const W = svgWidth('form', 300), H = 200, L = 40, B = 36, T = 16, n = matches.length, bw = (W - L - 8) / n;
    const nums = [...vals.filter(v => v != null).map(Number), ...(season && season.value != null ? [season.value] : [])];
    let lo = Math.min(0, ...nums), hi = Math.max(0, ...nums);
    if (lo === hi) hi = 1;
    const pad = (hi - lo) * 0.12; if (hi > 0) hi += pad; if (lo < 0) lo -= pad;
    const y = (v) => T + (H - T - B) * (hi - v) / (hi - lo), y0 = y(0);
    const tick = (v) => `<text x="${L - 4}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end" class="tx-axl">${esc(fmt(m, v))}</text>`;
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="tx-svg tx-form" role="group" aria-label="${esc(m.label)} match by match; each bar opens that match's moments">`;
    svg += `<line x1="${L}" y1="${y0.toFixed(1)}" x2="${W - 4}" y2="${y0.toFixed(1)}" class="tx-ax"/>${tick(0)}`;
    if (Math.max(0, ...nums) > 0) svg += tick(Math.max(...nums));
    if (lo < 0) svg += tick(Math.min(...nums));
    matches.forEach((mm, i) => {
      const v = vals[i], x = L + i * bw + 2, w = Math.max(4, bw - 4), cx = (x + w / 2).toFixed(1);
      const lab = `Round ${mm.round} ${mm.home ? 'v' : 'at'} ${club(mm.opponent).name}, ${mm.score}, ${Math.round(mm.minutes)} min: ${m.label} ${fmt(m, v)}. Open its moments`;
      let bar = '';
      if (v == null) bar = `<text x="${cx}" y="${(y0 - 4).toFixed(1)}" text-anchor="middle" class="tx-axl">–</text>`;
      else {
        const yv = y(v), top = Math.min(yv, y0), h = Math.max(1, Math.abs(y0 - yv)), neg = v < 0;
        bar = `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${neg ? '#ff8a8a' : GROUP_COL[m.group] || '#ffcd28'}"/>`
          + (textW(fmt(m, v).replace('%', ''), 10) <= bw - 2 ? `<text x="${cx}" y="${(neg ? top + h + 12 : top - 4).toFixed(1)}" text-anchor="middle" class="tx-fv">${esc(fmt(m, v).replace('%', ''))}</text>` : '');
      }
      svg += `<g class="tx-fbar${v == null ? ' nil' : ''}" role="button" tabindex="0" data-act="fev" data-mid="${esc(mm.match_id)}" data-fid="fb-${i}" aria-label="${esc(lab)}"><rect x="${x.toFixed(1)}" y="${T}" width="${w.toFixed(1)}" height="${H - T - B}" class="tx-hit"/>${bar}`
        + `<text x="${cx}" y="${H - B + 15}" text-anchor="middle" class="tx-axl">R${esc(mm.round)}</text><text x="${cx}" y="${H - B + 29}" text-anchor="middle" class="tx-axl dim">${mm.home ? '' : '@'}${esc(short(mm.opponent))}</text><title>${esc(lab)}</title></g>`;
    });
    if (season && season.value != null) { const ys = y(season.value).toFixed(1); svg += `<line x1="${L}" y1="${ys}" x2="${W - 4}" y2="${ys}" class="tx-avg"/><text x="${W - 6}" y="${(season.value < 0 ? +ys + 13 : ys - 4)}" text-anchor="end" class="tx-avgl">${esc(seasonLab)}</text>`; }
    svg += '</svg>';
    const ctab = defs.filter(c => (fm.metrics || {})[c]).map(c => { const cm = MK.get(c), x = fm.metrics[c], tr = x.last3_minus_season;
      return `<tr${c === k ? ' class="on"' : ''}><th scope="row"><button type="button" class="tx-lk" data-act="formk" data-k="${esc(c)}" data-mk="${esc(c)}" data-fid="fk-${esc(c)}">${esc(cm.label)}${noisy(cm)}</button></th>
        <td class="num"><button type="button" class="tx-n" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(c)}" data-fid="fm-${esc(c)}" aria-label="${esc(`${cm.label} mean ${fmt(cm, x.mean)}, open its moments`)}">${esc(fmt(cm, x.mean))}</button></td><td class="num">${x.sd == null ? '–' : esc(x.sd)}</td><td class="num">${x.cv == null ? '–' : esc(x.cv)}</td>
        <td class="num ${tr > 0 ? 'up' : tr < 0 ? 'dn' : ''}">${tr == null ? '–' : (tr > 0 ? '+' : '') + esc(tr)}</td></tr>`; }).join('');
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span class="sr">Metric</span><select data-r="formk" data-fid="form-k">${metricOptions(k)}</select></label>
        <span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}" tabindex="0">${esc(m.label)}${noisy(m)} <span class="tx-dim">ⓘ</span></span></div>${svg}
      <p class="tx-cap">${esc(FORM_UNIT[m.kind] || 'Each match')}. Bars open that match's moments, all of them.</p>
      ${ctab ? `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cons"><thead><tr><th>Consistency</th><th class="num">Mean</th><th class="num">SD</th><th class="num">CV</th><th class="num" title="Last three matches minus the season">L3−S</th></tr></thead><tbody>${ctab}</tbody></table></div>` : ''}`;
    paint('form', html, esc(`${p.short_name} · ${matches.length} m`));
  }

  // ------------------------------------------------------------------ SCAT: one metric against another
  function scatPoints() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y);
    const c = scatOf(x, y, pos, 'scat');
    if (c.st !== 'ok') return null;
    const ok = (m, pct, p) => m.has_percentile ? pct != null : p.qualified;
    return (c.v.points || []).map(pt => ({ p: PID.get(pt.global_id) || { ...pt, id: pt.global_id }, a: { value: pt.x, percentile: pt.x_percentile }, b: { value: pt.y, percentile: pt.y_percentile } }))
      .filter(o => o.a.value != null && o.b.value != null && o.p.minutes > 0 && (all || (ok(mx, o.a.percentile, o.p) && ok(my, o.b.percentile, o.p))))
      .sort((u, v) => u.a.value - v.a.value || u.b.value - v.b.value);
  }
  function renderScat() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y), pts = scatPoints();
    if (!pts) { paint('scat', waitHtml(scatOf(x, y, pos, 'scat'), 'the scatter'), esc(`${mx.label} × ${my.label}`)); return; }
    const W = svgWidth('scat', 300), H = Math.round(Math.min(340, Math.max(250, W * 0.62))), L = 48, B = 38, T = 14, Rm = 14;
    const xs = pts.map(o => o.a.value), ys = pts.map(o => o.b.value);
    const ext = (a) => { let lo = Math.min(...a), hi = Math.max(...a); if (!a.length) { lo = 0; hi = 1; } if (lo === hi) { lo -= 1; hi += 1; } const pad = (hi - lo) * 0.06; return [lo >= 0 ? Math.max(0, lo - pad) : lo - pad, hi + pad]; };
    const [x0, x1] = ext(xs), [y0, y1] = ext(ys);
    const sx = (v) => L + (W - L - Rm) * (v - x0) / (x1 - x0), sy = (v) => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
    const med = (a) => { if (!a.length) return null; const s = [...a].sort((p, q) => p - q), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
    const mxv = med(xs), myv = med(ys);
    if (scatCur != null && (scatCur < 0 || scatCur >= pts.length)) scatCur = null;
    const cur = scatCur != null ? pts[scatCur] : pts.find(o => o.p.id === S.focus) || null;
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="tx-svg tx-scat" tabindex="0" data-fid="scat-svg" data-r="scat" role="group" aria-label="${esc(`Scatter, ${mx.label} against ${my.label}, ${pts.length} players. Arrow keys move between players, Enter selects`)}">`;
    svg += `<line x1="${L}" y1="${H - B}" x2="${W - Rm}" y2="${H - B}" class="tx-ax"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" class="tx-ax"/>`;
    for (const t of [0, 0.5, 1]) {
      const vx = x0 + (x1 - x0) * t, vy = y0 + (y1 - y0) * t;
      svg += `<text x="${sx(vx).toFixed(1)}" y="${H - B + 15}" text-anchor="${t === 0 ? 'start' : t === 1 ? 'end' : 'middle'}" class="tx-axl">${esc(fmt(mx, vx))}</text><text x="${L - 4}" y="${(sy(vy) + 3).toFixed(1)}" text-anchor="end" class="tx-axl">${esc(fmt(my, vy))}</text>`;
    }
    svg += `<text x="${(L + W - Rm) / 2}" y="${H - 4}" text-anchor="middle" class="tx-axt">${esc(mx.label)} →</text><text x="13" y="${(T + H - B) / 2}" text-anchor="middle" class="tx-axt" transform="rotate(-90 13 ${(T + H - B) / 2})">${esc(my.label)} →</text>`;
    if (mxv != null) svg += `<line x1="${sx(mxv).toFixed(1)}" y1="${T}" x2="${sx(mxv).toFixed(1)}" y2="${H - B}" class="tx-med"/><line x1="${L}" y1="${sy(myv).toFixed(1)}" x2="${W - Rm}" y2="${sy(myv).toFixed(1)}" class="tx-med"/>`;
    const layer = (o, i) => {
      const ci = S.compare.indexOf(o.p.id), isF = o.p.id === S.focus, isC = cur && cur.p === o.p;
      const col = isF ? '#ffcd28' : ci >= 0 ? CMP_COL[ci] : null;
      return `<g class="tx-dot${col ? ' hi' : ''}${isC ? ' cur' : ''}" data-act="sel" data-pid="${esc(o.p.id)}" data-i="${i}"><circle cx="${sx(o.a.value).toFixed(1)}" cy="${sy(o.b.value).toFixed(1)}" r="${col ? 5 : 3.4}"${col ? ` fill="${col}"` : ''}/>`
        + (col || isC ? `<text x="${(sx(o.a.value) + 7).toFixed(1)}" y="${(sy(o.b.value) - 6).toFixed(1)}" class="tx-dl">${esc(lastName(o.p))}</text>` : '')
        + `<title>${esc(`${o.p.name} (${o.p.short_name}): ${mx.label} ${fmt(mx, o.a.value)}, ${my.label} ${fmt(my, o.b.value)}`)}</title></g>`;
    };
    const order = pts.map((o, i) => [o, i]).sort(([a], [b]) => ((a.p.id === S.focus || S.compare.includes(a.p.id)) - (b.p.id === S.focus || S.compare.includes(b.p.id))));
    svg += order.map(([o, i]) => layer(o, i)).join('') + '</svg>';
    const read = cur ? `<p class="tx-read"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(cur.p.id)}" data-fid="scat-sel">${esc(cur.p.name)}</button> <span class="tx-dim">${esc(cur.p.short_name)} ${esc(cur.p.position)}</span>
        <span class="tx-ml" data-mk="${esc(x)}">${esc(mx.label)}</span><button type="button" class="tx-n"${shade(mx, cur.a.percentile)} data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(x)}" data-fid="scat-x">${esc(fmt(mx, cur.a.value))}</button>
        <span class="tx-ml" data-mk="${esc(y)}">${esc(my.label)}</span><button type="button" class="tx-n"${shade(my, cur.b.percentile)} data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(y)}" data-fid="scat-y">${esc(fmt(my, cur.b.value))}</button></p>`
      : '<p class="tx-read tx-dim">The focus player is not on this chart (position or qualification). Arrow keys in the chart pick a player.</p>';
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span>X</span><select data-r="scx" data-fid="scat-xs">${metricOptions(x)}</select></label>
        <label class="tx-ctl"><span>Y</span><select data-r="scy" data-fid="scat-ys">${metricOptions(y)}</select></label>
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scpos" data-v="${v || ''}" aria-pressed="${pos === v}">${v || 'ALL'}</button>`).join('')}</div>
        <label class="tx-chk"><input type="checkbox" data-r="scall" data-fid="scat-all"${all ? ' checked' : ''}> Include unqualified</label></div>${svg}${read}
      <p class="tx-cap">${pts.length} ${esc(pos ? POSN[pos] : 'players')}${all ? '' : ', qualified on both'} · dashed lines = medians · click a dot to select</p>`;
    paint('scat', html, esc(`${mx.label} × ${my.label}`));
  }

  // ------------------------------------------------------------------ TEAM: team style
  function renderTeam() {
    const t = TEAMS.get(S.club), c = club(S.club), row = (SEASON.table || []).find(r => r.club_id === S.club) || {};
    if (!t) { paint('team', '<p class="tx-dim">No team.</p>'); return; }
    const vals = (k) => [...TEAMS.values()].map(x => x.values[k] && x.values[k].value).filter(v => v != null);
    const rows = (CAT.team_metrics || []).map(m => {
      const v = t.values[m.key]; if (!v) return '';
      const all = vals(m.key), lo = Math.min(...all), hi = Math.max(...all), w = hi === lo ? 50 : 4 + 92 * (v.value - lo) / (hi - lo);
      const mean = hi === lo ? 50 : 4 + 92 * (v.league_mean - lo) / (hi - lo);
      const judged = m.higher_is_better !== null, good = judged && v.rank <= 2;
      return `<tr><th scope="row"><span class="tx-ml" data-tk="${esc(m.key)}" data-cid="${esc(S.club)}">${esc(m.label)}</span>${m.kind === 'per90' ? '<span class="tx-dim tx-u"> /90</span>' : ''}</th>
        <td class="num"><button type="button" class="tx-n" data-act="tev" data-cid="${esc(S.club)}" data-tk="${esc(m.key)}" data-fid="tv-${esc(m.key)}" aria-label="${esc(`${c.name}, ${m.label} ${fmt(m, v.value)}, rank ${v.rank} of ${v.of}. Open what is behind it`)}">${esc(fmt(m, v.value))}</button></td>
        <td class="num ${good ? 'up' : ''}">${esc(v.rank)}/${esc(v.of)}</td><td class="num tx-dim">${esc(fmt(m, v.league_mean))}</td>
        <td class="tx-pbar"><span class="tx-range"><i data-l="${w.toFixed(1)}" class="${judged ? '' : 'style'}"></i><b data-l="${mean.toFixed(1)}"></b></span></td></tr>`;
    }).join('');
    const lowBest = (CAT.team_metrics || []).filter(m => m.higher_is_better === false).map(m => /^[A-Z][a-z]/.test(m.label) ? m.label[0].toLowerCase() + m.label.slice(1) : m.label);
    const squad = PLAYERS.filter(p => p.club_id === S.club).sort((a, b) => b.minutes - a.minutes);
    const unplayed = ((club(S.club).squad) || []).filter(s => !PID.has(s.global_id));
    const html = `<div class="tx-seg tx-clubs" role="group" aria-label="Club">${(SEASON.clubs || []).map(k => `<button type="button" data-act="club" data-cid="${esc(k.club_id)}" aria-pressed="${k.club_id === S.club}" title="${esc(k.name)}">${esc(k.short_name)}</button>`).join('')}</div>
      <p class="tx-name">${esc(c.name)} <span class="tx-dim">${esc(ord(row.position || 0))} · ${esc(row.points)} pts · ${esc(row.won)}-${esc(row.drawn)}-${esc(row.lost)} · ${esc(row.goals_for)}:${esc(row.goals_against)}</span></p>
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style</th><th class="num">Value</th><th class="num">Rank</th><th class="num">Lg avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div><h3 class="tx-h3">Squad by minutes</h3><ol class="tx-squad tx-scroll">${squad.map(p => `<li class="${p.id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-fid="sq-${esc(p.id)}">${esc(p.name)}</button><span class="tx-dim">${esc(p.position)} #${esc(p.kit_number)}</span><span class="num">${esc(Math.round(p.minutes))}′</span></li>`).join('')}${unplayed.map(s => `<li><span class="tx-dim">${esc(s.name)}</span><span class="tx-dim">${esc(s.position)} #${esc(s.kit_number)}</span><span class="num tx-dim">0′</span></li>`).join('')}</ol></div></div>
      <p class="tx-cap">Rank 1 = best${lowBest.length ? `: the lowest for ${esc(listText(lowBest))}` : ''}. Grey markers are style, ranked but not judged, and their rank 1 is the highest. The bar spans the league's clubs; the white tick is the league average. /90 = per 90 minutes; possession, PPDA and the other ratios are season values over every match. Shot numbers (xG, goals, shots) open every shot behind them with its clip; the others open one value per match, without a clip.</p>`;
    paint('team', html, esc(c.short_name));
  }
  // The shots behind a team's shot-based numbers (GET /api/teams/{club}/shots): 'for' is the club's own players,
  // 'against' their opponents in the club's matches.
  const TEAM_SHOTS = {
    xg_for: { side: 'for', v: 'xg' }, npxg_for: { side: 'for', v: 'xg', keep: (s) => !s.penalty }, penalty_xg: { side: 'for', v: 'xg', keep: (s) => s.penalty },
    xg_against: { side: 'against', v: 'xg' }, goals_for: { side: 'for', v: 'n', keep: (s) => s.outcome === 'goal' },
    goals_against: { side: 'against', v: 'n', keep: (s) => s.outcome === 'goal' }, shots_for: { side: 'for', v: 'n' }, shots_against: { side: 'against', v: 'n' },
  };
  const teamUnit = (m) => m.kind === 'per90' ? 'per 90' : m.unit === '%' ? '' : m.unit;
  async function teamReel(cid, tk) {
    const t = TEAMS.get(cid), m = TK.get(tk), v = t && t.values[tk];
    if (!t || !m || !v) return null;
    const u = teamUnit(m);
    const r = { title: `${t.club} · ${m.label}`, sub: `${fmt(m, v.value)}${u ? ' ' + u : ''} · rank ${v.rank} of ${v.of}${v.total != null ? ` · ${Number(Number(v.total).toFixed(2))} in total` : ''}`, i: -1, items: [], note: '' };
    // From the club's side: "R2 at EAS" when it played away, whoever took the shot.
    const shotRow = (s) => { const mf = matchFor(s.match_id, cid); return { when: mf.when, minute: s.minute, val: `xG ${Number(s.xg).toFixed(2)}`,
      note: `${s.name || 'Unknown player'}${s.club_id === cid ? '' : ' (' + short(s.club_id) + ')'} · ${OUTC[s.outcome] || 'Shot'}${s.penalty ? ' · pen' : ''}`, video: s.video_url, match_id: s.match_id }; };
    const spec = TEAM_SHOTS[tk];
    if (spec) {
      const data = await settle(teamShotsOf(cid, spec.side));
      if (!data) { C.delete(`tshots|${cid}|${spec.side}`); r.note = 'The shots did not load. Pick the number again to retry.'; return r; }
      const hits = (data.shots || []).filter(s => !spec.keep || spec.keep(s));
      r.items = hits.map(shotRow);
      const sum = spec.v === 'xg' ? hits.reduce((a, s) => a + (Number(s.xg) || 0), 0) : hits.length;
      const match = v.total == null || Math.abs(sum - v.total) < 0.011, noun = /^goals_/.test(tk) ? 'goal' : tk === 'penalty_xg' ? 'penalty' : 'shot';
      const tot = (x) => spec.v === 'xg' ? `${Number(x).toFixed(2)} xG` : String(x);
      r.note = !hits.length ? `No ${noun === 'penalty' ? 'penalties' : noun + 's'} behind this number this season.`
        : `Every ${spec.side === 'for' ? '' : 'opponent '}${noun} behind this number, each with its clip${match ? `; they add up to the season total (${tot(v.total != null ? v.total : sum)})` : `; they add up to ${tot(sum)}, the engine's total is ${tot(v.total)}`}.`;
      return r;
    }
    if (tk === 'set_piece_xg' || tk === 'set_piece_shots') {
      const st = await settle(styleOf(cid));
      if (!st) { C.delete('style|' + cid); r.note = 'The set-piece shots did not load. Pick the number again to retry.'; return r; }
      const ev = (st.evidence || {}).set_piece_xg || [];
      r.items = ev.map(e => ({ when: matchFor(e.match_id, cid).when, minute: e.minute, val: `xG ${Number(e.xg != null ? e.xg : e.value).toFixed(2)}`, note: [e.name, OUTC[e.outcome]].filter(Boolean).join(' · '), video: e.video_url || null, match_id: e.match_id }));
      r.note = ev.length ? 'Every set-piece shot behind this number, each with its clip.' : 'No set-piece shots this season.';
      return r;
    }
    const st = await settle(styleOf(cid));
    if (!st) { C.delete('style|' + cid); r.note = 'The matches did not load. Pick the number again to retry.'; return r; }
    r.items = (st.per_match || []).map(pm => ({ when: `R${pm.round} ${pm.home ? 'v' : 'at'} ${short(pm.opponent)}`, minute: null, val: fmt(m, pm.values[tk]), note: m.kind === 'per90' ? 'per 90 of the match' : "the match's value", video: null, match_id: pm.match_id }));
    r.unit = 'match';
    r.note = m.kind === 'ratio' ? 'A team-style ratio is built from every possession of a match: one value per match, no single clip.'
      : 'One value per match; the events behind this number are not listed here.';
    return r;
  }
  async function openTeamReel(cid, tk) {
    const t = TEAMS.get(cid), m = TK.get(tk);
    if (!t || !m) return;
    reelLoading(`${t.club} · ${m.label}`);
    revealClips();
    const r = await teamReel(cid, tk);
    if (r) openReel(r);
  }

  const RENDER = { scrn: renderScrn, plyr: renderPlyr, radar: renderRadar, clips: renderClips, shot: renderShot, heat: renderHeat, form: renderForm, scat: renderScat, team: renderTeam };

  // ------------------------------------------------------------------ tooltips: definition and source, on hover and focus
  function tipHtml(el, compact) {
    const mk = el.dataset.mk, tk = el.dataset.tk;
    const m = mk ? MK.get(mk) : TK.get(tk); if (!m) return '';
    // Arrowing through the screener: a short tip (the column header holds the full definition) that reads the cell.
    if (compact) {
      const p = PID.get(el.dataset.pid), c = p && cellOf(p, mk); if (!c) return '';
      const np = noPct(p, m, c);
      return `<p class="tt-h">${esc(m.label)}${m.noisy ? ' <span class="tt-w">≈ noisy</span>' : ''}</p><p class="tt-p"><b>${esc(p.name)}</b> ${esc(fmt(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : ''} · ${c.percentile == null ? esc(np ? np.text : 'no percentile') : `${esc(ord(c.percentile))} pctl vs ${esc(POSN[p.position])}`}</p><p class="tt-s">Enter opens its moments · the column header has the definition</p>`;
    }
    const src = (m.sources || []).map(s => ((CAT.sources || {})[s] || {}).title || s).join('; ');
    const judge = m.higher_is_better === null ? 'Style marker: ranked, not judged' : m.higher_is_better ? 'Higher is better' : 'Lower is better';
    let h = `<p class="tt-h">${esc(m.label)} <span class="tt-k">${esc(m.key)}</span></p><p>${esc(m.definition)}</p>
      <p class="tt-s"><b>Rule</b> ${esc(m.rule)}${src ? ` · <b>Source</b> ${esc(src)}` : ''}</p><p class="tt-s">${esc(mk ? unitText(m) : m.unit)} · ${esc(judge)}${mk && m.positions ? ` · matters for ${esc(m.positions.join(' '))}` : ''}</p>`;
    if (mk && m.noisy) h += `<p class="tt-w">≈ Noisy: split-half r ${esc(m.reliability_r)} (below ${esc((CAT.season.reliability || {}).noise_r)}); one season cannot yet separate players in the same role.</p>`;
    if (mk && m.min_attempts) h += `<p class="tt-s">Percentile needs at least ${esc(m.min_attempts)}: ${esc(m.min_attempts_rule)}</p>`;
    const p = el.dataset.pid && PID.get(el.dataset.pid), c = p && mk ? cellOf(p, mk) : null;
    if (c) h += `<p class="tt-p"><b>${esc(p.name)}</b> ${esc(fmt(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : c.total != null && m.kind !== 'total' ? ` (${esc(c.total)} in total)` : ''} · ${c.percentile == null ? esc((noPct(p, m, c) || { text: 'no percentile' }).text) : `${esc(ord(c.percentile))} percentile among qualified ${esc(POSN[p.position])}`}</p>`;
    const tv = tk && el.dataset.cid ? TEAMS.get(el.dataset.cid) : null;
    if (tv && tv.values[tk]) h += `<p class="tt-p">Rank ${esc(tv.values[tk].rank)} of ${esc(tv.values[tk].of)} · league average ${esc(fmt(m, tv.values[tk].league_mean))}</p>`;
    return h;
  }
  function showTip(el, compact) {
    const tip = $('txTip'), h = tipHtml(el, compact); if (!h) return;
    tip.innerHTML = h; tip.hidden = false; tipFor = el;
    el.setAttribute('aria-describedby', 'txTip');
    const r = el.getBoundingClientRect(), tw = Math.min(compact ? 260 : 340, window.innerWidth - 16);
    tip.style.width = tw + 'px';
    if (compact) {
      // Beside the cell (right, else left) so the rows below stay readable; with no room either side (a phone), above
      // the cell's row, where the rows already read sit.
      const th = tip.offsetHeight;
      const top = Math.min(Math.max(8, r.top + r.height / 2 - th / 2), window.innerHeight - th - 8);
      if (r.right + 8 + tw <= window.innerWidth - 8) { tip.style.left = (r.right + 8) + 'px'; tip.style.top = top + 'px'; return; }
      if (r.left - 8 - tw >= 8) { tip.style.left = (r.left - 8 - tw) + 'px'; tip.style.top = top + 'px'; return; }
      tip.style.left = Math.min(Math.max(8, r.left), window.innerWidth - tw - 8) + 'px';
      tip.style.top = (r.top - th - 6 > barBottom() ? r.top - th - 6 : r.bottom + 6) + 'px';
      return;
    }
    tip.style.left = Math.min(Math.max(8, r.left), window.innerWidth - tw - 8) + 'px';
    const th = tip.offsetHeight;
    tip.style.top = (r.bottom + 6 + th > window.innerHeight && r.top - th - 6 > 0 ? r.top - th - 6 : r.bottom + 6) + 'px';
  }
  function hideTip() {
    const tip = $('txTip'); if (!tip) return;
    tip.hidden = true;
    if (tipFor) tipFor.removeAttribute('aria-describedby');
    tipFor = null;
  }

  // ------------------------------------------------------------------ the command line: parsing
  function resolvePlayer(q, strict) {
    const n = norm(q); if (!n) return { none: true };
    const tiers = [(p) => norm(p.name) === n, (p) => surname(p) === n || norm(p.name).split(' ').slice(-1)[0] === n, (p) => norm(p.name).split(' ')[0] === n];
    if (!strict) tiers.push((p) => norm(p.name).includes(n));
    for (const t of tiers) {
      const hit = PLAYERS.filter(t);
      if (hit.length === 1) return { p: hit[0], alts: [] };
      // Synthetic names repeat (seven Toures): the regular, most minutes, opens; the namesakes are offered beside it.
      if (hit.length > 1) { hit.sort((a, b) => b.minutes - a.minutes || a.name.localeCompare(b.name)); return { p: hit[0], alts: hit.slice(1) }; }
    }
    return { none: true };
  }
  function resolvePlayers(text) {
    const parts = text.includes(',') ? text.split(',').map(s => s.trim()).filter(Boolean) : null;
    if (parts) return parts.map(s => ({ q: s, ...resolvePlayer(s) }));
    const toks = text.split(/\s+/).filter(t => t && !/^(v|vs|and|&)$/i.test(t)), outp = [];
    let i = 0;
    while (i < toks.length) {
      let done = false;
      for (let j = toks.length; j > i; j--) {
        const r = resolvePlayer(toks.slice(i, j).join(' '), true);
        if (r.p) { outp.push({ q: toks.slice(i, j).join(' '), p: r.p, alts: r.alts }); i = j; done = true; break; }
      }
      if (!done) { const r = resolvePlayer(toks[i]); outp.push({ q: toks[i], ...r }); i++; }
    }
    return outp;
  }
  function resolveMetric(q) {
    const raw = String(q || '').trim(); if (!raw) return { none: true };
    const k = norm(raw).replace(/[\s-]+/g, '_');
    if (MK.has(k)) return { m: MK.get(k) };
    const l = norm(raw), byL = METRICS.filter(m => norm(m.label) === l);
    if (byL.length === 1) return { m: byL[0] };
    const sub = METRICS.filter(m => norm(m.label).includes(l) || m.key.includes(k));
    if (sub.length === 1) return { m: sub[0] };
    const wm = wordMatch(l);
    if (wm.length === 1) return { m: wm[0] };
    return wm.length ? { many: wm } : sub.length ? { many: sub } : { none: true };
  }
  // Every word of the query starts a word of the metric's key or label ("aerial win %" finds aerial_win_pct).
  const mwords = (m) => [...m.key.split('_'), ...norm(m.label).replace(/%/g, ' pct ').split(/[\s\-()+,/]+/)].filter(Boolean);
  function wordMatch(l) {
    const ws = norm(l).replace(/%/g, ' pct ').split(/[\s\-()+,/_]+/).filter(Boolean);
    return ws.length ? METRICS.filter(m => { const mw = mwords(m); return ws.every(w => mw.some(x => x.startsWith(w))); }) : [];
  }
  function resolveClub(q) {
    const n = norm(q); if (!n) return null;
    const clubs = SEASON.clubs || [];
    return clubs.find(c => norm(c.short_name) === n || c.club_id === n || norm(c.name) === n)
      || clubs.find(c => norm(c.name).split(' ').some(w => w.startsWith(n)) || norm(c.name).startsWith(n)) || null;
  }
  const posOf = (t) => POS_WORDS[String(t || '').toUpperCase()] || null;
  const runBtn = (cmd, label) => `<button type="button" class="tx-mini" data-act="run" data-cmd="${esc(cmd)}">${esc(label || cmd)}</button>`;
  const altsHtml = (alts, cmd) => alts && alts.length ? ` <span class="tx-dim">· also:</span> ${alts.slice(0, 6).map(p => runBtn(`${cmd ? cmd + ' ' : ''}${p.name}`, `${p.name} ${p.short_name}`)).join(' ')}` : '';
  function onePlayer(arg) {
    if (!arg.trim()) return { p: PID.get(S.focus), alts: [] };
    const r = resolvePlayer(arg);
    if (r.p) return r;
    out(`No player called "${arg}". Type part of a name; suggestions appear as you type.`, 'err');
    return null;
  }
  async function run(text) {
    const t = String(text || '').trim().replace(/\s*<GO>$/i, '').trim().slice(0, 200); if (!t) return;
    if (store.hist[store.hist.length - 1] !== t) { store.hist.push(t); if (store.hist.length > 50) store.hist.shift(); save(); }
    histAt = -1;
    const toks = t.split(/\s+/), head = toks[0].toUpperCase(), rest = t.slice(toks[0].length).trim();
    if (head === 'HELP' || head === '?') { openHelp(); out('Help is open. Escape closes it.'); return; }
    if (head === 'RANK') return cmdRank(rest);
    if (head === 'CMP') return cmdCmp(rest);
    if (head === 'SCAT') return cmdScat(rest);
    if (head === 'TEAM') {
      const c = resolveClub(rest) || (rest ? null : club(S.club));
      if (!c || !c.club_id) { out(`No club called "${rest}". Clubs: ${(SEASON.clubs || []).map(x => x.short_name).join(', ')}.`, 'err'); return; }
      return team(c, `TEAM ${c.short_name} · ${c.name}: team style, ranked across the league's clubs.`);
    }
    const PANEL_CMD = { SIM: 'plyr', SHOT: 'shot', FORM: 'form', HEAT: 'heat', RDR: 'radar', PLYR: 'plyr' };
    if (PANEL_CMD[head]) {
      const r = onePlayer(rest); if (!r) return;
      const p = r.p;
      out(`${head} ${p.name}: loading…`);
      // What the panel draws loads first, so the output line and the panel are final before it is brought into view.
      const extra = head === 'SHOT' ? shotsOf(p.id) : head === 'FORM' ? formOf(p.id, [...(CAT.default_columns[p.position] || CAT.default_columns.all), S.form.k || ''].filter(Boolean)) : head === 'HEAT' ? heatOf(p.id) : null;
      await Promise.all([selectReady(p.id), extra ? settle(extra) : null]);
      await panelsSettled();
      let line;
      if (head === 'SIM') { const sm = similar(p.id).v; line = `SIM ${p.name}: ${((sm && sm.similar) || []).map(s => `${s.name} ${Number(s.similarity).toFixed(2)}`).join(', ') || 'none'}.`; }
      else if (head === 'SHOT') { const sh = (shotsOf(p.id).v || {}).shots || []; const g = sh.filter(s => s.outcome === 'goal').length; line = `SHOT ${p.name}: ${sh.length} shots, ${g} goal${g === 1 ? '' : 's'}. Each shot plays its clip.`; }
      else if (head === 'FORM') line = `FORM ${p.name}: ${p.appearances} matches. Bars open that match's moments.`;
      else line = `${head} ${p.name} · ${p.club}.`;
      out('', '', esc(line) + altsHtml(r.alts, head));
      showPanel(PANEL_CMD[head], true, head === 'SIM' ? '.tx-sim' : head === 'PLYR' ? '.tx-best' : null);
      return;
    }
    if (COMMANDS[head]) return;
    const c = resolveClub(t);
    if (c && (norm(c.short_name) === norm(t) || norm(c.name) === norm(t))) return team(c, `TEAM ${c.short_name} · ${c.name}.`);
    const r = resolvePlayer(t);
    if (r.p) {
      const p = r.p;
      out(`${p.name}: loading…`);
      await selectReady(p.id);
      await panelsSettled();
      out('', '', esc(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`) + altsHtml(r.alts, ''));
      // Bring the card and the player's numbers into view, not just the card's top strip.
      showPanel('plyr', true, '.tx-best');
      return;
    }
    if (c) return team(c, `TEAM ${c.short_name} · ${c.name}.`);
    const mm = resolveMetric(t);
    if (mm.m) return cmdRank(mm.m.key);
    out(`Not a player, club or command: "${t}". Try TOURE, RANK FW npxg, TEAM BRO or HELP.`, 'err');
  }
  async function team(c, line) {
    S.club = c.club_id; save();
    if (!visible('team')) showPanel('team', false); else renderTeam();
    await panelsSettled();
    out(line);
    showPanel('team', true);
  }
  function cmdRank(rest) {
    const toks = rest.split(/\s+/).filter(Boolean);
    let pos = null;
    if (toks.length && posOf(toks[0])) pos = posOf(toks.shift());
    else if (toks.length > 1 && posOf(toks[toks.length - 1])) pos = posOf(toks.pop());
    const r = resolveMetric(toks.join(' '));
    if (!r.m) {
      if (r.many) out('', 'err', `"${esc(toks.join(' '))}" matches ${r.many.length} metrics: ${r.many.slice(0, 6).map(m => runBtn(`RANK ${pos || 'ALL'} ${m.key}`, m.label)).join(' ')}`);
      else out('RANK needs a metric: RANK <position> <metric>, e.g. RANK FW npxg. Suggestions appear as you type.', 'err');
      return;
    }
    const m = r.m;
    S.scr.pos = pos === 'ALL' ? null : pos;
    // The ranked column goes first, so the order of the rows is explained by the first number the scout reads (at 375 px
    // only one metric column fits).
    S.scr.cols = [m.key, ...S.scr.cols.filter(k => k !== m.key)].slice(0, MAX_COLS);
    S.scr.sort = { k: m.key, dir: m.higher_is_better === false ? 1 : -1 };
    S.scr.q = ''; save();
    const finish = () => {
      const rows = screenRows(), ranks = screenRanks(rows);
      // The active cell is the leader's ranked number, so Alt+1 lands on rank 1 and the arrows walk down the ranking.
      scrAct = rows.length ? { pid: rows[0].id, c: 1 } : null;
      if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
      const tops = rows.filter((_, i) => ranks[i] === 1), c = tops[0] && cellOf(tops[0], m.key);
      const names = tops.length > 3 ? `${tops.slice(0, 3).map(p => p.name).join(', ')} and ${tops.length - 3} more` : tops.map(p => p.name).join(tops.length === 2 ? ' and ' : ', ');
      const nr = ranks.filter(x => x != null).length, un = rows.length - nr;
      // The line first, then the scroll: on a phone the line is in the page flow and pushes the table down.
      out(`RANK ${S.scr.pos || 'ALL'} · ${m.label}: ${rows.length} ${S.scr.pos ? POSN[S.scr.pos] : 'players'}${m.higher_is_better === false ? ' (lowest first)' : ''}${un ? `, ${nr} ranked (${un} ${S.scr.qual ? 'below the minimum attempts' : 'under the minutes or the minimum attempts'}, listed after)` : ''}${c ? `; top ${names} ${fmt(m, c.value)}${tops.length > 1 ? ', tied at rank 1' : ''}` : ''}. Alt+1 enters the table.`);
      const tw = document.querySelector('#tx-p-scrn .tx-tablewrap');
      let target = null;
      if (tw) {
        tw.scrollLeft = 0; tw.scrollTop = 0;
        // On a phone the first metric column can still run past the table's edge (Club, Pos and Min come first): scroll
        // the table, not the page, until the ranked column shows whole.
        const th = tw.querySelector(`thead th [data-k="${CSS.escape(m.key)}"]`), cell = th && th.closest('th');
        if (cell) { const over = cell.getBoundingClientRect().right - tw.getBoundingClientRect().right; if (over > 0) tw.scrollLeft = over + 4; }
        const trs = tw.querySelectorAll('tbody[data-r="grid"] tr');
        target = trs.length ? trs[Math.min(2, trs.length - 1)] : null;     // the first rows of the ranking, not just the box
      }
      showPanel('scrn', true, target);
    };
    if (ensureCols([m.key, ...S.scr.cols])) finish();
    else {
      out(`RANK · ${m.label}: loading the column…`);
      if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
      const wait = () => { if (S.scr.cols.every(k => COLS.has(k) || !MK.has(k))) finish(); else if (colsErr) out(`The ${m.label} column did not load (${errText(colsErr)}).`, 'err'); else setTimeout(wait, 60); };
      wait();
    }
  }
  async function cmdCmp(rest) {
    const rs = resolvePlayers(rest);
    if (!rs.length) { out('CMP needs two or three players: CMP <player> <player> [<player>].', 'err'); return; }
    const bad = rs.find(r => !r.p);
    if (bad) { out(`No player called "${bad.q}".`, 'err'); return; }
    const ids = [...new Set(rs.map(r => r.p.id))].slice(0, 3);
    if (ids.length === 1 && ids[0] !== S.focus) ids.unshift(S.focus);
    if (ids.length < 2) { out('CMP needs two or three different players.', 'err'); return; }
    out('CMP: loading…');
    await Promise.all(ids.map(id => settle(full(id))));
    S.compare = ids; S.focus = ids[0]; S.club = PID.get(ids[0]).club_id; save();
    renderAll();
    await panelsSettled();
    const amb = rs.filter(r => r.alts && r.alts.length);
    out('', '', esc(`CMP ${ids.map(id => PID.get(id).name).join(' · ')}: radar and table vs each player's position peers.`)
      + (amb.length ? ` <span class="tx-dim">"${esc(amb[0].q)}" could also be:</span> ${amb[0].alts.slice(0, 5).map(p => runBtn(`CMP ${ids.map(id => id === amb[0].p.id ? p.name : PID.get(id).name).join(', ')}`, `${p.name} ${p.short_name}`)).join(' ')}` : ''));
    showPanel('radar');
  }
  async function cmdScat(rest) {
    const toks = rest.split(/\s+/).filter(Boolean);
    let pos;
    if (toks.length > 2 && posOf(toks[toks.length - 1])) { const p = posOf(toks.pop()); pos = p === 'ALL' ? null : p; }
    let mx = null, my = null;
    for (let k = 1; k < toks.length && !mx; k++) {
      const a = resolveMetric(toks.slice(0, k).join(' ')), b = resolveMetric(toks.slice(k).join(' '));
      if (a.m && b.m) { mx = a.m; my = b.m; }
    }
    if (!mx) { out('SCAT needs two metrics: SCAT <metricX> <metricY> [<position>], e.g. SCAT npxg xa FW. Metric keys autocomplete.', 'err'); return; }
    S.scat.x = mx.key; S.scat.y = my.key; if (pos !== undefined) S.scat.pos = pos; scatCur = null; save();
    out(`SCAT · ${mx.label} × ${my.label}: loading…`);
    await settle(scatOf(mx.key, my.key, S.scat.pos));
    if (!visible('scat')) showPanel('scat', false); else renderScat();
    await panelsSettled();
    const pts = scatPoints() || [];
    out(`SCAT · ${mx.label} × ${my.label}${S.scat.pos ? ' · ' + POSN[S.scat.pos] : ''}: ${pts.length} players.`);
    showPanel('scat', true);
  }

  // ------------------------------------------------------------------ the command line: autocomplete and history
  function playerSugs(q, k, runIt) {
    const n = norm(q);
    const score = (p) => { const nm = norm(p.name), sn = surname(p); if (!n) return 0; if (sn.startsWith(n)) return 0; if (nm.startsWith(n)) return 1; if (nm.split(' ').some(w => w.startsWith(n))) return 2; if (n.length >= 3 && nm.includes(n)) return 3; return 9; };
    let ps;
    if (!n) { const f = PID.get(S.focus), sm = (C.get('sim|' + f.id) || {}).v; ps = [f, ...((sm && sm.similar) || []).map(s => PID.get(s.global_id)).filter(Boolean)]; }
    else ps = PLAYERS.filter(p => score(p) < 9).sort((a, b) => score(a) - score(b) || b.minutes - a.minutes);
    return ps.slice(0, 7).map(p => ({ kind: 'PLAYER', text: p.name, detail: `${p.short_name} ${p.position} #${p.kit_number}`, insert: p.name, k, run: runIt }));
  }
  function metricSugs(q, k, runIt, prefix = '', pos = null) {
    const n = norm(q), kk = n.replace(/[\s-]+/g, '_');
    const score = (m) => { if (!n) return 0; if (m.key.startsWith(kk)) return 0; const l = norm(m.label); if (l.startsWith(n)) return 1; if (l.split(' ').some(w => w.startsWith(n))) return 2; if (m.key.includes(kk) || l.includes(n)) return 3; const ws = n.replace(/%/g, ' pct ').split(/[\s\-()+,/_]+/).filter(Boolean), mw = mwords(m); if (ws.length && ws.every(w => mw.some(x => x.startsWith(w)))) return 4; return 9; };
    const base = n ? METRICS : (CAT.default_columns[pos || PID.get(S.focus).position] || CAT.default_columns.all).map(x => MK.get(x)).filter(Boolean);
    return base.filter(m => score(m) < 9).sort((a, b) => score(a) - score(b)).slice(0, 8)
      .map(m => ({ kind: 'METRIC', text: `${m.label}${m.noisy ? ' ≈' : ''}`, detail: m.key, insert: prefix + m.key, k, run: runIt, mk: m.key }));
  }
  function suggest() {
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length);
    const toks = before.split(/\s+/), cur = toks[toks.length - 1], wordsIn = toks.filter(Boolean);
    const head = (toks[0] || '').toUpperCase(), inArgs = toks.length > 1 && COMMANDS[head];
    const clubs = SEASON.clubs || [];
    let s = [];
    const trailing = (fn) => { for (let k = Math.min(3, toks.length - 1); k >= 1; k--) { const q = toks.slice(-k).join(' ').trim(); const r = fn(q, k); if (r.length && q) return r; } return fn(cur, 1); };
    if (!inArgs) {
      if (!before.trim()) { acItems = []; return paintAc(); }
      if (toks.length === 1) {
        s.push(...Object.keys(COMMANDS).filter(c => c.startsWith(head)).map(c => ({ kind: 'CMD', text: c, detail: COMMANDS[c].args || COMMANDS[c].help, insert: c, k: 1, run: c === 'HELP' })));
        s.push(...playerSugs(cur, 1, true).slice(0, 5));
        s.push(...clubs.filter(c => norm(c.short_name).startsWith(norm(cur)) || norm(c.name).split(' ').some(w => w.startsWith(norm(cur)))).map(c => ({ kind: 'CLUB', text: c.name, detail: `TEAM ${c.short_name}`, insert: `TEAM ${c.short_name}`, k: 1, run: true })));
        s.push(...metricSugs(cur, 1, true, `RANK ${PID.get(S.focus).position} `).slice(0, 3));
      } else s = playerSugs(wordsIn.join(' '), toks.length, true);
    } else if (['SIM', 'SHOT', 'FORM', 'HEAT', 'RDR', 'PLYR'].includes(head)) s = playerSugs(toks.slice(1).join(' '), toks.length - 1, true);
    else if (head === 'CMP') { s = trailing((q, k) => playerSugs(q, k, false)); }
    else if (head === 'TEAM') { const n = norm(cur); s = clubs.filter(c => !n || norm(c.short_name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'CLUB', text: c.name, detail: c.short_name, insert: c.short_name, k: 1, run: true })); }
    else if (head === 'RANK') {
      const args = toks.slice(1);
      if (args.length === 1) s = [...['ALL', ...POS].filter(p => p.startsWith(cur.toUpperCase())).map(p => ({ kind: 'POS', text: p, detail: p === 'ALL' ? 'every position' : POSN[p], insert: p, k: 1, run: false })), ...metricSugs(cur, 1, true)];
      else s = metricSugs(posOf(args[0]) ? args.slice(1).join(' ') : args.join(' '), posOf(args[0]) ? args.length - 1 : args.length, true, '', posOf(args[0]) === 'ALL' ? 'all' : posOf(args[0]));
    } else if (head === 'SCAT') {
      const args = toks.slice(1), done = args.slice(0, -1).filter(a => MK.has(norm(a))).length;
      if (done >= 2) s = ['ALL', ...POS].filter(p => p.startsWith(cur.toUpperCase())).map(p => ({ kind: 'POS', text: p, detail: p === 'ALL' ? 'every position' : POSN[p], insert: p, k: 1, run: true }));
      else s = metricSugs(cur, 1, false);
    }
    acItems = s.slice(0, 9); acAt = -1;
    paintAc();
  }
  function paintAc() {
    const ul = $('txAc'), inp = $('txIn');
    if (!acItems.length) { ul.hidden = true; ul.innerHTML = ''; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); return; }
    ul.innerHTML = acItems.map((s, i) => `<li role="option" id="txAc-${i}" aria-selected="${i === acAt}" data-i="${i}"${s.mk ? ` data-mk="${esc(s.mk)}"` : ''}><span class="tx-ak k-${esc(s.kind)}">${esc(s.kind)}</span><span class="tx-at">${esc(s.text)}</span><span class="tx-ad">${esc(s.detail)}</span></li>`).join('');
    ul.hidden = false; inp.setAttribute('aria-expanded', 'true');
    if (acAt >= 0) { inp.setAttribute('aria-activedescendant', 'txAc-' + acAt); const li = $('txAc-' + acAt); if (li) li.scrollIntoView({ block: 'nearest' }); } else inp.removeAttribute('aria-activedescendant');
  }
  function closeAc() { acItems = []; acAt = -1; paintAc(); }
  // Tab and a click take a suggestion into the line; Enter on a highlighted player or club runs it.
  function accept(i, runNow) {
    const s = acItems[i]; if (!s) return;
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length), after = inp.value.slice(before.length);
    const toks = before.split(/\s+/);
    const keep = toks.slice(0, Math.max(0, toks.length - s.k)).join(' ');
    inp.value = (keep ? keep + ' ' : '') + s.insert + ' ' + after.trimStart();
    closeAc();
    if (s.run && runNow) { const v = inp.value; inp.value = ''; run(v); }
    else { inp.setSelectionRange(inp.value.length, inp.value.length); suggest(); }
  }

  // ------------------------------------------------------------------ help
  function openHelp(opener) {
    const h = $('txHelp');
    const srcs = Object.entries(CAT.sources || {}).map(([k, s]) => `<li><span class="tt-k">${esc(k)}</span> ${s.url && /^https:\/\//.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`).join('');
    h.innerHTML = `<div class="tx-hhead"><h2 tabindex="-1" id="txHelpH">HELP · the Scout terminal</h2><button type="button" class="tx-mini" data-act="helpclose" aria-label="Close help">Esc &times;</button></div>
      <div class="tx-hbody"><table class="tx-mt"><tbody>
        <tr><th scope="row"><code>NAME</code> &lt;GO&gt;</th><td>Any surname or name opens the player: ${runBtn('TOURE')}</td></tr>
        ${Object.entries(COMMANDS).map(([c, x]) => `<tr><th scope="row"><code>${esc(c)}</code> <span class="tx-dim">${esc(x.args)}</span></th><td>${esc(x.help)} ${c === 'HELP' ? '' : runBtn(x.ex)}</td></tr>`).join('')}
      </tbody></table>
      <h3 class="tx-h3">Keys</h3><ul class="tx-keys">
        <li><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> focus the command line</li><li><kbd>Enter</kbd> is &lt;GO&gt;</li><li><kbd>↑</kbd> <kbd>↓</kbd> history, or move in the suggestions</li>
        <li><kbd>Tab</kbd> takes a suggestion into the line</li><li><kbd>Esc</kbd> closes suggestions, help and tips</li><li><kbd>Alt 1–9</kbd> jump to a panel (F1–F9)</li>
        <li><kbd>Alt 1</kbd> (F1) goes straight into the screener's table: arrow keys, Home/End and PageUp/PageDown move, Enter opens the moments</li><li>In the scatter: arrow keys pick a player, Enter selects</li></ul>
      <h3 class="tx-h3">Linking</h3><p>One focus player and up to three compared players drive every panel. Selecting a player anywhere (screener, scatter, similar players, squad, legend) updates the rest. A player's numbers open every moment behind them in CLIP, each with its clip; physical numbers, consistency means and team-style ratios open one value per match, without a clip. Ranks, SD and CV open nothing.</p>
      <h3 class="tx-h3">The numbers</h3><p>${esc(CAT.note)}</p><p>${esc((CAT.season.sample || {}).note)}</p><p>Percentiles: ${esc(CAT.season.percentile_rule)}.</p>
      <h3 class="tx-h3">Sources</h3><ul class="tx-srcs">${srcs}</ul></div>`;
    h.hidden = false; h._opener = opener || null;
    $('txHelpH').focus();
  }
  function closeHelp() { const h = $('txHelp'); if (h.hidden) return; h.hidden = true; if (/^Help is open/.test($('txOut').textContent)) out('Help closed.'); (h._opener && document.contains(h._opener) ? h._opener : $('txIn')).focus(); }

  // ------------------------------------------------------------------ events
  // Keyboard focus survives a repaint: after an action, if focus fell to <body> (the control was rebuilt or is gone), it
  // goes back to the same control (by data-fid, else by what it does), else to the nearest stable place: the panel's
  // heading, the focus player in the selection bar, or the current workspace button.
  const sig = (el) => el.dataset.fid ? `[data-fid="${CSS.escape(el.dataset.fid)}"]`
    : '[data-act="' + CSS.escape(el.dataset.act) + '"]' + ['id', 'pid', 'i', 'v', 'k', 'cid', 'd', 'mk', 'tk', 'mid', 'cmd'].filter(k => el.dataset[k] != null).map(k => `[data-${k}="${CSS.escape(el.dataset[k])}"]`).join('');
  function refocus(sel, pid, zid) {
    const a = document.activeElement;
    if (a && a !== document.body && document.contains(a)) return;
    // Look in the same place first (the PLYR panel and the selection bar both have "+ add" buttons for the same player).
    const scope = (pid && $('tx-p-' + pid)) || (zid && $(zid)) || document.querySelector('.tx');
    const usable = (el) => el && !el.disabled && el.getClientRects().length;
    const tries = [() => [...scope.querySelectorAll(sel)].find(usable),
      () => pid && $('tx-h-' + pid),
      () => zid === 'txSel' && document.querySelector('#txSel .tx-focus'),
      () => zid === 'txMeta' && document.querySelector('#txMeta [data-act="ws"][aria-pressed="true"]'),
      () => zid === 'txKeys' && document.querySelector('#txKeys .tx-fkey'),
      () => $('txIn')];
    for (const f of tries) {
      const el = f();
      if (!usable(el)) continue;
      el.focus({ preventScroll: true });
      if (document.activeElement === el) return;
    }
  }
  function doAct(t, e) {
    const sel = sig(t), panel = t.closest('[data-txp]'), zone = t.closest('#txSel, #txMeta, #txKeys, #txHelp, #txOut');
    const pid = panel && panel.dataset.txp, zid = zone && zone.id;
    const r = act(t, e);
    refocus(sel, pid, zid);
    if (r && r.then) r.then(() => refocus(sel, pid, zid), () => {});
  }
  function act(t) {
    const a = t.dataset.act, pid = t.dataset.pid;
    if (pid !== undefined && !GID.test(pid)) return null;
    if (a === 'sel') { select(pid); return null; }
    if (a === 'ev') {
      if (!MK.has(t.dataset.mk)) return null;
      if (t.dataset.sel && pid !== S.focus && PID.has(pid)) { S.focus = pid; S.club = PID.get(pid).club_id; save(); renderAll(); }
      return openEvidence(pid, t.dataset.mk);
    }
    if (a === 'fev') { const p = PID.get(S.focus); return openEvidence(S.focus, formKey(p), t.dataset.mid); }
    if (a === 'tev') { if (!CLUBID.test(t.dataset.cid || '') || !KEY.test(t.dataset.tk || '')) return null; return openTeamReel(t.dataset.cid, t.dataset.tk); }
    if (a === 'shot') { shotReel(PID.get(S.focus), +t.dataset.i); return null; }
    if (a === 'clip') { play(+t.dataset.i, true); return null; }
    if (a === 'cprev' || a === 'cnext') { if (!reel) return null; const d = a === 'cnext' ? 1 : -1; let i = reel.i + d; while (reel.items[i] && !reel.items[i].video) i += d; if (reel.items[i]) play(i, true); return null; }
    if (a === 'sort') { const k = t.dataset.k; S.scr.sort = S.scr.sort.k === k ? { k, dir: -S.scr.sort.dir } : { k, dir: k === 'name' || k === 'club' ? 1 : (MK.get(k) && MK.get(k).higher_is_better === false ? 1 : -1) }; save(); renderScrn(); return null; }
    if (a === 'rmcol') {
      const i = S.scr.cols.indexOf(t.dataset.k);
      S.scr.cols = S.scr.cols.filter(k => k !== t.dataset.k); save(); renderScrn();
      const xs = document.querySelectorAll('#tx-p-scrn [data-act="rmcol"]'), next = xs[Math.min(i, xs.length - 1)] || document.querySelector('#tx-p-scrn [data-r="addcol"]');
      if (next) next.focus({ preventScroll: true });
      return null;
    }
    if (a === 'scrpos') { S.scr.pos = POS.includes(t.dataset.v) ? t.dataset.v : null; scrAct = null; save(); renderScrn(); return null; }
    if (a === 'scrmode') { S.scr.mode = t.dataset.v === 'pct' ? 'pct' : 'val'; save(); renderScrn(); return null; }
    if (a === 'scrdef') { S.scr.cols = (CAT.default_columns[S.scr.pos || 'all'] || CAT.default_columns.all).filter(k => MK.has(k)); save(); renderScrn(); return null; }
    if (a === 'colsretry') { colsErr = null; renderScrn(); return null; }
    if (a === 'retry') { C.delete(t.dataset.key); renderAll(); return null; }
    if (a === 'reload') { load(); return null; }
    if (a === 'scpos') { S.scat.pos = POS.includes(t.dataset.v) ? t.dataset.v : null; scatCur = null; save(); renderScat(); return null; }
    if (a === 'rtpl') { S.radar.tpl = t.dataset.v === 'all' ? 'all' : 'pos'; save(); renderRadar(); return null; }
    if (a === 'formk') { if (MK.has(t.dataset.k)) { S.form.k = t.dataset.k; save(); renderForm(); } return null; }
    if (a === 'club') { if (CID.has(t.dataset.cid)) { S.club = t.dataset.cid; save(); renderTeam(); } return null; }
    if (a === 'cmpadd') { if (PID.has(pid)) { addCompare(pid); out(`Comparing ${S.compare.map(id => PID.get(id).name).join(' · ')}.`); } return null; }
    if (a === 'cmprm') { S.compare = S.compare.filter(id => id !== pid); save(); renderAll(); return null; }
    if (a === 'cmpclear') { S.compare = []; save(); renderAll(); return null; }
    if (a === 'pane') { showPanel(t.dataset.id); return null; }
    if (a === 'fkey') { goPanel(t.dataset.id); return null; }
    if (a === 'pclose') { const pp = S.panels.find(p => p.id === t.dataset.id); if (!pp) return null; pp.on = false; save(); renderLayout(); renderAll(); const k = document.querySelector(`.tx-fkey[data-id="${CSS.escape(t.dataset.id)}"]`); if (k) k.focus(); return null; }
    if (a === 'psize') { const pp = S.panels.find(p => p.id === t.dataset.id); if (!pp) return null; pp.size = SIZE_NEXT[pp.size] || 'S'; save(); renderLayout(); renderAll(); const b = document.querySelector(`[data-act="psize"][data-id="${CSS.escape(pp.id)}"]`); if (b) b.focus(); return null; }
    if (a === 'pmove') {
      const i = S.panels.findIndex(p => p.id === t.dataset.id), d = +t.dataset.d;
      if (i < 0) return null;
      let j = i + d; while (S.panels[j] && !S.panels[j].on) j += d;
      if (!S.panels[j]) return null;
      const [pp] = S.panels.splice(i, 1); S.panels.splice(j, 0, pp); save(); renderLayout(); renderAll();
      const b = document.querySelector(`[data-act="pmove"][data-id="${CSS.escape(pp.id)}"][data-d="${d}"]`); if (b) b.focus(); return null;
    }
    if (a === 'ws') { switchWs(+t.dataset.i); return null; }
    if (a === 'reset') { resetWs(); return null; }
    if (a === 'help') { openHelp(t); return null; }
    if (a === 'helpclose') { closeHelp(); return null; }
    if (a === 'run') { const c = t.dataset.cmd; if (!$('txHelp').hidden) $('txHelp').hidden = true; $('txIn').value = ''; const r = run(c); $('txIn').focus({ preventScroll: true }); return r; }
    return null;
  }
  // An F-key (or Alt+digit) shows its panel and moves there; F1 goes straight into the screener's table.
  function goPanel(id) {
    showPanel(id);
    if (id === 'scrn' && focusGrid()) return;
    const h = $('tx-h-' + id); if (h) h.focus({ preventScroll: true });
  }
  function wire() {
    const root = document.querySelector('.tx');
    root.addEventListener('click', (e) => {
      const t = e.target.closest('[data-act]');
      if (!t || !root.contains(t) || t.disabled) return;
      if (t.tagName === 'A') return;
      if (!ready && t.dataset.act !== 'reload') return;
      e.preventDefault(); doAct(t, e);
    });
    root.addEventListener('change', (e) => {
      const r = e.target.dataset.r; if (!r || !ready) return;
      if (r === 'addcol' && MK.has(e.target.value) && S.scr.cols.length < MAX_COLS) { S.scr.cols.push(e.target.value); save(); renderScrn(); const sel = document.querySelector('[data-fid="scr-add"]'); if (sel) sel.focus(); }
      if (r === 'scrqual') { S.scr.qual = e.target.checked; scrAct = null; save(); renderScrn(); }
      if (r === 'formk' && MK.has(e.target.value)) { S.form.k = e.target.value; save(); renderForm(); }
      if ((r === 'scx' || r === 'scy') && MK.has(e.target.value)) { S.scat[r === 'scx' ? 'x' : 'y'] = e.target.value; scatCur = null; save(); renderScat(); }
      if (r === 'scall') { S.scat.all = e.target.checked; scatCur = null; save(); renderScat(); }
    });
    root.addEventListener('input', (e) => { if (ready && e.target.dataset.r === 'scrq') { S.scr.q = e.target.value.slice(0, 40); scrAct = null; save(); renderScrn(); } });
    root.addEventListener('keydown', (e) => {
      const t = e.target;
      // SVG buttons (shots, form bars) take Enter and Space like buttons.
      if ((e.key === 'Enter' || e.key === ' ') && t.getAttribute && t.getAttribute('role') === 'button' && t.tagName !== 'BUTTON' && t.dataset.act) { e.preventDefault(); doAct(t, e); return; }
      if (t.dataset && t.dataset.r === 'scat') return scatKeys(e);
      if (t.closest && t.closest('tbody[data-r="grid"]')) return gridKeys(e, t);
    });
    // tooltips
    root.addEventListener('mouseover', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (ready && el && el !== tipFor && !el.closest('#txAc')) showTip(el); });
    root.addEventListener('mouseout', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && el === tipFor && !el.contains(e.relatedTarget) && document.activeElement !== el) hideTip(); });
    root.addEventListener('focusin', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (ready && el && !el.closest('#txAc')) showTip(el, !!(el.dataset.pid && el.closest('tbody[data-r="grid"]'))); else hideTip(); });
    root.addEventListener('focusout', (e) => { if (tipFor && e.target === tipFor) hideTip(); });
    window.addEventListener('scroll', () => { if (tipFor && document.activeElement !== tipFor) hideTip(); }, { passive: true });
    // the command line
    const inp = $('txIn');
    $('txForm').addEventListener('submit', (e) => {
      e.preventDefault(); if (!ready) return;
      if (acAt >= 0) { accept(acAt, true); return; }
      const v = inp.value; inp.value = ''; closeAc(); run(v);
    });
    inp.addEventListener('input', () => { if (ready) { histAt = -1; suggest(); } });
    inp.addEventListener('focus', () => { if (ready && inp.value) suggest(); });
    inp.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== inp) closeAc(); }, 120));
    inp.addEventListener('keydown', (e) => {
      if (!ready) return;
      const open = acItems.length > 0;
      if (e.key === 'ArrowDown' && open) { e.preventDefault(); acAt = (acAt + 1) % acItems.length; paintAc(); return; }
      if (e.key === 'ArrowUp' && open && acAt >= 0) { e.preventDefault(); acAt = acAt - 1; paintAc(); return; }
      if (e.key === 'ArrowUp' && (!open || acAt < 0)) {
        if (!store.hist.length) return;
        e.preventDefault(); closeAc();
        if (histAt < 0) histDraft = inp.value;           // what was being typed comes back on the way down
        histAt = histAt < 0 ? store.hist.length - 1 : Math.max(0, histAt - 1);
        inp.value = store.hist[histAt]; inp.setSelectionRange(inp.value.length, inp.value.length); return;
      }
      if (e.key === 'ArrowDown' && !open && histAt >= 0) {
        e.preventDefault(); histAt++;
        if (histAt >= store.hist.length) { histAt = -1; inp.value = histDraft; } else inp.value = store.hist[histAt];
        return;
      }
      if (e.key === 'Tab' && open && !e.shiftKey) { e.preventDefault(); accept(acAt >= 0 ? acAt : 0, false); return; }
      if (e.key === 'Escape') { e.stopPropagation(); if (open) closeAc(); else if (inp.value) inp.value = ''; else hideTip(); }
    });
    $('txAc').addEventListener('mousedown', (e) => { const li = e.target.closest('li[data-i]'); if (li) { e.preventDefault(); accept(+li.dataset.i, true); } });
    // global keys
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && String(e.key).toLowerCase() === 'k') {
        e.preventDefault();
        wantFocus = true;
        if (onTerminal()) { inp.focus(); inp.select(); return; }
        // From another section: open the Terminal now (the left panel's router runs on hashchange, which comes a task
        // later) and focus at once, so the keys typed straight after Cmd+K land in the command line.
        location.hash = 'terminal';
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        inp.focus();
        return;
      }
      if (!onTerminal() || !ready) return;
      if (e.key === 'Escape') { hideTip(); closeHelp(); if (acItems.length) closeAc(); }
      if (e.altKey && /^Digit[1-9]$/.test(e.code)) {
        const p = PANELS[+e.code.slice(5) - 1]; if (!p) return;
        e.preventDefault(); goPanel(p.id);
      }
    });
  }
  function gridKeys(e, t) {
    const tb = t.closest('tbody'), rows = [...tb.rows], r = rows.indexOf(t.closest('tr'));
    const cells = (tr) => [...tr.querySelectorAll('[data-nav]')];
    const c = cells(rows[r]).indexOf(t);
    let nr = r, nc = c;
    if (e.key === 'ArrowDown') nr++; else if (e.key === 'ArrowUp') nr--; else if (e.key === 'ArrowRight') nc++; else if (e.key === 'ArrowLeft') nc--;
    else if (e.key === 'PageDown') nr += 10; else if (e.key === 'PageUp') nr -= 10;
    else if (e.key === 'Home') nc = 0; else if (e.key === 'End') nc = 999; else return;
    e.preventDefault();
    nr = Math.max(0, Math.min(rows.length - 1, nr));
    const row = cells(rows[nr]); nc = Math.max(0, Math.min(row.length - 1, nc));
    const target = row[nc]; if (!target) return;
    t.tabIndex = -1; target.tabIndex = 0; target.focus();
    target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (tipFor === target) showTip(target, true);     // placed again after the scroll
    const pid = target.dataset.pid, mk = target.dataset.mk;
    scrAct = { pid, c: mk ? S.scr.cols.indexOf(mk) + 1 : 0 };
  }
  function scatKeys(e) {
    const pts = scatPoints(); if (!pts || !pts.length) return;
    let i = scatCur != null ? scatCur : Math.max(0, pts.findIndex(o => o.p.id === S.focus));
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = Math.min(pts.length - 1, i + 1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = Math.max(0, i - 1);
    else if (e.key === 'Home') i = 0; else if (e.key === 'End') i = pts.length - 1;
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (scatCur != null) { const id = pts[scatCur].p.id; scatCur = null; select(id); } return; }
    else return;
    e.preventDefault(); scatCur = i; renderScat();
    const mx = MK.get(S.scat.x), my = MK.get(S.scat.y);
    out(`${pts[i].p.name} · ${mx.label} ${fmt(mx, pts[i].a.value)} · ${my.label} ${fmt(my, pts[i].b.value)} (Enter selects)`);
  }

  wire();
  // FORM and SCAT are drawn at their panel's width: redraw them when it changes.
  let lastW = window.innerWidth, resizeT = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => { if (!ready || window.innerWidth === lastW) return; lastW = window.innerWidth; if (visible('form')) renderForm(); if (visible('scat')) renderScat(); }, 150);
  });
  // Another tab of this browser changed the workspaces (or Reset this demo cleared them): read them again.
  // When the key is gone (Reset this demo removes it), readStore() starts again from the defaults and forgets the history.
  R.store.watch((k) => {
    if (!ready || (k !== null && k !== STORE_KEY)) return;
    if (k === null) R.store.remove(STORE_KEY);   // storage cleared everywhere: forget the in-memory copy too
    readStore();
    if (!R.store.get(STORE_KEY, null)) { histAt = -1; histDraft = ''; reel = null; scatCur = null; scrAct = null; stopVideo(''); }
    paintMeta(); if (onTerminal()) { renderLayout(); renderAll(); }
  });
  // "Reset this demo" in Settings, in this tab: Regista.demo.reset() has just cleared the store (scout.js's listener runs
  // first), but the storage event only reaches other tabs. Forget the workspaces and the history held in memory too, and
  // drop a pending save, or the next save would write the old ones back.
  const resetBtn = $('stReset');
  if (resetBtn) resetBtn.addEventListener('click', () => {
    clearTimeout(saveT);
    store = { cur: 0, ws: [null, null, null], hist: [] };
    histAt = -1; histDraft = ''; reel = null; scatCur = null; scrAct = null;
    if (!ready) return;
    readStore(); paintMeta(); stopVideo(''); renderLayout(); renderAll();
  });
  window.addEventListener('hashchange', onRoute);
  onRoute();
})();
