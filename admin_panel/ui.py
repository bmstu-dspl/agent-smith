from __future__ import annotations

import html
from zoneinfo import available_timezones


def dashboard_html(username: str, role: str) -> str:
    safe_username = html.escape(username)
    safe_role = html.escape(role)
    timezone_names = ["UTC", *sorted(available_timezones() - {"UTC"})]
    timezone_options = "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
        for name in timezone_names
    )
    vertex_locations = [
        "global",
        "us",
        "eu",
        "us-central1",
        "us-east4",
        "us-west1",
        "us-west4",
        "europe-west1",
        "europe-west2",
        "europe-west4",
        "asia-northeast1",
        "asia-south1",
        "asia-southeast1",
    ]
    vertex_location_options = "".join(
        f'<option value="{name}">{name}</option>' for name in vertex_locations
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Smith Admin</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; --ink:#16202a; --muted:#64748b; --line:#dbe3ea; --brand:#075985; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; color:var(--ink); background:#f3f6f8; }}
    header {{ display:flex; justify-content:space-between; align-items:center; padding:1rem 1.5rem; color:white; background:#0c4a6e; }}
    header h1 {{ margin:0; font-size:1.2rem; }}
    header form {{ display:inline; }}
    nav {{ display:flex; gap:.4rem; padding:.75rem 1rem; overflow:auto; background:white; border-bottom:1px solid var(--line); }}
    nav button {{ border:0; background:transparent; padding:.6rem .8rem; cursor:pointer; white-space:nowrap; }}
    nav button.active {{ color:var(--brand); border-bottom:2px solid var(--brand); font-weight:700; }}
    main {{ max-width:1100px; margin:1.5rem auto; padding:0 1rem 3rem; }}
    section {{ display:none; background:white; border:1px solid var(--line); border-radius:10px; padding:1.25rem; box-shadow:0 2px 8px #0f172a0d; }}
    section.active {{ display:block; }}
    h2 {{ margin-top:0; }}
    form.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:1rem; }}
    label {{ display:flex; flex-direction:column; gap:.35rem; font-weight:600; }}
    input, textarea, select, button {{ font:inherit; }}
    input, textarea, select {{ padding:.65rem; border:1px solid #b9c6d2; border-radius:6px; }}
    textarea {{ min-height:8rem; }}
    .wide {{ grid-column:1/-1; }}
    button.primary {{ border:0; border-radius:6px; padding:.7rem 1rem; color:white; background:var(--brand); cursor:pointer; }}
    button.danger {{ border:1px solid #b91c1c; color:#b91c1c; background:white; border-radius:5px; padding:.35rem .55rem; cursor:pointer; }}
    table {{ width:100%; border-collapse:collapse; margin-top:1rem; }}
    th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:.6rem; vertical-align:top; }}
    .muted {{ color:var(--muted); }}
    #notice {{ position:fixed; right:1rem; bottom:1rem; max-width:28rem; padding:.8rem 1rem; border-radius:6px; color:white; background:#166534; display:none; }}
    #notice.error {{ background:#b91c1c; }}
    .actions {{ display:flex; gap:.35rem; flex-wrap:wrap; }}
  </style>
</head>
<body>
<header>
  <h1>Agent Smith Admin</h1>
  <div>{safe_username} · {safe_role} <button id="logout">Sign out</button></div>
</header>
<nav aria-label="Administration areas">
  <button data-tab="telegram" class="active">Telegram settings</button>
  <button data-tab="agent">Agent settings</button>
  <button data-tab="rag-settings">RAG settings</button>
  <button data-tab="rag-documents">RAG documents</button>
  <button data-tab="mcp">MCP servers</button>
  <button data-tab="admins">Administrators</button>
</nav>
<main>
  <section id="telegram" class="active">
    <h2>Telegram settings</h2>
    <p class="muted">A blank bot token keeps the existing encrypted token. Bot token and webhook changes require a bot restart; group, AI URL, and fallback changes are picked up while running.</p>
    <form id="telegram-form" class="grid">
      <input name="revision" type="hidden">
      <label>Bot token <input name="bot_token" type="password" autocomplete="off"></label>
      <label>Webhook host <input name="webhook_host" type="url" required></label>
      <label>Management group ID <input name="manager_group_id" type="number"></label>
      <label>AI agent URL <input name="ai_agent_url" type="url" required></label>
      <label><span>Customer-support fallback</span><select name="enable_escalation"><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
      <div class="wide"><button class="primary">Save Telegram settings</button></div>
    </form>
  </section>
  <section id="agent">
    <h2>Agent settings</h2>
    <form id="agent-form" class="grid">
      <input name="revision" type="hidden">
      <label>Provider <select name="provider"><option value="google_vertex">Google Vertex</option><option value="openai">OpenAI</option></select></label>
      <label>Model <input name="model" required></label>
      <label>Temperature <input name="temperature" type="number" min="0" max="2" step=".1" required></label>
      <label id="vertex-location-field">Vertex location <select name="vertex_location">{vertex_location_options}</select></label>
      <label>Primary timezone <select name="primary_timezone">{timezone_options}</select></label>
      <label class="wide">Persona prompt <textarea name="system_prompt" required></textarea></label>
      <p class="muted wide">The persona is configurable. Core tool-use and workflow instructions are managed by the runtime.</p>
      <div class="wide"><button class="primary">Save agent settings</button></div>
    </form>
  </section>
  <section id="rag-settings">
    <h2>RAG settings</h2>
    <form id="rag-form" class="grid">
      <input name="revision" type="hidden">
      <label>Status <select name="enabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
      <label>Retrieval mode <select name="retrieval_mode"><option>hybrid</option><option>semantic</option><option>lexical</option></select></label>
      <label>Search limit <input name="limit" type="number" min="1" max="100"></label>
      <label>Max context characters <input name="max_context_chars" type="number"></label>
      <label>Max chunk characters <input name="max_chunk_chars" type="number"></label>
      <label>Chunk overlap characters <input name="chunk_overlap_chars" type="number"></label>
      <label class="wide">Additional RAG instructions <textarea name="additional_instructions"></textarea></label>
      <div class="wide"><button class="primary">Save RAG settings</button></div>
    </form>
  </section>
  <section id="rag-documents">
    <h2>RAG documents</h2>
    <form id="rag-upload" class="grid">
      <label>Tenant <input name="tenant_id" value="default" required></label>
      <label>Document ID <input name="document_id" required></label>
      <label>Version ID <input name="version_id" required></label>
      <label>Title <input name="title" required></label>
      <label>Visibility <input name="visibility" value="tenant"></label>
      <label>Trust level <select name="trust_level"><option>trusted</option><option>unknown</option><option>untrusted</option></select></label>
      <label class="wide">Document file <input name="file" type="file" accept=".txt,.md,.markdown,.html,.htm,.docx,.pdf" required></label>
      <div class="wide"><button class="primary">Upload and process</button></div>
    </form>
    <div class="actions"><button id="rag-refresh">Refresh documents</button></div>
    <table><thead><tr><th>Document</th><th>Published version</th><th>Actions</th></tr></thead><tbody id="rag-documents-body"></tbody></table>
    <h3>Selected document versions</h3>
    <table><thead><tr><th>Version</th><th>Status</th><th>Actions</th></tr></thead><tbody id="rag-versions-body"></tbody></table>
    <h3>Search preview</h3>
    <form id="rag-search" class="grid">
      <label>Query <input name="query" required></label>
      <div><button class="primary">Search published memory</button></div>
    </form>
    <pre id="rag-search-results" class="muted"></pre>
  </section>
  <section id="mcp">
    <h2>MCP servers</h2>
    <form id="mcp-form" class="grid">
      <label>Name <input name="name" required></label>
      <label>Transport <select name="transport_type"><option>sse</option><option>http</option><option>stdio</option></select></label>
      <label class="wide">URL or command <input name="url" required></label>
      <label>Headers JSON <textarea name="headers">{{}}</textarea></label>
      <label>Query parameters JSON <textarea name="query_params">{{}}</textarea></label>
      <div class="wide"><button class="primary">Add MCP server</button></div>
    </form>
    <table><thead><tr><th>Server</th><th>Transport</th><th>Status</th><th>Actions</th></tr></thead><tbody id="mcp-body"></tbody></table>
  </section>
  <section id="admins">
    <h2>Administrators</h2>
    <form id="admin-form" class="grid">
      <label>Username <input name="username" required></label>
      <label>Password <input name="password" type="password" minlength="12" required></label>
      <label>Role <select name="role"><option>viewer</option><option>editor</option><option>admin</option></select></label>
      <div class="wide"><button class="primary">Create administrator</button></div>
    </form>
  </section>
</main>
<div id="notice" role="status"></div>
<script>
let csrf = "";
const notice = (message, error=false) => {{
  const element = document.getElementById("notice");
  element.textContent = message; element.className = error ? "error" : "";
  element.style.display = "block"; setTimeout(() => element.style.display = "none", 5000);
}};
async function api(path, options={{}}) {{
  options.headers = options.headers || {{}};
  if ((options.method || "GET") !== "GET") options.headers["X-CSRF-Token"] = csrf;
  const response = await fetch(path, options);
  if (!response.ok) {{
    let detail = response.statusText;
    try {{ const body = await response.json(); detail = body.detail || body.error || detail; }} catch (_) {{}}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }}
  if (response.status === 204) return null;
  return response.json();
}}
function fill(formId, data) {{
  const form = document.getElementById(formId);
  for (const [key, value] of Object.entries(data)) {{
    if (form.elements[key] && key !== "bot_token") form.elements[key].value = value ?? "";
  }}
}}
function jsonForm(form) {{
  return Object.fromEntries(new FormData(form).entries());
}}
function updateProviderFields() {{
  const provider = document.querySelector('#agent-form [name="provider"]').value;
  document.getElementById("vertex-location-field").style.display =
    provider === "google_vertex" ? "flex" : "none";
}}
document.querySelector('#agent-form [name="provider"]').onchange = updateProviderFields;
document.querySelectorAll("nav button").forEach(button => button.onclick = () => {{
  document.querySelectorAll("nav button, main section").forEach(x => x.classList.remove("active"));
  button.classList.add("active"); document.getElementById(button.dataset.tab).classList.add("active");
}});
async function loadSettings() {{
  const session = await api("/admin/api/session"); csrf = session.csrf_token;
  fill("telegram-form", await api("/admin/api/settings/telegram"));
  fill("agent-form", await api("/admin/api/settings/agent"));
  updateProviderFields();
  fill("rag-form", await api("/admin/api/settings/rag"));
}}
async function saveJsonSettings(event, area) {{
  event.preventDefault(); const data = jsonForm(event.target);
  for (const key of ["revision","manager_group_id","temperature","limit","max_context_chars","max_chunk_chars","chunk_overlap_chars"]) {{
    if (key in data) data[key] = data[key] === "" ? null : Number(data[key]);
  }}
  for (const key of ["enabled","enable_escalation"]) if (key in data) data[key] = data[key] === "true";
  if (data.bot_token === "") delete data.bot_token;
  const saved = await api(`/admin/api/settings/${{area}}`, {{method:"PUT",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(data)}});
  fill(event.target.id, saved); notice("Settings saved and available to the runtime.");
}}
document.getElementById("telegram-form").onsubmit = e => saveJsonSettings(e, "telegram").catch(e => notice(e.message,true));
document.getElementById("agent-form").onsubmit = e => saveJsonSettings(e, "agent").catch(e => notice(e.message,true));
document.getElementById("rag-form").onsubmit = e => saveJsonSettings(e, "rag").catch(e => notice(e.message,true));
document.getElementById("rag-upload").onsubmit = async event => {{
  event.preventDefault();
  try {{ await api("/admin/api/rag/documents/file", {{method:"POST", body:new FormData(event.target)}}); notice("Document processed."); await loadRag(); }}
  catch (error) {{ notice(error.message,true); }}
}};
async function loadRag() {{
  const tenant = document.querySelector("#rag-upload [name=tenant_id]").value;
  const body = document.getElementById("rag-documents-body"); body.replaceChildren();
  const result = await api(`/admin/api/rag/documents?tenant_id=${{encodeURIComponent(tenant)}}`);
  for (const doc of result.documents) {{
    const row = body.insertRow(); row.insertCell().textContent = `${{doc.title}} (${{doc.document_id}})`;
    row.insertCell().textContent = doc.published_version_id || "—";
    const actions = row.insertCell();
    const inspect = window.document.createElement("button"); inspect.textContent="Versions";
    inspect.onclick = () => loadVersions(tenant, doc.document_id);
    const button = window.document.createElement("button"); button.className="danger"; button.textContent="Delete";
    button.onclick = async () => {{ if(confirm("Delete document?")) {{ await api(`/admin/api/rag/documents/${{encodeURIComponent(doc.document_id)}}?tenant_id=${{encodeURIComponent(tenant)}}`,{{method:"DELETE"}}); await loadRag(); }} }};
    actions.append(inspect,button);
  }}
}}
async function loadVersions(tenant, documentId) {{
  const detail=await api(`/admin/api/rag/documents/${{encodeURIComponent(documentId)}}?tenant_id=${{encodeURIComponent(tenant)}}`);
  const body=document.getElementById("rag-versions-body"); body.replaceChildren();
  for (const version of detail.versions) {{
    const row=body.insertRow(); row.insertCell().textContent=version.version_id; row.insertCell().textContent=version.review_status;
    const actions=row.insertCell();
    for (const action of ["approve","reject","vectorize","publish","archive"]) {{
      const button=document.createElement("button"); button.textContent=action;
      button.onclick=async()=>{{await api(`/admin/api/rag/documents/${{encodeURIComponent(documentId)}}/versions/${{encodeURIComponent(version.version_id)}}/${{action}}?tenant_id=${{encodeURIComponent(tenant)}}`,{{method:"POST"}});await loadVersions(tenant,documentId);await loadRag();}};
      actions.append(button);
    }}
    const chunks=document.createElement("button"); chunks.textContent="View chunks";
    chunks.onclick=async()=>{{const result=await api(`/admin/api/rag/documents/${{encodeURIComponent(documentId)}}/versions/${{encodeURIComponent(version.version_id)}}/chunks?tenant_id=${{encodeURIComponent(tenant)}}`);document.getElementById("rag-search-results").textContent=JSON.stringify(result.chunks,null,2);}};
    const remove=document.createElement("button"); remove.className="danger"; remove.textContent="Delete version";
    remove.onclick=async()=>{{if(confirm("Delete version?")){{await api(`/admin/api/rag/documents/${{encodeURIComponent(documentId)}}/versions/${{encodeURIComponent(version.version_id)}}?tenant_id=${{encodeURIComponent(tenant)}}`,{{method:"DELETE"}});await loadVersions(tenant,documentId);await loadRag();}}}};
    actions.append(chunks,remove);
  }}
}}
document.getElementById("rag-search").onsubmit=async event=>{{
  event.preventDefault(); const tenant=document.querySelector("#rag-upload [name=tenant_id]").value;
  const query=new FormData(event.target).get("query"); const result=await api(`/admin/api/rag/search?tenant_id=${{encodeURIComponent(tenant)}}&query=${{encodeURIComponent(query)}}`);
  document.getElementById("rag-search-results").textContent=JSON.stringify(result.results,null,2);
}};
document.getElementById("rag-refresh").onclick = () => loadRag().catch(e => notice(e.message,true));
document.getElementById("mcp-form").onsubmit = async event => {{
  event.preventDefault();
  try {{ const data=jsonForm(event.target); data.headers=JSON.parse(data.headers||"{{}}"); data.query_params=JSON.parse(data.query_params||"{{}}");
    await api("/admin/api/mcp/servers",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(data)}}); notice("MCP server added."); await loadMcp();
  }} catch(error) {{ notice(error.message,true); }}
}};
async function loadMcp() {{
  const body=document.getElementById("mcp-body"); body.replaceChildren();
  for (const server of (await api("/admin/api/mcp/servers")).servers) {{
    const row=body.insertRow(); row.insertCell().textContent=`${{server.name}}\\n${{server.url}}`; row.insertCell().textContent=server.transport_type;
    row.insertCell().textContent=server.is_active ? "active" : "disabled"; const actions=row.insertCell();
    const toggle=document.createElement("button"); toggle.textContent=server.is_active?"Disable":"Enable";
    toggle.onclick=async()=>{{await api(`/admin/api/mcp/servers/${{server.server_id}}/toggle`,{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{is_active:!server.is_active}})}});await loadMcp();}};
    const remove=document.createElement("button"); remove.className="danger"; remove.textContent="Delete";
    remove.onclick=async()=>{{if(confirm("Delete MCP server?")){{await api(`/admin/api/mcp/servers/${{server.server_id}}`,{{method:"DELETE"}});await loadMcp();}}}};
    actions.append(toggle,remove);
  }}
}}
document.getElementById("admin-form").onsubmit = async event => {{
  event.preventDefault();
  try {{ await api("/admin/api/admins",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(jsonForm(event.target))}}); event.target.reset(); notice("Administrator created."); }}
  catch(error) {{ notice(error.message,true); }}
}};
document.getElementById("logout").onclick = async () => {{ await api("/admin/logout",{{method:"POST"}}); location.href="/admin/login"; }};
loadSettings().then(() => Promise.all([loadRag(),loadMcp()])).catch(error => notice(error.message,true));
</script>
</body></html>"""
