import hashlib

def compute_content_hash(heading: str, level: int, body_text: str) -> str:
    """
    Computes a SHA-256 hash of the node's content.
    Includes the heading, level, and body_text to detect any modification.
    """
    # Normalize line endings to avoid platform-specific discrepancies
    normalized_body = body_text.replace("\r\n", "\n")
    data = f"LEVEL:{level}\nHEADING:{heading}\nBODY:{normalized_body}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
