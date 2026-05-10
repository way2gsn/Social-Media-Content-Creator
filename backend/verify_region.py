
import os
import json
import asyncio
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT_ID = "project-fb884592-f206-43c0-948" 
LOCATION = "us-central1"
KEY_PATH = os.path.join(os.path.dirname(__file__), "key.json")

async def verify_region():
    print(f"🕵️ Verifying project access to {LOCATION} using Gemini...")
    with open(KEY_PATH, 'r') as f:
        key_data = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(key_data)
    vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)
    
    try:
        model = GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content("ping")
        print(f"✅ Gemini works in {LOCATION}!")
        return True
    except Exception as e:
        print(f"❌ Gemini failed in {LOCATION}: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(verify_region())
