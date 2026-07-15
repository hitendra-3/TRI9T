// State Management
let currentDocId = null;
let currentVerId = null;
let activeNodeId = null;
let activeSelectionId = null;
let selectedNodeIds = new Set();
let nodesMap = new Map(); // Store nodes by ID for quick access

// On Load
document.addEventListener("DOMContentLoaded", () => {
    // Check local storage for theme
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);
    
    // Load initial documents
    loadDocuments();
});

// Theme Toggle
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
}

// Ingestion Modal Controls
function openIngestModal() {
    document.getElementById("ingest-modal").style.display = "flex";
}

function closeIngestModal() {
    document.getElementById("ingest-modal").style.display = "none";
}

// Create Selection Modal Controls
function openCreateSelectionModal() {
    // Gather all checked checkboxes
    const checkedBoxes = document.querySelectorAll(".tree-node-checkbox:checked");
    if (checkedBoxes.length === 0) {
        alert("Please select at least one checkbox in the Document Structure tree first!");
        return;
    }
    document.getElementById("selection-modal").style.display = "flex";
}

function closeCreateSelectionModal() {
    document.getElementById("selection-modal").style.display = "none";
}

// Load Preset File from Backend
async function loadPresetFile(filename, verLabel) {
    try {
        const response = await fetch(`/api/documents/presets/${filename}`);
        if (!response.ok) throw new Error("Failed to load preset file");
        const data = await response.json();
        
        document.getElementById("ingest-ver-label").value = verLabel;
        document.getElementById("ingest-content").value = data.content;
    } catch (err) {
        alert("Error loading preset: " + err.message);
    }
}

// Handle custom file upload and read content
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById("ingest-content").value = e.target.result;
        
        // Auto-detect version label from filename (e.g. "ct200_manual_v2.md" -> "v2")
        const name = file.name.toLowerCase();
        const match = name.match(/_(v\d+)/) || name.match(/-(v\d+)/) || name.match(/^(v\d+)/);
        if (match) {
            document.getElementById("ingest-ver-label").value = match[1];
        }
    };
    reader.readAsText(file);
}

// Submit Ingestion to Backend
async function submitIngestion() {
    const docName = document.getElementById("ingest-doc-name").value.strip ? document.getElementById("ingest-doc-name").value.strip() : document.getElementById("ingest-doc-name").value;
    const verLabel = document.getElementById("ingest-ver-label").value.strip ? document.getElementById("ingest-ver-label").value.strip() : document.getElementById("ingest-ver-label").value;
    const content = document.getElementById("ingest-content").value;
    
    if (!docName || !verLabel || !content) {
        alert("Please fill in all fields before submitting!");
        return;
    }
    
    try {
        const response = await fetch("/api/documents/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                document_name: docName,
                version_label: verLabel,
                markdown_content: content
            })
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Ingestion failed");
        }
        
        const result = await response.json();
        alert(`Version ${verLabel} ingested successfully!\nTotal Nodes: ${result.stats.total_nodes}\nNew: ${result.stats.new_nodes}\nModified: ${result.stats.modified_nodes}\nDeleted: ${result.stats.deleted_nodes}`);
        
        closeIngestModal();
        
        // Reload documents and select the newly created version
        await loadDocuments(result.version.document_id, result.version.id);
        
    } catch (err) {
        alert("Ingestion Error: " + err.message);
    }
}

// Fetch and load documents
async function loadDocuments(selectDocId = null, selectVerId = null) {
    try {
        const response = await fetch("/api/documents");
        if (!response.ok) throw new Error("Failed to load documents");
        const docs = await response.json();
        
        const selector = document.getElementById("doc-selector");
        selector.innerHTML = "";
        
        if (docs.length === 0) {
            selector.innerHTML = '<option value="">-- No Documents --</option>';
            return;
        }
        
        docs.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = d.name;
            selector.appendChild(opt);
        });
        
        // Auto select first document or specified one
        const activeDoc = selectDocId || docs[0].id;
        selector.value = activeDoc;
        currentDocId = parseInt(activeDoc);
        
        await loadDocumentVersions(currentDocId, selectVerId);
        
    } catch (err) {
        console.error(err);
    }
}

