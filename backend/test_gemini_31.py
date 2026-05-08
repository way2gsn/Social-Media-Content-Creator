import asyncio, sys, os
sys.path.append('backend')
from gcp_client import get_gcp_client
from vertexai.generative_models import GenerativeModel

async def main():
    gcp = get_gcp_client()
    models_to_try = ["gemini-3.1-flash", "gemini-3.1-flash-001"]
    
    for model_id in models_to_try:
        print(f"Testing {model_id}...")
        try:
            model = GenerativeModel(model_id)
            # Test audio capability
            try:
                config = {"response_mime_type": "audio/mpeg"}
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, lambda: model.generate_content("Say hello in 2 words", generation_config=config))
                print(f"🔊 {model_id} supports audio/mpeg!")
            except Exception as audio_err:
                print(f"❌ {model_id} does not support audio/mpeg: {audio_err}")
                
        except Exception as e:
            print(f"❌ {model_id} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
