import os, json
from google import genai
from google.genai import types

key = json.load(open('backend/key.json'))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "backend/key.json"
client = genai.Client(vertexai=True, project=key['project_id'], location='us-central1')

print("Testing Veo via google-genai SDK...")
try:
    operation = client.models.generate_videos(
        model='veo-3.1-fast-generate-001',
        prompt='A tiny cute puppy walking on a red carpet, 4k cinematic',
        config={"aspect_ratio": "9:16"}
    )
    print("Operation started:", operation.name)
    print("Waiting...")
    
    # Wait for the LRO to complete
    operation = client.operations.wait(operation=operation)
    print("Finished! Status:", operation.done)
    
    if operation.result and hasattr(operation.result, 'generated_videos'):
        for i, video in enumerate(operation.result.generated_videos):
            if hasattr(video.video, 'video_bytes'):
                print("Generated video:", len(video.video.video_bytes), "bytes")
                with open(f"backend/test_veo_out_{i}.mp4", "wb") as f:
                    f.write(video.video.video_bytes)
            elif hasattr(video.video, 'uri'):
                print("Video saved at URI:", video.video.uri)
    
except Exception as e:
    print(f"Error: {e}")

