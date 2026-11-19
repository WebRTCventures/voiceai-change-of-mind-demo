"""Manual check, not part of the demo: what does the demo's Silero VAD hear in a recording?

Runs Pipecat's SileroVADAnalyzer with its default parameters over an audio file and prints
the confidence and volume it computes every ~100 ms, plus every state change. A chunk counts
as speech only when confidence >= params.confidence AND volume >= params.min_volume.

Usage (from the repo root, needs ffmpeg to decode):
    uv run python .kiro/specs/turn-detection-modes/vad_file.py "recording.m4a"
"""
import subprocess
import sys

import numpy as np
from pipecat.audio.vad.silero import SileroVADAnalyzer

pcm = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", sys.argv[1], "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
    capture_output=True,
    check=True,
).stdout
vad = SileroVADAnalyzer()
vad.set_sample_rate(16000)
n = vad.num_frames_required() * 2  # bytes per 512-sample window (32 ms)
p = vad.params
print(f"params: confidence>={p.confidence} min_volume>={p.min_volume} "
      f"start={p.start_secs}s stop={p.stop_secs}s\n")

prev_state, rows = None, []
for i in range(0, len(pcm) - n + 1, n):
    chunk = pcm[i : i + n]
    conf = float(np.asarray(vad.voice_confidence(chunk)).reshape(-1)[0])
    vol = vad._get_smoothed_volume(chunk)  # same helper the analyzer uses
    speaking = conf >= p.confidence and vol >= p.min_volume
    state = vad._run_analyzer(chunk)
    rows.append((i / 2 / 16000, conf, vol, speaking, state))
    if state != prev_state:
        print(f"{i / 2 / 16000:6.2f}s  state -> {state.name}")
        prev_state = state

print("\n  t(s)  conf  volume  speaking  state")
for t, conf, vol, sp, st in rows[::3]:  # about every 100 ms
    print(f"{t:6.2f}  {conf:4.2f}  {vol:5.2f}   {'yes' if sp else '.':<8}  {st.name}")
