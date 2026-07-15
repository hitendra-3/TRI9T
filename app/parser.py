import re
from typing import List, Dict, Any, Optional

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

    heading_regex = re.compile(r"^(#{1,6})\s+(.+)$")
    
    for line_idx, line in enumerate(lines):
        match = heading_regex.match(line)
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
