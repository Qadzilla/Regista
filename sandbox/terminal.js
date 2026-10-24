// The Scout terminal (sandbox, part B6): Maya Lindqvist's Terminal section under Scout (#scout/terminal). A command line
// with Bloomberg-style mnemonics (TOURE <GO>, RANK FW npxg, CMP, SCAT, SIM, SHOT, FORM, TEAM, HELP) over linked panels:
// screener, player, radar or pizza vs position peers, clips, shot map, heat map, form, scatter, team style. Selecting a
// player in any panel updates the others; every number opens the moments behind it (the engine's evidence) in the clips
// panel, which plays them from the local app named in terminal.json ("app"; never the live app, which runs the old
// league). terminal.json is part A's metrics engine exported by tools/export_terminal.py; it holds no hidden ratings.
// Three workspaces (panels, players, columns) are kept in this browser only (localStorage, wrapped in try/catch).
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
  const LS = 'regista.terminal.v1';

  let D = null, APP = '', loading = false, ready = false;
  const MK = new Map(), TK = new Map(), PID = new Map(), CID = new Map(), TEAMS = new Map(), SHOTS = new Map();
  let store = { cur: 0, ws: [null, null, null], hist: [] }, S = null, storageOK = true, saveT = 0;
  let reel = null, histAt = -1, acItems = [], acAt = -1, scatCur = null, scrAct = null, tipFor = null;

  // ------------------------------------------------------------------ loading (the first time the section opens)
  function onRoute() {
    if (!location.hash.startsWith('#scout/terminal')) { const v = clipVideo(); if (v) v.pause(); hideTip(); return; }
    if (!D && !loading) load();
  }
  function load() {
    loading = true;
    out('Loading the Regista League…');
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
    paintMeta(); paintKeys(); renderLayout(); renderAll();
    ready = true;
    out(`Ready: ${d.players.length} players, ${d.metrics.length} metrics, ${d.matches.length} matches. Type a name, a command or HELP, then Enter.`);
    if (location.hash.startsWith('#scout/terminal') && wantFocus) $('txIn').focus();
  }
  let wantFocus = false;

  // ------------------------------------------------------------------ workspaces, per visitor
  function defaults() {
    const f = PID.has('pl_bro_09') ? 'pl_bro_09' : D.players.find(p => p.minutes > 0).id, fp = PID.get(f);
    const cols = (D.default_columns[fp.position] || D.default_columns.all).filter(k => MK.has(k));
    return { v: 2, panels: DEFAULT_ORDER.map(id => PANELS.find(p => p.id === id)).map(p => ({ id: p.id, on: true, size: p.size })), focus: f, compare: [], club: fp.club_id,
      scr: { pos: fp.position, cols, sort: { k: cols[0], dir: -1 }, qual: true, mode: 'val', q: '' },
      scat: { x: 'npxg', y: 'xa', pos: fp.position, all: false }, form: { k: null }, radar: { tpl: 'pos' } };
  }
  function clean(s) {
    const o = defaults();
    if (!s || typeof s !== 'object' || (s.v !== 1 && s.v !== 2)) return o;
    // Version 1 had three sizes (L spanned the full width) and a default layout three screens tall: a v1 layout that is
    // still that default takes the new one; a layout the visitor changed is kept, its L read as XL.
    const V1_DEFAULT = 'scrn:L,plyr:S,radar:S,clips:S,shot:S,heat:S,form:S,scat:M,team:M';
    if (s.v === 1 && Array.isArray(s.panels) && s.panels.map(p => p && `${p.id}:${p.size}`).join(',') === V1_DEFAULT && s.panels.every(p => p.on !== false)) s.panels = null;
    else if (s.v === 1 && Array.isArray(s.panels)) s.panels = s.panels.map(p => p && p.size === 'L' ? { ...p, size: 'XL' } : p);
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
  const noisy = (m) => m.noisy ? '<span class="tx-noisy" aria-label="noisy">≈</span>' : '';
  function shade(m, pct) {
    if (pct == null) return '';
    const a = (0.05 + 0.4 * pct / 100).toFixed(3);
    return m.higher_is_better === null ? `background:rgba(110,140,200,${a})` : `background:rgba(255,205,40,${a})`;
  }
  const cellOf = (p, k) => (p && p.metrics && p.metrics[k]) || null;
  const pctOf = (p, k) => { const c = cellOf(p, k); return c ? c.percentile : null; };
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

  // ------------------------------------------------------------------ static pieces: meta strip, function keys, layout
  function paintMeta() {
    const sm = D.season.sample || {};
    const first = String(D.note || '').split('. ')[0].replace(/\.$/, '');
    $('txMeta').innerHTML = `<p class="tx-syn"><b>SYNTHETIC DATA</b> ${esc(first)}.</p>
      <details class="tx-about"><summary>Small sample · <span class="tx-noisy">≈</span> noisy</summary>
        <p>${esc(sm.note || '')}</p>
        <p><span class="tx-noisy">≈</span> ${esc(D.season.noisy_rule)} (r below ${esc(D.season.noise_r)}).</p>
        <p>Percentiles: ${esc(D.season.percentile_rule)}. Peers: ${esc(D.season.peer_groups)}. Qualified: at least ${esc(D.season.min_minutes)} minutes.</p>
        <p>${esc(D.evidence_rule)}</p></details>
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
    }).join('') + `<button type="button" class="tx-fkey help" data-act="help" aria-haspopup="dialog"><b>?</b> HELP<span>Commands and keys</span></button>`;
  }
  function renderLayout() {
    const g = $('txGrid');
    const keepClips = $('txClipBody');
    g.innerHTML = S.panels.filter(p => p.on).map((pp) => {
      const p = PANELS.find(x => x.id === pp.id), n = PANELS.indexOf(p) + 1;
      return `<section class="tx-panel s-${pp.size}" id="tx-p-${p.id}" data-panel="${p.id}" aria-labelledby="tx-h-${p.id}">
        <header class="tx-ph"><h2 id="tx-h-${p.id}" tabindex="-1"><span class="tx-fk">F${n}</span> ${esc(p.key)} <span class="tx-pt">${esc(p.title)}</span></h2>
          <span class="tx-pctx" data-ctx></span>
          <span class="tx-pbtns"><button type="button" data-act="pmove" data-id="${p.id}" data-d="-1" aria-label="Move ${esc(p.title)} earlier" title="Move earlier">&#9664;</button><button type="button" data-act="pmove" data-id="${p.id}" data-d="1" aria-label="Move ${esc(p.title)} later" title="Move later">&#9654;</button><button type="button" data-act="psize" data-id="${p.id}" aria-label="${esc(p.title)} size ${pp.size}, change" title="Size: S, M, L or XL">${pp.size}</button><button type="button" data-act="pclose" data-id="${p.id}" aria-label="Hide ${esc(p.title)}" title="Hide (F-key brings it back)">&times;</button></span></header>
        <div class="tx-pb" data-body></div></section>`;
    }).join('') || '<p class="tx-empty">Every panel is hidden. Press a function key above to bring one back.</p>';
    const cb = document.querySelector('#tx-p-clips [data-body]');
    if (cb) cb.appendChild(keepClips || buildClipBody());
    paintKeys();
  }
  const visible = (id) => S.panels.some(p => p.id === id && p.on);
  function showPanel(id, scroll = true) {
    const pp = S.panels.find(p => p.id === id);
    if (pp && !pp.on) { pp.on = true; save(); renderLayout(); renderAll(); }
    if (scroll) {
      const el = $('tx-p-' + id);
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.top < barBottom() || r.top > window.innerHeight - 80) scrollToPanel(el);
        el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
      }
    }
  }
  function renderAll() {
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
  function renderSel() {
    const f = PID.get(S.focus);
    const chips = S.compare.map((id, i) => { const p = PID.get(id); return `<span class="tx-chip" style="--c:${CMP_COL[i]}"><button type="button" data-act="sel" data-pid="${esc(id)}" data-fid="chip-${esc(id)}">${esc(p.name)}</button><button type="button" class="tx-x" data-act="cmprm" data-pid="${esc(id)}" aria-label="Remove ${esc(p.name)} from the comparison">&times;</button></span>`; }).join('');
    $('txSel').innerHTML = `<span class="tx-sl">FOCUS</span><button type="button" class="tx-focus" data-act="pane" data-id="plyr">${esc(f.name)} <span>${esc(f.short_name)} ${esc(f.position)} #${esc(f.kit_number)}</span></button>
      <span class="tx-sl">CMP</span>${chips || '<span class="tx-dim">none</span>'}
      ${S.compare.includes(S.focus) || S.compare.length >= 3 ? '' : `<button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(S.focus)}">+ add ${esc(f.name.split(' ').slice(-1)[0])}</button>`}
      ${S.compare.length ? '<button type="button" class="tx-mini" data-act="cmpclear">Clear</button>' : ''}`;
  }
  function addCompare(pid) {
    if (S.compare.includes(pid)) return;
    if (S.compare.length >= 3) S.compare.shift();
    S.compare.push(pid); save(); renderAll();
  }

  // ------------------------------------------------------------------ evidence into the clips panel
  function evidenceReel(pid, mk, match) {
    const p = PID.get(pid), m = MK.get(mk), ev = p.evidence && p.evidence[mk], c = cellOf(p, mk);
    const r = { title: `${p.name} · ${m.label}`, sub: c ? `${fmt(m, c.value)}${m.kind === 'ratio' && m.unit === '%' ? '' : ' ' + unitText(m)}${c.num != null ? ` · ${c.num} of ${c.den}` : c.total != null && m.kind !== 'total' ? ` · ${c.total} in total` : ''}${c.percentile != null ? ` · ${ord(c.percentile)} pctl` : ''}` : 'No minutes this season',
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
      if (!r.items.length) r.note = r.total > r.shown ? `This match's moments are past the first ${r.shown} exported; open the full list on the local app.` : 'No moments behind this number in this match.';
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
    // The scout must see the clip start: if most of the video (or, with nothing to play, the list) is out of view, behind
    // the sticky command bar or below the fold, bring the clips panel up.
    const el = $('tx-p-clips');
    if (el) {
      const scr = el.querySelector('.tx-screen'), target = scr && !scr.hidden ? scr : el.querySelector('.tx-cliphead') || el;
      if (!inView(target, 0.75)) scrollToPanel(el);
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
    }
  }
  // The bottom of what stays on top while scrolling: the sticky command bar (its height changes with the output line); on
  // a phone, where the bar scrolls away, the site header and the row of view tabs under it.
  function barBottom() {
    const bar = document.querySelector('.tx-top');
    if (bar && getComputedStyle(bar).position === 'sticky') return bar.getBoundingClientRect().bottom;
    const side = document.querySelector('.side'), top = document.querySelector('.top');
    return Math.max(0, side && getComputedStyle(side).flexDirection === 'row' ? side.getBoundingClientRect().bottom : 0, top ? top.getBoundingClientRect().bottom : 0);
  }
  // At least `frac` of the element is on screen, below the sticky command bar.
  function inView(node, frac) {
    const r = node.getBoundingClientRect(); if (!r.height) return false;
    return Math.min(r.bottom, window.innerHeight) - Math.max(r.top, barBottom()) >= r.height * frac;
  }
  // Scroll a panel's top to just below the command bar.
  function scrollToPanel(el) {
    const top = el.getBoundingClientRect().top + window.scrollY - barBottom() - 8;
    window.scrollTo({ top: Math.max(0, top), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
  function openEvidence(pid, mk, match) { if (PID.has(pid) && MK.has(mk)) openReel(evidenceReel(pid, mk, match)); }

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
    v.addEventListener('error', () => { if (v.getAttribute('src')) msg(`The clip did not load from ${APP}. Clips play from the local app on part A's code; start it and try again (each clip renders on its first request, which takes a few seconds).`); });
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
    b.querySelector('.tx-screen').hidden = !reel;
    b.querySelector('.tx-clipctl').hidden = !reel;
    if (!reel) {
      head.innerHTML = '<p class="tx-dim">Pick any number in any panel: the moments behind it play here.</p>';
      list.innerHTML = ''; if (ctx) ctx.textContent = ''; return;
    }
    const capped = reel.total > reel.shown;
    head.innerHTML = `<p class="tx-ct">${esc(reel.title)}</p><p class="tx-cs">${esc(reel.sub)}</p>
      <p class="tx-cs">${reel.match ? `${reel.items.length} in this match` : capped ? `First ${reel.shown} of ${reel.total}${reel.unit === 'match' ? ' matches' : ''}` : `${reel.items.length} ${reel.unit === 'match' ? 'match' : 'moment'}${reel.items.length === 1 ? '' : (reel.unit === 'match' ? 'es' : 's')}`}${capped && reel.pid ? ` · <a href="${esc(reel.full)}" target="_blank" rel="noopener">all ${esc(reel.total)} on the local app &#8599;</a>` : ''}</p>
      ${reel.legend ? `<p class="tx-cs tx-dim">${esc(reel.legend)}</p>` : ''}${reel.note ? `<p class="tx-cs tx-dim">${esc(reel.note)}</p>` : ''}`;
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
      const qa = ca && (m.has_percentile ? ca.percentile != null : true), qb = cb && (m.has_percentile ? cb.percentile != null : true);
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
    if (pa == null || pb == null || pa === pb) return 0;
    return (m.higher_is_better === false ? -dir : dir) * (pa - pb);
  }
  // Rank numbers as the engine gives them: rows with the same shown value share a rank (1, 2, 2, 4); rows without a
  // percentile (below the minimum attempts) are listed after, unranked.
  function screenRanks(rows) {
    const k = S.scr.sort.k, m = MK.get(k);
    if (!m) return rows.map((_, i) => i + 1);
    let prev = null, place = 0;
    return rows.map((p, i) => {
      const c = cellOf(p, k);
      if (!c || c.value == null || (m.has_percentile && c.percentile == null)) return null;
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
    const sc = S.scr, rows = screenRows(), cols = sc.cols.filter(k => MK.has(k));
    const sortAttr = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? 'descending' : 'ascending') : 'none';
    const arrow = (k) => sc.sort.k === k ? (sc.sort.dir === -1 ? ' ▼' : ' ▲') : '';
    if (!scrAct || !rows.some(p => p.id === scrAct.pid)) scrAct = { pid: rows.some(p => p.id === S.focus) ? S.focus : (rows[0] && rows[0].id), c: 0 };
    if (scrAct.c > cols.length) scrAct.c = 0;
    const cell = (p, k, ci) => {
      const m = MK.get(k), c = cellOf(p, k), act = scrAct.pid === p.id && scrAct.c === ci + 1;
      if (!c) return `<td class="num"><span class="tx-dim">–</span></td>`;
      const txt = sc.mode === 'pct' ? (c.percentile == null ? '–' : c.percentile) : fmt(m, c.value);
      const lab = `${p.name}, ${m.label} ${fmt(m, c.value)}${c.percentile != null ? `, ${ord(c.percentile)} percentile` : ', no percentile'}. Open its moments`;
      return `<td class="num"><button type="button" class="tx-n${c.percentile == null && m.has_percentile ? ' uq' : ''}" style="${shade(m, c.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-nav data-fid="c-${esc(p.id)}-${esc(k)}" tabindex="${act ? 0 : -1}" aria-label="${esc(lab)}">${esc(txt)}</button></td>`;
    };
    const head = `<tr><th class="tx-stk" aria-sort="${sortAttr('name')}"><button type="button" data-act="sort" data-k="name" data-fid="h-name">Player${arrow('name')}</button></th>
      <th aria-sort="${sortAttr('club')}"><button type="button" data-act="sort" data-k="club" data-fid="h-club">Club${arrow('club')}</button></th><th>Pos</th>
      <th class="num" aria-sort="${sortAttr('min')}"><button type="button" data-act="sort" data-k="min" data-fid="h-min">Min${arrow('min')}</button></th>
      ${cols.map(k => { const m = MK.get(k); return `<th class="num" aria-sort="${sortAttr(k)}"><span class="tx-th"><button type="button" data-act="sort" data-k="${esc(k)}" data-mk="${esc(k)}" data-fid="h-${esc(k)}">${esc(m.label)}${noisy(m)}${arrow(k)}</button><button type="button" class="tx-x" data-act="rmcol" data-k="${esc(k)}" aria-label="Remove the ${esc(m.label)} column">&times;</button></span></th>`; }).join('')}</tr>`;
    const ranks = screenRanks(rows);
    const body = rows.map((p, r) => {
      const ci = S.compare.indexOf(p.id), act = scrAct.pid === p.id && scrAct.c === 0;
      return `<tr class="${p.id === S.focus ? 'on' : ''}${ci >= 0 ? ' cmp' : ''}"${ci >= 0 ? ` style="--c:${CMP_COL[ci]}"` : ''}>
        <th class="tx-stk" scope="row"><span class="tx-rk">${ranks[r] == null ? '–' : ranks[r]}</span><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-nav data-fid="n-${esc(p.id)}" tabindex="${act ? 0 : -1}"${p.id === S.focus ? ' aria-current="true"' : ''}>${esc(p.name)}</button></th>
        <td>${esc(p.short_name)}</td><td>${esc(p.position)} <span class="tx-dim">${esc(p.role)}</span></td><td class="num">${esc(Math.round(p.minutes))}</td>
        ${cols.map((k, i) => cell(p, k, i)).join('')}</tr>`;
    }).join('');
    const html = `<div class="tx-ctls">
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scrpos" data-v="${v || ''}" aria-pressed="${sc.pos === v}">${v || 'ALL'}</button>`).join('')}</div>
        <label class="tx-ctl"><span class="sr">Filter by name or club</span><input type="search" data-r="scrq" data-fid="scr-q" value="${esc(sc.q)}" placeholder="Filter name / club" autocomplete="off"></label>
        <label class="tx-chk"><input type="checkbox" data-r="scrqual" data-fid="scr-qual"${sc.qual ? ' checked' : ''}> Qualified (${esc(D.season.min_minutes)}+ min)</label>
        <div class="tx-seg" role="group" aria-label="Show"><button type="button" data-act="scrmode" data-v="val" aria-pressed="${sc.mode === 'val'}">Value</button><button type="button" data-act="scrmode" data-v="pct" aria-pressed="${sc.mode === 'pct'}">Pctl</button></div>
        <label class="tx-ctl"><span class="sr">Add a column</span><select data-r="addcol" data-fid="scr-add"><option value="">+ Add column…</option>${metricOptions(null, m => !cols.includes(m.key))}</select></label>
        <button type="button" class="tx-mini" data-act="scrdef">Default columns</button></div>
      <p class="tx-cap">${rows.length} ${esc(sc.pos ? POSN[sc.pos] : 'players')}${sc.qual ? ', qualified' : ''} · shading = percentile vs position peers · arrow keys move, Enter opens</p>
      <div class="tx-scroll tx-tablewrap"><table class="tx-table"><thead>${head}</thead><tbody data-r="grid">${body || `<tr><td colspan="${4 + cols.length}" class="tx-dim">No players match.</td></tr>`}</tbody></table></div>`;
    paint('scrn', html, esc(sc.sort.k && MK.has(sc.sort.k) ? `sorted by ${MK.get(sc.sort.k).label}` : ''));
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
          ${p.qualified ? '<span class="tx-tag">QUALIFIED</span>' : `<span class="tx-tag dim">UNDER ${esc(D.season.min_minutes)} MIN</span>`}</p></div></div>
      <dl class="tx-bio">${bio.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      <div class="tx-acts"><button type="button" class="tx-mini" data-act="cmpadd" data-pid="${esc(p.id)}"${S.compare.includes(p.id) ? ' disabled' : ''}>+ Compare</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="SHOT ${esc(p.name)}">Shots</button><button type="button" class="tx-mini" data-act="run" data-cmd="FORM ${esc(p.name)}">Form</button>
        <button type="button" class="tx-mini" data-act="run" data-cmd="TEAM ${esc(p.short_name)}">Team</button></div>
      ${p.minutes > 0 ? `<h3 class="tx-h3">Best vs ${esc(POSN[p.position])}</h3>
      <table class="tx-mt"><tbody>${strengths.map(m => mrow(p, m)).join('')}</tbody></table>` : '<p class="tx-dim">No minutes this season.</p>'}
      <h3 class="tx-h3" id="txSimHead" tabindex="-1">SIM · most similar</h3>
      ${(p.similar || []).length ? `<ol class="tx-sim">${p.similar.map(s => { const q = PID.get(s.id); return `<li><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(s.id)}" data-fid="sim-${esc(s.id)}">${esc(s.name)}</button>
        <span class="tx-dim">${esc(short(s.club_id))} ${esc(q ? q.position : '')}</span><span class="tx-simbar" aria-label="similarity ${esc(s.similarity)}"><i style="width:${Math.max(2, Math.round(s.similarity * 100))}%"></i></span><span class="num">${esc(s.similarity.toFixed(2))}</span>
        <span class="tx-shared">${s.shared_strengths.filter(k => MK.has(k)).map(k => `<button type="button" class="tx-kchip" data-act="ev" data-pid="${esc(s.id)}" data-mk="${esc(k)}" data-fid="sim-${esc(s.id)}-${esc(k)}">${esc(MK.get(k).label)}</button>`).join('')}</span></li>`; }).join('')}</ol>
        <p class="tx-cap">Cosine similarity on the ${esc(p.position === 'GK' ? 'goalkeeper' : 'outfield')} template; chips are shared strengths (open them for that player).</p>` : '<p class="tx-dim">No similar players (too few minutes).</p>'}`;
    paint('plyr', html, esc(p.short_name));
  }
  // One metric row: label (definition on hover), value button (evidence), percentile bar.
  function mrow(p, m, opts = {}) {
    const c = cellOf(p, m.key);
    const val = c ? `<button type="button" class="tx-n" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(m.key)}" data-fid="${esc((opts.fid || 'm') + '-' + p.id + '-' + m.key)}" aria-label="${esc(`${m.label} ${fmt(m, c.value)}, open its moments`)}">${esc(fmt(m, c.value))}</button>` : '<span class="tx-dim">–</span>';
    const pc = c ? c.percentile : null;
    return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(m.key)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span></th><td class="num">${val}</td>
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
      const lab = MK.get(k).label, t = lab.length > 16 ? lab.slice(0, 15) + '…' : lab;
      return `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${s > 0.25 ? 'start' : s < -0.25 ? 'end' : 'middle'}" class="tx-axl">${esc(t)}</text>`;
    }).join('');
  }
  function renderRadar() {
    const f = PID.get(S.focus);
    const players = S.compare.length >= 2 ? S.compare.map(id => PID.get(id)) : [f];
    const base = players[0];
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
      players.forEach((p, j) => {
        const pts = keys.map((k, i) => { const pc = pctOf(p, k); return polar(cx, cy, r0 + (R - r0) * (pc == null ? 0 : pc) / 100, (i + 0.5) * 2 * Math.PI / n).map(v => v.toFixed(1)).join(','); }).join(' ');
        svg += `<polygon points="${pts}" fill="${CMP_COL[j]}" fill-opacity=".14" stroke="${CMP_COL[j]}" stroke-width="2"/>`;
      });
    }
    svg += axisLabels(keys, cx, cy, R) + '</svg>';
    const legend = players.map((p, j) => `<button type="button" class="tx-leg" style="--c:${CMP_COL[players.length > 1 ? j : 0]}" data-act="sel" data-pid="${esc(p.id)}" data-fid="rl-${esc(p.id)}">${esc(p.name)} <span class="tx-dim">${esc(p.short_name)} ${esc(p.position)}</span></button>`).join('');
    const tbl = players.length === 1 ? `<table class="tx-mt"><tbody>${keys.map(k => mrow(base, MK.get(k), { fid: 'r' })).join('')}</tbody></table>`
      : `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cmp"><thead><tr><th>Metric</th>${players.map((p, j) => `<th class="num" style="color:${CMP_COL[j]}">${esc(initials(p))}</th>`).join('')}</tr></thead><tbody>
        ${keys.map(k => { const m = MK.get(k); return `<tr><th scope="row"><span class="tx-ml" data-mk="${esc(k)}">${esc(m.label)}${noisy(m)}</span></th>${players.map(p => { const c = cellOf(p, k); return `<td class="num">${c ? `<button type="button" class="tx-n" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="rc-${esc(p.id)}-${esc(k)}" aria-label="${esc(`${p.name}, ${m.label} ${fmt(m, c.value)}, open its moments`)}">${esc(fmt(m, c.value))}</button><span class="tx-pc"> ${c.percentile == null ? '–' : esc(c.percentile)}</span>` : '<span class="tx-dim">–</span>'}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div>`;
    const html = `<div class="tx-ctls"><div class="tx-seg" role="group" aria-label="Metrics"><button type="button" data-act="rtpl" data-v="pos" aria-pressed="${S.radar.tpl === 'pos'}">${esc(base.position)} template</button><button type="button" data-act="rtpl" data-v="all" aria-pressed="${S.radar.tpl === 'all'}">All-round</button></div></div>
      <div class="tx-legs">${legend}</div>${svg}
      <p class="tx-cap">Percentile vs qualified ${esc(players.length > 1 ? 'peers in each player’s own position' : POSN[base.position])}${players.length > 1 ? '' : '; blue-grey wedges are style markers (ranked, not judged)'}. Values open their moments.</p>${tbl}`;
    paint('radar', html, players.length > 1 ? 'CMP' : esc(base.short_name));
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
    return `<span class="tx-stat"><span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}">${esc(m.label)}${noisy(m)}</span>${c ? `<button type="button" class="tx-n" style="${shade(m, c.percentile)}" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(k)}" data-fid="${esc(fid + k)}" aria-label="${esc(`${m.label} ${fmt(m, c.value)}, open its moments`)}">${esc(fmt(m, c.value))}</button>${c.total != null && m.kind !== 'total' && m.kind !== 'ratio' ? `<span class="tx-dim">${esc(c.total)} tot</span>` : ''}` : '<span class="tx-dim">–</span>'}</span>`;
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
    paint('shot', shots.length ? html : html.replace('</svg>', '<text x="78" y="36" text-anchor="middle" class="tx-axl" style="font-size:3.4px">No shots</text></svg>'), esc(`${p.short_name} · ${shots.length}`));
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
    paint('heat', html, esc(p.short_name));
  }

  // ------------------------------------------------------------------ FORM: match by match
  function renderForm() {
    const p = PID.get(S.focus), fm = p.form;
    const defs = (D.default_columns[p.position] || D.default_columns.all).filter(k => MK.has(k));
    const k = S.form.k && MK.has(S.form.k) ? S.form.k : defs[0], m = MK.get(k);
    if (!fm || !fm.matches || !fm.matches.length) { paint('form', '<p class="tx-dim">No matches this season.</p>', esc(p.short_name)); return; }
    const vals = fm.values[k] || [], season = cellOf(p, k);
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
    if (season && season.value != null) { const ys = y(season.value).toFixed(1); svg += `<line x1="${L}" y1="${ys}" x2="${W - 4}" y2="${ys}" class="tx-avg"/><text x="${W - 6}" y="${(season.value < 0 ? +ys + 13 : ys - 4)}" text-anchor="end" class="tx-avgl">season ${esc(fmt(m, season.value))}</text>`; }
    svg += '</svg>';
    const cons = fm.consistency || {};
    const ctab = Object.keys(cons).filter(c => MK.has(c)).map(c => { const cm = MK.get(c), x = cons[c], tr = x.last3_minus_season;
      return `<tr${c === k ? ' class="on"' : ''}><th scope="row"><button type="button" class="tx-lk" data-act="formk" data-k="${esc(c)}" data-mk="${esc(c)}" data-fid="fk-${esc(c)}">${esc(cm.label)}${noisy(cm)}</button></th>
        <td class="num"><button type="button" class="tx-n" data-act="ev" data-pid="${esc(p.id)}" data-mk="${esc(c)}" data-fid="fm-${esc(c)}" aria-label="${esc(`${cm.label} mean ${x.mean}, open its moments`)}">${esc(fmt(cm, x.mean))}</button></td><td class="num">${esc(x.sd)}</td><td class="num">${x.cv == null ? '–' : esc(x.cv)}</td>
        <td class="num ${tr > 0 ? 'up' : tr < 0 ? 'dn' : ''}">${tr == null ? '–' : (tr > 0 ? '+' : '') + esc(tr)}</td></tr>`; }).join('');
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span class="sr">Metric</span><select data-r="formk" data-fid="form-k">${metricOptions(k)}</select></label>
        <span class="tx-ml" data-mk="${esc(k)}" data-pid="${esc(p.id)}" tabindex="0">${esc(m.label)}${noisy(m)} <span class="tx-dim">ⓘ</span></span></div>${svg}
      <p class="tx-cap">Per 90 of each match (ratios and peaks per match); dashed line = season. Bars open that match's moments.</p>
      ${ctab ? `<div class="tx-scroll tx-tablewrap"><table class="tx-mt tx-cons"><thead><tr><th>Consistency</th><th class="num">Mean</th><th class="num">SD</th><th class="num">CV</th><th class="num" title="Last three matches minus the season">L3−S</th></tr></thead><tbody>${ctab}</tbody></table></div>` : ''}`;
    paint('form', html, esc(`${p.short_name} · ${fm.matches.length} m`));
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
        <span class="tx-ml" data-mk="${esc(x)}">${esc(mx.label)}</span><button type="button" class="tx-n" style="${shade(mx, cur.a.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(x)}" data-fid="scat-x">${esc(fmt(mx, cur.a.value))}</button>
        <span class="tx-ml" data-mk="${esc(y)}">${esc(my.label)}</span><button type="button" class="tx-n" style="${shade(my, cur.b.percentile)}" data-act="ev" data-sel="1" data-pid="${esc(cur.p.id)}" data-mk="${esc(y)}" data-fid="scat-y">${esc(fmt(my, cur.b.value))}</button></p>`
      : '<p class="tx-read tx-dim">The focus player is not on this chart (position or qualification). Arrow keys in the chart pick a player.</p>';
    const html = `<div class="tx-ctls"><label class="tx-ctl"><span>X</span><select data-r="scx" data-fid="scat-xs">${metricOptions(x)}</select></label>
        <label class="tx-ctl"><span>Y</span><select data-r="scy" data-fid="scat-ys">${metricOptions(y)}</select></label>
        <div class="tx-seg" role="group" aria-label="Position">${[null, ...POS].map(v => `<button type="button" data-act="scpos" data-v="${v || ''}" aria-pressed="${pos === v}">${v || 'ALL'}</button>`).join('')}</div>
        <label class="tx-chk"><input type="checkbox" data-r="scall" data-fid="scat-all"${all ? ' checked' : ''}> Include unqualified</label></div>${svg}${read}
      <p class="tx-cap">${pts.length} ${esc(pos ? POSN[pos] : 'players')}${all ? '' : ', qualified on both'} · dashed lines = medians · click a dot to select</p>`;
    paint('scat', html, esc(`${x} × ${y}`));
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
      return `<tr><th scope="row"><span class="tx-ml" data-tk="${esc(m.key)}">${esc(m.label)}</span></th>
        <td class="num"><button type="button" class="tx-n" data-act="tev" data-cid="${esc(S.club)}" data-tk="${esc(m.key)}" data-fid="tv-${esc(m.key)}" aria-label="${esc(`${c.name}, ${m.label} ${fmt(m, v.value)}, rank ${v.rank} of ${v.of}. Open the matches behind it`)}">${esc(fmt(m, v.value))}</button></td>
        <td class="num ${good ? 'up' : ''}">${esc(v.rank)}/${esc(v.of)}</td><td class="num tx-dim">${esc(fmt(m, v.league_mean))}</td>
        <td class="tx-pbar"><span class="tx-range"><i style="left:${w.toFixed(1)}%" class="${judged ? '' : 'style'}"></i><b style="left:${mean.toFixed(1)}%"></b></span></td></tr>`;
    }).join('');
    const lowBest = D.team_metrics.filter(m => m.higher_is_better === false).map(m => /^[A-Z][a-z]/.test(m.label) ? m.label[0].toLowerCase() + m.label.slice(1) : m.label);
    const squad = D.players.filter(p => p.club_id === S.club).sort((a, b) => b.minutes - a.minutes);
    const html = `<div class="tx-seg tx-clubs" role="group" aria-label="Club">${D.clubs.map(k => `<button type="button" data-act="club" data-cid="${esc(k.club_id)}" aria-pressed="${k.club_id === S.club}" title="${esc(k.name)}">${esc(k.short_name)}</button>`).join('')}</div>
      <p class="tx-name">${esc(c.name)} <span class="tx-dim">${esc(ord(row.position || 0))} · ${esc(row.points)} pts · ${esc(row.won)}-${esc(row.drawn)}-${esc(row.lost)} · ${esc(row.goals_for)}:${esc(row.goals_against)}</span></p>
      <div class="tx-team"><div class="tx-scroll tx-tablewrap"><table class="tx-mt"><thead><tr><th>Style (per 90)</th><th class="num">Value</th><th class="num">Rank</th><th class="num">Lg avg</th><th><span class="sr">Range</span></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div><h3 class="tx-h3">Squad by minutes</h3><ol class="tx-squad tx-scroll">${squad.map(p => `<li class="${p.id === S.focus ? 'on' : ''}"><button type="button" class="tx-pn" data-act="sel" data-pid="${esc(p.id)}" data-fid="sq-${esc(p.id)}">${esc(p.name)}</button><span class="tx-dim">${esc(p.position)} #${esc(p.kit_number)}</span><span class="num">${esc(Math.round(p.minutes))}′</span></li>`).join('')}</ol></div></div>
      <p class="tx-cap">Rank 1 = best${lowBest.length ? `: the lowest for ${esc(listText(lowBest))}` : ''}. Grey markers are style, ranked but not judged, and their rank 1 is the highest. The bar spans the league's six clubs; the white tick is the league average. Values open the matches (and, for set-piece xG, the shots) behind them.</p>`;
    paint('team', html, esc(c.short_name));
  }
  function teamReel(cid, tk) {
    const t = TEAMS.get(cid), m = TK.get(tk), v = t.values[tk];
    const r = { title: `${t.club} · ${m.label}`, sub: `${fmt(m, v.value)}${m.kind === 'ratio' ? '' : ' per 90'} · rank ${v.rank} of ${v.of}${v.total != null ? ` · ${Number(v.total.toFixed ? v.total.toFixed(2) : v.total)} in total` : ''}`, i: -1, items: [], note: '' };
    const ev = (t.evidence || {})[tk];
    if (ev && ev.length) {
      r.items = ev.map(e => { const hit = SHOTS.get(e.match_id + '|' + e.event_id), mt = D.matches.find(x => x.match_id === e.match_id) || {};
        const opp = mt.home === cid ? mt.away : mt.home;
        return { when: `R${e.round} v ${short(opp)}`, minute: hit ? hit.s.minute : e.minute, val: evText(m, e.value) || String(e.value), note: hit ? hit.p.name : '', video: hit ? hit.s.video_url : null, match_id: e.match_id }; });
      r.total = r.shown = r.items.length;
    } else {
      r.items = t.per_match.map(pm => ({ when: `R${pm.round} ${pm.home ? 'v' : '@'} ${short(pm.opponent)}`, minute: null, val: fmt(m, pm.values[tk]), note: 'per 90 of the match', video: null, match_id: pm.match_id }));
      r.total = r.shown = r.items.length;
      r.unit = 'match';
      r.note = 'A team-style number is built from every possession of a match: one value per match, no single clip.';
    }
    return r;
  }

  const RENDER = { scrn: renderScrn, plyr: renderPlyr, radar: renderRadar, clips: renderClips, shot: renderShot, heat: renderHeat, form: renderForm, scat: renderScat, team: renderTeam };

  // ------------------------------------------------------------------ tooltips: definition and source, on hover and focus
  function tipHtml(el) {
    const mk = el.dataset.mk, tk = el.dataset.tk;
    const m = mk ? MK.get(mk) : TK.get(tk); if (!m) return '';
    const src = (m.sources || []).map(s => (D.sources[s] || {}).title || s).join('; ');
    const judge = m.higher_is_better === null ? 'Style marker: ranked, not judged' : m.higher_is_better ? 'Higher is better' : 'Lower is better';
    let h = `<p class="tt-h">${esc(m.label)} <span class="tt-k">${esc(m.key)}</span></p><p>${esc(m.definition)}</p>
      <p class="tt-s"><b>Rule</b> ${esc(m.rule)}${src ? ` · <b>Source</b> ${esc(src)}` : ''}</p><p class="tt-s">${esc(mk ? unitText(m) : m.unit)} · ${esc(judge)}${mk && m.positions ? ` · matters for ${esc(m.positions.join(' '))}` : ''}</p>`;
    if (mk && m.noisy) h += `<p class="tt-w">≈ Noisy: split-half r ${esc(m.reliability_r)} (below ${esc(D.season.noise_r)}); one season cannot yet separate players in the same role.</p>`;
    if (mk && m.min_attempts) h += `<p class="tt-s">Percentile needs at least ${esc(m.min_attempts)}: ${esc(m.min_attempts_rule)}</p>`;
    const p = el.dataset.pid && PID.get(el.dataset.pid), c = p && mk ? cellOf(p, mk) : null;
    if (c) h += `<p class="tt-p"><b>${esc(p.name)}</b> ${esc(fmt(m, c.value))}${c.num != null ? ` (${esc(c.num)} of ${esc(c.den)})` : c.total != null && m.kind !== 'total' ? ` (${esc(c.total)} in total)` : ''} · ${c.percentile == null ? 'no percentile (below the minimum)' : `${esc(ord(c.percentile))} percentile among qualified ${esc(POSN[p.position])}`}</p>`;
    const tv = tk && el.dataset.cid ? TEAMS.get(el.dataset.cid) : null;
    if (tv && tv.values[tk]) h += `<p class="tt-p">Rank ${esc(tv.values[tk].rank)} of ${esc(tv.values[tk].of)} · league average ${esc(fmt(m, tv.values[tk].league_mean))}</p>`;
    return h;
  }
  function showTip(el) {
    const tip = $('txTip'), h = tipHtml(el); if (!h) return;
    tip.innerHTML = h; tip.hidden = false; tipFor = el;
    el.setAttribute('aria-describedby', 'txTip');
    const r = el.getBoundingClientRect(), tw = Math.min(340, window.innerWidth - 16);
    tip.style.width = tw + 'px';
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
  function resolvePlayer(q, strict) {
    const n = norm(q); if (!n) return { none: true };
    if (PID.has(q.trim())) return { p: PID.get(q.trim()), alts: [] };
    const tiers = [(p) => norm(p.name) === n, (p) => surname(p) === n || norm(p.name).split(' ').slice(-1)[0] === n, (p) => norm(p.name).split(' ')[0] === n];
    if (!strict) tiers.push((p) => norm(p.name).includes(n));
    for (const t of tiers) {
      const hit = D.players.filter(t);
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
  const altsHtml = (alts, cmd) => alts && alts.length ? ` <span class="tx-dim">· also:</span> ${alts.slice(0, 6).map(p => runBtn(`${cmd ? cmd + ' ' : ''}${p.name}`, `${p.name} ${p.short_name}`)).join(' ')}` : '';
  function onePlayer(arg, cmd) {
    if (!arg.trim()) return { p: PID.get(S.focus), alts: [] };
    const r = resolvePlayer(arg);
    if (r.p) return r;
    out(`No player called "${arg}". Type part of a name; suggestions appear as you type.`, 'err');
    return null;
  }
  function run(text) {
    const t = String(text || '').trim().replace(/\s*<GO>$/i, '').trim(); if (!t) return;
    if (store.hist[store.hist.length - 1] !== t) { store.hist.push(t); if (store.hist.length > 50) store.hist.shift(); save(); }
    histAt = -1;
    const toks = t.split(/\s+/), head = toks[0].toUpperCase().replace(/<GO>$/, ''), rest = t.slice(toks[0].length).replace(/<GO>\s*$/i, '').trim();
    if (head === 'HELP' || head === '?') { openHelp(); out('Help is open. Escape closes it.'); return; }
    if (head === 'RANK') return cmdRank(rest);
    if (head === 'CMP') return cmdCmp(rest);
    if (head === 'SCAT') return cmdScat(rest);
    if (head === 'TEAM') {
      const c = resolveClub(rest) || (rest ? null : club(S.club));
      if (!c || !c.club_id) { out(`No club called "${rest}". Clubs: ${D.clubs.map(x => x.short_name).join(', ')}.`, 'err'); return; }
      S.club = c.club_id; save(); showPanel('team'); renderTeam(); out(`TEAM ${c.short_name} · ${c.name}: style per 90, ranked across the league's six clubs.`); return;
    }
    const PANEL_CMD = { SIM: 'plyr', SHOT: 'shot', FORM: 'form', HEAT: 'heat', RDR: 'radar', PLYR: 'plyr' };
    if (PANEL_CMD[head]) {
      const r = onePlayer(rest, head); if (!r) return;
      const p = r.p;
      select(p.id, true); showPanel(PANEL_CMD[head]);
      let line;
      if (head === 'SIM') { const h = $('txSimHead'); if (h) h.scrollIntoView({ block: 'nearest' }); line = `SIM ${p.name}: ${(p.similar || []).map(s => `${s.name} ${s.similarity.toFixed(2)}`).join(', ') || 'none'}.`; }
      else if (head === 'SHOT') line = `SHOT ${p.name}: ${(p.shots || []).length} shots, ${((g) => `${g} goal${g === 1 ? '' : 's'}`)((p.shots || []).filter(s => s.outcome === 'goal').length)}. Each shot plays its clip.`;
      else if (head === 'FORM') line = `FORM ${p.name}: ${(p.form && p.form.matches || []).length} matches. Bars open that match's moments.`;
      else line = `${head} ${p.name} · ${p.club}.`;
      out('', '', esc(line) + altsHtml(r.alts, head));
      return;
    }
    if (COMMANDS[head]) return;
    const c = resolveClub(t), team = (k) => { S.club = k.club_id; save(); showPanel('team'); renderTeam(); out(`TEAM ${k.short_name} · ${k.name}.`); };
    if (c && (norm(c.short_name) === norm(t) || norm(c.name) === norm(t))) return team(c);
    const r = resolvePlayer(t);
    if (r.p) { const p = r.p; select(p.id, true); showPanel('plyr'); out('', '', esc(`${p.name} · ${p.club} · ${POS1[p.position]} (${p.role}) #${p.kit_number}`) + altsHtml(r.alts, '')); return; }
    if (c) return team(c);
    const mm = resolveMetric(t);
    if (mm.m) return cmdRank(mm.m.key);
    out(`Not a player, club or command: "${t}". Try TOURE, RANK FW npxg, TEAM BRO or HELP.`, 'err');
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
    if (!S.scr.cols.includes(m.key)) S.scr.cols.unshift(m.key);
    S.scr.sort = { k: m.key, dir: m.higher_is_better === false ? 1 : -1 };
    S.scr.q = ''; scrAct = null; save();
    showPanel('scrn'); renderScrn();
    const rows = screenRows(), ranks = screenRanks(rows), tops = rows.filter((_, i) => ranks[i] === 1), c = tops[0] && cellOf(tops[0], m.key);
    const names = tops.length > 3 ? `${tops.slice(0, 3).map(p => p.name).join(', ')} and ${tops.length - 3} more` : tops.map(p => p.name).join(tops.length === 2 ? ' and ' : ', ');
    out(`RANK ${S.scr.pos || 'ALL'} ${m.key}: ${rows.length} ${S.scr.pos ? POSN[S.scr.pos] : 'players'} by ${m.label}${m.higher_is_better === false ? ' (lowest first)' : ''}${c ? `; top ${names} ${fmt(m, c.value)}${tops.length > 1 ? `, tied at rank 1` : ''}` : ''}.`);
  }
  function cmdCmp(rest) {
    const rs = resolvePlayers(rest);
    const bad = rs.find(r => !r.p);
    if (bad || !rs.length) { out(rest ? `No player called "${bad.q}".` : 'CMP needs two or three players: CMP <player> <player> [<player>].', 'err'); return; }
    const ids = [...new Set(rs.map(r => r.p.id))].slice(0, 3);
    if (ids.length === 1 && ids[0] !== S.focus) ids.unshift(S.focus);
    if (ids.length < 2) { out('CMP needs two or three different players.', 'err'); return; }
    S.compare = ids; S.focus = ids[0]; S.club = PID.get(ids[0]).club_id; save();
    renderAll(); showPanel('radar');
    const amb = rs.filter(r => r.alts && r.alts.length);
    out('', '', esc(`CMP ${ids.map(id => PID.get(id).name).join(' · ')}: radar and table vs each player's position peers.`)
      + (amb.length ? ` <span class="tx-dim">"${esc(amb[0].q)}" could also be:</span> ${amb[0].alts.slice(0, 5).map(p => runBtn(`CMP ${ids.map(id => id === amb[0].p.id ? p.name : PID.get(id).name).join(', ')}`, `${p.name} ${p.short_name}`)).join(' ')}` : ''));
  }
  function cmdScat(rest) {
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
    showPanel('scat'); renderScat();
    out(`SCAT ${mx.key} × ${my.key}${S.scat.pos ? ' ' + S.scat.pos : ''}: ${scatPoints().length} players.`);
  }

  // ------------------------------------------------------------------ the command line: autocomplete and history
  function playerSugs(q, k, run) {
    const n = norm(q);
    const score = (p) => { const nm = norm(p.name), sn = surname(p); if (!n) return 0; if (sn.startsWith(n)) return 0; if (nm.startsWith(n)) return 1; if (nm.split(' ').some(w => w.startsWith(n))) return 2; if (n.length >= 3 && nm.includes(n)) return 3; return 9; };
    let ps;
    if (!n) { const f = PID.get(S.focus); ps = [f, ...(f.similar || []).map(s => PID.get(s.id)).filter(Boolean)]; }
    else ps = D.players.filter(p => score(p) < 9).sort((a, b) => score(a) - score(b) || b.minutes - a.minutes);
    return ps.slice(0, 7).map(p => ({ kind: 'PLAYER', text: p.name, detail: `${p.short_name} ${p.position} #${p.kit_number}`, insert: p.name, k, run }));
  }
  function metricSugs(q, k, run, prefix = '', pos = null) {
    const n = norm(q), kk = n.replace(/[\s-]+/g, '_');
    const score = (m) => { if (!n) return 0; if (m.key.startsWith(kk)) return 0; const l = norm(m.label); if (l.startsWith(n)) return 1; if (l.split(' ').some(w => w.startsWith(n))) return 2; if (m.key.includes(kk) || l.includes(n)) return 3; const ws = n.replace(/%/g, ' pct ').split(/[\s\-()+,/_]+/).filter(Boolean), mw = mwords(m); if (ws.length && ws.every(w => mw.some(x => x.startsWith(w)))) return 4; return 9; };
    const base = n ? D.metrics : (D.default_columns[pos || PID.get(S.focus).position] || D.default_columns.all).map(x => MK.get(x)).filter(Boolean);
    return base.filter(m => score(m) < 9).sort((a, b) => score(a) - score(b)).slice(0, 8)
      .map(m => ({ kind: 'METRIC', text: `${m.label}${m.noisy ? ' ≈' : ''}`, detail: m.key, insert: prefix + m.key, k, run, mk: m.key }));
  }
  function suggest() {
    const inp = $('txIn'), before = inp.value.slice(0, inp.selectionStart ?? inp.value.length);
    const toks = before.split(/\s+/), cur = toks[toks.length - 1], words = toks.filter(Boolean);
    const head = (toks[0] || '').toUpperCase(), inArgs = toks.length > 1 && COMMANDS[head];
    let s = [];
    const trailing = (fn) => { for (let k = Math.min(3, toks.length - 1); k >= 1; k--) { const q = toks.slice(-k).join(' ').trim(); const r = fn(q, k); if (r.length && q) return r; } return fn(cur, 1); };
    if (!inArgs) {
      if (!before.trim()) { acItems = []; return paintAc(); }
      if (toks.length === 1) {
        s.push(...Object.keys(COMMANDS).filter(c => c.startsWith(head)).map(c => ({ kind: 'CMD', text: c, detail: COMMANDS[c].args || COMMANDS[c].help, insert: c, k: 1, run: c === 'HELP' })));
        s.push(...playerSugs(cur, 1, true).slice(0, 5));
        s.push(...D.clubs.filter(c => norm(c.short_name).startsWith(norm(cur)) || norm(c.name).split(' ').some(w => w.startsWith(norm(cur)))).map(c => ({ kind: 'CLUB', text: c.name, detail: `TEAM ${c.short_name}`, insert: `TEAM ${c.short_name}`, k: 1, run: true })));
        s.push(...metricSugs(cur, 1, true, `RANK ${PID.get(S.focus).position} `).slice(0, 3));
      } else s = playerSugs(words.join(' '), toks.length, true);
    } else if (['SIM', 'SHOT', 'FORM', 'HEAT', 'RDR', 'PLYR'].includes(head)) s = playerSugs(toks.slice(1).join(' '), toks.length - 1, true);
    else if (head === 'CMP') { s = trailing((q, k) => playerSugs(q, k, false)); }
    else if (head === 'TEAM') { const n = norm(cur); s = D.clubs.filter(c => !n || norm(c.short_name).startsWith(n) || norm(c.name).split(' ').some(w => w.startsWith(n))).map(c => ({ kind: 'CLUB', text: c.name, detail: c.short_name, insert: c.short_name, k: 1, run: true })); }
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
    const srcs = Object.entries(D.sources).map(([k, s]) => `<li><span class="tt-k">${esc(k)}</span> ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`).join('');
    h.innerHTML = `<div class="tx-hhead"><h2 tabindex="-1" id="txHelpH">HELP · the Scout terminal</h2><button type="button" class="tx-mini" data-act="helpclose" aria-label="Close help">Esc &times;</button></div>
      <div class="tx-hbody"><table class="tx-mt"><tbody>
        <tr><th scope="row"><code>NAME</code> &lt;GO&gt;</th><td>Any surname or name opens the player: ${runBtn('TOURE')}</td></tr>
        ${Object.entries(COMMANDS).map(([c, x]) => `<tr><th scope="row"><code>${esc(c)}</code> <span class="tx-dim">${esc(x.args)}</span></th><td>${esc(x.help)} ${c === 'HELP' ? '' : runBtn(x.ex)}</td></tr>`).join('')}
      </tbody></table>
      <h3 class="tx-h3">Keys</h3><ul class="tx-keys">
        <li><kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> focus the command line</li><li><kbd>Enter</kbd> is &lt;GO&gt;</li><li><kbd>↑</kbd> <kbd>↓</kbd> history, or move in the suggestions</li>
        <li><kbd>Tab</kbd> takes a suggestion</li><li><kbd>Esc</kbd> closes suggestions, help and tips</li><li><kbd>Alt 1–9</kbd> jump to a panel (F1–F9)</li>
        <li>In the screener: arrow keys, Home/End, Enter</li><li>In the scatter: arrow keys pick a player, Enter selects</li></ul>
      <h3 class="tx-h3">Linking</h3><p>One focus player and up to three compared players drive every panel. Selecting a player anywhere (screener, scatter, similar players, squad, legend) updates the rest. Every number opens the moments behind it in CLIP; clips play from the local app at ${esc(APP)} (part A's code). Evidence is the first ${esc(10)} per number; a link gives the full list.</p>
      <h3 class="tx-h3">The numbers</h3><p>${esc(D.note)}</p><p>${esc(D.season.sample.note)}</p><p>Percentiles: ${esc(D.season.percentile_rule)}.</p>
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
  function doAct(t, e) {
    const sel = sig(t), panel = t.closest('[data-panel]'), zone = t.closest('#txSel, #txMeta, #txKeys, #txHelp, #txOut');
    const pid = panel && panel.dataset.panel, zid = zone && zone.id;
    act(t, e);
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
  function act(t, e) {
    const a = t.dataset.act;
    if (a === 'sel') { select(t.dataset.pid); return; }
    if (a === 'ev') { if (t.dataset.sel && t.dataset.pid !== S.focus) { S.focus = t.dataset.pid; S.club = PID.get(S.focus).club_id; save(); renderAll(); } openEvidence(t.dataset.pid, t.dataset.mk); return; }
    if (a === 'fev') { const k = S.form.k && MK.has(S.form.k) ? S.form.k : (D.default_columns[PID.get(S.focus).position] || D.default_columns.all)[0]; openEvidence(S.focus, k, t.dataset.mid); return; }
    if (a === 'tev') { openReel(teamReel(t.dataset.cid, t.dataset.tk)); return; }
    if (a === 'shot') { shotReel(PID.get(S.focus), +t.dataset.i); return; }
    if (a === 'clip') { play(+t.dataset.i, true); return; }
    if (a === 'cprev' || a === 'cnext') { if (!reel) return; const d = a === 'cnext' ? 1 : -1; let i = reel.i + d; while (reel.items[i] && !reel.items[i].video) i += d; if (reel.items[i]) play(i, true); return; }
    if (a === 'sort') { const k = t.dataset.k; S.scr.sort = S.scr.sort.k === k ? { k, dir: -S.scr.sort.dir } : { k, dir: k === 'name' || k === 'club' ? 1 : (MK.get(k) && MK.get(k).higher_is_better === false ? 1 : -1) }; save(); renderScrn(); return; }
    if (a === 'rmcol') {
      const i = S.scr.cols.indexOf(t.dataset.k);
      S.scr.cols = S.scr.cols.filter(k => k !== t.dataset.k); save(); renderScrn();
      const xs = document.querySelectorAll('#tx-p-scrn [data-act="rmcol"]'), next = xs[Math.min(i, xs.length - 1)] || document.querySelector('#tx-p-scrn [data-r="addcol"]');
      if (next) next.focus({ preventScroll: true });
      return;
    }
    if (a === 'scrpos') { S.scr.pos = t.dataset.v || null; scrAct = null; save(); renderScrn(); return; }
    if (a === 'scrmode') { S.scr.mode = t.dataset.v; save(); renderScrn(); return; }
    if (a === 'scrdef') { S.scr.cols = (D.default_columns[S.scr.pos || 'all'] || D.default_columns.all).filter(k => MK.has(k)); save(); renderScrn(); return; }
    if (a === 'scpos') { S.scat.pos = t.dataset.v || null; scatCur = null; save(); renderScat(); return; }
    if (a === 'rtpl') { S.radar.tpl = t.dataset.v; save(); renderRadar(); return; }
    if (a === 'formk') { S.form.k = t.dataset.k; save(); renderForm(); return; }
    if (a === 'club') { S.club = t.dataset.cid; save(); renderTeam(); return; }
    if (a === 'cmpadd') { addCompare(t.dataset.pid); out(`Comparing ${S.compare.map(id => PID.get(id).name).join(' · ')}.`); return; }
    if (a === 'cmprm') { S.compare = S.compare.filter(id => id !== t.dataset.pid); save(); renderAll(); return; }
    if (a === 'cmpclear') { S.compare = []; save(); renderAll(); return; }
    if (a === 'pane') { showPanel(t.dataset.id); return; }
    if (a === 'fkey') { showPanel(t.dataset.id); const h = $('tx-h-' + t.dataset.id); if (h) h.focus({ preventScroll: true }); return; }
    if (a === 'pclose') { const pp = S.panels.find(p => p.id === t.dataset.id); pp.on = false; save(); renderLayout(); renderAll(); const k = document.querySelector(`.tx-fkey[data-id="${t.dataset.id}"]`); if (k) k.focus(); return; }
    if (a === 'psize') { const pp = S.panels.find(p => p.id === t.dataset.id); pp.size = SIZE_NEXT[pp.size] || 'S'; save(); renderLayout(); renderAll(); const b = document.querySelector(`[data-act="psize"][data-id="${pp.id}"]`); if (b) b.focus(); return; }
    if (a === 'pmove') {
      const i = S.panels.findIndex(p => p.id === t.dataset.id), d = +t.dataset.d;
      let j = i + d; while (S.panels[j] && !S.panels[j].on) j += d;
      if (!S.panels[j]) return;
      const [pp] = S.panels.splice(i, 1); S.panels.splice(j, 0, pp); save(); renderLayout(); renderAll();
      const b = document.querySelector(`[data-act="pmove"][data-id="${pp.id}"][data-d="${d}"]`); if (b) b.focus(); return;
    }
    if (a === 'ws') { switchWs(+t.dataset.i); return; }
    if (a === 'reset') { resetWs(); return; }
    if (a === 'help') { openHelp(t); return; }
    if (a === 'helpclose') { closeHelp(); return; }
    if (a === 'run') { const c = t.dataset.cmd; if (!$('txHelp').hidden) $('txHelp').hidden = true; $('txIn').value = ''; run(c); $('txIn').focus({ preventScroll: true }); return; }
  }
  function wire() {
    const root = document.querySelector('.tx');
    root.addEventListener('click', (e) => {
      const t = e.target.closest('[data-act]');
      if (!t || !root.contains(t) || t.disabled || !ready) return;
      if (t.tagName === 'A') return;
      e.preventDefault(); doAct(t, e);
    });
    root.addEventListener('change', (e) => {
      const r = e.target.dataset.r; if (!r || !ready) return;
      if (r === 'addcol' && e.target.value) { S.scr.cols.push(e.target.value); save(); renderScrn(); const sel = document.querySelector('[data-fid="scr-add"]'); if (sel) sel.focus(); }
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
    root.addEventListener('focusin', (e) => { const el = e.target.closest('[data-mk],[data-tk]'); if (el && !el.closest('#txAc')) showTip(el); else hideTip(); });
    root.addEventListener('focusout', (e) => { if (tipFor && e.target === tipFor) hideTip(); });
    window.addEventListener('scroll', () => { if (tipFor && document.activeElement !== tipFor) hideTip(); }, { passive: true });
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
      if (e.key === 'Escape') { hideTip(); closeHelp(); if (acItems.length) closeAc(); }
      if (e.altKey && /^Digit[1-9]$/.test(e.code)) {
        const p = PANELS[+e.code.slice(5) - 1]; if (!p) return;
        e.preventDefault(); showPanel(p.id); const h = $('tx-h-' + p.id); if (h) h.focus({ preventScroll: true });
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
    resizeT = setTimeout(() => { if (!ready || window.innerWidth === lastW) return; lastW = window.innerWidth; if (visible('form')) renderForm(); if (visible('scat')) renderScat(); }, 150);
  });
  window.addEventListener('hashchange', onRoute);
  onRoute();
})();
