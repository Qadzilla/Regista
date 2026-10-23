// Switches between the three empty views by the URL hash (#home, #profile, #scout) and marks the current one in the nav.
(function () {
  const views = ['home', 'profile', 'scout'];
  function show() {
    const h = location.hash.slice(1);
    const v = views.includes(h) ? h : 'home';
    for (const s of document.querySelectorAll('main section[data-view]')) s.hidden = s.dataset.view !== v || h === 'search';
    document.getElementById('results').hidden = h !== 'search';
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
  function card(m) {
    const tags = (m.tags || []).filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
    const badge = String(m.model || '').startsWith('foundry:') ? '<span class="badges"><span class="badge">Labelled by Microsoft Foundry</span></span>' : '';
    return `<button type="button" class="card" aria-label="Play ${esc(m.title)}">
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
  function foundryAnswer(q, key, set) {
    const [what, understood] = WHAT[key], best = set.moments[0];
    return `<div class="fq-user">${esc(q)}</div>
      <div class="fa">I found ${set.total} ${esc(what)} across the season's 30 matches. The best is ${esc(best.title.split(': ').pop())}
        by ${esc(best.player)}, round ${best.round}, ${esc(best.home)} v ${esc(best.away)}. They're in the grid, best first.
        <div class="understood">Understood: ${esc(understood)}</div></div>
      <div class="trace"><b>How Regista answered</b><ol>
        <li>Microsoft Foundry agent (gpt-5-mini) read the question</li>
        <li>search_clips · Regista's MCP server</li>
        <li>search_index_query · Azure MCP Server → Azure AI Search</li>
        <li>Wrote the answer from what the tools returned</li></ol></div>`;
  }
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
    if (f) document.getElementById('fthread').innerHTML = foundryAnswer(q, key, set);
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
  document.getElementById('ffollow').addEventListener('submit', (e) => {
    e.preventDefault();
    const fq = document.getElementById('fq'), t = fq.value.trim();
    if (!t) return;
    document.getElementById('fthread').insertAdjacentHTML('beforeend', `<div class="fq-user">${esc(t)}</div><div class="fa understood">In the app, Microsoft Foundry answers follow-ups and narrows the grid.</div>`);
    fq.value = '';
  });
  window.addEventListener('hashchange', show);
  show();
})();
