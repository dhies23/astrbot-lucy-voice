# -*- coding: utf-8 -*-
"""露西语音 · 真机联调（会真的拉起 GPT-SoVITS 推理服务并合成一段）。

    set PYTHONPATH=K:\\AstrBot\\backend\\app
    K:\\AstrBot\\backend\\python\\python.exe tests\\test_live_tts.py

成功标准：产出 out/live_*.wav，且时长/采样率合理、能看出是露西的声音。
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "astrbot-plugin-lucy-voice"
GSV_ROOT = os.environ.get("LUCY_GSV_ROOT", "")
WEIGHTS = Path(os.environ.get("LUCY_WEIGHTS_DIR", str(Path.home() / "lucy-weights")))
sys.path.insert(0, str(PLUGIN))

from lucy import gsv  # noqa: E402
from lucy.config import Settings  # noqa: E402

CFG = {
    "tts": {
        "api_base": "http://127.0.0.1:9880",
        "timeout": 300,
        "gpt_weights": str(WEIGHTS / "lucy_v1_v5turbo-e10.ckpt"),
        "sovits_weights": str(WEIGHTS / "lucy_v1_v5turbo_e8_s14528_l8.pth"),
        "set_weights_on_init": True,
        "preset": "std",
        "auto_start": True,
        "gsv_root": GSV_ROOT,
        "python": str(Path(GSV_ROOT) / "runtime" / "python.exe") if GSV_ROOT else "",
    }
}


async def main() -> int:
    cfg = Settings(CFG)
    client = gsv.GSVClient(cfg)
    log_dir = ROOT / "out"
    log_dir.mkdir(exist_ok=True)
    service = gsv.ServiceManager(client, cfg, log_dir=log_dir)

    t0 = time.time()
    print("[1/4] 检查/拉起推理服务 …")
    ok, reason = await service.ensure_ready(timeout=420)
    if not ok:
        print(f"   失败：{reason}")
        await service.stop()
        await client.close()
        return 1
    print(f"   就绪，用时 {time.time() - t0:.1f}s；健康检查={await client.health()}")

    print("[2/4] 切换露西权重 …")
    t1 = time.time()
    if not await client.ensure_weights(force=True):
        print("   失败：切权重没成功（看日志 out/lucy_tts_api.log）")
        await service.stop()
        await client.close()
        return 1
    print(f"   完成，用时 {time.time() - t1:.1f}s")

    cases = [
        ("std", "おかえりなさいませ、マスター。ご飯はまだ温かいです。"),
        ("happy", "[开心]初めてマスターに褒めてもらえました。 嬉しい！"),
        ("soft", "[温柔]……そこにいてください。[停:300]露西、ご飯を温めてきますね。"),
    ]

    print("[3/4] 合成 …")
    for preset, text in cases:
        t2 = time.time()
        try:
            wav = await client.synth_plan(text, preset, lang="ja")
        except Exception as e:
            print(f"   {preset}: 失败 {e}")
            continue
        if not wav:
            print(f"   {preset}: 空结果")
            continue
        from lucy import audio

        info = audio.wav_info(wav)
        out = log_dir / f"live_{preset}.wav"
        out.write_bytes(wav)
        print(
            f"   {preset}: {info['seconds']}s / {info['rate']}Hz / {len(wav)}B / "
            f"{time.time() - t2:.1f}s → {out.name}"
        )

    print("[4/4] 中文兜底 …")
    try:
        wav = await client.synth_plan("主人，饭已经做好了。", "std", lang="zh")
        from lucy import audio

        info = audio.wav_info(wav)
        (log_dir / "live_zh.wav").write_bytes(wav)
        print(f"   zh: {info['seconds']}s / {info['rate']}Hz / {len(wav)}B")
    except Exception as e:
        print(f"   zh: 失败 {e}")

    keep = "--keep" in sys.argv
    if not keep:
        print("停掉本次拉起的推理服务（--keep 可保留）")
        await service.stop()
    await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
