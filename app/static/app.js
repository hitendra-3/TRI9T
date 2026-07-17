// ─── State ───────────────────────────────────────────────────────────────────
let currentDocId     = null;
let currentVerId     = null;
let activeNodeId     = null;
let activeSelectionId = null;
let selectedNodeIds  = new Set();
let nodesMap         = new Map();
let ingestIsNewDoc   = true;
let pendingIngestPayload = null;

// ─── Custom UI Popups (Toast & Modal) ─────────────────────────────────────────
function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-bar"></div>
        <div class="toast-content">${message.replace(/\n/g, "<br>")}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add("removing");
        setTimeout(() => toast.remove(), 200);
    }, 4000);
}

function showConfirm(title, message, confirmLabel = "Confirm", isDanger = false) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.style.display = "flex";
        overlay.style.zIndex = "10000";

        const btnClass = isDanger ? "btn-danger" : "btn-primary";
        const titleColor = isDanger ? "var(--red)" : "var(--primary)";
        const icon = isDanger 
            ? `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`
            : `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;

        overlay.innerHTML = `
            <div class="modal" style="max-width: 380px; transform: scale(0.95); transition: transform 0.15s ease;">
                <div class="modal-header">
                    <div class="modal-title" style="color: ${titleColor}; display: flex; align-items: center; gap: 6px;">
                        ${icon}
                        <span>${title}</span>
                    </div>
                </div>
                <div class="modal-body" style="font-size: 12px; color: var(--text-2); line-height: 1.5; padding: 16px;">
                    ${message.replace(/\n/g, "<br>")}
                </div>
                <div class="modal-footer" style="padding: 10px 16px; background: var(--bg); display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--border);">
                    <button class="btn btn-secondary btn-sm" id="confirm-cancel-btn">Cancel</button>
                    <button class="btn btn-sm ${btnClass}" id="confirm-ok-btn">${confirmLabel}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        
        setTimeout(() => {
            overlay.querySelector(".modal").style.transform = "scale(1)";
        }, 10);

        overlay.querySelector("#confirm-cancel-btn").onclick = () => {
            overlay.remove();
            resolve(false);
        };

        overlay.querySelector("#confirm-ok-btn").onclick = () => {
            overlay.remove();
            resolve(true);
        };
    });
}

function showAlertModal(title, message) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.style.display = "flex";
        overlay.style.zIndex = "10000";

        overlay.innerHTML = `
            <div class="modal" style="max-width: 380px; transform: scale(0.95); transition: transform 0.15s ease;">
                <div class="modal-header">
                    <div class="modal-title" style="color: var(--primary); display: flex; align-items: center; gap: 6px;">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        <span>${title}</span>
                    </div>
                </div>
                <div class="modal-body" style="font-size: 12px; color: var(--text-2); line-height: 1.5; padding: 16px;">
                    ${message.replace(/\n/g, "<br>")}
                </div>
                <div class="modal-footer" style="padding: 10px 16px; background: var(--bg); display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--border);">
                    <button class="btn btn-primary btn-sm" id="alert-ok-btn">OK</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        setTimeout(() => {
            overlay.querySelector(".modal").style.transform = "scale(1)";
        }, 10);

        overlay.querySelector("#alert-ok-btn").onclick = () => {
            overlay.remove();
            resolve();
        };
    });
}

// ─── Clear DB ─────────────────────────────────────────────────────────────────
async function clearDatabase() {
    const confirmed = await showConfirm(
        "Wipe Database", 
        "This will permanently delete all documents, versions, selections, and generated test cases.\n\nThis action cannot be undone.",
        "Wipe All Data",
        true
    );
    if (!confirmed) return;


    const btn = document.getElementById("btn-clear-db");
    btn.disabled = true;
    btn.textContent = "Clearing…";

    try {
        const r = await fetch("/api/documents/admin/clear-db", { method: "DELETE" });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Clear failed"); }

        // Reset all state
        currentDocId = null;
        currentVerId = null;
        activeNodeId = null;
        activeSelectionId = null;
        selectedNodeIds.clear();
        nodesMap.clear();

        // Reset UI
        document.getElementById("doc-selector").innerHTML = "<option value=''>— No Documents —</option>";
        document.getElementById("ver-selector").innerHTML = "<option value=''>— No Versions —</option>";
        document.getElementById("tree-root").innerHTML    = '<div class="empty-state">No document ingested yet.<br>Use <strong>Upload Document</strong> to begin.</div>';
        document.getElementById("section-detail-body").innerHTML = '<div class="empty-state">Select a node in the Document Structure tree to view its content and metadata.</div>';
        document.getElementById("test-cases-body").innerHTML     = '<div class="empty-state" style="padding:32px 20px;">Select or create a selection in the right panel, then generate QA test cases.</div>';
        document.getElementById("selection-selector").innerHTML  = '<option value="">— Choose Selection —</option>';
        document.getElementById("selection-details-pane").style.display = "none";
        document.getElementById("selection-empty-pane").style.display  = "block";
        document.getElementById("staleness-card").style.display         = "none";
        document.getElementById("version-changes-card").style.display   = "none";
        document.getElementById("btn-generate-tc").style.display        = "none";

        // Reset stat counters
        ["stat-total-sections","stat-modified-sections","stat-new-sections","stat-total-selections","stat-total-generations"].forEach(id => setText(id, "0"));
        ["side-ver-label","side-ver-date"].forEach(id => setText(id, "—"));
        ["side-ver-nodes","side-ver-changed","side-ver-new"].forEach(id => setText(id, "0"));
        setText("ver-badge-tree", "V—");

    } catch (err) {
        showToast("Error: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg> Clear DB`;
    }
}


// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem("theme") || "dark";
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

// ─── Sidebar Toggle ───────────────────────────────────────────────────────────
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    sidebar.classList.toggle("collapsed");
}

// ─── Global Upload State ──────────────────────────────────────────────────────
let docFileBase64 = null;
let docFileType = null;
let verFileBase64 = null;
let verFileType = null;

// ─── Modals ───────────────────────────────────────────────────────────────────
function openUploadDocModal() {
    document.getElementById("upload-doc-modal").style.display = "flex";
    document.getElementById("upload-doc-name").value = "CardioTrack CT-200";
    document.getElementById("upload-doc-ver-label").value = "v1";
    document.getElementById("upload-doc-file").value = "";
    document.getElementById("upload-doc-content").value = "";
    document.getElementById("upload-doc-content").disabled = false;
    docFileBase64 = null;
    docFileType = null;
}
function closeUploadDocModal() {
    document.getElementById("upload-doc-modal").style.display = "none";
}

async function openUploadVersionModal() {
    document.getElementById("upload-version-modal").style.display = "flex";
    document.getElementById("upload-ver-label").value = "";
    document.getElementById("upload-ver-file").value = "";
    document.getElementById("upload-ver-content").value = "";
    document.getElementById("upload-ver-content").disabled = false;
    verFileBase64 = null;
    verFileType = null;
    await populateUploadVerDocSelect();
}
function closeUploadVersionModal() {
    document.getElementById("upload-version-modal").style.display = "none";
    cancelIngestMismatch();
}

function openCreateSelectionModal() {
    if (!document.querySelectorAll(".tree-node-checkbox:checked").length) {
        showToast("Please check at least one section in the Document Structure tree first.", "warning");
        return;
    }
    document.getElementById("selection-modal").style.display = "flex";
}
function closeCreateSelectionModal() { document.getElementById("selection-modal").style.display = "none"; }

// ─── Populators & File Handlers ────────────────────────────────────────────────
async function populateUploadVerDocSelect() {
    try {
        const r = await fetch("/api/documents");
        if (!r.ok) return;
        const docs = await r.json();
        const select = document.getElementById("upload-ver-doc-select");
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
        
        if (currentDocId) {
            select.value = currentDocId;
            await suggestNextVersionLabel(currentDocId);
        }
        
        select.onchange = async () => {
            if (select.value) {
                await suggestNextVersionLabel(parseInt(select.value));
            }
        };
    } catch (err) {
        console.error(err);
    }
}

