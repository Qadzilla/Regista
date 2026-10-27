// The judges' page (/demo): what this server runs on, read from /api/health now, as Home's "Running on" row reads it (the
// same official icons, each beside its full name), and the catalogue's size from /api/catalogue. Only what health says
// is running is shown; nothing is listed from memory. "Take the tour" is shared/tour.js (data-tour-start).
// Plain script on window.Regista; no inline scripts, handlers or style attributes (the page runs under a CSP).
(function () {
  const R = window.Regista;
  const { esc } = R;
  const $ = (id) => document.getElementById(id);

  // [icon, full name, running?, what it does here]: the same services, icons and flags as Home (product/app.js runningOn).
  function services(h) {
    const cloud = h.cloud || {};
    return [
      ['foundry', 'Microsoft Foundry', cloud.foundry, `Answers Ask Microsoft Foundry, writes Foundry recaps and Scout answers, labels uploaded matches${cloud.model ? ` (${cloud.model})` : ''}`],
      ['agent-framework', 'Microsoft Agent Framework', true, 'Runs the agent workflows: vision, clips, labels, review, recap, profiles'],
      ['mcp', 'Azure MCP Server', h.azure_mcp, 'A Foundry agent\'s tool for the clip search index, beside Regista\'s own MCP server'],
      ['cosmos-db', 'Azure Cosmos DB', cloud.cosmos, 'Stores matches, clips, labels and reviewers\' verdicts'],
      ['ai-search', 'Azure AI Search', cloud.search, 'Indexes the library\'s labelled clips for search across matches'],
      ['container-apps', 'Azure Container Apps', h.container_apps, 'Runs this app, and the job that runs the vision agents on uploads'],
      ['storage', 'Azure Storage', h.storage, 'Holds uploaded footage, and the queue that hands it to the vision job'],
      ['app-insights', 'Application Insights', h.tracing, 'Receives a trace of every agent step and tool call'],
    ].filter((s) => s[2]);
  }

  async function health() {
    let h;
    try { h = await R.api('/api/health'); } catch (e) {
      $('runningNote').textContent = 'This server\'s health could not be read just now. Reload the page to try again.';
      return;
    }
    const on = services(h);
    $('runningList').innerHTML = on.map(([icon, name, , what]) => `<li class="dm-tile">
      <img src="/static/product/icons/${esc(icon)}.svg" alt="" width="40" height="40">
      <span class="dm-tname">${esc(name)}</span><span class="muted small">${esc(what)}</span></li>`).join('');
    $('runningNote').textContent = on.length > 1
      ? 'Read from this server\'s health check as the page opened: only what is running now is listed.'
      : 'This copy of Regista runs without Azure (a local run): the code itself, with Regista\'s own rules answering.';
  }

  async function catalogue() {
    let c;
    try { c = await R.api('/api/catalogue'); } catch (e) { return; }   // the static sentence stays
    const t = c.totals || {};
    if (!t.competitions) return;
    $('catLine').textContent = `${t.competitions} competitions in ${t.countries} countries, ${t.matches} uploaded matches: players compared only within their own level, age group and gender. Every number opens its moments.`;
  }

  health();
  catalogue();
})();
