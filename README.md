# 露西语音 · AstrBot 插件

> 把《露西 -她所期望的一切-》的女主角 **露西（PIM-001）** 装进 AstrBot：
> QQ 里她先用**自己训练的音色**说一句日语，再跟上同一句话的中文。
> 人格用**完整版 SKILL（含导演核对）**，语音走 **GPT-SoVITS v5turbo** 的本地推理。

```
主人：今天回来得真晚，饭都凉了吧。

露西：🔊「……お帰りなさいませ、マスター。ご飯はまだ温かいですよ。」
      凉了……露西摸过锅子，还有三十几度。现在三点二十六分，露西去热一下，八分钟就好。
```

语音和文字是**同一句话**：先中文正文，再附 `<ja>` 逐句日语翻译；插件拿翻译去合成，
所以「听到的」就是「看到的」。

---

## 语音示例

> 都是**真机跑出来的**（本机 GPT-SoVITS v5turbo + e8 LoRA + e10 GPT）。

| # | 场景 | 念出来的（日语） | 屏幕上的（中文） | 下载 |
|---|---|---|---|---|
| 01 | 迎接 | おかえりなさいませ、マスター。ご飯はまだ温かいです。 | ……主人回来了。饭还温着。 | 

https://github.com/user-attachments/assets/c160d071-7400-4a65-ba0f-eab3426ae78e


| 02 | 完整一轮 | マスターが戻りました。ご飯はまだ温かいまま、ルーシーがずっと一番奥の段に入れておきました。 | ……主人回来了。饭还温着的，露西一直搁在最里面那一格。 

https://github.com/user-attachments/assets/3c4f68a7-e420-4f49-a9e9-f6a8818a8478


| 03 | 自报家门 | ルーシー・ヴァレンタインです。サンプル名はこれで、PIM-001。 | 露西·瓦伦汀。样品名称就是这个，PIM-001。 |

https://github.com/user-attachments/assets/c3e8d05e-af33-4bfe-9f6e-b10ba13bdc30


| 04 | 情绪 [开心] | 初めてマスターに褒めてもらえました。嬉しい！ | 第一次被主人夸了。好开心！ | 

https://github.com/user-attachments/assets/f0a5d472-e7bd-4599-80eb-1df30e2a2b37


| 05 | 情绪 [温柔]+[停:300] | ……そこにいてください。ルーシー、ご飯を温めてきますね。 | ……请待在那里。露西去把饭热一下。 | 

https://github.com/user-attachments/assets/e4df95f1-de80-4875-9bc7-07deace60d70


| 06 | 中文兜底 | —— | 主人，饭已经做好了。 | 

https://github.com/user-attachments/assets/5f7b4f2d-da62-4c97-80a6-890835c2cbdc





第 06 条是「模型没写 `<ja>` 时」的兜底：还是她的音色，但中文发音带口音——
这正是这个插件坚持让模型写**日语朗读稿**的原因。

---

## 目录

