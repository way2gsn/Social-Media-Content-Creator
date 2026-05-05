import os
import asyncio
import json
import base64
import httpx
from datetime import datetime
from jinja2 import Template
from playwright.async_api import async_playwright
import urllib.parse
from PIL import Image
import io
try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

from glue import LOGO_PATH, OUTPUT_DIR, AISummarizer, BACKEND_DIR, STATIC_DIR, NewsFetcher

EXPL_TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates", "explainer")

class ExplainerEngine:
    def __init__(self):
        self.logo_base64 = None
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as f:
                self.logo_base64 = base64.b64encode(f.read()).decode()
        
        self.output_dir = os.path.join(OUTPUT_DIR, "explainers")
        os.makedirs(self.output_dir, exist_ok=True)
        self.summarizer = AISummarizer()

    async def _gcp_request(self, prompt):
        return await self.summarizer.client.generate_text(prompt)

    async def plan_explainer(self, topic, news_context, language="english"):
        """Extract key points and identify the character."""
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (Romanized Hindi + English mix)."

        prompt = (
            "SYSTEM: You are a Lead Editorial Designer for 'The Indian Express'.\n"
            f"{lang_instruction}\n"
            "TASK: Analyze the news and extract:\n"
            "1. THE MAIN CHARACTER: The most important person in the story (e.g. 'Narendra Modi').\n"
            "2. THE CORE QUOTE or HEADLINE: A high-impact punchy statement.\n"
            "3. 3 KEY POINTS: Accurate, short bullet points explaining the news.\n"
            "4. STYLE: Choose 'QUOTE' for direct statements, 'EXPLAINER' for standard news, or 'MODERN_EDITORIAL' for sophisticated feature stories.\n"
            "5. THEME: Choose 'POLITICS' (Red/Dark), 'TECH' (Blue/Neon), 'CULTURE' (Gold/Warm), or 'CRIME' (Deep Red/Cold).\n"
            "6. SUBJECT_TYPE: Choose 'PERSON' if it's about a specific individual, or 'OBJECT' if it's about a place, building, or thing.\n"
            f"NEWS CONTEXT: {news_context}\n"
            "Output strictly VALID JSON with keys: character_name, headline, points (list), style, theme, subject_type."
        )
        
        result = await self._gcp_request(prompt)
        try:
            plan = json.loads(result)
            # Convert stars to highlights for important words
            if 'headline' in plan:
                import re
                plan['headline'] = re.sub(r'\*\*(.*?)\*\*', r"<span class='highlight'>\1</span>", plan['headline'])
                plan['headline'] = plan['headline'].replace('*', '').strip()
            
            if 'points' in plan and isinstance(plan['points'], list):
                import re
                new_points = []
                for p in plan['points']:
                    p = re.sub(r'\*\*(.*?)\*\*', r"<span class='highlight'>\1</span>", p)
                    p = p.replace('*', '').strip()
                    new_points.append(p)
                plan['points'] = new_points

            # Ensure required keys exist
            if 'style' not in plan: plan['style'] = 'EXPLAINER'
            if 'theme' not in plan: plan['theme'] = 'POLITICS'
            if 'subject_type' not in plan: plan['subject_type'] = 'PERSON'
            if 'character_name' not in plan: plan['character_name'] = topic
            if 'points' not in plan: plan['points'] = ["Analyzing news context...", "Extracting key details...", "Finalizing editorial."]
            return plan, "Success"
        except Exception as e:
            return {
                "character_name": topic,
                "headline": topic,
                "points": ["News details are being processed...", "Check back shortly for the full explainer."],
                "style": "EXPLAINER"
            }, f"AI Parsing Error: {e}"

    def frame_character(self, img, side="left"):
        """Standardizes a character cutout into a 1080x1350 vertical frame, positioned safely to an editorial side."""
        # 1. Detect content bounding box
        bbox = img.getbbox()
        if not bbox: return img
        
        subject = img.crop(bbox)
        sw, sh = subject.size
        
        frame_w, frame_h = 1080, 1350
        canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        
        # 2. Scale subject to ~95% height for "WOW" factor (Massive presence)
        target_h = int(frame_h * 0.95)
        ratio = target_h / sh
        new_w, new_h = int(sw * ratio), target_h
        
        # Ensure it doesn't exceed 95% width either
        if new_w > frame_w * 0.95:
            ratio = (frame_w * 0.95) / sw
            new_w, new_h = int(frame_w * 0.95), int(sh * ratio)
            
        scaled_subject = subject.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 3. Position with Center-Anchor
        paste_x = (frame_w - new_w) // 2 if side == "center" else (50 if side == "left" else frame_w - new_w - 50)
        paste_y = frame_h - new_h
        canvas.paste(scaled_subject, (paste_x, paste_y), scaled_subject)
        return canvas

    async def process_cutout(self, image_url, side="left"):
        """Fetch image, remove background, apply filter, and SMART FRAME for portrait visibility."""
        if not image_url:
            return None
            
        try:
            # Add robust headers to avoid hotlink protection
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }
            async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200:
                    input_bytes = resp.content
                    output_bytes = remove(input_bytes)
                    
                    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
                    r, g, b, a = img.split()
                    rgb = Image.merge("RGB", (r, g, b)).convert("L")
                    
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Contrast(rgb)
                    rgb = enhancer.enhance(1.4)
                    
                    final_img = Image.merge("RGBA", (rgb, rgb, rgb, a))
                    
                    # Framed based on editorial side
                    framed_img = self.frame_character(final_img, side=side)
                    
                    buffered = io.BytesIO()
                    framed_img.save(buffered, format="PNG")
                    return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            print(f"Rembg/Processing Error: {e}")
        return None

    async def generate_explainer(self, topic, aspect_ratio="4:5", language="english", count=1):
        """Master Orchestrator for Carousel Explainers."""
        items = NewsFetcher.fetch_by_topic(topic, count=count)
        if not items: return [], "No news found"
        
        results = []
        statuses = []
        
        # Use InstagramEngine for rendering
        from glue import InstagramEngine
        engine = InstagramEngine()
        
        for idx, item in enumerate(items):
            print(f"DEBUG: Processing batch item {idx+1}/{len(items)} for {topic}")
            try:
                news_text = f"{item['title']} {item['summary']}"
                source_url = item['link']
                
                # 1. Plan Visuals
                plan, _ = await self.plan_explainer(topic, news_text, language=language)
                if not plan: 
                    statuses.append(f"AI Plan failed for item {idx+1}")
                    continue
                
                # 2. Generate Detailed Caption
                print(f"DEBUG: Generating Deep Caption for item {idx+1}")
                caption_data = await self.summarizer.generate_deep_caption(
                    plan['headline'], 
                    "Carousel Explainer", 
                    news_text, 
                    language=language
                )
                detailed_caption = caption_data.get('caption', f"{plan['headline']}\n\n{news_text}")

                # Side determination
                side = "right" if plan.get("style") == "QUOTE" else "left"
                
                # 3. Sourcing Image (Direct use, no cropping)
                candidate_urls = []
                try:
                    hero_url = await NewsFetcher.extract_hero_image(source_url)
                    if hero_url: candidate_urls.append(hero_url)
                except: print("DEBUG: Hero extraction failed, continuing to search.")
                
                try:
                    search_query = f"{plan['character_name']} official news"
                    search_results = await NewsFetcher.search_image(search_query, count=3)
                    candidate_urls.extend(search_results)
                except: print("DEBUG: Image search failed.")
                
                final_image_url = candidate_urls[0] if candidate_urls else None

                
                # AI Image Fallback: If no image found at all, generate one
                if not final_image_url:
                    print(f"DEBUG: No image found for carousel. Generating with Imagen 3.")
                    try:
                        imagen_prompt = f"Editorial news photography: {plan.get('headline', topic)}. Cinematic lighting, high resolution, professional journalism style, 4K quality."
                        img_bytes = await self.summarizer.client.generate_image(imagen_prompt, aspect_ratio="4:5")
                        if img_bytes:
                            imagen_filename = f"imagen_carousel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            imagen_path = os.path.join(OUTPUT_DIR, imagen_filename)
                            with open(imagen_path, "wb") as f:
                                f.write(img_bytes)
                            final_image_url = f"/static/output/{imagen_filename}"
                            print(f"DEBUG: AI image generated: {final_image_url}")
                    except Exception as img_err:
                        print(f"DEBUG: Imagen generation failed: {img_err}")

                # Convert image URL to base64 so Playwright renders it reliably
                image_base64 = None
                if final_image_url:
                    try:
                        if final_image_url.startswith("/static/output/"):
                            # Local file — read directly
                            local_path = os.path.join(OUTPUT_DIR, os.path.basename(final_image_url))
                            if os.path.exists(local_path):
                                with open(local_path, "rb") as f:
                                    image_base64 = base64.b64encode(f.read()).decode()
                        else:
                            # External URL — download and encode
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                                "Accept": "image/*,*/*;q=0.8",
                                "Referer": "https://www.google.com/"
                            }
                            async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as dl_client:
                                img_resp = await dl_client.get(final_image_url)
                                if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                                    image_base64 = base64.b64encode(img_resp.content).decode()
                                    print(f"DEBUG: Image converted to base64 ({len(img_resp.content)} bytes)")
                                else:
                                    print(f"DEBUG: Image download failed or too small ({img_resp.status_code})")
                    except Exception as b64_err:
                        print(f"DEBUG: Base64 conversion failed: {b64_err}")

                # 4. Rendering Multi-Slide Carousel in Dedicated Folder
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                carousel_id = f"carousel_{timestamp}_{idx}"
                carousel_dir = os.path.join(OUTPUT_DIR, "carousels", carousel_id)
                os.makedirs(carousel_dir, exist_ok=True)
                
                # Determine Layout
                is_person = plan.get('subject_type', 'PERSON') == 'PERSON'
                theme = plan.get('theme', 'POLITICS').upper()
                
                points = plan.get('points', [])
                total_slides = len(points) + 1 # +1 for Cover
                slide_paths = []

                # --- SLIDE 1: COVER ---
                cover_filename = os.path.join("carousels", carousel_id, "slide_01.png")
                template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "COVER.html")
                if not os.path.exists(template_path):
                    template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "EXPLAINER.html")
                
                with open(template_path, 'r') as f:
                    template_str = f.read()

                render_data_cover = {
                    **plan,
                    "original_image": f"data:image/jpeg;base64,{image_base64}" if image_base64 else final_image_url,
                    "is_person": is_person,
                    "language": language,
                    "slide_index": 1,
                    "total_slides": total_slides,
                    "view_height": 1350 if aspect_ratio == "4:5" else 1920,
                    "theme": theme,
                    "is_cover": True
                }
                
                path = await engine.render_post(render_data_cover, template_str, cover_filename, 1080, render_data_cover["view_height"], aspect_ratio=aspect_ratio)
                if path: slide_paths.append(path)

                # --- SLIDES 2+: POINTS ---
                point_template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "POINT.html")
                if not os.path.exists(point_template_path):
                    point_template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "EXPLAINER.html")
                
                with open(point_template_path, 'r') as f:
                    point_template_str = f.read()

                for s_idx, point in enumerate(points):
                    slide_num = s_idx + 2
                    point_filename = os.path.join("carousels", carousel_id, f"slide_{slide_num:02d}.png")
                    
                    render_data_point = {
                        **plan,
                        "current_point": point,
                        "original_image": f"data:image/jpeg;base64,{image_base64}" if image_base64 else final_image_url,
                        "is_person": False, # Points slides are text-heavy
                        "language": language,
                        "slide_index": slide_num,
                        "total_slides": total_slides,
                        "view_height": 1350 if aspect_ratio == "4:5" else 1920,
                        "theme": theme,
                        "is_cover": False
                    }

                    path = await engine.render_post(render_data_point, point_template_str, point_filename, 1080, render_data_point["view_height"], aspect_ratio=aspect_ratio)
                    if path: slide_paths.append(path)

                if slide_paths:
                    results.extend(slide_paths)
                    statuses.append(f"Successfully generated carousel folder {carousel_id} with {len(slide_paths)} slides")
                    
                    # Save to DB (Point to the folder or first slide)
                    from glue import DatabaseManager
                    DatabaseManager.save_post(
                        f"{topic} ({carousel_id})", 
                        plan['headline'], 
                        f"Editorial Carousel ({theme})", 
                        detailed_caption,              
                        slide_paths[0], 
                        source_url
                    )
                
                # Cooldown to ensure stability during high-volume batching
                await asyncio.sleep(1.0)
                
            except Exception as e:
                print(f"Batch Item Error: {idx} | {e}")
                statuses.append(f"Error on item {idx+1}: {str(e)}")

        return results, " | ".join(statuses)
