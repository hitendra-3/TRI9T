// ─── State ───────────────────────────────────────────────────────────────────
let currentDocId     = null;
let currentVerId     = null;
let activeNodeId     = null;
let activeSelectionId = null;
let selectedNodeIds  = new Set();
let nodesMap         = new Map();
let ingestIsNewDoc   = true;
let pendingIngestPayload = null;

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
    loadDocuments();
});

// ─── Theme ────────────────────────────────────────────────────────────────────
function toggleTheme() {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
}

// ─── Modals ───────────────────────────────────────────────────────────────────
function openIngestModal() {
    document.getElementById("ingest-modal").style.display = "flex";
    switchIngestMode(true);
    populateIngestDocSelect();
}
function closeIngestModal() {
    document.getElementById("ingest-modal").style.display = "none";
    cancelIngestMismatch();
}
function openCreateSelectionModal() {
    if (!document.querySelectorAll(".tree-node-checkbox:checked").length) {
        alert("Please check at least one section in the Document Structure tree first.");
        return;
    }
    document.getElementById("selection-modal").style.display = "flex";
}
function closeCreateSelectionModal() { document.getElementById("selection-modal").style.display = "none"; }

// ─── Ingest Mode Toggles & Populators ──────────────────────────────────────────
function switchIngestMode(isNewDoc) {
    ingestIsNewDoc = isNewDoc;
    const btnNew = document.getElementById("btn-mode-new-doc");
    const btnVer = document.getElementById("btn-mode-new-ver");
    const groupName = document.getElementById("ingest-doc-name-group");
    const groupSelect = document.getElementById("ingest-doc-select-group");
    
    if (isNewDoc) {
        btnNew.className = "btn btn-primary btn-sm";
        btnVer.className = "btn btn-secondary btn-sm";
        groupName.style.display = "block";
        groupSelect.style.display = "none";
    } else {
        btnNew.className = "btn btn-secondary btn-sm";
        btnVer.className = "btn btn-primary btn-sm";
        groupName.style.display = "none";
        groupSelect.style.display = "block";
    }
}

async function populateIngestDocSelect() {
    try {
        const r = await fetch("/api/documents");
        if (!r.ok) return;
        const docs = await r.json();
        const select = document.getElementById("ingest-doc-select");
        if (!select) return;
        select.innerHTML = "";
        
        if (docs.length === 0) {
            select.innerHTML = '<option value="">-- No Documents Available --</option>';
            return;
        }
        
        docs.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = d.name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error(err);
    }
}

function cancelIngestMismatch() {
    document.getElementById("confirm-mismatch-modal").style.display = "none";
    pendingIngestPayload = null;
}

async function proceedIngestMismatch() {
    if (!pendingIngestPayload) return;
    pendingIngestPayload.force = true;
    document.getElementById("confirm-mismatch-modal").style.display = "none";
    await executeIngestion(pendingIngestPayload);
}

// ─── File Upload ──────────────────────────────────────────────────────────────
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById("ingest-content").value = e.target.result;
        const m = file.name.toLowerCase().match(/_(v\d+)/) || file.name.toLowerCase().match(/-(v\d+)/);
        if (m) document.getElementById("ingest-ver-label").value = m[1];
    };
    reader.readAsText(file);
}

// ─── Load Preset ──────────────────────────────────────────────────────────────
async function loadPresetFile(filename, verLabel) {
    try {
        const r = await fetch(`/api/documents/presets/${filename}`);
        if (!r.ok) throw new Error("Failed to load preset");
        const d = await r.json();
        document.getElementById("ingest-ver-label").value = verLabel;
        document.getElementById("ingest-content").value = d.content;
    } catch (err) {
        alert("Error: " + err.message);
    }
}

