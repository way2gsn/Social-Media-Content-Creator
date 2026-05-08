import os, json
from google import genai

key = json.load(open('backend/key.json'))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "backend/key.json"

client = genai.Client(vertexai=True, project=key['project_id'], location='us-central1')

try:
    operation = client.operations.get(
        operation_id='projects/project-fb884592-f206-43c0-948/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/620c25cb-ebf5-42dc-9084-f4faaac6eb26'
    )
    print("Polled Operation:", operation)
except Exception as e:
    print(f"Error: {e}")

