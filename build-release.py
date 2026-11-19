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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "astrbot-plugin-lucy-voice"
RELEASE = ROOT / "release"
TOOLS = ROOT / "tools"
DIST = ROOT / "dist"
VERSION = "1.0.0"
NAME = f"lucy-astrbot-{VERSION}"
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


def zip_plugin(out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(PLUGIN.rglob("*")):
            if any(part in SKIP for part in p.parts) or p.suffix == ".pyc" or not p.is_file():
                continue
            z.write(p, f"astrbot_plugin_lucy_voice/{p.relative_to(PLUGIN).as_posix()}")


def zip_tree(src: Path, out: Path, arcroot: str) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            if any(part in SKIP for part in p.parts) or p.suffix == ".pyc" or not p.is_file():
                continue
            z.write(p, f"{arcroot}/{p.relative_to(src).as_posix()}")


def main() -> int:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)

    # 1) 插件源码 + 单包 zip（热装用）
    copy_tree(PLUGIN, STAGE / "astrbot-plugin-lucy-voice")
    zip_plugin(STAGE / "astrbot-plugin-lucy-voice-1.0.0.zip")
    zip_plugin(DIST / "astrbot-plugin-lucy-voice-1.0.0.zip")

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
    demo_src = ROOT / "docs" / "demo"
    if demo_src.is_dir():
        for mp3 in sorted(demo_src.glob("*.mp3")):
            shutil.copy2(mp3, demo / mp3.name)
    else:
        for sample in (ROOT / "out" / "live_std.wav",):
            if sample.exists():
                shutil.copy2(sample, demo / "japanese_sample.wav")
                break

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
    out = DIST / f"{NAME}.zip"
    zip_tree(STAGE, out, NAME)
    total = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    print(f"文件数 {len(files)} / 解包后 {total/1024/1024:.2f} MB")
    print(f"整合包 {out.name}: {out.stat().st_size/1024/1024:.2f} MB")
    print(f"  sha256 {sha256(out)}")
    print(f"单包   astrbot-plugin-lucy-voice-1.0.0.zip: "
          f"{(DIST/'astrbot-plugin-lucy-voice-1.0.0.zip').stat().st_size/1024/1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
