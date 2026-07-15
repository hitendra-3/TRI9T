# Approach Document - Tri9T AI Internship Assignment

This document outlines the design decisions, data models, parsing algorithms, versioning strategy, and LLM retry policies used to implement the CardioTrack CT-200 Home Blood Pressure Monitor manual management system.

---

## 1. Data Model & Storage

We use a single **SQLite** database containing all relational tables and a `JSON` column for storing generated test case outputs. 
- **Reasoning**: A single SQLite file provides transactional consistency (ACID) across document updates, node creation, selection building, and test generation. Using SQLite's built-in `JSON` column type (via SQLAlchemy's `JSON`) fulfills the "well-justified JSON store" requirement without introducing the operational overhead of a separate MongoDB process.

### Tables

1. **`documents`**: Represents the document itself.
   - `id` (int, PK)
   - `name` (str, unique)
   - `created_at` (datetime)
2. **`document_versions`**: Records individual document versions (e.g. `v1`, `v2`).
   - `id` (int, PK)
   - `document_id` (int, FK)
   - `version_label` (str, e.g. "v1")
   - `created_at` (datetime)
3. **`nodes`**: Stores parsed hierarchical sections of a specific document version.
   - `id` (int, PK)
   - `document_id` (int, FK)
   - `version_id` (int, FK)
   - `logical_id` (str, indexed) - A stable UUID shared by a section across versions.
   - `heading` (str) - Raw heading (e.g. `### 1.1 Intended Use`).
   - `title` (str) - Extracted title text.
   - `level` (int) - Heading level (1 to 6).
   - `body_text` (text) - Plain text and tables between headings.
   - `content_hash` (str) - SHA-256 hash of level + heading + body_text.
   - `parent_id` (int, FK, self-referential) - Hierarchical parent inside the same version.
   - `path` (str) - Hierarchical string path (e.g., `/CardioTrack.../4. Alarms/4.2 Error Codes`).
4. **`selections`**: Named sets of nodes pinned to a specific document version.
   - `id` (int, PK)
   - `name` (str)
   - `version_id` (int, FK)
   - `created_at` (datetime)
5. **`selection_nodes`**: Association table linking selections to nodes.
   - `selection_id` (int, FK, PK)
   - `node_id` (int, FK, PK)
6. **`generated_test_cases`**: Stores QA test cases generated from a selection.
   - `id` (int, PK)
   - `selection_id` (int, FK) - Links to the selection (and thus the version-pinned nodes).
   - `prompt` (text)
   - `raw_response` (text)
   - `test_cases` (JSON) - A list of generated test case dictionaries.
   - `created_at` (datetime)

---

## 2. Tree-Parsing Decisions & Irregularity Handling

Our custom parser (`app/parser.py`) uses a stack-based algorithm. It processes the markdown line-by-line:
- **Heading Identification**: It uses the regex `^(#{1,6})\s+(.+)$` to identify headers, extracting the level and heading title.
- **Parent Stack**: We maintain a stack of active parent nodes. When a heading of level $L$ is encountered, we pop all stack items of level $\ge L$. The remaining top element of the stack becomes the parent. The new node is then pushed.

### Handling Specific Document Irregularities
1. **Level-skipping (`#### 2.1.1.1` under `### 2.1`)**: Handled correctly. The stack stores the L3 parent, pushes the L4 child on top, and sets the L3 parent path.
2. **Out-of-order sibling numbering (`#### 3.2` then `### 3.4` then `### 3.3`)**: Handled correctly. Since the levels are $4 \rightarrow 3 \rightarrow 3$:
   - When processing `### 3.4`, the stack pops the L4 node (`3.2`), and the active parent shifts back to the nearest preceding L2 node (`3. Device Operation`).
   - When `### 3.3` is hit, it pops `3.4` and matches the same L2 parent. This maintains structural order and correctly positions `3.3` and `3.4` as siblings.
3. **Duplicate Headings (`4.2 Error Codes` and `7.1 Error Codes`)**: 
   - Because we generate a hierarchical path for each node (e.g. `/CardioTrack.../4. Alarms/4.2 Error Codes` and `/CardioTrack.../7. Troubleshooting/7.1 Error Codes`), they represent two distinct paths.
   - For duplicate headings under the *same parent* (not present in the manual but possible), we track path counts inside `app/parser.py` and append a `#count` suffix (e.g., `Error Codes #2`), ensuring path uniqueness.

---

## 3. Version-Matching Strategy & Known Failure Modes

