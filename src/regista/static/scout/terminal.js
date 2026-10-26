// The Scout terminal: the Terminal section of /scout (#terminal), ported from the sandbox design Zaid approved
// (ux/sandbox, sandbox/terminal.js: its "intuitive" round, then its catalogue round). A search box on top (a name, a club,
// a stat, a place or level such as "U19 midfielders in Spain", "women forwards", "players in Nigeria", "my level", a plain
// command such as "rank forwards goals", "compare Toure and Ustinov", "plot npxG against xA", "similar to Toure", or a
// plain question such as "who has the most xG?"; the old mnemonics RANK, CMP, SCAT, SIM, HL, SHOT, FORM, HEAT, RDR, TEAM and
// HELP still work; terminal-place.js reads the place words, terminal-words.js the rest) over linked panels: players table,
// player card, radar vs the player's pool, shots, touch map, form, scatter and team. Selecting a player in any panel
// updates the others; every underlined number plays the moments behind it, all of them (the API's evidence, paged until
// complete), in the clips drawer (a bottom sheet on phones).
//
// THE CATALOGUE: 14 competitions in 10 countries, one row per player and competition (a player with one competition keeps
// their global id as the row id; a career player's rows are "<global id>~<competition>"). Percentiles are within each
// player's level by default (the same tier, age group and gender), or their competition, or all levels of their gender.
// The browser never ranks: the order, the places, the lists per level or gender, and "none yet" come from the engine
// (GET /api/catalogue/players with the table's sort, the same rule as /api/catalogue/rank); the table only moves the rows
// the engine left without a place after the ranked ones, as /api/catalogue/rank lists them.
//
// LIVE, from the API, read only: the catalogue (/api/catalogue, /api/catalogue/matches, the players' directory and the
// table from /api/catalogue/players), the metric definitions (/api/metrics), one player's every metric in their
// competition (/api/players/{id}/metrics?competition=&scope=), the evidence behind a number (?evidence=KEY&evidence_offset=N),
// form, similar players, shots and the touch grid (each with competition=), the scatter (/api/terminal/scatter, one level
// at a time), compare (/api/catalogue/compare: its warning and best marks), team style (/api/teams, a catalogue club with
// competition=, and /api/competitions/{id} for its uploaded matches' record and squad), the league (/api/season). The
// terminal writes nothing to the server.
// PER VISITOR, in this browser only: three saved layouts (panels, players, columns, axes, filters and the percentile scope)
// and the search history, through Regista.store (shared/regista.js), never storage directly; "Reset layout" puts the
// current one back to the default.
//
// Plain script on window.Regista, loaded after scout.js, terminal-place.js and terminal-words.js. The page runs under a
// Content Security Policy: no inline handlers and no style attributes in markup, so shading, colours and widths are data
// attributes applied through element.style after rendering (styleUp). Every API value that reaches innerHTML goes through
// esc(). Everything shown is synthetic: invented players, clubs and competitions; countries and levels are labels.
(function () {
  'use strict';
  const R = window.Regista;
  const esc = R.esc;
  const PV = R.profileView;
  const TW = R.terminalWords;
  const TP = R.terminalPlace;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  if (!$('txForm') || !TW || !TP) return;

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
  const ROW = /^pl_[a-z0-9_]{1,40}(?:~co_[a-z0-9_]{1,40})?$/;   // a table row: a global id, or "<global id>~<competition>"
  const COMPID = /^co_[a-z0-9_]{1,40}$/;
  const CLUBID = /^cl_[a-z0-9_]{1,40}$/;
  const KEY = /^[a-z0-9_]{1,40}$/;
  const HEX = /^#[0-9a-f]{6}$/i;
  const VIDEO = /^\/api\/[A-Za-z0-9_./?=&%-]+$/;     // video urls from the API are relative; anything else is not played
  const COLS_PER_CALL = 16;                          // what /api/catalogue/players takes in one call
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
  const VER = 4;                     // saved layouts: v2 kept Clips in the grid; v3 opens it as a drawer; v4 adds the filters
                                     // (where) and the percentile scope (clean() migrates: v2 and v3 open on My level)
  const ENG = 'co_eng_sp_men';       // the Regista League: every league fixture is uploaded
  const SCOUT_CLUB = 'cl_fairhaven'; // Maya Lindqvist's club: "My level" is its level (semi-pro men)
  const SCOPES = ['level', 'competition', 'all'];
  const SCOPE_WORD = { level: 'level', competition: 'competition', all: 'all levels' };
  const W_FIELDS = [['country', 'Country'], ['tier', 'Level'], ['age_group', 'Age group'], ['gender', 'Gender'], ['competition', 'Competition']];
  const TIER_WORD = { semi_pro: 'semi-pro', amateur: 'amateur', college: 'college', academy: 'academy' };
  // The engine's pool rules (regista.catalogue.metrics FLOOR, MIN_POOL, SMALL_POOL; the cells' pools carry them too).
  const FLOOR = 45, MIN_POOL = 5, SMALL_POOL = 15;

  // ------------------------------------------------------------------ the data, from the API
  let CAT = null, SEASON = null, TEAMS_ALL = null, IX = null, V = null, METRICS = [];
  let loading = false, ready = false, wantFocus = false;
  const MK = new Map(), TK = new Map(), PID = new Map(), CID = new Map(), TEAMS = new Map(), MATCH = new Map();
  // The catalogue: competitions, levels (pools: key "semi_pro/senior/men" -> words "semi-pro men"), a player's number of
  // rows and first row by global id, the counts that read "none yet" at 0, the countries in the catalogue's order.
  const COMP = new Map(), LVL = new Map(), GIDN = new Map(), GID1 = new Map(), COUNT = new Set(), STORY = new Map();
  const QMIN = new Map();   // competition id -> its qualifying minutes (the directory read)
  let COUNTRIES = [], MINE = { tier: 'semi_pro', age_group: 'senior', gender: 'men' }, MINE_CLUB = 'Fairhaven FC';
  let PLAYERS = [];
  // Cells per percentile scope: "<scope>|<row id>" -> { metric key: cell } (table columns, and every metric once loaded).
  const CELLS = new Map();
  const colsPending = new Set();     // table requests in flight (the order and its extra columns), for panelsSettled
  const C = new Map();               // request cache: key -> { st: wait | ok | err, v, e, p }
  let store = { cur: 0, ws: [null, null, null], hist: [] }, S = null, storageOK = true, saveT = 0;
  let reel = null, histAt = -1, histDraft = '', acItems = [], acAt = -1, scatCur = null, scrAct = null, tipFor = null;
  let colMenuOpen = false, whereMenuOpen = false, actFrom = null, drawerFrom = null, keyAt = 0;

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

  // A row's id: the global id, or "<global id>~<competition>" for a player with rows in two competitions (so a link or a
  // saved layout from before the catalogue keeps working for everyone else).
  const rowIdOf = (gid, cid) => (GIDN.get(gid) || 0) > 1 ? `${gid}~${cid}` : gid;
  const levelKey = (x) => `${x.tier}/${x.age_group}/${x.gender}`;
  // Rows from the catalogue API (one per player and competition), with their cells for the scope they were asked in.
  function addRow(r, scope) {
    if (!r || !GID.test(String(r.global_id || '')) || !COMPID.test(String(r.competition_id || ''))) return null;
    const id = rowIdOf(r.global_id, r.competition_id);
    let p = PID.get(id);
    if (!p) { p = { id, gid: r.global_id, cid: r.competition_id }; PID.set(id, p); PLAYERS.push(p); if (!GID1.has(p.gid)) GID1.set(p.gid, id); }
    for (const k of ['name', 'club_id', 'club', 'short_name', 'kit', 'kit_number', 'position', 'role', 'age', 'height_cm',
      'preferred_foot', 'nationality', 'minutes', 'appearances', 'qualified', 'profile_url', 'competition', 'country', 'tier',
      'age_group', 'gender', 'career', 'also_in']) if (r[k] !== undefined) p[k] = r[k];
    p.level = levelKey(p); p.comp = COMP.get(p.cid) || { competition_id: p.cid, name: p.competition || p.cid, country: p.country };
    if (r.values && scope) { const key = `${scope}|${id}`, cs = CELLS.get(key) || {}; Object.assign(cs, r.values); CELLS.set(key, cs); }
    return id;
  }
  // Every player row of the catalogue, once, in one read: names for the search, row ids and playing time (no metric
  // cells: the table and the card ask for those).
  async function directory() {
    const j = await R.api('/api/catalogue/directory');
    const all = j.players || [];
    for (const [cid, q] of Object.entries(j.qualifying_minutes || {})) if (COMPID.test(cid) && typeof q === 'number') QMIN.set(cid, q);
    for (const r of all) GIDN.set(r.global_id, (GIDN.get(r.global_id) || 0) + 1);
    for (const r of all) addRow(r, 'level');
  }

  // ------------------------------------------------------------------ the players table, from the engine
  // The table asks the engine for its rows in order: the filters (where), the percentile scope, the position, regulars
  // only (the engine's own qualifying minutes per competition) or everyone, and the sort. The same call brings the first
  // 16 columns; more columns come in more calls with the same filters. Each call is paged (200 rows) until complete.
  const whereQS = (w) => W_FIELDS.map(([k]) => k).filter(k => w && w[k]).map(k => `${k}=${enc(w[k])}`).join('&');
  function tableBase() {
    const q = [whereQS(S.scr.where), `scope=${enc(S.scope)}`];
    if (S.scr.pos) q.push(`position=${enc(S.scr.pos)}`);
    if (!S.scr.qual) q.push('min_minutes=0');
    return q.filter(Boolean).join('&');
  }
  // The engine's sort for the table's: a metric (best first unless the other way was asked), minutes, or the name (a club
  // sort is the names list, put in club order here: an order, not a ranking).
  function sortParams() {
    const k = S.scr.sort.k, dir = S.scr.sort.dir;
    if (k === 'name') return { sort: 'name', order: dir === -1 ? 'desc' : null };
    if (k === 'club') return { sort: 'name', order: null };
    if (k === 'min') return { sort: 'minutes', order: dir === 1 ? 'asc' : null };
    const m = MK.get(k), best = m && m.higher_is_better === false ? 1 : -1;
    return { sort: k, order: dir === best ? null : (dir === -1 ? 'desc' : 'asc') };
  }
  async function pages(url, scope, each) {
    let first = null;
    for (let offset = 0, total = Infinity; offset < total;) {
      const j = await R.api(`${url}&limit=${SCREEN_PAGE}&offset=${offset}`);
      if (!first) first = j;
      for (const r of j.players || []) { const id = addRow(r, scope); if (id && each) each(id, r); }
      total = j.total;
      if (!(j.players || []).length) break;
      offset += j.players.length;
    }
    return first || {};
  }
  function tracked(key, fn) { colsPending.add(key); return fn().finally(() => colsPending.delete(key)); }
  // What the table needs now: the order (with the first columns) and the cells of any further columns.
  function tableData(cols) {
    const base = tableBase(), sp = sortParams(), scope = S.scope;
    const first = [...new Set([...(MK.has(sp.sort) ? [sp.sort] : []), ...cols])].slice(0, COLS_PER_CALL);
    const okey = `ord|${base}|${sp.sort}|${sp.order || ''}`;
    const ord = want(okey, () => tracked(okey, async () => {
      const o = { ids: [], rank: new Map(), board: new Map(), keys: new Set(first) };
      const j = await pages(`/api/catalogue/players?${base}&sort=${enc(sp.sort)}${sp.order ? `&order=${sp.order}` : ''}&metrics=${first.map(enc).join(',')}`,
        scope, (id, r) => { o.ids.push(id); o.rank.set(id, r.rank); o.board.set(id, r.board); });
      return Object.assign(o, { boards: j.boards || null, rank_by: j.rank_by || null, warning: j.warning || null, competitions: j.competitions || [] });
    }), 'scrn');
    const rest = cols.filter(k => MK.has(k) && !first.includes(k)), extra = [];
    for (let i = 0; i < rest.length; i += COLS_PER_CALL) {
      const chunk = rest.slice(i, i + COLS_PER_CALL), ckey = `cells|${base}|${chunk.join(',')}`;
      extra.push(want(ckey, () => tracked(ckey, () => pages(`/api/catalogue/players?${base}&sort=name&metrics=${chunk.map(enc).join(',')}`, scope)), 'scrn'));
    }
    return { ord, extra };
  }

  // One player's every metric in their competition and the scope shown (the cells, each with how many moments are behind
  // it: `moments` counts each event once, as the drawer lists it, where `total` counts a ratio's pass and its completion
  // twice), merged into the table of cells; the competition's own minimum attempts come with it.
  const rowQ = (p, scope) => `competition=${enc(p.cid)}${scope ? `&scope=${enc(scope)}` : ''}`;
  const fullKey = (pid) => `full|${S.scope}|${pid}`;
  const fullFn = (pid, scope) => () => { const p = PID.get(pid); return R.api(`/api/players/${enc(p.gid)}/metrics?${rowQ(p, scope)}&evidence_limit=0`).then(j => {
    const key = `${scope}|${pid}`, cs = CELLS.get(key) || {};
    for (const [k, c] of Object.entries(j.metrics || {})) { const { evidence, ...cell } = c; cs[k] = { ...cell, evidence_total: evidence ? (evidence.moments ?? evidence.total) : null }; }
    CELLS.set(key, cs);
    const { metrics, catalogue, season, ...info } = j; addRow({ ...info, competition_id: p.cid });
    p.desc = catalogue || p.desc || {};
    return true;
  }); };
  const full = (pid, panel) => want(fullKey(pid), fullFn(pid, S.scope), panel);
  const similar = (pid, panel) => { const p = PID.get(pid); return want(`sim|${S.scope}|${pid}`, () => R.api(`/api/players/${enc(p.gid)}/similar?${rowQ(p, S.scope)}`).then(j => {
    for (const s of j.similar || []) { addRow(s); s.row = rowIdOf(s.global_id, s.competition_id); }
    return j;
  }), panel); };
  const shotsOf = (pid, panel) => { const p = PID.get(pid); return want('shots|' + pid, () => R.api(`/api/players/${enc(p.gid)}/shots?${rowQ(p)}`), panel); };
  // The touch map's grid counts the competition's own matches only, like every other terminal number (the league
  // fixtures in England; the profile's league grid adds uploads).
  const heatOf = (pid, panel) => { const p = PID.get(pid); return want('heat|' + pid, () => R.api(`/api/players/${enc(p.gid)}/heatmap?${rowQ(p)}`), panel); };
  function formOf(pid, keys, panel) {
    const p = PID.get(pid), ks = [...new Set(keys)].filter(k => MK.has(k)).slice(0, COLS_PER_CALL);
    return want(`form|${S.scope}|${pid}|${ks.join(',')}`, () => R.api(`/api/players/${enc(p.gid)}/form?metrics=${ks.map(enc).join(',')}&${rowQ(p, S.scope)}`), panel);
  }
  // The scatter: one level at a time (raw numbers compare only within a level), inside the table's country or competition.
  function scatOf(x, y, pos, lv, panel) {
    const l = LVL.get(lv) || {}, w = S.scr.where || {};
    const q = [`x=${enc(x)}`, `y=${enc(y)}`, 'min_minutes=0', `scope=${enc(S.scope)}`, pos ? `position=${enc(pos)}` : '',
      l.tier ? `tier=${enc(l.tier)}&age_group=${enc(l.age_group)}&gender=${enc(l.gender)}` : '',
      w.country ? `country=${enc(w.country)}` : '', w.competition ? `competition=${enc(w.competition)}` : ''].filter(Boolean).join('&');
    return want(`scat|${q}`, () => R.api(`/api/terminal/scatter?${q}`).then(j => { for (const pt of j.points || []) addRow(pt); return j; }), panel);
  }
  // A club's competition for the team endpoints: none for the Regista League's clubs (the league's own answers), else its
  // catalogue competition.
  const teamComp = (cid) => TEAMS.has(cid) ? null : (club(cid).competition_id || null);
  const cq = (comp, pre = '?') => comp ? `${pre}competition=${enc(comp)}` : '';
  const styleOf = (cid, panel) => { const comp = teamComp(cid); return want(`style|${cid}`, () => R.api(`/api/teams/${enc(cid)}/style${cq(comp)}`), panel); };
  const teamShotsOf = (cid, side) => { const comp = teamComp(cid); return fetchOnce(`tshots|${cid}|${side}`, () => R.api(`/api/teams/${enc(cid)}/shots?side=${enc(side)}${cq(comp, '&')}`)); };
  const teamsIn = (comp, panel) => want(`teams|${comp}`, () => R.api(`/api/teams?competition=${enc(comp)}`), panel);
  const compOf = (comp, panel) => want(`comp|${comp}`, () => R.api(`/api/competitions/${enc(comp)}`), panel);
  // Every moment behind one number: the API pages its evidence (500 a page); read page after page until all are in.
  const evidenceOf = (pid, mk) => fetchOnce(`ev|${pid}|${mk}`, async () => {
    const p = PID.get(pid);
    let offset = 0, out = null;
    for (;;) {
      const j = await R.api(`/api/players/${enc(p.gid)}/metrics?evidence=${enc(mk)}&${rowQ(p)}&evidence_limit=${EVIDENCE_PAGE}&evidence_offset=${offset}`);
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
  // the players table as it stands, then one at the selected player's level, then the most minutes. The other namesakes
  // are offered beside the answer.
  function namesakeOrder(hits, ctx = {}) {
    const cp = ctx.p || (S && PID.get(S.focus)), sm = cp && S && (C.get(`sim|${S.scope}|${cp.id}`) || {}).v;
    const sim = new Set(((sm && sm.similar) || []).map(s => s.row));
    let table = null;
    const inTable = (p) => { if (!table) table = new Set(S ? screenRows().map(x => x.id) : []); return table.has(p.id); };
    const key = (p) => [!ctx.pos && cp && p.id === cp.id ? 0 : 1, sim.has(p.id) ? 0 : 1, ctx.pos && cp && p.position === cp.position ? 0 : 1, inTable(p) ? 0 : 1,
      cp && p.level === cp.level ? 0 : 1];
    const byKey = (a, b) => { for (let i = 0; i < a.k.length; i++) if (a.k[i] !== b.k[i]) return a.k[i] - b.k[i]; return 0; };
    return hits.map(p => ({ p, k: key(p) })).sort((a, b) => byKey(a, b) || (b.p.minutes || 0) - (a.p.minutes || 0) || a.p.name.localeCompare(b.p.name)).map(o => o.p);
  }
  const W = TW.create({ metrics: () => METRICS, defaults: () => (CAT ? CAT.default_columns : {}), clubs: () => [...CID.values()],
    players: () => PLAYERS.filter(p => p.name), byId: (id) => PID.get(id), focus: () => S && PID.get(S.focus), order: namesakeOrder });

  // ------------------------------------------------------------------ loading (the first time the section opens)
  const onTerminal = () => decodeURIComponent(location.hash.replace(/^#/, '')).split('/')[0] === 'terminal';
  function onRoute() {
    if (!onTerminal()) { const v = clipVideo(); if (v) v.pause(); hideTip(); return; }
    if (!ready && !loading) load();
    else if (ready) { renderLayout(); renderAll(); }
  }
  // The place words' vocabulary (terminal-place.js) from the catalogue: countries, competitions, levels, every club and
  // player name (a competition word that is also a name is never read alone), and the scout's own level.
  const placeIndex = () => ({ countries: COUNTRIES.map(country => ({ country })), competitions: [...COMP.values()], levels: IX.levels,
    clubs: [...CID.values()], players: PLAYERS, scout_level: { filters: { ...MINE } } });
  async function load() {
    loading = true;
    out('Loading the catalogue…');
    try {
      const [cat, season, teams, ix, cms] = await Promise.all([R.api('/api/metrics'), R.api('/api/season'), R.api('/api/teams'),
        R.api('/api/catalogue'), R.api('/api/catalogue/matches?limit=200')]);
      CAT = cat; SEASON = season; TEAMS_ALL = teams; IX = ix;
      for (const m of cat.metrics || []) {
        if (MK.has(m.key)) continue;
        const rel = m.reliability || {};
        const x = { ...m, has_percentile: m.kind !== 'total', noisy: !!rel.noisy, reliability_r: rel.r ?? null };
        MK.set(m.key, x); METRICS.push(x);
      }
      for (const m of cat.team_metrics || []) TK.set(m.key, m);
      for (const l of (ix.levels || {}).pools || []) LVL.set(l.key, l);
      for (const c of ix.competitions || []) {
        const level = levelKey(c);
        COMP.set(c.competition_id, { ...c, level, level_words: (LVL.get(level) || {}).words || level });
        if (!COUNTRIES.includes(c.country)) COUNTRIES.push(c.country);
      }
      for (const k of ix.count_metrics || []) COUNT.add(k);
      for (const c of ix.careers || []) if (c.story) STORY.set(c.global_id, c.story);
      for (const c of ix.clubs || []) CID.set(c.club_id, { ...c });
      for (const c of season.clubs || []) CID.set(c.club_id, { ...(CID.get(c.club_id) || {}), ...c, competition_id: ENG });
      const fh = CID.get(SCOUT_CLUB), fc = fh && COMP.get(fh.competition_id);
      if (fc) { MINE = { tier: fc.tier, age_group: fc.age_group, gender: fc.gender }; MINE_CLUB = fh.name; }
      for (const t of teams.teams || []) TEAMS.set(t.club_id, t);
      for (const r of season.rounds || []) for (const m of r.matches || []) MATCH.set(m.match_id, { ...m, round: r.round });
      for (const m of cms.matches || []) if (!MATCH.has(m.match_id)) MATCH.set(m.match_id, m);
      await directory();
      V = TP.vocab(placeIndex());
    } catch (e) {
      loading = false;
      out(`The catalogue did not load (${errText(e)}).`, 'err', `${esc(`The catalogue did not load (${errText(e)}).`)} <button type="button" class="tx-mini" data-act="reload">Retry</button>`);
      return;
    }
    readStore();
    if (!$('txClipBody')) $('txDrawerBody').appendChild(buildClipBody());
    loading = false; ready = true;
    paintMeta(); paintExamples(); paintFoot(); renderLayout(); renderAll();
    const t0 = IX.totals || {};
    out(`Ready: ${PLAYERS.length} player rows in ${t0.competitions || COMP.size} competitions and ${t0.countries || COUNTRIES.length} countries, ${METRICS.length} stats, ${MATCH.size} uploaded matches. The table opens on ${whereWords(S.scr.where)}. Search a name, a club, a stat or a place, or try an example.`);
    if (onTerminal() && wantFocus) $('txIn').focus();
    if (document.activeElement === $('txIn') && $('txIn').value) suggest();   // typed while the catalogue loaded
  }

  // ------------------------------------------------------------------ levels, places and pools in plain words
  const levelWords = (key) => (LVL.get(key) || {}).words || String(key || '');
  const mineWhere = () => ({ ...MINE });
  const MINE_KEY = () => levelKey(MINE);
  const isMine = (lv) => lv === MINE_KEY();
  const sameWhere = (a, b) => W_FIELDS.every(([k]) => ((a || {})[k] || null) === ((b || {})[k] || null));
  const inWhere = (comp, w = S.scr.where) => TP.admits(w || {}, comp);
  // "semi-pro men", "U19 in Spain", "Weserland-Liga (Germany, semi-pro men)", "the whole catalogue".
  function whereWords(w) {
    w = w || {};
    if (w.competition && COMP.has(w.competition)) { const c = COMP.get(w.competition); return `${c.name} (${c.country}, ${c.level_words})`; }
    const parts = [];
    if (w.tier) parts.push(TIER_WORD[w.tier] || w.tier);
    if (w.age_group && w.age_group !== 'college' && !(w.age_group === 'senior' && w.tier)) parts.push(w.age_group);
    if (w.gender) parts.push(w.gender);
    let t = parts.join(' ');
    if (w.country) t = `${t ? t + ' ' : 'players '}in ${w.country}`;
    return t || 'the whole catalogue';
  }
  // "semi-pro men forwards", "U19 midfielders in Spain", "forwards in Weserland-Liga", "forwards across the whole catalogue".
  function whoWords(w, pos) {
    w = w || {};
    if (w.competition && COMP.has(w.competition)) return `${pos} in ${COMP.get(w.competition).name}`;
    const parts = [];
    if (w.tier) parts.push(TIER_WORD[w.tier] || w.tier);
    if (w.age_group && w.age_group !== 'college' && !(w.age_group === 'senior' && w.tier)) parts.push(w.age_group);
    if (w.gender) parts.push(w.gender);
    let t = parts.length ? `${parts.join(' ')} ${pos}` : pos;
    if (w.country) t += ` in ${w.country}`;
    else if (!parts.length) t += ' across the whole catalogue';
    return t;
  }
  // The levels the filters cover, in the catalogue's order.
  const levelsIn = (w) => [...LVL.keys()].filter(k => [...COMP.values()].some(c => c.level === k && inWhere(c, w)));
  // "98th percentile among 33 semi-pro men forwards" (level), "97th percentile among 18 forwards in Regista League"
  // (competition), "96th percentile among 123 men forwards at every level" (all levels): the engine's pool words. Never
  // "98th of 33": a percentile above the pool's size read as a rank bigger than the field.
  const poolOf = (c) => (c && c.pool) || {};
  const poolSize = (c) => poolOf(c).size ?? (c ? c.peers : null);
  function poolLine(p, c) {
    if (!c || c.percentile == null) return '';
    return `${ord(c.percentile)} percentile among ${poolSize(c)} ${poolOf(c).words || POSN[p.position]}`;
  }
  const smallPool = (c) => !!(c && c.percentile != null && poolOf(c).small);
  // A count where more is better at 0 (the engine's none yet): no percentile and no place.
  const isNone = (c) => !!(c && c.none_yet);
  // "none yet · 25 of the 33 semi-pro men forwards have none"
  function noneText(p, c) {
    const z = c && c.zeros, words = poolOf(c).words || POSN[p.position];
    if (!z || !z.of) return 'none yet';
    return `none yet · ${z.none === z.of ? `all ${z.of}` : `${z.none} of the ${z.of}`} ${words} have none`;
  }
  // The pool a player's percentiles are read against, said once: "semi-pro men forwards", "forwards in Regista League".
  const poolWordsFor = (p) => S.scope === 'competition' ? `${POSN[p.position]} in ${p.comp.name}` : S.scope === 'all' ? `${p.gender} ${POSN[p.position]} at every level` : `${levelWords(p.level)} ${POSN[p.position]}`;
  // The qualifying minutes of a row's competition, as people say them ("101 minutes" in England, "45" elsewhere).
  function minMin(p) {
    const cs = p && CELLS.get(`${S.scope}|${p.id}`), any = cs && Object.values(cs).find(c => c && c.sample);
    const q = any ? any.sample.qualifying_minutes : p && QMIN.has(p.cid) ? QMIN.get(p.cid) : (p && p.cid === ENG ? CAT.season.min_minutes : null);
    return q == null ? null : Math.ceil(Number(q) || 0);
  }
  const sampleOf = (p) => { const cs = p && CELLS.get(`${S.scope}|${p.id}`), any = cs && Object.values(cs).find(c => c && c.sample); return any ? any.sample : null; };
  // "Femi Toure · Brookfield Rovers · Forward (ST) #9 · Regista League, England, semi-pro men"
  const rowLine = (p) => `${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number} · ${p.comp.name}, ${p.country}, ${levelWords(p.level)}`;
  const compLine = (cid) => { const c = COMP.get(cid); return c ? `${c.name} · ${c.country} · ${c.level_words}` : ''; };

  // ------------------------------------------------------------------ saved layouts, per visitor (Regista.store)
  function defaults() {
    const f = PID.has('pl_bro_09') ? 'pl_bro_09' : (PLAYERS.find(p => p.minutes > 0) || PLAYERS[0]).id, fp = PID.get(f);
    const cols = (CAT.default_columns[fp.position] || CAT.default_columns.all).filter(k => MK.has(k));
    return { v: VER, panels: DEFAULT_ORDER.map(id => PANELS.find(p => p.id === id)).map(p => ({ id: p.id, on: true, size: p.size })), focus: f, compare: [], club: fp.club_id,
      scope: 'level', scr: { pos: fp.position, cols, sort: { k: cols[0], dir: -1 }, qual: true, mode: 'val', q: '', where: mineWhere() },
      scat: { x: 'npxg', y: 'xa', pos: fp.position, all: false }, form: { k: null }, radar: { tpl: 'pos' } };
  }
  // A saved layout is checked before use: unknown players, metrics and panels are dropped. Version 2 (the first port) kept
  // Clips in the grid; version 3 opens it as a drawer. A v2 layout that is still the v2 default takes the new default (the
  // table with the player card and radar beside it); a changed one keeps its order, sizes and hidden panels, minus Clips.
  // Its players, comparison, columns, sort, filters and axes carry over. Version 4 (the catalogue) adds the table's place
  // filters (where) and the percentile scope; a v2 or v3 layout opens on the scout's own level, and a player saved by
  // global id who now has two rows (a career player) takes their first row.
  const V2_DEFAULT = 'scrn:L,clips:S,plyr:S,radar:S,form:S,shot:S,heat:S,scat:S,team:XL';
  function clean(s) {
    const o = defaults();
    if (!s || typeof s !== 'object' || ![2, 3, VER].includes(s.v)) return o;
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
    const asRow = (id) => typeof id === 'string' ? (PID.has(id) ? id : GID1.get(id) || null) : null;
    if (asRow(s.focus)) o.focus = asRow(s.focus);
    if (Array.isArray(s.compare)) o.compare = [...new Set(s.compare.map(asRow).filter(Boolean))].slice(0, 3);
    if (s.v === VER && SCOPES.includes(s.scope)) o.scope = s.scope;
    if (CID.has(s.club)) o.club = s.club;
    const sc = s.scr || {};
    if (sc.pos === null || POS.includes(sc.pos)) o.scr.pos = sc.pos;
    if (Array.isArray(sc.cols)) o.scr.cols = [...new Set(sc.cols.filter(k => MK.has(k)))].slice(0, MAX_COLS);
    if (sc.sort && (MK.has(sc.sort.k) || ['name', 'club', 'min'].includes(sc.sort.k))) o.scr.sort = { k: sc.sort.k, dir: sc.sort.dir === 1 ? 1 : -1 };
    o.scr.qual = sc.qual !== false; o.scr.mode = sc.mode === 'pct' ? 'pct' : 'val';
    o.scr.q = typeof sc.q === 'string' ? sc.q.slice(0, 40) : '';
    if (s.v === VER && sc.where && typeof sc.where === 'object') {
      const lv = IX.levels || {}, ok = { country: (v) => COUNTRIES.includes(v), tier: (v) => (lv.tiers || []).some(t => t.key === v),
        age_group: (v) => (lv.age_groups || []).some(a => a.key === v), gender: (v) => v === 'men' || v === 'women', competition: (v) => COMP.has(v) };
      const w = {};
      for (const k of Object.keys(ok)) if (typeof sc.where[k] === 'string' && ok[k](sc.where[k])) w[k] = sc.where[k];
      o.scr.where = w;
    }
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
  // ≈ for one row (its own level's flag, from the engine's cell) or, without a row, at the selected player's level (the
  // league's flag until their numbers are in).
  const noisyAt = (m, p) => { const c = cellOf(p || (S && PID.get(S.focus)), m.key); return c && c.noisy != null ? !!c.noisy : !!m.noisy; };
  const NOISY = '<span class="tx-noisy" role="img" aria-label="small sample, read with care">≈</span>';
  const noisy = (m, p) => noisyAt(m, p) ? NOISY : '';
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
  // A row's cell in the percentile scope shown (the table's calls and the player's own numbers fill them).
  const cellOf = (p, k) => (p && S && (CELLS.get(`${S.scope}|${p.id}`) || {})[k]) || null;
  const pctOf = (p, k) => { const c = cellOf(p, k); return c ? c.percentile : null; };
  // The Regista League's qualifying minutes as people say them ("101 minutes"; the engine's threshold is a third of a
  // club's minutes); every other competition has its own (minMin).
  const minMinutes = () => Math.ceil(Number(CAT.season.min_minutes) || 0);
  // Why a value has no percentile, as the engine decides it, in the catalogue's order: none yet (a count of 0); the metric
  // has no percentiles at all (a season count); it is not scored for the player's position; the player is under their
  // competition's qualifying minutes; a ratio has too few attempts; the pool is under its minimum size (5, or 2 in the
  // Regista League's own competition scope). `small` marks a small sample (the table's italics).
  function noPct(p, m, c) {
    if (!c || c.value == null || c.percentile != null) return null;
    if (isNone(c)) return { text: noneText(p, c), small: false };
    if (!m.has_percentile) return { text: 'no percentile: a season count, ranked by value only', small: false };
    if (!m.positions.includes(p.position)) return { text: `no percentile: not scored for ${POSN[p.position]} (scored for ${m.positions.join(' ')})`, small: false };
    const mm = minMin(p);
    if (!p.qualified) return { text: `no percentile: ${Math.round(p.minutes || 0)} minutes, under the ${mm == null ? 'minutes' : mm} a regular needs in ${p.comp.name}`, small: true };
    const att = ((p.desc || {})[m.key] || {}).min_attempts ?? (p.cid === ENG ? m.min_attempts : null);
    if (!c.qualified) return { text: `no percentile: below the minimum attempts${c.den != null && att ? ` (${c.den} attempts, needs ${att})` : ''}`, small: true };
    const pl = poolOf(c);
    if (pl.size != null && pl.min_size != null && pl.size < pl.min_size) return { text: `no percentile: only ${pl.size} regular ${POSN[p.position]} in this ${SCOPE_WORD[S.scope]} pool, and a percentile needs ${pl.min_size}`, small: false };
    return { text: `no percentile${pl.reason ? `: ${pl.reason}` : ''}`, small: false };
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
  // "R5 v ASH" / "R5 at ASH" for a club's match (league fixtures and every catalogue upload).
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
        <div class="tx-aboutp"><p>Percentiles compare a player with the regulars in the same position at the same level by default: the same tier, age group and gender (for example semi-pro men, or academy U19 men). The players table can switch to their competition, or to all levels of one gender. Men and women never share a pool.</p>
        <p>A regular has a third of the minutes of their competition's busiest club: at least ${esc(minMinutes())} minutes in the Regista League, at least ${esc(FLOOR)} elsewhere. A pool of fewer than ${esc(SMALL_POOL)} regulars is marked small; under ${esc(MIN_POOL)} there is no percentile. Where lower is better, the percentile is turned round.</p>
        <p>Raw numbers are ranked only within one level, percentiles only within one position: a list that mixes levels splits into one list per level, or, for one position, ranks each player by their percentile in their own pool. A count of 0 (no goals yet) is "none yet": no percentile and no place.</p>
        <p>${esc(plainSample(sm.note))} Outside England only the uploaded matches count, so a regular there has played one to three matches of about 30 minutes.</p>
        <p><span class="tx-noisy">≈</span> marks a stat that one season cannot yet use to tell players in the same role apart at that level (its split-half reliability is below ${esc(rel.noise_r)}).</p>
        <p>Every underlined number plays every moment behind it in the clips drawer. Physical numbers list one value per match (no single clip).</p></div></details>
      <div class="tx-ws" role="group" aria-label="Saved layouts"><span class="tx-wsl">Saved layouts:</span>
        ${[0, 1, 2].map(i => `<button type="button" data-act="ws" data-i="${i}" aria-pressed="${store.cur === i}" aria-label="Saved layout ${i + 1}" title="Saved layout ${i + 1}: panels, players, columns and filters, kept in this browser">${i + 1}</button>`).join('')}
        <button type="button" data-act="reset" class="tx-reset" title="Put this layout back to the default">Reset layout</button>
        ${storageOK ? '' : '<span class="tx-warn" title="This browser blocks storage, so layouts last until you leave the page.">not saved: storage blocked</span>'}</div>`;
  }
  // Example searches under the box, each running the command it stands for: the league's three, then the catalogue's
  // place and level questions.
  function paintExamples() {
    const f = PID.get('pl_bro_09') || PID.get(S.focus);
    const rival = PLAYERS.find(p => p.name === 'Amari Ustinov');
    const exs = [['Best finishers', 'rank forwards non-penalty goals'],
      ...(rival && rival !== f ? [[`Compare ${lastName(f)} and ${lastName(rival)}`, `compare ${f.name} and ${rival.name}`]] : []),
      [`Who plays like ${lastName(f)}?`, `similar to ${f.name}`],
      ['U19 midfielders in Spain', 'U19 midfielders in Spain'], ['Best dribblers in academy', 'best dribblers in academy'],
      ['Women forwards', 'women forwards'], ['Players in Nigeria', 'players in Nigeria'], ['My level', 'my level forwards']];
    $('txEx').innerHTML = `<span class="tx-exl">Try</span>${exs.map(([l, c]) => `<button type="button" class="tx-exb" data-act="run" data-cmd="${esc(c)}" title="Runs: ${esc(c)}">${esc(l)}</button>`).join('')}`;
  }
  // Synthetic data, said once and plainly, at the bottom of the section.
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const fmtDate = (iso) => { const [y, m, d] = String(iso || '').split('-').map(Number); return y && m && d ? `${d} ${MONTHS[m - 1]} ${y}` : String(iso || ''); };
  function paintFoot() {
    $('txFoot').innerHTML = `<b>Synthetic data:</b> invented players, clubs and competitions, generated by Regista; countries and levels are labels.${IX.as_of ? ` Data as of ${esc(fmtDate(IX.as_of))}.` : ''}`;
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
    if (!quiet) out(rowLine(p));
  }
  // Beside the search: the selected player, and the comparison when there is one.
  function renderSel() {
    const f = PID.get(S.focus);
    const chips = S.compare.map((id, i) => { const p = PID.get(id); return `<span class="tx-chip" data-c="${CMP_COL[i]}"><button type="button" data-act="sel" data-pid="${esc(id)}" data-fid="chip-${esc(id)}" title="Select ${esc(p.name)}">${esc(p.name)}</button><button type="button" class="tx-x" data-act="cmprm" data-pid="${esc(id)}" aria-label="Remove ${esc(p.name)} from the comparison" title="Remove from the comparison">&times;</button></span>`; }).join('');
    const inCmp = S.compare.includes(S.focus);
    let btn = '';
    if (!S.compare.length || (inCmp && S.compare.length < 3)) btn = '<button type="button" class="tx-mini tx-cmpw" data-act="cmpwith" title="Type a player to compare with">Compare with…</button>';
    else if (!inCmp) btn = `<button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(S.focus)}">Add ${esc(f.name)} to the comparison${S.compare.length >= 3 ? ` (replaces ${esc(PID.get(S.compare[0]).name)})` : ''}</button>`;
    $('txSel').innerHTML = `<span class="tx-sl">Selected:</span><button type="button" class="tx-focus" data-act="pane" data-id="plyr" title="Go to the player card">${esc(f.name)} <span>${esc(f.short_name)} · ${esc(f.position)} · #${esc(f.kit_number)} · ${esc(levelWords(f.level))}${f.country !== 'England' || !isMine(f.level) ? `, ${esc(f.country)}` : ''}</span></button>
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
  function cellSub(p, m, c) {
    if (!c) return `No minutes in ${p.comp.name}`;
    return `${fmt(m, c.value)}${m.kind === 'ratio' && m.unit === '%' ? '' : ' ' + unitText(m)}${c.num != null ? ` · ${c.num} of ${c.den}` : c.total != null && m.kind !== 'total' ? ` · ${c.total} in total` : ''}${c.percentile != null ? ` · ${poolLine(p, c)}` : isNone(c) ? ` · ${noneText(p, c)}` : ''} · ${p.comp.name}`;
  }
  function evidenceReel(pid, mk, ev, match) {
    const p = PID.get(pid), m = MK.get(mk), c = cellOf(p, mk);
    const r = { title: `${p.name} · ${m.label}${noisyAt(m, p) ? ' ≈' : ''}`, sub: cellSub(p, m, c), items: [], i: -1, pid, mk, match: match || null, note: '' };
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
      // One key can list an event twice (a pass that leads to two shots is two shot-creating actions): one row per
      // event, as evidence_total counts them, saying how many times it counts.
      r.items = mergeEvidence(ev).map(g => {
        const n = g.v.length, v = n > 1 ? g.v.reduce((a, b) => a + b, 0) : g.v[0];
        return { when: when(g.it), minute: g.it.minute, val: evText(m, v), note: [...g.notes.map(words), n > 1 ? `counts ${n} times` : ''].filter(Boolean).join(' · '), video: g.it.video_url || null, match_id: g.it.match_id };
      });
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

  // ------------------------------------------------------------------ Players: the players table, on the catalogue
  // The rows as the engine ordered them, in its lists (one per level, or one per gender when one position spans levels):
  // the rows the engine gave a place first, in its order, then the rest (too few minutes or attempts, no percentile, none
  // yet), as /api/catalogue/rank lists them after its ranked rows. The browser computes no place: the name filter above the
  // table only hides rows, and a club sort is the engine's names list put in club order (an order, not a ranking).
  const orderKeyNow = () => { const sp = sortParams(); return `ord|${tableBase()}|${sp.sort}|${sp.order || ''}`; };
  function screenBoards() {
    const c = S && C.get(orderKeyNow());
    if (!c || c.st !== 'ok') return [];
    const o = c.v, q = norm(S.scr.q);
    const keep = (p) => p && p.minutes > 0 && (!q || norm(p.name).includes(q) || norm(p.club).includes(q) || norm(p.short_name) === q);
    let rows = o.ids.map(id => PID.get(id)).filter(keep);
    if (S.scr.sort.k === 'club') rows = rows.slice().sort((a, b) => S.scr.sort.dir * String(a.club).localeCompare(String(b.club)) || String(a.name).localeCompare(String(b.name)));
    // Pool mode is always one list per gender (one gender: one list, with its gender for a name).
    const split = o.rank_by === 'pool' || !!(o.boards && o.boards.length > 1);
    const groups = new Map((split && o.boards ? o.boards.map(b => b.board) : []).map(k => [k, []]));
    for (const p of rows) { const k = !split ? '' : o.board.get(p.id) || (o.rank_by === 'pool' ? p.gender : ''); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(p); }
    const mode = o.rank_by === 'pool' ? 'pool' : split ? 'level' : 'one';
    return [...groups].filter(([, rs]) => rs.length).map(([key, rs]) => {
      const all = [...rs.filter(p => o.rank.get(p.id) != null), ...rs.filter(p => o.rank.get(p.id) == null)];
      return { key, mode, rows: all, ranks: all.map(p => o.rank.get(p.id) ?? null) };
    });
  }
  const screenRows = () => screenBoards().flatMap(b => b.rows);
  // A count where more is better (the engine's count_metrics): at 0 it reads "none yet".
  const isCount = (m) => !!m && COUNT.has(m.key);
  function metricOptions(sel, filter) {
    return (CAT.groups || []).map(g => {
      const ms = METRICS.filter(m => m.group === g.key && (!filter || filter(m)));
      return ms.length ? `<optgroup label="${esc(g.label)}">${ms.map(m => `<option value="${esc(m.key)}"${m.key === sel ? ' selected' : ''}>${esc(m.label)}${noisyAt(m) ? ' ≈' : ''}</option>`).join('')}</optgroup>` : '';
    }).join('');
  }
  // The filters: country, level, age group, gender and competition, each limited to what the others allow.
  function whereOptions(field) {
    const w = S.scr.where || {}, others = { ...w }; delete others[field];
    const comps = [...COMP.values()].filter(c => inWhere(c, others)), lv = IX.levels || {};
    const any = '<option value="">Any</option>';
    const opt = (v, l) => `<option value="${esc(v)}"${w[field] === v ? ' selected' : ''}>${esc(l)}</option>`;
    if (field === 'country') return any + COUNTRIES.filter(c => comps.some(x => x.country === c)).map(c => opt(c, c)).join('');
    if (field === 'tier') return any + (lv.tiers || []).filter(t => comps.some(x => x.tier === t.key)).map(t => opt(t.key, t.label)).join('');
    if (field === 'age_group') return any + (lv.age_groups || []).filter(t => comps.some(x => x.age_group === t.key)).map(t => opt(t.key, t.label)).join('');
    if (field === 'gender') return any + (lv.genders || []).filter(t => comps.some(x => x.gender === t.key)).map(t => opt(t.key, t.label)).join('');
    return any + COUNTRIES.map(co => { const cs = comps.filter(x => x.country === co); return cs.length ? `<optgroup label="${esc(co)}">${cs.map(x => opt(x.competition_id, x.name + ' (' + x.level_words + ')')).join('')}</optgroup>` : ''; }).join('');
  }
  // How the list is ranked, in words: "goals per 90", "take-ons won per 90", "minutes played".
  function statWordsOf(sm) {
    if (!sm) return { name: 'name', club: 'club', min: 'minutes played' }[S.scr.sort.k] || 'minutes played';
    const l = shortLabel(sm), low = /^[A-Z][a-z]/.test(l) ? l.charAt(0).toLowerCase() + l.slice(1) : l;
    return `${low}${sm.kind === 'per90' || sm.kind === 'padj' ? ' per 90' : sm.kind === 'total' ? ' this season' : ''}`;
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
    const td = tableData(cols), waits = [td.ord, ...td.extra];
    const failed = waits.find(c => c.st === 'err'), busyNow = waits.some(c => c.st === 'wait');
    const boards = td.ord.st === 'ok' ? screenBoards() : [], rows = boards.flatMap(b => b.rows), mode = boards.length ? boards[0].mode : 'one';
    const sm = MK.get(sc.sort.k), heads = boards.length > 1 || mode === 'pool';
    const sortAttr = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? 'descending' : 'ascending') : 'none';
    if (!scrAct || !rows.some(p => p.id === scrAct.pid)) scrAct = { pid: rows.some(p => p.id === S.focus) ? S.focus : (rows[0] && rows[0].id), c: 0 };
    if (scrAct.c > cols.length) scrAct.c = 0;
    const cell = (p, k, ci) => {
      const m = MK.get(k), act = scrAct.pid === p.id && scrAct.c === ci + 1, c = cellOf(p, k);
      if (!c) return busyNow ? '<td class="num"><span class="tx-dim" aria-label="loading">…</span></td>' : '<td class="num"><span class="tx-dim">–</span></td>';
      const txt = sc.mode === 'pct' ? (isNone(c) ? 'none' : c.percentile == null ? '–' : c.percentile) : fmt(m, c.value);
      const np = noPct(p, m, c);
      const lab = `${p.name}, ${m.label} ${withUnit(m, c.value)}${c.percentile != null ? `, ${poolLine(p, c)}${smallPool(c) ? ', a small pool' : ''}` : np ? `, ${np.text}` : ''}. ${cap1(playTextC(m, c))}`;
      return `<td class="num"><button type="button" class="tx-n${np && np.small ? ' uq' : ''}${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-sel="1" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-nav data-fid="c-${esc(p.id)}-${esc(k)}" tabindex="${act ? 0 : -1}" aria-label="${esc(lab)}">${esc(txt)}</button></td>`;
    };
    // The Percentile column: the sorted stat's percentile with the size of its pool, the small-pool flag, none yet, or why
    // there is none (in its tooltip).
    const poolCell = (p) => {
      if (!sm) return '';
      const c = cellOf(p, sm.key), np = noPct(p, sm, c);
      if (isNone(c)) return `<td class="num tx-pool" title="${esc(`${shortLabel(sm)}: ${noneText(p, c)}`)}"><span class="tx-nyet">none yet</span></td>`;
      if (!c || c.percentile == null) return `<td class="num tx-pool"><span class="tx-dim" title="${esc(np ? cap1(np.text) : 'No value')}">–</span></td>`;
      return `<td class="num tx-pool" title="${esc(`${shortLabel(sm)}: ${poolLine(p, c)}${smallPool(c) ? `. Small pool: fewer than ${SMALL_POOL} regulars` : ''}`)}">${esc(ord(c.percentile))} <span class="tx-dim">· <span class="tx-poolw">pool </span>${esc(poolSize(c))}</span>${smallPool(c) ? ' <span class="tx-small">small</span>' : ''}</td>`;
    };
    // A click on a header sorts (again: the other way); the sorted column is the yellow one, and the panel's header says
    // which way. Removing a column is in the Columns menu.
    const sortBtn = (k, label, extra = '') => `<button type="button" data-act="sort" data-k="${esc(k)}" data-fid="h-${esc(k)}"${extra}>${label}</button>`;
    const colNoisy = (k) => rows.some(p => (cellOf(p, k) || {}).noisy);
    const head = `<tr><th class="tx-stk" aria-sort="${sortAttr('name')}">${sortBtn('name', 'Player')}</th>
      <th class="tx-hc" aria-sort="${sortAttr('club')}">${sortBtn('club', 'Club')}</th><th class="tx-hc">Level</th><th class="tx-hc">Pos</th>
      <th class="num" aria-sort="${sortAttr('min')}">${sortBtn('min', 'Mins', ' title="Minutes played in this competition"')}</th>
      ${sm ? `<th class="num tx-poolh" title="${esc(`${sm.label}: the percentile, then the size of the pool it is ranked in (each player's ${SCOPE_WORD[S.scope]}, same position)`)}">Percentile</th>` : ''}
      ${cols.map(k => { const m = MK.get(k), nz = colNoisy(k); return `<th class="num" aria-sort="${sortAttr(k)}">${sortBtn(k, `${esc(shortLabel(m))}${m.kind === 'total' ? ' <span class="tx-u">(total)</span>' : ''}${nz ? NOISY : ''}`, `${shortLabel(m).length <= 12 ? ' class="nw"' : ''} data-mk="${esc(k)}" aria-label="${esc(m.label)}${nz ? ', small sample' : ''}, sort"`)}</th>`; }).join('')}</tr>`;
    const ncol = 5 + (sm ? 1 : 0) + cols.length;
    const statWords = statWordsOf(sm);
    // Each list names its level (or gender) and the stat it is ranked by: "Semi-pro men · your level · 66 players · ranked
    // by goals per 90".
    const boardHead = (b) => {
      const pos = sc.pos ? POSN[sc.pos] : 'players';
      if (b.mode === 'pool') {
        const lv = new Set(b.rows.map(p => p.level)).size;
        return `${cap1(b.key)} · ${b.rows.length} ${pos} from ${plural(lv, 'level')} · ranked by their percentile for ${statWords} in their own ${SCOPE_WORD[S.scope]} pool`;
      }
      return `${cap1(levelWords(b.key))}${isMine(b.key) ? ' · your level' : ''} · ${b.rows.length} ${pos} · ranked by ${statWords}`;
    };
    // After a list sorted by a count: how many have none of it, listed after the rest with no place.
    const noneRow = (b) => {
      if (!sm || !isCount(sm)) return '';
      const zero = b.rows.filter(p => isNone(cellOf(p, sm.key))).length;
      if (!zero) return '';
      const have = b.rows.filter(p => { const c = cellOf(p, sm.key); return c && c.value != null && !isNone(c); }).length;
      const what = statWords.replace(/ (per 90|this season)$/, '');
      return `<tr class="tx-bnone"><td colspan="${ncol}" class="tx-dim"><span class="tx-bnl">${esc(`${have} of the ${have + zero} players on this list ${have === 1 ? 'has' : 'have'} any ${what} so far. The ${zero === 1 ? 'one' : zero} with none ${zero === 1 ? 'is' : 'are'} listed after, with no place.`)}</span></td></tr>`;
    };
    const w = sc.where || {};
    const body = boards.map((b, bi) => (heads ? `<tr class="tx-board"><th colspan="${ncol}" scope="colgroup" id="txb-${bi}"><span class="tx-bh">${esc(boardHead(b))}</span></th></tr>` : '') + b.rows.map((p, r) => {
      const ci = S.compare.indexOf(p.id), act = scrAct.pid === p.id && scrAct.c === 0, rk = b.ranks[r];
      return `<tr class="${p.id === S.focus ? 'on' : ''}${ci >= 0 ? ' cmp' : ''}" data-row="${esc(p.id)}"${ci >= 0 ? ` data-c="${CMP_COL[ci]}"` : ''}>
        <th class="tx-stk" scope="row"><span class="tx-rk">${rk == null ? '–' : esc(rk)}</span><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-nav data-fid="n-${esc(p.id)}" tabindex="${act ? 0 : -1}"${p.id === S.focus ? ' aria-current="true"' : ''}>${esc(p.name)}</button><span class="tx-sub">${esc(p.short_name)} · ${esc(p.position)} · ${esc(levelWords(p.level))}${w.country ? '' : `, ${esc(p.country)}`}</span></th>
        <td class="tx-hc">${esc(p.short_name)}</td><td class="tx-hc tx-lvc" title="${esc(`${p.comp.name} · ${p.country}`)}">${esc(levelWords(p.level))} <span class="tx-dim">${esc(p.country)}</span></td><td class="tx-hc">${esc(p.position)} <span class="tx-dim">${esc(p.role)}</span></td><td class="num">${esc(Math.round(p.minutes))}</td>
        ${poolCell(p)}${cols.map((k, i) => cell(p, k, i)).join('')}</tr>`;
    }).join('') + noneRow(b)).join('');
    const mine = sameWhere(w, mineWhere()), all = !W_FIELDS.some(([k]) => w[k]);
    const levels = new Set(rows.map(p => p.level));
    const mixed = mode === 'pool' ? `One position across ${plural(levels.size, 'level')}: each player is ranked by their percentile within their own pool, one list per gender. A raw number at one level is not better or worse than the same number at another, so read each percentile against its own pool.`
      : mode === 'level' ? `This list mixes ${boards.length} levels, so it is split into one list per level: raw numbers are compared only within a level. Pick a position to rank everyone by their percentile in their own pool.` : '';
    const allWarn = S.scope === 'all' && td.ord.st === 'ok' && td.ord.v.warning ? cap1(td.ord.v.warning) : '';
    const status = failed ? ` · <span class="tx-bad">the table did not load (${esc(errText(failed.e))})</span> <button type="button" class="tx-mini" data-act="colsretry">Retry</button>`
      : busyNow ? ' · <span class="tx-wait">loading…</span>' : '';
    const html = `<div class="tx-ctls tx-wherebar">
        <details class="tx-menu tx-wmenu" data-r="wmenu"${whereMenuOpen ? ' open' : ''}><summary class="tx-mini" data-fid="scr-where">Where: <b>${esc(whereWords(w))}</b></summary>
          <div class="tx-menup tx-wherep" role="group" aria-label="Where">
            ${W_FIELDS.map(([f, l]) => `<label class="tx-ctl"><span>${esc(l)}</span><select data-r="w-${f}" data-fid="w-${f}">${whereOptions(f)}</select></label>`).join('')}
            <p class="tx-cap">Competitions and options narrow to what the other filters allow.</p></div></details>
        <button type="button" class="tx-mini" data-act="wmine" aria-pressed="${mine}" title="${esc(`Your level: ${levelWords(MINE_KEY())} (${MINE_CLUB}'s level)`)}">My level</button>
        <button type="button" class="tx-mini" data-act="wall" aria-pressed="${all}">Whole catalogue</button>
        <div class="tx-seg" role="group" aria-label="Percentiles within"><span class="tx-segl"><span class="tx-seglw">Percentiles within</span><span class="tx-segln">Compare within</span></span>${SCOPES.map(v => `<button type="button" data-act="scope" data-v="${v}" aria-pressed="${S.scope === v}" title="${esc(v === 'level' ? 'Same tier, age group and gender (the default)' : v === 'competition' ? 'Their own competition only' : 'Every level of their gender: men and women never share a pool')}">${esc(cap1(SCOPE_WORD[v]))}</button>`).join('')}</div></div>
      <div class="tx-ctls">
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scrpos" data-v="${v || ''}" aria-pressed="${sc.pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-ctl"><span class="sr">Filter by name or club</span><input type="search" data-r="scrq" data-fid="scr-q" value="${esc(sc.q)}" placeholder="Filter by name or club" autocomplete="off" maxlength="40"></label>
        <label class="tx-chk" title="${esc(`A regular has a third of the minutes of their competition's busiest club: ${minMinutes()} in the Regista League, at least ${FLOOR} elsewhere`)}"><input type="checkbox" data-r="scrqual" data-fid="scr-qual"${sc.qual ? ' checked' : ''}> Regulars only</label>
        <div class="tx-seg" role="group" aria-label="Show"><button type="button" data-act="scrmode" data-v="val" aria-pressed="${sc.mode === 'val'}">Value</button><button type="button" data-act="scrmode" data-v="pct" aria-pressed="${sc.mode === 'pct'}">Percentile</button></div>
        <details class="tx-menu" data-r="colmenu"${colMenuOpen ? ' open' : ''}><summary class="tx-mini" data-fid="scr-cols">Columns (${cols.length})</summary>
          <div class="tx-menup" role="group" aria-label="Columns">
            ${cols.length ? `<ul class="tx-collist">${cols.map(k => { const m = MK.get(k); return `<li><span>${esc(m.label)}${noisy(m)}</span><button type="button" class="tx-x" data-act="rmcol" data-k="${esc(k)}" data-fid="rm-${esc(k)}" aria-label="Remove the ${esc(m.label)} column" title="Remove">&times;</button></li>`; }).join('')}</ul>` : '<p class="tx-dim">No stat columns.</p>'}
            <label class="tx-ctl tx-addcol"><span>Add</span><select data-r="addcol" data-fid="scr-add"${cols.length >= MAX_COLS ? ' disabled' : ''}><option value="">a stat…</option>${metricOptions(null, m => !cols.includes(m.key))}</select></label>
            <button type="button" class="tx-mini" data-act="scrdef">Default columns</button></div></details></div>
      ${mixed ? `<p class="tx-warn tx-mixed">${esc(mixed)}</p>` : ''}${allWarn ? `<p class="tx-warn tx-mixed">All levels: ${esc(allWarn)}</p>` : ''}
      <p class="tx-cap">${rows.length} ${esc(sc.pos ? POSN[sc.pos] : 'players')} · ${esc(whereWords(w))}${heads ? ` · ${plural(boards.length, 'list')}` : ''}${sc.qual ? ', regulars only' : ''} · <b class="tx-capu">${sc.mode === 'pct' ? `percentiles within each player's ${esc(SCOPE_WORD[S.scope])}` : `values per 90 minutes${cols.some(k => { const x = MK.get(k); return x.kind !== 'per90' && x.kind !== 'padj'; }) ? ' (except %, averages and totals)' : ''}`}</b><span class="tx-capx">${sc.mode === 'pct' ? '' : ` · shading = percentile within each player's ${esc(SCOPE_WORD[S.scope])}`}${boards.some(b => b.ranks.some(x => x == null)) ? ' · – = not ranked (too few minutes or attempts, no percentile, or none yet)' : ''} · click a row to select, an underlined number to play its moments</span>${status}</p>
      <div class="tx-scroll tx-tablewrap"><table class="tx-table"><thead>${head}</thead><tbody data-r="grid">${body || `<tr><td colspan="${ncol}" class="tx-dim">${esc(td.ord.st === 'ok' ? emptyText() : td.ord.st === 'err' ? 'The players did not load.' : 'Loading the players…')}</td></tr>`}</tbody></table></div>`;
    const dirWord = sc.sort.dir === -1 ? (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'Z to A' : 'highest first') : (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'A to Z' : 'lowest first');
    const sortName = sm ? shortLabel(sm) : { name: 'name', club: 'club', min: 'minutes' }[sc.sort.k];
    paint('scrn', html, sortName ? esc(mode === 'pool' ? `Sorted by ${sortName}, percentile in own pool, ${sc.sort.dir === (sm && sm.higher_is_better === false ? 1 : -1) ? 'best first' : 'worst first'}` : `Sorted by ${sortName}, ${dirWord}`) : '');
  }
  // New filters: the table, the scatter (one level at a time) and the status line follow.
  async function setWhere(w, quiet) {
    const g = ++gen;
    S.scr.where = w; scrAct = null; save();
    renderScrn(); if (visible('scat')) renderScat();
    if (quiet) return;
    out(`Showing ${whereWords(w)}: loading…`);
    await settle(tableData(S.scr.cols.filter(k => MK.has(k))).ord);
    if (g !== gen) return;
    const n = screenRows().length;
    out(n ? `Showing ${whereWords(w)}: ${n} ${S.scr.pos ? POSN[S.scr.pos] : 'players'}${S.scr.qual ? ' (regulars)' : ''}.` : emptyText(), n ? '' : 'err');
  }
  function scopeText() {
    return S.scope === 'level' ? 'Percentiles within each player\'s level: the same tier, age group and gender (the default).'
      : S.scope === 'competition' ? 'Percentiles within each player\'s own competition.'
      : 'Percentiles across all levels of each player\'s gender: rows from different levels, so read each percentile against its own pool. Men and women never share a pool.';
  }
  // No rows: say which filters leave nothing, and what the catalogue does have.
  function emptyText() {
    const w = S.scr.where || {};
    if (![...COMP.values()].some(c => inWhere(c, w))) return `No competition in the catalogue matches ${whereWords(w)}. Try "Whole catalogue" or change a filter.`;
    return `No ${S.scr.pos ? POSN[S.scr.pos] : 'players'} match${S.scr.qual ? ' (regulars only: untick it to see everyone)' : ''}${S.scr.q ? ` "${S.scr.q}"` : ''}.`;
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
    const pw = poolWordsFor(p), mm = minMin(p);
    let best, sample = '';
    if (fc.st !== 'ok') best = waitHtml(fc, `${p.name}'s numbers`);
    else {
      // The player's own best numbers, by their percentile in the scope shown (a sort of one player's numbers, not a
      // ranking of players).
      const strengths = METRICS.filter(m => m.positions.includes(p.position) && m.has_percentile && m.higher_is_better !== null && pctOf(p, m.key) != null)
        .sort((a, b) => pctOf(p, b.key) - pctOf(p, a.key)).slice(0, 6);
      best = p.minutes > 0 ? `<h3 class="tx-h3">Best among ${esc(pw)}</h3>
        ${strengths.length ? `<table class="tx-mt tx-best"><tbody>${strengths.map(m => mrow(p, m)).join('')}</tbody></table>
        <p class="tx-cap">/90 = per 90 minutes played. The bar and the last number are the percentile among regular ${esc(pw)}, then the pool's size; "small" marks a pool under ${esc(SMALL_POOL)}.</p>`
        : `<table class="tx-mt tx-best"><tbody><tr><td class="tx-dim">${esc(!p.qualified ? `No percentiles yet: ${Math.round(p.minutes)} minutes, under the ${mm == null ? 'minutes' : mm} a regular needs in ${p.comp.name}.` : `No percentiles: too few regular ${POSN[p.position]} in this ${SCOPE_WORD[S.scope]} pool.`)}</td></tr></tbody></table>`}`
        : `<p class="tx-dim">No minutes in ${esc(p.comp.name)}.</p>`;
      const sp = sampleOf(p);
      if (sp) sample = `<p class="tx-cap tx-sample">Sample: ${esc(plural(p.appearances || 0, 'appearance'))} in ${esc(sp.club_matches != null ? `${sp.club_matches} uploaded ${sp.club_matches === 1 ? 'match' : 'matches'} of ${p.club}` : 'the uploaded matches')}${sp.competition_matches != null ? ` (${esc(sp.competition_matches)} uploaded in the competition)` : ''}, ${esc(Math.round(p.minutes || 0))} minutes; a regular needs ${esc(Math.ceil(Number(sp.qualifying_minutes) || 0))}.</p>`;
    }
    // A career player: their other competition, each with its own numbers and percentiles (never merged).
    const others = (p.also_in || []).filter(cid => cid !== p.cid && COMP.has(cid));
    const career = others.length ? `<p class="tx-cap tx-career">Also plays in ${others.map(cid => { const id = rowIdOf(p.gid, cid), q = PID.get(id), c = COMP.get(cid);
      return q ? `<button type="button" class="tx-lk" data-act="sel" data-pid="${esc(id)}" data-fid="car-${esc(id)}">${esc(c.name)} (${esc(c.level_words)}, ${esc(Math.round(q.minutes || 0))} min)</button>` : `${esc(c.name)} (${esc(c.level_words)}, no minutes yet)`; }).join(', ')}: numbers and percentiles stay per competition.${STORY.has(p.gid) ? ` ${esc(cap1(STORY.get(p.gid)))}.` : ''}</p>` : '';
    let sim;
    if (sm.st !== 'ok') sim = waitHtml(sm, 'similar players');
    else {
      const list = (sm.v.similar || []).filter(s => PID.has(s.row));
      sim = list.length ? `<ol class="tx-sim">${list.map(s => { const q = PID.get(s.row); return `<li><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(s.row)}" data-fid="sim-${esc(s.row)}">${esc(s.name)}</button>
        <span class="tx-dim">${esc(s.short_name)} ${esc(s.position)}${q.level !== p.level ? ` · ${esc(levelWords(q.level))}` : ''}${q.country !== p.country ? `, ${esc(q.country)}` : ''}</span><span class="tx-simbar" aria-label="similarity ${esc(s.similarity)}"><i data-w="${Math.max(2, Math.round(s.similarity * 100))}"></i></span><span class="num">${esc(Number(s.similarity).toFixed(2))}</span>
        <span class="tx-shared">${(s.shared_strengths || []).filter(k => MK.has(k)).map(k => `<button type="button" class="tx-kchip" data-act="ev" data-pid="${esc(s.row)}" data-mk="${esc(k)}" data-fid="sim-${esc(s.row)}-${esc(k)}">${esc(MK.get(k).label)}</button>`).join('')}</span></li>`; }).join('')}</ol>
        <p class="tx-cap">Similarity (1 = identical) on the ${esc(p.position === 'GK' ? 'goalkeeper' : 'outfield')} stats, among ${esc(S.scope === 'competition' ? `players in ${p.comp.name}` : S.scope === 'all' ? `all ${p.gender} at every level` : levelWords(p.level))} (the percentile setting in the players table); the chips are strengths they share (each plays that player's moments).${list.every(s => s.similarity < 0.5) ? ' No close match: every similarity is under 0.50.' : ''}</p>` : '<p class="tx-dim">No similar players (too few minutes, or too few regulars in this pool).</p>';
    }
    const html = `<div class="tx-card"><span class="tx-shirt" aria-hidden="true">${shirt(p)}</span>
        <div><p class="tx-name">${esc(p.name)}</p><p class="tx-line">${esc(p.club)} · ${esc(POS1[p.position])} (${esc(p.role)}) · #${esc(p.kit_number)}
          ${p.qualified ? `<span class="tx-tag" title="${esc(`At least ${mm == null ? 'the qualifying' : mm} minutes in ${p.comp.name}, so the player has percentiles`)}">Regular</span>` : `<span class="tx-tag dim">${esc(mm == null ? 'Not a regular yet' : `Under ${mm} minutes`)}</span>`}</p>
          <p class="tx-line tx-compl">${esc(p.comp.name)} · ${esc(p.country)} · <span class="tx-lv">${esc(levelWords(p.level))}</span>${isMine(p.level) ? ' <span class="tx-dim">· your level</span>' : ''}</p>
          <p class="tx-prof"><a href="/players/${esc(enc(p.gid))}">Open profile &rarr;</a></p></div></div>
      ${sample}${career}
      <dl class="tx-bio">${bio.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v ?? '–')}</dd></div>`).join('')}</dl>
      <div class="tx-acts"><button type="button" class="tx-mini" data-act="cmpwith" data-fid="card-cmp"${S.compare.length >= 3 && S.compare.includes(p.id) ? ' disabled' : ''}>Compare with…</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="highlights ${esc(p.name)}" title="Goals, shots, chances made, skills and defending in one reel">Highlights</button><button type="button" class="tx-mini" data-act="run" data-cmd="shots ${esc(p.name)}">Shots</button><button type="button" class="tx-mini" data-act="run" data-cmd="form ${esc(p.name)}">Form</button>
        <button type="button" class="tx-mini" data-act="team" data-cid="${esc(p.club_id)}">Team</button></div>
      ${best}
      <h3 class="tx-h3" id="txSimHead" tabindex="-1">Plays like</h3>${sim}`;
    paint('plyr', html, esc(p.short_name));
  }
  // One metric row: label (definition on hover), value button (evidence), percentile bar, and the percentile with the size
  // of its pool (the small flag under 15, none yet for a count of 0).
  function mrow(p, m, opts = {}) {
    const c = cellOf(p, m.key);
    const val = c ? `<button type="button" class="tx-n${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(m.key)}" data-fid="${esc((opts.fid || 'm') + '-' + p.id + '-' + m.key)}" aria-label="${esc(`${m.label} ${withUnit(m, c.value)}${c.percentile != null ? `, ${poolLine(p, c)}` : ''}, ${playTextC(m, c)}`)}">${esc(fmt(m, c.value))}</button>` : '<span class="tx-dim">–</span>';
    const pc = c ? c.percentile : null, np = c && noPct(p, m, c);
    const pcHtml = isNone(c) ? '<span class="tx-nyet">none yet</span>' : pc == null ? '–' : `${esc(pc)}<span class="tx-of"> · pool ${esc(poolSize(c))}</span>${smallPool(c) ? ' <span class="tx-small">small</span>' : ''}`;
    return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(m.key)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m, p)}</span>${unitMark(m)}</th><td class="num">${val}</td>
      <td class="tx-pbar"><span class="tx-bar" data-g="${GROUP_COL[m.group] || '#ffcd28'}"><i data-w="${pc == null ? 0 : Math.max(2, pc)}"></i></span></td><td class="num tx-pc" title="${esc(pc == null ? (np ? cap1(np.text) : '') : poolLine(p, c) + (smallPool(c) ? `: a small pool (under ${SMALL_POOL})` : ''))}">${pcHtml}</td></tr>`;
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
    const ctxText = players.length > 1 ? esc(`Comparing ${players.length}${outsider ? ` + ${lastName(outsider)}` : ''}`) : esc(`vs ${poolWordsFor(base)}`);
    if (waiting) { paint('radar', waitHtml(waiting, 'the percentiles'), ctxText); return; }
    const keys = (S.radar.tpl === 'all' ? CAT.default_columns.all : (CAT.default_columns[base.position] || CAT.default_columns.all)).filter(k => MK.has(k));
    // Compared players: the engine's warning and its best marks (one level: the best value; several levels and one
    // position: the best percentile, each in its own pool; several levels and positions: none).
    const cmp = players.length > 1 ? compareOf(players, keys, 'radar') : null, cv = cmp && cmp.st === 'ok' ? cmp.v : null;
    const bestOf = (k, p) => !!(cv && ((cv.best || {})[k] || []).includes(p.gid));
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
    const legend = players.map((p, j) => `<button type="button" class="tx-leg" data-c="${CMP_COL[players.length > 1 ? j : 0]}" data-act="sel" data-pid="${esc(p.id)}" data-fid="rl-${esc(p.id)}">${esc(p.name)} <span class="tx-dim">${esc(p.short_name)} ${esc(p.position)} · ${esc(levelWords(p.level))}</span></button>`).join('')
      + (outsider && !outsiderNote ? `<span class="tx-leg tx-legf">${esc(outsider.name)} <span class="tx-dim">${esc(outsider.short_name)} ${esc(outsider.position)} · selected, dashed</span></span>` : '');
    const outLine = outsider ? `<p class="tx-cap tx-rnote">${outsiderNote ? esc(outsiderNote) : `Comparing ${players.length}; ${esc(outsider.name)} (selected) is the dashed outline, not in the table.`} <button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(outsider.id)}" data-fid="r-add">Add to the comparison${players.length >= 3 ? ` (replaces ${esc(lastName(players[0]))})` : ''}</button></p>` : '';
    const tbl = players.length === 1 ? `<table class="tx-mt"><tbody>${keys.map(k => mrow(base, MK.get(k), { fid: 'r' })).join('')}</tbody></table>`
      : `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cmp"><thead><tr><th>Stat</th>${players.map((p, j) => `<th class="num" data-fg="${CMP_COL[j]}">${esc(initials(p))}</th>`).join('')}</tr></thead><tbody>
        ${keys.map(k => { const m = MK.get(k); return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(k)}">${esc(m.label)}${noisy(m)}</span>${unitMark(m)}</th>${players.map(p => { const c = cellOf(p, k), b = bestOf(k, p); return `<td class="num${b ? ' tx-best1' : ''}">${c ? `<button type="button" class="tx-n${zcC(c)}"${shade(m, c.percentile)} data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="rc-${esc(p.id)}-${esc(k)}" aria-label="${esc(`${p.name}, ${m.label} ${withUnit(m, c.value)}, ${c.percentile == null ? (noPct(p, m, c) || { text: 'no percentile' }).text : poolLine(p, c)}${b ? ', the best of the comparison' : ''}, ${playTextC(m, c)}`)}">${esc(fmt(m, c.value))}</button><span class="tx-pc" title="${esc(c.percentile == null ? cap1((noPct(p, m, c) || { text: 'no percentile' }).text) : poolLine(p, c))}"> ${isNone(c) ? '<span class="tx-nyet">none yet</span>' : c.percentile == null ? '–' : `${esc(c.percentile)}<span class="tx-of"> · pool ${esc(poolSize(c))}</span>${smallPool(c) ? ' <span class="tx-small">small</span>' : ''}`}</span>${b ? '<span class="tx-bestm" title="The best of the comparison, by the engine\'s rule"> ★</span>' : ''}` : '<span class="tx-dim">–</span>'}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div>
        ${cv && Object.keys(cv.best || {}).length ? '<p class="tx-cap">★ the best of the comparison, by the engine\'s rule: the best value within one level, the best percentile (each in its own pool) across levels.</p>' : ''}`;
    const html = `<div class="tx-ctls"><div class="tx-seg" role="group" aria-label="Stats"><button type="button" data-act="rtpl" data-v="pos" aria-pressed="${S.radar.tpl === 'pos'}">${esc(POS1[base.position])} stats</button><button type="button" data-act="rtpl" data-v="all" aria-pressed="${S.radar.tpl === 'all'}">All-round</button></div></div>
      <div class="tx-legs">${legend}</div>${outLine}${crossWarn(players, cv)}${blank.map(p => `<p class="tx-cap tx-rnote">${esc(`${p.name} has no outline: ${whyBlank(p)}. The table has the values.`)}</p>`).join('')}${svg}
      <p class="tx-cap">/90 = per 90 minutes. ${players.length > 1 ? `Each percentile is against the player's own pool: regulars in their position ${S.scope === 'competition' ? 'in their competition' : S.scope === 'all' ? 'across every level of their gender' : 'at their level'}, with its size beside it` : `Percentile among regular ${esc(poolWordsFor(base))}; blue-grey wedges are style markers (ranked, not judged)`}.${gaps ? ` ${players.length > 1 ? 'A gap in an outline' : 'An empty wedge'} is a stat with no percentile for that player (the table and its tips say why), never the 0th.` : ''} Values play their moments.</p>${tbl}`;
    paint('radar', html, ctxText);
  }

  // The engine's comparison of two or three rows (its warning and best marks), in their competitions and the scope shown.
  function compareOf(players, keys, panel) {
    const gids = players.map(p => p.gid);
    if (new Set(gids).size !== gids.length) return null;          // one player's two rows: no comparison call
    const q = `ids=${gids.map(enc).join(',')}&competitions=${players.map(p => enc(p.cid)).join(',')}&scope=${enc(S.scope)}&metrics=${keys.slice(0, COLS_PER_CALL).map(enc).join(',')}`;
    return want(`cmp|${q}`, () => R.api(`/api/catalogue/compare?${q}`), panel);
  }
  // Comparing players from different levels (or genders, or positions): say how to read it, every time, with the engine's
  // own warning.
  function crossWarn(players, cv) {
    if (players.length < 2) return '';
    const lv = [...new Set(players.map(p => p.level))], gd = new Set(players.map(p => p.gender)), ps = new Set(players.map(p => p.position));
    const parts = [];
    if (lv.length > 1) parts.push(`Different levels (${listText(lv.map(levelWords))}): each percentile is against the player's own pool, and a raw number from one level is not better or worse than the same number from another.`);
    if (gd.size > 1) parts.push('Men and women never share a pool.');
    if (ps.size > 1) parts.push('Different positions: each is ranked against their own position.');
    if (!parts.length && cv && cv.warning) parts.push(cap1(cv.warning) + '.');
    return parts.length ? `<p class="tx-warn tx-mixed" role="note">${esc(parts.join(' '))}</p>` : '';
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
      : `<p class="tx-dim">No minutes in ${esc(p.comp.name)}.</p>`;
    paint('shot', html, esc(`${p.name} · ${plural(shots.length, 'shot')}`));
  }
  function shotReel(p, start) {
    const c = shotsOf(p.id);
    if (c.st !== 'ok') return;
    const shots = c.v.shots || [];
    const r = { kind: 'shots', pid: p.id, title: `${p.name} · Shots`, sub: `${plural(shots.length, 'shot')}, penalties included`, i: -1, note: '',
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
      <p class="tx-cap">${esc(total)} ${p.cid === ENG ? 'on-ball actions in league matches this season' : `on-ball actions in ${esc(p.comp.name)}'s uploaded matches`} (${esc(listText(evs))}), so more than the Touches count, which is touch records only. Attacking left to right, ${esc(cols)} by ${esc(rows)} cells. The map has no clip per cell; the numbers above play their moments.</p>`;
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
    if (!matches.length) { paint('form', `<p class="tx-dim">No matches in ${esc(p.comp.name)}.</p>`, esc(p.name)); return; }
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
  // Raw numbers compare only within one level, so the scatter shows one level at a time: the table's level when it shows
  // one, else the selected player's level when the filters include it, else the first level the filters include.
  function scatLevel() {
    const lv = levelsIn(S.scr.where), f = PID.get(S.focus);
    return lv.length === 1 ? lv[0] : lv.includes(f.level) ? f.level : lv[0] || f.level;
  }
  function scatPoints() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y);
    const c = scatOf(x, y, pos, scatLevel(), 'scat');
    if (c.st !== 'ok') return null;
    // A regular with a value on both: a percentile, or a count of 0 (none yet) for a regular the stat is scored for.
    const ok = (m, pct, pool, p) => m.has_percentile ? (pct != null || (p.qualified && !(pool && pool.reason))) : p.qualified;
    return (c.v.points || []).map(pt => ({ p: PID.get(rowIdOf(pt.global_id, pt.competition_id)) || { ...pt, id: pt.global_id },
      a: { value: pt.x, percentile: pt.x_percentile, evidence_total: pt.x_evidence_total, pool: pt.x_pool }, b: { value: pt.y, percentile: pt.y_percentile, evidence_total: pt.y_evidence_total, pool: pt.y_pool } }))
      .filter(o => o.a.value != null && o.b.value != null && o.p.minutes > 0 && (all || (ok(mx, o.a.percentile, o.a.pool, o.p) && ok(my, o.b.percentile, o.b.pool, o.p))))
      .sort((u, v) => u.a.value - v.a.value || u.b.value - v.b.value);
  }
  function renderScat() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y), pts = scatPoints(), LV = scatLevel();
    const many = levelsIn(S.scr.where).length > 1;
    const ctxText = esc(`${shortLabel(mx)} against ${shortLabel(my)}`);
    if (!pts) { paint('scat', waitHtml(scatOf(x, y, pos, LV, 'scat'), 'the scatter'), ctxText); return; }
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
      : '<p class="tx-read tx-dim">The selected player is not on this chart (another level, position, or not a regular). Arrow keys in the chart pick a player.</p>';
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span>X</span><select data-r="scx" data-fid="scat-xs">${metricOptions(x)}</select></label>
        <label class="tx-ctl"><span>Y</span><select data-r="scy" data-fid="scat-ys">${metricOptions(y)}</select></label>
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scpos" data-v="${v || ''}" aria-pressed="${pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-chk"><input type="checkbox" data-r="scall" data-fid="scat-all"${all ? ' checked' : ''}> Include non-regulars</label></div>${svg}${read}
      <p class="tx-cap">${pts.length} ${esc(pos ? POSN[pos] : 'players')} · ${esc(levelWords(LV))}${(S.scr.where || {}).country ? ` in ${esc(S.scr.where.country)}` : ''}${(S.scr.where || {}).competition && COMP.has(S.scr.where.competition) ? ` in ${esc(COMP.get(S.scr.where.competition).name)}` : ''}${all ? '' : ', regulars with a value on both'} · dashed lines = medians · click a dot to select</p>
      ${many ? `<p class="tx-cap tx-dim">One level at a time: raw numbers compare only within a level. The filters in the players table cover more than one level, so this shows ${esc(levelWords(LV))}${LV === PID.get(S.focus).level ? ', the selected player\'s' : ''}.</p>` : ''}`;
    paint('scat', html, ctxText);
  }

  // ------------------------------------------------------------------ Team: team style
  // The shots behind a team's shot-based numbers (GET /api/teams/{club}/shots, with competition= for a catalogue club):
  // 'for' is the club's own players, 'against' their opponents in the club's matches.
  const TEAM_SHOTS = {
    xg_for: { side: 'for', v: 'xg' }, npxg_for: { side: 'for', v: 'xg', keep: (s) => !s.penalty }, penalty_xg: { side: 'for', v: 'xg', keep: (s) => s.penalty },
    xg_against: { side: 'against', v: 'xg' }, goals_for: { side: 'for', v: 'n', keep: (s) => s.outcome === 'goal' },
    goals_against: { side: 'against', v: 'n', keep: (s) => s.outcome === 'goal' }, shots_for: { side: 'for', v: 'n' }, shots_against: { side: 'against', v: 'n' },
  };
  // A club's team numbers: the Regista League's from /api/teams; a catalogue club's from its style, once loaded.
  function teamOf(cid) {
    if (TEAMS.has(cid)) return TEAMS.get(cid);
    const st = C.get('style|' + cid);
    return st && st.st === 'ok' ? st.v : null;
  }
  // What a team number opens, when that is known without a request: { n, unit }, or null. Its shots once loaded (a
  // shot-based number with a season total of 0 opens nothing), its set-piece shots or its matches once the style is in.
  function teamCount(cid, tk) {
    const t = teamOf(cid), v = t && t.values[tk], spec = TEAM_SHOTS[tk];
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
  // Every club in the catalogue, grouped by country and competition.
  function clubSelect() {
    const byComp = new Map();
    for (const c of CID.values()) if (c.competition_id) { if (!byComp.has(c.competition_id)) byComp.set(c.competition_id, []); byComp.get(c.competition_id).push(c); }
    return `<label class="tx-ctl tx-clubsel"><span>Club</span><select data-r="club" data-fid="team-club">${COUNTRIES.map(co => [...COMP.values()].filter(c => c.country === co).map(comp => {
      const cl = (byComp.get(comp.competition_id) || []).slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
      return cl.length ? `<optgroup label="${esc(`${co} · ${comp.name} (${comp.level_words})`)}">${cl.map(x => `<option value="${esc(x.club_id)}"${x.club_id === S.club ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</optgroup>` : '';
    }).join('')).join('')}</select></label>`;
  }
  const upl = (n) => `${n} uploaded ${n === 1 ? 'match' : 'matches'}`;
  const squadHtml = (list) => `<div><h3 class="tx-h3">Squad by minutes</h3><ol class="tx-squad tx-scroll">${list}</ol></div>`;
  function renderTeam() {
    if (!TEAMS.has(S.club)) { renderTeamCat(); return; }
    const t = TEAMS.get(S.club), c = club(S.club), row = (SEASON.table || []).find(r => r.club_id === S.club) || {};
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
    const squad = PLAYERS.filter(p => p.club_id === S.club && p.cid === ENG).sort((a, b) => b.minutes - a.minutes);
    const unplayed = ((club(S.club).squad) || []).filter(s => !PID.has(rowIdOf(s.global_id, ENG)));
    const html = `<div class="tx-ctls">${clubSelect()}</div>
      <p class="tx-name">${esc(c.name)} <span class="tx-dim">${esc(ord(row.position || 0))} · ${esc(row.points)} pts · ${esc(row.won)}-${esc(row.drawn)}-${esc(row.lost)} · ${esc(row.goals_for)}:${esc(row.goals_against)}</span></p>
      <p class="tx-cap">${esc(compLine(ENG))} · every league match uploaded (${esc((SEASON.rounds || []).reduce((n, r) => n + (r.matches || []).length, 0))} fixtures)</p>
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style</th><th class="num">Value</th><th class="num">Rank</th><th class="num">League avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        ${squadHtml(`${squad.map(p => `<li class="${p.id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-fid="sq-${esc(p.id)}">${esc(p.name)}</button><span class="tx-dim">${esc(p.position)} #${esc(p.kit_number)}</span><span class="num">${esc(Math.round(p.minutes))}′</span></li>`).join('')}${unplayed.map(s => `<li><span class="tx-dim">${esc(s.name)}</span><span class="tx-dim">${esc(s.position)} #${esc(s.kit_number)}</span><span class="num tx-dim">0′</span></li>`).join('')}`)}</div>
      <p class="tx-cap">Rank 1 = best${lowBest.length ? `: the lowest for ${esc(listText(lowBest))}` : ''}. Grey markers are style, ranked but not judged, and their rank 1 is the highest. The bar spans the league's clubs; the white tick is the league average. /90 = per 90 minutes; possession, PPDA and the other ratios are season values over every match (hover a name for its definition). Shot numbers (xG, goals, shots) play every shot behind them; the others list one value per match, without a clip.</p>`;
    paint('team', html, esc(c.short_name));
  }
  // A club outside the Regista League: its team style in its uploaded matches (GET /api/teams/{club}/style?competition=),
  // ranked by the engine within the competition's clubs with uploads and within the level; the bar spans the competition's
  // clubs (GET /api/teams?competition=); the record and the squad's minutes are the uploaded matches' only, not a league
  // table (GET /api/competitions/{id}).
  function renderTeamCat() {
    const c = club(S.club), cid = c.competition_id, comp = COMP.get(cid) || { name: cid, level_words: '' };
    const st = styleOf(S.club, 'team'), tl = teamsIn(cid, 'team'), cp = compOf(cid, 'team');
    const head = (res) => `<div class="tx-ctls">${clubSelect()}</div>
      <p class="tx-name">${esc(c.name)} ${res ? `<span class="tx-dim">${esc(upl(res.played))} · ${esc(res.won)}-${esc(res.drawn)}-${esc(res.lost)} · ${esc(res.goals_for)}:${esc(res.goals_against)}</span>` : ''}</p>
      <p class="tx-cap">${esc(compLine(cid))} · ${esc((cp.v && cp.v.results_note) || 'uploaded matches only, not a league table')}</p>`;
    if (cp.st !== 'ok') { paint('team', head(null) + waitHtml(cp, `${c.name}'s competition`), esc(c.short_name)); return; }
    const res = (cp.v.results || []).find(r => r.club_id === S.club);
    const sq = (((cp.v.clubs || []).find(x => x.club_id === S.club) || {}).squad || []).slice().sort((a, b) => (b.minutes || 0) - (a.minutes || 0));
    const squad = squadHtml(sq.map(s => { const id = rowIdOf(s.global_id, cid), q = PID.get(id); return q && s.minutes > 0
      ? `<li class="${id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(id)}" data-fid="sq-${esc(id)}">${esc(s.name)}</button><span class="tx-dim">${esc(s.position)} #${esc(s.kit_number)}</span><span class="num">${esc(Math.round(s.minutes))}′</span></li>`
      : `<li><span class="tx-dim">${esc(s.name)}</span><span class="tx-dim">${esc(s.position)} #${esc(s.kit_number)}</span><span class="num tx-dim">0′</span></li>`; }).join('') || '<li class="tx-dim">Nobody has played in an uploaded match.</li>');
    if (st.st === 'err' && st.e && st.e.status === 404) { paint('team', `${head(res)}<p class="tx-dim">No team numbers: this club has no uploaded match yet.</p><div class="tx-team">${squad}</div>`, esc(c.short_name)); return; }
    if (st.st !== 'ok' || tl.st !== 'ok') { paint('team', head(res) + waitHtml(st.st !== 'ok' ? st : tl, `${c.name}'s team numbers`), esc(c.short_name)); return; }
    const t = st.v, all = tl.v.teams || [];
    const vals = (k) => all.map(x => x.values && x.values[k] && x.values[k].value).filter(v => v != null);
    const rows = (CAT.team_metrics || []).map(m => {
      const v = t.values[m.key]; if (!v || v.value == null) return '';
      const vs = vals(m.key), lo = Math.min(...vs, v.value), hi = Math.max(...vs, v.value), w = hi === lo ? 50 : 4 + 92 * (v.value - lo) / (hi - lo);
      const mean = hi === lo ? 50 : 4 + 92 * (v.league_mean - lo) / (hi - lo);
      const judged = m.higher_is_better !== null, good = judged && v.rank <= 2 && v.of > 2, tc = teamCount(S.club, m.key), zero = !!tc && tc.n === 0;
      return `<tr><th scope="row"><span class="tx-ml" data-tk="${esc(m.key)}" data-cid="${esc(S.club)}">${esc(m.label)}</span>${m.kind === 'per90' ? '<span class="tx-dim tx-u"> /90</span>' : ''}</th>
        <td class="num"><button type="button" class="tx-n${zero ? ' z' : ''}" data-act="tev" data-cid="${esc(S.club)}" data-tk="${esc(m.key)}" data-fid="tv-${esc(m.key)}" aria-label="${esc(`${c.name}, ${m.label} ${fmt(m, v.value)}, rank ${v.rank} of ${v.of} in ${comp.name}${v.level_rank ? `, ${v.level_rank} of ${v.level_of} at the level` : ''}. ${zero ? 'Nothing behind it to play' : 'Open what is behind it'}`)}">${esc(fmt(m, v.value))}</button></td>
        <td class="num ${good ? 'up' : ''}">${esc(v.rank)}/${esc(v.of)}</td><td class="num tx-dim">${v.level_rank ? `${esc(v.level_rank)}/${esc(v.level_of)}` : '–'}</td><td class="num tx-dim">${esc(fmt(m, v.league_mean))}</td>
        <td class="tx-pbar"><span class="tx-range"><i data-l="${w.toFixed(1)}" class="${judged ? '' : 'style'}"></i><b data-l="${mean.toFixed(1)}"></b></span></td></tr>`;
    }).join('');
    const smp = t.sample || {};
    const html = `${head(res)}${smp.small ? `<p class="tx-warn">Small sample: ${esc(upl(smp.matches || 0))} of the ${esc(smp.competition_matches)} uploaded in ${esc(comp.name)}. Read these numbers with care.</p>` : `<p class="tx-cap">Sample: ${esc(upl(smp.matches || 0))} of the ${esc(smp.competition_matches)} uploaded in ${esc(comp.name)}.</p>`}
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style</th><th class="num">Value</th><th class="num" title="${esc(`Rank among ${comp.name}'s clubs with uploads`)}">Rank</th><th class="num" title="${esc(`Rank among every club at ${comp.level_words} with uploads`)}">Level</th><th class="num" title="${esc(`${comp.name} average`)}">Avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        ${squad}</div>
      <p class="tx-cap">Rank 1 = best within ${esc(comp.name)}'s ${esc(all.length)} clubs with uploads; Level ranks it among every club at ${esc(comp.level_words)}. Grey markers are style, ranked but not judged. The bar spans the competition's clubs; the white tick is its average. Shot numbers (xG, goals, shots) play every shot behind them; the others list one value per uploaded match.</p>`;
    paint('team', html, esc(c.short_name));
  }
  const teamUnit = (m) => m.kind === 'per90' ? 'per 90' : m.unit === '%' ? '' : m.unit;
  async function teamReel(cid, tk) {
    const m = TK.get(tk);
    if (!TEAMS.has(cid)) await settle(styleOf(cid));
    const t = teamOf(cid), v = t && t.values[tk];
    if (!t || !m || !v) return null;
    const u = teamUnit(m), comp = teamComp(cid), cname = comp && COMP.has(comp) ? COMP.get(comp).name : '';
    const r = { title: `${t.club} · ${m.label}`, sub: `${fmt(m, v.value)}${u ? ' ' + u : ''} · rank ${v.rank} of ${v.of}${cname ? ` in ${cname}` : ''}${v.total != null ? ` · ${Number(Number(v.total).toFixed(2))} in total` : ''}`, i: -1, items: [], note: '' };
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
      r.note = !hits.length ? `No ${noun === 'penalty' ? 'penalties' : noun + 's'} behind this number ${comp ? 'in the uploaded matches' : 'this season'}.`
        : `Every ${spec.side === 'for' ? '' : 'opponent '}${noun} behind this number, each with its clip${match ? `; they add up to the ${comp ? 'total' : 'season total'} (${tot(v.total != null ? v.total : sum)})` : `; they add up to ${tot(sum)}, the engine's total is ${tot(v.total)}`}.`;
      return r;
    }
    if (tk === 'set_piece_xg' || tk === 'set_piece_shots') {
      const st = await settle(styleOf(cid));
      if (!st) { C.delete('style|' + cid); r.note = 'The set-piece shots did not load. Pick the number again to retry.'; return r; }
      const ev = (st.evidence || {}).set_piece_xg || [];
      r.items = ev.map(e => ({ when: matchFor(e.match_id, cid).when, minute: e.minute, val: `xG ${Number(e.xg != null ? e.xg : e.value).toFixed(2)}`, note: [e.name, OUTC[e.outcome]].filter(Boolean).join(' · '), video: e.video_url || null, match_id: e.match_id }));
      r.note = ev.length ? 'Every set-piece shot behind this number, each with its clip.' : `No set-piece shots ${comp ? 'in the uploaded matches' : 'this season'}.`;
      return r;
    }
    const st = await settle(styleOf(cid));
    if (!st) { C.delete('style|' + cid); r.note = 'The matches did not load. Pick the number again to retry.'; return r; }
    r.items = (st.per_match || []).map(pm => ({ when: `R${pm.round} ${pm.home ? 'v' : 'at'} ${short(pm.opponent)}`, minute: null, val: fmt(m, pm.values[tk]), note: m.kind === 'per90' ? 'per 90 of the match' : "the match's value", video: null, match_id: pm.match_id }));
    r.unit = 'match';
    r.note = m.kind === 'ratio' ? 'A team-style ratio is built from every possession of a match: one value per match, no single clip.'
      : `One value per ${comp ? 'uploaded ' : ''}match; the events behind this number are not listed here.`;
    return r;
  }
  async function openTeamReel(cid, tk) {
    const m = TK.get(tk), c = club(cid);
    if (!m || !CID.has(cid)) return;
    const g = gen;
    reelLoading(`${c.name} · ${m.label}`);
    const r = await teamReel(cid, tk);
    if (r) openReel(r, 0, g === gen);
    else { reel = { title: `${c.name} · ${m.label}`, sub: '', items: [], i: -1, note: 'This number did not load. Pick it again to retry.' }; renderClips(); }
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
      return `<p class="tt-h">${esc(m.label)}${c.noisy ? ' <span class="tt-w">≈ small sample</span>' : ''}</p><p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : ''} · ${c.percentile == null ? esc(np ? np.text : 'no percentile') : esc(poolLine(p, c) + (smallPool(c) ? ' (a small pool)' : ''))}</p>${zeroC(c) ? '<p class="tt-s">No moments behind this number</p>' : n ? `<p class="tt-play">&#9654; ${esc(n)} · Enter plays them</p>` : '<p class="tt-play">&#9654; Enter plays its moments</p>'}<p class="tt-s">The column header has the definition</p>`;
    }
    const src = (m.sources || []).map(s => ((CAT.sources || {})[s] || {}).title || s).join('; ');
    const judge = m.higher_is_better === null ? 'Style marker: ranked, not judged' : m.higher_is_better ? 'Higher is better' : 'Lower is better';
    let h = `<p class="tt-h">${esc(m.label)}</p><p>${esc(m.definition)}</p>
      <p class="tt-s"><b>Rule</b> ${esc(m.rule)}${src ? ` · <b>Source</b> ${esc(src)}` : ''}</p><p class="tt-s">${esc(mk ? unitText(m) : m.unit)} · ${esc(judge)}${mk && m.positions ? ` · matters for ${esc(m.positions.join(' '))}` : ''}</p>`;
    const p = el.dataset.pid && PID.get(el.dataset.pid), c = p && mk ? cellOf(p, mk) : null, who = p || PID.get(S.focus);
    // ≈ as the engine marks it for this row (or the selected player's level); the league's split-half r is shown only
    // for the league's own flag.
    if (mk && (c ? c.noisy : noisyAt(m))) h += `<p class="tt-w">≈ Small sample, read with care: at ${esc(who ? levelWords(who.level) : 'this level')} one season cannot yet separate players in the same role on this stat (split-half reliability below ${esc((CAT.season.reliability || {}).noise_r)}).</p>`;
    if (mk && m.min_attempts) h += `<p class="tt-s">A percentile needs a minimum number of attempts, scaled to each competition's minutes (${esc(m.min_attempts)} in the Regista League: ${esc(m.min_attempts_rule)})</p>`;
    if (c) h += `<p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : c.total != null && m.kind !== 'total' ? ` (${esc(c.total)} in total)` : ''} · ${c.percentile == null ? esc((noPct(p, m, c) || { text: 'no percentile' }).text) : esc(poolLine(p, c) + (smallPool(c) ? ' (a small pool)' : ''))} · ${esc(p.comp.name)}</p>`;
    const tv = tk && el.dataset.cid ? teamOf(el.dataset.cid) : null;
    if (tv && tv.values[tk]) h += `<p class="tt-p">Rank ${esc(tv.values[tk].rank)} of ${esc(tv.values[tk].of)}${tv.values[tk].level_rank ? ` · ${esc(tv.values[tk].level_rank)} of ${esc(tv.values[tk].level_of)} at the level` : ''} · ${TEAMS.has(el.dataset.cid) ? 'league' : 'competition'} average ${esc(fmt(m, tv.values[tk].league_mean))}</p>`;
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
  const altsHtml = (alts, head) => alts && alts.length ? ` <span class="tx-dim">· also:</span> ${alts.slice(0, 6).map(p => runBtn(`${cmdWord(head) ? cmdWord(head) + ' ' : ''}${p.name}`, `${p.name} ${p.short_name}${p.level ? ` · ${levelWords(p.level)}` : ''}`)).join(' ')}` : '';
  function onePlayer(arg) {
    if (!arg.trim()) return { p: PID.get(S.focus), alts: [] };
    const r = W.resolvePlayer(arg);
    if (r.p) return r;
    out(`No player called "${arg}". Type part of a name; suggestions appear as you type.`, 'err');
    return null;
  }
  const posText = (pos) => pos ? POSN[pos] : 'players';
  const PANEL_CMD = { SIM: 'plyr', SHOT: 'shot', FORM: 'form', HEAT: 'heat', RDR: 'radar', PLYR: 'plyr' };
  // Commands that read their own arguments: a place inside them is read there ("rank women forwards goals", "plot npxG
  // against xA in academy"); the others name players or clubs.
  const OWN_ARGS = new Set(['RANK', 'SCAT', 'CMP', 'TEAM', 'HELP', 'HL', ...TW.PANEL_HEADS]);
  // True while a search's own place words set the filters (so a ranking after it does not call them carried over).
  let placeFresh = false;
  async function run(text) {
    const t = String(text || '').trim().replace(/\s*<GO>$/i, '').replace(/[?!.]+$/, '').trim().slice(0, 200); if (!t) return;
    const g = ++gen;
    placeFresh = false;
    if (store.hist[store.hist.length - 1] !== t) { store.hist.push(t); if (store.hist.length > 50) store.hist.shift(); save(); }
    histAt = -1;
    // Place and level words ("U19 midfielders in Spain", "women forwards", "players in Nigeria", "my level") set the
    // table's filters; what is left is searched as usual. A player's or club's exact name always wins.
    if (!OWN_ARGS.has(TW.parseHead(t).head)) {
      const pl = TP.parse(t, V);
      const exactClub = [...CID.values()].some(c => norm(c.name) === norm(t) || norm(c.short_name) === norm(t));
      if (pl.found && !exactClub && !W.resolvePlayer(t, true).p) return placeQuery(pl, g);
    }
    return runIntent(W.interpret(t), t, g, '');
  }
  async function runIntent(it, t, g, note) {
    if (it.do === 'help') { openHelp(); out('Help is open. Escape closes it.'); return; }
    if (it.do === 'rank') return cmdRank(it.rest, null, { note });
    if (it.do === 'rankKey') return cmdRank('', it.club, { m: MK.get(it.key), pos: it.pos, most: it.most, fewest: it.fewest, worst: it.worst, note });
    if (it.do === 'minutes') return rankMinutes(it.pos, it.club, note);
    if (it.do === 'cmp') return cmdCmp(it.rest);
    if (it.do === 'scat') return cmdScat(it.rest);
    if (it.do === 'team' || it.do === 'club') {
      const c = it.club || W.resolveClub(it.rest) || (it.rest ? null : club(S.club));
      if (!c || !c.club_id) { out(`No club called "${it.rest}". Type part of a club's name; suggestions appear as you type.`, 'err'); return; }
      return team(c, teamText(c));
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
      out('', 'err', `"${esc(t)}" could be ${it.keys.length} stats: ${ms.map(m => it.p ? runBtn(`${it.p.name} ${m.label}`, m.label) : runBtn(`rank ${pw(m)} ${m.key}`, m.label)).join(' ')}${esc(note)}`);
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
      else if (head === 'SHOT') { const sh = (shotsOf(p.id).v || {}).shots || []; line = `${p.name}: ${plural(sh.length, 'shot')}, ${plural(sh.filter(s => s.outcome === 'goal').length, 'goal')} in ${p.comp.name}. Each shot plays its clip.`; }
      else if (head === 'FORM') line = `${p.name}: ${plural(p.appearances || 0, 'match')} in ${p.comp.name}. Each bar plays that match's moments.`;
      else if (head === 'HEAT') line = `${p.name}: where they have the ball in ${p.cid === ENG ? 'league matches' : `${p.comp.name}'s uploaded matches`}, attacking left to right.`;
      else if (head === 'RDR') line = `${p.name}: percentiles against regular ${poolWordsFor(p)}.`;
      else line = rowLine(p) + '.';
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
      out('', '', esc(rowLine(p)) + altsHtml(it.alts, ''));
      // Bring the card and the player's numbers into view, not just the card's top strip.
      showPanel('plyr', true, '.tx-best');
      return;
    }
    out(`Nothing found for "${t}". Try a surname, a club, a stat such as "goals" or "most xG", "best finishers", a place such as "U19 midfielders in Spain", "${lastName(PID.get(S.focus))} highlights" or "Toure vs Ustinov". Help lists everything.${note}`, 'err');
    // Keep what was typed, selected, so a typo is one keystroke away from fixed.
    const inp = $('txIn');
    if (document.activeElement === inp && !inp.value) { inp.value = t; inp.select(); }
  }
  const teamText = (k) => TEAMS.has(k.club_id) ? `${k.name}: how they play, ranked across the Regista League's clubs.`
    : `${k.name} (${compLine(k.competition_id)}): how they play in their uploaded matches, ranked within their competition and their level.`;
  const unknownNote = (pl) => (pl.unknown.length ? ` The catalogue has no ${listText(pl.unknown)} competition, so that word was left out.` : '')
    + (pl.young === 'academy' ? ` "Young" was read as the academy levels (${listText([...new Set([...COMP.values()].filter(c => c.tier === 'academy').map(c => c.age_group))].sort())}).` : '')
    + (pl.young === 'dropped' ? ' "Young" was left out: the level you named sets the ages.' : '');
  const FILLER = /^(best|top|the|all|show|me|find|list|who|are|is|good|great|leading|any|every|some|of)$/;
  // A question with place words: set the filters, then search what is left (nothing, a position, a stat, a question).
  async function placeQuery(pl, g) {
    if (pl.unknown.length && !Object.keys(pl.where).length && !pl.reset) {
      out(`The catalogue has no ${listText(pl.unknown)} competition. Its age groups: ${((IX.levels || {}).age_groups || []).map(a => a.key).join(', ')}.`, 'err'); return;
    }
    S.scr.where = { ...pl.where }; scrAct = null; save(); placeFresh = true;
    const note = unknownNote(pl), rest = pl.rest.trim();
    const toks = rest.split(' ').filter(w => w && !FILLER.test(w));
    const firstCol = (pos) => { const key = pos === 'ALL' ? 'all' : pos; return (CAT.default_columns[key] || CAT.default_columns.all).find(x => MK.has(x)); };
    if (!toks.length) {
      if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
      if (visible('scat')) renderScat();
      out(`Showing ${whereWords(S.scr.where)}: loading…`);
      await settle(tableData(S.scr.cols.filter(k => MK.has(k))).ord);
      if (g !== gen) return;
      const n = screenRows().length;
      out(n ? `Showing ${whereWords(S.scr.where)}: ${n} ${S.scr.pos ? POSN[S.scr.pos] : 'players'}${S.scr.qual ? ' (regulars)' : ''}.${note}` : emptyText() + note, n ? '' : 'err');
      showPanel('scrn', true, scrollTable(null));
      return;
    }
    // What is left, read as the search box reads it ("best defenders" ranks defenders on what defenders are judged by);
    // a position alone ranks it on its first column.
    const it = W.interpret(rest);
    if (['rank', 'rankKey', 'minutes', 'many'].includes(it.do)) return runIntent(it, rest, g, note);
    if (toks.length === 1 && posOf(toks[0])) { const pos = posOf(toks[0]); return cmdRank('', null, { m: MK.get(firstCol(pos)), pos, note }); }
    // A position named among words the search does not know: rank that position and say what was left out, rather than
    // keep the position from before ("best young defenders in Ghana" once listed forwards).
    const pw = toks.find(w => posOf(w));
    if (pw) { const pos = posOf(pw), left = toks.filter(w => w !== pw).join(' '); return cmdRank('', null, { m: MK.get(firstCol(pos)), pos, note: `${note}${left ? ` "${left}" was not understood, so it was left out.` : ''}` }); }
    if (it.do !== 'none') return runIntent(it, rest, g, note);
    if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
    out(`Showing ${whereWords(S.scr.where)}. Nothing found for "${rest}": try a position, a stat or a question, for example "best dribblers".${note}`, 'err');
  }
  // "Toure goals": the moments behind that player's number, or, for a number with nothing behind it, the reason.
  async function openStat(p, k, alts, g) {
    const m = MK.get(k); if (!p || !m) return;
    out(`${p.name}: loading…`);
    await settle(full(p.id));
    if (g !== gen) return;
    select(p.id, true);
    const c = cellOf(p, k);
    if (zeroC(c)) { out('', '', esc(`${p.name}: ${m.label} ${c ? withUnit(m, c.value) : '–'} in ${p.comp.name}, so there are no moments to play.`) + altsHtml(alts, '')); return; }
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
  // The filters said after a ranking: kept from an earlier search, or the scout's own level.
  function carriedText(fresh) {
    const w = S.scr.where || {};
    if (fresh || !W_FIELDS.some(([k]) => w[k])) return '';
    return sameWhere(w, mineWhere()) ? ` At your level, ${levelWords(MINE_KEY())}: Whole catalogue shows every level.` : ` Still ${whereWords(w)} from your last search · Whole catalogue to clear.`;
  }
  async function cmdRank(rest, cl, given) {
    given = given || {};
    let note = given.note || '', fresh = placeFresh;
    let pos = null, m = null;
    if (given.m) { m = given.m; pos = given.pos || null; }
    else {
      // Place words inside a rank command ("rank women forwards goals", "rank forwards goals in academy").
      const pl = TP.parse(rest, V);
      if (pl.found) { S.scr.where = { ...pl.where }; rest = pl.rest; note += unknownNote(pl); fresh = true; }
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
    if (!m) { out('Rank needs a stat.', 'err'); return; }
    if (!pos && gkOnly(m)) pos = 'GK';
    // "most yellow cards": the most first, though fewer is better; "fewest goals conceded", "lowest xG": the smallest
    // first; "worst finishers": the better way reversed; otherwise a stat ranks its better way first.
    const lowerBetter = m.higher_is_better === false, end = given.most ? 'most' : given.fewest ? 'fewest' : given.worst ? 'worst' : null;
    const low = end === 'most' ? false : end === 'fewest' ? true : end === 'worst' ? !lowerBetter : lowerBetter;
    const why = end === 'worst' ? ' (worst first)' : low ? (lowerBetter ? ' (lowest first: lower is better)' : ' (fewest first; more is better)')
      : lowerBetter ? ' (most first; fewer is better)' : '';
    const g = gen;
    S.scr.pos = pos === 'ALL' ? null : pos;
    // The ranked column goes first, so the order of the rows is explained by the first number the scout reads (at 375 px
    // only one stat column fits).
    S.scr.cols = [m.key, ...S.scr.cols.filter(k => k !== m.key)].slice(0, MAX_COLS);
    S.scr.sort = { k: m.key, dir: low ? 1 : -1 };
    // A club filter ("best finishers at Brookfield") goes in the table's own filter box, where it shows and clears; when
    // the filters leave the club out, they move to the club's level.
    S.scr.q = cl ? cl.name : ''; scrAct = null;
    if (cl && !inWhere(COMP.get(cl.competition_id))) { const cc = COMP.get(cl.competition_id); if (cc) { S.scr.where = { tier: cc.tier, age_group: cc.age_group, gender: cc.gender }; note += ` The filters moved to ${cc.level_words}, ${cl.name}'s level.`; fresh = true; } }
    save();
    if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
    if (visible('scat')) renderScat();
    out(`Ranking by ${m.label}: loading…`);
    const td = tableData(S.scr.cols.filter(k => MK.has(k)));
    const got = await settle(td.ord);
    await Promise.all(td.extra.map(settle));
    if (g !== gen) return;    // a newer command or a picked player took over meanwhile
    if (!got) { out(`The ranking by ${m.label} did not load (${errText(td.ord.e)}).`, 'err'); renderScrn(); return; }
    const rows = screenRows();
    // The active cell is the leader's ranked number, so Alt+1 lands on rank 1 and the arrows walk down the ranking.
    scrAct = rows.length ? { pid: rows[0].id, c: 1 } : null;
    renderScrn();
    // The line first, then the scroll: on a phone the line is in the page flow and pushes the table down.
    out(rankText(m, cl, why) + note + carriedText(fresh));
    showPanel('scrn', true, scrollTable(m.key));
  }
  // The status line after a ranking, in the catalogue's terms: one list, one list per level, or by percentile per gender.
  function rankText(m, cl, why = '') {
    const boards = screenBoards(), rows = boards.flatMap(b => b.rows), mode = boards.length ? boards[0].mode : 'one';
    const who = whoWords(S.scr.where, posText(S.scr.pos)) + (cl ? ` at ${cl.name}` : '');
    if (!rows.length) return emptyText();
    const unr = boards.reduce((n, b) => n + b.ranks.filter(x => x == null).length, 0);
    const nz = rows.filter(p => isNone(cellOf(p, m.key))).length;
    const reason = mode === 'pool' ? 'no percentile' : S.scr.qual ? 'below the minimum attempts' : 'under the minutes or the minimum attempts';
    const whyAll = [nz ? `${nz} with none yet` : '', unr - nz > 0 ? `${unr - nz} ${reason}` : ''].filter(Boolean).join(', ');
    const unText = !unr ? '' : unr === rows.length ? `, none ranked (${whyAll})` : `, ${rows.length - unr} ranked (${whyAll}, listed after)`;
    if (mode === 'pool') {
      const lv = new Set(rows.map(p => p.level)).size;
      // Each list's first ranked player; a list with nobody ranked says so (no name with an empty percentile).
      const firsts = boards.map(b => { const i = b.ranks.findIndex(x => x != null), p = b.rows[i], c = p && cellOf(p, m.key);
        return p && c && c.percentile != null ? `${cap1(b.key)}: ${p.name} (${p.comp.name}), ${poolLine(p, c)}` : `${cap1(b.key)}: nobody ranked yet`; });
      return `${cap1(who)} ranked by ${m.label}${why}, each by their percentile in their own pool, since they span ${plural(lv, 'level')}: ${rows.length}${unText}${unr === rows.length ? '' : `. ${firsts.join('; ')}`}.`;
    }
    if (mode === 'level') {
      const tops = boards.slice(0, 4).map(b => { const i = b.ranks.findIndex(x => x != null), p = b.rows[i >= 0 ? i : 0], c = cellOf(p, m.key); return `${levelWords(b.key)}: ${i >= 0 ? `${p.name}, ${c ? withUnit(m, c.value) : '–'}` : 'nobody ranked yet'}`; });
      return `${cap1(who)} ranked by ${m.label}${why}, one list per level (raw numbers compare only within a level): ${plural(boards.length, 'list')}, ${rows.length} players${unText}. Top of each: ${tops.join('; ')}${boards.length > 4 ? ` and ${boards.length - 4} more` : ''}.`;
    }
    const b = boards[0], tops = b.rows.filter((_, i) => b.ranks[i] === 1), c = tops[0] && cellOf(tops[0], m.key);
    const names = tops.length > 3 ? `${tops.slice(0, 3).map(p => p.name).join(', ')} and ${tops.length - 3} more` : tops.map(p => p.name).join(tops.length === 2 ? ' and ' : ', ');
    return `${cap1(who)} ranked by ${m.label}${why}: ${rows.length}${unText}${c ? `. Top: ${names}, ${withUnit(m, c.value)}${tops.length > 1 ? ', tied' : ''}${c.percentile != null && tops.length === 1 ? ` (${poolLine(tops[0], c)})` : ''}` : ''}.`;
  }
  // The players table back to its top and left edge, with the sorted column in view; returns the row to scroll to.
  function scrollTable(key) {
    const tw = document.querySelector('#tx-p-scrn .tx-tablewrap');
    if (!tw) return null;
    tw.scrollLeft = 0; tw.scrollTop = 0;
    // On a phone the first stat column can still run past the table's edge: scroll the table, not the page, until the
    // ranked column shows whole; never so far that the Percentile column slides under the sticky name column (half
    // hidden, "96th" read as "6th"), nor so little that Mins sits half under it.
    const th = key && tw.querySelector(`thead th [data-k="${CSS.escape(key)}"]`), cell = th && th.closest('th');
    if (cell) {
      const box = tw.getBoundingClientRect(), over = cell.getBoundingClientRect().right - box.right;
      const stk = tw.querySelector('thead th.tx-stk'), pool = tw.querySelector('thead th.tx-poolh');
      const room = pool && stk ? Math.max(0, pool.getBoundingClientRect().left - box.left - stk.getBoundingClientRect().width) : Infinity;
      const minsTh = tw.querySelector('thead th [data-k="min"]'), minsW = minsTh ? minsTh.closest('th').getBoundingClientRect().width : 0;
      let sl = over > 0 ? Math.min(over + 4, room) : 0;
      if (sl > 0 && sl < minsW) sl = Math.min(minsW, room) >= minsW ? minsW : 0;
      if (sl > 0) tw.scrollLeft = sl;
    }
    const trs = tw.querySelectorAll('tbody[data-r="grid"] tr[data-row]');
    return trs.length ? trs[Math.min(2, trs.length - 1)] : null;     // the first rows of the ranking, not just the box
  }
  // "most minutes": the table sorted by minutes played (the engine's places, one list per level).
  async function rankMinutes(pos, cl, note = '') {
    const g = gen;
    S.scr.pos = pos === 'ALL' ? null : pos || null;
    S.scr.sort = { k: 'min', dir: -1 }; S.scr.q = cl ? cl.name : ''; scrAct = null; save();
    if (!visible('scrn')) showPanel('scrn', false); else renderScrn();
    await settle(tableData(S.scr.cols.filter(k => MK.has(k))).ord);
    if (g !== gen) return;
    renderScrn();
    const rows = screenRows();
    out(`${cap1(whoWords(S.scr.where, posText(S.scr.pos)))}${cl ? ` at ${cl.name}` : ''} by minutes played: ${rows.length}${rows[0] ? `. Most: ${rows[0].name}, ${Math.round(rows[0].minutes)} minutes` : ''}.${note}`);
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
    const cps = ids.map(id => PID.get(id)), lvs = new Set(cps.map(p => p.level));
    out('', '', esc(`Comparing ${listText(cps.map(p => p.name))}: radar and table, each against their own pool.${lvs.size > 1 ? ` Different levels (${listText([...lvs].map(levelWords))}): read each percentile against its own pool; raw numbers do not compare across levels.` : ''}${new Set(cps.map(p => p.gender)).size > 1 ? ' Men and women never share a pool.' : ''}`)
      + (amb.length ? ` <span class="tx-dim">"${esc(amb[0].q)}" could also be:</span> ${amb[0].alts.slice(0, 5).map(p => runBtn(`compare ${ids.map(id => id === amb[0].p.id ? p.name : PID.get(id).name).join(', ')}`, `${p.name} ${p.short_name}`)).join(' ')}` : ''));
    showPanel('radar');
  }
  const AGAINST = /^(against|vs|v|versus)$/i;
  async function cmdScat(rest) {
    // Place words inside the command ("plot npxG against xA in academy") set the table's filters; the scatter follows.
    const pl = TP.parse(rest, V);
    if (pl.found) { S.scr.where = { ...pl.where }; rest = pl.rest; scrAct = null; save(); if (visible('scrn')) renderScrn(); }
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
    await settle(scatOf(mx.key, my.key, S.scat.pos, scatLevel()));
    if (g !== gen) return;
    if (!visible('scat')) showPanel('scat', false); else renderScat();
    await panelsSettled();
    if (g !== gen) return;
    const pts = scatPoints() || [], l = LVL.get(scatLevel()) || {};
    out(`${mx.label} against ${my.label}, ${whoWords({ tier: l.tier, age_group: l.age_group, gender: l.gender, country: (S.scr.where || {}).country, competition: (S.scr.where || {}).competition }, S.scat.pos ? POSN[S.scat.pos] : 'players')}: ${plural(pts.length, 'player')} (one level at a time).`);
    showPanel('scat', true);
  }

  // ------------------------------------------------------------------ the search box: autocomplete and history
  function playerSugs(q, k, runIt, ctx) {
    const n = norm(q);
    const score = (p) => { const nm = norm(p.name), sn = surname(p); if (!n) return 0; if (sn.startsWith(n)) return 0; if (nm.startsWith(n)) return 1; if (nm.split(' ').some(w => w.startsWith(n))) return 2; if (n.length >= 3 && nm.includes(n)) return 3; return 9; };
    let ps;
    if (!n) { const f = PID.get(S.focus), sm = (C.get(`sim|${S.scope}|${f.id}`) || {}).v; ps = [f, ...((sm && sm.similar) || []).map(s => PID.get(s.row)).filter(Boolean)]; }
    else {
      // Namesakes in the order a typed name would pick them (the selected player, who they play like, the table…).
      const hit = PLAYERS.filter(p => p.name && score(p) < 9), at = new Map(namesakeOrder(hit, ctx).map((p, i) => [p.id, i]));
      ps = hit.sort((a, b) => score(a) - score(b) || at.get(a.id) - at.get(b.id));
    }
    return ps.slice(0, 7).map(p => ({ kind: 'Player', text: p.name, detail: `${p.short_name} · ${p.position} · #${p.kit_number} · ${levelWords(p.level)}, ${p.country}`, insert: p.name, k, run: runIt }));
  }
  // Places: countries, levels, age groups, genders, competitions, "my level" and "whole catalogue". Each sets the filters;
  // the count beside it is how many regulars the filter holds (a count, not a ranking).
  function placeSugs(q) {
    const n = norm(q); if (n.length < 2) return [];
    const lv = IX.levels || {};
    const count = (w) => PLAYERS.filter(p => p.qualified && inWhere(p.comp, w)).length;
    const opts = [
      ...COUNTRIES.map(c => ({ text: c, w: { country: c }, ins: `players in ${c}` })),
      ...(lv.tiers || []).map(t => ({ text: TIER_WORD[t.key] || t.key, w: { tier: t.key, ...(t.key === 'college' ? { age_group: 'college' } : {}) }, ins: `${TIER_WORD[t.key] || t.key} players` })),
      ...(lv.age_groups || []).filter(a => /^U\d/.test(a.key)).map(a => ({ text: a.key, w: { age_group: a.key }, ins: `${a.key} players` })),
      { text: 'women', w: { gender: 'women' }, ins: 'women players' }, { text: 'men', w: { gender: 'men' }, ins: 'men players' },
      ...[...COMP.values()].map(c => ({ text: c.name, w: { competition: c.competition_id }, ins: `players in the ${c.name}`, comp: c })),
      { text: 'my level', w: mineWhere(), ins: 'my level' }, { text: 'whole catalogue', w: {}, ins: 'players across the whole catalogue' },
    ];
    return opts.filter(o => norm(o.text).split(/[\s-]+/).some(w => w.startsWith(n)) || norm(o.text).startsWith(n)).slice(0, 4)
      .map(o => ({ kind: 'Place', text: o.text, detail: `${o.comp ? `${o.comp.country}, ${o.comp.level_words} · ` : ''}${count(o.w)} regulars`, insert: o.ins, k: 1, run: true }));
  }
  const groupLabel = (m) => ((CAT.groups || []).find(g => g.key === m.group) || {}).label || '';
  function metricSugs(q, k, runIt, prefix = '', pos = null, suffix = '') {
    const n = norm(q), kk = n.replace(/[\s-]+/g, '_');
    const score = (m) => { if (!n) return 0; const l = norm(m.label); if (l.startsWith(n)) return 0; if (m.key.startsWith(kk)) return 1; if (norm(shortLabel(m)).startsWith(n)) return 1; if (l.split(' ').some(w => w.startsWith(n))) return 2; if (m.key.includes(kk) || l.includes(n)) return 3; const ws = TW.loose(n).split(' ').filter(Boolean), mw = W.mwords(m); if (ws.length && ws.every(w => mw.some(x => x.startsWith(w)))) return 4; return 9; };
    const base = n ? METRICS : (CAT.default_columns[pos || PID.get(S.focus).position] || CAT.default_columns.all).map(x => MK.get(x)).filter(Boolean);
    return base.filter(m => score(m) < 9).sort((a, b) => score(a) - score(b)).slice(0, 8)
      .map(m => ({ kind: 'Stat', text: `${m.label}${noisyAt(m) ? ' ≈' : ''}`, detail: groupLabel(m), insert: prefix + m.label + suffix, k, run: runIt, mk: m.key }));
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
    const clubs = [...CID.values()];
    let s = [];
    const trailing = (fn) => { for (let k = Math.min(3, toks.length - 1); k >= 1; k--) { const q = toks.slice(-k).join(' ').trim(); const r = fn(q, k); if (r.length && q) return r; } return fn(cur, 1); };
    if (!inArgs) {
      if (toks.length === 1 || (wordsIn.length === 1 && !ph.started)) {
        const n = norm(cur);
        s.push(...Object.entries(COMMANDS).filter(([c, x]) => x.word.startsWith(n) || c.startsWith(cur.toUpperCase())).map(([c, x]) => ({ kind: 'Command', text: x.word, detail: x.args ? `${x.word} ${x.args}` : x.help, insert: x.word, k: 1, run: c === 'HELP' })));
        s.push(...playerSugs(cur, 1, true).slice(0, 5));
        s.push(...clubs.filter(c => norm(c.short_name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).slice(0, 4).map(c => ({ kind: 'Club', text: c.name, detail: `how they play · ${(COMP.get(c.competition_id) || {}).name || ''}`, insert: `team ${c.name}`, k: 1, run: true })));
        const fpos = POSN[PID.get(S.focus).position];
        s.push(...metricSugs(cur, 1, true, `rank ${fpos} `).slice(0, 3).map(x => ({ ...x, detail: `rank ${fpos}` })));
        s.push(...placeSugs(cur).slice(0, 3));
      } else s = [...playerSugs(wordsIn.join(' '), toks.length, true), ...placeSugs(wordsIn.join(' ')).map(x => ({ ...x, k: toks.length }))];
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
    const f = PID.get(S.focus), sm = (C.get(`sim|${S.scope}|${f.id}`) || {}).v, like = sm && sm.similar && sm.similar[0];
    const ex = (c, x) => c === 'TEAM' ? `team ${club(S.club).name}` : x.ex;
    h.innerHTML = `<div class="tx-hhead"><h2 tabindex="-1" id="txHelpH">How to use the Scout terminal</h2><button type="button" class="tx-mini" data-act="helpclose" aria-label="Close help">Close &times;</button></div>
      <div class="tx-hbody"><p>Type in the search box and press Enter. Click any example to run it.</p><table class="tx-mt tx-htable"><tbody>
        <tr><th scope="row"><code>a name</code></th><td>Opens the player. ${runBtn(lastName(f))}</td></tr>
        <tr><th scope="row"><code>a club</code> or <code>a stat</code></th><td>A club opens how it plays; a stat ranks every player on it. ${runBtn('goals')}</td></tr>
        <tr><th scope="row"><code>a place or level</code></th><td>A country, a level (semi-pro, amateur, college, academy), an age group (U17 to U20), women or men, a competition, "my level" or "whole catalogue" sets the players table's filters; add a position or a question. Lists that mix levels split into one list per level. ${runBtn('U19 midfielders in Spain')} ${runBtn('best dribblers in academy')} ${runBtn('women forwards')} ${runBtn('players in Nigeria')} ${runBtn('my level forwards', 'my level')}</td></tr>
        <tr><th scope="row"><code>a question</code></th><td>Plain words work too: best finishers, the most of any stat, a stat per 90, best finishers at a club, a player with a stat, a panel or "highlights", or two players with "vs". ${runBtn('who has the most xG?')} ${runBtn(`${lastName(f)} highlights`)} ${runBtn(`${lastName(f)} vs ${like ? String(like.name).split(' ').slice(-1)[0] : 'Ustinov'}`)}</td></tr>
        ${Object.entries(COMMANDS).filter(([c]) => c !== 'HELP').map(([c, x]) => `<tr><th scope="row"><code>${esc(x.word)}</code> <span class="tx-dim">${esc(x.args)}</span></th><td>${esc(x.help)} ${runBtn(ex(c, x))}</td></tr>`).join('')}
      </tbody></table>
      <p class="tx-dim">Short forms still work: ${Object.keys(COMMANDS).map(c => `<code>${esc(c)}</code>`).join(' ')} (for example <code>RANK FW npxg</code>).</p>
      <h3 class="tx-h3">Keys</h3><ul class="tx-keys">
        <li><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> goes to the search box</li><li><kbd>Enter</kbd> searches</li><li><kbd>↑</kbd> <kbd>↓</kbd> earlier searches, or move in the suggestions</li>
        <li><kbd>Tab</kbd> takes a suggestion</li><li><kbd>Esc</kbd> closes suggestions, help, tips and the clips drawer</li><li><kbd>Alt 1–9</kbd> jump to a panel, in the order of the panel buttons (each button's tooltip shows its key)</li>
        <li><kbd>Alt 1</kbd> (Players) goes straight into the players table: arrow keys, Home/End and PageUp/PageDown move, Enter plays the moments</li><li>In the scatter: arrow keys pick a player, Enter selects</li></ul>
      <h3 class="tx-h3">How the panels link</h3><p>One selected player and up to three compared players drive every panel. A player with two competitions has a row in each; numbers never merge across them. Selecting a player anywhere (a row in the table, a dot in the scatter, a similar player, the squad, a legend) updates the rest. Every underlined number plays every moment behind it in the clips drawer, each with its clip; physical numbers, consistency means and team-style ratios list one value per match, without a clip. Ranks, SD and CV open nothing.</p>
      <h3 class="tx-h3">The numbers</h3><p>${esc(IX.note || CAT.note)}</p><p>Percentiles are within each player's level by default (the same tier, age group and gender), or their competition, or all levels of their gender; every percentile shows the size of its pool, and a pool under ${esc(SMALL_POOL)} is marked small. A count of 0 is "none yet": no percentile and no place. The order and the places are the engine's. ${esc(plainSample((CAT.season.sample || {}).note))} Outside England only the uploaded matches count.</p><p><span class="tx-noisy">≈</span> small sample, read with care: the stat cannot yet tell players in the same role apart over one season.</p>
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
    if (pid !== undefined && !ROW.test(pid)) return null;
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
      if (t.classList.contains('z')) { const tm = TK.get(t.dataset.tk); out(`${CID.has(t.dataset.cid) ? club(t.dataset.cid).name : 'This club'}: ${tm ? tm.label : 'this number'} ${t.textContent}, so there is nothing to play.`); return null; }
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
    if (a === 'colsretry') { for (const [k, c] of [...C]) if (c.st === 'err' && /^(ord|cells)\|/.test(k)) C.delete(k); renderScrn(); return null; }
    if (a === 'wmine') { setWhere(mineWhere()); return null; }
    if (a === 'wall') { setWhere({}); return null; }
    if (a === 'scope') { if (SCOPES.includes(t.dataset.v)) { S.scope = t.dataset.v; scrAct = null; save(); renderAll(); out(scopeText()); } return null; }
    if (a === 'team') { if (CID.has(t.dataset.cid)) return team(club(t.dataset.cid), teamText(club(t.dataset.cid))); return null; }
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
        if (tr && ROW.test(tr.dataset.row) && !e.target.closest('a, button, input, select, summary')) { scrAct = { pid: tr.dataset.row, c: 0 }; select(tr.dataset.row); }
        return;
      }
      if (!root.contains(t) || t.disabled) return;
      if (t.tagName === 'A') return;
      e.preventDefault(); doAct(t, e);
    });
    // The Columns and Where menus stay open across repaints (their state is kept here) and close on a click outside them.
    root.addEventListener('toggle', (e) => {
      if (!e.target.classList || !e.target.classList.contains('tx-menu')) return;
      if (e.target.dataset.r === 'wmenu') whereMenuOpen = e.target.open; else colMenuOpen = e.target.open;
    }, true);
    document.addEventListener('click', (e) => {
      if ((!colMenuOpen && !whereMenuOpen) || e.target.closest('.tx-menu')) return;
      colMenuOpen = false; whereMenuOpen = false; for (const m of document.querySelectorAll('.tx .tx-menu[open]')) m.open = false;
    });
    root.addEventListener('change', (e) => {
      const r = e.target.dataset.r; if (!r || !ready) return;
      if (r === 'addcol' && MK.has(e.target.value) && S.scr.cols.length < MAX_COLS) { colMenuOpen = true; S.scr.cols.push(e.target.value); save(); renderScrn(); const sel = document.querySelector('[data-fid="scr-add"]'); if (sel) sel.focus(); }
      if (r === 'scrqual') { S.scr.qual = e.target.checked; scrAct = null; save(); renderScrn(); }
      if (r === 'formk' && MK.has(e.target.value)) { S.form.k = e.target.value; save(); renderForm(); }
      if ((r === 'scx' || r === 'scy') && MK.has(e.target.value)) { S.scat[r === 'scx' ? 'x' : 'y'] = e.target.value; scatCur = null; save(); renderScat(); }
      if (r === 'scall') { S.scat.all = e.target.checked; scatCur = null; save(); renderScat(); }
      if (r === 'club' && CID.has(e.target.value)) { S.club = e.target.value; save(); renderTeam(); out(teamText(club(S.club))); }
      if (r.startsWith('w-') && W_FIELDS.some(([k]) => k === r.slice(2))) {
        const f = r.slice(2), w = { ...(S.scr.where || {}) };
        if (e.target.value) w[f] = e.target.value; else delete w[f];
        // A competition the other filters no longer allow is dropped.
        if (w.competition && f !== 'competition' && !inWhere(COMP.get(w.competition), { ...w, competition: undefined })) delete w.competition;
        whereMenuOpen = true;
        setWhere(w);
      }
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
        if (menu) { const back = menu.contains(document.activeElement); colMenuOpen = false; whereMenuOpen = false; menu.open = false; if (back) menu.querySelector('summary').focus(); return; }
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