- [语音示例](#语音示例)
- [一、它做了什么](#一它做了什么)
- [二、安装](#二安装)
- [三、依赖](#三依赖)
- [四、配置](#四配置)
- [五、指令](#五指令)
- [六、工作原理](#六工作原理)
- [七、自检与排错](#七自检与排错)
- [八、发行包](#八发行包)
- [九、许可与致谢](#九许可与致谢)

---

## 一、它做了什么

| 环节 | 做法 |
|---|---|
| **人格** | 完整版 `SKILL.md`（含「交付前自检」＝导演核验默认开启）＋ 导演本 `director.md`；可以放在 AstrBot 的「人格」里，也可以由插件注入 |
| **双通道** | 提示词要求模型先写中文正文（3 句内、约 100 字，因为要念），再用 `<ja>…</ja>` 给出同一段话的逐句日语翻译 |
| **台词核对** | ① 导演本：删舞台说明、章节号、出戏词（原文/设定/材料…）；② 字数/句数比——日语像摘要就自动改走翻译稿，保证「念的就是屏幕上的字」 |
| **语音** | 日语稿 → GPT-SoVITS `api_v2`（v5turbo 底模 + 音色 LoRA + GPT 权重）→ 48 kHz WAV；7 套情绪预设、`[停:400]` 之类标记 |
| **发送** | 语音单独一条先发、文字随后（`split`），或同一条消息里 `[语音, 文字]`（`chain`）；顺带关掉「文字转图片」 |
| **出错** | 合成失败/超时只发文字；模型被历史带跑去当助手时不出声（不再出现「中文语音」） |

## 二、安装

### A. 整合包（推荐，含安装器）

| 包 | 大小 | 含权重 | 适合 |
|---|---|---|---|
| `lucy-astrbot-1.0.0-full.zip` | ~200 MB | ✅ | **解压即用**：权重就放在插件目录里 |
| `lucy-astrbot-1.0.0.zip` | ~4 MB | ❌ | 已经有权重 / 走 `tools/fetch-weights.py` 下载 |

1. 从 [Releases](https://github.com/dhies23/astrbot-lucy-voice/releases/latest) 下载并解压
2. 双击 `install-lucy-astrbot.cmd`，按提示填 WebUI 密码

安装器会：找数据目录 → 合并插件配置（保留你改过的项）→ 装插件（运行中走 WebUI 热装）→
**把权重放进插件目录并写进配置** → 写「露西」人格并设为默认 → 自检。

> **权重自动扫描**：插件启动时会在 `插件目录/weights/`、`插件数据目录/weights/`、
> `AstrBot数据目录/weights/` 里找 `*.ckpt`（GPT）和 `*.pth`（SoVITS），
> 按文件名里的 `v5turbo / e10 / e8` 打分挑最合适的（e8 优于 e1）。
> 所以**只要把两个权重丢进插件目录的 `weights/`，配置里什么都不填也能出声**——
> 日志会写 `[露西语音] 自动找到权重：gpt=… sovits=…`。

### B. 手动安装

```bash
# 1. 插件
git clone https://github.com/<you>/astrbot-lucy-voice.git
cp -r astrbot-lucy-voice/astrbot-plugin-lucy-voice  ~/.astrbot/data/plugins/astrbot_plugin_lucy_voice

# 2. 配置（把权重路径改成你自己的）
cp docs/config.example.json ~/.astrbot/data/config/astrbot_plugin_lucy_voice_config.json

# 3. 人格（可选，AstrBot 在运行时）
python tools/setup_astrbot_persona.py --password <WebUI密码>

# 4. 重载插件 / 重启 AstrBot
```

## 三、依赖

| 项 | 说明 |
|---|---|
| **AstrBot** | ≥ 4.5（在桌面端 4.29.4 / core 4.29.4 上验证）。插件本身只用标准库 + `aiohttp`（AstrBot 已自带） |
| **Python** | 安装器需要 Python 3.10+（AstrBot 自带的 `backend/python` 也行） |
| **GPT-SoVITS** | v5turbo 推理环境，含 `api_v2.py`（本插件与 [露西语音工坊](https://github.com/) 共用同一套接口） |
| **露西三件套权重** | 底模 `s2Gv5turbo.pth`（GPT-SoVITS 自带）；音色 LoRA `lucy_v1_v5turbo_e8_s14528_l8.pth`（63.8 MB）与 GPT(s1) `lucy_v1_v5turbo-e10.ckpt`（148.1 MB）→ 完整版整合包已内含，或从 [Release](https://github.com/dhies23/astrbot-lucy-voice/releases/latest) 单独下载 / `python tools/fetch-weights.py` |
| **参考音频** | 插件已内置 7 条（`assets/refs/*.wav`），无需另外准备 |
| **ffmpeg** | 只有 QQ 官方机器人（`qq_official`）发语音时需要（wav→silk），AstrBot 会调用 |

> 权重是训练产物（合计 213 MB），**不进 git**，挂在 Release 上：
> 两个文件都带 SHA-256，`python tools/fetch-weights.py --dest ./weights` 会下载并校验。
> 详细的来历、训练口径、加载验证见 [`docs/权重说明.md`](docs/权重说明.md)。

## 四、配置

WebUI → 插件管理 → 露西语音，或直接改
`data/config/astrbot_plugin_lucy_voice_config.json`。

**必填**

| 键 | 说明 |
|---|---|
| `tts.gpt_weights` | `lucy_v1_v5turbo-e10.ckpt` 绝对路径 |
| `tts.sovits_weights` | `lucy_v1_v5turbo_e8_s14528_l8.pth` 绝对路径 |
| `tts.api_base` | 默认 `http://127.0.0.1:9880` |

**常用**

| 键 | 默认 | 说明 |
|---|---|---|
| `tts.auto_start` | `false` | 9880 没起来时用 `gsv_root` 里的 `api_v2.py` 拉一个（会占显存） |
| `tts.gsv_root` | 空 | `api_v2.py` 所在目录；开了 `auto_start` 就必填 |
| `voice.send_mode` | `split` | `split`＝语音单独一条先发；`chain`＝同一条消息里 |
| `voice.max_ja_chars` | `200` | 日语稿字数上限（正文应和它差不多长） |
| `voice.faithful` | `true` | 日语必须是正文的翻译，像摘要就改用翻译稿 |
| `voice.translate_fallback` | `true` | 模型没写 `<ja>` 时自动把正文翻成日语再念 |
| `voice.emotion_markers` | `true` | 允许 `[温柔]` `[停:300]` 这类标记 |
| `director.gate` | `clean` | `off` / `clean`（删舞台说明、出戏句）/ `rework`（再让 LLM 过一遍导演本） |
| `persona.inject` | `true` | AstrBot 人格里没有露西时，由插件注入完整版 |

完整 schema 见 [`_conf_schema.json`](astrbot-plugin-lucy-voice/_conf_schema.json)。

## 五、指令

| 指令 | 作用 |
|---|---|
| `/露西`、`/露西语音`、`/lucy` | 状态（人格/语音/情绪、推理服务是否在线） |
| `/露西 开` / `/露西 关` | 人格 + 语音一起开关（按会话记） |
| `/露西 静音` / `/露西 出声` | 只关/开语音 |
| `/露西 念 おかえりなさい` | 立刻念一句（中日都行） |
| `/露西 情绪 温柔` | `std/calm/happy/excited/soft/quiet/shy`，也认中文 |
| `/露西 重启` | 重启 GPT-SoVITS 推理服务 |
| `/露西 清缓存` | 清合成缓存 |

**群聊里怎么叫她**：@她 直接说话；或引用她某条消息；或以 `/` 开头（不 @ 也行）。
不加 @、不引用、也没有 `/` 的群消息她不会接话（AstrBot 的唤醒规则）。

## 六、工作原理

```
用户消息 ──► on_llm_request ──► system_prompt
                              = AstrBot 人格(完整 SKILL + 导演本)
                              + 语音协议（先中文正文，再 <ja> 逐句翻译）
                              + 每轮一句格式提醒
        ──► 模型输出：「中文正文 + <ja>日语</ja>」
        ──► on_decorating_result
              ├─ 拆出 zh / ja
              ├─ 导演核对（舞台说明、章节号、出戏句）
              ├─ 一致性检查（字数比 / 句数差）→ 不合格就翻译一次
              ├─ GPT-SoVITS /tts 合成（情绪预设 + [标记]）
              └─ 消息链改写成 [语音] + [文字]
        ──► 先语音、后文字
```

**为什么分成两层人格**：`persona/SKILL.md` 约 1.5 万字，塞进 AstrBot 的「人格」后
WebUI 能看见、能切、能备份；插件检测到 `<!--LUCY-SKILL-->` 标记就只补语音协议，
不会把同一段话注入两遍。没配 AstrBot 人格时，插件自己注入完整版。

**为什么日语**：游戏原声是日语配音，用日语念才是她本来的声音；中文由模型写，
只作为文字。两段必须**语义一致**——这就是 `voice.faithful` 与 `consistent()` 的来历。

更细的设计与取舍见 [`docs/设计说明.md`](docs/设计说明.md)，改代码/发版见 [`docs/发布流程.md`](docs/发布流程.md)。

## 七、自检与排错

```bash
# 纯本地（不需要 AstrBot 在跑）
python tests/test_lucy_plugin.py        # 59 项：协议解析 / 导演核对 / 情绪 / 音频 / 钩子
python tests/test_installed.py          # 按 AstrBot 真实加载方式验已安装插件
python tests/test_poke_integration.py   # 戳一戳插件的平台门槛与触发
```

| 现象 | 处理 |
|---|---|
| 只有文字没有语音 | 9880 没起来：看 `data/temp/lucy_voice/lucy_tts_api.log`；或打开 `auto_start` |
| 语音是中文腔 | 模型没写 `<ja>`；看日志有没有 `[ja]`，`translate_fallback` 打开会自动翻译 |
| 声音和文字对不上 | 正常不会（`faithful` 会拦）；把它那一轮日志里 `合成 … [ja] '…'` 那行发出来 |
| 声音不像 / 时长翻倍 | 权重加载错了：yaml 里必须是**底模**，LoRA 走 `/set_sovits_weights` |
| 语音和文字错位 | 关掉 AstrBot 的流式回复 |
| 长回复变图片 | `reply.force_text` 保持打开（默认已开） |
| 群里不理人 | 没 @、没引用、也没 `/`；或白名单里没有这个群 |

## 八、发行包

都挂在 [**Releases**](https://github.com/dhies23/astrbot-lucy-voice/releases/latest)：

| 文件 | 内容 |
|---|---|
| `lucy-astrbot-1.0.0-full.zip`（~200 MB） | **完整版**整合包：插件 + **语音权重** + 安装器 + 人格脚本 + 试听 + 校验 |
| `lucy-astrbot-1.0.0.zip`（3.9 MB） | 精简包：同上但不含权重 |
| `astrbot-plugin-lucy-voice-1.0.0.zip`（1.8 MB） | 插件单包，可直接 WebUI「从文件安装」 |
| `lucy_v1_v5turbo_e8_s14528_l8.pth`（63.8 MB） | 音色 LoRA（SoVITS v5turbo, rank 8） |
| `lucy_v1_v5turbo-e10.ckpt`（148.1 MB） | GPT(s1)（Text2Semantic, epoch 10） |

试听放在仓库内 [`docs/demo/`](docs/demo)，不用下整包就能听。

重新打包：`python build-release.py`（生成到 `dist/`，该目录不进 git）。

## 九、许可与致谢

- **代码**：MIT（见 [LICENSE](LICENSE)）
- **人格文本**（`persona/SKILL.md`、`director.md`、`casebook.md`、`voice.md`）：
  由本项目蒸馏整理，随仓库提供，仅供个人扮演使用
- **参考音频**（`astrbot-plugin-lucy-voice/assets/refs/*.wav`）与**角色设定**：
  版权归 **M-Vizlab**（《露西 -她所期望的一切-》）。这里仅用于本地音色克隆，
  **请勿商用或二次分发**；如权利人要求，会立即移除
- **依赖项目**：[AstrBot](https://github.com/AstrBotDevs/AstrBot)、
  [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)、
  [astrbot_plugin_poke_to_llm](https://github.com/muyouzhi6/astrbot_plugin_poke_to_llm)（戳一戳可选）
