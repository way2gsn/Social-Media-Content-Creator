import os
import requests
import httpx
import asyncio
import traceback
import urllib3
from datetime import datetime

# Disable insecure request warnings for the 3rd party proxy step
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InstagramAPIEngine:
    def __init__(self, access_token=None, business_id=None):
        self.access_token = access_token
        self.business_id = business_id
        self.api_version = "v21.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    async def upload_to_proxy(self, file_path):
        """
        Uploads a local file to a temporary public proxy.
        Uses multiple strategies for high reliability.
        """
        if not os.path.exists(file_path):
            return None, f"File not found: {file_path}"
        
        loop = asyncio.get_event_loop()
        is_video = file_path.lower().endswith(('.mp4', '.mov', '.m4v'))
        content_type = "video/mp4" if is_video else "image/jpeg"
        
        # Strategy 1: Telegra.ph (Very fast, direct links, trusted by Meta)
        if not is_video:
            try:
                def sync_telegraph():
                    with open(file_path, "rb") as f:
                        return requests.post("https://telegra.ph/upload", files={"file": (os.path.basename(file_path), f, content_type)}, timeout=30, verify=False)
                
                response = await loop.run_in_executor(None, sync_telegraph)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        path = data[0].get("src")
                        if path:
                            url = f"https://telegra.ph{path}"
                            print(f"DEBUG: Proxy Success (Telegraph): {url}")
                            return url, "Success"
            except Exception as e:
                print(f"DEBUG: Telegraph failed: {e}")

        # Strategy 2: Catbox.moe
        try:
            def sync_catbox():
                with open(file_path, "rb") as f:
                    files = {
                        "reqtype": (None, "fileupload"),
                        "fileToUpload": (os.path.basename(file_path), f, content_type)
                    }
                    return requests.post("https://catbox.moe/user/api.php", files=files, timeout=60, verify=False)
            
            response = await loop.run_in_executor(None, sync_catbox)
            if response.status_code == 200 and response.text.startswith("http"):
                url = response.text.strip()
                print(f"DEBUG: Proxy Success (Catbox): {url}")
                return url, "Success"
        except Exception as e:
            print(f"DEBUG: Catbox failed: {e}")

        # Strategy 3: TmpFiles.org
        try:
            def sync_tmpfiles():
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, content_type)}
                    return requests.post("https://tmpfiles.org/api/v1/upload", files=files, timeout=60, verify=False)
            
            response = await loop.run_in_executor(None, sync_tmpfiles)
            if response.status_code == 200:
                data = response.json()
                url = data.get("data", {}).get("url")
                if url:
                    # Foolproof reconstruction: Slice and build to avoid any double-paths
                    file_id_path = url.split("tmpfiles.org/")[-1]
                    if file_id_path.startswith("dl/"):
                        file_id_path = file_id_path[3:] # Strip existing dl/ if present
                    
                    clean_url = f"https://tmpfiles.org/dl/{file_id_path}"
                    print(f"DEBUG: Proxy Success (TmpFiles - Reconstructed): {clean_url}")
                    return clean_url, "Success"
        except Exception as e:
            print(f"DEBUG: TmpFiles failed: {e}")

        return None, "All proxy bridges failed. Check connectivity."

        return None, "All proxy bridges failed (Catbox, File.io, TmpFiles). Check server logs."

    async def create_reels_container(self, video_url, caption):
        """Step 1: Create a media container for a Reels video."""
        if not self.access_token or not self.business_id:
            return None, "Missing API credentials"

        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self.access_token
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return None, f"Reels Container Error: {error_msg}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def create_story_container(self, asset_url, is_video=False):
        """Step 1: Create a media container for an Instagram Story."""
        if not self.access_token or not self.business_id:
            return None, "Missing API credentials"

        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "media_type": "STORIES",
            "access_token": self.access_token
        }
        if is_video:
            payload["video_url"] = asset_url
        else:
            payload["image_url"] = asset_url

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return None, f"Story Container Error: {error_msg}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def create_media_container(self, image_url, caption):
        """Step 1: Create a media container for a single image."""
        if not self.access_token or not self.business_id:
            return None, "Missing API credentials"

        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "image_url": image_url,
            "caption": caption,
            "access_token": self.access_token
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return None, f"Container Error: {error_msg}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def create_carousel_item_container(self, image_url):
        """Creates an item container for a single slide in a carousel."""
        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": self.access_token
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                # Log full error for diagnostics and pass back raw data if possible
                error_detail = f"{error_msg} | RAW: {data}"
                print(f"DEBUG: Instagram Carousel Item Error: {data}")
                return None, f"Item Container Error: {error_detail}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def create_carousel_container(self, item_ids, caption):
        """Creates the master carousel container linking multiple items."""
        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": self.access_token
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return None, f"Carousel Container Error: {error_msg}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def create_video_container(self, video_url, caption, media_type="REELS"):
        """Creates a media container for a video/reel."""
        if not self.access_token or not self.business_id:
            return None, "Missing API credentials"

        url = f"{self.base_url}/{self.business_id}/media"
        payload = {
            "media_type": media_type,
            "video_url": video_url,
            "caption": caption,
            "access_token": self.access_token
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return data["id"], "Success"
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return None, f"Video Container Error: {error_msg}"
            except Exception as e:
                return None, f"Request Error: {str(e)}"

    async def check_container_status(self, container_id):
        """Check if the container is finished processing."""
        url = f"{self.base_url}/{container_id}"
        params = {
            "fields": "status_code,error_message",
            "access_token": self.access_token
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Wait up to 5 minutes (60 attempts * 5s) for larger files
                for _ in range(60): 
                    response = await client.get(url, params=params)
                    data = response.json()
                    status = data.get("status_code")
                    if status == "FINISHED":
                        return True, "Finished"
                    if status == "ERROR":
                        return False, f"Processing failed on Instagram's end: {data.get('error', {}).get('message', 'Unknown error')}"
                    await asyncio.sleep(5)
                return False, "Processing timed out."
            except Exception as e:
                return False, str(e)

    async def publish_media(self, container_id):
        """Step 2: Publish the media container."""
        url = f"{self.base_url}/{self.business_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.access_token
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, data=payload)
                data = response.json()
                if "id" in data:
                    return True, "Successfully published!"
                return False, f"Publish Error: {data.get('error', {}).get('message', 'Unknown error')}"
            except Exception as e:
                return False, str(e)