// ─── Ingest ───────────────────────────────────────────────────────────────────
async function submitIngestion() {
    let docName = "";
    let docId = null;
    
    if (ingestIsNewDoc) {
        docName = document.getElementById("ingest-doc-name").value.trim();
        if (!docName) {
            alert("Please enter a document name.");
            return;
        }
    } else {
        const select = document.getElementById("ingest-doc-select");
        if (!select || !select.value) {
            alert("Please select a target document.");
            return;
        }
        docId = parseInt(select.value);
        docName = select.options[select.selectedIndex].textContent;
    }
    
    const verLabel = document.getElementById("ingest-ver-label").value.trim();
    const content  = document.getElementById("ingest-content").value;

    if (!verLabel || !content) {
        alert("Please fill in all fields.");
        return;
    }

    const payload = {
        document_name: docName,
        version_label: verLabel,
        markdown_content: content,
        force: false,
        is_new_document: ingestIsNewDoc,
        document_id: docId
    };
    
    await executeIngestion(payload);
}

async function executeIngestion(payload) {
    try {
        const r = await fetch("/api/documents/ingest", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(payload)
        });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Ingest failed"); }

        const result = await r.json();
        
        if (result.status === "warning") {
            pendingIngestPayload = payload;
            document.getElementById("mismatch-percent-lbl").textContent = `${result.mismatch_percent}%`;
            document.getElementById("confirm-mismatch-modal").style.display = "flex";
            return;
        }
        
        alert(`✓ "${payload.version_label}" ingested.\nTotal: ${result.stats.total_nodes} | New: ${result.stats.new_nodes} | Modified: ${result.stats.modified_nodes}`);
        closeIngestModal();
        await loadDocuments(result.version.document_id, result.version.id);
    } catch (err) {
        alert("Ingest Error: " + err.message);
    }
}

// ─── Documents ────────────────────────────────────────────────────────────────
async function loadDocuments(selectDocId = null, selectVerId = null) {
    try {
        const r = await fetch("/api/documents");
        if (!r.ok) throw new Error("Failed to load documents");
        const docs = await r.json();

        const sel = document.getElementById("doc-selector");
        sel.innerHTML = "";

        if (!docs.length) {
            sel.innerHTML = '<option value="">— No Documents —</option>';
            return;
        }

        docs.forEach(d => {
            const o = document.createElement("option");
            o.value = d.id; o.textContent = d.name;
            sel.appendChild(o);
        });

        const active = selectDocId || docs[0].id;
        sel.value = active;
        currentDocId = parseInt(active);
        await loadDocumentVersions(currentDocId, selectVerId);
    } catch (err) { console.error(err); }
}

// ─── Versions ─────────────────────────────────────────────────────────────────
async function loadDocumentVersions(docId, selectVerId = null) {
    if (!docId) return;
    currentDocId = parseInt(docId);

    try {
        const r = await fetch(`/api/documents/${docId}/versions`);
        if (!r.ok) throw new Error("Failed to load versions");
        const versions = await r.json();

        const sel = document.getElementById("ver-selector");
        sel.innerHTML = "";

        if (!versions.length) {
            sel.innerHTML = '<option value="">— No Versions —</option>';
            return;
        }

        versions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        versions.forEach((v, i) => {
            const o = document.createElement("option");
            o.value = v.id;
            o.textContent = v.version_label + (i === 0 ? " (Latest)" : "");
            sel.appendChild(o);
        });

        const active = selectVerId || versions[0].id;
        sel.value = active;
        currentVerId = parseInt(active);
        await loadVersionDetails(currentVerId);
    } catch (err) { console.error(err); }
}