async function suggestNextVersionLabel(docId) {
    try {
        const r = await fetch(`/api/documents/${docId}/versions`);
        if (!r.ok) return;
        const versions = await r.json();
        const input = document.getElementById("upload-ver-label");
        if (!input) return;
        
        if (versions.length === 0) {
            input.value = "v1";
            return;
        }
        
        versions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        const latest = versions[0].version_label;
        const match = latest.match(/v(\d+)/i);
        if (match) {
            const nextNum = parseInt(match[1]) + 1;
            input.value = `v${nextNum}`;
        } else {
            input.value = latest + "_new";
        }
    } catch (err) {
        console.error(err);
    }
}

function handleDocFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    const dropLabel = document.getElementById("upload-doc-file-name");
    if (dropLabel) dropLabel.textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";
    if (isPdf) {
        docFileType = "pdf";
        const reader = new FileReader();
        reader.onload = e => {
            docFileBase64 = e.target.result.split(",")[1];
            document.getElementById("upload-doc-content").value = `[PDF loaded: ${file.name}]`;
            document.getElementById("upload-doc-content").disabled = true;
        };
        reader.readAsDataURL(file);
    } else {
        docFileType = "md";
        docFileBase64 = null;
        const reader = new FileReader();
        reader.onload = e => {
            document.getElementById("upload-doc-content").value = e.target.result;
            document.getElementById("upload-doc-content").disabled = false;
        };
        reader.readAsText(file, "UTF-8");
    }
}

function handleVerFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    const m = file.name.toLowerCase().match(/_(v\d+)/) || file.name.toLowerCase().match(/-(v\d+)/);
    if (m) document.getElementById("upload-ver-label").value = m[1];
    const dropLabel = document.getElementById("upload-ver-file-name");
    if (dropLabel) dropLabel.textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";

    if (isPdf) {
        verFileType = "pdf";
        const reader = new FileReader();
        reader.onload = e => {
            verFileBase64 = e.target.result.split(",")[1];
            document.getElementById("upload-ver-content").value = `[PDF loaded: ${file.name}]`;
            document.getElementById("upload-ver-content").disabled = true;
        };
        reader.readAsDataURL(file);
    } else {
        verFileType = "md";
        verFileBase64 = null;
        const reader = new FileReader();
        reader.onload = e => {
            document.getElementById("upload-ver-content").value = e.target.result;
            document.getElementById("upload-ver-content").disabled = false;
        };
        reader.readAsText(file, "UTF-8");
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
    await executeIngestion(pendingIngestPayload, "version");
}

// ─── Submissions ─────────────────────────────────────────────────────────────
async function submitUploadDoc() {
    const docName = document.getElementById("upload-doc-name").value.trim();
    const verLabel = document.getElementById("upload-doc-ver-label").value.trim();
    const content = document.getElementById("upload-doc-content").value;
    
    if (!docName || !verLabel || (!content && !docFileBase64)) {
        showToast("Please fill in all fields.", "warning");
        return;
    }
    
    const payload = {
        document_name: docName,
        version_label: verLabel,
        markdown_content: docFileType === "pdf" ? null : content,
        file_base64: docFileBase64,
        file_type: docFileType,
        force: false,
        is_new_document: true,
        document_id: null
    };
    
    await executeIngestion(payload, "doc");
}

async function submitUploadVersion() {
    const select = document.getElementById("upload-ver-doc-select");
    if (!select || !select.value) {
        showToast("Please select a target document.", "warning");
        return;
    }
    
    const docId = parseInt(select.value);
    const docName = select.options[select.selectedIndex].textContent;
    const verLabel = document.getElementById("upload-ver-label").value.trim();
    const content = document.getElementById("upload-ver-content").value;
    
    if (!verLabel || (!content && !verFileBase64)) {
        showToast("Please fill in all fields.", "warning");
        return;
    }
    
    const payload = {
        document_name: docName,
        version_label: verLabel,
        markdown_content: verFileType === "pdf" ? null : content,
        file_base64: verFileBase64,
        file_type: verFileType,
        force: false,
        is_new_document: false,
        document_id: docId
    };
    
    await executeIngestion(payload, "version");
}

