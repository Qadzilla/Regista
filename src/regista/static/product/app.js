// The Product (/): ask for a moment, watch it, take it away. One result set on screen at a time: the selected player's
// moments until the first question, then whatever the last reply found. Every reply drives the grid, the timeline and
// the stage. Plain script on top of window.Regista (/static/shared/regista.js); the timeline is /static/product/timeline.js.
(function () {
  const R = window.Regista;
  // Everything that reaches innerHTML from the API goes through esc(): names, titles, tags, explanations, replies and
  // tool names can come from uploads, reviewers or models, so they are never trusted as markup.
  const esc = R.esc;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const REEL_MAX = 12;  // what /reel.mp4 accepts

  const state = {
    matches: [], match: null, info: null, player: null,
    all: new Map(),          // clip id -> clip as GET /clips returns it, every player: the grid's labels, the timeline
    results: [], total: 0,   // the current result set (normalised rows) and how many the question matched in all
    fromQuestion: false,     // false: the picked player's moments; true: the last reply's results
    reel: null,              // clip ids of the last "make a reel" reply, if any
    sort: 'best', selected: null, health: null,
  };
  const chat = { state: null, history: [], busy: false };

  // ------------------------------------------------------------------ small helpers

  const matchUrl = (path = '') => `/api/matches/${enc(state.match)}${path}`;
  const player = (pid) => state.info?.players.find(p => p.player_id === pid);
  const team = (tid) => state.info?.teams.find(t => t.team_id === tid);
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';

  // The name people would say: the surname when no one else in the match has it, else the full name.
  function spokenName(p) {
    const last = p.name.split(' ').slice(-1)[0];
    return state.info.players.filter(o => o.name.split(' ').slice(-1)[0] === last).length === 1 ? last : p.name;
  }

  // A clip from GET /clips or a result from /chat, as one shape. Chat results carry no label model, so the badge
  // reads it from the match's clips.
  function row(c) {
    const id = c.id || c.clip_id;
    const full = state.all.get(id);
    const lb = c.label || full?.label || {};
    return {
      id, player_id: c.player_id, t: c.t, t_end: c.t_end, reason: c.reason,
      title: c.title ?? lb.title, tags: c.tags ?? lb.tags ?? [], watchability: c.watchability ?? lb.watchability ?? 0,
      explanation: c.explanation ?? lb.explanation ?? '', model: lb.model || '',
      video_url: c.video_url !== undefined ? c.video_url : (full ? full.video_url : null),
    };
  }

  const sorted = (rows) => [...rows].sort(state.sort === 'time'
    ? (a, b) => a.t - b.t
    : (a, b) => (b.watchability - a.watchability) || (a.t - b.t));

  const plainTags = (tags) => tags.filter(t => !/_appearance$|^on_ball_main$|^touch$/.test(t));

  // ------------------------------------------------------------------ loading

  async function init() {
    wire();
    loadHealth();
    try {
      state.matches = await R.api('/api/matches');
    } catch (e) {
      return fatal(`Regista could not list its matches: ${detail(e)}`);
    }
    if (!state.matches.length) return fatal('There are no matches on this server yet.');
    $('match').innerHTML = state.matches.map(m => {
      const [a, b] = m.teams;
      const score = m.score ? ` ${esc(m.score[a.team_id])}–${esc(m.score[b.team_id])} ` : ' v ';
      return `<option value="${esc(m.match_id)}">${esc(a.name)}${score}${esc(b.name)}${m.source === 'cosmos' ? ' (from Cosmos DB)' : ''}</option>`;
    }).join('');
    await loadMatch(state.matches[0].match_id);
  }

  function fatal(text) {
    $('resultsHead').textContent = 'Moments';
    showEmpty(esc(text));
    $('stage').hidden = true;
  }

  async function loadMatch(id) {
    state.match = id;
    $('match').value = id;
    $('grid').innerHTML = '';
    showEmpty('Loading the match…');
    try {
      const [info, clips] = await Promise.all([R.api(matchUrl()), R.api(matchUrl('/clips'))]);
      state.info = info;
      state.all = new Map(clips.map(c => [c.id, { ...c, title: c.label?.title }]));
    } catch (e) {
      return fatal(`This match could not be loaded: ${detail(e)}`);
    }
    $('stage').hidden = false;
    const listed = state.matches.find(m => m.match_id === id);
    fillPlayers(listed?.clips_for);
    $('reportLink').href = matchUrl('/report');
    $('fullMatch').href = matchUrl('/video.mp4');
    $('fullMatch').hidden = state.info.source === 'cosmos';
    const cosmosOnly = state.info.source === 'cosmos';
    $('q').disabled = cosmosOnly; $('go').disabled = cosmosOnly;
    for (const b of $('examples').querySelectorAll('button')) b.disabled = cosmosOnly;
    newConversation();
    if (cosmosOnly) $('engineHint').textContent = 'This match is read from Cosmos DB without its event stream, so it cannot answer questions here. Its moments are below.';
  }

  function fillPlayers(preferred) {
    const withClips = new Set(state.info.players_with_clips);
    const label = (p) => `${esc(p.name)} · ${esc(p.kit_number)} · ${esc(team(p.team_id)?.name || p.team_id)}`;
    const opt = (p) => `<option value="${esc(p.player_id)}">${label(p)}</option>`;
    const ps = [...state.info.players].sort((a, b) => a.team_id.localeCompare(b.team_id) || (a.kit_number - b.kit_number));
    const have = ps.filter(p => withClips.has(p.player_id)), rest = ps.filter(p => !withClips.has(p.player_id));
    $('player').innerHTML = (have.length ? `<optgroup label="Players with moments">${have.map(opt).join('')}</optgroup>` : '')
      + (rest.length ? `<optgroup label="Everyone else">${rest.map(opt).join('')}</optgroup>` : '');
    state.player = (preferred && withClips.has(preferred) ? preferred : null) || have[0]?.player_id || ps[0]?.player_id;
    $('player').value = state.player;
  }

  // ------------------------------------------------------------------ the conversation

  // The server keeps nothing between turns: it merges each message into the query so far and returns it, and the page
  // sends it back. It starts from the picked player, so "make a reel of his best moments" knows who "his" is.
  function seed() {
    return { player_ids: state.player ? [state.player] : [], team_id: null, tags: [], reasons: [], minutes: null, limit: null, offset: 0 };
  }

  function newConversation() {
    chat.state = seed(); chat.history = [];
    $('log').innerHTML = ''; $('log').hidden = true;
    $('landing').hidden = false;
    renderExamples();
    engineHint();
    showPlayerMoments();
  }

  function renderExamples() {
    const p = player(state.player);
    const who = p ? spokenName(p) : 'Castellanos';
    const his = p ? `${spokenName(p)}'s` : 'his';
    const asks = [`Find me ${who} doing a nutmeg`, `Every touch by ${who}, in match order`, `Make a reel of ${his} best moments`];
    $('examples').innerHTML = asks.map(a => `<button type="button" class="example">${esc(a)}</button>`).join('');
    for (const b of $('examples').querySelectorAll('button')) b.onclick = () => { $('q').value = b.textContent; send(); };
  }

  const engine = () => document.querySelector('input[name="engine"]:checked').value;

  function engineHint() {
    if (state.info?.source === 'cosmos') return;
    const h = state.health;
    $('engineHint').textContent = engine() === 'rules'
      ? 'Instant: Regista\'s own rules find the moments and write the reply, in-process. Follow-ups build on what you asked; "start over" clears it.'
      : (h && !h.cloud.foundry
        ? 'Foundry is not configured on this server, so the Instant reply will stand. The moments found are the same.'
        : 'Foundry: the same search, then a Microsoft Foundry model writes the reply and may call its tools. Takes a few seconds.');
  }

  function addMsg(cls, html) {
    const div = document.createElement('div');
    div.className = `msg ${cls}`;
    div.innerHTML = html;
    $('log').hidden = false;
    $('log').appendChild(div);
    $('log').scrollTop = $('log').scrollHeight;
    const how = div.querySelector('details');
    if (how) how.addEventListener('toggle', () => { if (how.open) how.scrollIntoView({ block: 'nearest' }); });
    return div;
  }

  async function send(message = $('q').value.trim()) {
    if (!message || chat.busy || !state.match) return;
    chat.busy = true; $('go').disabled = true; $('q').value = '';
    $('landing').hidden = true;
    addMsg('me', esc(message));
    const eng = engine();
    const wait = addMsg('bot wait', eng === 'foundry' ? 'Searching, then asking Microsoft Foundry to write the reply…' : 'Searching…');
    try {
      const out = await R.api(matchUrl('/chat'), { method: 'POST', body: { message, state: chat.state, history: chat.history, engine: eng } });
      wait.remove();
      chat.state = out.state; chat.history = out.history;
      addMsg('bot', `${esc(out.reply)}${howAnswered(out, eng)}`);
      if (/match order|in order|chronolog/i.test(message)) setSort('time');
      else if (/\bbest\b|\btop\b/i.test(message)) setSort('best');
      applyReply(out);
    } catch (e) {
      wait.remove();
      const text = e.status === 429 ? detail(e) : e.status === 404 ? 'This match is not on this server any more. Pick another match.'
        : `Regista could not answer: ${detail(e)}`;
      addMsg('bot err', esc(text));
    } finally {
      chat.busy = false; $('go').disabled = state.info?.source === 'cosmos';
      $('q').focus();
    }
  }

  // "How Regista answered": what was understood, who answered, and the steps in order with their times (the trace),
  // or the tools the model called when there is no trace. The Instant path says plainly that no model ran.
  function howAnswered(out, eng) {
    const by = String(out.answered_by || 'rules');
    const instant = by.startsWith('rules');
    const SERVERS = { 'regista-mcp': 'Regista MCP server', 'azure-mcp': 'Azure MCP Server' };
    const ms = (v) => v == null ? '–' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;
    let steps = '';
    if (Array.isArray(out.trace) && out.trace.length) {
      steps = `<ol class="steps">${out.trace.map(s => `<li><span class="kind">${esc(s.kind)}</span><code>${esc(s.name)}</code>`
        + `${s.server ? `<span class="server">${esc(SERVERS[s.server] || s.server)}</span>` : ''}<span class="ms">${esc(ms(s.ms))}</span></li>`).join('')}</ol>`;
    } else if ((out.tools_used || []).length) {
      steps = `<div class="tags">${out.tools_used.map(t => `<span class="tool">${esc(t)}</span>`).join(' ')}</div>`;
    }
    const engineName = eng === 'foundry' ? 'Foundry' : 'Instant';
    const note = instant ? 'Ran in-process: no model, no MCP.' : `Written by ${esc(by.replace(/^foundry:/, 'Microsoft Foundry, '))}.`;
    return `<details class="how"><summary>How Regista answered</summary><dl>`
      + `<dt>Understood</dt><dd>${esc(out.understood || '–')}</dd>`
      + `<dt>Engine</dt><dd>${esc(engineName)} · answered by ${esc(by)}</dd>`
      + `<dt>How</dt><dd>${note}</dd>`
      + (steps ? `<dt>Steps</dt><dd>${steps}</dd>` : '')
      + `</dl></details>`;
  }

  function applyReply(out) {
    if (out.intent === 'reset') { restartQuery(); return; }
    const rows = (out.results || []).map(row);
    state.fromQuestion = true;
    state.reel = out.reel && out.reel.length ? out.reel.map(c => c.clip_id) : null;
    // "more" pages through the same question: the new page joins the set already on screen.
    state.results = out.intent === 'more' ? [...state.results, ...rows.filter(r => !state.results.some(x => x.id === r.id))] : rows;
    state.total = out.total ?? rows.length;
    state.selected = null;
    const ids = out.state?.player_ids || [];
    if (ids.length === 1 && ids[0] !== state.player && player(ids[0])) { state.player = ids[0]; $('player').value = ids[0]; renderExamples(); }
    $('resultsHead').innerHTML = `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(out.understood || '')}</span>`;
    render(state.results.length ? '' : 'Nothing matched that question. Try a player\'s surname, a kit number, or an action like "nutmeg" or "shot".');
    if (state.reel) playReel();
  }

  // "Start over" from the ask box: the log stays (it is the record of the conversation), the query and results reset.
  function restartQuery() {
    chat.state = seed(); chat.history = [];
    showPlayerMoments();
  }

  // ------------------------------------------------------------------ the result set: grid, timeline, stage

  function showPlayerMoments() {
    const p = player(state.player);
    state.fromQuestion = false; state.reel = null; state.selected = null;
    state.results = [...state.all.values()].filter(c => c.player_id === state.player).map(row);
    state.total = state.results.length;
    $('resultsHead').innerHTML = p
      ? `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(p.name)}, ${esc(team(p.team_id)?.name || '')}</span>`
      : 'Moments';
    render(p ? `No moments for ${esc(p.name)} in this match yet. Regista cuts a player's moments when the match is processed for them; pick a player from "Players with moments".`
      : 'Pick a player.');
  }

  function showEmpty(html) { $('empty').hidden = !html; $('empty').innerHTML = html || ''; }

  function render(emptyHtml) {
    const rows = sorted(state.results);
    showEmpty(rows.length ? '' : emptyHtml);
    const shown = state.fromQuestion ? state.results.length : state.total;
    $('more').hidden = !(state.fromQuestion && state.total > shown);
    $('more').textContent = `Show more (${state.total - shown} more)`;
    const vision = state.info?.origin === 'vision';
    $('grid').innerHTML = rows.map(r => `
      <button type="button" class="card" data-id="${esc(r.id)}" aria-label="Play ${esc(r.title)}">
        ${r.video_url ? `<video muted playsinline preload="none" src="${esc(r.video_url)}"></video>`
          : `<span class="novideo">Read from Cosmos DB. The labels and timings are stored there; this server does not hold the match's video.</span>`}
        <span class="body">
          <span class="reason ${r.reason === 'replay_appearance' ? 'replay' : ''}">${esc(R.reasonLabel(r.reason))} · ${esc(R.fmtTime(r.t))}</span>
          <span class="title">${esc(r.title)}</span>
          <span class="bar" title="How worth watching, from 0 to 1: ${esc(Number(r.watchability).toFixed(2))}"><i style="width:${Math.round(r.watchability * 100)}%"></i></span>
          <span class="tags">${plainTags(r.tags).map(t => `<span>${esc(R.tagLabel(t))}</span>`).join('')}</span>
          ${badges(r, vision)}
        </span>
      </button>`).join('');
    for (const card of $('grid').querySelectorAll('.card')) card.onclick = () => select(card.dataset.id, true);
    lazyPreview($('grid'));
    renderTimeline();
    renderStage();
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

  // The timeline is agent C's component (timeline.js). Until it is on the server, its place stays empty and hidden.
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
        highlight: new Set(state.results.map(r => r.id)),
        onPick: (id) => select(id, true),
      });
    } catch (e) {
      $('timelineWrap').hidden = true;
    }
  }

  function select(id, play) {
    state.selected = id;
    stopReel();
    renderStage(play);
    for (const c of $('grid').querySelectorAll('.card')) c.classList.toggle('on', c.dataset.id === id);
    if (play) $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function current() {
    const rows = sorted(state.results);
    return rows.find(r => r.id === state.selected) || (state.selected && state.all.has(state.selected) ? row(state.all.get(state.selected)) : rows[0]);
  }

  function renderStage(play = false, prefix = '') {
    const r = current();
    const v = $('stageVideo');
    reelLinks();
    if (!r) {
      v.removeAttribute('src'); v.hidden = true; $('stageLoading').hidden = true;
      $('stageNoVideo').hidden = false; $('stageNoVideo').textContent = 'No moments to play here yet.';
      $('stageNow').textContent = ''; $('stageTitle').textContent = 'Nothing to play yet';
      $('stageTags').innerHTML = ''; $('stageWhy').textContent = '';
      return;
    }
    $('stageNow').textContent = prefix || `${R.reasonLabel(r.reason)} · ${R.fmtTime(r.t)}–${R.fmtTime(r.t_end)}`;
    $('stageTitle').textContent = r.title || '';
    $('stageTags').innerHTML = plainTags(r.tags).map(t => `<span>${esc(R.tagLabel(t))}</span>`).join('');
    $('stageWhy').textContent = r.explanation || '';
    for (const c of $('grid').querySelectorAll('.card')) c.classList.toggle('on', c.dataset.id === r.id);
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
    if (play) v.play().catch(() => {});
  }

  // Loading text while a clip renders on first view; an error says so instead of a blank player.
  function wireStageVideo() {
    const v = $('stageVideo'), busy = (on) => { $('stageLoading').hidden = !on; };
    v.addEventListener('loadstart', () => busy(true));
    v.addEventListener('waiting', () => busy(true));
    for (const ev of ['loadeddata', 'canplay', 'playing', 'pause', 'emptied']) v.addEventListener(ev, () => busy(false));
    v.addEventListener('error', () => {
      if (!v.getAttribute('src')) return;
      busy(false);
      $('stageNoVideo').hidden = false;
      $('stageNoVideo').textContent = 'This clip could not be loaded. Try again in a moment.';
    });
  }

  // ------------------------------------------------------------------ reels and exports

  // The reel: the last "make a reel" reply if there was one, else the result set in the order on screen.
  const reelIds = () => (state.reel || sorted(state.results).map(r => r.id)).filter(id => state.all.get(id)?.video_url).slice(0, REEL_MAX);

  function reelLinks() {
    const ids = reelIds();
    const dl = $('downloadReel'), ex = $('exportMoments');
    $('playReel').disabled = !ids.length;
    $('playReel').textContent = ids.length > 1 ? `Play reel (${ids.length})` : 'Play reel';
    dl.setAttribute('aria-disabled', String(!ids.length));
    if (ids.length) dl.href = matchUrl(`/reel.mp4?clips=${ids.map(enc).join(',')}`); else dl.removeAttribute('href');
    const all = state.results.map(r => r.id);
    ex.setAttribute('aria-disabled', String(!all.length));
    if (!all.length) ex.removeAttribute('href');
    else ex.href = state.fromQuestion ? matchUrl(`/moments.csv?clips=${all.map(enc).join(',')}`) : matchUrl(`/moments.csv?player=${enc(state.player)}`);
  }

  const reel = { ids: [], i: 0, on: false };
  function playReel() {
    reel.ids = reelIds(); reel.i = 0; reel.on = reel.ids.length > 0;
    nextInReel();
  }
  function nextInReel() {
    if (!reel.on || reel.i >= reel.ids.length) { reel.on = false; return; }
    state.selected = reel.ids[reel.i++];
    renderStage(true, `Reel · clip ${reel.i} of ${reel.ids.length}`);
  }
  function stopReel() { reel.on = false; }

  // ------------------------------------------------------------------ sort, health, how it works

  function setSort(s) {
    state.sort = s;
    for (const b of document.querySelectorAll('.seg')) b.setAttribute('aria-pressed', String(b.dataset.sort === s));
  }

  async function loadHealth() {
    let h;
    try { h = await R.api('/api/health'); } catch (e) { $('builtOn').textContent = ''; $('services').innerHTML = '<li class="muted">Health is not available right now.</li>'; return; }
    state.health = h;
    engineHint();
    // Only what this deployment says is running.
    const on = [h.cloud.foundry ? `Microsoft Foundry${h.cloud.model ? ` (${h.cloud.model})` : ''}` : null, 'Microsoft Agent Framework',
      h.azure_mcp ? 'Azure MCP Server' : null, h.cloud.cosmos ? 'Azure Cosmos DB' : null, h.cloud.search ? 'Azure AI Search' : null,
      h.tracing ? 'Application Insights' : null].filter(Boolean);
    $('builtOn').textContent = `Built on ${on.join(' · ')}`;
    const services = [
      ['Microsoft Foundry', h.cloud.foundry, `A ${h.cloud.model || 'Foundry'} model labels uploaded matches and writes the Foundry replies.`],
      ['Azure Cosmos DB', h.cloud.cosmos, 'Stores matches, clips, labels and reviewers\' verdicts.'],
      ['Azure AI Search', h.cloud.search, 'Indexes every labelled clip for the Foundry Librarian.'],
      ['Azure MCP Server', h.azure_mcp, 'The Foundry Librarian\'s tool for querying the search index.'],
      ['Application Insights', h.tracing, 'Receives the Agent Framework traces, shown in Foundry tracing.'],
    ];
    $('services').innerHTML = services.map(([name, ok, what]) =>
      `<li><span class="tick ${ok ? 'on' : 'off'}" aria-hidden="true">${ok ? '✓' : '–'}</span><b>${esc(name)}</b>`
      + `<span class="what">${ok ? 'On this server. ' : 'Not configured on this server. '}${esc(what)}</span></li>`).join('');
  }

  function wire() {
    $('askForm').addEventListener('submit', (e) => { e.preventDefault(); send(); });
    for (const r of document.querySelectorAll('input[name="engine"]')) r.addEventListener('change', engineHint);
    $('match').onchange = () => loadMatch($('match').value);
    $('player').onchange = () => { state.player = $('player').value; newConversation(); };
    for (const b of document.querySelectorAll('.seg')) b.onclick = () => { setSort(b.dataset.sort); render($('empty').innerHTML); };
    $('more').onclick = () => send('more');
    $('playReel').onclick = () => { playReel(); $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); };
    $('stageVideo').addEventListener('ended', nextInReel);
    wireStageVideo();
    $('howOpen').onclick = () => { const d = $('how'); d.showModal ? d.showModal() : d.setAttribute('open', ''); };
    $('howClose').onclick = () => { const d = $('how'); d.close ? d.close() : d.removeAttribute('open'); };
    $('how').addEventListener('click', (e) => { if (e.target === $('how')) $('how').close(); });  // a click on the backdrop
  }

  init();
})();
