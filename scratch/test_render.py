
import asyncio
import os
import sys
from playwright.async_api import async_playwright

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from glue import InstagramEngine, DatabaseManager

async def test_render():
    print("🚀 Starting Standalone Render Test...")
    engine = InstagramEngine()
    
    # Mock data
    data = {
        "headline": "TEST RENDER",
        "subtitle": "Checking Playwright Stability",
        "caption": "Test Caption",
        "image_url": "https://placehold.co/1080x1920",
        "is_ai_image": False,
        "view_height": 1920
    }
    
    template_path = "backend/templates/explainer/EDITORIAL/MODERN_EDITORIAL.html"
    with open(template_path, 'r') as f:
        template_str = f.read()
        
    filename = "test_render_output.jpg"
    
    print("📸 Calling engine.render_post...")
    try:
        path = await engine.render_post(data, template_str, filename, width=1080, height=1920, aspect_ratio="9:16")
        print(f"✅ Render result: {path}")
        if path:
            print("💾 Saving to database...")
            DatabaseManager.save_post("TEST TOPIC", "TEST HEADLINE", "TEST SUBTITLE", "TEST CAPTION", path, "TEST SOURCE")
            print("✅ Save successful!")
    except Exception as e:
        print(f"❌ Render failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_render())