### Strategy
We use **Path-based Version Matching** (`app/versioning.py`).
- During ingestion of $V_n$, we compare the unique path of each node to the nodes of the previous version $V_{n-1}$.
- If the path matches exactly:
  - We assign the same `logical_id` to the $V_n$ node.
  - We compute the content hash. If the hash differs, we flag the node as modified and generate a unified diff between the old and new text.
- If the path does not match:
  - It is classified as **New** and receives a new `logical_id`.
- Any node path that existed in $V_{n-1}$ but is missing in $V_n$ is classified as **Deleted**.

### Why Path-Based?
In regulated medical device documentation, a section's position in the document hierarchy holds significant context. Comparing nodes by their absolute path ensures that parent-child structures are validated.

### Known Failure Modes
1. **Renaming a Parent Heading**: If a top-level section is renamed (e.g., `## 4. Alarms` becomes `## 4. Safety Alarms`), the paths of all its children change. They will be classified as "New" nodes with brand new logical IDs, and the old sections will appear as "Deleted." This breaks historical traceability.
2. **Moving a Section**: If `### 3.4 Auto Shutoff` is moved to Section 5, its path changes, leading to a new `logical_id`.
   - *Justification*: In safety-critical software, moving or renaming a section changes its semantic context. Invalidating previous test cases and flagging the section as new/deleted forces QA engineers to re-verify the requirement, which is the correct safe-by-default behavior.

---

## 4. LLM Prompt Design & Retry Strategy

### Prompt Design
The prompt enforces a strict JSON output matching our Pydantic schema (`GeneratedTestCasesList`). We instruct Gemini to return only raw JSON and provide examples showing how to parse numbers and events into concrete test steps and expected results.

### Structured-Output & Retry Strategy
If the LLM returns invalid JSON or schema-incompatible keys:
1. We attempt to clean typical markdown wraps (such as ```json ... ```).
2. If validation still fails, we trigger a **Correction Loop** (up to 3 retries):
   - We send the original text, the malformed LLM response, and the exact traceback error message back to the LLM.
   - We ask the LLM to output corrected, valid JSON conforming to the schema.
3. If all retries fail, we raise a clear `HTTP_500` error to prevent malformed data from persisting.

### Duplicate Selection Submission Policy
If a selection is submitted for test generation twice:
- By default, we cache and return the existing generated test cases.
- If the user passes `force=True`, we bypass the cache, trigger a new LLM call, and overwrite the existing generated test cases in the database.

---

## 5. Staleness & Impact Detection

Test cases are version-pinned to the selection version. When retrieving test cases (`GET /api/selections/{id}/test-cases`):
1. We find the latest version of the document.
2. If the selection is not on the latest version:
   - For each selected node, we look up its counterpart in the latest version using its `logical_id`.
   - If the counterpart is missing: mark as `is_stale = True` (Reason: Section was deleted) and show a deletion diff.
   - If the counterpart exists but has a different `content_hash`: mark as `is_stale = True` (Reason: Section was modified) and generate a unified diff.
3. The response includes `is_stale: true`, a list of affected nodes, and their unified line-by-line diffs.

---

## 6. Decision Log

### 1. What's the one part of this system most likely to silently give wrong results without erroring? How would you catch it?
**The Version Matching Engine.** If the manual author makes minor typos in the headers of several sections (e.g. `1.1 Intended Use` becomes `1.1 Intended uses`), the paths will shift. The system would match nothing, silently treating them as completely new sections and deleting the old ones. The QA engineer would see "test cases are fresh" for the new sections but completely lose traceability to their original test cases.
- *How to catch it*: We could add a fuzzy title matching fallback. If a path fails to match, we compare the section title using Levenshtein distance and check if a node with high text similarity exists under the same parent, warning the user about a potential rename.

### 2. Where did you choose simplicity over correctness because of time, and what would break first if this went to production as-is?
**Path-based parent resolution during ingestion.** We assume that headings always appear in sequential reading order. If a document has out-of-order text or disjointed markdown blocks (e.g. multiple headings on a single line or heading tags inside a markdown table/code block), the parser will process them incorrectly, leading to mis-parented nodes.
- *What would break*: In production, if an author uploads a markdown document with complex nested tables containing headers or a code block containing mock markdown, it will break the hierarchy and corrupt the node tree.

### 3. Name one input (to your parser, your versioning matcher, or your LLM call) that you did not handle, and what your system does when it sees it?
**Duplicate headings under the exact same parent section.** If the manual contains two identical `### Specifications` headers inside `## 2. General specifications`, they will generate identical paths.
- *System behavior*: Our parser detects duplicate sibling paths and appends a `#count` suffix (e.g., `/2. General/Specifications #2`). However, if they are reordered in V2, the suffixes will swap, causing the version matcher to incorrectly flag them as modified and swap their test case links.
