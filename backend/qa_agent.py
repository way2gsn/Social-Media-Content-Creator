import json
from gcp_client import get_gcp_client

class QAAgent:
    @staticmethod
    async def validate_post(image_path: str, title: str) -> tuple[bool, str]:
        """
        Validates the generated post image and context using Vertex AI Vision.
        Returns (is_approved, reason).
        """
        client = get_gcp_client()
        
        is_test = any(kw in title.lower() for kw in ["test", "manual", "force"])
        lenient_instruction = "IMPORTANT: This is a MANUAL TEST. Be more lenient on background text, focus on validating if the overall design and character likeness are professional." if is_test else ""

        prompt = f"""You are a senior editorial Quality Assurance agent for a premium news social media account.
Analyze this generated social media post and the provided context/title.

Context/Title used to generate this post: "{title}"
{lenient_instruction}

Check the following criteria:
1. Visual Clarity: The background should be clean. If there is chaotic/unreadable background text that ruins the premium look, FAIL it.
2. Contextual Value: Does the post have a complete, context-rich headline? If it is just a single name without context, FAIL it.
3. Character Visibility: Is the main subject clearly visible and properly framed? If they are completely hidden or distorted beyond recognition, FAIL it.

Output ONLY a raw, valid JSON object:
"approved": boolean (true if it passes the core criteria, false otherwise)
"reason": string (a short sentence explaining why it passed or failed)
"""
        
        response_text = await client.analyze_image(image_path, prompt)
        
        try:
            data = json.loads(response_text)
            approved = data.get("approved", False)
            reason = data.get("reason", "No reason provided.")
            return approved, reason
        except Exception as e:
            print(f"QAAgent JSON Parse Error: {e} | Raw: {response_text}")
            # If the model fails to return JSON, we assume it failed QA to be safe
            return False, "Failed to parse QA response from AI."