// Fetch and load versions
async function loadDocumentVersions(docId, selectVerId = null) {
    if (!docId) return;
    currentDocId = parseInt(docId);
    
    try {
        const response = await fetch(`/api/documents/${docId}/versions`);
        if (!response.ok) throw new Error("Failed to load versions");
        const versions = await response.json();
        
        const selector = document.getElementById("ver-selector");
        selector.innerHTML = "";
        
        if (versions.length === 0) {
            selector.innerHTML = '<option value="">-- No Versions --</option>';
            return;
        }
        
        // Sort versions descending (newest first)
        versions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        
        versions.forEach((v, index) => {
            const opt = document.createElement("option");
            opt.value = v.id;
            opt.textContent = v.version_label + (index === 0 ? " (Latest)" : "");
            selector.appendChild(opt);
        });
        
        // Auto select first (newest) or specified version
        const activeVer = selectVerId || versions[0].id;
        selector.value = activeVer;
        currentVerId = parseInt(activeVer);
        
        await loadVersionDetails(currentVerId);
        
    } catch (err) {
        console.error(err);
    }
}

// Fetch all details for a version (nodes, stats, selections)
async function loadVersionDetails(verId) {
    if (!verId) return;
    currentVerId = parseInt(verId);
    
    try {
        // 1. Fetch nodes for building tree
        const nodesResponse = await fetch(`/api/nodes/browse?document_id=${currentDocId}&version_id=${currentVerId}`);
        if (!nodesResponse.ok) throw new Error("Failed to load nodes");
        const topNodes = await nodesResponse.json();
        
        // Fetch all nodes in the document version recursively to build a flat map
        // We will build a helper mapping for search and selections.
        // Actually, we can fetch all nodes of this version by getting child nodes as well.
        // Since get_node_by_id returns children, we will write a recursive loader to fetch all nodes
        // Or simply search for all nodes of this version. Wait, we can hit `/api/nodes/search?document_id=X&query=&version_id=Y` with empty query?
        // Wait, search route requires min_length=1. We can fetch top nodes, and then as user expands tree we load child nodes!
        // That is very clean and efficient (Lazy Loading).
        // Let's implement tree rendering.
        
        nodesMap.clear();
        const treeRoot = document.getElementById("tree-root");
        treeRoot.innerHTML = "";
        
        if (topNodes.length === 0) {
            treeRoot.innerHTML = '<div class="text-secondary" style="font-size: 13px; text-align: center; padding: 20px;">No sections in this version.</div>';
            return;
        }
        
        topNodes.forEach(node => {
            nodesMap.set(node.id, node);
            const element = createTreeNodeElement(node);
            treeRoot.appendChild(element);
        });
        
        // 2. Fetch statistics of this version
        // Let's call /api/versions/{id} to get meta
        const verResponse = await fetch(`/api/versions/${currentVerId}`);
        if (verResponse.ok) {
            const verData = await verResponse.json();
            document.getElementById("side-ver-label").textContent = verData.version_label;
            
            // To get total nodes count and statistics:
            // Since stats are calculated on ingestion and not stored in version database column directly,
            // we can fetch count of nodes belonging to this version label.
            // Let's run a query count.
            // Actually, we can fetch all nodes using search with a wildcard if permitted, or fetch and count.
            // Let's count them dynamically when browsing tree, or show a simple placeholder if not loaded.
            // Wait, we can get statistics by calling search with query " " (space) or a common vowel,
            // or we can count from the tree! Let's fetch all nodes to count them correctly.
            // Since the CardioTrack manual is small (around 48 nodes), let's write a small helper route or search.
            // Wait, search route uses simple SQL LIKE. If we search for "%", it returns all nodes!
            // Let's test this: `GET /api/nodes/search?document_id=1&query=%25` (url encoded %).
            // Let's do that to get all nodes!
            const allNodesResponse = await fetch(`/api/nodes/search?document_id=${currentDocId}&query=%25&version_id=${currentVerId}`);
            if (allNodesResponse.ok) {
                const allNodes = await allNodesResponse.json();
                document.getElementById("side-ver-nodes").textContent = allNodes.length;
                document.getElementById("stat-total-sections").textContent = allNodes.length;
                
                // Let's enrich nodesMap with all nodes
                allNodes.forEach(n => nodesMap.set(n.id, n));
                
                // Fetch stats dynamically from backend
                const statsResponse = await fetch(`/api/versions/${currentVerId}/stats`);
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    document.getElementById("stat-new-sections").textContent = stats.new_nodes;
                    document.getElementById("stat-modified-sections").textContent = stats.modified_nodes;
                } else {
                    document.getElementById("stat-new-sections").textContent = "0";
                    document.getElementById("stat-modified-sections").textContent = "0";
                }
                
                // We can query other versions. For simplicity, let's make a call to count selections
                loadSelectionsList();
            }
        }
        
    } catch (err) {
        console.error(err);
    }
}

