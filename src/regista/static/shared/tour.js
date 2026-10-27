// The guided tour: one small card on each page it visits, "Step N of M", one or two plain sentences, Back, Next, Exit.
// It follows the demo video's beats (docs/demo-storyboard.md) on what the live app shows, and it only reads: no step
// clicks, asks or writes anything for the visitor. A step may suggest a click ("Press Goal reel") and may put words in a
// search box (never sending them), so a Microsoft Foundry question is only ever asked by the visitor pressing Ask.
//
// Each step names a URL (the tour goes there when the visitor presses Next or Back) and may name one element to
// highlight, by id ("#uploads") or by a data-tour attribute ('[data-tour="goal-reel"]'), never by a page's layout. A step
// marked "rules" says Data Search answers, so on arrival it puts the Clip view's "Who answers" switch back on Data Search
// (and the recap's on Instant): going Back from the Foundry step never spends a Foundry call. The switches only change
// how the page answers the visitor's next question; nothing is sent.
// Where the tour is lives in Regista.store (this browser only, key "tour"), so it resumes after a page load; Exit
// forgets it. Anywhere the step is not, the card says the tour is paused and offers the way back. Only one step moves
// the tour on by itself: one marked "follows" (its page is where the step before it sends the visitor by a link, such as
// Hector Santos from Find players), and only when this page has just loaded by following a link, in a tab the visitor
// is looking at. Never from another tab's change (a second tab on the next step's page would skip the hook), never on
// Back or Forward (steps 2-4 and 6 share one URL, so Back from the upload step would jump to Foundry), never on a page
// restored from the back/forward cache.
//
// Started by any element with data-tour-start (Home and /demo). Loaded with defer after the page's own scripts, on
// every page the tour visits. No inline scripts, handlers or style attributes: the pages run under a CSP.
(function () {
  const R = window.Regista;
  if (!R || typeof document === 'undefined') return;
  const esc = R.esc;
  const KEY = 'tour';
  // How long a step waits for its element: pages build parts of themselves after loading, and on a cold revision the
  // catalogue or a profile can take most of a minute to build the first time.
  const WAIT_MS = 60000;
  const CLICK_GAP_MS = 400;   // Next, Back or resume pressed again sooner is the same press (a double-click), not a second one

  // The steps. Plain data between the markers: tests/test_tour.py reads it as JSON and checks every URL is a route and
  // every target is in its page's HTML or made by its scripts.
  /* STEPS:BEGIN */
  const STEPS = [
    { "id": "hook", "url": "/players/pl_bro_09", "target": "[data-tour=\"goal-reel\"]",
      "title": "Every goal, found",
      "text": "Femi Toure is the top scorer in Regista's synthetic league: five goals, none a penalty. Here is every one, in match order.",
      "act": "Press Goal reel: each goal once, in match order." },
    { "id": "moments", "url": "/?match=syn_0294&player=t_home_09", "target": "#timelineWrap", "rules": true,
      "title": "Every moment of a match",
      "text": "This match comes from Regista's match generator. Regista cut every moment Sami Castellanos is on the ball, plus every replay, highlight and close-up he appears in. Each mark on the timeline is one.",
      "act": "Click any mark to play it." },
    { "id": "ask", "url": "/?match=syn_0294&player=t_home_09", "target": "#askForm", "above": true, "rules": true, "fill": { "id": "fq", "value": "his nutmegs" },
      "title": "Then you just ask",
      "text": "Ask in plain words. With Data Search picked, Regista's own rules answer, so no AI model is called. A follow-up keeps the thread: after his nutmegs, \"now the replays\" narrows them to the replays.",
      "act": "Press Ask, then type \"now the replays\" and press Ask again." },
    { "id": "recap", "url": "/?match=syn_0294&player=t_home_09", "target": "#recap", "rules": true,
      "title": "Recaps and replay packages",
      "text": "Each match gets a recap told from his side, and each sentence plays its moment. Its reel is a broadcaster's replay package.",
      "act": "Open Match recap, then click a sentence." },
    { "id": "video-in", "url": "/me?player=pl_bro_09#matches", "target": "[data-tour=\"agent-steps\"]",
      "title": "Video in: players upload",
      "text": "A rendered film of Femi's friendly went through Azure Blob Storage and a queue to a Container Apps job, where Regista's vision agents found him, each agent with its time. He answered \"Is this you?\" where they were unsure, and the match joined his profile.",
      "act": "Below the agents: the moments they found of him." },
    { "id": "foundry", "url": "/?match=syn_0294&player=t_home_09", "target": "#askForm", "above": true, "fill": { "id": "fq", "value": "his nutmegs here, and any in other matches?" },
      "title": "Microsoft Foundry and MCP",
      "text": "A Foundry agent (gpt-5-mini, on Microsoft Agent Framework) writes the reply and can search other matches with its tools; the moments on the page stay this match's. How Regista answered lists each tool it called and its server: Regista's MCP server or the Azure MCP Server.",
      "act": "Pick Ask Microsoft Foundry, then press Ask. Foundry questions are limited to a few a minute per visitor." },
    { "id": "catalogue", "url": "/scout#competition/co_esp_u19", "target": "[data-tour=\"co-head\"]",
      "title": "A catalogue, checked in Fabric",
      "text": "Regista is also a catalogue of matches uploaded below the professional level: 14 invented competitions in 10 countries. Not in this app: on 26 October 2026 Microsoft Fabric recomputed its 7,399 player numbers from the raw tables; 7,399 of 7,399 matched.",
      "act": "Below: who filmed each match." },
    { "id": "scout", "url": "/scout#find", "target": "#scExamples",
      "title": "Scouts: fair comparisons",
      "text": "Scouts ask in plain words. Players are compared only with players of their own level, age group and gender, and every percentile names its pool.",
      "act": "Press \"Who are the best U19 dribblers up front?\", then open Hector Santos." },
    { "id": "number", "url": "/players/pl_pnr_11", "target": "[data-tour=\"stat-take_ons_won\"]", "follows": true,
      "title": "Every number opens its moments",
      "text": "Hector Santos is an invented U19 forward in Spain. Each number on his profile opens the moments it was counted from.",
      "act": "Press Take-ons won, then pick a moment to play it." },
    { "id": "terminal", "url": "/scout#terminal", "target": "#txForm", "fill": { "id": "txIn", "value": "most goals in England" },
      "title": "The Scout terminal",
      "text": "127 metrics, each with its definition and source, in linked panels, with a search box that reads plain questions.",
      "act": "Press Search: Femi Toure comes first." },
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
  let card = null, lit = null, waitTimer = null, filled = null, ruled = null, lastMove = 0;
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

  // Did this page just load because the visitor followed a link (or typed the address), in a tab they are looking at?
  // Not a Back or Forward, and not a tab in the background (see the top of this file).
  function followedHere() {
    if (document.visibilityState !== 'visible') return false;
    let type = '';
    try {
      const nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
      type = nav ? nav.type : (performance.navigation && performance.navigation.type === 2 ? 'back_forward' : '');
    } catch (e) { type = ''; }
    return type !== 'back_forward';
  }

  // arrived: this is the page's own first render (not a hash change, another tab's change, or a restored page).
  function render(arrived = false) {
    const s = load();
    unlight();
    if (!s) { remove(); return; }
    // A visitor who followed the suggested link onto a "follows" step's page has moved the tour on.
    const next = STEPS[s.i + 1];
    if (arrived && next && next.follows && !isHere(STEPS[s.i]) && isHere(next) && followedHere()) { s.i += 1; save(s); }
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
          ${last ? '' : '<button type="button" class="tour-exit" data-tour-act="exit">Exit tour</button>'}
        </div>`
      : `<div class="tour-top"><p class="tour-n">Tour paused · ${esc(n)}</p></div>
        <p class="tour-t">The tour waits at “${esc(step.title)}”.</p>
        <div class="tour-bar">
          <button type="button" data-tour-act="resume">Back to the tour</button>
          <button type="button" class="tour-exit" data-tour-act="exit">Exit tour</button>
        </div>`;
    if (here && step.rules && ruled !== s.i) { ruled = s.i; rulesEngine(); }
    if (here && step.target) point(step, s.i);
  }

  // The Clip view's switches back on Regista's own rules (see the top of this file). The ask switch's change event runs
  // the page's own setEngine, which sets all three of its copies; the recap's switch is read when the recap is next
  // written, so it is only set.
  function rulesEngine() {
    const ask = document.querySelector('input[name="fengine"][value="rules"]');
    if (ask && !ask.checked) { ask.checked = true; ask.dispatchEvent(new Event('change', { bubbles: true })); }
    const recap = document.querySelector('input[name="recapEngine"][value="rules"]');
    if (recap && !recap.checked) recap.checked = true;
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
    reveal(el, step);
  }
  function reveal(el, step) {
    const head = document.querySelector('header.top');
    const top = (head && /sticky|fixed/.test(getComputedStyle(head).position) ? head.getBoundingClientRect().bottom : 0) + 8;
    // On phones the card is a strip along the bottom (tour.css, max-width 720px): the element goes just under the header,
    // so what it leads to (the video it plays, the answer, the list below it) shows between it and the card. A step whose
    // answer appears above its element ("above": the conversation grows over the Ask box) keeps it in the middle instead.
    if (card && !step.above && window.matchMedia && window.matchMedia('(max-width: 720px)').matches) {
      el.scrollIntoView({ block: 'start', inline: 'nearest' });
      window.scrollBy(0, el.getBoundingClientRect().top - top - 4);
      return;
    }
    el.scrollIntoView({ block: 'center', inline: 'nearest' });
    if (!card) return;
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
    ruled = null;
    const step = STEPS[i];
    if (isHere(step)) { render(); return; }
    if (samePage(step)) { location.hash = parse(step.url).hash; render(); return; }   // a section of this page
    // Leaving the page: the card's buttons stop answering until the next page shows its own card.
    if (card) for (const b of card.querySelectorAll('button')) b.disabled = true;
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
    if (act === 'next' || act === 'back' || act === 'resume') {
      // A double-click on Next would otherwise move two steps: the first press re-renders the card (or starts loading
      // the next page) and the second lands on the new Next. The second click of a double-click, or any press within
      // CLICK_GAP_MS of the last move, is ignored.
      const now = Date.now();
      if (e.detail > 1 || now - lastMove < CLICK_GAP_MS) return;
      lastMove = now;
    }
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
  window.addEventListener('hashchange', () => render());
  window.addEventListener('popstate', () => setTimeout(() => render(), 0));
  // A page restored from the back/forward cache keeps the card it was left with, buttons disabled by go(): draw it again.
  window.addEventListener('pageshow', (e) => { if (e.persisted) render(); });
  R.store.watch((k) => { if (k === KEY || k === null) render(); });

  window.RegistaTour = { steps: STEPS, start, exit, go };
  render(true);
})();
