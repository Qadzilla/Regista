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
  // An example search fills the box (the sandbox has no backend; searching itself comes from the app).
  for (const c of document.querySelectorAll('.chip')) c.addEventListener('click', () => { const q = document.getElementById('q'); q.value = c.textContent; q.focus(); });
  document.querySelector('.search').addEventListener('submit', (e) => e.preventDefault());
  window.addEventListener('hashchange', show);
  show();
})();
