import os
import sqlite3
import asyncio
import json
import base64
import httpx
import feedparser
import re
from datetime import datetime
from jinja2 import Template
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import urllib.parse
import shutil
from PIL import Image, ImageEnhance
import io
from gcp_client import get_gcp_client
# Constants
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# Docker Check: If we are in /app, the root is also /app
if BACKEND_DIR == "/app":
    ROOT_DIR = "/app"
else:
    ROOT_DIR = os.path.dirname(BACKEND_DIR)

GCP_KEY_PATH = os.path.join(BACKEND_DIR, "key.json")
STATIC_DIR = os.path.join(ROOT_DIR, "static")
OUTPUT_DIR = os.path.join(STATIC_DIR, "output")
DB_PATH = os.path.join(BACKEND_DIR, "automation.db")
LOGO_PATH = os.path.join(BACKEND_DIR, "Logo.png")
if not os.path.exists(LOGO_PATH):
    # Fallback for local dev if not moved yet
    LOGO_PATH = os.path.join(ROOT_DIR, "Logo.png")

# Studio Templates Directory
STUDIO_TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates", "studio")
EXPL_TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates", "explainer")

class DatabaseManager:
    @staticmethod
    def init_db():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS posts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      topic TEXT,
                      headline TEXT,
                      subtitle TEXT,
                      caption TEXT,
                      asset_path TEXT,
                      source_url TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS schedules
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      post_id INTEGER,
                      scheduled_at TIMESTAMP,
                      caption TEXT,
                      status TEXT DEFAULT 'pending',
                      error_message TEXT,
                      FOREIGN KEY (post_id) REFERENCES posts(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY,
                      value TEXT)''')
        
        # Initialize default mode
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('scheduler_mode', 'automation')")
        
        conn.commit()
        conn.close()

    @staticmethod
    def save_post(topic, headline, subtitle, caption, asset_path, source_url):
        print(f"DEBUG: Saving post to {DB_PATH} | Topic: {topic}")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO posts (topic, headline, subtitle, caption, asset_path, source_url)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (str(topic), str(headline), str(subtitle), str(caption), str(asset_path), str(source_url)))
        conn.commit()
        conn.close()

    @staticmethod
    def is_duplicate(url):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM posts WHERE source_url = ?", (str(url),))
        res = c.fetchone()
        conn.close()
        return res is not None

    @staticmethod
    def schedule_post(post_id, scheduled_at, caption):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO schedules (post_id, scheduled_at, caption)
                     VALUES (?, ?, ?)''', (post_id, scheduled_at, caption))
        conn.commit()
        conn.close()

    @staticmethod
    def get_schedules():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''SELECT s.*, p.headline, p.asset_path 
                     FROM schedules s 
                     JOIN posts p ON s.post_id = p.id 
                     ORDER BY s.scheduled_at ASC''')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def get_pending_schedules():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # FIX: Remove 'localtime' and use IST offset (+5.5h) for User compatibility.
        c.execute('''SELECT s.*, p.asset_path 
                     FROM schedules s 
                     JOIN posts p ON s.post_id = p.id 
                     WHERE s.status = 'pending' AND datetime(s.scheduled_at) <= datetime('now', '+5 hours', '+30 minutes')''')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def update_schedule_status(schedule_id, status, error_message=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE schedules SET status = ?, error_message = ? WHERE id = ?", (status, error_message, schedule_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_schedule(schedule_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_all_posts():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM posts ORDER BY created_at DESC")
        posts = [dict(row) for row in c.fetchall()]
        conn.close()
        return posts

    @staticmethod
    def get_settings():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        rows = c.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}

    @staticmethod
    def save_setting(key, value):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

class AISummarizer:
    def __init__(self):
        self.client = get_gcp_client()

    @staticmethod
    async def is_quote_worthy(headline, summary):
        """Intelligently detects if a news item is a significant statement from a key figure."""
        try:
            from gcp_client import GCPClient
            client = GCPClient()
            prompt = (
                "TASK: Determine if this news item is primarily a 'Big Statement' or 'Quote' from a politician, celebrity, or important person.\n"
                f"HEADLINE: {headline}\n"
                f"SUMMARY: {summary}\n"
                "CRITERIA:\n"
                "1. Does it feature a specific person saying something controversial, significant, or impactful?\n"
                "2. Is it a 'reaction' or 'assertion' rather than just a general event?\n"
                "Output ONLY 'TRUE' or 'FALSE'."
            )
            res = await client.generate_text(prompt)
            return "TRUE" in res.upper()
        except:
            return False

    async def analyze_image(self, image_path, prompt):
        """Analyzes an image using Gemini 2.5 GA for hyper-accurate reconstruction context."""
        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
            
            # Using the same unified client
            response = await self.client.generate_text(
                prompt,
                images=[img_data]
            )
            return response
        except Exception as e:
            print(f"DEBUG: Image Analysis Error: {e}")
            return ""
    async def summarize_news(self, title, text, language="english"):
        # Senior Investigative Journalist Persona
        lang_instruction = "OUTPUT LANGUAGE: Simple, Professional English."
        
        system = (
            "You are the Senior Investigative Journalist for 'Humorously Indians'.\n"
            f"{lang_instruction}\n"
            "TONE: Professional, Authoritative, Fact-Focused.\n"
            "GOAL: Provide deep context and investigative clarity. Move away from sarcasm to authentic reporting."
        )
        
        prompt = (f"Analyze this news in depth: {title}. {text}.\n"
                  "1. Create a detailed, context-rich ENGLISH headline (UPPERCASE). MAX 8 WORDS.\n"
                  "2. Create a 1-line investigative summary in English that provides critical background context. MAX 15 WORDS.\n"
                  "Output strictly as a JSON object with keys 'headline', 'subtitle'.")
        
        result = await self.client.generate_text(prompt, system_instruction=system)
        try:
            data = json.loads(result) if result else None
            if data:
                data['headline'] = data.get('headline', '').replace('**', '').replace('*', '').strip()
                data['subtitle'] = data.get('subtitle', '').replace('**', '').replace('*', '').strip()
            return data
        except: return None

    async def generate_deep_caption(self, headline, subtitle, news_text, language="english"):
        system = "You are a Senior Investigative Correspondent. Your captions provide deep, nuanced context and investigative detail in English."
        prompt = (f"Headline: {headline}\nSubtitle: {subtitle}\nContext: {news_text}\n"
                  "Create a detailed, context-rich 5-6 sentence Instagram caption in Simple English.\n"
                  "Structure: \n"
                  "1. Detailed context of the situation.\n"
                  "2. Key investigative insights and background data.\n"
                  "3. Impact on the common citizen.\n"
                  "4. Future implications or expert perspective.\n"
                  "Output as JSON: {'caption': '...'}")
        
        result = await self.client.generate_text(prompt, system_instruction=system)
        try:
            return json.loads(result) if result else {"caption": f"{headline}\n\n{subtitle}"}
        except: return {"caption": f"{headline}\n\n{subtitle}"}

    async def generate_search_query(self, title, text):
        prompt = (f"Based on this news: {title} {text}, create a DYNAMIC EDITORIAL COMPOSITION.\n"
                  "1. 'query': A 3-5 word search query for a PRESS PHOTOGRAPH.\n"
                  "2. 'visual_ideal': A CANDID, MUNDANE moment.\n"
                  "3. 'protagonist': The main person mentioned.\n"
                  "4. 'imagen_prompt': A detailed prompt for Imagen 3.0:\n"
                  "   - CRITICAL: NO TEXT, NO WORDS, NO LETTERS, NO NUMBERS IN THE IMAGE. The image must be a clean photograph ONLY.\n"
                  "   - COMPOSITION: Apply RULE OF THIRDS. Place the subject (person) on the far left or far right third of the frame.\n"
                  "   - NEGATIVE SPACE: Ensure the opposite side of the subject is 'Negative Space' (dark, clean, or blurred background) to act as a canvas for typography.\n"
                  "   - STYLE: Unfiltered press photography, 35mm film grain, harsh side-lighting, authentic skin textures.\n"
                  "   - SETTING: Mundane Indian bureaucratic settings.")
        
        result = await self.client.generate_text(prompt)
        try:
            data = json.loads(result)
            img_prompt = data.get('imagen_prompt', title)
            if "35mm" not in img_prompt:
                img_prompt += ", 35mm film grain, harsh direct flash, asymmetrical composition"
            return data.get('query', title), data.get('visual_ideal', title), data.get('protagonist', ""), img_prompt
        except: return title, title, "", f"Vintage magazine photo of {title}, 35mm film grain, dramatic lighting, asymmetrical"

    async def generate_satire(self, topic, news_context="", language="english"):
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        lang_instruction = "OUTPUT LANGUAGE: Simple English."

        system = (
            "You are a high-level Government Spin Doctor. Think of yourself as a charismatic politician talking to a massive crowd.\n"
            f"{lang_instruction}\n"
            "THE METHOD: NEVER complain. Reframe every failure or crisis as a 'Strategic Choice' or a 'Hidden Benefit'.\n"
            "THE VOCABULARY: Simplified Elite-Speak. Sound official but stay understandable.\n"
            "THE DEADPAN RULE: 100% serious tone. No sarcasm markers like 'Haha'. Total bureaucratic delusion.\n"
        )

        prompt = (
            f"NEWS CONTEXT: {news_context if news_context else topic}\n\n"
            "TASK:\n"
            "1. Headline: 5-WORD RULE. Must be ~5 words, official-sounding but understandable.\n"
            "2. Subtext: Sharp, absurd irony using simple-but-official words. Use <span class='highlight'>...</span> for the spin.\n"
            "3. Caption: 80-90 words. A confident political justification using circular logic.\n"
            "Return strictly VALID JSON with keys: headline, subtext, caption, hashtags."
        )
        
        result = await self.client.generate_text(prompt, system_instruction=system, use_pro=True)
        try:
            return json.loads(result) if result else None
        except: return None

class NewsFetcher:
    @staticmethod
    async def extract_hero_image(url):
        """Advanced Image Scraper with Retries and Cleanup."""
        print(f"DEBUG: Starting hero extraction for {url}")
        
        for attempt in range(2): # Double-Strike Retry
            browser = None
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-web-security"]
                    )
                    context = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1")
                    page = await context.new_page()
                    
                    # Faster timeout for first attempt
                    timeout = 25000 if attempt == 0 else 45000
                    await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
                    
                    # Redirect loop for Google News
                    for _ in range(3):
                        if "news.google.com" not in page.url: break
                        await asyncio.sleep(1)

                    hero = await page.evaluate("""() => {
                        const getMeta = (name) => {
                            const m = document.querySelector(`meta[property="${name}"]`) || 
                                      document.querySelector(`meta[name="${name}"]`);
                            return m ? m.content : null;
                        };
                        const og = getMeta('og:image') || getMeta('twitter:image');
                        if (og && og.startsWith('http')) return og;

                        const isLogo = (u) => ['logo', 'icon', 'google', 'placeholder', 'avatar', 'nav'].some(x => u.toLowerCase().includes(x));
                        const imgs = Array.from(document.querySelectorAll('img'))
                            .filter(img => img.naturalWidth >= 500 && img.naturalHeight >= 350 && !isLogo(img.src))
                            .sort((a, b) => (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight));
                        return imgs.length > 0 ? imgs[0].src : null;
                    }""")
                    
                    if hero:
                        print(f"DEBUG: Hero image found in attempt {attempt+1}")
                        return hero
                    
            except Exception as e:
                print(f"Hero Scrape Attempt {attempt+1} Error: {e}")
            finally:
                if browser:
                    try: await browser.close()
                    except: pass
                    
        return None

    @staticmethod
    async def search_image(query, headline="", visual_ideal="", count=5):
        """Semantic Image Search: Fetches 10 results and scores relevance via metadata."""
        print(f"DEBUG: Semantic Search for '{query}' | Target: {headline}")
        url = "https://duckduckgo.com/i.js"
        params = {"q": query, "o": "json", "v": "l", "f": ",,,", "p": "1"}
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        try:
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                results = data.get("results", [])
                
                scored_results = []
                keywords = set(re.findall(r'\w+', f"{headline} {visual_ideal}".lower()))
                
                for res in results:
                    img_url = res.get("image")
                    title = res.get("title", "").lower()
                    source = res.get("source", "").lower()
                    
                    if not img_url or not img_url.startswith("http"): continue
                    # Filter out non-portraits/clutter
                    if any(x in img_url.lower() for x in ['logo', 'icon', 'fbcdn', 'twimg', 'placeholder', 'avatar', 'gif']): continue
                    
                    # Scoring logic
                    score = 0
                    # 1. Keyword match in title/source
                    matches = sum(1 for kw in keywords if kw in title or kw in source)
                    score += matches * 15
                    
                    # 2. Preference for Reliable News Sources (Better Portraits)
                    news_sources = ['reuters', 'ap', 'pti', 'ani', 'ndtv', 'indiatimes', 'thehindu', 'news18', 'indianexpress', 'bloomberg', 'guardian']
                    if any(ns in source for ns in news_sources):
                        score += 50
                        
                    # 3. Penalize watermarked/stock sites
                    stock_sites = ['shutterstock', 'istock', 'getty', 'alamy', 'dreamstime', 'depositphotos', 'vector']
                    if any(ss in source for ss in stock_sites):
                        score -= 30
                        
                    # 4. Dimension score (prefer larger images)
                    width = int(res.get('width', 0))
                    height = int(res.get('height', 0))
                    if width >= 1000 and height >= 1000:
                        score += 20
                    elif width < 400:
                        score -= 50
                        
                    scored_results.append((score, img_url))
                
                if scored_results:
                    # Sort by score descending
                    scored_results.sort(key=lambda x: x[0], reverse=True)
                    # Return top 'count' results
                    return [res[1] for res in scored_results[:count]]
                    
        except Exception as e:
            print(f"Semantic Search Error: {e}")
        return []

    @staticmethod
    def fetch_by_topic(topic, count=5):
        query = urllib.parse.quote(topic)
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            import httpx
            # Use a short timeout for the RSS feed to prevent hanging
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                else:
                    return []
        except Exception as e:
            print(f"DEBUG: RSS Fetch Error: {e}")
            return []
            
        results = []
        for entry in feed.entries[:count]:
            results.append({
                'title': entry.title,
                'link': entry.link,
                'summary': entry.summary if 'summary' in entry else "",
                'source': entry.source.title if 'source' in entry else "Unknown"
            })
        return results

    @staticmethod
    def fetch_batch(topics_input, count=3):
        if isinstance(topics_input, str):
            topics = [t.strip() for t in topics_input.split(",") if t.strip()]
        else:
            topics = topics_input
            
        all_results = []
        for topic in topics:
            results = NewsFetcher.fetch_by_topic(topic, count=count)
            all_results.extend(results)
        return all_results

class InstagramEngine:
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self.summarizer = AISummarizer()
        
        # Logo Logic
        self.logo_base64 = None
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as f:
                self.logo_base64 = base64.b64encode(f.read()).decode()
        else:
            print(f"DEBUG: Logo NOT FOUND at {LOGO_PATH}")


    def frame_character(self, img, side="center", width=1080, height=1920):
        """Standardizes a character cutout for Studio posts."""
        bbox = img.getbbox()
        if not bbox: return img
        
        subject = img.crop(bbox)
        sw, sh = subject.size
        
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        
        # Scale to ~70% of canvas height for Studio (Big but balanced)
        target_h = int(height * 0.7)
        ratio = target_h / sh
        new_w, new_h = int(sw * ratio), target_h
        
        if new_w > width * 0.9:
            ratio = (width * 0.9) / sw
            new_w, new_h = int(width * 0.9), int(sh * ratio)
            
        scaled_subject = subject.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Positioning Logic: Dynamic depending on content (side parameter)
        if side == "left":
            paste_x = 50
        elif side == "right":
            paste_x = width - new_w - 50
        else: # center
            paste_x = (width - new_w) // 2
            
        paste_y = height - new_h - 100 # Safe bottom margin
        canvas.paste(scaled_subject, (paste_x, paste_y), scaled_subject)
        return canvas

    async def process_cutout(self, image_url, side="center", width=1080, height=1920, grayscale=False):
        """Processes an image into a high-quality cutout."""
        if not REMBG_AVAILABLE or not image_url: return None
        
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200:
                    # Switch to Vertex AI for background removal
                    output_bytes = await self.summarizer.gcp.remove_background(resp.content)
                    
                    if not output_bytes:
                        # Fallback to original bytes if cloud fails
                        output_bytes = resp.content
                        
                    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
                    
                    if grayscale:
                        r, g, b, a = img.split()
                        rgb = Image.merge("RGB", (r, g, b)).convert("L")
                        enhancer = ImageEnhance.Contrast(rgb)
                        rgb = enhancer.enhance(1.4)
                        img = Image.merge("RGBA", (rgb, rgb, rgb, a))
                    
                    framed_img = self.frame_character(img, side=side, width=width, height=height)
                    buffered = io.BytesIO()
                    framed_img.save(buffered, format="PNG")
                    return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            print(f"Cutout processing error: {e}")
        return None
    async def render_post(self, data, template_str, filename, width=1080, height=1350, aspect_ratio="4:5"):
        """
        Renders a single post using a Jinja2 template and Playwright.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--allow-file-access-from-files", "--disable-web-security"]
                )
                # Set the viewport to match the requested aspect ratio
                context = await browser.new_context(viewport={'width': width, 'height': height})
                page = await context.new_page()
                
                # Render the HTML with dynamic dimensions and BGs
                html = Template(template_str).render(
                    **data,
                    logo_base64=self.logo_base64,
                    width=width,
                    height=height,
                    datetime=datetime
                )
                
                # Use 'load' to ensure images are fully painted. 
                await page.set_content(html, wait_until='load', timeout=30000)
                print("DEBUG: Content set successfully.")
                
                # Fixed buffer for image painting (Increased for stability)
                await asyncio.sleep(3) 
                print("DEBUG: Buffer sleep complete. Taking screenshot...")
                
                # Use JPEG for better compatibility with Instagram Graph API
                jpeg_filename = filename.replace(".png", ".jpg")
                output_path = os.path.join(OUTPUT_DIR, jpeg_filename)

                # Dynamic resolution for Instagram compatibility
                clip_w, clip_h = width, height
                
                await page.screenshot(
                    path=output_path, 
                    type='jpeg',
                    quality=85, # Standardizing to 85% to avoid 'Too Large/Too Complex' errors
                    clip={'x': 0, 'y': 0, 'width': clip_w, 'height': clip_h}
                )
                
                await context.close()
                await browser.close()

                # --- SANITIZATION STEP ---
                # Re-save with PIL to strip metadata and ensure standard RGB color space
                try:
                    from PIL import Image
                    with Image.open(output_path) as img:
                        # Force RGB and standard JPEG profile
                        rgb_img = img.convert("RGB")
                        rgb_img.save(output_path, "JPEG", quality=90, optimize=True, progressive=False)
                    print(f"DEBUG: JPEG Sanitized OK: {output_path}")
                except Exception as img_err:
                    print(f"DEBUG: Image sanitization warning: {img_err}")
                
                print(f"DEBUG: Successfully rendered {aspect_ratio} post to {output_path}")
                return jpeg_filename
        except Exception as e:
            print(f"ENGINE ERROR: render_post failed: {e}")
            return None

    async def generate_standard_post(self, item, topic, aspect_ratio="4:5", language="english"):
        """Generates a high-quality standard post (4:5 or 9:16)."""
        try:
            # Determine dimensions
            width, height = 1080, 1350 # Default 4:5
            if aspect_ratio == "9:16":
                width, height = 1080, 1920

            # 1. Summarize
            summary = await self.summarizer.summarize_news(item['title'], item['summary'], language=language)
            caption_data = await self.summarizer.generate_deep_caption(
                summary.get('headline', item['title']), summary.get('subtitle', ''), item['summary'], language=language
            )
            if not summary: 
                print(f"ENGINE: Summary failed for {topic}")
                return None
            
            # 2. Image Sourcing (ALWAYS AI-GENERATED for Copyright Safety)
            print(f"DEBUG: Sourcing context for AI image reconstruction...")
            source_image_url = await NewsFetcher.extract_hero_image(item['link'])
            query, visual_ideal, protagonist, imagen_prompt = await self.summarizer.generate_search_query(summary['headline'], item['summary'])
            
            # --- IMPROVED CONTEXT: Analysis of source image if available ---
            image_analysis = ""
            if source_image_url and not source_image_url.startswith("/"):
                try:
                    # Download briefly to analyze
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(source_image_url, timeout=10)
                        if resp.status_code == 200:
                            tmp_path = os.path.join(OUTPUT_DIR, f"tmp_analysis_{datetime.now().strftime('%H%M%S')}.jpg")
                            with open(tmp_path, "wb") as f: f.write(resp.content)
                            
                            print(f"DEBUG: Analyzing source image for hyper-accurate details...")
                            analysis_prompt = f"Describe the protagonist, setting, and lighting of this image in dramatic detail for an AI artist. Focus on accuracy: {protagonist}"
                            image_analysis = await self.summarizer.client.analyze_image(tmp_path, analysis_prompt)
                            os.remove(tmp_path)
                except Exception as ae:
                    print(f"DEBUG: Source analysis skipped: {ae}")

            # Refine prompt with analysis
            final_prompt = imagen_prompt
            if image_analysis:
                final_prompt = f"{imagen_prompt}. Style Details from context: {image_analysis}. Ensure dramatic lighting and hyper-realistic textures."

            # 3. Generate the Final AI Image (Imagen 3.0)
            print(f"DEBUG: Generating dramatic AI image with Imagen 3.0...")
            img_bytes = await self.summarizer.client.generate_image(final_prompt, aspect_ratio=aspect_ratio)
            
            image_url = None
            is_ai_image = True
            
            if img_bytes:
                imagen_filename = f"gen_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                save_path = os.path.join(OUTPUT_DIR, imagen_filename)
                with open(save_path, "wb") as f:
                    f.write(img_bytes)
                image_url = f"/static/output/{imagen_filename}"
                print(f"DEBUG: AI Image Generated OK ({len(img_bytes)//1024}KB) -> {imagen_filename}")
            else:
                print(f"❌ FAILURE: AI Image generation failed. Post will have no image.")
                return None
            
            # 4. Convert image to base64 for reliable Playwright rendering
            image_base64 = None
            if image_url:
                try:
                    if image_url.startswith("/static/output/"):
                        local_path = os.path.join(OUTPUT_DIR, os.path.basename(image_url))
                        if os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                image_base64 = base64.b64encode(f.read()).decode()
                    else:
                        headers = {"User-Agent": "Mozilla/5.0"}
                        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as dl:
                            resp = await dl.get(image_url)
                            if resp.status_code == 200:
                                image_base64 = base64.b64encode(resp.content).decode()
                except Exception as e:
                    print(f"DEBUG: Image loading error: {e}")
            
            # 3. Generate Deep Caption
            caption_data = await self.summarizer.generate_deep_caption(summary['headline'], summary['subtitle'], item['summary'])
            
            # 4. Render
            template_path = os.path.join(EXPL_TEMPLATES_DIR, "EDITORIAL", "MODERN_EDITORIAL.html")
            with open(template_path, 'r') as f:
                template_str = f.read()

            from urllib.parse import urlparse
            source_domain = urlparse(item['link']).netloc.replace("www.", "")
            
            render_data = {
                **summary,
                "image_url": f"data:image/jpeg;base64,{image_base64}" if image_base64 else image_url,
                "is_ai_image": is_ai_image,
                "view_height": height,
                "source_domain": source_domain
            }

            filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            path = await self.render_post(render_data, template_str, filename, width=width, height=height, aspect_ratio=aspect_ratio)
            
            if path:
                # Save to database
                DatabaseManager.save_post(
                    item['title'], summary['headline'], "Standard", caption_data.get('caption', ''), os.path.basename(path), "Standard Engine"
                )
            
            return path
        except Exception as e:
            print(f"ENGINE ERROR: generate_standard_post failed: {e}")
            return None

    async def generate_investigative_post(self, topic, aspect_ratio="9:16", language="english"):
        # Fetch news first to get context
        items = NewsFetcher.fetch_by_topic(topic, count=1)
        news_context = ""
        image_url = None
        source_url = "Investigative Studio"
        if items:
            item = items[0]
            news_context = f"{item['title']} - {item['summary']}"
            source_url = item['link']
            image_url = await NewsFetcher.extract_hero_image(item['link'])
        
        # 1. Deep Context Summary
        investigative_data = await self.summarizer.summarize_news(topic, news_context, language=language)
        if not investigative_data: return None
        
        # 2. Image Sourcing (ALWAYS AI-GENERATED for Satire)
        print(f"DEBUG: Sourcing satire context for AI image reconstruction...")
        query, visual_ideal, protagonist, imagen_prompt = await self.summarizer.generate_search_query(satire_data.get('headline', topic), news_context)
        
        # --- IMPROVED CONTEXT: Analysis of source image if available ---
        image_analysis = ""
        if image_url and not image_url.startswith("/"):
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(image_url, timeout=10)
                    if resp.status_code == 200:
                        tmp_path = os.path.join(OUTPUT_DIR, f"tmp_satire_{datetime.now().strftime('%H%M%S')}.jpg")
                        with open(tmp_path, "wb") as f: f.write(resp.content)
                        
                        print(f"DEBUG: Analyzing source image for satirical reconstruction...")
                        analysis_prompt = f"Describe the scene, lighting, and characters for a satirical artist. Focus on accuracy: {protagonist}"
                        image_analysis = await self.summarizer.client.analyze_image(tmp_path, analysis_prompt)
                        os.remove(tmp_path)
            except Exception as ae:
                print(f"DEBUG: Satire source analysis skipped: {ae}")

        # Refine prompt with analysis
        final_prompt = f"{imagen_prompt}. Satirical Style Details: {image_analysis}. Ensure dramatic lighting and hyper-realistic, slightly exaggerated textures."

        # 3. Generate the Final AI Image (Imagen 3.0)
        print(f"DEBUG: Generating dramatic AI image for satire with Imagen 3.0...")
        img_bytes = await self.summarizer.client.generate_image(final_prompt, aspect_ratio=aspect_ratio)
        
        image_url = None
        is_ai_image = True
        
        if img_bytes:
            imagen_filename = f"satire_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            save_path = os.path.join(OUTPUT_DIR, imagen_filename)
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            image_url = f"/static/output/{imagen_filename}"
            print(f"DEBUG: Satire AI Image Generated OK ({len(img_bytes)//1024}KB) -> {imagen_filename}")
        else:
            print(f"❌ FAILURE: Satire AI Image generation failed.")
            return None
        
        if not image_url:
            image_url = f"https://loremflickr.com/1080/1080/{urllib.parse.quote(topic)},politics,india"
        
        # 3. Template — always EDITORIAL/SATIRE.html
        template_path = os.path.join(STUDIO_TEMPLATES_DIR, "EDITORIAL", "SATIRE.html")
        with open(template_path, 'r') as f:
            template_str = f.read()

        # 4. Render
        dims = {"9:16": (1080, 1920), "4:5": (1080, 1350)}
        width, height = dims.get(aspect_ratio, (1080, 1920))
        filename = f"investigative_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}.png"
        
        path = await self.render_post(
            {**investigative_data, "image_url": image_url},
            template_str,
            filename,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio
        )
        
        headline = investigative_data.get('headline', 'REPORT')
        subtext = investigative_data.get('subtitle', 'Deep Context Analysis')
        
        # Generate deep caption
        caption_data = await self.summarizer.generate_deep_caption(headline, subtext, news_context, language=language)
        full_caption = caption_data.get('caption', f"{headline}\n\n{news_context}")
        
        DatabaseManager.save_post(topic, headline, subtext, full_caption, path, source_url)
        return path

class Musicalizer:
    def __init__(self):
        self.audio_dir = os.path.join(STATIC_DIR, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)

    def get_tracks(self):
        """Returns a list of available audio tracks."""
        if not os.path.exists(self.audio_dir): return []
        return [f for f in os.listdir(self.audio_dir) if f.endswith((".mp3", ".wav", ".m4a"))]

    async def create_reel(self, image_path, audio_filename, output_filename=None, duration=10):
        """
        Converts a static image into an MP4 video with background music.
        """
        if not output_filename:
            output_filename = f"reel_{os.urandom(4).hex()}.mp4"
            
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        audio_path = os.path.join(self.audio_dir, audio_filename)
        
        if not os.path.exists(audio_path):
            return None, f"Audio track not found: {audio_filename}"
            
        # Detect image dimensions to match video output
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size
            print(f"DEBUG: Matching Reel resolution to image: {w}x{h}")
        except:
            w, h = 1080, 1350 # Default to 4:5 if detection fails
            
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", "30", "-g", "60",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return output_filename, "Success"
        else:
            print(f"FFmpeg Error: {stderr.decode()}")
            return None, f"FFmpeg Error: {stderr.decode()}"
