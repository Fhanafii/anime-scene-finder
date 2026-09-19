from __future__ import annotations

import subprocess
import json
from pathlib import Path


def video_duration(source: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def video_metadata(source: Path) -> dict[str, int | float | str]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate,codec_name", "-show_entries", "format=duration",
         "-of", "json", str(source)], check=True, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise ValueError("video stream not found")
    stream = streams[0]
    rate = stream.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
    duration = float(payload.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("video duration must be positive")
    return {"duration": duration, "width": int(stream.get("width", 0)), "height": int(stream.get("height", 0)), "fps": fps, "codec": stream.get("codec_name", "unknown")}


def detect_scenes(source: Path) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, SceneManager, open_video

    video = open_video(str(source))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    manager.detect_scenes(video=video)
    scenes = manager.get_scene_list()
    duration = video_duration(source)
    return [(start.get_seconds(), end.get_seconds()) for start, end in scenes] or [(0.0, duration)]


def representative_times(start: float, end: float, count: int = 3) -> list[float]:
    if end <= start or count < 1:
        raise ValueError("scene interval and keyframe count must be positive")
    count = min(count, 5)
    step = (end - start) / (count + 1)
    return [start + step * index for index in range(1, count + 1)]


def extract_frame(source: Path, timestamp: float, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(timestamp), "-i", str(source), "-frames:v", "1", "-q:v", "2", str(destination)],
        check=True,
    )
