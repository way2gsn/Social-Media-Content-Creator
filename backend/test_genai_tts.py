from google import genai
from google.genai import types
import json, os, asyncio

def main():
    key_path = "backend/key.json"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(key_path)
    
    with open(key_path, 'r') as f:
        key_data = json.load(f)
    
    client = genai.Client(
        vertexai=True,
        project=key_data['project_id'],
        location="us-central1"
    )
    
    text = "West Bengal. 2011. Ek aurat white saree mein, hawai chappal pehne, Kolkata ki streets par chal rahi hai. Mamata Banerjee."
    
    print("🎤 Generating Audio with Gemini 2.5 Flash TTS...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-tts",
            contents=text,
            config=types.GenerateContentConfig(
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Aoede" # Aoede is a very natural female voice
                        )
                    )
                )
            )
        )
        
        audio_bytes = None
        if response and response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_bytes = part.inline_data.data
                    print(f"✅ Success! Received {len(audio_bytes)} bytes.")
                    with open("static/output/test_voice.mp3", "wb") as f:
                        f.write(audio_bytes)
                    break
        if not audio_bytes:
            print("❌ No audio bytes in response.")
            
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    main()
