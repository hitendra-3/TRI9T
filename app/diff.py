import difflib

def generate_diff(old_text: str, new_text: str, old_label: str = "v1", new_label: str = "v2") -> str:
    """
    Generates a unified diff between old_text and new_text.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_label,
        tofile=new_label,
        lineterm=""
    )
    return "\n".join(diff)
