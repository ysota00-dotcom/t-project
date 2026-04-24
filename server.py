"""
Tomomi Learning UI — FastAPIサーバー
起動: python server.py
"""
import os
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic

from knowledge_db import init_db, seed, list_all, search, insert_question, get_by_unit_num

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

OUTPUT_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI()

# 生成中ステータス管理
_generating: dict[str, str] = {}  # key: "unit-num" → "running" | "done" | "error"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TOMOMI_SYSTEM = """あなたは「Tomomi」という30代の見習い司法書士です。
ユーザーの法律に関する質問に、以下のキャラクターで答えてください。

- 口調：ため口、でもやさしい口調
- 一人称：私
- 性格：穏やか、論理的、相手の誤解を優しく正す
- 口癖：「そうやね、ポイントは〜」「民法○条がそう定めてるんよ」「いい質問やね！」
- 相手のことは「Yasuさん」と呼ぶ（名前がわからない場合はそのまま）
- 条文番号をさりげなく入れる
- 長くなりすぎず200文字以内でまとめる"""

# ────────────────────────────────────────────────
# 起動時初期化
# ────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    seed()


# ────────────────────────────────────────────────
# 問題API
# ────────────────────────────────────────────────
@app.get("/api/questions")
def api_list():
    return list_all()


@app.get("/api/questions/search")
def api_search(q: str = ""):
    if not q:
        return list_all()
    return search(q)


class QuestionIn(BaseModel):
    unit: str
    law: str = ""
    question_num: int
    question_text: str
    answer: str
    explanation: str = ""
    exam_source: str = ""


@app.post("/api/questions")
def api_create(q: QuestionIn):
    insert_question(
        unit=q.unit, law=q.law, question_num=q.question_num,
        question_text=q.question_text, answer=q.answer,
        explanation=q.explanation, exam_source=q.exam_source,
    )
    return {"ok": True}


# ────────────────────────────────────────────────
# ストーリー生成API
# ────────────────────────────────────────────────
def _run_generate(unit: str, question_num: int):
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
        fname = f"story_{question_num:02d}.html"
        build_html(data, svg1, svg2, str(OUTPUT_DIR), filename=fname)
        _generating[key] = "done"
    except Exception as e:
        _generating[key] = f"error: {e}"


@app.post("/api/generate/{question_num}")
def api_generate(question_num: int, unit: str = "即時取得", force: bool = False):
    key = f"{unit}-{question_num}"
    if _generating.get(key) == "running":
        return {"status": "running"}
    fname = OUTPUT_DIR / f"story_{question_num:02d}.html"
    if fname.exists() and not force:
        return {"status": "done"}
    if fname.exists() and force:
        fname.unlink()
    t = threading.Thread(target=_run_generate, args=(unit, question_num), daemon=True)
    t.start()
    return {"status": "running"}


@app.get("/api/status/{question_num}")
def api_status(question_num: int, unit: str = "即時取得"):
    key   = f"{unit}-{question_num}"
    fname = OUTPUT_DIR / f"story_{question_num:02d}.html"
    if fname.exists():
        return {"status": "done", "url": f"/output/story_{question_num:02d}.html"}
    st = _generating.get(key, "idle")
    return {"status": st}


# ────────────────────────────────────────────────
# チャットAPI
# ────────────────────────────────────────────────
class ChatIn(BaseModel):
    messages: list[dict]   # [{"role":"user"|"assistant","content":"..."}]


@app.post("/api/chat")
def api_chat(body: ChatIn):
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=TOMOMI_SYSTEM,
        messages=body.messages,
    )
    return {"reply": resp.content[0].text.strip()}


# ────────────────────────────────────────────────
# 静的ファイル配信
# ────────────────────────────────────────────────
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
