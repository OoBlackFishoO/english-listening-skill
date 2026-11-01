# english-listening

> 给任意英语音频自动生成精听填空练习页：Whisper 转写、按标点断句、逐句中文译文、一键上线。Trae / Claude Skill。

一个本地跑的**出题流水线**。把一段听力音频丢进去，得到一套能直接挂到静态网站上的练习页：逐句精听、整段连听、挖空填词、判分、看中文对照，作答进度存在访客自己的浏览器里。

音频和文本**不出本机**，转写用本地 Whisper，不联网、不调 API。

## 生成的练习页长什么样

- 顶部常驻翻页条，长音频不迷路
- 逐句模式：一句一张卡，各有「▶ 本句 / 🔁 循环 / 中」按钮
- 整段模式：可自定义每段句数（1–12 句），整段连听做长填空
- 挖空密度可调（25%–95%，最高接近默写），填空题在浏览器里动态生成
- 变速播放、跟读高亮自动滚动、判分、显示全部译文
- 进度存在 `localStorage`，换段长不丢答案

## 前置条件

| 依赖 | 说明 |
|---|---|
| Python 3.10+ | 需要 `pip install openai-whisper imageio-ffmpeg` |
| 一个静态站点 | 空目录也行，`--sync-kit` 会自动补齐样式、脚本和列表页 |
| 磁盘 | Whisper `small.en` 模型约 480MB，缓存在 `~/.cache/whisper` |

有 NVIDIA 显卡会自动用 GPU（fp16），没有就走 CPU，只是慢一些。

## 安装

```bash
git clone https://github.com/OoBlackFishoO/english-listening-skill.git
cp -r english-listening-skill ~/.trae-cn/skills/english-listening
```

目录名必须是 `english-listening`，因为它和 `SKILL.md` 里的 `name` 对应。

其它支持 `SKILL.md` 的 agent，复制到它自己的 skills 目录即可。

## 配置

在 skill 目录下建 `config.json`（已在 `.gitignore` 里，不会提交）：

```json
{
  "python": "C:\\path\\to\\venv\\Scripts\\python.exe",
  "site": "D:\\path\\to\\your-site",
  "brand": {
    "name": "我的小站",
    "copyright": "© 2026 Your Name",
    "links": [{ "label": "GitHub", "url": "https://github.com/you" }]
  }
}
```

字段全部可省，回退顺序：**命令行参数 > 环境变量 > config.json > 自动探测**。

- `python`：装了 whisper 的解释器，agent 拼命令时要用
- `site`：站点仓库根。在站点目录下运行时**可以省略**，脚本会靠 `english/listening.html` 自动认出来
- `brand`：渲染进练习页页脚的品牌信息。省略时只显示「听力练习」，没有版权行和页脚链接

## 快速开始

```powershell
$SK = "$env:USERPROFILE\.trae-cn\skills\english-listening"
$PY = (Get-Content "$SK\config.json" -Raw -Encoding UTF8 | ConvertFrom-Json).python
$MK = "$SK\scripts\make.py"

# 0. 自检
& $PY $MK doctor

# 1. 转写（逐词时间戳）
& $PY $MK transcribe 听力.mp3 --slug cet6-x --title "2025.12 六级听力 · 第 3 套"

# 2. 按标点重组句子
& $PY $MK resegment cet6-x

# 3. 列待译句子
& $PY $MK zh cet6-x --dump

# 4. 翻译后回填（{"句子索引": "译文"}）
& $PY $MK zh cet6-x --inject zh.json

# 5. 导出练习包（末尾自动校验）
& $PY $MK export cet6-x --dest "<站点根>\english\listening\cet6-x" --sync-kit

# 6. 往列表页插卡片
& $PY $MK publish cet6-x
```

第 4 步的翻译由 agent 逐句给出（不机翻），每批 48 句。已有纯文本译文时用 `--auto zh.txt`（一行一句，条数必须相等）。

最后 `git push`，练习就上线了。

## 站点要求

练习页在 `english/listening/<slug>/`，靠相对路径 `../../../` 引用站点资源，所以**目录层级是硬约束**：