// Create a collapsible tree node element
function createTreeNodeElement(node) {
    const container = document.createElement("div");
    container.className = "tree-node";
    container.id = `node-container-${node.id}`;
    
    const header = document.createElement("div");
    header.className = "tree-node-header";
    header.id = `node-header-${node.id}`;
    header.onclick = (e) => {
        // Prevent click if clicking checkbox
        if (e.target.tagName === "INPUT") return;
        selectNode(node.id);
    };
    
    // Collapsible Arrow (only if it has children conceptually, e.g., level < 4 or we know it has kids)
    const arrow = document.createElement("span");
    arrow.className = "tree-node-arrow";
    arrow.textContent = "▶";
    header.appendChild(arrow);
    
    // Checkbox for selections
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "tree-node-checkbox";
    cb.value = node.id;
    cb.onclick = (e) => {
        if (cb.checked) {
            selectedNodeIds.add(node.id);
        } else {
            selectedNodeIds.delete(node.id);
        }
    };
    header.appendChild(cb);
    
    // Icon
    const icon = document.createElement("span");
    icon.className = "tree-node-icon";
    icon.textContent = getIconForLevel(node.level);
    header.appendChild(icon);
    
    // Title
    const titleText = document.createElement("span");
    titleText.textContent = node.title;
    header.appendChild(titleText);
    
    container.appendChild(header);
    
    // Children container
    const childrenContainer = document.createElement("div");
    childrenContainer.className = "tree-node-children";
    childrenContainer.id = `node-children-${node.id}`;
    container.appendChild(childrenContainer);
    
    // Toggle expand/collapse
    arrow.onclick = async (e) => {
        e.stopPropagation();
        const isExpanded = childrenContainer.classList.contains("expanded");
        
        if (isExpanded) {
            childrenContainer.classList.remove("expanded");
            arrow.classList.remove("expanded");
        } else {
            childrenContainer.classList.add("expanded");
            arrow.classList.add("expanded");
            
            // Load children from backend if not already loaded
            if (childrenContainer.children.length === 0) {
                await loadChildren(node.id, childrenContainer);
            }
        }
    };
    
    return container;
}

function getIconForLevel(level) {
    switch (level) {
        case 1: return "📁";
        case 2: return "📖";
        case 3: return "📄";
        default: return "📝";
    }
}

async function loadChildren(nodeId, containerElement) {
    try {
        const response = await fetch(`/api/nodes/${nodeId}`);
        if (!response.ok) throw new Error("Failed to load node details");
        const nodeDetail = await response.json();
        
        if (nodeDetail.children.length === 0) {
            // No children, hide the arrow
            const header = document.getElementById(`node-header-${nodeId}`);
            if (header) {
                const arrow = header.querySelector(".tree-node-arrow");
                if (arrow) arrow.style.visibility = "hidden";
            }
            return;
        }
        
        nodeDetail.children.forEach(child => {
            nodesMap.set(child.id, child);
            const childElement = createTreeNodeElement(child);
            containerElement.appendChild(childElement);
        });
        
    } catch (err) {
        console.error(err);
    }
}

