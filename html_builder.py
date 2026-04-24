"""
テキストを解析してHTMLページを生成する。
- 問題文・答え・解説・【図解】・まとめ表を自動検出して整形
- セリフをLINE風チャットバブルで表示
- SVGパネルを適切な位置に挿入
"""
import os
import re

HTML_HEAD = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TomomiとYasuの法律ストーリー</title>
<style>
* { box-sizing: border-box; }
body {
  font-family: 'Hiragino Kaku Gothic Pro', 'Meiryo', sans-serif;
  max-width: 860px;
  margin: 40px auto;
  padding: 0 24px 60px;
  background: #f4f4f0;
  color: #333;
  line-height: 1.9;
}
h1 {
  text-align: center;
  font-size: 20px;
  color: #444;
  border-bottom: 2px solid #bbb;
  padding-bottom: 14px;
  margin-bottom: 28px;
}
.story-block {
  background: white;
  padding: 20px 28px;
  border-radius: 10px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.08);
  margin: 16px 0;
  white-space: pre-wrap;
  font-size: 14.5px;
}
.problem-box {
  background: #f0f4ff;
  border-left: 5px solid #5577cc;
  padding: 20px 28px;
  border-radius: 0 10px 10px 0;
  margin: 16px 0;
  font-size: 15px;
  line-height: 2;
}
.problem-label {
  font-size: 12px;
  color: #5577cc;
  font-weight: bold;
  margin-bottom: 8px;
  letter-spacing: 0.05em;
}
.answer-box {
  background: white;
  border: 2px solid #ddd;
  border-radius: 10px;
  padding: 14px 24px;
  margin: 16px 0;
  display: flex;
  align-items: center;
  gap: 16px;
}
.answer-badge { font-size: 30px; }
.answer-main  { font-weight: bold; font-size: 16px; }
.answer-sub   { font-size: 14px; color: #666; }

/* ── チャットバブル ── */
.chat-section {
  background: #eae8e3;
  border-radius: 16px;
  padding: 20px 18px;
  margin: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.bubble-row-left  { display:flex; align-items:flex-start; gap:10px; justify-content:flex-start; }
.bubble-row-right { display:flex; align-items:flex-start; gap:10px; justify-content:flex-end; }
.avatar {
  width: 46px; height: 46px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #ccc;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.12);
}
.bubble-body { max-width: 74%; display: flex; flex-direction: column; }
.bubble-name {
  font-size: 11.5px;
  color: #666;
  margin-bottom: 4px;
  font-weight: bold;
  padding-left: 4px;
}
.bubble-name-right { text-align: right; padding-right: 4px; padding-left: 0; }
.bubble-yasu {
  position: relative;
  background: #ffffff;
  color: #1a1a1a;
  border-radius: 4px 18px 18px 18px;
  padding: 11px 15px;
  font-size: 14.5px;
  line-height: 1.8;
  white-space: pre-wrap;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12);
}
.bubble-yasu::before {
  content: '';
  position: absolute;
  top: 10px; left: -7px;
  border: 7px solid transparent;
  border-right-color: #ffffff;
  border-left: 0;
  filter: drop-shadow(-1px 0px 1px rgba(0,0,0,0.08));
}
.bubble-tomomi {
  position: relative;
  background: #dcf8c6;
  color: #1a1a1a;
  border-radius: 18px 4px 18px 18px;
  padding: 11px 15px;
  font-size: 14.5px;
  line-height: 1.8;
  white-space: pre-wrap;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12);
}
.bubble-tomomi::before {
  content: '';
  position: absolute;
  top: 10px; right: -7px;
  border: 7px solid transparent;
  border-left-color: #dcf8c6;
  border-right: 0;
  filter: drop-shadow(1px 0px 1px rgba(0,0,0,0.08));
}
.bubble-desc {
  font-size: 11px;
  color: #999;
  margin-top: 5px;
  font-style: italic;
  padding-left: 4px;
}
.bubble-desc-right { text-align: right; padding-right: 4px; padding-left: 0; }

