#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""露西 × AstrBot 一键安装器（发行整合包入口）

做的事情（全部可回滚）：
  1. 把插件拷进 AstrBot 的插件目录（data/plugins/astrbot_plugin_lucy_voice）
  2. 合并插件配置（权重路径 / api_v2 地址 / auto_start），不动你已有的其它设置
  3. 若 AstrBot 正在运行：通过 WebUI 接口热装 + 热重载，省一次重启
  4. 把「露西」写进 AstrBot 人格并设为默认人格（可用 --no-persona 跳过）
  5. 自检：插件是否激活、推理服务是否在线、权重文件是否存在

用法（双击 install-lucy-astrbot.cmd 也行）：
    python install.py
    python install.py --password 我的密码
    python install.py --data "D:\\AstrBot\\data" --gpt-weights "D:\\w\\e10.ckpt" --sovits-weights "D:\\w\\e8.pth" --gsv-root "D:\\GPT-SoVITS"
    python install.py --uninstall            # 回滚：删插件、默认人格还原
    python install.py --dry-run              # 只打印计划
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_SRC = HERE / "astrbot-plugin-lucy-voice"
PLUGIN_DIRNAME = "astrbot_plugin_lucy_voice"
WEIGHTS_SUBDIR = "weights"
WEIGHT_FILES = ("lucy_v1_v5turbo_e8_s14528_l8.pth", "lucy_v1_v5turbo-e10.ckpt")
PERSONA_SCRIPT = HERE / "tools" / "setup_astrbot_persona.py"
BUNDLE_ZIP = HERE / "astrbot-plugin-lucy-voice-1.0.0.zip"
VERSION = "1.0.0"


# ---------------------------------------------------------------- 小工具
def say(msg: str = "") -> None:
    print(msg, flush=True)


def step(n: int, total: int, msg: str) -> None:
    say(f"\n[{n}/{total}] {msg}")


def default_data_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".astrbot" / "data"


