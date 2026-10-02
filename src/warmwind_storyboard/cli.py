from __future__ import annotations

import argparse
import sys
from importlib import metadata
from pathlib import Path

from dotenv import load_dotenv

from .config import (
    DEFAULT_FRAMES_DIR,
    DEFAULT_INTERVAL,
    DEFAULT_OUTPUT,
    DEFAULT_VIDEO,
    StoryboardError,
)
from .pipeline import build_storyboard
from .render import StoryboardWriter

DIST_NAME = "warmwind-storyboard"


def _version() -> str:
    try:
        return metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0"


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number: {value!r}")
    if parsed <= 0:
        raise argparse.ArgumentTypeError("interval must be > 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rakontu",
        description="Turn a video into a storyboard.",
        epilog=(
            "Requires ffmpeg on PATH and OPENAI_API_KEY in the environment or a .env file. "
            "Use -o - to write the storyboard to stdout."
        ),
    )
    parser.add_argument(
        "-u",
        "--url",
        required=True,
        metavar="URL",
        help="video URL to storyboard (yt-dlp figures out the site)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=positive_float,
        default=DEFAULT_INTERVAL,
        metavar="SECONDS",
        help="seconds between sampled frames (default: %(default)s)",
    )
    parser.add_argument(
        "-o",
        "--output",
        "--rakonto",
        dest="output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        metavar="FILE.md",
        help="markdown storyboard path, or - for stdout (default: %(default)s)",
    )
    parser.add_argument(
        "--frames-dir",
        type=Path,
        default=Path(DEFAULT_FRAMES_DIR),
        metavar="DIR",
        help="where sampled frames are written (default: %(default)s)",
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=Path(DEFAULT_VIDEO),
        metavar="FILE",
        help="where the downloaded video is written (default: %(default)s)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="write captions only, without embedding frame images",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    to_stdout = str(args.output) == "-"
    if to_stdout:
        base_dir = args.frames_dir
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        base_dir = args.output.parent

    stream = sys.stdout if to_stdout else args.output.open("w", encoding="utf-8", newline="\n")
    writer = StoryboardWriter(
        stream,
        url=args.url,
        interval=args.interval,
        include_images=not args.no_images,
        base_dir=base_dir,
    )

    try:
        frames = build_storyboard(
            url=args.url,
            interval=args.interval,
            frames_dir=args.frames_dir,
            video_path=args.video,
        )
        for frame in frames:
            writer.add(frame)
            print(f"{frame.path.name} -> {frame.caption}", file=sys.stderr)
        writer.close(total=writer.count)
    except StoryboardError as exc:
        writer.close()
        print(f"rakontu: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        writer.close()
        print(f"rakontu: interrupted after {writer.count} frames", file=sys.stderr)
        return 130
    finally:
        if not to_stdout:
            stream.close()

    if not to_stdout:
        print(f"wrote {args.output} ({writer.count} frames)", file=sys.stderr)
    return 0