# -*- coding: utf-8 -*-
"""按 AstrBot 真实加载方式验证已安装的插件（不启动平台、不发消息）。

    set PYTHONPATH=K:\\AstrBot\\backend\\app
    K:\\AstrBot\\backend\\python\\python.exe tests\\test_installed.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ASTRBOT_ROOT = Path.home() / ".astrbot"
PLUGIN_DIR = ASTRBOT_ROOT / "data" / "plugins" / "astrbot_plugin_lucy_voice"

sys.path.insert(0, str(ASTRBOT_ROOT))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if not cond else ""))


def main() -> int:
    print("== 目录 ==")
    check("插件目录存在", PLUGIN_DIR.is_dir(), str(PLUGIN_DIR))
    for f in ("main.py", "metadata.yaml", "_conf_schema.json", "lucy/presets.py", "persona/SKILL.md"):
        check(f"文件 {f}", (PLUGIN_DIR / f).exists())

    print("\n== metadata.yaml（AstrBot 校验器）==")
    import yaml
    from astrbot.core.star.updater import _PluginUpdater

    meta = yaml.safe_load((PLUGIN_DIR / "metadata.yaml").read_text(encoding="utf-8"))
    try:
        _PluginUpdater.validate_plugin_metadata(meta, "metadata.yaml")
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    check("metadata 通过校验", ok, str(meta))
    check("name 与目录一致", meta.get("name") == PLUGIN_DIR.name, str(meta.get("name")))

    print("\n== _conf_schema.json（AstrBot 配置器）==")
    from astrbot.core.config.astrbot_config import AstrBotConfig

    schema = json.loads((PLUGIN_DIR / "_conf_schema.json").read_text(encoding="utf-8"))
    cfg_path = ASTRBOT_ROOT / "data" / "config" / "astrbot_plugin_lucy_voice_config.json"
    try:
        cfg = AstrBotConfig(str(cfg_path), schema=schema)
        check("配置可加载", True)
        check("默认值已合并", "tts" in cfg and "api_base" in cfg["tts"], str(list(cfg.keys()))[:120])
        check("权重路径已填", bool(cfg["tts"]["gpt_weights"]), cfg["tts"]["gpt_weights"])
    except Exception as e:
        import traceback

        traceback.print_exc()
        check("配置可加载", False, str(e))
        cfg = {}

    print("\n== 按 __import__ 方式加载插件模块 ==")
    mod_path = f"data.plugins.{PLUGIN_DIR.name}.main"
    try:
        mod = __import__(mod_path, fromlist=["main"])
        check("模块可导入", True)
    except Exception as e:
        import traceback

        traceback.print_exc()
        check("模块可导入", False, str(e))
        return 1

    from astrbot.api.star import Star

    cls = getattr(mod, "LucyVoicePlugin", None)
    check("类存在", cls is not None)
    check("是 Star 子类", issubclass(cls, Star))

    print("\n== 注册的 handler ==")
    # 装饰器注册在导入时完成，从注册表反查
    from astrbot.core.star.star_handler import star_handlers_registry

    handlers = [
        h for h in star_handlers_registry
        if getattr(h, "handler_module_path", "").endswith(f"{PLUGIN_DIR.name}.main")
    ]
    names = sorted({h.handler_name for h in handlers})
    print("   ", names)
    check("注册了 on_llm_request", any("inject_persona" == n for n in names), str(names))
    check("注册了 on_decorating_result", any("add_lucy_voice" == n for n in names), str(names))
    check("注册了命令", any("lucy_cmd" == n for n in names), str(names))

    print("\n== 实例化 + 真实配置 ==")
    try:
        plugin = cls(context=None, config=cfg)
        check("实例化成功", True)
        import asyncio

        asyncio.run(plugin.initialize())
        check("initialize 不抛异常", True)
        check("人格已装配", len(plugin._persona_text) > 10_000, str(len(plugin._persona_text)))
        check("推理服务探测有结果", plugin._online in (True, False), str(plugin._online))
        asyncio.run(plugin.terminate())
    except Exception as e:
        import traceback

        traceback.print_exc()
        check("实例化/初始化", False, str(e))

    print(f"\n===== {len(PASS)} passed / {len(FAIL)} failed =====")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