async function executeIngestion(payload, modalType) {
    const activeModal = modalType === "doc" 
        ? document.getElementById("upload-doc-modal") 
        : document.getElementById("upload-version-modal");
    
    const modalContent = activeModal.querySelector(".modal");
    let loadingOverlay = null;
    
    if (modalContent) {
        modalContent.style.position = "relative";
        loadingOverlay = document.createElement("div");
        loadingOverlay.className = "ingest-loading-overlay";
        loadingOverlay.style.position = "absolute";
        loadingOverlay.style.top = "0";
        loadingOverlay.style.left = "0";
        loadingOverlay.style.width = "100%";
        loadingOverlay.style.height = "100%";
        loadingOverlay.style.background = "rgba(0, 0, 0, 0.75)";
        loadingOverlay.style.display = "flex";
        loadingOverlay.style.flexDirection = "column";
        loadingOverlay.style.alignItems = "center";
        loadingOverlay.style.justifyContent = "center";
        loadingOverlay.style.zIndex = "1000";
        loadingOverlay.style.borderRadius = "8px";
        loadingOverlay.innerHTML = `
            <span class="spinner" style="margin-bottom:12px; width:32px; height:32px; border-width:4px;"></span>
            <div style="color:#ffffff; font-size:13px; font-weight:600;">Ingesting & parsing document...</div>
            <div style="color:#94a3b8; font-size:11px; margin-top:4px;">Please wait while the PDF/Markdown is processed</div>
        `;
        modalContent.appendChild(loadingOverlay);
    }

    try {
        const r = await fetch("/api/documents/ingest", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(payload)
        });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Ingest failed"); }

        const result = await r.json();
        
        if (result.status === "warning") {
            if (loadingOverlay) loadingOverlay.remove();
            pendingIngestPayload = payload;
            document.getElementById("mismatch-percent-lbl").textContent = `${result.mismatch_percent}%`;
            document.getElementById("confirm-mismatch-modal").style.display = "flex";
            return;
        }
        
        showToast(`✓ "${payload.version_label}" ingested.\nTotal: ${result.stats.total_nodes} | New: ${result.stats.new_nodes} | Modified: ${result.stats.modified_nodes}`, "success");
        
        if (modalType === "doc") {
            closeUploadDocModal();
        } else {
            closeUploadVersionModal();
        }
        
        await loadDocuments(result.version.document_id, result.version.id);
    } catch (err) {
        showToast("Ingest Error: " + err.message, "error");
    } finally {
        if (loadingOverlay && loadingOverlay.parentNode) {
            loadingOverlay.remove();
        }
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
        // 1. Fetch all nodes for this version using the wildcard search
        const ar = await fetch(`/api/nodes/search?document_id=${currentDocId}&query=%25&version_id=${currentVerId}`);
        if (!ar.ok) throw new Error("Failed to load nodes");
        const allNodes = await ar.json();

        // 2. Populate nodesMap
        nodesMap.clear();
        allNodes.forEach(n => nodesMap.set(n.id, n));

        // 3. Build hierarchical tree in memory and append recursively
        const treeRoot = document.getElementById("tree-root");
        treeRoot.innerHTML = "";

        const roots = buildTreeFromFlatList(allNodes);

        if (!roots.length) {
            treeRoot.innerHTML = '<div class="empty-state">No sections found in this version.</div>';
        } else {
            roots.forEach(n => {
                treeRoot.appendChild(createTreeNodeRecursive(n));
            });
        }

        // 4. Version metadata for sidebar
        const vr = await fetch(`/api/versions/${currentVerId}`);
        if (vr.ok) {
            const vd = await vr.json();
            document.getElementById("side-ver-label").textContent = vd.version_label;
            document.getElementById("side-ver-date").textContent   = new Date(vd.created_at).toLocaleDateString();
            const badge = document.getElementById("ver-badge-tree");
            if (badge) badge.textContent = vd.version_label;
        }

        // 5. Update counts
        setText("side-ver-nodes",       allNodes.length);
        setText("stat-total-sections",  allNodes.length);

        // 6. Dynamic stats
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

        // 7. Selections
        await loadSelectionsList();

        // 8. Total generations count
        await loadTotalGenerations();

        // 9. Version diff panel
        await loadVersionDiff(currentVerId);

    } catch (err) { console.error(err); }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ─── Version Diff Panel ───────────────────────────────────────────────────────
