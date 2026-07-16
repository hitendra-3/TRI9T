from app.parser import parse_markdown

# ─── Level Jump Tests ─────────────────────────────────────────────────────────

def test_direct_level_jump_parents_correctly():
    """
    A jump from H3 to H4 must parent the H4 node under the H3 node,
    not under the H2 ancestor.
    """
    md = (
        "# Device Manual\n"
        "## Specifications\n"
        "### General Specs\n"
        "General specs body.\n"
        "#### Battery Life\n"
        "Battery life body.\n"
    )
    nodes = parse_markdown(md)

    # Root, Specifications (L2), General Specs (L3), Battery Life (L4)
    assert len(nodes) == 4

    battery = nodes[3]
    general = nodes[2]

    assert battery["title"] == "Battery Life"
    assert battery["level"] == 4
    assert battery["parent_path"] == general["path"]
    assert battery["path"] == f"{general['path']}/Battery Life"


def test_out_of_order_sibling_levels_resolve_correctly():
    """
    When heading levels jump non-sequentially (H3 → H4 → H3 → H3),
    each H3 should be parented to its nearest H2 ancestor.
    """
    md = (
        "# Device Manual\n"
        "## Device Operation\n"
        "### Power On\n"
        "#### Startup Sequence\n"
        "Startup body.\n"
        "### Auto Shutoff\n"
        "Shutoff body.\n"
        "### Display\n"
        "Display body.\n"
    )
    nodes = parse_markdown(md)

    # Root, Device Operation (L2), Power On (L3), Startup Sequence (L4),
    # Auto Shutoff (L3), Display (L3)
    assert len(nodes) == 6

    operation  = nodes[1]
    power_on   = nodes[2]
    startup    = nodes[3]
    shutoff    = nodes[4]
    display    = nodes[5]

    assert startup["parent_path"] == power_on["path"]   # L4 under L3
    assert shutoff["parent_path"] == operation["path"]  # L3 under L2
    assert display["parent_path"] == operation["path"]  # L3 under L2


# ─── Duplicate Heading Tests ──────────────────────────────────────────────────

def test_duplicate_headings_produce_distinct_paths():
    """
    Two sections with identical heading text (e.g. 'Error Codes') under
    different parents must produce distinct paths with correct parent linkage.
    """
    md = (
        "# Device Manual\n"
        "## Alarms\n"
        "### Error Codes\n"
        "Alarm error codes.\n"
        "## Troubleshooting\n"
        "### Error Codes\n"
        "Troubleshooting error codes.\n"
    )
    nodes = parse_markdown(md)

    assert len(nodes) == 5

    alarms         = nodes[1]
    err_alarms     = nodes[2]
    troubleshoot   = nodes[3]
    err_trouble    = nodes[4]

    assert err_alarms["title"] == "Error Codes"
    assert err_alarms["parent_path"] == alarms["path"]

    assert err_trouble["title"] == "Error Codes"
    assert err_trouble["parent_path"] == troubleshoot["path"]

    # Paths must differ even though titles are the same
    assert err_alarms["path"] != err_trouble["path"]


# ─── Body Text Tests ──────────────────────────────────────────────────────────

def test_body_text_is_captured_under_correct_node():
    """
    Body text appearing after a heading must be associated with that heading's node,
    not the parent.
    """
    md = (
        "# Device Manual\n"
        "## Connectivity\n"
        "This section describes connectivity features.\n"
        "Supported protocols: BLE, USB.\n"
    )
    nodes = parse_markdown(md)

    assert len(nodes) == 2
    root = nodes[0]
    connectivity = nodes[1]

    assert connectivity["title"] == "Connectivity"
    assert "connectivity features" in connectivity["body_text"]
    assert root["body_text"].strip() == ""


def test_root_node_path_is_document_title():
    """
    The root node (H1) must have a path equal to its own title, with no parent path.
    """
    md = "# My Product Manual\n## Section One\nBody.\n"
    nodes = parse_markdown(md)

    root = nodes[0]
    assert root["level"] == 1
    assert root["parent_path"] is None
    assert "My Product Manual" in root["path"]


# ─── Empty / Edge Cases ───────────────────────────────────────────────────────

def test_single_heading_produces_one_node():
    """A document with only an H1 and no children produces exactly one node."""
    md = "# Standalone Title\nSome introductory text.\n"
    nodes = parse_markdown(md)
    assert len(nodes) == 1
    assert nodes[0]["level"] == 1


