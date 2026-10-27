// The guided tour: one small card on each page it visits, "Step N of M", one or two plain sentences, Back, Next, Exit.
// It follows the demo video's beats (docs/demo-storyboard.md) on what the live app shows, and it only reads: no step
// clicks, asks or writes anything for the visitor. A step may suggest a click ("Press Goal reel") and may put words in a
// search box (never sending them), so a Microsoft Foundry question is only ever asked by the visitor pressing Ask.
//
// Each step names a URL (the tour goes there when the visitor presses Next or Back) and may name one element to
// highlight, by id ("#uploads") or by a data-tour attribute ('[data-tour="goal-reel"]'), never by a page's layout.
// Where the tour is lives in Regista.store (this browser only, key "tour"), so it resumes after a page load; Exit
// forgets it. A visitor who follows a suggested link onto the next step's page moves the tour on; anywhere else the
// card says the tour is paused and offers the way back.
//
// Started by any element with data-tour-start (Home and /demo). Loaded with defer after the page's own scripts, on
// every page the tour visits. No inline scripts, handlers or style attributes: the pages run under a CSP.
(function () {
  const R = window.Regista;
  if (!R || typeof document === 'undefined') return;
  const esc = R.esc;
  const KEY = 'tour';
  const WAIT_MS = 20000;   // how long a step waits for its element (pages build parts of themselves after loading)

  // The steps. Plain data between the markers: tests/test_tour.py reads it as JSON and checks every URL is a route and
  // every target is in its page's HTML or made by its scripts.
  /* STEPS:BEGIN */
  const STEPS = [
    { "id": "hook", "url": "/players/pl_bro_09", "target": "[data-tour=\"goal-reel\"]",
      "title": "Every goal, found",
      "text": "Femi Toure is the Regista League's top scorer: five league goals, none a penalty. Regista found every one in the footage.",
      "act": "Press Goal reel: each goal once, in match order." },
    { "id": "moments", "url": "/?match=syn_0294&player=t_home_09", "target": "#timelineWrap",
      "title": "Every moment of a match",
      "text": "Regista watched this match and cut every moment Sami Castellanos is on the ball, plus every replay, highlight and close-up he appears in. Each mark on the timeline is one.",
      "act": "Click any mark to play it." },
    { "id": "ask", "url": "/?match=syn_0294&player=t_home_09", "target": "#askForm", "fill": { "id": "fq", "value": "his nutmegs" },
      "title": "Then you just ask",
      "text": "Ask in plain words. Data Search answers with Regista's own rules, so no AI model is called.",
      "act": "Press Ask to find his nutmegs." },
    { "id": "follow-up", "url": "/?match=syn_0294&player=t_home_09", "target": "#askForm", "fill": { "id": "fq", "value": "now the replays" },
      "title": "Follow-ups keep the thread",
      "text": "Regista remembers the question so far, so a follow-up narrows it: now only the replays of those nutmegs.",
      "act": "Press Ask." },
    { "id": "recap", "url": "/?match=syn_0294&player=t_home_09", "target": "#recap",
      "title": "Explained and recapped",
      "text": "Every match gets a recap, told from the picked player's side. Each sentence is a link that plays the moment it describes.",
      "act": "Open Match recap, click a sentence, then try Play recap reel." },
    { "id": "video-in", "url": "/me?player=pl_bro_09#matches", "target": "[data-tour=\"agent-steps\"]",
      "title": "Video in",
      "text": "Femi's footage of a friendly went through Azure Blob Storage and a queue to a Container Apps job, where Regista's vision agents ran in turn, each with its time.",
      "act": "Measured on Regista's own rendered footage." },
    { "id": "foundry", "url": "/?match=syn_0294&player=t_home_09", "target": "#askForm", "fill": { "id": "fq", "value": "every nutmeg in the library" },
      "title": "Microsoft Foundry and MCP",
      "text": "Switch to Ask Microsoft Foundry: a Foundry agent (gpt-5-mini, on Microsoft Agent Framework) answers and may call tools. Under its reply, How Regista answered shows each step, and which server ran each tool: Regista's MCP server or the Azure MCP Server.",
      "act": "Pick Ask Microsoft Foundry, then press Ask. Foundry questions are limited to a few a minute per visitor." },
    { "id": "catalogue", "url": "/scout#competitions", "target": "#coLine",
      "title": "A catalogue of uploaded footage",
      "text": "Regista is also a catalogue of matches uploaded by players and teams below the professional level: 14 competitions in 10 countries. Every player, club and competition is invented; countries and levels are labels.",
      "act": "Next opens one competition." },
    { "id": "competition", "url": "/scout#competition/co_esp_u19", "target": "[data-tour=\"co-uploads\"]",
      "title": "Checked in Microsoft Fabric",
      "text": "Each upload says who filmed it and the camera they named. On 26 October 2026 a Microsoft Fabric notebook recomputed every catalogue number from the raw tables: 7,399 of 7,399 rows matched. Fabric runs in its own workspace, not in this app.",
      "act": "Watch in the Clip view opens a match's moments; the tour waits." },
    { "id": "fans", "url": "/?match=syn_0294&player=t_home_09", "target": "[data-tour=\"stage-actions\"]",
      "title": "Fans, creators, broadcasters",
      "text": "Fans and creators take moments away: Download reel joins them into one video, Export moments lists them with timecodes. Broadcasters get the recap and its reel as a replay package.",
      "act": "Try Download reel." },
    { "id": "scout", "url": "/scout#find", "target": "#scExamples",
      "title": "Scouts: fair comparisons",
      "text": "Scouts ask in plain words. Players are compared only with players of their own level, age group and gender, and every percentile names its pool.",
      "act": "Press \"Who are the best U19 dribblers up front?\", then open Hector Santos." },
    { "id": "number", "url": "/players/pl_pnr_11", "target": "[data-tour=\"stat-take_ons_won\"]",
      "title": "Every number opens its moments",
      "text": "Hector Santos is an invented U19 forward in Spain. Each number on his profile opens the moments it was counted from.",
      "act": "Press Take-ons won, then pick a moment to play it." },
    { "id": "terminal", "url": "/scout#terminal", "target": "#txForm", "fill": { "id": "txIn", "value": "most goals in England" },
      "title": "The Scout terminal",
      "text": "127 metrics, each with its definition and source, in linked panels, with a search box that reads plain questions.",
      "act": "Press Search: Femi Toure comes first." },
    { "id": "players", "url": "/me?player=pl_bro_09#matches", "target": "#addBtn",
      "title": "Players build their profile",
      "text": "A player uploads their own match here, answers \"Is this you?\" where Regista is unsure, and the match joins their profile. Uploading starts cloud work, so on this demo it needs the operator's key.",
      "act": "" },
    { "id": "close", "url": "/demo", "target": "#closeLinks",
      "title": "That's Regista",
      "text": "Every touch, every replay, every player, found. Next: real footage from players and teams. The code, the tests and how each judging criterion is met are in the repository.",
      "act": "" }
  ];
  /* STEPS:END */

  // ------------------------------------------------------------------ where the visitor is
  const parse = (url) => {
    const u = new URL(url, location.origin);
    return { path: u.pathname.replace(/\/+$/, '') || '/', params: [...u.searchParams.entries()], hash: decodeURIComponent(u.hash.replace(/^#/, '')) };
  };
  const herePath = () => location.pathname.replace(/\/+$/, '') || '/';
  // Same page: the path and every query value the step names (pages add their own, such as clip=).
  function samePage(step) {
    const s = parse(step.url);
    if (s.path !== herePath()) return false;
    const q = new URLSearchParams(location.search);
    return s.params.every(([k, v]) => q.get(k) === v);
  }
  function isHere(step) {
    if (!samePage(step)) return false;
    const want = parse(step.url).hash;
    return !want || decodeURIComponent(location.hash.replace(/^#/, '')) === want;
  }

  const load = () => {
    const s = R.store.get(KEY, null);
    return s && Number.isInteger(s.i) && s.i >= 0 && s.i < STEPS.length ? s : null;
  };
  const save = (s) => R.store.set(KEY, s);

  // ------------------------------------------------------------------ the card
  let card = null, lit = null, waitTimer = null, filled = null;
  function ensureCard() {
    if (card) return card;
    card = document.createElement('aside');
    card.className = 'tour';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', 'Guided tour');
    card.addEventListener('click', onCardClick);
    document.body.appendChild(card);
    return card;
  }
  function unlight() {
    if (lit) lit.classList.remove('tour-on');
    lit = null;
    clearTimeout(waitTimer);
  }
  function remove() {
    unlight();
    if (card) card.remove();
    card = null;
    document.documentElement.classList.remove('tour-running');
  }

  function render() {
    const s = load();
    unlight();
    if (!s) { remove(); return; }
    // A visitor who followed the suggested link onto the next step's page has moved the tour on.
    if (!isHere(STEPS[s.i]) && s.i + 1 < STEPS.length && isHere(STEPS[s.i + 1])) { s.i += 1; save(s); }
    const step = STEPS[s.i];
    const c = ensureCard();
    document.documentElement.classList.add('tour-running');
    const n = `Step ${s.i + 1} of ${STEPS.length}`;
    if (s.min) {
      c.className = 'tour min';
      c.innerHTML = `<button type="button" class="tour-pill" data-tour-act="open" aria-expanded="false">Tour · ${esc(n)}</button>`;
      return;
    }
    const here = isHere(step);
    c.className = `tour${here ? '' : ' paused'}`;
    const last = s.i === STEPS.length - 1;
    c.innerHTML = here
      ? `<div class="tour-top"><p class="tour-n">${esc(n)}</p><button type="button" class="tour-x" data-tour-act="min" aria-label="Hide the tour card" aria-expanded="true">Hide</button></div>
        <h2 class="tour-h">${esc(step.title)}</h2>
        <p class="tour-t">${esc(step.text)}</p>
        ${step.act ? `<p class="tour-act">${esc(step.act)}</p>` : ''}
        <div class="tour-bar">
          <button type="button" class="alt" data-tour-act="back"${s.i === 0 ? ' disabled' : ''}>Back</button>
          <button type="button" data-tour-act="${last ? 'exit' : 'next'}">${last ? 'Finish' : 'Next'}</button>
          <button type="button" class="tour-exit" data-tour-act="exit">Exit tour</button>
        </div>`
      : `<div class="tour-top"><p class="tour-n">Tour paused · ${esc(n)}</p></div>
        <p class="tour-t">The tour waits at “${esc(step.title)}”.</p>
        <div class="tour-bar">
          <button type="button" data-tour-act="resume">Back to the tour</button>
          <button type="button" class="tour-exit" data-tour-act="exit">Exit tour</button>
        </div>`;
    if (here && step.target) point(step, s.i);
  }

  // Find the step's element (waiting while the page builds it), light it, fill its box, and bring it into view clear
  // of the card.
  function point(step, i, started = Date.now()) {
    const el = document.querySelector(step.target);
    const shown = el && el.getClientRects().length > 0;
    if (!shown) {
      if (Date.now() - started < WAIT_MS) waitTimer = setTimeout(() => { if (load()?.i === i) point(step, i, started); }, 250);
      return;
    }
    lit = el;
    el.classList.add('tour-on');
    if (step.fill && filled !== `${i}`) {
      const box = document.getElementById(step.fill.id);
      const ours = STEPS.map((x) => x.fill && x.fill.value).filter(Boolean);
      if (box && !box.disabled && (!box.value || ours.includes(box.value))) {
        box.value = step.fill.value;
        box.dispatchEvent(new Event('input', { bubbles: true }));
        filled = `${i}`;
      }
    }
    reveal(el);
  }
  function reveal(el) {
    el.scrollIntoView({ block: 'center', inline: 'nearest' });
    if (!card) return;
    const head = document.querySelector('header.top');
    const top = (head && /sticky|fixed/.test(getComputedStyle(head).position) ? head.getBoundingClientRect().bottom : 0) + 8;
    const r = el.getBoundingClientRect(), k = card.getBoundingClientRect();
    const overlaps = r.bottom > k.top && r.top < k.bottom && r.right > k.left && r.left < k.right;
    if (!overlaps) return;
    // Above the card, its top just under the header, so what follows it shows too.
    window.scrollBy(0, r.top - top - 4);
  }

  // ------------------------------------------------------------------ moving
  function go(i) {
    const s = { ...(load() || {}), i, min: false };
    save(s);
    filled = null;
    const step = STEPS[i];
    if (isHere(step)) { render(); return; }
    if (samePage(step)) { location.hash = parse(step.url).hash; render(); return; }   // a section of this page
    location.assign(step.url);
  }
  function exit() {
    R.store.remove(KEY);
    remove();
  }
  function start() { go(0); }

  function onCardClick(e) {
    const b = e.target.closest('[data-tour-act]');
    if (!b) return;
    const s = load();
    if (!s) { remove(); return; }
    const act = b.dataset.tourAct;
    if (act === 'next') go(Math.min(s.i + 1, STEPS.length - 1));
    else if (act === 'back') go(Math.max(s.i - 1, 0));
    else if (act === 'resume') go(s.i);
    else if (act === 'exit') exit();
    else if (act === 'min' || act === 'open') {
      save({ ...s, min: act === 'min' });
      render();
      const again = card && card.querySelector(act === 'min' ? '[data-tour-act="open"]' : '[data-tour-act="next"], [data-tour-act="exit"]');
      if (again) again.focus();
      return;
    }
    const again = card && card.querySelector('[data-tour-act="next"], [data-tour-act="resume"]');
    if (again) again.focus({ preventScroll: true });
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-tour-start]');
    if (!b) return;
    e.preventDefault();
    start();
  });
  window.addEventListener('hashchange', render);
  window.addEventListener('popstate', () => setTimeout(render, 0));
  R.store.watch((k) => { if (k === KEY || k === null) render(); });

  window.RegistaTour = { steps: STEPS, start, exit, go };
  render();
})();