async function loadVersionDiff(verId) {
    const card   = document.getElementById("version-changes-card");
    const body   = document.getElementById("version-changes-body");
    const badge  = document.getElementById("version-changes-badge");
    if (!card || !body) return;

    try {
        const r = await fetch(`/api/versions/${verId}/diff`);
        if (!r.ok) { card.style.display = "none"; return; }
        const data = await r.json();

        // Always show the card
        card.style.display = "block";

        const { summary, changes, is_first_version, prev_version_label, version_label } = data;
        const totalChanged = summary.modified + summary.deleted + summary.new;

        // Update badge
        if (totalChanged > 0 && !is_first_version) {
            badge.style.display = "inline-block";
            badge.textContent = `${totalChanged} change${totalChanged !== 1 ? 's' : ''}`;
        } else {
            badge.style.display = "none";
        }

        if (is_first_version) {
            body.innerHTML = `
                <div class="vc-first-version">
                    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <div style="font-size:12px;font-weight:600;margin-top:8px;">Initial Version</div>
                    <div style="font-size:11px;color:var(--text-2);margin-top:4px;">This is the first version — ${summary.total} sections ingested.</div>
                </div>`;
            return;
        }

        // Summary pills row
        let html = `
            <div class="vc-compare-bar">
                Comparing <strong>${escHtml(prev_version_label)}</strong> → <strong>${escHtml(version_label)}</strong>
            </div>
            <div class="vc-summary-pills">
                <span class="vc-pill vc-pill-modified">${summary.modified} Modified</span>
                <span class="vc-pill vc-pill-deleted">${summary.deleted} Deleted</span>
                <span class="vc-pill vc-pill-new">${summary.new} New</span>
                <span class="vc-pill vc-pill-unchanged">${summary.unchanged} Unchanged</span>
            </div>`;

        if (totalChanged === 0) {
            html += `<div class="vc-no-changes">✓ No sections changed between these versions.</div>`;
        } else {
            // Only render changed rows (skip unchanged)
            const changedItems = changes.filter(c => c.status !== "unchanged");
            html += `<div class="vc-change-list">`;
            changedItems.forEach((item, idx) => {
                const statusClass = `vc-status-${item.status}`;
                const statusLabel = item.status.charAt(0).toUpperCase() + item.status.slice(1);
                const badgeClass  = item.status === "modified" ? "badge-orange"
                                  : item.status === "deleted"  ? "badge-red"
                                  : "badge-green";
                const hasDiff = item.diff_text && item.diff_text.trim().length > 0;
                const indent  = Math.max(0, (item.level || 1) - 1) * 12;
                html += `
                    <div class="vc-change-row ${statusClass}" style="padding-left:${indent}px;">
                        <div class="vc-change-header" onclick="toggleVcRow('vc-diff-${idx}')">
                            <span class="vc-change-heading" title="${escHtml(item.path)}">${escHtml(item.heading)}</span>
                            <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                                <span class="badge ${badgeClass}">${statusLabel}</span>
                                ${hasDiff ? '<span class="vc-expand-icon">▾</span>' : ''}
                            </div>
                        </div>
                        ${hasDiff ? `<div class="vc-diff-panel" id="vc-diff-${idx}"><div class="diff-view">${colorDiff(item.diff_text)}</div></div>` : ''}
                    </div>`;
            });
            html += `</div>`;
        }

        body.innerHTML = html;
    } catch (err) {
        console.error("loadVersionDiff error:", err);
        const card = document.getElementById("version-changes-card");
        if (card) card.style.display = "none";
    }
}

