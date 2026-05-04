import asyncio
import os
import json
import base64
from explainer_engine import ExplainerEngine

async def test_explainer_render():
    print("--- Testing Explainer Rendering Directly ---")
    engine = ExplainerEngine()
    
    # Mock Plan
    plan = {
        "character_name": "Narendra Modi",
        "headline": "INDIA'S STRATEGIC HEATWAVE RESPONSE",
        "points": [
            "PM Modi chairs high-level review meeting on preparedness.",
            "States urged to conduct regular fire safety audits.",
            "Focus on health infrastructure and essential medicine stocks."
        ],
        "style": "EXPLAINER",
        "theme": "POLITICS"
    }
    
    # Mock Cutout (just a transparent placeholder for now to test layout)
    # Actually, let's use a real image and process it
    img_url = "https://img.etimg.com/thumb/msid-109015049,width-1200,height-900,resizemode-4,imgsize-39726/narendra-modi.jpg"
    
    print("Processing cutout...")
    cutout_b64 = await engine.process_cutout(img_url, side="left")
    
    print("Rendering...")
    os.makedirs("test_output", exist_ok=True)
    
    template_path = "templates/explainer/EDITORIAL/EXPLAINER.html"
    with open(template_path, 'r') as f:
        template_str = f.read()

    from jinja2 import Template
    render_data = {
        **plan,
        "cutout_base64": cutout_b64,
        "original_image": img_url,
        "language": "english",
        "silhouette": False,
        "slide_index": "01",
        "view_height": 1350
    }
    
    html_content = Template(template_str).render(**render_data)
    
    # Save HTML for debugging
    with open("test_output/explainer_test.html", "w") as f:
        f.write(html_content)
        
    print("SUCCESS: HTML saved to test_output/explainer_test.html")
    print("Now you can preview it or I can try to screenshot it if playwright is working.")

if __name__ == "__main__":
    asyncio.run(test_explainer_render())
