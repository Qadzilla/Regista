// The Player dashboard (/me): one (synthetic) league player's own space, in six sections under Player profile in the
// left panel (/me#overview, #profile, #matches, #messages, #team, #settings). It opens on Femi Toure (pl_bro_09) unless
// the address names another player (?player=pl_…); "Switch player" picks any player of the Regista League.
//
// Live, from the API: the profile (My profile is the same page scouts open, drawn by player/profile-view.js without the
// scout bar), the numbers and moments, the matches, the club's squad, results and table, uploads with every agent step
// and its time (polled), "Is this you?" questions and answers, the moments and recap of a finished upload.
// Per visitor, in this browser only (Regista.demo, shared/demo.js): messages (one store shared with the Scout
// dashboard), My details edits, settings.
//
// Uploads and answers need the admin key, kept as the Studio keeps it (shared/regista.js: asked for once, sent only in
// the X-Regista-Token header). Reads are open, so anyone can follow the progress. Plain script, no build step, no inline
// handlers or styles (the CSP allows scripts from this server only). Everything from the API reaches the page through
// textContent or attributes set one by one, never as markup.
(function () {
  'use strict';
  const R = window.Regista;
  const demo = R.demo;
  const PV = R.profileView;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const GID_RE = /^pl_[a-z0-9_]{1,40}$/;
  const POLL_MS = 2000;
  const IDLE_MS = 15000;
  const POS = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };

  // h('p', {class: 'muted'}, 'text', child, ...): elements with text children only; attributes are set, never parsed.
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }
  const swap = (el, ...kids) => { el.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false)); };

  function errText(e) {
    const d = e && e.detail !== undefined ? e.detail : e && e.message;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x && x.msg ? x.msg : JSON.stringify(x))).join('; ');
    return d ? JSON.stringify(d) : String(e);
  }
  const colour = (c, fallback) => (typeof c === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : fallback);
  // Same-origin paths only (links and videos the API hands back are relative).
  const local = (v) => (typeof v === 'string' && v.startsWith('/') && !v.startsWith('//') ? v : null);
  const clipUrl = (v) => (typeof v === 'string' && v.startsWith('/api/matches/') ? v : null);

  // The kit-coloured shirt (a goalkeeper's in the keeper's colour), built as SVG nodes.
  const SVG = 'http://www.w3.org/2000/svg';
  function shirt(kit, num, position, size = 72) {
    const k = kit || {};
    const gk = position === 'GK';
    const s = (tag, attrs) => { const el = document.createElementNS(SVG, tag); for (const [a, v] of Object.entries(attrs)) el.setAttribute(a, String(v)); return el; };
    const svg = s('svg', { viewBox: '0 0 64 60', width: size, height: Math.round(size * 60 / 64), 'aria-hidden': 'true', focusable: 'false' });
    svg.append(s('path', { d: 'M20 4 L8 10 L2 24 L11 28 L14 22 L14 56 L50 56 L50 22 L53 28 L62 24 L56 10 L44 4 C42 9 37 12 32 12 C27 12 22 9 20 4 Z',
      fill: colour(gk ? k.gk : k.primary, '#444'), stroke: 'rgba(255,255,255,.25)', 'stroke-width': 1 }));
    const t = s('text', { x: 32, y: 44, 'text-anchor': 'middle', 'font-size': 22, 'font-weight': 800, fill: gk ? '#111' : colour(k.secondary, '#fff'),
      'font-family': '-apple-system, Helvetica, Arial, sans-serif' });
    t.textContent = String(num ?? '');
    svg.append(t);
    return svg;
  }
  function paintMini(el, p) {
    const kit = p.kit || {};
    el.textContent = p.kit_number;
    el.style.background = colour(p.position === 'GK' ? kit.gk : kit.primary, '#444');
    el.style.color = p.position === 'GK' ? '#111' : colour(kit.secondary, '#fff');
  }

  // "3 min 05 s", "17 s", "2.4 s", "850 ms"
  function dur(ms) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return '';
    if (ms < 1000) return `${Math.round(ms)} ms`;
    const s = ms / 1000;
    if (s < 10) return `${s.toFixed(1)} s`;
    if (s < 60) return `${Math.round(s)} s`;
    return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')} s`;
  }
  const dayText = (epochS) => {
    try { return new Date(epochS * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return ''; }
  };
  const clockText = (epochS) => {
    try { return new Date(epochS * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
  };

  // ------------------------------------------------------------------------------------------------ state
  const S = {
    gid: null, P: null, clubs: [], season: null, writes: null, maxMb: 300, store: null,
    uploads: new Map(),   // upload_id -> { rec, el, ask, sig, answers: Map(item_id -> bool), parts, results, questions }
    timer: null, busy: false, view: null, nav: null, first: true,
    open: null, draft: [],   // Messages: the open conversation, the moments attached to the reply
  };
  const canWrite = () => S.writes === 'open' || (S.writes === 'token' && !!R.key.get());

  // Who the player is on this dashboard: the league's details, with this browser's "My details" edits on top.
  function me() {
    const P = S.P || {};
    const d = (S.gid && demo.details(S.gid)) || {};
    const kit = Number(d.kit_number);
    return {
      name: (typeof d.name === 'string' && d.name.trim()) || P.name || '',
      position: POS[d.position] ? d.position : P.position,
      kit_number: Number.isInteger(kit) && kit >= 1 && kit <= 99 ? kit : P.kit_number,
      foot: ['Right', 'Left', 'Both'].includes(d.foot) ? d.foot : '',
      height: Number(d.height) >= 140 && Number(d.height) <= 220 ? Math.round(Number(d.height)) : null,
      bio: typeof d.bio === 'string' ? d.bio.slice(0, 280) : '',
      edited: !!(S.gid && demo.details(S.gid)),
    };
  }
  const firstName = () => (me().name.split(' ')[0] || 'you');

  function netError(text, retry) {
    $('netErrorText').textContent = text;
    $('netError').hidden = false;
    $('netRetry').onclick = () => { $('netError').hidden = true; retry(); };
  }
  const offline = (e) => !(e instanceof R.ApiError);

  // ------------------------------------------------------------------------------------------------ sections
  function onSection(section, rest) {
    for (const el of document.querySelectorAll('[data-panel]')) {
      if (el.dataset.panel !== section) for (const v of el.querySelectorAll('video')) v.pause();
    }
    if (!S.P) return;
    const was = S.first;
    S.first = false;
    if (section === 'matches' && rest[0] === 'add') { toggleAdd(true); return; }
    if (section === 'matches' && rest[0] === 'questions') { setTimeout(() => $('questions').scrollIntoView({ behavior: 'smooth', block: 'start' }), 60); return; }
    if (section === 'messages') {
      const c = rest[0] && demo.forPlayer(S.gid).find((x) => x.scout === rest[0]);
      if (c) { S.open = c.id; S.draft = []; $('mx').classList.add('reading'); }
      readOpen();
      paintMessages();
    }
    if (!was) window.scrollTo(0, 0);
  }

  // The left panel's links keep the player the address names (a plain /me#overview would open Femi Toure).
  function fixNav() {
    const search = S.gid ? `?player=${enc(S.gid)}` : '';
    for (const a of document.querySelectorAll('nav.views a[href^="/me"]')) {
      a.setAttribute('href', `/me${search}${a.dataset.section ? `#${a.dataset.section}` : ''}`);
    }
  }
  function counts() {
    if (S.nav && S.gid) S.nav.count('messages', demo.unread('player', S.gid));
  }

  // ------------------------------------------------------------------------------------------------ the player
  async function choose(gid, { quiet = false } = {}) {
    if (!GID_RE.test(gid || '')) return false;
    let p;
    try { p = await R.api(`/api/players/${enc(gid)}`); } catch (e) {
      if (e instanceof R.ApiError && e.status === 404) {
        if (quiet) return false;
        $('foundNote').textContent = 'That player has not played in the Regista League.';
        return false;
      }
      if (offline(e)) { netError('Regista cannot be reached. Check the connection.', () => choose(gid, { quiet })); return false; }
      $('foundNote').textContent = `That player could not be loaded: ${errText(e)}`;
      return false;
    }
    const changed = gid !== S.gid;
    S.gid = gid; S.P = p;
    const url = new URL(location.href);
    url.searchParams.set('player', gid);
    try { history.replaceState(null, '', url.pathname + url.search + url.hash); } catch (e) { /* the page still works */ }
    fixNav();
    $('missing').hidden = true;
    $('main').classList.remove('me-wait');
    if (changed) {
      clearTimeout(S.timer);
      S.uploads.forEach((u) => { u.el.remove(); u.ask.remove(); });
      S.uploads.clear();
      S.open = null; S.draft = [];
      $('uploadMsg').textContent = '';
    }
    paintAll();
    onSection(S.nav.section(), S.nav.rest());
    await refresh();
    return true;
  }

  // After a finished upload the match is in the profile: read it again (the open evidence stays open).
  async function reloadProfile() {
    if (!S.gid) return;
    const gid = S.gid;
    try {
      const p = await R.api(`/api/players/${enc(gid)}`);
      if (gid !== S.gid) return;
      S.P = p;
      paintProfile(); paintSeason(); paintBest(); paintMatches(); paintActivity();
    } catch (e) { /* the old profile stays */ }
  }

  function paintAll() {
    const P = S.P;
    paintIdentity();
    paintProfile();
    paintSeason();
    paintBest();
    paintMatches();
    fillOpponents();
    renderKey();
    paintMessages();
    paintTeam();
    paintSettings();
    paintNeeds();
    paintActivity();
    paintQuestionsState();
    order();
    counts();
  }

  // The header strip (Switch player), the Overview's header and My profile's header, from me().
  function paintIdentity() {
    const P = S.P, d = me();
    document.title = `${d.name} · Regista Player`;
    $('as').hidden = false;
    paintMini($('asShirt'), { ...P, kit_number: d.kit_number, position: d.position });
    $('asName').textContent = d.name;
    swap($('ovShirt'), shirt(P.kit, d.kit_number, d.position));
    $('ovName').textContent = d.name;
    $('ovLine').textContent = `${POS[d.position] || d.position} · ${P.club} · Number ${d.kit_number}`;
    if (S.view) S.view.identity(d.name, d.position, d.kit_number, d);
  }

  // ------------------------------------------------------------------------------------------------ My profile
  // The same page scouts open, with My details (name, position, number, foot, height, a line about the player) on top.
  function paintProfile() {
    const keep = S.view ? S.view.state() : {};
    if (S.view) S.view.pause();
    S.view = PV.render($('meProfile'), S.P, { stat: keep.stat });
    const d = me();
    if (d.edited) S.view.identity(d.name, d.position, d.kit_number, d);
  }

  // ------------------------------------------------------------------------------------------------ Overview
  function paintSeason() {
    const P = S.P;
    const keys = (PV.HEADLINE[P.position] || PV.HEADLINE.FW).filter((k) => (P.counts || {})[k] !== undefined).slice(0, 3);
    const tile = (n, k, sub) => h('div', { class: 'ov-tile' }, h('span', { class: 'pf-n' }, n), h('span', { class: 'pf-k' }, k), h('span', { class: 'pf-rate' }, sub));
    swap($('ovSeason'),
      tile(P.appearances, P.appearances === 1 ? 'Match' : 'Matches', `${Math.round(P.minutes || 0)} minutes`),
      keys.map((k) => tile(P.counts[k], (P.stat_labels && P.stat_labels[k]) || R.tagLabel(k), PV.pctText((P.percentiles || {})[k], P.position))));
  }

  function paintBest() {
    const P = S.P;
    const top = PV.best(P, 1)[0];
    const v = $('ovVideo');
    $('ovWait').hidden = true;
    if (!top || !clipUrl(top.video_url)) {
      v.removeAttribute('src'); v.hidden = true;
      $('ovNow').textContent = '';
      $('ovTitle').textContent = 'No moments yet. Add a match and Regista cuts every moment you are on the ball.';
      return;
    }
    v.hidden = false;
    if (v.getAttribute('src') !== top.video_url) { v.preload = 'none'; v.src = top.video_url; }
    const match = (P.matches || []).find((m) => m.match_id === top.match_id);
    $('ovNow').textContent = [R.reasonLabel(top.reason), PV.roundName(match || top), PV.vsLineFor(P)(match)].filter(Boolean).join(' · ');
    $('ovNow').classList.toggle('replay', top.reason === 'replay_appearance');
    $('ovTitle').textContent = PV.short(top.title);
  }

  const latest = () => [...S.uploads.values()].map((u) => u.rec).sort((a, b) => b.created_at - a.created_at);
  const oppName = (rec) => (rec.opponent && rec.opponent.name) || (S.clubs.find((c) => c.club_id === rec.opponent_club_id) || {}).name || 'another club';
  const clipsNote = (rec) => plain(((rec.stages || []).find((s) => s.role === 'clips' && s.note && OK.has(s.status)) || {}).note || '');

  function paintNeeds() {
    if (!S.P) return;
    const convos = demo.forPlayer(S.gid).filter((c) => !c.blocked && !c.muted && c.unread && c.unread.player);
    const unread = convos.reduce((n, c) => n + c.unread.player, 0);
    const recs = latest();
    const asking = recs.filter((r) => r.status === 'needs_review');
    const up = recs[0];
    const needs = [];
    if (unread) {
      needs.push({ hot: true, href: `#messages/${enc(convos[0].scout)}`, head: `${unread} new message${unread === 1 ? '' : 's'} from scouts`,
        sub: convos.map((c) => { const s = demo.SCOUTS[c.scout] || {}; return `${s.name || 'A scout'}, ${s.club || ''}`; }).join(' · '), cta: 'Read' });
    }
    if (asking.length) {
      needs.push({ hot: true, href: '#matches/questions', head: 'Regista has a question for you',
        sub: `About your friendly v ${oppName(asking[0])}: is this you?`, cta: 'Answer' });
    }
    if (!up) {
      needs.push({ href: '#matches/add', head: 'Add a match', sub: 'Upload footage of a match you played: Regista cuts every moment you are on the ball.', cta: 'Add a match' });
    } else if (up.status === 'done') {
      needs.push({ href: '#matches', head: `Your friendly v ${oppName(up)} is ready`, sub: clipsNote(up) || 'Its moments are in your profile.', cta: 'See it' });
    } else if (up.status === 'failed') {
      needs.push({ href: '#matches', head: `Your friendly v ${oppName(up)} stopped`, sub: up.error || 'The agents could not finish it.', cta: 'See why' });
    } else if (up.status !== 'needs_review') {
      const now = steps(up).find((r) => r.state === 'running');
      needs.push({ href: '#matches', head: 'Your upload is being processed', sub: now ? `${now.label}: ${now.what}` : 'Regista’s agents are working on it.', cta: 'Follow it' });
    }
    if (!asking.length) {
      const answered = recs.flatMap((r) => (r.notes || []).filter((n) => /answer/i.test(n)));
      needs.push({ href: '#matches', head: 'No “Is this you?” questions waiting',
        sub: answered.length ? `You answered Regista on ${answered.length === 1 ? 'one upload' : `${answered.length} uploads`}.` : 'Regista asks here when it is not sure which player is you.', cta: 'Matches' });
    }
    swap($('ovNeeds'), needs.map((n) => h('a', { class: `ov-need${n.hot ? ' hot' : ''}`, href: n.href },
      h('span', { class: 'ov-nh' }, n.head), h('span', { class: 'ov-ns' }, n.sub), h('span', { class: 'ov-cta' }, `${n.cta} →`))));
  }

  function paintActivity() {
    if (!S.P) return;
    const items = [];
    for (const c of demo.forPlayer(S.gid)) {
      const last = c.msgs[c.msgs.length - 1];
      if (!last || c.blocked) continue;
      const s = demo.SCOUTS[c.scout] || { name: 'A scout', club: '' };
      items.push({ k: 'msg', at: last.at, href: `#messages/${enc(c.scout)}`,
        text: last.from === 'player' ? `You replied to ${s.name} (${s.club})` : `${s.name} (${s.club}) sent you a message` });
    }
    for (const r of latest()) {
      const what = r.status === 'done' ? `Your friendly v ${oppName(r)} was processed${clipsNote(r) ? `: ${clipsNote(r)}` : ''}`
        : r.status === 'needs_review' ? `Regista asked you about your friendly v ${oppName(r)}`
        : r.status === 'failed' ? `Your friendly v ${oppName(r)} stopped` : `Your friendly v ${oppName(r)} is being processed`;
      items.push({ k: 'up', at: (r.updated_at || r.created_at) * 1000, href: r.status === 'needs_review' ? '#matches/questions' : '#matches', text: what });
    }
    const club = S.P.club_id;
    const results = ((S.season && S.season.rounds) || []).flatMap((rd) => rd.matches.filter((m) => m.home === club || m.away === club)
      .map((m) => ({ ...m, date: m.date || rd.date }))).sort((a, b) => b.round - a.round).slice(0, 2);
    for (const m of results) {
      const sc = m.score || {};
      items.push({ k: 'match', at: Date.parse(`${m.date}T15:00:00`), href: '#profile',
        text: `Round ${m.round}: ${m.home_name} ${sc.t_home ?? ''}–${sc.t_away ?? ''} ${m.away_name}` });
    }
    items.sort((a, b) => (b.at || 0) - (a.at || 0));
    swap($('ovActivity'), items.length ? items.slice(0, 6).map((it) => h('li', {},
      h('span', { class: `ov-dot k-${it.k}`, 'aria-hidden': 'true' }), h('a', { href: it.href }, it.text),
      h('span', { class: 'muted small' }, demo.whenText(it.at, true)))) : h('li', { class: 'muted' }, 'Nothing yet.'));
  }

  // ------------------------------------------------------------------------------------------------ Switch player
  async function suggest(note) {
    try {
      const out = await R.api('/api/players?position=FW&sort=goals&limit=6');
      listFound(out.players, note || 'Or pick one of the league’s forwards:');
    } catch (e) {
      if (offline(e)) netError('Regista cannot be reached. Check the connection.', suggest);
      else $('foundNote').textContent = `The league's players could not be listed: ${errText(e)}`;
    }
  }

  async function search(q) {
    if (!q) return suggest();
    try {
      const out = await R.api(`/api/players?q=${enc(q)}&sort=name&limit=12`);
      listFound(out.players, out.players.length ? `${out.players.length === 12 ? 'The first 12' : out.players.length} matching “${q}”:` : `No player matches “${q}”.`);
    } catch (e) { $('foundNote').textContent = `Search failed: ${errText(e)}`; }
  }

  function listFound(players, note) {
    $('foundNote').textContent = note;
    swap($('found'), (players || []).map((p) => {
      const mini = h('span', { class: 'mini', 'aria-hidden': 'true' });
      paintMini(mini, p);
      return h('li', {}, h('button', { type: 'button', 'aria-current': p.global_id === S.gid ? 'true' : null, onclick: async () => {
        if (await choose(p.global_id)) closeFinder(false);
      } }, mini, h('span', { class: 'who' }, h('span', { class: 'nm' }, p.name),
        h('span', { class: 'cl' }, `${p.club} · ${POS[p.position] || p.position} · #${p.kit_number}`))));
    }));
  }

  function openFinder(note) {
    $('finder').hidden = false;
    $('change').setAttribute('aria-expanded', 'true');
    clearTimeout(S.timer);   // the uploads stop updating while another player is being picked
    if (typeof note === 'string') suggest(note);
    else if (!$('found').children.length) suggest();
    $('find').focus();
  }
  function closeFinder(focus = true) {
    $('finder').hidden = true;
    $('change').setAttribute('aria-expanded', 'false');
    if (S.gid) schedule(50);
    if (focus) $('change').focus();
  }

  function showMissing(text) {
    $('missingText').textContent = text;
    $('missing').hidden = false;
    $('main').classList.add('me-wait');
  }

  // ------------------------------------------------------------------------------------------------ Add a match
  function toggleAdd(open) {
    $('addBox').hidden = !open;
    $('addBtn').setAttribute('aria-expanded', String(open));
    if (open) setTimeout(() => { $('addBox').scrollIntoView({ behavior: 'smooth', block: 'start' }); const f = $('addBox').querySelector('input:not([type="radio"]), button'); if (f) f.focus({ preventScroll: true }); }, 60);
  }

  function fillOpponents() {
    const mine = S.P && S.P.club_id;
    swap($('opponent'), S.clubs.filter((c) => c.club_id !== mine).map((c) => h('option', { value: c.club_id }, c.name)));
  }

  function renderKey() {
    const box = $('keyBox');
    const form = $('uploadForm');
    if (S.writes === 'read-only' || S.writes === 'locked') {
      swap(box, h('p', { class: 'msg warn' }, S.writes === 'read-only' ? 'This deployment is read-only: nothing can be uploaded here.'
        : 'This deployment has no admin key configured, so nothing can be uploaded here.'));
      form.hidden = true;
      $('operator').hidden = true;
      paintKeyRow();
      return;
    }
    form.hidden = false;
    $('operator').hidden = S.writes === 'open';
    if (canWrite()) {
      swap(box, S.writes === 'token' ? h('p', { class: 'muted small' }, 'Using the admin key from this tab. ',
        h('button', { type: 'button', class: 'link', onclick: () => { R.key.clear(); renderKey(); } }, 'Forget it')) : null);
      $('uploadGo').disabled = false;
      paintKeyRow();
      return;
    }
    const input = h('input', { type: 'password', autocomplete: 'off', placeholder: 'Paste the admin key', 'aria-label': 'Admin key' });
    swap(box, h('form', { class: 'keyform', onsubmit: (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      R.key.set(v); input.value = '';
      renderKey();
      say('Key kept for this tab. Pick the video and upload.', 'ok');
    } },
    h('p', {}, h('b', {}, 'The operator’s admin key')),
    h('p', { class: 'muted small' }, 'It stays in this tab only (sessionStorage) and travels only in a request header, as in the Studio.'),
    h('div', { class: 'row' }, input, h('button', { type: 'submit' }, 'Use this key'))));
    $('uploadGo').disabled = true;
    paintKeyRow();
  }

  function say(text, tone) {
    const m = $('uploadMsg');
    m.className = `msg ${tone || ''}`;
    m.textContent = text || '';
  }

  // XMLHttpRequest, not fetch: it reports how much of the video has gone up.
  function send(fd, onProgress) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open('POST', '/api/player/uploads');
      if (R.key.get()) x.setRequestHeader('X-Regista-Token', R.key.get());
      x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
      x.onload = () => {
        let data = x.responseText;
        try { data = data ? JSON.parse(data) : null; } catch (e) { /* text */ }
        if (x.status >= 200 && x.status < 300) resolve(data);
        else reject(new R.ApiError(x.status, data && data.detail !== undefined ? data.detail : data));
      };
      x.onerror = () => reject(new Error('the connection dropped during the upload'));
      x.send(fd);
    });
  }

  async function upload(e) {
    e.preventDefault();
    const f = $('video').files[0];
    if (!f) { say('Pick the video first.', 'bad'); return; }
    if (!/\.mp4$/i.test(f.name)) { say('The footage must be an MP4 file (.mp4).', 'bad'); return; }
    if (f.size > S.maxMb * 1024 * 1024) { say(`That video is ${(f.size / 1048576).toFixed(0)} MB; the limit is ${S.maxMb} MB.`, 'bad'); return; }
    if (!$('opponent').value) { say('Pick the club you played against.', 'bad'); return; }
    const side = (document.querySelector('input[name="side"]:checked') || {}).value || 'home';
    const fd = new FormData();
    fd.append('global_id', S.gid);
    fd.append('opponent_club_id', $('opponent').value);
    fd.append('side', side);
    fd.append('video', f, f.name);
    $('uploadGo').disabled = true; say('');
    $('sending').hidden = false;
    const bar = $('sendBar');
    const progress = (done, total) => {
      const pct = Math.round((100 * done) / Math.max(1, total));
      bar.style.width = `${pct}%`;
      $('sendBarWrap').setAttribute('aria-valuenow', String(pct));
      $('sendText').textContent = pct < 100 ? `Uploading ${(done / 1048576).toFixed(1)} of ${(total / 1048576).toFixed(1)} MB…`
        : 'Storing the video and queueing the vision job…';
    };
    progress(0, f.size);
    try {
      const out = await send(fd, progress);
      say(`Uploaded. The vision job is queued${out.store === 'azure' ? ' in Azure' : ''}: follow it under Your uploads.`, 'ok');
      $('uploadForm').reset();
      upsert(out.upload);
      order();
      schedule(300);
      const u = S.uploads.get(out.upload.upload_id);
      if (u) u.el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      if (err.status === 401) { R.key.clear(); renderKey(); say('That key was not accepted. Paste it again.', 'bad'); }
      else if (err.status === 403) say(errText(err), 'bad');
      else say(`The upload failed: ${errText(err)}`, 'bad');
    } finally {
      $('sending').hidden = true;
      $('uploadGo').disabled = !canWrite();
    }
  }

  // ------------------------------------------------------------------------------------------------ Your uploads
  // Regista's agents in the order they run, one row each with its time. A stage's role (from the worker's record)
  // lights its row; the intelligence roles after the vision workflow all count as "Clips cut".
  const STEPS = [
    { key: 'received', label: 'Footage received', roles: ['queued', 'download'], what: 'The video is stored; a worker picks the job up from the queue and fetches the vision models.' },
    { key: 'shots', label: 'Camera shots', roles: ['shots'], what: 'Cuts the feed into camera shots: the main view, replays, highlights and closeups.' },
    { key: 'identity', label: 'Who is who', roles: ['identity'], what: 'Finds every player and names them by kit number, team colours and tracking.' },
    { key: 'review', label: 'Is this you?', roles: ['identity_review'], optional: true, what: 'Asks you about the calls it is least sure of.' },
    { key: 'possession', label: 'On the ball', roles: ['possession_vision'], what: 'Decides who is on the ball, moment by moment.' },
    { key: 'events', label: 'Events', roles: ['events_vision'], what: 'Spots passes, shots, take-ons, nutmegs and tackles.' },
    { key: 'writer', label: 'Match written', roles: ['vision_writer'], what: 'Writes the match as Regista’s event stream.' },
    { key: 'clips', label: 'Clips cut', roles: ['clips', 'ingest', 'validator', 'possession', 'clip', 'label', 'recap', 'persist', 'indexer', 'profiles', 'profile'],
      what: 'Cuts every moment you are on the ball, plus your replays, and labels them.' },
    { key: 'saved', label: 'Saved', roles: ['publish'], what: 'The match joins your profile.' },
  ];
  const OK = new Set(['ok', 'done', 'completed', 'success', 'succeeded']);
  const RUN = new Set(['running', 'started', 'working', 'retry', 'retrying']);
  const FAIL = new Set(['failed', 'error', 'dead_letter', 'dead']);
  const SKIP = new Set(['skipped', 'skip', 'not_run']);
  const STATUS = { queued: 'Queued', running: 'Working', needs_review: 'Waiting for you', done: 'Done', failed: 'Failed' };

  function asked(rec) {
    return rec.status === 'needs_review' || (rec.stages || []).some((s) => s.role === 'identity_review' && /answer|question/i.test(s.note || ''));
  }

  // A worker's note in plain words: no ids ("13 files saved as match pv_…" says "13 files saved"), and "2 answer(s)"
  // says "2 answers" ("1 answer" for one).
  const ID = /\b(?:pv|up|syn|vis|pl|t)_[A-Za-z0-9_]+\b/g;
  function plain(note) {
    return String(note || '')
      .replace(/\s*\bas match\s+(?:pv|up|syn|vis)_[A-Za-z0-9_]+\b/g, '')
      .replace(ID, '')
      .replace(/\b(\d+)\s+([A-Za-z]+)\(s\)/g, (m, n, w) => `${n} ${n === '1' ? w : `${w}s`}`)
      .replace(/\b([A-Za-z]+)\(s\)/g, '$1s')
      .replace(/\s{2,}/g, ' ').replace(/\s+([,.:;)])/g, '$1').trim();
  }

  function steps(rec) {
    const stages = Array.isArray(rec.stages) ? rec.stages : [];
    const shown = STEPS.filter((st) => !st.optional || asked(rec) || stages.some((s) => st.roles.includes(s.role)));
    const rows = shown.map((st) => {
      const ss = stages.filter((s) => st.roles.includes(s.role));
      const ms = ss.reduce((t, s) => t + (typeof s.ms === 'number' ? s.ms : 0), 0);
      const note = plain(ss.map((s) => s.note).filter(Boolean).slice(-1)[0] || '');
      let state = 'pending';
      if (st.key === 'received' && rec.status === 'queued') state = 'running';
      else if (st.key === 'review' && rec.status === 'needs_review') state = 'ask';
      else if (ss.some((s) => FAIL.has(s.status))) state = 'failed';
      else if (ss.some((s) => RUN.has(s.status))) state = 'running';
      else if (ss.length && ss.every((s) => SKIP.has(s.status))) state = 'skipped';
      else if (ss.length && ss.every((s) => OK.has(s.status) || SKIP.has(s.status))) state = 'ok';
      else if (st.key === 'received' && !ss.length) state = 'ok';   // a record from before the worker listed its download
      return { ...st, state, ms, note };
    });
    const last = rows.map((r) => r.state !== 'pending').lastIndexOf(true);
    if (rec.status === 'running' && !rows.some((r) => r.state === 'running')) {
      const next = rows.findIndex((r, i) => i > last && r.state === 'pending');
      if (next >= 0) rows[next].state = 'running';
    }
    if (rec.status === 'failed' && !rows.some((r) => r.state === 'failed')) {
      const next = rows.findIndex((r, i) => i > last && r.state === 'pending');
      if (next >= 0) rows[next].state = 'failed';
    }
    if (rec.status === 'done') rows.forEach((r) => { if (r.state === 'pending' || r.state === 'running') r.state = 'ok'; });
    if (rec.status === 'needs_review') {
      const ask = rows.findIndex((x) => x.key === 'review');
      rows.forEach((r, i) => { if (r.state === 'pending' && i < ask) r.state = 'ok'; });
    }
    return rows;
  }

  const ICON = { ok: '✓', failed: '✕', ask: '?', skipped: '–', pending: '·', running: '•' };
  const SAY = { ok: 'done', running: 'working', ask: 'waiting for you', failed: 'failed', skipped: 'skipped', pending: 'not yet' };

  function pipeline(rec) {
    const rows = steps(rec);
    const ol = h('ol', { class: 'pf-steps', 'aria-label': 'Regista’s agents on this video' });
    for (const r of rows) {
      const time = r.state === 'running' ? (r.key === 'received' && rec.status === 'queued' ? 'waiting…' : 'working…') : r.state === 'ask' ? 'your turn' : dur(r.ms);
      ol.append(h('li', { class: r.state, title: r.what },
        h('span', { class: 'pf-tick', 'aria-hidden': 'true' }, ICON[r.state] || ''),
        h('span', { class: 'pf-sname' }, r.label, h('span', { class: 'sr' }, `: ${SAY[r.state]}.`)),
        h('span', { class: 'pf-snote' }, r.note || r.what),
        h('span', { class: 'pf-sms' }, time)));
    }
    const now = rows.find((r) => r.state === 'running' || r.state === 'ask' || r.state === 'failed');
    const total = (rec.stages || []).reduce((t, s) => t + (typeof s.ms === 'number' ? s.ms : 0), 0);
    let line = null;
    if (now && now.state === 'running' && now.key === 'received' && rec.status === 'queued') {
      line = h('p', { class: 'now' }, h('b', {}, 'Waiting for a worker'),
        h('span', {}, S.store === 'azure' ? 'The video is in Azure Blob Storage; an Azure Container Apps Job picks the job up from the queue.' : now.what));
    } else if (now && now.state === 'running') line = h('p', { class: 'now' }, h('b', {}, now.label), h('span', {}, now.what));
    else if (now && now.state === 'ask') {
      line = h('p', { class: 'now ask' }, h('b', {}, 'Your turn'), h('span', {}, 'Regista has a question for you. ',
        h('a', { href: '#matches/questions' }, 'Answer it in Is this you?')));
    } else if (rec.status === 'done') {
      line = h('p', { class: 'now' }, h('b', {}, 'Finished'), h('span', { class: 'muted' }, total ? `The agents took ${dur(total)} in all.` : 'Every agent has run.'));
    }
    return [ol, line];
  }

  const title = (rec) => `Friendly v ${oppName(rec)}`;

  // One card per upload, kept across polls: only the parts whose data changed are rebuilt, so a playing clip or an
  // answer in progress is never reset by the next poll. The card's questions live in the "Is this you?" panel.
  function upsert(rec) {
    let u = S.uploads.get(rec.upload_id);
    if (!u) {
      const el = h('li', { class: 'pf-up run' });
      const ask = h('div', { class: 'ask-block', hidden: true });
      u = { rec, el, ask, sig: '', status: rec.status, answers: new Map(), parts: {}, results: null, questions: null };
      el.append(u.parts.head = h('div', { class: 'pf-uphead' }), u.parts.pipe = h('div', { class: 'pipe-wrap' }),
        u.parts.err = h('p', { class: 'err', role: 'alert' }), u.parts.res = h('div', { class: 'results' }));
      S.uploads.set(rec.upload_id, u);
      $('runs').append(el);
      $('asks').append(ask);
    }
    const before = u.status;
    u.rec = rec; u.status = rec.status;
    const sig = JSON.stringify([rec.status, rec.stages, rec.error, rec.updated_at, !!rec.links, S.store]);
    if (sig === u.sig) return;
    u.sig = sig;
    u.el.classList.toggle('live', rec.status === 'queued' || rec.status === 'running');
    const total = (rec.stages || []).reduce((t, s) => t + (typeof s.ms === 'number' ? s.ms : 0), 0);
    swap(u.parts.head, h('div', {},
      h('h3', {}, title(rec)),
      h('p', { class: 'muted small' }, [`Uploaded ${dayText(rec.created_at)}, ${clockText(rec.created_at)}`, rec.side === 'away' ? 'away' : 'at home',
        rec.size_bytes ? `${(rec.size_bytes / 1048576).toFixed(1)} MB` : null, rec.source === 'synthetic' ? 'synthetic footage' : null,
        rec.status === 'done' && total ? `processed in ${dur(total)}${S.store === 'azure' ? ' on Azure Container Apps' : ''}` : null].filter(Boolean).join(' · '))),
    h('span', { class: `pf-status ${rec.status}` }, STATUS[rec.status] || rec.status));
    swap(u.parts.pipe, pipeline(rec));
    u.parts.err.textContent = rec.status === 'failed' ? `The job stopped: ${rec.error || 'no reason given'}` : '';
    u.parts.err.hidden = rec.status !== 'failed';
    if (rec.status === 'needs_review') loadQuestions(u); else { swap(u.ask); u.ask.hidden = true; u.questions = null; }
    if (rec.status === 'done' && rec.links) loadResults(u); else if (rec.status !== 'done') { swap(u.parts.res); u.results = null; }
    if (before && before !== rec.status && rec.status === 'done') reloadProfile();
  }

  function order() {
    const runs = [...S.uploads.values()].sort((a, b) => b.rec.created_at - a.rec.created_at);
    for (const u of runs) { $('runs').append(u.el); $('asks').append(u.ask); }
    $('noUploads').hidden = runs.length > 0;
    const live = runs.filter((u) => u.rec.status === 'queued' || u.rec.status === 'running').length;
    $('uploadsSub').textContent = runs.length ? `${runs.length} upload${runs.length === 1 ? '' : 's'}${live ? ` · ${live} in progress, updating live` : ''}` : '';
  }

  function paintQuestionsState() {
    const waiting = [...S.uploads.values()].some((u) => !u.ask.hidden);
    $('noQuestions').hidden = waiting;
    const answered = latest().flatMap((r) => (r.notes || []).filter((n) => /answer/i.test(n)).map((n) => `${title(r)}: ${plain(n)}`));
    $('answered').hidden = !answered.length;
    swap($('answered'), answered.flatMap((t, i) => (i ? [h('br'), t] : [t])));
  }

  async function refresh() {
    if (!S.gid || S.busy) return;
    S.busy = true;
    const gid = S.gid;
    try {
      const out = await R.api(`/api/player/uploads?global_id=${enc(gid)}`);
      if (gid !== S.gid) return;
      if (out.max_mb) { S.maxMb = out.max_mb; $('maxMb').textContent = String(out.max_mb); }
      S.store = out.store || null;
      $('netError').hidden = true;
      for (const rec of out.uploads || []) upsert(rec);
      order();
      paintNeeds(); paintActivity(); paintQuestionsState();
    } catch (e) {
      if (offline(e)) netError('Regista cannot be reached; progress will update when it is back.', refresh);
    } finally {
      S.busy = false;
      const active = [...S.uploads.values()].some((u) => u.rec.status === 'queued' || u.rec.status === 'running');
      if (S.gid === gid && $('finder').hidden) schedule(active ? POLL_MS : IDLE_MS);
    }
  }

  // The working agent's clock, counted from the record's last change (the worker writes it when a stage starts).
  function tick() {
    const now = Date.now() / 1000;
    for (const u of S.uploads.values()) {
      if (u.rec.status !== 'queued' && u.rec.status !== 'running') continue;
      const tm = u.el.querySelector('.pf-steps li.running .pf-sms');
      if (!tm) continue;
      const secs = Math.max(0, Math.round(now - (u.rec.updated_at || now)));
      tm.textContent = `${u.rec.status === 'queued' ? 'waiting' : 'working'} ${R.fmtTime(secs)}`;
    }
  }

  function schedule(ms) {
    clearTimeout(S.timer);
    S.timer = setTimeout(() => { if (document.hidden) schedule(ms); else refresh(); }, ms);
  }

  // ------------------------------------------------------------------------------------------------ "Is this you?"
  async function loadQuestions(u) {
    if (u.questions && u.questions.upload === u.rec.updated_at) return;
    u.questions = { upload: u.rec.updated_at };
    u.ask.hidden = false;
    paintQuestionsState();
    let q;
    try { q = await R.api(`/api/player/uploads/${enc(u.rec.upload_id)}/questions`); } catch (e) {
      swap(u.ask, h('h3', {}, title(u.rec)), h('p', { class: 'bad' }, `The questions could not be loaded: ${errText(e)}`));
      return;
    }
    const items = q.items || [];
    const status = h('p', { class: 'small', role: 'status', 'aria-live': 'polite' });
    const go = h('button', { type: 'button' }, items.length ? 'Send my answers' : 'Finish');
    const skip = items.length ? h('button', { type: 'button', class: 'alt' }, 'Skip: keep the agents’ calls') : null;
    const cards = items.map((it) => question(u, it));
    const submit = async (all) => {
      if (!canWrite()) {
        status.className = 'small warn'; status.textContent = 'Answering needs the admin key: paste it in “Add a match” above.';
        renderKey(); toggleAdd(true); return;
      }
      const answers = all ? [...u.answers.entries()].map(([item_id, is_me]) => ({ item_id, is_me })) : [];
      if (all && items.length && !answers.length) { status.className = 'small warn'; status.textContent = 'Answer at least one, or skip.'; return; }
      go.disabled = true; if (skip) skip.disabled = true;
      status.className = 'small';
      status.textContent = answers.length ? 'Applying your answers: identity is corrected, then possession, events and your clips are worked out again…'
        : 'Finishing the match…';
      try {
        const out = await R.api(`/api/player/uploads/${enc(u.rec.upload_id)}/answers`, { method: 'POST', body: { answers }, auth: true });
        status.className = 'small ok';
        status.textContent = answers.length ? `Thanks: ${out.answers} answer${out.answers === 1 ? '' : 's'} applied.` : 'Done.';
        upsert(out.upload); order(); paintNeeds(); paintActivity(); paintQuestionsState();
      } catch (e) {
        if (e.status === 401) { R.key.clear(); renderKey(); }
        status.className = 'small bad'; status.textContent = errText(e);
        go.disabled = false; if (skip) skip.disabled = false;
      }
    };
    go.addEventListener('click', () => submit(true));
    if (skip) skip.addEventListener('click', () => submit(false));
    swap(u.ask,
      h('h3', {}, items.length ? `Is this you, ${firstName()}?` : 'Nothing to ask you'),
      h('p', { class: 'muted small' }, `${title(u.rec)}, uploaded ${dayText(u.rec.created_at)}. `,
        items.length ? `The identity agent is unsure about ${items.length === 1 ? 'one call' : `${items.length} calls`} that may be you. `
          + 'Your answers fix this match now and teach the kit-number reader for the next one.'
          : 'The identity agent had questions about other players, none about you. Finish to add the match to your profile.'),
      items.length ? h('ul', { class: 'qs' }, cards) : null,
      h('div', { class: 'ask-actions' }, go, skip, status));
  }

  function question(u, it) {
    const card = h('li', { class: 'q' });
    const pic = h('div', { class: 'pic' });
    if (it.image_url && /^\/api\/player\/uploads\/[A-Za-z0-9_]+\/crops\/[A-Za-z0-9_.\-]+\.jpg$/.test(it.image_url)) {
      pic.append(h('img', { src: it.image_url, alt: `The ${it.kind === 'track' ? 'player' : it.segment_kind || 'replay'} Regista is asking about, at ${R.fmtTime(it.t || 0)}`, loading: 'lazy' }));
    } else pic.append(`No picture · ${R.fmtTime(it.t || 0)}`);
    const yes = h('button', { type: 'button', class: 'y', 'aria-pressed': 'false' }, 'Yes, me');
    const no = h('button', { type: 'button', class: 'n', 'aria-pressed': 'false' }, 'No');
    const pick = (v) => {
      u.answers.set(it.item_id, v);
      yes.setAttribute('aria-pressed', String(v)); no.setAttribute('aria-pressed', String(!v));
      card.classList.toggle('yes', v); card.classList.toggle('no', !v);
    };
    if (u.answers.has(it.item_id)) setTimeout(() => pick(u.answers.get(it.item_id)));
    yes.addEventListener('click', () => pick(true));
    no.addEventListener('click', () => pick(false));
    const span = it.t0 !== undefined && it.t1 !== undefined ? `${R.fmtTime(it.t0)}–${R.fmtTime(it.t1)}` : R.fmtTime(it.t || 0);
    const pct = typeof it.p === 'number' ? Math.round(it.p * 100) : null;
    const hint = it.regista_thinks_its_you ? 'Regista named you here, but is not sure.'
      : it.kind === 'track' ? `${it.named_as ? `Regista named this player ${it.named_as}` : 'Regista left this player unnamed'}${pct !== null ? `; ${pct}% of its kit-number reads say you.` : '.'}`
      : (pct !== null ? `Regista’s estimate that you are in it: ${pct}%.` : 'Regista is not sure.');
    card.append(pic, h('div', { class: 'qb' },
      h('p', { class: 'qq' }, it.question || 'Is this you?'),
      h('p', { class: 'qm' }, `${it.kind === 'track' ? 'Main camera' : (it.segment_kind ? R.reasonLabel(`${it.segment_kind}_appearance`) : 'Replay')} · ${span}. ${hint}`),
      h('div', { class: 'yn', role: 'group', 'aria-label': it.question || 'Is this you?' }, yes, no)));
    return card;
  }

  // ------------------------------------------------------------------------------------------------ a finished upload
  async function loadResults(u) {
    const key = `${u.rec.upload_id}:${u.rec.updated_at}`;
    if (u.results === key) return;
    u.results = key;
    const links = u.rec.links || {};
    let clips = [];
    try { clips = await R.api(links.clips); } catch (e) {
      swap(u.parts.res, h('p', { class: 'bad' }, `The moments could not be loaded: ${errText(e)}`));
      return;
    }
    const pid = u.rec.match && u.rec.match.player_id;
    const mine = (clips || []).filter((c) => !pid || c.player_id === pid);
    const best = mine.slice(0, 6);
    const href = (v) => local(v) || '#';
    swap(u.parts.res,
      h('div', { class: 'pf-bar' }, h('h3', {}, `Your moments: ${mine.length}`),
        h('span', { class: 'badge filmed' }, 'Filmed by you · cut from video')),
      h('p', { class: 'muted small' }, mine.length ? `Best first. ${mine.length > best.length ? `The best ${best.length} are here, and every one is on Home. ` : 'Each one opens on Home too. '}The match now counts in your profile.`
        : 'Regista found no moments of you on the ball in this footage. The match still counts in your profile.'),
      best.length ? h('div', { class: 'moments' }, best.map(moment)) : null,
      h('div', { class: 'links' },
        h('a', { class: 'pf-btn', href: href(links.clip_view) }, 'Open the match on Home'),
        h('a', { class: 'btn alt', href: '#profile' }, 'See your updated profile')));
    const mid = u.rec.match && u.rec.match.match_id;
    if (mid && pid) {
      const box = h('section', { class: 'recap', 'aria-label': 'Your match recap' }, h('p', { class: 'muted small' }, 'Writing your match recap…'));
      u.parts.res.append(box);
      loadRecap(box, mid, pid, href(links.clip_view));
    }
  }

  // "Your match recap": the match told from the player's side (GET /recap, the Instant engine). Every sentence opens its
  // moment on Home; the recap reel plays here.
  async function loadRecap(box, mid, pid, clipView) {
    let r;
    try { r = await R.api(`/api/matches/${enc(mid)}/recap?player=${enc(pid)}`); } catch (e) {
      swap(box, h('p', { class: 'muted small' }, `The recap could not be written: ${errText(e)}`));
      return;
    }
    const at = (s) => (s.cites || []).find((c) => c.clip_id);
    const sentence = (s) => {
      const c = at(s);
      return c ? h('a', { href: `/?match=${enc(mid)}&player=${enc(c.player_id || pid)}&clip=${enc(c.clip_id)}` }, s.text) : h('span', {}, s.text);
    };
    const reelUrl = typeof r.reel_url === 'string' && r.reel_url.startsWith('/api/matches/') ? r.reel_url : null;
    const video = h('video', { controls: true, playsinline: true, preload: 'none' });
    video.hidden = true;
    const play = reelUrl ? h('button', { type: 'button', class: 'alt' }, `Play your recap reel (${(r.reel || []).length})`) : null;
    if (play) {
      play.addEventListener('click', () => {
        play.textContent = 'Cutting the reel… the first view takes a little while';
        play.disabled = true;
        video.src = reelUrl;
        video.hidden = false;
        video.addEventListener('playing', () => play.remove(), { once: true });
        video.addEventListener('error', () => { play.textContent = 'The reel could not be played. Try again.'; play.disabled = false; }, { once: true });
        video.play().catch(() => {});
      });
    }
    swap(box,
      h('h3', {}, 'Your match recap'),
      h('p', { class: 'headline' }, r.headline || ''),
      (r.paragraphs || []).map((p) => h('p', {}, (p.sentences || []).flatMap((s, i) => (i ? [' ', sentence(s)] : [sentence(s)])))),
      h('p', { class: 'muted small' }, 'Written by Regista from the match events. Each sentence opens its moment on Home.'),
      video,
      h('div', { class: 'links' }, play, h('a', { class: 'btn alt', href: clipView === '#' ? '#' : `${clipView}&recap=1` }, 'Read it on Home')));
  }

  function moment(c) {
    const lb = c.label || {};
    const video = h('video', { controls: true, playsinline: true, preload: 'none' });
    video.hidden = true;
    const wait = h('span', { class: 'wait' }, `${R.reasonLabel(c.reason)} · ${R.fmtTime(c.t)}`);
    const cover = h('button', { type: 'button', class: 'cover', 'aria-label': `Play: ${lb.title || 'moment'}` },
      h('span', { class: 'play', 'aria-hidden': 'true' }, '▶'), wait);
    cover.addEventListener('click', () => {
      if (!clipUrl(c.video_url)) return;
      wait.textContent = 'Cutting the clip…';
      video.src = c.video_url;
      video.hidden = false;
      video.addEventListener('playing', () => cover.remove(), { once: true });
      video.addEventListener('error', () => { wait.textContent = 'The clip could not be played. Try again.'; video.hidden = true; }, { once: true });
      video.play().catch(() => {});
    });
    const tags = (lb.tags || []).filter((t) => t !== 'touch' && t !== 'on_ball_main').slice(0, 4);
    return h('article', { class: 'card' },
      h('div', { class: 'thumb' }, video, cover),
      h('div', { class: 'body' },
        h('p', { class: 't' }, lb.title || 'A moment'),
        h('p', { class: 'm' }, `${R.fmtTime(c.t)} · ${R.reasonLabel(c.reason)}${typeof lb.watchability === 'number' ? ` · worth watching ${Math.round(lb.watchability * 100)}%` : ''}`),
        tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'tag' }, R.tagLabel(t)))) : null));
  }

  // ------------------------------------------------------------------------------------------------ All your matches
  function paintMatches() {
    const P = S.P;
    const vs = PV.vsLineFor(P);
    const rows = [...(P.matches || [])].reverse();
    swap($('allMatches'), rows.length ? rows.map((m) => h('li', {}, h('a', { href: PV.matchHref(m) },
      h('span', { class: 'pf-round' }, PV.roundName(m)),
      h('span', { class: 'pf-vs' }, vs(m), m.source === 'upload' ? h('span', { class: 'badge filmed' }, 'Filmed by you') : null),
      h('span', { class: 'pf-mm muted' }, m.home ? 'At home' : 'Away'),
      h('span', { class: 'pf-open' }, 'Open on Home')))) : h('li', { class: 'muted' }, 'No matches yet.'));
  }

  // ------------------------------------------------------------------------------------------------ Messages
  const scoutOf = (c) => demo.SCOUTS[c.scout] || { name: 'A scout', initials: '?', role: 'Scout', club: '', verified: false };
  const openConvo = () => demo.forPlayer(S.gid).find((c) => c.id === S.open) || null;
  function readOpen() {
    const c = openConvo();
    if (c && c.unread && c.unread.player && S.nav && S.nav.section() === 'messages') { demo.markRead(c.id, 'player'); counts(); paintNeeds(); }
  }

  // A moment as a clip card that plays where it is (match AND clip id: clip ids repeat across matches).
  function clipCard(r, onRemove) {
    const P = S.P;
    const match = (P.matches || []).find((m) => m.match_id === r.match_id);
    const src = clipUrl(r.video_url);
    const video = h('video', { controls: true, playsinline: true, preload: 'none', 'aria-label': PV.short(r.title) });
    if (src) video.src = src;
    return h('div', { class: 'mx-clip' }, video,
      h('div', { class: 'mx-cinfo' },
        h('span', { class: `reason${r.reason === 'replay_appearance' ? ' replay' : ''}` }, [R.reasonLabel(r.reason), PV.roundName(match || { round: r.round })].filter(Boolean).join(' · ')),
        h('b', {}, PV.short(r.title)),
        h('span', { class: 'muted small' }, match ? PV.vsLineFor(P)(match) : r.opponent ? `v ${r.opponent}` : '')),
      onRemove ? h('button', { type: 'button', class: 'link mx-unpick', 'aria-label': `Remove ${PV.short(r.title)}`, onclick: onRemove }, '×') : null);
  }

  function paintMessages() {
    if (!S.P) return;
    const list = demo.forPlayer(S.gid);
    $('mxNote').textContent = demo.NOTE;
    if (!list.length) {
      swap($('mxList'), h('li', { class: 'mx-empty muted small' }, 'No messages yet. When a scout writes to you, the conversation starts here.'));
      $('mxThread').hidden = true;
      $('mx').classList.remove('reading');
      counts();
      return;
    }
    $('mxThread').hidden = false;
    if (!list.find((c) => c.id === S.open)) S.open = list[0].id;
    swap($('mxList'), list.map((c) => {
      const s = scoutOf(c);
      const last = c.msgs[c.msgs.length - 1];
      const n = (c.unread && c.unread.player) || 0;
      const lastText = c.blocked ? 'Blocked' : last ? `${last.from === 'player' ? 'You: ' : ''}${last.text || 'Sent a moment'}` : 'No messages yet';
      return h('li', {}, h('button', { type: 'button', class: `mx-item${c.id === S.open ? ' on' : ''}${c.blocked ? ' blocked' : ''}`,
        'aria-current': c.id === S.open ? 'true' : null, onclick: () => {
          S.open = c.id; S.draft = [];
          $('mx').classList.add('reading');   // on a phone the thread replaces the list
          readOpen(); paintMessages();
          $('mxText').focus({ preventScroll: true });
        } },
        h('span', { class: 'mx-av', 'aria-hidden': 'true' }, s.initials),
        h('span', { class: 'mx-who' }, h('b', {}, s.name, s.verified ? h('span', { class: 'mx-ver', title: 'Verified scout' }, ' ✓') : null),
          h('span', { class: 'muted small' }, `${s.role}, ${s.club}`), h('span', { class: 'mx-last' }, lastText)),
        h('span', { class: 'mx-meta' }, h('span', { class: 'muted small' }, last ? demo.whenText(last.at, true) : ''),
          n && !c.blocked && !c.muted ? h('span', { class: 'count', 'aria-label': `${n} unread` }, String(n)) : null,
          c.muted ? h('span', { class: 'muted small' }, 'Muted') : null)));
    }));
    const c = openConvo();
    const s = scoutOf(c);
    swap($('mxHead'),
      h('div', {}, h('b', {}, s.name), s.verified ? h('span', { class: 'mx-ver' }, ' ✓ Verified scout') : null,
        h('p', { class: 'muted small' }, `${s.role}, ${s.club}`)),
      h('div', { class: 'mx-acts' },
        h('button', { type: 'button', class: 'alt', 'aria-pressed': String(!!c.muted), onclick: () => { demo.setMuted(c.id, !c.muted); paintMessages(); counts(); paintNeeds(); } }, c.muted ? 'Unmute' : 'Mute'),
        h('button', { type: 'button', class: 'alt', 'aria-pressed': String(!!c.blocked), onclick: () => { demo.setBlocked(c.id, !c.blocked); paintMessages(); counts(); paintNeeds(); paintActivity(); } }, c.blocked ? 'Unblock' : 'Block')));
    swap($('mxMsgs'), c.msgs.map((m) => h('li', { class: `mx-msg ${m.from === 'player' ? 'me' : 'them'}` },
      h('div', { class: 'mx-bubble' }, m.text ? h('p', {}, m.text) : null, (m.clips || []).map((r) => clipCard(r))),
      h('span', { class: 'muted small' }, `${m.from === 'player' ? 'You' : s.name.split(' ')[0]} · ${demo.whenText(m.at)}`))),
      c.blocked ? h('li', { class: 'mx-blocked muted small' }, 'You blocked this scout. They cannot message you.') : null);
    $('mxCompose').hidden = !!c.blocked;
    $('mxAttach').hidden = !!c.blocked;
    if (c.blocked) { $('mxPicker').hidden = true; S.draft = []; }
    paintDraft();
    paintPicker();
    const box = $('mxMsgs'); box.scrollTop = box.scrollHeight;
    counts();
  }

  function paintDraft() {
    swap($('mxDraft'), S.draft.map((r) => clipCard(r, () => { S.draft = S.draft.filter((x) => demo.refKey(x) !== demo.refKey(r)); paintDraft(); paintPicker(); })));
    $('mxDraft').hidden = !S.draft.length;
  }

  // The player's own best moments, to attach to a reply.
  function paintPicker() {
    const P = S.P;
    const picked = new Set(S.draft.map(demo.refKey));
    const vs = PV.vsLineFor(P);
    const mine = PV.best(P, 8);
    swap($('mxPickList'), mine.length ? mine.map((m) => {
      const match = (P.matches || []).find((x) => x.match_id === m.match_id);
      const box = h('input', { type: 'checkbox', value: PV.key(m) });
      box.checked = picked.has(PV.key(m));
      box.addEventListener('change', () => {
        const r = demo.ref(m, match);
        S.draft = box.checked ? [...S.draft, r] : S.draft.filter((x) => demo.refKey(x) !== demo.refKey(r));
        paintDraft();
      });
      return h('li', {}, h('label', {}, box, h('span', {}, h('b', {}, PV.short(m.title)), ' ',
        h('span', { class: 'muted small' }, `${PV.roundName(match || m)} · ${vs(match)}`))));
    }) : h('li', { class: 'muted small' }, 'No moments of you yet.'));
  }

  function sendReply(e) {
    e.preventDefault();
    const c = openConvo();
    if (!c || c.blocked) return;
    const text = $('mxText').value.trim();
    if (!text && !S.draft.length) return;
    if (!demo.send(c.id, 'player', text, S.draft)) return;
    S.draft = []; $('mxText').value = '';
    $('mxPicker').hidden = true; $('mxAttach').setAttribute('aria-expanded', 'false');
    paintMessages(); paintActivity();
    $('mxText').focus();
  }

  // ------------------------------------------------------------------------------------------------ Team
  function paintTeam() {
    const P = S.P, d = me();
    $('tmName').value = d.name;
    $('tmPos').value = d.position;
    $('tmKit').value = String(d.kit_number);
    const foot = document.querySelector(`input[name="tmfoot"][value="${d.foot || 'Right'}"]`);
    if (foot) foot.checked = true;
    $('tmHeight').value = d.height ? String(d.height) : '';
    $('tmBio').value = d.bio;
    $('tmUndo').hidden = !d.edited;
    const club = S.clubs.find((c) => c.club_id === P.club_id) || { name: P.club, kit: P.kit, squad: [] };
    const kit = club.kit || P.kit || {};
    $('tmCrest').style.background = `linear-gradient(135deg, ${colour(kit.primary, '#444')} 50%, ${colour(kit.secondary, '#fff')} 50%)`;
    $('tmClubHead').textContent = club.name;
    const table = (S.season && S.season.table) || [];
    const row = table.find((t) => t.club_id === P.club_id);
    $('tmClubLine').textContent = [S.season ? `${S.season.league} ${S.season.season}` : null, club.ground || null,
      row ? `${PV.ordinal(row.position)} in the table, ${row.points} points` : null].filter(Boolean).join(' · ');
    const num = (p) => (p.global_id === S.gid ? d.kit_number : p.kit_number);
    const squad = [...(club.squad || [])].sort((a, b) => num(a) - num(b));
    swap($('tmSquad'), squad.length ? squad.map((p) => {
      const you = p.global_id === S.gid;
      return h('li', { class: you ? 'you' : null },
        h('span', { class: 'tm-num' }, you ? d.kit_number : p.kit_number),
        h('span', {}, you ? d.name : p.name, you ? h('span', { class: 'badge filmed' }, 'You') : null),
        h('span', { class: 'muted small' }, `${POS[you ? d.position : p.position] || p.position}${p.starter ? '' : ' · sub'}`));
    }) : h('li', { class: 'muted' }, 'The squad could not be loaded.'));
    const results = ((S.season && S.season.rounds) || []).flatMap((rd) => rd.matches.filter((m) => m.home === P.club_id || m.away === P.club_id))
      .sort((a, b) => b.round - a.round);
    swap($('tmResults'), results.length ? results.map((m) => {
      const sc = m.score || {};
      const us = m.home === P.club_id ? sc.t_home : sc.t_away, them = m.home === P.club_id ? sc.t_away : sc.t_home;
      const res = us > them ? 'W' : us < them ? 'L' : 'D';
      return h('li', {}, h('span', { class: `tm-res r-${res}`, title: { W: 'Won', L: 'Lost', D: 'Drawn' }[res] },
        res, h('span', { class: 'sr' }, ` (${{ W: 'won', L: 'lost', D: 'drawn' }[res]})`)),
        h('span', { class: 'pf-round' }, `Round ${m.round}`), h('span', {}, `${m.home_name} ${sc.t_home ?? ''}–${sc.t_away ?? ''} ${m.away_name}`));
    }) : h('li', { class: 'muted' }, 'No results yet.'));
    const th = (t, full) => h('th', { scope: 'col', title: full || null }, full ? h('abbr', { title: full }, t) : t);
    swap($('tmTable'),
      h('caption', { class: 'sr' }, 'The league table'),
      h('thead', {}, h('tr', {}, th('#', 'Position'), th('Club'), th('P', 'Played'), th('W', 'Won'), th('D', 'Drawn'), th('L', 'Lost'), th('GD', 'Goal difference'), th('Pts', 'Points'))),
      h('tbody', {}, table.map((t) => h('tr', { class: t.club_id === P.club_id ? 'you' : null },
        h('td', {}, t.position), h('td', {}, t.club), h('td', {}, t.played), h('td', {}, t.won), h('td', {}, t.drawn), h('td', {}, t.lost),
        h('td', {}, `${t.goal_difference > 0 ? '+' : ''}${t.goal_difference}`), h('td', {}, h('b', {}, t.points))))));
  }

  function saveDetails(e) {
    e.preventDefault();
    const name = $('tmName').value.trim();
    const kit = Number($('tmKit').value);
    const height = $('tmHeight').value.trim() ? Number($('tmHeight').value) : null;
    const note = $('tmNote');
    if (!name) { note.className = 'small pf-addnote bad'; note.textContent = 'Your name cannot be empty.'; return; }
    if (!Number.isInteger(kit) || kit < 1 || kit > 99) { note.className = 'small pf-addnote bad'; note.textContent = 'The kit number is a whole number from 1 to 99.'; return; }
    if (height !== null && !(height >= 140 && height <= 220)) { note.className = 'small pf-addnote bad'; note.textContent = 'Height is in centimetres, from 140 to 220.'; return; }
    demo.saveDetails(S.gid, { name: name.slice(0, 60), position: $('tmPos').value, kit_number: kit,
      foot: (document.querySelector('input[name="tmfoot"]:checked') || {}).value || 'Right', height, bio: $('tmBio').value.trim().slice(0, 280) });
    paintIdentity(); paintTeam();
    note.className = 'small pf-addnote ok';
    note.textContent = 'Saved. Your dashboard and your profile show the new details.';
  }

  // ------------------------------------------------------------------------------------------------ Settings
  const emailFor = (st) => (st.emails && st.emails[S.gid]) || (S.gid === demo.PLAYER ? st.email
    : `${me().name.toLowerCase().normalize('NFD').replace(/[^a-z ]/g, '').trim().replace(/\s+/g, '.')}@regista-league.example`);

  function paintSettings() {
    const st = demo.settings('player') || {};
    $('stEmail').textContent = emailFor(st);
    for (const [name, v] of [['stsee', st.see], ['stmsg', st.message]]) {
      for (const r of document.querySelectorAll(`input[name="${name}"]`)) r.checked = r.value === v;
    }
    for (const box of document.querySelectorAll('[data-panel="settings"] input[data-set]')) {
      const [group, k] = box.dataset.set.split('.');
      box.checked = !!(st[group] && st[group][k]);
    }
    $('stLocal').textContent = demo.NOTE;
    paintKeyRow();
  }
  function paintKeyRow() {
    const has = !!R.key.get();
    $('stKey').textContent = S.writes === 'open' ? 'This server takes uploads and answers without a key.'
      : S.writes === 'read-only' || S.writes === 'locked' ? 'This deployment takes no uploads.'
      : has ? 'Kept in this tab for uploads and answers.' : 'Not set. Add a match asks for it when you upload.';
    $('stKeyBtn').hidden = !has;
  }
  function saveSetting(e) {
    const t = e.target;
    const st = demo.settings('player') || {};
    if (t.name === 'stsee') st.see = t.value;
    else if (t.name === 'stmsg') st.message = t.value;
    else if (t.dataset.set) { const [group, k] = t.dataset.set.split('.'); st[group] = { ...(st[group] || {}), [k]: t.checked }; }
    else return;
    demo.saveSettings('player', st);
    $('stNote').textContent = 'Saved.';
  }
  function editEmail(open) {
    $('stEmailForm').hidden = !open;
    $('stEmailBtn').setAttribute('aria-expanded', String(open));
    if (open) { $('stEmailInput').value = $('stEmail').textContent; $('stEmailInput').focus(); }
  }

  // "Reset this demo": every message, edit and setting back to how the demo starts.
  function resetDemo() {
    demo.reset();
    S.open = null; S.draft = [];
    $('mx').classList.remove('reading');
    paintIdentity(); paintTeam(); paintMessages(); paintSettings(); paintNeeds(); paintActivity(); counts();
    $('tmNote').textContent = '';
    $('stNote').textContent = 'The demo is back to how it started.';
  }

  // ------------------------------------------------------------------------------------------------ start
  function wire() {
    setInterval(tick, 1000);
    $('change').addEventListener('click', () => ($('finder').hidden ? openFinder() : closeFinder()));
    $('finderClose').addEventListener('click', () => closeFinder());
    $('missingPick').addEventListener('click', () => openFinder());
    $('findForm').addEventListener('submit', (e) => { e.preventDefault(); search($('find').value.trim()); });
    $('addBtn').addEventListener('click', () => toggleAdd($('addBox').hidden));
    $('addCancel').addEventListener('click', () => { toggleAdd(false); $('addBtn').focus(); });
    $('uploadForm').addEventListener('submit', upload);
    $('mxCompose').addEventListener('submit', sendReply);
    $('mxAttach').addEventListener('click', () => {
      const p = $('mxPicker'); p.hidden = !p.hidden;
      $('mxAttach').setAttribute('aria-expanded', String(!p.hidden));
    });
    $('mxBack').addEventListener('click', () => { $('mx').classList.remove('reading'); });
    // The Overview's best moment renders on its first request: say so while it is cut.
    const ov = $('ovVideo'), wait = $('ovWait');
    ov.addEventListener('play', () => { if (ov.readyState < 3) { wait.className = 'pf-loading'; wait.textContent = 'Cutting the clip… the first view takes a moment'; wait.hidden = false; } });
    ov.addEventListener('playing', () => { wait.hidden = true; });
    ov.addEventListener('error', () => { wait.className = 'pf-loading err'; wait.textContent = 'The clip could not be played. Try again.'; wait.hidden = false; });
    $('tmForm').addEventListener('submit', saveDetails);
    $('tmUndo').addEventListener('click', () => {
      demo.saveDetails(S.gid, null);
      paintIdentity(); paintTeam();
      $('tmNote').className = 'small pf-addnote'; $('tmNote').textContent = 'Back to your details in the league.';
    });
    document.querySelector('[data-panel="settings"]').addEventListener('change', saveSetting);
    $('stEmailBtn').addEventListener('click', () => editEmail($('stEmailForm').hidden));
    $('stEmailCancel').addEventListener('click', () => { editEmail(false); $('stEmailBtn').focus(); });
    $('stEmailForm').addEventListener('submit', (e) => {
      e.preventDefault();
      const v = $('stEmailInput').value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { $('stNote').textContent = 'That does not look like an email address.'; return; }
      const st = demo.settings('player') || {};
      st.emails = { ...(st.emails || {}), [S.gid]: v.slice(0, 120) };
      demo.saveSettings('player', st);
      editEmail(false); paintSettings();
      $('stNote').textContent = 'Saved.';
      $('stEmailBtn').focus();
    });
    $('stKeyBtn').addEventListener('click', () => { R.key.clear(); renderKey(); $('stNote').textContent = 'The admin key is forgotten in this tab.'; });
    $('stOut').addEventListener('click', () => {
      R.key.clear(); renderKey();
      $('stNote').textContent = 'Signed out: this tab no longer holds the admin key.';
    });
    $('stReset').addEventListener('click', resetDemo);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && S.gid && $('finder').hidden) schedule(50); });
    // Another tab of this browser changed the shared store (a scout replied from /scout, a reset): redraw what reads it.
    R.store.watch((k) => {
      if (!S.P) return;
      if (k === null || k === 'conversations') { paintMessages(); paintNeeds(); paintActivity(); counts(); }
      if (k === null || k === 'details') { paintIdentity(); paintTeam(); }
      if (k === null || k === 'settings.player') paintSettings();
    });
  }

  async function start() {
    $('main').classList.add('me-wait');
    try {
      const [health, season] = await Promise.all([R.api('/api/health'), R.api('/api/season')]);
      S.writes = health.writes;
      S.season = season;
      S.clubs = season.clubs || [];
    } catch (e) {
      $('loading').hidden = true;
      if (offline(e)) return netError('Regista cannot be reached. Check the connection.', start);
      return netError(`Regista could not load the league: ${errText(e)}`, start);
    }
    const wanted = new URLSearchParams(location.search).get('player');
    const gid = wanted && GID_RE.test(wanted) ? wanted : demo.PLAYER;
    const slow = setTimeout(() => { $('loading').textContent = 'Loading your dashboard… The league is built on first use, which can take about half a minute.'; }, 3000);
    let ok = await choose(gid, { quiet: true });
    if (!ok && gid !== demo.PLAYER && $('netError').hidden) {
      // A player the league does not know: open the default player and say so in Switch player.
      ok = await choose(demo.PLAYER, { quiet: true });
      if (ok) openFinder(`No player with that id has played in the Regista League. Pick one, or stay with ${me().name}. The league's forwards:`);
    }
    clearTimeout(slow);
    $('loading').hidden = true;
    if (!ok && $('netError').hidden) { showMissing('No player with this id has played in the Regista League.'); openFinder(); }
  }

  wire();
  S.nav = R.sections({ fallback: 'overview', onChange: onSection });
  start();
})();
