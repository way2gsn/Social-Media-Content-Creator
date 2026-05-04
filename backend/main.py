from fastapi import FastAPI, BackgroundTasks, Form, Request, UploadFile, File
import random
from datetime import timedelta
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import asyncio
import sqlite3
from glue import InstagramEngine, NewsFetcher, DatabaseManager, DB_PATH, Musicalizer, STATIC_DIR
from explainer_engine import ExplainerEngine
from instagram_uploader import InstagramUploader
from instagram_api import InstagramAPIEngine

# Absolute Paths for robust worker execution
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
STATIC_DIR = os.path.join(ROOT_DIR, "static")
OUTPUT_DIR = os.path.join(STATIC_DIR, "output")

uploader = InstagramUploader()
api_uploader = InstagramAPIEngine()

DB_PATH = "automation.db"
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("../static/output", exist_ok=True)
app.mount("/static", StaticFiles(directory="../static"), name="static")

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
                                
                                slides = sorted([f for f in os.listdir(folder_full) if f.endswith(".png")])
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

@app.get("/gallery")
async def get_gallery():
    posts = DatabaseManager.get_all_posts() if hasattr(DatabaseManager, 'get_all_posts') else []
    return JSONResponse({"posts": posts})

# ─── 1. STANDARD POST (4:5, template-based) ─────────────────────────
@app.post("/generate")
async def generate_endpoint(topics: str = Form(...), count: int = Form(5), language: str = Form("english"), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Fetching news...",
        "progress": 0,
        "logs": [f"Initialized Standard Post for {topics} ({language})"],
        "results": []
    }
    background_tasks.add_task(generate_standard_batch, task_id, topic_list, count, language)
    return {"task_id": task_id}

# ─── 2. CAROUSEL (4:5, multi-slide, template-based) ─────────────────
@app.post("/generate-carousel")
async def generate_carousel_endpoint(topics: str = Form(...), count: int = Form(1), language: str = Form("english"), background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    topic_list = [t.strip() for t in topics.split(",")]
    tasks[task_id] = {
        "status": "Starting Carousel Engine...",
        "progress": 0,
        "logs": [f"Initialized Carousel for {topics} ({language})"],
        "results": []
    }
    background_tasks.add_task(run_carousel_generation, task_id, topic_list, language, count)
    return {"task_id": task_id}

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

async def generate_standard_batch(task_id, topics, count, language):
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
            
            # Wrap each post in a timeout
            async def generate_with_timeout():
                return await engine.generate_standard_post(item, topic, language=language)
            
            path = await asyncio.wait_for(generate_with_timeout(), timeout=120)
            
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

async def run_carousel_generation(task_id, topics, language, count=1):
    try:
        total = len(topics)
        completed = 0
        for topic in topics:
            update_task(task_id, f"Planning carousel for {topic}...", int((completed / total) * 100), [f"Starting carousel analysis for '{topic}'"])
            paths, status_msg = await explainer_engine.generate_explainer(topic, aspect_ratio="4:5", language=language, count=count)
            update_task(task_id, f"Rendering carousel...", int(((completed + 0.5) / total) * 100), [f"Engine: {status_msg}"])
            if paths:
                if task_id in tasks: tasks[task_id]["results"].extend(paths)
                update_task(task_id, f"Carousel complete", int(((completed + 1) / total) * 100), [f"{len(paths)} slides rendered successfully."])
            completed += 1
        update_task(task_id, "Success", 100, ["Carousel batch complete!"])
    except Exception as e:
        update_task(task_id, "Error", 0, [f"CRITICAL ERROR: {str(e)}"])

# DB patch
def patch_db_manager():
    def get_all_posts():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM posts ORDER BY created_at DESC")
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows
    DatabaseManager.get_all_posts = staticmethod(get_all_posts)

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
        from datetime import datetime
        
        # 1. Determine topics (Trending news)
        topics = ["India Economy", "Tech India", "Startup India", "Political Irony", "Global News"]
        random.shuffle(topics)
        
        # 2. Cycle Strategy: Generate a mix to reach 10 posts/5 reels per day
        post_count = random.choice([2, 3])
        
        generated_assets = [] 
        
        # Generate Standard Posts
        items = NewsFetcher.fetch_batch(topics[:2], count=post_count)
        for item in items:
            try:
                # Use a background task style generation
                path = await engine.generate_standard_post(item, item['title'], language="english")
                if path:
                    # Check if we should musicalize
                    tracks = musicalizer.get_tracks()
                    abs_path = os.path.join(STATIC_DIR, "output", os.path.basename(path))
                    final_path = path
                    if tracks:
                        v_file, _ = await musicalizer.create_reel(abs_path, random.choice(tracks))
                        if v_file: final_path = v_file
                    
                    # Get post_id (last inserted)
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("SELECT id, caption, asset_path FROM posts ORDER BY id DESC LIMIT 1")
                    row = c.fetchone()
                    if row:
                        generated_assets.append({'id': row[0], 'caption': row[1], 'asset_path': row[2]})
                    conn.close()
            except Exception as e: print(f"DEBUG: Auto Post Gen Failed: {e}")

        # 3. Schedule them randomly
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
    """Background task that triggers the autonomous cycle every 6 hours."""
    while True:
        try:
            # Only run if enabled in settings
            settings = DatabaseManager.get_settings()
            if settings.get("full_auto") == "true":
                await AutonomousAutomation.run_cycle()
            else:
                print("🤖 [AUTONOMOUS] Full-Auto is OFF. Skipping cycle.")
        except Exception as e:
            print(f"🤖 [AUTONOMOUS] Loop Error: {e}")
        
        # Wait 6 hours (21600 seconds)
        await asyncio.sleep(21600)

patch_db_manager()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
