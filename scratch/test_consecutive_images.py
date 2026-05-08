import sys
import os
import asyncio
import time
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from gcp_client import GCPClient

async def run_test():
    client = GCPClient()
    prompts = [
        "A futuristic Indian city with flying rickshaws, cinematic lighting, 9:16 aspect ratio",
        "An Indian astronaut on Mars planting the Tricolor flag, hyper-realistic, 9:16",
        "A high-speed bullet train crossing a Himalayan bridge at sunset, 9:16",
        "A neon-lit Mumbai street in 2077 with cybernetic elements, 9:16"
    ]
    
    print(f"\n🚀 STARTING CONSECUTIVE IMAGE TEST (4 GENERATIONS)")
    print(f"Region Priority: us-central1 (Stable Imagen) -> global (Gemini 3.1)")
    print("-" * 60)
    
    results = []
    for i, prompt in enumerate(prompts):
        print(f"\n📸 GENERATION {i+1}/4")
        print(f"Prompt: {prompt[:60]}...")
        
        start_time = time.time()
        try:
            # We call the async generate_image method
            img_bytes = await client.generate_image(prompt, aspect_ratio="9:16")
            
            elapsed = time.time() - start_time
            if img_bytes:
                size_kb = len(img_bytes) // 1024
                filename = f"scratch/test_gen_{i+1}_{datetime.now().strftime('%H%M%S')}.png"
                with open(filename, "wb") as f:
                    f.write(img_bytes)
                
                print(f"✅ SUCCESS: Generated {size_kb}KB in {elapsed:.2f}s")
                print(f"📁 Saved to: {filename}")
                results.append(True)
            else:
                print(f"❌ FAILURE: Received None from generate_image after {elapsed:.2f}s")
                results.append(False)
        except Exception as e:
            print(f"💥 CRITICAL ERROR: {str(e)}")
            results.append(False)
            
        if i < 3:
            print(f"⏳ Waiting 5s before next attempt...")
            await asyncio.sleep(15)

    print("\n" + "=" * 60)
    print(f"📊 FINAL RESULTS: {sum(results)}/4 Successful")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_test())
