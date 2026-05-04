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
LOGO_PATH = os.path.join(ROOT_DIR, "Logo.png")

# Studio Templates Directory
STUDIO_TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates", "studio")

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
        # Get schedules where scheduled_at is in the past and status is pending
        # Using datetime() for robust comparison regardless of T or space separator
        c.execute('''SELECT s.*, p.asset_path 
                     FROM schedules s 
                     JOIN posts p ON s.post_id = p.id 
                     WHERE s.status = 'pending' AND datetime(s.scheduled_at) <= datetime('now', 'localtime')''')
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

    async def summarize_news(self, title, text, language="english"):
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (A mix of Romanized Hindi and English. e.g. 'Rupee down ho gaya')."
        
        system = (f"You are a Senior Editor at a top Indian news agency. {lang_instruction}\n"
                  "Analyze the news and provide a JSON response.")
        
        prompt = (f"Analyze this news: {title}. {text}.\n"
                  "1. Create a single-line 6-word bold headline (UPPERCASE).\n"
                  "2. Create a 1-line punchy subtitle.\n"
                  "Output strictly as a JSON object with keys 'headline', 'subtitle'.")
        
        result = await self.client.generate_text(prompt, system_instruction=system)
        try:
            data = json.loads(result) if result else None
            if data:
                # Strip markdown bold/italic stars
                data['headline'] = data.get('headline', '').replace('**', '').replace('*', '').strip()
                data['subtitle'] = data.get('subtitle', '').replace('**', '').replace('*', '').strip()
            return data
        except: return None

    async def generate_deep_caption(self, headline, subtitle, context, language="english"):
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (A mix of Romanized Hindi and English)."
        
        system = f"You are a viral social media strategist. {lang_instruction}"
        
        prompt = (f"Generate an ULTRA-DETAILED Instagram caption for this news.\n"
                  f"Headline: {headline}\n"
                  f"Summary: {subtitle}\n"
                  f"Context: {context}\n"
                  "RULES:\n"
                  "1. 100-120 words of deep analytical context.\n"
                  "2. Mention specific names and stats from context.\n"
                  "3. NO HTML tags.\n"
                  "4. Add 5-8 hashtags.\n"
                  "5. END with: 'Follow @Humorously_Indians for more posts.'\n"
                  "Output strictly as a JSON object with key 'caption'.")
        
        result = await self.client.generate_text(prompt, system_instruction=system)
        try:
            return json.loads(result) if result else {"caption": f"{headline}\n\n{subtitle}"}
        except: return {"caption": f"{headline}\n\n{subtitle}"}

    async def generate_search_query(self, title, text):
        prompt = (f"Based on this news: {title} {text}, create an image search strategy.\n"
                  "1. 'query': A 3-5 word search query for a REAL PHOTOGRAPH.\n"
                  "2. 'visual_ideal': A short description of what the photograph SHOULD contain (e.g. 'Person at a podium', 'Currency notes').\n"
                  "3. 'protagonist': The main person mentioned (e.g. 'Narendra Modi'). If no person, leave empty.\n"
                  "4. 'imagen_prompt': A detailed, cinematic prompt for AI image generation as a fallback. Describe lighting, style, and composition.\n"
                  "Return strictly VALID JSON with keys 'query', 'visual_ideal', 'protagonist', 'imagen_prompt'.")
        
        result = await self.client.generate_text(prompt)
        try:
            data = json.loads(result)
            prompt = data.get('imagen_prompt', title)
            # Force centered composition for better framing
            if "centered" not in prompt.lower():
                prompt += ", centered composition, subject in center of frame"
            return data.get('query', title), data.get('visual_ideal', title), data.get('protagonist', ""), prompt
        except: return title, title, "", f"{title}, centered composition"

    async def generate_satire(self, topic, news_context="", language="english"):
        lang_instruction = f"OUTPUT LANGUAGE: {language}"
        if language == "hinglish":
            lang_instruction = "OUTPUT LANGUAGE: Hinglish (Romanized Hindi + English mix)."

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
        """Advanced Image Scraper: Navigates to news link and finds the hero image."""
        print(f"DEBUG: Starting hero extraction for {url}")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--allow-file-access-from-files", "--disable-web-security"]
                )
                context = await browser.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1")
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                
                # Redirect loop for Google News
                try:
                    for _ in range(5):
                        if "news.google.com" not in page.url: break
                        await asyncio.sleep(1)
                except: pass

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
                await browser.close()
                return hero
        except Exception as e:
            print(f"Hero Scrape Error: {e}")
            return None
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
    async def render_post(self, data, template_str, filename, width=1080, height=1920):
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
                
                # Use load + buffer for cloud stability (networkidle can hang on fonts/trackers)
                print(f"DEBUG: Rendering post with wait_until='load' (Image type: {'Base64' if 'base64' in str(data.get('image_url','')) else 'URL/File'})")
                await page.set_content(html, wait_until='load', timeout=60000)
                # Fixed buffer for image painting
                await asyncio.sleep(3) 
                
                output_path = os.path.join(OUTPUT_DIR, filename)
                # Clip the screenshot to the exact dimensions of the aspect ratio
                await page.screenshot(path=output_path, clip={'x': 0, 'y': 0, 'width': width, 'height': height}, timeout=60000)
                await browser.close()
                return filename
        except Exception as e:
            print(f"ENGINE ERROR: render_post failed: {e}")
            return None

    async def generate_standard_post(self, item, topic, aspect_ratio="4:5", language="english"):
        try:
            # 1. Summarize with language
            summary = await self.summarizer.summarize_news(item['title'], item['summary'], language=language)
            if not summary: 
                print(f"ENGINE: Summary failed for {topic}")
                return None
            
            # 2. Image Sourcing
            image_url = await NewsFetcher.extract_hero_image(item['link'])
            query, visual_ideal, protagonist, imagen_prompt = await self.summarizer.generate_search_query(summary['headline'], item['summary'])
        
            is_ai_image = False
            if not image_url or "google" in image_url.lower():
                search_results = await NewsFetcher.search_image(query, summary['headline'], visual_ideal)
                if search_results:
                    image_url = search_results[0]
                else:
                    # GCP FALLBACK: Imagen 3 — triggers "dramatic" mode
                    print(f"DEBUG: No web image found. Generating dramatic AI image with Imagen 3...")
                    img_bytes = await self.summarizer.client.generate_image(imagen_prompt, aspect_ratio="4:5")
                    if img_bytes:
                        imagen_filename = f"imagen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        save_path = os.path.join(OUTPUT_DIR, imagen_filename)
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        image_url = f"/static/output/{imagen_filename}"
                        is_ai_image = True
                        print(f"DEBUG: AI Image Generated OK ({len(img_bytes)//1024}KB) -> {imagen_filename}")
                    else:
                        print("DEBUG: AI Image Generation FAILED (Empty Bytes)")
        
            # 2b. Convert image to base64 for reliable Playwright rendering
            image_base64 = None
            if image_url:
                try:
                    if image_url.startswith("/static/output/"):
                        local_path = os.path.join(OUTPUT_DIR, os.path.basename(image_url))
                        if os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                image_base64 = base64.b64encode(f.read()).decode()
                            print(f"DEBUG: Local image loaded OK ({len(image_base64)//1024}KB)")
                        else:
                            print(f"DEBUG: Local image NOT FOUND: {local_path}")
                    else:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                            "Referer": "https://www.google.com/",
                            "Accept-Language": "en-US,en;q=0.9"
                        }
                        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as dl:
                            resp = await dl.get(image_url)
                            # Quality Check: Minimum 40KB for web images, otherwise it's likely a thumbnail
                            if resp.status_code == 200 and len(resp.content) > 40000:
                                image_base64 = base64.b64encode(resp.content).decode()
                                print(f"DEBUG: High-Quality Web image downloaded OK ({len(resp.content)//1024}KB)")
                            else:
                                reason = "Too Small" if len(resp.content) <= 40000 else f"Status {resp.status_code}"
                                print(f"DEBUG: Web image REJECTED ({reason}): size={len(resp.content)} bytes. Triggering AI Fallback.")
                                # Trigger AI Fallback because web image is low quality
                                print(f"DEBUG: Generating HD AI alternative for low-quality source...")
                                img_bytes = await self.summarizer.client.generate_image(imagen_prompt, aspect_ratio="4:5")
                                if img_bytes:
                                    imagen_filename = f"imagen_hd_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                    with open(os.path.join(OUTPUT_DIR, imagen_filename), "wb") as f:
                                        f.write(img_bytes)
                                    image_base64 = base64.b64encode(img_bytes).decode()
                                    is_ai_image = True
                                    print(f"DEBUG: HD AI Replacement Generated OK ({len(img_bytes)//1024}KB)")
                except Exception as e:
                    print(f"DEBUG: Image base64 conversion failed: {e}")
            else:
                print(f"DEBUG: No image URL available for this post")
            
            # Final Image Source Strategy:
            # 1. Try Base64 (Most reliable for rendering)
            # 2. Try Local File Path (Fail-safe for GCP permissions)
            # 3. Fallback to raw URL
            if image_base64:
                final_image_src = f"data:image/jpeg;base64,{image_base64}"
            elif image_url and image_url.startswith("/static/output/"):
                # Convert relative static path to absolute file URL for Playwright
                filename_only = os.path.basename(image_url)
                abs_path = os.path.join(OUTPUT_DIR, filename_only)
                final_image_src = f"file://{abs_path}"
                print(f"DEBUG: Using file:// fallback for local asset: {final_image_src}")
            else:
                final_image_src = image_url or ""
            
            if not final_image_src:
                print("DEBUG: CRITICAL - final_image_src is EMPTY. Background will be black.")
            
            # 3. Generate Deep Caption
            caption_data = await self.summarizer.generate_deep_caption(summary['headline'], summary['subtitle'], item['summary'])
            full_caption = caption_data.get('caption', f"{summary['headline']}\n\n{summary['subtitle']}")
            
            # 4. Template selection — dramatic (AI image) vs standard (web image)
            if is_ai_image:
                template_path = os.path.join(STUDIO_TEMPLATES_DIR, "EDITORIAL", "DRAMATIC.html")
                if not os.path.exists(template_path):
                    template_path = os.path.join(STUDIO_TEMPLATES_DIR, "EDITORIAL", "POST.html")
            else:
                template_path = os.path.join(STUDIO_TEMPLATES_DIR, "EDITORIAL", "POST.html")
            
            with open(template_path, 'r') as f:
                template_str = f.read()

            # 5. Render at 4:5
            width, height = 1080, 1350
            filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}.png"
            path = await self.render_post(
                {**summary, "image_url": final_image_src, "is_dramatic": is_ai_image},
                template_str,
                filename,
                width=width,
                height=height
            )
            
            DatabaseManager.save_post(topic, summary['headline'], summary['subtitle'], full_caption, path, item['link'])
            return path
        except Exception as e:
            print(f"ENGINE ERROR: generate_standard_post failed: {e}")
            return None

    async def generate_satire_post(self, topic, aspect_ratio="9:16", language="english"):
        # Fetch news first to get context
        items = NewsFetcher.fetch_by_topic(topic, count=1)
        news_context = ""
        image_url = None
        source_url = "Satire Studio"
        if items:
            item = items[0]
            news_context = f"{item['title']} - {item['summary']}"
            source_url = item['link']
            image_url = await NewsFetcher.extract_hero_image(item['link'])
        
        # 1. Spin the Satire
        satire_data = await self.summarizer.generate_satire(topic, news_context, language=language)
        if not satire_data: return None
        
        # 2. Image Sourcing (AI-first for satire)
        if not image_url or "google" in image_url.lower():
            query, _, _, imagen_prompt = await self.summarizer.generate_search_query(satire_data.get('headline', topic), news_context)
            search_results = await NewsFetcher.search_image(query)
            
            if search_results:
                image_url = search_results[0]
            else:
                # GCP: Imagen 3
                print(f"DEBUG: No web image found for satire. Generating with Imagen 3.")
                img_bytes = await self.summarizer.client.generate_image(imagen_prompt, aspect_ratio=aspect_ratio)
                if img_bytes:
                    imagen_filename = f"imagen_satire_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    with open(os.path.join(OUTPUT_DIR, imagen_filename), "wb") as f:
                        f.write(img_bytes)
                    image_url = f"/static/output/{imagen_filename}"
        
        if not image_url:
            image_url = f"https://loremflickr.com/1080/1080/{urllib.parse.quote(topic)},politics,india"
        
        # 3. Template — always EDITORIAL/SATIRE.html
        template_path = os.path.join(STUDIO_TEMPLATES_DIR, "EDITORIAL", "SATIRE.html")
        with open(template_path, 'r') as f:
            template_str = f.read()

        # 4. Render
        dims = {"9:16": (1080, 1920), "4:5": (1080, 1350)}
        width, height = dims.get(aspect_ratio, (1080, 1920))
        filename = f"satire_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}.png"
        
        path = await self.render_post(
            {**satire_data, "image_url": image_url},
            template_str,
            filename,
            width=width,
            height=height
        )
        
        headline = satire_data.get('headline', 'STRIKE')
        subtext = satire_data.get('subtext', satire_data.get('subtitle', 'Strategic Calibration'))
        caption = satire_data.get('caption', 'Deep focus on systemic growth.')
        hashtags = satire_data.get('hashtags', '')
        full_caption = f"{caption}\n\n{hashtags}\n\nFollow @Humorously_Indians for more posts."
        
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
            
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1350:force_original_aspect_ratio=decrease,pad=1080:1350:(ow-iw)/2:(oh-ih)/2",
            "-c:a", "aac", "-shortest",
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
