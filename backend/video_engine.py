import os
import json
import asyncio
import uuid
import subprocess
from datetime import datetime
from gcp_client import get_gcp_client

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR == "/app":
    ROOT_DIR = "/app"
else:
    ROOT_DIR = os.path.dirname(BACKEND_DIR)
STATIC_DIR = os.path.join(ROOT_DIR, "static")
OUTPUT_DIR = os.path.join(STATIC_DIR, "output")

class CinematicVideoEngine:
    def __init__(self):
        self.gcp = get_gcp_client()

    async def generate_script(self, topic: str):
        prompt = f"""You are a world-class investigative journalist and documentary filmmaker.
Write a professional, authoritative 30-45 second documentary script about: "{topic}"

STYLE: Professional Documentary / News Narrative. Serious, fast-paced, and fact-heavy.
CRITICAL: You MUST cite sources and data points (e.g., 'According to a recent report by Reuters...', 'Data from the World Bank shows...').

CRITICAL: The narration MUST be written in "Romanized Hinglish" (Hindi words written in English letters, mixed with English).
Avoid Pure Hindi or Devanagari script. Use the language Indians use on WhatsApp or social media.

EDITORIAL HOOK: The first scene MUST start with a "Catchy Hook". This should be a controversial line, a shocking fact, or a bold statement that hooks the audience instantly.

VISUALS: Every scene MUST be unique. Specify "Indian context" for all visual prompts. 

For each scene, provide:
1. "narration": Spoken text in Romanized Hinglish with source citations.
2. "veo_prompt": Unique cinematic visual prompt (9:16). CRITICAL SAFETY RULES FOR veo_prompt:
   - NEVER mention any real person's name, political party, religion, caste, or ethnicity.
   - NEVER use words like: protest, violence, arrest, death, corruption, scam, attack, war, weapon, blood, bomb, terror.
   - ONLY describe abstract visuals: cityscapes, data charts, buildings, documents, hands typing, aerial views, nature, infrastructure.
   - Keep it purely visual and cinematic. Example: "Aerial drone shot of a modern Indian city skyline at golden hour, 4K cinematic."
3. "source_name": Name of the source being cited (e.g., "REUTERS").

4. "instagram_caption": Generate a viral, ultra-detailed Instagram caption (100-150 words) in Simple English. Include a catchy headline, a summary of the data points, relevant hashtags, and a call to action.

Output MUST be a valid JSON object. Format example:
{{
    "headline": "Education Inequality: The Harsh Reality",
    "instagram_caption": "Detailed investigative report on the current state of Indian education...",
    "scenes": [
        {{
            "narration": "Kya aapko pata hai ki India ke education system mein abhi bhi kitna bada gap hai? NITI Aayog ki report ne saare pol khol diye hain.",
            "veo_prompt": "Cinematic wide shot of a rural Indian school building, professional photography style, rule of thirds.",
            "source_name": "NITI AAYOG"
        }}
    ]
}}
"""
        response_text = await self.gcp.generate_text(prompt, use_pro=True)
        if not response_text: 
            print(f"❌ [VIDEO ENGINE] AI returned empty response.")
            return None
        
        try:
            # Clean markdown formatting if present
            import re
            cleaned = re.sub(r'^```(?:json)?\s*\n?', '', response_text.strip())
            cleaned = re.sub(r'\n?```\s*$', '', cleaned)
            return json.loads(cleaned)
        except Exception as e:
            print(f"❌ [VIDEO ENGINE] JSON Error: {e} | Raw: {response_text[:500]}...")
            return None

    async def generate_video(self, topic: str, voice: str = "en-IN-Chirp3-HD-Zephyr"):
        script_data = await self.generate_script(topic)
        if not script_data or 'scenes' not in script_data:
            return None, "Failed to generate script", None

        session_id = f"cine_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session_dir = os.path.join(OUTPUT_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        print(f"📂 [CINEMATIC] Session Directory: {session_dir}")

        print(f"🎬 [CINEMATIC] Starting production for: {script_data.get('headline')}")
        
        # We will generate TTS and Veo clips sequentially to avoid hitting GCP 429 quota limits
        total_scenes = len(script_data['scenes'])
        scene_results = []
        for idx, scene in enumerate(script_data['scenes']):
            res = await self._process_scene(scene, idx, session_dir, voice, total_scenes)
            scene_results.append(res)
        
        # Skip failed scenes instead of aborting — assemble what we have
        successful_indices = [i for i, r in enumerate(scene_results) if r]
        if not successful_indices:
            return None, "All scenes failed to generate", None
        
        if len(successful_indices) < len(scene_results):
            failed = [i for i, r in enumerate(scene_results) if not r]
            print(f"⚠️ [CINEMATIC] Scenes {failed} failed. Assembling {len(successful_indices)} of {len(scene_results)} scenes.")

        # Assemble with FFmpeg
        final_video_path = os.path.join(OUTPUT_DIR, f"{session_id}.mp4")
        
        # Create a concat file for ffmpeg (only successful scenes)
        concat_path = os.path.join(session_dir, "concat.txt")
        with open(concat_path, "w") as f:
            for idx in successful_indices:
                # We generated a merged clip for each scene
                scene_video = os.path.join(session_dir, f"scene_{idx}_merged.mp4")
                f.write(f"file '{scene_video}'\n")

        # Combine all scenes
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            final_video_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                print(f"FFmpeg Concat Error: {stderr.decode()}")
                return None, "Video assembly failed", None
                
            # Clean up temp dir
            import shutil
            shutil.rmtree(session_dir, ignore_errors=True)
            
            print(f"✅ [CINEMATIC] Final Video Ready: {final_video_path}")
            print(f"🔗 [CINEMATIC] URL: /static/output/{session_id}.mp4")
            
            return final_video_path, "Success", script_data
        except Exception as e:
            print(f"Assembly Error: {e}")
            return None, str(e), None

    async def _process_scene(self, scene: dict, idx: int, session_dir: str, voice: str, total_scenes: int):
        # 1. Generate Audio and Timepoints via SSML
        words = scene['narration'].replace('"', '').split()
        ssml_parts = ["<speak>"]
        for i, word in enumerate(words):
            # Strip punctuation for cleaner marks
            clean_word = "".join(c for c in word if c.isalnum())
            ssml_parts.append(f'<mark name="w_{i}"/>{word}')
        ssml_parts.append(f'<mark name="w_{len(words)}"/></speak>')
        ssml_text = "".join(ssml_parts) # Use "".join to avoid extra spaces between marks

        audio_bytes, timepoints = await self.gcp.generate_tts(ssml_text, voice, is_ssml=True)
        if not audio_bytes: return False
        
        audio_path = os.path.join(session_dir, f"scene_{idx}.wav")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        # Create ASS Subtitle File for animated captions (2-line Red/White style)
        ass_path = os.path.join(session_dir, f"scene_{idx}.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
            f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            # Alignment 2 = Bottom Center. MarginV 500 = ~30% from bottom (1920 * 0.3 = 576)
            f.write("Style: Modern,Arial,110,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,20,20,500,1\n\n")
            f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            
            if timepoints and len(timepoints) > 1:
                # Group into 2-word chunks
                for i in range(0, len(words), 2):
                    start_time = next((t['time_seconds'] for t in timepoints if t['mark_name'] == f"w_{i}"), 0)
                    end_idx = min(i + 2, len(words))
                    end_time = next((t['time_seconds'] for t in timepoints if t['mark_name'] == f"w_{end_idx}"), start_time + 1.0)
                    
                    mid_time = next((t['time_seconds'] for t in timepoints if t['mark_name'] == f"w_{i+1}"), start_time + 0.5) if i+1 < len(words) else end_time

                    def to_ass_time(sec):
                        h, s = divmod(sec, 3600)
                        m, s = divmod(s, 60)
                        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
                    
                    t1, t2, t3 = to_ass_time(start_time), to_ass_time(mid_time), to_ass_time(end_time)
                    
                    # Line 1: Word 1, Line 2: Word 2
                    word1 = words[i]
                    word2 = words[i+1] if i+1 < len(words) else ""
                    
                    # Logic: 
                    # From t1 to mid_time: Word 1 is Red, Word 2 is White
                    # From mid_time to t3: Word 1 is Red (or exits?), Word 2 is Red?
                    # User: "first line will be in Red and second is white... first come White text then red one then exit"
                    
                    if word2:
                        # Show Word 1 (Red) and Word 2 (White) then switch
                        # First half: Word 1 Red, Word 2 White
                        f.write(f"Dialogue: 0,{t1},{t2},Modern,,0,0,0,,{{\\fad(50,0)}}{{\\fscx110\\fscy110\\t(0,100,\\fscx100\\fscy100)}}{{\\c&H000000FF&}}{word1}\\N{{\\c&H00FFFFFF&}}{word2}\n")
                        # Second half: Word 1 Red (or White), Word 2 Red
                        f.write(f"Dialogue: 0,{t2},{t3},Modern,,0,0,0,,{{\\c&H00FFFFFF&}}{word1}\\N{{\\c&H000000FF&}}{word2}\n")
                    else:
                        f.write(f"Dialogue: 0,{t1},{t3},Modern,,0,0,0,,{{\\fad(50,50)}}{{\\fscx110\\fscy110\\t(0,100,\\fscx100\\fscy100)}}{{\\c&H000000FF&}}{word1}\n")
            else:
                f.write(f"Dialogue: 0,0:00:00.00,0:00:05.00,Modern,,0,0,0,,{scene['narration']}\n")

        # 2. Visual Generation (Veo 3.1 Image-to-Video for First & Last scene, Imagen 3 for others)
        is_first = (idx == 0)
        is_last = (idx == total_scenes - 1)
        
        visual_data = None
        is_static = True
        
        if is_first or is_last:
            # Step A: Generate a high-quality image first via Imagen 3
            print(f"🖼️ [VEO] Step 1: Generating reference image for scene {idx+1}...")
            image_data = await self.gcp.generate_image(scene['veo_prompt'], aspect_ratio="9:16")
            
            if image_data:
                # Step B: Animate the image into a video using Veo 3.1 (image-to-video)
                # Use a simple, safe animation prompt — no need for complex descriptions
                animation_prompt = "Slowly animate this scene with subtle cinematic camera movement, smooth zoom, and gentle parallax motion."
                print(f"🎥 [VEO] Step 2: Animating image with Veo 3.1 (Image-to-Video)...")
                video_data = await self.gcp.generate_veo_video(animation_prompt, image_bytes=image_data)
                
                if video_data:
                    visual_data = video_data
                    is_static = False
                    print(f"✅ [VEO] Image-to-Video successful for scene {idx+1}!")
                else:
                    # Veo failed but we still have the image — use it as static
                    print(f"⚠️ [VEO] Animation failed. Using static image for scene {idx+1}")
                    visual_data = image_data
            else:
                print(f"⚠️ [VEO] Image generation failed for scene {idx+1}")

        if is_static and not visual_data:
            print(f"🎨 [IMAGEN] Generating cinematic scene {idx+1}: {scene['veo_prompt'][:50]}...")
            visual_data = await self.gcp.generate_image(scene['veo_prompt'], aspect_ratio="9:16")
        
        if not visual_data:
            print(f"❌ [VISUAL] Failed to generate asset for scene {idx+1}")
            return False
            
        ext = "jpg" if is_static else "mp4"
        visual_path = os.path.join(session_dir, f"scene_{idx}.{ext}")
        with open(visual_path, "wb") as f:
            f.write(visual_data)

        # 3. Merge Audio and Video for this scene
        merged_path = os.path.join(session_dir, f"scene_{idx}_merged.mp4")
        
        vid_base = os.path.basename(visual_path)
        aud_base = os.path.basename(audio_path)
        ass_base = os.path.basename(ass_path)
        out_base = os.path.basename(merged_path)

        # Use the fully-loaded static ffmpeg we downloaded locally!
        ffmpeg_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ffmpeg"))
        if not os.path.exists(ffmpeg_bin):
            ffmpeg_bin = "ffmpeg" # Fallback

        if is_static:
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", aud_base]
            dur_proc = await asyncio.create_subprocess_exec(*dur_cmd, stdout=asyncio.subprocess.PIPE, cwd=session_dir)
            dur_stdout, _ = await dur_proc.communicate()
            duration = dur_stdout.decode().strip()
            if not duration: duration = "5"
            
            # 1. Ken Burns Effect (Slow Zoom-In) - Sync duration with audio
            # d = duration * 25 (fps) to ensure it only animates once
            n_frames = int(float(duration) * 25)
            
            # 2. Circular Logo Logic
            logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "Logo.png"))
            
            # Professional Data Card (Source Attribution)
            source_text = scene.get('source_name', 'OFFICIAL DATA').upper()
            
            # Complex filter chain:
            # 1. Animation + Data Card + Subtitles -> [v_base]
            v_base_chain = (
                f"zoompan=z='min(zoom+0.0015,1.5)':d={n_frames}:s=1080x1920:fps=25,"
                f"drawbox=y=ih-450:color=black@0.6:width=iw:height=100:t=fill,"
                f"drawtext=text='SOURCE\\: {source_text}':fontcolor=yellow:fontsize=40:x=50:y=h-420:font='Arial-Bold',"
                f"subtitles={ass_base}[v_base]"
            )
            
            # 2. Add Circular Logo if exists
            inputs = ["-loop", "1", "-i", vid_base, "-i", aud_base]
            if os.path.exists(logo_path):
                inputs += ["-i", logo_path]
                filter_complex = (
                    f"[0:v]{v_base_chain};"
                    f"[2:v]scale=150:150,format=bgra,geq=lum='p(X,Y)':a='if(gt(sqrt(pow(X-75,2)+pow(Y-75,2)),75),0,255)'[logo];"
                    f"[v_base][logo]overlay=W-w-50:50"
                )
            else:
                filter_complex = f"[0:v]{v_base_chain};[v_base]copy"

            cmd = [
                ffmpeg_bin, "-y"
            ] + inputs + [
                "-filter_complex", filter_complex,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-t", duration,
                out_base
            ]
        else:
            cmd = [
                ffmpeg_bin, "-y",
                "-stream_loop", "-1", "-i", vid_base,
                "-i", aud_base,
                "-vf", f"subtitles={ass_base}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", 
                "-c:a", "aac",
                "-shortest",
                out_base
            ]
            
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=session_dir
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            print(f"FFmpeg Merge Error for Scene {idx}: {stderr.decode()}")
            return False
            
        return True
