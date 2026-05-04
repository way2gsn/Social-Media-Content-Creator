import os
import asyncio
from playwright.async_api import async_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "user_data", "instagram")

class InstagramUploader:
    def __init__(self):
        os.makedirs(USER_DATA_DIR, exist_ok=True)

    async def launch_browser(self, headless=True):
        p = await async_playwright().start()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless,
            viewport={'width': 1280, 'height': 720}
        )
        return p, context

    async def setup_login(self):
        """Opens a visible browser for the user to login manually."""
        print("DEBUG: Opening Instagram for manual login...")
        p, context = await self.launch_browser(headless=False)
        page = await context.new_page()
        await page.goto("https://www.instagram.com/", wait_until="networkidle")
        
        print("IMPORTANT: Please log in to Instagram in the opened browser window.")
        print("The session will be saved automatically when you close the browser or stop the script.")
        
        # Wait for the user to close the page or for a timeout
        try:
            while not page.is_closed():
                await asyncio.sleep(1)
        except: pass
        
        await context.close()
        await p.stop()

    async def upload_post(self, image_path, caption):
        """Automates the upload of a post to Instagram."""
        print(f"DEBUG: Starting automated upload for {image_path}")
        abs_image_path = os.path.abspath(image_path)
        
        p, context = await self.launch_browser(headless=True)
        page = await context.new_page()
        
        try:
            await page.goto("https://www.instagram.com/", wait_until="networkidle")
            
            # Check if logged in (look for the 'New post' button)
            try:
                await page.wait_for_selector('svg[aria-label="New post"]', timeout=10000)
            except:
                await context.close()
                await p.stop()
                return False, "Not logged in. Please run setup first."

            # 1. Click 'Create' / 'New post'
            await page.click('svg[aria-label="New post"]')
            await asyncio.sleep(2)
            
            # 2. Upload File (handle the file input)
            async with page.expect_file_chooser() as fc_info:
                # Sometimes the 'Select from computer' button is needed
                try:
                    await page.click('button:has-text("Select from computer")', timeout=5000)
                except:
                    # Fallback to clicking the SVG if button is hidden
                    await page.click('svg[aria-label="Icon to represent media such as images or videos"]')
                    
            file_chooser = await fc_info.value
            await file_chooser.set_files(abs_image_path)
            await asyncio.sleep(3)
            
            # 3. Next -> Next -> Caption -> Share
            # Step: Crop/Ratio (Click Next)
            await page.click('div[role="button"]:has-text("Next")')
            await asyncio.sleep(2)
            
            # Step: Filters (Click Next)
            await page.click('div[role="button"]:has-text("Next")')
            await asyncio.sleep(2)
            
            # Step: Caption
            await page.wait_for_selector('div[aria-label="Write a caption..."]')
            await page.fill('div[aria-label="Write a caption..."]', caption)
            await asyncio.sleep(2)
            
            # Step: Share
            await page.click('div[role="button"]:has-text("Share")')
            
            # Wait for completion (look for 'Your post has been shared')
            await page.wait_for_selector('text="Your post has been shared"', timeout=30000)
            print("DEBUG: Upload successful!")
            
            await context.close()
            await p.stop()
            return True, "Success"
            
        except Exception as e:
            error_msg = f"Upload Error: {str(e)}"
            print(f"DEBUG: {error_msg}")
            await context.close()
            await p.stop()
            return False, error_msg

if __name__ == "__main__":
    # Test Setup
    uploader = InstagramUploader()
    asyncio.run(uploader.setup_login())
