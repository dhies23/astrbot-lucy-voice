# -*- coding: utf-8 -*-
"""听一下插件产出的 wav 到底是什么语言（faster-whisper 自动识别）。

    K:\\gptsovits\\...\\runtime\\python.exe tests/asr_check.py out/roundtrip_1_late.wav ...
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel

files = [Path(p) for p in sys.argv[1:]] or [
    Path("out/roundtrip_1_late.wav"),
    Path("out/roundtrip_2_who.wav"),
    Path("out/live_std.wav"),
]

model = WhisperModel(
    os.environ.get("LUCY_ASR_MODEL", "large-v3"),
    device=os.environ.get("LUCY_ASR_DEVICE", "cuda"),
    compute_type=os.environ.get("LUCY_ASR_COMPUTE", "float16"),
)
for p in files:
    if not p.exists():
        print(f"{p}: 不存在")
        continue
    segs, info = model.transcribe(
        str(p), beam_size=5, vad_filter=False, condition_on_previous_text=False
    )
    text = "".join(s.text for s in segs).strip()
    print(f"\n== {p.name}")
    print(f"   语言：{info.language}（p={info.language_probability:.3f}） 时长 {info.duration:.2f}s")
    print(f"   转写：{text}")
