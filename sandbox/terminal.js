// The Scout terminal (sandbox, part B6; the "intuitive" round): Maya Lindqvist's Terminal section under Scout
// (#scout/terminal). A search box on top (a name, a club, a stat, or a plain command such as "rank forwards goals",
// "compare Toure and Ustinov", "plot npxG against xA", "similar to Toure"; the old mnemonics RANK, CMP, SCAT, SIM, SHOT,
// FORM, HEAT, RDR, TEAM and HELP still work) over linked panels: players table, player card, radar vs position peers, shot
// map, touch map, form, scatter, team. Selecting a player in any panel updates the others; every number opens the moments
// behind it (the engine's evidence) in the clips drawer, which plays them from the app named in terminal.json ("app": the
// live app, which serves this league since part A merged). terminal.json is part A's metrics engine exported by
// tools/export_terminal.py; it holds no hidden ratings. Three saved layouts (panels, players, columns) are kept in this
// browser only (localStorage, wrapped in try/catch).
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = (s) => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const ord = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const POS = ['GK', 'DF', 'MF', 'FW'];
  const POSN = { GK: 'goalkeepers', DF: 'defenders', MF: 'midfielders', FW: 'forwards' };
  const POS1 = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };
  const POS_WORDS = { GK: 'GK', GOALKEEPER: 'GK', GOALKEEPERS: 'GK', KEEPER: 'GK', KEEPERS: 'GK', DF: 'DF', DEF: 'DF', DEFENDER: 'DF', DEFENDERS: 'DF',
    MF: 'MF', MID: 'MF', MIDFIELDER: 'MF', MIDFIELDERS: 'MF', FW: 'FW', FWD: 'FW', FORWARD: 'FW', FORWARDS: 'FW', STRIKER: 'FW', STRIKERS: 'FW',
    ALL: 'ALL', PLAYERS: 'ALL', EVERYONE: 'ALL' };
  const CMP_COL = ['#ffcd28', '#4cc9f0', '#f472b6'];
  const GROUP_COL = { shooting: '#ffcd28', creation: '#ff9f43', passes: '#4cc9f0', carrying: '#5ad17a', defence: '#ff6b6b',
    goalkeeping: '#2dd4bf', physical: '#a3a9b8', value: '#c084fc' };
  // Panel-button order (Alt+1 to Alt+9). Sizes span 4, 6, 8 or 12 of the layout's 12 columns (S, M, L, XL). Clips is not
  // in the grid: it is a drawer that opens when a number is clicked (a bottom sheet on phones).
  const PANELS = [
    { id: 'scrn', title: 'Players', size: 'L', cmd: 'RANK' },
    { id: 'plyr', title: 'Player', size: 'S', cmd: 'PLYR' },
    { id: 'radar', title: 'Radar', size: 'S', cmd: 'RDR' },
    { id: 'clips', title: 'Clips', size: 'S', drawer: true },
    { id: 'shot', title: 'Shots', size: 'S', cmd: 'SHOT' },
    { id: 'heat', title: 'Touch map', size: 'S', cmd: 'HEAT' },
    { id: 'form', title: 'Form', size: 'S', cmd: 'FORM' },
    { id: 'scat', title: 'Scatter', size: 'S', cmd: 'SCAT' },
    { id: 'team', title: 'Team', size: 'L', cmd: 'TEAM' },
  ];
  // The default layout: the players table on the left with the player card and radar it drives stacked on its right,
  // then form, shots and touch map, then the scatter and the team.
  const DEFAULT_ORDER = ['scrn', 'plyr', 'radar', 'form', 'shot', 'heat', 'scat', 'team'];
  const SIZES = ['S', 'M', 'L', 'XL'];
  const SIZE_NEXT = { S: 'M', M: 'L', L: 'XL', XL: 'S' };
  const SIZE_NAME = { S: 'small', M: 'medium', L: 'large', XL: 'full width' };
  // Commands in plain words, each with an example. The mnemonic (the key) is still accepted, as are the aliases below.
  const COMMANDS = {
    RANK: { word: 'rank', args: '<position> <stat>', help: 'Rank a position on any stat; the players table sorts by it.', ex: 'rank forwards non-penalty xG' },
    CMP: { word: 'compare', args: '<player> and <player> [and <player>]', help: 'Two or three players on the radar and side by side.', ex: 'compare Femi Toure and Amari Ustinov' },
    SCAT: { word: 'plot', args: '<stat> against <stat> [<position>]', help: 'One stat against another, a dot per player.', ex: 'plot non-penalty xG against xA forwards' },
    SIM: { word: 'similar to', args: '<player>', help: 'The five players most like them, on their position\'s stats.', ex: 'similar to Femi Toure' },
    HL: { word: 'highlights', args: '<player>', help: 'One reel of their goals, shots, chances made, skills and defending.', ex: 'highlights Femi Toure' },
    SHOT: { word: 'shots', args: '<player>', help: 'Every shot, sized by xG; each plays its clip.', ex: 'shots Femi Toure' },
    FORM: { word: 'form', args: '<player>', help: 'Match by match, any stat.', ex: 'form Femi Toure' },
    HEAT: { word: 'touch map', args: '<player>', help: 'Where the player has the ball.', ex: 'touch map Femi Toure' },
    RDR: { word: 'radar', args: '<player>', help: 'Percentiles against players in the same position.', ex: 'radar Femi Toure' },
    TEAM: { word: 'team', args: '<club>', help: 'How a club plays: possession, pressing, directness, chances.', ex: 'team Brookfield Rovers' },
    HELP: { word: 'help', args: '', help: 'Commands, keys and what the numbers mean.', ex: 'help' },
  };
  const ALIAS = { COMPARE: 'CMP', PLOT: 'SCAT', SCATTER: 'SCAT', SIMILAR: 'SIM', SHOTS: 'SHOT', RADAR: 'RDR', CLUB: 'TEAM', PLAYER: 'PLYR', '?': 'HELP',
    HEATMAP: 'HEAT', TOUCHMAP: 'HEAT', HIGHLIGHTS: 'HL', HIGHLIGHT: 'HL', CLIPS: 'HL', MOMENTS: 'HL', VIDEOS: 'HL', REEL: 'HL' };
  // Multi-word heads ("who plays like Toure?", "similar to Toure", "touch map Toure") come first.
  const HEAD_RE = /^(who\s+plays\s+like|plays\s+like|similar\s+to|players?\s+like|touch\s+map|heat\s+map|shot\s+map|best\s+moments|highlight\s+reel)(?=\s|$)/i;
  function parseHead(t) {
    const m = t.match(HEAD_RE);
    if (m) {
      const w = norm(m[1]), after = t.slice(m[1].length);
      return { head: /^(who|plays|similar|player)/.test(w) ? 'SIM' : w.startsWith('shot') ? 'SHOT' : /^(best|highlight)/.test(w) ? 'HL' : 'HEAT', rest: after.replace(/^\s+/, ''), started: /^\s/.test(after), word: m[1] };
    }
    const w = t.split(/\s+/)[0], up = w.toUpperCase(), after = t.slice(w.length);
    return { head: ALIAS[up] || up, rest: after.replace(/^\s+/, ''), started: /^\s/.test(after), word: w };
  }
  const LS = 'regista.terminal.v1';
  const VER = 3;

  let D = null, APP = '', loading = false, ready = false;
  const MK = new Map(), TK = new Map(), PID = new Map(), CID = new Map(), TEAMS = new Map(), SHOTS = new Map();
  let store = { cur: 0, ws: [null, null, null], hist: [] }, S = null, storageOK = true, saveT = 0;
  let reel = null, histAt = -1, acItems = [], acAt = -1, scatCur = null, scrAct = null, tipFor = null;
  // The sandbox's own player pages (#scout/player/<id>) exist for the players in scout.json; the rest open on the live app.
  let profileIds = new Set(), colMenuOpen = false, actFrom = null, drawerFrom = null;

  // ------------------------------------------------------------------ loading (the first time the section opens)
  function onRoute() {
    if (!location.hash.startsWith('#scout/terminal')) { const v = clipVideo(); if (v) v.pause(); hideTip(); return; }
    if (!D && !loading) load();
    if (ready) setTimeout(() => { placeNav(); navCurrent(); }, 0);
  }
  function load() {
    loading = true;
    out('Loading the Regista League…');
    fetch('scout.json').then(r => r.ok ? r.json() : null).then(sd => {
      if (sd && Array.isArray(sd.players)) profileIds = new Set(sd.players.map(p => p.global_id));
      if (ready && visible('plyr')) renderPlyr();
    }).catch(() => {});
    fetch('terminal.json').then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(setup).catch(e => { loading = false; out('Could not load terminal.json (' + e.message + ').', 'err'); });
  }
  function setup(d) {
    D = d; APP = String(d.app || '').replace(/\/$/, '');
    for (const m of d.metrics) MK.set(m.key, m);
    for (const m of d.team_metrics) TK.set(m.key, m);
    for (const c of d.clubs) CID.set(c.club_id, c);
    for (const t of d.teams) TEAMS.set(t.club_id, t);
    for (const p of d.players) {
      PID.set(p.id, p);
      for (const s of p.shots || []) SHOTS.set(s.match_id + '|' + s.event_id, { p, s });
    }
    readStore();
    $('txDrawerBody').appendChild(buildClipBody());
    paintMeta(); paintExamples(); paintFoot(); paintKeys(); renderLayout(); renderAll();
    ready = true;
    placeNav();
    out(`Ready: ${d.players.length} players, ${d.metrics.length} stats, ${d.matches.length} matches. Search a name, a club or a stat, or try an example.`);
    if (location.hash.startsWith('#scout/terminal') && wantFocus) $('txIn').focus();
  }
  let wantFocus = false;

  // ------------------------------------------------------------------ workspaces, per visitor
  function defaults() {
    const f = PID.has('pl_bro_09') ? 'pl_bro_09' : D.players.find(p => p.minutes > 0).id, fp = PID.get(f);
    const cols = (D.default_columns[fp.position] || D.default_columns.all).filter(k => MK.has(k));
    return { v: VER, panels: DEFAULT_ORDER.map(id => PANELS.find(p => p.id === id)).map(p => ({ id: p.id, on: true, size: p.size })), focus: f, compare: [], club: fp.club_id,
      scr: { pos: fp.position, cols, sort: { k: cols[0], dir: -1 }, qual: true, mode: 'val', q: '' },
      scat: { x: 'npxg', y: 'xa', pos: fp.position, all: false }, form: { k: null }, radar: { tpl: 'pos' } };
  }
  function clean(s) {
    const o = defaults();
    if (!s || typeof s !== 'object' || ![1, 2, 3].includes(s.v)) return o;
    // Version 1 had three sizes (L spanned the full width) and a default layout three screens tall: a v1 layout that is
    // still that default takes the new one; a layout the visitor changed is kept, its L read as XL.
    const V1_DEFAULT = 'scrn:L,plyr:S,radar:S,clips:S,shot:S,heat:S,form:S,scat:M,team:M';
    if (s.v === 1 && Array.isArray(s.panels) && s.panels.map(p => p && `${p.id}:${p.size}`).join(',') === V1_DEFAULT && s.panels.every(p => p.on !== false)) s.panels = null;
    else if (s.v === 1 && Array.isArray(s.panels)) s.panels = s.panels.map(p => p && p.size === 'L' ? { ...p, size: 'XL' } : p);
    // Version 2 kept Clips in the grid; version 3 opens it as a drawer. A v2 layout that is still the v2 default takes the
    // new default (the table with the player card and radar beside it); a changed one keeps its order and sizes, minus Clips.
    const V2_DEFAULT = 'scrn:L,clips:S,plyr:S,radar:S,form:S,shot:S,heat:S,scat:S,team:XL';
    if (s.v === 2 && Array.isArray(s.panels) && s.panels.map(p => p && `${p.id}:${p.size}`).join(',') === V2_DEFAULT && s.panels.every(p => p.on !== false)) s.panels = null;
    if (Array.isArray(s.panels)) {
      const seen = new Set(), ps = [];
      for (const p of s.panels) {
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
    if (Array.isArray(sc.cols)) o.scr.cols = [...new Set(sc.cols.filter(k => MK.has(k)))].slice(0, 40);
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
    let raw = null;
    try { localStorage.setItem(LS + '.probe', '1'); localStorage.removeItem(LS + '.probe'); raw = localStorage.getItem(LS); } catch (e) { storageOK = false; }
    let s = null;
    try { s = raw ? JSON.parse(raw) : null; } catch (e) { s = null; }
    if (s && Array.isArray(s.ws)) {
      store.cur = [0, 1, 2].includes(s.cur) ? s.cur : 0;
      store.ws = [0, 1, 2].map(i => s.ws[i] || null);
      store.hist = Array.isArray(s.hist) ? s.hist.filter(h => typeof h === 'string').slice(-50) : [];
    }
    S = store.ws[store.cur] = clean(store.ws[store.cur]);
  }
  function save() {
    clearTimeout(saveT);
    saveT = setTimeout(() => {
      if (!storageOK) return;
      try { localStorage.setItem(LS, JSON.stringify(store)); } catch (e) { storageOK = false; paintMeta(); }
    }, 120);
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
  const club = (cid) => CID.get(cid) || { name: cid, short_name: String(cid || '').replace(/^cl_/, '').slice(0, 3).toUpperCase(), kit: { primary: '#555', secondary: '#fff', gk: '#111' } };
  const short = (cid) => club(cid).short_name;
  function fmt(m, v) {
    if (v == null || Number.isNaN(Number(v))) return '–';
    const d = Number.isInteger(m.digits) ? m.digits : 2;
    return Number(v).toFixed(d) + (m.unit === '%' ? '%' : '');
  }
  const unitText = (m) => m.kind === 'per90' ? `${m.unit} per 90` : m.kind === 'padj' ? `${m.unit} per 90, possession-adjusted`
    : m.kind === 'ratio' ? (m.unit === '%' ? 'percentage' : `${m.unit}, average`) : m.kind === 'max' ? `${m.unit}, season peak`
    : m.kind === 'mean' ? `${m.unit}, mean of matches` : `${m.unit}, season total`;
  const noisy = (m) => m.noisy ? '<span class="tx-noisy" role="img" aria-label="small sample, read with care">≈</span>' : '';
  // Short column labels, so the table's headers fit on one or two lines; the full name, definition and source stay in the
  // tooltip on hover and focus.
  const SHORT = { np_goals_minus_xg: 'NP goals − xG', tkl_int_padj: 'Tkl + int (adj.)', progressive_passes_received: 'Prog. received',
    sot_faced: 'On target faced', npxg_plus_xa: 'NP xG + xA', xa: 'xA', sca: 'Shot-creating', gca: 'Goal-creating',
    pressured_pass_pct: 'Compl. under pressure', passes_under_pressure_completed: 'Under pressure, completed', clean_sheet_pct: 'Clean sheet %',
    clean_sheets: 'Clean sheets', gk_avg_pass_length: 'Keeper pass length', peak_speed: 'Top speed', peak_speed_mean: 'Top speed (typical)' };
  function shortLabel(m) {
    if (SHORT[m.key]) return SHORT[m.key];
    return m.label.replace(/^Non-penalty /, 'NP ').replace(/^npxG/, 'NP xG').replace(/Progressive /, 'Prog. ').replace(/progressive /, 'prog. ')
      .replace(/ into the penalty area$/, ' into box').replace(/^Completion /, 'Compl. ').replace(/ completed$/, ' compl.')
      .replace(/^Passes from the /, 'Passes, ').replace(/^Passes in the /, 'Passes, ').replace(/^Passes into the /, 'Passes into ')
      .replace(/^Defensive-third /, 'Def. third ').replace(/^Middle-third /, 'Mid third ').replace(/^Final-third /, 'Final third ')
      .replace(/ \(30-min matches\)$/, '').replace(/ per shot$/, '/shot').replace(/ into the final third$/, ' into final third')
      .replace(/^Compl\. (from|in) the (defensive|middle|final) third$/, (x, w, t) => `${{ defensive: 'Def.', middle: 'Mid', final: 'Final' }[t]} third pass %`);
  }
  // What a clickable number opens: "▶ 18 moments" (or matches, for numbers built per match).
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : w === 'match' ? 'es' : 's'}`;
  function evCount(p, mk) {
    const ev = p && p.evidence && p.evidence[mk];
    return ev ? plural(ev.total, ev.per_match ? 'match' : 'moment') : null;
  }
  // A number with no moments behind it (a 0.00, most often) is shown as plain text: nothing to play.
  const zeroEv = (p, mk) => { const ev = p && p.evidence && p.evidence[mk]; return !!ev && !(ev.total > 0); };
  const playText = (p, mk) => { if (zeroEv(p, mk)) return 'no moments to play'; const n = evCount(p, mk); return n ? `play its ${n}` : 'open its moments'; };
  const zc = (p, mk) => zeroEv(p, mk) ? ' z' : '';
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
  function shade(m, pct) {
    if (pct == null) return '';
    const a = (0.05 + 0.4 * pct / 100).toFixed(3);
    return m.higher_is_better === null ? `background:rgba(110,140,200,${a})` : `background:rgba(255,205,40,${a})`;
  }
  // The qualifying minutes as people say them ("101+ minutes"; the engine's threshold is a third of a club's minutes).
  const minMin = () => Math.ceil(Number(D.season.min_minutes) || 0);
  const cellOf = (p, k) => (p && p.metrics && p.metrics[k]) || null;
  const pctOf = (p, k) => { const c = cellOf(p, k); return c ? c.percentile : null; };
  // Why a value has no percentile, as the engine decides it (metrics.py _percentiles): the metric has no percentiles at all
  // (a season count), it is not scored for the player's position, the player is under the qualifying minutes, a ratio has
  // too few attempts, or the player is the only qualified peer. `small` marks a small sample (the screener's italics).
  function noPct(p, m, c) {
    if (!c || c.value == null || c.percentile != null) return null;
    if (!m.has_percentile) return { text: 'no percentile: a season count, ranked by value only', small: false };
    if (!m.positions.includes(p.position)) return { text: `no percentile: not scored for ${POSN[p.position]} (scored for ${m.positions.join(' ')})`, small: false };
    if (!p.qualified) return { text: `no percentile: under ${minMin()} minutes`, small: true };
    if (!c.qualified) return { text: `no percentile: below the minimum attempts${c.den != null && m.min_attempts ? ` (${c.den} attempts, needs ${m.min_attempts})` : ''}`, small: true };
    return { text: `no percentile: the only regular ${POS1[p.position].toLowerCase()} on this metric, so no peers to rank against`, small: false };
  }
  const initials = (p) => { const w = p.name.split(' '); return w.length > 1 ? `${w[0][0]}. ${w.slice(1).join(' ')}` : p.name; };
  function surname(p) { const w = norm(p.name).split(' '); return w.slice(1).join(' ') || w[0]; }
  function shirt(p, w = 46) {
    const c = club(p.club_id), fill = p.position === 'GK' ? c.kit.gk : c.kit.primary;
    if (window.PF && window.PF.shirtSvg) return window.PF.shirtSvg({ primary: fill, secondary: c.kit.secondary }, p.kit_number).replace('width="72" height="68"', `width="${w}" height="${Math.round(w * 0.94)}"`);
    return '';
  }
  function evText(m, v) {
    if (v == null) return '';
    if (v === 1 && !['xG', 'xT', 'm', 'km/h'].includes(m.unit)) return '';
    // xA's moments are the key passes, exported as 1 each (no per-pass xA): showing "xG 1" would misstate them.
    if (v === 1 && m.key === 'xa') return '';
    const n = Number(v);
    const s = Number.isInteger(n) ? String(n) : (Math.abs(n) < 1 ? n.toFixed(3) : n.toFixed(1));
    return ['xG', 'xT'].includes(m.unit) ? `${m.unit} ${s}` : ['m', 'km/h'].includes(m.unit) ? `${s} ${m.unit}` : s;
  }

  // ------------------------------------------------------------------ output line
  function out(msg, kind, html) {
    const o = $('txOut'); if (!o) return;
    o.className = 'tx-out' + (kind === 'err' ? ' err' : '');
    if (html) o.innerHTML = html; else o.textContent = msg;
  }

  // ------------------------------------------------------------------ static pieces: the header line, examples, footer, layout
  // The right end of the one header line: what "≈" means (the details hold the rules), and the three saved layouts.
  // The export's sample note in this view's words: "regular" (not "qualified"), ≈ (not "noisy"), and no module name.
  const plainSample = (t) => String(t || '').replace(/\ba qualified player's\b/g, "a regular's").replace(/\bqualified\b/g, 'regular')
    .replace(/a metric marked noisy/g, 'a stat marked ≈').replace(/ \(split-half reliability, [\w.]+\)/g, '');
  function paintMeta() {
    const sm = D.season.sample || {};
    $('txMeta').innerHTML = `<details class="tx-about"><summary><span class="tx-noisy" aria-hidden="true">≈</span> small sample, read with care</summary>
        <div class="tx-aboutp"><p>${esc(plainSample(sm.note))}</p>
        <p><span class="tx-noisy">≈</span> marks a stat whose split-half reliability within a role is below ${esc(D.season.noise_r)}: one season cannot yet tell players in the same role apart on it.</p>
        <p>Percentiles compare a player with the regulars (at least ${esc(minMin())} minutes) in the same position: goalkeepers, defenders, midfielders or forwards. Where lower is better, the percentile is turned round.</p>
        <p>Every number opens the moments behind it: the first ${esc(10)} play here, with a link to the full list on the app. Physical numbers list one value per match (no single clip).</p></div></details>
      <div class="tx-ws" role="group" aria-label="Saved layouts"><span class="tx-wsl">Saved layouts:</span>
        ${[0, 1, 2].map(i => `<button type="button" data-act="ws" data-i="${i}" aria-pressed="${store.cur === i}" aria-label="Saved layout ${i + 1}" title="Saved layout ${i + 1}: panels, players and columns, kept in this browser">${i + 1}</button>`).join('')}
        <button type="button" data-act="reset" class="tx-reset" title="Put this layout back to the default">Reset layout</button>
        ${storageOK ? '' : '<span class="tx-warn" title="This browser blocks storage, so layouts last until you leave the page.">not saved: storage blocked</span>'}</div>`;
  }
  // Example searches under the box, each running the command it stands for.
  function paintExamples() {
    const f = PID.has('pl_bro_09') ? PID.get('pl_bro_09') : PID.get(S.focus);
    const rival = D.players.find(p => p.name === 'Amari Ustinov') || (f.similar && f.similar[0] && PID.get(f.similar[0].id));
    const exs = [['Best finishers', 'rank forwards non-penalty goals'],
      ...(rival ? [[`Compare ${f.name.split(' ').slice(-1)[0]} and ${rival.name.split(' ').slice(-1)[0]}`, `compare ${f.name} and ${rival.name}`]] : []),
      [`Who plays like ${f.name.split(' ').slice(-1)[0]}?`, `similar to ${f.name}`]];
    $('txEx').innerHTML = `<span class="tx-exl">Try</span>${exs.map(([l, c]) => `<button type="button" class="tx-exb" data-act="run" data-cmd="${esc(c)}" data-keep title="Runs: ${esc(c)}">${esc(l)}</button>`).join('')}`;
  }
  // Synthetic data, said once and plainly, at the bottom of the section.
  function paintFoot() {
    const first = String(D.note || '').split('. ')[0].replace(/\.$/, ''), i = first.indexOf(': ');
    const lead = i > 0 ? first.slice(0, i) : 'Synthetic data', rest = i > 0 ? first.slice(i + 2) : first;
    $('txFoot').innerHTML = `<b>${esc(lead)}:</b> ${esc(rest)}. Clips play from ${esc(APP.replace(/^https?:\/\//, ''))}.`;
  }
  const keyOf = (id) => PANELS.findIndex(p => p.id === id) + 1;
  function paintKeys() {
    const dOpen = drawerOpen();
    $('txKeys').innerHTML = PANELS.map((p, i) => {      // in shortcut order, whatever the layout
      const n = i + 1, pp = p.drawer ? { on: dOpen } : S.panels.find(x => x.id === p.id) || { on: false };
      // Not a toggle: a panel button always shows its panel and moves to it, so it says whether the panel is hidden instead.
      const tip = p.drawer ? `Clips: open the clips drawer (Alt+${n})` : `${p.title}${pp.on ? ': go to it' : ' is hidden: show it'} (Alt+${n})`;
      return `<button type="button" class="tx-fkey" data-act="fkey" data-id="${p.id}" data-on="${pp.on}" aria-keyshortcuts="Alt+${n}"${p.drawer ? ` aria-expanded="${dOpen}" aria-controls="txDrawer"` : ''}
        aria-label="${esc(p.title)}${p.drawer || pp.on ? '' : ', hidden: show it'}" title="${esc(tip)}">${esc(p.title)}</button>`;
    }).join('') + `<button type="button" class="tx-fkey help" data-act="help" aria-haspopup="dialog" title="Commands, keys and what the numbers mean">Help</button>`;
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
      return `<section class="tx-panel s-${pp.size}${tall && i === 0 ? ' tall' : ''}" id="tx-p-${p.id}" data-panel="${p.id}" aria-labelledby="tx-h-${p.id}">
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
    const sc = $('tx-p-scrn'), L = document.querySelector('#txGrid .tx-colL'), R = document.querySelector('#txGrid .tx-colR');
    if (!sc || !L || !R) { if (!balancing && !bulk) fillRows(); return; }
    if (balancing || bulk) return;
    balancing = true;
    const a = document.activeElement, split = L.parentElement, g = $('txGrid');
    const widthOf = (id) => { const b = document.querySelector(`#tx-p-${id} [data-body]`); return b ? b.clientWidth : 0; };
    const w0 = { form: widthOf('form'), scat: widthOf('scat') };
    try {
      const wide = getComputedStyle(split).display !== 'contents';
      sc.style.setProperty('--tx-tallh', `${Math.max(480, Math.floor(R.offsetHeight))}px`);
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
    if (typeof ResizeObserver === 'function') { tallRO = new ResizeObserver(fitTall); [ids[0], ids[1]].forEach(id => { const el = $('tx-p-' + id); if (el) tallRO.observe(el); }); }
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
    if (!cur) for (const sec of document.querySelectorAll('#txGrid .tx-panel')) { if (sec.getBoundingClientRect().top <= line) cur = sec.dataset.panel; }
    if (!cur) { const f = document.querySelector('#txGrid .tx-panel'); cur = f && f.dataset.panel; }
    for (const b of nav.querySelectorAll('button')) {
      const isCur = b.dataset.id === cur;
      if (isCur !== (b.getAttribute('aria-current') === 'true')) { if (isCur) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); }
      if (isCur) { const bl = b.offsetLeft, br = bl + b.offsetWidth; if (bl < nav.scrollLeft || br > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = bl - 16; }
    }
  }
  const visible = (id) => S.panels.some(p => p.id === id && p.on);
  // Show a panel and bring what the command is about into view: its chart or table (or `sel` inside it), not just its top
  // edge, since a panel whose header peeks in at the bottom of the screen hides the chart the scout asked for.
  function showPanel(id, scroll = true, sel, force = false) {
    if (id === 'clips') { openDrawer(true); return; }
    const pp = S.panels.find(p => p.id === id);
    if (pp && !pp.on) { pp.on = true; save(); renderLayout(); renderAll(); }
    if (scroll) {
      const el = $('tx-p-' + id);
      if (el) {
        const body = el.querySelector('[data-body]');
        const target = (sel && el.querySelector(sel)) || (body && body.querySelector('svg.tx-svg, .tx-tablewrap')) || body || el;
        if (force) scrollToShow(el, el); else if (!inViewFit(target, 0.6)) scrollToShow(el, target);
        el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
      }
    }
  }
  // Repaint a panel (or show it, which paints everything), then bring it into view.
  function reveal(id, render, sel) {
    if (!visible(id)) showPanel(id, false); else render();
    showPanel(id, true, sel);
  }
  function renderAll() {
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
  function select(pid, quiet) {
    const p = PID.get(pid); if (!p) return;
    S.focus = pid; S.club = p.club_id; scatCur = null;
    save(); renderAll();
    if (!quiet) out(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`);
  }
  // Beside the search: the selected player, and the comparison when there is one.
  function renderSel() {
    const f = PID.get(S.focus);
    const chips = S.compare.map((id, i) => { const p = PID.get(id); return `<span class="tx-chip" style="--c:${CMP_COL[i]}"><button type="button" data-act="sel" data-pid="${esc(id)}" data-fid="chip-${esc(id)}" title="Select ${esc(p.name)}">${esc(p.name)}</button><button type="button" class="tx-x" data-act="cmprm" data-pid="${esc(id)}" aria-label="Remove ${esc(p.name)} from the comparison" title="Remove from the comparison">&times;</button></span>`; }).join('');
    const inCmp = S.compare.includes(S.focus);
    let btn = '';
    if (!S.compare.length || (inCmp && S.compare.length < 3)) btn = `<button type="button" class="tx-mini tx-cmpw" data-act="cmpwith" title="Type a player to compare with">Compare with…</button>`;
    else if (!inCmp) btn = `<button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(S.focus)}">Add ${esc(f.name)} to the comparison${S.compare.length >= 3 ? ` (replaces ${esc(PID.get(S.compare[0]).name)})` : ''}</button>`;
    $('txSel').innerHTML = `<span class="tx-sl">Selected:</span><button type="button" class="tx-focus" data-act="pane" data-id="plyr" title="Go to the player card">${esc(f.name)} <span>${esc(f.short_name)} · ${esc(f.position)} · #${esc(f.kit_number)}</span></button>
      ${S.compare.length ? `<span class="tx-sl">Comparing:</span>${chips}` : ''}${btn}
      ${S.compare.length ? '<button type="button" class="tx-mini" data-act="cmpclear" title="Stop comparing">Clear</button>' : ''}`;
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

  // ------------------------------------------------------------------ evidence into the clips panel
  function evidenceReel(pid, mk, match) {
    const p = PID.get(pid), m = MK.get(mk), ev = p.evidence && p.evidence[mk], c = cellOf(p, mk);
    const r = { title: `${p.name} · ${m.label}`, sub: c ? `${fmt(m, c.value)}${m.kind === 'ratio' && m.unit === '%' ? '' : ' ' + unitText(m)}${c.num != null ? ` · ${c.num} of ${c.den}` : c.total != null && m.kind !== 'total' ? ` · ${c.total} in total` : ''}${c.percentile != null ? ` · ${ord(c.percentile)} percentile` : ''}` : 'No minutes this season',
      total: ev ? ev.total : 0, shown: ev ? ev.items.length : 0, items: [], i: -1, pid, mk, match: match || null,
      full: `${APP}/api/players/${encodeURIComponent(pid)}/metrics?evidence=${encodeURIComponent(mk)}`, note: '' };
    if (!ev) { r.note = 'No evidence for this number.'; return r; }
    if (ev.per_match) {
      r.items = ev.items.map(it => ({ when: `R${it.round} v ${short(it.opponent)}`, minute: null, val: `${fmt(m, it.value)}${['m', 'km/h'].includes(m.unit) ? ' ' + m.unit : ''}`, note: `${Math.round(it.minutes)} min`, video: null, match_id: it.match_id }));
      r.unit = 'match';
      r.note = 'Physical numbers come from the 10 Hz motion record: one value per match, no single clip.';
    } else if (ev.keys) {
      // Several keys behind one number (a ratio's numerator and denominator, or a sum): one row per event, labelled with
      // what it counts toward, so a ratio's "8 of 19" reads as 19 rows, 8 of them ticked.
      const km = ev.keys.map(k => MK.get(k) || { key: k, label: k, unit: '' });
      const ratio = m.kind === 'ratio' && m.num && ev.keys[0] === m.num, count0 = evText(km[0], 1) === '';
      r.items = ev.items.map(it => {
        const mo = p.moments[it.m] || {}, parts = it.in.map((ki, j) => ({ m: km[ki], v: it.v[j], ki })), n = parts.find(x => x.ki === 0);
        let val, note;
        if (ratio && count0) { val = n ? '✓' : '✗'; note = n ? km[0].label : `${km[1].label} only`; }
        else if (ratio) { val = n ? evText(km[0], n.v) : '–'; note = n ? '' : `${km[1].label} only`; }
        else { val = parts.map(x => evText(x.m, x.v)).filter(Boolean).join(' · '); note = parts.map(x => x.m.label).join(' + '); }
        return { when: `R${mo.round} v ${short(mo.opponent)}`, minute: mo.minute, val, note: [note, it.note].filter(Boolean).join(' · '), video: mo.video_url || null, match_id: mo.match_id };
      });
      r.legend = ratio && count0 ? `One row per event: ✓ counts toward ${km[0].label} (the top of the ratio), ✗ only toward ${km[1].label}.`
        : ratio ? `One row per event, with its ${km[0].label}.` : 'One row per event, with what it counts toward.';
    } else {
      r.items = ev.items.map(it => {
        const mo = p.moments[it.m] || {};
        return { when: `R${mo.round} v ${short(mo.opponent)}`, minute: mo.minute, val: evText(m, it.v), note: it.note || '', video: mo.video_url || null, match_id: mo.match_id };
      });
    }
    if (match) {
      r.items = r.items.filter(it => it.match_id === match);
      const mm = (p.form && p.form.matches || []).find(x => x.match_id === match);
      if (mm) r.sub = `Round ${mm.round} v ${club(mm.opponent).name} · ${r.sub}`;
      if (!r.items.length) r.note = r.total > r.shown ? `This match's moments are past the first ${r.shown} exported; open the full list on the app.` : 'No moments behind this number in this match.';
    }
    return r;
  }
  function openReel(r, startAt = 0) {
    reel = r;
    const was = drawerOpen();
    renderClips();
    const first = r.items.findIndex((it, i) => i >= startAt && it.video);
    if (first >= 0) play(first, true); else if (r.items.length) { reel.i = startAt; renderClips(); stopVideo(r.items[startAt] ? 'nolink' : ''); }
    else stopVideo('');
    // The first number opens the drawer and moves keyboard focus into it (Escape or Close brings it back); while it is
    // open, later numbers just change what it plays, so a scout can keep arrowing through the table.
    openDrawer(!was);
    out(`Playing ${r.title}: ${plural(r.items.length, r.unit === 'match' ? 'match' : 'moment')}${r.total > r.items.length && !r.match ? ` of ${r.total}` : ''}.`);
  }
  const drawerOpen = () => { const d = $('txDrawer'); return !!d && !d.hidden; };
  function openDrawer(focus) {
    const d = $('txDrawer'), was = !d.hidden;
    if (!was) {
      const from = actFrom && actFrom.el && document.contains(actFrom.el) ? actFrom : { el: document.activeElement };
      drawerFrom = from;
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
    paintKeys(); paintNav();
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
  // scrolls away, the site header, the row of view tabs under it and the terminal's own row of panels.
  function siteBottom() {
    const side = document.querySelector('.side'), top = document.querySelector('.top');
    return Math.max(0, side && getComputedStyle(side).flexDirection === 'row' ? side.getBoundingClientRect().bottom : 0, top ? top.getBoundingClientRect().bottom : 0);
  }
  function barBottom() {
    const bar = document.querySelector('.tx-top');
    if (bar && getComputedStyle(bar).position === 'sticky') return bar.getBoundingClientRect().bottom;
    // The panel row's bottom once it has stuck (where it will be after a scroll down), not where it sits before that.
    const nav = $('txNav');
    return Math.max(siteBottom(), nav && getComputedStyle(nav).display !== 'none' ? (parseFloat(nav.style.top) || 0) + nav.offsetHeight : 0);
  }
  // The phone's panel row sticks just under the site header and the view tabs, whose height depends on the screen.
  function placeNav() {
    const nav = $('txNav'); if (!nav || getComputedStyle(nav).display === 'none') return;
    const top = document.querySelector('.top'), side = document.querySelector('.side');
    let y = top ? top.offsetHeight : 0;
    if (side && getComputedStyle(side).flexDirection === 'row' && getComputedStyle(side).position === 'sticky') y += side.offsetHeight;
    nav.style.top = y + 'px';
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
  // list), chances made, skills and defending, each moment once (a goal is not also a shot, an assist not also a key pass),
  // in that order of importance and match by match within each. The export lists the first 10 moments of each stat.
  const HL_KINDS = [['goals', 'Goal', 'goals'], ['assists', 'Assist', 'assists'], ['penalties_saved', 'Penalty saved', 'penalties saved'],
    ['saves', 'Save', 'saves'], ['shots', 'Shot', 'other shots'], ['key_passes', 'Chance made', 'chances made'], ['nutmegs', 'Nutmeg', 'nutmegs'],
    ['skill_moves', 'Skill move', 'skill moves'], ['take_ons_won', 'Take-on won', 'take-ons won'], ['tackles_won', 'Tackle won', 'tackles won'],
    ['interceptions', 'Interception', 'interceptions'], ['blocks', 'Block', 'blocks']];
  const OUTCOME = { saved: 'saved', blocked: 'blocked', off_target: 'off target', goal: 'goal' };
  function highlightsReel(p) {
    const seen = new Set(), items = [], counts = [];
    const keyOf = (mo) => mo.clip_id || mo.video_url || `${mo.match_id}|${mo.t}`;
    for (const [mk, word, many] of HL_KINDS) {
      let got = [];
      if (mk === 'shots') {
        got = (p.shots || []).filter(sh => sh.outcome !== 'goal').map(sh => ({ mo: sh, val: `xG ${Number(sh.xg).toFixed(2)}`, note: `Shot, ${OUTCOME[sh.outcome] || String(sh.outcome).replace(/_/g, ' ')}${sh.penalty ? ' (penalty)' : ''}` }));
      } else {
        const ev = p.evidence && p.evidence[mk];
        if (!ev || ev.per_match || ev.keys) continue;
        got = ev.items.map(it => ({ mo: p.moments[it.m] || {}, val: '', note: word }));
      }
      got = got.filter(x => x.mo && x.mo.video_url && !seen.has(keyOf(x.mo)));
      got.sort((x, y) => (x.mo.round - y.mo.round) || (x.mo.minute - y.mo.minute));
      for (const x of got) { seen.add(keyOf(x.mo)); items.push({ when: `R${x.mo.round} v ${short(x.mo.opponent)}`, minute: x.mo.minute, val: x.val || word, note: x.val ? x.note : '', video: x.mo.video_url, match_id: x.mo.match_id }); }
      if (got.length) counts.push(got.length === 1 ? `1 ${mk === 'shots' ? 'other shot' : word.toLowerCase()}` : `${got.length} ${many}`);
    }
    return { title: `${p.name} · Highlights`, sub: counts.length ? cap1(listText(counts)) : 'No moments yet', kind: 'highlights', counts,
      total: items.length, shown: items.length, items, i: -1, pid: p.id, mk: null, match: null, full: '',
      note: items.length ? '' : `${p.name} has no goals, shots, chances made, skills or defensive moments with a clip this season.`,
      legend: items.length ? 'Goals first, then the rest by importance, match by match.' : '' };
  }
  function playHighlights(p, alts) {
    select(p.id, true);
    const r = highlightsReel(p);
    openReel(r);
    out('', '', r.items.length ? esc(`Playing ${p.name}'s highlights: ${listText(r.counts)} (${plural(r.items.length, 'moment')}).`) + altsHtml(alts, 'HL')
      : esc(`${p.name} has no highlights to play yet.`) + altsHtml(alts, 'HL'));
  }
  function openEvidence(pid, mk, match) { if (PID.has(pid) && MK.has(mk)) openReel(evidenceReel(pid, mk, match)); }

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
    v.addEventListener('error', () => { if (v.getAttribute('src')) msg(`The clip did not load from ${APP}. Try again: each clip renders on its first request, which takes a few seconds.`); });
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
    const empty = !!reel && !reel.items.length;
    b.querySelector('.tx-screen').hidden = !reel || empty;
    b.querySelector('.tx-clipctl').hidden = !reel || empty;
    if (!reel) {
      head.innerHTML = '<p class="tx-dim">Click any underlined number in any panel: the moments behind it play here.</p>';
      list.innerHTML = ''; if (ctx) ctx.textContent = ''; return;
    }
    const capped = reel.total > reel.shown;
    head.innerHTML = `<p class="tx-ct">${esc(reel.title)}</p><p class="tx-cs">${esc(reel.sub)}</p>
      ${empty ? `<p class="tx-cs tx-none">${reel.note ? 'Nothing to play.' : 'Nothing to play: there are no moments behind this number.'}</p>` : `<p class="tx-cs">${reel.match ? `${reel.items.length} in this match` : capped ? `First ${reel.shown} of ${reel.total}${reel.unit === 'match' ? ' matches' : ''}` : `${reel.items.length} ${reel.unit === 'match' ? 'match' : 'moment'}${reel.items.length === 1 ? '' : (reel.unit === 'match' ? 'es' : 's')}`}${capped && reel.pid ? ` · <a href="${esc(reel.full)}" target="_blank" rel="noopener">all ${esc(reel.total)} on the app &#8599;</a>` : ''}</p>`}
      ${empty ? '' : reel.legend ? `<p class="tx-cs tx-dim">${esc(reel.legend)}</p>` : ''}${reel.note ? `<p class="tx-cs tx-dim">${esc(reel.note)}</p>` : ''}`;
    if (ctx) ctx.textContent = reel.items.length ? `${Math.max(0, reel.i) + 1}/${reel.items.length}` : '';
    list.innerHTML = reel.items.map((it, i) => `<li><button type="button" class="tx-clip${i === reel.i ? ' on' : ''}" data-act="clip" data-i="${i}" data-fid="clip-${i}"${i === reel.i ? ' aria-current="true"' : ''}>
        <span class="tx-cw">${esc(it.when)}${it.minute != null ? ` <b>${esc(it.minute)}'</b>` : ''}</span><span class="tx-cv">${esc(it.val)}</span><span class="tx-cn">${esc(it.note)}${it.video ? '' : ' <i>no clip</i>'}</span></button></li>`).join('');
  }
  function play(i, auto) {
    if (!reel || !reel.items[i]) return;
    reel.i = i; renderClips();
    const it = reel.items[i], v = clipVideo(); if (!v) return;
    if (!it.video) { stopVideo('nolink'); return; }
    msg('');
    const src = APP + it.video;
    if (v.getAttribute('src') !== src) { v.setAttribute('src', src); v.load(); } else v.currentTime = 0;
    if (auto) { const pr = v.play(); if (pr && pr.catch) pr.catch(() => {}); }
  }
  function stopVideo(why) {
    const v = clipVideo(); if (!v) return;
    v.pause(); v.removeAttribute('src'); v.load();
    msg(why === 'nolink' ? (reel && reel.note) || 'No clip for this moment.' : '');
  }

  // ------------------------------------------------------------------ SCRN: the screener
  function screenRows() {
    const sc = S.scr, q = norm(sc.q);
    const rows = D.players.filter(p => p.minutes > 0 && (!sc.pos || p.position === sc.pos) && (!sc.qual || p.qualified)
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
  // Exported values are rounded, so equal values may hide different true rates. Break the tie as the engine orders it (by
  // the unrounded value), in the sort direction: the unrounded rate where the counts give it, else the percentile (which
  // the engine computed from the unrounded values; it runs the metric's better way, so it flips for lower-is-better).
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
  // Rank numbers as the engine gives them: rows with the same shown value share a rank (1, 2, 2, 4); rows outside the
  // pool (under the minutes, or a ratio below the minimum attempts) are listed after, unranked.
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
    return D.groups.map(g => {
      const ms = D.metrics.filter(m => m.group === g.key && (!filter || filter(m)));
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
    const rows = screenRows();
    const sortAttr = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? 'descending' : 'ascending') : 'none';
    if (!scrAct || !rows.some(p => p.id === scrAct.pid)) scrAct = { pid: rows.some(p => p.id === S.focus) ? S.focus : (rows[0] && rows[0].id), c: 0 };
    if (scrAct.c > cols.length) scrAct.c = 0;
    const cell = (p, k, ci) => {
      const m = MK.get(k), c = cellOf(p, k), act = scrAct.pid === p.id && scrAct.c === ci + 1;
      if (!c) return `<td class="num"><span class="tx-dim">–</span></td>`;
      const txt = sc.mode === 'pct' ? (c.percentile == null ? '–' : c.percentile) : fmt(m, c.value);
      const np = noPct(p, m, c);
      const n = evCount(p, k);
      const lab = `${p.name}, ${m.label} ${withUnit(m, c.value)}${c.percentile != null ? `, ${ord(c.percentile)} percentile` : np ? `, ${np.text}` : ''}. ${cap1(playText(p, k))}`;
      return `<td class="num"><button type="button" class="tx-n${np && np.small ? ' uq' : ''}${zc(p, k)}" style="${shade(m, c.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-nav data-fid="c-${esc(p.id)}-${esc(k)}" tabindex="${act ? 0 : -1}" aria-label="${esc(lab)}">${esc(txt)}</button></td>`;
    };
    // A click on a header sorts (again: the other way); the sorted column is the yellow one, and the panel's header says
    // which way. Removing a column is in the Columns menu.
    const sortBtn = (k, label, extra = '') => `<button type="button" data-act="sort" data-k="${esc(k)}" data-fid="h-${esc(k)}"${extra}>${label}</button>`;
    const head = `<tr><th class="tx-stk" aria-sort="${sortAttr('name')}">${sortBtn('name', 'Player')}</th>
      <th class="tx-hc" aria-sort="${sortAttr('club')}">${sortBtn('club', 'Club')}</th><th class="tx-hc">Pos</th>
      <th class="num" aria-sort="${sortAttr('min')}">${sortBtn('min', 'Mins', ' title="Minutes played"')}</th>
      ${cols.map(k => { const m = MK.get(k); return `<th class="num" aria-sort="${sortAttr(k)}">${sortBtn(k, `${esc(shortLabel(m))}${m.kind === 'total' ? ' <span class="tx-u">(total)</span>' : ''}${noisy(m)}`, `${shortLabel(m).length <= 12 ? ' class="nw"' : ''} data-mk="${esc(k)}" aria-label="${esc(m.label)}${m.noisy ? ', small sample' : ''}, sort"`)}</th>`; }).join('')}</tr>`;
    const ranks = screenRanks(rows);
    const body = rows.map((p, r) => {
      const ci = S.compare.indexOf(p.id), act = scrAct.pid === p.id && scrAct.c === 0;
      return `<tr class="${p.id === S.focus ? 'on' : ''}${ci >= 0 ? ' cmp' : ''}" data-row="${esc(p.id)}"${ci >= 0 ? ` style="--c:${CMP_COL[ci]}"` : ''}>
        <th class="tx-stk" scope="row"><span class="tx-rk">${ranks[r] == null ? '–' : ranks[r]}</span><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-nav data-fid="n-${esc(p.id)}" tabindex="${act ? 0 : -1}"${p.id === S.focus ? ' aria-current="true"' : ''}>${esc(p.name)}</button><span class="tx-sub">${esc(p.short_name)} · ${esc(p.position)} ${esc(p.role)}</span></th>
        <td class="tx-hc">${esc(p.short_name)}</td><td class="tx-hc">${esc(p.position)} <span class="tx-dim">${esc(p.role)}</span></td><td class="num">${esc(Math.round(p.minutes))}</td>
        ${cols.map((k, i) => cell(p, k, i)).join('')}</tr>`;
    }).join('');
    const html = `<div class="tx-ctls">
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scrpos" data-v="${v || ''}" aria-pressed="${sc.pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-ctl"><span class="sr">Filter by name or club</span><input type="search" data-r="scrq" data-fid="scr-q" value="${esc(sc.q)}" placeholder="Filter by name or club" autocomplete="off"></label>
        <label class="tx-chk"><input type="checkbox" data-r="scrqual" data-fid="scr-qual"${sc.qual ? ' checked' : ''}> Regulars only (${esc(minMin())}+ minutes)</label>
        <div class="tx-seg" role="group" aria-label="Show"><button type="button" data-act="scrmode" data-v="val" aria-pressed="${sc.mode === 'val'}">Value</button><button type="button" data-act="scrmode" data-v="pct" aria-pressed="${sc.mode === 'pct'}">Percentile</button></div>
        <details class="tx-menu" data-r="colmenu"${colMenuOpen ? ' open' : ''}><summary class="tx-mini" data-fid="scr-cols">Columns (${cols.length})</summary>
          <div class="tx-menup" role="group" aria-label="Columns">
            ${cols.length ? `<ul class="tx-collist">${cols.map(k => { const m = MK.get(k); return `<li><span>${esc(m.label)}${noisy(m)}</span><button type="button" class="tx-x" data-act="rmcol" data-k="${esc(k)}" data-fid="rm-${esc(k)}" aria-label="Remove the ${esc(m.label)} column" title="Remove">&times;</button></li>`; }).join('')}</ul>` : '<p class="tx-dim">No stat columns.</p>'}
            <label class="tx-ctl tx-addcol"><span>Add</span><select data-r="addcol" data-fid="scr-add"><option value="">a stat…</option>${metricOptions(null, m => !cols.includes(m.key))}</select></label>
            <button type="button" class="tx-mini" data-act="scrdef">Default columns</button></div></details></div>
      <p class="tx-cap">${rows.length} ${esc(sc.pos ? POSN[sc.pos] : 'players')}${sc.qual ? ', regulars only' : ''} · <b class="tx-capu">${sc.mode === 'pct' ? 'percentiles vs the same position' : `values per 90 minutes${cols.some(k => { const x = MK.get(k); return x.kind !== 'per90' && x.kind !== 'padj'; }) ? ' (except %, averages and totals)' : ''}`}</b><span class="tx-capx">${sc.mode === 'pct' ? '' : ' · shading = percentile vs the same position'}${ranks.some(x => x == null) ? ' · – = not ranked (too few minutes or attempts)' : ''} · click a row to select, an underlined number to play its moments</span></p>
      <div class="tx-scroll tx-tablewrap"><table class="tx-table"><thead>${head}</thead><tbody data-r="grid">${body || `<tr><td colspan="${4 + cols.length}" class="tx-dim">No players match.</td></tr>`}</tbody></table></div>`;
    const sm = MK.get(sc.sort.k), dirWord = sc.sort.dir === -1 ? (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'Z to A' : 'highest first') : (sc.sort.k === 'name' || sc.sort.k === 'club' ? 'A to Z' : 'lowest first');
    const sortName = sm ? shortLabel(sm) : { name: 'name', club: 'club', min: 'minutes' }[sc.sort.k];
    paint('scrn', html, sortName ? esc(`Sorted by ${sortName}, ${dirWord}`) : '');
  }

  // ------------------------------------------------------------------ PLYR: the player card, top numbers, similar players
  function renderPlyr() {
    const p = PID.get(S.focus);
    const strengths = D.metrics.filter(m => m.positions.includes(p.position) && m.has_percentile && m.higher_is_better !== null && pctOf(p, m.key) != null)
      .sort((a, b) => pctOf(p, b.key) - pctOf(p, a.key)).slice(0, 6);
    const bio = [['Age', p.age], ['Height', p.height_cm ? p.height_cm + ' cm' : '–'], ['Foot', p.preferred_foot ? p.preferred_foot.charAt(0).toUpperCase() + p.preferred_foot.slice(1) : '–'], ['Nation', p.nationality],
      ['Minutes', Math.round(p.minutes)], ['Apps', p.appearances]];
    const html = `<div class="tx-card"><span class="tx-shirt" aria-hidden="true">${shirt(p)}</span>
        <div><p class="tx-name">${esc(p.name)}</p><p class="tx-line">${esc(p.club)} · ${esc(POS1[p.position])} (${esc(p.role)}) · #${esc(p.kit_number)}
          ${p.qualified ? `<span class="tx-tag" title="At least ${esc(minMin())} minutes, so the player has percentiles">Regular</span>` : `<span class="tx-tag dim">Under ${esc(minMin())} minutes</span>`}</p>
          <p class="tx-prof">${profileIds.has(p.id) ? `<a href="#scout/player/${encodeURIComponent(p.id)}">Open profile &rarr;</a>` : `<a href="${esc(`${APP}/players/${encodeURIComponent(p.id)}`)}" target="_blank" rel="noopener">Open profile on the live app &#8599;</a>`}</p></div></div>
      <dl class="tx-bio">${bio.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      <div class="tx-acts"><button type="button" class="tx-mini" data-act="cmpwith" data-fid="card-cmp"${S.compare.length >= 3 && S.compare.includes(p.id) ? ' disabled' : ''}>Compare with…</button>
        <button type="button" class="tx-mini" data-act="run" data-keep data-cmd="highlights ${esc(p.name)}" title="Goals, shots, chances made, skills and defending in one reel">Highlights</button><button type="button" class="tx-mini" data-act="run" data-keep data-cmd="shots ${esc(p.name)}">Shots</button><button type="button" class="tx-mini" data-act="run" data-keep data-cmd="form ${esc(p.name)}">Form</button>
        <button type="button" class="tx-mini" data-act="run" data-keep data-cmd="team ${esc(p.club)}">Team</button></div>
      ${p.minutes > 0 ? `<h3 class="tx-h3">Best among ${esc(POSN[p.position])}</h3>
      <table class="tx-mt"><tbody>${strengths.map(m => mrow(p, m)).join('')}</tbody></table>
      <p class="tx-cap">/90 = per 90 minutes played. The bar and the last number are the percentile among regular ${esc(POSN[p.position])}.</p>` : '<p class="tx-dim">No minutes this season.</p>'}
      <h3 class="tx-h3" id="txSimHead" tabindex="-1">Plays like</h3>
      ${(p.similar || []).length ? `<ol class="tx-sim">${p.similar.map(s => { const q = PID.get(s.id); return `<li><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(s.id)}" data-fid="sim-${esc(s.id)}">${esc(s.name)}</button>
        <span class="tx-dim">${esc(short(s.club_id))} ${esc(q ? q.position : '')}</span><span class="tx-simbar" aria-label="similarity ${esc(s.similarity)}"><i style="width:${Math.max(2, Math.round(s.similarity * 100))}%"></i></span><span class="num">${esc(s.similarity.toFixed(2))}</span>
        <span class="tx-shared">${s.shared_strengths.filter(k => MK.has(k)).map(k => `<button type="button" class="tx-kchip" data-act="ev" data-pid="${esc(s.id)}" data-mk="${esc(k)}" data-fid="sim-${esc(s.id)}-${esc(k)}">${esc(MK.get(k).label)}</button>`).join('')}</span></li>`; }).join('')}</ol>
        <p class="tx-cap">Similarity (1 = identical) on the ${esc(p.position === 'GK' ? 'goalkeeper' : 'outfield')} stats; the chips are strengths they share (each plays that player's moments).</p>` : '<p class="tx-dim">No similar players (too few minutes).</p>'}`;
    paint('plyr', html, esc(p.short_name));
  }
  // One metric row: label (definition on hover), value button (evidence), percentile bar.
  function mrow(p, m, opts = {}) {
    const c = cellOf(p, m.key);
    const val = c ? `<button type="button" class="tx-n${zc(p, m.key)}" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(m.key)}" data-fid="${esc((opts.fid || 'm') + '-' + p.id + '-' + m.key)}" aria-label="${esc(`${m.label} ${withUnit(m, c.value)}, ${playText(p, m.key)}`)}">${esc(fmt(m, c.value))}</button>` : '<span class="tx-dim">–</span>';
    const pc = c ? c.percentile : null;
    return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(m.key)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${unitMark(m)}</th><td class="num">${val}</td>
      <td class="tx-pbar"><span class="tx-bar" style="--g:${GROUP_COL[m.group] || '#ffcd28'}"><i style="width:${pc == null ? 0 : Math.max(2, pc)}%"></i></span></td><td class="num tx-pc">${pc == null ? '–' : esc(pc)}</td></tr>`;
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
      const m = MK.get(k), lab = shortLabel(m), t = lab.length > 18 ? lab.slice(0, 17) + '…' : lab;
      return `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${s > 0.25 ? 'start' : s < -0.25 ? 'end' : 'middle'}" class="tx-axl"><title>${esc(m.label)}</title>${esc(t)}</text>`;
    }).join('');
  }
  function renderRadar() {
    const f = PID.get(S.focus);
    const players = S.compare.length >= 2 ? S.compare.map(id => PID.get(id)) : [f];
    const base = players[0], outsider = players.length > 1 && !S.compare.includes(f.id) ? f : null;
    const keys = (S.radar.tpl === 'all' ? D.default_columns.all : (D.default_columns[base.position] || D.default_columns.all)).filter(k => MK.has(k));
    const n = keys.length, cx = 180, cy = 158, R = 96, r0 = 14;
    let svg = `<svg viewBox="0 0 360 316" class="tx-svg tx-radar" aria-hidden="true">`;
    for (const q of [25, 50, 75, 100]) svg += `<circle cx="${cx}" cy="${cy}" r="${(r0 + (R - r0) * q / 100).toFixed(1)}" class="tx-ring"/>`;
    if (players.length === 1) {
      keys.forEach((k, i) => {
        const a0 = i * 2 * Math.PI / n + 0.01, a1 = (i + 1) * 2 * Math.PI / n - 0.01, pc = pctOf(base, k), m = MK.get(k);
        const r1 = r0 + (R - r0) * (pc == null ? 0 : Math.max(3, pc)) / 100;
        svg += `<path d="${wedge(cx, cy, r0, R, a0, a1)}" class="tx-wbg"/>`;
        if (pc != null) svg += `<path d="${wedge(cx, cy, r0, r1, a0, a1)}" fill="${GROUP_COL[m.group] || '#ffcd28'}" fill-opacity="${m.higher_is_better === null ? 0.45 : 0.85}" class="tx-wedge" data-act="ev" data-pid="${esc(base.id)}" data-mk="${esc(k)}"><title>${esc(m.label)}: ${esc(fmt(m, cellOf(base, k).value))}, ${esc(ord(pc))} percentile</title></path>`;
        // The value sits inside its wedge when the wedge has room (black on a solid wedge, white on a style marker's paler
        // one), else just outside it in light text on the dark ring: each choice is at least 4.5:1.
        const inside = r1 - r0 >= 18, [tx, ty] = polar(cx, cy, inside ? r1 - 9 : r1 + 9, (a0 + a1) / 2);
        const tone = !inside ? 'out' : m.higher_is_better === null ? 'lt' : '';
        svg += `<text x="${tx.toFixed(1)}" y="${(ty + 4).toFixed(1)}" text-anchor="middle" class="tx-wv ${tone}">${pc == null ? '' : esc(pc)}</text>`;
      });
    } else {
      keys.forEach((k, i) => { const [x, y] = polar(cx, cy, R, (i + 0.5) * 2 * Math.PI / n); svg += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="tx-ring"/>`; });
      const ptsOf = (p) => keys.map((k, i) => { const pc = pctOf(p, k); return polar(cx, cy, r0 + (R - r0) * (pc == null ? 0 : pc) / 100, (i + 0.5) * 2 * Math.PI / n).map(v => v.toFixed(1)).join(','); }).join(' ');
      players.forEach((p, j) => { svg += `<polygon points="${ptsOf(p)}" fill="${CMP_COL[j]}" fill-opacity=".14" stroke="${CMP_COL[j]}" stroke-width="2"/>`; });
      // The selected player, when not one of the compared, is drawn as a dashed outline so selecting a player still moves the radar.
      if (outsider) svg += `<polygon points="${ptsOf(f)}" fill="none" stroke="#fff" stroke-width="1.5" stroke-dasharray="4 3" class="tx-rfocus"/>`;
    }
    svg += axisLabels(keys, cx, cy, R) + '</svg>';
    const legend = players.map((p, j) => `<button type="button" class="tx-leg" style="--c:${CMP_COL[players.length > 1 ? j : 0]}" data-act="sel" data-pid="${esc(p.id)}" data-fid="rl-${esc(p.id)}">${esc(p.name)} <span class="tx-dim">${esc(p.short_name)} ${esc(p.position)}</span></button>`).join('')
      + (outsider ? `<span class="tx-leg tx-legf">${esc(outsider.name)} <span class="tx-dim">${esc(outsider.short_name)} ${esc(outsider.position)} · selected, dashed</span></span>` : '');
    const outLine = outsider ? `<p class="tx-cap tx-rnote">Comparing ${players.length}; ${esc(outsider.name)} (selected) is the dashed outline, not in the table. <button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(outsider.id)}" data-fid="r-add">Add to the comparison${players.length >= 3 ? ` (replaces ${esc(players[0].name.split(' ').slice(-1)[0])})` : ''}</button></p>` : '';
    const tbl = players.length === 1 ? `<table class="tx-mt"><tbody>${keys.map(k => mrow(base, MK.get(k), { fid: 'r' })).join('')}</tbody></table>`
      : `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cmp"><thead><tr><th>Metric</th>${players.map((p, j) => `<th class="num" style="color:${CMP_COL[j]}">${esc(initials(p))}</th>`).join('')}</tr></thead><tbody>
        ${keys.map(k => { const m = MK.get(k); return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(k)}">${esc(m.label)}${noisy(m)}</span>${unitMark(m)}</th>${players.map(p => { const c = cellOf(p, k); return `<td class="num">${c ? `<button type="button" class="tx-n${zc(p, k)}" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="rc-${esc(p.id)}-${esc(k)}" aria-label="${esc(`${p.name}, ${m.label} ${withUnit(m, c.value)}, ${playText(p, k)}`)}">${esc(fmt(m, c.value))}</button><span class="tx-pc"> ${c.percentile == null ? '–' : esc(c.percentile)}</span>` : '<span class="tx-dim">–</span>'}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div>`;
    const html = `<div class="tx-ctls"><div class="tx-seg" role="group" aria-label="Metrics"><button type="button" data-act="rtpl" data-v="pos" aria-pressed="${S.radar.tpl === 'pos'}">${esc(POS1[base.position])} stats</button><button type="button" data-act="rtpl" data-v="all" aria-pressed="${S.radar.tpl === 'all'}">All-round</button></div></div>
      <div class="tx-legs">${legend}</div>${outLine}${svg}
      <p class="tx-cap">/90 = per 90 minutes. Percentile vs regular ${esc(players.length > 1 ? 'players in each one’s own position' : POSN[base.position])}${players.length > 1 ? '' : '; blue-grey wedges are style markers (ranked, not judged)'}. Values play their moments.</p>${tbl}`;
    paint('radar', html, players.length > 1 ? esc(`Comparing ${players.length}${outsider ? ` + ${outsider.name.split(' ').slice(-1)[0]}` : ''}`) : esc(`vs ${POSN[base.position]}`));
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
  function numBtn(p, k, fid) {
    const m = MK.get(k), c = cellOf(p, k); if (!m) return '';
    return `<span class="tx-stat"><span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${c ? `<button type="button" class="tx-n${zc(p, k)}" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="${esc(fid + k)}" aria-label="${esc(`${m.label} ${withUnit(m, c.value)}, ${playText(p, k)}`)}">${esc(fmt(m, c.value))}</button>${c.total != null && m.kind !== 'total' && m.kind !== 'ratio' ? `<span class="tx-dim">${esc(c.total)} in total</span>` : ''}` : '<span class="tx-dim">–</span>'}</span>`;
  }
  function renderShot() {
    const p = PID.get(S.focus), shots = p.shots || [];
    const playing = reel && reel.kind === 'shots' && reel.pid === p.id ? reel.i : -1;
    let svg = `<svg viewBox="51.5 -1.5 55 71" class="tx-svg tx-pitchsvg" role="group" aria-label="Shot map, ${shots.length} shots; each plays its clip">${halfPitch()}`;
    shots.forEach((s, i) => {
      const r = (0.9 + Math.sqrt(s.xg) * 3.4).toFixed(2);
      const lab = `R${s.round} v ${short(s.opponent)} ${s.minute}', ${s.body_part.replace('_', ' ')}, xG ${s.xg.toFixed(2)}, ${OUTC[s.outcome] || s.outcome}${s.penalty ? ', penalty' : ''}. Play`;
      svg += `<g class="tx-shot o-${esc(s.outcome)}${i === playing ? ' on' : ''}" role="button" tabindex="0" data-act="shot" data-i="${i}" data-fid="shot-${i}" aria-label="${esc(lab)}"><circle cx="${s.x}" cy="${s.y}" r="${r}"/><title>${esc(lab)}</title></g>`;
    });
    svg += '</svg>';
    const nps = shots.filter(s => !s.penalty);
    const html = shots.length || p.minutes ? `<div class="tx-stats">${['shots', 'goals', 'npxg', 'npxg_per_shot', 'shots_on_target'].map(k => numBtn(p, k, 'sh-')).join('')}</div>${svg}
      <p class="tx-legend"><span class="o-goal">● Goal</span> <span class="o-saved">● Saved</span> <span class="o-blocked">● Blocked</span> <span class="o-off_target">○ Off target</span> · size = xG · ${nps.length} non-penalty, ${shots.length - nps.length} penalty</p>`
      : '<p class="tx-dim">No minutes this season.</p>';
    paint('shot', shots.length ? html : html.replace('</svg>', '<text x="78" y="36" text-anchor="middle" class="tx-axl" style="font-size:3.4px">No shots</text></svg>'), esc(`${p.name} · ${plural(shots.length, 'shot')}`));
  }
  function shotReel(p, start) {
    const r = { kind: 'shots', pid: p.id, title: `${p.name} · Shots`, sub: `${p.shots.length} shots, penalties included`, total: p.shots.length, shown: p.shots.length, i: -1, note: '',
      items: p.shots.map(s => ({ when: `R${s.round} v ${short(s.opponent)}`, minute: s.minute, val: `xG ${s.xg.toFixed(2)}`, note: `${OUTC[s.outcome] || s.outcome}${s.penalty ? ' · pen' : ''} · ${s.body_part.replace('_', ' ')}`, video: s.video_url, match_id: s.match_id })) };
    openReel(r, start);
    if (visible('shot')) renderShot();
  }
  function renderHeat() {
    const p = PID.get(S.focus), hm = p.heatmap || [];
    const [cols, rows] = D.pitch.heatmap_grid, cw = 105 / cols, ch = 68 / rows;
    const max = Math.max(1, ...hm.flat()), total = hm.flat().reduce((a, b) => a + b, 0);
    let cells = '';
    hm.forEach((row, y) => row.forEach((v, x) => { if (v) cells += `<rect x="${(x * cw).toFixed(2)}" y="${(y * ch).toFixed(2)}" width="${cw.toFixed(2)}" height="${ch.toFixed(2)}" fill="#ffcd28" fill-opacity="${(0.08 + 0.8 * v / max).toFixed(3)}"><title>${v} on-ball action${v === 1 ? '' : 's'}</title></rect>`; }));
    const EVN = { touch: 'touches', pass: 'passes', cross: 'crosses', carry: 'carries', take_on: 'take-ons', shot: 'shots', tackle: 'tackles', interception: 'interceptions', recovery: 'recoveries', clearance: 'clearances' };
    const evs = (D.pitch.heatmap_events || []).map(e => EVN[e] || e.replace(/_/g, ' '));
    const evList = evs.length > 1 ? `${evs.slice(0, -1).join(', ')} and ${evs[evs.length - 1]}` : evs.join('');
    const html = `<div class="tx-stats">${['touches', 'touches_in_box', 'progressive_passes_received'].map(k => numBtn(p, k, 'ht-')).join('')}</div>
      <svg viewBox="-1.5 -1.5 108 71" class="tx-svg tx-pitchsvg" role="img" aria-label="Heat map: ${total} on-ball actions, attacking left to right"><rect x="0" y="0" width="105" height="68" class="tx-turf"/>${cells}${fullPitch()}<path d="M44,72 L61,72" class="tx-dir"/></svg>
      <p class="tx-cap">${esc(total)} on-ball actions this season (${esc(evList)}), so more than the Touches count, which is touch records only. Attacking left to right, ${esc(cols)} by ${esc(rows)} cells. The map has no clip per cell; the numbers above open their moments.</p>`;
    paint('heat', html, esc(p.name));
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
  function renderForm() {
    const p = PID.get(S.focus), fm = p.form;
    const defs = (D.default_columns[p.position] || D.default_columns.all).filter(k => MK.has(k));
    const k = S.form.k && MK.has(S.form.k) ? S.form.k : defs[0], m = MK.get(k);
    if (!fm || !fm.matches || !fm.matches.length) { paint('form', '<p class="tx-dim">No matches this season.</p>', esc(p.short_name)); return; }
    const vals = fm.values[k] || [], cell = cellOf(p, k);
    // The dashed line is in the bars' unit: a season count (clean sheets, cards) is drawn as its average per match played,
    // never as the season total over bars that count one match each.
    const isTotal = m.kind === 'total';
    const season = cell && cell.value != null ? { value: isTotal ? cell.value / fm.matches.length : cell.value } : null;
    const seasonLab = season ? (isTotal ? `season ${Number(season.value).toFixed(2)} a match (${fmt(m, cell.value)} in ${fm.matches.length})` : `season ${fmt(m, season.value)}`) : '';
    // Drawn at the panel's own width (one unit = one pixel) so the labels stay at their CSS size; the scale always holds
    // zero, so negative values (xT added, goals minus xG, on-pitch differences) hang below a zero line inside the chart.
    const W = svgWidth('form', 300), H = 200, L = 40, B = 36, T = 16, n = fm.matches.length, bw = (W - L - 8) / n;
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
    fm.matches.forEach((mm, i) => {
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
        + `<text x="${cx}" y="${H - B + 15}" text-anchor="middle" class="tx-axl">R${esc(mm.round)}</text><text x="${cx}" y="${H - B + 29}" text-anchor="middle" class="tx-axl dim">${mm.home ? '' : '@'}${esc(short(mm.opponent))}</text><title>${esc(lab)}</title></g>`;
    });
    if (season && season.value != null) { const ys = y(season.value).toFixed(1); svg += `<line x1="${L}" y1="${ys}" x2="${W - 4}" y2="${ys}" class="tx-avg"/><text x="${W - 6}" y="${(season.value < 0 ? +ys + 13 : ys - 4)}" text-anchor="end" class="tx-avgl">${esc(seasonLab)}</text>`; }
    svg += '</svg>';
    const cons = fm.consistency || {};
    const ctab = Object.keys(cons).filter(c => MK.has(c)).map(c => { const cm = MK.get(c), x = cons[c], tr = x.last3_minus_season;
      return `<tr${c === k ? ' class="on"' : ''}><th scope="row"><button type="button" class="tx-lk" data-act="formk" data-k="${esc(c)}" data-mk="${esc(c)}" data-fid="fk-${esc(c)}">${esc(cm.label)}${noisy(cm)}</button></th>
        <td class="num"><button type="button" class="tx-n${zc(p, c)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(c)}" data-fid="fm-${esc(c)}" aria-label="${esc(`${cm.label} mean ${x.mean}, ${playText(p, c)}`)}">${esc(fmt(cm, x.mean))}</button></td><td class="num">${esc(x.sd)}</td><td class="num">${x.cv == null ? '–' : esc(x.cv)}</td>
        <td class="num ${tr > 0 ? 'up' : tr < 0 ? 'dn' : ''}">${tr == null ? '–' : (tr > 0 ? '+' : '') + esc(tr)}</td></tr>`; }).join('');
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span class="sr">Metric</span><select data-r="formk" data-fid="form-k">${metricOptions(k)}</select></label>
        <span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}" tabindex="0">${esc(m.label)}${noisy(m)} <span class="tx-dim">ⓘ</span></span></div>${svg}
      <p class="tx-cap">${esc(FORM_UNIT[m.kind] || 'Each match')}. Bars open that match's moments.</p>
      ${ctab ? `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cons"><thead><tr><th>Consistency</th><th class="num">Mean</th><th class="num" title="Standard deviation across matches">SD</th><th class="num" title="Coefficient of variation: SD divided by the mean">CV</th><th class="num" title="The last three matches minus the season">Last 3 vs season</th></tr></thead><tbody>${ctab}</tbody></table></div>` : ''}`;
    paint('form', html, esc(`${p.name} · ${plural(fm.matches.length, 'match')}`));
  }

  // ------------------------------------------------------------------ SCAT: one metric against another
  function scatPoints() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y);
    const ok = (m, c, p) => m.has_percentile ? c.percentile != null : p.qualified;
    return D.players.filter(p => p.minutes > 0 && (!pos || p.position === pos)).map(p => ({ p, a: cellOf(p, x), b: cellOf(p, y) }))
      .filter(o => o.a && o.b && o.a.value != null && o.b.value != null && (all || (ok(mx, o.a, o.p) && ok(my, o.b, o.p))))
      .sort((u, v) => u.a.value - v.a.value || u.b.value - v.b.value);
  }
  function renderScat() {
    const { x, y, pos, all } = S.scat, mx = MK.get(x), my = MK.get(y), pts = scatPoints();
    const W = svgWidth('scat', 300), H = Math.round(Math.min(340, Math.max(250, W * 0.62))), L = 48, B = 38, T = 14, R = 14;
    const xs = pts.map(o => o.a.value), ys = pts.map(o => o.b.value);
    const ext = (a) => { let lo = Math.min(...a), hi = Math.max(...a); if (!a.length) { lo = 0; hi = 1; } if (lo === hi) { lo -= 1; hi += 1; } const pad = (hi - lo) * 0.06; return [lo >= 0 ? Math.max(0, lo - pad) : lo - pad, hi + pad]; };
    const [x0, x1] = ext(xs), [y0, y1] = ext(ys);
    const sx = (v) => L + (W - L - R) * (v - x0) / (x1 - x0), sy = (v) => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
    const med = (a) => { if (!a.length) return null; const s = [...a].sort((p, q) => p - q), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
    const mxv = med(xs), myv = med(ys);
    if (scatCur != null && (scatCur < 0 || scatCur >= pts.length)) scatCur = null;
    const cur = scatCur != null ? pts[scatCur] : pts.find(o => o.p.id === S.focus) || null;
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="tx-svg tx-scat" tabindex="0" data-fid="scat-svg" data-r="scat" role="group" aria-label="${esc(`Scatter, ${mx.label} against ${my.label}, ${pts.length} players. Arrow keys move between players, Enter selects`)}">`;
    svg += `<line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" class="tx-ax"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" class="tx-ax"/>`;
    for (const t of [0, 0.5, 1]) {
      const vx = x0 + (x1 - x0) * t, vy = y0 + (y1 - y0) * t;
      svg += `<text x="${sx(vx).toFixed(1)}" y="${H - B + 15}" text-anchor="${t === 0 ? 'start' : t === 1 ? 'end' : 'middle'}" class="tx-axl">${esc(fmt(mx, vx))}</text><text x="${L - 4}" y="${(sy(vy) + 3).toFixed(1)}" text-anchor="end" class="tx-axl">${esc(fmt(my, vy))}</text>`;
    }
    svg += `<text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle" class="tx-axt">${esc(mx.label)} →</text><text x="13" y="${(T + H - B) / 2}" text-anchor="middle" class="tx-axt" transform="rotate(-90 13 ${(T + H - B) / 2})">${esc(my.label)} →</text>`;
    if (mxv != null) svg += `<line x1="${sx(mxv).toFixed(1)}" y1="${T}" x2="${sx(mxv).toFixed(1)}" y2="${H - B}" class="tx-med"/><line x1="${L}" y1="${sy(myv).toFixed(1)}" x2="${W - R}" y2="${sy(myv).toFixed(1)}" class="tx-med"/>`;
    const layer = (o, i) => {
      const ci = S.compare.indexOf(o.p.id), isF = o.p.id === S.focus, isC = cur && cur.p === o.p;
      const col = isF ? '#ffcd28' : ci >= 0 ? CMP_COL[ci] : null;
      return `<g class="tx-dot${col ? ' hi' : ''}${isC ? ' cur' : ''}" data-act="sel" data-pid="${esc(o.p.id)}" data-i="${i}"><circle cx="${sx(o.a.value).toFixed(1)}" cy="${sy(o.b.value).toFixed(1)}" r="${col ? 5 : 3.4}"${col ? ` fill="${col}"` : ''}/>`
        + (col || isC ? `<text x="${(sx(o.a.value) + 7).toFixed(1)}" y="${(sy(o.b.value) - 6).toFixed(1)}" class="tx-dl">${esc(o.p.name.split(' ').slice(-1)[0])}</text>` : '')
        + `<title>${esc(`${o.p.name} (${o.p.short_name}): ${mx.label} ${fmt(mx, o.a.value)}, ${my.label} ${fmt(my, o.b.value)}`)}</title></g>`;
    };
    const order = pts.map((o, i) => [o, i]).sort(([a], [b]) => ((a.p.id === S.focus || S.compare.includes(a.p.id)) - (b.p.id === S.focus || S.compare.includes(b.p.id))));
    svg += order.map(([o, i]) => layer(o, i)).join('') + '</svg>';
    const read = cur ? `<p class="tx-read"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(cur.p.id)}" data-fid="scat-sel">${esc(cur.p.name)}</button> <span class="tx-dim">${esc(cur.p.short_name)} ${esc(cur.p.position)}</span>
        <span class="tx-ml" data-mk="${esc(x)}">${esc(mx.label)}</span><button type="button" class="tx-n${zc(cur.p, x)}" style="${shade(mx, cur.a.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(x)}" data-fid="scat-x">${esc(fmt(mx, cur.a.value))}</button>
        <span class="tx-ml" data-mk="${esc(y)}">${esc(my.label)}</span><button type="button" class="tx-n${zc(cur.p, y)}" style="${shade(my, cur.b.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(y)}" data-fid="scat-y">${esc(fmt(my, cur.b.value))}</button></p>`
      : '<p class="tx-read tx-dim">The selected player is not on this chart (position, or not a regular). Arrow keys in the chart pick a player.</p>';
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span>X</span><select data-r="scx" data-fid="scat-xs">${metricOptions(x)}</select></label>
        <label class="tx-ctl"><span>Y</span><select data-r="scy" data-fid="scat-ys">${metricOptions(y)}</select></label>
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scpos" data-v="${v || ''}" aria-pressed="${pos === v}" title="${v ? esc(POS1[v] + 's') : 'Every position'}">${v || 'All'}</button>`).join('')}</div>
        <label class="tx-chk"><input type="checkbox" data-r="scall" data-fid="scat-all"${all ? ' checked' : ''}> Include non-regulars</label></div>${svg}${read}
      <p class="tx-cap">${pts.length} ${esc(pos ? POSN[pos] : 'players')}${all ? '' : ', regulars with a value on both'} · dashed lines = medians · click a dot to select</p>`;
    paint('scat', html, esc(`${shortLabel(mx)} against ${shortLabel(my)}`));
  }

  // ------------------------------------------------------------------ TEAM: team style
  function renderTeam() {
    const t = TEAMS.get(S.club), c = club(S.club), row = D.table.find(r => r.club_id === S.club) || {};
    if (!t) { paint('team', '<p class="tx-dim">No team.</p>'); return; }
    const vals = (k) => D.teams.map(x => x.values[k] && x.values[k].value).filter(v => v != null);
    const rows = D.team_metrics.map(m => {
      const v = t.values[m.key]; if (!v) return '';
      const all = vals(m.key), lo = Math.min(...all), hi = Math.max(...all), w = hi === lo ? 50 : 4 + 92 * (v.value - lo) / (hi - lo);
      const mean = hi === lo ? 50 : 4 + 92 * (v.league_mean - lo) / (hi - lo);
      const judged = m.higher_is_better !== null, good = judged && ((m.higher_is_better && v.rank <= 2) || (!m.higher_is_better && v.rank <= 2));
      return `<tr><th scope="row"><span class="tx-ml" data-tk="${esc(m.key)}">${esc(m.label)}</span>${m.kind === 'per90' ? '<span class="tx-dim tx-u"> /90</span>' : ''}</th>
        <td class="num"><button type="button" class="tx-n" data-act="tev" data-cid="${esc(S.club)}" data-tk="${esc(m.key)}" data-fid="tv-${esc(m.key)}" aria-label="${esc(`${c.name}, ${m.label} ${fmt(m, v.value)}, rank ${v.rank} of ${v.of}. Open the matches behind it`)}">${esc(fmt(m, v.value))}</button></td>
        <td class="num ${good ? 'up' : ''}">${esc(v.rank)}/${esc(v.of)}</td><td class="num tx-dim">${esc(fmt(m, v.league_mean))}</td>
        <td class="tx-pbar"><span class="tx-range"><i style="left:${w.toFixed(1)}%" class="${judged ? '' : 'style'}"></i><b style="left:${mean.toFixed(1)}%"></b></span></td></tr>`;
    }).join('');
    const lowBest = D.team_metrics.filter(m => m.higher_is_better === false).map(m => /^[A-Z][a-z]/.test(m.label) ? m.label[0].toLowerCase() + m.label.slice(1) : m.label);
    const squad = D.players.filter(p => p.club_id === S.club).sort((a, b) => b.minutes - a.minutes);
    const html = `<div class="tx-seg tx-clubs" role="group" aria-label="Club">${D.clubs.map(k => `<button type="button" data-act="club" data-cid="${esc(k.club_id)}" aria-pressed="${k.club_id === S.club}" title="${esc(k.name)}">${esc(k.short_name)}</button>`).join('')}</div>
      <p class="tx-name">${esc(c.name)} <span class="tx-dim">${esc(ord(row.position || 0))} · ${esc(row.points)} pts · ${esc(row.won)}-${esc(row.drawn)}-${esc(row.lost)} · ${esc(row.goals_for)}:${esc(row.goals_against)}</span></p>
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style</th><th class="num">Value</th><th class="num">Rank</th><th class="num">League avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div><h3 class="tx-h3">Squad by minutes</h3><ol class="tx-squad tx-scroll">${squad.map(p => `<li class="${p.id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-fid="sq-${esc(p.id)}">${esc(p.name)}</button><span class="tx-dim">${esc(p.position)} #${esc(p.kit_number)}</span><span class="num">${esc(Math.round(p.minutes))}′</span></li>`).join('')}</ol></div></div>
      <p class="tx-cap">Rank 1 = best${lowBest.length ? `: the lowest for ${esc(listText(lowBest))}` : ''}. Grey markers are style, ranked but not judged, and their rank 1 is the highest. The bar spans the league's six clubs; the white tick is the league average. /90 = per 90 minutes; possession, PPDA and the other ratios are season values over every match. Shot numbers (xG, goals, shots) open every shot behind them; the others open one value per match.</p>`;
    paint('team', html, esc(c.short_name));
  }
  // The shots behind a team's shot-based numbers, from the season's shot records (every league shot is in the export with
  // its clip): 'for' is the club's own players, 'against' their opponents in the club's matches.
  const TEAM_SHOTS = {
    xg_for: { side: 'for', v: 'xg' }, npxg_for: { side: 'for', v: 'xg', keep: (s) => !s.penalty }, penalty_xg: { side: 'for', v: 'xg', keep: (s) => s.penalty },
    xg_against: { side: 'against', v: 'xg' }, goals_for: { side: 'for', v: 'n', keep: (s) => s.outcome === 'goal' },
    goals_against: { side: 'against', v: 'n', keep: (s) => s.outcome === 'goal' }, shots_for: { side: 'for', v: 'n' }, shots_against: { side: 'against', v: 'n' },
  };
  function teamShots(t, tk) {
    const spec = TEAM_SHOTS[tk]; if (!spec) return null;
    const ms = new Set(t.per_match.map(pm => pm.match_id)), hits = [];
    for (const h of SHOTS.values()) {
      if (!ms.has(h.s.match_id) || (h.p.club_id === t.club_id) !== (spec.side === 'for') || (spec.keep && !spec.keep(h.s))) continue;
      hits.push(h);
    }
    hits.sort((a, b) => a.s.round - b.s.round || a.s.t - b.s.t);
    return { spec, hits };
  }
  const teamUnit = (m) => m.kind === 'per90' ? 'per 90' : m.unit === '%' ? '' : m.unit;
  function teamReel(cid, tk) {
    const t = TEAMS.get(cid), m = TK.get(tk), v = t.values[tk], u = teamUnit(m);
    const r = { title: `${t.club} · ${m.label}`, sub: `${fmt(m, v.value)}${u ? ' ' + u : ''} · rank ${v.rank} of ${v.of}${v.total != null ? ` · ${Number(v.total.toFixed ? v.total.toFixed(2) : v.total)} in total` : ''}`, i: -1, items: [], note: '' };
    const ev = (t.evidence || {})[tk === 'set_piece_shots' ? 'set_piece_xg' : tk], ts = teamShots(t, tk);
    const shotRow = (h) => ({ when: `R${h.s.round} v ${short(h.s.opponent)}`, minute: h.s.minute, val: `xG ${h.s.xg.toFixed(2)}`,
      note: `${h.p.name}${h.p.club_id === cid ? '' : ' (' + h.p.short_name + ')'} · ${OUTC[h.s.outcome] || h.s.outcome}${h.s.penalty ? ' · pen' : ''}`, video: h.s.video_url, match_id: h.s.match_id });
    if (ts) {
      r.items = ts.hits.map(shotRow);
      r.total = r.shown = r.items.length;
      const sum = ts.spec.v === 'xg' ? ts.hits.reduce((a, h) => a + h.s.xg, 0) : ts.hits.length;
      const match = v.total == null || Math.abs(sum - v.total) < 0.011, noun = /^goals_/.test(tk) ? 'goal' : tk === 'penalty_xg' ? 'penalty' : 'shot';
      const tot = (x) => ts.spec.v === 'xg' ? `${Number(x).toFixed(2)} xG` : String(x);
      r.note = !ts.hits.length ? `No ${noun === 'penalty' ? 'penalties' : noun + 's'} behind this number this season.`
        : `Every ${ts.spec.side === 'for' ? '' : 'opponent '}${noun} behind this number, each with its clip${match ? `; they add up to the season total (${tot(v.total != null ? v.total : sum)})` : `; they add up to ${tot(sum)}, the engine's total is ${tot(v.total)}`}.`;
    } else if (ev && ev.length) {
      r.items = ev.map(e => { const hit = SHOTS.get(e.match_id + '|' + e.event_id), mt = D.matches.find(x => x.match_id === e.match_id) || {};
        const opp = mt.home === cid ? mt.away : mt.home;
        return { when: `R${e.round} v ${short(opp)}`, minute: hit ? hit.s.minute : e.minute, val: hit ? `xG ${hit.s.xg.toFixed(2)}` : evText(m, e.value) || String(e.value), note: hit ? hit.p.name : '', video: hit ? hit.s.video_url : null, match_id: e.match_id }; });
      r.total = r.shown = r.items.length;
      r.note = 'Every set-piece shot behind this number, each with its clip.';
    } else {
      r.items = t.per_match.map(pm => ({ when: `R${pm.round} ${pm.home ? 'v' : '@'} ${short(pm.opponent)}`, minute: null, val: fmt(m, pm.values[tk]), note: m.kind === 'per90' ? 'per 90 of the match' : "the match's value", video: null, match_id: pm.match_id }));
      r.total = r.shown = r.items.length;
      r.unit = 'match';
      r.note = m.kind === 'ratio' ? 'A team-style ratio is built from every possession of a match: one value per match, no single clip.'
        : 'One value per match; the events behind this number are not listed here.';
    }
    return r;
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
      const n = evCount(p, mk);
      return `<p class="tt-h">${esc(m.label)}${m.noisy ? ' <span class="tt-w">≈ small sample</span>' : ''}</p><p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : ''} · ${c.percentile == null ? esc(np ? np.text : 'no percentile') : `${esc(ord(c.percentile))} percentile vs ${esc(POSN[p.position])}`}</p>${zeroEv(p, mk) ? '<p class="tt-s">No moments behind this number</p>' : n ? `<p class="tt-play">&#9654; ${esc(n)} · Enter plays them</p>` : ''}<p class="tt-s">The column header has the definition</p>`;
    }
    const src = (m.sources || []).map(s => (D.sources[s] || {}).title || s).join('; ');
    const judge = m.higher_is_better === null ? 'Style marker: ranked, not judged' : m.higher_is_better ? 'Higher is better' : 'Lower is better';
    let h = `<p class="tt-h">${esc(m.label)}</p><p>${esc(m.definition)}</p>
      <p class="tt-s"><b>Rule</b> ${esc(m.rule)}${src ? ` · <b>Source</b> ${esc(src)}` : ''}</p><p class="tt-s">${esc(mk ? unitText(m) : m.unit)} · ${esc(judge)}${mk && m.positions ? ` · matters for ${esc(m.positions.join(' '))}` : ''}</p>`;
    if (mk && m.noisy) h += `<p class="tt-w">≈ Small sample, read with care: split-half r ${esc(m.reliability_r)} (below ${esc(D.season.noise_r)}); one season cannot yet separate players in the same role.</p>`;
    if (mk && m.min_attempts) h += `<p class="tt-s">Percentile needs at least ${esc(m.min_attempts)}: ${esc(m.min_attempts_rule)}</p>`;
    const p = el.dataset.pid && PID.get(el.dataset.pid), c = p && mk ? cellOf(p, mk) : null;
    if (c) h += `<p class="tt-p"><b>${esc(p.name)}</b> ${esc(withUnit(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : c.total != null && m.kind !== 'total' ? ` (${esc(c.total)} in total)` : ''} · ${c.percentile == null ? esc((noPct(p, m, c) || { text: 'no percentile' }).text) : `${esc(ord(c.percentile))} percentile among regular ${esc(POSN[p.position])}`}</p>`;
    const tv = tk && el.dataset.cid ? TEAMS.get(el.dataset.cid) : null;
    if (tv && tv.values[tk]) h += `<p class="tt-p">Rank ${esc(tv.values[tk].rank)} of ${esc(tv.values[tk].of)} · league average ${esc(fmt(m, tv.values[tk].league_mean))}</p>`;
    // A clickable number says what it opens.
    if (el.classList.contains('tx-n')) {
      let n = null;
      if (c && zeroEv(p, mk)) { h += '<p class="tt-s">No moments behind this number</p>'; return h; }
      if (c) n = evCount(p, mk);
      else if (tv && tv.values[tk]) { const r = teamReel(el.dataset.cid, tk); n = plural(r.items.length, r.unit === 'match' ? 'match' : r.items.some(it => it.video) ? 'moment' : 'item'); }
      if (n) h += `<p class="tt-play">&#9654; ${esc(n)} · click to play</p>`;
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
    let left = Math.min(Math.max(8, r.left), window.innerWidth - tw - 8);
    tip.style.left = left + 'px';
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
  // Synthetic names repeat (seven Toures, five Ustinovs), so a bare surname picks the namesake the scout most likely means:
  // the selected player themselves, or one they play like (their "Plays like" list), then, when comparing, one in the same position, then one
  // in the players table as it stands, then the most minutes. The other namesakes are offered beside the answer.
  function namesakeOrder(hits, ctx = {}) {
    const cp = ctx.p || PID.get(S.focus), sim = new Set(((cp && cp.similar) || []).map(s => s.id));
    let table = null;
    const inTable = (p) => { if (!table) table = new Set(screenRows().map(x => x.id)); return table.has(p.id); };
    const key = (p) => [!ctx.pos && cp && p.id === cp.id ? 0 : 1, sim.has(p.id) ? 0 : 1, ctx.pos && cp && p.position === cp.position ? 0 : 1, inTable(p) ? 0 : 1];
    const byKey = (a, b) => { for (let i = 0; i < a.k.length; i++) if (a.k[i] !== b.k[i]) return a.k[i] - b.k[i]; return 0; };
    return hits.map(p => ({ p, k: key(p) })).sort((a, b) => byKey(a, b) || b.p.minutes - a.p.minutes || a.p.name.localeCompare(b.p.name)).map(o => o.p);
  }
  function resolvePlayer(q, strict, ctx) {
    const n = norm(q); if (!n) return { none: true };
    if (PID.has(q.trim())) return { p: PID.get(q.trim()), alts: [] };
    const tiers = [(p) => norm(p.name) === n, (p) => surname(p) === n || norm(p.name).split(' ').slice(-1)[0] === n, (p) => norm(p.name).split(' ')[0] === n];
    if (!strict) tiers.push((p) => norm(p.name).includes(n));
    for (const t of tiers) {
      const hit = D.players.filter(t);
      if (hit.length === 1) return { p: hit[0], alts: [] };
      if (hit.length > 1) { const o = namesakeOrder(hit, ctx); return { p: o[0], alts: o.slice(1) }; }
    }
    return { none: true };
  }
  // "Toure and Ustinov", "Toure vs Ustinov", "Toure with Ustinov", "Femi Toure, Amari Ustinov": each name after the first
  // is read in the light of the first (a namesake who plays like them, or in the same position, wins).
  const JOIN_RE = /^(v|vs|vs\.|versus|and|with|&|against)$/i;
  function resolvePlayers(text) {
    const outp = [], ctxOf = () => ({ p: outp.length && outp[0].p ? outp[0].p : PID.get(S.focus), pos: outp.length > 0 });
    const parts = text.includes(',') ? text.split(',').map(s => s.trim().replace(/^(and|with|vs|v|versus|&)\s+/i, '')).filter(Boolean) : null;
    if (parts) { for (const s of parts) outp.push({ q: s, ...resolvePlayer(s, false, ctxOf()) }); return outp; }
    const toks = text.split(/\s+/).filter(t => t && !JOIN_RE.test(t));
    let i = 0;
    while (i < toks.length) {
      let done = false;
      for (let j = toks.length; j > i; j--) {
        const r = resolvePlayer(toks.slice(i, j).join(' '), true, ctxOf());
        if (r.p) { outp.push({ q: toks.slice(i, j).join(' '), p: r.p, alts: r.alts }); i = j; done = true; break; }
      }
      if (!done) { const r = resolvePlayer(toks[i], false, ctxOf()); outp.push({ q: toks[i], ...r }); i++; }
    }
    return outp;
  }
  function resolveMetric(q) {
    const raw = String(q || '').trim(); if (!raw) return { none: true };
    const k = norm(raw).replace(/[\s-]+/g, '_');
    if (MK.has(k)) return { m: MK.get(k) };
    const l = norm(raw), byL = D.metrics.filter(m => norm(m.label) === l);
    if (byL.length === 1) return { m: byL[0] };
    const sub = D.metrics.filter(m => norm(m.label).includes(l) || m.key.includes(k));
    if (sub.length === 1) return { m: sub[0] };
    const wm = wordMatch(l);
    if (wm.length === 1) return { m: wm[0] };
    return wm.length ? { many: wm } : sub.length ? { many: sub } : { none: true };
  }
  // Every word of the query starts a word of the metric's key or label ("aerial win %" finds aerial_win_pct).
  const mwords = (m) => [...m.key.split('_'), ...norm(m.label).replace(/%/g, ' pct ').split(/[\s\-()+,/]+/)].filter(Boolean);
  function wordMatch(l) {
    const ws = norm(l).replace(/%/g, ' pct ').split(/[\s\-()+,/_]+/).filter(Boolean);
    return ws.length ? D.metrics.filter(m => { const mw = mwords(m); return ws.every(w => mw.some(x => x.startsWith(w))); }) : [];
  }
  function resolveClub(q) {
    const n = norm(q); if (!n) return null;
    return D.clubs.find(c => norm(c.short_name) === n || c.club_id === n || norm(c.name) === n)
      || D.clubs.find(c => norm(c.name).split(' ').some(w => w.startsWith(n)) || norm(c.name).startsWith(n)) || null;
  }
  const posOf = (t) => POS_WORDS[String(t || '').toUpperCase()] || null;
  const runBtn = (cmd, label) => `<button type="button" class="tx-mini" data-act="run" data-cmd="${esc(cmd)}">${esc(label || cmd)}</button>`;
  const cmdWord = (head) => COMMANDS[head] ? COMMANDS[head].word : '';
  const altsHtml = (alts, head) => alts && alts.length ? ` <span class="tx-dim">· also:</span> ${alts.slice(0, 6).map(p => runBtn(`${cmdWord(head) ? cmdWord(head) + ' ' : ''}${p.name}`, `${p.name} ${p.short_name}`)).join(' ')}` : '';
  function onePlayer(arg) {
    if (!arg.trim()) return { p: PID.get(S.focus), alts: [] };
    const r = resolvePlayer(arg);
    if (r.p) return r;
    out(`No player called "${arg}". Type part of a name; suggestions appear as you type.`, 'err');
    return null;
  }
  const posText = (pos) => pos ? POSN[pos] : 'players';
  const cap1 = (t) => t.charAt(0).toUpperCase() + t.slice(1);
  function run(text) {
    const t = String(text || '').trim().replace(/\s*<GO>$/i, '').replace(/[?!.]+$/, '').trim(); if (!t) return;
    if (store.hist[store.hist.length - 1] !== t) { store.hist.push(t); if (store.hist.length > 50) store.hist.shift(); save(); }
    histAt = -1;
    dispatch(t);
  }
  function dispatch(t) {
    const ph = parseHead(t), head = ph.head, rest = ph.rest.replace(/<GO>\s*$/i, '').trim();
    if (head === 'HELP') { openHelp(); out('Help is open. Escape closes it.'); return; }
    if (head === 'RANK') return cmdRank(rest);
    if (head === 'CMP') return cmdCmp(rest);
    if (head === 'SCAT') return cmdScat(rest);
    if (head === 'TEAM') {
      const c = resolveClub(rest) || (rest ? null : club(S.club));
      if (!c || !c.club_id) { out(`No club called "${rest}". Clubs: ${D.clubs.map(x => x.name).join(', ')}.`, 'err'); return; }
      S.club = c.club_id; save(); reveal('team', renderTeam); out(`${c.name}: how they play, ranked across the league's six clubs.`); return;
    }
    if (head === 'HL') { const r = onePlayer(rest); if (r) playHighlights(r.p, r.alts); return; }
    const PANEL_CMD = { SIM: 'plyr', SHOT: 'shot', FORM: 'form', HEAT: 'heat', RDR: 'radar', PLYR: 'plyr' };
    if (PANEL_CMD[head]) {
      const r = onePlayer(rest); if (!r) return;
      const p = r.p;
      select(p.id, true); showPanel(PANEL_CMD[head], true, head === 'SIM' ? '.tx-sim' : head === 'PLYR' ? '.tx-card' : null);
      let line;
      if (head === 'SIM') { line = `Plays like ${p.name}: ${(p.similar || []).map(s => `${s.name} ${s.similarity.toFixed(2)}`).join(', ') || 'nobody yet (too few minutes)'}.`; }
      else if (head === 'SHOT') line = `${p.name}: ${plural((p.shots || []).length, 'shot')}, ${plural((p.shots || []).filter(s => s.outcome === 'goal').length, 'goal')}. Each shot plays its clip.`;
      else if (head === 'FORM') line = `${p.name}: ${plural((p.form && p.form.matches || []).length, 'match')}. Each bar plays that match's moments.`;
      else if (head === 'HEAT') line = `${p.name}: where they have the ball, attacking left to right.`;
      else if (head === 'RDR') line = `${p.name}: percentiles against ${POSN[p.position]}.`;
      else line = `${p.name} · ${p.club}.`;
      out('', '', esc(line) + altsHtml(r.alts, head));
      return;
    }
    const c = resolveClub(t), team = (k) => { S.club = k.club_id; save(); reveal('team', renderTeam); out(`${k.name}: how they play.`); };
    if (c && (norm(c.short_name) === norm(t) || norm(c.name) === norm(t))) return team(c);
    const r = resolvePlayer(t);
    if (r.p) { const p = r.p; select(p.id, true); showPanel('plyr', true, '.tx-card'); out('', '', esc(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`) + altsHtml(r.alts, '')); return; }
    if (c) return team(c);
    const mm = resolveMetric(t);
    if (mm.m) return cmdRank(mm.m.key);
    const nat = natural(t);
    if (nat) return nat();
    out(`Nothing found for "${t}". Try a surname, a club, a stat such as "goals", "best finishers", "Toure highlights" or "Toure vs Ustinov". Help lists everything.`, 'err');
  }
  // Plain questions, as a scout types them into a search box: "who are the best finishers?", "top scorers", "strikers",
  // "best dribblers in midfield", "Toure shots", "Toure goals", "Toure vs Ustinov". Each becomes the command it means.
  const SYN = [
    [/^(finishers|finishing|finisher)$/, 'np_goals', 'FW'],
    [/^(scorers|goalscorers|goal scorers|scorer|goalscorer|scoring|goals)$/, 'goals', null],
    [/^(dribblers|dribbler|dribbling|dribbles)$/, 'take_ons_won', null],
    [/^(creators|creator|chance creators|playmakers|playmaker|creating|creativity|chance creation)$/, 'sca', null],
    [/^(assisters|assist makers|providers|assists|assisting)$/, 'assists', null],
    [/^(shooters|shooting|shot takers)$/, 'shots', null],
    [/^(passers|passer|passing)$/, 'progressive_passes', null],
    [/^(carriers|ball carriers|carrying)$/, 'progressive_carries', null],
    [/^(tacklers|tackler|tackling|ball winners|ball winning|defending)$/, 'tkl_int_padj', null],
    [/^(headers|heading|in the air|aerial|air)$/, 'aerial_duels_won', null],
    [/^(pressers|pressing)$/, 'pressures', null],
    [/^(runners|running|work rate|workhorses|engines)$/, 'distance', null],
    [/^(sprinters|fastest|quickest|pace|speed|fastest players|quickest players)$/, 'peak_speed', null],
    [/^(shot stoppers|shot-stoppers|stoppers|saving|saves)$/, 'save_pct', 'GK'],
  ];
  const PANEL_W = { shots: 'SHOT', shot: 'SHOT', 'shot map': 'SHOT', form: 'FORM', 'touch map': 'HEAT', 'heat map': 'HEAT', heatmap: 'HEAT', touchmap: 'HEAT',
    radar: 'RDR', profile: 'PLYR', card: 'PLYR', player: 'PLYR', similar: 'SIM', 'similar players': 'SIM', 'plays like': 'SIM', lookalikes: 'SIM', team: 'TEAM', club: 'TEAM' };
  const synStat = (s) => { for (const [re, k, pos] of SYN) if (re.test(s) && MK.has(k)) return { k, pos }; return null; };
  // Words that ask to watch a player: "Toure highlights", "Toure clips", "best moments Toure".
  const HL_W = new Set(['highlights', 'highlight', 'highlight reel', 'clips', 'clip', 'moments', 'best moments', 'top moments', 'videos', 'video', 'reel', 'best bits']);
  // "who scores the most", "who assists the most": the verb names the stat.
  const VERB = { scores: 'goals', score: 'goals', scored: 'goals', assists: 'assists', assisted: 'assists', creates: 'creators', create: 'creators',
    shoots: 'shooters', dribbles: 'dribblers', tackles: 'tacklers', passes: 'passers', runs: 'runners', covers: 'runners', presses: 'pressers',
    saves: 'saves', carries: 'carriers', heads: 'headers', wins: null };
  // A club named strictly (its short name, its name, or the first word of its name), so "in midfield" is never a club.
  const clubStrict = (q) => { const n = norm(q); return n ? D.clubs.find(c => norm(c.short_name) === n || norm(c.name) === n || norm(c.name).split(' ')[0] === n) || null : null; };
  function natural(t) {
    let s0 = norm(t).replace(/[?!.]+$/, '').replace(/\b(who|what|that|it|he|she)['’]s\b/g, '$1 is').replace(/['’]s\b/g, '').replace(/['’]/g, '');
    // "per 90" is how every rate here is shown already
    s0 = s0.replace(/\s*(\/\s*90|per 90( minutes)?|per ninety|p90|per game|per match|a game|a match)(?=\s|$)/g, '').replace(/\s+/g, ' ').trim();
    // The opening words of a question or a request, as many as there are ("who has", "show me", "can you show me").
    const OPEN = /^(can\s+you|could\s+you|please|i\s+want\s+to\s+see|let\s+me\s+see|who\s+(are|is|were|was|has|have|had|got|gets)|which\s+players?\s+(are|is|have|has)|which\s+players?|who|show\s+me|show|find\s+me|find|list|give\s+me|get\s+me|get|open|pull\s+up|look\s+up|search\s+for|search|go\s+to|take\s+me\s+to|play|watch|see)\s+/;
    let watch = false, who = false;
    for (let m = s0.match(OPEN); m; m = s0.match(OPEN)) { if (/^(play|watch|see|i want|let me)/.test(m[1])) watch = true; if (/^(who|which)/.test(m[1])) who = true; s0 = s0.slice(m[0].length); }
    if (who) { const v = s0.split(' ')[0]; if (VERB[v]) s0 = [VERB[v], ...s0.split(' ').slice(1).filter(w => !/^(the|most|more|best|often|goals|chances|ground|ball)$/.test(w))].join(' '); }
    if (!s0) return null;
    // "at Brookfield", "for Calder", "from Dunmore": a club filter on the ranking (or "Brookfield best finishers").
    let cl = null;
    const cm = s0.match(/\s(?:at|for|from|in)\s+(.+)$/);
    if (cm && clubStrict(cm[1])) { cl = clubStrict(cm[1]); s0 = s0.slice(0, cm.index).trim(); }
    else { const w0 = s0.split(' '); if (w0.length > 1 && clubStrict(w0[0]) && !resolvePlayer(w0[0], true).p) { cl = clubStrict(w0[0]); s0 = w0.slice(1).join(' '); } }
    let s = s0.replace(/^the\s+/, '').replace(/^((best|top|most|leading|greatest|highest|good|great|strongest|biggest|elite)\s+)+/, '').replace(/^\d+\s+/, '');
    s = s.replace(/\s+(in the league|in the regista league|this season|in the season|right now)$/, '').trim();
    const rank = (q) => () => cmdRank(q, cl);
    if (s) {
      // A position word anywhere ("forwards", "strikers", "in midfield"), with what is left read as a stat.
      const toks = s.split(' ');
      let pos = null;
      const MIDWORDS = { midfield: 'MF', defence: 'DF', defense: 'DF', attack: 'FW', goal: null };
      const rest = toks.filter(w => {
        const p = posOf(w) || (MIDWORDS[w] !== undefined && MIDWORDS[w] ? MIDWORDS[w] : null);
        if (p && !pos) { pos = p; return false; }
        return true;
      }).filter(w => !/^(at|for|by|on|in|of|the|with)$/.test(w)).join(' ');
      const posWord = (p) => p === 'ALL' || !p ? 'all' : POSN[p];
      if (pos && !rest) return rank(`${posWord(pos)} ${(D.default_columns[pos === 'ALL' ? 'all' : pos] || D.default_columns.all).find(x => MK.has(x))}`);
      const st = synStat(rest);
      if (st) return rank(`${posWord(pos || st.pos)} ${st.k}`);
      if (pos || cl) { const m = resolveMetric(rest); if (m.m) return rank(`${posWord(pos)} ${m.m.key}`); }
    }
    // "<player> <panel, stat or highlights>" and the other way round: "Toure shots", "Toure goals", "Toure highlights".
    const w = s0.split(' ').filter(x => !/^(of|for|by|me|the|all)$/.test(x));
    const asPanelOrStat = (q) => HL_W.has(q) ? { hl: true } : PANEL_W[q] ? { panel: PANEL_W[q] } : synStat(q) ? { k: synStat(q).k } : (() => { const m = resolveMetric(q); return m.m ? { k: m.m.key } : null; })();
    for (let j = w.length - 1; j >= 1; j--) {
      for (const [pq, xq] of [[w.slice(0, j), w.slice(j)], [w.slice(w.length - j), w.slice(0, w.length - j)]]) {
        const pr = resolvePlayer(pq.join(' '), true); if (!pr.p) continue;
        const x = asPanelOrStat(xq.join(' ')); if (!x) continue;
        const p = pr.p;
        if (x.hl) return () => playHighlights(p, pr.alts);
        if (x.panel === 'TEAM') return () => dispatch(`team ${p.club}`);
        if (x.panel) return () => dispatch(`${COMMANDS[x.panel] ? COMMANDS[x.panel].word : 'player'} ${p.name}`);
        return () => {
          select(p.id, true); showPanel('plyr', false);
          const m = MK.get(x.k), c = cellOf(p, x.k);
          if (zeroEv(p, x.k)) { out(`${p.name}: ${m.label} ${c ? withUnit(m, c.value) : '–'}, so there are no moments to play.`); return; }
          openEvidence(p.id, x.k);
        };
      }
    }
    // "Toure vs Ustinov", "Femi Toure and Amari Ustinov", "Toure with Ustinov": a comparison without the word "compare".
    if (/\s(v|vs|vs\.|versus|and|with|&|against)\s|,/.test(` ${s0} `)) {
      const rs = resolvePlayers(s0);
      if (rs.length >= 2 && rs.every(r => r.p)) return () => cmdCmp(s0);
    }
    // What is left after "show me", "open", "watch": a bare highlights word, a player or a club.
    if (HL_W.has(s0)) return () => playHighlights(PID.get(S.focus));
    if (s0 !== norm(t)) {
      const pr = resolvePlayer(s0);
      if (pr.p) return watch ? () => playHighlights(pr.p, pr.alts) : () => dispatch(s0);
      if (resolveClub(s0)) return () => dispatch(`team ${s0}`);
    }
    return null;
  }
  function cmdRank(rest, cl) {
    const toks = rest.split(/\s+/).filter(Boolean);
    let pos = null;
    if (toks.length && posOf(toks[0])) pos = posOf(toks.shift());
    else if (toks.length > 1 && posOf(toks[toks.length - 1])) pos = posOf(toks.pop());
    if (toks.length > 1 && /^(by|on)$/i.test(toks[0])) toks.shift();      // rank forwards by goals
    const r = resolveMetric(toks.join(' '));
    if (!r.m) {
      if (r.many) out('', 'err', `"${esc(toks.join(' '))}" matches ${r.many.length} stats: ${r.many.slice(0, 6).map(m => runBtn(`rank ${pos && pos !== 'ALL' ? POSN[pos] : 'all'} ${m.label}`, m.label)).join(' ')}`);
      else out('Rank needs a stat: rank <position> <stat>, for example "rank forwards non-penalty xG". Suggestions appear as you type.', 'err');
      return;
    }
    const m = r.m;
    S.scr.pos = pos === 'ALL' ? null : pos;
    // The ranked column goes first, so the order of the rows is explained by the first number the scout reads (at 375 px
    // only one stat column fits).
    S.scr.cols = [m.key, ...S.scr.cols.filter(k => k !== m.key)];
    S.scr.sort = { k: m.key, dir: m.higher_is_better === false ? 1 : -1 };
    // A club filter ("best finishers at Brookfield") goes in the table's own filter box, where it shows and clears.
    S.scr.q = cl ? cl.name : ''; scrAct = null; save();
    if (!visible('scrn')) showPanel('scrn', false);
    renderScrn();
    const tw = document.querySelector('#tx-p-scrn .tx-tablewrap');
    if (tw) {
      tw.scrollLeft = 0; tw.scrollTop = 0;
      // On a phone the first stat column can still run past the table's edge (Club, Pos and Mins come first): scroll the
      // table, not the page, until the ranked column shows whole.
      const th = tw.querySelector(`thead th [data-k="${CSS.escape(m.key)}"]`), cell = th && th.closest('th');
      if (cell) { const over = cell.getBoundingClientRect().right - tw.getBoundingClientRect().right; if (over > 0) tw.scrollLeft = over + 4; }
    }
    showPanel('scrn');
    const rows = screenRows(), ranks = screenRanks(rows), tops = rows.filter((_, i) => ranks[i] === 1), c = tops[0] && cellOf(tops[0], m.key);
    const names = tops.length > 3 ? `${tops.slice(0, 3).map(p => p.name).join(', ')} and ${tops.length - 3} more` : tops.map(p => p.name).join(tops.length === 2 ? ' and ' : ', ');
    const nr = ranks.filter(x => x != null).length, un = rows.length - nr;
    out(`${cap1(posText(S.scr.pos))}${cl ? ` at ${cl.name}` : ''} ranked by ${m.label}${m.higher_is_better === false ? ' (lowest first: lower is better)' : ''}: ${rows.length}${un ? `, ${nr} ranked (${un} ${S.scr.qual ? 'below the minimum attempts' : 'under the minutes or the minimum attempts'}, listed after)` : ''}${c ? `. Top: ${names}, ${withUnit(m, c.value)}${tops.length > 1 ? ', tied' : ''}` : ''}.`);
  }
  function cmdCmp(rest) {
    const rs = resolvePlayers(rest);
    const bad = rs.find(r => !r.p);
    if (bad || !rs.length) { out(rest ? `No player called "${bad.q}".` : 'Compare needs two or three players: compare <player> and <player>.', 'err'); return; }
    const ids = [...new Set(rs.map(r => r.p.id))].slice(0, 3);
    if (ids.length === 1 && ids[0] !== S.focus) ids.unshift(S.focus);
    if (ids.length < 2) { out('Compare needs two or three different players.', 'err'); return; }
    S.compare = ids; S.focus = ids[0]; S.club = PID.get(ids[0]).club_id; save();
    renderAll(); showPanel('radar');
    const amb = rs.filter(r => r.alts && r.alts.length);
    out('', '', esc(`Comparing ${listText(ids.map(id => PID.get(id).name))}: radar and table, each against their own position.`)
      + (amb.length ? ` <span class="tx-dim">"${esc(amb[0].q)}" could also be:</span> ${amb[0].alts.slice(0, 5).map(p => runBtn(`compare ${ids.map(id => id === amb[0].p.id ? p.name : PID.get(id).name).join(', ')}`, `${p.name} ${p.short_name}`)).join(' ')}` : ''));
  }
  const AGAINST = /^(against|vs|v|versus)$/i;
  function cmdScat(rest) {
    const toks = rest.split(/\s+/).filter(Boolean);
    let pos;
    if (toks.length > 2 && posOf(toks[toks.length - 1])) { const p = posOf(toks.pop()); pos = p === 'ALL' ? null : p; }
    let mx = null, my = null;
    const ai = toks.findIndex(w => AGAINST.test(w));
    if (ai > 0) { const a = resolveMetric(toks.slice(0, ai).join(' ')), b = resolveMetric(toks.slice(ai + 1).join(' ')); if (a.m && b.m) { mx = a.m; my = b.m; } }
    const ts = toks.filter(w => !AGAINST.test(w));
    for (let k = 1; k < ts.length && !mx; k++) {
      const a = resolveMetric(ts.slice(0, k).join(' ')), b = resolveMetric(ts.slice(k).join(' '));
      if (a.m && b.m) { mx = a.m; my = b.m; }
    }
    if (!mx) { out('Plot needs two stats: plot <stat> against <stat> [position], for example "plot non-penalty xG against xA forwards". Stats autocomplete.', 'err'); return; }
    S.scat.x = mx.key; S.scat.y = my.key; if (pos !== undefined) S.scat.pos = pos; scatCur = null; save();
    reveal('scat', renderScat);
    out(`${mx.label} against ${my.label}${S.scat.pos ? `, ${POSN[S.scat.pos]}` : ''}: ${plural(scatPoints().length, 'player')}.`);
  }

  // ------------------------------------------------------------------ the search box: autocomplete and history
  function playerSugs(q, k, run, ctx) {
    const n = norm(q);
    const score = (p) => { const nm = norm(p.name), sn = surname(p); if (!n) return 0; if (sn.startsWith(n)) return 0; if (nm.startsWith(n)) return 1; if (nm.split(' ').some(w => w.startsWith(n))) return 2; if (n.length >= 3 && nm.includes(n)) return 3; return 9; };
    let ps;
    if (!n) { const f = PID.get(S.focus); ps = [f, ...(f.similar || []).map(s => PID.get(s.id)).filter(Boolean)]; }
    else {
      // Namesakes in the order a typed name would pick them (the selected player, who they play like, the table…).
      const hit = D.players.filter(p => score(p) < 9), at = new Map(namesakeOrder(hit, ctx).map((p, i) => [p.id, i]));
      ps = hit.sort((a, b) => score(a) - score(b) || at.get(a.id) - at.get(b.id));
    }
    return ps.slice(0, 7).map(p => ({ kind: 'Player', text: p.name, detail: `${p.short_name} · ${p.position} · #${p.kit_number}`, insert: p.name, k, run }));
  }
  const groupLabel = (m) => (D.groups.find(g => g.key === m.group) || {}).label || '';
  function metricSugs(q, k, run, prefix = '', pos = null, suffix = '') {
    const n = norm(q), kk = n.replace(/[\s-]+/g, '_');
    const score = (m) => { if (!n) return 0; const l = norm(m.label); if (l.startsWith(n)) return 0; if (m.key.startsWith(kk)) return 1; if (l.split(' ').some(w => w.startsWith(n))) return 2; if (m.key.includes(kk) || l.includes(n)) return 3; const ws = n.replace(/%/g, ' pct ').split(/[\s\-()+,/_]+/).filter(Boolean), mw = mwords(m); if (ws.length && ws.every(w => mw.some(x => x.startsWith(w)))) return 4; return 9; };
    const base = n ? D.metrics : (D.default_columns[pos || PID.get(S.focus).position] || D.default_columns.all).map(x => MK.get(x)).filter(Boolean);
    return base.filter(m => score(m) < 9).sort((a, b) => score(a) - score(b)).slice(0, 8)
      .map(m => ({ kind: 'Stat', text: `${m.label}${m.noisy ? ' ≈' : ''}`, detail: groupLabel(m), insert: prefix + m.label + suffix, k, run, mk: m.key }));
  }
  const POS_SUG = (cur, run) => ['ALL', ...POS].filter(p => (p === 'ALL' ? 'all' : POSN[p]).startsWith(norm(cur)) || p.startsWith(cur.toUpperCase()))
    .map(p => ({ kind: 'Position', text: p === 'ALL' ? 'all' : POSN[p], detail: p === 'ALL' ? 'every position' : p, insert: p === 'ALL' ? 'all' : POSN[p], k: 1, run }));
  function suggest() {
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length);
    if (!before.trim()) { acItems = []; return paintAc(); }
    const toks = before.split(/\s+/), cur = toks[toks.length - 1], words = toks.filter(Boolean);
    const ph = parseHead(before.replace(/^\s+/, '')), head = ph.head;
    const inArgs = ph.started && (COMMANDS[head] || head === 'PLYR');
    const args = ph.rest.split(/\s+/);            // the last is the word being typed ('' after a space)
    let s = [];
    const trailing = (fn) => { for (let k = Math.min(3, toks.length - 1); k >= 1; k--) { const q = toks.slice(-k).join(' ').trim(); const r = fn(q, k); if (r.length && q) return r; } return fn(cur, 1); };
    if (!inArgs) {
      if (toks.length === 1 || (words.length === 1 && !ph.started)) {
        const n = norm(cur);
        s.push(...Object.entries(COMMANDS).filter(([c, x]) => x.word.startsWith(n) || c.startsWith(cur.toUpperCase())).map(([c, x]) => ({ kind: 'Command', text: x.word, detail: x.args ? `${x.word} ${x.args}` : x.help, insert: x.word, k: 1, run: c === 'HELP' })));
        s.push(...playerSugs(cur, 1, true).slice(0, 5));
        s.push(...D.clubs.filter(c => norm(c.short_name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'Club', text: c.name, detail: 'how they play', insert: `team ${c.name}`, k: 1, run: true })));
        s.push(...metricSugs(cur, 1, true, `rank ${POSN[PID.get(S.focus).position]} `).slice(0, 3).map(x => ({ ...x, detail: `rank ${POSN[PID.get(S.focus).position]}` })));
      } else s = playerSugs(words.join(' '), toks.length, true);
    } else if (['SIM', 'HL', 'SHOT', 'FORM', 'HEAT', 'RDR', 'PLYR'].includes(head)) s = playerSugs(args.join(' '), args.length, true);
    else if (head === 'CMP') {
      // Players already named before the last "," / "and" / "vs" are not suggested again (Compare with… names the selected one).
      const more = /,|\band\b|\bvs?\b/i.test(ph.rest), m = ph.rest.match(/^(.*)(,|\band\b|\bvs?\b)/i), named = m ? norm(m[1]) : '';
      const first = named ? resolvePlayers(m[1]).find(r => r.p) : null, ctx = first ? { p: first.p, pos: true } : undefined;
      s = trailing((q, k) => playerSugs(q, k, more, ctx).filter(x => !named || !named.includes(norm(x.text))));
    }
    else if (head === 'TEAM') { const n = norm(args.join(' ')); s = D.clubs.filter(c => !n || norm(c.short_name).startsWith(n) || norm(c.name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'Club', text: c.name, detail: c.short_name, insert: c.name, k: args.length, run: true })); }
    else if (head === 'RANK') {
      if (args.length === 1) s = [...POS_SUG(cur, false), ...metricSugs(cur, 1, true)];
      else { const p0 = posOf(args[0]), q = p0 ? args.slice(1) : args; s = metricSugs(q.join(' '), q.length, true, '', p0 === 'ALL' ? 'all' : p0); }
    } else if (head === 'SCAT') {
      const ai = args.slice(0, -1).findIndex(w => AGAINST.test(w));
      if (ai < 0) s = trailing((q, k) => metricSugs(q, k, false, '', null, ' against'));
      else {
        const after = args.slice(ai + 1), done = after.length > 1 && resolveMetric(after.slice(0, -1).join(' ')).m && cur === '';
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
  function accept(i) {
    const s = acItems[i]; if (!s) return;
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length), after = inp.value.slice(before.length);
    const toks = before.split(/\s+/);
    const keep = toks.slice(0, Math.max(0, toks.length - s.k)).join(' ');
    inp.value = (keep ? keep + ' ' : '') + s.insert + ' ' + after.trimStart();
    closeAc();
    if (s.run) { const v = inp.value; inp.value = ''; run(v); }
    else { inp.setSelectionRange(inp.value.length, inp.value.length); suggest(); }
  }

  // ------------------------------------------------------------------ help
  function openHelp(opener) {
    const h = $('txHelp');
    const srcs = Object.entries(D.sources).map(([k, s]) => `<li>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`).join('');
    const f = PID.get(S.focus), ex = (c, x) => c === 'TEAM' ? `team ${club(S.club).name}` : x.ex;
    h.innerHTML = `<div class="tx-hhead"><h2 tabindex="-1" id="txHelpH">How to use the Scout terminal</h2><button type="button" class="tx-mini" data-act="helpclose" aria-label="Close help">Close &times;</button></div>
      <div class="tx-hbody"><p>Type in the search box and press Enter. Click any example to run it.</p><table class="tx-mt tx-htable"><tbody>
        <tr><th scope="row"><code>a name</code></th><td>Opens the player. ${runBtn(f.name.split(' ').slice(-1)[0])}</td></tr>
        <tr><th scope="row"><code>a club</code> or <code>a stat</code></th><td>A club opens how it plays; a stat ranks every player on it. ${runBtn('goals')}</td></tr>
        <tr><th scope="row"><code>a question</code></th><td>Plain words work too: best finishers, who has the most assists, best finishers at a club, a player with a stat, a panel or "highlights", or two players with "vs". ${runBtn('who has the most assists?')} ${runBtn(`${f.name.split(' ').slice(-1)[0]} highlights`)} ${runBtn(`${f.name.split(' ').slice(-1)[0]} vs ${(f.similar && f.similar[0] ? f.similar[0].name : f.name).split(' ').slice(-1)[0]}`)}</td></tr>
        ${Object.entries(COMMANDS).filter(([c]) => c !== 'HELP').map(([c, x]) => `<tr><th scope="row"><code>${esc(x.word)}</code> <span class="tx-dim">${esc(x.args)}</span></th><td>${esc(x.help)} ${runBtn(ex(c, x))}</td></tr>`).join('')}
      </tbody></table>
      <p class="tx-dim">Short forms still work: ${Object.entries(COMMANDS).map(([c, x]) => `<code>${esc(c)}</code>`).join(' ')} (for example <code>RANK FW npxg</code>).</p>
      <h3 class="tx-h3">Keys</h3><ul class="tx-keys">
        <li><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> goes to the search box</li><li><kbd>Enter</kbd> searches</li><li><kbd>↑</kbd> <kbd>↓</kbd> earlier searches, or move in the suggestions</li>
        <li><kbd>Tab</kbd> takes a suggestion</li><li><kbd>Esc</kbd> closes suggestions, help, tips and the clips drawer</li><li><kbd>Alt 1–9</kbd> jump to a panel, in the order of the panel buttons (each button's tooltip shows its key)</li>
        <li>In the players table: arrow keys, Home/End, Enter</li><li>In the scatter: arrow keys pick a player, Enter selects</li></ul>
      <h3 class="tx-h3">How the panels link</h3><p>One selected player and up to three compared players drive every panel. Selecting a player anywhere (a row in the table, a dot in the scatter, a similar player, the squad, a legend) updates the rest. Every underlined number plays the moments behind it in the clips drawer, from ${esc(APP.replace(/^https?:\/\//, ''))}; the first ${esc(10)} are listed, with a link to all of them.</p>
      <h3 class="tx-h3">The numbers</h3><p>${esc(D.note)}</p><p>${esc(plainSample(D.season.sample.note))}</p><p><span class="tx-noisy">≈</span> small sample, read with care: the stat cannot yet tell players in the same role apart over one season.</p>
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
  function doAct(t, e) {
    const sel = sig(t), panel = t.closest('[data-panel]'), zone = t.closest('#txSel, #txMeta, #txKeys, #txHelp, #txOut, #txEx, #txNav, #txDrawer');
    const pid = panel && panel.dataset.panel, zid = zone && zone.id;
    // What a number was clicked from, so closing the clips drawer can bring focus back to it.
    actFrom = { el: t, sel, scope: pid ? 'tx-p-' + pid : zid };
    act(t, e);
    actFrom = null;
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
      () => zid === 'txNav' && document.querySelector('#txNav button'),
      () => $('txIn')];
    for (const f of tries) {
      const el = f();
      if (!usable(el)) continue;
      el.focus({ preventScroll: true });
      if (document.activeElement === el) return;
    }
  }
  function act(t, e) {
    const a = t.dataset.act;
    if (a === 'sel') { select(t.dataset.pid); return; }
    if (a === 'ev') {
      if (t.dataset.sel && t.dataset.pid !== S.focus) { S.focus = t.dataset.pid; S.club = PID.get(S.focus).club_id; save(); renderAll(); }
      const p = PID.get(t.dataset.pid), m = MK.get(t.dataset.mk);
      // Nothing behind a zero: say so on the status line instead of opening an empty drawer.
      if (p && m && zeroEv(p, m.key)) { const c = cellOf(p, m.key); out(`${p.name}: ${m.label} ${c ? withUnit(m, c.value) : '–'}, so there are no moments to play.`); return; }
      openEvidence(t.dataset.pid, t.dataset.mk); return;
    }
    if (a === 'fev') { const k = S.form.k && MK.has(S.form.k) ? S.form.k : (D.default_columns[PID.get(S.focus).position] || D.default_columns.all)[0]; openEvidence(S.focus, k, t.dataset.mid); return; }
    if (a === 'tev') { openReel(teamReel(t.dataset.cid, t.dataset.tk)); return; }
    if (a === 'shot') { shotReel(PID.get(S.focus), +t.dataset.i); return; }
    if (a === 'clip') { play(+t.dataset.i, true); return; }
    if (a === 'cprev' || a === 'cnext') { if (!reel) return; const d = a === 'cnext' ? 1 : -1; let i = reel.i + d; while (reel.items[i] && !reel.items[i].video) i += d; if (reel.items[i]) play(i, true); return; }
    if (a === 'sort') { const k = t.dataset.k; S.scr.sort = S.scr.sort.k === k ? { k, dir: -S.scr.sort.dir } : { k, dir: k === 'name' || k === 'club' ? 1 : (MK.get(k) && MK.get(k).higher_is_better === false ? 1 : -1) }; save(); renderScrn(); return; }
    if (a === 'rmcol') {
      const i = S.scr.cols.indexOf(t.dataset.k);
      const wasSort = S.scr.sort.k === t.dataset.k;
      colMenuOpen = true; S.scr.cols = S.scr.cols.filter(k => k !== t.dataset.k); save(); renderScrn();
      if (wasSort) { const sk = S.scr.sort.k, sm = MK.get(sk); out(`Removed ${MK.get(t.dataset.k).label}; the table is now sorted by ${sm ? sm.label : 'minutes'}.`); }
      const xs = document.querySelectorAll('#tx-p-scrn [data-act="rmcol"]'), next = xs[Math.min(i, xs.length - 1)] || document.querySelector('#tx-p-scrn [data-r="addcol"]');
      if (next) next.focus({ preventScroll: true });
      return;
    }
    if (a === 'scrpos') { S.scr.pos = t.dataset.v || null; scrAct = null; save(); renderScrn(); return; }
    if (a === 'scrmode') { S.scr.mode = t.dataset.v; save(); renderScrn(); return; }
    if (a === 'scrdef') { colMenuOpen = true; S.scr.cols = (D.default_columns[S.scr.pos || 'all'] || D.default_columns.all).filter(k => MK.has(k)); save(); renderScrn(); return; }
    if (a === 'scpos') { S.scat.pos = t.dataset.v || null; scatCur = null; save(); renderScat(); return; }
    if (a === 'rtpl') { S.radar.tpl = t.dataset.v; save(); renderRadar(); return; }
    if (a === 'formk') { S.form.k = t.dataset.k; save(); renderForm(); return; }
    if (a === 'club') { S.club = t.dataset.cid; save(); renderTeam(); return; }
    if (a === 'cmpadd') { addCompare(t.dataset.pid); out(`Comparing ${listText(S.compare.map(id => PID.get(id).name))}.`); return; }
    if (a === 'cmpwith') { compareWith(); return; }
    if (a === 'cmprm') { S.compare = S.compare.filter(id => id !== t.dataset.pid); save(); renderAll(); return; }
    if (a === 'cmpclear') { S.compare = []; save(); renderAll(); return; }
    if (a === 'pane') { showPanel(t.dataset.id); return; }
    if (a === 'fkey') {
      if (t.dataset.id === 'clips') { if (drawerOpen()) closeDrawer(); else openDrawer(true); return; }
      // From the phone's panel row, the panel's top always comes up under the row.
      showPanel(t.dataset.id, true, null, !!t.closest('#txNav')); if (t.closest('#txNav')) navCurrent(t.dataset.id); const h = $('tx-h-' + t.dataset.id); if (h) h.focus({ preventScroll: true }); return;
    }
    if (a === 'dclose') { closeDrawer(); return; }
    if (a === 'pclose') { const pp = S.panels.find(p => p.id === t.dataset.id); pp.on = false; save(); renderLayout(); renderAll(); const k = document.querySelector(`.tx-fkey[data-id="${t.dataset.id}"]`); if (k) k.focus(); return; }
    if (a === 'psize') { const pp = S.panels.find(p => p.id === t.dataset.id); pp.size = SIZE_NEXT[pp.size] || 'S'; save(); renderLayout(); renderAll(); const b = document.querySelector(`[data-act="psize"][data-id="${pp.id}"]`); if (b) b.focus(); out(`${PANELS.find(x => x.id === pp.id).title}: ${SIZE_NAME[pp.size]}.`); return; }
    if (a === 'pmove') {
      const i = S.panels.findIndex(p => p.id === t.dataset.id), d = +t.dataset.d;
      let j = i + d; while (S.panels[j] && !S.panels[j].on) j += d;
      if (!S.panels[j]) return;
      const [pp] = S.panels.splice(i, 1); S.panels.splice(j, 0, pp); save(); renderLayout(); renderAll();
      // The same arrow keeps focus, unless the panel reached the end: then the other arrow.
      const b = document.querySelector(`[data-act="pmove"][data-id="${pp.id}"][data-d="${d}"]`), o = document.querySelector(`[data-act="pmove"][data-id="${pp.id}"][data-d="${-d}"]`);
      (b && !b.disabled ? b : o).focus(); return;
    }
    // Phones: saved layouts and the small-sample note fold into "Layouts & notes".
    if (a === 'more') { const o = t.getAttribute('aria-expanded') !== 'true'; t.setAttribute('aria-expanded', String(o)); t.closest('.tx-line').classList.toggle('open', o); return; }
    if (a === 'ws') { switchWs(+t.dataset.i); return; }
    if (a === 'reset') { resetWs(); return; }
    if (a === 'help') { openHelp(t); return; }
    if (a === 'helpclose') { closeHelp(); return; }
    // An example or a suggestion button runs its command. From help (which closes) focus goes to the search box; elsewhere
    // it stays on the button, so a phone does not pop its keyboard.
    if (a === 'run') { const c = t.dataset.cmd, fromHelp = !$('txHelp').hidden && $('txHelp').contains(t); if (fromHelp) $('txHelp').hidden = true; $('txIn').value = ''; closeAc(); run(c); if (fromHelp) $('txIn').focus({ preventScroll: true }); return; }
  }
  function wire() {
    const root = document.querySelector('.tx');
    root.addEventListener('click', (e) => {
      const t = e.target.closest('[data-act]');
      if (!ready) return;
      // A click anywhere on a row of the players table (not on its name or a number) selects that player.
      if (!t) {
        const tr = e.target.closest('tbody[data-r="grid"] tr[data-row]');
        if (tr && !e.target.closest('a, button, input, select, summary')) { scrAct = { pid: tr.dataset.row, c: 0 }; select(tr.dataset.row); }
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
      if (r === 'addcol' && e.target.value) { colMenuOpen = true; S.scr.cols.push(e.target.value); save(); renderScrn(); const sel = document.querySelector('[data-fid="scr-add"]'); if (sel) sel.focus(); }
      if (r === 'scrqual') { S.scr.qual = e.target.checked; scrAct = null; save(); renderScrn(); }
      if (r === 'formk') { S.form.k = e.target.value; save(); renderForm(); }
      if (r === 'scx' || r === 'scy') { S.scat[r === 'scx' ? 'x' : 'y'] = e.target.value; scatCur = null; save(); renderScat(); }
      if (r === 'scall') { S.scat.all = e.target.checked; scatCur = null; save(); renderScat(); }
    });
    root.addEventListener('input', (e) => { if (e.target.dataset.r === 'scrq') { S.scr.q = e.target.value; scrAct = null; save(); renderScrn(); } });
    root.addEventListener('keydown', (e) => {
      const t = e.target;
      // SVG buttons (shots, form bars) take Enter and Space like buttons.
      if ((e.key === 'Enter' || e.key === ' ') && t.getAttribute && t.getAttribute('role') === 'button' && t.tagName !== 'BUTTON' && t.dataset.act) { e.preventDefault(); doAct(t, e); return; }
      if (t.dataset && t.dataset.r === 'scat') return scatKeys(e);
      if (t.closest && t.closest('tbody[data-r="grid"]')) return gridKeys(e, t);
    });
    // tooltips
    root.addEventListener('mouseover', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && el !== tipFor && !el.closest('#txAc')) showTip(el); });
    root.addEventListener('mouseout', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && el === tipFor && !el.contains(e.relatedTarget) && document.activeElement !== el) hideTip(); });
    root.addEventListener('focusin', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && !el.closest('#txAc')) showTip(el, !!(el.dataset.pid && el.closest('tbody[data-r="grid"]'))); else hideTip(); });
    root.addEventListener('focusout', (e) => { if (tipFor && e.target === tipFor) hideTip(); });
    let navT = 0;
    window.addEventListener('scroll', () => {
      if (tipFor && document.activeElement !== tipFor) hideTip();
      if (!navT) navT = setTimeout(() => { navT = 0; if (ready) navCurrent(); }, 80);
    }, { passive: true });
    // the command line
    const inp = $('txIn');
    $('txForm').addEventListener('submit', (e) => {
      e.preventDefault(); if (!ready) return;
      if (acAt >= 0) { accept(acAt); return; }
      const v = inp.value; inp.value = ''; closeAc(); run(v);
    });
    inp.addEventListener('input', () => { if (ready) suggest(); });
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
        histAt = histAt < 0 ? store.hist.length - 1 : Math.max(0, histAt - 1);
        inp.value = store.hist[histAt]; inp.setSelectionRange(inp.value.length, inp.value.length); return;
      }
      if (e.key === 'ArrowDown' && !open && histAt >= 0) {
        e.preventDefault(); histAt++;
        if (histAt >= store.hist.length) { histAt = -1; inp.value = ''; } else inp.value = store.hist[histAt];
        return;
      }
      if (e.key === 'Tab' && open && !e.shiftKey) { e.preventDefault(); accept(acAt >= 0 ? acAt : 0); return; }
      if (e.key === 'Escape') { e.stopPropagation(); if (open) closeAc(); else if (inp.value) inp.value = ''; else hideTip(); }
    });
    $('txAc').addEventListener('mousedown', (e) => { const li = e.target.closest('li[data-i]'); if (li) { e.preventDefault(); accept(+li.dataset.i); } });
    // global keys
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (!location.hash.startsWith('#scout/terminal')) location.hash = 'scout/terminal';
        wantFocus = true;
        setTimeout(() => { inp.focus(); inp.select(); }, 30);
        return;
      }
      if (!location.hash.startsWith('#scout/terminal') || !ready) return;
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
        e.preventDefault();
        if (p.drawer) { if (drawerOpen()) closeDrawer(); else openDrawer(true); return; }
        showPanel(p.id); const h = $('tx-h-' + p.id); if (h) h.focus({ preventScroll: true });
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
    const pts = scatPoints(); if (!pts.length) return;
    let i = scatCur != null ? scatCur : Math.max(0, pts.findIndex(o => o.p.id === S.focus));
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = Math.min(pts.length - 1, i + 1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = Math.max(0, i - 1);
    else if (e.key === 'Home') i = 0; else if (e.key === 'End') i = pts.length - 1;
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (scatCur != null) { const id = pts[scatCur].p.id; scatCur = null; select(id); } return; }
    else return;
    e.preventDefault(); scatCur = i; renderScat();
    out(`${pts[i].p.name} · ${MK.get(S.scat.x).label} ${fmt(MK.get(S.scat.x), pts[i].a.value)} · ${MK.get(S.scat.y).label} ${fmt(MK.get(S.scat.y), pts[i].b.value)} (Enter selects)`);
  }

  wire();
  // FORM and SCAT are drawn at their panel's width: redraw them when it changes.
  let lastW = window.innerWidth, resizeT = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => { if (!ready) return; placeNav(); navCurrent(); fitTall(); if (window.innerWidth === lastW) return; lastW = window.innerWidth; if (visible('form')) renderForm(); if (visible('scat')) renderScat(); }, 150);
  });
  window.addEventListener('hashchange', onRoute);
  onRoute();
})();
