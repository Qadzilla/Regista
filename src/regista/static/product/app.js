// The Product (/): ask for a moment, watch it, take it away. One result set on screen at a time: the selected player's
// moments until the first question, then whatever the last reply found. Every reply drives the grid, the timeline and
// the stage. Plain script on top of window.Regista (/static/shared/regista.js); the timeline is /static/product/timeline.js.
// No inline scripts, handlers or style attributes: the page runs under a Content Security Policy.
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
    all: new Map(),          // clip id -> clip as GET /clips returns it: every persisted clip, plus the moments of each
                             // player looked at (derived on the fly by the server): the grid's labels, the timeline
    loaded: new Set(),       // players whose moments are in state.all
    results: [], total: 0,   // the current result set (normalised rows) and how many the question matched in all
    fromQuestion: false,     // false: the picked player's moments; true: the last reply's results
    reel: null,              // clip ids of the last "make a reel" reply, if any
    tag: null,               // the tag chip filtering the grid, or null for all
    sort: 'best', selected: null, health: null,
  };
  const chat = { state: null, history: [], busy: false };

  // ------------------------------------------------------------------ small helpers

  const matchUrl = (path = '', id = state.match) => `/api/matches/${enc(id)}${path}`;
  const player = (pid) => state.info?.players.find(p => p.player_id === pid);
  const team = (tid) => state.info?.teams.find(t => t.team_id === tid);
  const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
  const detail = (e) => (e && typeof e.detail === 'string') ? e.detail : (e && e.message) || 'Something went wrong.';
  // fetch() itself failed: the server or the network is down. ApiError means the server answered.
  const offline = (e) => !(e instanceof R.ApiError);
  const OFFLINE = 'Can\'t reach Regista right now. Check your connection and try again.';
  const momentsOf = (pid) => (state.info?.moment_counts || {})[pid] || 0;

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

  // A clip from GET /clips or a result from /chat, as one shape. Chat results carry no label model, so the badge
  // reads it from the match's clips. A Foundry label's explanation was written to justify a score ("Scored 0.56
  // because… xG"); people read its summary instead, which says what happens.
  function row(c) {
    const id = c.id || c.clip_id;
    const full = state.all.get(id);
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

  const sorted = (rows) => [...rows].sort(state.sort === 'time'
    ? (a, b) => a.t - b.t
    : (a, b) => (b.watchability - a.watchability) || (a.t - b.t));

  // The result set as the grid shows it: filtered by the tag chip, in the order picked.
  const visible = () => sorted(state.tag ? state.results.filter(r => r.tags.includes(state.tag)) : state.results);

  // ------------------------------------------------------------------ errors with a way out

  function showNetError(text, retry) {
    const box = $('netError');
    box.hidden = false;
    $('netErrorText').textContent = text;
    $('netRetry').onclick = () => { box.hidden = true; retry(); };
  }
  const hideNetError = () => { $('netError').hidden = true; };

  // ------------------------------------------------------------------ loading

  async function init() {
    wire();
    loadHealth();
    try {
      state.matches = await R.api('/api/matches');
    } catch (e) {
      if (offline(e)) { fatal(''); return showNetError(OFFLINE, init); }
      return fatal(`Regista could not list its matches: ${detail(e)}`);
    }
    hideNetError();
    if (!state.matches.length) return fatal('There are no matches on this server yet.');
    $('match').innerHTML = state.matches.map(m => `<option value="${esc(m.match_id)}">${esc(matchName(m))}</option>`).join('');
    await loadMatch(featured().match_id);
  }

  // The match the page opens on: the one the server marks featured, else the one with video and the most clips.
  function featured() {
    const marked = state.matches.find(m => m.featured);
    if (marked) return marked;
    const withVideo = state.matches.filter(m => m.video);
    return [...(withVideo.length ? withVideo : state.matches)].sort((a, b) => (b.clip_count || 0) - (a.clip_count || 0))[0];
  }

  function fatal(text) {
    $('resultsHead').textContent = 'Moments';
    showEmpty(esc(text));
    $('stage').hidden = true;
  }

  // A switch loads everything first and only then replaces what is on screen: if it fails, the picker goes back to the
  // match still shown, so the page never mixes two matches.
  async function loadMatch(id) {
    const previous = state.info ? state.match : null;
    $('match').disabled = true;
    if (!previous) showEmpty('Loading the match…');
    let info, clips;
    try {
      [info, clips] = await Promise.all([R.api(matchUrl('', id)), R.api(matchUrl('/clips', id))]);
    } catch (e) {
      $('match').disabled = false;
      if (previous) $('match').value = previous;
      if (offline(e)) return showNetError(OFFLINE, () => loadMatch(id));
      if (previous) return showNetError(`That match could not be loaded: ${detail(e)}`, () => loadMatch(id));
      return fatal(`This match could not be loaded: ${detail(e)}`);
    }
    $('match').disabled = false;
    hideNetError();
    state.match = id; state.info = info; $('match').value = id;
    state.all = new Map(clips.map(c => [c.id, { ...c, title: c.label?.title }]));
    state.loaded = new Set(info.players_with_clips || []);
    $('stage').hidden = false;
    const listed = state.matches.find(m => m.match_id === id);
    showMatchLine(listed || info);
    fillPlayers(listed?.clips_for);
    $('fullMatch').href = matchUrl('/video.mp4');
    $('fullMatch').hidden = state.info.source === 'cosmos';
    report.loaded = null; $('report').hidden = true; $('reportToggle').setAttribute('aria-expanded', 'false');
    const cosmosOnly = state.info.source === 'cosmos';
    $('q').disabled = cosmosOnly; $('go').disabled = cosmosOnly;
    await newConversation();
    if (cosmosOnly) $('engineHint').textContent = 'This match is read from Cosmos DB without its event stream, so it cannot answer questions here. Its moments are below.';
  }

  function showMatchLine(m) {
    $('matchTitle').textContent = matchName({ ...m, title: m.title || state.info.title, teams: m.teams || state.info.teams });
    const sub = m.subtitle || state.info.subtitle;
    $('matchSub').textContent = sub || '';
    $('matchSub').hidden = !sub;
    $('visionNote').hidden = state.info.origin !== 'vision';
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
    await newConversation();
  }

  // ------------------------------------------------------------------ the conversation

  // The server keeps nothing between turns: it merges each message into the query so far and returns it, and the page
  // sends it back. It starts from the picked player, so "make a reel of his best moments" knows who "his" is.
  function seed() {
    return { player_ids: state.player ? [state.player] : [], team_id: null, tags: [], reasons: [], minutes: null, limit: null, offset: 0 };
  }

  async function newConversation() {
    chat.state = seed(); chat.history = [];
    $('log').innerHTML = ''; $('log').hidden = true;
    try { await loadPlayerClips(state.player); } catch (e) { /* the grid says so below */ }
    showLanding();
    engineHint();
    showPlayerMoments();
  }

  function showLanding() {
    $('landing').hidden = false;
    renderExamples();
  }

  // The first chip asks for something the player really did, so it never comes back empty: the most telling tag among
  // their moments, in a phrase the Librarian understands.
  const ASKS = [
    ['goal', (w) => `Show me ${w} scoring`, 'Goals'], ['nutmeg', (w) => `Find me ${w} doing a nutmeg`, 'Nutmegs'],
    ['take_on', (w) => `Find me ${w} doing a take-on`, 'Take-ons'], ['assist', (w) => `Find me ${w}'s assists`, 'Assists'],
    ['shot', (w) => `Find me ${w}'s shots`, 'Shots'], ['save', (w) => `Find me ${w}'s saves`, 'Saves'],
    ['header', (w) => `Find me ${w}'s headers`, 'Headers'], ['tackle', (w) => `Find me ${w}'s tackles`, 'Tackles'],
    ['interception', (w) => `Find me ${w}'s interceptions`, 'Interceptions'], ['cross', (w) => `Find me ${w}'s crosses`, 'Crosses'],
    ['dribble', (w) => `Find me ${w} dribbling`, 'Dribbles'], ['carry', (w) => `Find me ${w}'s carries`, 'Carries'],
    ['pass', (w) => `Find me ${w}'s passes`, 'Passes'],
  ];

  // How a chip names a player so the Librarian finds exactly them. It reads the first name part it knows, in roster
  // order: a surname no one else has is enough, else the full name when its first name leads to them, else the name
  // with team and kit number ("Ivan Brennan, Southgate's number 1").
  function chipName(p) {
    const parts = new Map();
    for (const o of state.info.players) for (const w of o.name.toLowerCase().split(' ')) { if (!parts.has(w)) parts.set(w, []); parts.get(w).push(o); }
    const words = p.name.toLowerCase().split(' ');
    const last = words[words.length - 1];
    if (parts.get(last).length === 1) return { who: p.name.split(' ').slice(-1)[0], plain: true };
    if (parts.get(words[0])[0] === p) return { who: p.name, plain: true };
    const name = p.name, side = (team(p.team_id)?.name || '').split(' ')[0];  // plain text: esc() is applied where it is shown
    return { who: `${name}, ${side}'s number ${p.kit_number}`, plain: false };
  }

  function renderExamples() {
    // A player with no moments gets chips about the player who has the most, so every chip answers.
    let p = player(state.player);
    if (p && !momentsOf(p.player_id)) p = player(Object.entries(state.info.moment_counts || {}).sort((a, b) => b[1] - a[1])[0]?.[0]) || p;
    const asks = [];
    if (p) {
      const { who, plain } = chipName(p);
      const tags = new Set([...state.all.values()].filter(c => c.player_id === p.player_id).flatMap(c => c.label?.tags || []));
      const first = ASKS.find(([tag]) => tags.has(tag));
      if (first) asks.push(plain ? first[1](who) : `${first[2]} by ${who}`);
      if (momentsOf(p.player_id)) asks.push(`Every touch by ${who}, in match order`,
        plain ? `Make a reel of ${who}'s best moments` : `The best moments of ${who}, as a reel`);
    }
    $('examples').innerHTML = asks.map(a => `<button type="button" class="example">${esc(a)}</button>`).join('');
    const off = state.info?.source === 'cosmos';
    for (const b of $('examples').querySelectorAll('button')) { b.disabled = off; b.onclick = () => { $('q').value = b.textContent; send(); }; }
  }

  const engine = () => document.querySelector('input[name="engine"]:checked').value;

  function engineHint() {
    if (state.info?.source === 'cosmos') return;
    const h = state.health;
    $('engineHint').textContent = engine() === 'rules'
      ? 'Instant: Regista\'s own rules find the moments and write the reply, with no AI model. Follow-ups build on what you asked; "start over" clears it.'
      : (h && !h.cloud.foundry
        ? 'Foundry is not set up on this server, so Regista\'s rules will write the reply. The moments found are the same.'
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

  async function send(message = $('q').value.trim(), { quiet = false, withState = null } = {}) {
    if (!message || chat.busy || !state.match) return null;
    chat.busy = true; $('go').disabled = true; $('q').value = '';
    $('landing').hidden = true;
    addMsg('me', esc(message));
    const eng = engine();
    const wait = addMsg('bot wait', eng === 'foundry' ? 'Searching, then asking Microsoft Foundry to write the reply…' : 'Searching…');
    let out = null;
    const prevOrder = (withState || chat.state)?.order;
    try {
      out = await R.api(matchUrl('/chat'), { method: 'POST', body: { message, state: withState || chat.state, history: chat.history, engine: eng } });
      wait.remove();
      chat.state = out.state; chat.history = out.history;
      remember(out.results);
      const msg = addMsg('bot', `${esc(out.reply)}${fallbackLine(out, eng)}${howAnswered(out, eng)}`);
      // The server keeps the order asked for in state.order ("time" after "in match order"); older servers did not.
      if (out.state?.order === 'time' || (out.state?.order === undefined && /match order|in order|chronolog/i.test(message))) setSort('time');
      else if ((prevOrder === 'time' && out.state?.order === null) || /\bbest\b|\btop\b/i.test(message)) setSort('best');
      applyReply(out, message);
      offerWayOut(msg, out);
      if (state.sort === 'time' && out.intent === 'search') await fillMatchOrder();
    } catch (e) {
      wait.remove();
      const text = offline(e) ? OFFLINE : e.status === 429 ? detail(e)
        : e.status === 404 ? 'This match is not on this server any more. Pick another match.' : `Regista could not answer: ${detail(e)}`;
      const err = addMsg('bot err', esc(text));
      if (offline(e) || e.status >= 500) {
        const b = Object.assign(document.createElement('button'), { type: 'button', className: 'alt retry', textContent: 'Retry' });
        b.onclick = () => { err.remove(); send(message); };
        err.appendChild(b);
        $('log').scrollTop = $('log').scrollHeight;
      }
    } finally {
      chat.busy = false; $('go').disabled = state.info?.source === 'cosmos';
      if (!quiet) $('q').focus();
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

  // "How Regista answered": the steps in plain words, then the exact step names and times on a smaller details line.
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
        + `${s.server ? `<span class="server">${esc(SERVERS[s.server] || s.server)}</span>` : ''}<span class="ms">${esc(ms(s.ms))}</span></li>`).join('')}</ol>`;
    } else if ((out.tools_used || []).length) {
      details = `<div class="tags">${out.tools_used.map(t => `<span class="tool">${esc(t)}</span>`).join(' ')}</div>`;
    }
    const who = instant ? 'Regista\'s own rules, with no AI model' : `Microsoft Foundry (${esc(by.replace(/^foundry:/, ''))})`;
    return `<details class="how"><summary>How Regista answered</summary>`
      + (plain.length ? `<ol class="plain">${plain.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` : '')
      + `<p class="by">Answered by ${who}${eng === 'foundry' && instant ? ' (Foundry was asked for)' : ''}.</p>`
      + (details ? `<details class="tech"><summary>Details: step names and times</summary>${details}`
        + `<p class="engine-raw">Engine ${esc(eng)} · answered by ${esc(by)}</p></details>` : '')
      + `</details>`;
  }

  // Plain text: each line goes through esc() where it is shown.
  function plainSteps(out, trace) {
    const ids = out.state?.player_ids || [];
    const of = ids.length === 1 && momentsOf(ids[0]) ? ` of ${momentsOf(ids[0])}` : '';
    const lastModel = trace.map(x => x.kind).lastIndexOf('model');
    let searches = 0;
    const steps = trace.map((step, i) => {
      if (step.kind === 'step') {
        if (step.name === 'librarian.load_match') return 'Read the match';
        if (step.name === 'conversation.step') return out.understood ? `Understood: ${String(out.understood).replace(/ · /g, ', ')}` : 'Read the question';
        if (step.name === 'librarian.search_clips') {
          searches += 1;
          if (searches > 1) return 'Checked what else the same player has';
          return out.intent === 'reset' ? 'Cleared the question' : `Found ${out.total ?? (out.results || []).length}${of} moments`;
        }
        return 'Worked on the question';
      }
      if (step.kind === 'agent') return 'Handed the question to the Foundry Librarian agent';
      if (step.kind === 'model') return i === lastModel ? `Microsoft Foundry (${step.name}) wrote the reply` : `Microsoft Foundry (${step.name}) chose what to look up`;
      if (step.kind === 'tool') return toolStep(step);
      return 'Another step';
    });
    if (!trace.length) for (const t of out.tools_used || []) steps.push(toolStep({ name: t, server: /^search_index_|^cosmos_/.test(t) ? 'azure-mcp' : 'regista-mcp' }));
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
    const rows = (out.results || []).map(row);
    state.fromQuestion = true; state.tag = null;
    state.reel = out.reel && out.reel.length ? out.reel.map(c => c.clip_id) : null;
    // "more" pages through the same question: the new page joins the set already on screen.
    state.results = out.intent === 'more' ? [...state.results, ...rows.filter(r => !state.results.some(x => x.id === r.id))] : rows;
    state.total = out.total ?? rows.length;
    state.selected = null;
    const ids = out.state?.player_ids || [];
    if (ids.length === 1 && ids[0] !== state.player && player(ids[0])) {
      state.player = ids[0]; $('player').value = ids[0];
      loadPlayerClips(ids[0]).then(() => { renderTimeline(); }).catch(() => {});
    }
    $('resultsHead').innerHTML = `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(out.understood || '')}</span>`;
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
      const fresh = (out.results || []).map(row).filter(r => !state.results.some(x => x.id === r.id));
      if (!fresh.length) break;
      st = out.state;
      state.results = [...state.results, ...fresh];
    }
    chat.state = st;
    render('');
  }

  // "Start over" from the ask box: the log stays (it is the record of the conversation), the query and results reset,
  // and the example questions come back.
  function restartQuery() {
    chat.state = seed(); chat.history = [];
    showLanding();
    showPlayerMoments();
  }

  // ------------------------------------------------------------------ the result set: grid, timeline, stage

  function showPlayerMoments() {
    const p = player(state.player);
    state.fromQuestion = false; state.reel = null; state.selected = null; state.tag = null;
    state.results = [...state.all.values()].filter(c => c.player_id === state.player).map(row);
    state.total = state.results.length;
    $('resultsHead').innerHTML = p
      ? `${esc(plural(state.total, 'moment'))} <span class="muted">· ${esc(p.name)}, ${esc(team(p.team_id)?.name || '')}</span>`
      : 'Moments';
    render(p ? `${esc(p.name)} never had the ball in the main camera and is in no replay or highlight, so Regista cut no moments for this player. Pick someone from "Players with moments".`
      : 'Pick a player.');
  }

  // After a failed player switch: the moments of the player still picked.
  function showMatchMoments() { if (state.info) showPlayerMoments(); }

  function showEmpty(html) { $('empty').hidden = !html; $('empty').innerHTML = html || ''; }

  function render(emptyHtml) {
    const rows = visible();
    showEmpty(rows.length ? '' : emptyHtml);
    const shown = state.fromQuestion ? state.results.length : state.total;
    $('more').hidden = !(state.fromQuestion && state.total > shown);
    $('more').textContent = `Show more (${state.total - shown} more)`;
    renderTagBar();
    const vision = state.info?.origin === 'vision';
    $('grid').innerHTML = rows.map(r => `
      <button type="button" class="card" data-id="${esc(r.id)}" aria-label="Play ${esc(r.title)}">
        ${r.video_url ? `<span class="thumb"><video muted playsinline preload="none" src="${esc(r.video_url)}"></video><span class="prep">Preparing…</span></span>`
          : `<span class="novideo">Read from Cosmos DB. The labels and timings are stored there; this server does not hold the match's video.</span>`}
        <span class="body">
          <span class="reason ${r.reason === 'replay_appearance' ? 'replay' : ''}">${esc(R.reasonLabel(r.reason))} · ${esc(R.fmtTime(r.t))}</span>
          <span class="title">${esc(r.title)}</span>
          <span class="bar" title="How worth watching, from 0 to 1: ${esc(Number(r.watchability).toFixed(2))}"><i data-w="${esc(Math.round(r.watchability * 100))}"></i></span>
          <span class="tags">${plainTags(r.tags).map(t => `<span>${esc(R.tagLabel(t))}</span>`).join('')}</span>
          ${badges(r, vision)}
        </span>
      </button>`).join('');
    for (const i of $('grid').querySelectorAll('.bar i')) i.style.width = `${Number(i.dataset.w) || 0}%`;
    for (const card of $('grid').querySelectorAll('.card')) card.onclick = () => select(card.dataset.id, true);
    for (const v of $('grid').querySelectorAll('.thumb video')) {
      const prep = v.nextElementSibling;
      v.addEventListener('loadeddata', () => { prep.hidden = true; });
      v.addEventListener('error', () => { prep.textContent = 'Could not load the preview'; });
    }
    lazyPreview($('grid'));
    renderTimeline();
    renderStage();
  }

  // Tag chips over the grid: one per football tag in the result set, with its count, as a filter.
  function renderTagBar() {
    const counts = new Map();
    for (const r of state.results) for (const t of new Set(plainTags(r.tags))) counts.set(t, (counts.get(t) || 0) + 1);
    if (state.tag && !counts.has(state.tag)) state.tag = null;
    const bar = $('tagbar');
    if (counts.size < 1 || state.results.length < 2) { bar.hidden = true; bar.innerHTML = ''; return; }
    const chips = [[null, 'All', state.results.length], ...[...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t, n]) => [t, R.tagLabel(t), n])];
    bar.hidden = false;
    bar.innerHTML = chips.map(([t, name, n]) => `<button type="button" class="chip" data-tag="${esc(t || '')}" aria-pressed="${String(state.tag === t)}">`
      + `${esc(name)} <span class="n">${esc(n)}</span></button>`).join('');
    for (const b of bar.querySelectorAll('.chip')) b.onclick = () => {
      state.tag = b.dataset.tag || null; state.selected = null;
      render($('empty').innerHTML);
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

  function select(id, play) {
    state.selected = id;
    stopReel();
    renderStage(play);
    for (const c of $('grid').querySelectorAll('.card')) c.classList.toggle('on', c.dataset.id === id);
    if (play) $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function current() {
    const rows = visible();
    return rows.find(r => r.id === state.selected) || (state.selected && state.all.has(state.selected) ? row(state.all.get(state.selected)) : rows[0]);
  }

  function renderStage(play = false, prefix = '') {
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
    $('askForm').addEventListener('submit', (e) => { e.preventDefault(); send(); });
    for (const r of document.querySelectorAll('input[name="engine"]')) r.addEventListener('change', engineHint);
    $('match').onchange = () => loadMatch($('match').value);
    $('player').onchange = () => pickPlayer($('player').value);
    for (const b of document.querySelectorAll('.seg')) b.onclick = () => { setSort(b.dataset.sort); render($('empty').innerHTML); };
    $('more').onclick = () => send('more');
    $('playReel').onclick = () => { playReel(); $('stage').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); };
    $('stageVideo').addEventListener('ended', nextInReel);
    $('downloadReel').addEventListener('click', downloadReel);
    wireStageVideo();
    $('reportToggle').onclick = toggleReport;
    $('howOpen').onclick = () => { const d = $('how'); d.showModal ? d.showModal() : d.setAttribute('open', ''); };
    $('howClose').onclick = () => { const d = $('how'); d.close ? d.close() : d.removeAttribute('open'); };
    $('how').addEventListener('click', (e) => { if (e.target === $('how')) $('how').close(); });  // a click on the backdrop
    $('how').addEventListener('close', () => $('howOpen').focus());  // Escape, Close or the backdrop: back to the button
  }

  init();
})();
