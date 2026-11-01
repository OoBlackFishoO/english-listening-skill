---
name: english-listening
description: 把任意英语音频做成可上线的网站听力填空练习（转写→按标点断句→逐句补中文→导出练习包→插入卡片），也负责给已有练习包补译文。适用于「做听力练习包、这段音频做成听力练习、转写这段听力、真题上线、出题、导出听力练习、听力练习加翻译、data.js 补 zh、英语听力中文对照」等请求。
---

# 英语听力 · 出题到上线

一条流程走完：音频 → 断句 → 译文 → 练习包 → 卡片 → 上线。
模板、脚本、规范都在本 skill 内，**唯一真源就是这里**。

## 先判断走哪条路

| 请求 | 走 |
|---|---|
| 有一段新音频，要做成练习 | **A 全流程**（下面 1–7 步） |
| 已有练习包缺中文 / 要换译文 | **B 只补译文**，不重跑转写 |

## 配置与自检

skill 目录下的 `config.json`（不入库）记录本机路径与品牌，字段都可省略：

```json
{
  "python": "<装了 whisper 的 python.exe>",
  "site": "<站点仓库根>",
  "work": "",
  "brand": {
    "name": "我的小站",
    "copyright": "© 2026 Your Name",
    "links": [{ "label": "GitHub", "url": "https://github.com/you" }]
  }
}
```

优先级：**命令行参数 > 环境变量（`LISTEN_SITE` / `LISTEN_WORK`）> config.json > 自动探测**。
在站点仓库目录下运行时，`site` 会靠 `english/listening.html` 自动认出，可以不配。
`brand` 全部可省——省了就用中性默认（站名「我的站点」，无版权行、无 footer 链接）。

```powershell
$SK = "$env:USERPROFILE\.trae-cn\skills\english-listening"
$PY = (Get-Content "$SK\config.json" -Raw -Encoding UTF8 | ConvertFrom-Json).python
$MK = "$SK\scripts\make.py"
& $PY $MK doctor        # 模板 / torch+cuda / whisper / ffmpeg / 站点 / 解释器
```

`python` 必须是装了 `openai-whisper` + `imageio-ffmpeg` 的解释器（`pip install openai-whisper imageio-ffmpeg`）。
Whisper 模型缓存在 `%USERPROFILE%\.cache\whisper`，首次用某个模型会自动下载（`small.en` 约 480MB）。

中间产物默认 `~/.cache/listening-work/<slug>/`，可用 `--work` 覆盖。

## 站点侧前提

- 练习包放 `english/listening/<slug>/`，只含 `index.html`、`audio.mp3`、`data.js`。
- **目录深度是硬约束**：模板里写死 `../../../css/style.css`，放错层级就没样式。
- 站点还需要 `css/style.css`、`js/clay.js`、`favicon.svg`，以及 `english/listening.html` 列表页
  （`publish` 靠它插卡片）。这三样资源和一个空列表页都能由 `export --sync-kit` 自动补齐，
  **已存在的文件不覆盖**。新建站点时第一次 export 带上就行。

## A 全流程

```powershell
& $PY $MK transcribe 音频.mp3 --slug cet6-x --title "2025.12 六级听力 · 第 3 套"
& $PY $MK resegment cet6-x
& $PY $MK zh cet6-x --dump
# … 翻译，写成 {"0":"译文","3":"译文"} 的临时 JSON …
& $PY $MK zh cet6-x --inject zh.json
& $PY $MK export cet6-x --dest "<站点根>\english\listening\cet6-x"
& $PY $MK publish cet6-x
```

1. **transcribe**：GPU 自动启用 fp16，30 秒音频约 10 秒。`--model` 换模型（默认 `small.en`）。
2. **resegment**：按句末标点重组，输出 `sents.json`（`zh` 为空）。
3. **zh --dump**：列待译句子，写 `zh_todo.json`。
4. **翻译**（由你来做，不机翻）：每批 48 句，按《翻译规范》逐句给，宁可短译不许并句。
   长材料用 `--inject` 分批合并；纯文本一行一句可用 `--auto zh.txt`（条数必须相等）。
