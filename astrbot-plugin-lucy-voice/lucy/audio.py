# -*- coding: utf-8 -*-
"""WAV 小工具：拆帧、重采样、补静音、拼接、归一化。

GPT-SoVITS api_v2 返回 16bit PCM 单声道 WAV（露西权重通常 48 kHz），
这里只用标准库处理，避免给 AstrBot 增加依赖。
"""
from __future__ import annotations

import array
import io
import wave
from typing import Any


def wav_info(raw: bytes) -> dict[str, Any]:
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 1
            return {
                "ch": w.getnchannels(),
                "width": w.getsampwidth(),
                "rate": rate,
                "frames": frames,
                "seconds": round(frames / rate, 3),
            }
    except Exception:
        return {"ch": 1, "width": 2, "rate": 48000, "frames": 0, "seconds": 0.0}


def _decode(raw: bytes) -> tuple[array.array, dict[str, Any]]:
    with wave.open(io.BytesIO(raw), "rb") as w:
        info = {
            "ch": w.getnchannels(),
            "width": w.getsampwidth(),
            "rate": w.getframerate(),
            "frames": w.getnframes(),
        }
        data = w.readframes(w.getnframes())
    if info["width"] != 2:
        raise ValueError("只支持 16bit PCM")
    arr = array.array("h")
    arr.frombytes(data)
    return arr, info


def _resample(arr: array.array, src: int, dst: int) -> array.array:
    if src == dst or not src:
        return arr
    n = int(len(arr) * dst / src)
    out = array.array("h", bytes(2 * max(0, n)))
    step = src / dst
    for i in range(max(0, n)):
        pos = i * step
        i0 = int(pos)
        i1 = min(i0 + 1, len(arr) - 1)
        frac = pos - i0
        out[i] = int(arr[i0] * (1 - frac) + arr[i1] * frac)
    return out


def silence(seconds: float, rate: int = 48000) -> bytes:
    n = max(0, int(seconds * rate))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(2 * n))
    return buf.getvalue()


def concat_wavs(
    chunks: list[bytes], gap_ms: int = 120, normalize: bool = True
) -> tuple[bytes, float]:
    """把多段 WAV 拼成一条，中间按 gap_ms 补静音。"""
    chunks = [c for c in chunks if c]
    if not chunks:
        return b"", 0.0
    if len(chunks) == 1:
        samples, info = _decode(chunks[0])
        rate = info["rate"]
    else:
        arrays: list[array.array] = []
        rate = 0
        for ch in chunks:
            arr, info = _decode(ch)
            if info["ch"] != 1:
                raise ValueError("只支持单声道")
            if not rate:
                rate = info["rate"]
            arrays.append(_resample(arr, info["rate"], rate))
        gap = array.array("h", bytes(2 * max(0, int(rate * gap_ms / 1000.0))))
        merged = array.array("h")
        for i, a in enumerate(arrays):
            if i and len(gap):
                merged.extend(gap)
            merged.extend(a)
        samples = merged

    if normalize and len(samples):
        peak = max(max(samples), -min(samples))
        if peak > 0:
            if peak < 0.82 * 32767:  # 偏轻 -> 提上来
                g = (0.92 * 32767) / peak
                for i in range(len(samples)):
                    samples[i] = int(samples[i] * g)
            elif peak > 0.995 * 32767:  # 贴顶 -> 压一点
                g = (0.95 * 32767) / peak
                for i in range(len(samples)):
                    samples[i] = int(samples[i] * g)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue(), len(samples) / float(rate)
