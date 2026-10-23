// Switches between the three empty views by the URL hash (#home, #profile, #scout) and marks the current one in the nav.
(function () {
  const views = ['home', 'profile', 'scout'];
  function show() {
    const v = views.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';
    for (const s of document.querySelectorAll('main section')) s.hidden = s.dataset.view !== v;
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
  document.querySelector('.search').addEventListener('submit', (e) => e.preventDefault());
  window.addEventListener('hashchange', show);
  show();
})();