5. **export**：压 64k 单声道 mp3、生成 `data.js`、把 `assets/exercise_template.html` 的占位符
   （`{{SITE_NAME}}` / `{{FOOTER_LINKS}}` / `{{COPYRIGHT_LINE}}`）按 `brand` 渲染成 `index.html`，
   末尾自动 `check`。`--brand "站名"` 可临时覆盖站名；`--sync-kit` 给缺资源的站点补 css/js/favicon。
   导出目录不在站点 `english/listening/` 下时会警告样式失效。
6. **check 不通过就回 `sents.json` 改，重跑 export**，不要带缺译上线（`--force` 只在用户明确要求时用）。
7. **publish**：往 `english/listening.html` 插入卡片（置顶、自动轮换配色、重排交错延迟、幂等——同 slug 重复执行是替换不是追加）。`--print` 只看不改。

最后提醒用户：**git add / commit / push 才真正上线**（不要主动提交，除非用户要求）。

## B 只补译文

```powershell
$ZH = "$SK\scripts\zh_tool.py"
& $PY $ZH dump   "<站点根>\english\listening\cet6-x\data.js" src.txt
& $PY $ZH inject <data.js> <zh目录>     # zh_0.json, zh_1.json … 纯字符串数组
& $PY $ZH verify <data.js> src.txt
```

三条红线：**只写 `zh`**；一句对一句（条数 = 展平总句数）；`text`/`words[]`/断句/句序一个字节都不动。
改英文等于挖空和跟听全盘错位。

注意：网站上补的译文不会回流到中间产物。要长期保留，回 `sents.json` 补再 `export`。

## 铁律

- 断句只认句末标点 `. ? !`，不认 Whisper 的静音分段。`resegment` 已实现，不要手改句子边界。
- 材料边界只认 `Questions / Section / Conversation / Passage / Recording` 开头的句子，否则两段材料会被粘成一段。
- 不挖空。填空由练习页动态生成，密度和方式由访客自己调。
- `data.js` 格式固定 `window.__EXERCISE__ = <紧凑 JSON>;\n`，前缀不能变。
- 模板 `assets/exercise_template.html` 是**带占位符的源文件**，导出时才渲染成页面。
  线上已有的包是渲染产物，与模板不要求字节一致——不要为了"对齐"去覆盖线上包。
- 站点主题在 `assets/site-kit/` 有一份副本（style.css / clay.js / favicon.svg），
  用于给新站点补资源；它可能与站点线上版本不同步，以站点仓库为准。

## 翻译规范

- 口语对话**译意不译字**，单句一般 ≤ 35 字，不逐词硬译。
- 数字单位中文化：`$3,000` → 3000 美元，`2.5 billion` → 25 亿。
- 专名全篇统一：人名地名先定一次译法，之后整篇沿用；`B&B` → 民宿（B&B），期刊用《》。
- 引语用中文引号“”，避免 JSON 转义。
- 被 Whisper 切断的残句照译：前半句用省略号，后半句当续写。
- 题干与「问题 N。」逐条照译，题号保留阿拉伯数字。

## 常见坑

- `data.js` 常是单行大文件（>64KB），Read 工具会拒绝，用脚本解析。
- 写文件用 `newline="\n"`，否则 Windows 下变 CRLF。
- PowerShell 会给 `python -c` 吞掉双引号：复杂逻辑写成 `.py` 文件跑。
- Windows PowerShell 5.1 读 UTF-8 无 BOM 文件会按 GBK 解码，中文路径变乱码：
  `Get-Content` 一律加 `-Encoding UTF8`。
- `paragraphsPerPage` 固定 1；练习页真正的分页由访客侧「每段句数」设置控制。
- 音频 12MB/25 分钟是常态，页面已 `preload="metadata"`，不要改成预加载全部。
- Whisper 的 `Failed to launch Triton kernels` 警告无害（DTW 回退到普通实现），不用处理。

## 收尾汇报

句子数、材料数、缺译数、check 结果、练习包路径、卡片是否插入、是否需要 push。
