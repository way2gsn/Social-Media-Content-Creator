import asyncio
import os
import sys
from gcp_client import get_gcp_client

async def test_gcp():
    print("--- Testing GCP Connectivity ---")
    client = get_gcp_client()
    
    # Test 1: Gemini Text
    print("\n[1/2] Testing Gemini 1.5 Flash...")
    prompt = "Give me a one-line satirical headline about AI taking over the world."
    text = await client.generate_text(prompt, json_mode=False)
    if text:
        print(f"SUCCESS: {text.strip()}")
    else:
        print("FAILED: No response from Gemini.")

    # Test 2: Imagen 3
    print("\n[2/2] Testing Imagen 3...")
    prompt = "A cinematic editorial portrait of a robot writing on a typewriter, dramatic lighting, 8k."
    img_bytes = await client.generate_image(prompt, aspect_ratio="1:1")
    if img_bytes:
        os.makedirs("test_output", exist_ok=True)
        with open("test_output/test_imagen.png", "wb") as f:
            f.write(img_bytes)
        print(f"SUCCESS: Image saved to test_output/test_imagen.png ({len(img_bytes)} bytes)")
    else:
        print("FAILED: No image generated.")

if __name__ == "__main__":
    asyncio.run(test_gcp())
