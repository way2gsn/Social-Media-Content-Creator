import os
import json
import base64
from google.oauth2 import service_account
import vertexai

# Smart Import for Vertex AI models (handles different library versions)
try:
    from vertexai.generative_models import GenerativeModel, Part
except ImportError:
    from vertexai.preview.generative_models import GenerativeModel, Part

try:
    from vertexai.vision_models import ImageGenerationModel, Image as VertexImage
except ImportError:
    try:
        from vertexai.preview.vision_models import ImageGenerationModel, Image as VertexImage
    except ImportError:
        # Fallback placeholder if entirely missing (prevents crash)
        ImageGenerationModel = None
        VertexImage = None

import io
from PIL import Image

class GCPClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GCPClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, key_path=None):
        if hasattr(self, 'initialized'):
            return
        
        if key_path is None:
            # Auto-resolve relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(base_dir, "key.json")
            
        with open(key_path, 'r') as f:
            self.key_data = json.load(f)
        
        self.project_id = self.key_data['project_id']
        self.location = "us-central1" # Original working region
        self.credentials = service_account.Credentials.from_service_account_info(self.key_data)
        
        print(f"GCP: Initializing in {self.location} with Secret Model gemini-2.5-flash...")
        try:
            vertexai.init(project=self.project_id, location=self.location, credentials=self.credentials)
            # This is the secret model that actually works for this project!
            self.text_model = GenerativeModel("gemini-2.5-flash")
            self.pro_model = GenerativeModel("gemini-2.5-flash") # Use same for pro
            
            # Load image model — imagen-3.0-generate-002 (imagegeneration@006 is EOL)
            try:
                self.image_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
            except Exception as img_err:
                print(f"GCP: imagen-3.0-generate-002 failed, trying fallback: {img_err}")
                self.image_model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")
            
            print("GCP: Vertex AI fully UNLOCKED.")
        except Exception as e:
            print(f"GCP CRITICAL ERROR: {str(e)}")

        self.initialized = True
    async def generate_text(self, prompt, system_instruction=None, json_mode=True, use_pro=False):
        """Generates text using Gemini 1.5 Flash or Pro."""
        model = self.pro_model if use_pro else self.text_model
        
        # Configuration
        config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "max_output_tokens": 2048,
        }
        
        # config["response_mime_type"] = "application/json" removed for compatibility with older SDK versions

        # Note: In vertexai, system_instruction is passed during model initialization 
        # but for simplicity here we prepend it if provided
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        try:
            # Running in thread since vertexai is blocking
            import asyncio
            import re
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: model.generate_content(full_prompt, generation_config=config)
            )
            text = response.text if response and hasattr(response, 'text') else ""
            
            # gemini-2.5-flash wraps JSON in markdown code fences — strip them
            if text and json_mode:
                text_content = text.strip()
                # Remove ```json ... ``` or ``` ... ``` wrappers
                cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text_content)
                cleaned = re.sub(r'\n?```\s*$', '', cleaned)
                return cleaned.strip()
            
            return text if text else ""
        except Exception as e:
            print(f"GCP Text Error: {e}")
            return ""

    async def analyze_image(self, image_path: str, prompt: str) -> str:
        """Analyzes an image using Gemini Flash Vision capabilities."""
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                
            mime_type = "image/jpeg"
            if image_path.lower().endswith(".png"): mime_type = "image/png"
            elif image_path.lower().endswith(".webp"): mime_type = "image/webp"
            
            image_part = Part.from_data(image_bytes, mime_type=mime_type)
            
            import asyncio
            import re
            loop = asyncio.get_event_loop()
            
            model = self.pro_model
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content([image_part, prompt])
            )
            
            text = response.text if response and hasattr(response, 'text') else ""
            if text:
                text_content = text.strip()
                cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text_content)
                cleaned = re.sub(r'\n?```\s*$', '', cleaned)
                return cleaned.strip()
            return ""
        except Exception as e:
            print(f"GCP Vision Error: {e}")
            return ""


    async def generate_image(self, prompt, aspect_ratio="9:16"):
        """Generates an image using Imagen 3."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Aspect ratio mapping for Imagen
            ar_map = {"9:16": "9:16", "4:5": "3:4", "1:1": "1:1"}
            target_ar = ar_map.get(aspect_ratio, "9:16")

            async def _do_gen(ar_val):
                return await loop.run_in_executor(
                    None,
                    lambda: self.image_model.generate_images(
                        prompt=prompt,
                        number_of_images=1,
                        language="en",
                        aspect_ratio=ar_val,
                        safety_filter_level="block_only_high",
                        person_generation="allow_all"
                    )
                )

            try:
                response = await _do_gen(target_ar)
            except TypeError as te:
                if "aspect_ratio" in str(te):
                    print(f"DEBUG: SDK doesn't support aspect_ratio. Retrying without it...")
                    # Fallback for older SDKs
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.image_model.generate_images(
                            prompt=prompt,
                            number_of_images=1,
                            language="en"
                        )
                    )
                else: raise te

            if response and response.images:
                # Get image bytes
                img_bytes = response.images[0]._image_bytes
                return img_bytes
        except Exception as e:
            print(f"GCP Image Error: {e}")
            return None

    async def remove_background(self, image_bytes):
        """
        Removes background using Vertex AI's native Image Editing capabilities.
        Uses Imagen 3's background removal feature to ensure 100% cloud-native AI.
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Note: For strict background removal, we use the image editing model
            # with an empty background prompt or specialized background swap mode
            # depending on the specific sub-version enabled in the project.
            # Here we use the latest Imagen editing capability.
            from vertexai.vision_models import Image as VertexImage
            
            input_image = VertexImage(image_bytes)
            
            response = await loop.run_in_executor(
                None,
                lambda: self.image_model.edit_image(
                    base_image=input_image,
                    prompt="transparent background, isolated subject",
                    edit_mode="background-removal", # Specialized mode for background removal
                    number_of_images=1
                )
            )
            
            if response and response.images:
                return response.images[0]._image_bytes
        except Exception as e:
            print(f"GCP Background Removal Error: {e}")
            # Fallback to returning original if AI fails (better than crash)
            return None 

# Singleton instance
gcp_client = None

def get_gcp_client():
    global gcp_client
    if gcp_client is None:
        gcp_client = GCPClient()
    return gcp_client
