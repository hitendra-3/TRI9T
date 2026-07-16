import re
import os
import io
from typing import List, Dict, Any, Optional

_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)(?:\s+#+\s*)?$")
_SECTION_HEADING_RE = re.compile(r"^Section\s+\d+", re.I)
_BOLD_HEADING_RE = re.compile(r"^\*\*(.+)\*\*$")


def _numbered_heading_level(line: str) -> int:
    """Map '1.' -> H2, '1.1' -> H3, '2.1.1.1' -> H5 based on section depth."""
    match = re.match(r"^(\d+(?:\.\d+)*)", line.strip())
    if match:
        segments = match.group(1).split(".")
        return min(6, max(2, len(segments) + 1))
    return 2


def _is_numbered_heading(line: str) -> bool:
    if _SECTION_HEADING_RE.match(line):
        return True

    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", line.strip())
    if not match:
        return False

    number, title = match.group(1), match.group(2).strip()

    # Subsections such as 1.1, 2.1.1 are always headings.
    if re.fullmatch(r"\d+(?:\.\d+)+", number):
        return True

    # Top-level sections: "1. Device Overview"
    if re.match(r"^\d+\.\s+[A-Z]", line.strip()):
        # Skip ordered-list items like "1. Normal: systolic < 120"
        if re.match(r"^[A-Za-z0-9\s]+:", title):
            return False
        return True

    return False


def normalize_markdown_headings(content: str) -> str:
    """
    Convert plain-text section lines into ATX markdown headings so MD uploads
    produce the same hierarchical tree as PDF uploads (which are OCR'd to markdown).
    """
    content = content.lstrip("\ufeff")
    lines = content.splitlines()
    normalized: List[str] = []
    title_assigned = False
    i = 0

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        if not stripped:
            normalized.append(raw)
            i += 1
            continue

        # Setext-style headings (Title\n===== or Section\n-----)
        if i + 1 < len(lines):
            underline = lines[i + 1].strip()
            if underline and set(underline) <= {"="} and len(underline) >= 3:
                normalized.append(f"# {stripped}")
                title_assigned = True
                i += 2
                continue
            if underline and set(underline) <= {"-"} and len(underline) >= 3:
                normalized.append(f"## {stripped}")
                title_assigned = True
                i += 2
                continue

        if _ATX_HEADING_RE.match(stripped):
            normalized.append(stripped)
            title_assigned = True
            i += 1
            continue

        bold_match = _BOLD_HEADING_RE.match(stripped)
        if bold_match:
            inner = bold_match.group(1).strip()
            if _is_numbered_heading(inner):
                level = _numbered_heading_level(inner)
                normalized.append(f"{'#' * level} {inner}")
            else:
                normalized.append(f"## {inner}")
            title_assigned = True
            i += 1
            continue

        if _is_numbered_heading(stripped):
            level = _numbered_heading_level(stripped)
            normalized.append(f"{'#' * level} {stripped}")
            title_assigned = True
            i += 1
            continue

        if stripped.isupper() and len(stripped) < 80 and not stripped.startswith("|"):
            normalized.append(f"## {stripped}")
            title_assigned = True
            i += 1
            continue

        if (
            not title_assigned
            and not stripped.startswith("|")
            and not stripped.startswith("- ")
            and not stripped.startswith("* ")
            and not stripped.startswith("<!--")
        ):
            normalized.append(f"# {stripped}")
            title_assigned = True
            i += 1
            continue

        normalized.append(raw)
        i += 1

    return "\n".join(normalized)

def parse_pdf_via_gemini(pdf_bytes: bytes) -> str:
    """
    Uses Gemini 2.5 Flash to perform layout-preserving multimodal OCR
    and extract clean markdown structure from the PDF file.
    """
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in a .env file.")
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    
    prompt = """
You are an expert document parsing agent.
Your task is to parse the attached PDF document and convert its entire contents into clean, structural Markdown text.
You must preserve:
1. The hierarchical structure of headings (use #, ##, ###, ####, etc. properly).
2. All sections, subsections, lists, bullet points, and tables.
3. Retain table data in standard markdown table format (e.g. | Header 1 | Header 2 | ...).
4. Maintain the layout order and text content exactly. Do not omit any text, paragraphs, error codes, specifications, or details.
5. Do not add any conversational text or prefix/suffix. Return ONLY the final markdown content.
"""
    
    response = model.generate_content([
        {
            "mime_type": "application/pdf",
            "data": pdf_bytes
        },
        prompt
    ])
    return response.text.strip()

def parse_pdf_via_pypdf(pdf_bytes: bytes) -> str:
    """
    Local fallback parser using pypdf to extract text and structure from a digital PDF.
    """
    from pypdf import PdfReader
    
    reader = PdfReader(io.BytesIO(pdf_bytes))
    markdown_lines = []
    
    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line:
                markdown_lines.append(line)
        markdown_lines.append("")
        
    return normalize_markdown_headings("\n".join(markdown_lines))

def parse_pdf_to_markdown(pdf_bytes: bytes) -> str:
    """
    Parses PDF bytes to Markdown content. Tries Gemini 2.5 Flash first for structural OCR,
    and falls back to pypdf for local extraction if Gemini fails or is not configured.
    """
    if os.getenv("GEMINI_API_KEY"):
        try:
            return parse_pdf_via_gemini(pdf_bytes)
        except Exception as e:
            print(f"Gemini PDF parsing failed: {e}. Falling back to pypdf.")
            
    return parse_pdf_via_pypdf(pdf_bytes)

def parse_markdown(content: str) -> List[Dict[str, Any]]:
    """
    Parses a markdown string into a hierarchical list of nodes.
    Each node has:
      - heading: raw heading line (e.g., '### 1.1 Intended Use')
      - title: cleaned heading title (e.g., '1.1 Intended Use')
      - level: header level (1 for #, 2 for ##, etc.)
      - body_text: accumulated text under this heading
      - path: unique hierarchical path (e.g., '/Title/1. Device Overview/1.1 Intended Use')
      - parent_path: path of the parent node
    """
    content = normalize_markdown_headings(content)
    lines = content.splitlines()
    nodes = []
    
    # Current active state
    current_heading = None
    current_title = ""
    current_level = 0
    current_body_lines = []
    
    # Stack of active parents: list of dicts with keys 'level', 'title', 'path'
    stack = []
    
    # To track sibling duplicates and generate unique paths: parent_path -> {title: count}
    path_counts = {}

    def commit_current_node():
        nonlocal current_heading, current_title, current_level, current_body_lines
        if current_heading is None:
            return
            
        body_text = "\n".join(current_body_lines).strip()
        
        # Pop stack until we find parent (level < current_level)
        while stack and stack[-1]["level"] >= current_level:
            stack.pop()
            
        parent_path = stack[-1]["path"] if stack else ""
        
        # Generate unique title path
        parent_tracker = path_counts.setdefault(parent_path, {})
        base_title = current_title
        if base_title in parent_tracker:
            parent_tracker[base_title] += 1
            unique_title = f"{base_title} #{parent_tracker[base_title]}"
        else:
            parent_tracker[base_title] = 1
            unique_title = base_title
            
        path = f"{parent_path}/{unique_title}"
        
        nodes.append({
            "heading": current_heading,
            "title": unique_title,
            "level": current_level,
            "body_text": body_text,
            "path": path,
            "parent_path": parent_path or None
        })
        
        # Push current node to stack
        stack.append({
            "level": current_level,
            "title": unique_title,
            "path": path
        })

    for line_idx, line in enumerate(lines):
        match = _ATX_HEADING_RE.match(line.strip())
        if match:
            # Commit the previous section
            commit_current_node()
            
            # Start new section
            hashes, title_text = match.groups()
            current_heading = line.strip()
            current_title = title_text.strip()
            current_level = len(hashes)
            current_body_lines = []
        else:
            # Accumulate body text
            # Skip empty lines at the very beginning of a section, but keep internal blank lines
            if current_heading is not None:
                current_body_lines.append(line)
            else:
                # If there is content before the first header, create an implicit root node
                # Or if it's metadata/blank lines. In ct200_manual.md, the first line is `# CardioTrack...`
                # so this case won't be hit for content, but we handle it just in case.
                if line.strip():
                    current_heading = "# Document Root"
                    current_title = "Document Root"
                    current_level = 1
                    current_body_lines = [line]

    # Commit the final section
    commit_current_node()
    
    return nodes
