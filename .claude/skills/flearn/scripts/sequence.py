#!/usr/bin/env python3
"""Render a flearn walk page from a JSON spec: one sequence diagram per walk.

    python3 sequence.py spec.json out.html

The spec owns the content. This file owns the geometry, so every diagram in
every project comes out on the same grid with the same legend and the same
colours. Never hand-write the SVG; edit the spec and run this again.

Lifelines are the stops of the answer model, and the gutter number on each
arrow is the stop it belongs to, so the diagram and the stop cards share one
numbering.

Spec shape (only "title" and "features" are required at the top):

{
  "title": "Send a chat message",
  "subtitle": "talk-to-web · walked YYYY-MM-DD · walk mode",
  "root": "/abs/path/to/repo",                 # joined to code paths for links
  "features": [{
    "slug": "chat-turn",
    "title": "One chat turn",
    "overview": "the whole flow in two or three plain sentences, said first",
    "parts": [["1·6 SCREEN","Browser","frontend/src/"], ...],     # 3-5 of them
    "msgs":  [{"src":0,"dst":1,"label":"POST /x","kind":"http",
               "stop":1,"gap":0}, ...],                           # at most 10
    "frame": {"op":"ALT","guard1":"[a]","guard2":"[else]",
              "first":3,"last":8,"divider":5,"parts":[0,1,2]},     # optional
    "stops": [{"n":1,"name":"Screen","who":"streamChat",
               "what":"one to four sentences","hands":"what goes next",
               "code":[["frontend/src/x.ts","88-115","streamChat"], ...],
               "changed": false}, ...],                           # changed: session mode
    "failure": "one AI failure and the line that defends it",
    "choice":  "one choice and why",
    "number":  "one number and where it comes from"
  }]
}

A code row is [path, "start-end", symbol]. A relative path is joined to
"root"; an absolute path is used as is. Each row renders as a vscode:// link.

kind is one of: call, http, ret, async, ok, self.
  call  solid muted        an internal call
  http  solid link-blue    HTTP, a WebSocket, or any external service
  ret   dashed + filled    a return
  async dashed + open head fire and forget
  ok    solid coral        the one primary success message (exactly one per diagram)
  self  a U-loop on one lifeline (src must equal dst)

"gap" adds vertical room above a message. Use 8 on the first message of an
alt region so the guard label has space.

Lifelines whose tag names CONTEXT, LOOP or BRAIN are drawn highlighted: those
are the deep stops, where the reader should look first.
"""
from __future__ import annotations

import html
import json
import sys

INK = "#e6e9f2"
MUTED = "#9aa5be"
SOFT = "#6f7a92"
PAPER = "#161a24"
ACCENT = "#f0824f"
LINK = "#7aa5f7"
RULE = "rgba(230,233,242,0.14)"

W = 1280
COL_L, COL_R = 96, 1240
HEAD_Y, HEAD_H, LIFE_TOP = 64, 64, 128
MSG_Y0, STEP, GUTTER_X = 176, 48, 44

DEEP = ("CONTEXT", "LOOP", "BRAIN")

STROKE = {
    "call": (MUTED, None, "a"),
    "http": (LINK, None, "l"),
    "ret": (MUTED, "5,4", "a"),
    "async": (MUTED, "5,4", "o"),
    "ok": (ACCENT, None, "ac"),
    "self": (MUTED, None, "a"),
}


def r4(v: float) -> int:
    return int(round(v / 4.0)) * 4


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def centers(n: int) -> list[int]:
    slot = (COL_R - COL_L) / float(n)
    return [r4(COL_L + slot * (i + 0.5)) for i in range(n)]


