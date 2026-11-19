# 露西语音（astrbot_plugin_lucy_voice）

> 把「露西 SKILL（完整版，含导演核对）」装进 AstrBot，并让她的每条回复都先用**日语配音**说出来，
> 再跟一段**中文文字**。
>
> QQ 里的顺序是固定的：**先语音 → 再文字**。

```
主人：今天回来得真晚。

露西：🔊「……お帰りが遅かったですね。ご飯はまだ温かいです。」   ← 语音（日语，露西本人音色）
      ……回来得真晚。饭还温着，露西一直用小火煨着。              ← 文字（中文，同一条消息里跟着）
```

---

## 一、它做了什么

| 环节 | 做法 |
|---|---|
| **人格** | `on_llm_request` 把**完整版 SKILL.md**（含「交付前自检」＝导演核验默认开启）＋ **导演本** `director.md` 叠进 system prompt |
| **双通道** | 提示词要求模型**先写中文正文**（3 句内、约 100 字），再在正文后写 `<ja>…</ja>`——同一段话的**逐句日语翻译** |
| **台词核对** | ①导演本：删舞台说明、删章节号、丢掉含出戏词（原文/设定/材料…）的句子；②字数/句数比——日语稿像摘要就改用翻译稿，保证**声音念的就是屏幕上的字** |
| **语音** | 日语稿交给 GPT-SoVITS `api_v2` 合成（v5turbo 底模 + e8 LoRA + e10 GPT），7 套情绪、`[停:400]` 之类标记 |
| **发送** | `on_decorating_result`：先把语音单独发一条、文字照常走管线（默认 `split`），或把消息链排成 `[语音, 文字]`（`chain`）；顺带强制关掉「文字转图片」 |

人格只改 system prompt，不动 AstrBot 里的人设配置；语音只在 `LLM 结果` 上触发，命令回话不会被念。
模型如果按人格规矩「退出角色」（主人说别演了），就不会写 `<ja>`，插件也不会给代码/长文配音。

## 二、依赖

1. **AstrBot** ≥ 4.5（本项目在桌面端 4.29.4 / core 4.29.4 上验证）。
2. **GPT-SoVITS v5turbo** 推理环境（含 `api_v2.py`），以及露西的三件套权重：

   | 角色 | 文件 | 说明 |
   |---|---|---|
   | 底模 | `GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth` | 整合包自带 |
   | 音色 LoRA | `lucy_v1_v5turbo_e8_s14528_l8.pth` | `/set_sovits_weights` 加载 |
   | GPT(s1) | `lucy_v1_v5turbo-e10.ckpt` | `/set_gpt_weights` 加载 |

   > **别把 LoRA 路径写进 yaml 的 `vits_weights_path`**——会走错加载分支、产出残模型。
   > 插件自己生成的 yaml 只写底模，LoRA/GPT 一律走 `/set_*_weights`。

3. **参考音频**已随插件带好（`assets/refs/*.wav`，官方日配 7 条），不需要另外准备。

## 三、安装

### 3.1 直接拷贝（推荐）

把整个 `astrbot_plugin_lucy_voice/` 目录放进 AstrBot 的插件目录：

| 运行方式 | 插件目录 |
|---|---|
| 桌面端（打包运行时） | `C:\Users\<你>\.astrbot\data\plugins\` |
| 源码/CLI | `<AstrBot 根目录>\data\plugins\` |

然后在 WebUI「插件管理」里**重载插件**（或重启 AstrBot）。

配置文件落在 `data/config/astrbot_plugin_lucy_voice_config.json`，也可在 WebUI 里改。

### 3.2 zip 安装

`dist/astrbot-plugin-lucy-voice-1.0.0.zip` → WebUI 插件页「从文件安装」。

## 四、必填配置

| 键 | 必填 | 说明 |
|---|---|---|
| `tts.api_base` | ✅ | 默认 `http://127.0.0.1:9880` |
| `tts.gpt_weights` | ✅ | `lucy_v1_v5turbo-e10.ckpt` 的**绝对路径** |
| `tts.sovits_weights` | ✅ | `lucy_v1_v5turbo_e8_s14528_l8.pth` 的**绝对路径** |
| `voice.send_mode` | ⬜ | `split`（默认，语音一条、文字一条）/ `chain`（同一条消息里） |
| `tts.auto_start` | ⬜ | 9880 没起来时自动用 `gsv_root` 里的 `api_v2.py` 拉一个（占显存） |
| `tts.gsv_root` | ⬜ | `auto_start` 打开时必填，例：`K:\gptsovits\GPT-SoVITS-v5-…\GPT-SoVITS-v5-…` |

