# pipeline-videos

Turns a recorded meeting into a transcript, ready for whatever summarizes it
next. One command, no manual note-taking.

```
python process_video.py meeting.mp4
```

Video → audio (ffmpeg) → transcript (Whisper) → saved, logged, and printed to
stdout so a downstream summarizer can pick it up from the pipe. The video is
moved out of the inbox folder so it is never processed twice.

I built this because I sit in a lot of calls and took notes badly. It has been
running weekly on real meetings since May 2026.

## What it does

- Extracts audio with ffmpeg, tuned to avoid a Whisper failure mode: at low
  bitrate with a silence filter, quiet speakers made the model loop on "...".
- Splits audio into ~20 minute chunks when the file exceeds the 25MB API limit
- Transcribes with Whisper, auto-detecting language
- Skips anything already transcribed, so re-running is safe
- Files the video under `_processed/` and appends a row to `_log/processed.csv`

The summarizing step is not in here — this writes the transcript to stdout and
gets out of the way.

## Setup

Requires `ffmpeg` and `ffprobe` on PATH, and Python 3.9+.

```
pip install openai
echo "OPENAI_API_KEY=sk-..." > .env
```

Output folders are created on first run. Raw video storage defaults to
`~/Videos` and is configurable with the `VIDEO_STORAGE` environment variable.

## Notes

Transcripts and summaries are gitignored — this repo is the tool, not the data.

MIT licensed.
