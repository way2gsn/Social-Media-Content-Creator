import os
import asyncio
import json
import base64
import httpx
from datetime import datetime
from jinja2 import Template
from playwright.async_api import async_playwright
import urllib.parse
from glue import LOGO_PATH, OUTPUT_DIR, AISummarizer, BACKEND_DIR, STATIC_DIR

CAROUSEL_TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates", "carousel")

class CarouselEngine:
    def __init__(self):
        self.summarizer = AISummarizer()
        self.logo_base64 = None
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as f:
                self.logo_base64 = base64.b64encode(f.read()).decode()
        
        # Heritage BGs Logic
        self.heritage_dark_bg = None
        self.heritage_light_bg = None
        dark_path = os.path.join(STATIC_DIR, "assets", "Dark_BG.png")
        light_path = os.path.join(STATIC_DIR, "assets", "Light_BG.png")
        if os.path.exists(dark_path):
            with open(dark_path, "rb") as f:
                self.heritage_dark_bg = base64.b64encode(f.read()).decode()
        if os.path.exists(light_path):
            with open(light_path, "rb") as f:
                self.heritage_light_bg = base64.b64encode(f.read()).decode()

    async def _gcp_request(self, prompt):
        return await self.summarizer.client.generate_text(prompt)

    def _clean_json(self, text):
        """Removes markdown code blocks and extra whitespace."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    async def plan_carousel(self, news_text, mode="real", language="english"):
        """Phase 1: Content Architect - Gemma plans the narrative."""
        
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (Romanized Hindi + English mix. Headlines and body text should feel like a conversational WhatsApp mix)."
        elif language == "hindi":
            lang_instruction = "OUTPUT LANGUAGE: Hindi (Devanagari script)."

        # Mode-specific persona rules
        if mode == "satire":
            persona = (
                "SYSTEM: You are a high-level Government Spin Doctor.\n"
                "METHOD: NEVER complain. Reframe every failure as a 'Strategic Choice' or 'Optional Success'.\n"
                "VOCABULARY: Use simple-but-official words (e.g., 'Atmospheric Optics', 'Strategic Deceleration').\n"
                "TONE: Deadpan, delusional, 100% serious.\n"
                "HEADLINE: Follow the 5-WORD RULE. Aggressive, understandable, but official."
            )
        else:
            persona = (
                "SYSTEM: You are a Lead Financial Editor for a premium global newsroom (Bloomberg style).\n"
                "TONE: Analytical, high-end, professional, and serious.\n"
                "HEADLINE: Aggressive editorial style, sophisticated vocabulary."
            )

        prompt = (
            f"{persona}\n"
            f"{lang_instruction}\n"
            f"TASK: Analyze the news context and plan a 5-10 slide Instagram carousel (1080x1350).\n"
            "TEMPLATE TYPES: HOOK, COVER, CHART, COMPARISON, METRICS, SPIN.\n\n"
            f"NEWS TEXT: {news_text}\n\n"
            "COGNITIVE RULES:\n"
            "1. Slide 1 must ALWAYS be a HOOK (Catchy Hook for engagement).\n"
            "2. Include CHART (with 'chart_type' bar/line/pie and 'chart_data' JSON) and METRICS.\n"
            "3. Include COMPARISON (with 'promise_text' and 'result_text').\n"
            "4. Output a STRICT JSON array of slide objects. However, if using a dictionary, use 'slides' as the top-level key.\n"
            "Return ONLY the JSON. No conversational text."
        )
        
        result = await self._gcp_request(prompt)
        print(f"DEBUG Carousel Plan Response: {result[:500]}...")
        
        try:
            cleaned = self._clean_json(result)
            data = json.loads(cleaned)
            
            # PHASE 1: Try to find a list of slides
            slides = []
            if isinstance(data, list):
                slides = data
            elif isinstance(data, dict):
                # Search common list keys
                for key in ["slides", "carousel", "plan", "narrative", "instagram_carousel"]:
                    if key in data and isinstance(data[key], list):
                        slides = data[key]
                        break
                
                # FALLBACK: If the dict has keys like "slide_1", "slide_2"...
                if not slides:
                    # Sort keys to preserve order (slide_1, slide_2, ...)
                    sorted_keys = sorted(data.keys(), key=lambda x: str(x))
                    potential_slides = []
                    for k in sorted_keys:
                        if isinstance(data[k], dict) and ("template" in data[k] or "headline" in data[k]):
                            potential_slides.append(data[k])
                    
                    if len(potential_slides) > 0:
                        slides = potential_slides
                        print(f"DEBUG: Recovered {len(slides)} slides from dictionary keys.")

            if slides:
                # Ensure all elements are dicts
                valid_data = [s for s in slides if isinstance(s, dict)]
                return valid_data, f"SUCCESS: Found {len(valid_data)} slides"
            
            return [], f"ERROR: AI returned {type(data)} but no slide list found. Content: {result[:200]}"
        except Exception as e:
            return [], f"JSON ERROR: {str(e)} | RAW: {result[:500]}"

    async def generate_carousel_caption(self, plan_data, mode="real", language="english"):
        """Phase 2: Generate caption based on mode."""
        summary = " ".join([s.get('headline', '') for s in plan_data])
        
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (Romanized Hindi + English mix)."
        
        if mode == "satire":
            prompt = (
                "SYSTEM: You are a high-level Government Spin Doctor for 'Humorously Indians'.\n"
                f"{lang_instruction}\n"
                "TASK: Write a 3-paragraph Instagram caption for this carousel.\n"
                f"CAROUSEL TOPICS: {summary}\n"
                "TONE: Confident, pseudo-official, ironically delusional.\n"
                "Include 5-8 hashtags and end with: 'Follow @Humorously_Indians for more posts.'\n"
                "Output strictly as a JSON object with key 'caption'."
            )
        else:
            prompt = (
                "SYSTEM: You are a Lead Financial Editor.\n"
                f"{lang_instruction}\n"
                "TASK: Write a professional, punchy Instagram caption summarizing the analysis.\n"
                f"CAROUSEL TOPICS: {summary}\n"
                "TONE: Analytical, insightful, professional.\n"
                "Include 5-8 hashtags and end with: 'Follow @Humorously_Indians for more posts.'\n"
                "Output strictly as a JSON object with key 'caption'."
            )

        result = await self._gcp_request(prompt)
        try:
            return json.loads(result).get("caption", "")
        except:
            return "Strategic analysis complete. #StrategicPivot"

    async def render_slides(self, session_id, plan_data, image_url=None, theme="EDITORIAL", heritage_mode="dark"):
        """Phase 3: Parallel Rendering Engine - Playwright renders all slides."""
        session_dir = os.path.join(OUTPUT_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        
        # Copy base.css to the session dir for local reference if needed, 
        # but here we just use the absolute path in the template for simplicity
        base_css_path = os.path.abspath(os.path.join(CAROUSEL_TEMPLATES_DIR, "base.css"))
        
        total_slides = len(plan_data)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # Enable local file access for base.css
            context = await browser.new_context(
                viewport={'width': 1080, 'height': 1350},
                bypass_csp=True,
                ignore_https_errors=True
            )
            
            async def render_single_slide(index, slide):
                if not isinstance(slide, dict):
                    print(f"Skipping slide {index}: Not a dictionary")
                    return None
                    
                template_type = slide.get('template', 'SPIN')
                template_name = f"{template_type}.html"
                template_path = os.path.join(CAROUSEL_TEMPLATES_DIR, template_name)
                
                if not os.path.exists(template_path):
                    print(f"Error: Template {template_name} not found")
                    return None

                with open(template_path, 'r') as f:
                    template_str = f.read()

                with open(base_css_path, 'r') as f:
                    base_css_content = f.read()

                # Merge slide data with global context
                render_data = {
                    **slide,
                    "slide_index": index,
                    "total_slides": total_slides,
                    "logo_base64": self.logo_base64,
                    "dark_bg_base64": self.heritage_dark_bg,
                    "light_bg_base64": self.heritage_light_bg,
                    "image_url": image_url if index == 0 else None, # Only cover/hook gets image
                    "theme": theme,
                    "heritage_mode": heritage_mode
                }

                # Inline CSS and render template
                html_content = Template(template_str).render(**render_data)
                html_content = html_content.replace('<link rel="stylesheet" href="base.css">', f'<style>{base_css_content}</style>')

                page = await context.new_page()
                await page.set_content(html_content, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2) # Wait for Chart.js/Fonts
                
                filename = f"slide_{index+1}.png"
                filepath = os.path.join(session_dir, filename)
                await page.screenshot(path=filepath)
                await page.close()
                return filename

            # Render in parallel!
            tasks = [render_single_slide(i, slide) for i, slide in enumerate(plan_data)]
            results = await asyncio.gather(*tasks)
            await browser.close()
            
            return [os.path.join(session_id, r) for r in results if r]

    async def generate_carousel(self, news_text, image_url=None, mode="real", language="english", theme="EDITORIAL", heritage_mode="dark"):
        """Master Orchestrator."""
        session_id = f"carousel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Plan
        plan, debug_msg = await self.plan_carousel(news_text, mode=mode, language=language)
        if not plan: return None, debug_msg
        
        # 2. Render
        slide_paths = await self.render_slides(session_id, plan, image_url, theme=theme, heritage_mode=heritage_mode)
        
        # 3. Caption
        caption = await self.generate_carousel_caption(plan, mode=mode, language=language)
        
        return {
            "session_id": session_id,
            "slides": slide_paths,
            "caption": caption,
            "plan": plan
        }, debug_msg
