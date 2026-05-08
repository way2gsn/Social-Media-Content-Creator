import os
import time
from PIL import Image as PILImage
from google import genai
from google.genai import types

# --- 1. CONFIGURATION ---
KEY_FILE = "key.json" 
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_FILE

PROJECT_ID = "project-fb884592-f206-43c0-948"
LOCATION = "global" 
INPUT_FOLDER = "Second Iteration back"
OUTPUT_FOLDER = "Second iteration output"

# --- 2. THE BRANDED PROMPTS ---

PROMPT_AESTHETIC = (
"TASK: Create a 100% accurate photorealistic replica of the subject in the source image. "
"The product/character MUST be a literal mirror of the source likeness. "
"A professional, luxurious product shot of the package. "
"The product is placed on a weathered wooden farmhouse table with natural light. "
"Add small amounts of raw materials around the product (only those present in the main product). "
"Morning sunlight and soft shadows. 4K resolution. "
"Instruction: Maintain EXACT label, shape, and likeness. No artistic interpretation."
)

PROMPT_NUTRITION = (
   "TASK: Literal replication of the source image subject. Mirror the likeness exactly. "
   "A clean, bright, high-end product shot. Minimalist infographic style emphasizing "
   "nutritional value. Packaging must be identical and 100% accurate to the source. "
   "Do not add any 100 percent certified text. "
   "Remove expiration date and MRP if visible."
)

def safe_generate(prompt, image, output_path):
    """Retries with regional failover if a 429 quota error occurs."""
    locations = ["us-central1", "europe-west4", "asia-northeast1", "global"]
    
    for loc in locations:
        try:
            print(f"  📡 Trying {loc} for image processing...")
            client = genai.Client(vertexai=True, project=PROJECT_ID, location=loc)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, image],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1", image_size="2K")
                )
            )
            response.parts[0].as_image().save(output_path)
            return True
        except Exception as e:
            if "429" in str(e):
                print(f"  🛑 Quota hit in {loc}. Trying next region...")
                continue
            else:
                print(f"  ❌ Error in {loc}: {e}")
                return False
    return False

def run_automation(limit=50):
    # client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION) # No longer needed here
    
    for folder in [INPUT_FOLDER, OUTPUT_FOLDER]:
        if not os.path.exists(folder): os.makedirs(folder)

    files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(('jpg', 'jpeg', 'png'))]
    to_process = files[:limit]

    print(f"🌾 Starting Phasal Bazar Production: {len(to_process)} files...")

    for index, filename in enumerate(to_process):
        input_path = os.path.join(INPUT_FOLDER, filename)
        print(f"\n[{index+1}/{len(to_process)}] Processing: {filename}")
        
        try:
            raw_image = PILImage.open(input_path)

            # 1. Aesthetic version
            # path_a = os.path.join(OUTPUT_FOLDER, f"vibe_{filename}")
            # if safe_generate(PROMPT_AESTHETIC, raw_image, path_a):
            #     print(f"  ✅ Aesthetic version saved.")

            # time.sleep(10) # Gap between calls for the same image

            # 2. Nutritional version
            path_b = os.path.join(OUTPUT_FOLDER, f"nutrition_{filename}")
            if safe_generate(PROMPT_NUTRITION, raw_image, path_b):
                print(f"  ✅ Nutritional version saved.")

            # Safety gap before moving to the next file
            time.sleep(15)

        except Exception as e:
            print(f"❌ Critical failure on {filename}: {e}")

if __name__ == "__main__":
    run_automation(limit=100) # Increased limit to handle more files








     