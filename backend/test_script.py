import asyncio
from video_engine import CinematicVideoEngine

async def main():
    engine = CinematicVideoEngine()
    print("Generating script...")
    res = await engine.generate_script("The history of AI")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
