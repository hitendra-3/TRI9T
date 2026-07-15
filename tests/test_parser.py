from app.parser import parse_markdown

def test_irregular_level_jump():
    """
    Test that a jump from level 3 (###) to level 4 (####) correctly
    parents the level 4 node to the level 3 node.
    """
    markdown = """# CardioTrack Manual
## 2. Specifications
### 2.1 General Specifications
body text 2.1
#### 2.1.1.1 Battery Life Under Typical Use
body text 2.1.1.1
"""
    nodes = parse_markdown(markdown)
    
    # We expect 4 nodes: Root (L1), Specifications (L2), General (L3), Battery Life (L4)
    assert len(nodes) == 4
    
    battery_node = nodes[3]
    general_node = nodes[2]
    
    assert battery_node["title"] == "2.1.1.1 Battery Life Under Typical Use"
    assert battery_node["level"] == 4
    assert battery_node["parent_path"] == general_node["path"]
    assert battery_node["path"] == f"{general_node['path']}/2.1.1.1 Battery Life Under Typical Use"

def test_out_of_order_sibling_levels():
    """
    Test that out of order sibling level jumps (#### 3.2, ### 3.4, ### 3.3)
    correctly resolve parents.
    """
    markdown = """# CardioTrack Manual
## 3. Device Operation
### 3.1 Powering On
#### 3.2 Cuff Inflation Sequence
body 3.2
### 3.4 Auto Shutoff
body 3.4
### 3.3 Result Display
body 3.3
"""
    nodes = parse_markdown(markdown)
    
    # We expect: Root, Operation (L2), Powering On (L3), Cuff Inflation (L4), Auto Shutoff (L3), Result Display (L3)
    assert len(nodes) == 6
    
    cuff_inflation = nodes[3]
    auto_shutoff = nodes[4]
    result_display = nodes[5]
    operation = nodes[1]
    powering_on = nodes[2]
    
    assert cuff_inflation["parent_path"] == powering_on["path"]
    assert auto_shutoff["parent_path"] == operation["path"]
    assert result_display["parent_path"] == operation["path"]

def test_duplicate_headings_different_parents():
    """
    Asserts that the duplicate-heading case (Error Codes under Section 4 and Section 7)
    produces distinct paths with the correct parent nodes.
    """
    markdown = """# CardioTrack Manual
## 4. Alarms and Safety Behavior
### 4.2 Error Codes
Alarms error codes...
## 7. Troubleshooting
### 7.1 Error Codes
Troubleshooting error codes...
"""
    nodes = parse_markdown(markdown)
    
    assert len(nodes) == 5
    
    section4 = nodes[1]
    err_code_4 = nodes[2]
    section7 = nodes[3]
    err_code_7 = nodes[4]
    
    assert err_code_4["title"] == "4.2 Error Codes"
    assert err_code_4["parent_path"] == section4["path"]
    assert err_code_4["path"] == f"{section4['path']}/4.2 Error Codes"
    
    assert err_code_7["title"] == "7.1 Error Codes"
    assert err_code_7["parent_path"] == section7["path"]
    assert err_code_7["path"] == f"{section7['path']}/7.1 Error Codes"
    
    assert err_code_4["path"] != err_code_7["path"]