function toggleVcRow(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("open");
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

// ─── Tree Node Builder (Recursive) ────────────────────────────────────────────
function buildTreeFromFlatList(nodes) {
    const map = {};
    const roots = [];
    
    // Sort all nodes by ID first to preserve natural document structure ordering
    const sorted = [...nodes].sort((a, b) => a.id - b.id);
    
    sorted.forEach(n => {
        map[n.id] = { ...n, children: [] };
    });
    
    sorted.forEach(n => {
        const mapped = map[n.id];
        if (n.parent_id && map[n.parent_id]) {
            map[n.parent_id].children.push(mapped);
        } else {
            roots.push(mapped);
        }
    });
    
    return roots;
}

function createTreeNodeRecursive(node) {
    const hasChildren = node.children && node.children.length > 0;
    const level = node.level || 1;

    const wrap = document.createElement("div");
    wrap.id = `tc-${node.id}`;

    // Row
    const row = document.createElement("div");
    row.className = `tree-node tree-level-${level}`;
    row.id = `th-${node.id}`;

    // Indent guide — each level adds a connector line
    for (let i = 1; i < level; i++) {
        const guide = document.createElement("span");
        guide.className = "tree-indent";
        row.appendChild(guide);
    }

    // Toggle arrow
    const arrow = document.createElement("span");
    arrow.className = "tree-toggle";
    if (hasChildren) {
        arrow.innerHTML = `<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>`;
    } else {
        arrow.innerHTML = `<svg viewBox="0 0 24 24" width="6" height="6" fill="none" stroke="currentColor" stroke-width="2" opacity="0.3"><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>`;
    }

    // Checkbox
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.className = "tree-check tree-node-checkbox"; cb.value = node.id;
    cb.onclick = e => {
        e.stopPropagation();
        node.id && (cb.checked ? selectedNodeIds.add(node.id) : selectedNodeIds.delete(node.id));
    };

    // Label
    const label = document.createElement("span");
    label.className = "tree-label";
    label.textContent = node.title;
    label.title = node.title;
    label.onclick = () => selectNode(node.id);

    row.append(arrow, cb, label);
    wrap.appendChild(row);

    // Children
    if (hasChildren) {
        const kids = document.createElement("div");
        kids.className = "tree-children collapsed";
        kids.id = `tk-${node.id}`;

        node.children.sort((a, b) => a.id - b.id);
        node.children.forEach(c => kids.appendChild(createTreeNodeRecursive(c)));
        wrap.appendChild(kids);

        arrow.onclick = e => {
            e.stopPropagation();
            const isCollapsed = kids.classList.contains("collapsed");
            if (isCollapsed) {
                kids.classList.remove("collapsed");
                arrow.classList.add("open");
            } else {
                kids.classList.add("collapsed");
                arrow.classList.remove("open");
            }
        };
    }

    return wrap;
}

// ─── Select Node ──────────────────────────────────────────────────────────────
async function selectNode(nodeId) {
    activeNodeId = nodeId;
    document.querySelectorAll(".tree-node").forEach(h => h.classList.remove("selected"));
    const hdr = document.getElementById(`th-${nodeId}`);
    if (hdr) hdr.classList.add("selected");

    const body = document.getElementById("section-detail-body");
    body.innerHTML = `<div class="empty-state"><span class="spinner"></span></div>`;

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
                    diffBlock = `<div class="diff-block">
                        <div class="diff-block-label">Changes vs Latest Version</div>
                        <div class="diff-view">${colorDiff(dd.diff_text)}</div>
                    </div>`;
                } else if (dd.diff_type === "deleted") {
                    diffBadge = `<span class="badge badge-red">DELETED IN LATEST</span>`;
                }
            } else {
                diffBadge = `<span class="badge badge-green">CURRENT</span>`;
            }
        }

        const levelLabels = ["","H1","H2","H3","H4","H5"];
        const levelBadge = ["badge-blue","badge-blue","badge-green","badge-orange","badge-yellow","badge-yellow"][node.level] || "badge-blue";
        const parentPath = node.path.substring(0, node.path.lastIndexOf("/")) || "Root";

        body.innerHTML = `
            <div class="detail-top">
                <div class="detail-heading">${escHtml(node.heading)}</div>
                <button class="btn-view-changes" onclick="scrollToDiff()">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
                    View Changes
                </button>
            </div>

            <div class="meta-badges">
                <span class="badge ${levelBadge}">${levelLabels[node.level] || "H" + node.level}</span>
                <span class="badge badge-dim">ID ${node.id}</span>
                <span class="badge badge-dim">v${currentVerId}</span>
                ${diffBadge}
            </div>

            <table class="meta-table">
                <tr><td>Parent</td><td>${escHtml(parentPath)}</td></tr>
                <tr><td>Content Hash</td><td>
                    <span class="mono-sm">${node.content_hash.substring(0,16)}&hellip;</span>
                    <button class="hash-btn" onclick="copy('${node.content_hash}','Hash')">Copy</button>
                </td></tr>
                <tr><td>Logical ID</td><td class="mono-sm">${node.logical_id.substring(0,24)}&hellip;</td></tr>
            </table>

            <div class="section-content-label">Content</div>
            <div class="section-body">${renderMarkdown(node.body_text)}</div>

            <div id="diff-anchor">${diffBlock}</div>
        `;
    } catch (err) {
        body.innerHTML = `<div class="error-state">${err.message}</div>`;
    }
}