def svg(fid, title, desc, parts, msgs, frame=None) -> str:
    n = len(parts)
    cx = centers(n)
    box_w = 192 if n >= 5 else 200

    ys, cur = [], MSG_Y0
    for m in msgs:
        cur += m.get("gap", 0)
        ys.append(cur)
        cur += STEP
    bottom = ys[-1] + 32
    legend_y = bottom + 40
    height = r4(legend_y + 40)

    o = [
        f'<svg viewBox="0 0 {W} {height}" role="img" aria-labelledby="{fid}-t {fid}-d"'
        ' xmlns="http://www.w3.org/2000/svg">',
        f'<title id="{fid}-t">{esc(title)}</title>',
        f'<desc id="{fid}-d">{esc(desc)}</desc>',
        "<defs>"
        f'<marker id="{fid}-a" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{MUTED}"/></marker>'
        f'<marker id="{fid}-ac" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{ACCENT}"/></marker>'
        f'<marker id="{fid}-l" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{LINK}"/></marker>'
        f'<marker id="{fid}-o" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
        f'<polyline points="0 0, 8 3, 0 6" fill="none" stroke="{MUTED}" stroke-width="1.2"/>'
        "</marker></defs>",
        f'<rect width="100%" height="100%" fill="{PAPER}"/>',
    ]

    if frame:
        pset = frame["parts"]
        fx = min(cx[p] for p in pset) - 16
        fx2 = max(cx[p] for p in pset) + 16
        ftop, fbot = ys[frame["first"]] - 44, ys[frame["last"]] + 20
        o.append(
            f'<rect x="{r4(fx)}" y="{r4(ftop)}" width="{r4(fx2 - fx)}" height="{r4(fbot - ftop)}"'
            ' rx="4" fill="rgba(230,233,242,0.03)" stroke="rgba(230,233,242,0.28)" stroke-width="1"/>'
        )
        o.append(
            f'<rect x="{r4(fx)}" y="{r4(ftop)}" width="40" height="16" rx="2" fill="{PAPER}"'
            ' stroke="rgba(230,233,242,0.28)" stroke-width="1"/>'
        )
        o.append(
            f'<text x="{r4(fx) + 20}" y="{r4(ftop) + 12}" fill="{MUTED}" font-size="8"'
            " font-family=\"'Geist Mono', monospace\" text-anchor=\"middle\""
            f' letter-spacing="0.12em">{esc(frame["op"])}</text>'
        )
        gw = r4(len(frame["guard1"]) * 5 + 16)
        o.append(f'<rect x="{r4(fx) + 48}" y="{r4(ftop) + 2}" width="{gw}" height="14" rx="2" fill="{PAPER}"/>')
        o.append(
            f'<text x="{r4(fx) + 52}" y="{r4(ftop) + 13}" fill="{MUTED}" font-size="8"'
            " font-family=\"'Geist Mono', monospace\""
            f' letter-spacing="0.04em">{esc(frame["guard1"])}</text>'
        )
        if frame.get("divider") is not None:
            dv = r4(ys[frame["divider"]] - 26)
            o.append(
                f'<line x1="{r4(fx) + 8}" y1="{dv}" x2="{r4(fx2) - 8}" y2="{dv}"'
                ' stroke="rgba(230,233,242,0.22)" stroke-width="1" stroke-dasharray="4,3"/>'
            )
            gw2 = r4(len(frame.get("guard2", "")) * 5 + 16)
            o.append(f'<rect x="{r4(fx) + 8}" y="{dv + 3}" width="{gw2}" height="14" rx="2" fill="{PAPER}"/>')
            o.append(
                f'<text x="{r4(fx) + 12}" y="{dv + 14}" fill="{MUTED}" font-size="8"'
                " font-family=\"'Geist Mono', monospace\""
                f' letter-spacing="0.04em">{esc(frame.get("guard2", ""))}</text>'
            )

    for p in range(n):
        touch = [ys[i] for i, m in enumerate(msgs) if p in (m["src"], m["dst"])]
        if not touch:
            continue
        o.append(
            f'<rect x="{cx[p] - 4}" y="{r4(min(touch) - 12)}" width="8"'
            f' height="{r4(max(touch) - min(touch) + 24)}"'
            f' fill="rgba(230,233,242,0.07)" stroke="{MUTED}" stroke-width="0.8"/>'
        )

    for p in range(n):
        o.append(
            f'<line x1="{cx[p]}" y1="{LIFE_TOP}" x2="{cx[p]}" y2="{bottom}"'
            ' stroke="rgba(230,233,242,0.22)" stroke-width="1" stroke-dasharray="3,3"/>'
        )

    for i, m in enumerate(msgs):
        y = ys[i]
        color, dash, mk = STROKE[m["kind"]]
        da = f' stroke-dasharray="{dash}"' if dash else ""
        label = m["label"]
        o.append(
            f'<text x="{GUTTER_X}" y="{y + 4}" fill="{SOFT}" font-size="8"'
            f" font-family=\"'Geist Mono', monospace\" text-anchor=\"middle\">{m.get('stop', i + 1)}</text>"
        )
        if m["src"] == m["dst"]:
            c = cx[m["src"]]
            o.append(
                f'<path d="M {c + 4} {y - 8} L {c + 56} {y - 8} L {c + 56} {y + 12} L {c + 8} {y + 12}"'
                f' fill="none" stroke="{color}" stroke-width="1.2"{da}'
                f' marker-end="url(#{fid}-{mk})"/>'
            )
            o.append(
                f'<rect x="{c + 64}" y="{y - 12}" width="{r4(len(label) * 5 + 12)}" height="16"'
                f' rx="2" fill="{PAPER}"/>'
            )
            o.append(
                f'<text x="{c + 70}" y="{y}" fill="{MUTED}" font-size="8"'
                f" font-family=\"'Geist Mono', monospace\">{esc(label)}</text>"
            )
            continue
        x1, x2 = cx[m["src"]], cx[m["dst"]]
        d = 6 if x2 > x1 else -6
        o.append(
            f'<line x1="{x1 + (4 if x2 > x1 else -4)}" y1="{y}" x2="{x2 - d}" y2="{y}"'
            f' stroke="{color}" stroke-width="1.2"{da} marker-end="url(#{fid}-{mk})"/>'
        )
        midx = r4((x1 + x2) / 2)
        tw = r4(len(label) * 5 + 16)
        lc = ACCENT if m["kind"] == "ok" else (LINK if m["kind"] == "http" else MUTED)
        o.append(f'<rect x="{midx - tw // 2}" y="{y - 26}" width="{tw}" height="16" rx="2" fill="{PAPER}"/>')
        o.append(
            f'<text x="{midx}" y="{y - 14}" fill="{lc}" font-size="8"'
            " font-family=\"'Geist Mono', monospace\" text-anchor=\"middle\""
            f' letter-spacing="0.04em">{esc(label)}</text>'
        )

    for p, (role, name, path) in enumerate(parts):
        x = r4(cx[p] - box_w // 2)
        focal = any(k in role for k in DEEP)
        fill = "rgba(240,130,79,0.10)" if focal else "#1e2330"
        stroke = ACCENT if focal else INK
        o.append(f'<rect x="{x}" y="{HEAD_Y}" width="{box_w}" height="{HEAD_H}" rx="6" fill="{PAPER}"/>')
        o.append(
            f'<rect x="{x}" y="{HEAD_Y}" width="{box_w}" height="{HEAD_H}" rx="6"'
            f' fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
        )
        o.append(
            f'<text x="{cx[p]}" y="{HEAD_Y + 18}" fill="{SOFT}" font-size="8"'
            " font-family=\"'Geist Mono', monospace\" text-anchor=\"middle\""
            f' letter-spacing="0.12em">{esc(role)}</text>'
        )
        o.append(
            f'<text x="{cx[p]}" y="{HEAD_Y + 38}" fill="{INK}" font-size="12" font-weight="600"'
            f" font-family=\"'Geist', sans-serif\" text-anchor=\"middle\">{esc(name)}</text>"
        )
        o.append(
            f'<text x="{cx[p]}" y="{HEAD_Y + 54}" fill="{MUTED}" font-size="9"'
            f" font-family=\"'Geist Mono', monospace\" text-anchor=\"middle\">{esc(path)}</text>"
        )

    o.append(
        f'<line x1="40" y1="{r4(legend_y - 16)}" x2="{W - 40}" y2="{r4(legend_y - 16)}"'
        f' stroke="{RULE}" stroke-width="0.8"/>'
    )
    x = 40
    for lab, col, dash in [
        ("CALL", MUTED, None),
        ("HTTP / EXTERNAL", LINK, None),
        ("RETURN", MUTED, "5,4"),
        ("FIRE AND FORGET", MUTED, "5,4"),
        ("PRIMARY SUCCESS", ACCENT, None),
    ]:
        da = f' stroke-dasharray="{dash}"' if dash else ""
        o.append(
            f'<line x1="{x}" y1="{r4(legend_y + 4)}" x2="{x + 24}" y2="{r4(legend_y + 4)}"'
            f' stroke="{col}" stroke-width="1.2"{da}/>'
        )
        o.append(
            f'<text x="{x + 32}" y="{r4(legend_y + 8)}" fill="{MUTED}" font-size="8"'
            f" font-family=\"'Geist Mono', monospace\" letter-spacing=\"0.12em\">{lab}</text>"
        )
        x += r4(len(lab) * 6 + 72)
    o.append("</svg>")
    return "\n".join(o)


CSS = """
:root{--paper:#161a24;--ink:#e6e9f2;--muted:#9aa5be;--soft:#6f7a92;
--rule:rgba(230,233,242,0.14);--accent:#f0824f;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:'Geist',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;line-height:1.55;}
.wrap{max-width:1360px;margin:0 auto;padding:56px 40px 80px;}
.eyebrow{font-family:'Geist Mono',monospace;font-size:8px;letter-spacing:.14em;color:var(--soft);
text-transform:uppercase;margin:0 0 8px;}
.eyebrow.small{margin-top:24px;}
h1{font-family:'Instrument Serif',Georgia,serif;font-weight:400;font-size:44px;line-height:1.1;margin:0 0 12px;}
h2{font-family:'Instrument Serif',Georgia,serif;font-weight:400;font-size:28px;margin:0 0 8px;}
h3{font-size:14px;font-weight:600;margin:0 0 2px;}
.sub{color:var(--muted);font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.04em;margin:0 0 8px;}
.feature{border-top:1px solid var(--rule);padding-top:32px;margin-bottom:56px;}
nav{display:flex;flex-wrap:wrap;gap:8px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
padding:16px 0;margin-bottom:48px;}
nav a{font-family:'Geist Mono',monospace;font-size:9px;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);text-decoration:none;border:1px solid var(--rule);border-radius:4px;padding:4px 8px;}
nav a:hover{color:var(--accent);border-color:var(--accent);}
.overview{font-size:16px;color:var(--ink);max-width:820px;margin:0 0 24px;}
.diagram{overflow-x:auto;margin-bottom:8px;}
.diagram svg{display:block;width:100%;min-width:1000px;height:auto;}
.stops{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin:8px 0 32px;}
.stop{background:#1e2330;border:1px solid var(--rule);border-radius:6px;padding:16px;}
.stop.deep{border-color:var(--accent);background:rgba(240,130,79,0.06);}
.tag{font-family:'Geist Mono',monospace;font-size:9px;letter-spacing:.14em;color:var(--accent);margin:0 0 8px;}
.badge{margin-left:8px;padding:1px 6px;border:1px solid var(--accent);border-radius:3px;font-size:8px;}
.stop dl{margin:0;font-size:13px;}
.stop dt{font-family:'Geist Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;
color:var(--soft);margin-top:10px;}
.stop dd{margin:2px 0 0;color:var(--muted);}
.stop dd.who{font-family:'Geist Mono',monospace;color:var(--ink);font-size:12px;}
.stop dd.hands{color:var(--ink);}
ul.code{list-style:none;margin:0;padding:0;}
ul.code li{margin:4px 0;}
ul.code a{text-decoration:none;display:block;}
ul.code .sym{font-family:'Geist Mono',monospace;font-size:11px;color:var(--ink);display:block;}
ul.code .loc{font-family:'Geist Mono',monospace;font-size:10px;color:#7aa5f7;word-break:break-all;}
ul.code a:hover .loc{text-decoration:underline;}
.blocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:24px;}
.block{border-top:1px solid var(--rule);padding-top:12px;color:var(--muted);}
.block p{margin:0;}
footer{border-top:1px solid var(--rule);padding-top:16px;font-family:'Geist Mono',monospace;
font-size:10px;color:var(--soft);line-height:1.8;}
@media (max-width:700px){.wrap{padding:32px 16px;}}
"""


def code_rows(rows, root) -> str:
    out = ""
    for path, lines, symbol in rows:
        full = path if path.startswith("/") else f"{root.rstrip('/')}/{path}"
        first = str(lines).split("-")[0]
        out += (
            f'<li><a href="vscode://file{esc(full)}:{esc(first)}">'
            f'<span class="sym">{esc(symbol)}</span>'
            f'<span class="loc">{esc(full)}:{esc(lines)}</span></a></li>'
        )
    return f'<ul class="code">{out}</ul>'


def stop_cards(stops, root) -> str:
    cards = ""
    for st in stops:
        deep = " deep" if any(k in st["name"].upper() for k in DEEP) else ""
        badge = '<span class="badge">CHANGED IN THIS SESSION</span>' if st.get("changed") else ""
        cards += (
            f'<article class="stop{deep}"><p class="tag">STOP {esc(st["n"])} · '
            f'{esc(st["name"].upper())}{badge}</p>'
            f'<dl><dt>who</dt><dd class="who">{esc(st["who"])}</dd>'
            f'<dt>what</dt><dd>{esc(st["what"])}</dd>'
            f'<dt>hands over</dt><dd class="hands">{esc(st["hands"])}</dd>'
            f"<dt>code</dt><dd>{code_rows(st['code'], root)}</dd></dl></article>"
        )
    return f'<div class="stops">{cards}</div>'


def closing(f) -> str:
    out = ""
    for key, label in (("failure", "ONE FAILURE"), ("choice", "ONE CHOICE AND WHY"), ("number", "ONE NUMBER")):
        if f.get(key):
            out += f'<div class="block"><p class="eyebrow">{label}</p><p>{esc(f[key])}</p></div>'
    return f'<div class="blocks">{out}</div>'


CADENCE = (
    "Interview cadence: 1. one-line overview. 2. draw the boxes. 3. walk the stops, "
    "short at the edges, deep in the middle. 4. one failure. 5. one choice and why. "
    "6. one number. Then stop and let them ask."
)


def build(spec: dict) -> str:
    feats = spec["features"]
    root = spec.get("root", "")
    for f in feats:
        slug = f["slug"]
        assert len(f["parts"]) <= 5, f"{slug}: more than 5 lifelines"
        assert len(f["msgs"]) <= 10, f"{slug}: more than 10 messages"
        assert sum(1 for m in f["msgs"] if m["kind"] == "ok") == 1, (
            f"{slug}: needs exactly one 'ok' message"
        )
        numbers = {st["n"] for st in f["stops"]}
        for m in f["msgs"]:
            assert m.get("stop") in numbers, f"{slug}: arrow {m['label']!r} names no known stop"
        for st in f["stops"]:
            assert st.get("hands"), f"{slug}: stop {st['n']} says nothing about what it hands over"
            assert st.get("code"), f"{slug}: stop {st['n']} points at no code"
            for row in st["code"]:
                assert len(row) == 3 and str(row[1]).replace("-", "").isdigit(), (
                    f"{slug}: stop {st['n']} code row {row!r} is not [path, 'start-end', symbol]"
                )
                assert row[0].startswith("/") or root, f"{slug}: relative path {row[0]!r} with no root"

    nav = (
        "<nav>" + "".join(f'<a href="#{f["slug"]}">{esc(f["title"])}</a>' for f in feats) + "</nav>"
        if len(feats) > 1 else ""
    )

    body = ""
    for f in feats:
        body += (
            f'<section class="feature" id="{f["slug"]}">'
            f'<p class="eyebrow">WALK THE REQUEST</p>'
            f'<h2>{esc(f["title"])}</h2><p class="overview">{esc(f["overview"])}</p>'
            f'<div class="diagram">{svg(f["slug"], f["title"], f["overview"], f["parts"], f["msgs"], f.get("frame"))}</div>'
            '<p class="eyebrow small">THE STOPS — SAME NUMBERS AS THE DIAGRAM GUTTER</p>'
            f'{stop_cards(f["stops"], root)}{closing(f)}</section>'
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(spec["title"])}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div class="wrap">
<p class="eyebrow">FLEARN</p>
<h1>{esc(spec["title"])}</h1>
<p class="sub">{esc(spec.get("subtitle", ""))}</p>
{nav}
{body}
<footer>{esc(CADENCE)}<br>{spec.get("footer", "")}</footer>
</div></body></html>"""


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: sequence.py <spec.json> <out.html>")
    with open(sys.argv[1]) as fh:
        spec = json.load(fh)
    with open(sys.argv[2], "w") as fh:
        fh.write(build(spec))
    total = sum(len(f["msgs"]) for f in spec["features"])
    print(f"{sys.argv[2]}  {len(spec['features'])} feature(s), {total} messages")
