import asyncio, httpx, json

async def test():
    url = "https://duckduckgo.com/i.js"
    params = {"q": "Narendra Modi News", "o": "json"}
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        data = r.json()
        if "results" in data and len(data["results"]) > 0:
            print("Keys found:", data["results"][0].keys())
            print("Sample title:", data["results"][0].get("title"))
            print("Sample source:", data["results"][0].get("source"))

if __name__ == "__main__":
    asyncio.run(test())
