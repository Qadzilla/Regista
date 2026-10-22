// The Scout view (/scout): the Regista League's table, every player as a card filtered and sorted by any stat, a
// shortlist kept in this browser, and two or three shortlisted players compared side by side. Plain script on top of
// window.Regista (/static/shared/regista.js). No inline scripts, handlers or style attributes in markup: the page runs
// under a Content Security Policy, so colours and bar widths are set through element.style after rendering.
// Every number on the page comes from the API (/api/season, /api/players, /api/compare); this file only formats them.
(function () {
  const R = window.Regista;
  // Everything that reaches innerHTML from the API goes through esc(): names, clubs and moment titles are data, never
  // markup.
  const esc = R.esc;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const LIMIT = 200;            // what /api/players accepts; the league has fewer players than this
  const COMPARE_MAX = 3;        // what /api/compare accepts
  const SHORTLIST_KEY = 'regista-scout-shortlist';

  const POSITIONS = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };
  // The headline rates a card shows first for each position (keys of the card's `headline`), before the sort fills in.
  const BY_POSITION = {
    GK: ['saves', 'passes_completed', 'recoveries'],
    DF: ['tackles_won', 'interceptions', 'recoveries', 'passes_completed'],
    MF: ['key_passes', 'passes_completed', 'take_ons_won', 'tackles_won'],
    FW: ['goals', 'shots', 'take_ons_won', 'key_passes'],
  };
  const CARD_RATES = 4;

  const state = {
    season: null,
    stats: [],                  // the stat catalogue from the API: {key, label, kind: per90|ratio, headline}
    players: [],                // the cards on screen
    filters: { position: '', club: '', q: '', min_minutes: 0, sort: 'minutes' },
    shortlist: [],              // [{global_id, name, club, short_name, kit_number, position, kit}]
    picked: new Set(),          // shortlisted ids picked for Compare
    known: new Map(),           // global id -> every card seen (the list and the Scout agent's replies), for the stars
    seq: 0,                     // drops replies to older player requests
  };

  // ------------------------------------------------------------------ small helpers

  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';
  const offline = (e) => !(e instanceof R.ApiError);
  const OFFLINE = 'Can\'t reach Regista right now. Check your connection and try again.';
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const statOf = (key) => state.stats.find(s => s.key === key);
  const labelOf = (key) => key === 'minutes' ? 'Minutes played' : key === 'name' ? 'Name' : (statOf(key)?.label || 'that stat');
  const HEX = /^#[0-9a-f]{6}$/i;

  function ordinal(n) {
    const v = n % 100;
    const s = (v >= 11 && v <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th');
    return `${n}${s}`;
  }
  const fmtRate = (v) => (v === null || v === undefined) ? '–' : Number(v).toFixed(2);
  const fmtRatio = (v) => (v === null || v === undefined) ? '–' : `${Math.round(Number(v) * 100)}%`;
  const fmtMinutes = (m) => `${Math.round(Number(m) || 0)} min`;

  // Text on a kit colour: dark on light kits, light on dark ones.
  function inkOn(hex) {
    if (!HEX.test(hex || '')) return '#111';
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.55 ? '#111' : '#fff';
  }
  const kitColour = (p) => (p.position === 'GK' && p.kit?.gk) ? p.kit.gk : p.kit?.primary;

  // Swatches and shirt numbers carry data-c (fill) and optionally data-c2 (edge); bars carry data-w (percent). Applied
  // after each render through element.style, which the Content Security Policy allows.
  function paint(root) {
    for (const el of root.querySelectorAll('[data-c]')) {
      const c = el.dataset.c;
      if (!HEX.test(c)) continue;
      el.style.background = c;
      if (el.classList.contains('shirt')) el.style.color = inkOn(c);
      if (HEX.test(el.dataset.c2 || '')) el.style.borderColor = el.dataset.c2;
    }
    for (const el of root.querySelectorAll('[data-w]')) el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.w) || 0))}%`;
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
      return `<tr>
        <td>${esc(r.position)}</td>
        <th scope="row" class="club-col"><button type="button" class="club" data-club="${esc(r.club_id)}"
            aria-label="Show ${esc(r.club)} players"><span class="kit" data-c="${esc(r.kit?.primary)}" data-c2="${esc(r.kit?.secondary)}"></span>
          <span class="full">${esc(r.club)}</span><span class="short" aria-hidden="true">${esc(r.short_name)}</span></button></th>
        <td>${esc(r.played)}</td><td>${esc(r.won)}</td><td>${esc(r.drawn)}</td><td>${esc(r.lost)}</td>
        <td>${esc(gd)}</td><td class="pts">${esc(r.points)}</td></tr>`;
    }).join('');
    paint($('tableBody'));
  }

  $('tableBody').addEventListener('click', (ev) => {
    const b = ev.target.closest('button.club');
    if (!b) return;
    const club = state.filters.club === b.dataset.club ? '' : b.dataset.club;
    $('fClub').value = club;
    setFilter({ club });
    $('resultsHead').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  // ------------------------------------------------------------------ filters

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

  // The filters live in the address too, so a search can be shared or reloaded.
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
  }

  function writeUrl() {
    const f = state.filters;
    const u = new URLSearchParams();
    if (f.position) u.set('position', f.position);
    if (f.club) u.set('club', f.club);
    if (f.q) u.set('q', f.q);
    if (f.min_minutes) u.set('min_minutes', String(f.min_minutes));
    if (f.sort !== 'minutes') u.set('sort', f.sort);
    const qs = u.toString();
    try { history.replaceState(null, '', qs ? `/scout?${qs}` : '/scout'); } catch (e) {}
  }

  function setFilter(patch) {
    Object.assign(state.filters, patch);
    writeUrl();
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
    loadPlayers();
  });

  // ------------------------------------------------------------------ player cards

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

  // Three or four rates for a card: the sort first when the card carries it, then the position's headline rates.
  function picks(p) {
    const sort = state.filters.sort;
    const keys = [];
    const st = statOf(sort);
    if (st && (st.kind === 'ratio' || p.headline?.[sort])) keys.push(sort);
    for (const k of BY_POSITION[p.position] || BY_POSITION.MF) if (!keys.includes(k)) keys.push(k);
    return keys.slice(0, CARD_RATES);
  }

  function rateRow(p, key) {
    const st = statOf(key);
    if (st?.kind === 'ratio') {
      const v = p.ratios?.[key];
      return `<li><span class="lbl">${esc(st.label)}</span><span class="val">${esc(fmtRatio(v))}</span>
        <span class="pct muted">of attempts</span></li>`;
    }
    const h = p.headline?.[key];
    if (!h) return '';
    const pc = h.percentile;
    const pcText = pc === null || pc === undefined ? 'no percentile' : `${ordinal(pc)} percentile`;
    const pcTitle = pc === null || pc === undefined ? 'Too few minutes to rank among players in the same position'
      : `Higher than ${pc}% of ${POSITIONS[p.position] ? POSITIONS[p.position].toLowerCase() + 's' : 'players'} in the league`;
    return `<li><span class="lbl">${esc(h.label)}</span><span class="val">${esc(fmtRate(h.per90))}</span>
      <span class="pct muted" title="${esc(pcTitle)}">${esc(pcText)}</span>
      <span class="bar" aria-hidden="true"><i data-w="${esc(pc ?? 0)}"></i></span></li>`;
  }

  function cardHtml(p) {
    const on = isShortlisted(p.global_id);
    const best = p.best_moment?.title;
    return `<article class="card" data-id="${esc(p.global_id)}">
      <div class="card-top">
        <span class="shirt" data-c="${esc(kitColour(p))}" data-c2="${esc(p.kit?.secondary)}" aria-hidden="true">${esc(p.kit_number)}</span>
        <div class="who">
          <h3 class="name"><a href="/players/${enc(p.global_id)}">${esc(p.name)}</a></h3>
          <p class="sub"><span class="kit" data-c="${esc(p.kit?.primary)}" data-c2="${esc(p.kit?.secondary)}" aria-hidden="true"></span>
            ${esc(p.club)} · #${esc(p.kit_number)} · ${esc(POSITIONS[p.position] || p.position)}</p>
          <p class="sub muted">${esc(fmtMinutes(p.minutes))} · ${esc(plural(p.appearances, 'match', 'matches'))}</p>
        </div>
        <button type="button" class="star" data-star="${esc(p.global_id)}" aria-pressed="${on}"
          aria-label="${on ? 'Remove' : 'Add'} ${esc(p.name)} ${on ? 'from' : 'to'} the shortlist">${on ? '★' : '☆'}</button>
      </div>
      <p class="per">Per 90 minutes</p>
      <ul class="rates">${picks(p).map(k => rateRow(p, k)).join('')}</ul>
      ${best ? `<p class="best"><span class="muted">Best moment</span> ${esc(best)}</p>` : '<p class="best muted">No labelled moments yet.</p>'}
    </article>`;
  }

  function renderCards() {
    const f = state.filters;
    const n = state.players.length;
    const sortWords = f.sort === 'name' ? 'by name' : f.sort === 'minutes' ? 'by minutes played' : `by ${labelOf(f.sort).toLowerCase()}`;
    $('resultsHead').textContent = `Players`;
    $('resultsSub').textContent = n ? `${plural(n, 'player')}, sorted ${sortWords}${statOf(f.sort)?.kind === 'per90' ? ' per 90 minutes' : ''}` : '';
    const st = statOf(f.sort);
    if (st && st.kind === 'per90' && !st.headline) {
      $('resultsSub').textContent += `. Cards do not show ${st.label.toLowerCase()}; each player's profile does.`;
    }
    $('cards').innerHTML = state.players.map(cardHtml).join('');
    paint($('cards'));
    $('empty').hidden = n > 0;
    if (!n) $('empty').textContent = 'No players match these filters. Try a lower minimum or another position.';
  }

  $('cards').addEventListener('click', (ev) => {
    const b = ev.target.closest('button.star');
    if (!b) return;
    const p = state.known.get(b.dataset.star);
    if (p) toggleShortlist(p);
  });

  // ------------------------------------------------------------------ shortlist (this browser only)

  // localStorage may be missing or throw (private windows, blocked storage): the shortlist then lives in memory and
  // the panel says so.
  let stored = true;
  function loadShortlist() {
    try {
      const raw = localStorage.getItem(SHORTLIST_KEY);
      const list = raw ? JSON.parse(raw) : [];
      state.shortlist = Array.isArray(list) ? list.filter(x => x && typeof x.global_id === 'string' && /^pl_[a-z0-9_]{1,40}$/.test(x.global_id)) : [];
      for (const x of state.shortlist.slice(0, COMPARE_MAX)) state.picked.add(x.global_id);  // ready to compare on return
    } catch (e) {
      stored = false;
      state.shortlist = [];
    }
  }
  function saveShortlist() {
    try { localStorage.setItem(SHORTLIST_KEY, JSON.stringify(state.shortlist)); stored = true; } catch (e) { stored = false; }
  }
  const isShortlisted = (gid) => state.shortlist.some(x => x.global_id === gid);

  function toggleShortlist(p) {
    if (isShortlisted(p.global_id)) {
      state.shortlist = state.shortlist.filter(x => x.global_id !== p.global_id);
      state.picked.delete(p.global_id);
    } else {
      state.shortlist.push({ global_id: p.global_id, name: p.name, club: p.club, short_name: p.short_name, kit_number: p.kit_number,
                             position: p.position, kit: p.kit });
      if (state.picked.size < COMPARE_MAX) state.picked.add(p.global_id);
    }
    saveShortlist();
    renderShortlist();
    syncStars();
  }

  // Every star on the page (the list and the Scout agent's reply) shows whether its player is shortlisted.
  function syncStars() {
    for (const b of document.querySelectorAll('button.star')) {
      const p = state.known.get(b.dataset.star);
      const on = isShortlisted(b.dataset.star);
      b.setAttribute('aria-pressed', String(on));
      b.textContent = on ? '★' : '☆';
      if (p) b.setAttribute('aria-label', `${on ? 'Remove' : 'Add'} ${p.name} ${on ? 'from' : 'to'} the shortlist`);
    }
  }

  function renderShortlist() {
    const list = state.shortlist;
    for (const id of [...state.picked]) if (!isShortlisted(id)) state.picked.delete(id);
    $('shortCount').textContent = list.length ? `(${list.length})` : '';
    $('shortEmpty').hidden = list.length > 0;
    $('shortStore').hidden = stored;
    $('shortActions').hidden = list.length < 2;
    $('shortList').innerHTML = list.map(p => {
      const picked = state.picked.has(p.global_id);
      const full = !picked && state.picked.size >= COMPARE_MAX;
      return `<li>
        <label class="pick"><input type="checkbox" data-pick="${esc(p.global_id)}" ${picked ? 'checked' : ''} ${full ? 'disabled' : ''}>
          <span class="sr">Compare ${esc(p.name)}</span></label>
        <span class="shirt sm" data-c="${esc(kitColour(p))}" aria-hidden="true">${esc(p.kit_number)}</span>
        <span class="sl-who"><a href="/players/${enc(p.global_id)}">${esc(p.name)}</a>
          <span class="muted">${esc(p.short_name || p.club)} · ${esc(p.position)}</span></span>
        <button type="button" class="x" data-drop="${esc(p.global_id)}" aria-label="Remove ${esc(p.name)} from the shortlist">×</button>
      </li>`;
    }).join('');
    paint($('shortList'));
    const n = state.picked.size;
    $('compareGo').disabled = n < 2;
    $('compareHint').textContent = n < 2 ? `Pick ${n ? 'one more' : 'two or three'} to compare.` : `${n} picked.`;
  }

  $('shortList').addEventListener('change', (ev) => {
    const box = ev.target.closest('input[data-pick]');
    if (!box) return;
    const id = box.dataset.pick;
    if (box.checked && state.picked.size < COMPARE_MAX) state.picked.add(id); else state.picked.delete(id);
    renderShortlist();
    const again = $('shortList').querySelector(`input[data-pick="${CSS.escape(id)}"]`);
    if (again) again.focus();
  });
  $('shortList').addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-drop]');
    if (!b) return;
    const p = state.shortlist.find(x => x.global_id === b.dataset.drop);
    if (!p) return;
    toggleShortlist(p);
    ($('shortList').querySelector('button[data-drop]') || $('shortHead')).focus();
  });

  // ------------------------------------------------------------------ compare

  async function compare() {
    const ids = state.shortlist.map(p => p.global_id).filter(id => state.picked.has(id)).slice(0, COMPARE_MAX);
    if (ids.length < 2) return;
    $('compareGo').disabled = true;
    $('compare').hidden = false;
    $('compareBody').innerHTML = '<p class="muted">Loading…</p>';
    $('compareHead').focus();
    $('compare').scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const out = await R.api(`/api/compare?ids=${ids.map(enc).join(',')}`);
      clearNetError();
      renderCompare(out);
    } catch (e) {
      $('compareBody').innerHTML = `<p class="muted">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
    } finally {
      $('compareGo').disabled = state.picked.size < 2;
    }
  }

  function renderCompare(out) {
    const ps = out.players || [];
    const stats = out.stats || state.stats;
    const head = ps.map(p => {
      const c = p.card;
      return `<th scope="col"><span class="shirt sm" data-c="${esc(kitColour(c))}" aria-hidden="true">${esc(c.kit_number)}</span>
        <a href="/players/${enc(c.global_id)}">${esc(c.name)}</a>
        <span class="muted">${esc(c.short_name)} · ${esc(c.position)}</span>
        <span class="muted">${esc(fmtMinutes(p.minutes))}</span></th>`;
    }).join('');
    const rows = (kind, title) => {
      const body = stats.filter(s => s.kind === kind).map(s => {
        const vals = ps.map(p => kind === 'ratio' ? p.ratios?.[s.key] : p.per90?.[s.key]);
        const nums = vals.filter(v => v !== null && v !== undefined).map(Number);
        const top = nums.length ? Math.max(...nums) : null;
        const markBest = top !== null && top > 0 && nums.length > 1;
        const cells = ps.map((p, i) => {
          const v = vals[i];
          const best = markBest && v !== null && v !== undefined && Number(v) === top;
          const pc = kind === 'per90' ? p.percentiles?.[s.key] : null;
          const txt = kind === 'ratio' ? fmtRatio(v) : fmtRate(v);
          return `<td class="${best ? 'best' : ''}">${esc(txt)}${best ? '<span class="sr"> (highest)</span>' : ''}${
            pc !== null && pc !== undefined ? `<span class="pc">${esc(ordinal(pc))}</span>` : ''}</td>`;
        }).join('');
        return `<tr><th scope="row">${esc(s.label)}</th>${cells}</tr>`;
      }).join('');
      return body ? `<tbody><tr class="group"><th scope="rowgroup" colspan="${ps.length + 1}">${esc(title)}</th></tr>${body}</tbody>` : '';
    };
    $('compareBody').innerHTML = `<table class="ctable">
      <caption class="sr">${esc(ps.map(p => p.card.name).join(', '))} compared</caption>
      <thead><tr><td></td>${head}</tr></thead>
      ${rows('per90', 'Per 90 minutes (percentile)')}${rows('ratio', 'Share that worked')}
    </table>`;
    paint($('compareBody'));
  }

  $('compareGo').addEventListener('click', compare);
  $('compareClose').addEventListener('click', () => { $('compare').hidden = true; $('compareGo').focus(); });

  // ------------------------------------------------------------------ the Scout agent (wired by Scout C)

  // Renders a reply from the Scout agent (POST /api/scout/ask) into #scoutAnswer: the reply, how the question was
  // understood, who answered and with which tools, then the players as ordinary cards (stars join the shortlist).
  function renderScoutAnswer(json) {
    const box = $('scoutAnswer');
    const reply = json && typeof (json.reply ?? json.answer) === 'string' ? (json.reply ?? json.answer) : '';
    const players = Array.isArray(json?.players) ? json.players.filter(p => p && p.global_id) : [];
    for (const p of players) state.known.set(p.global_id, p);
    const by = typeof json?.answered_by === 'string' ? json.answered_by : '';
    const tools = Array.isArray(json?.tools_used) ? json.tools_used : [];
    const byLine = by.startsWith('foundry')
      ? `Answered by Microsoft Foundry${tools.length ? `, using ${tools.map(esc).join(', ')}` : ''}.`
      : (by && by !== 'rules' ? `Answered by Regista's rules (${esc(by.replace(/^rules\s*/, '').replace(/^\(|\)$/g, ''))}).` : "Answered by Regista's rules.");
    const checked = Array.isArray(json?.checked) && json.checked.length
      ? `<p class="muted small">Numbers in this reply that no tool returned: ${json.checked.map(esc).join(', ')}.</p>` : '';
    box.innerHTML = (reply ? `<p class="reply">${esc(reply)}</p>` : '') +
      (json?.understood ? `<p class="muted small">Understood: ${esc(json.understood)}</p>` : '') +
      `<p class="muted small">${byLine}</p>${checked}` +
      (players.length ? `<div class="cards">${players.map(cardHtml).join('')}</div>` : '');
    paint(box);
  }
  window.RegistaScout = { renderScoutAnswer };

  $('scoutAnswer').addEventListener('click', (ev) => {
    const b = ev.target.closest('button.star');
    if (!b) return;
    const p = state.known.get(b.dataset.star);
    if (p) toggleShortlist(p);
  });

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

  // ------------------------------------------------------------------ start

  async function start() {
    loadShortlist();
    renderShortlist();
    if (await loadSeason()) await loadPlayers();
  }
  start();
})();
