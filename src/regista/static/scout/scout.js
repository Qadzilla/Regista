// The Scout dashboard (/scout): Maya Lindqvist, chief scout at Fairhaven FC (a synthetic persona, like every player, club
// and competition). Nine sections, one per hash (Regista.sections, shared/regista.js): #overview, #find, #competitions
// (and #competition/<id> for one competition), #terminal (terminal.js), #shortlist, #reports, #messages, #team,
// #settings. A section's hash may name a player: /scout#messages/<id> opens (or starts) the conversation with them,
// #shortlist/<id> puts them on the shortlist and in compare, #reports/<id> opens their draft. The scout bar on
// /players/{id} links here that way (it writes first, then goes; the hash alone is enough too).
//
// LIVE, from the API: the catalogue (/api/catalogue: 14 competitions in 10 countries, their levels and clubs), Find
// players (/api/catalogue/players: the filters, the order, the places and the boards are the engine's; this script
// never ranks), the Scout agent on the catalogue (POST /api/scout/ask with where "catalogue", Data Search or Foundry),
// the competition pages (/api/competitions/{id}), uploaded matches (/api/catalogue/matches), Team needs (the engine's
// /api/catalogue/rank with min_percentile), the shortlist's numbers (/api/catalogue/players/{id}), compare and its best
// marks (/api/catalogue/compare) and the moments behind every number (?evidence=KEY). The league's cards
// (/api/players) still name the people in Messages and Reports.
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
  const PV = R.profileView;   // the shared profile renderer's helpers (shirts, ordinals, moment keys, links)
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const LIMIT = 200;            // the most rows /api/players and /api/catalogue/* hand back in one page
  const COMPARE_MAX = demo.COMPARE_MAX;   // what /api/catalogue/compare accepts
  const ME = demo.SCOUTS[demo.SCOUT];
  const CLUB_ID = ME.club_id;
  const MY = ME.level || { tier: 'semi_pro', age_group: 'senior', gender: 'men', competition_id: 'co_eng_sp_men' };
  const MY_KEY = `${MY.tier}/${MY.age_group}/${MY.gender}`;
  const GID = /^pl_[a-z0-9_]{1,40}$/;
  const COID = /^co_[a-z0-9_]{1,40}$/;
  const CLIP_VIEW = /^\/\?match=[A-Za-z0-9_]+(&[a-z_]+=[A-Za-z0-9_]+)*$/;   // Clip view links from the API

  const POSITIONS = PV.POS;
  const GROUP = PV.GROUP;
  // The numbers a card leads with for each position (terminal metric keys), after the sort.
  const LEAD = {
    FW: ['goals', 'shots', 'assists'],
    MF: ['recoveries', 'tackles_won', 'key_passes'],
    DF: ['interceptions', 'tackles_won', 'recoveries'],
    GK: ['saves', 'passes_completed', 'recoveries'],
  };
  const CARD_KEYS = [...new Set(Object.values(LEAD).flat())];
  const SORTS = ['goals', 'assists', 'shots', 'key_passes', 'take_ons_won', 'nutmegs', 'passes_completed', 'tackles_won',
                 'interceptions', 'recoveries', 'saves'];
  const COMPARE_ALL = ['goals', 'assists', 'key_passes', 'take_ons_won', 'tackles_won', 'interceptions', 'recoveries'];
  const NEED_STATS = [...new Set([...CARD_KEYS, 'goals', 'assists', 'key_passes', 'take_ons_won', 'nutmegs'])];
  const EXAMPLES = ['Who are the best U19 dribblers up front?', 'Find me women forwards who score',
                    'Which amateur midfielders create the most chances?'];
  const CAMERA = { tripod: 'Tripod', phone: 'Phone', drone: 'Drone', broadcast: 'Broadcast camera' };
  const PAGE_ONE = 24, PAGE_MANY = 4, NEED_N = 6;
  // The levels warning's reason, behind "Why?".
  const WHY_LEVELS = 'Lower levels and younger players produce different raw numbers: fewer completed passes, more balls lost, slower runs. So the same number means something different at each level. A percentile compares a player only with players at their own level, which is why it is the fair way to read players from different levels.';

  const state = {
    cat: null,                  // GET /api/catalogue
    pools: { min_pool: 5, small_pool: 15 },   // GET /api/catalogue/pools (the percentile's minimum and the small flag)
    metrics: new Map(),         // terminal metric key -> its definition (label, positions), GET /api/metrics
    compOf: new Map(),          // competition id -> its summary
    poolOf: new Map(),          // level key ("semi_pro/senior/men") -> the level pool (words, label, competitions)
    clubOf: new Map(),          // club id -> {name, short_name, competition_id, kit}
    all: new Map(),             // global id -> every league player's card (Messages and Reports name them)
    known: new Map(),           // global id -> anyone seen (catalogue rows, league cards), for names and stars
    rows: new Map(),            // global id -> Promise of GET /api/catalogue/players/{id} (the shortlist, compare)
    comps: new Map(),           // competition id -> Promise of GET /api/competitions/{id}
    fits: new Map(),            // need query -> Promise of GET /api/catalogue/rank (Team needs, the Overview)
    matches: null,              // Promise of GET /api/catalogue/matches (the Overview's new footage)
    find: { q: '', country: '', tier: '', age_group: '', gender: '', competition: '', position: '', sort: 'goals', all: false },
    found: null,                // the last /api/catalogue/players answer on screen
    hidden: 0,                  // rows the list leaves out for too few minutes
    open: new Map(),            // board key -> every row of that board, once "Show all" loaded them
    seq: 0,                     // drops replies to older list requests
    ready: false,               // the catalogue is loaded
    profiles: new Map(),        // global id -> Promise of GET /api/players/{id} (the league profile: Reports' moments)
    openConvo: null,            // conversation id on screen in Messages
    openReport: null,           // report id on screen in Reports
    picker: null,               // section index whose "Insert a moment" list is open
    coId: null, coClub: null, coAll: false,   // the competition page on screen, its squad's club, all its matches
    needOpen: new Set(),        // "<need id>|level" or "|below": lists shown in full
    section: '',
  };

  // ------------------------------------------------------------------ small helpers

  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';
  const offline = (e) => !(e instanceof R.ApiError);
  const OFFLINE = 'Can\'t reach Regista right now. Check your connection and try again.';
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const cap = (t) => String(t || '').charAt(0).toUpperCase() + String(t || '').slice(1);
  const ord = (n) => PV.ordinal(Math.round(Number(n)));
  const labelOf = (key) => key === 'minutes' ? 'Minutes played' : (state.metrics.get(key)?.label || R.tagLabel(key));
  const shortStat = (k) => labelOf(k).toLowerCase();
  const statWords = (k) => (k === 'minutes' ? 'minutes played' : `${shortStat(k)} per 90`);
  const HEX = /^#[0-9a-f]{6}$/i;
  const VIDEO = /^\/api\/[A-Za-z0-9_./?=&%-]+$/;     // video urls from the API are relative; anything else is not played
  const fmtRate = (v) => (v === null || v === undefined) ? '–' : Number(v).toFixed(2);
  const fmtMinutes = (m) => `${Math.round(Number(m) || 0)} minutes`;
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const fmtDate = (iso) => { const [y, m, d] = String(iso || '').split('-').map(Number); return y ? `${d} ${MONTHS[m - 1]} ${y}` : ''; };
  const player = (gid) => state.all.get(gid) || state.known.get(gid) || null;
  const nameOf = (gid, fallback) => player(gid)?.name || fallback || 'A player';
  const firstName = (name) => String(name || '').split(' ')[0];
  const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const posLine = (p) => p ? `${POSITIONS[p.position] || p.position} · ${p.club}` : '';
  const shirt = (p, size = 40) => PV.shirtSvg(p.kit, p.kit_number, p.position, size);
  const stageBadge = (stage) => stage ? `<span class="sc-stage s-${esc(stage)}">${esc(stage)}</span>` : '';
  const verdictBadge = (v) => v ? `<span class="sc-verdict v-${esc(String(v).replace(/ /g, ''))}">${esc(v)}</span>` : '';
  // "Round 2 · v Calder Town" for a moment reference (messages, reports).
  const refWhere = (r) => [r.round !== null && r.round !== undefined ? `Round ${r.round}` : 'Friendly', r.opponent ? `v ${r.opponent}` : '']
    .filter(Boolean).join(' · ');

  // The catalogue's words for where a row plays.
  const levelKey = (r) => `${r.tier}/${r.age_group}/${r.gender}`;
  const levelWords = (r) => state.poolOf.get(levelKey(r))?.words || '';
  const compName = (cid) => state.compOf.get(cid)?.name || '';
  const whereLine = (r) => `${r.competition || compName(r.competition_id)} · ${r.country || state.compOf.get(r.competition_id)?.country || ''}`;
  const levelChip = (r) => `<span class="sc-lvl">${esc(levelWords(r))}</span>`;
  const isMineLevel = (c) => levelKey(c) === MY_KEY;
  // The light "read with care" mark the engine puts on a noisy number (Zaid: kept wherever the engine says so).
  const care = (c, minutes) => (c && c.noisy ? `<span class="sc-noisy" role="img" aria-label="read with care: too few minutes to tell players apart on this number yet" title="Read with care: ${minutes != null ? `at ${esc(Math.round(minutes))} minutes ` : ''}this number cannot yet tell players apart">≈</span>` : '');
  const noisyLine = () => `<p class="small sc-noisyline"><span class="sc-noisy" aria-hidden="true">≈</span> ${esc(state.cat?.noisy_words?.replace(/^≈ /, '') || 'marks a number to read with care.')}</p>`;

  // The pool line, never hidden: "98th percentile among 33 semi-pro men forwards", "None yet · 25 of the 33 semi-pro
  // men forwards have none", or why there is no percentile. Everything in it is the engine's cell.
  function poolLine(c, r) {
    if (!c) return '';
    const pool = c.pool || {};
    const who = pool.words || `${levelWords(r)} ${GROUP[r.position] || 'players'}`;
    if (c.none_yet) {
      const z = c.zeros;
      return z ? `None yet · ${z.none === z.of ? `all ${z.of}` : `${z.none} of the ${z.of}`} ${who} have none` : 'None yet';
    }
    if (c.percentile !== null && c.percentile !== undefined) return `${ord(c.percentile)} percentile among ${pool.size} ${who}`;
    const s = c.sample || {};
    if (c.qualified === false || r.qualified === false) {
      return `No percentile: ${Math.round(s.minutes ?? r.minutes ?? 0)} minutes, under the ${Math.round(s.qualifying_minutes ?? 0)} ${r.competition || compName(r.competition_id)} asks for`;
    }
    if (pool.size !== undefined && pool.min_size && pool.size < pool.min_size) {
      return `No percentile: only ${pool.size} qualified ${who} to compare with (it takes ${pool.min_size})`;
    }
    if (pool.reason === 'not ranked for this position') return `No percentile: not ranked for ${GROUP[r.position] || 'this position'}`;
    return pool.reason ? `No percentile: ${pool.reason}` : 'No percentile';
  }
  // The small-pool flag with its reason (a pool under 15: one match moves a percentile a lot).
  function smallFlag(c, r) {
    const pool = c && c.pool;
    if (!pool || !pool.small || !pool.size || c.none_yet) return '';
    return `<span class="sc-flag"><span class="sc-small" title="Fewer than ${esc(state.pools.small_pool)} players to compare with: one match moves a percentile a lot">Small pool</span><span class="sc-smallwhy">only ${esc(pool.size)} qualified ${esc(pool.words || '')} to compare with</span></span>`;
  }
  const sampleLine = (r) => `${plural(r.appearances || 0, 'match', 'matches')} · ${fmtMinutes(r.minutes)} in ${r.competition || compName(r.competition_id)}`;
  const alsoIn = (r) => (r.also_in || []).filter(c => state.compOf.has(c)).map(compName);
  const warnWhy = (first) => `<div class="sc-warn"><p class="small">${esc(first)}</p><details class="sc-why"><summary>Why?</summary><p class="small">${esc(WHY_LEVELS)}</p></details></div>`;

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

  // A player's league profile (moments, evidence, matches), read once per page: Reports cite its moments.
  function profile(gid) {
    if (!state.profiles.has(gid)) {
      const p = R.api(`/api/players/${enc(gid)}`);
      p.catch(() => state.profiles.delete(gid));
      state.profiles.set(gid, p);
    }
    return state.profiles.get(gid);
  }
  // A player across the catalogue (every row, with the cards' numbers), read once per page.
  function catRows(gid) {
    if (!state.rows.has(gid)) {
      const p = R.api(`/api/catalogue/players/${enc(gid)}?metrics=${CARD_KEYS.join(',')}&moments=0`).then((P) => {
        const r = primaryRow(P);
        if (r && !state.all.has(gid)) state.known.set(gid, { ...cardOfRow(P, r), global_id: gid });
        return P;
      });
      p.catch(() => state.rows.delete(gid));
      state.rows.set(gid, p);
    }
    return state.rows.get(gid);
  }
  // The row with the most minutes (the API's own default row), and the card fields a list needs from it.
  const primaryRow = (P) => (P && P.rows && P.rows.length ? [...P.rows].sort((a, b) => b.sample.minutes - a.sample.minutes)[0] : null);
  function cardOfRow(P, r) {
    const c = (P.career || []).find(x => x.competition_id === r.competition_id) || {};
    const club = state.clubOf.get(r.club_id) || {};
    return { global_id: P.global_id, name: P.name, position: r.position, club: r.club, club_id: r.club_id, kit: club.kit,
             kit_number: c.kit_number, competition_id: r.competition_id, competition: r.competition, country: r.country,
             tier: r.tier, age_group: r.age_group, gender: r.gender, minutes: r.sample.minutes, appearances: r.sample.appearances,
             qualified: r.sample.minutes >= r.sample.qualifying_minutes, also_in: r.also_in, age: P.bio?.age, values: r.metrics };
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
  nav = R.sections({ fallback: 'overview', alias: { competition: 'competitions' }, onChange: show });

  function show(section, rest) {
    for (const v of document.querySelectorAll('main video')) if (!v.closest(`[data-panel="${section}"]`)) v.pause();
    const moved = section !== state.section;
    state.section = section;
    counts();
    if (!state.ready) return;
    const gid = GID.test(rest[0] || '') ? rest[0] : '';
    if (section === 'overview') paintOverview();
    if (section === 'find') { /* the cards are kept current as filters change */ }
    if (section === 'competitions') paintCompetitions();
    if (section === 'competition') openCompetition(COID.test(rest[0] || '') ? rest[0] : '');
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

  // ------------------------------------------------------------------ the catalogue

  async function loadCatalogue() {
    const [cat, pools, metrics] = await Promise.all([R.api('/api/catalogue'), R.api('/api/catalogue/pools'), R.api('/api/metrics')]);
    state.cat = cat;
    state.pools = { min_pool: pools.min_pool ?? 5, small_pool: pools.small_pool ?? 15 };
    for (const m of metrics.metrics || []) state.metrics.set(m.key, m);
    for (const c of cat.competitions || []) state.compOf.set(c.competition_id, c);
    for (const p of cat.levels?.pools || []) state.poolOf.set(p.key, p);
    for (const c of cat.clubs || []) state.clubOf.set(c.club_id, c);
    if (cat.note) $('footNote').textContent = cat.note;
  }
  // Every league player once (sorted by name): Messages and Reports list and name them.
  async function loadAll() {
    const out = await R.api(`/api/players?sort=name&limit=${LIMIT}`);
    state.all = new Map((out.players || []).map(p => [p.global_id, p]));
  }
  // Countries in the catalogue's own order, each with its competitions.
  function countries() {
    const out = new Map();
    for (const c of state.cat.competitions || []) {
      if (!out.has(c.country)) out.set(c.country, []);
      out.get(c.country).push(c);
    }
    return out;
  }

  // ------------------------------------------------------------------ Find players: filters

  const opt = (v, label, sel) => `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(label)}</option>`;
  function fillFilters() {
    const L = state.cat.levels || {};
    $('fCountry').innerHTML = opt('', 'Any') + [...countries().keys()].map(c => opt(c, c)).join('');
    $('fTier').innerHTML = opt('', 'Any') + (L.tiers || []).map(t => opt(t.key, t.label)).join('');
    $('fAge').innerHTML = opt('', 'Any') + (L.age_groups || []).map(t => opt(t.key, t.label)).join('');
    $('fGender').innerHTML = opt('', 'Any') + (L.genders || []).map(t => opt(t.key, t.label)).join('');
    $('fSort').innerHTML = SORTS.filter(k => state.metrics.has(k)).map(k => opt(k, `${labelOf(k)} per 90`)).join('') + opt('minutes', 'Minutes played');
    const mine = state.poolOf.get(MY_KEY);
    $('fMine').textContent = `My level: ${mine ? mine.words : 'semi-pro men'}`;
    $('fMine').title = `${ME.club}'s level: ${mine ? mine.label : ''}`;
    readUrl();
  }
  // The competition list follows the other filters, so it never offers a competition the list would leave empty.
  function compOptions() {
    const f = state.find;
    const all = state.cat.competitions || [];
    const ok = all.filter(c => (!f.country || c.country === f.country) && (!f.tier || c.tier === f.tier)
      && (!f.age_group || c.age_group === f.age_group) && (!f.gender || c.gender === f.gender));
    if (f.competition && !ok.some(c => c.competition_id === f.competition)) f.competition = '';
    const by = new Map();
    for (const c of ok) { if (!by.has(c.country)) by.set(c.country, []); by.get(c.country).push(c); }
    $('fComp').innerHTML = opt('', ok.length === all.length ? 'Any' : `Any of these ${ok.length}`, f.competition)
      + [...by].map(([country, cs]) => `<optgroup label="${esc(country)}">${cs.map(c => opt(c.competition_id, `${c.name} (${levelWords(c)})`, f.competition)).join('')}</optgroup>`).join('');
  }
  // The filters live in the address's query too (beside the #find hash), so a search can be shared or reloaded.
  const URL_KEYS = ['q', 'country', 'tier', 'age_group', 'gender', 'competition', 'position', 'sort'];
  function readUrl() {
    const u = new URLSearchParams(location.search);
    const f = state.find;
    const has = (sel, v) => [...$(sel).options].some(o => o.value === v);
    if (u.get('q')) f.q = u.get('q').slice(0, 80);
    if (u.get('country') && has('fCountry', u.get('country'))) f.country = u.get('country');
    if (u.get('tier') && has('fTier', u.get('tier'))) f.tier = u.get('tier');
    if (u.get('age_group') && has('fAge', u.get('age_group'))) f.age_group = u.get('age_group');
    if (u.get('gender') && has('fGender', u.get('gender'))) f.gender = u.get('gender');
    if (COID.test(u.get('competition') || '') && state.compOf.has(u.get('competition'))) f.competition = u.get('competition');
    if (POSITIONS[u.get('position')]) f.position = u.get('position');
    if (u.get('sort') && has('fSort', u.get('sort'))) f.sort = u.get('sort');
    f.all = u.get('all') === '1';
    writeFilters();
  }
  function writeFilters() {
    const f = state.find;
    compOptions();
    $('fName').value = f.q; $('fCountry').value = f.country; $('fTier').value = f.tier; $('fAge').value = f.age_group;
    $('fGender').value = f.gender; $('fComp').value = f.competition; $('fPosition').value = f.position; $('fSort').value = f.sort;
    $('fAll').checked = f.all;
  }
  function writeUrl() {
    const f = state.find;
    const u = new URLSearchParams();
    for (const k of URL_KEYS) if (f[k] && !(k === 'sort' && f.sort === 'goals')) u.set(k, f[k]);
    if (f.all) u.set('all', '1');
    const qs = u.toString();
    try { history.replaceState(null, '', `/scout${qs ? `?${qs}` : ''}${location.hash || '#find'}`); } catch (e) {}
  }
  const isWhole = () => { const f = state.find; return !f.country && !f.tier && !f.age_group && !f.gender && !f.competition; };
  const isMine = () => { const f = state.find; return f.tier === MY.tier && f.age_group === MY.age_group && f.gender === MY.gender && !f.country && !f.competition; };
  function setFind(patch) {
    Object.assign(state.find, patch);
    writeFilters();
    writeUrl();
    loadFind();
  }
  function readFilters() {
    return { q: $('fName').value.trim().slice(0, 80), country: $('fCountry').value, tier: $('fTier').value, age_group: $('fAge').value,
             gender: $('fGender').value, competition: $('fComp').value, position: $('fPosition').value, sort: $('fSort').value,
             all: $('fAll').checked };
  }
  for (const id of ['fCountry', 'fTier', 'fAge', 'fGender', 'fComp', 'fPosition', 'fSort', 'fAll']) {
    $(id).addEventListener('change', () => setFind(readFilters()));
  }
  let typing = null;
  $('fName').addEventListener('input', () => {
    clearTimeout(typing);
    typing = setTimeout(() => setFind({ q: $('fName').value.trim().slice(0, 80) }), 250);
  });
  $('filterForm').addEventListener('submit', (ev) => ev.preventDefault());
  $('fWhole').addEventListener('click', () => setFind({ country: '', tier: '', age_group: '', gender: '', competition: '' }));
  $('fMine').addEventListener('click', () => setFind({ country: '', competition: '', tier: MY.tier, age_group: MY.age_group, gender: MY.gender }));
  // Opens Find players on one competition (from a competition page).
  function findIn(cid) {
    state.find = { ...state.find, q: '', country: '', tier: '', age_group: '', gender: '', competition: cid, position: '' };
    writeFilters();
    writeUrl();
    loadFind();
    nav.go('find');
  }

  // ------------------------------------------------------------------ Find players: the list (the engine's)

  // The positions a sort is scored for (the metrics engine decides): with no position picked, a goals list leaves
  // goalkeepers out and a saves list holds only them. '' when every position is scored.
  function scoredFor(sort) {
    const ps = state.metrics.get(sort)?.positions || [];
    return sort === 'minutes' || !ps.length || ps.length === 4 ? '' : ps.join(',');
  }
  function findParams(f) {
    const u = new URLSearchParams();
    for (const k of ['country', 'tier', 'age_group', 'gender', 'competition', 'q']) if (f[k]) u.set(k, f[k]);
    const pos = f.position || scoredFor(f.sort);
    if (pos) u.set('position', pos);
    u.set('sort', f.sort);
    u.set('metrics', [...new Set([...(f.sort === 'minutes' ? [] : [f.sort]), ...CARD_KEYS])].join(','));
    if (f.all) u.set('min_minutes', '0');
    return u;
  }
  async function loadFind() {
    const f = { ...state.find };
    const u = findParams(f);
    u.set('limit', String(PAGE_ONE));
    const mine = ++state.seq;
    state.open.clear();
    $('cards').setAttribute('aria-busy', 'true');
    $('fWhole').setAttribute('aria-pressed', String(isWhole()));
    $('fMine').setAttribute('aria-pressed', String(isMine()));
    try {
      // the list, and how many more players the filters hold without enough minutes (the same filters, every minute)
      const all = new URLSearchParams(u); all.set('min_minutes', '0'); all.set('limit', '1');
      const [out, every] = await Promise.all([R.api(`/api/catalogue/players?${u}`), f.all ? null : R.api(`/api/catalogue/players?${all}`)]);
      if (mine !== state.seq) return;
      clearNetError();
      state.found = { ...out, params: u.toString(), f };
      state.hidden = every ? Math.max(0, every.total - out.total) : 0;
      renderFind();
    } catch (e) {
      if (mine !== state.seq) return;
      netError(e, loadFind);
    } finally {
      if (mine === state.seq) $('cards').setAttribute('aria-busy', 'false');
    }
  }
  // Every row of one board (or of the whole list), page by page as the API hands them out.
  async function loadBoard(key, offset, size) {
    const out = [];
    const base = new URLSearchParams(state.found.params);
    for (let o = offset; o < offset + size; o += LIMIT) {
      base.set('offset', String(o));
      base.set('limit', String(Math.min(LIMIT, offset + size - o)));
      const page = await R.api(`/api/catalogue/players?${base}`);
      out.push(...(page.players || []));
    }
    return out;
  }

  // The stat a card leads with when the list is not sorted by one: the player's best percentile among their position's.
  function strongest(r) {
    const keys = (LEAD[r.position] || LEAD.FW).filter(k => r.values && r.values[k]);
    return keys.reduce((a, k) => ((r.values[k].percentile ?? -1) > (r.values[a].percentile ?? -1) ? k : a), keys[0]);
  }
  // A player's card: the name's link covers the card (to /players/{id}); the star sits above it. Who, where
  // (competition, country, level), three numbers with bars, the pool line of the sort stat, the small-pool flag with its
  // reason, the sample, and the engine's place on this list.
  function cardHtml(r, sort) {
    const sl = demo.shortlist()[r.global_id];
    const on = !!sl;
    const k = sort === 'minutes' || !(r.values && r.values[sort]) ? strongest(r) : sort;
    const keys = [...new Set([k, ...(LEAD[r.position] || LEAD.FW)])].filter(x => r.values && r.values[x]).slice(0, 3);
    const c = r.values && r.values[k];
    const also = alsoIn(r);
    const url = /^\/players\/pl_[a-z0-9_]+$/.test(r.profile_url || '') ? r.profile_url : `/players/${enc(r.global_id)}`;
    return `<article class="sc-pcard" data-id="${esc(r.global_id)}">
      <div class="sc-chead">${r.rank ? `<span class="sc-rank" title="Place on this list">${esc(r.rank)}</span>` : ''}<span class="sc-shirt" aria-hidden="true">${shirt(r)}</span>
        <span class="who"><a class="name" href="${esc(url)}">${esc(r.name)}</a>
          <span class="muted small">${esc(POSITIONS[r.position] || r.position)} · ${esc(r.club)}</span>
          <span class="sc-stagebox">${on ? stageBadge(sl.stage) : ''}</span></span>
        <button type="button" class="star" data-star="${esc(r.global_id)}" aria-pressed="${on}"
          aria-label="${on ? 'Remove' : 'Add'} ${esc(r.name)} ${on ? 'from' : 'to'} the shortlist">${on ? '★' : '☆'}</button>
      </div>
      <p class="sc-where"><span>${esc(whereLine(r))}</span>${levelChip(r)}</p>
      <ul class="rates">${keys.map(x => { const v = r.values[x];
        return `<li${x === k ? ' class="on"' : ''}><span class="lbl"><b>${esc(fmtRate(v.value))}</b> ${esc(shortStat(x))} per 90</span>
          <span class="bar" aria-hidden="true"><i${v.none_yet || v.percentile == null ? '' : ` data-w="${esc(v.percentile)}"`}></i></span></li>`; }).join('')}</ul>
      ${c ? `<p class="sc-pool"><b>${esc(cap(shortStat(k)))} per 90:</b> ${esc(poolLine(c, r))}${care(c, r.minutes)}</p>${smallFlag(c, r)}` : ''}
      <p class="muted small sc-cfoot">${esc(sampleLine(r))}${also.length ? ` · also plays in ${esc(also.join(', '))}` : ''}</p>
    </article>`;
  }

  // A board's heading: its level in words (one list per level), or its gender (and position) across levels.
  function boardTitle(b, out) {
    if (b.by === 'level') return cap(state.poolOf.get(b.level)?.words || b.label);
    if (b.by === 'gender_position') return `${b.gender === 'women' ? 'Women' : 'Men'}, ${GROUP[b.position] || b.position}`;
    return b.gender === 'women' ? 'Women' : 'Men';
  }
  function boardComps(b, out) {
    const sel = new Set(out.competitions || []);
    const ids = b.by === 'level' ? (state.poolOf.get(b.level)?.competitions || []).filter(c => sel.has(c))
      : [...sel].filter(c => state.compOf.get(c)?.gender === b.gender);
    return ids.map(compName).join(', ');
  }
  function renderFind() {
    const out = state.found, f = out.f;
    const stat = statWords(f.sort);
    const comps = out.competitions || [];
    const ctry = new Set(comps.map(c => state.compOf.get(c)?.country));
    const keepers = !f.position && scoredFor(f.sort);
    const career = (out.players || []).some(r => r.career) || (out.boards || []).some(b => (b.top || []).some(r => r.career));
    $('resultsSub').innerHTML = `${esc(plural(out.total, 'player'))}${f.all ? '' : ' with enough minutes for a percentile'}${f.q ? '' : ` · ${esc(plural(comps.length, 'competition'))} in ${esc(plural(ctry.size, 'country', 'countries'))}`} · footage up to ${esc(fmtDate(state.cat.as_of))}`
      + (state.hidden ? ` · <button type="button" class="link" data-allmin>${esc(state.hidden)} more without enough minutes</button>` : '')
      + (keepers ? ` · ${scoredFor(f.sort) === 'GK' ? 'only goalkeepers are ranked on this' : 'goalkeepers left out of this sort (pick Goalkeeper to see them)'}` : '')
      + (career ? ' · a player in two competitions appears once for each' : '')
      + ' · synthetic data, invented names';
    $('empty').hidden = out.total > 0;
    if (!out.total) {
      $('fRule').innerHTML = '';
      $('cards').innerHTML = '';
      $('empty').textContent = 'Nobody matches these filters. Try fewer, or the whole catalogue.';
      return;
    }
    const boards = out.boards || [{ board: '-', by: null, size: out.total, offset: 0, top: out.players || [], with_any: out.with_any, none_yet: out.none_yet }];
    const many = boards.length > 1;
    const pos = f.position || ((out.players || [])[0] || {}).position;
    const oneLevel = !many && (out.pools || []).length === 1 ? state.poolOf.get(out.pools[0].label) : null;
    const rule = f.sort === 'name' ? 'In alphabetical order.'
      : out.rank_by === 'pool' ? `Ranked by each player's percentile among their own level's ${GROUP[pos] || 'players'} for ${stat}, one list per gender. Ties go to players whose pool is not small, then more minutes; players with none yet come last, with no place number.`
        : !many ? `Ranked by ${stat}${oneLevel ? ` within ${oneLevel.words}` : ''}: everyone here plays at the same level. Players showing the same number share a place.`
          : `One list per level, ranked by ${stat} within the level: a raw number is only compared with players at the same level.${f.position ? '' : ' Pick a position to rank across levels by percentile.'}`;
    $('fRule').innerHTML = `<p class="small">${esc(rule)}</p>` + (out.warning ? warnWhy('Players from different levels: read each percentile against its own pool.') : '');
    let noisy = false;
    $('cards').innerHTML = boards.map(b => {
      const full = state.open.get(b.board);
      const rows = full || (many ? (b.top || []).slice(0, PAGE_MANY) : (b.top || []));
      if (rows.some(r => r.values && r.values[f.sort] && r.values[f.sort].noisy)) noisy = true;
      const n = (b.with_any ?? null) !== null ? b.with_any + b.none_yet : 0;
      const noneLine = b.none_yet ? `<p class="muted small sc-bnone">${esc(`${b.with_any} of the ${n} players on this list${f.all ? '' : ' with enough minutes'} ${b.with_any === 1 ? 'has' : 'have'} any ${shortStat(f.sort)} so far. The ${b.none_yet === 1 ? 'one' : b.none_yet} with none ${b.none_yet === 1 ? 'is' : 'are'} listed last, with no place number.`)}</p>` : '';
      const head = many ? `${boardTitle(b, out)}` : oneLevel ? `Everyone here: ${oneLevel.words}` : '';
      const shownMax = many ? PAGE_MANY : PAGE_ONE;
      return `<section class="sc-bd">${head ? `<h3 class="sc-bh">${esc(head)} <span class="muted small">${esc(plural(b.size, 'player'))}${many || oneLevel ? ` · ${esc(many ? boardComps(b, out) : (oneLevel.competitions || []).filter(c => comps.includes(c)).map(compName).join(', '))}` : ''}</span></h3>` : ''}
        <div class="sc-cards">${rows.map(r => cardHtml(r, f.sort)).join('')}</div>${noneLine}
        ${b.size > rows.length ? `<button type="button" class="alt sc-more" data-board="${esc(b.board)}" data-off="${esc(b.offset)}" data-size="${esc(b.size)}">Show all ${esc(b.size)}</button>` : ''}
        ${full && b.size > shownMax ? `<button type="button" class="link sc-more" data-fold="${esc(b.board)}">Show fewer</button>` : ''}</section>`;
    }).join('') + (noisy ? noisyLine() : '');
    paint($('cards'));
    for (const r of [...(out.players || []), ...boards.flatMap(b => b.top || [])]) if (!state.all.has(r.global_id)) state.known.set(r.global_id, r);
  }
  $('resultsSub').addEventListener('click', (e) => { if (e.target.closest('[data-allmin]')) setFind({ all: true }); });
  $('cards').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-board]'), fold = e.target.closest('[data-fold]');
    if (fold) { state.open.delete(fold.dataset.fold); renderFind(); return; }
    if (!b) return;
    const seq = state.seq;
    b.disabled = true;
    b.textContent = 'Loading…';
    try {
      const rows = await loadBoard(b.dataset.board, Number(b.dataset.off) || 0, Number(b.dataset.size) || 0);
      if (seq !== state.seq) return;
      for (const r of rows) if (!state.all.has(r.global_id)) state.known.set(r.global_id, r);
      state.open.set(b.dataset.board, rows);
      renderFind();
    } catch (err) {
      netError(err, () => renderFind());
    }
  });

  // A star adds a player to the shortlist (Watching) or takes them off it.
  function toggleShortlist(gid) {
    if (demo.onShortlist(gid)) demo.setStage(gid, '');
    else demo.setStage(gid, 'Watching');
    syncStars();
  }
  // Every star and stage badge on the page shows whether its player is shortlisted.
  function syncStars() {
    const sl = demo.shortlist();
    for (const b of document.querySelectorAll('button.star')) {
      const p = player(b.dataset.star);
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

  // ------------------------------------------------------------------ Find players: the Scout agent (on the catalogue)

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
        return ({ 'scout.parse': 'Read the question', 'scout.catalogue_place': 'Read where to look: countries, levels and ages',
                  'scout.search_players': 'Ranked the league\'s players', 'scout.search_catalogue_players': 'Ranked the catalogue\'s players',
                  'scout.get_profile': 'Read the player\'s profile', 'scout.get_catalogue_player': 'Read the player across the catalogue',
                  'scout.compare_players': 'Compared the players' })[s.name]
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
    const args = json?.query?.args && typeof json.query.args === 'object'
      ? Object.entries(json.query.args).map(([a, v]) => `${a}=${v}`).join(', ') : '';
    return `<details class="how"><summary>How the Scout agent answered · ${esc(short)} · ${esc(plural(plain.length, 'step'))}</summary>
      <ol class="plain">${plain.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      <details class="tech"><summary>Details: step names and times</summary>
        <div class="times">${trace.map(s => `${esc(s.kind)} · ${esc(s.name)}${s.server ? ` · ${esc(SERVERS[s.server] || s.server)}` : ''} · ${esc(msText(s.ms))}`).join('<br>')}</div>
        ${args ? `<p class="small muted">The catalogue search's arguments: <code>${esc(args)}</code></p>` : ''}
        ${json.trace_note ? `<p class="small muted">${esc(json.trace_note)}</p>` : ''}</details></details>`;
  }

  // One player the Scout agent found: who, where, the number the answer was about with its pool line, small and noisy
  // marks, minutes, and a link to the profile.
  function agentRow(p) {
    const s = p.stat && typeof p.stat === 'object' ? p.stat : null;
    const known = player(p.global_id);
    const url = /^\/players\/pl_[a-z0-9_]+$/.test(p.profile_url || '') ? p.profile_url : `/players/${enc(p.global_id)}`;
    const cell = s ? { ...s, qualified: p.qualified, sample: { minutes: p.minutes } } : null;
    const line = s ? `${fmtRate(s.value)} ${String(s.label || '').toLowerCase()} per 90 · ${poolLine(cell, p)}` : '';
    return `<a href="${esc(url)}" class="sc-minirow">${known && known.kit ? `<span class="sc-shirt" aria-hidden="true">${shirt(known)}</span>` : ''}
      <span><b>${esc(p.name)}</b> <span class="muted small">${esc(POSITIONS[p.position] || p.position || '')} · ${esc(p.club || '')}${p.competition ? ` · ${esc(p.competition)}, ${esc(p.country || '')}` : ''}</span>
        <span class="small">${esc(line)}${s && s.pool && s.pool.small && !s.none_yet ? ' · <span class="sc-small">Small pool</span>' : ''} · ${esc(fmtMinutes(p.minutes))}${care(s, p.minutes)}</span></span></a>`;
  }
  // Renders a reply from the Scout agent (POST /api/scout/ask) into #scoutAnswer: the reply, how the question was
  // understood, who answered and with which tools, the cross-level warning when the tool gave one, the players, and the
  // steps it took.
  function renderScoutAnswer(json) {
    const box = $('scoutAnswer');
    const reply = json && typeof (json.reply ?? json.answer) === 'string' ? (json.reply ?? json.answer) : '';
    const players = Array.isArray(json?.players) ? json.players.filter(p => p && GID.test(p.global_id || '')) : [];
    const by = typeof json?.answered_by === 'string' ? json.answered_by : '';
    const tools = Array.isArray(json?.tools_used) ? json.tools_used : [];
    const byLine = by.startsWith('foundry')
      ? `Answered by Microsoft Foundry${tools.length ? `, using ${tools.map(esc).join(', ')}` : ''}.`
      : (by && by !== 'rules' ? `Answered by Regista's rules (${esc(by.replace(/^rules\s*/, '').replace(/^\(|\)$/g, ''))}).` : "Answered by Regista's rules.");
    const checked = Array.isArray(json?.checked) && json.checked.length
      ? `<p class="muted small">Numbers in this reply that no tool returned: ${json.checked.map(esc).join(', ')}.</p>` : '';
    const total = typeof json?.result_total === 'number' && json.result_total > players.length
      ? `<p class="muted small">The first ${esc(players.length)} of ${esc(json.result_total)}.</p>` : '';
    box.innerHTML = (reply ? `<p class="sc-reply">${esc(reply)}</p>` : '') +
      (json?.understood ? `<p class="muted small">Understood: ${esc(json.understood)}</p>` : '') +
      `<p class="muted small">${byLine}</p>${checked}` +
      (typeof json?.warning === 'string' && json.warning ? warnWhy(`${cap(json.warning.split('. ')[0].replace(/^rows from/, 'players from').replace(/\.$/, ''))}.`) : '') +
      (players.length ? `<div class="sc-mini">${players.map(agentRow).join('')}</div>${total}` : '') +
      (players.some(p => p.stat && p.stat.noisy) ? noisyLine() : '') +
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
    $('scoutAnswer').innerHTML = `<p class="muted">${engine === 'foundry' ? 'Asking the Foundry Scout agent… (a few seconds)' : 'Searching the catalogue…'}</p>`;
    try {
      renderScoutAnswer(await R.api('/api/scout/ask', { method: 'POST', body: { q, engine, where: 'catalogue' } }));
    } catch (e) {
      const why = e && e.status === 429 ? 'Too many questions just now; try again in a minute.'
        : e && e.status === 422 ? 'Ask in under 200 characters.'
        : 'Regista could not answer just now. Check your connection and try again.';
      $('scoutAnswer').innerHTML = `<p class="muted">${esc(why)}</p>`;
    } finally {
      go.disabled = false;
    }
  });

  // ------------------------------------------------------------------ uploaded matches (the Overview and competition pages)

  function uploaderText(u) {
    if (!u) return '';
    return u.type === 'player' ? `Uploaded by ${u.name || 'a player'}, a player at ${u.club || 'their club'}` : `Uploaded by the ${u.club || 'club'} team account`;
  }
  // One uploaded match: date, the score line, where (or the round, on its own competition's page), who uploaded it, the
  // camera label, and a link into the Clip view.
  function matchRow(m, inComp) {
    const c = state.compOf.get(m.competition_id) || {};
    const score = `${m.home_name} ${m.score?.t_home ?? ''}–${m.score?.t_away ?? ''} ${m.away_name}`;
    const rnd = m.round ? `Round ${m.round}` : '';
    const where = inComp ? rnd : [`${c.name || m.competition || ''} · ${c.country || m.country || ''} · ${levelWords(c)}`, rnd].filter(Boolean).join(' · ');
    return `<li class="sc-up"><span class="sc-update">${esc(fmtDate(m.date))}</span>
      <span class="sc-upmain"><b>${esc(score)}</b><span class="muted small">${esc(where)}</span>
        <span class="small">${esc(uploaderText(m.uploader))}${m.camera ? ` · <span class="sc-cam">${esc(CAMERA[m.camera] || m.camera)}</span>` : ''}</span></span>
      ${CLIP_VIEW.test(m.clip_view || '') ? `<a class="pf-btn alt sc-watch" href="${esc(m.clip_view)}">Watch in the Clip view</a>` : ''}</li>`;
  }
  function catalogueMatches() {
    if (!state.matches) {
      state.matches = R.api(`/api/catalogue/matches?limit=${LIMIT}`).then(out => out.matches || []);
      state.matches.catch(() => { state.matches = null; });
    }
    return state.matches;
  }
  const newestFirst = (a, b) => String(b.date).localeCompare(String(a.date)) || String(a.match_id).localeCompare(String(b.match_id));

  // ------------------------------------------------------------------ Competitions: the list, and one competition

  const tierWord = (c) => (state.cat.levels?.tiers || []).find(t => t.key === c.tier)?.label || c.tier;
  const ageWord = (c) => (state.cat.levels?.age_groups || []).find(t => t.key === c.age_group)?.label || c.age_group;
  const genderWord = (c) => (c.gender === 'women' ? 'Women' : 'Men');
  // The counts are uploads, not accounts: "19 uploaded by team accounts, 11 by players".
  function uploadersText(u) {
    const t = u?.team || 0, p = u?.player || 0;
    const tt = t ? `${t} uploaded by ${t === 1 ? 'a team account' : 'team accounts'}` : '';
    const pp = p ? `${p} ${t ? 'by' : 'uploaded by'} ${p === 1 ? 'a player' : 'players'}` : '';
    return [tt, pp].filter(Boolean).join(', ');
  }
  const cams = (o) => Object.entries(o || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${(CAMERA[k] || k).toLowerCase()}`).join(' · ');
  function paintCompetitions() {
    const t = state.cat.totals || {};
    $('coLine').textContent = `${t.competitions} competitions in ${t.countries} countries · ${t.clubs} clubs · ${t.matches} uploaded matches, up to ${fmtDate(state.cat.as_of)} · synthetic: invented competitions, clubs and players; countries and levels are labels.`;
    $('coList').innerHTML = [...countries()].map(([country, cs]) => `<section class="sc-country"><h2>${esc(country)} <span class="muted small">${esc(plural(cs.length, 'competition'))}</span></h2>
      <div class="sc-cocards">${cs.map(c => `<a class="sc-cocard" href="/scout#competition/${esc(c.competition_id)}"><span class="sc-coname"><b>${esc(c.name)}</b>${isMineLevel(c) ? '<span class="sc-mine">Your level</span>' : ''}</span>
          <span class="muted small">${esc(c.region)} · ${esc(c.format)} · ${esc(c.season)}</span>
          <span class="sc-where">${levelChip(c)}<span class="small">${esc(tierWord(c))} · ${esc(ageWord(c))} · ${esc(genderWord(c))}</span></span>
          <span class="sc-cofacts"><span><b>${esc(c.teams)}</b> clubs</span><span><b>${esc(c.players)}</b> players</span><span><b>${esc(c.uploaded_matches)}</b> uploaded matches</span></span>
          <span class="small">${c.coverage === 'full' ? 'Every league match uploaded so far' : 'Some matches uploaded'}${c.dates ? ` · ${esc(fmtDate(c.dates[0]))} to ${esc(fmtDate(c.dates[1]))}` : ''}</span>
          <span class="muted small">Cameras: ${esc(cams(c.cameras))}</span>
          <span class="muted small">${esc(uploadersText(c.uploaders))}</span></a>`).join('')}</div></section>`).join('')
      + `<p class="muted small sc-camnote">${esc(state.cat.camera_note || '')}</p>`;
  }
  function competition(cid) {
    if (!state.comps.has(cid)) {
      const p = R.api(`/api/competitions/${enc(cid)}`);
      p.catch(() => state.comps.delete(cid));
      state.comps.set(cid, p);
    }
    return state.comps.get(cid);
  }
  async function openCompetition(cid) {
    const c = state.compOf.get(cid);
    if (!c) { nav.go('competitions'); return; }
    if (state.coId !== cid) { state.coId = cid; state.coAll = false; state.coClub = null; }
    const box = $('coPage');
    box.innerHTML = `<p class="muted">Loading ${esc(c.name)}…</p>`;
    let S;
    try { S = await competition(cid); } catch (e) {
      box.innerHTML = `<p class="muted">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
      return;
    }
    if (state.coId !== cid || state.section !== 'competition') return;
    if (!state.coClub || !S.clubs.some(k => k.club_id === state.coClub)) {
      state.coClub = (S.clubs.find(k => k.club_id === CLUB_ID) || S.clubs[0] || {}).club_id || null;
    }
    paintCompetition(S, c);
  }
  function paintCompetition(S, c) {
    const lp = S.level_pool || { positions: {}, competitions: [] };
    const others = (lp.competitions || []).filter(x => x !== c.competition_id).map(x => state.compOf.get(x)).filter(Boolean);
    const pools = ['GK', 'DF', 'MF', 'FW'].map(p => { const z = (lp.positions || {})[p] || { size: 0 };
      return `${z.size} ${GROUP[p]}${z.under_min ? ` (too few for a percentile: it takes ${state.pools.min_pool})` : z.small ? ' (small pool)' : ''}`; }).join(' · ');
    const matches = [...(S.matches || [])].map(m => ({ ...m, competition_id: c.competition_id }))
      .sort((a, b) => String(b.date).localeCompare(String(a.date)) || (b.round || 0) - (a.round || 0));
    const club = S.clubs.find(k => k.club_id === state.coClub);
    const table = S.table ? `<div class="tablewrap"><table class="sc-ctable sc-table"><caption class="sr">${esc(c.name)} table</caption>
        <thead><tr><th class="l" scope="col">#</th><th class="l" scope="col">Club</th><th scope="col">P</th><th scope="col">W</th><th scope="col">D</th><th scope="col">L</th><th scope="col">Goals</th><th scope="col">Pts</th></tr></thead><tbody>
        ${S.table.map(t => `<tr${t.club_id === CLUB_ID ? ' class="mine"' : ''}><td>${esc(t.position)}</td><th scope="row">${esc(t.club)}</th><td>${esc(t.played)}</td><td>${esc(t.won)}</td><td>${esc(t.drawn)}</td><td>${esc(t.lost)}</td><td>${esc(t.goals_for)}–${esc(t.goals_against)}</td><td><b>${esc(t.points)}</b></td></tr>`).join('')}</tbody></table></div>`
      : `<p class="muted small">${esc(cap(S.results_note || 'uploaded matches only, not a league table'))}: what each club's uploaded matches add up to.</p>
        <div class="tablewrap"><table class="sc-ctable sc-table"><caption class="sr">${esc(c.name)} results</caption>
        <thead><tr><th class="l" scope="col">Club</th><th scope="col">Uploaded</th><th scope="col">W</th><th scope="col">D</th><th scope="col">L</th><th scope="col">Goals</th></tr></thead><tbody>
        ${(S.results || []).map(t => `<tr><th scope="row">${esc(t.club)}</th><td>${esc(t.played)}</td><td>${esc(t.won)}</td><td>${esc(t.drawn)}</td><td>${esc(t.lost)}</td><td>${esc(t.goals_for)}–${esc(t.goals_against)}</td></tr>`).join('')}</tbody></table></div>`;
    const ups = S.player_uploads || [];
    $('coPage').innerHTML = `<header class="panel sc-cohead"><div><p class="muted small">${esc(c.country)} · ${esc(c.region)}</p><h1>${esc(c.name)}</h1>
        <p class="sc-where">${levelChip(c)}<span class="small">${esc(tierWord(c))} · ${esc(ageWord(c))} · ${esc(genderWord(c))} · ${esc(c.format)} · season ${esc(c.season)}</span>${isMineLevel(c) ? '<span class="sc-mine">Your level</span>' : ''}</p>
        ${c.eligibility ? `<p class="small muted">Who can play: ${esc(c.eligibility)}</p>` : ''}
        <p class="small">${c.coverage === 'full' ? `Every league match so far is uploaded: ${esc(matches.length)} matches.` : `${esc(plural(matches.length, 'match', 'matches'))} uploaded so far; the season goes on after ${esc(fmtDate(state.cat.as_of))} without footage yet.`}</p></div>
        <button type="button" data-findin="${esc(c.competition_id)}">Find players here</button></header>
      <section class="panel"><h2>How players here are compared</h2>
        <p class="small">With every <b>${esc(levelWords(c))}</b> player in the same position${others.length ? `: this competition and ${esc(others.map(o => `${o.name} (${o.country})`).join(', '))}` : ', and this is the only competition at that level'}. Players with enough minutes to compare: ${esc(pools)}.</p>
        <p class="muted small">${esc(S.sample?.words || '')}</p>
        <p class="muted small">The minutes a percentile needs are a third of the busiest club's minutes${c.coverage === 'full' ? '' : ', and never fewer than 45'}.</p></section>
      <section class="panel"><h2>Uploaded matches</h2><p class="muted small">Newest first. ${esc(S.camera_note || '')}</p>
        <ol class="sc-uploads">${matches.slice(0, state.coAll ? Infinity : 8).map(m => matchRow(m, true)).join('')}</ol>
        ${matches.length > 8 ? `<button type="button" class="alt sc-more" data-coall>${state.coAll ? 'Show the newest 8' : `Show all ${esc(matches.length)}`}</button>` : ''}
        ${ups.length ? `<h3 class="sc-nh">Uploaded through the Player view</h3><p class="muted small">${esc(S.player_uploads_note || '')}</p>
          <ol class="sc-uploads">${ups.map(u => `<li class="sc-up"><span class="sc-update">${esc(fmtDate(u.date))}</span>
            <span class="sc-upmain"><b>${esc(u.title || `${u.name}'s ${u.kind === 'friendly' ? 'friendly' : 'match'} v ${u.opponent}`)}</b>
              <span class="muted small">${esc(`${u.name || ''}, ${u.club || ''} · ${u.kind === 'friendly' ? 'a friendly' : 'a match'} v ${u.opponent || ''} · not counted here`)}</span>
              ${u.camera ? `<span class="small"><span class="sc-cam">${esc(CAMERA[u.camera] || u.camera)}</span></span>` : ''}</span>
            ${CLIP_VIEW.test(u.clip_view || '') ? `<a class="pf-btn alt sc-watch" href="${esc(u.clip_view)}">Watch in the Clip view</a>` : ''}</li>`).join('')}</ol>` : ''}</section>
      <section class="panel"><h2>${S.table ? 'Table' : 'Results'}</h2>${table}</section>
      <section class="panel"><h2>Squads</h2>
        <div class="sc-clubs" role="group" aria-label="Clubs">${S.clubs.map(k => `<button type="button" class="chip" data-coclub="${esc(k.club_id)}" aria-pressed="${k.club_id === state.coClub}">${esc(k.name)}</button>`).join('')}</div>
        ${club ? `<p class="muted small">${esc([club.city, club.ground, plural(club.uploaded_matches || 0, 'uploaded match', 'uploaded matches')].filter(Boolean).join(' · '))}</p>
        <ol class="sc-squad">${(club.squad || []).map(p => `<li>
          <span class="tm-num">${esc(p.kit_number)}</span>
          <span class="sc-sqwho">${p.played && GID.test(p.global_id || '') ? `<a href="/players/${enc(p.global_id)}">${esc(p.name)}</a>` : esc(p.name)}<span class="muted small">${esc(POSITIONS[p.position] || p.position)} · age ${esc(p.age)}${p.career && p.career.length ? ` · also plays in ${esc(p.career.map(compName).filter(Boolean).join(', '))}` : ''}</span></span>
          <span class="small sc-sqmin">${p.played ? `${esc(plural(p.appearances, 'match', 'matches'))} · ${esc(Math.round(p.minutes))} min${p.qualified ? '' : ' · <span class="muted">not enough for a percentile</span>'}` : '<span class="muted">not in any uploaded match yet</span>'}</span></li>`).join('')}</ol>` : ''}</section>
      <p class="muted small">${esc(S.note || '')}</p>`;
  }
  $('coPage').addEventListener('click', async (e) => {
    const k = e.target.closest('[data-coclub]'), f = e.target.closest('[data-findin]'), a = e.target.closest('[data-coall]');
    if (f) { findIn(f.dataset.findin); return; }
    if (!a && !k) return;
    if (a) state.coAll = !state.coAll;
    if (k) state.coClub = k.dataset.coclub;
    const cid = state.coId;
    try {
      const S = await competition(cid);
      if (state.coId !== cid) return;
      paintCompetition(S, state.compOf.get(cid));
      const again = $('coPage').querySelector(k ? `[data-coclub="${CSS.escape(k.dataset.coclub)}"]` : '[data-coall]');
      if (again) again.focus();
    } catch (err) { /* the page already says what failed */ }
  });

  // ------------------------------------------------------------------ Team needs (the engine's answer)

  // Who fits a need: the engine's /api/catalogue/rank with min_percentile. At her level: by the stat per 90 (one level,
  // so raw numbers compare). From below (every men's level below semi-pro, any age): by each player's percentile in their
  // own level (raw numbers from different levels do not compare). A player with none of the stat never fits (none yet
  // has no percentile); women's pools are never mixed in (Fairhaven is a men's club). Her own club's players are left out.
  function fitQuery(n, side) {
    const u = new URLSearchParams({ metric: n.stat, position: n.pos, min_percentile: String(Number(n.pct) || 75), limit: String(LIMIT) });
    if (side === 'level') { u.set('tier', MY.tier); u.set('age_group', MY.age_group); u.set('gender', MY.gender); }
    else { u.set('tier', 'amateur,college,academy'); u.set('gender', MY.gender); u.set('rank_by', 'pool'); }
    return `/api/catalogue/rank?${u}`;
  }
  function fitsOf(n, side) {
    if (side === 'below' && n.where === 'level') return Promise.resolve([]);
    const url = fitQuery(n, side);
    if (!state.fits.has(url)) {
      const p = R.api(url).then(out => (out.players || []).filter(r => r.club_id !== CLUB_ID));
      p.catch(() => state.fits.delete(url));
      state.fits.set(url, p);
    }
    return state.fits.get(url);
  }
  const validNeed = (n) => n && POSITIONS[n.pos] && state.metrics.has(n.stat);
  async function needFits(n) {
    if (!validNeed(n)) return { level: [], below: [] };
    const [level, below] = await Promise.all([fitsOf(n, 'level'), fitsOf(n, 'below')]);
    return { level, below };
  }

  // ------------------------------------------------------------------ Overview

  // Each shortlisted player's catalogue answer (or null when there is none), for the Overview, the shortlist and compare.
  async function shortlistRows() {
    const gids = Object.keys(demo.shortlist()).filter(g => GID.test(g));
    const out = new Map();
    await Promise.all(gids.map(async (gid) => {
      try { out.set(gid, await catRows(gid)); } catch (e) { out.set(gid, null); }
    }));
    return out;
  }
  let overviewSeq = 0;
  async function paintOverview() {
    const mine = ++overviewSeq;
    const cards = [];
    for (const c of demo.forScout(demo.SCOUT)) {
      if (!(c.unread && c.unread.scout)) continue;
      const last = [...c.msgs].reverse().find(m => m.from === 'player');
      cards.push({ href: `/scout#messages/${enc(c.player)}`, head: `${nameOf(c.player, c.player_name)} replied`,
                   sub: last ? (last.text || 'Sent a moment') : '', cta: 'Read', hot: true });
    }
    // Matches shortlisted players uploaded through the Player view: named in the catalogue, never counted.
    const rows = await shortlistRows();
    const uploads = [];
    for (const [gid, P] of rows) {
      for (const u of (P && P.not_counted) || []) if (u.source === 'upload') uploads.push({ gid, u });
    }
    uploads.sort((a, b) => String(b.u.date || '').localeCompare(String(a.u.date || '')));
    for (const { gid, u } of uploads) {
      cards.push({ href: `/players/${enc(gid)}`, head: `${nameOf(gid)} added a match`,
                   sub: `A ${u.kind === 'friendly' ? 'friendly' : 'match'} v ${u.opponent || 'another club'}, filmed by the player and cut by Regista (not in the catalogue's numbers)`, cta: 'Profile' });
    }
    for (const r of demo.reports().filter(x => x.draft)) {
      cards.push({ href: `/scout#reports/${enc(r.gid)}`, head: `Your report on ${nameOf(r.gid)} is a draft`,
                   sub: 'Finish it with a verdict: Sign, Keep watching or Pass.', cta: 'Finish it' });
    }
    const needs = demo.needs().filter(validNeed);
    let fitCount = null;
    try {
      const all = await Promise.all(needs.map(needFits));
      fitCount = new Set(all.flatMap(f => [...f.level, ...f.below].map(r => r.global_id))).size;
    } catch (e) { /* the card says it could not count */ }
    cards.push({ href: '/scout#team', head: fitCount === null ? 'What Fairhaven needs' : `${plural(fitCount, 'player fits', 'players fit')} what Fairhaven needs`,
                 sub: needs.length ? `At your level and from below · ${needs.map(n => String(n.title || '').replace(/^An? /, '')).join(' · ')}` : 'Add what the club is looking for.', cta: 'See them' });
    let matches = [];
    try { matches = await catalogueMatches(); } catch (e) { /* the panel says so below */ }
    const asOf = state.cat.as_of;
    const weekAgo = new Date(Date.parse(`${asOf}T12:00:00Z`) - 7 * 86400000).toISOString().slice(0, 10);
    const week = matches.filter(m => m.date > weekAgo && m.date <= asOf);
    if (matches.length) {
      cards.push({ href: '/scout#competitions', head: `${plural(week.length, 'match', 'matches')} uploaded this week`,
                   sub: `In ${plural(new Set(week.map(m => m.competition_id)).size, 'competition')}, up to ${fmtDate(asOf)}`, cta: 'Browse' });
    }
    if (mine !== overviewSeq || state.section !== 'overview') return;
    $('ovNeeds').innerHTML = cards.map(c => `<a class="ov-need${c.hot ? ' hot' : ''}" href="${esc(c.href)}">
      <span class="ov-nh">${esc(c.head)}</span><span class="ov-ns">${esc(c.sub)}</span><span class="ov-cta">${esc(c.cta)} &rarr;</span></a>`).join('');

    const t = state.cat.totals || {};
    $('ovNewLine').textContent = matches.length
      ? `${t.matches} uploaded matches from ${t.competitions} competitions in ${t.countries} countries, up to ${fmtDate(asOf)}. The latest:`
      : 'The catalogue\'s uploaded matches are not available just now.';
    $('ovNewUploads').innerHTML = [...matches].sort(newestFirst).slice(0, 5).map(m => matchRow(m)).join('');

    const sl = demo.shortlist();
    const rowOf = (g) => { const P = rows.get(g); const r = P && primaryRow(P); return r ? { ...r, ...cardOfRow(P, r) } : null; };
    $('ovStages').innerHTML = demo.STAGES.map(st => {
      const ps = Object.keys(sl).filter(g => sl[g].stage === st);
      return `<a class="ov-tile sc-st" href="/scout#shortlist">${stageBadge(st)}<span class="pf-n">${esc(ps.length)}</span>
        <span class="pf-rate">${ps.map(g => { const r = rowOf(g); return `${esc(nameOf(g))}${r ? ` <span class="sc-tlvl">(${esc(r.country)}, ${esc(levelWords(r))})</span>` : ''}`; }).join(', ') || 'Nobody yet'}</span></a>`;
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
      const r = rowOf(gid);
      const where = r && r.competition_id !== MY.competition_id ? ` (${r.competition}, ${r.country}, ${levelWords(r)})` : '';
      act.push({ k: 'match', at: v.at, href: '/scout#shortlist', text: `${nameOf(gid)}${where} is on your shortlist: ${v.stage}` });
    }
    for (const { gid, u } of uploads) {
      const at = Date.parse(`${u.date}T12:00:00Z`);
      if (isFinite(at)) act.push({ k: 'up', at, href: `/players/${enc(gid)}`, text: `${nameOf(gid)} added a ${u.kind === 'friendly' ? 'friendly' : 'match'} v ${u.opponent || 'another club'}` });
    }
    act.sort((a, b) => (b.at || 0) - (a.at || 0));
    $('ovActivity').innerHTML = act.slice(0, 6).map(a => `<li><span class="ov-dot k-${esc(a.k)}" aria-hidden="true"></span>
      <a href="${esc(a.href)}">${esc(a.text)}</a><span class="muted small">${esc(demo.whenText(a.at, true))}</span></li>`).join('')
      || '<li class="muted small">Nothing yet.</li>';
  }

  // ------------------------------------------------------------------ Shortlist: stages and compare

  // The number a shortlist item leads with: the player's best percentile among their position's lead numbers.
  function itemLine(r) {
    const k = strongest(r);
    const c = k && r.values[k];
    if (!c) return '';
    return `<span class="small">${esc(fmtRate(c.value))} ${esc(shortStat(k))} per 90 · ${esc(poolLine(c, r))}${care(c, r.minutes)}</span>${smallFlag(c, r)}`;
  }
  let boardSeq = 0;
  async function paintBoard() {
    const mine = ++boardSeq;
    const sl = demo.shortlist();
    const picked = new Set(demo.compare());
    const ids = Object.keys(sl).filter(g => GID.test(g));
    $('shortEmpty').hidden = ids.length > 0;
    const rows = await shortlistRows();
    if (mine !== boardSeq) return;
    $('scBoard').innerHTML = demo.STAGES.map(st => {
      const here = ids.filter(g => sl[g].stage === st);
      return `<section class="sc-col panel" aria-label="${esc(st)}"><h2>${stageBadge(st)} <span class="muted small">${esc(here.length)}</span></h2>
        ${here.map(gid => {
          const P = rows.get(gid), row = P && primaryRow(P), r = row ? { ...cardOfRow(P, row) } : null;
          const p = r || player(gid) || { name: gid, position: '', club: '' };
          const on = picked.has(gid);
          const full = !on && picked.size >= COMPARE_MAX;
          return `<article class="sc-item" data-item="${esc(gid)}" tabindex="-1">
            <a href="/players/${enc(gid)}"><b>${esc(p.name)}</b></a>
            <span class="muted small">${esc(posLine(p))}</span>
            ${r ? `<span class="sc-where small"><span>${esc(whereLine(r))}</span>${levelChip(r)}</span>
            ${itemLine(r)}
            <span class="muted small">${esc(sampleLine(r))}</span>` : '<span class="muted small">Not in an uploaded match yet.</span>'}
            ${sl[gid].note ? `<p class="sc-inote">${esc(sl[gid].note)}</p>` : ''}
            <div class="sc-iacts"><label class="sc-cmp"><input type="checkbox" data-cmp="${esc(gid)}"${on ? ' checked' : ''}${full || !r ? ' disabled' : ''}> Compare</label>
              <label><span class="sr">Move ${esc(p.name)} to</span><select data-move="${esc(gid)}">${demo.STAGES.map(s2 =>
                `<option value="${esc(s2)}"${s2 === st ? ' selected' : ''}>${esc(s2)}</option>`).join('')}<option value="">Remove</option></select></label></div></article>`;
        }).join('') || '<p class="muted small">Nobody here yet.</p>'}</section>`;
    }).join('');
    paint($('scBoard'));
    const n = [...picked].filter(g => sl[g]).length;
    $('compareGo').disabled = n < 2;
    $('compareGo').textContent = n ? `Compare (${n})` : 'Compare';
    $('compareHint').textContent = n >= 2 ? `${n} picked. Compare holds up to three.`
      : n === 1 ? 'Tick one more to compare.' : 'Tick two or three players to compare them.';
  }

  async function openShortlist(gid) {
    if (gid) {
      if (!demo.onShortlist(gid)) demo.setStage(gid, 'Watching');
      const inIt = demo.compare().includes(gid) || demo.toggleCompare(gid);
      settle('shortlist');
      await paintBoard();
      if (!inIt) $('compareHint').textContent = `Compare holds three players. Untick one to add ${nameOf(gid)}.`;
      const item = $('scBoard').querySelector(`[data-item="${CSS.escape(gid)}"]`);
      if (item) {
        item.classList.add('flash');
        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
        item.focus({ preventScroll: true });
      }
      return;
    }
    paintBoard();
  }

  $('scBoard').addEventListener('change', async (e) => {
    const t = e.target;
    if (t.dataset.cmp) {
      const gid = t.dataset.cmp;
      if (t.checked !== demo.compare().includes(gid)) demo.toggleCompare(gid);
      await paintBoard();
      const again = $('scBoard').querySelector(`input[data-cmp="${CSS.escape(gid)}"]`);
      if (again) again.focus();
    }
    if (t.dataset.move !== undefined) {
      const gid = t.dataset.move;
      demo.setStage(gid, t.value);
      await paintBoard();
      const again = $('scBoard').querySelector(`select[data-move="${CSS.escape(gid)}"]`);
      (again || $('compareGo')).focus();
    }
  });

  // Compare: the catalogue's compare (/api/catalogue/compare): each number with its percentile and pool; the server marks
  // the best (one level: the best value as shown; several levels, one position: the best percentile; several levels and
  // positions: nothing). A count at 0 reads "None yet" and is never marked best.
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
      const rows = await shortlistRows();
      const positions = ids.map(g => { const P = rows.get(g), r = P && primaryRow(P); return r ? r.position : (player(g) || {}).position; });
      const keys = [...new Set([...positions.flatMap(p => LEAD[p] || LEAD.FW), ...COMPARE_ALL])].filter(k => state.metrics.has(k)).slice(0, 16);
      const out = await R.api(`/api/catalogue/compare?ids=${ids.map(enc).join(',')}&metrics=${keys.join(',')}`);
      clearNetError();
      renderCompare(out, keys);
    } catch (e) {
      $('compareBody').innerHTML = `<p class="muted">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
    } finally {
      $('compareGo').disabled = demo.compare().filter(g => demo.shortlist()[g]).length < 2;
    }
  }

  function renderCompare(out, keys) {
    const ps = out.players || [];
    const levels = new Set(ps.map(levelKey)), poss = new Set(ps.map(p => p.position));
    const oneLevel = levels.size === 1, onePos = poss.size === 1;
    $('compareNote').className = `${oneLevel ? 'muted ' : 'sc-warnline '}small`;
    $('compareNote').textContent = (oneLevel
      ? `Per 90 minutes. Everyone here plays at one level (${levelWords(ps[0] || {})}), so the numbers compare directly; the best is in yellow.`
      : `Per 90 minutes, each with its percentile in the player's own level. These players play at different levels: read each percentile against its own pool. A raw number from one level is not better or worse than the same number from another.${onePos ? ' The highest percentile is in yellow.' : ' Nothing is marked best across levels and positions.'}`)
      + ' Pick a number to see the moments behind it.';
    const head = ps.map(p => `<th scope="col"><span class="sc-shirt" aria-hidden="true">${shirt(p, 34)}</span>
        <a href="/players/${enc(p.global_id)}">${esc(p.name)}</a>
        <span class="muted small">${esc(POSITIONS[p.position] || p.position)} · ${esc(p.club)}</span>
        <span class="muted small">${esc(p.country)} · ${esc(levelWords(p))}</span>
        <span class="muted small">${esc(fmtMinutes(p.minutes))}</span></th>`).join('');
    const body = keys.filter(k => ps.some(p => p.values && p.values[k])).map(k => {
      const label = labelOf(k);
      const best = new Set((out.best && out.best[k]) || []);
      const cells = ps.map(p => {
        const c = p.values && p.values[k];
        if (!c) return '<td>–</td>';
        const isBest = best.has(p.global_id);
        const pct = c.none_yet ? `None yet${c.zeros ? ` · ${c.zeros.none === c.zeros.of ? `all ${c.zeros.of}` : `${c.zeros.none} of ${c.zeros.of}`} in the pool have none` : ''}`
          : c.percentile !== null && c.percentile !== undefined ? `${ord(c.percentile)} percentile · pool ${c.pool?.size ?? c.peers}` : 'no percentile';
        const said = poolLine(c, p);
        return `<td class="${isBest ? 'best' : ''}"><button type="button" class="link" data-ev="${esc(p.global_id)}|${esc(p.competition_id)}|${esc(k)}"
            aria-label="${esc(`${p.name}: ${fmtRate(c.value)} ${label.toLowerCase()} per 90. ${said}. Show the moments`)}">${esc(fmtRate(c.value))}</button>${care(c, p.minutes)}${isBest ? '<span class="sr"> (best)</span>' : ''}
          <span class="sc-cpct">${esc(pct)}${!c.none_yet && c.pool && c.pool.small && c.pool.size ? ' · small pool' : ''}</span></td>`;
      }).join('');
      return `<tr><th scope="row">${esc(label)}</th>${cells}</tr>`;
    }).join('');
    $('compareBody').innerHTML = `<table class="sc-ctable ctable">
      <caption class="sr">${esc(ps.map(p => p.name).join(', '))} compared, per 90 minutes</caption>
      <thead><tr><td></td>${head}</tr></thead><tbody>${body}</tbody>
    </table>`;
    paint($('compareBody'));
  }

  // The moments behind one number in the comparison: the catalogue's evidence for that stat in that competition, each
  // playing beside the list, paged by evidence_offset.
  async function compareEvidence(gid, cid, key, offset = 0) {
    const box = $('compareEv');
    box.hidden = false;
    if (!offset) box.innerHTML = '<p class="muted small">Loading the moments…</p>';
    let E;
    try {
      E = await R.api(`/api/catalogue/players/${enc(gid)}?evidence=${enc(key)}&competition=${enc(cid)}${offset ? `&evidence_offset=${offset}` : ''}`);
    } catch (e) {
      box.innerHTML = `<p class="muted small">${esc(offline(e) ? OFFLINE : detail(e))}</p>`;
      return;
    }
    const ev = E.evidence || { items: [], total: 0 };
    const label = labelOf(key).toLowerCase();
    const items = ev.items || [];
    const li = (e) => {
      const where = `Round ${e.round ?? '?'} · ${e.minute ?? '?'}'`;
      return e.clip_id && VIDEO.test(e.video_url || '')
        ? `<li><button type="button" class="link" data-cplay="${esc(e.video_url)}" data-cnow="${esc(`${cap(label)} · ${where}`)}">&#9654; ${esc(where)}</button></li>`
        : `<li><span class="small">${esc(where)}</span> <span class="muted small">no clip of its own</span>${CLIP_VIEW.test(e.link || '') ? ` <a class="small" href="${esc(e.link)}">Open the match</a>` : ''}</li>`;
    };
    if (offset) {
      const list = box.querySelector('ol');
      if (list) list.insertAdjacentHTML('beforeend', items.map(li).join(''));
      const more = box.querySelector('[data-evmore]');
      const shown = offset + items.length;
      if (more) { if (shown < ev.total) { more.dataset.evmore = String(shown); more.textContent = `Show more (${shown} of ${ev.total})`; } else more.remove(); }
      return;
    }
    const total = E.total ?? ev.total;
    box.innerHTML = `<div class="pf-bar"><h3 tabindex="-1" id="compareEvHead">${esc(E.name)}, ${esc(label)} in ${esc(E.competition)}: ${esc(total ?? 0)}${ev.total > items.length ? ` <span class="muted small">(the first ${esc(items.length)} of ${esc(ev.total)} moments)</span>` : ''}</h3>
        <button type="button" class="alt" data-evclose>Close</button></div>
      <div class="sc-cevgrid"><div><ol>${items.map(li).join('') || '<li class="muted small">None in the uploaded matches.</li>'}</ol>
        ${ev.total > items.length ? `<button type="button" class="link" data-evmore="${esc(items.length)}" data-ev="${esc(gid)}|${esc(cid)}|${esc(key)}">Show more (${esc(items.length)} of ${esc(ev.total)})</button>` : ''}</div>
      <div><div class="pf-screen"><video id="compareVideo" data-now="compareNow" controls playsinline preload="none"></video></div>
        <p class="small muted" id="compareNow">${items.length ? 'Pick a moment to play it.' : ''}</p></div></div>`;
    $('compareEvHead').focus({ preventScroll: true });
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  $('compareBody').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ev]');
    if (!b) return;
    const [gid, cid, key] = b.dataset.ev.split('|');
    if (GID.test(gid) && COID.test(cid)) compareEvidence(gid, cid, key);
  });
  $('compareEv').addEventListener('click', (e) => {
    if (e.target.closest('[data-evclose]')) { $('compareEv').hidden = true; $('compareVideo')?.pause(); return; }
    const more = e.target.closest('[data-evmore]');
    if (more) {
      const [gid, cid, key] = more.dataset.ev.split('|');
      if (GID.test(gid) && COID.test(cid)) compareEvidence(gid, cid, key, Number(more.dataset.evmore) || 0);
      return;
    }
    const c = e.target.closest('[data-cplay]');
    if (c) playInto($('compareVideo'), c.dataset.cplay, $('compareNow'), c.dataset.cnow);
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
    const order = [...Object.keys(sl).filter(g => player(g)), ...[...state.all.keys()].filter(g => !sl[g])];
    $('newReportFor').innerHTML = order.map(g => {
      const p = player(g);
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
    const order = [...Object.keys(sl).filter(g => player(g)), ...[...state.all.keys()].filter(g => !sl[g])];
    const keep = $('newMsgTo').value;
    $('newMsgTo').innerHTML = order.map(g => {
      const p = player(g);
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

  async function paintTeam() {
    const keep = $('needStat').value;
    $('needStat').innerHTML = NEED_STATS.filter(k => state.metrics.has(k)).map(k => `<option value="${esc(k)}">${esc(labelOf(k))} per 90</option>`).join('');
    if (keep) $('needStat').value = keep;
    paintNeeds();
    let S;
    try { S = await competition(MY.competition_id); } catch (e) {
      $('clubLine').textContent = offline(e) ? OFFLINE : detail(e);
      return;
    }
    const C = (S.clubs || []).find(c => c.club_id === CLUB_ID);
    if (!C) return;
    const row = (S.table || []).find(t => t.club_id === CLUB_ID);
    const k = C.kit || {};
    if (HEX.test(k.primary || '') && HEX.test(k.secondary || '')) $('crest').style.background = `linear-gradient(135deg, ${k.primary} 50%, ${k.secondary} 50%)`;
    $('clubHead').textContent = C.name;
    $('clubLine').textContent = [`${S.name}, ${S.country}`, state.poolOf.get(MY_KEY)?.words, C.ground,
      row ? `${row.position === 1 ? 'top of the table' : `${PV.ordinal(row.position)} in the table`}, ${plural(row.points, 'point')} from ${plural(row.played, 'match', 'matches')}` : '']
      .filter(Boolean).join(' · ');
    $('squad').innerHTML = [...(C.squad || [])].sort((a, b) => a.kit_number - b.kit_number).map(p => `<li><span class="tm-num">${esc(p.kit_number)}</span>
      <span>${GID.test(p.global_id || '') ? `<a href="/players/${enc(p.global_id)}">${esc(p.name)}</a>` : esc(p.name)}</span>
      <span class="muted small">${esc(POSITIONS[p.position] || p.position)}${p.starter ? '' : ' · substitute'}${p.played ? ` · ${esc(Math.round(p.minutes))} min` : ''}</span></li>`).join('')
      || '<li class="muted small">No squad listed.</li>';
  }

  // One player who fits a need (a row of /api/catalogue/rank: the card and the need's stat).
  function fitRow(r, n) {
    const sl = demo.shortlist()[r.global_id];
    return `<a href="/players/${enc(r.global_id)}" class="sc-minirow"><span class="sc-shirt" aria-hidden="true">${shirt(r)}</span>
      <span><b>${esc(r.name)}</b> <span class="muted small">${esc(r.club)} · ${esc(whereLine(r))}</span>
        <span class="small">${esc(fmtRate(r.value))} ${esc(shortStat(n.stat))} per 90 · ${esc(poolLine(r, r))}${r.pool && r.pool.small ? ' · <span class="sc-small">Small pool</span>' : ''}${care(r, r.minutes)}</span>
        <span class="muted small">${esc(fmtMinutes(r.minutes))} · age ${esc(r.age)}</span></span>${sl ? stageBadge(sl.stage) : ''}</a>`;
  }
  function needList(n, side, rows, empty) {
    const k = `${n.id}|${side}`, all = state.needOpen.has(k), shown = all ? rows : rows.slice(0, NEED_N);
    return `<div class="sc-mini">${shown.map(r => fitRow(r, n)).join('') || `<p class="muted small">${esc(empty)}</p>`}</div>
      ${rows.length > NEED_N ? `<p class="small sc-nmore">${all ? `All ${esc(rows.length)} shown · ` : `${esc(NEED_N)} of ${esc(rows.length)} shown · `}<button type="button" class="link" data-needmore="${esc(k)}">${all ? `Show the first ${esc(NEED_N)}` : `Show all ${esc(rows.length)}`}</button></p>` : ''}`;
  }
  let needsSeq = 0;
  async function paintNeeds() {
    const mine = ++needsSeq;
    const needs = demo.needs();
    const words = state.poolOf.get(MY_KEY)?.words || 'semi-pro men';
    if (!needs.length) { $('needs').innerHTML = '<p class="muted small">No needs yet. Add what the club is looking for.</p>'; return; }
    if (!$('needs').children.length) $('needs').innerHTML = '<p class="muted small">Finding who fits…</p>';
    const fits = await Promise.all(needs.map(n => needFits(n).catch(() => null)));
    if (mine !== needsSeq) return;
    $('needs').innerHTML = needs.map((n, i) => {
      const f = fits[i];
      const pos = POSITIONS[n.pos] || n.pos;
      const head = `<div class="pf-bar"><h3>${esc(n.title)}</h3><button type="button" class="link" data-dropneed="${esc(n.id)}"
          aria-label="Remove the need: ${esc(n.title)}">Remove</button></div>`;
      if (!validNeed(n)) return `<article class="sc-need">${head}<p class="muted small">This need names a number the catalogue does not have. Remove it and add it again.</p></article>`;
      if (!f) return `<article class="sc-need">${head}<p class="muted small">${esc(OFFLINE)}</p></article>`;
      const below = n.where !== 'level';
      return `<article class="sc-need">${head}
        <p class="muted small">${esc(pos)}s with ${esc(shortStat(n.stat))} per 90 better than ${esc(n.pct)}% of their own level's ${esc(GROUP[n.pos] || 'players')} · ${esc(plural(f.level.length + f.below.length, 'fits', 'fit'))}</p>
        <h4 class="sc-nh">At your level <span class="muted small">${esc(words)} · ${esc(f.level.length)} · ranked by ${esc(shortStat(n.stat))} per 90</span></h4>
        ${needList(n, 'level', f.level, 'Nobody at your level fits this yet.')}
        ${below ? `<h4 class="sc-nh">From below <span class="muted small">amateur, college and academy men · ${esc(f.below.length)} · ranked by their percentile for ${esc(shortStat(n.stat))} per 90 in their own level</span></h4>
        ${needList(n, 'below', f.below, 'Nobody from below fits this yet.')}` : ''}</article>`;
    }).join('');
    paint($('needs'));
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
    if (!POSITIONS[pos] || !state.metrics.has(stat)) return;
    const title = $('needTitle').value.trim().slice(0, 60) || `A ${POSITIONS[pos].toLowerCase()} strong on ${shortStat(stat)}`;
    const where = $('needWhere').value === 'level' ? 'level' : 'below';
    demo.saveNeeds([...demo.needs(), { id: `nd_${Date.now().toString(36)}`, title, pos, stat, pct: Number($('needPct').value) || 75, where }]);
    $('needTitle').value = '';
    toggleBox($('addNeed'), $('needForm'), false);
    paintNeeds();
    $('addNeed').focus();
  });
  $('needs').addEventListener('click', (e) => {
    const m = e.target.closest('[data-needmore]');
    if (m) {
      const k = m.dataset.needmore;
      if (state.needOpen.has(k)) state.needOpen.delete(k); else state.needOpen.add(k);
      paintNeeds().then(() => { const again = $('needs').querySelector(`[data-needmore="${CSS.escape(k)}"]`); if (again) again.focus(); });
      return;
    }
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
    $('stResetNote').textContent = 'Done: messages, the shortlist, reports, needs, settings and the Terminal saved layouts are back to how they started.';
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
  });

  async function start() {
    counts();
    try {
      await Promise.all([loadCatalogue(), loadAll()]);
    } catch (e) {
      $('cards').innerHTML = '<p class="muted">The catalogue is not available.</p>';
      netError(e, start);
      return;
    }
    clearNetError();
    state.ready = true;
    fillFilters();
    loadFind();
    // the shortlist's players, so their names read everywhere (Messages, Reports) before anyone opens them
    shortlistRows().then(() => { if (state.section === 'messages') paintMessages(); if (state.section === 'reports') paintReports(); });
    show(nav.section(), nav.rest());
  }
  start();
})();
