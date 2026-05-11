import os
import json
import os
# CRITICAL: Prevent gRPC fork conflicts globally for background tasks
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"

import base64
from google.oauth2 import service_account
import vertexai
from google import genai
from google.genai import types

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

    def __init__(self, key_path=None, location="us-central1"):
        if hasattr(self, 'initialized'):
            return
        
        if key_path is None:
            # Auto-resolve relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(base_dir, "key.json")
            
        with open(key_path, 'r') as f:
            self.key_data = json.load(f)
        
        self.project_id = self.key_data['project_id']
        self.location = location
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

            self.text_model_name = "gemini-2.5-flash"
            self.image_gen_model_name = "imagen-3.0-generate-002"
            self.text_model = GenerativeModel(self.text_model_name)
            self.pro_model = GenerativeModel("gemini-2.5-pro") 
            
            # 1. New GenAI Client for stable Multimodal (Gemini 3.1) - Primary for this user
            self.genai_client = genai.Client(
                vertexai=True, 
                project=self.project_id, 
                location=self.location,
                credentials=self.credentials
            )
            print("GCP: GenAI Client (Stable Multimodal) Ready.")

            # 2. Stable Imagen 3.0 Model (Fallback/Secondary)
            self.image_model = None
            try:
                self.image_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
                print("GCP: Imagen 3.0 STABLE Initialized.")
            except Exception as e:
                print(f"GCP: Imagen STABLE unavailable ({e}). Trying v6...")
                try:
                    self.image_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
                    print("GCP: Imagen Fallback (v6) Initialized.")
                except:
                    print("GCP: ALL Imagen legacy models unavailable in this region.")
            
            print("GCP: Vertex AI fully UNLOCKED.")
        except Exception as e:
            print(f"GCP CRITICAL ERROR: {str(e)}")

        self.initialized = True

    async def research_topic(self, topic: str) -> dict:
        """Research a topic using Gemini + Google Search Grounding.
        Returns: {summary: str, sources: [{title, url}], facts: [str]}
        """
        import asyncio
        loop = asyncio.get_event_loop()
        
        research_prompt = f"""You are an investigative journalist researching: "{topic}"

Search the web and compile a comprehensive research brief with:
1. KEY FACTS: List 5-8 specific, verifiable data points with numbers, dates, and statistics.
2. SOURCES: For each fact, note the exact source name (e.g., "Reuters", "NDTV", "Economic Times").
3. CONTEXT: Provide background context that explains why this topic matters right now.
4. RECENT DEVELOPMENTS: What happened in the last 7 days related to this topic?

Be specific. Use real numbers. Cite real reports. This will be used to create a factual documentary script.
Format as a structured research brief, NOT JSON."""

        print(f"🔍 [RESEARCH] Searching web for: {topic}...")
        
        locations = ["us-central1", "europe-west4", "global"]
        
        for loc in locations:
            try:
                temp_client = genai.Client(
                    vertexai=True,
                    project=self.project_id,
                    location=loc,
                    credentials=self.credentials
                )
                
                response = await loop.run_in_executor(
                    None,
                    lambda: temp_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=research_prompt,
                        config=types.GenerateContentConfig(
                            tools=[
                                types.Tool(google_search=types.GoogleSearch())
                            ],
                            temperature=0.1,
                            max_output_tokens=4096
                        )
                    )
                )
                
                if not response or not response.text:
                    continue
                
                result = {
                    "summary": response.text.strip(),
                    "sources": [],
                    "source_urls": []
                }
                
                # Extract grounding metadata (source URLs)
                try:
                    candidate = response.candidates[0]
                    if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks:
                        seen_titles = set()
                        for chunk in candidate.grounding_metadata.grounding_chunks:
                            if chunk.web and chunk.web.title and chunk.web.title not in seen_titles:
                                seen_titles.add(chunk.web.title)
                                result["sources"].append({
                                    "title": chunk.web.title,
                                    "url": chunk.web.uri or ""
                                })
                                if chunk.web.uri:
                                    result["source_urls"].append(chunk.web.uri)
                        
                        print(f"📰 [RESEARCH] Found {len(result['sources'])} sources:")
                        for s in result["sources"][:5]:
                            print(f"   📄 {s['title']}")
                except Exception as meta_err:
                    print(f"⚠️ [RESEARCH] Could not extract grounding metadata: {meta_err}")
                
                return result
                
            except Exception as e:
                print(f"⚠️ [RESEARCH] Error in {loc}: {e}")
                continue
        
        print(f"⚠️ [RESEARCH] All regions failed. Proceeding without research.")
        return {"summary": "", "sources": [], "source_urls": []}

    async def extract_article_images(self, source_urls: list) -> list:
        """Fetch Open Graph images from article URLs.
        Returns list of {url, image_bytes, mime_type} dicts.
        """
        import asyncio
        import urllib.request
        import urllib.error
        import re
        import ssl
        
        loop = asyncio.get_event_loop()
        images = []
        
        if not source_urls:
            return images
        
        print(f"🖼️ [RESEARCH] Extracting images from {len(source_urls)} source articles...")
        
        ctx = ssl.create_default_context()
        
        def _fetch_og_image(url):
            """Fetch the OG image from a single URL."""
            try:
                # Follow redirects to get the actual article URL
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'
                })
                with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                    # Only read first 50KB to find OG tags
                    html = resp.read(50000).decode('utf-8', errors='ignore')
                    final_url = resp.url
                
                # Extract og:image
                og_match = re.search(r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
                if not og_match:
                    og_match = re.search(r'content=["\'](.*?)["\']\s+(?:property|name)=["\']og:image["\']', html, re.IGNORECASE)
                
                if not og_match:
                    return None
                
                img_url = og_match.group(1)
                if not img_url.startswith('http'):
                    return None
                
                # Download the image
                img_req = urllib.request.Request(img_url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'
                })
                with urllib.request.urlopen(img_req, timeout=10, context=ctx) as img_resp:
                    img_bytes = img_resp.read()
                    content_type = img_resp.headers.get('Content-Type', 'image/jpeg')
                
                if len(img_bytes) < 5000:  # Skip tiny images (icons, etc.)
                    return None
                
                return {
                    "url": final_url,
                    "image_url": img_url,
                    "image_bytes": img_bytes,
                    "mime_type": content_type.split(';')[0].strip()
                }
            except Exception:
                return None
        
        # Process up to 5 URLs
        for url in source_urls[:5]:
            try:
                result = await loop.run_in_executor(None, _fetch_og_image, url)
                if result:
                    images.append(result)
                    print(f"   ✅ Got image from: {result['url'][:60]}... ({len(result['image_bytes'])} bytes)")
            except Exception:
                continue
        
        print(f"🖼️ [RESEARCH] Extracted {len(images)} article images.")
        return images

    async def analyze_image_relevance(self, image_bytes: bytes, topic: str) -> bool:
        """Use Gemini Vision to check if an article image is cinematically useful.
        Returns True if the image is a real, relevant photograph suitable for a documentary reel.
        Returns False for logos, posters, graphics, screenshots, or irrelevant images.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        
        try:
            # Determine mime type
            mime_type = "image/jpeg"
            if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = "image/png"
            elif image_bytes[:4] == b'RIFF':
                mime_type = "image/webp"
            
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            
            analysis_prompt = f"""Analyze this image for use in a cinematic documentary reel about: "{topic}"

