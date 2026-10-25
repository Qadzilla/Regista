// The Scout terminal: the Terminal section of /scout (#terminal), ported from the sandbox design Zaid approved
// (ux/sandbox, sandbox/terminal.js, its "intuitive" round). A search box on top (a name, a club, a stat, a plain command
// such as "rank forwards goals", "compare Toure and Ustinov", "plot npxG against xA", "similar to Toure", or a plain
// question such as "who has the most xG?"; the old mnemonics RANK, CMP, SCAT, SIM, HL, SHOT, FORM, HEAT, RDR, TEAM and
// HELP still work; terminal-words.js reads it) over linked panels: players table, player card, radar vs position peers,
// shots, touch map, form, scatter and team. Selecting a player in any panel updates the others; every underlined number
// plays the moments behind it, all of them (the API's evidence, paged until complete), in the clips drawer (a bottom
// sheet on phones).
//
// LIVE, from the API (regista.terminal_api and the season API), read only: the metric catalogue (/api/metrics), the
// players table's columns (/api/terminal/screen), one player's every metric (/api/players/{id}/metrics), the evidence
// behind a number (?evidence=KEY&evidence_offset=N), form, similar players, shots, the league-only touch grid (/heatmap),
// the scatter, team style and team shots, the league (/api/season). The terminal writes nothing to the server.
// PER VISITOR, in this browser only: three saved layouts (panels, players, columns, axes) and the search history, through
// Regista.store (shared/regista.js), never storage directly; "Reset layout" puts the current one back to the default.
//
// Plain script on window.Regista, loaded after scout.js and terminal-words.js. The page runs under a Content Security
// Policy: no inline handlers and no style attributes in markup, so shading, colours and widths are data attributes applied
// through element.style after rendering (styleUp). Every API value that reaches innerHTML goes through esc().
(function () {
  'use strict';
  const R = window.Regista;
  const esc = R.esc;
  const PV = R.profileView;
  const TW = R.terminalWords;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  if (!$('txForm') || !TW) return;

  const norm = TW.norm;
  const ord = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const POS = ['GK', 'DF', 'MF', 'FW'];
  const POSN = { GK: 'goalkeepers', DF: 'defenders', MF: 'midfielders', FW: 'forwards' };
  const POS1 = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };
  const posOf = TW.posOf;
  const shortLabel = TW.shortLabel;
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
  // Panel-button order (Alt+1 to Alt+9). Sizes span 4, 6, 8 or 12 of the layout's 12 columns (S, M, L, XL); below the
  // first row each row is widened to fill (fillRows), so a size is how much of a row a panel asks for. Clips is not in
  // the grid: it is a drawer that opens when a number is clicked (a bottom sheet on phones).
  const PANELS = [
    { id: 'scrn', title: 'Players', size: 'L' },
    { id: 'plyr', title: 'Player', size: 'S' },
    { id: 'radar', title: 'Radar', size: 'S' },
    { id: 'clips', title: 'Clips', size: 'S', drawer: true },
    { id: 'shot', title: 'Shots', size: 'S' },
    { id: 'heat', title: 'Touch map', size: 'S' },
    { id: 'form', title: 'Form', size: 'S' },
    { id: 'scat', title: 'Scatter', size: 'S' },
    { id: 'team', title: 'Team', size: 'L' },
  ];
  // The default layout: the players table on the left with the player card and radar it drives stacked on its right,
  // then form, shots and touch map, then the scatter and the team.
  const DEFAULT_ORDER = ['scrn', 'plyr', 'radar', 'form', 'shot', 'heat', 'scat', 'team'];
  const SIZES = ['S', 'M', 'L', 'XL'];
  const SIZE_NEXT = { S: 'M', M: 'L', L: 'XL', XL: 'S' };
  const SIZE_NAME = { S: 'small', M: 'medium', L: 'large', XL: 'full width' };
  const COMMANDS = TW.COMMANDS;
  const STORE_KEY = 'terminal';      // Regista.store: regista.demo.v1.terminal, this browser only
  const VER = 3;                     // saved layouts: v2 kept Clips in the grid; v3 opens it as a drawer (clean() migrates)

  // ------------------------------------------------------------------ the data, from the API
  let CAT = null, SEASON = null, TEAMS_ALL = null, METRICS = [];
  let loading = false, ready = false, wantFocus = false;
  const MK = new Map(), TK = new Map(), PID = new Map(), CID = new Map(), TEAMS = new Map(), MATCH = new Map();
  let PLAYERS = [];
  const CELLS = new Map();           // player id -> { metric key: cell } (table columns, and every metric once loaded)
  const COLS = new Set(), colsPending = new Set();
  let colsErr = null;
  const C = new Map();               // request cache: key -> { st: wait | ok | err, v, e, p }
  let store = { cur: 0, ws: [null, null, null], hist: [] }, S = null, storageOK = true, saveT = 0;
  let reel = null, histAt = -1, histDraft = '', acItems = [], acAt = -1, scatCur = null, scrAct = null, tipFor = null;
  let colMenuOpen = false, actFrom = null, drawerFrom = null, keyAt = 0;

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
  // Repaints asked for while data lands are batched into the next frame (or 100 ms later, where a hidden page gets no
  // frames, so a tab in the background still shows its data when it comes back).
  const pending = new Set();
  let raf = false;
  function repaintSoon(id) {
    pending.add(id);
    if (raf) return;
    raf = true;
    nextFrame().then(() => {
      raf = false;
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
  // Table columns for every player who played, paged and in calls of 16 metrics, cached per metric. Each cell carries
  // evidence_total: how many moments are behind the number (a number with none is plain text, not a play link).
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
  // Whether every key has its column loaded; loads the missing ones and repaints the table when they land.
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
  // One player's every metric (the cells, each with how many moments are behind it), merged into the table of cells.
  const fullKey = (pid) => 'full|' + pid;
  const fullFn = (pid) => () => R.api(`/api/players/${enc(pid)}/metrics?evidence_limit=0`).then(j => {
    const cs = CELLS.get(pid) || {};
    for (const [k, c] of Object.entries(j.metrics || {})) { const { evidence, ...cell } = c; cs[k] = { ...cell, evidence_total: evidence ? evidence.total : null }; }
    CELLS.set(pid, cs); addPlayers([j]); return true;
  });
  const full = (pid, panel) => want(fullKey(pid), fullFn(pid), panel);
  const similar = (pid, panel) => want('sim|' + pid, () => R.api(`/api/players/${enc(pid)}/similar`), panel);
  const shotsOf = (pid, panel) => want('shots|' + pid, () => R.api(`/api/players/${enc(pid)}/shots`), panel);
  // The touch map's grid counts league fixtures only, like every other terminal number (the profile's grid adds uploads).
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

  // ------------------------------------------------------------------ reading the search box (terminal-words.js)
  // Synthetic names repeat (seven Toures, five Ustinovs), so a bare surname picks the namesake the scout most likely means:
  // the selected player themselves, or one they play like, then, when comparing, one in the same position, then one in
  // the players table as it stands, then the most minutes. The other namesakes are offered beside the answer.
  function namesakeOrder(hits, ctx = {}) {
    const cp = ctx.p || (S && PID.get(S.focus)), sm = cp && (C.get('sim|' + cp.id) || {}).v;
    const sim = new Set(((sm && sm.similar) || []).map(s => s.global_id));
    let table = null;
    const inTable = (p) => { if (!table) table = new Set(S ? screenRows().map(x => x.id) : []); return table.has(p.id); };
    const key = (p) => [!ctx.pos && cp && p.id === cp.id ? 0 : 1, sim.has(p.id) ? 0 : 1, ctx.pos && cp && p.position === cp.position ? 0 : 1, inTable(p) ? 0 : 1];
    const byKey = (a, b) => { for (let i = 0; i < a.k.length; i++) if (a.k[i] !== b.k[i]) return a.k[i] - b.k[i]; return 0; };
    return hits.map(p => ({ p, k: key(p) })).sort((a, b) => byKey(a, b) || (b.p.minutes || 0) - (a.p.minutes || 0) || a.p.name.localeCompare(b.p.name)).map(o => o.p);
  }
  const W = TW.create({ metrics: () => METRICS, defaults: () => (CAT ? CAT.default_columns : {}), clubs: () => (SEASON ? SEASON.clubs : []),
    players: () => PLAYERS.filter(p => p.name), byId: (id) => PID.get(id), focus: () => S && PID.get(S.focus), order: namesakeOrder });

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
        if (MK.has(m.key)) continue;
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
    if (!$('txClipBody')) $('txDrawerBody').appendChild(buildClipBody());
    loading = false; ready = true;
    paintMeta(); paintExamples(); paintFoot(); renderLayout(); renderAll();
    out(`Ready: ${PLAYERS.length} players, ${METRICS.length} stats, ${MATCH.size} matches. Search a name, a club or a stat, or try an example.`);
    if (onTerminal() && wantFocus) $('txIn').focus();
    if (document.activeElement === $('txIn') && $('txIn').value) suggest();   // typed while the league loaded
  }

  // ------------------------------------------------------------------ saved layouts, per visitor (Regista.store)
  function defaults() {
    const f = PID.has('pl_bro_09') ? 'pl_bro_09' : (PLAYERS.find(p => p.minutes > 0) || PLAYERS[0]).id, fp = PID.get(f);
    const cols = (CAT.default_columns[fp.position] || CAT.default_columns.all).filter(k => MK.has(k));
    return { v: VER, panels: DEFAULT_ORDER.map(id => PANELS.find(p => p.id === id)).map(p => ({ id: p.id, on: true, size: p.size })), focus: f, compare: [], club: fp.club_id,
      scr: { pos: fp.position, cols, sort: { k: cols[0], dir: -1 }, qual: true, mode: 'val', q: '' },
      scat: { x: 'npxg', y: 'xa', pos: fp.position, all: false }, form: { k: null }, radar: { tpl: 'pos' } };
  }
  // A saved layout is checked before use: unknown players, metrics and panels are dropped. Version 2 (the first port) kept
  // Clips in the grid; version 3 opens it as a drawer. A v2 layout that is still the v2 default takes the new default (the
  // table with the player card and radar beside it); a changed one keeps its order, sizes and hidden panels, minus Clips.
  // Its players, comparison, columns, sort, filters and axes carry over.
  const V2_DEFAULT = 'scrn:L,clips:S,plyr:S,radar:S,form:S,shot:S,heat:S,scat:S,team:XL';
  function clean(s) {
    const o = defaults();
    if (!s || typeof s !== 'object' || ![2, VER].includes(s.v)) return o;
    let panels = Array.isArray(s.panels) ? s.panels : null;
    if (s.v === 2 && panels && panels.map(p => p && `${p.id}:${p.size}`).join(',') === V2_DEFAULT && panels.every(p => p && p.on !== false)) panels = null;
    if (panels) {
      const seen = new Set(), ps = [];
      for (const p of panels) {
        const def = p && PANELS.find(x => x.id === p.id);
        if (def && !def.drawer && !seen.has(p.id)) { seen.add(p.id); ps.push({ id: p.id, on: p.on !== false, size: SIZES.includes(p.size) ? p.size : def.size }); }
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
      // the layouts and history still held in memory, and drop a pending save, which would write them back.
      clearTimeout(saveT);
      store = { cur: 0, ws: [null, null, null], hist: [] };
    }
    S = store.ws[store.cur] = clean(store.ws[store.cur]);
  }
  function save() {
    clearTimeout(saveT);
    saveT = setTimeout(() => { if (!R.store.set(STORE_KEY, store) && storageOK) { storageOK = false; paintMeta(); } }, 120);
  }
  // A click on 1, 2 or 3 loads that layout; there is no save button, since every change saves itself into the current one.
  function switchWs(i) {
    const was = store.cur, empty = !store.ws[i];
    store.cur = i; S = store.ws[i] = clean(store.ws[i]);
    save(); paintMeta(); renderLayout(); renderAll();
    out(i === was ? `Layout ${i + 1} is the current one (changes save automatically).`
      : `Switched to layout ${i + 1}${empty ? ', which was empty, so it starts from the default' : ''} (changes save automatically).`);
  }
  function resetWs() {
    S = store.ws[store.cur] = defaults();
    save(); paintMeta(); renderLayout(); renderAll();
    out(`Layout ${store.cur + 1} reset to the default.`);
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
  const noisy = (m) => m.noisy ? '<span class="tx-noisy" role="img" aria-label="small sample, read with care">≈</span>' : '';
  // A value with its unit as people read it: "1.64 per 90", "5 this season", "71.4%".
  function withUnit(m, v) {
    const s = fmt(m, v); if (s === '–') return s;
    const u = ['m', 'km/h'].includes(m.unit) ? ` ${m.unit}` : '';
    if (m.kind === 'per90') return `${s}${u} per 90`;
    if (m.kind === 'padj') return `${s}${u} per 90 (possession-adjusted)`;
    if (m.kind === 'total') return `${s} this season`;
    return s + u;
  }
  // The unit mark after a stat's name in the metric tables: "/90" for per-90 numbers, "total" for season counts.
  const unitMark = (m) => m.kind === 'per90' || m.kind === 'padj' ? '<span class="tx-dim tx-u"> /90</span>' : m.kind === 'total' ? '<span class="tx-dim tx-u"> total</span>' : '';
  // What a clickable number opens: "▶ 18 moments" (or matches, for numbers built per match). The count is the API's
  // evidence_total, the full list the drawer plays; a number with nothing behind it (a 0.00, most often) is plain text.
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : w === 'match' ? 'es' : 's'}`;
  const evTotalC = (c) => (c && c.evidence_total != null ? Number(c.evidence_total) : null);
  const countC = (m, c) => { const n = evTotalC(c); return n == null ? null : plural(n, m.group === 'physical' ? 'match' : 'moment'); };
  const zeroC = (c) => evTotalC(c) === 0;
  const playTextC = (m, c) => { if (zeroC(c)) return 'no moments to play'; const n = countC(m, c); return n ? `play its ${n}` : 'open its moments'; };
  const zcC = (c) => zeroC(c) ? ' z' : '';
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
  // The qualifying minutes as people say them ("101+ minutes"; the engine's threshold is a third of a club's minutes).
  const minMinutes = () => Math.ceil(Number(CAT.season.min_minutes) || 0);
  // Why a value has no percentile, as the engine decides it (metrics.py _percentiles): the metric has no percentiles at all
  // (a season count), it is not scored for the player's position, the player is under the qualifying minutes, a ratio has
  // too few attempts, or the player is the only regular peer. `small` marks a small sample (the table's italics).
  function noPct(p, m, c) {
    if (!c || c.value == null || c.percentile != null) return null;
    if (!m.has_percentile) return { text: 'no percentile: a season count, ranked by value only', small: false };
    if (!m.positions.includes(p.position)) return { text: `no percentile: not scored for ${POSN[p.position]} (scored for ${m.positions.join(' ')})`, small: false };
    if (!p.qualified) return { text: `no percentile: under ${minMinutes()} minutes`, small: true };
    if (!c.qualified) return { text: `no percentile: below the minimum attempts${c.den != null && m.min_attempts ? ` (${c.den} attempts, needs ${m.min_attempts})` : ''}`, small: true };
    return { text: `no percentile: the only regular ${POS1[p.position].toLowerCase()} on this metric, so no peers to rank against`, small: false };
  }
  const initials = (p) => { const w = String(p.name).split(' '); return w.length > 1 ? `${w[0][0]}. ${w.slice(1).join(' ')}` : p.name; };
  const lastName = (p) => String(p.name).split(' ').slice(-1)[0];
  function surname(p) { const w = norm(p.name).split(' '); return w.slice(1).join(' ') || w[0]; }
  const shirt = (p, w = 46) => PV && PV.shirtSvg ? PV.shirtSvg(club(p.club_id).kit, p.kit_number, p.position, w) : '';
  const words = (k) => { const s = String(k || '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
  const cap1 = (t) => String(t).charAt(0).toUpperCase() + String(t).slice(1);
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
  // The export's sample note in this view's words: "regular" (not "qualified"), ≈ (not "noisy"), and no module name.
  const plainSample = (t) => String(t || '').replace(/\ba qualified player's\b/g, "a regular's").replace(/\bqualified\b/g, 'regular')
    .replace(/a metric marked noisy/g, 'a stat marked ≈').replace(/ \(split-half reliability, [\w.]+\)/g, '');

  // ------------------------------------------------------------------ the status line
  // Commands wait for the network, so an older one can finish after a newer command or a click that picks a player. Each
  // command and each picked player bumps `gen`; a command whose gen is no longer current drops its line and its scroll.
  let gen = 0;
  function out(msg, kind, html) {
    const o = $('txOut'); if (!o) return;
    o.className = 'tx-out' + (kind === 'err' ? ' err' : '');
    if (html) o.innerHTML = html; else o.textContent = msg;
  }

  // ------------------------------------------------------------------ static pieces: the header line, examples, footer, layout
  // The right end of the one header line: what "≈" means (the details hold the rules), and the three saved layouts.
  function paintMeta() {
    const sm = CAT.season.sample || {}, rel = CAT.season.reliability || {};
    $('txMeta').innerHTML = `<details class="tx-about"><summary><span class="tx-noisy" aria-hidden="true">≈</span> small sample, read with care</summary>
        <div class="tx-aboutp"><p>${esc(plainSample(sm.note))}</p>
        <p><span class="tx-noisy">≈</span> marks a stat that one season cannot yet use to tell players in the same role apart (its split-half reliability is below ${esc(rel.noise_r)}).</p>
        <p>Percentiles compare a player with the regulars (at least ${esc(minMinutes())} minutes) in the same position: goalkeepers, defenders, midfielders or forwards. Where lower is better, the percentile is turned round.</p>
        <p>Every underlined number plays every moment behind it in the clips drawer. Physical numbers list one value per match (no single clip).</p></div></details>
      <div class="tx-ws" role="group" aria-label="Saved layouts"><span class="tx-wsl">Saved layouts:</span>
        ${[0, 1, 2].map(i => `<button type="button" data-act="ws" data-i="${i}" aria-pressed="${store.cur === i}" aria-label="Saved layout ${i + 1}" title="Saved layout ${i + 1}: panels, players and columns, kept in this browser">${i + 1}</button>`).join('')}
        <button type="button" data-act="reset" class="tx-reset" title="Put this layout back to the default">Reset layout</button>
        ${storageOK ? '' : '<span class="tx-warn" title="This browser blocks storage, so layouts last until you leave the page.">not saved: storage blocked</span>'}</div>`;
  }
  // Example searches under the box, each running the command it stands for.
  function paintExamples() {
    const f = PID.get('pl_bro_09') || PID.get(S.focus);
    const rival = PLAYERS.find(p => p.name === 'Amari Ustinov');
    const exs = [['Best finishers', 'rank forwards non-penalty goals'],
      ...(rival && rival !== f ? [[`Compare ${lastName(f)} and ${lastName(rival)}`, `compare ${f.name} and ${rival.name}`]] : []),
      [`Who plays like ${lastName(f)}?`, `similar to ${f.name}`]];
    $('txEx').innerHTML = `<span class="tx-exl">Try</span>${exs.map(([l, c]) => `<button type="button" class="tx-exb" data-act="run" data-cmd="${esc(c)}" title="Runs: ${esc(c)}">${esc(l)}</button>`).join('')}`;
  }
  // Synthetic data, said once and plainly, at the bottom of the section.
  function paintFoot() {
    const first = String(CAT.note || CAT.season.note || '').split('. ')[0].replace(/\.$/, ''), i = first.indexOf(': ');
    const lead = i > 0 ? first.slice(0, i) : 'Synthetic data', rest = i > 0 ? first.slice(i + 2) : first;
    $('txFoot').innerHTML = `<b>${esc(lead)}:</b> ${esc(rest)}.`;
  }
  function paintKeys() {
    const dOpen = drawerOpen();
    $('txKeys').innerHTML = PANELS.map((p, i) => {      // in shortcut order, whatever the layout
      const n = i + 1, pp = p.drawer ? { on: dOpen } : S.panels.find(x => x.id === p.id) || { on: false };
      // Not a toggle: a panel button always shows its panel and moves to it, so it says whether the panel is hidden instead.
      const tip = p.drawer ? `Clips: open the clips drawer (Alt+${n})` : `${p.title}${pp.on ? ': go to it' : ' is hidden: show it'} (Alt+${n})`;
      return `<button type="button" class="tx-fkey" data-act="fkey" data-id="${p.id}" data-on="${pp.on}" aria-keyshortcuts="Alt+${n}"${p.drawer ? ` aria-expanded="${dOpen}" aria-controls="txDrawer"` : ''}
        aria-label="${esc(p.title)}${p.drawer || pp.on ? '' : ', hidden: show it'}" title="${esc(tip)}">${esc(p.title)}</button>`;
    }).join('') + '<button type="button" class="tx-fkey help" data-act="help" aria-haspopup="dialog" title="Commands, keys and what the numbers mean">Help</button>';
  }
  const ICON = {
    left: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg>',
    right: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5"/></svg>',
    size: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M9.5 2.5h4v4M13.5 2.5 9 7M6.5 13.5h-4v-4M2.5 13.5 7 9"/></svg>',
    close: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
  };
  function renderLayout() {
    const g = $('txGrid');
    const on = S.panels.filter(p => p.on && !(PANELS.find(x => x.id === p.id) || {}).drawer);
    // The players table runs down beside the two panels that follow it when they are small (the default: the player card
    // and the radar stacked on its right), on screens wide enough for that.
    const tall = on.length >= 3 && on[0].id === 'scrn' && on[0].size === 'L' && on[1].size === 'S' && on[2].size === 'S';
    const secs = on.map((pp, i) => {
      const p = PANELS.find(x => x.id === pp.id), t = esc(p.title), nx = SIZE_NEXT[pp.size];
      return `<section class="tx-panel s-${pp.size}${tall && i === 0 ? ' tall' : ''}" id="tx-p-${p.id}" data-txp="${p.id}" aria-labelledby="tx-h-${p.id}">
        <header class="tx-ph"><h2 id="tx-h-${p.id}" tabindex="-1">${t}</h2>
          <span class="tx-pctx" data-ctx></span>
          <span class="tx-pbtns" role="group" aria-label="Arrange ${t}">
            <button type="button" data-act="pmove" data-id="${p.id}" data-d="-1" aria-label="Move ${t} earlier" title="Move earlier"${i === 0 ? ' disabled' : ''}>${ICON.left}</button><button type="button" data-act="pmove" data-id="${p.id}" data-d="1" aria-label="Move ${t} later" title="Move later"${i === on.length - 1 ? ' disabled' : ''}>${ICON.right}</button><button type="button" data-act="psize" data-id="${p.id}" aria-label="${t}: ${SIZE_NAME[pp.size]}, make it ${SIZE_NAME[nx]}" title="Size: ${SIZE_NAME[pp.size]} (click for ${SIZE_NAME[nx]})">${ICON.size}</button><button type="button" data-act="pclose" data-id="${p.id}" aria-label="Hide ${t}" title="Hide (its button above brings it back)">${ICON.close}</button></span></header>
        <div class="tx-pb" data-body></div></section>`;
    });
    // Wide screens: the table top left, the card and radar in a right column beside it, and a slot under the table that the
    // next panels may move into (fitTall); the panels after them go in the grid below, each row filled (fillRows).
    // Narrower, the columns dissolve (display: contents) and every panel is a grid item again.
    g.innerHTML = !secs.length ? '<p class="tx-empty">Every panel is hidden. Press a panel button above to bring one back.</p>'
      : tall ? `<div class="tx-split">${secs[0]}<div class="tx-colR">${secs[1]}${secs[2]}</div><div class="tx-colL"></div></div>${secs.slice(3).join('')}`
      : secs.join('');
    watchTall(tall ? [on[1].id, on[2].id] : null);
    paintKeys(); paintNav();
  }
  // The tall players table is capped at the height of the card and radar beside it. The panels that come next (form,
  // shots, touch map…) may move up into the slot under the table, two to a row, in their order. fitTall tries every count
  // (none, the first, the first two…) and keeps the one that leaves the least empty space on the page, counting the space
  // beside the radar, the half row a single panel leaves in the slot, and the rows below; so a short table (18 forwards,
  // the goalkeepers) pulls panels up and a long one (every position) leaves them below. Kept in step as the panels
  // change; it runs after the paints that change these heights too, since a hidden tab may hold back ResizeObserver
  // callbacks.
  let tallRO = null, tallIds = null, balancing = false, bulk = false;
  const WIDE_MQ = '(min-width: 1101px)', PHONE_MQ = '(max-width: 720px)';
  // Below the columns, every row of panels fills the 12 columns: a panel's size (small, medium, large, full width) is how
  // much of a row it asks for, and what a row leaves over is shared among its panels, so no block is left empty at the
  // end of a row. Phones stack the panels at full width (CSS), so nothing is set there.
  function fillRows() {
    const g = $('txGrid'); if (!g) return;
    const panels = [...g.querySelectorAll('.tx-panel')];
    for (const el of panels) el.style.gridColumn = '';
    if (matchMedia(PHONE_MQ).matches) return;
    const wide = matchMedia(WIDE_MQ).matches;
    const BASE = wide ? { S: 4, M: 6, L: 8, XL: 12 } : { S: 6, M: 6, L: 12, XL: 12 };
    // Wide, only the grid's own children (the split's panels are laid out by its columns); narrower, every panel.
    const items = wide ? panels.filter(el => el.parentElement === g) : panels;
    let row = [], used = 0;
    const flush = () => {
      const left = 12 - used, add = row.length ? Math.floor(left / row.length) : 0;
      let rem = left - add * row.length;
      for (const r of row) { const n = r.span + add + (rem > 0 ? 1 : 0); rem--; r.el.style.gridColumn = `span ${n}`; }
      row = []; used = 0;
    };
    for (const el of items) {
      const span = BASE[(el.className.match(/\bs-(S|M|L|XL)\b/) || [])[1] || 'S'];
      if (used + span > 12) flush();
      row.push({ el, span }); used += span;
    }
    flush();
  }
  function fitTall() {
    const sc = $('tx-p-scrn'), L = document.querySelector('#txGrid .tx-colL'), Rc = document.querySelector('#txGrid .tx-colR');
    if (!sc || !L || !Rc) { if (!balancing && !bulk) fillRows(); return; }
    if (balancing || bulk) return;
    balancing = true;
    const a = document.activeElement, split = L.parentElement, g = $('txGrid');
    const widthOf = (id) => { const b = document.querySelector(`#tx-p-${id} [data-body]`); return b ? b.clientWidth : 0; };
    const w0 = { form: widthOf('form'), scat: widthOf('scat') };
    try {
      const wide = getComputedStyle(split).display !== 'contents';
      sc.style.setProperty('--tx-tallh', `${Math.max(480, Math.floor(Rc.offsetHeight))}px`);
      // Everything back below the columns, in order; then, wide, try each count of panels in the slot.
      for (const f of [...L.children].reverse()) split.after(f);
      if (wide) {
        const after = [];
        for (let n = split.nextElementSibling; n && n.classList.contains('tx-panel') && after.length < 6; n = n.nextElementSibling) after.push(n);
        // Empty space: the grid's area less the panels' areas (the gaps between panels are the same for every count).
        const empty = () => { fillRows(); const gr = g.getBoundingClientRect(); let s = gr.width * gr.height; for (const el of g.querySelectorAll('.tx-panel')) s -= el.offsetWidth * el.offsetHeight; return s; };
        let best = 0, bestE = empty();
        for (let k = 1; k <= after.length; k++) {
          L.appendChild(after[k - 1]);
          const e = empty();
          if (e < bestE - 2000) { best = k; bestE = e; }      // strictly better by more than a sliver; else keep fewer moved up
        }
        for (let k = after.length; k > best; k--) split.after(after[k - 1]);
      }
      fillRows();
      // Form and Scatter are drawn at their panel's width: redraw the ones that changed width.
      for (const id of ['form', 'scat']) if (visible(id) && widthOf(id) !== w0[id]) RENDER[id]();
    } finally { balancing = false; }
    if (a && a !== document.body && a !== document.activeElement && document.contains(a)) a.focus({ preventScroll: true });
  }
  function watchTall(ids) {
    if (tallRO) { tallRO.disconnect(); tallRO = null; }
    tallIds = ids;
    if (!ids) { fillRows(); return; }
    if (typeof ResizeObserver === 'function') { tallRO = new ResizeObserver(() => fitTall()); [ids[0], ids[1]].forEach(id => { const el = $('tx-p-' + id); if (el) tallRO.observe(el); }); }
    fitTall();
  }
  // Phones: a sticky row of the panels, so a scout jumps to one instead of scrolling past them all.
  function paintNav() {
    const on = S.panels.filter(p => p.on);
    $('txNav').innerHTML = on.map(pp => { const p = PANELS.find(x => x.id === pp.id); return p && !p.drawer ? `<button type="button" data-act="fkey" data-id="${p.id}">${esc(p.title)}</button>` : ''; }).join('')
      + `<button type="button" data-act="fkey" data-id="clips" aria-expanded="${drawerOpen()}" aria-controls="txDrawer">Clips</button>`;
    navCurrent();
  }
  let navHold = null, navHoldT = 0;
  function navCurrent(jumped) {
    const nav = $('txNav'); if (!nav || getComputedStyle(nav).display === 'none') return;
    // A jump marks its panel at once and holds it while the smooth scroll runs.
    if (jumped) { navHold = jumped; clearTimeout(navHoldT); navHoldT = setTimeout(() => { navHold = null; }, 900); }
    const line = barBottom() + 12;
    let cur = navHold;
    if (!cur) for (const sec of document.querySelectorAll('#txGrid .tx-panel')) { if (sec.getBoundingClientRect().top <= line) cur = sec.dataset.txp; }
    if (!cur) { const f = document.querySelector('#txGrid .tx-panel'); cur = f && f.dataset.txp; }
    for (const b of nav.querySelectorAll('button')) {
      const isCur = b.dataset.id === cur;
      if (isCur !== (b.getAttribute('aria-current') === 'true')) { if (isCur) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); }
      if (isCur) { const bl = b.offsetLeft, br = bl + b.offsetWidth; if (bl < nav.scrollLeft || br > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = bl - 16; }
    }
  }
  const visible = (id) => !!S && S.panels.some(p => p.id === id && p.on);
  // Show a panel and bring what the command is about into view: its chart or table (or `sel` inside it, a selector or an
  // element), not just its top edge, since a panel whose header peeks in at the bottom of the screen hides the chart.
  // `force` (the phone's panel row) always brings the panel's top up under the row.
  function showPanel(id, scroll = true, sel, force = false) {
    if (id === 'clips') { openDrawer(true); return; }
    const pp = S.panels.find(p => p.id === id);
    if (pp && !pp.on) { pp.on = true; save(); renderLayout(); renderAll(); }
    if (!scroll) return;
    const el = $('tx-p-' + id);
    if (!el) return;
    const body = el.querySelector('[data-body]');
    const target = (sel instanceof Element ? sel : sel && el.querySelector(sel)) || (body && body.querySelector('svg.tx-svg, .tx-tablewrap')) || body || el;
    if (force) scrollToShow(el, el); else if (!inViewFit(target, 0.6)) scrollToShow(el, target);
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }
  function renderAll() {
    if (!ready) return;
    renderSel();
    bulk = true;
    try { for (const p of S.panels) if (p.on && RENDER[p.id]) RENDER[p.id](); } finally { bulk = false; }
    fitTall();
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
    if (tallIds && (tallIds.includes(id) || id === 'scrn' || sec.parentElement.classList.contains('tx-colL'))) fitTall();
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
    if (!quiet) gen++;  // a player picked by hand overrides any command still loading
    S.focus = pid; S.club = p.club_id; scatCur = null;
    save(); renderAll();
    if (!quiet) out(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`);
  }
  // Beside the search: the selected player, and the comparison when there is one.
  function renderSel() {
    const f = PID.get(S.focus);
    const chips = S.compare.map((id, i) => { const p = PID.get(id); return `<span class="tx-chip" data-c="${CMP_COL[i]}"><button type="button" data-act="sel" data-pid="${esc(id)}" data-fid="chip-${esc(id)}" title="Select ${esc(p.name)}">${esc(p.name)}</button><button type="button" class="tx-x" data-act="cmprm" data-pid="${esc(id)}" aria-label="Remove ${esc(p.name)} from the comparison" title="Remove from the comparison">&times;</button></span>`; }).join('');
    const inCmp = S.compare.includes(S.focus);
    let btn = '';
    if (!S.compare.length || (inCmp && S.compare.length < 3)) btn = '<button type="button" class="tx-mini tx-cmpw" data-act="cmpwith" title="Type a player to compare with">Compare with…</button>';
    else if (!inCmp) btn = `<button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(S.focus)}">Add ${esc(f.name)} to the comparison${S.compare.length >= 3 ? ` (replaces ${esc(PID.get(S.compare[0]).name)})` : ''}</button>`;
    $('txSel').innerHTML = `<span class="tx-sl">Selected:</span><button type="button" class="tx-focus" data-act="pane" data-id="plyr" title="Go to the player card">${esc(f.name)} <span>${esc(f.short_name)} · ${esc(f.position)} · #${esc(f.kit_number)}</span></button>
      ${S.compare.length ? `<span class="tx-sl">Comparing:</span>${chips}` : ''}${btn}
      ${S.compare.length ? '<button type="button" class="tx-mini" data-act="cmpclear" title="Stop comparing">Clear</button>' : ''}`;
    styleUp($('txSel'));
  }
  // "Compare with…": the search box takes "compare <selected>, " and suggests the player to add.
  function compareWith() {
    const names = (S.compare.includes(S.focus) ? S.compare : [S.focus, ...S.compare]).map(id => PID.get(id).name);
    const inp = $('txIn');
    inp.value = `compare ${names.join(', ')}, `;
    inp.focus({ preventScroll: true }); inp.setSelectionRange(inp.value.length, inp.value.length);
    suggest();
    out(`Type the player to compare with ${listText(names)}, then pick them or press Enter.`);
  }
  function addCompare(pid) {
    if (S.compare.includes(pid)) return;
    if (S.compare.length >= 3) S.compare.shift();
    S.compare.push(pid); save(); renderAll();
  }

  // ------------------------------------------------------------------ evidence into the clips drawer
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
    return `${fmt(m, c.value)}${m.kind === 'ratio' && m.unit === '%' ? '' : ' ' + unitText(m)}${c.num != null ? ` · ${c.num} of ${c.den}` : c.total != null && m.kind !== 'total' ? ` · ${c.total} in total` : ''}${c.percentile != null ? ` · ${ord(c.percentile)} percentile` : ''}`;
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
  // The first number opens the drawer and moves keyboard focus into it (Escape or Close brings it back); while it is open,
  // later numbers just change what it plays, so a scout can keep arrowing through the table. `say` writes the status line
  // (a reel that finished loading after a newer command does not).
  function openReel(r, startAt = 0, say = true) {
    reel = r;
    const was = drawerOpen();
    renderClips();
    const first = r.items.findIndex((it, i) => i >= startAt && it.video);
    if (first >= 0) play(first, true); else if (r.items.length) { reel.i = startAt; renderClips(); stopVideo(r.items[startAt] ? 'nolink' : ''); }
    else stopVideo('');
    openDrawer(!was);
    const name = String(r.title).replace(/ ≈$/, '');
    if (say) out(r.items.length ? `Playing ${name}: ${plural(r.items.length, r.unit === 'match' ? 'match' : 'moment')}${r.match ? ' in this match' : ''}.` : `${name}: nothing to play.`);
  }
  // While the moments load, the drawer says so (a long list comes in pages of 500).
  function reelLoading(title) {
    reel = { title, sub: '', items: [], i: -1, note: 'Loading every moment behind this number…', loading: true };
    stopVideo('');
    const was = drawerOpen();
    renderClips();
    openDrawer(!was);
  }
  async function openEvidence(pid, mk, match) {
    const p = PID.get(pid), m = MK.get(mk);
    if (!p || !m) return;
    const g = gen, c = evidenceOf(pid, mk);
    if (c.st !== 'ok') reelLoading(`${p.name} · ${m.label}`);
    const ev = await settle(c);
    if (!ev) C.delete(`ev|${pid}|${mk}`);
    openReel(evidenceReel(pid, mk, ev, match), 0, g === gen);
  }
  const drawerOpen = () => { const d = $('txDrawer'); return !!d && !d.hidden; };
  function openDrawer(focus) {
    const d = $('txDrawer'), was = !d.hidden;
    if (!was) {
      drawerFrom = actFrom && actFrom.el && document.contains(actFrom.el) ? actFrom : { el: document.activeElement };
      d.hidden = false; document.querySelector('.tx').classList.add('tx-dopen');
      renderClips(); paintKeys(); paintNav();
    } else if (actFrom && actFrom.el && !d.contains(actFrom.el)) drawerFrom = actFrom;
    if (focus) $('txDrawerH').focus({ preventScroll: true });
  }
  function closeDrawer() {
    const d = $('txDrawer'); if (!d || d.hidden) return;
    const v = clipVideo(); if (v) v.pause();
    const had = d.contains(document.activeElement);
    d.hidden = true; document.querySelector('.tx').classList.remove('tx-dopen');
    if (S) { paintKeys(); paintNav(); }
    const back = drawerFrom; drawerFrom = null;
    if (!had && document.activeElement && document.activeElement !== document.body) return;
    // Back to what opened it, or, when a repaint replaced that control, to the same control in its panel.
    const usable = (el) => el && document.contains(el) && el.getClientRects().length;
    let el = back && usable(back.el) ? back.el : null;
    if (!el && back && back.sel) el = [...((back.scope && $(back.scope)) || document).querySelectorAll(back.sel)].find(usable) || null;
    if (!el && back && back.scope && $(back.scope)) el = $(back.scope).querySelector('h2') || null;
    (el || $('txIn')).focus({ preventScroll: true });
  }
  // The bottom of what stays on top while scrolling: the sticky search bar on a wide screen; on a phone, where the bar
  // scrolls away, the site header when it sticks and the terminal's own row of panels under it.
  function barBottom() {
    const bar = document.querySelector('.tx-top');
    if (bar && getComputedStyle(bar).position === 'sticky') return bar.getBoundingClientRect().bottom;
    const top = document.querySelector('header.top');
    const site = top && /sticky|fixed/.test(getComputedStyle(top).position) ? Math.max(0, top.getBoundingClientRect().bottom) : 0;
    // The panel row's bottom once it has stuck (where it will be after a scroll down), not where it sits before that.
    const nav = $('txNav');
    return Math.max(site, nav && getComputedStyle(nav).display !== 'none' ? (parseFloat(getComputedStyle(nav).top) || 0) + nav.offsetHeight : 0);
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
  // A player's highlights: one reel of the moments behind their goals, assists, saves, shots (every one, from the shot
  // list), chances made, skills and defending, each clip once (a goal is not also a shot, an assist not also a key pass),
  // in that order of importance and match by match within each. Every moment of each stat, read through the API.
  const HL_KINDS = [['goals', 'Goal', 'goals'], ['assists', 'Assist', 'assists'], ['penalties_saved', 'Penalty saved', 'penalties saved'],
    ['saves', 'Save', 'saves'], ['shots', 'Shot', 'other shots'], ['key_passes', 'Chance made', 'chances made'], ['nutmegs', 'Nutmeg', 'nutmegs'],
    ['skill_moves', 'Skill move', 'skill moves'], ['take_ons_won', 'Take-on won', 'take-ons won'], ['tackles_won', 'Tackle won', 'tackles won'],
    ['interceptions', 'Interception', 'interceptions'], ['blocks', 'Block', 'blocks']];
  const OUTCOME = { saved: 'saved', blocked: 'blocked', off_target: 'off target', goal: 'goal' };
  async function highlightsReel(p) {
    const kinds = HL_KINDS.filter(([mk]) => mk === 'shots' || MK.has(mk));
    const loads = await Promise.all(kinds.map(([mk]) => settle(mk === 'shots' ? shotsOf(p.id) : evidenceOf(p.id, mk))));
    const seen = new Set(), items = [], counts = [];
    let failed = false;
    const keyOf = (mo) => mo.clip_id || mo.video_url || `${mo.match_id}|${mo.t}`;
    const roundOf = (mo) => mo.round != null ? mo.round : ((MATCH.get(mo.match_id) || {}).round || 0);
    kinds.forEach(([mk, word, many], i) => {
      const got0 = loads[i];
      if (!got0) { failed = true; if (mk !== 'shots') C.delete(`ev|${p.id}|${mk}`); return; }
      let got;
      if (mk === 'shots') got = (got0.shots || []).filter(sh => sh.outcome !== 'goal').map(sh => ({ mo: sh, val: `xG ${Number(sh.xg).toFixed(2)}`, note: `Shot, ${OUTCOME[sh.outcome] || words(sh.outcome).toLowerCase()}${sh.penalty ? ' (penalty)' : ''}` }));
      else if (got0.per_match || (got0.keys || []).length > 1) return;
      else got = (got0.items || []).map(it => ({ mo: it, val: '', note: word }));
      got = got.filter(x => x.mo && x.mo.video_url && VIDEO.test(String(x.mo.video_url)) && !seen.has(keyOf(x.mo)));
      got.sort((x, y) => (roundOf(x.mo) - roundOf(y.mo)) || ((x.mo.minute || 0) - (y.mo.minute || 0)));
      for (const x of got) { seen.add(keyOf(x.mo)); items.push({ when: matchFor(x.mo.match_id, p.club_id).when, minute: x.mo.minute, val: x.val || word, note: x.val ? x.note : '', video: x.mo.video_url, match_id: x.mo.match_id }); }
      if (got.length) counts.push(got.length === 1 ? `1 ${mk === 'shots' ? 'other shot' : word.toLowerCase()}` : `${got.length} ${many}`);
    });
    return { title: `${p.name} · Highlights`, sub: counts.length ? cap1(listText(counts)) : 'No moments yet', kind: 'highlights', counts,
      items, i: -1, pid: p.id, mk: null, match: null,
      note: failed ? 'Some of the moments did not load; ask for the highlights again to retry.' : items.length ? '' : `${p.name} has no goals, shots, chances made, skills or defensive moments with a clip this season.`,
      legend: items.length ? 'Goals first, then the rest by importance, match by match.' : '' };
  }
  async function playHighlights(p, alts, g) {
    select(p.id, true);
    reelLoading(`${p.name} · Highlights`);
    out(`${p.name}: loading the highlights…`);
    const r = await highlightsReel(p);
    if (g !== gen) return;
    openReel(r, 0, false);
    out('', '', r.items.length ? esc(`Playing ${p.name}'s highlights: ${listText(r.counts)} (${plural(r.items.length, 'moment')}).`) + altsHtml(alts, 'HL')
      : esc(`${p.name} has no highlights to play yet.`) + altsHtml(alts, 'HL'));
  }

  // ------------------------------------------------------------------ Clips: the drawer (its video element is built once)
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
    const ctx = $('txDrawerCtx');
    // Nothing to play (a number with no moments, a player with no shots): no player and no controls, just the plain reason.
    const empty = !!reel && !reel.loading && !reel.items.length;
    b.querySelector('.tx-screen').hidden = !reel || reel.loading || empty;
    b.querySelector('.tx-clipctl').hidden = !reel || reel.loading || empty;
    if (!reel) {
      head.innerHTML = '<p class="tx-dim">Click any underlined number in any panel: the moments behind it play here.</p>';
      list.innerHTML = ''; if (ctx) ctx.textContent = ''; return;
    }
    const n = reel.items.length, unit = reel.unit === 'match' ? (n === 1 ? 'match' : 'matches') : (n === 1 ? 'moment' : 'moments');
    head.innerHTML = `<p class="tx-ct">${esc(reel.title)}</p>${reel.sub ? `<p class="tx-cs">${esc(reel.sub)}</p>` : ''}
      ${reel.loading ? '' : empty ? `<p class="tx-cs tx-none">${reel.note ? 'Nothing to play.' : 'Nothing to play: there are no moments behind this number.'}</p>` : `<p class="tx-cs">${reel.match ? `${esc(n)} in this match` : `${esc(n)} ${unit}`}</p>`}
      ${!empty && reel.legend ? `<p class="tx-cs tx-dim">${esc(reel.legend)}</p>` : ''}${reel.note ? `<p class="tx-cs tx-dim">${esc(reel.note)}</p>` : ''}`;
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

  // ------------------------------------------------------------------ Players: the players table
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
  // percentile is a separate thing (position peers only) and only the shading and the Percentile view show it.
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
    // Sorted by a stat whose column was removed: sort by the first column left (else by minutes), so the order is always
    // explained by a column the scout can see and click.
    if (MK.has(sc.sort.k) && !cols.includes(sc.sort.k)) {
      const k = cols[0];
      sc.sort = k ? { k, dir: MK.get(k).higher_is_better === false ? 1 : -1 } : { k: 'min', dir: -1 };
      save();
    }
    const all = ensureCols(cols);
    const rows = screenRows();
    const sortAttr = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? 'descending' : 'ascending') : 'none';
    if (!scrAct || !rows.some(p => p.id === scrAct.pid)) scrAct = { pid: rows.some(p => p.id === S.focus) ? S.focus : (rows[0] && rows[0].id), c: 0 };
    if (scrAct.c > cols.length) scrAct.c = 0;
    const cell = (p, k, ci) => {
      const m = MK.get(k), act = scrAct.pid === p.id && scrAct.c === ci + 1, c = cellOf(p, k);
      if (!COLS.has(k) && !c) return '<td class="num"><span class="tx-dim" aria-label="loading">…</span></td>';
      if (!c) return '<td class="num"><span class="tx-dim">–</span></td>';
      const txt = sc.mode === 'pct' ? (c.percentile == null ? '–' : c.percentile) : fmt(m, c.value);
      const np = noPct(p, m, c);
      const lab = `${p.name}, ${m.label} ${withUnit(m, c.value)}${c.percentile != null ? `, ${ord(c.percentile)} percentile` : np ? `, ${np.text}` : ''}. ${cap1(playTextC(m, c))}`;
      return `<td class="num"><button type="button" class="tx-n${np && np.small ? ' uq' : ''}${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-sel="1" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-nav data-fid="c-${esc(p.id)}-${esc(k)}" tabindex="${act ? 0 : -1}" aria-label="${esc(lab)}">${esc(txt)}</button></td>`;
    };
    // A click on a header sorts (again: the other way); the sorted column is the yellow one, and the panel's header says
    // which way. Removing a column is in the Columns menu.
    const sortBtn = (k, label, extra = '') => `<button type="button" data-act="sort" data-k="${esc(k)}" data-fid="h-${esc(k)}"${extra}>${label}</button>`;
    const head = `<tr><th class="tx-stk" aria-sort="${sortAttr('name')}">${sortBtn('name', 'Player')}</th>
      <th class="tx-hc" aria-sort="${sortAttr('club')}">${sortBtn('club', 'Club')}</th><th class="tx-hc">Pos</th>
      <th class="num" aria-sort="${sortAttr('min')}">${sortBtn('min', 'Mins', ' title="Minutes played"')}</th>
      ${cols.map(k => { const m = MK.get(k); return `<th class="num" aria-sort="${sortAttr(k)}">${sortBtn(k, `${esc(shortLabel(m))}${m.kind === 'total' ? ' <span class="tx-u">(total)</span>' : ''}${noisy(m)}`, `${shortLabel(m).length <= 12 ? ' class="nw"' : ''} data-mk="${esc(k)}" aria-label="${esc(m.label)}${m.noisy ? ', small sample' : ''}, sort"`)}</th>`; }).join('')}</tr>`;
    const ranks = all ? screenRanks(rows) : rows.map(() => null);
    const body = rows.map((p, r) => {
      const ci = S.compare.indexOf(p.id), act = scrAct.pid === p.id && scrAct.c === 0;
      return `<tr class="${p.id === S.focus ? 'on' : ''}${ci >= 0 ? ' cmp' : ''}" data-row="${esc(p.id)}"${ci >= 0 ? ` data-c="${CMP_COL[ci]}"` : ''}>
        <th class="tx-stk" scope="row"><span class="tx-rk">${ranks[r] == null ? '–' : ranks[r]}</span><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-nav data-fid="n-${esc(p.id)}" tabindex="${act ? 0 : -1}"${p.id === S.focus ? ' aria-current="true"' : ''}>${esc(p.name)}</button><span class="tx-sub">${esc(p.short_name)} · ${esc(p.position)} ${esc(p.role)}</span></th>
        <td class="tx-hc">${esc(p.short_name)}</td><td class="tx-hc">${esc(p.position)} <span class="tx-dim">${esc(p.role)}</span></td><td class="num">${esc(Math.round(p.minutes))}</td>
        ${cols.map((k, i) => cell(p, k, i)).join('')}</tr>`;
    }).join('');
    const status = colsErr ? ` · <span class="tx-bad">a column did not load (${esc(errText(colsErr))})</span> <button type="button" class="tx-mini" data-act="colsretry">Retry</button>`
      : all ? '' : ' · <span class="tx-wait">loading columns…</span>';
    const html = `<div class="tx-ctls">
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scrpos" data-v="${v || ''}" aria-pressed="${sc.pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-ctl"><span class="sr">Filter by name or club</span><input type="search" data-r="scrq" data-fid="scr-q" value="${esc(sc.q)}" placeholder="Filter by name or club" autocomplete="off" maxlength="40"></label>
        <label class="tx-chk"><input type="checkbox" data-r="scrqual" data-fid="scr-qual"${sc.qual ? ' checked' : ''}> Regulars only (${esc(minMinutes())}+ minutes)</label>
        <div class="tx-seg" role="group" aria-label="Show"><button type="button" data-act="scrmode" data-v="val" aria-pressed="${sc.mode === 'val'}">Value</button><button type="button" data-act="scrmode" data-v="pct" aria-pressed="${sc.mode === 'pct'}">Percentile</button></div>
        <details class="tx-menu" data-r="colmenu"${colMenuOpen ? ' open' : ''}><summary class="tx-mini" data-fid="scr-cols">Columns (${cols.length})</summary>
          <div class="tx-menup" role="group" aria-label="Columns">
            ${cols.length ? `<ul class="tx-collist">${cols.map(k => { const m = MK.get(k); return `<li><span>${esc(m.label)}${noisy(m)}</span><button type="button" class="tx-x" data-act="rmcol" data-k="${esc(k)}" data-fid="rm-${esc(k)}" aria-label="Remove the ${esc(m.label)} column" title="Remove">&times;</button></li>`; }).join('')}</ul>` : '<p class="tx-dim">No stat columns.</p>'}
            <label class="tx-ctl tx-addcol"><span>Add</span><select data-r="addcol" data-fid="scr-add"${cols.length >= MAX_COLS ? ' disabled' : ''}><option value="">a stat…</option>${metricOptions(null, m => !cols.includes(m.key))}</select></label>
            <button type="button" class="tx-mini" data-act="scrdef">Default columns</button></div></details></div>
      <p class="tx-cap">${rows.length} ${esc(sc.pos ? POSN[sc.pos] : 'players')}${sc.qual ? ', regulars only' : ''} · <b class="tx-capu">${sc.mode === 'pct' ? 'percentiles vs the same position' : `values per 90 minutes${cols.some(k => { const x = MK.get(k); return x.kind !== 'per90' && x.kind !== 'padj'; }) ? ' (except %, averages and totals)' : ''}`}</b><span class="tx-capx">${sc.mode === 'pct' ? '' : ' · shading = percentile vs the same position'}${ranks.some(x => x == null) && all ? ' · – = not ranked (too few minutes or attempts)' : ''} · click a row to select, an underlined number to play its moments</span>${status}</p>
      <div class="tx-scroll tx-tablewrap"><table class="tx-table"><thead>${head}</thead><tbody data-r="grid">${body || `<tr><td colspan="${4 + cols.length}" class="tx-dim">No players match.</td></tr>`}</tbody></table></div>`;
    const sm = MK.get(sc.sort.k), dirWord = sc.sort.dir === -1 ? (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'Z to A' : 'highest first') : (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'A to Z' : 'lowest first');
    const sortName = sm ? shortLabel(sm) : { name: 'name', club: 'club', min: 'minutes' }[sc.sort.k];
    paint('scrn', html, sortName ? esc(`Sorted by ${sortName}, ${dirWord}`) : '');
  }
  // Alt+1: straight into the players table, on its active cell (one tab stop; arrows move from there).
  function focusGrid() {
    const cellEl = document.querySelector('#tx-p-scrn tbody[data-r="grid"] [data-nav][tabindex="0"]') || document.querySelector('#tx-p-scrn tbody[data-r="grid"] [data-nav]');
    if (cellEl) { cellEl.focus({ preventScroll: true }); cellEl.scrollIntoView({ block: 'nearest', inline: 'nearest' }); return true; }
    return false;
  }

  // ------------------------------------------------------------------ Player: the player card, top numbers, similar players
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
      best = p.minutes > 0 ? `<h3 class="tx-h3">Best among ${esc(POSN[p.position])}</h3>
        <table class="tx-mt tx-best"><tbody>${strengths.map(m => mrow(p, m)).join('') || '<tr><td class="tx-dim">No percentiles yet (too few minutes).</td></tr>'}</tbody></table>
        <p class="tx-cap">/90 = per 90 minutes played. The bar and the last number are the percentile among regular ${esc(POSN[p.position])}.</p>` : '<p class="tx-dim">No minutes this season.</p>';
    }
    let sim;
    if (sm.st !== 'ok') sim = waitHtml(sm, 'similar players');
    else {
      const list = sm.v.similar || [];
      sim = list.length ? `<ol class="tx-sim">${list.map(s => `<li><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(s.global_id)}" data-fid="sim-${esc(s.global_id)}">${esc(s.name)}</button>
        <span class="tx-dim">${esc(s.short_name)} ${esc(s.position)}</span><span class="tx-simbar" aria-label="similarity ${esc(s.similarity)}"><i data-w="${Math.max(2, Math.round(s.similarity * 100))}"></i></span><span class="num">${esc(Number(s.similarity).toFixed(2))}</span>
        <span class="tx-shared">${(s.shared_strengths || []).filter(k => MK.has(k)).map(k => `<button type="button" class="tx-kchip" data-act="ev" data-pid="${esc(s.global_id)}" data-mk="${esc(k)}" data-fid="sim-${esc(s.global_id)}-${esc(k)}">${esc(MK.get(k).label)}</button>`).join('')}</span></li>`).join('')}</ol>
        <p class="tx-cap">Similarity (1 = identical) on the ${esc(p.position === 'GK' ? 'goalkeeper' : 'outfield')} stats, among regular ${esc(POSN[p.position])}; the chips are strengths they share (each plays that player's moments).${list.every(s => s.similarity < 0.5) ? ' No close match: every similarity is under 0.50.' : ''}</p>` : '<p class="tx-dim">No similar players (too few minutes).</p>';
    }
    const html = `<div class="tx-card"><span class="tx-shirt" aria-hidden="true">${shirt(p)}</span>
        <div><p class="tx-name">${esc(p.name)}</p><p class="tx-line">${esc(p.club)} · ${esc(POS1[p.position])} (${esc(p.role)}) · #${esc(p.kit_number)}
          ${p.qualified ? `<span class="tx-tag" title="At least ${esc(minMinutes())} minutes, so the player has percentiles">Regular</span>` : `<span class="tx-tag dim">Under ${esc(minMinutes())} minutes</span>`}</p>
          <p class="tx-prof"><a href="/players/${esc(enc(p.id))}">Open profile &rarr;</a></p></div></div>
      <dl class="tx-bio">${bio.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v ?? '–')}</dd></div>`).join('')}</dl>
      <div class="tx-acts"><button type="button" class="tx-mini" data-act="cmpwith" data-fid="card-cmp"${S.compare.length >= 3 && S.compare.includes(p.id) ? ' disabled' : ''}>Compare with…</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="highlights ${esc(p.name)}" title="Goals, shots, chances made, skills and defending in one reel">Highlights</button><button type="button" class="tx-mini" data-act="run" data-cmd="shots ${esc(p.name)}">Shots</button><button type="button" class="tx-mini" data-act="run" data-cmd="form ${esc(p.name)}">Form</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="team ${esc(p.club)}">Team</button></div>
      ${best}
      <h3 class="tx-h3" id="txSimHead" tabindex="-1">Plays like</h3>${sim}`;
    paint('plyr', html, esc(p.short_name));
  }
  // One metric row: label (definition on hover), value button (evidence), percentile bar.
  function mrow(p, m, opts = {}) {
    const c = cellOf(p, m.key);
    const val = c ? `<button type="button" class="tx-n${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(m.key)}" data-fid="${esc((opts.fid || 'm') + '-' + p.id + '-' + m.key)}" aria-label="${esc(`${m.label} ${withUnit(m, c.value)}, ${playTextC(m, c)}`)}">${esc(fmt(m, c.value))}</button>` : '<span class="tx-dim">–</span>';
    const pc = c ? c.percentile : null;
    return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(m.key)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${unitMark(m)}</th><td class="num">${val}</td>
      <td class="tx-pbar"><span class="tx-bar" data-g="${GROUP_COL[m.group] || '#ffcd28'}"><i data-w="${pc == null ? 0 : Math.max(2, pc)}"></i></span></td><td class="num tx-pc">${pc == null ? '–' : esc(pc)}</td></tr>`;
  }

  // ------------------------------------------------------------------ Radar: pizza (one player) or radar (compare)
  const polar = (cx, cy, r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)];
  function wedge(cx, cy, r0, r1, a0, a1) {
    const [x0, y0] = polar(cx, cy, r1, a0), [x1, y1] = polar(cx, cy, r1, a1), [x2, y2] = polar(cx, cy, r0, a1), [x3, y3] = polar(cx, cy, r0, a0);
    const f = (n) => n.toFixed(2);
    return `M${f(x0)},${f(y0)} A${r1},${r1} 0 0 1 ${f(x1)},${f(y1)} L${f(x2)},${f(y2)} A${r0},${r0} 0 0 0 ${f(x3)},${f(y3)} Z`;
  }
  // Short labels on the axes (the full name on hover); none is cut, since every short label fits in 18 characters.
  function axisLabels(keys, cx, cy, Rr) {
    const n = keys.length;
    return keys.map((k, i) => {
      const a = (i + 0.5) * 2 * Math.PI / n, [x, y] = polar(cx, cy, Rr + 10, a), s = Math.sin(a);
      const m = MK.get(k), lab = shortLabel(m), t = lab.length > 18 ? lab.slice(0, 17) + '…' : lab;
      return `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${s > 0.25 ? 'start' : s < -0.25 ? 'end' : 'middle'}" class="tx-axl"><title>${esc(m.label)}</title>${esc(t)}</text>`;
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
    const ctxText = players.length > 1 ? esc(`Comparing ${players.length}${outsider ? ` + ${lastName(outsider)}` : ''}`) : esc(`vs ${POSN[base.position]}`);
    if (waiting) { paint('radar', waitHtml(waiting, 'the percentiles'), ctxText); return; }
    const keys = (S.radar.tpl === 'all' ? CAT.default_columns.all : (CAT.default_columns[base.position] || CAT.default_columns.all)).filter(k => MK.has(k));
    const n = keys.length, cx = 180, cy = 158, Rr = 96, r0 = 14;
    let svg = '<svg viewBox="0 0 360 316" class="tx-svg tx-radar" aria-hidden="true">';
    for (const q of [25, 50, 75, 100]) svg += `<circle cx="${cx}" cy="${cy}" r="${(r0 + (Rr - r0) * q / 100).toFixed(1)}" class="tx-ring"/>`;
    let gaps = false, outsiderNote = '';
    const blank = [];      // compared players with no percentile at all on this template: not drawn, and the note says why
    const whyBlank = (p) => p.position !== base.position && keys.every(k => !MK.get(k).positions.includes(p.position))
      ? `${POSN[p.position]} are not scored on the ${POSN[base.position]}' stats`
      : (noPct(p, MK.get(keys[0]), cellOf(p, keys[0])) || { text: 'no percentile on these stats' }).text.replace(/^no percentile: /, '');
    if (players.length === 1) {
      keys.forEach((k, i) => {
        const a0 = i * 2 * Math.PI / n + 0.01, a1 = (i + 1) * 2 * Math.PI / n - 0.01, pc = pctOf(base, k), m = MK.get(k);
        const r1 = r0 + (Rr - r0) * (pc == null ? 0 : Math.max(3, pc)) / 100;
        svg += `<path d="${wedge(cx, cy, r0, Rr, a0, a1)}" class="tx-wbg"/>`;
        if (pc != null) svg += `<path d="${wedge(cx, cy, r0, r1, a0, a1)}" fill="${GROUP_COL[m.group] || '#ffcd28'}" fill-opacity="${m.higher_is_better === null ? 0.45 : 0.85}" class="tx-wedge" data-act="ev" data-pid="${esc(base.id)}" data-mk="${esc(k)}"><title>${esc(m.label)}: ${esc(fmt(m, cellOf(base, k).value))}, ${esc(ord(pc))} percentile</title></path>`;
        else gaps = true;
        // The value sits inside its wedge when the wedge has room (black on a solid wedge, white on a style marker's paler
        // one), else just outside it in light text on the dark ring: each choice is at least 4.5:1.
        const inside = r1 - r0 >= 18, [tx, ty] = polar(cx, cy, inside ? r1 - 9 : r1 + 9, (a0 + a1) / 2);
        const tone = !inside ? 'out' : m.higher_is_better === null ? 'lt' : '';
        svg += `<text x="${tx.toFixed(1)}" y="${(ty + 4).toFixed(1)}" text-anchor="middle" class="tx-wv ${tone}">${pc == null ? '–' : esc(pc)}</text>`;
      });
    } else {
      keys.forEach((k, i) => { const [x, y] = polar(cx, cy, Rr, (i + 0.5) * 2 * Math.PI / n); svg += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="tx-ring"/>`; });
      const ptsOf = (p) => keys.map((k, i) => { const pc = pctOf(p, k); return pc == null ? null : polar(cx, cy, r0 + (Rr - r0) * pc / 100, (i + 0.5) * 2 * Math.PI / n); });
      players.forEach((p, j) => {
        const pts = ptsOf(p);
        if (!pts.some(Boolean)) { blank.push(p); return; }
        if (pts.some(q => !q)) gaps = true;
        svg += outline(pts, `stroke="${CMP_COL[j]}" stroke-width="2"`, `fill="${CMP_COL[j]}" fill-opacity=".14"`);
      });
      // The selected player, when not one of the compared, is a dashed outline so selecting a player still moves the radar;
      // with no percentile on these stats at all (a keeper on a forward's stats), it is not drawn and the note says why.
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
    svg += axisLabels(keys, cx, cy, Rr) + '</svg>';
    const legend = players.map((p, j) => `<button type="button" class="tx-leg" data-c="${CMP_COL[players.length > 1 ? j : 0]}" data-act="sel" data-pid="${esc(p.id)}" data-fid="rl-${esc(p.id)}">${esc(p.name)} <span class="tx-dim">${esc(p.short_name)} ${esc(p.position)}</span></button>`).join('')
      + (outsider && !outsiderNote ? `<span class="tx-leg tx-legf">${esc(outsider.name)} <span class="tx-dim">${esc(outsider.short_name)} ${esc(outsider.position)} · selected, dashed</span></span>` : '');
    const outLine = outsider ? `<p class="tx-cap tx-rnote">${outsiderNote ? esc(outsiderNote) : `Comparing ${players.length}; ${esc(outsider.name)} (selected) is the dashed outline, not in the table.`} <button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(outsider.id)}" data-fid="r-add">Add to the comparison${players.length >= 3 ? ` (replaces ${esc(lastName(players[0]))})` : ''}</button></p>` : '';
    const tbl = players.length === 1 ? `<table class="tx-mt"><tbody>${keys.map(k => mrow(base, MK.get(k), { fid: 'r' })).join('')}</tbody></table>`
      : `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cmp"><thead><tr><th>Stat</th>${players.map((p, j) => `<th class="num" data-fg="${CMP_COL[j]}">${esc(initials(p))}</th>`).join('')}</tr></thead><tbody>
        ${keys.map(k => { const m = MK.get(k); return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(k)}">${esc(m.label)}${noisy(m)}</span>${unitMark(m)}</th>${players.map(p => { const c = cellOf(p, k); return `<td class="num">${c ? `<button type="button" class="tx-n${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="rc-${esc(p.id)}-${esc(k)}" aria-label="${esc(`${p.name}, ${m.label} ${withUnit(m, c.value)}, ${c.percentile == null ? (noPct(p, m, c) || { text: 'no percentile' }).text : ord(c.percentile) + ' percentile'}, ${playTextC(m, c)}`)}">${esc(fmt(m, c.value))}</button><span class="tx-pc"> ${c.percentile == null ? '–' : esc(c.percentile)}</span>` : '<span class="tx-dim">–</span>'}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div>`;
    const html = `<div class="tx-ctls"><div class="tx-seg" role="group" aria-label="Stats"><button type="button" data-act="rtpl" data-v="pos" aria-pressed="${S.radar.tpl === 'pos'}">${esc(POS1[base.position])} stats</button><button type="button" data-act="rtpl" data-v="all" aria-pressed="${S.radar.tpl === 'all'}">All-round</button></div></div>
      <div class="tx-legs">${legend}</div>${outLine}${blank.map(p => `<p class="tx-cap tx-rnote">${esc(`${p.name} has no outline: ${whyBlank(p)}. The table has the values.`)}</p>`).join('')}${svg}
      <p class="tx-cap">/90 = per 90 minutes. Percentile vs regular ${esc(players.length > 1 ? 'players in each one’s own position' : POSN[base.position])}${players.length > 1 ? '' : '; blue-grey wedges are style markers (ranked, not judged)'}.${gaps ? ` ${players.length > 1 ? 'A gap in an outline' : 'An empty wedge'} is a stat with no percentile for that player (the table and its tips say why), never the 0th.` : ''} Values play their moments.</p>${tbl}`;
    paint('radar', html, ctxText);
  }

  // ------------------------------------------------------------------ Shots and Touch map: pitch charts
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
    return `<span class="tx-stat"><span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${c ? `<button type="button" class="tx-n${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="${esc(fid + k)}" aria-label="${esc(`${m.label} ${withUnit(m, c.value)}, ${playTextC(m, c)}`)}">${esc(fmt(m, c.value))}</button>${c.total != null && m.kind !== 'total' && m.kind !== 'ratio' ? `<span class="tx-dim">${esc(c.total)} in total</span>` : ''}` : '<span class="tx-dim">–</span>'}</span>`;
  }
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
  function renderShot() {
    const p = PID.get(S.focus), fc = full(p.id, 'shot'), sc = shotsOf(p.id, 'shot');
    if (fc.st !== 'ok' || sc.st !== 'ok') { paint('shot', waitHtml(fc.st !== 'ok' ? fc : sc, `${p.name}'s shots`), esc(p.name)); return; }
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
    paint('shot', html, esc(`${p.name} · ${plural(shots.length, 'shot')}`));
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
    if (fc.st !== 'ok' || pc.st !== 'ok') { paint('heat', waitHtml(fc.st !== 'ok' ? fc : pc, `${p.name}'s touches`), esc(p.name)); return; }
    const hm = Array.isArray(pc.v.grid) ? pc.v.grid : [];
    const [cols, rows] = (CAT.pitch && CAT.pitch.heatmap_grid) || [12, 8], cw = 105 / cols, ch = 68 / rows;
    const flat = hm.flat().map(v => Number(v) || 0);
    const max = Math.max(1, ...flat), total = flat.reduce((a, b) => a + b, 0);
    let cells = '';
    hm.forEach((row, y) => (row || []).forEach((v0, x) => { const v = Number(v0) || 0; if (v) cells += `<rect x="${(x * cw).toFixed(2)}" y="${(y * ch).toFixed(2)}" width="${cw.toFixed(2)}" height="${ch.toFixed(2)}" fill="#ffcd28" fill-opacity="${(0.08 + 0.8 * v / max).toFixed(3)}"><title>${v} on-ball action${v === 1 ? '' : 's'}</title></rect>`; }));
    const EVN = { touch: 'touches', pass: 'passes', cross: 'crosses', carry: 'carries', take_on: 'take-ons', shot: 'shots', tackle: 'tackles', interception: 'interceptions', recovery: 'recoveries', clearance: 'clearances' };
    const evs = ((CAT.pitch && CAT.pitch.heatmap_events) || []).map(e => EVN[e] || words(e).toLowerCase());
    const html = `<div class="tx-stats">${['touches', 'touches_in_box', 'progressive_passes_received'].map(k => numBtn(p, k, 'ht-')).join('')}</div>
      <svg viewBox="-1.5 -1.5 108 71" class="tx-svg tx-pitchsvg" role="img" aria-label="Touch map: ${total} on-ball actions, attacking left to right"><rect x="0" y="0" width="105" height="68" class="tx-turf"/>${cells}${fullPitch()}<path d="M44,70 L61,70" class="tx-dir"/></svg>
      <p class="tx-cap">${esc(total)} on-ball actions in league matches this season (${esc(listText(evs))}), so more than the Touches count, which is touch records only. Attacking left to right, ${esc(cols)} by ${esc(rows)} cells. The map has no clip per cell; the numbers above play their moments.</p>`;
    paint('heat', html, esc(p.name));
  }

  // ------------------------------------------------------------------ Form: match by match
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
    const fc = formOf(p.id, [...defs, k], 'form'), full0 = full(p.id, 'form');
    if (fc.st !== 'ok') { paint('form', waitHtml(fc, `${p.name}'s matches`), esc(p.name)); return; }
    const fm = fc.v, matches = fm.matches || [];
    if (!matches.length) { paint('form', '<p class="tx-dim">No matches this season.</p>', esc(p.name)); return; }
    const fk = (fm.metrics || {})[k] || {}, vals = fk.values || [];
    // The dashed line is in the bars' unit: a season count (clean sheets, cards) is drawn as its average per match played,
    // never as the season total over bars that count one match each.
    const isTotal = m.kind === 'total';
    const sv = fk.season;
    const season = sv != null ? { value: isTotal ? sv / matches.length : sv } : null;
    const seasonLab = season ? (isTotal ? `season ${Number(season.value).toFixed(2)} a match (${fmt(m, sv)} in ${matches.length})` : `season ${fmt(m, season.value)}`) : '';
    // Drawn at the panel's own width (one unit = one pixel) so the labels stay at their CSS size; the scale always holds
    // zero, so negative values (xT added, goals minus xG, on-pitch differences) hang below a zero line inside the chart.
    const W2 = svgWidth('form', 300), H = 200, L = 40, B = 36, T = 16, n = matches.length, bw = (W2 - L - 8) / n;
    const nums = [...vals.filter(v => v != null).map(Number), ...(season && season.value != null ? [season.value] : [])];
    let lo = Math.min(0, ...nums), hi = Math.max(0, ...nums);
    if (lo === hi) hi = 1;
    const pad = (hi - lo) * 0.12; if (hi > 0) hi += pad; if (lo < 0) lo -= pad;
    const y = (v) => T + (H - T - B) * (hi - v) / (hi - lo), y0 = y(0);
    const tick = (v) => `<text x="${L - 4}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end" class="tx-axl">${esc(fmt(m, v))}</text>`;
    let svg = `<svg viewBox="0 0 ${W2} ${H}" width="${W2}" height="${H}" class="tx-svg tx-form" role="group" aria-label="${esc(m.label)} match by match; each bar plays that match's moments">`;
    svg += `<line x1="${L}" y1="${y0.toFixed(1)}" x2="${W2 - 4}" y2="${y0.toFixed(1)}" class="tx-ax"/>${tick(0)}`;
    if (Math.max(0, ...nums) > 0) svg += tick(Math.max(...nums));
    if (lo < 0) svg += tick(Math.min(...nums));
    matches.forEach((mm, i) => {
      const v = vals[i], x = L + i * bw + 2, w = Math.max(4, bw - 4), cx = (x + w / 2).toFixed(1);
      const lab = `Round ${mm.round} ${mm.home ? 'v' : 'at'} ${club(mm.opponent).name}, ${mm.score}, ${Math.round(mm.minutes)} min: ${m.label} ${fmt(m, v)}. Play that match's moments`;
      let bar = '';
      if (v == null) bar = `<text x="${cx}" y="${(y0 - 4).toFixed(1)}" text-anchor="middle" class="tx-axl">–</text>`;
      else {
        const yv = y(v), top = Math.min(yv, y0), h = Math.max(1, Math.abs(y0 - yv)), neg = v < 0;
        bar = `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${neg ? '#ff8a8a' : GROUP_COL[m.group] || '#ffcd28'}"/>`
          + (textW(fmt(m, v).replace('%', ''), 10) <= bw - 2 ? `<text x="${cx}" y="${(neg ? top + h + 12 : top - 4).toFixed(1)}" text-anchor="middle" class="tx-fv">${esc(fmt(m, v).replace('%', ''))}</text>` : '');
      }
      svg += `<g class="tx-fbar${v == null ? ' nil' : ''}" role="button" tabindex="0" data-act="fev" data-mid="${esc(mm.match_id)}" data-fid="fb-${i}" aria-label="${esc(lab)}"><rect x="${x.toFixed(1)}" y="${T}" width="${w.toFixed(1)}" height="${H - T - B}" class="tx-hit"/>${bar}`
        + `<text x="${cx}" y="${H - B + 15}" text-anchor="middle" class="tx-axl">R${esc(mm.round)}</text><text x="${cx}" y="${H - B + 29}" text-anchor="middle" class="tx-axl dim">${mm.home ? 'v' : 'at'} ${esc(short(mm.opponent))}</text><title>${esc(lab)}</title></g>`;
    });
    if (season && season.value != null) { const ys = y(season.value).toFixed(1); svg += `<line x1="${L}" y1="${ys}" x2="${W2 - 4}" y2="${ys}" class="tx-avg"/><text x="${W2 - 6}" y="${(season.value < 0 ? +ys + 13 : ys - 4)}" text-anchor="end" class="tx-avgl">${esc(seasonLab)}</text>`; }
    svg += '</svg>';
    const cellFor = (c) => full0.st === 'ok' ? cellOf(p, c) : null;
    const ctab = defs.filter(c => (fm.metrics || {})[c]).map(c => { const cm = MK.get(c), x = fm.metrics[c], tr = x.last3_minus_season, cc = cellFor(c);
      return `<tr${c === k ? ' class="on"' : ''}><th scope="row"><button type="button" class="tx-lk" data-act="formk" data-k="${esc(c)}" data-mk="${esc(c)}" data-fid="fk-${esc(c)}">${esc(cm.label)}${noisy(cm)}</button></th>
        <td class="num"><button type="button" class="tx-n${zcC(cc)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(c)}" data-fid="fm-${esc(c)}" aria-label="${esc(`${cm.label} mean ${fmt(cm, x.mean)}, ${playTextC(cm, cc)}`)}">${esc(fmt(cm, x.mean))}</button></td><td class="num">${x.sd == null ? '–' : esc(x.sd)}</td><td class="num">${x.cv == null ? '–' : esc(x.cv)}</td>
        <td class="num ${tr > 0 ? 'up' : tr < 0 ? 'dn' : ''}">${tr == null ? '–' : (tr > 0 ? '+' : '') + esc(tr)}</td></tr>`; }).join('');
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span class="sr">Stat</span><select data-r="formk" data-fid="form-k">${metricOptions(k)}</select></label>
        <span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}" tabindex="0">${esc(m.label)}${noisy(m)} <span class="tx-dim">ⓘ</span></span></div>${svg}
      <p class="tx-cap">${esc(FORM_UNIT[m.kind] || 'Each match')}. Bars play that match's moments, all of them.</p>
      ${ctab ? `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cons"><thead><tr><th>Consistency</th><th class="num">Mean</th><th class="num" title="Standard deviation across matches">SD</th><th class="num" title="Coefficient of variation: SD divided by the mean (lower is steadier)">CV</th><th class="num" title="The last three matches minus the season">Last 3 vs season</th></tr></thead><tbody>${ctab}</tbody></table></div>` : ''}`;
    paint('form', html, esc(`${p.name} · ${plural(matches.length, 'match')}`));
  }

  // ------------------------------------------------------------------ Scatter: one stat against another
  function scatPoints() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y);
    const c = scatOf(x, y, pos, 'scat');
    if (c.st !== 'ok') return null;
    const ok = (m, pct, p) => m.has_percentile ? pct != null : p.qualified;
    return (c.v.points || []).map(pt => ({ p: PID.get(pt.global_id) || { ...pt, id: pt.global_id },
      a: { value: pt.x, percentile: pt.x_percentile, evidence_total: pt.x_evidence_total }, b: { value: pt.y, percentile: pt.y_percentile, evidence_total: pt.y_evidence_total } }))
      .filter(o => o.a.value != null && o.b.value != null && o.p.minutes > 0 && (all || (ok(mx, o.a.percentile, o.p) && ok(my, o.b.percentile, o.p))))
      .sort((u, v) => u.a.value - v.a.value || u.b.value - v.b.value);
  }
  function renderScat() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y), pts = scatPoints();
    const ctxText = esc(`${shortLabel(mx)} against ${shortLabel(my)}`);
    if (!pts) { paint('scat', waitHtml(scatOf(x, y, pos, 'scat'), 'the scatter'), ctxText); return; }
    const W2 = svgWidth('scat', 300), H = Math.round(Math.min(340, Math.max(250, W2 * 0.62))), L = 48, B = 38, T = 14, Rm = 14;
    const xs = pts.map(o => o.a.value), ys = pts.map(o => o.b.value);
    const ext = (a) => { let lo = Math.min(...a), hi = Math.max(...a); if (!a.length) { lo = 0; hi = 1; } if (lo === hi) { lo -= 1; hi += 1; } const pad = (hi - lo) * 0.06; return [lo >= 0 ? Math.max(0, lo - pad) : lo - pad, hi + pad]; };
    const [x0, x1] = ext(xs), [y0, y1] = ext(ys);
    const sx = (v) => L + (W2 - L - Rm) * (v - x0) / (x1 - x0), sy = (v) => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
    const med = (a) => { if (!a.length) return null; const s = [...a].sort((p, q) => p - q), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
    const mxv = med(xs), myv = med(ys);
    if (scatCur != null && (scatCur < 0 || scatCur >= pts.length)) scatCur = null;
    const cur = scatCur != null ? pts[scatCur] : pts.find(o => o.p.id === S.focus) || null;
    let svg = `<svg viewBox="0 0 ${W2} ${H}" width="${W2}" height="${H}" class="tx-svg tx-scat" tabindex="0" data-fid="scat-svg" data-r="scat" role="group" aria-label="${esc(`Scatter, ${mx.label} against ${my.label}, ${pts.length} players. Arrow keys move between players, Enter selects`)}">`;
    svg += `<line x1="${L}" y1="${H - B}" x2="${W2 - Rm}" y2="${H - B}" class="tx-ax"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" class="tx-ax"/>`;
    for (const t of [0, 0.5, 1]) {
      const vx = x0 + (x1 - x0) * t, vy = y0 + (y1 - y0) * t;
      svg += `<text x="${sx(vx).toFixed(1)}" y="${H - B + 15}" text-anchor="${t === 0 ? 'start' : t === 1 ? 'end' : 'middle'}" class="tx-axl">${esc(fmt(mx, vx))}</text><text x="${L - 4}" y="${(sy(vy) + 3).toFixed(1)}" text-anchor="end" class="tx-axl">${esc(fmt(my, vy))}</text>`;
    }
    svg += `<text x="${(L + W2 - Rm) / 2}" y="${H - 4}" text-anchor="middle" class="tx-axt">${esc(mx.label)} →</text><text x="13" y="${(T + H - B) / 2}" text-anchor="middle" class="tx-axt" transform="rotate(-90 13 ${(T + H - B) / 2})">${esc(my.label)} →</text>`;
    if (mxv != null) svg += `<line x1="${sx(mxv).toFixed(1)}" y1="${T}" x2="${sx(mxv).toFixed(1)}" y2="${H - B}" class="tx-med"/><line x1="${L}" y1="${sy(myv).toFixed(1)}" x2="${W2 - Rm}" y2="${sy(myv).toFixed(1)}" class="tx-med"/>`;
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
        <span class="tx-ml" data-mk="${esc(x)}">${esc(mx.label)}</span><button type="button" class="tx-n${zcC(cur.a)}"${shade(mx, cur.a.percentile)} data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(x)}" data-fid="scat-x" aria-label="${esc(`${mx.label} ${withUnit(mx, cur.a.value)}, ${playTextC(mx, cur.a)}`)}">${esc(fmt(mx, cur.a.value))}</button>
        <span class="tx-ml" data-mk="${esc(y)}">${esc(my.label)}</span><button type="button" class="tx-n${zcC(cur.b)}"${shade(my, cur.b.percentile)} data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(y)}" data-fid="scat-y" aria-label="${esc(`${my.label} ${withUnit(my, cur.b.value)}, ${playTextC(my, cur.b)}`)}">${esc(fmt(my, cur.b.value))}</button></p>`
      : '<p class="tx-read tx-dim">The selected player is not on this chart (position, or not a regular). Arrow keys in the chart pick a player.</p>';
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span>X</span><select data-r="scx" data-fid="scat-xs">${metricOptions(x)}</select></label>
        <label class="tx-ctl"><span>Y</span><select data-r="scy" data-fid="scat-ys">${metricOptions(y)}</select></label>
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scpos" data-v="${v || ''}" aria-pressed="${pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-chk"><input type="checkbox" data-r="scall" data-fid="scat-all"${all ? ' checked' : ''}> Include non-regulars</label></div>${svg}${read}
      <p class="tx-cap">${pts.length} ${esc(pos ? POSN[pos] : 'players')}${all ? '' : ', regulars with a value on both'} · dashed lines = medians · click a dot to select</p>`;
    paint('scat', html, ctxText);
  }

  // ------------------------------------------------------------------ Team: team style
  // The shots behind a team's shot-based numbers (GET /api/teams/{club}/shots): 'for' is the club's own players,
  // 'against' their opponents in the club's matches.
  const TEAM_SHOTS = {
    xg_for: { side: 'for', v: 'xg' }, npxg_for: { side: 'for', v: 'xg', keep: (s) => !s.penalty }, penalty_xg: { side: 'for', v: 'xg', keep: (s) => s.penalty },
    xg_against: { side: 'against', v: 'xg' }, goals_for: { side: 'for', v: 'n', keep: (s) => s.outcome === 'goal' },
    goals_against: { side: 'against', v: 'n', keep: (s) => s.outcome === 'goal' }, shots_for: { side: 'for', v: 'n' }, shots_against: { side: 'against', v: 'n' },
  };
  // What a team number opens, when that is known without a request: { n, unit }, or null. Its shots once loaded (a
  // shot-based number with a season total of 0 opens nothing), its set-piece shots or its matches once the style is in.
  function teamCount(cid, tk) {
    const t = TEAMS.get(cid), v = t && t.values[tk], spec = TEAM_SHOTS[tk];
    if (!v) return null;
    if (spec) {
      if (v.total != null && Number(v.total) === 0) return { n: 0, unit: 'moment' };
      const c = C.get(`tshots|${cid}|${spec.side}`);
      return c && c.st === 'ok' ? { n: (c.v.shots || []).filter(s => !spec.keep || spec.keep(s)).length, unit: 'moment' } : null;
    }
    const st = C.get('style|' + cid);
    if (!st || st.st !== 'ok') return null;
    if (tk === 'set_piece_xg' || tk === 'set_piece_shots') return { n: ((st.v.evidence || {}).set_piece_xg || []).length, unit: 'moment' };
    return { n: (st.v.per_match || []).length, unit: 'match' };
  }
  function renderTeam() {
    const t = TEAMS.get(S.club), c = club(S.club), row = (SEASON.table || []).find(r => r.club_id === S.club) || {};
    if (!t) { paint('team', '<p class="tx-dim">No team.</p>'); return; }
    const vals = (k) => [...TEAMS.values()].map(x => x.values[k] && x.values[k].value).filter(v => v != null);
    const rows = (CAT.team_metrics || []).map(m => {
      const v = t.values[m.key]; if (!v) return '';
      const all = vals(m.key), lo = Math.min(...all), hi = Math.max(...all), w = hi === lo ? 50 : 4 + 92 * (v.value - lo) / (hi - lo);
      const mean = hi === lo ? 50 : 4 + 92 * (v.league_mean - lo) / (hi - lo);
      const judged = m.higher_is_better !== null, good = judged && v.rank <= 2, tc = teamCount(S.club, m.key), zero = !!tc && tc.n === 0;
      return `<tr><th scope="row"><span class="tx-ml" data-tk="${esc(m.key)}" data-cid="${esc(S.club)}">${esc(m.label)}</span>${m.kind === 'per90' ? '<span class="tx-dim tx-u"> /90</span>' : ''}</th>
        <td class="num"><button type="button" class="tx-n${zero ? ' z' : ''}" data-act="tev" data-cid="${esc(S.club)}" data-tk="${esc(m.key)}" data-fid="tv-${esc(m.key)}" aria-label="${esc(`${c.name}, ${m.label} ${fmt(m, v.value)}, rank ${v.rank} of ${v.of}. ${zero ? 'Nothing behind it to play' : 'Open what is behind it'}`)}">${esc(fmt(m, v.value))}</button></td>
        <td class="num ${good ? 'up' : ''}">${esc(v.rank)}/${esc(v.of)}</td><td class="num tx-dim">${esc(fmt(m, v.league_mean))}</td>
        <td class="tx-pbar"><span class="tx-range"><i data-l="${w.toFixed(1)}" class="${judged ? '' : 'style'}"></i><b data-l="${mean.toFixed(1)}"></b></span></td></tr>`;
    }).join('');
    const lowBest = (CAT.team_metrics || []).filter(m => m.higher_is_better === false).map(m => /^[A-Z][a-z]/.test(m.label) ? m.label[0].toLowerCase() + m.label.slice(1) : m.label);
    const squad = PLAYERS.filter(p => p.club_id === S.club).sort((a, b) => b.minutes - a.minutes);
    const unplayed = ((club(S.club).squad) || []).filter(s => !PID.has(s.global_id));
    const html = `<div class="tx-seg tx-clubs" role="group" aria-label="Club">${(SEASON.clubs || []).map(k => `<button type="button" data-act="club" data-cid="${esc(k.club_id)}" aria-pressed="${k.club_id === S.club}" title="${esc(k.name)}">${esc(k.short_name)}</button>`).join('')}</div>
      <p class="tx-name">${esc(c.name)} <span class="tx-dim">${esc(ord(row.position || 0))} · ${esc(row.points)} pts · ${esc(row.won)}-${esc(row.drawn)}-${esc(row.lost)} · ${esc(row.goals_for)}:${esc(row.goals_against)}</span></p>
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style</th><th class="num">Value</th><th class="num">Rank</th><th class="num">League avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div><h3 class="tx-h3">Squad by minutes</h3><ol class="tx-squad tx-scroll">${squad.map(p => `<li class="${p.id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-fid="sq-${esc(p.id)}">${esc(p.name)}</button><span class="tx-dim">${esc(p.position)} #${esc(p.kit_number)}</span><span class="num">${esc(Math.round(p.minutes))}′</span></li>`).join('')}${unplayed.map(s => `<li><span class="tx-dim">${esc(s.name)}</span><span class="tx-dim">${esc(s.position)} #${esc(s.kit_number)}</span><span class="num tx-dim">0′</span></li>`).join('')}</ol></div></div>
      <p class="tx-cap">Rank 1 = best${lowBest.length ? `: the lowest for ${esc(listText(lowBest))}` : ''}. Grey markers are style, ranked but not judged, and their rank 1 is the highest. The bar spans the league's clubs; the white tick is the league average. /90 = per 90 minutes; possession, PPDA and the other ratios are season values over every match (hover a name for its definition). Shot numbers (xG, goals, shots) play every shot behind them; the others list one value per match, without a clip.</p>`;
    paint('team', html, esc(c.short_name));
  }
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
    const g = gen;
    reelLoading(`${t.club} · ${m.label}`);
    const r = await teamReel(cid, tk);
    if (r) openReel(r, 0, g === gen);
  }

  const RENDER = { scrn: renderScrn, plyr: renderPlyr, radar: renderRadar, clips: renderClips, shot: renderShot, heat: renderHeat, form: renderForm, scat: renderScat, team: renderTeam };

  // ------------------------------------------------------------------ tooltips: definition and source, on hover and focus
  function tipHtml(el, compact) {
    const mk = el.dataset.mk, tk = el.dataset.tk;
    const m = mk ? MK.get(mk) : TK.get(tk); if (!m) return '';
    // Arrowing through the players table: a short tip (the column header holds the full definition) that reads the cell.
    if (compact) {
      const p = PID.get(el.dataset.pid), c = p && cellOf(p, mk); if (!c) return '';
      const np = noPct(p, m, c), n = countC(m, c);
      return `<p class="tt-h">${esc(m.label)}${m.noisy ? ' <span class="tt-w">≈ small sample</span>' : ''}</p><p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : ''} · ${c.percentile == null ? esc(np ? np.text : 'no percentile') : `${esc(ord(c.percentile))} percentile vs ${esc(POSN[p.position])}`}</p>${zeroC(c) ? '<p class="tt-s">No moments behind this number</p>' : n ? `<p class="tt-play">&#9654; ${esc(n)} · Enter plays them</p>` : '<p class="tt-play">&#9654; Enter plays its moments</p>'}<p class="tt-s">The column header has the definition</p>`;
    }
    const src = (m.sources || []).map(s => ((CAT.sources || {})[s] || {}).title || s).join('; ');
    const judge = m.higher_is_better === null ? 'Style marker: ranked, not judged' : m.higher_is_better ? 'Higher is better' : 'Lower is better';
    let h = `<p class="tt-h">${esc(m.label)}</p><p>${esc(m.definition)}</p>
      <p class="tt-s"><b>Rule</b> ${esc(m.rule)}${src ? ` · <b>Source</b> ${esc(src)}` : ''}</p><p class="tt-s">${esc(mk ? unitText(m) : m.unit)} · ${esc(judge)}${mk && m.positions ? ` · matters for ${esc(m.positions.join(' '))}` : ''}</p>`;
    if (mk && m.noisy) h += `<p class="tt-w">≈ Small sample, read with care: split-half r ${esc(m.reliability_r)} (below ${esc((CAT.season.reliability || {}).noise_r)}); one season cannot yet separate players in the same role.</p>`;
    if (mk && m.min_attempts) h += `<p class="tt-s">Percentile needs at least ${esc(m.min_attempts)}: ${esc(m.min_attempts_rule)}</p>`;
    const p = el.dataset.pid && PID.get(el.dataset.pid), c = p && mk ? cellOf(p, mk) : null;
    if (c) h += `<p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : c.total != null && m.kind !== 'total' ? ` (${esc(c.total)} in total)` : ''} · ${c.percentile == null ? esc((noPct(p, m, c) || { text: 'no percentile' }).text) : `${esc(ord(c.percentile))} percentile among regular ${esc(POSN[p.position])}`}</p>`;
    const tv = tk && el.dataset.cid ? TEAMS.get(el.dataset.cid) : null;
    if (tv && tv.values[tk]) h += `<p class="tt-p">Rank ${esc(tv.values[tk].rank)} of ${esc(tv.values[tk].of)} · league average ${esc(fmt(m, tv.values[tk].league_mean))}</p>`;
    // A clickable number says what it opens.
    if (el.classList.contains('tx-n')) {
      if (el.classList.contains('z')) return h + '<p class="tt-s">No moments behind this number</p>';
      let n = null;
      if (c) n = countC(m, c);
      else if (tv && tv.values[tk]) { const k = teamCount(el.dataset.cid, tk); if (k) n = plural(k.n, k.unit); }
      h += n ? `<p class="tt-play">&#9654; ${esc(n)} · click to play</p>` : '<p class="tt-play">&#9654; click to play what is behind it</p>';
    }
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

  // ------------------------------------------------------------------ the search box: running what it asks for
  const runBtn = (cmd, label) => `<button type="button" class="tx-mini" data-act="run" data-cmd="${esc(cmd)}">${esc(label || cmd)}</button>`;
  const cmdWord = (head) => COMMANDS[head] ? COMMANDS[head].word : '';
  const altsHtml = (alts, head) => alts && alts.length ? ` <span class="tx-dim">· also:</span> ${alts.slice(0, 6).map(p => runBtn(`${cmdWord(head) ? cmdWord(head) + ' ' : ''}${p.name}`, `${p.name} ${p.short_name}`)).join(' ')}` : '';
  function onePlayer(arg) {
    if (!arg.trim()) return { p: PID.get(S.focus), alts: [] };
    const r = W.resolvePlayer(arg);
    if (r.p) return r;
    out(`No player called "${arg}". Type part of a name; suggestions appear as you type.`, 'err');
    return null;
  }
  const posText = (pos) => pos ? POSN[pos] : 'players';
  const PANEL_CMD = { SIM: 'plyr', SHOT: 'shot', FORM: 'form', HEAT: 'heat', RDR: 'radar', PLYR: 'plyr' };
  async function run(text) {
    const t = String(text || '').trim().replace(/\s*<GO>$/i, '').replace(/[?!.]+$/, '').trim().slice(0, 200); if (!t) return;
    const g = ++gen;
    if (store.hist[store.hist.length - 1] !== t) { store.hist.push(t); if (store.hist.length > 50) store.hist.shift(); save(); }
    histAt = -1;
    const it = W.interpret(t);
    if (it.do === 'help') { openHelp(); out('Help is open. Escape closes it.'); return; }
    if (it.do === 'rank') return cmdRank(it.rest);
    if (it.do === 'rankKey') return cmdRank('', it.club, { m: MK.get(it.key), pos: it.pos });
    if (it.do === 'minutes') return rankMinutes(it.pos, it.club);
    if (it.do === 'cmp') return cmdCmp(it.rest);
    if (it.do === 'scat') return cmdScat(it.rest);
    if (it.do === 'team' || it.do === 'club') {
      const c = it.club || W.resolveClub(it.rest) || (it.rest ? null : club(S.club));
      if (!c || !c.club_id) { out(`No club called "${it.rest}". Clubs: ${(SEASON.clubs || []).map(x => x.name).join(', ')}.`, 'err'); return; }
      return team(c, `${c.name}: how they play, ranked across the league's clubs.`);
    }
    if (it.do === 'hl' || it.do === 'hlPlayer' || it.do === 'hlFocus') {
      const r = it.do === 'hl' ? onePlayer(it.rest) : it.do === 'hlPlayer' ? { p: it.p, alts: it.alts } : { p: PID.get(S.focus), alts: [] };
      if (r) return playHighlights(r.p, r.alts, g);
      return;
    }
    if (it.do === 'stat') return openStat(it.p, it.key, it.alts, g);
    if (it.do === 'many') {
      const ms = it.keys.map(k => MK.get(k)).filter(Boolean).slice(0, 6);
      const pw = (m) => it.pos && it.pos !== 'ALL' ? POSN[it.pos] : (gkOnly(m) && it.pos !== 'ALL' ? 'goalkeepers' : 'all');
      out('', 'err', `"${esc(t)}" could be ${it.keys.length} stats: ${ms.map(m => it.p ? runBtn(`${it.p.name} ${m.label}`, m.label) : runBtn(`rank ${pw(m)} ${m.key}`, m.label)).join(' ')}`);
      return;
    }
    if (it.do === 'panel') {
      const head = it.head;
      const r = it.p ? { p: it.p, alts: it.alts || [] } : onePlayer(it.rest); if (!r) return;
      const p = r.p;
      out(`${p.name}: loading…`);
      // What the panel draws loads first, so the status line and the panel are final before it is brought into view.
      const extra = head === 'SHOT' ? shotsOf(p.id) : head === 'FORM' ? formOf(p.id, [...(CAT.default_columns[p.position] || CAT.default_columns.all), S.form.k || ''].filter(Boolean)) : head === 'HEAT' ? heatOf(p.id) : null;
      await Promise.all([settle(full(p.id)), settle(similar(p.id)), extra ? settle(extra) : null]);
      if (g !== gen) return;  // a newer command or a picked player took over meanwhile
      select(p.id, true);
      await panelsSettled();
      if (g !== gen) return;
      let line;
      if (head === 'SIM') { const sm = similar(p.id).v; line = `Plays like ${p.name}: ${((sm && sm.similar) || []).map(s => `${s.name} ${Number(s.similarity).toFixed(2)}`).join(', ') || 'nobody yet (too few minutes)'}.`; }
      else if (head === 'SHOT') { const sh = (shotsOf(p.id).v || {}).shots || []; line = `${p.name}: ${plural(sh.length, 'shot')}, ${plural(sh.filter(s => s.outcome === 'goal').length, 'goal')}. Each shot plays its clip.`; }
      else if (head === 'FORM') line = `${p.name}: ${plural(p.appearances || 0, 'match')}. Each bar plays that match's moments.`;
      else if (head === 'HEAT') line = `${p.name}: where they have the ball in league matches, attacking left to right.`;
      else if (head === 'RDR') line = `${p.name}: percentiles against regular ${POSN[p.position]}.`;
      else line = `${p.name} · ${p.club}.`;
      out('', '', esc(line) + altsHtml(r.alts, head));
      showPanel(PANEL_CMD[head], true, head === 'SIM' ? '.tx-sim' : head === 'PLYR' ? '.tx-best' : null);
      return;
    }
    if (it.do === 'player') {
      const p = it.p;
      out(`${p.name}: loading…`);
      await Promise.all([settle(full(p.id)), settle(similar(p.id))]);
      if (g !== gen) return;
      select(p.id, true);
      await panelsSettled();
      if (g !== gen) return;
      out('', '', esc(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`) + altsHtml(it.alts, ''));
      // Bring the card and the player's numbers into view, not just the card's top strip.
      showPanel('plyr', true, '.tx-best');
      return;
    }
    out(`Nothing found for "${t}". Try a surname, a club, a stat such as "goals" or "most xG", "best finishers", "${lastName(PID.get(S.focus))} highlights" or "Toure vs Ustinov". Help lists everything.`, 'err');
    // Keep what was typed, selected, so a typo is one keystroke away from fixed.
    const inp = $('txIn');
    if (document.activeElement === inp && !inp.value) { inp.value = t; inp.select(); }
  }
  // "Toure goals": the moments behind that player's number, or, for a number with nothing behind it, the reason.
  async function openStat(p, k, alts, g) {
    const m = MK.get(k); if (!p || !m) return;
    out(`${p.name}: loading…`);
    await settle(full(p.id));
    if (g !== gen) return;
    select(p.id, true);
    const c = cellOf(p, k);
    if (zeroC(c)) { out('', '', esc(`${p.name}: ${m.label} ${c ? withUnit(m, c.value) : '–'}, so there are no moments to play.`) + altsHtml(alts, '')); return; }
    return openEvidence(p.id, k);
  }
  async function team(c, line) {
    const g = gen;
    S.club = c.club_id; save();
    if (!visible('team')) showPanel('team', false); else renderTeam();
    await panelsSettled();
    if (g !== gen) return;
    out(line);
    showPanel('team', true);
  }
  // A stat scored only for goalkeepers (save %, clean sheets) ranks the goalkeepers unless a position was named.
  const gkOnly = (m) => Array.isArray(m.positions) && m.positions.length === 1 && m.positions[0] === 'GK';
  function cmdRank(rest, cl, given) {
    let pos = null, m = null;
    if (given && given.m) { m = given.m; pos = given.pos || null; }
    else {
      const toks = rest.split(/\s+/).filter(Boolean);
      if (toks.length && posOf(toks[0])) pos = posOf(toks.shift());
      else if (toks.length > 1 && posOf(toks[toks.length - 1])) pos = posOf(toks.pop());
      if (toks.length > 1 && /^(by|on)$/i.test(toks[0])) toks.shift();      // rank forwards by goals
      const r = W.resolveMetric(toks.join(' '));
      if (!r.m) {
        if (r.many) out('', 'err', `"${esc(toks.join(' '))}" matches ${r.many.length} stats: ${r.many.slice(0, 6).map(x => runBtn(`rank ${pos && pos !== 'ALL' ? POSN[pos] : 'all'} ${x.key}`, x.label)).join(' ')}`);
        else out('Rank needs a stat: rank <position> <stat>, for example "rank forwards non-penalty xG". Suggestions appear as you type.', 'err');
        return;
      }
      m = r.m;
    }
    if (!pos && gkOnly(m)) pos = 'GK';
    const g = gen;
    S.scr.pos = pos === 'ALL' ? null : pos;
    // The ranked column goes first, so the order of the rows is explained by the first number the scout reads (at 375 px
    // only one stat column fits).
    S.scr.cols = [m.key, ...S.scr.cols.filter(k => k !== m.key)].slice(0, MAX_COLS);
    S.scr.sort = { k: m.key, dir: m.higher_is_better === false ? 1 : -1 };
    // A club filter ("best finishers at Brookfield") goes in the table's own filter box, where it shows and clears.
    S.scr.q = cl ? cl.name : ''; save();
    const finish = () => {
      if (g !== gen) return;    // a newer command or a picked player took over meanwhile
      const rows = screenRows(), ranks = screenRanks(rows);
      // The active cell is the leader's ranked number, so Alt+1 lands on rank 1 and the arrows walk down the ranking.
      scrAct = rows.length ? { pid: rows[0].id, c: 1 } : null;
      if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
      const tops = rows.filter((_, i) => ranks[i] === 1), c = tops[0] && cellOf(tops[0], m.key);
      const names = tops.length > 3 ? `${tops.slice(0, 3).map(p => p.name).join(', ')} and ${tops.length - 3} more` : tops.map(p => p.name).join(tops.length === 2 ? ' and ' : ', ');
      const nr = ranks.filter(x => x != null).length, un = rows.length - nr;
      // The line first, then the scroll: on a phone the line is in the page flow and pushes the table down.
      out(`${cap1(posText(S.scr.pos))}${cl ? ` at ${cl.name}` : ''} ranked by ${m.label}${m.higher_is_better === false ? ' (lowest first: lower is better)' : ''}: ${rows.length}${un ? `, ${nr} ranked (${un} ${S.scr.qual ? 'below the minimum attempts' : 'under the minutes or the minimum attempts'}, listed after)` : ''}${c ? `. Top: ${names}, ${withUnit(m, c.value)}${tops.length > 1 ? ', tied' : ''}` : ''}.`);
      showPanel('scrn', true, scrollTable(m.key));
    };
    if (ensureCols([m.key, ...S.scr.cols])) finish();
    else {
      out(`Ranking by ${m.label}: loading the column…`);
      if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
      const wait = () => { if (g !== gen) return; if (S.scr.cols.every(k => COLS.has(k) || !MK.has(k))) finish(); else if (colsErr) out(`The ${m.label} column did not load (${errText(colsErr)}).`, 'err'); else setTimeout(wait, 60); };
      wait();
    }
  }
  // The players table back to its top and left edge, with the sorted column in view; returns the row to scroll to.
  function scrollTable(key) {
    const tw = document.querySelector('#tx-p-scrn .tx-tablewrap');
    if (!tw) return null;
    tw.scrollLeft = 0; tw.scrollTop = 0;
    // On a phone the first stat column can still run past the table's edge: scroll the table, not the page, until the
    // ranked column shows whole.
    const th = key && tw.querySelector(`thead th [data-k="${CSS.escape(key)}"]`), cell = th && th.closest('th');
    if (cell) { const over = cell.getBoundingClientRect().right - tw.getBoundingClientRect().right; if (over > 0) tw.scrollLeft = over + 4; }
    const trs = tw.querySelectorAll('tbody[data-r="grid"] tr');
    return trs.length ? trs[Math.min(2, trs.length - 1)] : null;     // the first rows of the ranking, not just the box
  }
  // "most minutes": the table sorted by minutes played.
  function rankMinutes(pos, cl) {
    S.scr.pos = pos === 'ALL' ? null : pos || null;
    S.scr.sort = { k: 'min', dir: -1 }; S.scr.q = cl ? cl.name : ''; scrAct = null; save();
    if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
    const rows = screenRows();
    out(`${cap1(posText(S.scr.pos))}${cl ? ` at ${cl.name}` : ''} by minutes played: ${rows.length}${rows[0] ? `. Most: ${rows[0].name}, ${Math.round(rows[0].minutes)} minutes` : ''}.`);
    showPanel('scrn', true, scrollTable(null));
  }
  async function cmdCmp(rest) {
    const rs = W.resolvePlayers(rest);
    if (!rs.length) { out('Compare needs two or three players: compare <player> and <player>.', 'err'); return; }
    const bad = rs.find(r => !r.p);
    if (bad) { out(`No player called "${bad.q}".`, 'err'); return; }
    const ids = [...new Set(rs.map(r => r.p.id))].slice(0, 3);
    if (ids.length === 1 && ids[0] !== S.focus) ids.unshift(S.focus);
    if (ids.length < 2) { out('Compare needs two or three different players.', 'err'); return; }
    const g = gen;
    out('Comparing: loading…');
    await Promise.all(ids.map(id => settle(full(id))));
    if (g !== gen) return;
    S.compare = ids; S.focus = ids[0]; S.club = PID.get(ids[0]).club_id; save();
    renderAll();
    await panelsSettled();
    if (g !== gen) return;
    const amb = rs.filter(r => r.alts && r.alts.length);
    out('', '', esc(`Comparing ${listText(ids.map(id => PID.get(id).name))}: radar and table, each against their own position.`)
      + (amb.length ? ` <span class="tx-dim">"${esc(amb[0].q)}" could also be:</span> ${amb[0].alts.slice(0, 5).map(p => runBtn(`compare ${ids.map(id => id === amb[0].p.id ? p.name : PID.get(id).name).join(', ')}`, `${p.name} ${p.short_name}`)).join(' ')}` : ''));
    showPanel('radar');
  }
  const AGAINST = /^(against|vs|v|versus)$/i;
  async function cmdScat(rest) {
    const toks = rest.split(/\s+/).filter(Boolean);
    let pos;
    if (toks.length > 2 && posOf(toks[toks.length - 1])) { const p = posOf(toks.pop()); pos = p === 'ALL' ? null : p; }
    let mx = null, my = null;
    const ai = toks.findIndex(w => AGAINST.test(w));
    if (ai > 0) { const a = W.resolveMetric(toks.slice(0, ai).join(' ')), b = W.resolveMetric(toks.slice(ai + 1).join(' ')); if (a.m && b.m) { mx = a.m; my = b.m; } }
    const ts = toks.filter(w => !AGAINST.test(w));
    for (let k = 1; k < ts.length && !mx; k++) {
      const a = W.resolveMetric(ts.slice(0, k).join(' ')), b = W.resolveMetric(ts.slice(k).join(' '));
      if (a.m && b.m) { mx = a.m; my = b.m; }
    }
    if (!mx) { out('Plot needs two stats: plot <stat> against <stat> [position], for example "plot non-penalty xG against xA forwards". Stats autocomplete.', 'err'); return; }
    S.scat.x = mx.key; S.scat.y = my.key; if (pos !== undefined) S.scat.pos = pos; scatCur = null; save();
    const g = gen;
    out(`${mx.label} against ${my.label}: loading…`);
    await settle(scatOf(mx.key, my.key, S.scat.pos));
    if (g !== gen) return;
    if (!visible('scat')) showPanel('scat', false); else renderScat();
    await panelsSettled();
    if (g !== gen) return;
    const pts = scatPoints() || [];
    out(`${mx.label} against ${my.label}${S.scat.pos ? `, ${POSN[S.scat.pos]}` : ''}: ${plural(pts.length, 'player')}.`);
    showPanel('scat', true);
  }

  // ------------------------------------------------------------------ the search box: autocomplete and history
  function playerSugs(q, k, runIt, ctx) {
    const n = norm(q);
    const score = (p) => { const nm = norm(p.name), sn = surname(p); if (!n) return 0; if (sn.startsWith(n)) return 0; if (nm.startsWith(n)) return 1; if (nm.split(' ').some(w => w.startsWith(n))) return 2; if (n.length >= 3 && nm.includes(n)) return 3; return 9; };
    let ps;
    if (!n) { const f = PID.get(S.focus), sm = (C.get('sim|' + f.id) || {}).v; ps = [f, ...((sm && sm.similar) || []).map(s => PID.get(s.global_id)).filter(Boolean)]; }
    else {
      // Namesakes in the order a typed name would pick them (the selected player, who they play like, the table…).
      const hit = PLAYERS.filter(p => p.name && score(p) < 9), at = new Map(namesakeOrder(hit, ctx).map((p, i) => [p.id, i]));
      ps = hit.sort((a, b) => score(a) - score(b) || at.get(a.id) - at.get(b.id));
    }
    return ps.slice(0, 7).map(p => ({ kind: 'Player', text: p.name, detail: `${p.short_name} · ${p.position} · #${p.kit_number}`, insert: p.name, k, run: runIt }));
  }
  const groupLabel = (m) => ((CAT.groups || []).find(g => g.key === m.group) || {}).label || '';
  function metricSugs(q, k, runIt, prefix = '', pos = null, suffix = '') {
    const n = norm(q), kk = n.replace(/[\s-]+/g, '_');
    const score = (m) => { if (!n) return 0; const l = norm(m.label); if (l.startsWith(n)) return 0; if (m.key.startsWith(kk)) return 1; if (norm(shortLabel(m)).startsWith(n)) return 1; if (l.split(' ').some(w => w.startsWith(n))) return 2; if (m.key.includes(kk) || l.includes(n)) return 3; const ws = TW.loose(n).split(' ').filter(Boolean), mw = W.mwords(m); if (ws.length && ws.every(w => mw.some(x => x.startsWith(w)))) return 4; return 9; };
    const base = n ? METRICS : (CAT.default_columns[pos || PID.get(S.focus).position] || CAT.default_columns.all).map(x => MK.get(x)).filter(Boolean);
    return base.filter(m => score(m) < 9).sort((a, b) => score(a) - score(b)).slice(0, 8)
      .map(m => ({ kind: 'Stat', text: `${m.label}${m.noisy ? ' ≈' : ''}`, detail: groupLabel(m), insert: prefix + m.label + suffix, k, run: runIt, mk: m.key }));
  }
  const POS_SUG = (cur, runIt) => ['ALL', ...POS].filter(p => (p === 'ALL' ? 'all' : POSN[p]).startsWith(norm(cur)) || p.startsWith(cur.toUpperCase()))
    .map(p => ({ kind: 'Position', text: p === 'ALL' ? 'all' : POSN[p], detail: p === 'ALL' ? 'every position' : p, insert: p === 'ALL' ? 'all' : POSN[p], k: 1, run: runIt }));
  function suggest() {
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length);
    if (!before.trim()) { acItems = []; return paintAc(); }
    const toks = before.split(/\s+/), cur = toks[toks.length - 1], wordsIn = toks.filter(Boolean);
    const ph = TW.parseHead(before.replace(/^\s+/, '')), head = ph.head;
    const inArgs = ph.started && (COMMANDS[head] || head === 'PLYR');
    const args = ph.rest.split(/\s+/);            // the last is the word being typed ('' after a space)
    const clubs = SEASON.clubs || [];
    let s = [];
    const trailing = (fn) => { for (let k = Math.min(3, toks.length - 1); k >= 1; k--) { const q = toks.slice(-k).join(' ').trim(); const r = fn(q, k); if (r.length && q) return r; } return fn(cur, 1); };
    if (!inArgs) {
      if (toks.length === 1 || (wordsIn.length === 1 && !ph.started)) {
        const n = norm(cur);
        s.push(...Object.entries(COMMANDS).filter(([c, x]) => x.word.startsWith(n) || c.startsWith(cur.toUpperCase())).map(([c, x]) => ({ kind: 'Command', text: x.word, detail: x.args ? `${x.word} ${x.args}` : x.help, insert: x.word, k: 1, run: c === 'HELP' })));
        s.push(...playerSugs(cur, 1, true).slice(0, 5));
        s.push(...clubs.filter(c => norm(c.short_name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'Club', text: c.name, detail: 'how they play', insert: `team ${c.name}`, k: 1, run: true })));
        const fpos = POSN[PID.get(S.focus).position];
        s.push(...metricSugs(cur, 1, true, `rank ${fpos} `).slice(0, 3).map(x => ({ ...x, detail: `rank ${fpos}` })));
      } else s = playerSugs(wordsIn.join(' '), toks.length, true);
    } else if (['SIM', 'HL', 'SHOT', 'FORM', 'HEAT', 'RDR', 'PLYR'].includes(head)) s = playerSugs(args.join(' '), args.length, true);
    else if (head === 'CMP') {
      // Players already named before the last "," / "and" / "vs" are not suggested again (Compare with… names the selected one).
      const more = /,|\band\b|\bvs?\b/i.test(ph.rest), m = ph.rest.match(/^(.*)(,|\band\b|\bvs?\b)/i), named = m ? norm(m[1]) : '';
      const first = named ? W.resolvePlayers(m[1]).find(r => r.p) : null, ctx = first ? { p: first.p, pos: true } : undefined;
      s = trailing((q, k) => playerSugs(q, k, more, ctx).filter(x => !named || !named.includes(norm(x.text))));
    }
    else if (head === 'TEAM') { const n = norm(args.join(' ')); s = clubs.filter(c => !n || norm(c.short_name).startsWith(n) || norm(c.name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'Club', text: c.name, detail: c.short_name, insert: c.name, k: args.length, run: true })); }
    else if (head === 'RANK') {
      if (args.length === 1) s = [...POS_SUG(cur, false), ...metricSugs(cur, 1, true)];
      else { const p0 = posOf(args[0]), q = p0 ? args.slice(1) : args; s = metricSugs(q.join(' '), q.length, true, '', p0 === 'ALL' ? 'all' : p0); }
    } else if (head === 'SCAT') {
      const ai = args.slice(0, -1).findIndex(w => AGAINST.test(w));
      if (ai < 0) s = trailing((q, k) => metricSugs(q, k, false, '', null, ' against'));
      else {
        const after = args.slice(ai + 1), done = after.length > 1 && W.resolveMetric(after.slice(0, -1).join(' ')).m && cur === '';
        s = done ? POS_SUG(cur, true) : metricSugs(after.join(' '), after.length, true);
      }
    }
    acItems = s.slice(0, 9); acAt = -1;
    paintAc();
  }
  function paintAc() {
    const ul = $('txAc'), inp = $('txIn');
    if (!acItems.length) { ul.hidden = true; ul.innerHTML = ''; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); return; }
    ul.innerHTML = acItems.map((s, i) => `<li role="option" id="txAc-${i}" aria-selected="${i === acAt}" data-i="${i}"${s.mk ? ` data-mk="${esc(s.mk)}"` : ''}><span class="tx-ak k-${esc(s.kind.toLowerCase())}">${esc(s.kind)}</span><span class="tx-at">${esc(s.text)}</span><span class="tx-ad">${esc(s.detail)}</span></li>`).join('');
    ul.hidden = false; inp.setAttribute('aria-expanded', 'true');
    if (acAt >= 0) { inp.setAttribute('aria-activedescendant', 'txAc-' + acAt); const li = $('txAc-' + acAt); if (li) li.scrollIntoView({ block: 'nearest' }); } else inp.removeAttribute('aria-activedescendant');
  }
  function closeAc() { acItems = []; acAt = -1; paintAc(); }
  // Tab and a click take a suggestion into the box; Enter on a highlighted player, club or stat runs it.
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
    const srcs = Object.entries(CAT.sources || {}).map(([, s]) => `<li>${s.url && /^https:\/\//.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`).join('');
    const f = PID.get(S.focus), sm = (C.get('sim|' + f.id) || {}).v, like = sm && sm.similar && sm.similar[0];
    const ex = (c, x) => c === 'TEAM' ? `team ${club(S.club).name}` : x.ex;
    h.innerHTML = `<div class="tx-hhead"><h2 tabindex="-1" id="txHelpH">How to use the Scout terminal</h2><button type="button" class="tx-mini" data-act="helpclose" aria-label="Close help">Close &times;</button></div>
      <div class="tx-hbody"><p>Type in the search box and press Enter. Click any example to run it.</p><table class="tx-mt tx-htable"><tbody>
        <tr><th scope="row"><code>a name</code></th><td>Opens the player. ${runBtn(lastName(f))}</td></tr>
        <tr><th scope="row"><code>a club</code> or <code>a stat</code></th><td>A club opens how it plays; a stat ranks every player on it. ${runBtn('goals')}</td></tr>
        <tr><th scope="row"><code>a question</code></th><td>Plain words work too: best finishers, the most of any stat, a stat per 90, best finishers at a club, a player with a stat, a panel or "highlights", or two players with "vs". ${runBtn('who has the most xG?')} ${runBtn(`${lastName(f)} highlights`)} ${runBtn(`${lastName(f)} vs ${like ? String(like.name).split(' ').slice(-1)[0] : 'Ustinov'}`)}</td></tr>
        ${Object.entries(COMMANDS).filter(([c]) => c !== 'HELP').map(([c, x]) => `<tr><th scope="row"><code>${esc(x.word)}</code> <span class="tx-dim">${esc(x.args)}</span></th><td>${esc(x.help)} ${runBtn(ex(c, x))}</td></tr>`).join('')}
      </tbody></table>
      <p class="tx-dim">Short forms still work: ${Object.keys(COMMANDS).map(c => `<code>${esc(c)}</code>`).join(' ')} (for example <code>RANK FW npxg</code>).</p>
      <h3 class="tx-h3">Keys</h3><ul class="tx-keys">
        <li><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> goes to the search box</li><li><kbd>Enter</kbd> searches</li><li><kbd>↑</kbd> <kbd>↓</kbd> earlier searches, or move in the suggestions</li>
        <li><kbd>Tab</kbd> takes a suggestion</li><li><kbd>Esc</kbd> closes suggestions, help, tips and the clips drawer</li><li><kbd>Alt 1–9</kbd> jump to a panel, in the order of the panel buttons (each button's tooltip shows its key)</li>
        <li><kbd>Alt 1</kbd> (Players) goes straight into the players table: arrow keys, Home/End and PageUp/PageDown move, Enter plays the moments</li><li>In the scatter: arrow keys pick a player, Enter selects</li></ul>
      <h3 class="tx-h3">How the panels link</h3><p>One selected player and up to three compared players drive every panel. Selecting a player anywhere (a row in the table, a dot in the scatter, a similar player, the squad, a legend) updates the rest. Every underlined number plays every moment behind it in the clips drawer, each with its clip; physical numbers, consistency means and team-style ratios list one value per match, without a clip. Ranks, SD and CV open nothing.</p>
      <h3 class="tx-h3">The numbers</h3><p>${esc(CAT.note)}</p><p>${esc(plainSample((CAT.season.sample || {}).note))}</p><p><span class="tx-noisy">≈</span> small sample, read with care: the stat cannot yet tell players in the same role apart over one season.</p>
      <h3 class="tx-h3">Sources</h3><ul class="tx-srcs">${srcs}</ul></div>`;
    h.hidden = false; h._opener = opener || null;
    $('txHelpH').focus();
  }
  function closeHelp() { const h = $('txHelp'); if (h.hidden) return; h.hidden = true; if (/^Help is open/.test($('txOut').textContent)) out('Help closed.'); (h._opener && document.contains(h._opener) ? h._opener : $('txIn')).focus(); }

  // ------------------------------------------------------------------ events
  // Keyboard focus survives a repaint: after an action, if focus fell to <body> (the control was rebuilt or is gone), it
  // goes back to the same control (by data-fid, else by what it does), else to the nearest stable place: the panel's
  // heading, the selected player beside the search, or the current saved-layout button.
  const sig = (el) => el.dataset.fid ? `[data-fid="${CSS.escape(el.dataset.fid)}"]`
    : '[data-act="' + CSS.escape(el.dataset.act) + '"]' + ['id', 'pid', 'i', 'v', 'k', 'cid', 'd', 'mk', 'tk', 'mid', 'cmd'].filter(k => el.dataset[k] != null).map(k => `[data-${k}="${CSS.escape(el.dataset[k])}"]`).join('');
  function refocus(sel, pid, zid) {
    const a = document.activeElement;
    if (a && a !== document.body && document.contains(a)) return;
    // Look in the same place first (the player card and the selection both have "Compare with…" for the same player).
    const scope = (pid && $('tx-p-' + pid)) || (zid && $(zid)) || document.querySelector('.tx');
    const usable = (el) => el && !el.disabled && el.getClientRects().length;
    const tries = [() => [...scope.querySelectorAll(sel)].find(usable),
      () => pid && $('tx-h-' + pid),
      () => zid === 'txSel' && document.querySelector('#txSel .tx-focus'),
      () => zid === 'txMeta' && document.querySelector('#txMeta [data-act="ws"][aria-pressed="true"]'),
      () => zid === 'txKeys' && document.querySelector('#txKeys .tx-fkey'),
      () => zid === 'txNav' && document.querySelector('#txNav button'),
      () => $('txIn')];
    for (const f of tries) {
      const el = f();
      if (!usable(el)) continue;
      el.focus({ preventScroll: true });
      if (document.activeElement === el) return;
    }
  }
  function doAct(t, e) {
    const sel = sig(t), panel = t.closest('[data-txp]'), zone = t.closest('#txSel, #txMeta, #txKeys, #txHelp, #txOut, #txEx, #txNav, #txDrawer');
    const pid = panel && panel.dataset.txp, zid = zone && zone.id;
    // What a number was clicked from, so closing the clips drawer can bring focus back to it.
    actFrom = { el: t, sel, scope: pid ? 'tx-p-' + pid : zid };
    let r;
    try { r = act(t, e); } finally { actFrom = null; }
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
      const p = PID.get(pid), m = MK.get(t.dataset.mk);
      // Nothing behind a zero: say so on the status line instead of opening an empty drawer.
      if (t.classList.contains('z')) { const c = cellOf(p, m.key); out(`${p ? p.name : 'This player'}: ${m.label} ${c ? withUnit(m, c.value) : t.textContent}, so there are no moments to play.`); return null; }
      return openEvidence(pid, t.dataset.mk);
    }
    if (a === 'fev') { const p = PID.get(S.focus); return openEvidence(S.focus, formKey(p), t.dataset.mid); }
    if (a === 'tev') {
      if (!CLUBID.test(t.dataset.cid || '') || !KEY.test(t.dataset.tk || '')) return null;
      if (t.classList.contains('z')) { const tm = TK.get(t.dataset.tk), tt = TEAMS.get(t.dataset.cid); out(`${tt ? tt.club : 'This club'}: ${tm ? tm.label : 'this number'} ${t.textContent}, so there is nothing to play.`); return null; }
      return openTeamReel(t.dataset.cid, t.dataset.tk);
    }
    if (a === 'shot') { shotReel(PID.get(S.focus), +t.dataset.i); return null; }
    if (a === 'clip') { play(+t.dataset.i, true); return null; }
    if (a === 'cprev' || a === 'cnext') { if (!reel) return null; const d = a === 'cnext' ? 1 : -1; let i = reel.i + d; while (reel.items[i] && !reel.items[i].video) i += d; if (reel.items[i]) play(i, true); return null; }
    if (a === 'sort') { const k = t.dataset.k; S.scr.sort = S.scr.sort.k === k ? { k, dir: -S.scr.sort.dir } : { k, dir: k === 'name' || k === 'club' ? 1 : (MK.get(k) && MK.get(k).higher_is_better === false ? 1 : -1) }; save(); renderScrn(); return null; }
    if (a === 'rmcol') {
      const i = S.scr.cols.indexOf(t.dataset.k), wasSort = S.scr.sort.k === t.dataset.k;
      colMenuOpen = true; S.scr.cols = S.scr.cols.filter(k => k !== t.dataset.k); save(); renderScrn();
      if (wasSort && MK.has(t.dataset.k)) { const sm = MK.get(S.scr.sort.k); out(`Removed ${MK.get(t.dataset.k).label}; the table is now sorted by ${sm ? sm.label : 'minutes'}.`); }
      const xs = document.querySelectorAll('#tx-p-scrn [data-act="rmcol"]'), next = xs[Math.min(i, xs.length - 1)] || document.querySelector('#tx-p-scrn [data-r="addcol"]');
      if (next) next.focus({ preventScroll: true });
      return null;
    }
    if (a === 'scrpos') { S.scr.pos = POS.includes(t.dataset.v) ? t.dataset.v : null; scrAct = null; save(); renderScrn(); return null; }
    if (a === 'scrmode') { S.scr.mode = t.dataset.v === 'pct' ? 'pct' : 'val'; save(); renderScrn(); return null; }
    if (a === 'scrdef') { colMenuOpen = true; S.scr.cols = (CAT.default_columns[S.scr.pos || 'all'] || CAT.default_columns.all).filter(k => MK.has(k)); save(); renderScrn(); return null; }
    if (a === 'colsretry') { colsErr = null; renderScrn(); return null; }
    if (a === 'retry') { C.delete(t.dataset.key); renderAll(); return null; }
    if (a === 'reload') { load(); return null; }
    if (a === 'scpos') { S.scat.pos = POS.includes(t.dataset.v) ? t.dataset.v : null; scatCur = null; save(); renderScat(); return null; }
    if (a === 'rtpl') { S.radar.tpl = t.dataset.v === 'all' ? 'all' : 'pos'; save(); renderRadar(); return null; }
    if (a === 'formk') { if (MK.has(t.dataset.k)) { S.form.k = t.dataset.k; save(); renderForm(); } return null; }
    if (a === 'club') { if (CID.has(t.dataset.cid)) { S.club = t.dataset.cid; save(); renderTeam(); } return null; }
    if (a === 'cmpadd') { if (PID.has(pid)) { addCompare(pid); out(`Comparing ${listText(S.compare.map(id => PID.get(id).name))}.`); } return null; }
    if (a === 'cmpwith') { compareWith(); return null; }
    if (a === 'cmprm') { S.compare = S.compare.filter(id => id !== pid); save(); renderAll(); return null; }
    if (a === 'cmpclear') { S.compare = []; save(); renderAll(); return null; }
    if (a === 'pane') { showPanel(t.dataset.id); return null; }
    if (a === 'fkey') { goPanel(t.dataset.id, !!t.closest('#txNav')); return null; }
    if (a === 'dclose') { closeDrawer(); return null; }
    if (a === 'pclose') { const pp = S.panels.find(p => p.id === t.dataset.id); if (!pp) return null; pp.on = false; save(); renderLayout(); renderAll(); const k = document.querySelector(`.tx-fkey[data-id="${CSS.escape(t.dataset.id)}"]`); if (k) k.focus(); return null; }
    if (a === 'psize') {
      const pp = S.panels.find(p => p.id === t.dataset.id); if (!pp) return null;
      pp.size = SIZE_NEXT[pp.size] || 'S'; save(); renderLayout(); renderAll();
      const b = document.querySelector(`[data-act="psize"][data-id="${CSS.escape(pp.id)}"]`); if (b) b.focus();
      out(`${PANELS.find(x => x.id === pp.id).title}: ${SIZE_NAME[pp.size]}.`); return null;
    }
    if (a === 'pmove') {
      const i = S.panels.findIndex(p => p.id === t.dataset.id), d = +t.dataset.d;
      if (i < 0) return null;
      let j = i + d; while (S.panels[j] && !S.panels[j].on) j += d;
      if (!S.panels[j]) return null;
      const [pp] = S.panels.splice(i, 1); S.panels.splice(j, 0, pp); save(); renderLayout(); renderAll();
      // The same arrow keeps focus, unless the panel reached the end: then the other arrow.
      const b = document.querySelector(`[data-act="pmove"][data-id="${CSS.escape(pp.id)}"][data-d="${d}"]`), o = document.querySelector(`[data-act="pmove"][data-id="${CSS.escape(pp.id)}"][data-d="${-d}"]`);
      const to = b && !b.disabled ? b : o; if (to) to.focus(); return null;
    }
    // Phones: saved layouts and the small-sample note fold into "Layouts & notes".
    if (a === 'more') { const o = t.getAttribute('aria-expanded') !== 'true'; t.setAttribute('aria-expanded', String(o)); t.closest('.tx-line').classList.toggle('open', o); return null; }
    if (a === 'ws') { switchWs(+t.dataset.i); return null; }
    if (a === 'reset') { resetWs(); return null; }
    if (a === 'help') { openHelp(t); return null; }
    if (a === 'helpclose') { closeHelp(); return null; }
    // An example or a suggestion button runs its command. From help (which closes) focus goes to the search box; elsewhere
    // it stays on the button, so a phone does not pop up its keyboard.
    if (a === 'run') {
      const c = t.dataset.cmd, fromHelp = !$('txHelp').hidden && $('txHelp').contains(t);
      if (fromHelp) $('txHelp').hidden = true;
      $('txIn').value = ''; closeAc();
      const r = run(c);
      if (fromHelp) $('txIn').focus({ preventScroll: true });
      return r;
    }
    return null;
  }
  // A panel button (or Alt+digit) shows its panel and moves there; Players (Alt+1) goes straight into its table; Clips
  // opens and closes the drawer. From the phone's panel row, the panel's top always comes up under the row.
  function goPanel(id, fromNav) {
    if (id === 'clips') { if (drawerOpen()) closeDrawer(); else openDrawer(true); return; }
    showPanel(id, true, null, !!fromNav);
    if (fromNav) navCurrent(id);
    if (id === 'scrn' && focusGrid()) return;
    const h = $('tx-h-' + id); if (h) h.focus({ preventScroll: true });
  }
  function wire() {
    const root = document.querySelector('.tx');
    root.addEventListener('click', (e) => {
      const t = e.target.closest('[data-act]');
      if (!ready && !(t && t.dataset.act === 'reload')) return;
      // A click anywhere on a row of the players table (not on its name or a number) selects that player.
      if (!t) {
        const tr = e.target.closest('tbody[data-r="grid"] tr[data-row]');
        if (tr && GID.test(tr.dataset.row) && !e.target.closest('a, button, input, select, summary')) { scrAct = { pid: tr.dataset.row, c: 0 }; select(tr.dataset.row); }
        return;
      }
      if (!root.contains(t) || t.disabled) return;
      if (t.tagName === 'A') return;
      e.preventDefault(); doAct(t, e);
    });
    // The Columns menu stays open across repaints (its state is kept here) and closes on a click outside it.
    root.addEventListener('toggle', (e) => { if (e.target.classList && e.target.classList.contains('tx-menu')) colMenuOpen = e.target.open; }, true);
    document.addEventListener('click', (e) => {
      if (!colMenuOpen || e.target.closest('.tx-menu')) return;
      colMenuOpen = false; for (const m of document.querySelectorAll('.tx .tx-menu[open]')) m.open = false;
    });
    root.addEventListener('change', (e) => {
      const r = e.target.dataset.r; if (!r || !ready) return;
      if (r === 'addcol' && MK.has(e.target.value) && S.scr.cols.length < MAX_COLS) { colMenuOpen = true; S.scr.cols.push(e.target.value); save(); renderScrn(); const sel = document.querySelector('[data-fid="scr-add"]'); if (sel) sel.focus(); }
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
    // tooltips: on hover, and on keyboard focus (a mouse click that leaves focus on a number, or Close putting focus back
    // on it, shows none, so it never sits over the rows a scout reads next)
    window.addEventListener('keydown', () => { keyAt = Date.now(); }, true);
    window.addEventListener('pointerdown', () => { keyAt = 0; }, true);
    root.addEventListener('mouseover', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (ready && el && el !== tipFor && !el.closest('#txAc')) showTip(el); });
    root.addEventListener('mouseout', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && el === tipFor && !el.contains(e.relatedTarget) && document.activeElement !== el) hideTip(); });
    root.addEventListener('focusin', (e) => {
      const el = e.target.closest('[data-mk],[data-tk]');
      if (ready && el && !el.closest('#txAc') && Date.now() - keyAt < 1500) showTip(el, !!(el.dataset.pid && el.closest('tbody[data-r="grid"]'))); else if (!el || el !== tipFor) hideTip();
    });
    root.addEventListener('focusout', (e) => { if (tipFor && e.target === tipFor) hideTip(); });
    let navT = 0;
    window.addEventListener('scroll', () => {
      if (tipFor && document.activeElement !== tipFor) hideTip();
      if (!navT) navT = setTimeout(() => { navT = 0; if (ready && onTerminal()) navCurrent(); }, 80);
    }, { passive: true });
    // the search box
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
        // later) and focus at once, so the keys typed straight after Cmd+K land in the search box.
        location.hash = 'terminal';
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        inp.focus();
        return;
      }
      if (!onTerminal() || !ready) return;
      // Escape closes one thing at a time: help, the Columns menu, the suggestions, then the clips drawer.
      if (e.key === 'Escape') {
        hideTip();
        if (!$('txHelp').hidden) { closeHelp(); return; }
        const menu = document.querySelector('.tx .tx-menu[open]');
        if (menu) { const back = menu.contains(document.activeElement); colMenuOpen = false; menu.open = false; if (back) menu.querySelector('summary').focus(); return; }
        if (acItems.length) { closeAc(); return; }
        if (drawerOpen()) { closeDrawer(); return; }
      }
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
  // Form and Scatter are drawn at their panel's width: redraw them when it changes; the wide layout re-balances.
  let lastW = window.innerWidth, resizeT = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      if (!ready || !onTerminal()) return;
      navCurrent(); fitTall();
      if (window.innerWidth === lastW) return;
      lastW = window.innerWidth; if (visible('form')) renderForm(); if (visible('scat')) renderScat();
    }, 150);
  });
  // Forget what is playing and close the drawer (a reset of the saved layouts).
  function forgetReel() { reel = null; stopVideo(''); renderClips(); if (drawerOpen()) closeDrawer(); }
  // Another tab of this browser changed the saved layouts (or Reset this demo cleared them): read them again.
  // When the key is gone (Reset this demo removes it), readStore() starts again from the defaults and forgets the history.
  R.store.watch((k) => {
    if (!ready || (k !== null && k !== STORE_KEY)) return;
    if (k === null) R.store.remove(STORE_KEY);   // storage cleared everywhere: forget the in-memory copy too
    readStore();
    if (!R.store.get(STORE_KEY, null)) { histAt = -1; histDraft = ''; scatCur = null; scrAct = null; forgetReel(); }
    paintMeta(); if (onTerminal()) { renderLayout(); renderAll(); }
  });
  // "Reset this demo" in Settings, in this tab: Regista.demo.reset() has just cleared the store (scout.js's listener runs
  // first), but the storage event only reaches other tabs. Forget the layouts and the history held in memory too, and
  // drop a pending save, or the next save would write the old ones back.
  const resetBtn = $('stReset');
  if (resetBtn) resetBtn.addEventListener('click', () => {
    clearTimeout(saveT);
    store = { cur: 0, ws: [null, null, null], hist: [] };
    histAt = -1; histDraft = ''; scatCur = null; scrAct = null;
    if (!ready) { reel = null; return; }
    readStore(); paintMeta(); forgetReel(); renderLayout(); renderAll();
  });
  window.addEventListener('hashchange', onRoute);
  onRoute();
})();
