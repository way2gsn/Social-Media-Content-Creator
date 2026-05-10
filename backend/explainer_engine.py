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
from composition_engine import DynamicCompositionEngine

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
        lang_instruction = f"OUTPUT LANGUAGE: Simple English"

        prompt = (
            "SYSTEM: You are a Senior Investigative Journalist for 'Humorously Indians'.\n"
            f"{lang_instruction}\n"
            "TASK: Analyze the news in depth and extract:\n"
            "1. THE MAIN CHARACTER: Identify the SPECIFIC PERSON by name.\n"
            "2. SECONDARY_CHARACTER: Opponent or subject by name.\n"
            "3. INVESTIGATIVE HEADLINE: A detailed, context-rich English headline. MAX 8 WORDS.\n"
            "4. 3-5 CRITICAL DATA POINTS: Accurate, context-rich bullet points in English. Keep them brief.\n"
            "5. STYLE: 'MAGAZINE' (Detailed Editorial), 'EXPLAINER', or 'QUOTE'.\n"
            "6. THEME: 'POLITICS', 'TECH', 'CULTURE', or 'CRIME'.\n"
            "7. SUBJECT_TYPE: 'PERSON' or 'OBJECT'.\n"
            "8. LAYOUT: 'DYNAMIC' (Let the Composition Engine decide).\n"
            "9. VISUAL_STRATEGY: 'AI_GENERATE'.\n"
            "10. IS_LISTICLE: boolean.\n"
            "11. CONTENT_DEPTH: 'INVESTIGATIVE_DEPTH'.\n"
            f"NEWS CONTEXT: {news_context}\n"
            "Output strictly VALID JSON with keys: character_name, secondary_character, headline, points (list), style, theme, subject_type, layout, visual_strategy, is_listicle, content_depth."
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

    def frame_character(self, img, layout="ASIDE"):
        """Standardizes a character cutout into a 1080x1350 vertical frame with smart positioning."""
        # 1. Detect content bounding box
        bbox = img.getbbox()
        if not bbox: return img
        
        subject = img.crop(bbox)
        sw, sh = subject.size
        
        frame_w, frame_h = 1080, 1350
        canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        
        # 2. Resizing — Maintain Aspect Ratio
        target_h = int(frame_h * 0.9) # Person takes up 90% of height
        ratio = target_h / sh
        new_w, new_h = int(sw * ratio), target_h
        subject = subject.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 3. Smart Positioning
        if layout == "CENTERED":
            # Hero Shot: Center-bottom
            x_offset = (frame_w - new_w) // 2
        else:
            # Editorial Shot: Pushed to the left/right but with better padding
            x_offset = int(frame_w * 0.05) # 5% margin from edge
            
        y_offset = frame_h - new_h # Align to bottom
        
        canvas.paste(subject, (x_offset, y_offset), subject)
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
                
                # 3. Visual Sourcing — Poster Shield & Smart Choice
                visual_strategy = plan.get('visual_strategy', 'WEB_SEARCH')
                is_listicle = plan.get('is_listicle', False)
                content_depth = plan.get('content_depth', 'SINGLE_POST_OK')
                is_person = plan.get('subject_type', 'PERSON') == 'PERSON'
                
                # FORCE CAROUSEL for Informational News
                if is_listicle or content_depth == 'CAROUSEL_MANDATORY':
                    print(f"DEBUG: Content Strategy Shift: Topic '{topic}' requires a Carousel for value delivery.")
                    # We ensure points are extracted
                    if not plan.get('points'):
                        plan['points'] = ["Analyzing the impact...", "Key highlights and significance...", "Historical context..."]

                # 3. Visual Sourcing — ALWAYS AI-GENERATED for Copyright Safety
                print(f"DEBUG: Sourcing carousel context for AI reconstruction...")
                source_image_url = await NewsFetcher.extract_hero_image(source_url)
                
                # --- IMPROVED CONTEXT: Analysis of source image if available ---
                image_analysis = ""
                if source_image_url and not source_image_url.startswith("/"):
                    try:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(source_image_url, timeout=10)
                            if resp.status_code == 200:
                                tmp_path = os.path.join(OUTPUT_DIR, f"tmp_expl_{idx}_{datetime.now().strftime('%H%M%S')}.jpg")
                                with open(tmp_path, "wb") as f: f.write(resp.content)
                                
                                print(f"DEBUG: Performing Hyper-Detailed Character Analysis for accuracy...")
                                analysis_prompt = (
                                    f"TASK: Create a hyper-accurate visual fingerprint of the protagonist: {plan.get('character_name', topic)}.\n"
                                    "Analyze and describe in extreme detail:\n"
                                    "1. Precise facial features, hair style, and ethnicity.\n"
                                    "2. Exact clothing, accessories, and posture.\n"
                                    "3. Environmental lighting and photographic style (e.g. 'Golden hour news portrait').\n"
                                    "This description MUST allow an AI to perfectly replicate the likeness of the person."
                                )
                                image_analysis = await self.summarizer.client.analyze_image(tmp_path, analysis_prompt)
                                os.remove(tmp_path)
                    except Exception as ae:
                        print(f"DEBUG: Carousel source analysis skipped: {ae}")

                # --- NEW: Identity Fallback if no image analysis was possible ---
                if not image_analysis and plan.get('character_name'):
                    print(f"DEBUG: Scraper failed. Generating AI physical blueprint for: {plan['character_name']}")
                    fallback_prompt = (
                        f"Describe the physical appearance of {plan['character_name']} in extreme photographic detail. "
                        "Focus on facial structure, hair, ethnicity, and common attire. "
                        "This description will be used to generate a photorealistic AI likeness."
                    )
                    image_analysis = await self._gcp_request(fallback_prompt)

                # Refine prompt with analysis
                imagen_prompt = (
                    f"CRITICAL IDENTITY: {plan.get('character_name', topic)}. "
                    f"A professional photorealistic portrait of {plan.get('character_name', topic)}. "
                    f"Visual Details: {image_analysis}. "
                    f"Context: {plan.get('headline')}. "
                    "Cinematic news photography, 8k, ultra-realistic, highly detailed likeness, "
                    "professional journalism aesthetic, dramatic soft lighting, shallow depth of field, centered composition."
                )
                
                final_image_url = None
                image_base64 = None
                is_ai_image = True
                
                try:
                    print(f"DEBUG: Generating dramatic AI image for carousel slide with Imagen 3.0...")
                    img_bytes = await self.summarizer.client.generate_image(imagen_prompt, aspect_ratio=aspect_ratio)
                    if img_bytes:
                        imagen_filename = f"gen_expl_{idx}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        save_path = os.path.join(OUTPUT_DIR, imagen_filename)
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        final_image_url = f"/static/output/{imagen_filename}"
                        image_base64 = base64.b64encode(img_bytes).decode()
                except Exception as e:
                    print(f"❌ GCP Carousel Image Error: {e}")
                    statuses.append(f"Image Gen failed for item {idx+1}")
                    continue
                # 4. Process for Rendering (NO CUTOUTS as requested)
                # We use the full-frame image_base64
                cutout_base64 = None
                secondary_cutout_base64 = None
                layout = plan.get('layout', 'ASIDE')
                
                slide_paths = []
                total_slides = len(plan.get('points', [])) + 1

                # 4. Rendering Multi-Slide Carousel
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                carousel_id = f"carousel_{timestamp}_{idx}"
                carousel_dir = os.path.join(OUTPUT_DIR, "carousels", carousel_id)
                os.makedirs(carousel_dir, exist_ok=True)
                
                is_person = plan.get('subject_type', 'PERSON') == 'PERSON'
                theme = plan.get('theme', 'POLITICS').upper()
                points = plan.get('points', [])
                # Determine dimensions
                width, height = 1080, 1350
                if aspect_ratio == "9:16":
                    height = 1920

                # --- SLIDE 1: COVER ---
                cover_filename = os.path.join("carousels", carousel_id, "slide_01.jpg")
                style = plan.get('style', 'EXPLAINER').upper()
                
                template_file = "COVER.html"
                
                template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", template_file)
                if not os.path.exists(template_path):
                    template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "EXPLAINER.html")
                
                with open(template_path, 'r') as f:
                    template_str = f.read()

                render_data_cover = {
                    **plan,
                    "original_image": f"data:image/jpeg;base64,{image_base64}" if image_base64 else final_image_url,
                    "cutout_image": cutout_base64, 
                    "secondary_cutout": secondary_cutout_base64,
                    "layout": layout,
                    "language": language,
                    "slide_index": 1,
                    "total_slides": total_slides,
                    "view_height": height,
                    "theme": theme,
                    "is_cover": True
                }
                
                path = await engine.render_post(render_data_cover, template_str, cover_filename, width, height, aspect_ratio=aspect_ratio)
                if path: slide_paths.append(path)

                # --- SLIDES 2+: POINTS ---
                point_template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "POINT.html")
                if not os.path.exists(point_template_path):
                    point_template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "EXPLAINER.html")
                
                with open(point_template_path, 'r') as f:
                    point_template_str = f.read()

                for s_idx, point in enumerate(points):
                    slide_num = s_idx + 2
                    point_filename = os.path.join("carousels", carousel_id, f"slide_{slide_num:02d}.jpg")
                    
                    render_data_point = {
                        **plan,
                        "current_point": point,
                        "original_image": f"data:image/jpeg;base64,{image_base64}" if image_base64 else final_image_url,
                        "cutout_base64": cutout_base64,
                        "layout": layout,
                        "language": language,
                        "slide_index": slide_num,
                        "total_slides": total_slides,
                        "view_height": height,
                        "theme": theme,
                        "is_cover": False
                    }

                    path = await engine.render_post(render_data_point, point_template_str, point_filename, width, height, aspect_ratio=aspect_ratio)
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

    async def generate_quote_post(self, topic, language="english", aspect_ratio="9:16"):
        """Generates a standalone, single-image premium Quote post."""
        items = NewsFetcher.fetch_by_topic(topic, count=1)
        if not items: return None, "No news found"
        
        item = items[0]
        news_text = f"{item['title']} {item['summary']}"
        source_url = item['link']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. Plan Visuals
        plan, _ = await self.plan_explainer(topic, news_text, language=language)
        if not plan: return None, "AI Plan failed"
        
        # Force style to QUOTE
        plan['style'] = 'QUOTE'
        theme = plan.get('theme', 'POLITICS').upper()
        
        # 2. Caption
        caption_data = await self.summarizer.generate_deep_caption(
            plan.get('headline', topic), plan.get('quote', 'Premium Quote'), news_text, language=language
        )
        detailed_caption = caption_data.get('caption', f"{plan.get('headline', topic)}\n\n{news_text}")
        
        # 3. Image Sourcing (ALWAYS AI-GENERATED for Quotes)
        print(f"DEBUG: Sourcing quote context for AI reconstruction...")
        source_image_url = await NewsFetcher.extract_hero_image(item['link'])
        
        # --- IMPROVED CONTEXT: Analysis of source image if available ---
        image_analysis = ""
        if source_image_url and not source_image_url.startswith("/"):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(source_image_url, timeout=10)
                    if resp.status_code == 200:
                        tmp_path = os.path.join(OUTPUT_DIR, f"tmp_quote_{timestamp}.jpg")
                        with open(tmp_path, "wb") as f: f.write(resp.content)
                        
                        print(f"DEBUG: Performing Hyper-Detailed Portrait Analysis for Quote Accuracy...")
                        analysis_prompt = (
                            f"TASK: Create a hyper-accurate facial and upper-body fingerprint of: {plan.get('character_name', topic)}.\n"
                            "IGNORE THE BACKGROUND. Focus ONLY on:\n"
                            "1. Precise facial features, hair style, and ethnicity.\n"
                            "2. Clothing details and posture.\n"
                            "This description MUST allow an AI to perfectly replicate the subject as a close-up portrait."
                        )
                        image_analysis = await self.summarizer.client.analyze_image(tmp_path, analysis_prompt)
                        os.remove(tmp_path)
            except Exception as ae:
                print(f"DEBUG: Quote source analysis skipped: {ae}")

        # --- NEW: Identity Fallback if no image analysis was possible ---
        if not image_analysis and plan.get('character_name'):
            print(f"DEBUG: Scraper failed. Generating AI physical blueprint for Quote: {topic}")
            fallback_prompt = (
                f"Describe the facial features and hair of {plan.get('character_name', topic)} in extreme photographic detail. "
                "This description will be used to generate a photorealistic close-up AI headshot."
            )
            image_analysis = await self._gcp_request(fallback_prompt)

        # ─── AUTONOMOUS RETRY LOOP ───
        max_retries = 3
        for attempt in range(max_retries):
            print(f"🤖 [AUTONOMOUS] Generation Attempt {attempt + 1}/{max_retries} for: {topic}")
            
            # Refine prompt with analysis and Art Director constraints
            image_prompt = (
                f"CRITICAL IDENTITY: {plan.get('character_name', topic)}. "
                "CRITICAL: NO TEXT, NO WORDS, NO LETTERS IN IMAGE. "
                f"COMPOSITION: Apply RULE OF THIRDS. Place the subject on the far left or far right third of the frame. "
                f"NEGATIVE SPACE: Opposite side must be dark, clean, or blurred canvas. "
                f"STYLE: Unfiltered press photography, 35mm film grain, harsh side-lighting, authentic skin textures. "
                f"Likeness Details: {image_analysis}. "
                "QUALITY: No AI smoothing. Mundane bureaucratic Indian setting. NO GENERIC POINTING. NO BOKEH."
            )
            
            final_image_url = None
            image_base64 = None
            
            try:
                img_data = await self.summarizer.client.generate_image(image_prompt, aspect_ratio=aspect_ratio)
                if img_data:
                    imagen_filename = f"gen_mag_{timestamp}_{attempt}.jpg"
                    save_path = os.path.join(OUTPUT_DIR, imagen_filename)
                    with open(save_path, "wb") as f:
                        f.write(img_data)
                    final_image_url = f"/static/output/{imagen_filename}"
                    image_base64 = base64.b64encode(img_data).decode()
            except Exception as e:
                print(f"❌ GCP Image Generation Error: {e}")
                continue

            # 4. Render with Dynamic Composition
            quote_filename = f"mag_{timestamp}_{attempt}.jpg"
            abs_gen_path = os.path.join(OUTPUT_DIR, os.path.basename(final_image_url))
            
            # Art Director Analysis
            comp = DynamicCompositionEngine.analyze_image(abs_gen_path)
            
            # Select Template
            template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "MAGAZINE.html")
            with open(template_path, 'r') as f:
                template_str = f.read()
                
            width, height = 1080, 1920 

            from urllib.parse import urlparse
            source_domain = urlparse(source_url).netloc.replace("www.", "")
            
            # Prepare Headline HTML
            headline = plan.get('headline', topic)
            words = headline.split()
            if len(words) > 2:
                headline_html = f"<span class='accent-word'>{' '.join(words[:2])}</span><br>{' '.join(words[2:])}"
            else:
                headline_html = f"<span class='accent-word'>{headline}</span>"

            render_data = {
                **plan,
                "headline_html": headline_html,
                "original_image": f"data:image/jpeg;base64,{image_base64}" if image_base64 else final_image_url,
                "view_height": height, 
                "theme": theme,
                "source_domain": source_domain,
                "layout": comp['layout'],
                "colors": comp['colors'],
                "text_anchor": comp['text_anchor']
            }
            
            from glue import InstagramEngine
            engine = InstagramEngine()
            path = await engine.render_post(render_data, template_str, quote_filename, width, height, aspect_ratio="9:16")
            
            if path:
                from qa_agent import QAAgent
                from glue import STATIC_DIR
                abs_img_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
                
                # We still run QA for logging/metadata, but we NO LONGER reject the post.
                is_approved, reason = await QAAgent.validate_post(abs_img_path, topic)
                print(f"🕵️ [QA REPORT] Approved: {is_approved} | Reason: {reason}")
                
                # ALWAYS SAVE to Database as requested by user
                from glue import DatabaseManager
                DatabaseManager.save_post(
                    topic, plan['headline'], f"Magazine ({theme})", detailed_caption, path, source_url
                )
                print(f"✅ [AUTONOMOUS] Post saved to gallery: {path}")
                return path, "Success"
            
        return None, "Failed to render post after image generation."
