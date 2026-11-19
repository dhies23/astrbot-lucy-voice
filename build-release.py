# -*- coding: utf-8 -*-
"""打「露西 × AstrBot」发行整合包。

    python build-release.py

产物：
    dist/lucy-astrbot-1.0.0.zip             整合包（插件 + 安装器 + 人格脚本 + 试听）
    dist/astrbot-plugin-lucy-voice-1.0.0.zip 插件单包（也塞在整合包里，供热装）
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "astrbot-plugin-lucy-voice"
RELEASE = ROOT / "release"
TOOLS = ROOT / "tools"
DIST = ROOT / "dist"
VERSION = "1.0.0"
NAME = f"lucy-astrbot-{VERSION}"
WEIGHT_FILES = ("lucy_v1_v5turbo_e8_s14528_l8.pth", "lucy_v1_v5turbo-e10.ckpt")
STAGE = ROOT / "build" / "release" / NAME

SKIP = {"__pycache__", ".git", ".pytest_cache"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.rglob("*")):
        if any(part in SKIP for part in p.parts) or p.suffix == ".pyc":
            continue
        target = dst / p.relative_to(src)
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)


def zip_plugin(out: Path, include_weights: bool = False) -> None:
    """插件单包（热装用）。默认不含权重——213 MB 塞不进 WebUI 上传。"""
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(PLUGIN.rglob("*")):
            if any(part in SKIP for part in p.parts) or p.suffix == ".pyc" or not p.is_file():
                continue
            if not include_weights and "weights" in p.relative_to(PLUGIN).parts:
                continue
            z.write(p, f"astrbot_plugin_lucy_voice/{p.relative_to(PLUGIN).as_posix()}")


def zip_tree(src: Path, out: Path, arcroot: str) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            if any(part in SKIP for part in p.parts) or p.suffix == ".pyc" or not p.is_file():
                continue
            z.write(p, f"{arcroot}/{p.relative_to(src).as_posix()}")


def find_weights(explicit: str | None) -> Path | None:
    """找一份包含两个权重文件的目录。"""
    cands: list[Path] = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("LUCY_WEIGHTS_DIR")
    if env:
        cands.append(Path(env))
    cands += [
        ROOT / "weights",
        PLUGIN / "weights",
        Path.home() / "lucy-weights",
        Path(r"B:/lucy文本skill/dsh-skill-lucy-voice/runtime/weights"),
    ]
    for c in cands:
        if c.is_dir() and all((c / f).exists() for f in WEIGHT_FILES):
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-dir", help="包含两个权重文件的目录（默认自动找）")
    ap.add_argument("--no-weights", action="store_true", help="打精简版（不含权重）")
    args = ap.parse_args()

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)

    # 1) 插件源码 + 单包 zip（热装用，永远不含权重）
    copy_tree(PLUGIN, STAGE / "astrbot-plugin-lucy-voice")
    zip_plugin(STAGE / "astrbot-plugin-lucy-voice-1.0.0.zip")
    zip_plugin(DIST / "astrbot-plugin-lucy-voice-1.0.0.zip")

    weights_dir = None if args.no_weights else find_weights(args.weights_dir)

    # 2) 安装器
    for name in ("install.py", "install-lucy-astrbot.cmd", "uninstall-lucy-astrbot.cmd", "安装说明.md"):
        shutil.copy2(RELEASE / name, STAGE / name)
    # 同名的一份 ASCII 文件名说明：不认 UTF-8 文件名的解压工具里也能找到
    shutil.copy2(RELEASE / "安装说明.md", STAGE / "INSTALL.md")

    # 3) 人格脚本
    copy_tree(TOOLS, STAGE / "tools")
    for junk in ("__pycache__",):
        p = STAGE / "tools" / junk
        if p.exists():
            shutil.rmtree(p)

    # 4) 试听
    demo = STAGE / "demo"
    demo.mkdir()
    sample = ROOT / "out" / "live_std.wav"
    if sample.exists():
        shutil.copy2(sample, demo / "japanese_sample.wav")

    # 5) 版本与校验
    (STAGE / "VERSION.txt").write_text(
        f"{NAME}\nplugin: astrbot_plugin_lucy_voice v{VERSION}\n"
        "requires: AstrBot >= 4.5, GPT-SoVITS v5turbo (api_v2)\n",
        encoding="utf-8",
    )
    files = sorted(p for p in STAGE.rglob("*") if p.is_file())
    lines = [f"{sha256(p)}  {p.relative_to(STAGE).as_posix()}" for p in files]
    (STAGE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 6) 打包
    # 先打精简版（不含权重），再塞权重打完整版
    out = DIST / f"{NAME}.zip"
    zip_tree(STAGE, out, NAME)
    print(f"精简包 {out.name}: {out.stat().st_size/1024/1024:.2f} MB")

    if weights_dir:
        wdst = STAGE / "astrbot-plugin-lucy-voice" / "weights"
        wdst.mkdir(parents=True, exist_ok=True)
        for f in WEIGHT_FILES:
            shutil.copy2(weights_dir / f, wdst / f)
        out = DIST / f"{NAME}-full.zip"
        zip_tree(STAGE, out, NAME)
        print(f"完整包 {out.name}: {out.stat().st_size/1024/1024:.2f} MB（含权重，来自 {weights_dir}）")
    else:
        print("!! 没找到权重，只出精简版")
    total = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    print(f"文件数 {len(files)} / 解包后 {total/1024/1024:.2f} MB")

    print(f"  sha256 {sha256(out)}")
    print(f"单包   astrbot-plugin-lucy-voice-1.0.0.zip: "
          f"{(DIST/'astrbot-plugin-lucy-voice-1.0.0.zip').stat().st_size/1024/1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
