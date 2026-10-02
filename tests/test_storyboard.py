from __future__ import annotations

import base64
import io
import subprocess
from pathlib import Path

import pytest

from warmwind_storyboard import cli, pipeline
from warmwind_storyboard.config import DEFAULT_INTERVAL, StoryboardError
from warmwind_storyboard.pipeline import FrameCaption, Storyboard, ffmpeg_fps_filter
from warmwind_storyboard.render import StoryboardWriter, format_timestamp, render_markdown


@pytest.fixture
def fake_video(tmp_path: Path) -> Path:
    """A tiny real mp4 so ffmpeg has something to read."""
    video = tmp_path / "video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=10:size=64x48:rate=10",
            "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return video


def make_frames(directory: Path, count: int) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        p = directory / f"frame_{i:04d}.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        paths.append(p)
    return paths


class TestFpsFilter:
    @pytest.mark.parametrize(
        ("interval", "expected"),
        [(10.0, "fps=1/10"), (3.0, "fps=1/3"), (2.5, "fps=1/2.5"), (1.0, "fps=1/1")],
    )
    def test_formats_cleanly(self, interval, expected):
        assert ffmpeg_fps_filter(interval) == expected


class TestSampling:
    def test_frame_count_matches_interval(self, tmp_path, fake_video):
        frames = pipeline.sample_frames(fake_video, tmp_path / "frames", 5.0)
        assert len(frames) == 2  # 10s video at 5s interval

    def test_stale_frames_are_removed(self, tmp_path, fake_video):
        out = tmp_path / "frames"
        stale = make_frames(out, 3)
        pipeline.sample_frames(fake_video, out, 5.0)
        for path in stale:
            assert path.exists() is False or path.stat().st_size > 20

    def test_missing_ffmpeg_is_reported(self, tmp_path, fake_video, monkeypatch):
        monkeypatch.setattr(pipeline.shutil, "which", lambda _: None)
        with pytest.raises(StoryboardError, match="ffmpeg"):
            pipeline.sample_frames(fake_video, tmp_path / "frames", 5.0)


