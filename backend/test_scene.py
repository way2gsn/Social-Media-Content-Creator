import asyncio
from video_engine import CinematicVideoEngine
import os

async def main():
    engine = CinematicVideoEngine()
    print("Testing scene generation...")
    scene = {
        "narration": "Doston, aaj ki duniya faster than ever change ho rahi hai.",
        "veo_prompt": "Cinematic drone shot over a futuristic neon city at night, 4k."
    }
    os.makedirs("static/output/test_session", exist_ok=True)
    res = await engine._process_scene(scene, 0, "static/output/test_session", "hi-IN-Neural2-D")
    print("Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
