import asyncio
import os
from explainer_engine import ExplainerEngine

async def test_explainer_carousel():
    print("--- Testing Explainer Carousel Logic ---")
    engine = ExplainerEngine()
    
    # Topic likely to have multiple points
    topic = "ISRO Chandrayaan 4 mission"
    
    print(f"Generating explainer carousel for: {topic}")
    # generate_explainer now returns (results, status)
    results, status = await engine.generate_explainer(topic, count=1)
    
    if results:
        print(f"SUCCESS: Generated {len(results)} slides.")
        for r in results:
            print(f"Slide: {r}")
    else:
        print(f"FAILED: {status}")

if __name__ == "__main__":
    asyncio.run(test_explainer_carousel())
