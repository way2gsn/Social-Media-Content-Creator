import asyncio
from playwright.async_api import async_playwright

async def test_scraper(url):
    print(f"Testing URL: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            # Go to Google News link
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)
            print(f"Final URL after redirects: {page.url}")
            
            # Extract meta tags
            image = await page.evaluate("""() => {
                const getMeta = (name) => {
                    const m = document.querySelector(`meta[property="${name}"]`) || 
                              document.querySelector(`meta[name="${name}"]`) ||
                              document.querySelector(`meta[itemprop="${name}"]`);
                    return m ? m.content : null;
                };
                return getMeta('og:image') || getMeta('twitter:image');
            }""")
            print(f"Detected Hero Image: {image}")
            
            # Check for generic logos
            if image and ("logo" in image.lower() or "google" in image.lower()):
                print("Warning: Detected a logo as hero image.")
                
        except Exception as e:
            print(f"Error during test: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    # Test link from RSS
    test_url = "https://news.google.com/rss/articles/CBMisAFBVV95cUxNeFlka25qYlZ4ekIwbkpsMzhZOHF1TV9Kajd3UmhLTlhlM0Z5bU84OHIxeW1Wb1NncUNlTDRuY3Brb2dZSWp3ZXRndjZ2QkRUMHRlVzI1WURoXzBicml0dmk0MFRub2lIcUdndU94M212RER2ZGlrUmF1RElTMTZ6WllqU2Z2U1h2UGpZOU9sMTBrd2NoOEdTbzJzZnpMZm4yMGFSTlVQOWljU1ZlSkFpRQ?oc=5"
    asyncio.run(test_scraper(test_url))
