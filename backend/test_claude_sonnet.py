
import os
import json
import asyncio
from google.oauth2 import service_account
import httpx

PROJECT_ID = "project-fb884592-f206-43c0-948" 
LOCATION = "us-east5"
KEY_PATH = os.path.join(os.path.dirname(__file__), "key.json")

async def test_sonnet():
    print(f"🚀 Final Check: Testing Claude 3.5 Sonnet in {LOCATION}...")
    with open(KEY_PATH, 'r') as f:
        key_data = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(
        key_data, 
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    token = credentials.token
    if not token:
        import google.auth.transport.requests
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        token = credentials.token

    model_id = "claude-3-5-sonnet@20240620"
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/anthropic/models/{model_id}:rawPredict"
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "anthropic_version": "vertex-2023-10-16",
        "messages": [{"role": "user", "content": "Ping"}],
        "max_tokens": 10
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
        if resp.status_code == 200:
            print("✅ SUCCESS! Claude 3.5 Sonnet is available.")
        else:
            print(f"❌ Claude 3.5 Sonnet also failed ({resp.status_code}).")
            print("💡 This confirms that Anthropic models are not yet enabled for this project in GCP Console.")

if __name__ == "__main__":
    asyncio.run(test_sonnet())
