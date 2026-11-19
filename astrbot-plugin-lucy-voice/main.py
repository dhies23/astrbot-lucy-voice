# -*- coding: utf-8 -*-
"""露西语音 · AstrBot 插件

把「露西 SKILL（完整版，含导演核对）」装进 AstrBot，并给每条回复配一条日语配音：

    QQ 里先收到露西的语音 → 紧接着收到中文文字

工作方式：

1. ``on_llm_request``：把完整版人格 + 语音协议叠进 system prompt（模型因此会先写
   一段 ``<ja>…</ja>`` 日语朗读稿，再写中文正文）。
2. ``on_decorating_result``：把回复拆成「日语稿 / 中文正文」；中文过一遍导演核对
   （删舞台说明、章节号、出戏句）；日语交给 GPT-SoVITS api_v2 合成；最后把消息链
   重排成 ``[语音, 文字]``。

作者：露西项目；协议：与露西语音工坊（Lucy Voice Studio）一致。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Plain, Record
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_temp_path,
)

from .lucy import director, gsv, persona, presets, protocol
from .lucy.persona import TRANSLATE_SYSTEM, TRANSLATE_USER
from .lucy.config import PLUGIN_DIR, Settings

PLUGIN_NAME = "露西语音"
STATUS_HELP = (
    "露西语音 · 用法\n"
    "  /露西            看状态\n"
    "  /露西 开｜关      人格 + 语音一起开关\n"
    "  /露西 静音｜出声   只关/开语音（人格仍在）\n"
    "  /露西 念 <文本>    立刻念一句（中日都行）\n"
    "  /露西 情绪 <预设>  设本会话默认情绪：std/calm/happy/excited/soft/quiet/shy\n"
    "  /露西 重启        重启 GPT-SoVITS 推理服务"
)


class LucyVoicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = Settings(config)
        self._state: dict[str, dict] = {}
        self._client = gsv.GSVClient(self.conf)
        self._tmpdir = Path(get_astrbot_temp_path()) / "lucy_voice"
        self._tmpdir.mkdir(parents=True, exist_ok=True)
        self._service = gsv.ServiceManager(self._client, self.conf, log_dir=self._tmpdir)
        self._persona_text = ""
        self._streaming_warned = False
        self._last_error_log = 0.0
        self._online: bool | None = None
        self._warm_task: asyncio.Task | None = None
        self._persona_mode_logged = False

    # ------------------------------------------------------------ 生命周期
    def _autoconfig_weights(self) -> tuple[str, str]:
        """配置里没填权重时，在插件目录 / 数据目录里自动找一套。"""
        if self.conf.gpt_weights and self.conf.sovits_weights:
            return self.conf.gpt_weights, self.conf.sovits_weights
        try:
            data_dir = Path(get_astrbot_data_path())
        except Exception:
            data_dir = None
        dirs = gsv.weight_search_dirs(PLUGIN_DIR, data_dir)
        gpt, sovits = gsv.autodetect_weights(dirs)
        if gpt or sovits:
            self._client.set_weight_paths(gpt, sovits)
            logger.info(
                f"[{PLUGIN_NAME}] 自动找到权重：gpt={Path(gpt).name if gpt else '(无)'} "
                f"sovits={Path(sovits).name if sovits else '(无)'}"
            )
            if not gpt or not sovits:
                logger.warning(f"[{PLUGIN_NAME}] 只找到了一半权重，建议在配置里补齐")
        else:
            logger.info(
                f"[{PLUGIN_NAME}] 没找到权重文件（找过 {len(dirs)} 个目录）；"
                "可以在配置里填 tts.gpt_weights / tts.sovits_weights"
            )
        return gpt, sovits

    async def initialize(self) -> None:
        self._autoconfig_weights()
        self._persona_text = persona.build_cached(
            self.conf.persona_casebook,
            self.conf.persona_voice_lib,
            self.conf.persona_extra,
        )
        logger.info(
            f"[{PLUGIN_NAME}] 人格已装载（{len(self._persona_text)} 字符，"
            f"案例卡={self.conf.persona_casebook}，原话库={self.conf.persona_voice_lib}）"
        )
        try:
            alive = await self._client.health()
            self._online = alive
            if alive:
                logger.info(f"[{PLUGIN_NAME}] 推理服务在线：{self.conf.api_base}")
                if self.conf.set_weights_on_init:
                    await self._client.ensure_weights()
            else:
                logger.warning(
                    f"[{PLUGIN_NAME}] {self.conf.api_base} 上没有检测到 api_v2。"
                    "语音会走兜底（只发文字）；可在配置里打开 auto_start 或手动启动推理服务。"
                )
        except Exception as e:  # 网络问题不该拦住插件加载
            logger.warning(f"[{PLUGIN_NAME}] 初始化检查失败：{e}")

        # 开了 auto_start 就在后台先把推理服务焐热，免得第一条消息等一分钟
        if self.conf.auto_start:
            self._warm_task = asyncio.create_task(self._warmup())

    async def _warmup(self) -> None:
        try:
            ok, reason = await self._service.ensure_ready()
            self._online = ok
            if ok:
                if self.conf.set_weights_on_init:
                    await self._client.ensure_weights()
                # 空跑一句：把 CUDA kernel / JIT 的首次开销吃掉，
                # 否则第一条真实消息要多等 20 秒左右。
                try:
                    warm = await asyncio.wait_for(
                        self._client.synth_once("ん", self.conf.preset, 1.0, "ja"),
                        timeout=180,
                    )
                    logger.info(f"[{PLUGIN_NAME}] 推理已热身（试合成 {len(warm)} B）")
                except Exception as e:
                    logger.info(f"[{PLUGIN_NAME}] 热身合成失败（不影响使用）：{e}")
                logger.info(f"[{PLUGIN_NAME}] 推理服务已预热（{self.conf.api_base}）")
            else:
                logger.warning(f"[{PLUGIN_NAME}] 预热失败：{reason}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[{PLUGIN_NAME}] 预热异常：{e}")

    async def terminate(self) -> None:
        task = getattr(self, "_warm_task", None)
        if task and not task.done():
            task.cancel()
        await self._service.stop()
        await self._client.close()

    # ------------------------------------------------------------ 会话状态
    def _s(self, event: AstrMessageEvent) -> dict:
        umo = event.unified_msg_origin or "default"
        st = self._state.get(umo)
        if st is None:
            st = {
                "on": bool(self.conf.enabled),
                "voice": bool(self.conf.voice_default_on),
                "preset": self.conf.preset,
            }
            self._state[umo] = st
        return st

    def _active(self, event: AstrMessageEvent) -> bool:
        return bool(self.conf.enabled) and bool(self._s(event)["on"])

    def _voice_on(self, event: AstrMessageEvent) -> bool:
        return self._active(event) and bool(self._s(event)["voice"])

    # ------------------------------------------------------------ 人格注入
    REMINDER = (
        "（本会话格式提醒）你就是露西·瓦伦汀，不是通用助手。"
        "这一轮：先写中文正文（3 句以内、约 100 字，会被念出来），"
        "再在正文之后用 <ja>…</ja> 给出同一段话的逐句日语翻译（不增不减、句数数字一致）；"
        "不要提文档/表格/定时提醒这类助手功能，不要自我介绍、不要声明在扮演。"
    )

    @filter.on_llm_request()
    async def inject_persona(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        if not self._active(event):
            return
        if not self.conf.persona_inject:
            return
        try:
            if not self._persona_text:
                self._persona_text = persona.build_cached(
                    self.conf.persona_casebook,
                    self.conf.persona_voice_lib,
                    self.conf.persona_extra,
                )
            base = req.system_prompt or ""
            if persona.has_skill(base):
                # AstrBot 的「人格」里已经放了完整版：只补语音通道，别把 1.5 万字重复一遍
                layer = persona.build_voice_layer_cached(self.conf.persona_extra)
                if not self._persona_mode_logged:
                    self._persona_mode_logged = True
                    logger.info(f"[{PLUGIN_NAME}] 人格来自 AstrBot 人格配置，插件只注入语音协议")
            elif self.conf.persona_inject:
                layer = self._persona_text
                if not self._persona_mode_logged:
                    self._persona_mode_logged = True
                    logger.info(f"[{PLUGIN_NAME}] AstrBot 人格里没有露西，插件注入完整版人格")
            elif self._voice_on(event):
                # 人格交给别处管，但语音协议还是得有，否则模型不会写 <ja>
                layer = persona.build_voice_layer_cached(self.conf.persona_extra)
            else:
                layer = ""
            if layer:
                req.system_prompt = persona.inject_into(base, layer)
            # 会话历史里可能留着「入伙前」的助手口气回复，光靠末尾的人格容易被带跑；
            # 在用户消息后追加一句格式提醒，把最近一次指令压回露西身上。
            if self._voice_on(event):
                try:
                    req.extra_user_content_parts.append(TextPart(text=self.REMINDER))
                except Exception:
                    pass
        except Exception:
            logger.exception(f"[{PLUGIN_NAME}] 人格注入失败")

    # ------------------------------------------------------------ 发消息前：加语音
    @filter.on_decorating_result(priority=20)
    async def add_lucy_voice(self, event: AstrMessageEvent) -> None:
        if not self._active(event):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        if not result.is_model_result():
            return

        plains = [c for c in result.chain if isinstance(c, Plain)]
        if not plains:
            return
        raw = "".join(c.text or "" for c in plains)
        if not raw.strip():
            return

        reply = protocol.split_reply(raw)

        # ---- 导演核对（中文正文）
        zh = reply.zh
        gate = self.conf.director_gate
        if gate != "off":
            try:
                zh, fixes = director.clean(zh)
                if fixes:
                    logger.info(f"[{PLUGIN_NAME}] 导演核对：{'、'.join(fixes)}")
                if gate == "rework":
                    zh = await self._rework(event, zh)
            except Exception:
                logger.exception(f"[{PLUGIN_NAME}] 导演核对失败，按原稿发送")
                zh = reply.zh
        if not (zh or "").strip():
            zh = reply.zh or raw

        # ---- 语音
        audio_path: Path | None = None
        audio_sent = False
        if self._voice_on(event):
            audio_path = await self._speak(event, reply)

        # split 模式：语音先单独发一条，文字照常走管线。
        # 好处是语音发失败也不会连累文字；顺序仍然是「先声音、后文字」。
        if audio_path is not None and self.conf.voice_send_mode == "split":
            try:
                await event.send(
                    event.chain_result([Record.fromFileSystem(str(audio_path))])
                )
                audio_sent = True
            except Exception as e:
                logger.warning(f"[{PLUGIN_NAME}] 语音单独发送失败，改放同一条消息里：{e}")

        # ---- 重排消息链：语音在前，文字在后
        new_chain: list = []
        placed = False
        for comp in result.chain:
            if isinstance(comp, Plain):
                if placed:
                    continue
                if audio_path is not None and not audio_sent:
                    new_chain.append(Record.fromFileSystem(str(audio_path)))
                if self.conf.voice_keep_text or not audio_sent:
                    new_chain.append(Plain(zh))
                placed = True
            else:
                new_chain.append(comp)
        if not placed:
            if audio_path is not None and not audio_sent:
                new_chain.insert(0, Record.fromFileSystem(str(audio_path)))
            if self.conf.voice_keep_text or not audio_sent:
                new_chain.append(Plain(zh))

        result.chain = new_chain
        if self.conf.force_text:
            result.use_t2i_ = False

        if result.result_content_type is not None and not self._streaming_warned:
            try:
                from astrbot.core.message.message_event_result import ResultContentType

                if result.result_content_type == ResultContentType.STREAMING_FINISH:
                    self._streaming_warned = True
                    logger.warning(
                        f"[{PLUGIN_NAME}] 检测到流式输出，语音可能与文字错位；"
                        "建议在 AstrBot 里关闭流式回复。"
                    )
            except Exception:
                pass

    # ------------------------------------------------------------ 合成
    async def _speak(self, event: AstrMessageEvent, reply: protocol.Reply) -> Path | None:
        lang = "ja"
        text = ""
        if reply.ja_ok:
            text = reply.ja
            if self.conf.voice_faithful and not protocol.consistent(reply.zh, reply.ja):
                logger.info("[露西语音] 日语稿像摘要（字数/句数对不上），改用翻译稿")
                translated = await self._translate(event, reply.zh)
                if not translated:
                    logger.info("[露西语音] 翻译失败，这次不出声（宁缺，不许声音和文字对不上）")
                    return None
                text = translated
        else:
            if not self.conf.voice_fallback_zh:
                return None
            if not protocol.speakable(reply.zh):
                logger.info(f"[{PLUGIN_NAME}] 正文不适合朗读（代码/过长/出戏），跳过语音")
                return None
            if self.conf.voice_translate_fallback:
                text = await self._translate(event, reply.zh) or ""
            if not text:
                # 没有日语：用中文正文兜底（音色仍是她，只是发音带口音）
                text = reply.zh
                lang = "zh"
        text = protocol.clip_ja(text, self.conf.voice_max_chars)
        text = (text or "").strip()
        if not text:
            return None

        if not self.conf.voice_emotion_markers:
            text = presets.MARKER_RE.sub("", text)

        key = hashlib.sha1(
            f"{text}|{self.conf.api_base}|{self._s(event)['preset']}".encode("utf-8")
        ).hexdigest()[:16]
        cached = self._tmpdir / f"{key}.wav"
        if cached.exists() and cached.stat().st_size > 1024:
            return cached
        ok, reason = await self._service.ensure_ready()
        if not ok:
            self._online = False
            self._log_error(f"推理服务不可用：{reason}")
            return None
        self._online = True
        if self.conf.set_weights_on_init:
            await self._client.ensure_weights()

        preset_id = self._s(event).get("preset") or self.conf.preset
        try:
            t0 = time.time()
            wav = await asyncio.wait_for(
                self._client.synth_plan(text, preset_id, lang=lang),
                timeout=max(30.0, self.conf.timeout),
            )
            if not wav:
                self._log_error("合成结果为空")
                return None
            cached.write_bytes(wav)
            self._trim_cache()
            logger.info(
                f"[{PLUGIN_NAME}] 合成 {len(text)} 字 [{lang}] {text[:48]!r} / "
                f"{len(wav)} B / {time.time() - t0:.1f}s → {cached.name}"
            )
            return cached
        except asyncio.TimeoutError:
            self._log_error("合成超时")
        except Exception as e:
            self._log_error(f"合成失败：{e}")
        return None

    def _log_error(self, message: str) -> None:
        now = time.time()
        if now - self._last_error_log > 30:
            self._last_error_log = now
            logger.warning(f"[{PLUGIN_NAME}] {message}（30 秒内同类错误不重复打印）")

    def _trim_cache(self, keep: int = 300) -> None:
        """合成缓存别无限长——超过 300 条就删最旧的。"""
        try:
            files = sorted(
                (f for f in self._tmpdir.glob("*.wav") if f.is_file()),
                key=lambda f: f.stat().st_mtime,
            )
            for f in files[:-keep]:
                f.unlink(missing_ok=True)
        except Exception:
            pass

    async def _translate(self, event: AstrMessageEvent, zh: str) -> str:
        """把中文正文翻成露西腔的日语（只给语音用，不改变发出去的文字）。"""
        zh = (zh or "").strip()
        if not zh:
            return ""
        try:
            provider = None
            getter = getattr(self.context, "get_using_provider_async", None)
            if getter:
                provider = await getter(event.unified_msg_origin)
            if provider is None:
                provider = self.context.get_using_provider()
            if provider is None:
                return ""
            resp = await asyncio.wait_for(
                provider.text_chat(
                    prompt=TRANSLATE_USER.format(zh=zh),
                    system_prompt=TRANSLATE_SYSTEM,
                    contexts=[],
                ),
                timeout=45,
            )
            out = (getattr(resp, "completion_text", "") or "").strip()
            out = protocol.sanitize_ja(out)
            out = out.strip("「」\"' ")
            if not protocol.has_ja_kana(out):
                return ""
            return out
        except Exception as e:
            logger.warning(f"[{PLUGIN_NAME}] 翻译失败：{e}")
            return ""

    async def _rework(self, event: AstrMessageEvent, zh: str) -> str:
        """导演第二遍：让 LLM 按导演本删改（配置 director.gate=rework 时启用）。"""
        if not zh.strip():
            return zh
        try:
            provider = None
            getter = getattr(self.context, "get_using_provider_async", None)
            if getter:
                provider = await getter(event.unified_msg_origin)
            if provider is None:
                provider = self.context.get_using_provider()
            if provider is None:
                return zh
            system, user = director.rework_prompt(zh)
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=user, system_prompt=system, contexts=[]),
                timeout=60,
            )
            new = (getattr(resp, "completion_text", "") or "").strip()
            if not new:
                return zh
            new, _ = director.clean(new)
            if len(new) < max(8, len(zh) * 0.4):
                logger.warning(f"[{PLUGIN_NAME}] 导演二遍结果过短，已丢弃")
                return zh
            return new
        except Exception as e:
            logger.warning(f"[{PLUGIN_NAME}] 导演二遍失败：{e}")
            return zh

    # ------------------------------------------------------------ 命令
    @filter.command("露西", alias={"lucy", "露西语音"})
    async def lucy_cmd(self, event: AstrMessageEvent):
        """露西语音：状态 / 开关 / 试听 / 情绪 / 重启"""
        parts = re.split(r"\s+", (event.message_str or "").strip())
        # 去掉命令词本身
        args = [p for p in parts[1:] if p]
        st = self._s(event)
        sub = args[0] if args else ""

        if sub in ("", "状态", "help", "帮助", "?"):
            yield event.plain_result(self._status_text(event))
            return

        if sub in ("开", "打开", "on", "启用"):
            st["on"] = True
            st["voice"] = True
            yield event.plain_result("露西回来了。…欢迎回来，主人。")
            return

        if sub in ("关", "关闭", "off", "停用"):
            st["on"] = False
            yield event.plain_result("……那露西先退下了。主人有事，再叫露西。")
            return

        if sub in ("静音", "安静", "mute"):
            st["voice"] = False
            yield event.plain_result("……好。露西不出声了，写给您看。")
            return

        if sub in ("出声", "说话", "unmute"):
            st["voice"] = True
            yield event.plain_result("……嗯。露西在的，主人。")
            return

        if sub in ("念", "说", "试听", "tts"):
            text = " ".join(args[1:]).strip()
            if not text:
                yield event.plain_result("要给露西一句话才能念——例如：/露西 念 おかえりなさい、マスター")
                return
            reply = protocol.Reply(ja=text, zh="", raw=text, had_tag=True)
            if not protocol.has_ja_kana(text):
                reply = protocol.Reply(ja="", zh=text, raw=text, had_tag=False)
            path = await self._speak(event, reply)
            if path is None:
                yield event.plain_result("……喉咙不太舒服，念不出来。主人先看字吧。")
                return
            yield event.chain_result([Record.fromFileSystem(str(path))])
            return

        if sub in ("情绪", "预设", "preset"):
            if len(args) < 2:
                yield event.plain_result(
                    "现在的情绪是「" + presets.get_preset(st["preset"])["zh"] + "」。"
                    "可选：" + "、".join(f"{p['id']}({p['zh']})" for p in presets.PRESETS)
                )
                return
            asked = args[1].strip().lower()
            matched = presets.PRESET_BY_ID.get(asked)
            if matched is None:
                for p in presets.PRESETS:
                    if asked in [m.lower() for m in p["markers"]] or asked == p["zh"]:
                        matched = p
                        break
            if matched is None:
                yield event.plain_result("露西不认识这个情绪…可选：" + "、".join(presets.preset_ids()))
                return
            st["preset"] = matched["id"]
            yield event.plain_result(f"……好。露西会用「{matched['zh']}」的声音说话。")
            return

        if sub in ("重启", "restart"):
            yield event.plain_result("露西去把喉咙重新打开…稍等一下。")
            await self._service.stop()
            ok, reason = await self._service.ensure_ready()
            if ok:
                if self.conf.set_weights_on_init:
                    await self._client.ensure_weights(force=True)
                yield event.plain_result("……好了。露西可以说话了。")
            else:
                yield event.plain_result(f"……还是不行。{reason}")
            return

        if sub in ("清缓存", "重置"):
            removed = 0
            for f in self._tmpdir.glob("*.wav"):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
            yield event.plain_result(f"清掉了 {removed} 段旧声音。")
            return

        # 认不出来的子命令：不抢话，交回给模型当普通聊天处理。
        # （群里「@露西 露西 今天回来得真晚」这种会被指令过滤器误命中，这里兜住。）
        logger.info(f"[{PLUGIN_NAME}] 未识别的子命令 {sub!r}，交回模型处理")
        return

    def _status_text(self, event: AstrMessageEvent) -> str:
        st = self._s(event)
        preset = presets.get_preset(st["preset"])
        online = {True: "在线", False: "没连上", None: "未探测"}[self._online]
        return (
            f"{STATUS_HELP}\n"
            f"────\n"
            f"当前：人格 {'开' if st['on'] else '关'} · "
            f"语音 {'开' if st['voice'] else '静音'} · "
            f"情绪「{preset['zh']}」\n"
            f"推理服务：{self.conf.api_base}（{online}）"
        )
