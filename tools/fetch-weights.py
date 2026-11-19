#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 GitHub Release 下载露西的语音权重并校验 SHA-256。

    python tools/fetch-weights.py                 # 下到 ./weights
    python tools/fetch-weights.py --dest D:\\w    # 指定目录
    python tools/fetch-weights.py --check-only     # 只校验已有文件

只依赖标准库。下载中断的文件不会被留下（先写 .part 再改名）。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "dhies23/astrbot-lucy-voice"
TAG = "v1.0.0"
BASE = f"https://github.com/{REPO}/releases/download/{TAG}"

FILES = [
    (
        "lucy_v1_v5turbo_e8_s14528_l8.pth",
        "1b9ccc63f98513c25857a4954c564e85b9da113ead191ea124ead39dfd30375d",
        66_899_835,
        "音色 LoRA（SoVITS v5turbo, rank 8）",
    ),
    (
        "lucy_v1_v5turbo-e10.ckpt",
        "72fa496ddcc3a3f7e30bd140134cfcc909e5371f2845ec46708aa5f1b5e1988b",
        155_313_267,
        "GPT(s1)（Text2Semantic, epoch 10）",
    ),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def download(name: str, expected: str, size: int, dest: Path) -> bool:
    target = dest / name
    if target.exists() and target.stat().st_size == size:
        got = sha256(target)
        if got == expected:
            print(f"  [skip] {name} 已存在且校验通过")
            return True
        print(f"  [warn] {name} 校验不符，重新下载")
    url = f"{BASE}/{name}"
    part = target.with_suffix(target.suffix + ".part")
    print(f"  [get ] {name}  ({human(size)})")
    print(f"         {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lucy-weights-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, part.open("wb") as f:
            done = 0
            last = -1
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / max(size, 1))
                if pct // 5 != last:
                    last = pct // 5
                    print(f"         {pct:3d}%  {human(done)}", flush=True)
        got = sha256(part)
        if got != expected:
            part.unlink(missing_ok=True)
            print(f"  [FAIL] {name} SHA-256 不符\n         期望 {expected}\n         实际 {got}")
            return False
        part.replace(target)
        print(f"  [ ok ] {name}")
        return True
    except Exception as e:
        part.unlink(missing_ok=True)
        print(f"  [FAIL] {name}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="下载露西语音权重并校验")
    ap.add_argument("--dest", default="weights", help="保存目录（默认 ./weights）")
    ap.add_argument("--check-only", action="store_true", help="只校验，不下载")
    args = ap.parse_args()
    dest = Path(args.dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"目标目录：{dest}")

    ok = True
    for name, sha, size, desc in FILES:
        print(f"\n{name}  —  {desc}")
        if args.check_only:
            p = dest / name
            if not p.exists():
                print("  [miss] 文件不存在")
                ok = False
                continue
            got = sha256(p)
            good = got == sha
            print(f"  [{'ok' if good else 'FAIL'}] {human(p.stat().st_size)}  sha256 {got[:16]}…")
            ok &= good
        else:
            ok &= download(name, sha, size, dest)

    print("\n" + ("全部就绪。" if ok else "有文件失败，见上面的输出。"))
    if ok:
        print("把这两个路径填进插件配置的 tts.gpt_weights / tts.sovits_weights：")
        for name, *_ in FILES:
            print(f"  {dest / name}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
