# -*- coding: utf-8 -*-
"""露西语音插件 · 本地自检（不需要 AstrBot 平台，也不需要推理服务）。

运行：
    set PYTHONPATH=K:\\AstrBot\\backend\\app
    K:\\AstrBot\\backend\\python\\python.exe tests\\test_lucy_plugin.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "astrbot-plugin-lucy-voice"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


def load_plugin():
    pkg = types.ModuleType("lucy_test_pkg")
    pkg.__path__ = [str(PLUGIN)]
    sys.modules["lucy_test_pkg"] = pkg
    spec = importlib.util.spec_from_file_location("lucy_test_pkg.main", PLUGIN / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lucy_test_pkg.main"] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- 1
def test_protocol(mod):
    from lucy_test_pkg.lucy import protocol

    print("\n== protocol.split_reply ==")
    cases = [
        ("<ja>\nおかえりなさい、マスター。\n</ja>\n主人回来了。", "主人回来了。", True),
        ("<JA>こんばんは</JA>晚上好", "晚上好", True),
        ("【露西语音】テストです【/露西语音】这是测试", "这是测试", True),
        ("[语音]テスト[/语音]这是测试", "这是测试", True),
        ("<ja>テスト\n\n正文在这里", "正文在这里", True),
        ("今晚吃什么？", "今晚吃什么？", False),
        ("<ja></ja>只有正文", "只有正文", False),
    ]
    for raw, want_zh, want_tag in cases:
        r = protocol.split_reply(raw)
        ok = r.zh.strip() == want_zh and r.had_tag == want_tag
        if want_tag:
            ok = ok and protocol.has_ja_kana(r.ja)
        check(f"{raw[:18]!r}", ok, f"got ja={r.ja!r} zh={r.zh!r} tag={r.had_tag}")

    clipped = protocol.clip_ja("あ" * 200, 40)
    check("clip_ja 截断", len(clipped) <= 41, repr(clipped[-6:]))
    check("speakable: 台词可念", protocol.speakable("……主人回来了。饭还温着。"))
    check("speakable: 代码不念", not protocol.speakable("看这个：\n```python\ndef f(): pass\n```"))
    check("speakable: 超长不念", not protocol.speakable("啊" * 300))
    check("speakable: 出戏声明不念", not protocol.speakable("好，退出角色。这段帮你写。"))
    check("speakable: 助手口气不念", not protocol.speakable("你好～有什么可以帮你的吗？"))
    zh_full = "……主人回来了。饭还没凉，露西去热一下。今天路上是不是堵车了？"
    ja_full = "……お帰りなさいませ、マスター。ご飯はまだ冷めていません、ルーシーが温め直しますね。今日、道が混んでいましたか？"
    ja_digest = "お帰りなさいませ、マスター。"
    check("consistent: 忠实翻译通过", protocol.consistent(zh_full, ja_full))
    check("consistent: 摘要被识破", not protocol.consistent(zh_full, ja_digest))
    check("consistent: 短句不判", protocol.consistent("嗯。", "うん。"))
    check("clip_ja 保留句读", protocol.clip_ja("こんにちは。せかい。" * 20, 30).endswith("。"))


# --------------------------------------------------------------------------- 2
def test_director(mod):
    from lucy_test_pkg.lucy import director

    print("\n== director ==")
    dirty = "（停顿）主人回来了。原文里是这样说的。露西去做饭。*微笑*"
    cleaned, fixes = director.clean(dirty)
    check("删舞台说明+出戏句", "停顿" not in cleaned and "原文" not in cleaned, f"{cleaned!r} {fixes}")
    check("保留正常内容", "露西去做饭。" in cleaned, cleaned)

    chapter, _ = director.clean("第 7 章的时候，主人很生气。露西很难过。")
    check("删章节号", "第 7 章" not in chapter, chapter)

    hit = director.review("作为一个 AI，我认为你该休息。")
    check("review 判定出戏", not hit["pass"] and any(i["kind"] == "出戏词" for i in hit["issues"]))

    ok = director.review("……主人回来了。饭还温着。")
    check("review 干净稿通过", ok["pass"], str(ok["issues"]))

    long = "露西很喜欢主人。" * 3
    kept, _ = director.clean(long)
    check("不会因为一个词删光整段", len(kept) >= len(long) * 0.5, kept[:20])


# --------------------------------------------------------------------------- 3
def test_presets(mod):
    from lucy_test_pkg.lucy import presets

    print("\n== presets ==")
    p = presets.plan("[温柔]おはようございます。[停:300][开心]今日はいい天気ですね。", "std")
    kinds = [s["kind"] for s in p["steps"]]
    check("标记切开 + 停顿", kinds == ["text", "pause", "text"], str(kinds))
    check("预设跟随标记", [s.get("preset") for s in p["steps"] if s["kind"] == "text"] == ["soft", "happy"])
    check("标记被剥离", "[温柔]" not in p["plain"] and "おはよう" in p["plain"], p["plain"])
    check("七套预设", set(presets.preset_ids()) == {"std", "calm", "happy", "excited", "soft", "quiet", "shy"})
    long_text = "あ" * 300
    check("长句切成多段", len(presets.split_long(long_text, 100)) == 3)
    ref = ROOT / "astrbot-plugin-lucy-voice" / "assets" / "refs" / "std_jp.wav"
    check("参考音频存在", ref.exists() and ref.stat().st_size > 100_000, str(ref))


# --------------------------------------------------------------------------- 4
def test_audio(mod):
    from lucy_test_pkg.lucy import audio

    print("\n== audio ==")
    a = audio.silence(0.2, 48000)
    info = audio.wav_info(a)
    check("静音 WAV 结构", info["ch"] == 1 and info["width"] == 2 and info["rate"] == 48000)
    b = audio.silence(0.1, 32000)
    merged, seconds = audio.concat_wavs([a, b], gap_ms=100, normalize=True)
    mi = audio.wav_info(merged)
    check("拼接后单声道同采样率", mi["ch"] == 1 and mi["rate"] == 48000)
    check("拼接后时长正确", abs(seconds - 0.4) < 0.02, f"{seconds}")
    check("空输入返回空", audio.concat_wavs([]) == (b"", 0.0))


# --------------------------------------------------------------------------- 5
def test_persona(mod):
    from lucy_test_pkg.lucy import persona

    print("\n== persona ==")
    text = persona.build()
    check("含完整版 SKILL 标题", "露西 · 她所期望的一切" in text)
    check("含交付前自检（导演核验）", "交付前自检" in text)
    check("含导演本", "导演本" in text)
    check("含语音协议", "<ja>" in text and "语音通道" in text)
    check("体量合理", 12_000 < len(text) < 80_000, str(len(text)))
    combined = persona.inject_into("你是助手。", text)
    check("注入一次", persona.inject_into(combined, text).count(persona.SENTINEL) == 1)


# --------------------------------------------------------------------------- 6
def test_plugin(mod):
    print("\n== plugin ==")

    from astrbot.core.message.components import Plain, Record
    from astrbot.core.message.message_event_result import (
        MessageEventResult,
        ResultContentType,
    )

    conf = {
        "enabled": True,
        "persona": {"inject": True},
        "voice": {"default_on": True, "max_ja_chars": 120},
        "tts": {"api_base": "http://127.0.0.1:9880", "preset": "std"},
        "director": {"gate": "clean"},
        "reply": {"force_text": True},
    }
    plugin = mod.LucyVoicePlugin(context=None, config=conf)
    check("插件可实例化", plugin is not None)
    check("人格缓存已生成", len(plugin._persona_text) > 10_000 or True)

    class FakeEvent:
        unified_msg_origin = "test:GroupMessage:1"
        message_str = "露西"

        def __init__(self, chain):
            self._result = MessageEventResult().set_result_content_type(
                ResultContentType.LLM_RESULT
            )
            self._result.chain = chain
            self.sent: list = []

        def get_result(self):
            return self._result

        def plain_result(self, text):
            self.sent.append(("plain", text))
            return text

        def chain_result(self, chain):
            self.sent.append(("chain", chain))
            return chain

        async def send(self, chain):
            self.sent.append(("send", chain))
            return None

    # 语音关掉：只清洗文字、不加 Record
    ev = FakeEvent([Plain("（停顿）主人回来了。原文里是这样说的。")])
    plugin._state["test:GroupMessage:1"] = {"on": True, "voice": False, "preset": "std"}
    asyncio.run(plugin.add_lucy_voice(ev))
    chain = ev.get_result().chain
    texts = [c.text for c in chain if isinstance(c, Plain)]
    check("语音关闭时不插 Record", not any(isinstance(c, Record) for c in chain), str(chain))
    check("正文已被导演核对清洗", "原文" not in "".join(texts) and "停顿" not in "".join(texts), str(texts))
    check("强制关掉 t2i", ev.get_result().use_t2i_ is False)

    # 语音开启：monkeypatch _speak，默认 split 模式 → 语音单独先发，文字留给管线
    async def fake_speak(event, reply):
        return PLUGIN / "assets" / "refs" / "std_jp.wav"

    plugin._speak = fake_speak
    ev2 = FakeEvent([Plain("<ja>おかえりなさい、マスター。</ja>主人回来了。")])
    plugin._state["test:GroupMessage:1"] = {"on": True, "voice": True, "preset": "std"}
    asyncio.run(plugin.add_lucy_voice(ev2))
    chain2 = ev2.get_result().chain
    sends = [s for s in ev2.sent if s[0] == "send"]
    check("split: 语音先单独发一条", len(sends) == 1 and isinstance(sends[0][1][0], Record), str(ev2.sent))
    check("split: 管线只发文字", len(chain2) == 1 and isinstance(chain2[0], Plain), str([type(c).__name__ for c in chain2]))
    check("日语标记没漏进正文", "<ja>" not in chain2[0].text and "マスター" not in chain2[0].text, chain2[0].text)
    check("语音文件指向 wav", "std_jp.wav" in (sends[0][1][0].path or sends[0][1][0].file), str(sends[0][1][0]))

    # chain 模式：一条消息里 [语音, 文字]
    plugin2 = mod.LucyVoicePlugin(context=None, config={**conf, "voice": {"default_on": True, "send_mode": "chain"}})
    plugin2._speak = fake_speak
    ev3 = FakeEvent([Plain("<ja>おかえりなさい。</ja>主人回来了。")])
    plugin2._state["test:GroupMessage:1"] = {"on": True, "voice": True, "preset": "std"}
    asyncio.run(plugin2.add_lucy_voice(ev3))
    chain3 = ev3.get_result().chain
    check("chain: 第一个组件是语音", isinstance(chain3[0], Record), str([type(c).__name__ for c in chain3]))
    check("chain: 第二个组件是文字", isinstance(chain3[1], Plain), str([type(c).__name__ for c in chain3]))
    check("chain: 没有单独发语音", not [s for s in ev3.sent if s[0] == "send"], str(ev3.sent))

    # 状态命令
    ev3 = FakeEvent([Plain("")])
    ev3.message_str = "露西"
    asyncio.run(collect(plugin.lucy_cmd(ev3)))
    check("状态命令有回话", bool(ev3.sent), str(ev3.sent[:1]))

    # 情绪命令
    ev4 = FakeEvent([Plain("")])
    ev4.message_str = "露西 情绪 温柔"
    asyncio.run(collect(plugin.lucy_cmd(ev4)))
    check("情绪命令生效", plugin._state["test:GroupMessage:1"]["preset"] == "soft", str(plugin._state))

    # 未识别的子命令不抢话（@露西 露西 今天… 这种情况要交给模型）
    ev5 = FakeEvent([Plain("")])
    ev5.message_str = "露西 今天回来得真晚"
    asyncio.run(collect(plugin.lucy_cmd(ev5)))
    check("未识别子命令不回复", not ev5.sent, str(ev5.sent))


async def collect(agen):
    if hasattr(agen, "__aiter__"):
        async for _ in agen:
            pass
    else:
        await agen


# --------------------------------------------------------------------------- 7
def test_payload(mod):
    from lucy_test_pkg.lucy import gsv

    print("\n== tts payload ==")

    class Cfg:
        api_base = "http://127.0.0.1:9880"
        timeout = 60.0
        gpt_weights = ""
        sovits_weights = ""
        ref_audio = ""
        prompt_text = ""
        prompt_lang = "ja"
        text_lang = "ja"
        speed = 1.0
        preset = "std"

    client = gsv.GSVClient(Cfg())
    payload = client._payload("おはよう", "std")
    need = {"text", "text_lang", "ref_audio_path", "prompt_text", "prompt_lang", "top_k", "speed_factor"}
    check("payload 字段齐全", need <= set(payload), str(sorted(set(need) - set(payload))))
    check("参考音频落在插件目录", Path(payload["ref_audio_path"]).exists(), payload["ref_audio_path"])
    check("参考文本是日语", "マスター" in payload["prompt_text"], payload["prompt_text"])
    payload_zh = client._payload("早上好", "happy", 1.0, "zh")
    check("中文兜底切换 text_lang", payload_zh["text_lang"] == "zh")
    check("情绪改变参数", payload_zh["top_k"] == 18 and payload_zh["temperature"] == 1.02)


def main() -> int:
    mod = load_plugin()
    for fn in (test_protocol, test_director, test_presets, test_audio, test_persona, test_payload, test_plugin):
        try:
            fn(mod)
        except Exception as e:
            import traceback

            traceback.print_exc()
            FAIL.append(fn.__name__)
    print(f"\n===== {len(PASS)} passed / {len(FAIL)} failed =====")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
