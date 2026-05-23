"""音声解説ファイル生成モジュール（条文単位）"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import anthropic
from openai import OpenAI

ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
OPENAI_CLIENT = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

BASE_DIR  = Path(__file__).parent
TOC_FILE  = BASE_DIR / "オートマシステム民法１－３.txt"
SPEC_FILE = BASE_DIR / "音声解説機能.md"
AUDIO_DIR = BASE_DIR / "output" / "audio"

# ─── 民法一覧パーサ ────────────────────────────────────
# 音声解説機能.md の ＜民法一覧＞ セクションから
# 条文番号 → 正式名称 の辞書を作る

_article_titles: dict[int, str] | None = None


def parse_article_titles() -> dict[int, str]:
    """
    音声解説機能.md から全条文の見出しを抽出する。
    例: 第188条（即時取得） → {188: "即時取得"}
        第3条の2 → {302: ...} ※「の2」は別扱い（スキップ可）
    Returns dict[article_num, title]
    """
    global _article_titles
    if _article_titles is not None:
        return _article_titles

    result: dict[int, str] = {}
    try:
        text = None
        if SPEC_FILE.exists():
            text = SPEC_FILE.read_text(encoding="utf-8")
        else:
            # Dockerビルド後にファイル名が変わる場合のフォールバック
            for p in BASE_DIR.glob("*.md"):
                if "声解説" in p.name or "audio" in p.name.lower():
                    text = p.read_text(encoding="utf-8")
                    break
        if text:
            if "＜民法一覧＞" in text or "＜民法一覧＞" in text:
                marker = "＜民法一覧＞"
                if marker in text:
                    text = text[text.index(marker):]
            pattern = re.compile(r'第(\d+)条(?:（([^）]+)）)?')
            for m in pattern.finditer(text):
                num = int(m.group(1))
                title = m.group(2) or ""
                result[num] = title
    except Exception as e:
        print(f"parse_article_titles エラー: {e}")

    _article_titles = result
    return result


def get_article_title(article_num: int) -> str:
    """条文番号から正式名称を返す。なければ空文字。"""
    return parse_article_titles().get(article_num, "")


# ─── TOC パーサ ────────────────────────────────────────

def parse_toc() -> list[dict]:
    """
    オートマシステム目次テキストをパースしてトピック一覧を返す。
    各要素: { volume, part, part_title, chapter, chapter_title,
               topic_num, topic_title, articles }
    articles = 条文番号のリスト（例：[188, 192, 193]）
    """
    text = TOC_FILE.read_text(encoding="utf-8")
    results = []

    current_volume = 0
    current_part = 0
    current_part_title = ""
    current_chapter = 0
    current_chapter_title = ""

    vol_re   = re.compile(r'オートマシステム\s+(\d+)\s+民法')
    part_re  = re.compile(r'^第(\d+)部[　\s]+(.+)')
    chap_re  = re.compile(r'^第(\d+)章[　\s]*(.*)')
    topic_re = re.compile(r'^[　\s]+(\d+)\.\s+(.+)')

    for line in text.splitlines():
        stripped = line.strip()

        m = vol_re.search(stripped)
        if m:
            current_volume = int(m.group(1))
            current_part = 0
            current_chapter = 0
            continue

        m = part_re.match(stripped)
        if m:
            current_part = int(m.group(1))
            current_part_title = m.group(2).strip()
            current_chapter = 0
            continue

        m = chap_re.match(stripped)
        if m:
            current_chapter = int(m.group(1))
            current_chapter_title = m.group(2).strip()
            continue

        # 民法Ⅲ形式：「タイトル ／ 2. タイトル ／ ...」
        if '／' in stripped and current_chapter > 0:
            parts = [p.strip() for p in stripped.split('／')]
            for seg in parts:
                m2 = re.match(r'(\d+)\.\s+(.+)', seg)
                if m2:
                    topic_num = int(m2.group(1))
                    raw = m2.group(2).strip()
                else:
                    topic_num = 1
                    raw = seg.strip()
                if not raw:
                    continue
                articles = _extract_articles(raw)
                title = re.sub(r'\([^)]+\)', '', raw).strip()
                results.append(_entry(current_volume, current_part, current_part_title,
                                      current_chapter, current_chapter_title,
                                      topic_num, title, articles))
            continue

        # 通常トピック行
        m = topic_re.match(line)
        if m:
            topic_num = int(m.group(1))
            raw = m.group(2).strip()
            articles = _extract_articles(raw)
            title = re.sub(r'\([^)]+\)', '', raw).strip()
            results.append(_entry(current_volume, current_part, current_part_title,
                                  current_chapter, current_chapter_title,
                                  topic_num, title, articles))

    return results


def _entry(volume, part, part_title, chapter, chapter_title, topic_num, topic_title, articles):
    return {
        "volume": volume, "part": part, "part_title": part_title,
        "chapter": chapter, "chapter_title": chapter_title,
        "topic_num": topic_num, "topic_title": topic_title, "articles": articles,
    }


def _extract_articles(title: str) -> list[int]:
    """
    タイトル内の括弧から条文番号リストを抽出。
    「412条の2」などの混在も許容し、純粋な整数だけ返す。
    例: 利益衡量(188,192,193) → [188, 192, 193]
        帰責事由(555,412条の2,415) → [555, 415]
    """
    m = re.search(r'\(([^)]+)\)', title)
    if not m:
        return []
    return [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]


def find_topic(volume: int, part: int, chapter: int, topic_num: int) -> dict | None:
    for item in parse_toc():
        if (item["volume"] == volume and item["part"] == part
                and item["chapter"] == chapter and item["topic_num"] == topic_num):
            return item
    return None


def list_chapter_topics(volume: int, part: int, chapter: int) -> list[dict]:
    return [t for t in parse_toc()
            if t["volume"] == volume and t["part"] == part and t["chapter"] == chapter]


def list_parts(volume: int) -> list[dict]:
    seen = {}
    for t in parse_toc():
        if t["volume"] == volume:
            key = t["part"]
            if key not in seen:
                seen[key] = {"part": t["part"], "part_title": t["part_title"]}
    return list(seen.values())


def list_chapters(volume: int, part: int) -> list[dict]:
    seen = {}
    for t in parse_toc():
        if t["volume"] == volume and t["part"] == part:
            key = t["chapter"]
            if key not in seen:
                seen[key] = {"chapter": t["chapter"], "chapter_title": t["chapter_title"]}
    return list(seen.values())


# ─── ファイルパス ────────────────────────────────────────

def audio_article_path(article_num: int) -> Path:
    """条文番号からMP3ファイルパスを返す。番号はグローバルユニーク。"""
    return AUDIO_DIR / f"a{article_num}.mp3"


# ─── スクリプト生成 ────────────────────────────────────

ARTICLE_SCRIPT_PROMPT = """\
司法書士試験の勉強として、以下の条文について先生とともみの対話形式で音声解説スクリプトを作成してください。