/* ── パネル ── */
.panel-wrap   { margin: 24px 0; border-radius: 6px; overflow: hidden; border: 3px solid #222; box-shadow: 0 4px 16px rgba(0,0,0,0.18); }
.panel-label  { font-size: 12px; color: #888; margin-top: 6px; text-align: center; }

/* ── 解説カード ── */
.diagram-card {
  background: #fffbf0;
  border: 2px solid #e8c84a;
  border-radius: 12px;
  padding: 20px 26px;
  margin: 20px 0;
}
.diagram-title { font-weight:bold; color:#996600; font-size:15px; margin-bottom:14px; }
.diagram-row {
  display:flex; align-items:flex-start; padding:8px 0;
  border-bottom:1px dashed #e0cc80; font-size:14px; gap:12px;
}
.diagram-row:last-child { border-bottom:none; }
.d-key  { flex:0 0 220px; color:#555; }
.badge-ok { background:#4CAF50; color:white; border-radius:20px; padding:2px 10px; font-size:12px; font-weight:bold; white-space:nowrap; }
.badge-ng { background:#F44336; color:white; border-radius:20px; padding:2px 10px; font-size:12px; font-weight:bold; white-space:nowrap; }
.d-note { color:#888; font-size:13px; line-height:1.6; }
.conclusion-box {
  margin-top:14px; background:#fff0f0; border:2px solid #F44336;
  border-radius:8px; padding:12px 18px; font-weight:bold; color:#c00; font-size:14px;
}

/* ── まとめ表 ── */
.summary-wrap { background:white; padding:20px 28px; border-radius:10px; box-shadow:0 1px 6px rgba(0,0,0,0.08); margin:16px 0; }
.summary-label { font-weight:bold; color:#555; margin-bottom:12px; font-size:15px; }
.summary-table { width:100%; border-collapse:collapse; font-size:14px; }
.summary-table th { background:#555; color:white; padding:9px 14px; text-align:left; }
.summary-table td { padding:9px 14px; border-bottom:1px solid #eee; }
.summary-table tr:last-child td { border-bottom:none; }
.ok   { color:#4CAF50; font-weight:bold; }
.ng   { color:#F44336; font-weight:bold; }
.r-ng { color:#F44336; font-weight:bold; }
</style>
</head>
<body>
<h1>⚖️ TomomiとYasuの法律ストーリー</h1>
"""

HTML_FOOT = "</body></html>\n"

PANEL_TEMPLATE = """<div class="panel-wrap">{svg}</div>
<div class="panel-label">▲ {label}</div>
"""

# 「Yasu（感情）」だけの行、または「Yasu（感情）「セリフ...」」の両形式に対応
SPEAKER_RE = re.compile(r'^(Yasu|Tomomi)(（[^）]*）|\([^)]*\))?\s*(「.*|『.*)?$')


# ── チャットバブル ────────────────────────────────────────

def _make_bubble(speaker: str, desc: str, lines: list) -> str:
    text = "\n".join(lines).strip()
    if not text:
        return ""
    if speaker == "Tomomi":
        text = re.sub(r'Yasu(?!さん)', 'Yasuさん', text)
    text_esc = _escape(text)
    desc_esc  = _escape(desc.strip("（）()")) if desc else ""
    if speaker == "Yasu":
        name_html = f'<div class="bubble-name">👦 Yasu</div>'
        desc_html = f'<div class="bubble-desc">{desc_esc}</div>' if desc_esc else ""
        bubble    = f'<div class="bubble-yasu">{text_esc}</div>'
        return (f'<div class="bubble-row-left">'
                f'<div class="avatar">👦</div>'
                f'<div class="bubble-body">{name_html}{bubble}{desc_html}</div>'
                f'</div>')
    else:
        name_html = f'<div class="bubble-name bubble-name-right">Tomomi 👧</div>'
        desc_html = f'<div class="bubble-desc bubble-desc-right">{desc_esc}</div>' if desc_esc else ""
        bubble    = f'<div class="bubble-tomomi">{text_esc}</div>'
        return (f'<div class="bubble-row-right">'
                f'<div class="bubble-body">{name_html}{bubble}{desc_html}</div>'
                f'<div class="avatar">👧</div>'
                f'</div>')


# ── 解析ユーティリティ ────────────────────────────────────

def _is_table_header(line: str) -> bool:
    cols = re.split(r'[\t　 ]+', line.strip())
    keywords = {"バージョン", "善意", "無過失", "結果"}
    return len(cols) >= 3 and bool(keywords & set(cols))


def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 3


def _is_md_separator(line: str) -> bool:
    return bool(re.match(r'^\|[\s\-\|]+\|$', line.strip()))


def _md_inline(text: str) -> str:
    """**bold** → <strong>、`code` → <code>、> quote → blockquote"""
    text = _escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


def _parse_md_table(lines: list, start: int, label: str = "まとめ") -> tuple:
    html = f'<div class="summary-wrap"><div class="summary-label">📊 {label}</div><table class="summary-table">\n'
    i = start
    is_header = True
    while i < len(lines):
        l = lines[i].strip()
        if not l:
            break
        if _is_md_separator(l):
            i += 1; continue
        if not _is_md_table_row(l):
            break
        cols = [c.strip() for c in l.strip("|").split("|")]
        if is_header:
            html += "<tr>" + "".join(f"<th>{_md_inline(c)}</th>" for c in cols) + "</tr>\n"
            is_header = False
        else:
            def fmt(c):
                c2 = _md_inline(c)
                if c.strip() == "○": return f'<td class="ok">○</td>'
                if c.strip() == "×": return f'<td class="ng">×</td>'
                return f"<td>{c2}</td>"
            html += "<tr>" + "".join(fmt(c) for c in cols) + "</tr>\n"
        i += 1
    html += "</table></div>\n"
    return html, i


def _is_summary_label(line: str) -> bool:
    return "まとめ" in line and len(line.strip()) < 30


def _parse_diagram_block(lines: list, start: int) -> tuple:
    title = re.sub(r'^【|】$', '', lines[start].strip()).strip()
    rows, conclusion = [], ""
    i = start + 1
    while i < len(lines):
        s = lines[i].strip()
        if not s: i += 1; continue
        if s.startswith("【") and s.endswith("】"): break
        if not lines[i].startswith((" ", "　", "\t")) and s and i > start + 1 and not s.startswith("→"): break
        if "結論" in s or s.startswith("→"):
            conclusion += s + "<br>"
        else:
            rows.append(s)
        i += 1

    card = f'<div class="diagram-card"><div class="diagram-title">📋 {title}</div>\n'
    for row in rows:
        r = re.sub(r'→\s*○', '→ <span class="badge-ok">✅ ○</span>', row)
        r = re.sub(r'→\s*×', '→ <span class="badge-ng">❌ ×</span>', r)
        card += f'<div class="diagram-row"><div class="d-key">{r}</div></div>\n'
    if conclusion:
        card += f'<div class="conclusion-box">{conclusion}</div>\n'
    card += '</div>\n'
    return card, i


def _parse_table(lines: list, start: int, label: str = "まとめ") -> tuple:
    html = f'<div class="summary-wrap"><div class="summary-label">📊 {label}</div><table class="summary-table">\n'
    i = start
    is_header = True
    while i < len(lines):
        l = lines[i].strip()
        if not l:
            i += 1
            if i < len(lines) and not lines[i].strip(): break
            continue
        cols = [c.strip() for c in re.split(r'[\t　 ]+', l) if c.strip()]
        if len(cols) < 2: break
        if is_header:
            html += "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>\n"
            is_header = False
        else:
            def fmt(c):
                if c == "○": return f'<td class="ok">○</td>'
                if c == "×": return f'<td class="ng">×</td>'
                if re.search(r'×（', c): return f'<td class="ng">{c}</td>'
                if re.search(r'取得できない|返還', c): return f'<td class="r-ng">{c}</td>'
                return f"<td>{c}</td>"
            html += "<tr>" + "".join(fmt(c) for c in cols) + "</tr>\n"
        i += 1
    html += "</table></div>\n"
    return html, i


def _is_answer_line(line: str) -> bool:
    return line.strip().startswith("答え：") or line.strip().startswith("答え:")


def _parse_answer(line: str) -> str:
    text   = line.strip()
    badge  = "❌" if "×" in text else "⭕" if "○" in text else "❓"
    answer = text.replace("答え：", "").replace("答え:", "").strip()
    return (f'<div class="answer-box"><span class="answer-badge">{badge}</span>'
            f'<div><div class="answer-main">答え：{answer}</div></div></div>\n')


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _find_line(lines: list, marker: str) -> int:
    if not marker: return -1
    marker = marker.strip()
    for i, l in enumerate(lines):
        if marker and marker in l:
            return i + 1
    return -1


# ── メイン ───────────────────────────────────────────────

def build_html(data: dict, svg1: str, svg2: str, output_dir: str = "output", filename: str = "story.html") -> str:
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)

    full_text    = data.get("full_text", "")
    panel1_after = data.get("panel1_after", "")
    panel2_after = data.get("panel2_after", "")
    lines = full_text.split("\n")

    p1_idx = _find_line(lines, panel1_after)
    p2_idx = _find_line(lines, panel2_after)
    if p1_idx == -1: p1_idx = len(lines) // 3
    if p2_idx == -1 or p2_idx <= p1_idx: p2_idx = len(lines) * 2 // 3

    sections          = []
    panel1_inserted   = False
    panel2_inserted   = False
    in_problem        = False
    problem_buf       = []
    story_buf         = []
    # チャットバブル収集用
    chat_bubbles      = []   # list of HTML strings
    cur_speaker       = None
    cur_desc          = ""
    cur_lines         = []

    def flush_chat():
        nonlocal cur_speaker, cur_desc, cur_lines, chat_bubbles
        if cur_speaker and cur_lines:
            chat_bubbles.append(_make_bubble(cur_speaker, cur_desc, cur_lines))
        cur_speaker = None
        cur_desc    = ""
        cur_lines   = []

    def flush_chat_section():
        nonlocal chat_bubbles
        flush_chat()
        if chat_bubbles:
            html = '<div class="chat-section">\n' + "\n".join(chat_bubbles) + "\n</div>\n"
            chat_bubbles = []
            return html
        return ""

    def flush_story():
        nonlocal story_buf
        s = flush_chat_section()
        if story_buf:
            text = "\n".join(story_buf).strip()
            story_buf = []
            if text:
                html_text = _md_inline(text).replace("\n", "<br>")
                return s + f'<div class="story-block">{html_text}</div>\n'
        return s

    i = 0
    while i < len(lines):
        raw = lines[i]
        l   = raw.strip()

        # ── パネル2挿入チェック（位置ベース）──
        if not panel2_inserted and i >= p2_idx:
            sections.append(flush_story())
            sections.append(PANEL_TEMPLATE.format(svg=svg2, label="最後のシーン"))
            panel2_inserted = True

        # ── 答え行 → 直後にパネル1を挿入 ──
        if _is_answer_line(l):
            sections.append(flush_story())
            sections.append(_parse_answer(l))
            if not panel1_inserted:
                sections.append(PANEL_TEMPLATE.format(svg=svg1, label="最初のシーン"))
                panel1_inserted = True
            i += 1; continue

        # ── 【図解】ブロック ──
        if l.startswith("【") and l.endswith("】"):
            sections.append(flush_story())
            card, i = _parse_diagram_block(lines, i)
            sections.append(card)
            continue

        # ── 表（既存キーワード形式）──
        if _is_table_header(l):
            sections.append(flush_story())
            table_html, i = _parse_table(lines, i)
            sections.append(table_html)
            continue

        # ── Markdownテーブル（| col | 形式）──
        if _is_md_table_row(l) and not _is_md_separator(l):
            sections.append(flush_story())
            table_html, i = _parse_md_table(lines, i)
            sections.append(table_html)
            continue

        # ── まとめラベル ──
        if _is_summary_label(l):
            sections.append(flush_story())
            nxt = lines[i+1].strip() if i+1 < len(lines) else ""
            if _is_table_header(nxt):
                table_html, i = _parse_table(lines, i+1, label=l.strip())
                sections.append(table_html)
            elif _is_md_table_row(nxt):
                table_html, i = _parse_md_table(lines, i+1, label=re.sub(r'[\*#]+', '', l).strip())
                sections.append(table_html)
            else:
                story_buf.append(raw); i += 1
            continue

        # ── Markdown引用（> text）──
        if l.startswith("> "):
            sections.append(flush_story())
            quote = _md_inline(l[2:].strip())
            sections.append(f'<div class="conclusion-box">{quote}</div>\n')
            i += 1; continue

        # ── 問題文 ──
        if l == "問題文":
            sections.append(flush_story())
            in_problem = True; problem_buf = []; i += 1; continue

        if in_problem:
            if l == "" and problem_buf and any("○か" in ll or "×か" in ll for ll in problem_buf):
                in_problem = False
                body = "\n".join(problem_buf).strip()
                q_line, main_body = "", []
                for bl in body.split("\n"):
                    if "○か" in bl or "×か" in bl: q_line = bl
                    else: main_body.append(bl)
                sections.append(
                    f'<div class="problem-box"><div class="problem-label">📝 問題文</div>'
                    f'{_escape(chr(10).join(main_body))}'
                    + (f'<br><br><strong>{_escape(q_line)}</strong>' if q_line else "")
                    + '</div>\n')
                problem_buf = []
            else:
                if l or problem_buf: problem_buf.append(raw)
            i += 1; continue

        # ── スキップ行 ──
        if l in ("解説", "答えを見る前に考えてみてください↓"):
            i += 1; continue

        # ── スピーカー行（Yasu / Tomomi） ──
        m = SPEAKER_RE.match(l)
        if m:
            flush_chat()
            if story_buf:
                sections.append(flush_story())
            cur_speaker = m.group(1)
            cur_desc    = m.group(2) or ""
            inline_text = m.group(3) or ""
            cur_lines   = [inline_text] if inline_text else []
            i += 1; continue

        # ── セリフ行（「で始まる）or スピーカー直後の継続行 ──
        if cur_speaker is not None:
            if l.startswith("「") or l.startswith("『") or (l and not l.startswith("【")):
                cur_lines.append(raw)
                i += 1; continue
            else:
                # セリフ終了
                flush_chat()

        # ── 空行でチャットセクション区切り ──
        if l == "" and chat_bubbles:
            # 空行はセクション内のスペースとして許容（flush しない）
            i += 1; continue

        # ── 通常テキスト ──
        if chat_bubbles and cur_speaker is None:
            sections.append(flush_chat_section())
        story_buf.append(raw)
        i += 1

    sections.append(flush_story())
    if not panel1_inserted:
        sections.insert(max(1, len(sections)//2),
                        PANEL_TEMPLATE.format(svg=svg1, label="最初のシーン"))
    if not panel2_inserted:
        sections.append(PANEL_TEMPLATE.format(svg=svg2, label="最後のシーン"))

    html = HTML_HEAD + "".join(s for s in sections if s) + HTML_FOOT
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML出力完了: {out_path}")
    return out_path
