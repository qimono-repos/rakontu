from __future__ import annotations

DEFAULT_INTERVAL = 3.0  # seconds between sampled frames
DEFAULT_OUTPUT = "rakonto.md"
DEFAULT_FRAMES_DIR = "frames"
DEFAULT_VIDEO = "video.mp4"
FRAME_PATTERN = "frame_%04d.jpg"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 100
DEFAULT_TIMEOUT = 60

CAPTION_PROMPT = (
    "Describe this frame in one sentence: what the person does and what the software shows."
)


class StoryboardError(RuntimeError):
    """An error worth reporting to the user without a traceback."""