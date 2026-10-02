from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import requests

from .config import (
    CAPTION_PROMPT,
    DEFAULT_FRAMES_DIR,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    DEFAULT_VIDEO,
    FRAME_PATTERN,
    StoryboardError,
)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


@dataclass(frozen=True)
class FrameCaption:
    index: int  # 0-based position in the sampled sequence
    path: Path
    timestamp: float
    caption: str


@dataclass(frozen=True)
class Storyboard:
    url: str
    interval: float
    frames: list[FrameCaption] = field(default_factory=list)


def ffmpeg_fps_filter(interval: float) -> str:
    """Map a sampling interval in seconds onto an ffmpeg fps filter."""
    if float(interval).is_integer():
        return f"fps=1/{int(interval)}"
    return f"fps=1/{interval:g}"


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise StoryboardError("ffmpeg was not found on PATH")


def resolve_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise StoryboardError(
            "OPENAI_API_KEY is not set (put it in a .env file or the environment)"
        )
    return api_key


def download(url: str, dest: Path = Path(DEFAULT_VIDEO)) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bv*[height<=720]+ba/b",
        "--merge-output-format",
        "mp4",
        "--output",
        str(dest),
        url,
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise StoryboardError(f"yt-dlp failed to download {url}") from exc
    return dest


def sample_frames(video: Path, out_dir: Path, interval: float) -> list[Path]:
    video = Path(video)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Drop frames from a previous run so a changed -i cannot caption stale images.
    for stale in out_dir.glob("frame_*.jpg"):
        stale.unlink(missing_ok=True)

    ensure_ffmpeg()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        ffmpeg_fps_filter(interval),
        "-q:v",
        "3",
        str(out_dir / FRAME_PATTERN),
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise StoryboardError("ffmpeg failed to extract frames from the video") from exc

    return sorted(out_dir.glob("frame_*.jpg"))


def describe_frame(path: Path, api_key: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode()
    try:
        response = requests.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": CAPTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                            },
                        ],
                    }
                ],
                "max_tokens": DEFAULT_MAX_TOKENS,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise StoryboardError(f"OpenAI API returned HTTP {status} for {Path(path).name}") from exc
    except requests.exceptions.RequestException as exc:
        raise StoryboardError(f"could not reach the OpenAI API: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise StoryboardError(f"unexpected OpenAI response for {Path(path).name}") from exc


def build_storyboard(
    url: str,
    interval: float,
    frames_dir: Path = Path(DEFAULT_FRAMES_DIR),
    video_path: Path = Path(DEFAULT_VIDEO),
) -> Iterator[FrameCaption]:
    """Download, sample, and caption, yielding one result per frame as it lands."""
    if interval <= 0:
        raise StoryboardError("interval must be > 0")

    api_key = resolve_api_key()
    download(url, dest=video_path)
    frame_paths = sample_frames(video_path, frames_dir, interval)

    for index, frame_path in enumerate(frame_paths):
        yield FrameCaption(
            index=index,
            path=frame_path,
            timestamp=index * interval,
            caption=describe_frame(frame_path, api_key),
        )