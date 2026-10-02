import base64
import glob
import os
import subprocess

from dotenv import load_dotenv
load_dotenv()

import requests

VIDEO_URL = "https://www.youtube.com/watch?v=x_ST4jvZk_A"
OUT_DIR = "frames"
os.makedirs(OUT_DIR, exist_ok=True)

subprocess.run(
    [
        "yt-dlp",
        "-f", "bv*[height<=720]+ba/b",
        "--merge-output-format", "mp4",
        "-o", "video.mp4",
        VIDEO_URL,
    ],
    check=True,
)

subprocess.run(
    ["ffmpeg", "-y", "-i", "video.mp4", "-vf", "fps=1/10", "-q:v", "3", f"{OUT_DIR}/frame_%04d.jpg"],
    check=True,
)

api_key = os.environ["OPENAI_API_KEY"]

for path in sorted(glob.glob(f"{OUT_DIR}/*.jpg")):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this frame in one sentence: what the person does and what the software shows.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 100,
        },
        timeout=60,
    )
    response.raise_for_status()
    print(path, "->", response.json()["choices"][0]["message"]["content"])
