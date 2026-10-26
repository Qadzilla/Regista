// Home (/): ask for any moment across every match, watch it in its match, take it away. Three views on one page:
//   landing  the logo, the tagline and one search box (Data Search or Ask Microsoft Foundry);
//   results  the moments every match found for the conversation so far, best first, with a compact search bar;
//   match    the full match view of one moment: timeline, stage, the recap folded away, the player's moments.
// The conversation (every question, its answer and how it was answered) lives in the panel on the right.
// Plain script on top of window.Regista (/static/shared/regista.js); the timeline is /static/product/timeline.js.
// No inline scripts, handlers or style attributes: the page runs under a Content Security Policy.
(function () {
  const R = window.Regista;
  // Everything that reaches innerHTML from the API goes through esc(): names, titles, tags, explanations, replies and
  // tool names can come from uploads, reviewers or models, so they are never trusted as markup.
  const esc = R.esc;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const REEL_MAX = 12;   // what /reel.mp4 accepts
  const PARALLEL = 6;    // requests in flight at once when Home searches every match (a browser's per-host limit)

  // The match view's state: one match, one player, one result set (the player's moments, or the last reply asked there).
  const state = {
    matches: [], match: null, info: null, player: null,
    all: new Map(),          // clip id -> clip as GET /clips returns it: every persisted clip, plus the moments of each
                             // player looked at (derived on the fly by the server): the grid's labels, the timeline
    loaded: new Set(),       // players whose moments are in state.all
    results: [], total: 0,   // the current result set (normalised rows) and how many the question matched in all
    fromQuestion: false,     // false: the picked player's moments; true: the last reply's results
    reel: null,              // clip ids of the last "make a reel" reply, if any
    tag: null,               // the tag chip filtering the grid, or null for all
    sort: 'best', selected: null, health: null,
    picked: null,            // the moment last picked by a click or a link: the clip= of the page's URL
    head: 'Moments', emptyHtml: '',
    season: [],              // the Regista League's matches (GET /api/season), in round order
    clubs: new Map(),        // club id -> short name ("ASH"), for the match line on result cards
    view: 'landing',         // 'landing' | 'results' | 'match'
    catalogue: new Map(),    // match id -> GET /api/catalogue/matches row: every uploaded match (the league's included),
                             // with its competition, round, score, date, camera and uploader
    comps: new Map(),        // competition id -> GET /api/catalogue competition, with its level in words
  };
  // The match view's conversation (as before: the query so far for this match). history is the whole conversation, for
  // a Foundry reply's context; the log in the panel shows every turn, from Home and from the match view.
  const chat = { state: null, history: [], busy: false };
  // Home's search across every match: one call to the match's own /chat per match, merged best first.
  const search = {
    results: [], total: 0, fromQuestion: true, reel: null, tag: null, sort: 'best', head: 'Moments', emptyHtml: '',
    asked: false,            // a search has results to go back to
    states: new Map(),       // match id -> the query so far in that match, as its /chat returned it
    perMatch: new Map(),     // match id -> {total, counted}: what each match found, and how much of it counts
    names: null,             // the players the conversation named (a Set of names), or null for anyone
    infos: new Map(),        // match id -> GET /api/matches/{id} (origin, for the "Cut from video" badge)
    clips: new Map(),        // match id -> clip id -> clip (label models, for the Foundry badge), library matches only
    wayout: null,            // {label, go}: the follow-up that clears piled-up filters, when nothing was found
    comp: '',                // the Competition filter on the results ('' for every competition)
    expanded: new Set(),     // competitions whose results show all, not the best 8
  };
  const ui = { engine: 'rules' };

  // ------------------------------------------------------------------ small helpers

  const matchUrl = (path = '', id = state.match) => `/api/matches/${enc(id)}${path}`;
  const player = (pid) => state.info?.players.find(p => p.player_id === pid);
  const team = (tid) => state.info?.teams.find(t => t.team_id === tid);
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';
  // fetch() itself failed: the server or the network is down. ApiError means the server answered.
  const offline = (e) => !(e instanceof R.ApiError);
  const OFFLINE = 'Can\'t reach Regista right now. Check your connection and try again.';
  const COSMOS_HINT = 'This match is read from Cosmos DB without its event stream, so it cannot answer questions here. Its moments are below.';
  const momentsOf = (pid) => (state.info?.moment_counts || {})[pid] || 0;
  const set = () => state.view === 'results' ? search : state;   // the result set the grid shows in this view

  // A match as people would name it: its title, else the teams and score. Never its id.
  function matchName(m) {
    if (m.title) return m.title;
    const [a, b] = m.teams || [];
    if (!a || !b) return 'A match';
    const score = m.score ? ` ${m.score[a.team_id]}–${m.score[b.team_id]} ` : ' v ';
    return `${a.name}${score}${b.name}${m.source === 'cosmos' ? ' (from Cosmos DB)' : ''}`;
  }

  // Tags that are bookkeeping, not football: never shown or offered as filters (as in regista.conversation).
  const INTERNAL = /_appearance$|_against$|^(on_ball_main|touch|possession_change|kick_off|period_start|period_end)$/;
  const plainTags = (tags) => (tags || []).filter(t => !INTERNAL.test(t));

  // The match clock at video time t, as the clip's scoreboard draws it (the engine's count: period 2 starts at 45:00,
  // whatever the match's length): MM:SS inside a period, HT between the halves, FT after. From the match's periods
  // (GET /api/matches/{id}); without them, the video time.
  const START_MIN = { 1: 0, 2: 45, 3: 90, 4: 105, 5: 120 };
  function clockOf(info, t) {
    const ps = (info && info.periods) || [], x = Number(t) || 0;
    if (!ps.length) return R.fmtTime(x);
    for (let i = 0; i < ps.length; i++) {
      if (x < ps[i].t) return i === 0 ? '00:00' : 'HT';
      if (x < ps[i].t_end) { const s = (START_MIN[ps[i].period] ?? 0) * 60 + (x - ps[i].t); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`; }
    }
    return 'FT';
  }
  // A catalogue match in words: "Round 1 · Eastwick United 0–2 Brookfield Rovers", the date, the camera and the uploader.
  const CAMS = { tripod: 'tripod', phone: 'phone', drone: 'drone', broadcast: 'broadcast camera' };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const fmtDate = (iso) => { const [y, m, d] = String(iso || '').split('-').map(Number); return y && m && d ? `${d} ${MONTHS[m - 1]} ${y}` : String(iso || ''); };
  const scoreWords = (cm) => cm.score ? `${cm.home_name} ${cm.score.t_home}–${cm.score.t_away} ${cm.away_name}` : `${cm.home_name} v ${cm.away_name}`;
  const matchWords = (cm) => `${cm.round ? `Round ${cm.round} · ` : ''}${scoreWords(cm)}`;
  const upWords = (u) => !u ? '' : u.type === 'player' ? `uploaded by ${u.name}, a player at ${u.club}` : `uploaded by the ${u.club} team account`;
  const levelOf = (comp) => comp ? comp.level_words : '';

  // A clip from GET /clips or a result from /chat, as one shape. Chat results carry no label model, so the badge
  // reads it from the match's clips. A Foundry label's explanation was written to justify a score ("Scored 0.56
  // because… xG"); people read its summary instead, which says what happens. ctx: a result from Home's search
  // ({mid, idx}: its match and that match's place in the list), read against that match's clips.
  function row(c, ctx = null) {
    const id = c.id || c.clip_id;
    const full = (ctx ? search.clips.get(ctx.mid) : state.all)?.get(id);
    const lb = c.label || full?.label || {};
    const model = lb.model || full?.label?.model || '';
    let explanation = c.explanation ?? lb.explanation ?? '';
    if (String(model).startsWith('foundry:')) explanation = lb.summary || c.summary || full?.label?.summary || '';
    if (/^Scored\b/.test(explanation)) explanation = '';
    return {
      id, player_id: c.player_id, t: c.t, t_end: c.t_end, reason: c.reason,
      title: c.title ?? lb.title, tags: c.tags ?? lb.tags ?? [], watchability: c.watchability ?? lb.watchability ?? 0,
      explanation, model,
      video_url: c.video_url !== undefined ? c.video_url : (full ? full.video_url : null),
      mid: ctx ? ctx.mid : state.match, idx: ctx ? ctx.idx : 0, player: c.player || '', raw: c,
    };
  }

  // Chat results the page has not seen yet (a player picked by name in the question) join state.all, so the timeline
  // has markers for them too.
  function remember(results) {
    for (const c of results || []) {
      const id = c.clip_id || c.id;
      if (!id || state.all.has(id)) continue;
      state.all.set(id, { id, player_id: c.player_id, t: c.t, t_end: c.t_end, reason: c.reason, title: c.title, video_url: c.video_url,
                          label: { title: c.title, tags: c.tags || [], watchability: c.watchability || 0, explanation: c.explanation || '',
                                   summary: c.summary || '' } });
    }
  }

  // Best first: watchability, then the match's place in the list, then time. Match order: the matches in list order,
  // each from kick-off. Within one match (the match view) both are as they always were.
  const sorted = (rows, s = set()) => [...rows].sort(s.sort === 'time'
    ? (a, b) => (a.idx - b.idx) || (a.t - b.t)
    : (a, b) => (b.watchability - a.watchability) || (a.idx - b.idx) || (a.t - b.t));

  // The result set as the grid shows it: filtered by the tag chip, in the order picked.
  const visible = () => { const s = set(); return sorted(s.tag ? s.results.filter(r => r.tags.includes(s.tag)) : s.results, s); };

  // ------------------------------------------------------------------ errors with a way out

  function showNetError(text, retry) {
    const box = $('netError');
    box.hidden = false;
    $('netErrorText').textContent = text;
    $('netRetry').onclick = () => { box.hidden = true; retry(); };
  }
  const hideNetError = () => { $('netError').hidden = true; };

  // ------------------------------------------------------------------ the views

  // One view at a time. The moments section (heading, sort, tag chips, grid) moves under the results or under the
  // match; the conversation panel shows in the match view, and on the results when Microsoft Foundry answers.
  // push: a step people take (landing to results, results to a match) gets its own history entry, so Back returns.
  function showView(v, { sync = true, push = false } = {}) {
    if (push && v !== state.view && window.history?.pushState) {
      try { history.pushState({ view: v, from: state.view }, '', location.pathname); } catch (e) { /* the page still works */ }
    }
    state.view = v;
    $('landing').hidden = v !== 'landing';
    $('work').hidden = v === 'landing';
    $('resultsView').hidden = v !== 'results';
    $('resultsTop').hidden = v !== 'results';
    $('matchView').hidden = v !== 'match';
    const slot = v === 'results' ? $('resultsSlotSearch') : $('resultsSlotMatch');
    if ($('resultsSection').parentElement !== slot) slot.appendChild($('resultsSection'));
    if (v !== 'match') { stopReel(); $('stageVideo').pause(); }
    $('backToResults').hidden = !(v === 'match' && search.asked);
    // The realism report is about one match, so it is offered only where that match is on screen.
    $('reportLine').hidden = v !== 'match';
    if (v !== 'match') { $('report').hidden = true; $('reportToggle').setAttribute('aria-expanded', 'false'); }
    layoutPanel();
    if (v === 'results' || (v === 'match' && state.info)) render();
    if (sync) syncUrl();
  }

  function layoutPanel() {
    const on = state.view === 'match' || (state.view === 'results' && engine() === 'foundry');
    $('convo').hidden = !on;
    $('work').classList.toggle('with-convo', on);
    $('work').classList.toggle('in-match', state.view === 'match');
    // The panel's box asks this match in the match view, every match on the results.
    const here = state.view === 'match';
    const text = here ? 'Ask about this match' : 'Ask a follow-up across every match';
    $('fq').placeholder = text; $('fqLabel').textContent = text;
    const cosmosOnly = here && state.info?.source === 'cosmos';
    $('fq').disabled = cosmosOnly; $('go').disabled = cosmosOnly || chat.busy;
    engineHint();
  }

  // ------------------------------------------------------------------ links into the page

  // /?match={id}&player={per-match player id}&clip={clip id}&t={seconds}: the Scout pages link to a moment this way.
  // Values that do not look like ids are dropped here; ids no match has fall back quietly to the featured match.
  const LINK_ID = /^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$/;
  function readLink() {
    const q = new URLSearchParams(location.search);
    const id = (k) => { const v = q.get(k); return v && LINK_ID.test(v) && !v.includes('..') ? v : null; };
    const t = Number(q.get('t'));
    return { match: id('match'), player: id('player'), clip: id('clip'), t: q.get('t') !== null && Number.isFinite(t) && t >= 0 ? t : null,
             recap: q.get('recap') === '1' };
  }
  const playerOfClip = (cid) => /^cl_(.+)_\d{6}$/.exec(cid || '')?.[1] || null;  // clip ids are cl_{player id}_{number}

  // The URL follows what is on screen (match, player, the moment picked), so it can be shared. Within a view it is
  // replaced: picking moments, players or matches does not fill the back button; moving between views pushes an entry
  // (showView), so Back goes from a match to the results and from the results to the landing. Each entry keeps what
  // it showed, for popstate. Home's landing and results have no match, so their URL is plain /.
  function syncUrl() {
    if (!window.history?.replaceState) return;
    let url = location.pathname;
    const entry = { view: state.view, from: history.state?.from || null };  // from: the view this entry was pushed from
    if (state.view === 'match' && state.match) {
      const q = new URLSearchParams({ match: state.match });
      if (state.player) q.set('player', state.player);
      if (state.picked) q.set('clip', state.picked);
      url = `${location.pathname}?${q}`;
      Object.assign(entry, { match: state.match, player: state.player, clip: state.picked });
    }
    try { history.replaceState(entry, '', url); } catch (e) { /* the page still works */ }
  }

  // Back and Forward: show the view the entry was, as it was left. Results that are gone (a "start over") show the
  // landing instead.
  async function onPopState(e) {
    const s = e.state || {};
    if (s.view === 'match' && s.match) {
      showView('match', { sync: false });
      if (s.match !== state.match || !state.info) {
        if (!(await loadMatch(s.match, { player: s.player, quiet: true }))) return showView(search.asked ? 'results' : 'landing');
      } else if (s.player && s.player !== state.player && player(s.player)) {
        $('player').value = s.player; await pickPlayer(s.player);
      }
      if (s.clip && state.all.has(s.clip)) { state.selected = s.clip; state.picked = s.clip; renderStage(false); markPlaying(s.clip); }
      return syncUrl();
    }
    const v = s.view === 'results' && search.asked ? 'results' : 'landing';
    showView(v);
    window.scrollTo(0, 0);
    $(v === 'results' ? 'rq' : 'q').focus({ preventScroll: true });
  }

  // The moment a link asked for: the clip itself, else the moment nearest to t (among the linked player's moments when
  // the link names one, else anyone's, picking its player), with the full-match video set to start at t.
  async function openLinked(link) {
    if (link.clip && state.all.has(link.clip)) return select(link.clip, true, true);
    if (link.t === null) return;
    const dist = (c) => c.t <= link.t && link.t <= c.t_end ? 0 : Math.min(Math.abs(c.t - link.t), Math.abs(c.t_end - link.t));
    const mine = link.player === state.player ? [...state.all.values()].filter(c => c.player_id === state.player) : [];
    const near = (mine.length ? mine : [...state.all.values()]).reduce((a, c) => (!a || dist(c) < dist(a) ? c : a), null);
    if (near && near.player_id !== state.player && player(near.player_id)) { $('player').value = near.player_id; await pickPlayer(near.player_id); }
    $('fullMatch').href = `${matchUrl('/video.mp4')}#t=${Math.round(link.t)}`;
    if (near) select(near.id, true, true);
  }

  // ------------------------------------------------------------------ loading

  let seasonReady = Promise.resolve(), catalogueReady = Promise.resolve();

  async function init() {
    wire();
    startPrompts();
    loadHealth();
    try {
      state.matches = await R.api('/api/matches');
    } catch (e) {
      if (offline(e)) { fatal(''); return showNetError(OFFLINE, init); }
      return fatal(`Regista could not list its matches: ${detail(e)}`);
    }
    hideNetError();
    const link = readLink();
    // The featured match first, then the others as the server lists them; the league's matches join later (loadSeason).
    const first = state.matches.length ? featured() : null;
    state.matches = [first, ...state.matches.filter(m => m !== first)].filter(Boolean);
    $('match').innerHTML = state.matches.map(m => `<option value="${esc(m.match_id)}">${esc(matchName(m))}</option>`).join('');
    seasonReady = loadSeason();  // not awaited: the first paint never waits for the league
    catalogueReady = loadCatalogue();  // nor for the catalogue's other competitions
    recapView.wanted = link.recap;  // the profile's "Recap" link: open the recap and scroll to it as soon as it is written
    if (link.match) {
      showView('match');
      if (await loadMatch(link.match, { player: link.player || playerOfClip(link.clip), quiet: true })) {
        await openLinked(link);
        if (recapView.wanted) openRecap();
        return syncUrl();
      }
    }
    showView('landing');
    if (location.search && window.history?.replaceState) history.replaceState({ view: 'landing' }, '', location.pathname);  // a link that led nowhere
    if (!first) {
      await seasonReady;
      if (!state.season.length) return fatal('There are no matches on this server yet.');
      return loadMatch(state.season[0].match_id);
    }
    await loadMatch(first.match_id);  // in the background of Home: it fills the Match and Player pickers
  }

  // The Regista League's matches, in round order, in their own group under the matches above. Season matches are
  // ordinary matches to the API, so nothing else on the page treats them differently. No league on this server, or no
  // answer: the picker keeps what it has (and Home searches the matches it has).
  async function loadSeason() {
    let s;
    try { s = await R.api('/api/season'); } catch (e) { return; }
    const ms = (s.rounds || []).flatMap(r => r.matches || []);
    if (!ms.length) return;
    state.season = ms;
    state.clubs = new Map((s.clubs || []).map(c => [c.club_id, c.short_name]));
    const sel = $('match'), keep = sel.value;
    const g = seasonGroup();
    g.label = [s.league, s.season].filter(Boolean).join(' ') || g.label;
    g.innerHTML = ms.map(m => `<option value="${esc(m.match_id)}">${esc(m.title || `Round ${m.round}: ${m.home_name} v ${m.away_name}`)}</option>`).join('');
    if (keep) sel.value = keep;
  }

  function seasonGroup() {
    let g = $('seasonGroup');
    if (!g) {
      g = Object.assign(document.createElement('optgroup'), { id: 'seasonGroup', label: 'Regista League 2026/27' });
      $('match').appendChild(g);
    }
    return g;
  }

  // The catalogue: every uploaded match, grouped by country and competition, each with its round, score, date, camera and
  // who uploaded it. The Regista League's own group (loadSeason) keeps its matches and takes the same words; every other
  // competition joins the picker as its own group. /api/matches keeps its shape: nothing here changes it. No catalogue on
  // this server, or no answer: the picker keeps what it has.
  async function loadCatalogue() {
    let ix, ms = [];
    try {
      ix = await R.api('/api/catalogue');
      for (let offset = 0, total = Infinity; offset < total;) {
        const j = await R.api(`/api/catalogue/matches?limit=200&offset=${offset}`);
        ms.push(...(j.matches || [])); total = j.total;
        if (!(j.matches || []).length) break;
        offset += j.matches.length;
      }
    } catch (e) { return; }
    const words = new Map((((ix.levels || {}).pools) || []).map(l => [l.key, l.words]));
    for (const c of ix.competitions || []) state.comps.set(c.competition_id, { ...c, level_words: words.get(`${c.tier}/${c.age_group}/${c.gender}`) || c.tier });
    for (const m of ms) state.catalogue.set(m.match_id, m);
    await seasonReady;
    const sel = $('match'), keep = sel.value;
    const opt = (m) => `<option value="${esc(m.match_id)}">${esc(`${matchWords(m)} · ${fmtDate(m.date)} · ${CAMS[m.camera] || m.camera} · ${m.uploader && m.uploader.type === 'player' ? 'uploaded by a player' : 'uploaded by a team account'}`)}</option>`;
    const byComp = (cid) => ms.filter(m => m.competition_id === cid).sort((a, b) => String(a.date).localeCompare(String(b.date)) || (a.round || 0) - (b.round || 0));
    const label = (c) => `${c.country} · ${c.name} (${c.level_words})`;
    for (const c of state.comps.values()) {
      const list = byComp(c.competition_id); if (!list.length) continue;
      // The league's group is already there (its matches are /api/season's): same words, same ids.
      const g = c.competition_id === 'co_eng_sp_men' && state.season.length ? seasonGroup()
        : Object.assign(document.createElement('optgroup'), { className: 'catgroup' });
      g.label = label(c);
      g.innerHTML = list.map(opt).join('');
      if (!g.parentElement) sel.appendChild(g);
    }
    if (keep) sel.value = keep;
    // Home's "Or open a match": the same list, with its own first line.
    $('homeMatch').innerHTML = `<option value="">${esc(`Pick one of the ${sel.options.length} matches…`)}</option>${sel.innerHTML}`;
    $('homeMatch').value = '';
    $('homePick').hidden = false;
    if (state.info) showMatchLine(state.matches.find(m => m.match_id === state.match) || state.info);
  }

  // A match opened by a link before the league's list arrived (or one not listed at all) still gets its option.
  function ensureOption(id, info) {
    if ([...$('match').options].some(o => o.value === id)) return;
    const o = Object.assign(document.createElement('option'), { value: id, textContent: matchName(info) });
    (id.startsWith('rl_') ? seasonGroup() : $('match')).appendChild(o);
  }

  // The match the page opens on: the one the server marks featured, else the one with video and the most clips.
  function featured() {
    const marked = state.matches.find(m => m.featured);
    if (marked) return marked;
    const withVideo = state.matches.filter(m => m.video);
    return [...(withVideo.length ? withVideo : state.matches)].sort((a, b) => (b.clip_count || 0) - (a.clip_count || 0))[0];
  }

  function fatal(text) {
    state.head = 'Moments'; $('resultsHead').textContent = 'Moments';
    showEmpty(esc(text));
    $('stage').hidden = true;
    $('landingNote').textContent = text; $('landingNote').hidden = !text;
  }

  // A switch loads everything first and only then replaces what is on screen: if it fails, the picker goes back to the
  // match still shown, so the page never mixes two matches.
  // quiet: a link's match, which falls back to Home if it fails, so a failure here says nothing.
  async function loadMatch(id, { player: wanted = null, quiet = false } = {}) {
    const previous = state.info ? state.match : null;
    $('match').disabled = true;
    if (!previous) showEmpty('Loading the match…');
    let info, clips;
    try {
      [info, clips] = await Promise.all([R.api(matchUrl('', id)), R.api(matchUrl('/clips', id))]);
    } catch (e) {
      $('match').disabled = false;
      if (previous) $('match').value = previous;
      if (quiet && !previous) return false;
      if (offline(e)) return showNetError(OFFLINE, () => loadMatch(id));
      if (previous) return showNetError(`That match could not be loaded: ${detail(e)}`, () => loadMatch(id));
      return fatal(`This match could not be loaded: ${detail(e)}`);
    }
    $('match').disabled = false;
    hideNetError();
    ensureOption(id, info);
    state.match = id; state.info = info; state.picked = null; $('match').value = id;
    state.all = new Map(clips.map(c => [c.id, { ...c, title: c.label?.title }]));
    state.loaded = new Set(info.players_with_clips || []);
    $('stage').hidden = false;
    const listed = state.matches.find(m => m.match_id === id);
    showMatchLine(listed || info);
    fillPlayers(wanted || listed?.clips_for);
    $('fullMatch').href = matchUrl('/video.mp4');
    $('fullMatch').hidden = state.info.source === 'cosmos';
    // A league match runs 30 minutes: its first full view renders the whole video, which takes minutes, so a note under
    // the stage's actions says so (the button keeps a short label, so the four actions stay on one row).
    const long = (state.info.duration_s || 0) > 600;
    $('fullMatch').textContent = 'Watch the full match';
    $('fullMatchNote').hidden = !long || $('fullMatch').hidden;
    if (long) $('fullMatch').setAttribute('aria-describedby', 'fullMatchNote'); else $('fullMatch').removeAttribute('aria-describedby');
    report.loaded = null; $('report').hidden = true; $('reportToggle').setAttribute('aria-expanded', 'false');
    await newConversation();
    layoutPanel();  // a match read from Cosmos DB cannot answer questions: the panel's box says so
    return true;
  }

  // The match's name and, for a match cut from video, what the badge means. (Its explainer line is not shown.)
  // A catalogue match adds a line under its title: competition, country, level, date, who uploaded it and the camera they
  // named (joined here from the catalogue's list, so /api/matches/{id} keeps its shape).
  function showMatchLine(m) {
    $('matchTitle').textContent = matchName({ ...m, title: m.title || state.info.title, teams: m.teams || state.info.teams });
    $('visionNote').hidden = state.info.origin !== 'vision';
    const cm = state.catalogue.get(state.match), comp = cm && state.comps.get(cm.competition_id);
    $('matchMeta').hidden = !cm;
    $('matchMeta').textContent = cm ? [comp ? `${comp.name} · ${comp.country} · ${levelOf(comp)}` : cm.competition, fmtDate(cm.date), upWords(cm.uploader),
      cm.camera ? `filmed on a ${CAMS[cm.camera] || cm.camera} (the uploader's label)` : ''].filter(Boolean).join(' · ') : '';
  }

  // Players with moments first (most first), then everyone else. Any player can be picked: the server finds the
  // moments of a player it has not cut yet.
  function fillPlayers(preferred) {
    const label = (p) => {
      const n = momentsOf(p.player_id);
      return `${esc(p.name)} · ${esc(p.kit_number)} · ${esc(team(p.team_id)?.name || p.team_id)}${n ? ` · ${esc(plural(n, 'moment'))}` : ''}`;
    };
    const opt = (p) => `<option value="${esc(p.player_id)}">${label(p)}</option>`;
    const ps = [...state.info.players].sort((a, b) => a.team_id.localeCompare(b.team_id) || (a.kit_number - b.kit_number));
    const have = ps.filter(p => momentsOf(p.player_id)).sort((a, b) => momentsOf(b.player_id) - momentsOf(a.player_id));
    const rest = ps.filter(p => !momentsOf(p.player_id));
    $('player').innerHTML = (have.length ? `<optgroup label="Players with moments">${have.map(opt).join('')}</optgroup>` : '')
      + (rest.length ? `<optgroup label="No moments in this match">${rest.map(opt).join('')}</optgroup>` : '');
    state.player = (preferred && player(preferred) ? preferred : null) || have[0]?.player_id || ps[0]?.player_id;
    $('player').value = state.player;
  }

  // The picked player's moments: GET /clips?player= returns the clips on disk, or derives them for a player who has none.
  async function loadPlayerClips(pid) {
    if (!pid || state.loaded.has(pid) || state.info?.source === 'cosmos') return;
    const clips = await R.api(matchUrl(`/clips?player=${enc(pid)}`));
    for (const c of clips) state.all.set(c.id, { ...c, title: c.label?.title });
    state.loaded.add(pid);
  }

  async function pickPlayer(pid) {
    const before = state.player;
    state.player = pid;
    $('resultsHead').textContent = 'Moments'; showEmpty('Finding the moments…'); $('grid').innerHTML = '';
    try {
      await loadPlayerClips(pid);
    } catch (e) {
      state.player = before; $('player').value = before;
      showMatchMoments();
      return showNetError(offline(e) ? OFFLINE : `That player's moments could not be loaded: ${detail(e)}`, () => { $('player').value = pid; pickPlayer(pid); });
    }
    hideNetError();
    state.picked = null;
    await newConversation();
    syncUrl();
  }

  // ------------------------------------------------------------------ the landing: prompts that type themselves

  // Example prompts type themselves into the empty search box and back out, one after another. They pause while the
  // box has focus or text in it, and stay still for people who prefer less motion. Tab fills in the prompt showing.
  const PROMPTS = [
    'Find me the best saves this season',
    'Show me every header this season',
    'Find me all the nutmegs',
    'Show me take-ons in the final third',
    'Find me every assist, best first',
    'Show me Femi Toure\'s goals, assists and shots',
  ];
  const typing = { p: 0, n: 0, up: true, shown: '' };

  function startPrompts() {
    const q = $('q');
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    q.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey && !q.value && typing.shown) { e.preventDefault(); q.value = PROMPTS[typing.p]; }
    });
    q.addEventListener('focus', () => { if (!q.value) q.placeholder = typing.shown; });
    q.addEventListener('blur', () => { if (!q.value) q.placeholder = typing.shown; });
    if (still) { typing.shown = PROMPTS[0]; q.placeholder = PROMPTS[0]; return; }
    const tick = () => {
      if ($('landing').hidden || document.activeElement === q || q.value) return setTimeout(tick, 400);
      const text = PROMPTS[typing.p];
      if (typing.up) {
        typing.n++; typing.shown = text.slice(0, typing.n); q.placeholder = `${typing.shown}|`;
        if (typing.n >= text.length) { typing.up = false; q.placeholder = typing.shown; return setTimeout(tick, 1800); }
        return setTimeout(tick, 45 + Math.random() * 40);
      }
      typing.n--; typing.shown = text.slice(0, typing.n); q.placeholder = `${typing.shown}|`;
      if (typing.n <= 0) { typing.up = true; typing.p = (typing.p + 1) % PROMPTS.length; return setTimeout(tick, 400); }
      return setTimeout(tick, 22);
    };
    tick();
  }

  // ------------------------------------------------------------------ the conversation: shared pieces

  const engine = () => ui.engine;

  // The three "Who answers" switches (landing, results bar, panel) are one choice.
  function setEngine(v) {
    ui.engine = v;
    for (const r of document.querySelectorAll('input[name="engine"], input[name="rengine"], input[name="fengine"]')) r.checked = r.value === v;
    layoutPanel();
  }

  function engineHint() {
    if (state.view === 'match' && state.info?.source === 'cosmos') { $('engineHint').textContent = COSMOS_HINT; return; }
    const h = state.health;
    const where = state.view === 'match' ? 'Questions here search this match.' : 'Questions here search every match.';
    $('engineHint').textContent = engine() === 'rules'
      ? `Data Search: Regista's own rules find the moments and write the reply, with no AI model. Follow-ups build on what you asked; "start over" clears it. ${where}`
      : (h && !h.cloud.foundry
        ? `Foundry is not set up on this server, so Regista's rules will write the reply. The moments found are the same. ${where}`
        : `Ask Microsoft Foundry: the same search, then a Microsoft Foundry model writes the reply and may call its tools. Takes a few seconds. ${where}`);
  }

  function logChanged() {
    const empty = !$('log').children.length;
    $('log').hidden = empty; $('logEmpty').hidden = !empty;
    $('log').scrollTop = $('log').scrollHeight;
  }

  function addMsg(cls, html) {
    const div = document.createElement('div');
    div.className = `msg ${cls}`;
    div.innerHTML = html;
    $('log').appendChild(div);
    logChanged();
    const how = div.querySelector('details');
    if (how) how.addEventListener('toggle', () => { if (how.open) how.scrollIntoView({ block: 'nearest' }); });
    return div;
  }

  // Which matches a reply searched, on the first line of the reply.
  const where = (text) => `<span class="where">${esc(text)}</span>`;

  function busy(on) {
    chat.busy = on;
    $('homeGo').disabled = on; $('barGo').disabled = on;
    $('go').disabled = on || (state.view === 'match' && state.info?.source === 'cosmos');
  }

  function errorText(e, scope) {
    return offline(e) ? OFFLINE : e.status === 429 ? detail(e)
      : e.status === 404 ? 'This match is not on this server any more. Pick another match.' : `${scope}: ${detail(e)}`;
  }

  function addError(e, scope, retry) {
    const err = addMsg('bot err', esc(errorText(e, scope)));
    if (offline(e) || e.status >= 500) {
      const b = Object.assign(document.createElement('button'), { type: 'button', className: 'alt retry', textContent: 'Retry' });
      b.onclick = () => { err.remove(); logChanged(); retry(); };
      err.appendChild(b);
      $('log').scrollTop = $('log').scrollHeight;
    }
    return err;
  }

  // ------------------------------------------------------------------ Home: search every match

  // Every match Home can search: the library's (in the picker's order, featured first) and the league's, in round
  // order. A match read from Cosmos DB without its event stream cannot answer questions, so it is left out (and said).
  function searchList() {
    const list = [], seen = new Set();
    let skipped = 0;
    for (const m of [...state.matches, ...state.season, ...state.catalogue.values()]) {
      if (seen.has(m.match_id)) continue;
      seen.add(m.match_id);
      if (m.source === 'cosmos') { skipped++; continue; }
      const cm = state.catalogue.get(m.match_id);
      list.push({ id: m.match_id, name: m.home_name ? (m.title || `Round ${m.round}: ${m.home_name} v ${m.away_name}`) : matchName(m),
                  card: cardLine(m), library: !m.home_name, idx: list.length, comp: cm ? cm.competition_id : '', cm: cm || null });
    }
    return { list, skipped };
  }
  const nameOf = (mid) => searchList().list.find(m => m.id === mid)?.name || 'a match';

  // The short line on a result card that says which match it comes from: "Round 2 · EAS v ASH" for a league match,
  // the match's own name for the library's.
  // A catalogue match: "Round 1 · Eastwick United 0–2 Brookfield Rovers · Regista League" (full club names: a code means
  // nothing for a club a scout does not know).
  function cardLine(m) {
    const cm = state.catalogue.get(m.match_id);
    if (cm) return `${matchWords(cm)} · ${cm.competition}`;
    if (!m.home_name) return matchName(m);
    const short = (club, name) => state.clubs.get(club) || name;
    return `Round ${m.round} · ${short(m.home, m.home_name)} v ${short(m.away, m.away_name)}`;
  }

  // Runs fn over items, at most n at a time; the results keep the items' order.
  async function pool(items, n, fn) {
    const out = new Array(items.length);
    let i = 0;
    const worker = async () => { while (i < items.length) { const k = i++; out[k] = await fn(items[k], k); } };
    await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
    return out;
  }

  // Each match reads a name in the question on its own, so "Femi Toure" can mean Femi Rahman in a match Toure did not
  // play. The names the question really says: players with results whose full name is in it, else whose surname is.
  // null: the question names no one with a result (then every match's answer stands).
  const FOOTBALL_WORDS = /^(shot|shots|header|headers|cross|crosses|pass|passes|goal|goals|save|saves|ball|best|top|more|tackle|tackles)$/;
  const words = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);
  function namesIn(message, results) {
    const said = new Set(words(message));
    const names = [...new Set(results.map(r => r.player).filter(Boolean))];
    const full = names.filter(n => words(n).length > 1 && words(n).every(w => said.has(w)));
    if (full.length) return new Set(full);
    const sur = names.filter(n => { const w = words(n); return w.length > 1 && !FOOTBALL_WORDS.test(w[w.length - 1]) && said.has(w[w.length - 1]); });
    return sur.length ? new Set(sur) : null;
  }
  const resolved = (st) => (st?.player_ids || []).length > 0 || !!st?.team_id;
  const carriedFilters = (st) => (st?.tags || []).length || (st?.reasons || []).length || st?.minutes;

  // One question to every match: each match's own /chat (the Instant engine: no model) with that match's query so far,
  // merged best first. With Ask Microsoft Foundry, Foundry then writes the reply once, from the match with the best
  // result (the /chat Foundry engine reads one match). fresh: a new search from the landing; withStates: the queries to
  // send instead of the current ones (a Retry, or the server's way out); only: just these matches ("Show more").
  async function searchEvery(message, { fresh = false, withStates = null, only = null, quiet = false, focus = null } = {}) {
    if (!message || chat.busy) return null;
    busy(true);
    await seasonReady; await catalogueReady;
    const { list: everyMatch, skipped } = searchList();
    const list = only ? everyMatch.filter(m => only.includes(m.id)) : everyMatch;
    if (fresh) { search.states = new Map(); search.names = null; }
    const before = new Map(search.states);
    const eng = engine();
    showView('results', { push: true });
    if (message !== 'more') $('rq').value = message;
    addMsg('me', esc(message));
    const wait = addMsg('bot wait', eng === 'foundry' ? 'Searching every match, then asking Microsoft Foundry to write the reply…' : 'Searching every match…');
    if (!list.length) {
      wait.remove(); logChanged();
      addMsg('bot err', esc('There are no matches on this server to search.'));
      announce('There are no matches on this server to search.');
      busy(false);
      return null;
    }
    const progress = (done) => {
      $('resultsHead').textContent = 'Searching every match…';
      $('grid').innerHTML = ''; $('tagbar').hidden = true; $('more').hidden = true;
      showEmpty(esc(`Searching every match… ${done} of ${list.length}`));
    };
    if (search.results.length === 0 || message !== 'more') progress(0);
    const t0 = performance.now();
    let done = 0;
    const outs = await pool(list, PARALLEL, async (m) => {
      const st = withStates ? (withStates.get(m.id) ?? null) : (search.states.get(m.id) ?? null);
      try {
        const out = await R.api(matchUrl('/chat', m.id), { method: 'POST', body: { message, state: st, history: [], engine: 'rules' } });
        return { m, out, st };
      } catch (e) {
        return { m, err: e, st };
      } finally {
        done++;
        if (message !== 'more') progress(done);
      }
    });
    const wall = performance.now() - t0;
    const oks = outs.filter(o => o.out), bad = outs.filter(o => o.err);
    if (!oks.length) {
      wait.remove(); logChanged();
      const e = bad[0]?.err;
      addError(e, 'Regista could not search the matches', () => searchEvery(message, { withStates: before, only }));
      search.head = 'Moments';
      if (message !== 'more') { search.results = []; search.total = 0; }
      search.wayout = offline(e) || e?.status >= 500 ? { label: 'Retry', go: () => searchEvery(message, { withStates: before, only }) } : null;
      render(esc(errorText(e, 'Regista could not search the matches')));
      announce(errorText(e, 'Regista could not search the matches'));
      busy(false);
      if (!quiet) $(focus || 'rq')?.focus();
      return null;
    }
    for (const o of oks) search.states.set(o.m.id, o.out.state);
    const intent = oks[0].out.intent;
    if (intent === 'reset') {
      wait.remove(); logChanged();
      addMsg('bot', `${where('Every match')}${esc(oks[0].out.reply)}`);
      chat.history = [];
      resetSearch();
      busy(false);
      showView('landing');
      if (!quiet) $('q').focus();
      return oks[0].out;
    }

    // Which answers count: if the question named someone in some matches, the matches where it named no one drop out;
    // then, if it says a player's name, only that player's moments.
    const kept = oks.some(o => resolved(o.out.state)) ? oks.filter(o => resolved(o.out.state)) : oks;
    const named = namesIn(message, kept.flatMap(o => o.out.results || []));
    if (named) search.names = named;
    const newRows = [];
    for (const o of oks) {
      const keep = kept.includes(o);
      const rows = keep ? (o.out.results || []).filter(c => !search.names || search.names.has(c.player)) : [];
      const partial = keep && rows.length < (o.out.results || []).length;
      const total = keep ? (partial ? rows.length : (o.out.total ?? rows.length)) : 0;
      const pm = search.perMatch.get(o.m.id);
      search.perMatch.set(o.m.id, intent === 'more' && pm ? { total: Math.max(pm.total, total), counted: pm.counted } : { total, counted: true });
      for (const c of rows) newRows.push(row(c, { mid: o.m.id, idx: o.m.idx }));
    }
    if (intent !== 'more') for (const m of everyMatch) if (!oks.some(o => o.m.id === m.id) && !only) search.perMatch.set(m.id, { total: 0, counted: true });
    await loadSearchDetails([...new Set(newRows.map(r => r.mid))]);
    const fixed = newRows.map(r => row(r.raw, { mid: r.mid, idx: r.idx }));  // now with each match's label models
    search.results = intent === 'more' ? [...search.results, ...fixed.filter(r => !search.results.some(x => x.mid === r.mid && x.id === r.id))] : fixed;
    search.total = Math.max(search.results.length, [...search.perMatch.values()].reduce((a, p) => a + (p.total || 0), 0));
    search.fromQuestion = true; search.tag = null; search.asked = true;
    if (intent !== 'more') { search.comp = ''; search.expanded = new Set(); }
    const best = sorted(search.results, { sort: 'best' });
    const topMid = best[0]?.mid || kept[0]?.m.id || list[0].id;
    const top = oks.find(o => o.m.id === topMid) || kept[0] || oks[0];
    const understood = top.out.understood || '';
    // The server keeps the order asked for in state.order ("time" after "in match order").
    const prevOrder = top.st?.order;
    if (top.out.state?.order === 'time') setSort('time', search);
    else if ((prevOrder === 'time' && top.out.state?.order === null) || /\bbest\b|\btop\b/i.test(message)) setSort('best', search);

    // Ask Microsoft Foundry: one Foundry reply, written from the match with the best result.
    let fout = null, ferr = null;
    if (eng === 'foundry') {
      try {
        fout = await R.api(matchUrl('/chat', topMid), { method: 'POST', body: { message, state: top.st ?? null, history: chat.history, engine: 'foundry' } });
        search.states.set(topMid, fout.state);
      } catch (e) { ferr = e; }
    }
    wait.remove(); logChanged();
    const matchesWith = new Set(search.results.map(r => r.mid)).size;
    const composed = !search.total ? `Nothing in any match for ${understood || 'that'}.`
      : `${plural(search.total, 'moment')} in ${plural(matchesWith, 'match', 'matches')} · ${understood}. Best: ${best[0].title}, ${nameOf(best[0].mid)}.`;
    const foundryWrote = fout && String(fout.answered_by || '').startsWith('foundry');
    const out = {
      reply: foundryWrote ? fout.reply : composed, understood, total: search.total, intent,
      answered_by: fout ? fout.answered_by : 'rules', tools_used: fout?.tools_used || [], state: { player_ids: [] },
      trace: [...aggregate(oks), ...(fout?.trace || []).filter(s => s.kind !== 'step')],
      every: { searched: oks.length, matchesWith, ms: wall },
    };
    const scope = foundryWrote ? `<span class="scope">Microsoft Foundry wrote this from ${esc(nameOf(topMid))}, the match with the best result. `
      + 'The moments in the grid come from every match.</span>' : '';
    const msg = addMsg('bot', `${where('Every match')}${esc(out.reply)}${scope}${fallbackLine(out, eng)}${howAnswered(out, eng)}`);
    if (ferr) addError(ferr, 'Microsoft Foundry could not write the reply', () => searchEvery(message, { withStates: before, only }));
    if (!foundryWrote) chat.history = [...chat.history, { role: 'user', text: message }, { role: 'assistant', text: composed.slice(0, 600) }].slice(-12);
    else chat.history = fout.history;

    // The way out when piled-up filters leave nothing: the server's own suggestion, else all of the named player.
    search.wayout = null;
    if (!search.total && intent !== 'more') {
      const sug = oks.find(o => o.out.suggest?.message)?.out.suggest;
      const names = search.names ? [...search.names] : [];
      if (sug) {
        search.wayout = { label: sug.label || sug.message.charAt(0).toUpperCase() + sug.message.slice(1),
                          go: () => searchEvery(sug.message, { withStates: new Map(oks.map(o => [o.m.id, o.out.suggest?.state || null])) }) };
      } else if (names.length === 1 && oks.some(o => carriedFilters(o.out.state))) {
        search.wayout = { label: `Show all of ${names[0]}'s moments`, go: () => searchEvery(names[0], { fresh: true }) };  // set as textContent
      }
      if (search.wayout) {
        const b = Object.assign(document.createElement('button'), { type: 'button', className: 'alt wayout', textContent: search.wayout.label });
        const go = search.wayout.go;
        b.onclick = () => { b.disabled = true; go(); };
        msg.insertBefore(b, msg.querySelector('details.how'));
      }
    }

    searchNote(everyMatch.length, skipped, bad.length);
    search.head = `${esc(plural(search.total, 'moment'))} <span class="muted">· ${esc(understood)}</span>`;
    const carried = oks.some(o => carriedFilters(o.out.state));
    busy(false);
    render(search.results.length ? ''
      : carried && !/^(start over|reset)/i.test(message)
        ? `Nothing for ${esc(understood || 'that')} in any match. Filters from earlier questions still apply: ${search.wayout ? 'use the button below' : 'change the question'}, or say "start over".`
        : 'Nothing matched that question in any match. Try a player\'s surname, a kit number, or an action like "nutmeg" or "shot".');
    if (state.view !== 'results') return out;  // a card was opened meanwhile: stay with it
    announce(out.reply);
    if (message !== 'more') window.scrollTo(0, 0);
    if (search.sort === 'time' && intent === 'search') await fillEveryMatchOrder(kept);
    if (search.results.length && (oks.some(o => (o.out.reel || []).length) || /\b(reel|montage|compilation)\b/i.test(message))) await reelFromSearch(kept);
    if (!quiet && state.view === 'results') $(focus || 'rq')?.focus();
    return out;
  }

  // The results' own polite status (#resultsStatus, visually hidden): says what a search found when the conversation
  // panel, whose log is the other live region, is hidden (Data Search on the results). Cleared first, so the same
  // words twice are read twice.
  function announce(text) {
    const el = $('resultsStatus');
    el.textContent = '';
    if (!$('convo').hidden || !text) return;
    setTimeout(() => { if ($('convo').hidden) el.textContent = text; }, 60);
  }

  function resetSearch() {
    search.states = new Map(); search.perMatch = new Map(); search.names = null; search.results = []; search.total = 0;
    search.tag = null; search.reel = null; search.asked = false; search.wayout = null; search.head = 'Moments'; search.emptyHtml = '';
    $('searchNote').hidden = true;
  }

  // Each match's own steps, added up: one line per step name, with how many matches ran it (each counted once), how
  // many times it ran in all (a match can run a step twice) and their time together.
  function aggregate(oks) {
    const byName = new Map();
    for (const o of oks) for (const s of o.out.trace || []) {
      const k = [s.kind, s.name, s.server || ''].join('|');  // a key, never shown
      const a = byName.get(k) || { kind: s.kind, name: s.name, server: s.server, ms: 0, runs: 0, mids: new Set() };
      a.ms += Number(s.ms) || 0; a.runs += 1; a.mids.add(o.m.id);
      byName.set(k, a);
    }
    return [...byName.values()].map(({ mids, ...a }) => ({ ...a, n: mids.size }));
  }

  // What the results do not cover: matches read from Cosmos DB without their event stream, matches that did not answer,
  // and the players a name in the question left out.
  function searchNote(n, skipped, failed) {
    const parts = [];
    if (failed) parts.push(`Regista could not search ${failed} of ${plural(n, 'match', 'matches')}.`);
    if (skipped) parts.push(`${plural(skipped, 'match', 'matches')} read from Cosmos DB without ${skipped === 1 ? 'its' : 'their'} event stream cannot be searched.`);
    if (search.names) parts.push(`Only ${[...search.names].join(' and ')}: where a name in the question meant another player, that match is left out.`);
    $('searchNote').textContent = parts.join(' ');
    $('searchNote').hidden = !parts.length;
  }

  // What the cards need from each match that found something: its origin ("Cut from video") and, for the library's
  // matches, its clips' label models ("Labelled by Microsoft Foundry"). Read once per match; a failure only loses badges.
  async function loadSearchDetails(mids) {
    const library = new Set(searchList().list.filter(m => m.library).map(m => m.id));
    await pool(mids.filter(mid => !search.infos.has(mid)), PARALLEL, async (mid) => {
      try { search.infos.set(mid, await R.api(matchUrl('', mid))); } catch (e) { return; }
      if (!library.has(mid)) return;  // a league match's clips are hundreds of rows, all labelled by Regista's rules
      try { search.clips.set(mid, new Map((await R.api(matchUrl('/clips', mid))).map(c => [c.id, c]))); } catch (e) { /* no badge */ }
    });
  }

  // "In match order" means every moment from kick-off: the server returns them all in one page; an older server pages
  // them, so the page fetches each match's remaining pages itself (Instant engine, no lines in the conversation).
  async function fillEveryMatchOrder(kept) {
    for (const o of kept) {
      const pm = search.perMatch.get(o.m.id);
      let st = search.states.get(o.m.id);
      for (let i = 0; i < 10 && pm && search.results.filter(r => r.mid === o.m.id).length < pm.total; i++) {
        let out;
        try {
          out = await R.api(matchUrl('/chat', o.m.id), { method: 'POST', body: { message: 'more', state: st, history: [], engine: 'rules' } });
        } catch (e) { break; }
        const fresh = (out.results || []).filter(c => !search.names || search.names.has(c.player)).map(c => row(c, { mid: o.m.id, idx: o.m.idx }))
          .filter(r => !search.results.some(x => x.mid === r.mid && x.id === r.id));
        if (!fresh.length) break;
        st = out.state;
        search.results = [...search.results, ...fresh];
      }
      search.states.set(o.m.id, st);
    }
    render();
  }

  // A reel is one match's (the reel endpoint takes one match): a reel asked for on the results plays the best match's
  // part of them, in that match's view.
  async function reelFromSearch(kept) {
    const top = sorted(search.results, { sort: 'best' })[0];
    if (!top) return;
    const o = kept.find(x => x.m.id === top.mid);
    const rows = sorted(search.results.filter(r => r.mid === top.mid), { sort: 'best' });
    const ids = o?.out.reel?.length ? o.out.reel.map(c => c.clip_id) : rows.map(r => r.id);
    await openResult(top.mid, top.id, { part: { rows, reel: ids, understood: o?.out.understood || '' } });
  }

  // A card on the results opens its match: the full match view, that moment on the stage, its player's moments below.
  // part: open with this match's share of the results instead (a reel asked for on the results).
  async function openResult(mid, id, { part = null } = {}) {
    const pid = playerOfClip(id);
    const pushed = state.view !== 'match';
    showView('match', { sync: false, push: true });  // the URL changes once the moment is on the stage
    window.scrollTo(0, 0);
    if (mid !== state.match || !state.info) {
      if (!(await loadMatch(mid, { player: pid }))) { if (pushed && history.state?.view === 'match') history.back(); else if (search.asked) showView('results'); return; }
    } else if (pid && pid !== state.player && player(pid)) {
      $('player').value = pid; await pickPlayer(pid);
    }
    const r = search.results.find(x => x.mid === mid && x.id === id);
    if (r) remember([r.raw]);
    if (part) {
      remember(part.rows.map(x => x.raw));
      state.results = part.rows.map(x => row(x.raw)); state.total = part.rows.length; state.fromQuestion = true; state.tag = null;
      state.reel = part.reel;
      state.head = `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(part.understood)}</span>`;
      render('');
      playReel();
      return syncUrl();
    }
    select(id, true);
  }

  // ------------------------------------------------------------------ the match view's conversation

  // The server keeps nothing between turns: it merges each message into the query so far and returns it, and the page
  // sends it back. It starts from the picked player, so "make a reel of his best moments" knows who "his" is.
  function seed() {
    return { player_ids: state.player ? [state.player] : [], team_id: null, tags: [], reasons: [], minutes: null, limit: null, offset: 0 };
  }

  // A new match or player: the query starts again from the player (the conversation so far stays in the panel).
  async function newConversation() {
    resetRecap();
    chat.state = seed();
    try { await loadPlayerClips(state.player); } catch (e) { /* the grid says so below */ }
    engineHint();
    showPlayerMoments();
  }

  // How a way-out button names a player so the Librarian finds exactly them. It reads the first name part it knows, in
  // roster order: a surname no one else has is enough, else the full name when its first name leads to them, else the
  // name with team and kit number ("Ivan Brennan, Southgate's number 1").
  function chipName(p) {
    const parts = new Map();
    for (const o of state.info.players) for (const w of o.name.toLowerCase().split(' ')) { if (!parts.has(w)) parts.set(w, []); parts.get(w).push(o); }
    const ws = p.name.toLowerCase().split(' ');
    const last = ws[ws.length - 1];
    if (parts.get(last).length === 1) return { who: p.name.split(' ').slice(-1)[0], plain: true };
    if (parts.get(ws[0])[0] === p) return { who: p.name, plain: true };
    const name = p.name, side = (team(p.team_id)?.name || '').split(' ')[0];  // plain text: esc() is applied where it is shown
    return { who: `${name}, ${side}'s number ${p.kit_number}`, plain: false };
  }

  // One question about the match on screen, from the panel's box in the match view.
  async function send(message = $('fq').value.trim(), { quiet = false, withState = null } = {}) {
    if (!message || chat.busy || !state.match) return null;
    busy(true); $('fq').value = '';
    addMsg('me', esc(message));
    const eng = engine();
    const wait = addMsg('bot wait', eng === 'foundry' ? 'Searching, then asking Microsoft Foundry to write the reply…' : 'Searching…');
    let out = null;
    const prevOrder = (withState || chat.state)?.order;
    try {
      out = await R.api(matchUrl('/chat'), { method: 'POST', body: { message, state: withState || chat.state, history: chat.history, engine: eng } });
      wait.remove(); logChanged();
      chat.state = out.state; chat.history = out.history;
      remember(out.results);
      const msg = addMsg('bot', `${where(nameOf(state.match) === 'a match' ? matchName(state.info) : nameOf(state.match))}${esc(out.reply)}${fallbackLine(out, eng)}${howAnswered(out, eng)}`);
      // The server keeps the order asked for in state.order ("time" after "in match order"); older servers did not.
      if (out.state?.order === 'time' || (out.state?.order === undefined && /match order|in order|chronolog/i.test(message))) setSort('time');
      else if ((prevOrder === 'time' && out.state?.order === null) || /\bbest\b|\btop\b/i.test(message)) setSort('best');
      applyReply(out, message);
      offerWayOut(msg, out);
      if (state.sort === 'time' && out.intent === 'search') await fillMatchOrder();
    } catch (e) {
      wait.remove(); logChanged();
      addError(e, 'Regista could not answer', () => send(message));
    } finally {
      busy(false);
      if (!quiet) $('fq').focus();
    }
    return out;
  }

  // When the reply found nothing because filters from earlier questions still apply, a button sends the follow-up that
  // clears them: the server's suggestion when it has one ({label, message, state}: the message, sent with the cleared
  // state), else "start over" and the player's name.
  function offerWayOut(msg, out) {
    if (out.intent === 'reset' || (out.results || []).length || out.total) return;
    const st = out.state || {};
    const carried = (st.tags || []).length || (st.reasons || []).length || st.minutes;
    const s = out.suggest;
    let label, go;
    if (s && s.message) {
      label = s.label || s.message.charAt(0).toUpperCase() + s.message.slice(1);
      go = () => send(s.message, { withState: s.state || null });
    } else if (carried && (st.player_ids || []).length === 1 && player(st.player_ids[0])) {
      const pl = player(st.player_ids[0]);
      label = `Show all of ${pl.name}'s moments`;  // set as textContent
      go = async () => { await send('start over', { quiet: true }); await send(chipName(pl).who); };
    } else return;
    const b = Object.assign(document.createElement('button'), { type: 'button', className: 'alt wayout', textContent: label });
    b.onclick = () => { b.disabled = true; go(); };
    msg.insertBefore(b, msg.querySelector('details.how'));  // above the trace, where the eye is
    $('log').scrollTop = $('log').scrollHeight;
  }

  // One short line in the reply when Foundry was asked for but Regista's rules answered.
  function fallbackLine(out, eng) {
    const by = String(out.answered_by || 'rules');
    if (eng !== 'foundry' || !by.startsWith('rules') || out.intent === 'reset') return '';
    const why = /not configured/.test(by) ? 'Foundry is not set up on this server'
      : /too long/.test(by) ? 'Foundry took too long' : 'Foundry could not answer this time';
    return `<span class="fallback">${esc(why)}, so Regista's rules wrote this reply.</span>`;
  }

  // How many matches ran a step added up across every match: " · 34 matches", or " · 53 runs in 34 matches" when some
  // ran it more than once. A step of one match's own answer has no count.
  function stepCount(s) {
    if (!s.n) return '';
    const where = plural(s.n, 'match', 'matches');
    return s.runs > s.n ? ` · ${s.runs} runs in ${where}` : s.n > 1 ? ` · ${where}` : '';
  }

  // "How Regista answered": one line per answer (who answered, how many steps); the steps in plain words open on
  // demand, and the exact step names and times one click further.
  function howAnswered(out, eng) {
    const by = String(out.answered_by || 'rules');
    const instant = by.startsWith('rules');
    const SERVERS = { 'regista-mcp': 'Regista MCP server', 'azure-mcp': 'Azure MCP Server' };
    const ms = (v) => v == null ? '–' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : v < 1 ? '<1 ms' : `${Math.round(v)} ms`;
    const trace = Array.isArray(out.trace) ? out.trace : [];
    const plain = plainSteps(out, trace);
    let details = '';
    if (trace.length) {
      details = `<ol class="steps">${trace.map(s => `<li><span class="kind">${esc(s.kind)}</span><code>${esc(s.name)}</code>`
        + `${s.server ? `<span class="server">${esc(SERVERS[s.server] || s.server)}</span>` : ''}`
        + `<span class="ms">${esc(ms(s.ms))}${esc(stepCount(s))}</span></li>`).join('')}</ol>`;
    } else if ((out.tools_used || []).length) {
      details = `<div class="tags">${out.tools_used.map(t => `<span class="tool">${esc(t)}</span>`).join(' ')}</div>`;
    }
    const who = instant ? 'Regista\'s own rules, with no AI model' : `Microsoft Foundry (${esc(by.replace(/^foundry:/, ''))})`;
    const short = instant ? 'Data Search, no AI model' : `Microsoft Foundry (${esc(by.replace(/^foundry:/, ''))})`;
    return `<details class="how"><summary>How Regista answered · ${short} · ${esc(plural(plain.length, 'step'))}</summary>`
      + (plain.length ? `<ol class="plain">${plain.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` : '')
      + `<p class="by">Answered by ${who}${eng === 'foundry' && instant ? ' (Foundry was asked for)' : ''}.</p>`
      + (details ? `<details class="tech"><summary>Details: step names and times</summary>${details}`
        + `<p class="engine-raw">Engine ${esc(eng)} · answered by ${esc(by)}${out.every ? esc(` · ${out.every.searched} matches searched in ${ms(out.every.ms)}`) : ''}</p></details>` : '')
      + `</details>`;
  }

  // Plain text: each line goes through esc() where it is shown.
  function plainSteps(out, trace) {
    const ids = out.state?.player_ids || [];
    const of = ids.length === 1 && momentsOf(ids[0]) ? ` of ${momentsOf(ids[0])}` : '';
    const lastModel = trace.map(x => x.kind).lastIndexOf('model');
    const understood = out.understood ? `Understood: ${String(out.understood).replace(/ · /g, ', ')}` : 'Read the question';
    let searches = 0;
    const steps = [];
    if (out.every) {  // Home's search: every match's own steps, said once
      steps.push(`Read every match (${plural(out.every.searched, 'match', 'matches')})`, understood,
        out.intent === 'reset' ? 'Cleared the question' : `Found ${out.total} moments in ${plural(out.every.matchesWith, 'match', 'matches')}`);
    }
    trace.forEach((step, i) => {
      if (step.kind === 'step') {
        if (out.every) return;
        if (step.name === 'librarian.load_match') return steps.push('Read the match');
        if (step.name === 'conversation.step') return steps.push(understood);
        if (step.name === 'librarian.search_clips') {
          searches += 1;
          if (searches > 1) return steps.push('Checked what else the same player has');
          return steps.push(out.intent === 'reset' ? 'Cleared the question' : `Found ${out.total ?? (out.results || []).length}${of} moments`);
        }
        return steps.push('Worked on the question');
      }
      if (step.kind === 'agent') return steps.push('Handed the question to the Foundry Librarian agent');
      if (step.kind === 'model') return steps.push(i === lastModel ? `Microsoft Foundry (${step.name}) wrote the reply` : `Microsoft Foundry (${step.name}) chose what to look up`);
      if (step.kind === 'tool') return steps.push(toolStep(step));
      return steps.push('Another step');
    });
    if (!trace.some(s => s.kind !== 'step')) for (const t of out.tools_used || []) steps.push(toolStep({ name: t, server: /^search_index_|^cosmos_/.test(t) ? 'azure-mcp' : 'regista-mcp' }));
    return steps;
  }

  function toolStep(step) {
    const via = step.server === 'azure-mcp' ? 'through the Azure MCP Server' : step.server === 'regista-mcp' ? 'through Regista\'s MCP server' : '';
    const what = /^search_index_|^search_library$/.test(step.name) ? 'Searched the clip library with Azure AI Search'
      : step.name === 'search_clips' ? 'Searched this match\'s moments'
      : step.name === 'list_matches' ? 'Listed the matches'
      : /^cosmos_/.test(step.name) ? 'Read the library in Azure Cosmos DB' : `Used the tool ${step.name}`;
    return via ? `${what} ${via}` : what;
  }

  function applyReply(out, message = '') {
    if (out.intent === 'reset') { restartQuery(); return; }
    const rows = (out.results || []).map(c => row(c));
    state.fromQuestion = true; state.tag = null;
    state.reel = out.reel && out.reel.length ? out.reel.map(c => c.clip_id) : null;
    // "more" pages through the same question: the new page joins the set already on screen.
    state.results = out.intent === 'more' ? [...state.results, ...rows.filter(r => !state.results.some(x => x.id === r.id))] : rows;
    state.total = out.total ?? rows.length;
    state.selected = null;
    const ids = out.state?.player_ids || [];
    if (ids.length === 1 && ids[0] !== state.player && player(ids[0])) {
      state.player = ids[0]; $('player').value = ids[0]; state.picked = null;
      scoutLink(); syncUrl();
      loadPlayerClips(ids[0]).then(() => { renderTimeline(); }).catch(() => {});
    }
    state.head = `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(out.understood || '')}</span>`;
    const st = out.state || {};
    const carried = (st.tags || []).length || (st.reasons || []).length || st.minutes;
    render(state.results.length ? ''
      : carried && message && !/^(start over|reset)/i.test(message)
        ? `Nothing for ${esc(out.understood || 'that')}. Filters from earlier questions still apply: use the button in the reply, or say "start over".`
        : 'Nothing matched that question. Try a player\'s surname, a kit number, or an action like "nutmeg" or "shot".');
    // "Make a reel of Castellanos's best moments" names a player, so the server treats it as a search, not a reel of the
    // results so far: the page plays the reel of what it found either way.
    if (state.reel || /\b(reel|montage|compilation)\b/i.test(message)) playReel();
  }

  // The server pages its answers best first. "In match order" means every moment from kick-off, not the best six put in
  // order, so the page fetches the remaining pages itself (with the Instant engine: the same search, no model) and adds
  // them to the set without adding lines to the conversation.
  async function fillMatchOrder() {
    let st = chat.state;
    for (let i = 0; i < 10 && state.results.length < state.total; i++) {
      let out;
      try {
        out = await R.api(matchUrl('/chat'), { method: 'POST', body: { message: 'more', state: st, history: [], engine: 'rules' } });
      } catch (e) { break; }
      remember(out.results);
      const fresh = (out.results || []).map(c => row(c)).filter(r => !state.results.some(x => x.id === r.id));
      if (!fresh.length) break;
      st = out.state;
      state.results = [...state.results, ...fresh];
    }
    chat.state = st;
    render();
  }

  // "Start over" in the match view: the log stays (it is the record of the conversation), the query resets to the
  // picked player and the player's moments come back.
  function restartQuery() {
    chat.state = seed(); chat.history = [];
    showPlayerMoments();
  }

  // ------------------------------------------------------------------ the result set: grid, timeline, stage

  // On a Regista League match each player has a season profile in the Scout view; players outside the league have none.
  function scoutLink() {
    const p = player(state.player), gid = p?.global_player_id;
    const ok = typeof gid === 'string' && /^pl_[a-z0-9_]{1,40}$/.test(gid);
    $('scoutLinkLine').hidden = !ok;
    if (!ok) return $('scoutLink').removeAttribute('href');
    $('scoutLink').href = `/players/${enc(gid)}`;
    $('scoutLink').textContent = `See ${String(p.name)}'s Scout profile`;  // text, never markup
  }

  function showPlayerMoments() {
    const p = player(state.player);
    scoutLink();
    state.fromQuestion = false; state.reel = null; state.selected = null; state.tag = null;
    state.results = [...state.all.values()].filter(c => c.player_id === state.player).map(c => row(c));
    state.total = state.results.length;
    state.head = p
      ? `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(p.name)}, ${esc(team(p.team_id)?.name || '')}</span>`
      : 'Moments';
    render(p ? `${esc(p.name)} never had the ball in the main camera and is in no replay or highlight, so Regista cut no moments for this player. Pick someone from "Players with moments".`
      : 'Pick a player.');
  }

  // After a failed player switch: the moments of the player still picked.
  function showMatchMoments() { if (state.info) showPlayerMoments(); }

  function showEmpty(html) { $('empty').hidden = !html; $('empty').innerHTML = html || ''; }

  // The grid of the view on screen: the results (every match) or the match view's moments. emptyHtml: what to say when
  // nothing is there (kept with the set, so a re-render says it again).
  function render(emptyHtml) {
    const s = set();
    if (state.view === 'landing') return;
    if (emptyHtml !== undefined) s.emptyHtml = emptyHtml;
    const rows = visible();
    $('resultsHead').innerHTML = s.head || 'Moments';
    for (const b of document.querySelectorAll('.seg')) b.setAttribute('aria-pressed', String(b.dataset.sort === s.sort));
    showEmpty(rows.length ? '' : s.emptyHtml);
    if (!rows.length && s === search && search.wayout) {
      const b = Object.assign(document.createElement('button'), { type: 'button', className: 'alt wayout', textContent: search.wayout.label });
      const go = search.wayout.go;
      b.onclick = () => { b.disabled = true; go(); };
      $('empty').appendChild(b);
    }
    const shown = s.fromQuestion ? s.results.length : s.total;
    $('more').hidden = !(s.fromQuestion && s.total > shown);
    $('more').textContent = `Show more (${s.total - shown} more)`;
    renderTagBar();
    const vision = (r) => visionOf(s === search ? search.infos.get(r.mid) : state.info);
    const cards = s === search ? new Map(searchList().list.map(m => [m.id, m.card])) : null;  // results: which match
    const info = (r) => s === search ? search.infos.get(r.mid) : state.info;
    const card = (r) => {
      const cm = cards ? state.catalogue.get(r.mid) : null;
      return `
      <button type="button" class="card" data-id="${esc(r.id)}" data-mid="${esc(r.mid)}" aria-label="Play ${esc(r.title)}">
        ${r.video_url ? `<span class="thumb"><video muted playsinline preload="none" src="${esc(r.video_url)}"></video><span class="prep">Preparing…</span></span>`
          : `<span class="novideo">Read from Cosmos DB. The labels and timings are stored there; this server does not hold the match's video.</span>`}
        <span class="body">
          ${cards ? `<span class="from">${esc(cards.get(r.mid) || '')}</span>` : ''}
          ${cm ? `<span class="uline">${esc([fmtDate(cm.date), CAMS[cm.camera] || cm.camera, upWords(cm.uploader)].filter(Boolean).join(' · '))}</span>` : ''}
          <span class="reason ${r.reason === 'replay_appearance' ? 'replay' : ''}">${esc(R.reasonLabel(r.reason))} · ${esc(clockOf(info(r), r.t))}</span>
          <span class="title">${esc(r.title)}</span>
          <span class="bar" title="How worth watching, from 0 to 1: ${esc(Number(r.watchability).toFixed(2))}"><i data-w="${esc(Math.round(r.watchability * 100))}"></i></span>
          <span class="tags">${plainTags(r.tags).map(t => `<span>${esc(R.tagLabel(t))}</span>`).join('')}</span>
          ${badges(r, vision(r))}
        </span>
      </button>`;
    };
    // Results: grouped by competition, in the catalogue's country order (the sample and uploaded matches last), the best
    // 8 of each with "Show all N", and the Competition filter. The match view: one grid.
    const groups = s === search ? resultGroups(rows) : null;
    $('grid').classList.toggle('grouped', !!groups);
    $('grid').innerHTML = !groups ? rows.map(card).join('') : groups.map(gr => {
      const all = search.comp || search.expanded.has(gr.key) || gr.rows.length <= RESULTS_PER, shown = all ? gr.rows : gr.rows.slice(0, RESULTS_PER);
      return `<section class="rgroup" aria-label="${esc(gr.name)}"><h3 class="rgh">${esc(gr.name)} <span class="muted">${esc(`${gr.sub ? `${gr.sub} · ` : ''}${plural(gr.rows.length, 'moment')}`)}</span></h3>
        <div class="rgrid">${shown.map(card).join('')}</div>
        ${all ? '' : `<button type="button" class="alt rmore" data-more="${esc(gr.key)}">Show all ${esc(gr.rows.length)}</button>`}</section>`;
    }).join('');
    if (groups) {
      for (const b of $('grid').querySelectorAll('.rmore')) b.onclick = () => { search.expanded.add(b.dataset.more); render(); };
      paintCompFilter(rows);
    } else $('rcompWrap').hidden = true;
    for (const i of $('grid').querySelectorAll('.bar i')) i.style.width = `${Number(i.dataset.w) || 0}%`;
    for (const card of $('grid').querySelectorAll('.card')) {
      card.onclick = () => (state.view === 'results' ? openResult(card.dataset.mid, card.dataset.id) : select(card.dataset.id, true));
    }
    for (const v of $('grid').querySelectorAll('.thumb video')) {
      const prep = v.nextElementSibling;
      v.addEventListener('loadeddata', () => { prep.hidden = true; });
      v.addEventListener('error', () => { prep.textContent = 'Could not load the preview'; });
    }
    lazyPreview($('grid'));
    if (state.view === 'match') { renderTimeline(); renderStage(); }
  }
  const visionOf = (info) => info?.origin === 'vision';
  const RESULTS_PER = 8;
  const OTHER = '_other';
  // The results' groups: one per competition, in the catalogue's order; the matches outside the catalogue (the sample
  // and uploaded matches) last. The Competition filter keeps one group.
  function resultGroups(rows) {
    const list = new Map(searchList().list.map(m => [m.id, m])), by = new Map();
    for (const r of rows) { const k = (list.get(r.mid) || {}).comp || OTHER; if (!by.has(k)) by.set(k, []); by.get(k).push(r); }
    const order = [...state.comps.keys(), OTHER];
    return order.filter(k => by.has(k) && (!search.comp || search.comp === k)).map(k => {
      const c = state.comps.get(k);
      return { key: k, rows: by.get(k), name: c ? c.name : 'Other matches', sub: c ? `${c.country} · ${c.level_words}` : 'sample and uploaded matches' };
    });
  }
  function paintCompFilter(rows) {
    const list = new Map(searchList().list.map(m => [m.id, m])), n = new Map();
    for (const r of rows) { const k = (list.get(r.mid) || {}).comp || OTHER; n.set(k, (n.get(k) || 0) + 1); }
    if (search.comp && !n.has(search.comp)) search.comp = '';
    const countries = [...new Set([...state.comps.values()].map(c => c.country))];
    const opt = (k, label) => `<option value="${esc(k)}"${search.comp === k ? ' selected' : ''}>${esc(`${label} (${n.get(k)})`)}</option>`;
    $('rcomp').innerHTML = `<option value="">${esc(`All competitions (${rows.length})`)}</option>`
      + countries.map(co => { const cs = [...state.comps.values()].filter(c => c.country === co && n.has(c.competition_id)); return cs.length ? `<optgroup label="${esc(co)}">${cs.map(c => opt(c.competition_id, c.name)).join('')}</optgroup>` : ''; }).join('')
      + (n.has(OTHER) ? opt(OTHER, 'Other matches') : '');
    $('rcompWrap').hidden = n.size < 2 && !search.comp;
  }

  // Tag chips over the grid: one per football tag in the result set, with its count, as a filter.
  function renderTagBar() {
    const s = set();
    const counts = new Map();
    for (const r of s.results) for (const t of new Set(plainTags(r.tags))) counts.set(t, (counts.get(t) || 0) + 1);
    if (s.tag && !counts.has(s.tag)) s.tag = null;
    const bar = $('tagbar');
    if (counts.size < 1 || s.results.length < 2) { bar.hidden = true; bar.innerHTML = ''; return; }
    const chips = [[null, 'All', s.results.length], ...[...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t, n]) => [t, R.tagLabel(t), n])];
    bar.hidden = false;
    bar.innerHTML = chips.map(([t, name, n]) => `<button type="button" class="chip" data-tag="${esc(t || '')}" aria-pressed="${String(s.tag === t)}">`
      + `${esc(name)} <span class="n">${esc(n)}</span></button>`).join('');
    for (const b of bar.querySelectorAll('.chip')) b.onclick = () => {
      set().tag = b.dataset.tag || null; if (state.view === 'match') state.selected = null;
      render();
      bar.querySelector(`.chip[data-tag="${CSS.escape(b.dataset.tag)}"]`)?.focus();
    };
  }

  function badges(r, vision) {
    const out = [];
    if (String(r.model).startsWith('foundry:')) out.push(`<span class="badge" title="Label written by ${esc(r.model.replace('foundry:', 'Microsoft Foundry, '))}">Labelled by Microsoft Foundry</span>`);
    if (vision) out.push('<span class="badge vision" title="Cut from video by Regista\'s vision layer, run offline">Cut from video</span>');
    return out.length ? `<span class="badges">${out.join('')}</span>` : '';
  }

  // Clips render on first request, so the grid must not ask for every video at once: a card loads its first frame
  // only when it scrolls into view.
  const previewer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { e.target.preload = 'metadata'; e.target.load(); previewer.unobserve(e.target); }
  }, { rootMargin: '200px' }) : null;
  function lazyPreview(root) {
    for (const v of root.querySelectorAll('video[preload="none"]')) previewer ? previewer.observe(v) : (v.preload = 'metadata');
  }

  // The timeline (timeline.js): every clip the page knows, the current result set highlighted.
  function renderTimeline() {
    const tl = R.timeline;
    if (!tl || typeof tl.render !== 'function' || !state.info) { $('timelineWrap').hidden = true; return; }
    $('timelineWrap').hidden = false;
    try {
      tl.render($('timeline'), {
        duration: state.info.duration_s ?? state.info.video?.duration_s,
        periods: state.info.periods || [],
        clips: [...state.all.values()],
        keyMoments: state.info.key_moments || [],
        highlight: new Set(visible().map(r => r.id)),
        selected: state.selected,
        onPick: (id) => select(id, true),
      });
    } catch (e) {
      $('timelineWrap').hidden = true;
    }
  }

  // fromLink: a link put this moment on the stage, before anyone touched the page; browsers only let it start muted.
  function select(id, play, fromLink = false) {
    state.selected = id; state.picked = id;
    stopReel();
    renderStage(play, '', fromLink);
    syncUrl();
    markPlaying(id);
    if (play) $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // The playing card is marked for screen readers (and the timeline rings it); it carries no yellow outline.
  function markPlaying(id) {
    for (const c of $('grid').querySelectorAll('.card')) {
      c.classList.toggle('on', c.dataset.id === id);
      if (c.dataset.id === id) c.setAttribute('aria-current', 'true'); else c.removeAttribute('aria-current');
    }
  }

  function current() {
    const rows = visible();
    return rows.find(r => r.id === state.selected) || (state.selected && state.all.has(state.selected) ? row(state.all.get(state.selected)) : rows[0]);
  }

  function renderStage(play = false, prefix = '', fromLink = false) {
    if (state.view !== 'match') return;  // the stage loads its video only when the match view is on screen
    const r = current();
    const v = $('stageVideo');
    reelLinks();
    if (!r) {
      v.pause(); v.removeAttribute('src'); v.hidden = true; $('stageLoading').hidden = true;
      $('stageNoVideo').hidden = false; $('stageNoVideo').textContent = 'No moments to play here yet.';
      $('stageNow').textContent = ''; $('stageTitle').textContent = 'Nothing to play yet';
      $('stageTags').innerHTML = ''; $('stageWhy').textContent = '';
      return;
    }
    $('stageNow').textContent = prefix || `${R.reasonLabel(r.reason)} · ${clockOf(state.info, r.t)}–${clockOf(state.info, r.t_end)}`;
    $('stageTitle').textContent = r.title || '';
    $('stageTags').innerHTML = plainTags(r.tags).map(t => `<span>${esc(R.tagLabel(t))}</span>`).join('');
    $('stageWhy').textContent = r.explanation || '';
    markPlaying(r.id);
    if (!r.video_url) {
      v.pause(); v.removeAttribute('src'); v.hidden = true; $('stageLoading').hidden = true;
      $('stageNoVideo').hidden = false;
      $('stageNoVideo').textContent = 'Read from Cosmos DB. The labels and timings are stored there; this server does not hold the match\'s video.';
      return;
    }
    $('stageNoVideo').hidden = true; v.hidden = false;
    if (v.getAttribute('src') !== r.video_url) {
      v.src = r.video_url;
      v.preload = play ? 'auto' : 'metadata';
    }
    if (play) v.play().catch(() => { if (fromLink) { v.muted = true; v.play().catch(() => {}); } });
  }

  // Loading text while a clip renders on first view; an error says so instead of a blank player.
  function wireStageVideo() {
    const v = $('stageVideo'), busyOn = (on) => { $('stageLoading').hidden = !on; };
    v.addEventListener('loadstart', () => busyOn(true));
    v.addEventListener('waiting', () => busyOn(true));
    for (const ev of ['loadeddata', 'canplay', 'playing', 'pause', 'emptied']) v.addEventListener(ev, () => busyOn(false));
    v.addEventListener('error', () => {
      if (!v.getAttribute('src')) return;
      busyOn(false);
      $('stageNoVideo').hidden = false;
      $('stageNoVideo').textContent = 'This clip could not be loaded. Try again in a moment.';
    });
  }

  // ------------------------------------------------------------------ the recap

  // GET /recap: a headline and short paragraphs told from the picked player's side, every sentence citing its moment.
  // Folded into "Match recap": it is written when opened. A new match or player always starts with the Instant recap
  // (no model, no cost); Foundry writes one only when picked.
  const recapView = { data: null, req: 0, wanted: false, key: null };
  const recapEngine = () => document.querySelector('input[name="recapEngine"]:checked').value;
  const recapKey = () => `${state.match}|${state.player}`;

  function resetRecap() {
    document.querySelector('input[name="recapEngine"][value="rules"]').checked = true;
    recapView.key = null; recapView.req++;  // a recap still being written for the last match or player is dropped
    const box = $('recap');
    box.hidden = !state.info || state.info.source === 'cosmos' || !state.player;
    if (!box.hidden && box.open) loadRecap('rules');
  }

  // The profiles' "Recap" link (recap=1): open it; it scrolls into view once written.
  function openRecap() {
    const box = $('recap');
    if (box.hidden) { recapView.wanted = false; return; }
    if (box.open) loadRecap(recapEngine()); else box.open = true;  // the toggle event writes it
  }

  async function loadRecap(eng = recapEngine()) {
    const box = $('recap');
    if (!state.info || state.info.source === 'cosmos' || !state.player) { box.hidden = true; return; }
    if (eng === 'rules') document.querySelector('input[name="recapEngine"][value="rules"]').checked = true;
    const req = ++recapView.req;
    recapView.key = recapKey();
    const p = player(state.player);
    box.hidden = false;
    $('recapWho').textContent = p ? `This match, told from ${String(p.name)}'s side.` : 'This match.';  // text, never markup
    $('recapBody').innerHTML = `<p class="wait">${eng === 'foundry' ? 'Asking Microsoft Foundry to write the recap. This can take half a minute…' : 'Writing the recap…'}</p>`;
    $('recapBy').textContent = '';
    recapButtons(null);
    let out;
    try {
      out = await R.api(matchUrl(`/recap?player=${enc(state.player)}&engine=${enc(eng)}`));
    } catch (e) {
      if (req !== recapView.req) return;
      $('recapBody').innerHTML = `<p class="wait">${esc(offline(e) ? OFFLINE : `The recap could not be written: ${detail(e)}`)}</p>`;
      recapView.key = null;  // opening it again tries again
      return;
    }
    if (req !== recapView.req) return;  // the match or player changed meanwhile
    recapView.data = out;
    renderRecap(out, eng);
    if (recapView.wanted) {  // below the header where it sticks (wide screens; on a phone it scrolls away)
      recapView.wanted = false;
      const head = document.querySelector('header.top');
      const covers = head && /sticky|fixed/.test(getComputedStyle(head).position) ? head.offsetHeight : 0;
      window.scrollTo(0, box.getBoundingClientRect().top + window.scrollY - covers - 8);  // a page just opened: jump, no animation
    }
  }

  function renderRecap(out, eng) {
    const sentence = (s, pi, si) => {
      const c = (s.cites || []).find(x => x.clip_id && out.clips?.[x.clip_id]?.video_url);
      if (!c) return `<span>${esc(s.text)}</span>`;
      // A link to the moment's own URL (it opens in a new tab too); a click plays it on the stage.
      const href = `?match=${enc(state.match)}&player=${enc(out.clips[c.clip_id].player_id)}&clip=${enc(c.clip_id)}`;
      return `<a class="cite" href="${esc(href)}" data-p="${pi}" data-s="${si}" title="Play this moment">${esc(s.text)}</a>`;
    };
    $('recapBody').innerHTML = `<h3>${esc(out.headline)}</h3>`
      + (out.paragraphs || []).map((p, pi) => `<p>${(p.sentences || []).map((s, si) => sentence(s, pi, si)).join(' ')}</p>`).join('');
    for (const a of $('recapBody').querySelectorAll('a.cite')) a.onclick = (e) => { e.preventDefault(); playCite(a); };
    $('recapBy').innerHTML = recapByLine(out, eng);
    recapButtons(out);
  }

  // Who wrote it, in plain words; for Foundry, what Regista's check of its sentences found.
  function recapByLine(out, eng) {
    const by = String(out.answered_by || 'rules');
    if (by.startsWith('foundry:')) {
      const ch = out.checked || {}, left = (ch.dropped || []).length;
      return `Written by Microsoft Foundry (${esc(by.slice(8))}) from the match's facts${out.cached ? ', written earlier and kept' : ''}. `
        + `Regista checked every sentence: ${esc(plural(ch.kept ?? 0, 'sentence'))} kept`
        + (left ? `, ${esc(left)} left out (no moment to point at, or a number the match does not hold).` : ', none left out.')
        + ' Pick a sentence to play its moment.';
    }
    const why = eng !== 'foundry' ? '' : /not configured/.test(by) ? 'Foundry is not set up on this server, so '
      : /busy/.test(by) ? 'Foundry is busy right now, so ' : /too long/.test(by) ? 'Foundry took too long, so ' : 'Foundry could not write it this time, so ';
    return why ? `<span class="fallback">${esc(why)}Regista's rules wrote this recap.</span>Pick a sentence to play its moment.`
      : 'Instant: written by Regista\'s own rules from the match events, with no AI model. Pick a sentence to play its moment.';
  }

  function recapButtons(out) {
    const ids = out ? (out.reel || []).filter(id => out.clips?.[id]?.video_url) : [];
    $('recapReel').disabled = !ids.length;
    $('recapReel').textContent = ids.length ? `Play recap reel (${ids.length})` : 'Play recap reel';
    const dl = $('recapReelDl');
    dl.setAttribute('aria-disabled', String(!ids.length));
    if (ids.length) dl.href = matchUrl(`/reel.mp4?clips=${ids.map(enc).join(',')}`); else dl.removeAttribute('href');
  }

  // The recap's clips join the page's own (another player's goal, say), so the stage and the timeline can show them.
  function rememberRecap(out) {
    for (const [id, c] of Object.entries(out.clips || {})) {
      if (state.all.has(id)) continue;
      state.all.set(id, { id, player_id: c.player_id, t: c.t, t_end: c.t_end, reason: c.reason, title: c.title, video_url: c.video_url,
                          label: { title: c.title, tags: c.tags || [], watchability: c.watchability || 0, explanation: c.explanation || '',
                                   summary: c.summary || '' } });
    }
  }

  function playCite(btn) {
    const out = recapView.data;
    const s = out?.paragraphs?.[Number(btn.dataset.p)]?.sentences?.[Number(btn.dataset.s)];
    const c = s && (s.cites || []).find(x => x.clip_id && out.clips?.[x.clip_id]?.video_url);
    if (!c) return;
    rememberRecap(out);
    for (const a of $('recapBody').querySelectorAll('a.cite')) a.classList.toggle('on', a === btn);
    select(c.clip_id, true);
  }

  function playRecapReel() {
    const out = recapView.data;
    if (!out) return;
    rememberRecap(out);
    reel.ids = (out.reel || []).filter(id => state.all.get(id)?.video_url); reel.i = 0; reel.on = reel.ids.length > 0; reel.name = 'Recap reel';
    nextInReel();
    $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ------------------------------------------------------------------ reels and exports

  // The reel: the last "make a reel" reply if there was one, else the result set in the order on screen.
  const reelIds = () => (state.reel || visible().map(r => r.id)).filter(id => state.all.get(id)?.video_url).slice(0, REEL_MAX);

  function reelLinks() {
    const ids = reelIds();
    const dl = $('downloadReel'), ex = $('exportMoments');
    $('playReel').disabled = !ids.length;
    $('playReel').textContent = ids.length > 1 ? `Play reel (${ids.length})` : 'Play reel';
    dl.setAttribute('aria-disabled', String(!ids.length));
    if (ids.length) dl.href = matchUrl(`/reel.mp4?clips=${ids.map(enc).join(',')}`); else dl.removeAttribute('href');
    const all = visible().map(r => r.id);
    ex.setAttribute('aria-disabled', String(!all.length));
    if (!all.length) ex.removeAttribute('href');
    else ex.href = state.fromQuestion || state.tag ? matchUrl(`/moments.csv?clips=${all.map(enc).join(',')}`) : matchUrl(`/moments.csv?player=${enc(state.player)}`);
  }

  // The first download of a reel renders it, which takes a few seconds per clip, and a plain link shows nothing until
  // the file starts. So the page fetches it itself and says what it is doing; without fetch the link works as is.
  async function downloadReel(e) {
    const a = $('downloadReel'), href = a.getAttribute('href');
    if (!href || a.dataset.busy) { e.preventDefault(); return; }
    if (!window.fetch || !window.URL?.createObjectURL) return;
    e.preventDefault();
    a.dataset.busy = '1'; a.setAttribute('aria-busy', 'true');
    a.textContent = 'Preparing reel…';
    let failed = false;
    try {
      const res = await fetch(href);
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') || '')?.[1] || 'regista_reel.mp4';
      const t = Object.assign(document.createElement('a'), { href: url, download: name });
      document.body.appendChild(t); t.click(); t.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      failed = true;
      a.textContent = err instanceof TypeError ? 'Can\'t reach Regista. Try again.' : 'The reel could not be made. Try again.';
    } finally {
      setTimeout(() => { a.textContent = 'Download reel'; delete a.dataset.busy; a.removeAttribute('aria-busy'); }, failed ? 3000 : 0);
    }
  }

  const reel = { ids: [], i: 0, on: false, name: 'Reel' };
  function playReel() {
    reel.ids = reelIds(); reel.i = 0; reel.on = reel.ids.length > 0; reel.name = 'Reel';
    nextInReel();
  }
  function nextInReel() {
    if (!reel.on || reel.i >= reel.ids.length) { reel.on = false; return; }
    state.selected = reel.ids[reel.i++];
    renderStage(true, `${reel.name} · clip ${reel.i} of ${reel.ids.length}`);
  }
  function stopReel() { reel.on = false; }

  // ------------------------------------------------------------------ sort, health, how it works

  function setSort(s, target = set()) {
    target.sort = s;
    if (target === set()) for (const b of document.querySelectorAll('.seg')) b.setAttribute('aria-pressed', String(b.dataset.sort === s));
  }

  async function loadHealth() {
    let h;
    try { h = await R.api('/api/health'); } catch (e) { $('stack').hidden = true; $('services').innerHTML = '<li class="muted">Health is not available right now.</li>'; return; }
    state.health = h;
    engineHint();
    runningOn(h);
    const services = [
      ['Microsoft Foundry', h.cloud.foundry, `A ${h.cloud.model || 'Foundry'} model labels uploaded matches and writes the Foundry replies.`],
      ['Azure Cosmos DB', h.cloud.cosmos, 'Stores matches, clips, labels and reviewers\' verdicts.'],
      ['Azure AI Search', h.cloud.search, 'Indexes every labelled clip for the Foundry Librarian.'],
      ['Azure MCP Server', h.azure_mcp, 'The Foundry Librarian\'s tool for querying the search index.'],
      ['Application Insights', h.tracing, 'Receives the Agent Framework traces, shown in Foundry tracing.'],
      ['Azure Container Apps', h.container_apps, 'Runs this app, and the vision job that processes uploaded footage.'],
      ['Azure Storage', h.storage, 'Holds uploaded footage and the queue that hands it to the vision job.'],
    ];
    $('services').innerHTML = services.map(([name, ok, what]) =>
      `<li><span class="tick ${ok ? 'on' : 'off'}" aria-hidden="true">${ok ? '✓' : '–'}</span><b>${esc(name)}</b>`
      + `<span class="what">${ok ? 'On this server. ' : 'Not configured on this server. '}${esc(what)}</span></li>`).join('');
  }

  // "Running on", under the landing's search: only what this deployment says is running (Agent Framework is the code
  // itself, so it is always there). Icon first, the full service name under it; a tile opens How it works.
  function runningOn(h) {
    const tiles = [
      ['foundry', 'Microsoft Foundry', h.cloud.foundry, `Writes the Foundry replies and labels uploaded matches${h.cloud.model ? ` (${h.cloud.model})` : ''}`],
      ['agent-framework', 'Microsoft Agent Framework', true, 'Runs the agent workflows: ingest, clips, labels, review, recap'],
      ['mcp', 'Azure MCP Server', h.azure_mcp, 'The Foundry Librarian\'s tool for the search index'],
      ['cosmos-db', 'Azure Cosmos DB', h.cloud.cosmos, 'Stores matches, clips, labels and reviewers\' verdicts'],
      ['ai-search', 'Azure AI Search', h.cloud.search, 'Indexes every labelled clip'],
      ['container-apps', 'Azure Container Apps', h.container_apps, 'Runs this app and the vision job'],
      ['storage', 'Azure Storage', h.storage, 'Holds uploaded footage and the vision job queue'],
      ['app-insights', 'Application Insights', h.tracing, 'Receives the agents\' traces'],
    ].filter(t => t[2]);
    $('stackList').innerHTML = tiles.map(([icon, name, , what]) => `<li><button type="button" class="tile" title="${esc(what)}">`
      + `<img src="/static/product/icons/${esc(icon)}.svg" alt="" width="40" height="40"><span>${esc(name)}</span></button></li>`).join('');
    for (const b of $('stackList').querySelectorAll('.tile')) b.onclick = () => $('howOpen').click();
    $('stack').hidden = tiles.length < 2;  // the code alone (no Azure configured) is not worth a row
  }

  // The realism report is Markdown (GET /report). It is shown here as a page: escaped first, then a small subset of
  // Markdown (headings, bold, tables, paragraphs) turned into elements, so nothing in it can become markup.
  const report = { loaded: null };
  const METRIC = (name) => {
    const s = String(name).replace(/_per90$/, ' per 90 minutes').replace(/^xg_/, 'xG ').replace(/_s$/, ' (seconds)').replace(/_/g, ' ');
    return s.startsWith('xG') ? s : s.charAt(0).toUpperCase() + s.slice(1);
  };
  function markdown(md) {
    const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    const lines = String(md).split('\n');
    const html = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^\s*$/.test(line) || /^Diagnostics\b/.test(line)) continue;  // raw counters with no band: not for people
      const h = /^(#{1,3})\s+(.*)$/.exec(line);
      if (h) { html.push(`<h4>${inline(h[2])}</h4>`); continue; }
      if (/^\|/.test(line)) {
        const rows = [];
        while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
        i--;
        const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        const [head, , ...body] = rows;
        html.push(`<div class="tablewrap"><table><thead><tr>${cells(head).map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>`
          + body.map(r => `<tr>${cells(r).map((c, j) => j === 0 ? `<td>${esc(METRIC(c))}</td>`
            : /^(in band|high|low)$/.test(c) ? `<td><span class="verdict ${c === 'in band' ? 'ok' : 'off'}">${esc(c)}</span></td>` : `<td>${inline(c)}</td>`).join('')}</tr>`).join('')
          + '</tbody></table></div>');
        continue;
      }
      html.push(`<p>${inline(line)}</p>`);
    }
    return html.join('');
  }

  async function toggleReport() {
    const box = $('report'), btn = $('reportToggle');
    const open = box.hidden;
    box.hidden = !open; btn.setAttribute('aria-expanded', String(open));
    if (!open || report.loaded === state.match) return;
    box.textContent = 'Loading the report…';
    try {
      // The report names the match by its id; people read "this match".
      const md = String(await R.api(matchUrl('/report'))).replace(/^# Synthetic realism report: .*$/m, '# Realism report for this match')
        .split(state.match).join('this match');
      box.innerHTML = markdown(md);
      report.loaded = state.match;
    } catch (e) {
      box.textContent = offline(e) ? OFFLINE : 'The realism report is not available for this match.';
    }
  }

  function wire() {
    logChanged();  // the panel says how to start until the first question
    $('homeForm').addEventListener('submit', (e) => {
      e.preventDefault();
      const message = $('q').value.trim() || PROMPTS[typing.p];  // an empty box searches the prompt showing
      $('q').value = '';
      searchEvery(message, { fresh: true, focus: 'rq' });
    });
    $('barForm').addEventListener('submit', (e) => { e.preventDefault(); searchEvery($('rq').value.trim(), { focus: 'rq' }); });
    $('askForm').addEventListener('submit', (e) => {
      e.preventDefault();
      if (state.view === 'match') return send();
      const message = $('fq').value.trim();
      $('fq').value = '';
      searchEvery(message, { focus: 'fq' });
    });
    for (const r of document.querySelectorAll('input[name="engine"], input[name="rengine"], input[name="fengine"]')) r.addEventListener('change', () => setEngine(r.value));
    $('backToResults').onclick = () => {
      if (history.state?.from === 'results') { history.back(); return; }  // popstate shows the results
      showView('results', { push: true }); window.scrollTo(0, 0); $('rq').focus();
    };
    window.addEventListener('popstate', onPopState);
    $('match').onchange = async () => { showView('match'); if (await loadMatch($('match').value)) syncUrl(); };
    $('player').onchange = () => { showView('match'); pickPlayer($('player').value); };
    // Home's "Or open a match": the match view, as a new entry (Back returns to Home).
    $('homeMatch').onchange = async () => {
      const id = $('homeMatch').value; if (!id) return;
      $('homeMatch').value = '';
      showView('match', { sync: false, push: true }); window.scrollTo(0, 0);
      if (await loadMatch(id)) syncUrl();
    };
    $('rcomp').onchange = () => { search.comp = $('rcomp').value; render(); };
    for (const b of document.querySelectorAll('.seg')) b.onclick = () => { setSort(b.dataset.sort); render(); };
    $('more').onclick = () => {
      if (state.view !== 'results') return send('more');
      const left = [...search.perMatch].filter(([mid, p]) => p.total > search.results.filter(r => r.mid === mid).length).map(([mid]) => mid);
      searchEvery('more', { only: left });
    };
    $('playReel').onclick = () => { playReel(); $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); };
    $('stageVideo').addEventListener('ended', nextInReel);
    $('downloadReel').addEventListener('click', downloadReel);
    for (const r of document.querySelectorAll('input[name="recapEngine"]')) r.addEventListener('change', () => loadRecap(recapEngine()));
    $('recap').addEventListener('toggle', () => { if ($('recap').open && recapView.key !== recapKey()) loadRecap(recapEngine()); });
    $('recapReel').onclick = playRecapReel;
    wireStageVideo();
    $('reportToggle').onclick = toggleReport;
    $('howOpen').onclick = () => { const d = $('how'); d.showModal ? d.showModal() : d.setAttribute('open', ''); };
    $('howClose').onclick = () => { const d = $('how'); d.close ? d.close() : d.removeAttribute('open'); };
    $('how').addEventListener('click', (e) => { if (e.target === $('how')) $('how').close(); });  // a click on the backdrop
    $('how').addEventListener('close', () => $('howOpen').focus());  // Escape, Close or the backdrop: back to the button
  }

  init();
})();