// Select a node and display details in center pane
async function selectNode(nodeId) {
    activeNodeId = nodeId;
    
    // Highlight active node in tree
    document.querySelectorAll(".tree-node-header").forEach(h => h.classList.remove("selected"));
    const activeHeader = document.getElementById(`node-header-${nodeId}`);
    if (activeHeader) activeHeader.classList.add("selected");
    
    const detailBody = document.getElementById("section-detail-body");
    detailBody.innerHTML = '<div style="text-align:center; padding: 20px;"><span class="loading-spinner"></span> Loading details...</div>';
    
    try {
        const response = await fetch(`/api/nodes/${nodeId}`);
        if (!response.ok) throw new Error("Failed to fetch node");
        const node = await response.json();
        
        // Fetch diff summary comparison
        const diffResponse = await fetch(`/api/nodes/${nodeId}/diff`);
        let diffBadge = "";
        let diffBlock = "";
        
        if (diffResponse.ok) {
            const diffData = await diffResponse.json();
            if (diffData.has_changed) {
                if (diffData.diff_type === "modified") {
                    diffBadge = '<span class="badge yellow">CHANGED</span>';
                    diffBlock = `
                        <div class="control-label" style="margin-top:16px; margin-bottom:8px;">Changes in Latest Version:</div>
                        <div class="diff-view">${formatDiffHtml(diffData.diff_text)}</div>
                    `;
                } else if (diffData.diff_type === "deleted") {
                    diffBadge = '<span class="badge red">DELETED IN LATEST</span>';
                }
            } else {
                diffBadge = '<span class="badge green">CURRENT</span>';
            }
        }
        
        detailBody.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <h2 style="font-size:18px; font-weight:700;">${node.heading}</h2>
                <div style="display:flex; gap:6px;">
                    <span class="badge blue">Level ${node.level}</span>
                    ${diffBadge}
                </div>
            </div>
            
            <div class="sidebar-version-stat" style="margin-bottom:12px; font-size:13px; color:var(--text-secondary);">
                <span>Path:</span>
                <strong>${node.path}</strong>
            </div>

            <div class="hash-container">
                <span style="font-family:monospace; word-break:break-all;">Hash: ${node.content_hash}</span>
                <button class="hash-btn" onclick="navigator.clipboard.writeText('${node.content_hash}'); alert('Hash copied to clipboard!')">Copy</button>
            </div>

            <div class="control-label" style="margin-bottom:8px;">Text Content:</div>
            <div class="section-text">${renderContentHtml(node.body_text)}</div>
            
            ${diffBlock}
            
            <table class="metadata-table">
                <tr>
                    <td>Logical Node ID</td>
                    <td style="font-family:monospace;">${node.logical_id}</td>
                </tr>
                <tr>
                    <td>Database Node ID</td>
                    <td>${node.id}</td>
                </tr>
                <tr>
                    <td>Parent Section Path</td>
                    <td>${node.path.substring(0, node.path.lastIndexOf("/")) || "None (Root)"}</td>
                </tr>
            </table>
        `;
        
    } catch (err) {
        detailBody.innerHTML = `<div class="alert alert-danger"><div class="alert-title">⚠️ Error</div>${err.message}</div>`;
    }
}

// Convert markdown tables and lists into formatted HTML
function renderContentHtml(text) {
    if (!text) return "<em>(No text content in this section)</em>";
    
    // Safely encode HTML tags
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    // Simple table parser
    const lines = html.split("\n");
    let inTable = false;
    let tableHeaders = [];
    let tableRows = [];
    let outputLines = [];
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        if (line.startsWith("|") && line.endsWith("|")) {
            inTable = true;
            // Split line by |
            const cells = line.split("|").map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
            
            // Check if it's separator line (e.g. |---|---|)
            if (cells.every(c => c.match(/^:-*-*:*$/) || c.match(/^-+$/))) {
                // Skip separator lines
                continue;
            }
            
            if (tableHeaders.length === 0) {
                tableHeaders = cells;
            } else {
                tableRows.push(cells);
            }
        } else {
            if (inTable) {
                // Build HTML Table
                let tableHtml = '<div style="overflow-x:auto; margin: 16px 0;"><table class="tc-table" style="font-size:12px;">';
                tableHtml += '<thead><tr>' + tableHeaders.map(h => `<th style="padding:8px 12px;">${h}</th>`).join("") + '</tr></thead>';
                tableHtml += '<tbody>' + tableRows.map(row => '<tr>' + row.map(cell => `<td style="padding:8px 12px; border-bottom:1px solid var(--border);">${cell}</td>`).join("") + '</tr>').join("") + '</tbody>';
                tableHtml += '</table></div>';
                
                outputLines.push(tableHtml);
                
                // Reset table variables
                inTable = false;
                tableHeaders = [];
                tableRows = [];
            }
            outputLines.push(line);
        }
    }
    
    // Add final table if document ends during table
    if (inTable) {
        let tableHtml = '<div style="overflow-x:auto; margin: 16px 0;"><table class="tc-table" style="font-size:12px;">';
        tableHtml += '<thead><tr>' + tableHeaders.map(h => `<th style="padding:8px 12px;">${h}</th>`).join("") + '</tr></thead>';
        tableHtml += '<tbody>' + tableRows.map(row => '<tr>' + row.map(cell => `<td style="padding:8px 12px; border-bottom:1px solid var(--border);">${cell}</td>`).join("") + '</tr>').join("") + '</tbody>';
        tableHtml += '</table></div>';
        outputLines.push(tableHtml);
    }
    
    return outputLines.join("\n");
}

// Colorize unified diff formatting
function formatDiffHtml(diffText) {
    if (!diffText) return "";
    
    return diffText.split("\n").map(line => {
        if (line.startsWith("+")) {
            return `<div class="diff-line-add">${line}</div>`;
        } else if (line.startsWith("-")) {
            return `<div class="diff-line-del">${line}</div>`;
        } else if (line.startsWith("@@")) {
            return `<div class="diff-line-info">${line}</div>`;
        }
        return `<div>${line}</div>`;
    }).join("");
}

// Fetch all selections for dropdown
async function loadSelectionsList(selectSelId = null) {
    try {
        // Query database selections
        // Since there is no list selections endpoint in our model, we can query selections from Selection model.
        // Wait, how do we query selections? We should create an endpoint in routes/selections.py to list all selections.
        // Wait! Let's check: did we add a `GET /api/selections` endpoint to list selections?
        // Ah! In `app/routes/selections.py`, we only added:
        // `POST /api/selections`
        // `GET /api/selections/{selection_id}`
        // Oh! We didn't add a list selections endpoint!
        // Wait, can we fetch selections from the database? Yes, let's write a `GET /api/selections` list endpoint in `app/routes/selections.py`!
        // That is extremely important so that the dropdown can be loaded! Let's make sure we add it.
        // Let's implement it. Wait, let's inspect if there is already a list selections endpoint. No, we only wrote create and read.
        // Let's first make a list selections endpoint in selections.py. I can do it easily using the replace tool.
        // Let's check: yes, we'll write `GET /api/selections` returning `List[SelectionResponse]`.
        
        // Let's fetch selections from `/api/selections`
        const response = await fetch("/api/selections");
        if (!response.ok) throw new Error("Failed to load selections");
        const selections = await response.json();
        
        const selector = document.getElementById("selection-selector");
        selector.innerHTML = '<option value="">-- Choose Selection --</option>';
        
        selections.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = s.name;
            selector.appendChild(opt);
        });
        
        document.getElementById("stat-total-selections").textContent = selections.length;
        
        if (selectSelId) {
            selector.value = selectSelId;
            loadSelectionDetails(selectSelId);
        }
        
    } catch (err) {
        console.error("Selections list error: " + err.message);
    }
}

// Load details of selection and check staleness
async function loadSelectionDetails(selectionId) {
    if (!selectionId) {
        document.getElementById("selection-details-pane").style.display = "none";
        document.getElementById("selection-empty-pane").style.display = "block";
        document.getElementById("staleness-card").style.display = "none";
        document.getElementById("btn-generate-tc").style.display = "none";
        document.getElementById("test-cases-body").innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 40px 20px;">Select or create a selection in the right-hand panel, then generate test cases.</div>';
        return;
    }
    
    activeSelectionId = parseInt(selectionId);
    
    document.getElementById("selection-details-pane").style.display = "block";
    document.getElementById("selection-empty-pane").style.display = "none";
    document.getElementById("btn-generate-tc").style.display = "inline-flex";
    
    try {
        // Fetch selection details
        const response = await fetch(`/api/selections/${selectionId}`);
        if (!response.ok) throw new Error("Failed to load selection");
        const selection = await response.json();
        
        // Display pinned version
        // We will need to query the version label from the version ID or from selection details
        // Selection schema currently lists selection nodes, name, version_id
        document.getElementById("sel-pinned-ver").textContent = `V${selection.version_id}`;
        document.getElementById("sel-created-on").textContent = new Date(selection.created_at).toLocaleString();
        
        // List selected nodes
        const nodesList = document.getElementById("sel-nodes-list");
        nodesList.innerHTML = "";
        
        selection.nodes.forEach(n => {
            const item = document.createElement("div");
            item.className = "selected-section-item";
            item.innerHTML = `
                <span>${n.path}</span>
            `;
            nodesList.appendChild(item);
        });
        
        // Load generated test cases and staleness
        loadTestCases(selectionId);
        
    } catch (err) {
        console.error(err);
    }
}

// Load test cases and display staleness cards
async function loadTestCases(selectionId) {
    const tcBody = document.getElementById("test-cases-body");
    const stalenessCard = document.getElementById("staleness-card");
    const stalenessBody = document.getElementById("staleness-body");
    
    tcBody.innerHTML = '<div style="text-align:center; padding: 20px;"><span class="loading-spinner"></span> Loading test cases...</div>';
    
    try {
        const response = await fetch(`/api/selections/${selectionId}/test-cases`);
        
        if (response.status === 404) {
            // Not generated yet
            tcBody.innerHTML = `
                <div style="text-align: center; color: var(--text-secondary); padding: 40px 20px;">
                    <div style="font-size:36px; margin-bottom:12px;">🤖</div>
                    No QA test cases have been generated for this selection yet.<br><br>
                    <button class="btn btn-primary" onclick="triggerTestGeneration()">⚡ Generate Test Cases Now</button>
                </div>
            `;
            stalenessCard.style.display = "none";
            return;
        }
        
        if (!response.ok) throw new Error("Failed to load test cases");
        const gen = await response.json();
        
        // Render test cases table
        let tableHtml = `
            <table class="tc-table">
                <thead>
                    <tr>
                        <th style="width:30px;">#</th>
                        <th style="width:200px;">Title & Priority</th>
                        <th>Steps</th>
                        <th>Expected Result</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        gen.test_cases.forEach((tc, idx) => {
            let priorityBadge = `<span class="badge ${tc.priority === 'High' ? 'red' : tc.priority === 'Medium' ? 'orange' : 'blue'}">${tc.priority}</span>`;
            tableHtml += `
                <tr>
                    <td>${idx + 1}</td>
                    <td>
                        <div style="font-weight:700; margin-bottom:4px;">${tc.title}</div>
                        ${priorityBadge}
                    </td>
                    <td>
                        <ol style="margin-left: 16px; font-size:12px;">
                            ${tc.steps.map(s => `<li>${s}</li>`).join("")}
                        </ol>
                    </td>
                    <td style="font-size:12px;">${tc.expected_result}</td>
                </tr>
            `;
        });
        
        tableHtml += '</tbody></table>';
        
        tcBody.innerHTML = tableHtml;
        
        // Show staleness if applicable
        if (gen.is_stale) {
            stalenessCard.style.display = "block";
            
            // Count changed/modified nodes
            const changedCount = gen.impacted_nodes.filter(n => n.status === "modified").length;
            const deletedCount = gen.impacted_nodes.filter(n => n.status === "deleted").length;
            
            let impactNodesHtml = "";
            gen.impacted_nodes.forEach(node => {
                const badgeColor = node.status === "modified" ? "yellow" : "red";
                impactNodesHtml += `
                    <div style="margin-top:12px; border-top:1px solid var(--border); padding-top:12px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:12px;">
                            <strong>${node.path}</strong>
                            <span class="badge ${badgeColor}">${node.status.toUpperCase()}</span>
                        </div>
                        <div class="diff-view">${formatDiffHtml(node.diff)}</div>
                    </div>
                `;
            });
            
            stalenessBody.innerHTML = `
                <div class="alert alert-danger" style="margin-bottom:12px;">
                    <div class="alert-title">⚠️ Test cases are STALE</div>
                    <div>Some sections in this selection have been modified or deleted in the latest manual version.</div>
                </div>
                
                <table class="metadata-table">
                    <tr>
                        <td>Total Sections</td>
                        <td>${gen.impacted_nodes.length + 1}</td>
                    </tr>
                    <tr>
                        <td>Modified Sections</td>
                        <td><span style="color:var(--warning); font-weight:700;">${changedCount}</span></td>
                    </tr>
                    <tr>
                        <td>Deleted Sections</td>
                        <td><span style="color:var(--error); font-weight:700;">${deletedCount}</span></td>
                    </tr>
                </table>
                
                <div class="control-label" style="margin-top:16px;">Impacted Section Diffs:</div>
                ${impactNodesHtml}
            `;
        } else {
            stalenessCard.style.display = "none";
        }
        
    } catch (err) {
        tcBody.innerHTML = `<div class="alert alert-danger"><div class="alert-title">⚠️ Error</div>${err.message}</div>`;
    }
}

