import asyncio
import os
import json
from glue import InstagramEngine, STATIC_DIR

async def test_single_post():
    engine = InstagramEngine()
    
    topic = "India and Japan forge data partnership for AI-ready smart cities"
    item = {
        'title': topic,
        'summary': "India and Japan have signed a major data sharing agreement to accelerate the development of AI-driven smart city infrastructure.",
        'link': "https://timesofindia.indiatimes.com/"
    }
    
    print(f"🚀 STARTING DIRECT TEST FOR: {topic}")
    print("-" * 50)
    
    try:
        path = await engine.generate_standard_post(item, topic, aspect_ratio="9:16", language="english")
        
        if path:
            print(f"\n✅ SUCCESS! Asset generated: {path}")
            abs_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
            print(f"📁 Full Path: {abs_path}")
            if os.path.exists(abs_path):
                print(f"📦 File Size: {os.path.getsize(abs_path)//1024}KB")
            else:
                print(f"⚠️ Warning: File not found at {abs_path} even though path was returned.")
        else:
            print("\n❌ FAILURE: Engine returned None (Silent Error)")
            
    except Exception as e:
        print(f"\n💥 CRITICAL EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_single_post())
