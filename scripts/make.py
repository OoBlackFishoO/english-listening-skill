# -*- coding: utf-8 -*-
"""
英语听力练习 · 一体化出题流水线
================================
音频 → Whisper 逐词时间戳 → 按标点断句 → 补中文 → 导出练习包 → 插卡片上线。

  python make.py doctor
  python make.py transcribe 音频.mp3 --slug cet6-x --title "2025.12 六级听力 · 第 3 套"
  python make.py resegment cet6-x
  python make.py zh cet6-x --dump                     # 列出待译 → 写 zh_todo.json
  python make.py zh cet6-x --inject zh.json           # {"0": "译文", "3": "译文"}
  python make.py zh cet6-x --auto zh.txt              # 一行一句的纯文本
  python make.py export cet6-x --dest <练习包目录>
  python make.py check <练习包目录>
  python make.py publish cet6-x                       # 往 english/listening.html 插卡片
  python make.py list

中间产物默认在 ~/.cache/listening-work/<slug>/，可用 --work 或 LISTEN_WORK 覆盖。
模板唯一真源是本文件同级的 assets/exercise_template.html。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(BASE)
TEMPLATE = os.path.join(SKILL, "assets", "exercise_template.html")
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "small.en")


def load_config():
    """本机配置（不入库）：skill 目录下的 config.json。"""
    p = os.path.join(SKILL, "config.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("config.json 读取失败，已忽略：%s" % e)
    return {}


CFG = load_config()

WORK = (os.environ.get("LISTEN_WORK") or CFG.get("work") or
        os.path.join(os.path.expanduser("~"), ".cache", "listening-work"))
SITE = os.environ.get("LISTEN_SITE") or CFG.get("site") or ""


def detect_site(start=None):
    """从当前目录逐级向上找站点根（含 english/listening.html 的那层）。"""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, "english", "listening.html")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def site_or_die(explicit=""):
    s = explicit or SITE or detect_site()
    if not s:
        sys.exit("未配置站点目录。三选一：\n"
                 "  1) 在 skill 目录的 config.json 里写 \"site\": \"<站点根>\"\n"
                 "  2) 设环境变量 LISTEN_SITE\n"
                 "  3) 命令行加 --site <站点根>\n"
                 "（在站点仓库目录下运行时会自动识别）")
    return os.path.abspath(s)


# 材料（题目/篇章播报）边界，与练习页保持同一套规则
QBREAK = re.compile(r"^(Questions?|Section|Conversation|Passage|Recording)\b", re.I)
END = re.compile(r'[.!?]["\')]?$')

TONE_ROTATION = [("sky", "#DFEEF9"), ("lilac", "#EDE6FB"),
                 ("butter", "#FFE3D5"), ("mint", "#DFF3E4")]


# ---------- 基础工具 ----------
def slugify(text):
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", text or "").strip("-").lower()
    if not clean:
        clean = "ex-" + hashlib.md5((text or "x").encode("utf-8")).hexdigest()[:8]
    return clean[:48]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def unit(slug, work=None):
    return os.path.join(work or WORK, slug)


def fmt(sec):
    sec = max(0, int(round(sec or 0)))
    return "%d:%02d" % (sec // 60, sec % 60)


def join_words(words):
    """把词拼回句子文本：撇号/&开头、连字符结尾的词直接相连。"""
    out = ""
    for w in words:
        t = (w.get("w") or "").strip()
        if not t:
            continue
        if not out:
            out = t
        elif t[0] in "'&" or out.endswith("-") or out.endswith("&"):
            out += t
        else:
            out += " " + t
    return out


def all_sentences(data):
    return [s for p in data["paragraphs"] for s in p["sentences"]]


# ---------- doctor：环境自检 ----------
def cmd_doctor(args):
    print("skill      ", SKILL)
    print("config.json", (os.path.join(SKILL, "config.json")
                         if CFG else "无（可复制 config.example.json 一份）"))
    print("模板       ", TEMPLATE, "存在" if os.path.exists(TEMPLATE) else "缺失")
    print("中间产物   ", WORK)
    site = args.site or SITE or detect_site()
    src = ("--site" if args.site else
           "config.json / LISTEN_SITE" if SITE else
           "自动探测" if site else "未配置")
    print("网站根     ", site or "（未配置）", "| 来源：", src)
    if site:
        page = os.path.join(site, "english", "listening.html")
        print("              english/listening.html",
              "存在" if os.path.isfile(page) else "缺失")
    if CFG.get("python"):
        print("配置解释器 ", CFG["python"],
              "存在" if os.path.exists(CFG["python"]) else "缺失")
    print("当前解释器 ", sys.executable, sys.version.split()[0])
    try:
        import torch
        print("torch      ", torch.__version__,
              "| cuda", torch.cuda.is_available(),
              torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
    except Exception as e:
        print("torch      不可用：", e)
    try:
        import whisper  # noqa: F401
        print("whisper    ", "已安装")
    except Exception as e:
        print("whisper    不可用：", e)
    try:
        import imageio_ffmpeg
        print("ffmpeg     ", imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as e:
        print("ffmpeg     不可用：", e)
    cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    if os.path.isdir(cache):
        pts = [f for f in os.listdir(cache) if f.endswith(".pt")]
        print("模型缓存   ", ", ".join(pts) or "空")


# ---------- transcribe ----------
def decode_audio(path):
    import imageio_ffmpeg
    import numpy as np
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    raw = subprocess.check_output(
        [exe, "-i", path, "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
        stderr=subprocess.DEVNULL)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def cmd_transcribe(args):
    src = os.path.abspath(args.audio)
    if not os.path.exists(src):
        sys.exit("找不到音频：" + src)
    slug = args.slug or slugify(os.path.splitext(os.path.basename(src))[0])

    import torch
    import whisper
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("加载模型 %s（device=%s）…" % (args.model, dev))
    model = whisper.load_model(args.model, device=dev)
    print("转写中 …（时长较长的音频要几分钟）")
    result = model.transcribe(decode_audio(src), verbose=False,
                              fp16=(dev == "cuda"), word_timestamps=True)

    segments = []
    for s in result.get("segments", []):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        s_start, s_end = float(s["start"]), float(s["end"])
        words = []
        for w in s.get("words") or []:
            ws = w.get("start") if w.get("start") is not None else s_start
            we = w.get("end") if w.get("end") is not None else s_end
            words.append({"w": (w.get("word") or "").strip(),
                          "s": round(float(ws), 2), "e": round(float(we), 2)})
        segments.append({"start": round(s_start, 2), "end": round(s_end, 2),
                         "text": text, "words": words})

    data = {
        "title": args.title or os.path.splitext(os.path.basename(src))[0],
        "audio": src,
        "model": args.model,
        "duration": round(float(result.get("duration") or
                                (segments[-1]["end"] if segments else 0)), 2),
        "segments": segments,
    }
    out = write_json(os.path.join(unit(slug, args.work), "segments.json"), data)
    print("段落 %d · 词 %d · 时长 %s" %
          (len(segments), sum(len(s["words"]) for s in segments),
           fmt(data["duration"])))
    print("→", out)
    print("下一步：python make.py resegment " + slug)


# ---------- resegment：按标点重组 ----------
def resegment(segments):
    """整篇展平 → 按材料切 → 按句末标点断句。返回 paragraphs。"""
    mats, cur = [], []
    for s in segments:
        if cur and QBREAK.match((s.get("text") or "").strip()):
            mats.append(cur)
            cur = []
        cur.append(s)
    if cur:
        mats.append(cur)

    paragraphs = []
    for mat in mats:
        words = []
        for s in mat:
            for w in (s.get("words") or []):
                words.append(w)
        groups, cur = [], []
        for w in words:
            cur.append(w)
            if END.search((w.get("w") or "").strip()):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)

        sents = []
        for grp in groups:
            sents.append({
                "start": grp[0].get("s"),
                "end": grp[-1].get("e"),
                "text": join_words(grp),
                "words": [{"w": (g.get("w") or "").strip(),
                           "s": g.get("s"), "e": g.get("e")} for g in grp],
                "zh": "",
            })
        paragraphs.append({"sentences": sents})
    return paragraphs


def cmd_resegment(args):
    src = os.path.join(unit(args.slug, args.work), "segments.json")
    if not os.path.exists(src):
        sys.exit("找不到 " + src + "，请先 transcribe")
    seg = read_json(src)
    paragraphs = resegment(seg["segments"])
    data = {
        "title": seg.get("title") or args.slug,
        "audio": seg.get("audio"),
        "duration": seg.get("duration"),
        "paragraphs": paragraphs,
    }
    out = write_json(os.path.join(unit(args.slug, args.work), "sents.json"), data)
    total = sum(len(p["sentences"]) for p in paragraphs)
    print("材料 %d · 句子 %d（原 %d 段）" %
          (len(paragraphs), total, len(seg["segments"])))
    print("→", out)
    print("下一步：python make.py zh %s --dump" % args.slug)


# ---------- zh：译文清单 / 回填 ----------
def cmd_zh(args):
    path = os.path.join(unit(args.slug, args.work), "sents.json")
    if not os.path.exists(path):
        sys.exit("找不到 " + path + "，请先 resegment")
    data = read_json(path)
    sents = all_sentences(data)

    if args.auto:
        with open(args.auto, encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
        if len(lines) != len(sents):
            sys.exit("条数不符：译文 %d 行，句子 %d 句。请先 --dump 对齐。"
                     % (len(lines), len(sents)))
        for s, t in zip(sents, lines):
            s["zh"] = t.strip()
        write_json(path, data)
        left = [i for i, s in enumerate(sents) if not (s.get("zh") or "").strip()]
        print("回填 %d 句 · 仍缺 %d 句" % (len(lines), len(left)))
        return

    if args.inject:
        fix = read_json(args.inject)
        filled = 0
        for k, v in fix.items():
            i = int(k)
            if 0 <= i < len(sents) and (v or "").strip():
                sents[i]["zh"] = v.strip()
                filled += 1
        write_json(path, data)
        left = [i for i, s in enumerate(sents) if not (s.get("zh") or "").strip()]
        print("回填 %d 句 · 仍缺 %d 句" % (filled, len(left)))
        if left:
            print("待译索引：", ",".join(map(str, left[:40])) +
                  (" …" if len(left) > 40 else ""))
        return

    todo = [{"i": i, "text": s["text"]} for i, s in enumerate(sents)
            if not (s.get("zh") or "").strip()]
    out = write_json(os.path.join(unit(args.slug, args.work), "zh_todo.json"), todo)
    print("总句数 %d · 已译 %d · 待译 %d" %
          (len(sents), len(sents) - len(todo), len(todo)))
    for t in todo[:10]:
        print("  [%d] %s" % (t["i"], t["text"][:90]))
    if len(todo) > 10:
        print("  … 其余见文件")
    print("→", out)


# ---------- export ----------
def build_data_js(payload):
    js = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return "window.__EXERCISE__ = " + js + ";\n"


DEFAULT_BRAND = {"name": "我的站点", "copyright": "", "links": []}


def get_brand(override=""):
    """品牌信息：config.json 的 brand 段，可被 --brand 覆盖站名。"""
    b = json.loads(json.dumps(DEFAULT_BRAND))
    b.update({k: v for k, v in (CFG.get("brand") or {}).items() if v})
    if override:
        b["name"] = override
    return b


def render_html(html, brand_override=""):
    """把占位符渲染成实际页面。未配置品牌时用中性默认值。"""
    brand = get_brand(brand_override)
    name = brand.get("name") or DEFAULT_BRAND["name"]
    links = brand.get("links") or []
    link_html = "\n      ".join(
        '<a href="%s"%s>%s</a>' % (
            l.get("url") or "#",
            ' target="_blank" rel="noopener"'
            if str(l.get("url") or "").startswith("http") else "",
            l.get("label") or "链接") for l in links)
    copy = (brand.get("copyright") or "").strip()
    copy_line = '<p class="footer-copy">%s</p>' % copy if copy else ""

    html = html.replace("{{SITE_NAME_JSON}}", json.dumps(name, ensure_ascii=False))
    html = html.replace("{{SITE_NAME}}", name)
    html = html.replace("{{FOOTER_LINKS}}", link_html)
    html = html.replace("{{COPYRIGHT_LINE}}", copy_line)
    left = set(re.findall(r"\{\{[A-Z_]+\}\}", html))
    if left:
        print("！占位符未替换：%s" % ", ".join(sorted(left)))
    return html


def render_template(brand_override=""):
    with open(TEMPLATE, encoding="utf-8") as f:
        return render_html(f.read(), brand_override)


def site_root_of(dest):
    """练习包在 <站点根>/english/listening/<slug>/，往上三级。"""
    return os.path.abspath(os.path.join(dest, "..", "..", ".."))


def looks_like_site(root):
    return any(os.path.exists(os.path.join(root, x))
               for x in ("index.html", "english", "css"))


def sync_kit(dest):
    """给站点补齐 css/js/favicon；缺 english/listening.html 时也补一份空列表页。"""
    site_root = site_root_of(dest)
    if not looks_like_site(site_root):
        print("！跳过 --sync-kit：%s 不像站点根（无 index.html / english / css）" % site_root)
        return
    kit = os.path.join(SKILL, "assets", "site-kit")
    for rel, name in (("css/style.css", "style.css"),
                      ("js/clay.js", "clay.js"),
                      ("favicon.svg", "favicon.svg")):
        dst = os.path.join(site_root, rel)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(kit, name), dst)
        print("补站点资源 →", dst)

    page = os.path.join(site_root, "english", "listening.html")
    if os.path.exists(page):
        return
    with open(os.path.join(kit, "listening.html"), encoding="utf-8") as f:
        html = render_html(f.read())
    os.makedirs(os.path.dirname(page), exist_ok=True)
    with open(page, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("补站点页面 →", page)
    print("  提示：里面的「← 回英语区」指向 ../english.html，站点没有这一页就删掉那行按钮")


def cmd_export(args):
    path = os.path.join(unit(args.slug, args.work), "sents.json")
    if not os.path.exists(path):
        sys.exit("找不到 " + path + "，请先 resegment")
    data = read_json(path)
    sents = all_sentences(data)
    left = sum(1 for s in sents if not (s.get("zh") or "").strip())
    if left and not args.force:
        sys.exit("还有 %d 句没译文，补齐或用 --force 强制导出" % left)

    title = args.title or data.get("title") or args.slug
    audio = args.audio or data.get("audio")
    if not audio or not os.path.exists(audio):
        sys.exit("找不到音频源：" + str(audio))

    dest = os.path.abspath(args.dest or os.path.join(WORK, "export", args.slug))
    os.makedirs(dest, exist_ok=True)

    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    print("压缩音频 →", os.path.join(dest, "audio.mp3"))
    subprocess.check_call(
        [exe, "-y", "-i", audio, "-ac", "1", "-ar", "44100", "-b:a", "64k",
         os.path.join(dest, "audio.mp3")], stderr=subprocess.DEVNULL)

    payload = {
        "title": title,
        "audio": "audio.mp3",
        "paragraphsPerPage": 1,
        "paragraphs": data["paragraphs"],
    }
    with open(os.path.join(dest, "data.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(build_data_js(payload))
    if not os.path.exists(TEMPLATE):
        sys.exit("模板缺失：" + TEMPLATE)
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(render_template(args.brand))
    print("data.js %d 句 · index.html 已渲染" % len(sents))
    print("→", dest)
    site = args.site or SITE or detect_site()
    if site:
        want = os.path.join(os.path.abspath(site), "english", "listening")
        if not os.path.abspath(dest).lower().startswith(want.lower() + os.sep):
            print("！注意：导出目录不在 %s 下，练习页里的 ../../../css/ 会失效（没样式）。"
                  % want)
            print("  正式上线请用 --dest \"%s%c<slug>\"" % (want, os.sep))
    if args.sync_kit:
        sync_kit(dest)
    cmd_check(argparse.Namespace(dir=dest))


# ---------- check ----------
def cmd_check(args):
    dest = os.path.abspath(args.dir)
    js = os.path.join(dest, "data.js")
    if not os.path.exists(js):
        sys.exit("找不到 " + js)
    raw = open(js, encoding="utf-8").read()
    payload = json.loads(raw[len("window.__EXERCISE__ = "):].rstrip().rstrip(";"))
    sents = [s for p in payload.get("paragraphs", []) for s in p.get("sentences", [])]
    nozh = [s for s in sents if not (s.get("zh") or "").strip()]
    nowords = [s for s in sents if not s.get("words")]
    badtime = []
    prev_end = -1
    for s in sents:
        if s.get("start") is None or s.get("end") is None or s["end"] < s["start"]:
            badtime.append(s)
        if s.get("start", 0) < prev_end - 0.5:
            badtime.append(s)
        prev_end = max(prev_end, s.get("end") or 0)
    print("检查 %s" % dest)
    print("  标题 %s" % payload.get("title", ""))
    print("  材料 %d · 句子 %d · 词 %d" %
          (len(payload.get("paragraphs", [])), len(sents),
           sum(len(s.get("words") or []) for s in sents)))
    print("  缺译 %d · 无词 %d · 时间异常 %d" % (len(nozh), len(nowords), len(badtime)))
    if not (nozh or nowords or badtime):
        print("  结果：通过")


# ---------- publish：往列表页插卡片 ----------
CARD_RE = re.compile(r'<a class="clay-card pop"[^>]*>')


def _renumber_cards(html):
    """按出现顺序重排 --d 交错延迟，第一张不带；其余属性原样保留。"""
    n = [0]

    def rep(m):
        attrs = re.sub(r'\s*style="--d:[^"]*"', "", m.group(1))
        if n[0] > 0:
            d = ("%.2f" % (n[0] * 0.08)).lstrip("0") or "0"
            attrs += ' style="--d:%ss"' % d
        n[0] += 1
        return '<a class="clay-card pop"%s>' % attrs

    return re.sub(r'<a class="clay-card pop"([^>]*)>', rep, html)


def build_card(slug, title, desc, badge, tone, bg, minutes, sents, zh_ok):
    chips = ['<span class="chip">约 %d 分钟</span>' % max(1, round(minutes))]
    chips.append('<span class="chip">%d 句</span>' % sents)
    if zh_ok:
        chips.append('<span class="chip">带翻译</span>')
    return (
        '      <a class="clay-card pop" href="listening/%s/index.html">\n'
        '        <div class="card-top">\n'
        '          <span class="clay-icon" style="background:%s">🎧</span>\n'
        '          <h3>%s</h3>\n'
        '          <span class="badge %s">%s</span>\n'
        '        </div>\n'
        '        <p class="desc">%s</p>\n'
        '        <div class="chips">%s</div>\n'
        '      </a>\n' % (slug, bg, title, tone, badge, desc, "".join(chips)))


def cmd_publish(args):
    site = site_or_die(args.site)
    page = os.path.join(site, "english", "listening.html")
    if not os.path.exists(page):
        sys.exit("找不到列表页：" + page)

    data = None
    sp = os.path.join(unit(args.slug, args.work), "sents.json")
    if os.path.exists(sp):
        data = read_json(sp)
    if data is None:
        dj = os.path.join(site, "english", "listening", args.slug, "data.js")
        if not os.path.exists(dj):
            sys.exit("找不到 sents.json 或线上 data.js，无法生成卡片")
        raw = open(dj, encoding="utf-8").read()
        data = json.loads(raw[len("window.__EXERCISE__ = "):].rstrip().rstrip(";"))

    sents = all_sentences(data) if "paragraphs" in data else []
    zh_ok = all((s.get("zh") or "").strip() for s in sents) if sents else False
    dur = data.get("duration") or 0
    title = args.title or data.get("title") or args.slug
    desc = args.desc or ("%d 句材料，可逐句精听或整段连听，每句都能点「中」看翻译。"
                         % len(sents) if zh_ok else
                         "%d 句材料，可逐句精听或整段连听。" % len(sents))
    tone, bg = args.tone, None
    existing = len(CARD_RE.findall(open(page, encoding="utf-8").read()))
    for t, b in TONE_ROTATION:
        if t == tone:
            bg = b
    if bg is None:
        tone, bg = TONE_ROTATION[existing % len(TONE_ROTATION)]

    card = build_card(args.slug, title, desc, args.badge, tone, bg,
                      (dur or 0) / 60.0, len(sents), zh_ok)

    if args.print:
        sys.stdout.write(card)
        return

    html = open(page, encoding="utf-8").read()
    stale = re.compile(
        r'[ \t]*<a class="clay-card pop"[^>]*href="listening/%s/index\.html"[^>]*>.*?</a>\n'
        % re.escape(args.slug), re.S)
    html, n = stale.subn("", html)
    if n:
        print("替换已有卡片 %d 张" % n)
    marker = '<div class="cards">\n'
    if marker not in html:
        sys.exit('列表页里找不到 <div class="cards"> 锚点，请手工粘贴卡片')
    html = html.replace(marker, marker + card, 1)
    html = _renumber_cards(html)
    with open(page, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("已插入卡片：%s → %s" % (title, page))
    print("提醒：卡片置顶；记得 git add / commit / push 才真正上线。")


# ---------- list ----------
def cmd_list(args):
    root = args.work or WORK
    if not os.path.isdir(root):
        print("（还没有任何中间产物）")
        return
    rows = []
    for slug in sorted(os.listdir(root)):
        sp = os.path.join(root, slug, "sents.json")
        if not os.path.exists(sp):
            continue
        d = read_json(sp)
        s = all_sentences(d)
        left = sum(1 for x in s if not (x.get("zh") or "").strip())
        rows.append((slug, d.get("title", ""), len(s), left, d.get("duration") or 0))
    if not rows:
        print("（还没有任何中间产物）")
        return
    print("%-28s %-8s %-6s %-6s %s" % ("slug", "句数", "缺译", "时长", "标题"))
    for r in rows:
        print("%-28s %-8d %-6d %-6s %s" % (r[0], r[2], r[3], fmt(r[4]), r[1]))


# ---------- 入口 ----------
def main():
    ap = argparse.ArgumentParser(description="英语听力练习一体化流水线")
    ap.add_argument("--work", help="中间产物根目录，默认 %s" % WORK)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="环境自检")
    p.add_argument("--site", default="", help="站点根目录（默认自动探测）")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("transcribe", help="Whisper 转写（词级时间戳）")
    p.add_argument("audio")
    p.add_argument("--slug")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--title")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("resegment", help="按标点重组句子")
    p.add_argument("slug")
    p.set_defaults(func=cmd_resegment)

    p = sub.add_parser("zh", help="译文清单 / 回填")
    p.add_argument("slug")
    p.add_argument("--dump", action="store_true", help="列出待译句子（默认行为）")
    p.add_argument("--inject", help='译文 JSON：{"句子索引": "译文"}')
    p.add_argument("--auto", help="纯文本译文，一行一句，条数须与句子数相等")
    p.set_defaults(func=cmd_zh)

    p = sub.add_parser("export", help="导出网站练习包")
    p.add_argument("slug")
    p.add_argument("--title")
    p.add_argument("--audio", help="音频源（默认取 segments.json 记录的原路径）")
    p.add_argument("--dest", help="目标目录，默认 <work>/export/<slug>")
    p.add_argument("--site", default="", help="站点根目录（默认自动探测）")
    p.add_argument("--force", action="store_true", help="允许缺译文导出")
    p.add_argument("--brand", default="", help="覆盖站点名（默认取 config.json 的 brand.name）")
    p.add_argument("--sync-kit", action="store_true",
                   help="目标站点缺 css/js/favicon 时，从 assets/site-kit 补一份")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("check", help="校验练习包")
    p.add_argument("dir")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("publish", help="往 english/listening.html 插入/更新卡片")
    p.add_argument("slug")
    p.add_argument("--site", default="", help="站点根目录（默认自动探测）")
    p.add_argument("--title")
    p.add_argument("--desc")
    p.add_argument("--badge", default="练习")
    p.add_argument("--tone", default="", help="sky / lilac / butter / mint，默认自动轮换")
    p.add_argument("--print", action="store_true", help="只打印卡片 HTML，不改文件")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("list", help="列出所有中间产物及进度")
    p.set_defaults(func=cmd_list)

    args = ap.parse_args()
    os.makedirs(args.work or WORK, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
