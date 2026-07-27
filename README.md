# pipeline-videos

Turns a recorded meeting into a transcript, ready for whatever summarizes it next.

```
python process_video.py meeting.mp4
```

```
meeting.mp4
   │  ffmpeg
   ▼
audio.mp3 ──(>25MB? split into 20-min chunks)
   │  Whisper
   ▼
_transcripts/2026-07-27_weekly-review_transcript.txt
   │
   ├─→ stdout ──→ whatever summarizes it next
   ├─→ _log/processed.csv
   └─→ meeting.mp4 moved to _processed/
```

## Why this exists

I sit in a lot of calls and I took notes badly. Not occasionally — structurally.
I would follow the conversation or I would write it down, never both, and a week
later I could not tell you what we had agreed on.

So the job was never "transcribe a video". It was: make the meeting still exist
next month, with no discipline required from me at the time. That constraint is
why this looks the way it does. It has run weekly on real meetings since May 2026.

## Design notes

**The folder is the queue.** No database, no state file, no job table. A video
sitting in the inbox folder means unprocessed; the script moves it to
`_processed/` when it is done. Crash halfway through and the video is still in
the inbox, so re-running is the recovery procedure. There is nothing to repair.

**Whisper loops on silence, and it is your fault, not its.** The first version
used a 32k bitrate plus ffmpeg's `silenceremove` filter — sensible, half the
file size. On a call with a quiet speaker and normal pauses, the transcript
came back as pages of "...". The filter was eating the low-volume speech and
Whisper was hallucinating into the gap. Fix was to stop being clever: 128k, no
filter, and the failure never came back. The cheap preprocessing was costing
the entire output.

**Chunking copies, it does not re-encode.** The Whisper API caps at 25MB. Long
calls get split with `-f segment -c copy`, so ffmpeg slices the existing stream
instead of decoding and re-encoding it — seconds instead of minutes, and no
generational quality loss on a file that is about to be transcribed anyway.

**Summarizing is deliberately not in here.** The transcript goes to stdout and
the script stops. Summarization models change every few months; ffmpeg and
"move the file when you are done" do not. Keeping the volatile part outside
means the durable part never has to be rewritten.

**Re-running is safe by default.** Before spending anything on audio extraction
or API calls, it checks whether a transcript already exists for that filename
and exits if so. Deleting the
transcript is how you force a re-process — the presence of the output file is
the only state it trusts.

## Setup

Requires `ffmpeg` and `ffprobe` on PATH, and Python 3.9+.

```
pip install openai
echo "OPENAI_API_KEY=sk-..." > .env
```

Output folders are created on first run. Raw video storage defaults to `~/Videos`,
configurable with `VIDEO_STORAGE`.

## What it does not do

No speaker diarization — it will not tell you who said what. No live/streaming
transcription, files only. No summarization, on purpose (see above). Language is
auto-detected; pass `language=` to the Whisper call to force one.

Transcripts and summaries are gitignored. This repo is the tool, not the data.

MIT licensed.