其余默认即可。若你已经在用**露西语音工坊**（8760），9880 大概率已经起着、权重也切好了，
这时可以关掉 `set_weights_on_init`，让工坊独占管理。

## 四之二、人格放在哪（两种用法都支持）

| 用法 | 做法 | 插件行为 |
|---|---|---|
| **A 推荐：写在 AstrBot 人格里** | 跑 `python tools/setup_astrbot_persona.py --password <WebUI 密码>`：创建人格 `lucy`（完整版 SKILL + 导演本，带 `<!--LUCY-SKILL-->` 标记）、设为默认人格、附带两段定调对白和一句「出错时的台词」 | 检测到标记 → 只注入语音协议，**不重复**那 1.5 万字 |
| B 全交给插件 | AstrBot 人格保持 default/空 | 插件每轮注入完整版人格 + 语音协议 |

切回去：WebUI「人格」里把默认人格改回 `default` 即可（插件会自动回到用法 B）。
备份/迁移：`dist/lucy-persona-astrbot.json`（含 system_prompt、begin_dialogs、出错台词）。

## 五、命令

| 命令 | 作用 |
|---|---|
| `/露西` | 看状态与帮助 |
| `/露西 开` / `/露西 关` | 人格 + 语音一起开关 |
| `/露西 静音` / `/露西 出声` | 只关/开语音（人格照旧） |
| `/露西 念 おかえりなさい、マスター` | 立刻念一句（中文也行，会自动切语种） |
| `/露西 情绪 温柔` | 本会话默认情绪：`std/calm/happy/excited/soft/quiet/shy` |
| `/露西 重启` | 重启推理服务（改完权重不用重启 AstrBot） |
| `/露西 清缓存` | 清掉合成缓存 |

## 六、和别的 TTS 插件的关系

**建议关掉 `astrbot_plugin_GPT_SoVITS`**（或至少把它的 `auto.tts_prob` 调成 0）。
它会在 `on_decorating_result` 里把整条消息换成语音（只剩声音没有字），和本插件抢同一个 api。

本插件优先级 20，会先跑；跑完链里已经有 `Record`，那个插件的「只含 Plain 才处理」检查会跳过它。
但为了不留隐患，还是建议停用。

## 七、排错

| 现象 | 原因 / 处理 |
|---|---|
| 只有文字没有语音 | 9880 没起 → 看 `data/temp/lucy_voice/lucy_tts_api.log`；或打开 `auto_start` |
| 语音是中文腔 | 模型没写 `<ja>`，走了中文兜底。检查人格是否注入（`/露西` 状态）、模型是否支持长中文指令 |
| 文字里出现 `<ja>` | 模型写法太野 · 已尽力兼容；遇到新的写法改 `lucy/protocol.py` 的正则即可 |
| 声音不像 / 时长翻倍 | 权重加载错了：确认 yaml 里是**底模**，LoRA 走 `/set_sovits_weights` |
| 语音和文字错位 | AstrBot 开了流式输出 → 关掉流式回复 |
| 长回复变成图片 | `reply.force_text` 打开（默认已开） |
| QQ 里只有文字、语音发不出 | QQ 官方机器人（qq_official）需要该机器人有**语音消息**权限；本机已验证 wav→腾讯 silk 编码可用（`SILK_V3`），发不出就是平台权限或适配器问题。换 NapCat（aiocqhttp）最稳 |
| 每轮 token 消耗高 | 人格约 1.7 万字符（≈1.2–1.6 万 token）/轮，这是「完整版」的代价；可关 `persona.inject` 或换轻量人设 |

## 八、目录

```
main.py              插件主体：注入人格 / 重排消息链 / 命令
_conf_schema.json    WebUI 配置面板
metadata.yaml
lucy/
  config.py          配置摊平
  persona.py         人格组装（SKILL + 导演本 + 语音协议）
  protocol.py        拆 <ja>/中文、清洗、截断
  director.py        导演核对（出戏词/章节号/舞台说明）
  presets.py         7 套情绪 + [标记] 语法
  gsv.py             api_v2 客户端 + 推理服务管理
  audio.py           WAV 拼接/静音/归一化
persona/
  SKILL.md           完整版人格（含交付前自检）
  director.md        导演本
  casebook.md        案例卡（默认不注入）
  voice.md           原话库（默认不注入）
assets/refs/*.wav    7 条官方日配参考音频
```

## 九、许可与出处

* 人格与语音：露西项目（《露西 -她所期望的一切-》，角色与配音版权归 M-Vizlab）。
* 插件代码：随项目自用，按需修改。
