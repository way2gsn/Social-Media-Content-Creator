from fastapi import FastAPI, BackgroundTasks, Form, Request, UploadFile, File
import random
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import asyncio
import sqlite3
from glue import InstagramEngine, NewsFetcher, DatabaseManager, DB_PATH, Musicalizer, STATIC_DIR, AISummarizer
from explainer_engine import ExplainerEngine
from instagram_uploader import InstagramUploader
from instagram_api import InstagramAPIEngine
from video_engine import CinematicVideoEngine

# Absolute Paths for robust worker execution
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# Docker Check: If we are in /app, the root is also /app
if BACKEND_DIR == "/app":
    ROOT_DIR = "/app"
else:
    ROOT_DIR = os.path.dirname(BACKEND_DIR)

STATIC_DIR = os.path.join(ROOT_DIR, "static")
OUTPUT_DIR = os.path.join(STATIC_DIR, "output")

uploader = InstagramUploader()
api_uploader = InstagramAPIEngine()

DB_PATH = os.path.join(BACKEND_DIR, "automation.db")
# Backend Version (Must match UI version)
VERSION = "2.1.0" # Neural Mobile Engine Upgrade

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving - must match where glue.py saves output (ROOT_DIR/static)
STATIC_DIR = os.path.join(ROOT_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "output"), exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

tasks = {}
engine = InstagramEngine()
explainer_engine = ExplainerEngine()

def update_task(task_id, status, progress, log_msgs=None):
    if task_id in tasks:
        tasks[task_id]["status"] = status
        tasks[task_id]["progress"] = progress
        if log_msgs:
            tasks[task_id]["logs"].extend(log_msgs)

