import os
import json
import os
# CRITICAL: Prevent gRPC fork conflicts globally for background tasks
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"

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
        self.credentials = service_account.Credentials.from_service_account_info(self.key_data).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        
        print(f"GCP: Initializing in {self.location} with gemini-2.5-flash...")
        try:
            vertexai.init(project=self.project_id, location=self.location, credentials=self.credentials)
            
            from vertexai.generative_models import SafetySetting, HarmCategory, HarmBlockThreshold
            self.safety_settings = [
                SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_NONE),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_NONE),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_NONE),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            ]

            self.text_model = GenerativeModel("gemini-2.5-flash")
            self.pro_model = GenerativeModel("gemini-2.5-flash") 
            # Load image model — imagen-3.0-fast-generate-001
            try:
                self.image_model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")
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
        
        # Configuration - Lower temperature for better stability/JSON compliance
        config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "max_output_tokens": 4096
        }

        # Note: In vertexai, system_instruction is passed during model initialization 
        # but for simplicity here we prepend it if provided
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        # Quota Resilience Strategy: Flash-to-Flash Fallback (Best for this project)
        model_name = "gemini-2.5-flash" # Primary
        max_retries = 5
        retry_delay = 3
        current_model_id = model_name
        
        for attempt in range(max_retries):
            try:
                # Emergency Fallback: If 2.5 is exhausted, switch to 1.5-flash (different quota)
                if attempt >= 3:
                    current_model_id = "gemini-1.5-flash"
                
                model = GenerativeModel(current_model_id)
                
                # Running in thread since vertexai is blocking
                import asyncio
                import re
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: model.generate_content(
                        full_prompt, 
                        generation_config=config,
                        safety_settings=self.safety_settings
                    )
                )
                text = response.text if response and hasattr(response, 'text') else ""
                if not text:
                    raise Exception("Empty response from AI")
                break # Success
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "Resource exhausted" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        print(f"⚠️ Quota hit (429) for {current_model_id}. Emergency retry in {wait_time}s... ({attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                print(f"GCP Text Error on {current_model_id}: {e}")
                text = ""
                # If we've already tried the fallback model and still fail, break
                if current_model_id == "gemini-1.5-flash":
                    break
        
        # Process result outside the loop
        if text and json_mode:
            text_content = text.strip()
            # Remove ```json ... ``` or ``` ... ``` wrappers
            cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text_content)
            cleaned = re.sub(r'\n?```\s*$', '', cleaned)
            return cleaned.strip()
        
        return text if text else ""

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

    async def generate_tts(self, text: str, voice_name: str = "gemini-2.5-flash-tts", is_ssml: bool = False) -> tuple[bytes, list]:
        """Generates High-End Gemini 2.5 Flash TTS audio via GenAI SDK."""
        try:
            import asyncio
            import os
            from google import genai
            from google.genai import types
            
            # Reset environment to prevent gRPC fork conflicts and ensure auth
            os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"
            
            # Ensure the GenAI SDK knows where the key is
            base_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(base_dir, "key.json")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
            
            # Initialize GenAI Client FRESH for each request to avoid FD poll issues
            client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            
            # Use Aoede (Female) or Charon (Male) for natural documentary tone
            voice_profile = "Aoede" if "Mamata" in text or "woman" in text.lower() else "Charon"
            
            # Proper nesting for SpeechConfig as expected by the Google GenAI SDK
            # Removing speaking_rate for now as it's causing validation errors in this SDK version
            speech_config_dict = {
                'voice_config': {
                    'prebuilt_voice_config': {
                        'voice_name': voice_profile
                    }
                }
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-2.5-flash-tts",
                    contents=text,
                    config=types.GenerateContentConfig(
                        speech_config=speech_config_dict,
                        temperature=0.3
                    )
                )
            )
            
            audio_bytes = None
            if response and response.candidates:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        raw_data = part.inline_data.data
                        
                        # Convert Raw PCM to playable MP3 using ffmpeg
                        import subprocess
                        import tempfile
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as f_in:
                            f_in.write(raw_data)
                            temp_in = f_in.name
                            
                        # Force 1.4x speed for high-density professional documentary pacing
                        if is_ssml:
                            # Wrap existing SSML in prosody for speed control
                            text = text.replace("<speak>", '<speak><prosody rate="1.4">').replace("</speak>", "</prosody></speak>")
                        else:
                            text = f'<speak><prosody rate="1.4">{text}</prosody></speak>'
                            is_ssml = True
                            
                        temp_out = temp_in.replace(".raw", ".mp3")
                        
                        # ffmpeg command for PCM 16-bit 24kHz mono to MP3
                        cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", temp_in, temp_out]
                        subprocess.run(cmd, capture_output=True)
                        
                        if os.path.exists(temp_out):
                            with open(temp_out, "rb") as f_out:
                                audio_bytes = f_out.read()
                            
                            # Cleanup
                            os.remove(temp_in)
                            os.remove(temp_out)
                        break
            
            # Word-timing estimation for Gemini TTS (Smart Sync)
            words = text.split()
            duration = len(words) * 0.45 # Adjusted for Gemini's natural flow
            timepoints = []
            for i, word in enumerate(words):
                timepoints.append({"mark_name": f"w_{i}", "time_seconds": (i / len(words)) * duration})

            return audio_bytes, timepoints
        except Exception as e:
            print(f"GCP Gemini 2.5 TTS Error: {e}")
            # Fallback to standard high-quality Neural2 if GenAI fails
            return await self.generate_tts_fallback(text)

    async def generate_tts_fallback(self, text: str) -> tuple[bytes, list]:
        """Standard fallback logic."""
        try:
            import asyncio
            from google.cloud import texttospeech_v1beta1 as texttospeech
            client = texttospeech.TextToSpeechClient(credentials=self.credentials)
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code="en-IN", name="en-IN-Neural2-D")
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            request = texttospeech.SynthesizeSpeechRequest(input=synthesis_input, voice=voice, audio_config=audio_config)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: client.synthesize_speech(request=request))
            return response.audio_content, []
        except:
            return None, []

    async def ensure_veo_bucket(self):
        try:
            import asyncio
            from google.cloud import storage
            
            bucket_name = f"{self.project_id}-veo-output"
            
            def _create_bucket():
                client = storage.Client(credentials=self.credentials, project=self.project_id)
                bucket = client.bucket(bucket_name)
                if not bucket.exists():
                    print(f"☁️ [GCS] Creating bucket {bucket_name} for Veo outputs...")
                    client.create_bucket(bucket, location=self.location)
                return bucket_name
                
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _create_bucket)
        except Exception as e:
            print(f"GCS Bucket Error: {e}")
            return None

    async def generate_veo_video(self, prompt: str) -> bytes:
        """
        Generates a cinematic video clip using Vertex AI Veo 3.1 Fast.
        Uses predictLongRunning REST API and GCS to handle async video generation.
        """
        try:
            import asyncio
            import json
            import urllib.request
            import ssl
            import google.auth.transport.requests
            import time
            from google.cloud import storage

            bucket_name = await self.ensure_veo_bucket()
            if not bucket_name: 
                print("⚠️ [VEO] Could not create or access GCS bucket.")
                return None
            
            import uuid
            file_name = f"veo_output_{uuid.uuid4().hex[:8]}.mp4"
            gcs_uri = f"gs://{bucket_name}/{file_name}"
            
            model_name = "veo-3.1-generate-001"
                
            # Force get token
            request = google.auth.transport.requests.Request()
            self.credentials.refresh(request)
            token = self.credentials.token

            endpoint = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model_name}:predictLongRunning"
            
            payload = {
                "instances": [
                    {
                        "prompt": prompt
                    }
                ],
                "parameters": {
                    "aspectRatio": "9:16",
                    "personGeneration": "ALLOW_ALL",
                    "outputConfig": {"gcsDestination": {"uri": gcs_uri}}
                }
            }
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers=headers)
            
            loop = asyncio.get_event_loop()
            
            # Start LRO
            def _start_lro():
                context = ssl.create_default_context()
                with urllib.request.urlopen(req, context=context) as response:
                    return json.loads(response.read())
                    
            op_data = await loop.run_in_executor(None, _start_lro)
            if "name" not in op_data: 
                print("⚠️ [VEO] Failed to start Long Running Operation.")
                return None
            
            op_name = op_data["name"]
            print(f"🎥 [VEO] Operation started: {op_name}")
            print(f"⏳ [VEO GCS] Monitoring gs://{bucket_name}/{file_name} for completion...")

            # 3. Poll GCS directly instead of the broken Operation API
            storage_client = storage.Client(credentials=self.credentials, project=self.project_id)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            timeout_seconds = 600  # 10 minutes max
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                # blob.exists() is a network call, run in executor
                exists = await loop.run_in_executor(None, blob.exists)
                if exists:
                    print(f"✅ [VEO GCS] Video detected! Downloading...")
                    video_data = await loop.run_in_executor(None, blob.download_as_bytes)
                    # Clean up
                    try:
                        await loop.run_in_executor(None, blob.delete)
                    except:
                        pass
                    return video_data
                
                await asyncio.sleep(15) # Poll every 15 seconds
                elapsed = int(time.time() - start_time)
                if elapsed % 60 == 0:
                    print(f"⏳ [VEO GCS] Still waiting... ({elapsed}s elapsed)")

            print("❌ [VEO GCS] Timeout waiting for video to appear in GCS.")
            return None
            
        except Exception as e:
            print(f"GCP Veo Video Error: {e}")
            if hasattr(e, 'read'): print(e.read().decode())
            return None

# Singleton instance
gcp_client = None

def get_gcp_client():
    global gcp_client
    if gcp_client is None:
        gcp_client = GCPClient()
    return gcp_client
