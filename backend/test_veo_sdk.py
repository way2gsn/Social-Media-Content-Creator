import asyncio
from google.oauth2 import service_account
import json
import vertexai
from vertexai.preview.vision_models import VideoGenerationModel

key = json.load(open('backend/key.json'))
creds = service_account.Credentials.from_service_account_info(key).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
vertexai.init(project=key['project_id'], location="us-central1", credentials=creds)

try:
    print("Loading model...")
    model = VideoGenerationModel.from_pretrained("veo-3.1-fast-generate-001")
    print("Generating video...")
    # Passing an empty string for gcs_destination or letting it default if possible
    res = model.generate_video(prompt="Cinematic shot of a computer monitor")
    print(res)
except Exception as e:
    print(f"Error: {e}")

