// The player profile page (/players/{global_id}): one synthetic player across every match of the Regista League, as a
// scout sees it. Reads GET /api/players/{id} and draws it with the shared renderer (profile-view.js, the same page the
// Player dashboard shows as "My profile"), with the SCOUT BAR on top: shortlist stage, Message, Compare, Notes, Write a
// report. What the bar keeps (stages, notes, compare picks, conversations, drafts) is the visitor's own, in this
// browser only (Regista.demo, shared/demo.js); Message, Compare and Write a report open the Scout dashboard's section
// with this player picked: /scout#messages/<id>, /scout#shortlist/<id>, /scout#reports/<id>.
// No build step, no inline script or style (the CSP allows script-src 'self').
(function () {
  const R = window.Regista;
  const { esc, api, ApiError } = R;
  const demo = R.demo;
  const $ = (id) => document.getElementById(id);

  const GID = decodeURIComponent(location.pathname.replace(/\/+$/, '').split('/').pop() || '');
  const POSITIONS = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };

  let profile = null;
  let view = null;
  const listeners = [];

  // Another script (add-match.js) may follow the profile: it gets it on load and after every reload, and can ask for a
  // reload once a match is added. Nothing here depends on that script existing.
  window.RegistaPlayer = {
    id: GID,
    get profile() { return profile; },
    onProfile(fn) { listeners.push(fn); if (profile) fn(profile); },
    reload: () => load(),
  };

  // ------------------------------------------------------------------ load
  async function load() {
    $('netError').hidden = true;
    if (!/^pl_[a-z0-9_]{1,40}$/.test(GID)) return showMissing('That is not a player id.');
    $('loading').hidden = !!profile;
    const slow = setTimeout(() => {
      $('loading').textContent = 'Loading the profile… The league is built on first use, which can take about half a minute.';
    }, 3000);
    let next;
    try {
      next = await api(`/api/players/${encodeURIComponent(GID)}`);
    } catch (e) {
      clearTimeout(slow);
      $('loading').hidden = true;
      if (e instanceof ApiError && e.status === 404) return showMissing();
      $('netErrorText').textContent = e instanceof ApiError
        ? `The profile could not be loaded (${typeof e.detail === 'string' ? e.detail : `HTTP ${e.status}`}).`
        : 'The profile could not be loaded. Check your connection.';
      $('netError').hidden = false;
      return;
    }
    clearTimeout(slow);
    $('loading').hidden = true;
    profile = next;
    show();
    listeners.forEach((fn) => { try { fn(profile); } catch (e) { console.error(e); } });
    document.dispatchEvent(new CustomEvent('regista:profile', { detail: profile }));
  }

  function showMissing(text) {
    document.title = 'No such player · Regista Scout';
    if (text) $('missingText').textContent = text;
    $('profile').hidden = true;
    $('loading').hidden = true;
    $('missing').hidden = false;
  }

  function show() {
    $('missing').hidden = true;
    $('profile').hidden = false;
    document.title = `${profile.name} · Regista Scout`;
    const keep = view ? view.state() : {};       // a reload (a match added) keeps the open evidence
    if (view) view.pause();
    view = R.profileView.render($('profileView'), profile, { bar: scoutBar, stat: keep.stat });
    myDetails();
  }

  // The player's own "My details" edits from the Player dashboard (/me#team) in this browser: scouts see what the
  // player wrote at the top of the profile, as the player's My profile does.
  function myDetails() {
    if (!view || !profile) return;
    const d = demo.details(profile.global_id);
    if (!d) { view.identity(); return; }
    const kit = Number(d.kit_number), height = Number(d.height);
    const name = (typeof d.name === 'string' && d.name.trim()) || profile.name;
    view.identity(name, POSITIONS[d.position] ? d.position : profile.position,
      Number.isInteger(kit) && kit >= 1 && kit <= 99 ? kit : profile.kit_number,
      { foot: ['Right', 'Left', 'Both'].includes(d.foot) ? d.foot : '', height: height >= 140 && height <= 220 ? Math.round(height) : null,
        bio: typeof d.bio === 'string' ? d.bio.slice(0, 280) : '' });
    document.title = `${name} · Regista Scout`;
  }

  // ------------------------------------------------------------------ the scout bar
  let notesOpen = false;
  function scoutBar(slot, p) {
    const sl = demo.shortlist()[p.global_id];
    const inCompare = demo.compare().includes(p.global_id);
    const pos = POSITIONS[p.position] || p.position;
    const opt = (v, text, on) => `<option value="${esc(v)}"${on ? ' selected' : ''}>${esc(text)}</option>`;
    slot.innerHTML = `<div class="sc-bar panel" role="region" aria-label="Scout tools for ${esc(p.name)}">
        <div class="sc-barwho"><b>${esc(p.name)}</b><span class="muted small">${esc(pos)} · ${esc(p.club)}</span></div>
        <label class="sc-stagepick"><span class="sr">Shortlist stage for ${esc(p.name)}</span><select data-bar="stage">
          ${opt('', 'Not on your shortlist', !sl)}${demo.STAGES.map((st) => opt(st, st, sl && sl.stage === st)).join('')}</select></label>
        <a class="sc-barbtn" data-bar="message" href="/scout#messages/${esc(encodeURIComponent(p.global_id))}">Message</a>
        <a class="sc-barbtn" data-bar="compare" href="/scout#shortlist/${esc(encodeURIComponent(p.global_id))}"
           title="${inCompare ? 'In your comparison' : 'Add to your comparison'}">${inCompare ? 'In compare' : 'Compare'}</a>
        <button type="button" class="alt" data-bar="notes" aria-expanded="${notesOpen}" aria-controls="scNoteBox">Notes${sl && sl.note ? ' ·' : ''}</button>
        <a class="sc-barbtn primary" data-bar="report" href="/scout#reports/${esc(encodeURIComponent(p.global_id))}">Write a report</a>
      </div>
      <div class="sc-note panel" id="scNoteBox"${notesOpen ? '' : ' hidden'}>
        <label class="pf-field"><span>Your notes on ${esc(p.name)} (private to you)</span>
          <textarea rows="3" maxlength="2000" data-bar="note"></textarea></label>
        <div class="pf-addbar"><button type="button" data-bar="save">Save note</button>
          <button type="button" class="alt" data-bar="cancel">Cancel</button></div>
        <p class="small muted" data-bar="saved" role="status"></p>
      </div>`;
    slot.querySelector('[data-bar="note"]').value = (sl && sl.note) || '';
    if (slot.dataset.wired) return;
    slot.dataset.wired = '1';
    slot.addEventListener('change', (e) => {
      if (e.target.dataset.bar !== 'stage') return;
      demo.setStage(p.global_id, e.target.value);
      scoutBar(slot, p);
      slot.querySelector('[data-bar="stage"]').focus();
    });
    slot.addEventListener('click', (e) => {
      const b = e.target.closest('[data-bar]');
      if (!b) return;
      const act = b.dataset.bar;
      // The links write first, then go: the Scout dashboard opens on what they started.
      if (act === 'message') demo.startConversation(demo.SCOUT, p.global_id, p.name);
      else if (act === 'compare') {
        if (!demo.onShortlist(p.global_id)) demo.setStage(p.global_id, 'Watching');
        if (!demo.compare().includes(p.global_id)) demo.toggleCompare(p.global_id);
      } else if (act === 'report') demo.draftReport(p.global_id, [p.name, (POSITIONS[p.position] || p.position).toLowerCase(), p.club].join(', '));
      else if (act === 'notes' || act === 'cancel') {
        notesOpen = act === 'notes' ? !notesOpen : false;
        scoutBar(slot, p);
        if (notesOpen) slot.querySelector('[data-bar="note"]').focus();
        else slot.querySelector('[data-bar="notes"]').focus();
      } else if (act === 'save') {
        demo.setNote(p.global_id, slot.querySelector('[data-bar="note"]').value.trim());
        scoutBar(slot, p);
        slot.querySelector('[data-bar="saved"]').textContent = 'Saved.';
      }
    });
  }

  // The left panel's Messages count: Maya's unread messages, in this browser.
  function counts() {
    const el = document.querySelector('nav.views [data-count="messages"]');
    if (el) { const n = demo.unread('scout', demo.SCOUT); el.textContent = n ? String(n) : ''; }
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    // Back to the Scout dashboard as it was left (filters, section): the browser's own back when Scout sent us here.
    let fromScout = false;
    try {
      const ref = document.referrer && new URL(document.referrer);
      if (ref && ref.origin === location.origin && ref.pathname.startsWith('/scout')) {
        fromScout = true;
        $('back').href = `${ref.pathname}${ref.search}#find`;  // a referrer never carries the hash
      }
    } catch (e) { /* keep /scout#find */ }
    $('back').addEventListener('click', (e) => {
      if (fromScout && history.length > 1) { e.preventDefault(); history.back(); }
    });
    $('netRetry').addEventListener('click', load);
    // Another tab of this browser changed the shortlist or messages: redraw the bar and the count.
    R.store.watch(() => {
      counts();
      myDetails();
      const slot = document.querySelector('.pf-barslot');
      if (slot && profile) scoutBar(slot, profile);
    });
    counts();
  }

  wire();
  load();
})();
