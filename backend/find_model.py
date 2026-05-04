import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
import json

def find_any_gemini():
    with open("key.json", "r") as f:
        key_data = json.load(f)
    
    credentials = service_account.Credentials.from_service_account_info(key_data)
    
    # Try multiple common and experimental names
    models = [
        "gemini-1.5-flash-001", "gemini-1.5-flash-002",
        "gemini-2.0-flash-001", "gemini-2.5-flash", "gemini-3-flash",
        "gemini-pro-vision", "gemini-1.0-pro-002"
    ]
    
    vertexai.init(project=key_data['project_id'], location="us-central1", credentials=credentials)
    
    for m in models:
        try:
            print(f"Testing {m}...")
            model = GenerativeModel(m)
            resp = model.generate_content("test")
            print(f"SUCCESS with {m}: {resp.text[:20]}")
            return m
        except Exception as e:
            print(f"FAILED with {m}: {str(e)[:150]}")

if __name__ == "__main__":
    find_any_gemini()