```
你的站点/
├── index.html             ← 有一个就行
├── css/style.css          ← 缺了自动补
├── js/clay.js             ← 缺了自动补
├── favicon.svg            ← 缺了自动补
└── english/
    ├── listening.html     ← 缺了自动补（练习目录页）
    └── listening/
        └── cet6-x/
            ├── index.html ← 导出生成
            ├── audio.mp3  ← 导出生成（64k 单声道）
            └── data.js    ← 导出生成
```

`export --sync-kit` 会从 `assets/site-kit/` 补齐上面前四个标了「补」的文件，
**已存在的一律不覆盖**，所以对自己已有站点重复执行是安全的。

补出来的 `english/listening.html` 是个空目录页，只留一个空的 `<div class="cards">`，
等 `publish` 往里插卡片。它顶部有个「← 回英语区」按钮指向 `../english.html`，
如果你的站点没有这一页，删掉那行按钮即可（脚本会提醒）。

`data.js` 的格式固定，练习页只认这个前缀：

```js
window.__EXERCISE__ = {"title": "...", "audio": "audio.mp3", "paragraphs": [{ "sentences": [
  { "start": 0.0, "end": 3.77, "text": "Hello!", "zh": "你好！", "words": [{ "w": "Hello!", "s": 0.0, "e": 0.73 }] }
] }] };
```

## 两种用法

**A. 从音频到上线** —— 上面那个流程，走完 `transcribe → publish`。

**B. 只给已有练习包补译文** —— 不重跑转写，直接改 `data.js` 里的 `zh` 字段：

```powershell
$ZH = "$SK\scripts\zh_tool.py"
& $PY $ZH dump   <站点根>\english\listening\cet6-x\data.js src.txt
& $PY $ZH inject <data.js> <zh目录>     # zh_0.json, zh_1.json … 纯字符串数组
& $PY $ZH verify <data.js> src.txt
```

红线：只写 `zh`。`text`、`words[]`、断句、句序一个字节都不能动——`start/end` 和 `words[].s/e` 是挖空和跟听的唯一依据。

## 命令速查

| 命令 | 作用 |
|---|---|
| `doctor` | 自检环境、模板、站点、解释器 |
| `transcribe <音频> --slug --title` | Whisper 转写，输出 `work/<slug>/segments.json` |
| `resegment <slug>` | 按 `. ? !` 重组句子，输出 `sents.json` |
| `zh <slug> --dump` | 列待译句子 |
| `zh <slug> --inject zh.json` | 按索引回填译文 |
| `zh <slug> --auto zh.txt` | 纯文本回填（一行一句） |
| `export <slug> --dest <目录>` | 压音频、生成 `data.js`、渲染 `index.html`、自动校验 |
| `check <练习包目录>` | 校验句数 / 缺译 / 时间戳异常 |
| `publish <slug>` | 往 `english/listening.html` 插卡片（幂等） |
| `list` | 列出所有中间产物及进度 |

中间产物默认在 `~/.cache/listening-work/<slug>/`，可用 `--work` 或 `LISTEN_WORK` 覆盖。

## 两条设计原则

**断句按标点，不按静音。** Whisper 按静音切出来的段经常把一句话切成两半（`…joined the | diplomatic corps…`）。这里把整篇展平成词序列，只在 `. ? !` 处断开，所以句子是完整的。

**不挖空、不机翻。** 挖空由练习页浏览器端动态生成，密度访客自己调；译文由 agent 或人逐句给，质量优先于速度。

## 常见问题

**导出后页面没样式？** 目录层级放错了，或者站点缺 `css/style.css`。用 `--sync-kit` 补，并确认练习包在 `english/listening/<slug>/`（三层）。

**`Failed to launch Triton kernels` 警告？** 无害，Whisper 的 DTW 回退到普通实现，不影响时间戳。

**PowerShell 里中文路径变乱码？** PS 5.1 读 UTF-8 无 BOM 文件会按 GBK 解码，`Get-Content` 要加 `-Encoding UTF8`。

**`data.js` 用编辑器打不开？** 它是单行大文件（>64KB），用脚本解析，别整份读。

## 许可证

MIT
