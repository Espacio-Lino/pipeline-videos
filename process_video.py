#!/usr/bin/env python3
"""
process_video.py — Video transcription pipeline
Usage: python process_video.py <video_file>
Reads OPENAI_API_KEY from .env file in same directory.
"""

import csv
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── Load .env ─────────────────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        # Handle both KEY=value and $env:KEY = "value" formats
        line = line.strip()
        m = re.search(r'(?:\$env:)?([A-Z_]+)\s*=\s*["\']?([^"\']+)["\']?', line)
        if m:
            os.environ[m.group(1)] = m.group(2).strip()

load_env()

# ── Folder structure ──────────────────────────────────────────────
# Code and generated text live next to this script. Raw video is bulk
# storage and stays out of the repo — override with VIDEO_STORAGE.
BASE_DIR = Path(__file__).parent
STORAGE_DIR = Path(os.environ.get("VIDEO_STORAGE", Path.home() / "Videos"))
DIRS = {
    "processed":   STORAGE_DIR / "_processed",
    "transcripts": BASE_DIR / "_transcripts",
    "summaries":   BASE_DIR / "_summaries",
    "log":         BASE_DIR / "_log",
}
LOG_FILE = DIRS["log"] / "processed.csv"
LOG_HEADERS = ["date", "generated_title", "source_video", "duration_min"]


def setup_dirs():
    for d in DIRS.values():
        d.mkdir(exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(LOG_HEADERS)


# ── Audio extraction ──────────────────────────────────────────────
def extract_audio(video_path: Path, tmp_dir: str) -> Path:
    audio_path = Path(tmp_dir) / "audio.mp3"
    print(f"[1/3] Extracting audio from {video_path.name}...")
    # 128k bitrate, no silence filter. 32k + silenceremove made Whisper loop
    # on "..." whenever the speaker was quiet or paused.
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-ar", "16000",
         "-ac", "1", "-b:a", "128k",
         str(audio_path), "-y"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ffmpeg error:", result.stderr[-500:])
        sys.exit(1)
    size_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"       Audio size: {size_mb:.1f} MB")
    return audio_path


def get_video_duration_min(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    try:
        return round(float(result.stdout.strip()) / 60, 1)
    except Exception:
        return 0.0


# ── Transcription (Whisper API) ───────────────────────────────────
def transcribe(audio_path: Path, openai_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    print("[2/3] Transcribing with Whisper API...")

    # Whisper API has a 25MB limit — split if needed
    size_mb = audio_path.stat().st_size / 1024 / 1024
    if size_mb > 24:
        print(f"       File {size_mb:.1f}MB > 25MB limit, splitting...")
        return transcribe_chunked(audio_path, client)

    with open(audio_path, "rb") as f:
        # Language is auto-detected; pass language= to force one.
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text"
        )
    return response


def transcribe_chunked(audio_path: Path, client) -> str:
    """Split audio into ~20min chunks and transcribe each."""
    tmp = audio_path.parent
    chunk_prefix = str(tmp / "chunk")
    subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-f", "segment", "-segment_time", "1200",
        "-c", "copy", f"{chunk_prefix}_%03d.mp3", "-y"
    ], capture_output=True)

    chunks = sorted(Path(tmp).glob("chunk_*.mp3"))
    full_transcript = []
    for i, chunk in enumerate(chunks):
        print(f"       Chunk {i+1}/{len(chunks)}...")
        with open(chunk, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="text"
            )
        full_transcript.append(resp)
    return "\n".join(full_transcript)


# ── Save transcript ───────────────────────────────────────────────
def save_transcript(transcript: str, date_str: str, slug: str) -> Path:
    fname = f"{date_str}_{slug}_transcript.txt"
    path = DIRS["transcripts"] / fname
    path.write_text(transcript, encoding="utf-8")
    return path


def move_video(video_path: Path) -> Path:
    dest = DIRS["processed"] / video_path.name
    video_path.rename(dest)
    return dest


def log_entry(date_str: str, title: str, video_name: str, duration_min: float):
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([date_str, title, video_name, duration_min])


# ── Main ──────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python process_video.py <video_file>")
        sys.exit(1)

    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"Error: not found -> {video_path}")
        sys.exit(1)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("Error: OPENAI_API_KEY not found in .env or environment")
        sys.exit(1)

    setup_dirs()

    date_str     = datetime.now().strftime("%Y-%m-%d")
    duration_min = get_video_duration_min(video_path)
    print(f"       Duration: {duration_min} min")

    # ── Skip if already transcribed ───────────────────────────────
    tmp_slug = re.sub(r"[^\w]", "-", video_path.stem.lower())[:40]
    existing = list(DIRS["transcripts"].glob(f"*{tmp_slug}*"))
    if existing:
        print(f"       Already transcribed -> {existing[0].name}")
        print("       Skip. Delete transcript file to re-process.")
        sys.exit(0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = extract_audio(video_path, tmp_dir)
        transcript = transcribe(audio_path, openai_key)

    # Saved under a provisional slug — the downstream summarizer renames it
    # once it knows what the meeting was about.
    transcript_path = save_transcript(transcript, date_str, tmp_slug)
    print(f"[3/3] Transcript saved -> {transcript_path.name}")

    move_video(video_path)
    print(f"       Video moved   -> _processed/{video_path.name}")

    # Logged with the provisional title; updated after summarization.
    log_entry(date_str, tmp_slug, video_path.name, duration_min)

    # Transcript goes to stdout so a summarizer can pick it up from the pipe.
    print(f"\n--- TRANSCRIPT START ---")
    print(transcript)
    print(f"--- TRANSCRIPT END ---")
    print(f"\nDATE:{date_str}")
    print(f"DURATION:{duration_min}")
    print(f"TRANSCRIPT_PATH:{transcript_path}")
    print(f"VIDEO_ORIGINAL:{video_path.name}")


if __name__ == "__main__":
    main()