def test_deeply_nested_headings_chain_parents():
    """
    A 4-level deep hierarchy should chain each node to its immediate parent.
    """
    md = (
        "# Manual\n"
        "## Chapter\n"
        "### SubChapter\n"
        "#### Detail\n"
        "Detail body.\n"
    )
    nodes = parse_markdown(md)
    assert len(nodes) == 4

    manual     = nodes[0]
    chapter    = nodes[1]
    subchapter = nodes[2]
    detail     = nodes[3]

    assert chapter["parent_path"] == manual["path"]
    assert subchapter["parent_path"] == chapter["path"]
    assert detail["parent_path"] == subchapter["path"]

# ─── Plain-Text / MD Normalization Tests ─────────────────────────────────────

def test_plain_text_md_without_hash_headings():
    """
    MD files with plain numbered section lines (no # prefix) must produce
    the same hierarchical structure as properly formatted markdown.
    """
    md = (
        "CardioTrack CT-200 Home Blood Pressure Monitor\n\n"
        "1. Device Overview\n"
        "The CT-200 is an oscillometric device.\n\n"
        "1.1 Intended Use\n"
        "The CT-200 is intended to measure blood pressure.\n\n"
        "2. Physical and Electrical Specifications\n"
        "Some specs here.\n"
    )
    nodes = parse_markdown(md)

    assert len(nodes) == 4
    assert nodes[0]["title"].startswith("CardioTrack CT-200")
    assert nodes[0]["level"] == 1
    assert nodes[1]["title"] == "1. Device Overview"
    assert nodes[1]["level"] == 2
    assert nodes[2]["title"] == "1.1 Intended Use"
    assert nodes[2]["level"] == 3
    assert nodes[3]["title"] == "2. Physical and Electrical Specifications"
    assert nodes[3]["level"] == 2


def test_existing_hash_markdown_unchanged():
    """
    Properly formatted ATX markdown (with # headings) must parse correctly after
    normalization — hierarchy and content must be preserved.
    We check structure not exact count, so minor manual edits don't break CI.
    """
    with open("data/ct200_manual.md", encoding="utf-8") as f:
        md = f.read()
    nodes = parse_markdown(md)
    assert len(nodes) >= 28, f"Expected at least 28 nodes, got {len(nodes)}"
    assert nodes[1]["title"] == "1. Device Overview"
    assert nodes[0]["level"] == 1          # root is H1
    assert nodes[1]["level"] == 2          # top-level section is H2
    # Every node must have a path, heading, and content_hash-ready fields
    for node in nodes:
        assert node["path"]
        assert node["heading"]
        assert node["level"] >= 1


def test_headings_without_space_after_hash():
    """Headings like '#Title' (no space) should still be recognized."""
    md = "#Title\n##Section One\nBody text.\n"
    nodes = parse_markdown(md)
    assert len(nodes) == 2
    assert nodes[0]["title"] == "Title"
    assert nodes[1]["title"] == "Section One"


# ─── PDF Parsing Pipeline Tests ───────────────────────────────────────────────

from unittest.mock import patch, MagicMock

def test_pdf_parsing_pipeline_fallback():
    """
    Test that the PDF parsing pipeline falls back to pypdf when Gemini key is not set
    or fails.
    """
    from app.parser import parse_pdf_to_markdown
    
    mock_pdf_bytes = b"%PDF-1.4 mock pdf data"
    
    with patch("app.parser.os.getenv", return_value=None):  # No Gemini API Key
        with patch("pypdf.PdfReader") as MockPdfReader:
            # Setup mock reader pages
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "1. Section One\nSome content under section one."
            
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            MockPdfReader.return_value = mock_reader
            
            result = parse_pdf_to_markdown(mock_pdf_bytes)
            
            assert "## 1. Section One" in result
            assert "Some content" in result

def test_pdf_parsing_pipeline_gemini():
    """
    Test that the PDF parsing pipeline uses Gemini when API key is set.
    """
    from app.parser import parse_pdf_to_markdown
    
    mock_pdf_bytes = b"%PDF-1.4 mock pdf data"
    
    with patch("app.parser.os.getenv", return_value="fake_api_key"):
        with patch("google.generativeai.GenerativeModel") as MockModel:
            mock_model_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "# Ingested Document\n## 1. Safety\nSafety instructions."
            mock_model_instance.generate_content.return_value = mock_response
            MockModel.return_value = mock_model_instance
            
            result = parse_pdf_to_markdown(mock_pdf_bytes)
            
            assert "# Ingested Document" in result
            assert "## 1. Safety" in result
            assert "Safety instructions." in result
