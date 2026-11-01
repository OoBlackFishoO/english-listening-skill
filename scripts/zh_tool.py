"""给听力练习包 data.js 补译文的三件套：dump / inject / verify。

用法（在任意目录）：
    python zh_tool.py dump   <data.js> [src.txt]
    python zh_tool.py inject <data.js> <zh_dir>      # zh_dir 里放 zh_0.json, zh_1.json ...
    python zh_tool.py verify <data.js> [src.txt]

zh_0.json 等文件为纯字符串数组，顺序等于全局句序（paragraphs -> sentences 展平）。
inject 会断言：条数相等、每条含中文；然后整份 json.dumps(ensure_ascii=False) 写回。
"""
import io
import json
import os
import re
import sys


def load(path):
    raw = io.open(path, encoding="utf-8").read()
    i, j = raw.index("{"), raw.rindex("}") + 1
    return raw[:i], raw[j:], json.loads(raw[i:j])


def flat(exc):
    return [" ".join(w["w"] for w in s["words"])
            for p in exc["paragraphs"] for s in p["sentences"]]


def save(path, pre, post, exc):
    body = json.dumps(exc, ensure_ascii=False)
    io.open(path, "w", encoding="utf-8", newline="\n").write(pre + body + post)


def cmd_dump(data, src):
    pre, post, exc = load(data)
    zh = flat(exc)
    with io.open(src, "w", encoding="utf-8", newline="\n") as f:
        for k, t in enumerate(zh):
            f.write("%d\t%s\n" % (k, t))
    print("句子数 %d -> %s" % (len(zh), src))


def cmd_inject(data, folder):
    pre, post, exc = load(data)
    eng = flat(exc)
    zh, k = [], 0
    while os.path.exists(os.path.join(folder, "zh_%d.json" % k)):
        zh.extend(json.load(io.open(os.path.join(folder, "zh_%d.json" % k), encoding="utf-8")))
        k += 1
    assert len(zh) == len(eng), "条数不符：译文 %d 条，英文 %d 句" % (len(zh), len(eng))
    for i, t in enumerate(zh):
        assert re.search(r"[\u4e00-\u9fff]", t), "第 %d 条没有中文：%s" % (i, t)
    i = 0
    for p in exc["paragraphs"]:
        for s in p["sentences"]:
            s["zh"] = zh[i].strip()
            i += 1
    save(data, pre, post, exc)
    print("已写入 %d 条译文" % len(zh))


def cmd_verify(data, src):
    pre, post, exc = load(data)
    eng = flat(exc)
    old = [l.split("\t", 1)[1].rstrip("\n")
           for l in io.open(src, encoding="utf-8") if l.strip()]
    filled = sum(1 for p in exc["paragraphs"] for s in p["sentences"] if s.get("zh"))
    print("英文与基线一致:", old == eng)
    print("总句数:", len(eng), "已填译文:", filled)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    op, data = sys.argv[1], sys.argv[2]
    if op == "dump":
        cmd_dump(data, sys.argv[3] if len(sys.argv) > 3 else "src.txt")
    elif op == "inject":
        cmd_inject(data, sys.argv[3])
    elif op == "verify":
        cmd_verify(data, sys.argv[3] if len(sys.argv) > 3 else "src.txt")
    else:
        print(__doc__)