class TestApiKey:
    def test_missing_key_raises_readable_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(StoryboardError, match="OPENAI_API_KEY"):
            pipeline.resolve_api_key()

    def test_blank_key_is_rejected(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        with pytest.raises(StoryboardError, match="OPENAI_API_KEY"):
            pipeline.resolve_api_key()


class TestDescribeFrame:
    def test_returns_caption_content(self, tmp_path, monkeypatch):
        frame = tmp_path / "frame_0001.jpg"
        frame.write_bytes(b"bytes")
        seen = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "A person types."}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen["payload"] = json
            seen["headers"] = headers
            seen["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr(pipeline.requests, "post", fake_post)
        caption = pipeline.describe_frame(frame, "sk-test")

        assert caption == "A person types."
        assert seen["payload"]["model"] == "gpt-4o-mini"
        image_block = seen["payload"]["messages"][0]["content"][1]
        assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert base64.b64decode(image_block["image_url"]["url"].split(",", 1)[1]) == b"bytes"

    def test_http_error_becomes_storyboard_error(self, tmp_path, monkeypatch):
        frame = tmp_path / "frame_0001.jpg"
        frame.write_bytes(b"bytes")

        class FakeResponse:
            status_code = 429

            def raise_for_status(self):
                raise pipeline.requests.exceptions.HTTPError(response=self)

        monkeypatch.setattr(pipeline.requests, "post", lambda *a, **k: FakeResponse())
        with pytest.raises(StoryboardError, match="429"):
            pipeline.describe_frame(frame, "sk-test")


class TestRendering:
    def test_timestamp_formatting(self):
        assert format_timestamp(0) == "00:00:00"
        assert format_timestamp(3) == "00:00:03"
        assert format_timestamp(90) == "00:01:30"
        assert format_timestamp(3725) == "01:02:05"

    def test_markdown_has_header_and_sections(self):
        sb = Storyboard(
            url="https://example.com/v",
            interval=3.0,
            frames=[
                FrameCaption(0, Path("frames/frame_0001.jpg"), 0.0, "First"),
                FrameCaption(1, Path("frames/frame_0002.jpg"), 3.0, "Second"),
            ],
        )
        md = render_markdown(sb, base_dir=Path.cwd())
        assert md.startswith("# Rakonto")
        assert "https://example.com/v" in md
        assert "- Intervalo: 3 s" in md
        assert "## 00:00:00 - frame_0001.jpg" in md
        assert "## 00:00:03 - frame_0002.jpg" in md
        assert "First" in md and "Second" in md

    def test_image_links_use_forward_slashes(self, tmp_path):
        frame = tmp_path / "frames" / "frame_0001.jpg"
        sb = Storyboard("u", 3.0, [FrameCaption(0, frame, 0.0, "c")])
        md = render_markdown(sb, base_dir=tmp_path)
        assert "(frames/frame_0001.jpg)" in md
        assert "\\" not in md

    def test_no_images_omits_links(self, tmp_path):
        frame = tmp_path / "frames" / "frame_0001.jpg"
        sb = Storyboard("u", 3.0, [FrameCaption(0, frame, 0.0, "c")])
        md = render_markdown(sb, include_images=False, base_dir=tmp_path)
        assert "![" not in md

    def test_writer_streams_incrementally(self):
        buf = io.StringIO()
        writer = StoryboardWriter(buf, "u", 3.0, include_images=False)
        writer.add(FrameCaption(0, Path("f1.jpg"), 0.0, "one"))
        assert "one" in buf.getvalue()  # already written before close
        writer.add(FrameCaption(1, Path("f2.jpg"), 3.0, "two"))
        writer.close(total=writer.count)
        assert writer.count == 2
        assert "two" in buf.getvalue()


class TestCli:
    def test_url_is_required(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main([])
        assert exc.value.code == 2
        assert "-u/--url" in capsys.readouterr().err

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_interval_rejected(self, bad):
        with pytest.raises(SystemExit) as exc:
            cli.main(["-u", "https://example.com", "-i", bad])
        assert exc.value.code == 2

    def test_defaults(self):
        args = cli.build_parser().parse_args(["-u", "https://example.com"])
        assert args.interval == DEFAULT_INTERVAL == 3.0
        assert str(args.output) == "rakonto.md"
        assert str(args.frames_dir) == "frames"
        assert str(args.video) == "video.mp4"
        assert args.no_images is False

    def test_rakonto_is_alias_for_output(self):
        args = cli.build_parser().parse_args(
            ["-u", "https://example.com", "--rakonto", "out.md"]
        )
        assert str(args.output) == "out.md"

    def test_version(self, capsys):
        with pytest.raises(SystemExit):
            cli.main(["--version"])
        assert "rakontu" in capsys.readouterr().out

    def test_help_uses_rakontu_prog(self, capsys):
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert capsys.readouterr().out.startswith("usage: rakontu")

    def test_end_to_end_writes_markdown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        frames_dir = tmp_path / "frames"
        make_frames(frames_dir, 3)
        out = tmp_path / "nested" / "rakonto.md"

        monkeypatch.setattr(cli, "build_storyboard", lambda **kw: iter([
            FrameCaption(0, frames_dir / "frame_0001.jpg", 0.0, "Opens terminal"),
            FrameCaption(1, frames_dir / "frame_0002.jpg", 3.0, "Runs uv init"),
        ]))

        rc = cli.main([
            "-u", "https://example.com/v",
            "-o", str(out),
            "--frames-dir", str(frames_dir),
            "--video", str(tmp_path / "v.mp4"),
        ])

        assert rc == 0
        text = out.read_text(encoding="utf-8")
        assert "# Rakonto" in text
        assert "Opens terminal" in text
        assert "Runs uv init" in text
        assert "frames/frame_0001.jpg" in text

    def test_output_dash_goes_to_stdout(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(cli, "build_storyboard", lambda **kw: iter([
            FrameCaption(0, tmp_path / "frame_0001.jpg", 0.0, "Hello"),
        ]))

        rc = cli.main(["-u", "https://example.com/v", "-o", "-"])

        assert rc == 0
        captured = capsys.readouterr()
        assert "# Rakonto" in captured.out
        assert "Hello" in captured.out
        assert "wrote" not in captured.err

    def test_pipeline_error_returns_one(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        def boom(**kw):
            raise StoryboardError("ffmpeg was not found on PATH")
            yield  # pragma: no cover

        monkeypatch.setattr(cli, "build_storyboard", boom)
        rc = cli.main(["-u", "https://example.com/v", "-o", str(tmp_path / "o.md")])

        assert rc == 1
        assert "ffmpeg was not found" in capsys.readouterr().err