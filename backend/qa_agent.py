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
3. Character Visibility: Is the main subject clearly visible and properly framed?
4. Topic Alignment (Context Lock): Does the image match the news topic? 
   - If the news is about "Financials/Economy", the image must be symbolic (money, scales, graphs). 
   - If the news is about "Protests", the atmosphere must be tense/realistic. 
   - NO fictional characters (e.g. Wonder Woman, Superheroes) allowed for real-world news events. FAIL if you see any "Superheroes" or "Fictional characters" in a news post.
5. Visual Style: Does it look like RAW PHOTOJOURNALISM? If it looks like a "3D Render", "Cartoon", or "Cinematic AI Art", FAIL it. It must look like a press photo.
6. Compositional Integrity (THE KILL SWITCH): Analyze the placement of the text relative to the subject. 
   - If the oversized text covers the subject's eyes, mouth, or central face, FAIL it immediately.
   - If the subject is not positioned according to the Rule of Thirds (far left or far right), FAIL it.

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
