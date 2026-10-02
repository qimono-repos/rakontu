from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

from .pipeline import Storyboard


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def relative_image_link(frame_path: Path, base_dir: Path) -> str:
    try:
        rel = Path(frame_path).resolve().relative_to(Path(base_dir).resolve())
    except ValueError:
        rel = Path(frame_path)
    return rel.as_posix()


class StoryboardWriter:
    """Streams a storyboard to a text stream, one section per frame.

    Writing incrementally means an interrupted run still leaves the captions
    produced so far on disk instead of losing them.
    """

    def __init__(
        self,
        stream: TextIO,
        url: str,
        interval: float,
        include_images: bool = True,
        base_dir: Path | None = None,
    ) -> None:
        self._stream = stream
        self._base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self._include_images = include_images
        self.count = 0
        self._write_header(url, interval)

    def _write_header(self, url: str, interval: float) -> None:
        header = "\n".join(
            [
                "# Rakonto",
                "",
                f"- Video: {url}",
                f"- Intervalo: {interval:g} s",
                "",
            ]
        )
        self._stream.write(header)

    def add(self, frame) -> None:
        lines = [f"## {format_timestamp(frame.timestamp)} - {frame.path.name}", ""]
        if self._include_images:
            link = relative_image_link(frame.path, self._base_dir)
            lines.append(f"![{frame.path.name}]({link})")
            lines.append("")
        lines.append(frame.caption.strip())
        lines.append("")
        self._stream.write("\n".join(lines))
        self.count += 1
        self._flush()

    def close(self, total: int | None = None) -> None:
        if total is not None:
            self._stream.write(f"\n<!-- {total} frames -->\n")
        self._flush()

    def _flush(self) -> None:
        self._stream.flush()


def render_markdown(
    storyboard: Storyboard,
    include_images: bool = True,
    base_dir: Path | None = None,
) -> str:
    import io

    buf = io.StringIO()
    writer = StoryboardWriter(
        buf,
        storyboard.url,
        storyboard.interval,
        include_images=include_images,
        base_dir=base_dir,
    )
    for frame in storyboard.frames:
        writer.add(frame)
    return buf.getvalue()