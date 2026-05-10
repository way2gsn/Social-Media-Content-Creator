
import os
import json
import asyncio
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel
import httpx

PROJECT_ID = "project-fb884592-f206-43c0-948" 
LOCATION = "us-east5"
KEY_PATH = os.path.join(os.path.dirname(__file__), "key.json")

async def test_models():
    print(f"🚀 Testing Advanced Models in {LOCATION}...")
    
    with open(KEY_PATH, 'r') as f:
        key_data = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(
        key_data, 
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)
    
    # 1. First, verify with a known working model in this system
    print("\n--- Phase 1: Gemini 2.5 Flash Verification ---")
    try:
        model = GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content("test")
        print(f"✅ SUCCESS: Gemini 2.5 Flash is working in {LOCATION}.")
    except Exception as e:
        print(f"❌ Gemini 2.5 Flash failed: {e}")

    # 2. Test Claude 3 Opus (Standard ID)
    print("\n--- Phase 2: Claude 3 Opus Test ---")
    try:
        model_id = "claude-3-opus@20240229"
        url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/anthropic/models/{model_id}:rawPredict"
        
        token = credentials.token
        if not token:
            import google.auth.transport.requests
            auth_request = google.auth.transport.requests.Request()
            credentials.refresh(auth_request)
            token = credentials.token

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [{"role": "user", "content": "Hello Claude 3 Opus"}],
            "max_tokens": 100
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=20.0)
            if resp.status_code == 200:
                print("✅ SUCCESS: Claude 3 Opus is available.")
                print(resp.json().get('content', [{}])[0].get('text'))
            else:
                print(f"❌ Claude 3 Opus failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Claude 3 Opus test error: {e}")

    # 3. Test Claude 4 Opus (User's specific request)
    print("\n--- Phase 3: Claude 4 Opus (Experimental ID) Test ---")
    # Note: 'claude-4-opus' is hypothetical but the user explicitly requested it.
    # On Vertex AI, new models follow the 'claude-X-opus@YYYYMMDD' format.
    # We will try a few variations.
    
    model_ids = ["claude-4-opus", "claude-4-opus@20260101", "claude-3-5-opus@20241022"]
    
    for m_id in model_ids:
        print(f"Testing ID: {m_id}...")
        try:
            url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/anthropic/models/{m_id}:rawPredict"
            payload = {
                "anthropic_version": "vertex-2023-10-16",
                "messages": [{"role": "user", "content": "Hello Claude 4"}],
                "max_tokens": 100
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                if resp.status_code == 200:
                    print(f"✅ SUCCESS! Claude 4 found with ID: {m_id}")
                    return
                else:
                    print(f"   - Failed ({resp.status_code})")
        except:
            pass

    print("\n💡 CONCLUSION: No Claude 4 models found yet. Recommend sticking to Claude 3.5 or 3 Opus for now.")

if __name__ == "__main__":
    asyncio.run(test_models())
