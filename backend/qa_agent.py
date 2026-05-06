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
        
        prompt = f"""You are a strict editorial Quality Assurance agent for a premium news social media account.
Analyze this generated social media post and the provided context/title.

Context/Title used to generate this post: "{title}"

Check the following criteria STRICTLY:
1. Visual Clarity: Is the background a messy poster full of text? The background should be clean. If there is chaotic background text (like a movie poster or an ad) behind the main subject, FAIL it.
2. Contextual Value: Does the post have a complete, context-rich headline, or is it a half-baked, meaningless title? If the text on the post or the context provided is meaningless or just a single name without context, FAIL it.
3. Character Visibility: Is the main subject clearly visible and properly framed? If they are cut off awkwardly or completely hidden, FAIL it.

Output ONLY a raw, valid JSON object with the following keys:
"approved": boolean (true if it passes ALL criteria, false otherwise)
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
