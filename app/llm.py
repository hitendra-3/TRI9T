import os
import json
import re
import google.generativeai as genai
from typing import Dict, Any
from app.schemas import GeneratedTestCasesList

def generate_qa_test_cases(doc_name: str, context_text: str, model_name: str = "gemini-3.1-flash-lite") -> Dict[str, Any]:
    """
    Sends the selected manual text to Google Gemini 2.5 Flash to generate
    3 to 5 QA test cases. Enforces JSON structured output and performs validation
    with retries in case of format errors.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in a .env file.")
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
You are a professional QA engineer specializing in medical devices.
Your task is to generate 3 to 5 high-quality, concrete, and repeatable QA test cases based on the provided technical manual section for '{doc_name}'.

For medical devices, test cases must be specific, repeatable, and safety-critical where appropriate.
Avoid generic descriptions. Specify concrete inputs, simulated events, and expected outputs as described in the text.

Each test case must include:
1. Title: A short, repeatable check title (e.g., "Overpressure Protection and Auto-Deflation").
2. Steps: Clear, sequential, concrete steps for a QA engineer to execute the test.
3. Expected Result: The expected behavior of the device as defined by the manual.
4. Priority: "High", "Medium", or "Low".

Selected Manual Content:
\"\"\"
{context_text}
\"\"\"

You MUST return a valid JSON object matching this schema:
{{
  "test_cases": [
    {{
      "title": "Title of test case",
      "steps": ["Step 1", "Step 2", ...],
      "expected_result": "Detailed expected result",
      "priority": "High" | "Medium" | "Low"
    }}
  ]
}}

Return ONLY the JSON object. Do not include markdown code block formatting (like ```json ... ```) or any additional explanation text.
"""
    
    max_retries = 3
    last_error = None
    raw_response = ""
    
    for attempt in range(max_retries):
        try:
            # We can also add JSON response MIME type configuration
            generation_config = {"response_mime_type": "application/json"}
            response = model.generate_content(prompt, generation_config=generation_config)
            raw_response = response.text.strip()
            
            # Clean response text if LLM wrapped it in markdown code blocks despite instructions
            cleaned_text = raw_response
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
                cleaned_text = re.sub(r"\n```$", "", cleaned_text)
                cleaned_text = cleaned_text.strip()
                
            data = json.loads(cleaned_text)
            
            # Validate schema using Pydantic
            validated = GeneratedTestCasesList(**data)
            
            return {
                "prompt": prompt,
                "raw_response": raw_response,
                "test_cases": [tc.model_dump() for tc in validated.test_cases]
            }
            
        except Exception as e:
            last_error = e
            # Adjust the prompt for the retry to point out the error and ask for correction
            prompt = f"""
The previous attempt to generate test cases failed with the following error: {str(e)}
The generated response was:
{raw_response}

Please correct the formatting, ensure it is valid JSON, and matches this exact schema:
{{
  "test_cases": [
    {{
      "title": "Title",
      "steps": ["Step 1", "Step 2"],
      "expected_result": "Expected result",
      "priority": "High" | "Medium" | "Low"
    }}
  ]
}}
Original Manual Content:
\"\"\"
{context_text}
\"\"\"
"""
            
    raise RuntimeError(
        f"Failed to generate valid structured test cases after {max_retries} attempts. "
        f"Last error: {str(last_error)}. Raw response: {raw_response}"
    )