@app.on_event("startup")
async def startup_event():
    DatabaseManager.init_db()
    # Add default setting for full auto if missing
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('full_auto', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_schedule', 'true')")
    conn.commit()
    conn.close()
    
    asyncio.create_task(perpetual_scheduler())
    asyncio.create_task(autonomous_background_loop())
    print("🚀 All Background Systems Online (Scheduler + Autonomous Engine)")

async def perpetual_scheduler():
    """Background loop to check for due posts and upload them."""
    print("DEBUG: Scheduler worker started.")
    while True:
        try:
            settings = DatabaseManager.get_settings()
            mode = settings.get("scheduler_mode", "automation")
            pending = DatabaseManager.get_pending_schedules()
            
            for task in pending:
                try:
                    print(f"DEBUG: Processing schedule {task['id']} for post {task['post_id']} (Mode: {mode})")
                    DatabaseManager.update_schedule_status(task['id'], "uploading")
                    
                    success, msg = False, "Unknown Error"
                    
                    if mode == "api":
                        token = settings.get("ig_access_token")
                        biz_id = settings.get("ig_business_id")
                        
                        if not token or not biz_id:
                            success, msg = False, "Missing Instagram API Token or Business ID"
                        else:
                            api_engine = InstagramAPIEngine(access_token=token, business_id=biz_id)
                            
                            # ─── CAROUSEL DETECTION ───
                            is_carousel = "carousels/" in task['asset_path']
                            
                            if is_carousel:
                                # 1. Find all slides in the folder
                                folder_rel = os.path.dirname(task['asset_path'])
                                folder_full = os.path.join(OUTPUT_DIR, folder_rel)
                                
                                slides = sorted([f for f in os.listdir(folder_full) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
                                if not slides:
                                    success, msg = False, "No slides found in carousel folder."
                                else:
                                    item_ids = []
                                    print(f"DEBUG: Processing carousel with {len(slides)} slides.")
                                    
                                    for s in slides:
                                        s_path = os.path.join(folder_full, s)
                                        p_url, p_err = await api_engine.upload_to_proxy(s_path)
                                        if not p_url:
                                            msg = f"Slide Proxy Error: {p_err}"
                                            break
                                        
                                        c_id, c_err = await api_engine.create_carousel_item_container(p_url)
                                        if not c_id:
                                            msg = f"Item Container Error: {c_err}"
                                            break
                                        
                                        # Wait for item to be ready
                                        ready, r_err = await api_engine.check_container_status(c_id)
                                        if not ready:
                                            msg = f"Item Ready Error: {r_err}"
                                            break
                                        
                                        item_ids.append(c_id)
                                    
                                    if len(item_ids) == len(slides):
                                        # Create master carousel container
                                        master_id, m_err = await api_engine.create_carousel_container(item_ids, task['caption'])
                                        if master_id:
                                            ready, r_err = await api_engine.check_container_status(master_id)
                                            if ready:
                                                success, msg = await api_engine.publish_media(master_id)
                                            else:
                                                success, msg = False, f"Master Ready Error: {r_err}"
                                        else:
                                            success, msg = False, m_err
                                    else:
                                        success = False
                                        # msg is already set in the loop
                            else:
                                # ─── SINGLE POST ───
                                full_asset_path = os.path.join(OUTPUT_DIR, task['asset_path'])
                                public_url, p_msg = await api_engine.upload_to_proxy(full_asset_path)
                                
                                if not public_url:
                                    success, msg = False, f"Proxy Error: {p_msg}"
                                else:
                                    # Determine if it's a video/reel or image
                                    is_video = task['asset_path'].lower().endswith(('.mp4', '.mov', '.m4v'))
                                    if is_video:
                                        container_id, c_msg = await api_engine.create_reels_container(public_url, task['caption'])
                                    else:
                                        container_id, c_msg = await api_engine.create_media_container(public_url, task['caption'])

                                    if container_id:
                                        ready, r_msg = await api_engine.check_container_status(container_id)
                                        if ready:
                                            success, msg = await api_engine.publish_media(container_id)
                                        else:
                                            success, msg = False, r_msg
                                    else:
                                        success, msg = False, c_msg
                    else:
                        full_image_path = os.path.join(OUTPUT_DIR, task['asset_path'])
                        success, msg = await uploader.upload_post(full_image_path, task['caption'])
                    
                    if success:
                        DatabaseManager.update_schedule_status(task['id'], "completed")
                        # ─── AUTO-STORY ───
                        try:
                            # After successful main post, try to add to Story
                            if public_url:
                                is_v = task['asset_path'].lower().endswith(('.mp4', '.mov', '.m4v'))
                                s_id, s_err = await api_engine.create_story_container(public_url, is_video=is_v)
                                if s_id:
                                    # Wait for story container to be ready (especially for videos)
                                    ready, r_msg = await api_engine.check_container_status(s_id)
                                    if ready:
                                        await api_engine.publish_media(s_id)
                                        print(f"DEBUG: Successfully posted to Story for task {task['id']}")
                        except Exception as e:
                            print(f"DEBUG: Auto-Story failed: {e}")
                    else:
                        DatabaseManager.update_schedule_status(task['id'], "failed", msg)
                except Exception as e:
                    print(f"TASK ERROR: {e}")
                    DatabaseManager.update_schedule_status(task['id'], "failed", str(e))
        except Exception as e:
            print(f"SCHEDULER LOOP ERROR: {e}")
            
        await asyncio.sleep(60)

@app.get("/version")
async def get_version():
    return {"version": VERSION}

@app.get("/gallery")
async def get_gallery():
    posts = DatabaseManager.get_all_posts()
    return JSONResponse({"posts": posts})

# ─── 1. STANDARD POST (4:5 or 9:16) ─────────────────────────
@app.post("/generate")
async def generate_endpoint(topics: str = Form(...), count: int = Form(5), language: str = Form("english"), aspect_ratio: str = Form("4:5"), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Fetching news...",
        "progress": 0,
        "logs": [f"Initialized Standard Post ({aspect_ratio}) for {topics}"],
        "results": []
    }
    background_tasks.add_task(generate_standard_batch, task_id, topic_list, count, language, aspect_ratio)
    return {"task_id": task_id}

# ─── 2. CAROUSEL (4:5 or 9:16) ─────────────────
@app.post("/generate-carousel")
async def generate_carousel_endpoint(topics: str = Form(...), count: int = Form(1), language: str = Form("english"), aspect_ratio: str = Form("4:5"), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Starting Carousel Engine...",
        "progress": 0,
        "logs": [f"Initialized Carousel ({aspect_ratio}) for {topics}"],
        "results": []
    }
    background_tasks.add_task(run_carousel_generation, task_id, topic_list, language, count, aspect_ratio)
    return {"task_id": task_id}

# ─── 3. QUOTE POST (4:5 or 9:16) ───────────────
@app.post("/generate-quote")
async def generate_quote_endpoint(topics: str = Form(...), language: str = Form("english"), aspect_ratio: str = Form("9:16"), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Starting Quote Engine...",
        "progress": 0,
        "logs": [f"Initialized Premium Quote ({aspect_ratio}) for {topics}"],
        "results": []
    }
    background_tasks.add_task(run_quote_generation, task_id, topic_list, language, aspect_ratio)
    return {"task_id": task_id}

# ─── 4. MAGAZINE POST (High-End Art Director Test) ───────────
@app.post("/generate-magazine")
async def generate_magazine_endpoint(topics: str = Form(...), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Starting Magazine Art Director...",
        "progress": 0,
        "logs": [f"Initialized Senior Art Director 'MAGAZINE' Post for {topics}"],
        "results": []
    }
    # We use the quote generation runner as it's been upgraded to the Magazine logic
    background_tasks.add_task(run_quote_generation, task_id, topic_list, "english", "9:16")
    return {"task_id": task_id}

# ─── 4. CINEMATIC VIDEO (9:16, AI script, Veo, TTS) ────────────
@app.post("/generate-cinematic")
async def generate_cinematic_endpoint(topics: str = Form(...), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Starting Cinematic Engine...",
        "progress": 0,
        "logs": [f"Initialized Cinematic Video Engine for {topics}"],
        "results": []
    }
    background_tasks.add_task(run_cinematic_generation, task_id, topic_list)
    return {"task_id": task_id}

@app.delete("/delete_post/{post_id}")
async def delete_post(post_id: int):
    try:
        print(f"DEBUG: Attempting to delete post ID {post_id}")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get asset path first to delete file
        c.execute("SELECT asset_path FROM posts WHERE id = ?", (post_id,))
        row = c.fetchone()
        if row:
            asset_path = row[0]
            # Delete from static folder
            full_path = os.path.join(STATIC_DIR, "output", os.path.basename(asset_path))
            if os.path.exists(full_path):
                os.remove(full_path)
                print(f"DEBUG: Deleted physical file {full_path}")
        
        # Delete from DB
        c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        # FIX: Table name is 'schedules' (plural)
        c.execute("DELETE FROM schedules WHERE post_id = ?", (post_id,))
        conn.commit()
        conn.close()
        print(f"DEBUG: Successfully deleted post {post_id} from database")
        return {"status": "success"}
    except Exception as e:
        print(f"ERROR: Delete post failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return tasks[task_id]

@app.get("/schedules")
async def get_schedules_endpoint():
    schedules = DatabaseManager.get_schedules()
    return JSONResponse({"schedules": schedules})

@app.post("/schedule")
async def schedule_endpoint(post_id: int = Form(...), scheduled_at: str = Form(...), caption: str = Form(...)):
    DatabaseManager.schedule_post(post_id, scheduled_at, caption)
    return {"status": "Scheduled successfully"}

@app.delete("/schedule/{schedule_id}")
async def delete_schedule_endpoint(schedule_id: int):
    DatabaseManager.delete_schedule(schedule_id)
    return {"status": "Schedule deleted"}

@app.post("/instagram/setup")
async def setup_instagram():
    background_tasks = BackgroundTasks()
    background_tasks.add_task(uploader.setup_login)
    return {"status": "Setup started in background"}

@app.get("/settings")
async def get_settings():
    settings = DatabaseManager.get_settings()
    # Also return available tracks
    musicalizer = Musicalizer()
    settings["available_tracks"] = musicalizer.get_tracks()
    return settings

@app.post("/settings")
async def save_settings(data: dict):
    for k, v in data.items():
        if k != "available_tracks":
            DatabaseManager.save_setting(k, str(v))
    return {"status": "Success"}

@app.post("/upload-audio")
async def upload_audio_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.mp3', '.wav', '.m4a')):
        return JSONResponse({"error": "Only .mp3, .wav, or .m4a files are allowed"}, status_code=400)
    
    audio_dir = os.path.join(STATIC_DIR, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    
    # Sanitize filename
    clean_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in file.filename])
    file_path = os.path.join(audio_dir, clean_name)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    return {"status": "Success", "filename": clean_name}

@app.delete("/audio/{filename}")
async def delete_audio_endpoint(filename: str):
    audio_dir = os.path.join(STATIC_DIR, "audio")
    file_path = os.path.join(audio_dir, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "Deleted"}
    return JSONResponse({"error": "File not found"}, status_code=404)

# ─── BACKGROUND WORKERS ──────────────────────────────────────────────

async def generate_standard_batch(task_id, topics, count, language, aspect_ratio="4:5"):
    engine = InstagramEngine()
    musicalizer = Musicalizer()
    settings = DatabaseManager.get_settings()
    use_music = settings.get("use_music") == "true"
    default_track = settings.get("default_track")
    
    # 1. Fetch News
    try:
        update_task(task_id, "Searching News...", 10)
        # Use a timeout for the entire batch fetch
        items = NewsFetcher.fetch_batch(topics, count=count)
    except Exception as e:
        update_task(task_id, "Error: News Fetch Failed", 0, [f"ERROR: {str(e)}"])
        return

    if not items:
        update_task(task_id, "Error: No news found", 0, ["ERROR: News search returned empty results."])
        return

    # 2. Process Batch with overall timeout
    for i, item in enumerate(items):
        try:
            progress = 20 + int((i / len(items)) * 70)
            topic = item.get('title', topics[0] if topics else "News")
            update_task(task_id, f"Processing {i+1}/{len(items)}: {topic[:40]}...", progress, [f"Rendering: {topic}"])
            
            # Wrap each post in a timeout (Increased to 600s to allow for backoffs)
            async def generate_with_timeout():
                return await engine.generate_standard_post(item, topic, aspect_ratio=aspect_ratio, language=language)
            
            path = await asyncio.wait_for(generate_with_timeout(), timeout=600)
            
            # MANDATORY DELAY: 2 minutes between every generation as requested
            if i < len(items) - 1:
                update_task(task_id, f"Resting for 2 mins...", progress + 2, [f"Delay: Waiting 120s before next post for stability..."])
                await asyncio.sleep(120)
            
            # Musicalization
            if use_music and path:
                tracks = musicalizer.get_tracks()
                if tracks:
                    track = default_track if default_track in tracks else tracks[0]
                    update_task(task_id, f"Adding Music: {track}...", progress + 5, [f"Musicalizing {path}..."])
                    # path is relative to static/output
                    abs_img_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
                    video_filename, v_msg = await musicalizer.create_reel(abs_img_path, track)
                    
                    if video_filename:
                        # Update post in DB to use video
                        new_path = video_filename # Musicalizer returns filename only
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        # We find the post we just saved and update it
                        c.execute("UPDATE posts SET asset_path = ? WHERE asset_path = ?", (new_path, path))
                        conn.commit()
                        conn.close()
                        print(f"DEBUG: Post upgraded to video: {new_path}")
        except Exception as e:
            update_task(task_id, f"Error on item {i+1}", progress, [f"ERROR: {str(e)}"])
    
    update_task(task_id, "Success", 100, ["Batch complete! Check gallery."])

async def run_carousel_generation(task_id, topics, language, count=1, aspect_ratio="4:5"):
    try:
        total = len(topics)
        completed = 0
        for topic in topics:
            update_task(task_id, f"Planning carousel for {topic}...", int((completed / total) * 100), [f"Starting carousel analysis for '{topic}'"])
            paths, status_msg = await explainer_engine.generate_explainer(topic, aspect_ratio=aspect_ratio, language=language, count=count)
            update_task(task_id, f"Rendering carousel...", int(((completed + 0.5) / total) * 100), [f"Engine: {status_msg}"])
            if paths:
                if task_id in tasks: tasks[task_id]["results"].extend(paths)
                update_task(task_id, f"Carousel complete", int(((completed + 1) / total) * 100), [f"{len(paths)} slides rendered successfully."])
            
            # MANDATORY DELAY: 2 minutes between every carousel item as requested
            if completed < total - 1:
                update_task(task_id, "Resting for 2 mins...", int(((completed + 1) / total) * 100), ["Delay: Waiting 120s before next carousel for stability..."])
                await asyncio.sleep(120)

            completed += 1
        update_task(task_id, "Success", 100, ["Carousel batch complete!"])
    except Exception as e:
        update_task(task_id, "Error", 0, [f"CRITICAL ERROR: {str(e)}"])

async def run_quote_generation(task_id, topics, language, aspect_ratio="9:16"):
    try:
        from glue import Musicalizer, DatabaseManager, STATIC_DIR
        import os
        import sqlite3
        
        settings = DatabaseManager.get_settings()
        use_music = settings.get('use_music', False)
        default_track = settings.get('default_track', 'lofi')
        musicalizer = Musicalizer()
        
        total = len(topics)
        completed = 0
        for topic in topics:
            update_task(task_id, f"Planning quote for {topic}...", int((completed / total) * 100), [f"Starting quote analysis for '{topic}'"])
            path, status_msg = await explainer_engine.generate_quote_post(topic, language=language, aspect_ratio=aspect_ratio)
            update_task(task_id, f"Rendering quote...", int(((completed + 0.5) / total) * 100), [f"Engine: {status_msg}"])
            
            if path:
                # Video Conversion (Musicalizer)
                if use_music:
                    tracks = musicalizer.get_tracks()
                    if tracks:
                        track = default_track if default_track in tracks else tracks[0]
                        update_task(task_id, f"Adding Music: {track}...", int(((completed + 0.8) / total) * 100), [f"Musicalizing {path}..."])
                        abs_img_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
                        video_filename, v_msg = await musicalizer.create_reel(abs_img_path, track)
                        
                        if video_filename:
                            new_path = video_filename
                            conn = sqlite3.connect(DB_PATH)
                            c = conn.cursor()
                            c.execute("UPDATE posts SET asset_path = ? WHERE asset_path = ?", (new_path, path))
                            conn.commit()
                            conn.close()
                            path = new_path
                            print(f"DEBUG: Quote upgraded to video: {new_path}")
                
                if task_id in tasks: tasks[task_id]["results"].append(path)
                update_task(task_id, f"Quote complete", int(((completed + 1) / total) * 100), [f"Quote rendered successfully."])
            completed += 1
        update_task(task_id, "Success", 100, ["Quote batch complete!"])
    except Exception as e:
        update_task(task_id, "Error", 0, [f"CRITICAL ERROR: {str(e)}"])

async def run_cinematic_generation(task_id, topics):
    try:
        from video_engine import CinematicVideoEngine
        from glue import DatabaseManager
        import os
        
        engine = CinematicVideoEngine()
        total = len(topics)
        completed = 0
        
        for topic in topics:
            update_task(task_id, f"Writing script for {topic}...", int((completed / total) * 100), [f"Starting Cinematic Engine for '{topic}'"])
            path, msg, script_data = await engine.generate_video(topic)
            update_task(task_id, f"Rendering video...", int(((completed + 0.8) / total) * 100), [f"Engine: {msg}"])
            
            if path and script_data:
                caption = script_data.get('instagram_caption', 'Autogenerated pro documentary')
                if task_id in tasks: tasks[task_id]["results"].append(os.path.basename(path))
                # Save to DB
                DatabaseManager.save_post(
                    topic, f"Cinematic Video: {topic}", "Veo & TTS", caption, os.path.basename(path), "Cinematic Studio"
                )
                update_task(task_id, f"Video complete", int(((completed + 1) / total) * 100), [f"Video rendered successfully."])
            completed += 1
        update_task(task_id, "Success", 100, ["Cinematic batch complete!"])
    except Exception as e:
        update_task(task_id, "Error", 0, [f"CRITICAL ERROR: {str(e)}"])

# ─── AUTONOMOUS FULL-AUTO ENGINE ──────────────────────────────────────

class AutonomousAutomation:
    @staticmethod
    async def run_cycle():
        """
        Runs 4 times a day.
        Generates 2-3 posts and 1-2 Reels.
        Schedules them randomly with 1-3 hour gaps.
        """
        print("🤖 [AUTONOMOUS] Starting Full-Auto Content Cycle...")
        engine = InstagramEngine()
        musicalizer = Musicalizer()
        from datetime import datetime, timedelta
        from glue import AISummarizer
        explainer_engine = ExplainerEngine()
        
        # 1. Determine topics (Authentic Investigative Reporting)
        topics = [
            "Indian Political Analysis", "Government Policy Impact", "Indian Economic Growth Data", 
            "Middle Class Reality India", "Urban Infrastructure Audit India", "Political Promises Progress Report",
            "Indian Judicial System Background", "Public Transport Infrastructure India", "Digital Divide India",
            "Environmental Policy Ground Reality India", "Education System Reforms India",
            "Taxation Structure Analysis India", "Indian Diplomacy Deep-Dive", "Bureaucracy Efficiency Report India"
        ]
        random.shuffle(topics)
        
        # 2. Daily Content Strategy Mix (Deterministic 24-hour Cycle)
        # Goal: 1x 4:5, 3x 9:16 (Std/Quote), 2x Reels
        current_hour = datetime.now().hour
        generation_tasks = []

        # Define what to generate based on the 6-hour cycle
        if 0 <= current_hour < 6:
            # Cycle 1: 1 Reel + 2 Standard (9:16)
            generation_tasks = [("REEL", "9:16"), ("STANDARD", "9:16"), ("STANDARD", "9:16")]
        elif 6 <= current_hour < 12:
            # Cycle 2: 1 Reel + 2 Standard (4:5)
            generation_tasks = [("REEL", "9:16"), ("STANDARD", "4:5"), ("STANDARD", "4:5")]
        elif 12 <= current_hour < 18:
            # Cycle 3: 1 Reel + 2 Standard (9:16) + 1 Quote (9:16)
            generation_tasks = [("REEL", "9:16"), ("STANDARD", "9:16"), ("STANDARD", "9:16"), ("QUOTE", "9:16")]
        else:
            # Cycle 4: 2 Standard (9:16) + 1 Quote (9:16)
            generation_tasks = [("STANDARD", "9:16"), ("STANDARD", "9:16"), ("QUOTE", "9:16")]

        generated_assets = [] 
        
        # Process Tasks
        items = NewsFetcher.fetch_batch(topics[:len(generation_tasks) + 1], count=len(generation_tasks))
        for i, task in enumerate(generation_tasks):
            try:
                task_type, aspect_ratio = task
                item = items[i] if i < len(items) else items[0]
                
                # Intelligent Format Override: Check if news is a "Big Statement"
                is_quote_worthy = await AISummarizer.is_quote_worthy(item['title'], item['summary'])
                if is_quote_worthy and task_type == "STANDARD":
                    print(f"🤖 [AUTONOMOUS] Intelligence: Significant Statement detected. Overriding STANDARD -> QUOTE for '{item['title']}'")
                    task_type = "QUOTE"
                    aspect_ratio = "9:16" # Quote posts are always 9:16 vertical
                
                print(f"🤖 [AUTONOMOUS] Cycle Task: Generating {task_type} ({aspect_ratio}) for: {item['title']}")
                path = None
                
                lang_instruction = "OUTPUT LANGUAGE: Simple English."
                if task_type == "REEL":
                    cine_engine = CinematicVideoEngine()
                    path, _, _ = await cine_engine.generate_video(item['title'])
                elif task_type == "QUOTE":
                    path, _ = await explainer_engine.generate_quote_post(item['title'], language="english")
                else: # STANDARD
                    path = await engine.generate_standard_post(item, item['title'], language="english", aspect_ratio=aspect_ratio)
                
                if path:
                    # Musicalize if not a video
                    is_video = path.endswith((".mp4", ".mov"))
                    if not is_video:
                        tracks = musicalizer.get_tracks()
                        abs_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
                        if tracks:
                            v_file, _ = await musicalizer.create_reel(abs_path, random.choice(tracks))
                            if v_file: path = v_file
                    
                    # The generation engines already saved to DB.
                    # We just need to fetch the latest post for scheduling.
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("SELECT id, caption, asset_path FROM posts ORDER BY id DESC LIMIT 1")
                    row = c.fetchone()
                    if row:
                        generated_assets.append({'id': row[0], 'caption': row[1], 'asset_path': row[2]})
                    conn.close()
            except Exception as e: print(f"DEBUG: Auto Content Task Failed: {e}")

        # 3. Schedule them randomly if enabled
        settings = DatabaseManager.get_settings()
        if settings.get("auto_schedule") != "true":
            print("🤖 [AUTONOMOUS] Auto-Scheduling is DISABLED. Posts saved to gallery, skipping queue.")
            return

        # Start from 1 hour from now
        current_time = datetime.now() + timedelta(hours=1)
        
        for asset in generated_assets:
            # Add random gap 1-3 hours (60 to 180 minutes)
            gap = random.randint(60, 180) 
            current_time += timedelta(minutes=gap)
            sched_str = current_time.strftime("%Y-%m-%dT%H:%M")
            DatabaseManager.schedule_post(asset['id'], sched_str, asset['caption'])
            print(f"🤖 [AUTONOMOUS] Scheduled post {asset['id']} for {sched_str}")

async def autonomous_background_loop():
    """Background task that triggers the autonomous cycle. 
    Checks settings every 10 mins, but only runs content cycle every 6 hours."""
    last_run = None
    while True:
        try:
            settings = DatabaseManager.get_settings()
            if settings.get("full_auto") == "true":
                # Check if 6 hours have passed since last run
                if last_run is None or (datetime.now() - last_run) > timedelta(hours=6):
                    await AutonomousAutomation.run_cycle()
                    last_run = datetime.now()
                else:
                    wait_time = (last_run + timedelta(hours=6) - datetime.now()).total_seconds()
                    print(f"🤖 [AUTONOMOUS] Next cycle in {int(wait_time/60)} minutes.")
            else:
                # Reset last_run so it starts immediately when toggled ON
                last_run = None
                print("🤖 [AUTONOMOUS] Full-Auto is OFF. Checking again in 10 mins.")
        except Exception as e:
            print(f"🤖 [AUTONOMOUS] Loop Error: {e}")
        
        # Check setting every 10 minutes (600 seconds)
        await asyncio.sleep(600)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
