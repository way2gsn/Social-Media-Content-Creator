from google.cloud import texttospeech
from google.oauth2 import service_account
import json

key = json.load(open('backend/key.json'))
creds = service_account.Credentials.from_service_account_info(key)
client = texttospeech.TextToSpeechClient(credentials=creds)

voices = client.list_voices()
for voice in voices.voices:
    if "IN" in voice.language_codes[0]:
        print(f"Name: {voice.name}")
