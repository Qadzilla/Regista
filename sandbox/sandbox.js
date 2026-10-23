// Switches between the three empty views by the URL hash (#home, #profile, #scout) and marks the current one in the nav.
(function () {
  const views = ['home', 'profile', 'scout'];
  function show() {
    const h = location.hash.slice(1).split('/')[0];  // #profile/messages: the profile view, its Messages section
    const v = views.includes(h) ? h : 'home';
    for (const s of document.querySelectorAll('main section[data-view]')) s.hidden = s.dataset.view !== v || h === 'search' || h === 'match';
    document.getElementById('results').hidden = h !== 'search';
    document.getElementById('matchview').hidden = h !== 'match';
    for (const a of document.querySelectorAll('.side a')) {
      if (a.dataset.view === v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    }
  }
  // Example prompts type themselves into the empty search box and back out, one after another. They pause while the
  // box has focus or text in it, and stay still for people who prefer less motion. Tab fills in the prompt on show.
  const prompts = [
    'Find me shots from outside the box this season',
    'Show me every header this season',
    'Find me all the nutmegs',
    'Show me take-ons in the final third',
    'Find me every assist, best first',
    "Show me Femi Toure's goals, assists and shots",
  ];
  const q = document.getElementById('q');
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let p = 0, n = 0, typing = true, shown = '';
  function tick() {
    if (still) { q.placeholder = prompts[0]; return; }
    if (document.activeElement === q || q.value) { setTimeout(tick, 400); return; }
    const text = prompts[p];
    if (typing) {
      n++; shown = text.slice(0, n); q.placeholder = shown + '|';
      if (n >= text.length) { typing = false; q.placeholder = shown; return setTimeout(tick, 1800); }
      return setTimeout(tick, 45 + Math.random() * 40);
    }
    n--; shown = text.slice(0, n); q.placeholder = shown + '|';
    if (n <= 0) { typing = true; p = (p + 1) % prompts.length; return setTimeout(tick, 400); }
    setTimeout(tick, 22);
  }
  q.addEventListener('keydown', (e) => { if (e.key === 'Tab' && !q.value && shown) { e.preventDefault(); q.value = prompts[p]; } });
  q.addEventListener('blur', () => { if (!q.value) q.placeholder = shown; });
  tick();
  // ---- results. The sandbox has no backend: results.json holds real result sets from the Regista League for the six
  // prompts, and a typed search is matched to the nearest of them by its words.
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // The card, exactly as the app draws it (src/regista/static/product/app.js render()): the same labels, tags it hides,
  // time format and badge. The sandbox has no video, so the preview frame stays empty.
  const INTERNAL = /_appearance$|_against$|^(on_ball_main|touch|possession_change|kick_off|period_start|period_end)$/;
  const REASONS = { on_ball_main: 'On the ball', replay_appearance: 'Replay', highlight_appearance: 'Highlight', closeup_appearance: 'Closeup' };
  const TAGS = { take_on: 'Take-on', kick_off: 'Kick-off', skill_move: 'Skill move', ball_won: 'Ball won', key_pass: 'Key pass' };
  const words = (t) => { const s = String(t ?? '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
  const tagLabel = (t) => TAGS[t] || words(t);
  const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const WHAT = {    'Find me shots from outside the box this season': ['shots from outside the box', 'shots from more than 18 metres out, on the ball'],
    'Show me every header this season': ['headers', 'shots with the head'],
    'Find me all the nutmegs': ['nutmegs', 'every nutmeg, with its replays and highlights'],
    'Show me take-ons in the final third': ['take-ons won in the final third', 'successful take-ons near either goal'],
    'Find me every assist, best first': ['assists', 'passes that led to a goal, best first'],
    "Show me Femi Toure's goals, assists and shots": ["Femi Toure's goals, assists and shots", 'Femi Toure (Brookfield Rovers, number 9), on the ball'],
  };
  const KEYS = [['outside', 0], ['distance', 0], ['header', 1], ['head', 1], ['nutmeg', 2], ['take-on', 3], ['take on', 3], ['dribbl', 3], ['assist', 4], ['toure', 5]];
  let data = null;
  fetch('results.json').then(r => r.json()).then(d => { data = d; });
  function pick(text) {
    const t = text.toLowerCase(), names = Object.keys(WHAT);
    const exact = names.find(n => n.toLowerCase() === t);
    if (exact) return exact;
    const k = KEYS.find(([w]) => t.includes(w));
    return names[k ? k[1] : 2];
  }
  function card(m, mid, on) {
    const tags = (m.tags || []).filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
    const badge = String(m.model || '').startsWith('foundry:') ? '<span class="badges"><span class="badge">Labelled by Microsoft Foundry</span></span>' : '';
    return `<button type="button" class="card${on ? ' on' : ''}" data-mid="${esc(mid || m.match_id)}" data-cid="${esc(m.clip_id)}" aria-label="Play ${esc(m.title)}">
        <span class="thumb"><span class="prep"></span></span>
        <span class="body">
          <span class="reason ${m.kind === 'replay_appearance' ? 'replay' : ''}">${esc(REASONS[m.kind] || words(m.kind))} · ${esc(fmtTime(m.t || 0))}</span>
          <span class="title">${esc(m.title)}</span>
          <span class="bar"><i style="width:${Math.round((m.watch || 0) * 100)}%"></i></span>
          <span class="tags">${tags}</span>
          ${badge}
        </span>
      </button>`;
  }
  // ---- the conversation: every question and its answer, shown only in the right panel. "How Regista answered" is one
  // line per answer; its steps and their timings open on demand.
  const turns = [];
  let matches = null;
  fetch('matches.json').then(r => r.json()).then(d => { matches = d; });
  function addTurn(q, engine, key, set) {
    const [what, understood] = WHAT[key], best = set.moments[0];
    const where = `${best.title.split(': ').pop()} by ${best.player}, round ${best.round}, ${best.home} v ${best.away}`;
    if (engine === 'foundry') {
      turns.push({ q, engine, answer: `I found ${set.total} ${what} across the season's 30 matches. The best is ${where}. They're in the grid, best first.`,
        how: ['Read the season', `Understood: ${understood}`, `Found ${set.total} moments`, 'Handed the question to the Foundry Librarian agent', 'Microsoft Foundry (gpt-5-mini) wrote the reply'],
        times: [['step', 'librarian.load_season', '12 ms'], ['step', 'conversation.step', '3 ms'], ['tool', 'search_clips · Regista MCP server', '41 ms'], ['tool', 'search_index_query · Azure MCP Server', '0.9 s'], ['model', 'gpt-5-mini', '5.8 s']],
        by: 'Answered by Microsoft Foundry (gpt-5-mini)' });
    } else {
      turns.push({ q, engine, answer: `${set.total} moments: ${what}. Best: ${where}.`,
        how: ['Read the season', `Understood: ${understood}`, `Found ${set.total} moments`],
        times: [['step', 'librarian.load_season', '12 ms'], ['step', 'conversation.step', '<1 ms'], ['step', 'librarian.search_clips', '2 ms']],
        by: "Answered by Data Search: Regista's own data, no AI model" });
    }
  }
  function convoHtml() {
    const items = turns.map(t => `<div class="turn"><div class="fq-user">${esc(t.q)}</div><div class="fa">${esc(t.answer)}</div>
      <details class="how"><summary>${esc(t.by)} · ${t.how.length} steps</summary><ol>${t.how.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
        <details class="how"><summary>Step names and times</summary><div class="times">${t.times.map(([k, n, ms]) => `${esc(k)} · ${esc(n)} · ${esc(ms)}`).join('<br>')}</div></details>
      </details></div>`).join('');
    return `<div class="fhead"><span class="fdot"></span>Conversation</div><div class="fthread">${items || '<p class="how">Ask for a moment to start.</p>'}</div>
      <form class="ffollow"><label class="sr">Ask a follow-up</label><input type="text" autocomplete="off" placeholder="Ask a follow-up"></form>`;
  }
  function paintConvo(el) {
    el.innerHTML = convoHtml();
    const th = el.querySelector('.fthread'); th.scrollTop = th.scrollHeight;
    el.querySelector('.ffollow').addEventListener('submit', (e) => {
      e.preventDefault();
      const inp = e.target.querySelector('input'), t = inp.value.trim();
      if (!t) return;
      turns.push({ q: t, engine: 'rules', answer: 'In the app, a follow-up narrows the search ("now the replays", "second half").', how: ['Follow-up'], times: [['step', 'conversation.step', '<1 ms']], by: 'Sandbox' });
      paintConvo(el);
    });
  }
  // ---- the match view: the clicked clip on the stage.
  let cur = null;
  function openMatch(mid, cid) {
    if (!matches || !matches[mid]) return;
    const pid = cid.replace(/^cl_/, '').replace(/_\d+$/, '');
    cur = { mid, pid, cid };
    if (location.hash !== '#match') location.hash = 'match';
    window.scrollTo(0, 0);
    paintMatch();
  }
  function paintMatch() {
    const M = matches[cur.mid], P = M.players[cur.pid], c = P.moments.find(m => m.clip_id === cur.cid) || P.moments[0];
    document.getElementById('mtitle').textContent = M.title;
    const halves = M.periods.slice(1).map(p => `<span class="half" style="left:${(p.t / M.duration * 100).toFixed(2)}%"></span>`).join('');
    document.getElementById('tline').innerHTML = halves + P.moments.map(m => `<button type="button" class="mk k-${esc(m.kind)}${m.clip_id === c.clip_id ? ' on' : ''}" data-cid="${esc(m.clip_id)}" style="left:${(m.t / M.duration * 100).toFixed(2)}%" title="${esc(m.title)}" aria-label="${esc(m.title)}"></button>`).join('');
    document.getElementById('sreason').className = 'reason' + (c.kind === 'replay_appearance' ? ' replay' : '');
    document.getElementById('sreason').textContent = `${REASONS[c.kind] || words(c.kind)} · ${fmtTime(c.t)}–${fmtTime(c.t_end)}`;
    document.getElementById('stitle').textContent = c.title;
    document.getElementById('stags').innerHTML = c.tags.filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
    document.getElementById('sexpl').textContent = c.explanation;
    document.getElementById('playreel').textContent = `Play reel (${P.moments.length})`;
    document.getElementById('rhead').textContent = P.recap.headline;
    document.getElementById('rparas').innerHTML = P.recap.paragraphs.map(x => `<p>${x.clip ? `<a data-cid="${esc(x.clip)}">${esc(x.text)}</a>` : esc(x.text)}</p>`).join('');
    document.getElementById('mcount').innerHTML = `${P.moments.length} moments <span class="muted">· ${esc(P.name)} in this match</span>`;
    document.getElementById('mgrid').innerHTML = P.moments.map(m => card(m, cur.mid, m.clip_id === c.clip_id)).join('');
    paintConvo(document.getElementById('convo'));
  }
  document.getElementById('matchview').addEventListener('click', (e) => {
    const t = e.target.closest('[data-cid]');
    if (!t || !cur) return;
    e.preventDefault();
    cur.cid = t.dataset.cid; paintMatch();
    if (t.closest('#mgrid') || t.closest('#rparas')) window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  document.getElementById('rgrid').addEventListener('click', (e) => {
    const t = e.target.closest('.card'); if (t) openMatch(t.dataset.mid, t.dataset.cid);
  });
  function search(q, engine) {
    if (!q || !data) return;
    const key = pick(q), set = data[key];
    document.getElementById('rq').value = q;
    document.querySelector(`input[name=rengine][value=${engine}]`).checked = true;
    document.getElementById('rcount').innerHTML = `${set.total} moments` + (set.total > set.moments.length ? ` <span class="muted">· the best ${set.moments.length}</span>` : '');
    document.getElementById('rgrid').innerHTML = set.moments.map(card).join('');
    const f = engine === 'foundry';
    document.getElementById('foundry').hidden = !f;
    document.querySelector('.rbody').classList.toggle('with-foundry', f);
    addTurn(q, engine, key, set);
    if (f) paintConvo(document.getElementById('foundry'));
    if (location.hash !== '#search') location.hash = 'search';
    window.scrollTo(0, 0);
  }
  const engineOf = (name) => document.querySelector(`input[name=${name}]:checked`).value;
  document.querySelector('#home .search').addEventListener('submit', (e) => {
    e.preventDefault();
    search(q.value.trim() || shown.replace(/\|$/, '') || prompts[p], engineOf('engine'));
  });
  document.getElementById('rsearch').addEventListener('submit', (e) => { e.preventDefault(); search(document.getElementById('rq').value.trim(), engineOf('rengine')); });
  for (const r of document.querySelectorAll('input[name=rengine]')) r.addEventListener('change', () => search(document.getElementById('rq').value.trim(), r.value));

  window.addEventListener('hashchange', show);
  show();
})();
