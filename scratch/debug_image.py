import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join('/Volumes/Ghanshyam SSD1/Social Media Content Creator', 'backend'))

from gcp_client import GCPClient

async def debug_image():
    client = GCPClient()
    # Wait for initialization
    await asyncio.sleep(2)
    
    prompt = "A high-stakes political debate in India, cinematic lighting, 9:16 aspect ratio"
    print(f"DEBUG: Testing Stable Image Gen with prompt: {prompt}")
    
    try:
        img_bytes = await client.generate_image(prompt, aspect_ratio="9:16")
        if img_bytes:
            print(f"✅ SUCCESS: Generated {len(img_bytes)} bytes")
            with open("/Volumes/Ghanshyam SSD1/Social Media Content Creator/scratch/debug_image_output.png", "wb") as f:
                f.write(img_bytes)
            print("✅ Image saved to scratch/debug_image_output.png")
        else:
            print("❌ FAILURE: Received None from generate_image")
    except Exception as e:
        print(f"❌ CRITICAL EXCEPTION: {e}")

if __name__ == "__main__":
    scratch_dir = "/Volumes/Ghanshyam SSD1/Social Media Content Creator/scratch"
    if not os.path.exists(scratch_dir): os.makedirs(scratch_dir)
    asyncio.run(debug_image())
