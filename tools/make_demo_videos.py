#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把试听音频做成「波形视频」（MP4），方便在 README / 网页里看+听。

    python tools/make_demo_videos.py --src docs/demo --ffmpeg C:/tools/ffmpeg/bin/ffmpeg.exe

做法：
  1. 读 WAV → 取包络（每 ~10 ms 一个 RMS 值）
  2. Pillow 逐帧画：整段波形铺满一行，已播部分用紫色、未播部分用暗灰，外加一条播放头
  3. ffmpeg 把 PNG 序列 + 原始音频编成 H.264/AAC

只依赖 Pillow、numpy、ffmpeg；不改动原始音频。`docs/demo/meta.json` 提供每条的标题。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 960, 300
FPS = 24
BG = (13, 13, 17)
FG = (238, 238, 244)
DIM = (150, 152, 168)
BAR_IDLE = (58, 58, 74)
BAR_PLAY = (214, 184, 242)
ACCENT = (214, 184, 242)

WAVE_X, WAVE_Y, WAVE_W, WAVE_H = 40, 110, 880, 130
BAR_W = 3
BAR_GAP = 2

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


# ----------------------------------------------------------------- 基础
def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise SystemExit(f"{path}: 只支持 16bit PCM")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, rate


def envelope(samples: np.ndarray, rate: int, cols: int, win_ms: float = 10.0) -> np.ndarray:
    """把整段音频压成 cols 个峰值（0..1）。"""
    n = len(samples)
    if n == 0:
        return np.zeros(cols, dtype=np.float32)
    step = max(1, int(rate * win_ms / 1000.0))
    frames = n // step
    if frames == 0:
        frames = 1
    trimmed = samples[: frames * step].reshape(frames, step)
    peaks = np.abs(trimmed).max(axis=1)
    # 重采样到 cols（取每列覆盖区间的最大值，保留瞬态）
    idx = np.linspace(0, frames, cols + 1).astype(int)
    out = np.zeros(cols, dtype=np.float32)
    for i in range(cols):
        a, b = idx[i], max(idx[i] + 1, idx[i + 1])
        out[i] = peaks[a:b].max() if a < frames else 0.0
    return np.clip(out, 0, 1)


def duration_str(secs: float) -> str:
    return f"{secs:0.1f} s"


def draw_card(meta: dict, secs: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([28, 26, 32, 66], fill=ACCENT)
    d.text((44, 20), meta["title"], font=font(26), fill=FG)
    d.text((44, 56), meta.get("subtitle", ""), font=font(15), fill=DIM)
    d.line([28, 88, W - 28, 88], fill=(38, 38, 50))
    d.text((W - 28 - 58, H - 52), duration_str(secs), font=font(16), fill=ACCENT)
    d.text((28, H - 40), "露西 · GPT-SoVITS v5turbo · 48 kHz", font=font(12), fill=DIM)
    d.rectangle([0, H - 3, W - 1, H - 1], fill=(90, 70, 110))
    return img


def render_frames(card: Image.Image, env: np.ndarray, secs: float, out_dir: Path) -> int:
    cols = len(env)
    step = BAR_W + BAR_GAP
    total = max(1, int(round(secs * FPS)))
    for i in range(total + 1):
        t = i / FPS
        ratio = min(1.0, t / secs) if secs else 1.0
        played = int(round(cols * ratio))
        img = card.copy()
        d = ImageDraw.Draw(img)
        for c in range(cols):
            h = max(1.0, env[c] * WAVE_H)
            x = WAVE_X + c * step
            if x + BAR_W > WAVE_X + WAVE_W:
                break
            color = BAR_PLAY if c < played else BAR_IDLE
            y0 = WAVE_Y + (WAVE_H - h) / 2
            d.rectangle([x, y0, x + BAR_W - 1, y0 + h], fill=color)
        # 播放头
        px = WAVE_X + WAVE_W * ratio
        d.rectangle([px - 1, WAVE_Y - 8, px + 1, WAVE_Y + WAVE_H + 8], fill=(255, 255, 255))
        img.save(out_dir / f"{i:05d}.png")
    return total + 1


def encode(ffmpeg: str, frames_dir: Path, audio: Path, out_mp4: Path) -> None:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(FPS), "-i", str(frames_dir / "%05d.png"),
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "slow", "-crf", "26",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ac", "1",
        "-shortest", "-movflags", "+faststart",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="docs/demo", help="wav/mp3 与 meta.json 所在目录")
    ap.add_argument("--out", default="", help="输出目录（默认同 --src）")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    out_dir = Path(args.out).resolve() if args.out else src
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))

    for stem, info in meta.items():
        wav = src / f"{stem}.wav"
        audio = wav if wav.exists() else src / f"{stem}.mp3"
        if not audio.exists():
            print(f"跳过 {stem}：没有音频")
            continue
        if audio.suffix == ".wav":
            samples, rate = read_wav(audio)
            secs = len(samples) / rate
        else:
            secs = probe_duration(args.ffmpeg, audio)
            tmp = Path(tempfile.mkdtemp()) / "a.wav"
            subprocess.run(
                [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(audio), "-ac", "1", "-ar", "48000", str(tmp)],
                check=True,
            )
            samples, rate = read_wav(tmp)
            shutil.rmtree(tmp.parent, ignore_errors=True)

        cols = WAVE_W // (BAR_W + BAR_GAP)
        env = envelope(samples, rate, cols)
        card = draw_card(info, secs)
        frames_dir = Path(tempfile.mkdtemp())
        try:
            n = render_frames(card, env, secs, frames_dir)
            mp4 = out_dir / f"{stem}.mp4"
            encode(args.ffmpeg, frames_dir, audio, mp4)
            print(f"{mp4.name}  {secs:0.1f}s  {n} 帧  {mp4.stat().st_size / 1024:.0f} KB")
            if args.keep_frames:
                keep = out_dir / f"{stem}.frames"
                shutil.copytree(frames_dir, keep, dirs_exist_ok=True)
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)
    return 0


def probe_duration(ffmpeg: str, path: Path) -> float:
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


if __name__ == "__main__":
    sys.exit(main())