// ─── Version Details ──────────────────────────────────────────────────────────
async function loadVersionDetails(verId) {
    if (!verId) return;
    currentVerId = parseInt(verId);

    try {
        // 1. Top-level tree nodes
        const nr = await fetch(`/api/nodes/browse?document_id=${currentDocId}&version_id=${currentVerId}`);
        if (!nr.ok) throw new Error("Failed to load nodes");
        const topNodes = await nr.json();

        nodesMap.clear();
        const treeRoot = document.getElementById("tree-root");
        treeRoot.innerHTML = "";

        if (!topNodes.length) {
            treeRoot.innerHTML = '<div class="empty-state">No sections found in this version.</div>';
        } else {
            topNodes.forEach(n => { nodesMap.set(n.id, n); treeRoot.appendChild(createTreeNode(n)); });
        }

        // 2. Version metadata for sidebar
        const vr = await fetch(`/api/versions/${currentVerId}`);
        if (vr.ok) {
            const vd = await vr.json();
            document.getElementById("side-ver-label").textContent = vd.version_label;
            document.getElementById("side-ver-date").textContent   = new Date(vd.created_at).toLocaleDateString();
            const badge = document.getElementById("ver-badge-tree");
            if (badge) badge.textContent = vd.version_label;
        }

        // 3. All nodes (wildcard) for counts + map enrichment
        const ar = await fetch(`/api/nodes/search?document_id=${currentDocId}&query=%25&version_id=${currentVerId}`);
        if (ar.ok) {
            const all = await ar.json();
            setText("side-ver-nodes",       all.length);
            setText("stat-total-sections",  all.length);
            all.forEach(n => nodesMap.set(n.id, n));
        }

        // 4. Dynamic stats
        const sr = await fetch(`/api/versions/${currentVerId}/stats`);
        if (sr.ok) {
            const s = await sr.json();
            setText("stat-new-sections",      s.new_nodes);
            setText("stat-modified-sections", s.modified_nodes);
            setText("side-ver-changed",       s.modified_nodes);
            setText("side-ver-new",           s.new_nodes);
        } else {
            ["stat-new-sections","stat-modified-sections","side-ver-changed","side-ver-new"].forEach(id => setText(id, "0"));
        }

        // 5. Selections
        await loadSelectionsList();

        // 6. Total generations count
        await loadTotalGenerations();

    } catch (err) { console.error(err); }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ─── Generation Count ─────────────────────────────────────────────────────────
async function loadTotalGenerations() {
    try {
        const r = await fetch("/api/selections");
        if (!r.ok) return;
        const sels = await r.json();
        let total = 0;
        await Promise.all(sels.map(async s => {
            const x = await fetch(`/api/selections/${s.id}/test-cases`);
            if (x.ok) total++;
        }));
        setText("stat-total-generations", total);
    } catch (err) { console.error(err); }
}

// ─── Tree Node Builder ────────────────────────────────────────────────────────
function createTreeNode(node) {
    const wrap = document.createElement("div");
    wrap.className = "tree-node";
    wrap.id = `tc-${node.id}`;

    const hdr = document.createElement("div");
    hdr.className = "tree-node-header";
    hdr.id = `th-${node.id}`;
    hdr.onclick = e => { if (e.target.tagName !== "INPUT") selectNode(node.id); };

    // Arrow
    const arrow = document.createElement("span");
    arrow.className = "tree-node-arrow";
    arrow.innerHTML = "&#9654;";

    // Checkbox
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.className = "tree-node-checkbox"; cb.value = node.id;
    cb.onclick = e => { e.stopPropagation(); node.id && (cb.checked ? selectedNodeIds.add(node.id) : selectedNodeIds.delete(node.id)); };

    // Label
    const label = document.createElement("span");
    label.className = "tree-node-label";
    label.textContent = node.title;

    hdr.append(arrow, cb, label);
    wrap.appendChild(hdr);

    // Children container
    const kids = document.createElement("div");
    kids.className = "tree-node-children";
    kids.id = `tk-${node.id}`;
    wrap.appendChild(kids);

    // Expand/collapse
    arrow.onclick = async e => {
        e.stopPropagation();
        const open = kids.classList.toggle("expanded");
        arrow.classList.toggle("expanded", open);
        if (open && !kids.children.length) await loadChildren(node.id, kids);
    };

    return wrap;
}

// ─── Load Children ────────────────────────────────────────────────────────────
async function loadChildren(nodeId, container) {
    try {
        const r = await fetch(`/api/nodes/${nodeId}`);
        if (!r.ok) return;
        const nd = await r.json();

        if (!nd.children.length) {
            const hdr = document.getElementById(`th-${nodeId}`);
            if (hdr) hdr.querySelector(".tree-node-arrow").style.visibility = "hidden";
            return;
        }

        nd.children.forEach(c => { nodesMap.set(c.id, c); container.appendChild(createTreeNode(c)); });
    } catch (err) { console.error(err); }
}

// ─── Select Node ──────────────────────────────────────────────────────────────
async function selectNode(nodeId) {
    activeNodeId = nodeId;
    document.querySelectorAll(".tree-node-header").forEach(h => h.classList.remove("selected"));
    const hdr = document.getElementById(`th-${nodeId}`);
    if (hdr) hdr.classList.add("selected");

    const body = document.getElementById("section-detail-body");
    body.innerHTML = `<div style="text-align:center;padding:24px;"><span class="spinner"></span></div>`;

    try {
        const r   = await fetch(`/api/nodes/${nodeId}`);
        if (!r.ok) throw new Error("Failed to fetch node");
        const node = await r.json();

        const dr   = await fetch(`/api/nodes/${nodeId}/diff`);
        let diffBadge = "";
        let diffBlock = "";

        if (dr.ok) {
            const dd = await dr.json();
            if (dd.has_changed) {
                if (dd.diff_type === "modified") {
                    diffBadge = `<span class="badge badge-yellow">CHANGED</span>`;
                    diffBlock = `<div style="margin-top:12px;">
                        <div style="font-size:11px;font-weight:600;color:var(--text-2);margin-bottom:6px;text-transform:uppercase;">Changes vs Latest Version</div>
                        <div class="diff-view">${colorDiff(dd.diff_text)}</div>
                    </div>`;
                } else if (dd.diff_type === "deleted") {
                    diffBadge = `<span class="badge badge-red">DELETED IN LATEST</span>`;
                }
            } else {
                diffBadge = `<span class="badge badge-green">CURRENT</span>`;
            }
        }

        const levelBadge = ["","badge-blue","badge-green","badge-orange","badge-yellow"][node.level] || "badge-blue";
        const parentPath = node.path.substring(0, node.path.lastIndexOf("/")) || "None (Root)";

        body.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:10px;">
                <div class="detail-heading">${escHtml(node.heading)}</div>
                <button class="btn btn-secondary btn-sm" onclick="scrollToDiff()" style="flex-shrink:0;">View Changes</button>
            </div>

            <div class="meta-badges">
                <span class="badge ${levelBadge}">Level ${node.level}</span>
                <span class="badge badge-blue">ID: ${node.id}</span>
                <span class="badge badge-blue">V${currentVerId}</span>
                ${diffBadge}
            </div>

            <table class="meta-table" style="margin-bottom:12px;">
                <tr><td>Parent Section</td><td>${escHtml(parentPath)}</td></tr>
                <tr><td>Heading Level</td><td>H${node.level}</td></tr>
                <tr><td>Content Hash</td><td>
                    <span style="font-family:monospace;">${node.content_hash.substring(0,16)}…</span>
                    <button class="hash-btn" style="margin-left:6px;" onclick="copy('${node.content_hash}','Hash')">Copy</button>
                </td></tr>
                <tr><td>Logical Node ID</td><td style="font-family:monospace;font-size:10.5px;">${node.logical_id.substring(0,20)}…</td></tr>
            </table>

            <div style="font-size:11px;font-weight:600;color:var(--text-2);margin-bottom:6px;text-transform:uppercase;">Text Content</div>
            <div class="section-body">${renderMarkdown(node.body_text)}</div>

            <div id="diff-anchor">${diffBlock}</div>
        `;
    } catch (err) {
        body.innerHTML = `<div style="color:var(--red);padding:16px;">${err.message}</div>`;
    }
}

function scrollToDiff() {
    const el = document.getElementById("diff-anchor");
    if (el) el.scrollIntoView({ behavior: "smooth" });
}

function copy(text, label) {
    navigator.clipboard.writeText(text).then(() => alert(`${label} copied!`));
}

function escHtml(s) {
    if (!s) return "";
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function colorDiff(text) {
    if (!text) return "";
    return text.split("\n").map(l => {
        const s = escHtml(l);
        if (l.startsWith("+")) return `<span class="diff-add">${s}</span>`;
        if (l.startsWith("-")) return `<span class="diff-del">${s}</span>`;
        if (l.startsWith("@@")) return `<span class="diff-info">${s}</span>`;
        return `<span>${s}</span>`;
    }).join("\n");
}

function renderMarkdown(text) {
    if (!text) return "<em style='color:var(--text-3);'>No content in this section.</em>";
    let html = escHtml(text);
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Inline code
    html = html.replace(/`(.+?)`/g, "<code style='background:var(--bg);border:1px solid var(--border);border-radius:3px;padding:1px 4px;font-size:10.5px;'>$1</code>");

    // Simple markdown table
    const lines = html.split("\n");
    let out = []; let inTable = false; let headers = []; let rows = [];

    function flushTable() {
        if (!headers.length) return;
        let t = `<div style="overflow-x:auto;margin:8px 0;"><table class="tc-table" style="font-size:11px;">`;
        t += `<thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead>`;
        t += `<tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
        t += `</table></div>`;
        out.push(t);
        inTable = false; headers = []; rows = [];
    }

    lines.forEach(line => {
        if (line.startsWith("|") && line.endsWith("|")) {
            const cells = line.split("|").slice(1,-1).map(c=>c.trim());
            if (cells.every(c => /^[-:]+$/.test(c))) return; // separator
            if (!inTable) { inTable = true; headers = cells; }
            else rows.push(cells);
        } else {
            if (inTable) flushTable();
            out.push(line);
        }
    });
    if (inTable) flushTable();

    return out.join("\n");
}

// ─── Selections ───────────────────────────────────────────────────────────────
async function loadSelectionsList(selectId = null) {
    try {
        const r = await fetch("/api/selections");
        if (!r.ok) throw new Error("Failed to load selections");
        const sels = await r.json();

        const sel = document.getElementById("selection-selector");
        sel.innerHTML = '<option value="">— Choose Selection —</option>';
        sels.forEach(s => {
            const o = document.createElement("option");
            o.value = s.id; o.textContent = s.name;
            sel.appendChild(o);
        });

        setText("stat-total-selections", sels.length);

        if (selectId) { sel.value = selectId; loadSelectionDetails(selectId); }
    } catch (err) { console.error(err); }
}

async function loadSelectionDetails(selId) {
    const detPane   = document.getElementById("selection-details-pane");
    const emptyPane = document.getElementById("selection-empty-pane");
    const tcBtn     = document.getElementById("btn-generate-tc");
    const staleness = document.getElementById("staleness-card");
    const tcBody    = document.getElementById("test-cases-body");

    if (!selId) {
        detPane.style.display = "none";
        emptyPane.style.display = "block";
        staleness.style.display = "none";
        tcBtn.style.display = "none";
        tcBody.innerHTML = '<div class="empty-state" style="padding:32px 20px;">Select or create a selection, then generate test cases.</div>';
        return;
    }

    activeSelectionId = parseInt(selId);
    detPane.style.display   = "block";
    emptyPane.style.display = "none";
    tcBtn.style.display     = "inline-flex";

    try {
        const r   = await fetch(`/api/selections/${selId}`);
        if (!r.ok) throw new Error("Failed to load selection");
        const sel = await r.json();

        const verOpt = document.querySelector(`#ver-selector option[value="${sel.version_id}"]`);
        setText("sel-pinned-ver", (verOpt?.textContent || `v${sel.version_id}`).replace(" (Latest)",""));
        document.getElementById("sel-pinned-ver").className = "badge badge-blue";
        document.getElementById("sel-created-on").textContent = new Date(sel.created_at).toLocaleString();

        const list  = document.getElementById("sel-nodes-list");
        list.innerHTML = "";
        setText("sel-node-count", sel.nodes.length);

        sel.nodes.forEach(n => {
            const parts = n.path.split("/").filter(Boolean);
            const short = parts.slice(-2).join(" / ");
            const item  = document.createElement("div");
            item.className = "tag-item";
            item.innerHTML = `<span class="tag-item-label" title="${escHtml(n.path)}">${escHtml(short)}</span><span style="color:var(--text-3);font-size:10px;">#${n.id}</span>`;
            list.appendChild(item);
        });

        await loadTestCases(selId);
    } catch (err) { console.error(err); }
}

// ─── Test Cases ───────────────────────────────────────────────────────────────
async function loadTestCases(selId) {
    const tcBody    = document.getElementById("test-cases-body");
    const staleness = document.getElementById("staleness-card");

    tcBody.innerHTML = `<div style="text-align:center;padding:24px;"><span class="spinner"></span><div style="margin-top:8px;font-size:11px;color:var(--text-2);">Loading test cases…</div></div>`;

    try {
        const r = await fetch(`/api/selections/${selId}/test-cases`);

        if (r.status === 404) {
            tcBody.innerHTML = `
                <div class="empty-state" style="padding:40px 20px;">
                    <div style="font-size:32px;margin-bottom:12px;">🤖</div>
                    No test cases generated yet for this selection.<br><br>
                    <button class="btn btn-primary btn-sm" onclick="triggerTestGeneration()">⚡ Generate Now</button>
                </div>`;
            staleness.style.display = "none";
            return;
        }

        if (!r.ok) throw new Error("Failed to load test cases");
        const gen = await r.json();

        // Resolve selection name for meta bar
        const selOpt = document.querySelector(`#selection-selector option[value="${selId}"]`);
        const selName = selOpt?.textContent || "Selection";
        const genTime = gen.created_at ? new Date(gen.created_at).toLocaleString() : "Unknown";

        // Build tab UI
        let html = `
            <div class="tc-meta-bar">
                <span><strong>Selection:</strong> ${escHtml(selName)}</span>
                <span><strong>Version:</strong> v${gen.version_id ?? "?"}</span>
                <span><strong>Generated:</strong> ${genTime}</span>
            </div>
            <div class="tabs-bar">
                <button class="tab-btn active" id="tab-tc"  onclick="switchTcTab('tc')">Test Cases (${gen.test_cases.length})</button>
                <button class="tab-btn"         id="tab-raw" onclick="switchTcTab('raw')">Raw LLM Output</button>
            </div>

            <div class="tab-panel active" id="panel-tc">
                <table class="tc-table">
                    <thead>
                        <tr>
                            <th style="width:28px;">#</th>
                            <th>Title</th>
                            <th style="width:76px;">Priority</th>
                            <th style="width:62px;">Status</th>
                        </tr>
                    </thead>
                    <tbody>`;

        gen.test_cases.forEach((tc, i) => {
            const pc = tc.priority === "High" ? "badge-red" : tc.priority === "Medium" ? "badge-orange" : "badge-blue";
            html += `
                <tr class="tc-row" onclick="toggleRow('tr-detail-${i}')">
                    <td>${i+1}</td>
                    <td style="font-weight:600;">${escHtml(tc.title)}</td>
                    <td><span class="badge ${pc}">${escHtml(tc.priority)}</span></td>
                    <td><span class="badge badge-green">Valid</span></td>
                </tr>
                <tr class="tc-detail-row" id="tr-detail-${i}">
                    <td colspan="4" class="tc-detail-cell">
                        <div style="font-size:10.5px;font-weight:700;text-transform:uppercase;color:var(--text-2);margin-bottom:6px;">Steps</div>
                        <ol style="margin-left:18px;margin-bottom:12px;">
                            ${tc.steps.map(s => `<li style="margin-bottom:4px;">${escHtml(s)}</li>`).join("")}
                        </ol>
                        <div style="font-size:10.5px;font-weight:700;text-transform:uppercase;color:var(--text-2);margin-bottom:5px;">Expected Result</div>
                        <div>${escHtml(tc.expected_result)}</div>
                    </td>
                </tr>`;
        });

        html += `</tbody></table></div>`;

        // Raw LLM output tab
        const rawContent = gen.raw_response || JSON.stringify(gen.test_cases, null, 2);
        html += `
            <div class="tab-panel" id="panel-raw">
                <div class="raw-output-container">
                    <pre class="raw-output">${escHtml(rawContent)}</pre>
                </div>
            </div>`;

        tcBody.innerHTML = html;

        // ── Staleness Card ──────────────────────────────────────────────────
        if (gen.is_stale && gen.impacted_nodes?.length) {
            staleness.style.display = "block";
            const changed = gen.impacted_nodes.filter(n => n.status === "modified").length;
            const deleted = gen.impacted_nodes.filter(n => n.status === "deleted").length;
            const total   = gen.impacted_nodes.length;
            const unchanged = Math.max(0, total - changed - deleted);

            let changedRows = gen.impacted_nodes.map(n => {
                const bc    = n.status === "modified" ? "badge-orange" : "badge-red";
                const parts = n.path.split("/").filter(Boolean);
                const short = parts.slice(-2).join(" / ");
                return `
                    <div class="changed-section-row">
                        <span class="changed-section-label">• ${escHtml(short)}</span>
                        <span class="badge ${bc}">${n.status === "modified" ? "CHANGED" : "DELETED"}</span>
                    </div>`;
            }).join("");

            document.getElementById("staleness-body").innerHTML = `
                <div class="stale-banner">
                    <div class="stale-banner-title">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        ${changed + deleted} of ${total} sections have changed since this test set was generated.
                    </div>
                    <div class="stale-banner-subtitle">This test set may be <strong>STALE</strong>.</div>
                </div>

                <div style="font-size:11px;font-weight:700;margin-bottom:8px;">Impact Summary</div>
                <table class="meta-table" style="margin-bottom:14px;">
                    <tr><td>Total Sections in Selection</td><td>${total}</td></tr>
                    <tr><td>Changed Sections</td><td style="color:var(--orange);font-weight:700;">${changed}</td></tr>
                    <tr><td>Unchanged Sections</td><td style="color:var(--green);font-weight:700;">${unchanged}</td></tr>
                    <tr><td>Overall Status</td><td><span class="badge badge-red">STALE</span></td></tr>
                </table>

                <div style="font-size:11px;font-weight:700;margin-bottom:8px;">Changed Sections</div>
                <div>${changedRows}</div>

                <button class="btn btn-secondary btn-sm" style="margin-top:14px;width:100%;justify-content:center;" onclick="expandDiffs(${selId})">
                    View Detailed Diff →
                </button>
            `;
        } else {
            staleness.style.display = "none";
        }

    } catch (err) {
        tcBody.innerHTML = `<div style="color:var(--red);padding:16px;">${err.message}</div>`;
    }
}

function switchTcTab(which) {
    ["tc","raw"].forEach(id => {
        document.getElementById(`tab-${id}`)?.classList.toggle("active", id === which);
        document.getElementById(`panel-${id}`)?.classList.toggle("active", id === which);
    });
}

function toggleRow(id) {
    document.getElementById(id)?.classList.toggle("open");
}

// ─── Expand Diffs ─────────────────────────────────────────────────────────────
async function expandDiffs(selId) {
    try {
        const r = await fetch(`/api/selections/${selId}/test-cases`);
        if (!r.ok) return;
        const gen = await r.json();
        const body = document.getElementById("staleness-body");
        const existing = body.querySelector("#diff-detail-section");
        if (existing) { existing.remove(); return; } // toggle off

        let html = `<div id="diff-detail-section" style="margin-top:14px;">
            <div style="font-size:11px;font-weight:700;margin-bottom:8px;">Detailed Diffs</div>`;

        gen.impacted_nodes.forEach(n => {
            const parts = n.path.split("/").filter(Boolean);
            const short = parts.slice(-2).join(" / ");
            const bc    = n.status === "modified" ? "badge-orange" : "badge-red";
            html += `
                <div style="margin-bottom:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <strong style="font-size:12px;">${escHtml(short)}</strong>
                        <span class="badge ${bc}">${n.status.toUpperCase()}</span>
                    </div>
                    <div class="diff-view">${colorDiff(n.diff)}</div>
                </div>`;
        });

        html += `</div>`;
        body.insertAdjacentHTML("beforeend", html);
    } catch (err) { console.error(err); }
}

// ─── Generate Test Cases ──────────────────────────────────────────────────────
async function triggerTestGeneration() {
    if (!activeSelectionId) return;

    document.getElementById("test-cases-body").innerHTML = `
        <div style="text-align:center;padding:40px 20px;">
            <span class="spinner"></span>
            <div style="margin-top:12px;font-weight:600;">Contacting Gemini…</div>
            <div style="font-size:11px;color:var(--text-2);margin-top:4px;">Generating structured QA test cases. This may take ~10 seconds.</div>
        </div>`;

    try {
        const r = await fetch(`/api/selections/${activeSelectionId}/generate`, { method: "POST" });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Generation failed"); }
        await loadTestCases(activeSelectionId);
        await loadTotalGenerations();
    } catch (err) {
        alert("LLM Error: " + err.message);
        loadTestCases(activeSelectionId);
    }
}

// ─── Create Selection ─────────────────────────────────────────────────────────
async function submitCreateSelection() {
    const name = document.getElementById("new-selection-name").value.trim();
    if (!name) { alert("Please enter a selection name."); return; }

    const checked  = document.querySelectorAll(".tree-node-checkbox:checked");
    const nodeIds  = Array.from(checked).map(cb => parseInt(cb.value));

    try {
        const r = await fetch("/api/selections", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ name, node_ids: nodeIds })
        });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Failed to create"); }
        const sel = await r.json();
        closeCreateSelectionModal();
        document.querySelectorAll(".tree-node-checkbox").forEach(cb => cb.checked = false);
        selectedNodeIds.clear();
        await loadSelectionsList(sel.id);
    } catch (err) {
        alert("Error: " + err.message);
    }
}

// ─── Search ───────────────────────────────────────────────────────────────────
function handleSearch(query) {
    const term = query.toLowerCase().trim();

    if (!term) {
        document.querySelectorAll(".tree-node").forEach(n => n.style.display = "");
        return;
    }

    nodesMap.forEach(node => {
        const el = document.getElementById(`tc-${node.id}`);
        if (!el) return;
        const match = node.title.toLowerCase().includes(term) || (node.body_text || "").toLowerCase().includes(term);
        el.style.display = match ? "" : "none";

        if (match) {
            // Expand all ancestors
            let pid = node.parent_id;
            while (pid) {
                const pe = document.getElementById(`tc-${pid}`);
                const pk = document.getElementById(`tk-${pid}`);
                const pa = document.getElementById(`th-${pid}`)?.querySelector(".tree-node-arrow");
                if (pe) pe.style.display = "";
                if (pk) pk.classList.add("expanded");
                if (pa) pa.classList.add("expanded");
                pid = nodesMap.get(pid)?.parent_id || null;
            }
        }
    });
}
