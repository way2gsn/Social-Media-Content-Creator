import urllib.request, json, ssl
from google.oauth2 import service_account
import google.auth.transport.requests

key = json.load(open('backend/key.json'))
creds = service_account.Credentials.from_service_account_info(key).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
request = google.auth.transport.requests.Request()
creds.refresh(request)
token = creds.token

endpoint = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{key['project_id']}/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001:predictLongRunning"
payload = {"instances": [{"prompt": "test"}], "parameters": {"outputConfig": {"gcsDestination": {"uri": "gs://test-bucket/out.mp4"}}}}
req = urllib.request.Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as response:
        print(response.read())
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'): print(e.read().decode())
