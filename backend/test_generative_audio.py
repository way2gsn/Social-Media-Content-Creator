import asyncio
import sys
import os
sys.path.append('backend')
from gcp_client import get_gcp_client

async def main():
    gcp = get_gcp_client()
    text = "West Bengal. 2011. Ek aurat white saree mein, hawai chappal pehne, Kolkata ki streets par chal rahi hai. Koi security nahi, koi convoy nahi, koi drama nahi. Bas ek aurat aur uski chappal. Aur ye wahi aurat hai jisne 34 saal ka Communist empire tod diya. Sirf apne dum par. Mamata Banerjee."
    
    print("🎤 Generating High-End Generative Audio (Gemini 2.5 Flash)...")
    audio_bytes, timepoints = await gcp.generate_tts(text)
    
    if audio_bytes:
        output_path = "static/output/test_voice.mp3"
        os.makedirs("static/output", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        print(f"✅ Success! Audio saved to: {output_path}")
        print(f"⏱️ Estimated Timepoints: {len(timepoints)}")
    else:
        print("❌ Failed to generate audio. Check logs for GCP errors.")

if __name__ == "__main__":
    asyncio.run(main())
