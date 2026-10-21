// The match timeline: kick-off to full time, periods shaded, goals marked, one marker per clip in a lane for its kind
// (on the ball, replay, highlight, closeup). Plain script, no build step: it adds window.Regista.timeline.
//
//   Regista.timeline.render(el, { duration, periods, clips, keyMoments, highlight, selected, onPick })
//
//   duration    seconds of video (match.duration_s); falls back to the last period or clip end
//   periods     [{period, t, t_end}] as GET /api/matches/{id} returns them
//   clips       [{id, t, t_end, reason, title?, label: {title}}] as GET /api/matches/{id}/clips returns them
//   keyMoments  [{t, kind: "goal", label}] (match.key_moments)
//   highlight   a Set of clip ids in the current result set; the rest are dimmed. Omit it to dim nothing
//   selected    optional clip id now on the stage, outlined
//   onPick      called with a clip id on click, Enter or Space
//
// Call it again with the same element whenever anything changes: it replaces what it drew. It redraws itself when the
// element is resized. Markers are one tab stop: Tab reaches the strip, the arrow keys (and Home, End) move between
// clips in match order, and hover or focus shows the clip's title. Everything from the API is set as text, never markup.
(function () {
  const R = window.Regista = window.Regista || {};
  const NS = 'http://www.w3.org/2000/svg';
  const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

  // Lanes in a fixed order, so a kind is always in the same place; colours come from shared/regista.css.
  const LANES = [
    { reason: 'on_ball_main', label: 'On the ball', short: 'Ball' },
    { reason: 'replay_appearance', label: 'Replay', short: 'Replay' },
    { reason: 'highlight_appearance', label: 'Highlight', short: 'Highl.' },
    { reason: 'closeup_appearance', label: 'Closeup', short: 'Close' },
  ];
  const OTHER = { reason: 'other', label: 'Other', short: 'Other' };
  const KINDS = Object.fromEntries(LANES.map(l => [l.reason, l.label]));

  const GOAL_H = 20, LANE_H = 16, LANE_GAP = 4, AXIS_H = 20, HIT_MIN = 12, MARK_MIN = 3;

  const CSS = `
  .rtl { position: relative; user-select: none; -webkit-user-select: none; }
  .rtl svg { display: block; width: 100%; overflow: visible; }
  .rtl svg:focus { outline: none; }
  .rtl .bg { fill: var(--panel, #161a24); }
  .rtl .period { fill: var(--line, #262c3a); opacity: .55; }
  .rtl .grid { stroke: var(--line, #262c3a); stroke-width: 1; }
  .rtl .tick, .rtl .lane-name, .rtl .period-name { fill: var(--muted, #9aa3b5); font: 10px/1 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; }
  .rtl .lane-name { font-size: 11px; }
  .rtl .goal-line { stroke: var(--text, #f3f4f6); stroke-width: 1; stroke-dasharray: 2 3; opacity: .55; }
  .rtl .goal { fill: var(--text, #f3f4f6); stroke: var(--bg, #0c0e14); stroke-width: 1.5; }
  .rtl .k-on_ball_main { fill: var(--accent, #ffcd28); }
  .rtl .k-replay_appearance { fill: var(--replay, #d62028); }
  .rtl .k-highlight_appearance { fill: var(--highlight, #4aa8ff); }
  .rtl .k-closeup_appearance { fill: var(--closeup, #c18cff); }
  .rtl .k-other { fill: var(--muted, #9aa3b5); }
  .rtl .clip { cursor: pointer; }
  .rtl .clip .hit { fill: transparent; }
  .rtl .clip.dim .mark { opacity: .22; }
  .rtl .clip:hover .mark, .rtl .clip.dim:hover .mark { opacity: 1; }
  .rtl .clip .ring { fill: none; stroke: var(--text, #f3f4f6); stroke-width: 2; display: none; }
  .rtl .clip.sel .ring { display: block; stroke: var(--text, #f3f4f6); }
  .rtl .clip:focus { outline: none; }
  .rtl .clip:focus-visible .ring, .rtl svg:focus-visible .clip.cur .ring { display: block; stroke: var(--accent, #ffcd28); }
  .rtl-tip { position: absolute; z-index: 3; pointer-events: none; transform: translateX(-50%); max-width: min(280px, 90%);
             background: var(--bg, #0c0e14); color: var(--text, #f3f4f6); border: 1px solid var(--line, #262c3a); border-radius: 6px;
             padding: 6px 9px; font-size: 12px; line-height: 1.35; box-shadow: 0 4px 14px rgba(0,0,0,.45); }
  .rtl-tip b { display: block; font-weight: 700; }
  .rtl-tip span { color: var(--muted, #9aa3b5); }`;

  function injectStyle() {
    if (document.getElementById('regista-timeline-style')) return;
    const s = document.createElement('style');
    s.id = 'regista-timeline-style';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function node(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }

  function text(parent, x, y, cls, value, anchor) {
    const t = node('text', { x, y, class: cls, 'text-anchor': anchor || 'start' }, parent);
    t.textContent = value;
    return t;
  }

  // A tick step that leaves at least ~56 px between labels: 30 s up to 30 min.
  function tickStep(duration, px) {
    const steps = [30, 60, 120, 300, 600, 900, 1800];
    return steps.find(s => (s / duration) * px >= 56) || steps[steps.length - 1];
  }

  const titleOf = (c) => c.title || (c.label && c.label.title) || `${KINDS[c.reason] || 'Clip'} at ${fmt(c.t)}`;

  function draw(el) {
    const st = el._regTimeline;
    const o = st.opts;
    const width = Math.max(240, Math.floor(el.clientWidth || 0) || 600);
    st.width = width;
    const clips = (o.clips || []).filter(c => Number.isFinite(c.t)).slice().sort((a, b) => a.t - b.t || String(a.id).localeCompare(String(b.id)));
    const periods = o.periods || [];
    const duration = o.duration > 0 ? o.duration
      : Math.max(1, ...periods.map(p => p.t_end || 0), ...clips.map(c => c.t_end || c.t));
    const highlight = o.highlight instanceof Set ? o.highlight : null;

    const used = new Set(clips.map(c => (KINDS[c.reason] ? c.reason : 'other')));
    const lanes = LANES.filter(l => used.has(l.reason)).concat(used.has('other') ? [OTHER] : []);
    if (!lanes.length) lanes.push(LANES[0]);
    const laneOf = Object.fromEntries(lanes.map((l, i) => [l.reason, i]));

    const narrow = width < 480;
    const gutter = narrow ? 46 : 78, right = 8;
    const plot = width - gutter - right;
    const x = (t) => gutter + Math.max(0, Math.min(1, t / duration)) * plot;
    const lanesTop = GOAL_H, lanesH = lanes.length * (LANE_H + LANE_GAP) - LANE_GAP;
    const laneY = (i) => lanesTop + i * (LANE_H + LANE_GAP);
    const height = lanesTop + lanesH + AXIS_H;

    // Keep focus on the same clip across a redraw.
    const hadFocus = el.contains(document.activeElement);
    const focusedId = hadFocus && document.activeElement.dataset ? document.activeElement.dataset.clip : null;

    el.textContent = '';
    const wrap = document.createElement('div');
    wrap.className = 'rtl';
    el.appendChild(wrap);
    const shown = highlight ? clips.filter(c => highlight.has(c.id)).length : clips.length;
    const svg = node('svg', { viewBox: `0 0 ${width} ${height}`, height, role: 'group',
                              'aria-label': `Match timeline, ${fmt(duration)}: ${clips.length} clips, ${shown} in the current results. Arrow keys move between clips, Enter plays one.` }, wrap);
    const tip = document.createElement('div');
    tip.className = 'rtl-tip';
    tip.hidden = true;
    tip.setAttribute('aria-hidden', 'true');  // the markers' own labels say the same to screen readers
    wrap.appendChild(tip);

    node('rect', { class: 'bg', x: gutter, y: lanesTop - 2, width: plot, height: lanesH + 4, rx: 3 }, svg);
    periods.forEach((p, i) => {
      const x0 = x(p.t || 0), x1 = x(p.t_end != null ? p.t_end : duration);
      node('rect', { class: 'period', x: x0, y: lanesTop - 2, width: Math.max(0, x1 - x0), height: lanesH + 4 }, svg);
      if (periods.length > 1 && x1 - x0 > 60) text(svg, x0 + 3, 9, 'period-name', i === 0 ? '1st half' : i === 1 ? '2nd half' : `Period ${p.period}`);
    });

    const step = tickStep(duration, plot);
    for (let t = 0; t <= duration + 0.01; t += step) {
      node('line', { class: 'grid', x1: x(t), x2: x(t), y1: lanesTop - 2, y2: lanesTop + lanesH + 4 }, svg);
      if (t > 0 && duration - t > step * 0.4) text(svg, x(t), height - 5, 'tick', fmt(t), 'middle');
    }
    text(svg, gutter, height - 5, 'tick', 'KO', 'start');
    text(svg, gutter + plot, height - 5, 'tick', 'FT', 'end');

    lanes.forEach((l, i) => {
      const y = laneY(i) + LANE_H / 2;
      node('circle', { class: `k-${l.reason}`, cx: 5, cy: y, r: 4 }, svg);
      text(svg, 13, y + 4, 'lane-name', narrow ? l.short : l.label);
    });

    // Dimmed clips first, so the current results are drawn on top of them.
    const layer = node('g', {}, svg);
    const order = clips.slice().sort((a, b) => (highlight ? highlight.has(a.id) - highlight.has(b.id) : 0) || a.t - b.t);
    const byId = {};
    for (const c of order) {
      const kind = KINDS[c.reason] ? c.reason : 'other';
      const x0 = x(c.t), x1 = Math.max(x(c.t_end != null ? c.t_end : c.t), x0 + MARK_MIN);
      const y = laneY(laneOf[kind]);
      const dim = highlight && !highlight.has(c.id);
      const g = node('g', { class: `clip${dim ? ' dim' : ''}${o.selected === c.id ? ' sel' : ''}`, role: 'button', tabindex: '-1',
                            'data-clip': c.id,
                            'aria-label': `${titleOf(c)}. ${KINDS[c.reason] || c.reason || 'Clip'}, ${fmt(c.t)} to ${fmt(c.t_end != null ? c.t_end : c.t)}${dim ? '' : ', in the results'}` }, layer);
      const hw = Math.max(HIT_MIN, x1 - x0);
      node('rect', { class: 'hit', x: (x0 + x1) / 2 - hw / 2, y: y - LANE_GAP / 2, width: hw, height: LANE_H + LANE_GAP }, g);
      // A pixel short at the end, so clips that follow each other (a goal's replays) read as separate marks.
      node('rect', { class: `mark k-${kind}`, x: x0, y: y + 2, width: Math.max(MARK_MIN, x1 - x0 - 1), height: LANE_H - 4, rx: 1.5 }, g);
      node('rect', { class: 'ring', x: x0 - 2, y: y, width: x1 - x0 + 4, height: LANE_H, rx: 3 }, g);
      byId[c.id] = { g, clip: c, cx: (x0 + x1) / 2 };
    }

    // Goals over the lanes: a dashed line through every lane and a ball on top. Not focusable: the label is read out
    // with the strip's description below.
    const goals = (o.keyMoments || []).filter(m => Number.isFinite(m.t));
    for (const m of goals) {
      const gx = x(m.t);
      node('line', { class: 'goal-line', x1: gx, x2: gx, y1: GOAL_H - 6, y2: lanesTop + lanesH + 2 }, svg);
      const ball = node('circle', { class: 'goal', cx: gx, cy: GOAL_H / 2 + 1, r: 5, role: 'img', 'aria-label': m.label || 'Goal' }, svg);
      ball.addEventListener('pointerenter', () => showTip(gx, m.label || 'Goal', fmt(m.t)));
      ball.addEventListener('pointerleave', hideTip);
    }
    if (goals.length) svg.setAttribute('aria-description', goals.map(m => m.label).join('; '));

    // The tip opens under the strip: it never covers the markers, and is never cut off by the top of the page.
    function showTip(cx, title, meta) {
      tip.textContent = '';
      const b = document.createElement('b');
      b.textContent = title;
      const s = document.createElement('span');
      s.textContent = meta;
      tip.append(b, s);
      tip.hidden = false;
      // Keep the tip inside the strip: centred on the marker unless that would cross an edge.
      const half = Math.min(tip.offsetWidth, width) / 2;
      tip.style.left = `${Math.max(half, Math.min(width - half, cx))}px`;
      tip.style.top = `${height + 2}px`;
    }
    function hideTip() { tip.hidden = true; }
    const tipFor = (id) => {
      const m = byId[id];
      if (!m) return;
      const c = m.clip;
      showTip(m.cx, titleOf(c), `${fmt(c.t)}–${fmt(c.t_end != null ? c.t_end : c.t)} · ${KINDS[c.reason] || 'Clip'}`);
    };

    // One tab stop: the current clip (the selected one, else the first result, else the first clip) holds tabindex 0.
    const nav = clips.map(c => c.id);
    let cur = st.current && byId[st.current] ? st.current
      : o.selected && byId[o.selected] ? o.selected
      : (clips.find(c => !highlight || highlight.has(c.id)) || clips[0] || {}).id;
    const setCurrent = (id, focus) => {
      if (cur && byId[cur]) { byId[cur].g.setAttribute('tabindex', '-1'); byId[cur].g.classList.remove('cur'); }
      cur = id;
      st.current = id;
      if (!byId[id]) return;
      byId[id].g.setAttribute('tabindex', '0');
      byId[id].g.classList.add('cur');
      if (focus) byId[id].g.focus();
    };
    if (cur) setCurrent(cur, false);

    const pick = (id) => { if (id && typeof o.onPick === 'function') o.onPick(id); };
    layer.addEventListener('click', (e) => {
      const g = e.target.closest('.clip');
      if (!g) return;
      setCurrent(g.dataset.clip, false);
      pick(g.dataset.clip);
    });
    layer.addEventListener('pointerover', (e) => { const g = e.target.closest('.clip'); if (g) tipFor(g.dataset.clip); });
    layer.addEventListener('pointerleave', () => { if (!wrap.contains(document.activeElement)) hideTip(); else tipFor(cur); });
    layer.addEventListener('focusin', (e) => { const g = e.target.closest('.clip'); if (g) { setCurrent(g.dataset.clip, false); tipFor(g.dataset.clip); } });
    layer.addEventListener('focusout', (e) => { if (!wrap.contains(e.relatedTarget)) hideTip(); });
    layer.addEventListener('keydown', (e) => {
      const i = nav.indexOf(cur);
      let next = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = nav[Math.min(nav.length - 1, i + 1)];
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = nav[Math.max(0, i - 1)];
      else if (e.key === 'Home') next = nav[0];
      else if (e.key === 'End') next = nav[nav.length - 1];
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(cur); return; }
      else if (e.key === 'Escape') { hideTip(); return; }
      if (next) { e.preventDefault(); setCurrent(next, true); tipFor(next); }
    });

    if (focusedId && byId[focusedId]) setCurrent(focusedId, true);
  }

  function render(el, opts) {
    if (!el) return;
    injectStyle();
    const st = el._regTimeline || (el._regTimeline = { width: 0, current: null });
    st.opts = opts || {};
    draw(el);
    // Redraw when the element's width changes (not on every height change this drawing itself causes).
    if (!st.observer && typeof ResizeObserver === 'function') {
      st.observer = new ResizeObserver(() => {
        const w = Math.floor(el.clientWidth || 0);
        if (w && Math.abs(w - st.width) >= 1 && el.isConnected) draw(el);
      });
      st.observer.observe(el);
    }
  }

  R.timeline = { render };
})();