function scrollToDiff() {
    const el = document.getElementById("diff-anchor");
    if (el) el.scrollIntoView({ behavior: "smooth" });
}

function copy(text, label) {
    navigator.clipboard.writeText(text).then(() => showToast(`${label} copied!`, "success"));
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
                <div class="empty-state tc-empty">
                    <div class="tc-empty-icon">
                        <svg viewBox="0 0 48 48" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.5">
                            <rect x="8" y="6" width="32" height="36" rx="3" stroke-opacity="0.2"/>
                            <line x1="14" y1="14" x2="34" y2="14" stroke-opacity="0.2"/>
                            <line x1="14" y1="20" x2="34" y2="20" stroke-opacity="0.2"/>
                            <line x1="14" y1="26" x2="28" y2="26" stroke-opacity="0.2"/>
                            <line x1="14" y1="32" x2="22" y2="32" stroke-opacity="0.2"/>
                        </svg>
                    </div>
                    <p>No test cases generated yet.</p>
                    <button class="btn-gen" onclick="triggerTestGeneration()">
                        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                        Generate
                    </button>
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
            const statusClass = gen.is_stale ? "badge-red" : "badge-green";
            const statusText = gen.is_stale ? "Stale" : "Valid";
            html += `
                <tr class="tc-row" onclick="toggleRow('tr-detail-${i}')">
                    <td>${i+1}</td>
                    <td style="font-weight:600;">${escHtml(tc.title)}</td>
                    <td><span class="badge ${pc}">${escHtml(tc.priority)}</span></td>
                    <td><span class="badge ${statusClass}">${statusText}</span></td>
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
                const label = n.heading || (n.path.split("/").filter(Boolean).slice(-2).join(" / "));
                return `
                    <div class="changed-section-row">
                        <span class="changed-section-label" title="${escHtml(n.path)}">• ${escHtml(label)}</span>
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
            staleness.style.display = "block";
            const selNodeCount = document.getElementById("sel-node-count")?.textContent || "0";
            
            document.getElementById("staleness-body").innerHTML = `
                <div class="stale-banner" style="background:#ecfdf5; border-color:#a7f3d0; color:#065f46;">
                    <div class="stale-banner-title" style="color:#059669; font-weight:600; display:flex; align-items:center; gap:6px;">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        Test cases are UP TO DATE.
                    </div>
                    <div class="stale-banner-subtitle" style="color:#065f46; font-size:11px; padding-left:20px; font-weight:500;">All selected sections match the active manual version.</div>
                </div>

                <div style="font-size:11px;font-weight:700;margin-bottom:8px;">Impact Summary</div>
                <table class="meta-table">
                    <tr><td>Total Sections in Selection</td><td>${selNodeCount}</td></tr>
                    <tr><td>Changed Sections</td><td style="color:var(--orange);font-weight:700;">0</td></tr>
                    <tr><td>Unchanged Sections</td><td style="color:var(--green);font-weight:700;">${selNodeCount}</td></tr>
                    <tr><td>Overall Status</td><td><span class="badge badge-green">CURRENT</span></td></tr>
                </table>
            `;
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
        <div class="empty-state">
            <span class="spinner"></span>
            <p style="margin-top:12px;font-weight:500;">Contacting Gemini&hellip;</p>
            <p class="hint-text">Generating structured QA test cases. This may take ~10 seconds.</p>
        </div>`;

    try {
        const r = await fetch(`/api/selections/${activeSelectionId}/generate`, { method: "POST" });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Generation failed"); }
        await loadTestCases(activeSelectionId);
        await loadTotalGenerations();
    } catch (err) {
        showToast("LLM Error: " + err.message, "error");
        loadTestCases(activeSelectionId);
    }
}

// ─── Create Selection ─────────────────────────────────────────────────────────
async function submitCreateSelection() {
    const name = document.getElementById("new-selection-name").value.trim();
    if (!name) { showToast("Please enter a selection name.", "warning"); return; }

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
        showToast("Error: " + err.message, "error");
    }
}

// ─── Search ───────────────────────────────────────────────────────────────────
function handleSearch(query) {
    const term = query.toLowerCase().trim();

    if (!term) {
        document.querySelectorAll("#tree-root > div").forEach(n => n.style.display = "");
        return;
    }

    nodesMap.forEach(node => {
        const el = document.getElementById(`tc-${node.id}`);
        if (!el) return;
        const match = node.title.toLowerCase().includes(term) || (node.body_text || "").toLowerCase().includes(term);
        el.style.display = match ? "" : "none";

        if (match) {
            let pid = node.parent_id;
            while (pid) {
                const pe = document.getElementById(`tc-${pid}`);
                const pk = document.getElementById(`tk-${pid}`);
                const arrow = document.getElementById(`th-${pid}`)?.querySelector(".tree-toggle");
                if (pe) pe.style.display = "";
                if (pk) {
                    pk.classList.remove("collapsed");
                    if (arrow) arrow.classList.add("open");
                }
                pid = nodesMap.get(pid)?.parent_id || null;
            }
        }
    });
}

// ─── Drag & Drop Support ──────────────────────────────────────────────────────
function initDragAndDrop() {
    // Prevent default drag behaviors for window
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        window.addEventListener(eventName, e => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });

    const setupZone = (zone, input, fileHandler) => {
        if (!zone || !input) return;

        ['dragenter', 'dragover'].forEach(eventName => {
            zone.addEventListener(eventName, e => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.add('highlight');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, e => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.remove('highlight');
            }, false);
        });

        zone.addEventListener('drop', e => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length) {
                input.files = files;
                fileHandler(input);
            }
        }, false);
    };

    // Document Modal drop zone
    const docModal = document.getElementById("upload-doc-modal");
    if (docModal) {
        const zone = docModal.querySelector(".file-drop-zone");
        const input = document.getElementById("upload-doc-file");
        setupZone(zone, input, handleDocFileUpload);
    }

    // Version Modal drop zone
    const verModal = document.getElementById("upload-version-modal");
    if (verModal) {
        const zone = verModal.querySelector(".file-drop-zone");
        const input = document.getElementById("upload-ver-file");
        setupZone(zone, input, handleVerFileUpload);
    }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    loadDocuments();
    initDragAndDrop();
});

