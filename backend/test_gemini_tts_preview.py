import asyncio, sys, os, json
sys.path.append('backend')
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel

async def main():
    key_path = "backend/key.json"
    with open(key_path, 'r') as f:
        key_data = json.load(f)
    
    project_id = key_data['project_id']
    location = "us-central1"
    credentials = service_account.Credentials.from_service_account_info(key_data)
    vertexai.init(project=project_id, location=location, credentials=credentials)
    
    model_id = "gemini-3.1-flash-tts-preview"
    print(f"Testing {model_id}...")
    try:
        model = GenerativeModel(model_id)
        # Try a simple text request first to see if model is valid
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content("Hello"))
        print(f"✅ Model access successful! Response: {response.text}")
    except Exception as e:
        print(f"❌ {model_id} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