Answer ONLY "YES" or "NO" based on these rules:
- YES: Real photograph of people, places, events, buildings, infrastructure, nature — something visually interesting for a documentary.
- NO: Logo, brand graphic, poster, banner, advertisement, app screenshot, text-heavy infographic, social media post, cartoon, icon, stock illustration, watermarked preview, or any image that would look unprofessional in a documentary.

One word answer only: YES or NO"""

            response = await loop.run_in_executor(
                None,
                lambda: self.genai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[analysis_prompt, image_part],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        max_output_tokens=10
                    )
                )
            )
            
            if response and response.text:
                answer = response.text.strip().upper()
                return answer.startswith("YES")
            
            return False
        except Exception as e:
            print(f"   ⚠️ Image analysis failed: {e}")
            return False  # Reject on error — safer to generate fresh

    async def generate_text(self, prompt, system_instruction=None, json_mode=True, use_pro=False):
        """Generates text using Gemini 1.5 Flash or Pro via the modern GenAI SDK."""
        import asyncio
        loop = asyncio.get_event_loop()
        
        # Region Priority & Backoff (Synchronized with imageGen.py: global primary)
        # Region Priority & Backoff: Prioritize high-capacity regions over global to avoid initial 429s
        locations = ["us-central1", "europe-west4", "asia-northeast1", "global"]
        backoffs = [5, 15, 45, 120] # Slightly more aggressive backoff for 2.5 tier
        max_retries = len(locations)
        
        # Determine model
        model_id = "gemini-2.5-pro" if use_pro else self.text_model_name
        
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
            
        for attempt in range(max_retries):
            loc = locations[attempt % len(locations)]
            try:
                # Create a regional client for this attempt
                temp_client = genai.Client(
                    vertexai=True,
                    project=self.project_id,
                    location=loc,
                    credentials=self.credentials
                )
                
                response = await loop.run_in_executor(
                    None,
                    lambda: temp_client.models.generate_content(
                        model=model_id,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            top_p=0.95,
                            max_output_tokens=4096
                        )
                    )
                )
                
                if response and response.text:
                    text = response.text.strip()
                    if json_mode:
                        import re
                        # Remove ```json ... ``` or ``` ... ``` wrappers
                        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text)
                        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
                        return cleaned.strip()
                    return text
                    
                raise Exception("Empty response from model")
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "Resource exhausted" in error_str:
                    wait_time = backoffs[attempt]
                    print(f"⚠️ Text Quota hit (429) in {loc} for {model_id}. Failover in {wait_time}s... ({attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"⚠️ Text Gen Error on {model_id} ({loc}): {e}")
                    if attempt == max_retries - 1:
                        return f"Error: {str(e)}"
        
        return "Summary generation unavailable."

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
            
            # Handle multiple parts (e.g. text + thought signature)
            text_parts = []
            if response and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text'):
                        text_parts.append(part.text)
            
            text = "".join(text_parts)
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
        """Generates an image using Stable Imagen 3.0 (Primary) or Gemini Multimodal (Fallback)."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            # 1. Primary Choice: Stable Imagen 3.0
            if self.image_model is not None:
                try:
                    # Aspect ratio mapping for Imagen
                    ar_map = {"9:16": "9:16", "4:5": "3:4", "1:1": "1:1"}
                    target_ar = ar_map.get(aspect_ratio, "9:16")

                    print(f"DEBUG: Using Stable Imagen 3.0 (Aspect: {target_ar})")
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.image_model.generate_images(
                            prompt=prompt,
                            number_of_images=1,
                            language="en",
                            aspect_ratio=target_ar,
                            safety_filter_level="block_only_high",
                            person_generation="allow_all"
                        )
                    )
                    if response and response.images:
                        print(f"✅ Image Generated via STABLE Imagen 3.0")
                        return response.images[0]._image_bytes
                except Exception as e:
                    print(f"⚠️ Stable Imagen Failed: {e}. Trying Gemini Failover...")

            # 2. Secondary Choice: Gemini Multimodal Failover with Multi-Region Resilience
            # USER PREFERENCE: Prioritize global for 3.1 stability
            locations = ["global", "us-central1", "us-east4", "europe-west4"]
            # Synchronized with imageGen.py: 60s -> 120s -> 180s backoff
            backoffs = [60, 120, 180, 240] 
            max_retries = len(backoffs)
            current_model_id = self.image_gen_model_name
            
            if hasattr(self, 'image_gen_model_name') and ("gemini-3" in self.image_gen_model_name or "gemini-2.5" in self.image_gen_model_name or "image-preview" in self.image_gen_model_name):
                for attempt in range(max_retries):
                    loc = locations[attempt % len(locations)]
                    # The new GenAI SDK handles location at client level
                    # So we create a localized client for this attempt
                    temp_client = genai.Client(
                        vertexai=True, 
                        project=self.project_id, 
                        location=loc, 
                        credentials=self.credentials
                    )
                    
                    # Logic: Only try Gemini Multimodal in 'global'. 
                    # If failing over to other regions, use stable Imagen or 1.5-flash for vision only
                    use_multimodal = (loc == "global")
                    # Safety gap before generation (Matched to imageGen.py success: 15s)
                    await asyncio.sleep(15)
                    
                    try:
                        if use_multimodal:
                            print(f"DEBUG: Attempting Multimodal Gen in {loc} via {self.image_gen_model_name}")
                            response = await loop.run_in_executor(
                                None,
                                lambda: temp_client.models.generate_content(
                                    model=self.image_gen_model_name,
                                    contents=[prompt],
                                    config=types.GenerateContentConfig(
                                        response_modalities=["IMAGE"],
                                        image_config=types.ImageConfig(
                                            aspect_ratio=aspect_ratio,
                                            image_size="1K"
                                        )
                                    )
                                )
                            )
                            if response and response.candidates:
                                for part in response.candidates[0].content.parts:
                                    if part.inline_data:
                                        print(f"✅ AI Image Generated natively in {loc} via {self.text_model_name}")
                                        return part.inline_data.data
                        else:
                            # REGIONAL FALLBACK: Use Stable Imagen in this region
                            print(f"DEBUG: Using Regional Stable Imagen in {loc} (Failover Path)")
                            ar_map = {"9:16": "9:16", "4:5": "3:4", "1:1": "1:1"}
                            target_ar = ar_map.get(aspect_ratio, "9:16")
                            
                            # Use the newer SDK for Imagen in regions too
                            response = await loop.run_in_executor(
                                None,
                                lambda: temp_client.models.generate_images(
                                    model="imagen-3.0-generate-001",
                                    prompt=prompt,
                                    config=types.GenerateImagesConfig(
                                        number_of_images=1,
                                        aspect_ratio=target_ar,
                                        safety_filter_level="BLOCK_ONLY_HIGH",
                                        person_generation="ALLOW_ALL"
                                    )
                                )
                            )
                            if response:
                                try:
                                    print(f"DEBUG: Regional Response Object Found")
                                    data_dict = {}
                                    if hasattr(response, 'model_dump'):
                                        data_dict = response.model_dump()
                                    elif hasattr(response, 'dict'):
                                        data_dict = response.dict()
                                    
                                    img_bytes = None
                                    
                                    # Recursive search for bytes
                                    def find_bytes(obj):
                                        if isinstance(obj, bytes) and len(obj) > 5000: # Typical image size
                                            return obj
                                        if isinstance(obj, dict):
                                            for v in obj.values():
                                                res = find_bytes(v)
                                                if res: return res
                                        if isinstance(obj, list):
                                            for v in obj:
                                                res = find_bytes(v)
                                                if res: return res
                                        return None

                                    img_bytes = find_bytes(data_dict)
                                    
                                    if img_bytes:
                                        print(f"✅ Image Generated via Regional Stable Imagen ({loc}) - {len(img_bytes)} bytes")
                                        return img_bytes
                                except Exception as de:
                                    print(f"DEBUG: Error during recursive extraction: {de}")
                            
                            print(f"⚠️ Regional Imagen ({loc}) returned no valid image data. Continuing failover...")
                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str or "Resource exhausted" in error_str:
                            wait_time = backoffs[attempt]
                            print(f"⚠️ Image Quota hit (429) in {loc}. Failover in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        break
            
            return None
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

    async def generate_veo_video(self, prompt: str, image_bytes: bytes = None) -> bytes:
        """
        Generates a cinematic video clip using Vertex AI Veo 3.1 Fast.
        Supports image-to-video (preferred) and text-to-video modes.
        When image_bytes is provided, Veo animates the image into a video clip.
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
            
            model_name = "veo-3.1-fast-generate-001"
                
            # Force get token
            request = google.auth.transport.requests.Request()
            self.credentials.refresh(request)
            token = self.credentials.token

            endpoint = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model_name}:predictLongRunning"
            
            # Build instance — image-to-video if image provided, text-to-video otherwise
            instance = {"prompt": prompt}
            
            if image_bytes:
                # Determine mime type from bytes
                mime_type = "image/jpeg"
                if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                    mime_type = "image/png"
                
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                instance["image"] = {
                    "bytesBase64Encoded": image_b64,
                    "mimeType": mime_type
                }
                print(f"🖼️ [VEO] Mode: Image-to-Video ({len(image_bytes)} bytes, {mime_type})")
            else:
                print(f"📝 [VEO] Mode: Text-to-Video")
            
            payload = {
                "instances": [instance],
                "parameters": {
                    "aspectRatio": "9:16",
                    "personGeneration": "ALLOW_ALL",
                    "durationSeconds": 4
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
            print(f"📡 [VEO] LRO Response: {json.dumps(op_data, indent=2)}")
            if "name" not in op_data: 
                print("⚠️ [VEO] Failed to start Long Running Operation.")
                return None
            
            op_name = op_data["name"]
            print(f"🎥 [VEO] Operation started: {op_name}")
            print(f"⏳ [VEO GCS] Monitoring {gcs_uri} for completion...")

            # 3. Poll using fetchPredictOperation — try v1beta1 first (where LROs register)
            api_versions = ["v1beta1", "v1"]
            active_endpoint = None
            
            print(f"📡 [VEO] Waiting 15s for operation to register...")
            await asyncio.sleep(15)
            
            timeout_seconds = 900
            start_time = time.time()
            last_progress = -1
            
            while time.time() - start_time < timeout_seconds:
                elapsed = int(time.time() - start_time)
                try:
                    # Refresh token every 5 mins
                    if elapsed > 0 and elapsed % 300 == 0:
                        request = google.auth.transport.requests.Request()
                        self.credentials.refresh(request)
                        token = self.credentials.token
                        headers["Authorization"] = f"Bearer {token}"
                        print(f"\n🔑 [VEO] Token refreshed at {elapsed}s")
                    
                    def _fetch_op():
                        endpoints = [active_endpoint] if active_endpoint else [
                            f"https://{self.location}-aiplatform.googleapis.com/{v}/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model_name}:fetchPredictOperation"
                            for v in api_versions
                        ]
                        last_err = None
                        for ep in endpoints:
                            try:
                                body = json.dumps({"operationName": op_name}).encode('utf-8')
                                req = urllib.request.Request(ep, data=body, headers=headers, method='POST')
                                ctx = ssl.create_default_context()
                                with urllib.request.urlopen(req, context=ctx) as resp:
                                    return ep, json.loads(resp.read())
                            except urllib.error.HTTPError as he:
                                last_err = he
                                continue
                        raise last_err if last_err else Exception("All API versions failed")
                            
                    result = await loop.run_in_executor(None, _fetch_op)
                    working_ep, status_data = result
                    
                    if not active_endpoint:
                        active_endpoint = working_ep
                        print(f"\n📡 [VEO] Connected: {working_ep}")
                    
                    # Check for completion
                    if status_data.get("done"):
                        if "error" in status_data:
                            print(f"\n❌ [VEO] Operation failed: {json.dumps(status_data['error'], indent=2)}")
                            return None
                        print(f"\n✅ [VEO] Complete! ({elapsed}s)")
                        print(f"📡 [VEO] Full response: {json.dumps(status_data, indent=2)[:2000]}")
                        
                        # Try to extract video from response directly
                        response_data = status_data.get("response", {})
                        
                        # Veo returns videos under "videos" key (not "predictions")
                        videos = response_data.get("videos", [])
                        for vid in videos:
                            if isinstance(vid, dict):
                                video_b64 = vid.get("bytesBase64Encoded")
                                if video_b64:
                                    print(f"📥 [VEO] Extracting inline video ({len(video_b64)} chars base64)...")
                                    return base64.b64decode(video_b64)
                        
                        # Fallback: check predictions key
                        predictions = response_data.get("predictions", [])
                        
                        for pred in predictions:
                            # Check for inline video bytes (base64)
                            if isinstance(pred, dict):
                                video_b64 = pred.get("bytesBase64Encoded") or pred.get("video", {}).get("bytesBase64Encoded")
                                if video_b64:
                                    print(f"📥 [VEO] Extracting inline video data...")
                                    return base64.b64decode(video_b64)
                                
                                # Check for GCS URI in response
                                video_uri = pred.get("videoUri") or pred.get("gcsUri") or pred.get("video", {}).get("uri")
                                if video_uri:
                                    print(f"📥 [VEO] Video at: {video_uri}")
                                    # Parse and download from the actual URI
                                    parts = video_uri.replace("gs://", "").split("/", 1)
                                    actual_bucket = parts[0]
                                    actual_blob = parts[1] if len(parts) > 1 else file_name
                                    
                                    storage_client = storage.Client(credentials=self.credentials, project=self.project_id)
                                    b = storage_client.bucket(actual_bucket).blob(actual_blob)
                                    video_data = await loop.run_in_executor(None, b.download_as_bytes)
                                    print(f"📥 [VEO] Downloaded {len(video_data)} bytes from {video_uri}")
                                    try:
                                        await loop.run_in_executor(None, b.delete)
                                    except: pass
                                    return video_data
                        
                        # Fallback: search the bucket for any recent video files
                        print(f"🔍 [VEO] Searching bucket {bucket_name} for video files...")
                        storage_client = storage.Client(credentials=self.credentials, project=self.project_id)
                        bucket_obj = storage_client.bucket(bucket_name)
                        
                        def _find_video():
                            blobs = list(bucket_obj.list_blobs(prefix="veo_output"))
                            if not blobs:
                                # Try listing ALL blobs
                                blobs = list(bucket_obj.list_blobs())
                            # Sort by time, newest first
                            blobs.sort(key=lambda b: b.time_created or datetime.min, reverse=True)
                            return blobs
                        
                        from datetime import datetime
                        found_blobs = await loop.run_in_executor(None, _find_video)
                        
                        if found_blobs:
                            print(f"🔍 [VEO] Found {len(found_blobs)} files in bucket:")
                            for fb in found_blobs[:5]:
                                print(f"   📄 {fb.name} ({fb.size} bytes, created: {fb.time_created})")
                            
                            # Download the newest one
                            newest = found_blobs[0]
                            video_data = await loop.run_in_executor(None, newest.download_as_bytes)
                            print(f"📥 [VEO] Downloaded {newest.name}: {len(video_data)} bytes")
                            try:
                                await loop.run_in_executor(None, newest.delete)
                            except: pass
                            return video_data
                        
                        print(f"❌ [VEO] No video files found in bucket {bucket_name}")
                        break
                        
                    # Progress bar
                    progress = 0
                    metadata = status_data.get("metadata", {})
                    if "progressPercentage" in metadata:
                        progress = metadata["progressPercentage"]
                    elif "percentDone" in metadata:
                        progress = metadata["percentDone"]
                    
                    bar_len = 20
                    if progress > 0 and progress > last_progress:
                        filled_len = int(bar_len * progress / 100)
                        bar = '█' * filled_len + '░' * (bar_len - filled_len)
                        print(f"\r🎥 [VEO] |{bar}| {progress}% ({elapsed}s)", end="", flush=True)
                        last_progress = progress
                    else:
                        est = min(95, int((elapsed / 120) * 100))
                        filled_len = int(bar_len * est / 100)
                        bar = '█' * filled_len + '░' * (bar_len - filled_len)
                        print(f"\r🎥 [VEO] |{bar}| ~{est}% ({elapsed}s)", end="", flush=True)
                            
                except Exception as e:
                    if "404" not in str(e):
                        print(f"\n⚠️ [VEO Poll] {e}")
                
                await asyncio.sleep(10)

            print("\n") # New line after progress bar
            
            # 4. Final verification and download from GCS
            storage_client = storage.Client(credentials=self.credentials, project=self.project_id)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            exists = await loop.run_in_executor(None, blob.exists)
            if exists:
                print(f"✅ [VEO GCS] Video found! Downloading from GCS...")
                video_data = await loop.run_in_executor(None, blob.download_as_bytes)
                print(f"📥 [VEO GCS] Downloaded {len(video_data)} bytes.")
                # Clean up
                try:
                    await loop.run_in_executor(None, blob.delete)
                except: pass
                return video_data

            print(f"❌ [VEO GCS] Timeout or file missing at {gcs_uri}")
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
