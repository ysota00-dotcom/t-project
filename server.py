"""
Tomomi Learning UI — FastAPIサーバー
起動: python server.py
"""
import os
import json
import re
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic

from knowledge_db import init_db, seed, list_all, search, search_knowledge, insert_question, get_by_unit_num, list_by_chapter, count_by_chapter, get_drill_questions, save_drill_questions, delete_drill_questions, delete_questions_by_ids, get_all_progress, set_progress, get_past_exam_questions, get_past_exam_years, count_past_exam_by_chapter, get_past_exam_by_chapter, upsert_past_exam_tag, save_audio_lesson, get_audio_lesson, list_audio_lessons_by_chapter, save_audio_article, get_audio_article, list_audio_articles_by_nums

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

OUTPUT_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI()

# 生成中ステータス管理
_generating: dict[str, str] = {}  # key: "unit-num" → "running" | "done" | "error"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TOMOMI_SYSTEM_BASE = """あなたは「Tomomi」という30代の見習い司法書士です。
ユーザーの法律に関する質問に、以下のキャラクターで答えてください。

- 口調：ため口、でもやさしい口調
- 一人称：私
- 性格：穏やか、論理的、相手の誤解を優しく正す
- 口癖：「そうやね、ポイントは〜」「民法○条がそう定めてるんよ」「いい質問やね！」
- 相手のことは「Yasuさん」と呼ぶ（名前がわからない場合はそのまま）
- 条文番号をさりげなく入れる
- 長くなりすぎず250文字以内でまとめる"""


def build_system(query: str) -> str:
    try:
        hits = search_knowledge(query)
    except Exception:
        hits = []
    if not hits:
        return TOMOMI_SYSTEM_BASE
    context = "\n\n".join(
        f"[{h['title']}]({h['law']})\n{h['content']}" for h in hits
    )
    return (
        TOMOMI_SYSTEM_BASE
        + f"\n\n---\n以下の資料を参考に答えること。資料の存在やシステムについては一切言及しないこと。\n{context}\n---"
    )

# ────────────────────────────────────────────────
# 起動時初期化
# ────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    seed()
    def _import_and_tag():
        try:
            from import_past_exams import import_all
            import_all()
        except Exception as e:
            print(f"過去問インポートエラー: {e}")
            return
        try:
            from tag_past_exams import tag_all
            tag_all()
        except Exception as e:
            print(f"過去問タグ付けエラー: {e}")
    threading.Thread(target=_import_and_tag, daemon=True).start()


# ────────────────────────────────────────────────
# 問題API
# ────────────────────────────────────────────────
@app.get("/api/questions")
def api_list(book: int = 0, part: int = 0, chapter: int = 0):
    if book or part or chapter:
        return list_by_chapter(book, part, chapter)
    return list_all()


@app.get("/api/questions/search")
def api_search(q: str = ""):
    if not q:
        return list_all()
    return search(q)


@app.get("/api/chapters/counts")
def api_chapter_counts():
    return count_by_chapter()


class QuestionIn(BaseModel):
    unit: str
    law: str = ""
    question_num: int
    question_text: str
    answer: str
    explanation: str = ""
    exam_source: str = ""
    book: int = 0
    part: int = 0
    chapter: int = 0
    topic: str = ""


@app.post("/api/questions")
def api_create(q: QuestionIn):
    insert_question(
        unit=q.unit, law=q.law, question_num=q.question_num,
        question_text=q.question_text, answer=q.answer,
        explanation=q.explanation, exam_source=q.exam_source,
        book=q.book, part=q.part, chapter=q.chapter, topic=q.topic,
    )
    return {"ok": True}


# ────────────────────────────────────────────────
# 脳トレAPI
# ────────────────────────────────────────────────
def _generate_drill(originals: list) -> list:
    import random
    orig_json = json.dumps([
        {"question_num": q["question_num"], "question_text": q["question_text"],
         "answer": q["answer"], "explanation": q.get("explanation", "")}
        for q in originals
    ], ensure_ascii=False, indent=2)

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        messages=[{"role": "user", "content": f"""司法書士試験の練習問題として、以下の問題集のバリエーション問題を{len(originals)}問作成してください。

【元問題】
{orig_json}

