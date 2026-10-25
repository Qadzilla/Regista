// The Scout dashboard (/scout): Maya Lindqvist, chief scout at Fairhaven FC (a synthetic persona, like the league).
// Eight sections, one per hash (Regista.sections, shared/regista.js): #overview, #find, #terminal (terminal.js), #shortlist,
// #reports, #messages, #team, #settings. A section's hash may name a player: /scout#messages/<id> opens (or starts) the
// conversation with them, #shortlist/<id> puts them on the shortlist and in compare, #reports/<id> opens their draft. The
// scout bar on /players/{id} links here that way (it writes first, then goes; the hash alone is enough too).
//
// LIVE, from the API: the league (/api/season), every player's card (/api/players: the filters are the server's),
// the Scout agent (POST /api/scout/ask, Data Search or Foundry), compare (/api/compare) and the moments behind every
// number (/api/players/{id}, read when a number, a report or an upload card needs them).
// PER VISITOR, in this browser only (Regista.demo, shared/demo.js): messages, shortlist stages and notes, compare picks,
// reports, Fairhaven's needs, settings. Nothing of that is sent to the server.
//
// Plain script on window.Regista. No inline scripts, handlers or style attributes in markup: the page runs under a
// Content Security Policy, so colours and bar widths are set through element.style after rendering (paint()).
(function () {
  const R = window.Regista;
  // Everything that reaches innerHTML from the API or from this browser's store goes through esc(): names, clubs,
  // moment titles, notes and messages are data, never markup.
  const esc = R.esc;
  const demo = R.demo;
  const PV = R.profileView;   // the shared profile renderer's helpers (shirts, percentile words, moment keys, links)
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const LIMIT = 200;            // what /api/players accepts; the league has fewer players than this
  const COMPARE_MAX = demo.COMPARE_MAX;   // what /api/compare accepts
  const ME = demo.SCOUTS[demo.SCOUT];
  const CLUB_ID = ME.club_id;
  const GID = /^pl_[a-z0-9_]{1,40}$/;

  const POSITIONS = PV.POS;
  const GROUP = PV.GROUP;
  // The headline rates a card shows first for each position (keys of the card's `headline`), before the sort fills in.
  const BY_POSITION = {
    GK: ['saves', 'passes_completed', 'recoveries'],
    DF: ['interceptions', 'tackles_won', 'recoveries', 'passes_completed'],
    MF: ['recoveries', 'tackles_won', 'key_passes', 'passes_completed'],
    FW: ['goals', 'shots', 'assists', 'take_ons_won'],
  };
  const CARD_RATES = 3;
  const EXAMPLES = ['Forwards with the most goals', 'Midfielders who win the ball back', 'Who wins the most take-ons?',
                    'Defenders with the most interceptions'];

  const state = {
    season: null,
    stats: [],                  // the stat catalogue from the API: {key, label, kind: per90|ratio, headline}
    players: [],                // the cards on screen in Find players
    all: new Map(),             // global id -> every league player's card (names, clubs and numbers everywhere else)
    filters: { position: '', club: '', q: '', min_minutes: 0, sort: 'minutes' },
    known: new Map(),           // global id -> every card seen (the list and the Scout agent's replies), for the stars
    seq: 0,                     // drops replies to older player requests
    ready: false,               // the league and the players are loaded
    profiles: new Map(),        // global id -> Promise of GET /api/players/{id}
    openConvo: null,            // conversation id on screen in Messages
    openReport: null,           // report id on screen in Reports
    picker: null,               // section index whose "Insert a moment" list is open
    section: '',
  };

  // ------------------------------------------------------------------ small helpers

  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';
  const offline = (e) => !(e instanceof R.ApiError);
  const OFFLINE = 'Can\'t reach Regista right now. Check your connection and try again.';
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const statOf = (key) => state.stats.find(s => s.key === key);
  const labelOf = (key) => key === 'minutes' ? 'Minutes played' : key === 'name' ? 'Name' : (statOf(key)?.label || R.tagLabel(key));
  const HEX = /^#[0-9a-f]{6}$/i;
  const VIDEO = /^\/api\/[A-Za-z0-9_./?=&%-]+$/;     // video urls from the API are relative; anything else is not played
  const fmtRate = (v) => (v === null || v === undefined) ? '–' : Number(v).toFixed(2);
  const fmtRatio = (v) => (v === null || v === undefined) ? '–' : `${Math.round(Number(v) * 100)}%`;
  const fmtMinutes = (m) => `${Math.round(Number(m) || 0)} minutes`;
  const player = (gid) => state.all.get(gid) || state.known.get(gid) || null;
  const nameOf = (gid, fallback) => player(gid)?.name || fallback || 'A player';
  const firstName = (name) => String(name || '').split(' ')[0];
  const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const posLine = (p) => p ? `${POSITIONS[p.position] || p.position} · ${p.club}` : '';
  const shirt = (p, size = 40) => PV.shirtSvg(p.kit, p.kit_number, p.position, size);
  const headOf = (p, k) => (p && p.headline && p.headline[k]) || null;
  const stageBadge = (stage) => stage ? `<span class="sc-stage s-${esc(stage)}">${esc(stage)}</span>` : '';
  const verdictBadge = (v) => v ? `<span class="sc-verdict v-${esc(String(v).replace(/ /g, ''))}">${esc(v)}</span>` : '';
  // "Round 2 · v Calder Town" for a moment reference (messages, reports).
  const refWhere = (r) => [r.round !== null && r.round !== undefined ? `Round ${r.round}` : 'Friendly', r.opponent ? `v ${r.opponent}` : '']
    .filter(Boolean).join(' · ');

  // Swatches carry data-c (fill) and optionally data-c2 (edge); bars carry data-w (percent). Applied after each render
  // through element.style, which the Content Security Policy allows.
  function paint(root) {
    for (const el of root.querySelectorAll('[data-c]')) {
      const c = el.dataset.c;
      if (!HEX.test(c)) continue;
      el.style.background = c;
      if (HEX.test(el.dataset.c2 || '')) el.style.borderColor = el.dataset.c2;
    }
    for (const el of root.querySelectorAll('[data-w]')) el.style.width = `${Math.max(3, Math.min(100, Number(el.dataset.w) || 0))}%`;
  }

  // A player's full profile (moments, evidence, matches), read once per page.
  function profile(gid) {
    if (!state.profiles.has(gid)) {
      const p = R.api(`/api/players/${enc(gid)}`);
      p.catch(() => state.profiles.delete(gid));
      state.profiles.set(gid, p);
    }
    return state.profiles.get(gid);
  }

  // One video plays at a time across the page; leaving a section pauses its videos.
  document.addEventListener('play', (e) => {
    for (const v of document.querySelectorAll('video')) if (v !== e.target && !v.paused) v.pause();
  }, true);
  function playInto(video, url, now, text) {
    if (!video || !VIDEO.test(String(url || ''))) { if (now) now.textContent = 'This moment has no video.'; return; }
    if (video.getAttribute('src') !== url) video.src = url;
    if (now) now.textContent = text || '';
    video.play().catch(() => { if (now) now.textContent = `${text ? `${text} · ` : ''}Cutting the clip… press play in a moment.`; });
  }
  // A clip that fails to render says so under its player.
  watchVideoErrors();
  function watchVideoErrors() {
    document.addEventListener('error', (e) => {
      const v = e.target;
      if (!(v instanceof HTMLVideoElement) || !v.dataset.now) return;
      const now = $(v.dataset.now);
      if (now) now.textContent = 'This moment could not be played just now. Try again in a moment.';
    }, true);
  }

  // ------------------------------------------------------------------ errors with a way out

  let retry = null;
  function netError(e, again) {
    $('netErrorText').textContent = offline(e) ? OFFLINE : detail(e);
    retry = again;
    $('netError').hidden = false;
  }
  function clearNetError() { $('netError').hidden = true; retry = null; }
  $('netRetry').addEventListener('click', () => { const f = retry; clearNetError(); if (f) f(); });

  // ------------------------------------------------------------------ the left panel's sections

  // sections() calls show() at once, before it returns: show() must not need `nav` yet.
  let nav = null;
  nav = R.sections({ fallback: 'overview', onChange: show });

  function show(section, rest) {
    for (const v of document.querySelectorAll('main video')) if (!v.closest(`[data-panel="${section}"]`)) v.pause();
    const moved = section !== state.section;
    state.section = section;
    counts();
    if (!state.ready) return;
    const gid = GID.test(rest[0] || '') ? rest[0] : '';
    if (section === 'overview') paintOverview();
    if (section === 'find') { /* the cards are kept current as filters change */ }
    if (section === 'shortlist') openShortlist(gid);
    if (section === 'reports') openReports(gid);
    if (section === 'messages') openMessages(gid);
    if (section === 'team') paintTeam();
    if (section === 'settings') paintSettings();
    if (moved && !gid) window.scrollTo(0, 0);
  }
  // A section's hash that named a player has done its job: keep the section, drop the player (a reload does not redo it).
  function settle(section) {
    try { history.replaceState(null, '', `${location.pathname}${location.search}#${section}`); } catch (e) {}
  }
  function counts() { if (nav) nav.count('messages', demo.unread('scout', demo.SCOUT)); }

  // ------------------------------------------------------------------ the league

  async function loadSeason() {
    try {
      const s = await R.api('/api/season');
      state.season = s;
      state.stats = s.stats || [];
      renderLeague(s);
      fillFilters(s);
      return true;
    } catch (e) {
      $('tableBody').innerHTML = '<tr><td colspan="8" class="muted">The league is not available.</td></tr>';
      netError(e, start);
      return false;
    }
  }

  function renderLeague(s) {
    const rounds = (s.rounds || []).length;
    const matches = (s.rounds || []).reduce((n, r) => n + (r.matches || []).length, 0);
    $('leagueHead').textContent = `${s.league} ${s.season}`;
    $('leagueSub').textContent = `${plural((s.clubs || []).length, 'club')} · ${plural(rounds, 'round')} · ${plural(matches, 'match', 'matches')}`;
    if (s.note) $('footNote').textContent = s.note;
    $('tableBody').innerHTML = (s.table || []).map(r => {
      const gd = r.goal_difference > 0 ? `+${r.goal_difference}` : String(r.goal_difference);
      return `<tr${r.club_id === CLUB_ID ? ' class="ours"' : ''}>
        <td>${esc(r.position)}</td>
        <th scope="row" class="club-col"><button type="button" class="club" data-club="${esc(r.club_id)}"
            aria-label="Show ${esc(r.club)} players"><span class="kit" data-c="${esc(r.kit?.primary)}" data-c2="${esc(r.kit?.secondary)}"></span>
          <span class="full">${esc(r.club)}</span><span class="short" aria-hidden="true">${esc(r.short_name)}</span></button></th>
        <td>${esc(r.played)}</td><td>${esc(r.won)}</td><td>${esc(r.drawn)}</td><td>${esc(r.lost)}</td>
        <td>${esc(gd)}</td><td class="pts">${esc(r.points)}</td></tr>`;
    }).join('');
    paint($('tableBody'));
    syncClubButtons();
  }
  function syncClubButtons() {
    for (const b of $('tableBody').querySelectorAll('button.club')) b.setAttribute('aria-pressed', String(b.dataset.club === state.filters.club));
  }

  $('tableBody').addEventListener('click', (ev) => {
    const b = ev.target.closest('button.club');
    if (!b) return;
    const club = state.filters.club === b.dataset.club ? '' : b.dataset.club;
    $('fClub').value = club;
    if (club) moreFilters(true);
    setFilter({ club });
    $('filterForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  // ------------------------------------------------------------------ Find players: filters

  function fillFilters(s) {
    $('fClub').innerHTML = '<option value="">All clubs</option>' +
      (s.clubs || []).map(c => `<option value="${esc(c.club_id)}">${esc(c.name)}</option>`).join('');
    const group = (kind, title) => {
      const opts = state.stats.filter(st => st.kind === kind).map(st => `<option value="${esc(st.key)}">${esc(st.label)}</option>`).join('');
      return opts ? `<optgroup label="${esc(title)}">${opts}</optgroup>` : '';
    };
    $('fSort').innerHTML = '<option value="minutes">Minutes played</option><option value="name">Name</option>' +
      group('per90', 'Per 90 minutes') + group('ratio', 'Share that worked');
    readUrl();
  }

  // The filters live in the address's query too (beside the #find hash), so a search can be shared or reloaded.
  function readUrl() {
    const u = new URLSearchParams(location.search);
    const f = state.filters;
    if (POSITIONS[u.get('position')]) f.position = u.get('position');
    if (u.get('club') && [...$('fClub').options].some(o => o.value === u.get('club'))) f.club = u.get('club');
    if (u.get('q')) f.q = u.get('q').slice(0, 80);
    const mm = Number(u.get('min_minutes'));
    if (Number.isFinite(mm) && mm > 0) f.min_minutes = Math.min(10000, mm);
    if (u.get('sort') && [...$('fSort').options].some(o => o.value === u.get('sort'))) f.sort = u.get('sort');
    $('fPosition').value = f.position; $('fClub').value = f.club; $('fName').value = f.q;
    $('fMinutes').value = String(f.min_minutes); $('fSort').value = f.sort;
    if (f.club || f.min_minutes) moreFilters(true);
  }

  // Club and Minimum minutes sit behind "More filters", under the sandbox's three (Name or club, Position, Sort by).
  // Closed, the link counts the filters it hides that are on ("More filters (1)"), so a hidden Club or minimum is never silent.
  function moreFilters(open) {
    $('fMoreBox').hidden = !open;
    $('fMore').setAttribute('aria-expanded', String(open));
    syncMore();
  }
  function syncMore() {
    const f = state.filters;
    const on = (f.club ? 1 : 0) + (f.min_minutes ? 1 : 0);
    $('fMore').textContent = !$('fMoreBox').hidden ? 'Fewer filters' : on ? `More filters (${on})` : 'More filters';
  }
  // The club's name as the Club select shows it.
  function clubName(id) {
    const o = [...$('fClub').options].find(x => x.value === id);
    return o ? o.textContent : '';
  }
  $('fMore').addEventListener('click', () => {
    const open = $('fMoreBox').hidden;
    moreFilters(open);
    if (open) $('fClub').focus();
  });

  function writeUrl() {
    const f = state.filters;
    const u = new URLSearchParams();
    if (f.position) u.set('position', f.position);
    if (f.club) u.set('club', f.club);
    if (f.q) u.set('q', f.q);
    if (f.min_minutes) u.set('min_minutes', String(f.min_minutes));
    if (f.sort !== 'minutes') u.set('sort', f.sort);
    const qs = u.toString();
    try { history.replaceState(null, '', `/scout${qs ? `?${qs}` : ''}${location.hash || '#find'}`); } catch (e) {}
  }

  function setFilter(patch) {
    Object.assign(state.filters, patch);
    writeUrl();
    syncClubButtons();
    syncMore();
    loadPlayers();
  }

  $('fPosition').addEventListener('change', () => setFilter({ position: $('fPosition').value }));
  $('fClub').addEventListener('change', () => setFilter({ club: $('fClub').value }));
  $('fSort').addEventListener('change', () => setFilter({ sort: $('fSort').value }));
  let typing = null;
  $('fName').addEventListener('input', () => {
    clearTimeout(typing);
    typing = setTimeout(() => setFilter({ q: $('fName').value.trim().slice(0, 80) }), 250);
  });
  $('fMinutes').addEventListener('input', () => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      const v = Number($('fMinutes').value);
      setFilter({ min_minutes: Number.isFinite(v) && v > 0 ? Math.min(10000, v) : 0 });
    }, 300);
  });
  $('filterForm').addEventListener('submit', (ev) => ev.preventDefault());
  $('fReset').addEventListener('click', () => {
    Object.assign(state.filters, { position: '', club: '', q: '', min_minutes: 0, sort: 'minutes' });
    $('fPosition').value = ''; $('fClub').value = ''; $('fName').value = ''; $('fMinutes').value = '0'; $('fSort').value = 'minutes';
    writeUrl();
    syncClubButtons();
    syncMore();
    loadPlayers();
  });

  // ------------------------------------------------------------------ Find players: cards

  // Every league player once (sorted by name): names, clubs and numbers for the shortlist, messages, reports and needs.
  async function loadAll() {
    const out = await R.api(`/api/players?sort=name&limit=${LIMIT}`);
    state.all = new Map((out.players || []).map(p => [p.global_id, p]));
    for (const p of state.all.values()) state.known.set(p.global_id, p);
    if (out.stats) state.stats = out.stats;
  }

  async function loadPlayers() {
    const f = state.filters;
    const u = new URLSearchParams({ sort: f.sort, limit: String(LIMIT) });
    if (f.position) u.set('position', f.position);
    if (f.club) u.set('club', f.club);
    if (f.q) u.set('q', f.q);
    if (f.min_minutes) u.set('min_minutes', String(f.min_minutes));
    const mine = ++state.seq;
    $('cards').setAttribute('aria-busy', 'true');
    try {
      const out = await R.api(`/api/players?${u}`);
      if (mine !== state.seq) return;
      clearNetError();
      state.players = out.players || [];
      for (const p of state.players) state.known.set(p.global_id, p);
      if (out.stats) state.stats = out.stats;
      renderCards();
    } catch (e) {
      if (mine !== state.seq) return;
      netError(e, loadPlayers);
    } finally {
      if (mine === state.seq) $('cards').setAttribute('aria-busy', 'false');
    }
  }

  // Three rates for a card: the sort first when the card carries it, then the position's headline rates.
  function picks(p) {
    const sort = state.filters.sort;
    const keys = [];
    const st = statOf(sort);
    if (st && (st.kind === 'ratio' ? p.ratios?.[sort] !== undefined : p.headline?.[sort])) keys.push(sort);
    for (const k of BY_POSITION[p.position] || BY_POSITION.MF) if (!keys.includes(k)) keys.push(k);
    return keys.slice(0, CARD_RATES);
  }

  function rateRow(p, key) {
    const st = statOf(key);
    if (st?.kind === 'ratio') {
      const v = p.ratios?.[key];
      return `<li><span class="lbl"><b>${esc(fmtRatio(v))}</b> ${esc(st.label.toLowerCase())}</span>
        <span class="pct muted">of attempts</span></li>`;
    }
    const h = headOf(p, key);
    if (!h) return '';
    const pc = h.percentile;
    const said = PV.pctText(pc, p.position);
    return `<li title="${esc(said)}"><span class="lbl"><b>${esc(fmtRate(h.per90))}</b> ${esc(h.label.toLowerCase())} per 90</span>
      <span class="bar" aria-hidden="true"><i data-w="${esc(pc ?? 0)}"></i></span>
      <span class="pct muted">${esc(said)}</span></li>`;
  }

  // A player's card: the name's link covers the whole card (to /players/{id}); the star sits above it.
  function cardHtml(p, extra = '') {
    const sl = demo.shortlist()[p.global_id];
    const on = !!sl;
    const best = p.best_moment?.title;
    return `<article class="sc-pcard" data-id="${esc(p.global_id)}">
      <div class="sc-chead"><span class="sc-shirt" aria-hidden="true">${shirt(p)}</span>
        <span class="who"><a class="name" href="/players/${enc(p.global_id)}">${esc(p.name)}</a>
          <span class="muted small">${esc(POSITIONS[p.position] || p.position)} · ${esc(p.club)} · #${esc(p.kit_number)}</span>
          <span class="sc-stagebox">${on ? stageBadge(sl.stage) : ''}</span></span>
        <button type="button" class="star" data-star="${esc(p.global_id)}" aria-pressed="${on}"
          aria-label="${on ? 'Remove' : 'Add'} ${esc(p.name)} ${on ? 'from' : 'to'} the shortlist">${on ? '★' : '☆'}</button>
      </div>
      ${extra}
      <ul class="rates">${picks(p).map(k => rateRow(p, k)).join('')}</ul>
      <p class="muted small sc-cfoot">${esc(plural(p.appearances, 'match', 'matches'))} · ${esc(fmtMinutes(p.minutes))}</p>
      ${best ? `<p class="best"><span class="muted">Best moment</span> ${esc(PV.short(best))}</p>` : '<p class="best muted">No labelled moments yet.</p>'}
    </article>`;
  }

  function renderCards() {
    const f = state.filters;
    const n = state.players.length;
    const sortWords = f.sort === 'name' ? 'by name' : f.sort === 'minutes' ? 'by minutes played' : `by ${labelOf(f.sort).toLowerCase()}`;
    // The line names the Club and minimum when they are on, since both can sit behind a closed "More filters".
    const club = f.club ? clubName(f.club) : '';
    const scope = `${club ? ` at ${club}` : ''}${f.min_minutes ? ` with at least ${fmtMinutes(f.min_minutes)}` : ''}`;
    $('resultsSub').textContent = n ? `${plural(n, 'player')}${scope}, sorted ${sortWords}${statOf(f.sort)?.kind === 'per90' ? ' per 90 minutes' : ''}` : '';
    const st = statOf(f.sort);
    if (st && st.kind === 'per90' && !st.headline) {
      $('resultsSub').textContent += `. Cards do not show ${st.label.toLowerCase()}; each player's profile does.`;
    }
    $('cards').innerHTML = state.players.map(p => cardHtml(p)).join('');
    paint($('cards'));
    $('empty').hidden = n > 0;
    if (!n) {
      const tries = [];
      if (f.q) tries.push('another name');
      if (f.position) tries.push('another position');
      if (club) tries.push(`a club other than ${club}`);
      if (f.min_minutes) tries.push(`a minimum below ${fmtMinutes(f.min_minutes)}`);
      const said = tries.length > 1 ? `${tries.slice(0, -1).join(', ')} or ${tries[tries.length - 1]}` : tries[0];
      $('empty').textContent = `No players match these filters.${said ? ` Try ${said}.` : ''}`;
    }
  }

  // A star adds a player to the shortlist (Watching) or takes them off it.
  function toggleShortlist(gid) {
    if (demo.onShortlist(gid)) demo.setStage(gid, '');
    else demo.setStage(gid, 'Watching');
    syncStars();
  }
  // Every star and stage badge on the page (the list and the Scout agent's reply) shows whether its player is shortlisted.
  function syncStars() {
    const sl = demo.shortlist();
    for (const b of document.querySelectorAll('button.star')) {
      const p = state.known.get(b.dataset.star);
      const on = !!sl[b.dataset.star];
      b.setAttribute('aria-pressed', String(on));
      b.textContent = on ? '★' : '☆';
      if (p) b.setAttribute('aria-label', `${on ? 'Remove' : 'Add'} ${p.name} ${on ? 'from' : 'to'} the shortlist`);
      const box = b.closest('.sc-pcard')?.querySelector('.sc-stagebox');
      if (box) box.innerHTML = on ? stageBadge(sl[b.dataset.star].stage) : '';
    }
  }
  for (const box of ['cards', 'scoutAnswer']) {
    $(box).addEventListener('click', (ev) => {
      const b = ev.target.closest('button.star');
      if (b && GID.test(b.dataset.star)) toggleShortlist(b.dataset.star);
    });
  }

  // ------------------------------------------------------------------ Find players: the Scout agent

  $('scExamples').innerHTML = EXAMPLES.map(q => `<button type="button" class="chip" data-ask="${esc(q)}">${esc(q)}</button>`).join('');
  $('scExamples').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-ask]');
    if (!b) return;
    $('scoutAsk').value = b.dataset.ask;
    $('scoutAskForm').requestSubmit();
  });

  const SERVERS = { 'regista-mcp': 'Regista MCP server', 'azure-mcp': 'Azure MCP Server' };
  const msText = (v) => v === null || v === undefined ? '–' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : v < 1 ? '<1 ms' : `${Math.round(v)} ms`;
  // The answer's steps in plain words (each line is escaped where it is shown).
  function plainSteps(json, trace) {
    const lastModel = trace.map(x => x.kind).lastIndexOf('model');
    return trace.map((s, i) => {
      if (s.kind === 'step') {
        return ({ 'scout.parse': 'Read the question', 'scout.search_players': 'Ranked the league\'s players',
                  'scout.get_profile': 'Read the player\'s profile', 'scout.compare_players': 'Compared the players' })[s.name]
          || 'Worked on the question';
      }
      if (s.kind === 'agent') return 'Handed the question to the Foundry Scout agent';
      if (s.kind === 'model') return i === lastModel ? `Microsoft Foundry (${s.name}) wrote the reply` : `Microsoft Foundry (${s.name}) chose what to look up`;
      if (s.kind === 'tool') return `Used ${s.name}${s.server === 'regista-mcp' ? ' through Regista\'s MCP server' : s.server === 'azure-mcp' ? ' through the Azure MCP Server' : ''}`;
      return 'Another step';
    });
  }
  function howAnswered(json) {
    const by = typeof json?.answered_by === 'string' ? json.answered_by : 'rules';
    const trace = Array.isArray(json?.trace) ? json.trace.filter(s => s && typeof s === 'object') : [];
    if (!trace.length) return '';
    const plain = plainSteps(json, trace);
    const short = by.startsWith('foundry') ? `Microsoft Foundry (${by.replace(/^foundry:/, '')})` : 'Data Search, no AI model';
    return `<details class="how"><summary>How the Scout agent answered · ${esc(short)} · ${esc(plural(plain.length, 'step'))}</summary>
      <ol class="plain">${plain.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      <details class="tech"><summary>Details: step names and times</summary>
        <div class="times">${trace.map(s => `${esc(s.kind)} · ${esc(s.name)}${s.server ? ` · ${esc(SERVERS[s.server] || s.server)}` : ''} · ${esc(msText(s.ms))}`).join('<br>')}</div>
        ${json.trace_note ? `<p class="small muted">${esc(json.trace_note)}</p>` : ''}</details></details>`;
  }

  // Renders a reply from the Scout agent (POST /api/scout/ask) into #scoutAnswer: the reply, how the question was
  // understood, who answered and with which tools, the steps it took, then the players as ordinary cards (stars join the
  // shortlist; each card says the number the answer was about).
  function renderScoutAnswer(json) {
    const box = $('scoutAnswer');
    const reply = json && typeof (json.reply ?? json.answer) === 'string' ? (json.reply ?? json.answer) : '';
    const players = Array.isArray(json?.players) ? json.players.filter(p => p && GID.test(p.global_id || '')) : [];
    for (const p of players) state.known.set(p.global_id, p);
    const by = typeof json?.answered_by === 'string' ? json.answered_by : '';
    const tools = Array.isArray(json?.tools_used) ? json.tools_used : [];
    const byLine = by.startsWith('foundry')
      ? `Answered by Microsoft Foundry${tools.length ? `, using ${tools.map(esc).join(', ')}` : ''}.`
      : (by && by !== 'rules' ? `Answered by Regista's rules (${esc(by.replace(/^rules\s*/, '').replace(/^\(|\)$/g, ''))}).` : "Answered by Regista's rules.");
    const checked = Array.isArray(json?.checked) && json.checked.length
      ? `<p class="muted small">Numbers in this reply that no tool returned: ${json.checked.map(esc).join(', ')}.</p>` : '';
    const about = (p) => {
      const s = p.stat;
      if (!s || typeof s !== 'object' || !s.label) return '';
      // The rank is among the player's position (regista.season.scout.rank_in_position): say so.
      const rank = s.rank && s.of_players
        ? ` · ${s.tied_with ? 'joint ' : ''}${PV.ordinal(s.rank)} of ${s.of_players} ${GROUP[p.position] || 'players'}` : '';
      return `<p class="sc-about small">${esc(s.label)}: ${esc(s.display || '')}${esc(rank)}</p>`;
    };
    box.innerHTML = (reply ? `<p class="sc-reply">${esc(reply)}</p>` : '') +
      (json?.understood ? `<p class="muted small">Understood: ${esc(json.understood)}</p>` : '') +
      `<p class="muted small">${byLine}</p>${checked}` +
      (players.length ? `<div class="sc-cards">${players.map(p => cardHtml(p, about(p))).join('')}</div>` : '') +
      howAnswered(json);
    paint(box);
  }
  window.RegistaScout = { renderScoutAnswer };

  $('scoutAskForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const q = $('scoutAsk').value.trim();
    if (!q) return;
    const engine = document.querySelector('input[name="scoutEngine"]:checked')?.value || 'rules';
    const go = $('scoutAskGo');
    go.disabled = true;
    $('scoutAnswer').innerHTML = `<p class="muted">${engine === 'foundry' ? 'Asking the Foundry Scout agent… (a few seconds)' : 'Ranking the players…'}</p>`;
    try {
      renderScoutAnswer(await R.api('/api/scout/ask', { method: 'POST', body: { q, engine } }));
    } catch (e) {
      const why = e && e.status === 429 ? 'Too many questions just now; try again in a minute.'
        : e && e.status === 422 ? 'Ask in under 200 characters.'
        : 'Regista could not answer just now. Check your connection and try again.';
      $('scoutAnswer').innerHTML = `<p class="muted">${esc(why)}</p>`;
    } finally {
      go.disabled = false;
    }
  });

  // ------------------------------------------------------------------ Overview

  // The stat a player is best at among the ones their position leads with (what a shortlist item shows).
  function strongest(p) {
    const keys = (BY_POSITION[p.position] || BY_POSITION.MF).filter(k => headOf(p, k));
    return keys.reduce((a, k) => ((headOf(p, k).percentile ?? -1) > (headOf(p, a).percentile ?? -1) ? k : a), keys[0]);
  }
  const fits = (n) => [...state.all.values()]
    .filter(p => p.position === n.pos && p.club_id !== CLUB_ID && (headOf(p, n.stat)?.percentile ?? -1) >= Number(n.pct))
    .sort((a, b) => headOf(b, n.stat).per90 - headOf(a, n.stat).per90);

  // Uploads by shortlisted players: their profiles' matches from outside the league (footage they filmed).
  async function shortlistUploads() {
    const gids = Object.keys(demo.shortlist()).filter(g => state.all.has(g));
    const out = [];
    await Promise.all(gids.map(async (gid) => {
      try {
        const P = await profile(gid);
        for (const m of P.matches || []) if (m.source === 'upload') out.push({ gid, m });
      } catch (e) { /* a profile that does not load adds no card */ }
    }));
    return out.sort((a, b) => String(b.m.date || '').localeCompare(String(a.m.date || '')));
  }

  let uploadsCache = [];
  function paintOverview() {
    const cards = [];
    for (const c of demo.forScout(demo.SCOUT)) {
      if (!(c.unread && c.unread.scout)) continue;
      const last = [...c.msgs].reverse().find(m => m.from === 'player');
      cards.push({ href: `/scout#messages/${enc(c.player)}`, head: `${nameOf(c.player, c.player_name)} replied`,
                   sub: last ? (last.text || 'Sent a moment') : '', cta: 'Read', hot: true });
    }
    for (const { gid, m } of uploadsCache) {
      cards.push({ href: `/players/${enc(gid)}`, head: `${nameOf(gid)} added a match`,
                   sub: `A friendly v ${m.opponent || 'another club'}, filmed by the player and cut by Regista`, cta: 'Watch' });
    }
    for (const r of demo.reports().filter(x => x.draft)) {
      cards.push({ href: `/scout#reports/${enc(r.gid)}`, head: `Your report on ${nameOf(r.gid)} is a draft`,
                   sub: 'Finish it with a verdict: Sign, Keep watching or Pass.', cta: 'Finish it' });
    }
    const needs = demo.needs();
    const fitCount = new Set(needs.flatMap(n => fits(n).map(p => p.global_id))).size;
    cards.push({ href: '/scout#team', head: `${plural(fitCount, 'player fits', 'players fit')} what Fairhaven needs`,
                 sub: needs.map(n => String(n.title || '').replace(/^An? /, '')).join(' · ') || 'Add what the club is looking for.', cta: 'See them' });
    $('ovNeeds').innerHTML = cards.map(c => `<a class="ov-need${c.hot ? ' hot' : ''}" href="${esc(c.href)}">
      <span class="ov-nh">${esc(c.head)}</span><span class="ov-ns">${esc(c.sub)}</span><span class="ov-cta">${esc(c.cta)} &rarr;</span></a>`).join('');

    const sl = demo.shortlist();
    $('ovStages').innerHTML = demo.STAGES.map(st => {
      const names = Object.keys(sl).filter(g => sl[g].stage === st).map(g => nameOf(g));
      return `<a class="ov-tile sc-st" href="/scout#shortlist">${stageBadge(st)}<span class="pf-n">${esc(names.length)}</span>
        <span class="pf-rate">${esc(names.join(', ') || 'Nobody yet')}</span></a>`;
    }).join('');

    // Recent activity, from what this browser holds (messages, reports, the shortlist) and the players' uploads.
    const act = [];
    for (const c of demo.forScout(demo.SCOUT)) {
      const last = c.msgs[c.msgs.length - 1];
      if (!last) continue;
      const who = nameOf(c.player, c.player_name);
      act.push({ k: 'msg', at: last.at, href: `/scout#messages/${enc(c.player)}`,
                 text: last.from === 'player' ? `${who} replied` : `You wrote to ${who}` });
    }
    for (const r of demo.reports()) {
      act.push({ k: 'match', at: r.at, href: `/scout#reports`,
                 text: r.draft ? `You started a report on ${nameOf(r.gid)}` : `You wrote a report on ${nameOf(r.gid)}${r.verdict ? `: ${r.verdict}` : ''}` });
    }
    for (const [gid, v] of Object.entries(sl)) {
      act.push({ k: 'match', at: v.at, href: '/scout#shortlist', text: `${nameOf(gid)} is on your shortlist: ${v.stage}` });
    }
    for (const { gid, m } of uploadsCache) {
      const at = Date.parse(`${m.date}T12:00:00Z`);
      if (isFinite(at)) act.push({ k: 'up', at, href: `/players/${enc(gid)}`, text: `${nameOf(gid)} added a friendly v ${m.opponent || 'another club'}` });
    }
    act.sort((a, b) => (b.at || 0) - (a.at || 0));
    $('ovActivity').innerHTML = act.slice(0, 6).map(a => `<li><span class="ov-dot k-${esc(a.k)}" aria-hidden="true"></span>
      <a href="${esc(a.href)}">${esc(a.text)}</a><span class="muted small">${esc(demo.whenText(a.at, true))}</span></li>`).join('')
      || '<li class="muted small">Nothing yet.</li>';
  }
  function refreshUploads() {
    shortlistUploads().then((list) => {
      const changed = JSON.stringify(list) !== JSON.stringify(uploadsCache);
      uploadsCache = list;
      if (changed && state.section === 'overview') paintOverview();
    });
  }

  // ------------------------------------------------------------------ Shortlist: stages and compare

  function paintBoard() {
    const sl = demo.shortlist();
    const picked = new Set(demo.compare());
    const ids = Object.keys(sl).filter(g => player(g));
    $('shortEmpty').hidden = ids.length > 0;
    $('scBoard').innerHTML = demo.STAGES.map(st => {
      const here = ids.filter(g => sl[g].stage === st);
      return `<section class="sc-col panel" aria-label="${esc(st)}"><h2>${stageBadge(st)} <span class="muted small">${esc(here.length)}</span></h2>
        ${here.map(gid => {
          const p = player(gid), k = strongest(p), h = headOf(p, k);
          const on = picked.has(gid);
          const full = !on && picked.size >= COMPARE_MAX;
          return `<article class="sc-item" data-item="${esc(gid)}" tabindex="-1">
            <a href="/players/${enc(gid)}"><b>${esc(p.name)}</b></a>
            <span class="muted small">${esc(posLine(p))}</span>
            ${h ? `<span class="small">${esc(fmtRate(h.per90))} ${esc(h.label.toLowerCase())} per 90 · ${esc(PV.pctText(h.percentile, p.position))}</span>` : ''}
            ${sl[gid].note ? `<p class="sc-inote">${esc(sl[gid].note)}</p>` : ''}
            <div class="sc-iacts"><label class="sc-cmp"><input type="checkbox" data-cmp="${esc(gid)}"${on ? ' checked' : ''}${full ? ' disabled' : ''}> Compare</label>
              <label><span class="sr">Move ${esc(p.name)} to</span><select data-move="${esc(gid)}">${demo.STAGES.map(s2 =>
                `<option value="${esc(s2)}"${s2 === st ? ' selected' : ''}>${esc(s2)}</option>`).join('')}<option value="">Remove</option></select></label></div></article>`;
        }).join('') || '<p class="muted small">Nobody here yet.</p>'}</section>`;
    }).join('');
    const n = [...picked].filter(g => sl[g]).length;
    $('compareGo').disabled = n < 2;
    $('compareGo').textContent = n ? `Compare (${n})` : 'Compare';
    $('compareHint').textContent = n >= 2 ? `${n} picked. Compare holds up to three.`
      : n === 1 ? 'Tick one more to compare.' : 'Tick two or three players to compare them.';
  }

  function openShortlist(gid) {
    if (gid && player(gid)) {
      if (!demo.onShortlist(gid)) demo.setStage(gid, 'Watching');
      const inIt = demo.compare().includes(gid) || demo.toggleCompare(gid);
      paintBoard();
      if (!inIt) $('compareHint').textContent = `Compare holds three players. Untick one to add ${nameOf(gid)}.`;
      const item = $('scBoard').querySelector(`[data-item="${CSS.escape(gid)}"]`);
      if (item) {
        item.classList.add('flash');
        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
        item.focus({ preventScroll: true });
      }
      settle('shortlist');
      return;
    }
    if (gid) settle('shortlist');
    paintBoard();
  }

  $('scBoard').addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.cmp) {
      const gid = t.dataset.cmp;
      if (t.checked !== demo.compare().includes(gid)) demo.toggleCompare(gid);
      paintBoard();
      const again = $('scBoard').querySelector(`input[data-cmp="${CSS.escape(gid)}"]`);
      if (again) again.focus();
    }
    if (t.dataset.move !== undefined) {
      const gid = t.dataset.move;
      demo.setStage(gid, t.value);
      paintBoard();
      const again = $('scBoard').querySelector(`select[data-move="${CSS.escape(gid)}"]`);
      (again || $('compareGo')).focus();
    }
  });

  async function compare() {
    const sl = demo.shortlist();
    const ids = demo.compare().filter(g => sl[g]).slice(0, COMPARE_MAX);
    if (ids.length < 2) return;
    $('compareGo').disabled = true;
    $('compare').hidden = false;
    $('compareEv').hidden = true;
    $('compareBody').innerHTML = '<p class="muted">Loading…</p>';
    $('compareHead').focus({ preventScroll: true });
    $('compare').scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const out = await R.api(`/api/compare?ids=${ids.map(enc).join(',')}`);
      clearNetError();
      renderCompare(out);
    } catch (e) {
      $('compareBody').innerHTML = `<p class="muted">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
    } finally {
      $('compareGo').disabled = demo.compare().filter(g => demo.shortlist()[g]).length < 2;
    }
  }

  // The sandbox's compact table: each player's position-leading rates, then the same seven for everyone, per 90 minutes.
  const COMPARE_LEAD = { FW: ['goals', 'shots', 'assists'], MF: ['recoveries', 'tackles_won', 'key_passes'],
                         DF: ['interceptions', 'tackles_won', 'recoveries'], GK: ['saves', 'passes_completed', 'recoveries'] };
  const COMPARE_ALL = ['goals', 'assists', 'key_passes', 'take_ons_won', 'tackles_won', 'interceptions', 'recoveries'];

  function renderCompare(out) {
    const ps = out.players || [];
    const keys = [...new Set(ps.flatMap(p => COMPARE_LEAD[p.card.position] || COMPARE_LEAD.FW).concat(COMPARE_ALL))]
      .filter(k => ps.some(p => p.per90 && p.per90[k] !== undefined));
    const head = ps.map(p => {
      const c = p.card;
      return `<th scope="col"><span class="sc-shirt" aria-hidden="true">${shirt(c, 34)}</span>
        <a href="/players/${enc(c.global_id)}">${esc(c.name)}</a>
        <span class="muted small">${esc(POSITIONS[c.position] || c.position)} · ${esc(c.short_name)}</span></th>`;
    }).join('');
    const body = keys.map(k => {
      const label = labelOf(k);
      const vals = ps.map(p => p.per90?.[k]);
      const nums = vals.filter(v => v !== null && v !== undefined).map(Number);
      const top = nums.length ? Math.max(...nums) : null;
      const markBest = top !== null && top > 0 && nums.length > 1;
      const cells = ps.map((p, i) => {
        const v = vals[i];
        const best = markBest && v !== null && v !== undefined && Number(v) === top;
        const txt = fmtRate(v);
        // How the number ranks, in words, on hover and for screen readers ("Higher than 88% of the league's midfielders").
        const said = PV.pctText(p.percentiles?.[k], p.card.position);
        const num = v !== null && v !== undefined
          ? `<button type="button" class="link" data-ev="${esc(p.card.global_id)}|${esc(k)}" title="${esc(said)}"
              aria-label="${esc(`${p.card.name}: ${txt} ${label.toLowerCase()} per 90. ${said}. Show the moments`)}">${esc(txt)}</button>`
          : esc(txt);
        return `<td class="${best ? 'best' : ''}">${num}${best ? '<span class="sr"> (highest)</span>' : ''}</td>`;
      }).join('');
      return `<tr><th scope="row">${esc(label)}</th>${cells}</tr>`;
    }).join('');
    $('compareBody').innerHTML = `<table class="sc-ctable ctable">
      <caption class="sr">${esc(ps.map(p => p.card.name).join(', '))} compared, per 90 minutes</caption>
      <thead><tr><td></td>${head}</tr></thead><tbody>${body}</tbody>
    </table>`;
  }

  // The moments behind one number in the comparison: the player's evidence for that stat, each playing beside the list.
  async function compareEvidence(gid, key) {
    const box = $('compareEv');
    box.hidden = false;
    box.innerHTML = '<p class="muted small">Loading the moments…</p>';
    let P;
    try { P = await profile(gid); } catch (e) {
      box.innerHTML = `<p class="muted small">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
      return;
    }
    const clipOf = new Map((P.moments || []).map(m => [PV.key(m), m]));
    const matchOf = new Map((P.matches || []).map(m => [m.match_id, m]));
    const vs = PV.vsLineFor(P);
    const ev = (P.evidence && P.evidence[key]) || [];
    const total = (P.counts && P.counts[key]) || 0;
    const label = (P.stat_labels && P.stat_labels[key]) || labelOf(key);
    box.innerHTML = `<div class="pf-bar"><h3 tabindex="-1" id="compareEvHead">${esc(P.name)}: ${esc(total)} ${esc(label.toLowerCase())}, verified by Regista</h3>
        <button type="button" class="alt" data-evclose>Close</button></div>
      <div class="sc-cevgrid"><ol>${ev.map(e => {
        const m = matchOf.get(e.match_id), c = e.clip_id && clipOf.get(PV.key(e));
        const where = `${m ? `${PV.roundName(m)} · ${vs(m)} · ` : ''}${R.fmtTime(e.t || 0)}`;
        return c ? `<li><button type="button" class="link" data-cplay="${esc(PV.key(e))}" data-gid="${esc(gid)}">${esc(PV.short(c.title))}</button> <span class="muted small">${esc(where)}</span></li>`
          : `<li><span class="small">${esc(where)}</span> <a class="small" href="${esc(e.clip_id ? PV.clipHref(e.match_id, e.player_id, e.clip_id) : PV.timeHref(e.match_id, e.t || 0))}">${e.clip_id ? 'Watch on Home' : 'Open the match on Home'}</a></li>`;
      }).join('') || '<li class="muted small">None this season.</li>'}</ol>
      <div><div class="pf-screen"><video id="compareVideo" data-now="compareNow" controls playsinline preload="none"></video></div>
        <p class="small muted" id="compareNow">${ev.length ? 'Pick a moment to play it.' : ''}</p></div></div>`;
    $('compareEvHead').focus({ preventScroll: true });
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  $('compareBody').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ev]');
    if (!b) return;
    const [gid, key] = b.dataset.ev.split('|');
    if (GID.test(gid)) compareEvidence(gid, key);
  });
  $('compareEv').addEventListener('click', async (e) => {
    if (e.target.closest('[data-evclose]')) { $('compareEv').hidden = true; $('compareVideo')?.pause(); return; }
    const c = e.target.closest('[data-cplay]');
    if (!c) return;
    try {
      const P = await profile(c.dataset.gid);
      const m = (P.moments || []).find(x => PV.key(x) === c.dataset.cplay);
      if (m) playInto($('compareVideo'), m.video_url, $('compareNow'), `${PV.short(m.title)} · ${PV.roundName(m)}`);
    } catch (err) { /* the list already says what failed */ }
  });
  $('compareGo').addEventListener('click', compare);
  $('compareClose').addEventListener('click', () => {
    $('compare').hidden = true;
    for (const v of $('compare').querySelectorAll('video')) v.pause();
    $('compareGo').focus();
  });

  // ------------------------------------------------------------------ Reports

  const reportTitle = (gid) => {
    const p = player(gid);
    return p ? `${p.name}, ${(POSITIONS[p.position] || p.position).toLowerCase()}, ${p.club}` : '';
  };
  const findReport = (id) => demo.reports().find(r => r.id === id) || null;

  function openReports(gid) {
    if (gid && player(gid)) {
      const r = demo.draftReport(gid, reportTitle(gid));
      if (r) state.openReport = r.id;
      state.picker = null;
      settle('reports');
    }
    paintReports();
  }

  function fillReportFor() {
    const sl = demo.shortlist();
    const order = [...Object.keys(sl).filter(g => state.all.has(g)), ...[...state.all.keys()].filter(g => !sl[g])];
    $('newReportFor').innerHTML = order.map(g => {
      const p = state.all.get(g);
      return `<option value="${esc(g)}">${esc(p.name)} · ${esc(p.club)}${sl[g] ? ` · ${esc(sl[g].stage)}` : ''}</option>`;
    }).join('');
  }

  function citeChip(r, si, ci, draft, section) {
    if (!r || !r.match_id || !r.clip_id) return '';
    const label = `${PV.short(r.title) || 'A moment'}`;
    return `<span class="sc-citewrap"><button type="button" class="sc-cite" data-rplay="${esc(si)}|${esc(ci)}">&#9654; ${esc(label)}
      <span class="muted">${esc(refWhere(r))}</span></button>${draft
        ? `<button type="button" class="sc-uncite" data-runcite="${esc(si)}|${esc(ci)}" aria-label="Remove ${esc(label)} from ${esc(section || 'this section')}">×</button>` : ''}</span>`;
  }

  function paintReports() {
    const list = demo.reports();
    if (!list.some(r => r.id === state.openReport)) state.openReport = list[0] ? list[0].id : null;
    $('reportList').innerHTML = list.map(r => `<li><button type="button" class="sc-ritem${r.id === state.openReport ? ' on' : ''}" data-rep="${esc(r.id)}"
        aria-current="${r.id === state.openReport}"><b>${esc(nameOf(r.gid))}</b><span class="muted small">${esc(demo.whenText(r.at, true))}${r.draft ? ' · Draft' : ''}</span>${verdictBadge(r.verdict)}</button></li>`).join('')
      || '<li class="muted small sc-rnone">No reports yet.</li>';
    const r = findReport(state.openReport);
    const box = $('report');
    if (!r) { box.innerHTML = '<p class="muted">Write a report from any player\'s profile, or with New report.</p>'; return; }
    const title = r.title || reportTitle(r.gid) || nameOf(r.gid);
    const screen = `<div class="pf-screen sc-rscreen"><video id="reportVideo" data-now="reportNow" controls playsinline preload="none"></video></div>
      <p class="small muted" id="reportNow">Pick a moment to play it.</p>`;
    if (r.draft) {
      box.innerHTML = `<div class="pf-bar"><h2>${esc(title)}</h2><a class="small-link" href="/players/${enc(r.gid)}">Open profile</a></div>
        <p class="muted small">Draft · started ${esc(demo.whenText(r.at))} · saved as you type</p>
        ${(r.sections || []).some(s => (s.cites || []).length) ? screen : ''}
        ${(r.sections || []).map((s, i) => `<div class="sc-rsec"><label class="pf-field"><span>${esc(s.name)}</span>
            <textarea rows="3" maxlength="4000" data-rtext="${i}"></textarea></label>
          <div class="sc-cites">${(s.cites || []).map((c, ci) => citeChip(c, i, ci, true, s.name)).join('')}
            <button type="button" class="alt sc-insert" data-rins="${i}" aria-expanded="${state.picker === i}">Insert a moment</button></div>
          <div class="mx-picker" data-rpick="${i}"${state.picker === i ? '' : ' hidden'}><p class="muted small">Loading ${esc(firstName(nameOf(r.gid)))}'s moments…</p></div></div>`).join('')}
        <fieldset class="st-choice sc-rverdict"><legend>Verdict</legend>${demo.VERDICTS.map(v =>
          `<label><input type="radio" name="rverdict" value="${esc(v)}"${r.verdict === v ? ' checked' : ''}><span>${esc(v)}</span></label>`).join('')}</fieldset>
        <div class="pf-addbar"><button type="button" data-rsave>Save report</button><button type="button" class="alt" data-rdiscard>Discard</button></div>
        <p class="small muted" id="reportStatus" role="status"></p>`;
      box.querySelectorAll('[data-rtext]').forEach((t) => { t.value = (r.sections[Number(t.dataset.rtext)] || {}).text || ''; });
      if (state.picker !== null) fillPicker(r, state.picker);
      return;
    }
    box.innerHTML = `<div class="pf-bar"><h2>${esc(title)}</h2>${verdictBadge(r.verdict)}</div>
      <p class="muted small">By ${esc((demo.SCOUTS[r.author] || ME).name)} · ${esc(demo.whenText(r.at, true))} · <a href="/players/${enc(r.gid)}">Open profile</a></p>
      ${screen}
      ${(r.sections || []).map((s, i) => `<div class="sc-rsec"><h3>${esc(s.name)}</h3>${s.text ? `<p>${esc(s.text)}</p>` : '<p class="muted">Nothing written.</p>'}
        <div class="sc-cites">${(s.cites || []).map((c, ci) => citeChip(c, i, ci, false)).join('')}</div></div>`).join('')}
      <div class="pf-addbar"><button type="button" class="alt" data-redit>Edit</button><button type="button" class="alt" data-rdiscard>Delete</button></div>`;
  }

  // The moments a draft can cite: the player's best ones, from their profile.
  async function fillPicker(r, i) {
    const pick = $('report').querySelector(`[data-rpick="${i}"]`);
    if (!pick) return;
    let P;
    try { P = await profile(r.gid); } catch (e) {
      pick.innerHTML = `<p class="muted small">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
      return;
    }
    if (state.picker !== i || state.openReport !== r.id) return;
    const have = new Set(((findReport(r.id)?.sections || [])[i]?.cites || []).map(demo.refKey));
    const matchOf = new Map((P.matches || []).map(m => [m.match_id, m]));
    const ms = PV.best(P, 12);
    pick.innerHTML = ms.length ? `<p class="muted small">${esc(firstName(P.name))}'s best moments. Pick one to cite it here.</p>
      <ol>${ms.map(m => `<li><button type="button" class="link" data-radd="${esc(i)}|${esc(PV.key(m))}"${have.has(PV.key(m)) ? ' disabled' : ''}>${esc(PV.short(m.title))}</button>
        <span class="muted small">${esc(PV.roundName(matchOf.get(m.match_id) || m))}${matchOf.get(m.match_id)?.opponent ? ` · v ${esc(matchOf.get(m.match_id).opponent)}` : ''}</span></li>`).join('')}</ol>`
      : `<p class="muted small">${esc(P.name)} has no moments to cite yet.</p>`;
  }

  let typingReport = null;
  $('report').addEventListener('input', (e) => {
    const t = e.target.closest('[data-rtext]');
    if (!t) return;
    clearTimeout(typingReport);
    const id = state.openReport, i = Number(t.dataset.rtext), text = t.value;
    typingReport = setTimeout(() => {
      const r = findReport(id);
      if (!r || !r.sections[i]) return;
      r.sections[i].text = text.slice(0, 4000);
      demo.saveReport(r);
    }, 300);
  });
  // Text typed in the last moment is kept before anything redraws the report.
  function flushReportText() {
    clearTimeout(typingReport);
    const r = findReport(state.openReport);
    if (!r || !r.draft) return r;
    for (const t of $('report').querySelectorAll('[data-rtext]')) {
      const s = r.sections[Number(t.dataset.rtext)];
      if (s) s.text = t.value.slice(0, 4000);
    }
    demo.saveReport(r);
    return r;
  }
  $('report').addEventListener('change', (e) => {
    if (e.target.name !== 'rverdict') return;
    const r = flushReportText();
    if (r) { r.verdict = e.target.value; demo.saveReport(r); }
  });
  $('report').addEventListener('click', async (e) => {
    const t = e.target;
    const ins = t.closest('[data-rins]'), add = t.closest('[data-radd]'), play = t.closest('[data-rplay]'), un = t.closest('[data-runcite]');
    if (ins) {
      flushReportText();
      const i = Number(ins.dataset.rins);
      state.picker = state.picker === i ? null : i;
      paintReports();
      const again = $('report').querySelector(`[data-rins="${i}"]`);
      if (again) again.focus();
      return;
    }
    if (add) {
      const r = flushReportText();
      const [i, ...rest] = add.dataset.radd.split('|');
      const k = rest.join('|');
      try {
        const P = await profile(r.gid);
        const m = (P.moments || []).find(x => PV.key(x) === k);
        const s = r.sections[Number(i)];
        if (m && s && !(s.cites || []).some(c => demo.refKey(c) === k)) {
          s.cites = [...(s.cites || []), demo.ref(m, (P.matches || []).find(x => x.match_id === m.match_id))];
          demo.saveReport(r);
        }
      } catch (err) { return; }
      state.picker = null;
      paintReports();
      const again = $('report').querySelector(`[data-rins="${i}"]`);
      if (again) again.focus();
      return;
    }
    if (un) {
      const r = flushReportText();
      const [si, ci] = un.dataset.runcite.split('|').map(Number);
      if (r && r.sections[si]) { r.sections[si].cites.splice(ci, 1); demo.saveReport(r); }
      paintReports();
      return;
    }
    if (play) {
      const r = findReport(state.openReport);
      const [si, ci] = play.dataset.rplay.split('|').map(Number);
      const c = r && r.sections[si] && r.sections[si].cites[ci];
      if (c) {
        playInto($('reportVideo'), c.video_url, $('reportNow'), `${PV.short(c.title)} · ${refWhere(c)}`);
        $('reportVideo')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      return;
    }
    if (t.closest('[data-rsave]')) {
      const r = flushReportText();
      if (!r) return;
      r.draft = false;
      r.at = Date.now();
      demo.saveReport(r);
      state.picker = null;
      paintReports();
      return;
    }
    if (t.closest('[data-redit]')) {
      const r = findReport(state.openReport);
      if (r) { r.draft = true; demo.saveReport(r); paintReports(); }
      return;
    }
    if (t.closest('[data-rdiscard]')) {
      demo.dropReport(state.openReport);
      state.openReport = null;
      state.picker = null;
      paintReports();
      $('newReport').focus();
    }
  });
  $('reportList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-rep]');
    if (!b) return;
    flushReportText();
    state.openReport = b.dataset.rep;
    state.picker = null;
    paintReports();
    const again = $('reportList').querySelector(`[data-rep="${CSS.escape(b.dataset.rep)}"]`);
    if (again) again.focus();
  });
  function toggleBox(btn, box, open) {
    box.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  }
  $('newReport').addEventListener('click', () => {
    const open = $('newReportBox').hidden;
    if (open) fillReportFor();
    toggleBox($('newReport'), $('newReportBox'), open);
    if (open) $('newReportFor').focus();
  });
  $('newReportCancel').addEventListener('click', () => { toggleBox($('newReport'), $('newReportBox'), false); $('newReport').focus(); });
  $('newReportStart').addEventListener('click', () => {
    const gid = $('newReportFor').value;
    if (!GID.test(gid)) return;
    flushReportText();
    const r = demo.draftReport(gid, reportTitle(gid));
    if (r) state.openReport = r.id;
    toggleBox($('newReport'), $('newReportBox'), false);
    paintReports();
    const first = $('report').querySelector('[data-rtext]');
    if (first) first.focus();
  });

  // ------------------------------------------------------------------ Messages (one store for both sides)

  function openMessages(gid) {
    if (gid && player(gid)) {
      const c = demo.startConversation(demo.SCOUT, gid, nameOf(gid));
      if (c) {
        state.openConvo = c.id;
        $('mx').classList.add('reading');
        toggleBox($('newMsg'), $('newMsgBox'), false);
        setTimeout(() => { if (!$('mxText').disabled) $('mxText').focus({ preventScroll: true }); }, 50);
      }
    }
    paintMessages();
  }

  function clipCard(r) {
    if (!r || !r.match_id || !r.clip_id || !VIDEO.test(String(r.video_url || ''))) return '';
    return `<div class="mx-clip"><video controls playsinline preload="none" src="${esc(r.video_url)}"></video>
      <div class="mx-cinfo"><span class="reason${r.reason === 'replay_appearance' ? ' replay' : ''}">${esc(R.reasonLabel(r.reason))} · ${esc(refWhere(r))}</span>
        <b>${esc(PV.short(r.title))}</b></div></div>`;
  }

  function paintMessages() {
    const list = demo.forScout(demo.SCOUT);
    if (!list.some(c => c.id === state.openConvo)) state.openConvo = list[0] ? list[0].id : null;
    const open = list.find(c => c.id === state.openConvo) || null;
    // The conversation on screen is read; another browser tab may still add to it (the store's watch redraws).
    // (On a phone the list and the thread take turns: a thread is read only once it is opened.)
    const threadShown = !window.matchMedia('(max-width: 900px)').matches || $('mx').classList.contains('reading');
    if (open && open.unread && open.unread.scout && state.section === 'messages' && threadShown) {
      demo.markRead(open.id, 'scout');
      open.unread.scout = 0;
    }
    counts();
    const sl = demo.shortlist();
    $('mxList').innerHTML = list.map(c => {
      const p = player(c.player), name = nameOf(c.player, c.player_name), last = c.msgs[c.msgs.length - 1];
      const lastText = last ? `${last.from === 'scout' ? 'You: ' : ''}${last.text || 'Sent a moment'}` : 'New conversation';
      const n = (c.unread && c.unread.scout) || 0;
      return `<li><button type="button" class="mx-item${c.id === state.openConvo ? ' on' : ''}${c.blocked ? ' blocked' : ''}" data-convo="${esc(c.id)}"
          aria-current="${c.id === state.openConvo}">
        <span class="mx-av" aria-hidden="true">${esc(initials(name))}</span>
        <span class="mx-who"><b>${esc(name)}</b><span class="muted small">${esc(p ? `${POSITIONS[p.position] || p.position}, ${p.club}` : '')}</span>
          <span class="mx-last">${esc(lastText)}</span></span>
        <span class="mx-meta"><span class="muted small">${esc(last ? demo.whenText(last.at, true) : '')}</span>${n ? `<span class="count">${esc(n)}<span class="sr"> unread</span></span>` : ''}</span></button></li>`;
    }).join('') || '<li class="muted small sc-mxnone">No conversations yet. Start one with New message.</li>';
    if (!open) {
      $('mxHead').innerHTML = '<div><b>No conversation open</b><p class="muted small">Pick one, or start one with New message.</p></div>';
      $('mxMsgs').innerHTML = '';
      $('mxText').disabled = true; $('mxSend').disabled = true;
      fillNewMsgTo();
      return;
    }
    const p = player(open.player), name = nameOf(open.player, open.player_name);
    $('mxHead').innerHTML = `<div><b>${esc(name)}</b><p class="muted small">${esc(p ? `${POSITIONS[p.position] || p.position}, ${p.club}` : '')}${
        sl[open.player] ? ` · on your shortlist: ${esc(sl[open.player].stage)}` : ''}</p></div>
      <div class="mx-acts"><a class="pf-btn sc-smallbtn" href="/players/${enc(open.player)}">Profile</a></div>`;
    $('mxMsgs').innerHTML = open.msgs.map(m => `<li class="mx-msg ${m.from === 'scout' ? 'me' : 'them'}"><div class="mx-bubble">${m.text ? `<p>${esc(m.text)}</p>` : ''}${(m.clips || []).map(clipCard).join('')}</div>
        <span class="muted small">${esc(m.from === 'scout' ? 'You' : firstName(name))} · ${esc(demo.whenText(m.at))}</span></li>`).join('')
      || '<li class="muted small mx-blocked">Say hello: players see who you are and your club.</li>';
    if (open.blocked) $('mxMsgs').insertAdjacentHTML('beforeend', `<li class="muted small mx-blocked">${esc(firstName(name))} is not taking messages from you.</li>`);
    $('mxText').disabled = !!open.blocked; $('mxSend').disabled = !!open.blocked;
    $('mxText').placeholder = open.blocked ? 'This conversation is closed' : `Write to ${firstName(name)}`;
    const box = $('mxMsgs'); box.scrollTop = box.scrollHeight;
    fillNewMsgTo();
  }

  function fillNewMsgTo() {
    const sl = demo.shortlist();
    const order = [...Object.keys(sl).filter(g => state.all.has(g)), ...[...state.all.keys()].filter(g => !sl[g])];
    const keep = $('newMsgTo').value;
    $('newMsgTo').innerHTML = order.map(g => {
      const p = state.all.get(g);
      return `<option value="${esc(g)}">${esc(p.name)} · ${esc(p.club)}${sl[g] ? ' · shortlisted' : ''}</option>`;
    }).join('');
    if (keep && order.includes(keep)) $('newMsgTo').value = keep;
  }

  $('mxList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-convo]');
    if (!b) return;
    state.openConvo = b.dataset.convo;
    $('mx').classList.add('reading');
    $('mxStatus').textContent = '';
    const c = demo.conversation(state.openConvo);
    if (c) { try { history.replaceState(null, '', `${location.pathname}${location.search}#messages/${enc(c.player)}`); } catch (err) {} }
    paintMessages();
    if (!$('mxText').disabled) $('mxText').focus({ preventScroll: true });
  });
  $('mxBack').addEventListener('click', () => { $('mx').classList.remove('reading'); settle('messages'); });
  $('mxCompose').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $('mxText').value.trim();
    if (!text || !state.openConvo) return;
    const sent = demo.send(state.openConvo, 'scout', text);
    $('mxStatus').textContent = sent ? '' : 'This message could not be sent: the player is not taking messages from you.';
    if (sent) $('mxText').value = '';
    paintMessages();
    $('mxText').focus();
  });
  $('newMsg').addEventListener('click', () => {
    const open = $('newMsgBox').hidden;
    if (open) fillNewMsgTo();
    toggleBox($('newMsg'), $('newMsgBox'), open);
    if (open) $('newMsgTo').focus();
  });
  $('newMsgCancel').addEventListener('click', () => { toggleBox($('newMsg'), $('newMsgBox'), false); $('newMsg').focus(); });
  $('newMsgStart').addEventListener('click', () => {
    const gid = $('newMsgTo').value;
    if (GID.test(gid)) openMessages(gid);
  });

  // ------------------------------------------------------------------ Team: Fairhaven's needs and squad

  function paintTeam() {
    const s = state.season;
    const C = (s?.clubs || []).find(c => c.club_id === CLUB_ID);
    const row = (s?.table || []).find(t => t.club_id === CLUB_ID);
    if (C) {
      const k = C.kit || {};
      if (HEX.test(k.primary || '') && HEX.test(k.secondary || '')) $('crest').style.background = `linear-gradient(135deg, ${k.primary} 50%, ${k.secondary} 50%)`;
      $('clubHead').textContent = C.name;
      $('clubLine').textContent = [`${s.league} ${s.season}`, C.ground,
        row ? `${row.position === 1 ? 'top of the table' : `${PV.ordinal(row.position)} in the table`}, ${plural(row.points, 'point')}` : '']
        .filter(Boolean).join(' · ');
      $('squad').innerHTML = [...(C.squad || [])].sort((a, b) => a.kit_number - b.kit_number).map(p => `<li><span class="tm-num">${esc(p.kit_number)}</span>
        <span>${GID.test(p.global_id || '') ? `<a href="/players/${enc(p.global_id)}">${esc(p.name)}</a>` : esc(p.name)}</span>
        <span class="muted small">${esc(POSITIONS[p.position] || p.position)}${p.starter ? '' : ' · substitute'}</span></li>`).join('')
        || '<li class="muted small">No squad listed.</li>';
    }
    const per90 = state.stats.filter(st => st.kind === 'per90' && st.headline);
    const keep = $('needStat').value;
    $('needStat').innerHTML = per90.map(st => `<option value="${esc(st.key)}">${esc(st.label)} per 90</option>`).join('');
    if (keep) $('needStat').value = keep;
    paintNeeds();
  }

  function paintNeeds() {
    const sl = demo.shortlist();
    $('needs').innerHTML = demo.needs().map((n) => {
      const ps = fits(n);
      const pos = POSITIONS[n.pos] || n.pos;
      return `<article class="sc-need"><div class="pf-bar"><h3>${esc(n.title)}</h3><button type="button" class="link" data-dropneed="${esc(n.id)}"
          aria-label="Remove the need: ${esc(n.title)}">Remove</button></div>
        <p class="muted small">${esc(pos)}s with ${esc(labelOf(n.stat).toLowerCase())} per 90 higher than ${esc(n.pct)}% of the league's ${esc(GROUP[n.pos] || 'players')} · ${esc(plural(ps.length, 'player fits', 'players fit'))}</p>
        <div class="sc-mini">${ps.slice(0, 6).map(p => `<a href="/players/${enc(p.global_id)}" class="sc-minirow"><span class="sc-shirt" aria-hidden="true">${shirt(p)}</span>
          <span><b>${esc(p.name)}</b> <span class="muted small">${esc(p.club)} · ${esc(fmtRate(headOf(p, n.stat).per90))} per 90 · ${esc(PV.pctText(headOf(p, n.stat).percentile, p.position))}</span></span>${sl[p.global_id] ? stageBadge(sl[p.global_id].stage) : ''}</a>`).join('')
          || '<p class="muted small">Nobody in the league fits this yet.</p>'}</div></article>`;
    }).join('') || '<p class="muted small">No needs yet. Add what the club is looking for.</p>';
  }

  $('addNeed').addEventListener('click', () => {
    const open = $('needForm').hidden;
    toggleBox($('addNeed'), $('needForm'), open);
    if (open) $('needTitle').focus();
  });
  $('needCancel').addEventListener('click', () => { toggleBox($('addNeed'), $('needForm'), false); $('addNeed').focus(); });
  $('needForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const pos = $('needPos').value, stat = $('needStat').value;
    if (!POSITIONS[pos] || !statOf(stat)) return;
    const title = $('needTitle').value.trim().slice(0, 60) || `A ${POSITIONS[pos].toLowerCase()} strong on ${labelOf(stat).toLowerCase()}`;
    demo.saveNeeds([...demo.needs(), { id: `nd_${Date.now().toString(36)}`, title, pos, stat, pct: Number($('needPct').value) || 75 }]);
    $('needTitle').value = '';
    toggleBox($('addNeed'), $('needForm'), false);
    paintNeeds();
    $('addNeed').focus();
  });
  $('needs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-dropneed]');
    if (!b) return;
    demo.saveNeeds(demo.needs().filter(n => n.id !== b.dataset.dropneed));
    paintNeeds();
    $('addNeed').focus();
  });

  // ------------------------------------------------------------------ Settings

  function paintSettings() {
    const st = demo.settings('scout') || {};
    $('stEmail').textContent = st.email || '';
    for (const box of document.querySelectorAll('[data-notify]')) box.checked = !!(st.notify && st.notify[box.dataset.notify]);
    for (const r of document.querySelectorAll('input[name="scPrivacy"]')) r.checked = r.value === (st.privacy || 'club');
  }
  function saveSetting(fn) {
    const st = demo.settings('scout') || {};
    fn(st);
    demo.saveSettings('scout', st);
  }
  document.querySelector('[data-panel="settings"]').addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.notify) saveSetting(st => { st.notify = { ...(st.notify || {}), [t.dataset.notify]: t.checked }; });
    if (t.name === 'scPrivacy') saveSetting(st => { st.privacy = t.value === 'me' ? 'me' : 'club'; });
  });
  $('stEmailEdit').addEventListener('click', () => {
    const open = $('stEmailForm').hidden;
    toggleBox($('stEmailEdit'), $('stEmailForm'), open);
    if (open) { $('stEmailInput').value = (demo.settings('scout') || {}).email || ''; $('stEmailInput').focus(); }
  });
  $('stEmailCancel').addEventListener('click', () => { toggleBox($('stEmailEdit'), $('stEmailForm'), false); $('stEmailEdit').focus(); });
  $('stEmailForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = $('stEmailInput').value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { $('stEmailInput').setCustomValidity('Enter an email address.'); $('stEmailInput').reportValidity(); return; }
    $('stEmailInput').setCustomValidity('');
    saveSetting(st => { st.email = v.slice(0, 120); });
    toggleBox($('stEmailEdit'), $('stEmailForm'), false);
    paintSettings();
    $('stEmailEdit').focus();
  });
  $('stEmailInput').addEventListener('input', () => $('stEmailInput').setCustomValidity(''));
  // As on the Player dashboard: signing out forgets the admin key this tab holds (Regista.key).
  $('stOut').addEventListener('click', () => {
    R.key.clear();
    $('stOutNote').textContent = 'Signed out: this tab no longer holds the admin key.';
  });
  $('stReset').addEventListener('click', () => {
    demo.reset();
    state.openConvo = null; state.openReport = null; state.picker = null;
    repaintAll();
    paintSettings();
    $('stResetNote').textContent = 'Done: messages, the shortlist, reports, needs, settings and the Terminal workspaces are back to how they started.';
  });

  // ------------------------------------------------------------------ start

  function repaintAll() {
    counts();
    syncStars();
    paintBoard();
    paintReports();
    paintMessages();
    paintNeeds();
    if (state.section === 'overview') paintOverview();
    if (state.section === 'settings') paintSettings();
  }

  // Another tab of this browser (the Player dashboard, a profile's scout bar) changed what this browser keeps.
  R.store.watch(() => {
    if (!state.ready) return;
    repaintAll();
    if (state.section === 'overview') refreshUploads();
  });

  async function start() {
    counts();
    if (!(await loadSeason())) return;
    try {
      await loadAll();
    } catch (e) {
      netError(e, start);
      return;
    }
    clearNetError();
    state.ready = true;
    paintTeam();
    loadPlayers();
    show(nav.section(), nav.rest());
    refreshUploads();
  }
  start();
})();
