import urllib.request, json, ssl
from google.oauth2 import service_account
import google.auth.transport.requests

key = json.load(open('backend/key.json'))
creds = service_account.Credentials.from_service_account_info(key).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
request = google.auth.transport.requests.Request()
creds.refresh(request)
token = creds.token

# Hardcoded operation ID from earlier
op_id = "106a3d2a-7406-45e1-8577-0e312ace3011"
endpoint = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{key['project_id']}/locations/us-central1/operations/{op_id}"

req = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'): print(e.read().decode())