【条文】民法第{article_num}条{title_part}
【トピック】{topic_title}（{chapter_title}）

【ルール】
- 先生（40代男性司法書士）：ため口・フレンドリー「〜んだよね」
- ともみ（30代女性見習い）：敬語・初学者として疑問を投げかける
- 先生から始めて交互に（先生→ともみ→先生→ともみ→先生）
- スピーカーラベル不要（台詞のみ）
- 1行 = 1発話（改行区切り）
- 合計10〜15行、500文字程度
- この条文の要点と試験に出るポイントを押さえる
- 条文番号を自然に会話に入れる

【出力】台詞のみ。前置き・説明・ラベル不要。"""


def generate_article_script(article_num: int, article_title: str,
                             topic_title: str, chapter_title: str) -> str:
    title_part = f"【{article_title}】" if article_title else ""
    resp = ANTHROPIC_CLIENT.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": ARTICLE_SCRIPT_PROMPT.format(
            article_num=article_num,
            title_part=title_part,
            topic_title=topic_title,
            chapter_title=chapter_title,
        )}]
    )
    return resp.content[0].text.strip()


# ─── TTS + MP3結合 ────────────────────────────────────

TTS_INSTRUCTIONS_TEACHER = (
    "日本語ネイティブの司法書士講師として、はきはきと速めのテンポで話してください。"
    "自然な日本語のイントネーションで、英語話者風の発音にならないようにしてください。"
    "ゆっくり丁寧すぎず、授業のテンポで明快に話してください。"
)
TTS_INSTRUCTIONS_TOMOMI = (
    "日本語ネイティブの女性として、自然なテンポで聞き取りやすく話してください。"
    "英語話者風の発音にならないようにしてください。"
)


def _tts_line(text: str, voice: str) -> bytes:
    instructions = TTS_INSTRUCTIONS_TEACHER if voice == "onyx" else TTS_INSTRUCTIONS_TOMOMI
    resp = OPENAI_CLIENT.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
        instructions=instructions,
        speed=1.15,  # 1.0がデフォルト、1.15で少し速め
    )
    return resp.content


def generate_audio_bytes(script: str) -> bytes:
    lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
    chunks = []
    for i, line in enumerate(lines):
        voice = "onyx" if i % 2 == 0 else "nova"
        print(f"  TTS [{voice}] {line[:30]}...")
        chunks.append(_tts_line(line, voice))
    return b"".join(chunks)


# ─── メイン生成関数 ────────────────────────────────────

def generate_article_audio(article_num: int, topic_title: str = "",
                            chapter_title: str = "") -> dict:
    """
    1条文の音声を生成してMP3を保存する。
    Returns: { "article_num", "article_title", "script", "file_path" }
    """
    article_title = get_article_title(article_num)

    # topic/chapter が渡されなければTOCから検索
    if not topic_title or not chapter_title:
        for t in parse_toc():
            if article_num in t["articles"]:
                topic_title = topic_title or t["topic_title"]
                chapter_title = chapter_title or t["chapter_title"]
                break

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = audio_article_path(article_num)

    label = f"第{article_num}条【{article_title}】" if article_title else f"第{article_num}条"
    print(f"スクリプト生成中: {label}")
    script = generate_article_script(article_num, article_title, topic_title, chapter_title)
    print("TTS処理中...")
    audio_bytes = generate_audio_bytes(script)
    out_path.write_bytes(audio_bytes)
    print(f"保存完了: {out_path.name}")

    return {
        "article_num": article_num,
        "article_title": article_title,
        "script": script,
        "file_path": str(out_path),
    }