【バリエーションのルール】各問題に対し、以下のいずれかを適用してください：
- 登場人物の名前や物の種類を変える（例：カメラ→バイク、A→C）
- 同じ法的論点を別の状況・言い回しで表現する
- 条件を少し変えて正解の○×を逆転させる
- 論点の応用・発展問題にする

【出力形式】以下のJSON配列のみ出力してください（前置き・説明は不要）：
[{{"question_num":1,"question_text":"問題文","answer":"○","explanation":"解説"}},...]

必ず{len(originals)}問すべてを作成してください。法的に正確に。"""}]
    )

    text = resp.content[0].text.strip()
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        raise ValueError("JSON配列が見つかりません")
    data = json.loads(match.group())
    random.shuffle(data)
    return data


@app.get("/api/drill")
def api_drill_get(book: int = 0, part: int = 0, chapter: int = 0):
    cached = get_drill_questions(book, part, chapter)
    if cached:
        return cached
    originals = list_by_chapter(book, part, chapter)
    if not originals:
        return []
    generated = _generate_drill(originals)
    save_drill_questions(book, part, chapter, generated)
    return generated


@app.delete("/api/drill")
def api_drill_delete(book: int = 0, part: int = 0, chapter: int = 0):
    delete_drill_questions(book, part, chapter)
    return {"ok": True}


# ────────────────────────────────────────────────
# ストーリー生成API
# ────────────────────────────────────────────────
_auto_queue: dict[str, dict] = {}  # key: "book-part-chapter" → state dict


def _chapter_key(book: int, part: int, chapter: int) -> str:
    return f"{book}-{part}-{chapter}"


def _do_generate(unit: str, question_num: int):
    """同期的に1問生成する（スレッド内から呼ぶ）"""
    key = f"{unit}-{question_num}"
    try:
        _generating[key] = "running"
        from story_generator import generate_story
        from scene_extractor import extract_scenes
        from svg_renderer import render_panel
        from html_builder import build_html

        story = generate_story(unit, question_num)
        data  = extract_scenes(story)
        prop_name = data.get("prop", {}).get("name", "")
        svg1  = render_panel(data["scene_01"], prop_name)
        svg2  = render_panel(data["scene_02"], prop_name)
        fname = f"story_{unit}_{question_num:02d}.html"
        build_html(data, svg1, svg2, str(OUTPUT_DIR), filename=fname)
        _generating[key] = "done"
    except Exception as e:
        _generating[key] = f"error: {e}"


def _run_auto_queue(book: int, part: int, chapter: int):
    import time as _time
    key = _chapter_key(book, part, chapter)
    questions = list_by_chapter(book, part, chapter)
    pending = [q for q in questions
               if not (OUTPUT_DIR / f"story_{q['unit']}_{q['question_num']:02d}.html").exists()]
    total = len(questions)
    already_done = total - len(pending)

    _auto_queue[key] = {
        "status": "running", "total": total,
        "done": already_done, "queued": len(pending),
        "current": None, "errors": 0,
    }

    for q in pending:
        num  = q["question_num"]
        unit = q["unit"]
        fname = OUTPUT_DIR / f"story_{unit}_{num:02d}.html"

        if fname.exists():
            _auto_queue[key]["done"]   += 1
            _auto_queue[key]["queued"] -= 1
            continue

        gen_key = f"{unit}-{num}"
        while _generating.get(gen_key) == "running":
            _time.sleep(2)
        if fname.exists():
            _auto_queue[key]["done"]   += 1
            _auto_queue[key]["queued"] -= 1
            continue

        _auto_queue[key]["current"] = num
        _auto_queue[key]["queued"] -= 1
        _do_generate(unit, num)
        _auto_queue[key]["current"] = None

        if fname.exists():
            _auto_queue[key]["done"] += 1
        else:
            _auto_queue[key]["errors"] += 1

    _auto_queue[key]["status"] = "done"


@app.post("/api/generate/auto")
def api_generate_auto(book: int = 0, part: int = 0, chapter: int = 0):
    key = _chapter_key(book, part, chapter)
    if _auto_queue.get(key, {}).get("status") == "running":
        return {"status": "already_running", "count": 0}
    questions = list_by_chapter(book, part, chapter)
    pending = [q for q in questions
               if not (OUTPUT_DIR / f"story_{q['unit']}_{q['question_num']:02d}.html").exists()]
    if not pending:
        return {"status": "all_done", "count": 0}
    threading.Thread(target=_run_auto_queue, args=(book, part, chapter), daemon=True).start()
    return {"status": "queued", "count": len(pending)}


@app.get("/api/generate/auto/status")
def api_generate_auto_status(book: int = 0, part: int = 0, chapter: int = 0):
    key = _chapter_key(book, part, chapter)
    questions = list_by_chapter(book, part, chapter)
    total = len(questions)
    done_count = sum(
        1 for q in questions
        if (OUTPUT_DIR / f"story_{q['unit']}_{q['question_num']:02d}.html").exists()
    )
    state = _auto_queue.get(key)
    if not state:
        return {"status": "idle", "total": total, "done": done_count,
                "queued": 0, "running": 0, "errors": 0, "current": None}
    return {
        "status": state["status"],
        "total": total,
        "done": done_count,
        "queued": state.get("queued", 0),
        "running": 1 if state.get("current") is not None else 0,
        "errors": state.get("errors", 0),
        "current": state.get("current"),
    }


@app.post("/api/generate/{question_num}")
def api_generate(question_num: int, unit: str = "即時取得", force: bool = False):
    key = f"{unit}-{question_num}"
    if _generating.get(key) == "running":
        return {"status": "running"}
    fname = OUTPUT_DIR / f"story_{unit}_{question_num:02d}.html"
    if fname.exists() and not force:
        return {"status": "done"}
    if fname.exists() and force:
        fname.unlink()
    threading.Thread(target=_do_generate, args=(unit, question_num), daemon=True).start()
    return {"status": "running"}


@app.get("/api/status/{question_num}")
def api_status(question_num: int, unit: str = "即時取得"):
    key   = f"{unit}-{question_num}"
    fname = OUTPUT_DIR / f"story_{unit}_{question_num:02d}.html"
    if fname.exists():
        return {"status": "done", "url": f"/output/story_{unit}_{question_num:02d}.html"}
    st = _generating.get(key, "idle")
    return {"status": st}


# ────────────────────────────────────────────────
# 進捗API
# ────────────────────────────────────────────────
@app.get("/api/progress/all")
def api_progress_all():
    return get_all_progress()


class ProgressIn(BaseModel):
    key: str
    value: str  # JSON文字列


@app.post("/api/progress")
def api_progress_set(body: ProgressIn):
    set_progress(body.key, body.value)
    return {"ok": True}


# ────────────────────────────────────────────────
# チャットAPI
# ────────────────────────────────────────────────
class ChatIn(BaseModel):
    messages: list[dict]   # [{"role":"user"|"assistant","content":"..."}]


@app.post("/api/chat")
def api_chat(body: ChatIn):
    # 直近のユーザー発言でDBを検索し、ヒット内容をシステムプロンプトに注入
    last_user = next(
        (m["content"] for m in reversed(body.messages) if m["role"] == "user"), ""
    )
    system = build_system(last_user)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=system,
        messages=body.messages,
    )
    return {"reply": resp.content[0].text.strip()}


# ────────────────────────────────────────────────
# 過去問API
# ────────────────────────────────────────────────
@app.get("/api/past-exam/years")
def api_past_exam_years():
    return get_past_exam_years()


@app.get("/api/past-exam/questions")
def api_past_exam_questions(year: int, part: str):
    return get_past_exam_questions(year, part)


@app.get("/api/past-exam/count-by-chapter")
def api_past_exam_count_by_chapter():
    return count_past_exam_by_chapter()


@app.get("/api/past-exam/by-chapter")
def api_past_exam_by_chapter(book: int, part_num: int, chapter: int):
    return get_past_exam_by_chapter(book, part_num, chapter)


class PastExamTagIn(BaseModel):
    year: int
    part: str
    question_num: int
    book: int = 0
    part_num: int = 0
    chapter: int = 0
    subject: str = ""


@app.post("/api/past-exam/tag")
def api_past_exam_tag(t: PastExamTagIn):
    upsert_past_exam_tag(t.year, t.part, t.question_num, t.book, t.part_num, t.chapter, t.subject)
    return {"ok": True}


# ────────────────────────────────────────────────
# 音声解説API（条文単位）
# ────────────────────────────────────────────────
_article_generating: dict[int, str] = {}  # article_num → "running"|"done"|"error:..."


def _do_generate_article(article_num: int, topic_title: str = "", chapter_title: str = ""):
    try:
        _article_generating[article_num] = "running"
        from audio_generator import generate_article_audio, audio_article_path
        result = generate_article_audio(article_num, topic_title, chapter_title)
        rel_path = f"/output/audio/{audio_article_path(article_num).name}"
        save_audio_article(article_num, result["article_title"], result["script"], rel_path)
        _article_generating[article_num] = "done"
    except Exception as e:
        _article_generating[article_num] = f"error: {e}"
        print(f"音声生成エラー [第{article_num}条]: {e}")


class ArticleGenerateIn(BaseModel):
    article_num: int
    topic_title: str = ""
    chapter_title: str = ""


@app.post("/api/audio/generate")
def api_audio_generate(body: ArticleGenerateIn):
    num = body.article_num
    if _article_generating.get(num) == "running":
        return {"status": "running"}
    from audio_generator import audio_article_path
    fpath = BASE_DIR / "output" / "audio" / audio_article_path(num).name
    if fpath.exists():
        return {"status": "already_done", "url": f"/output/audio/{fpath.name}"}
    threading.Thread(
        target=_do_generate_article,
        args=(num, body.topic_title, body.chapter_title),
        daemon=True
    ).start()
    return {"status": "queued"}


@app.get("/api/audio/status")
def api_audio_status(article_num: int):
    from audio_generator import audio_article_path
    fpath = BASE_DIR / "output" / "audio" / audio_article_path(article_num).name
    if fpath.exists():
        return {"status": "done", "url": f"/output/audio/{fpath.name}"}
    return {"status": _article_generating.get(article_num, "idle")}


@app.get("/api/audio/list")
def api_audio_list(volume: int, part: int, chapter: int):
    """章内の全トピックをトピック→条文の階層で返す。条文ごとに生成ステータス付き。"""
    from audio_generator import list_chapter_topics, audio_article_path, get_article_title
    topics = list_chapter_topics(volume, part, chapter)

    # 全条文番号を集めてDB一括取得
    all_nums = [n for t in topics for n in t["articles"]]
    try:
        db_map = {r["article_num"]: r for r in list_audio_articles_by_nums(all_nums)}
    except Exception as e:
        print(f"audio_articles DB エラー: {e}")
        db_map = {}

    result = []
    for t in topics:
        articles = []
        for num in t["articles"]:
            fpath = BASE_DIR / "output" / "audio" / audio_article_path(num).name
            if fpath.exists():
                status = "done"
                url = f"/output/audio/{fpath.name}"
            elif _article_generating.get(num) == "running":
                status = "running"
                url = None
            else:
                status = "idle"
                url = None
            articles.append({
                "article_num": num,
                "article_title": get_article_title(num),
                "status": status,
                "url": url,
            })
        result.append({
            "topic_num": t["topic_num"],
            "topic_title": t["topic_title"],
            "articles": articles,
        })
    return result


@app.get("/api/audio/toc")
def api_audio_toc():
    from audio_generator import parse_toc
    toc = parse_toc()
    tree: dict = {}
    for t in toc:
        v, p, c = t["volume"], t["part"], t["chapter"]
        tree.setdefault(v, {"volume": v, "parts": {}})
        tree[v]["parts"].setdefault(p, {"part": p, "part_title": t["part_title"], "chapters": {}})
        tree[v]["parts"][p]["chapters"].setdefault(c, {"chapter": c, "chapter_title": t["chapter_title"]})
    volumes = []
    for v in sorted(tree):
        parts = []
        for p in sorted(tree[v]["parts"]):
            chapters = [tree[v]["parts"][p]["chapters"][c]
                        for c in sorted(tree[v]["parts"][p]["chapters"])]
            parts.append({**tree[v]["parts"][p], "chapters": chapters})
        volumes.append({"volume": v, "parts": parts})
    return volumes


# ────────────────────────────────────────────────
# 静的ファイル配信
# ────────────────────────────────────────────────
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _no_cache(path: str) -> FileResponse:
    resp = FileResponse(path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/")
def root():
    return _no_cache(str(STATIC_DIR / "index.html"))


@app.get("/journey")
def journey():
    return _no_cache(str(BASE_DIR / "index.html"))


@app.get("/{name}.png")
def serve_png(name: str):
    f = BASE_DIR / f"{name}.png"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(str(f))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
