# -*- coding: utf-8 -*-
"""戳一戳插件 × 露西：验证「能不能触发、触发后走不走 LLM 链路」。

    PYTHONPATH=K:\\AstrBot\\backend\\app  K:\\AstrBot\\backend\\python\\python.exe tests\\test_poke_integration.py

不需要真的 QQ：用手搓的事件对象喂给插件的 on_poke，看它有没有产出 LLM 请求。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

PLUGIN = Path.home() / ".astrbot" / "data" / "plugins" / "astrbot_plugin_poke_to_llm"
CFG_PATH = Path.home() / ".astrbot" / "data" / "config" / "astrbot_plugin_poke_to_llm_config.json"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if not cond else ""))


def load_plugin():
    spec = importlib.util.spec_from_file_location("poke_plugin_main", PLUGIN / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["poke_plugin_main"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeEvent:
    def __init__(self, platform: str, raw: dict, sender="10001", sender_name="主人",
                 group="88888"):
        self._platform = platform
        self.message_obj = SimpleNamespace(raw_message=raw, message_id="m1")
        self._sender = sender
        self._sender_name = sender_name
        self._group = group
        self.unified_msg_origin = f"{platform}:GroupMessage:{group}" if group else f"{platform}:FriendMessage:{sender}"
        self.extra: dict = {}
        self.requests: list = []

    # 平台/身份
    def get_platform_name(self):
        return self._platform

    def get_platform_id(self):
        return self._platform

    def get_self_id(self):
        return "99999"

    def get_sender_id(self):
        return self._sender

    def get_sender_name(self):
        return self._sender_name

    def get_group_id(self):
        return self._group

    def is_admin(self):
        return False

    # extra
    def set_extra(self, k, v):
        self.extra[k] = v

    def get_extra(self, k, default=None):
        return self.extra.get(k, default)

    # LLM 请求（真实实现返回 ProviderRequest；这里只要证明它被调用了）
    def request_llm(self, prompt=None, conversation=None, **kw):
        req = SimpleNamespace(prompt=prompt, conversation=conversation, kind="ProviderRequest")
        self.requests.append(req)
        return req


def poke_raw(target="99999", group="88888"):
    return {
        "post_type": "notice",
        "notice_type": "notify",
        "sub_type": "poke",
        "self_id": 99999,
        "user_id": 10001,
        "target_id": int(target),
        "group_id": int(group) if group else None,
    }


async def collect(agen):
    out = []
    async for item in agen:
        out.append(item)
    return out


def make_plugin(mod, cfg: dict):
    return mod.PokeToLLM(context=SimpleNamespace(conversation_manager=None), config=cfg)


def main() -> int:
    print("== 插件与配置 ==")
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8-sig")) if CFG_PATH.exists() else {}
    check("插件目录存在", (PLUGIN / "main.py").exists(), str(PLUGIN))
    check("配置文件存在", bool(cfg), str(CFG_PATH))
    check("提示词已改成露西版", "露西" in (cfg.get("poke_prompt") or ""), (cfg.get("poke_prompt") or "")[:40])

    mod = load_plugin()
    plugin = make_plugin(mod, cfg)
    check("插件可实例化", plugin is not None)
    check("v2.4.0", mod.VERSION == "2.4.0", mod.VERSION)

    print("\n== 场景 A：qq_official（当前平台）==")
    ev = FakeEvent("qq_official", poke_raw())
    out = asyncio.run(collect(plugin.on_poke(ev)))
    check("QQ 官方平台不触发", out == [] and ev.requests == [],
          f"yielded={len(out)} requests={len(ev.requests)}")
    print("     → 说明：QQ 官方机器人 API 不下发 poke 事件，插件在这一层就返回了")

    print("\n== 场景 B：aiocqhttp（NapCat/OneBot）==")
    ev2 = FakeEvent("aiocqhttp", poke_raw())
    out2 = asyncio.run(collect(plugin.on_poke(ev2)))
    check("戳机器人 → 产出 LLM 请求", len(out2) == 1 and len(ev2.requests) == 1,
          f"yielded={len(out2)}")
    prompt = ev2.requests[0].prompt if ev2.requests else ""
    check("请求里带露西提示词", "露西" in prompt, prompt[:60])
    check("提示词带入戳的人", "主人" in prompt or "10001" in prompt, prompt[:80])
    check("标记了 poke 触发（给上游插件认）", ev2.extra.get("_poke_trigger") is True, str(ev2.extra))

    print("\n== 场景 C：戳的不是机器人 ==")
    ev3 = FakeEvent("aiocqhttp", poke_raw(target="12345"))
    out3 = asyncio.run(collect(plugin.on_poke(ev3)))
    check("不响应", out3 == [] and ev3.requests == [])

    print("\n== 场景 D：冷却 ==")
    plugin2 = make_plugin(mod, cfg)
    ev4 = FakeEvent("aiocqhttp", poke_raw())
    plugin2._group_cooldown = 0  # 只留用户冷却，方便测
    first = asyncio.run(collect(plugin2.on_poke(ev4)))
    ev5 = FakeEvent("aiocqhttp", poke_raw())
    second = asyncio.run(collect(plugin2.on_poke(ev5)))
    check("第一次触发", len(first) == 1)
    check("冷却内第二次被挡", second == [], f"{len(second)}")

    print(f"\n===== {len(PASS)} passed / {len(FAIL)} failed =====")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
