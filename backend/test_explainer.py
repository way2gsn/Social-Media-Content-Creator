import asyncio
import os
from explainer_engine import ExplainerEngine

async def test_explainer():
    print("--- Testing New Explainer Aesthetics ---")
    engine = ExplainerEngine()
    
    # We'll just trigger a real generation for a trending topic
    # This will fetch real news and use real images
    topic = "Narendra Modi"
    
    print(f"Generating explainer for: {topic}")
    output_path = await engine.generate_explainer(topic, count=1)
    
    if output_path:
        print(f"SUCCESS: Explainer saved to {output_path}")
    else:
        print("FAILED to generate explainer.")

if __name__ == "__main__":
    asyncio.run(test_explainer())