// Trigger generation via Gemini
async function triggerTestGeneration() {
    if (!activeSelectionId) return;
    
    const tcBody = document.getElementById("test-cases-body");
    tcBody.innerHTML = `
        <div style="text-align:center; padding: 40px 20px;">
            <span class="loading-spinner"></span>
            <div style="margin-top:12px; font-weight:600;">Contacting Google Gemini 2.5 Flash...</div>
            <div style="font-size:12px; color:var(--text-secondary); margin-top:4px;">Generating structured QA test cases. This may take up to 10 seconds.</div>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/selections/${activeSelectionId}/generate`, {
            method: "POST"
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Generation failed");
        }
        
        alert("QA test cases generated successfully!");
        loadTestCases(activeSelectionId);
        
    } catch (err) {
        alert("LLM Generation Error: " + err.message);
        loadTestCases(activeSelectionId);
    }
}

// Submit Named Selection Creation
async function submitCreateSelection() {
    const name = document.getElementById("new-selection-name").value.trim();
    if (!name) {
        alert("Please enter a selection name!");
        return;
    }
    
    // Gather checked nodes from DOM checkboxes
    const checkedBoxes = document.querySelectorAll(".tree-node-checkbox:checked");
    const nodeIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));
    
    try {
        const response = await fetch("/api/selections", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: name,
                node_ids: nodeIds
            })
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to create selection");
        }
        
        const selection = await response.json();
        alert(`Selection "${name}" created successfully!`);
        
        closeCreateSelectionModal();
        
        // Clear all checkboxes
        document.querySelectorAll(".tree-node-checkbox").forEach(cb => cb.checked = false);
        selectedNodeIds.clear();
        
        // Reload selections dropdown and auto-select this new one
        await loadSelectionsList(selection.id);
        
    } catch (err) {
        alert("Selection Error: " + err.message);
    }
}

