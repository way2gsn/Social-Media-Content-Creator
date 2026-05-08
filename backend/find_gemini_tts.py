from google.cloud import texttospeech_v1beta1 as texttospeech
import json, os

def main():
    key_path = "backend/key.json"
    with open(key_path, 'r') as f:
        key_data = json.load(f)
    
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_info(key_data)
    client = texttospeech.TextToSpeechClient(credentials=credentials)
    
    voices = client.list_voices().voices
    gemini_voices = [v.name for v in voices if "gemini" in v.name.lower() or "3.1" in v.name.lower()]
    print(f"GEMINI VOICES: {gemini_voices}")

if __name__ == "__main__":
    main()
