import asyncio, sys, os
sys.path.append('backend')
from gcp_client import get_gcp_client

async def main():
    gcp = get_gcp_client()
    try:
        res = await gcp.generate_text("Explain Hinglish in 10 words.")
        print(f"RESULT: {res}")
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(main())
