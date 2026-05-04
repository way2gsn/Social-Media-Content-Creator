import requests
import os

def test_catbox():
    # Use a dummy file
    file_path = "test_upload.txt"
    with open(file_path, "w") as f:
        f.write("test content")
    
    try:
        with open(file_path, "rb") as f:
            files = {
                "reqtype": (None, "fileupload"),
                "fileToUpload": (os.path.basename(file_path), f, "text/plain")
            }
            resp = requests.post("https://catbox.moe/user/api.php", files=files, timeout=60, verify=False)
            print(f"Status: {resp.status_code}")
            print(f"Text: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    test_catbox()