def find_data_dir(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(default_data_dir())
    env = os.environ.get("ASTRBOT_DATA") or os.environ.get("ASTRBOT_ROOT")
    if env:
        p = Path(env)
        candidates.append(p if p.name == "data" else p / "data")
    for c in candidates:
        if (c / "cmd_config.json").exists():
            return c.resolve()
    tried = "\n".join(f"  - {c}" for c in candidates)
    raise SystemExit(
        "找不到 AstrBot 的数据目录（里面应该有 cmd_config.json）。\n"
        f"找过这些位置：\n{tried}\n"
        "解决：先用 AstrBot 桌面端启动一次，或用 --data 指定，例如\n"
        '  python install.py --data "C:\\Users\\你\\.astrbot\\data"'
    )


# ---------------------------------------------------------------- HTTP
def api(base: str, path: str, token: str | None = None, method: str = "GET", body=None, timeout=120):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{method} {path} → HTTP {e.code}: {detail}") from None
    except Exception as e:
        raise RuntimeError(f"{method} {path} → {e}") from None


def api_alive(base: str) -> bool:
    try:
        api(base, "/api/auth/login", method="POST", body={"username": "", "password": ""}, timeout=5)
        return True
    except RuntimeError as e:
        # 401 说明服务在，只是账号密码不对
        return "401" in str(e) or "422" in str(e)


def login(base: str, password: str) -> str:
    data = api(base, "/api/auth/login", method="POST", body={"username": "astrbot", "password": password})
    return data["data"]["token"]


def upload_plugin(base: str, token: str) -> dict:
    """用 WebUI 的「从文件安装」接口装插件（会顺带加载）。"""
    boundary = "----LucyVoiceBoundary7f3a"
    payload = BUNDLE_ZIP.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{BUNDLE_ZIP.name}"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        base + "/api/v1/plugins/install/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- 配置
def base_config() -> dict:
    return {
        "enabled": True,
        "persona": {"inject": True, "include_casebook": False, "include_voice_lib": False, "extra_prompt": ""},
        "voice": {
            "default_on": True,
            "fallback_zh": True,
            "max_ja_chars": 200,
            "send_text_after_voice": True,
            "send_mode": "split",
            "emotion_markers": True,
            "faithful": True,
            "translate_fallback": True,
        },
        "tts": {
            "api_base": "http://127.0.0.1:9880",
            "timeout": 120,
            "gpt_weights": "",
            "sovits_weights": "",
            "set_weights_on_init": True,
            "ref_audio": "",
            "prompt_text": "",
            "text_lang": "ja",
            "prompt_lang": "ja",
            "preset": "std",
            "speed": 1.0,
            "gap_ms": 160,
            "normalize": True,
            "auto_start": False,
            "gsv_root": "",
            "base_yaml": "",
            "python": "",
        },
        "director": {"gate": "clean", "provider_id": ""},
        "reply": {"force_text": True},
        "debug": False,
    }


def merge_config(cfg_path: Path, args, force: bool) -> dict:
    cfg = base_config()
    if cfg_path.exists() and not force:
        try:
            existing = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = {}
        if isinstance(existing, dict):
            for k, v in existing.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
            say(f"   · 已有配置：保留你填过的项（{cfg_path.name}）")
    if args.gpt_weights:
        cfg["tts"]["gpt_weights"] = args.gpt_weights
    if args.sovits_weights:
        cfg["tts"]["sovits_weights"] = args.sovits_weights
    if args.gsv_root:
        cfg["tts"]["gsv_root"] = args.gsv_root
        cfg["tts"]["auto_start"] = True
    if args.api_base:
        cfg["tts"]["api_base"] = args.api_base
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg


# ---------------------------------------------------------------- 安装 / 卸载
def copy_plugin(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        PLUGIN_SRC,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def bundle_weights() -> Path | None:
    """安装包里带的权重：优先 插件目录/weights，其次 根目录/weights。"""
    for cand in (PLUGIN_SRC / WEIGHTS_SUBDIR, HERE / WEIGHTS_SUBDIR):
        if cand.is_dir() and all((cand / f).exists() for f in WEIGHT_FILES):
            return cand
    return None


def copy_weights(src: Path, dst_plugin: Path) -> int:
    """把权重拷进已安装的插件目录（插件启动时会自己扫到）。"""
    target = dst_plugin / WEIGHTS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    for f in WEIGHT_FILES:
        s, d = src / f, target / f
        if d.exists() and d.stat().st_size == s.stat().st_size:
            say(f"   · 权重已就位：{f}")
            total += d.stat().st_size
            continue
        shutil.copy2(s, d)
        total += d.stat().st_size
        say(f"   · 复制权重：{f}（{d.stat().st_size/1048576:.1f} MB）")
    return total


def run_persona(args, base: str, password: str | None) -> int:
    cmd = [sys.executable, str(PERSONA_SCRIPT)]
    if password:
        cmd += ["--password", password]
    if base:
        cmd += ["--base", base]
    cmd += ["--plugin-dir", str(PLUGIN_SRC)]
    say("   · " + " ".join(str(c) for c in cmd))
    return subprocess.call(cmd)


def install(args) -> int:
    total = 6
    data = find_data_dir(args.data)
    say(f"露西 × AstrBot 安装器 v{VERSION}")
    say(f"   AstrBot 数据目录：{data}")

    plugins = data / "plugins"
    cfg_path = data / "config" / f"{PLUGIN_DIRNAME}_config.json"
    dst = plugins / PLUGIN_DIRNAME
    base = args.base.rstrip("/")

    step(1, total, "检查安装包")
    for p in (PLUGIN_SRC / "main.py", PLUGIN_SRC / "_conf_schema.json", PERSONA_SCRIPT):
        if not p.exists():
            raise SystemExit(f"安装包不完整：缺少 {p}")
    say(f"   · 插件源：{PLUGIN_SRC}")
    say(f"   · 目标：{dst}")
    if args.dry_run:
        say("   · --dry-run：到此为止")
        return 0

    step(2, total, "写入插件配置")
    cfg = merge_config(cfg_path, args, args.force_config)
    say(f"   · {cfg_path}")
    say(f"   · 权重：gpt={cfg['tts']['gpt_weights'] or '(未填)'}")
    say(f"           sovits={cfg['tts']['sovits_weights'] or '(未填)'}")
    say(f"   · api_v2：{cfg['tts']['api_base']}，auto_start={cfg['tts']['auto_start']}")

    step(3, total, "安装插件")
    password = args.password
    online = api_alive(base)
    used_api = False
    if online and BUNDLE_ZIP.exists():
        if not password and sys.stdin.isatty():
            say("   · AstrBot 正在运行，用 WebUI 账号热装（直接回车＝跳过，改走文件安装）")
            password = input("   · WebUI 密码：").strip() or None
        if password:
            try:
                token = login(base, password)
                res = upload_plugin(base, token)
                say(f"   · 热装结果：{res.get('message') or res.get('status')}")
                used_api = True
            except Exception as e:
                say(f"   · 热装失败（{e}），改走文件安装")
    if not used_api:
        plugins.mkdir(parents=True, exist_ok=True)
        copy_plugin(dst)
        say(f"   · 已拷贝到 {dst}")
        if online:
            say("   · 提示：AstrBot 正在运行，重载插件或重启后生效（WebUI → 插件管理 → 重载）")

    step(4, total, "布置语音权重")
    wsrc = None if args.skip_weights else bundle_weights()
    if args.gpt_weights or args.sovits_weights:
        say("   · 用命令行传的权重路径（写进配置）")
    elif wsrc:
        if used_api:
            # 热装只装了代码，权重得单独放到插件目录里
            copy_weights(wsrc, dst)
        else:
            say(f"   · 安装包里自带权重（{wsrc}），已随插件目录一起拷贝")
        cfg["tts"]["gpt_weights"] = str((dst / WEIGHTS_SUBDIR / WEIGHT_FILES[1]).resolve())
        cfg["tts"]["sovits_weights"] = str((dst / WEIGHTS_SUBDIR / WEIGHT_FILES[0]).resolve())
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        say(f"   · 配置已指向：{dst / WEIGHTS_SUBDIR}")
    else:
        say("   · 安装包里没有权重，也没传参数——插件启动时会在自己的 weights/ 里扫；"
            "扫不到就用你现有的推理服务权重")

    step(5, total, "配置 AstrBot 人格")
    if args.no_persona:
        say("   · --no-persona：跳过（插件会自己注入完整版人格）")
    elif not online:
        say("   · AstrBot 没在运行，人格先不写。启动后执行：")
        say(f'     python "{PERSONA_SCRIPT}" --password <WebUI密码> --plugin-dir "{PLUGIN_SRC}"')
    elif not password:
        say("   · 没有 WebUI 密码，人格先不写。可稍后执行：")
        say(f'     python "{PERSONA_SCRIPT}" --password <WebUI密码> --plugin-dir "{PLUGIN_SRC}"')
    else:
        rc = run_persona(args, base, password)
        say(f"   · 人格脚本退出码：{rc}")

    step(6, total, "自检")
    if online and password:
        try:
            token = login(base, password)
            items = api(base, "/api/v1/plugins", token)["data"]
            items = items if isinstance(items, list) else items.get("plugins") or []
            for p in items:
                if p.get("name") == PLUGIN_DIRNAME:
                    say(f"   · 插件：activated={p.get('activated')} error={p.get('error')}")
        except Exception as e:
            say(f"   · 插件状态查询失败：{e}")
    for key in ("gpt_weights", "sovits_weights"):
        val = cfg["tts"][key]
        if val:
            say(f"   · {key}: {'存在' if Path(val).exists() else '找不到文件！'}")
        else:
            say(f"   · {key}: 未填（用的是推理服务当前权重）")
    try:
        with urllib.request.urlopen(cfg["tts"]["api_base"] + "/", timeout=3) as r:
            say(f"   · 推理服务：在线（HTTP {r.status}）")
    except Exception:
        say("   · 推理服务：离线（首条消息会触发 auto_start，或先启动露西语音工坊）")

    say("\n完成。接下来：")
    say("   1. QQ 里发一句「我回来了」看是不是先语音、后文字")
    say("   2. 发 /露西 看状态；/露西 念 おかえりなさい 试听")
    say("   3. 想回滚：python install.py --uninstall")
    return 0


def uninstall(args) -> int:
    data = find_data_dir(args.data)
    dst = data / "plugins" / PLUGIN_DIRNAME
    base = args.base.rstrip("/")
    say("回滚露西 × AstrBot")
    if dst.exists():
        shutil.rmtree(dst)
        say(f"   · 已删除插件目录：{dst}")
    else:
        say("   · 插件目录本来就不存在")

    password = args.password
    if api_alive(base) and not password and sys.stdin.isatty():
        password = input("   · WebUI 密码（用于还原默认人格，可留空跳过）：").strip() or None
    if password:
        try:
            token = login(base, password)
            profiles = api(base, "/api/v1/config-profiles", token)["data"]
            items = profiles if isinstance(profiles, list) else profiles.get("info_list") or []
            pid = (items[0].get("id") if items else None) or "default"
            conf = api(base, f"/api/v1/config-profiles/{pid}", token)["data"]
            config = conf.get("config") if isinstance(conf, dict) and "config" in conf else conf
            config.setdefault("agent_runner", {}).setdefault("config", {}).setdefault("persona", {})["persona_id"] = "default"
            api(base, f"/api/v1/config-profiles/{pid}", token, "PUT", config)
            say("   · 默认人格已还原为 default")
            if args.purge_persona:
                api(base, "/api/v1/personas/by-id?persona_id=lucy", token, "DELETE")
                say("   · 已删除人格 lucy")
        except Exception as e:
            say(f"   · 还原人格失败：{e}")
    say("   · 配置文件和人格（lucy）默认保留，方便以后重装；要删就手动删")
    say("   · 插件要重启 AstrBot（或在 WebUI 里点重载）才会彻底卸载")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="露西 × AstrBot 发行版安装器")
    ap.add_argument("--data", help="AstrBot 数据目录（默认 ~/.astrbot/data）")
    ap.add_argument("--base", default="http://127.0.0.1:6185", help="WebUI 地址")
    ap.add_argument("--password", help="WebUI 密码（热装/写人格用）")
    ap.add_argument("--api-base", help="GPT-SoVITS api_v2 地址，默认 http://127.0.0.1:9880")
    ap.add_argument("--gpt-weights", help="GPT(s1) 权重绝对路径（lucy_v1_v5turbo-e10.ckpt）")
    ap.add_argument("--sovits-weights", help="SoVITS LoRA 绝对路径（lucy_v1_v5turbo_e8_*.pth）")
    ap.add_argument("--gsv-root", help="GPT-SoVITS 根目录（含 api_v2.py），填了会自动开 auto_start")
    ap.add_argument("--no-persona", action="store_true", help="不写 AstrBot 人格")
    ap.add_argument("--skip-weights", action="store_true", help="忽略安装包里的权重")
    ap.add_argument("--force-config", action="store_true", help="用默认值覆盖插件配置")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    ap.add_argument("--uninstall", action="store_true", help="回滚安装")
    ap.add_argument("--purge-persona", action="store_true", help="回滚时连人格一起删")
    args = ap.parse_args()
    return uninstall(args) if args.uninstall else install(args)


if __name__ == "__main__":
    raise SystemExit(main())