// Filter tree sections by query matching
function handleSearch(query) {
    const term = query.toLowerCase().trim();
    const treeRoot = document.getElementById("tree-root");
    
    if (!term) {
        // Show everything and collapse except top
        document.querySelectorAll(".tree-node").forEach(node => {
            node.style.display = "block";
        });
        return;
    }
    
    // Scan all items in the nodesMap
    nodesMap.forEach(node => {
        const header = document.getElementById(`node-header-${node.id}`);
        const container = document.getElementById(`node-container-${node.id}`);
        
        if (header && container) {
            const textMatch = node.title.toLowerCase().includes(term) || node.body_text.toLowerCase().includes(term);
            if (textMatch) {
                container.style.display = "block";
                // Show all parents
                let parentId = node.parent_id;
                while (parentId) {
                    const parentContainer = document.getElementById(`node-container-${parentId}`);
                    const parentChildren = document.getElementById(`node-children-${parentId}`);
                    const parentArrow = document.getElementById(`node-header-${parentId}`)?.querySelector(".tree-node-arrow");
                    
                    if (parentContainer) parentContainer.style.display = "block";
                    if (parentChildren) parentChildren.classList.add("expanded");
                    if (parentArrow) parentArrow.classList.add("expanded");
                    
                    const parentNode = nodesMap.get(parentId);
                    parentId = parentNode ? parentNode.parent_id : null;
                }
            } else {
                container.style.display = "none";
            }
        }
    });
}
