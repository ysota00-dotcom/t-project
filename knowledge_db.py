"""
ナレッジDB — SQLite + FTS5
使い方:
  python knowledge_db.py              # シード実行（11問を投入）
  python knowledge_db.py --search 公信力
  python knowledge_db.py --search 無過失
  python knowledge_db.py --list
"""
import sqlite3
import os
import argparse

DB_PATH      = os.path.join(os.path.dirname(__file__), "output", "knowledge.db")
REPLICA_PATH = os.path.join(os.path.dirname(__file__), "output", "knowledge_replica.db")
TURSO_URL    = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN  = os.environ.get("TURSO_AUTH_TOKEN")


class _Row(dict):
    """libsql のタプル行を dict + 整数インデックスでアクセス可能なオブジェクトに変換"""
    def __init__(self, row, description):
        cols = [d[0] for d in description]
        super().__init__(zip(cols, row))
        self._vals = list(row)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, cursor, is_turso: bool):
        self._c = cursor
        self._turso = is_turso

    def _wrap(self, row):
        if self._turso and row is not None:
            return _Row(row, self._c.description)
        return row

    def fetchall(self):
        rows = self._c.fetchall()
        if self._turso:
            return [_Row(r, self._c.description) for r in rows]
        return rows

    def fetchone(self):
        return self._wrap(self._c.fetchone())

    def __getitem__(self, key):
        return self.fetchone()[key]

    @property
    def description(self):
        return self._c.description


class _Conn:
    """sqlite3 / libsql を統一インターフェースで扱うラッパー"""
    def __init__(self, conn, is_turso: bool):
        self._conn = conn
        self._turso = is_turso

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            try:
                self._conn.commit()
                if self._turso:
                    self._conn.sync()
            except Exception:
                pass
        try:
            self._conn.close()
        except Exception:
            pass
        return False

    def execute(self, sql: str, params=()):
        cur = self._conn.execute(sql, params)
        return _Cursor(cur, self._turso)

    def executemany(self, sql: str, seq):
        self._conn.executemany(sql, seq)
        if self._turso:
            self._conn.commit()


def get_conn() -> _Conn:
    if TURSO_URL and TURSO_TOKEN:
        import libsql_experimental as libsql  # noqa
        os.makedirs(os.path.dirname(REPLICA_PATH), exist_ok=True)
        conn = libsql.connect(REPLICA_PATH, sync_url=TURSO_URL, auth_token=TURSO_TOKEN)
        return _Conn(conn, is_turso=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return _Conn(conn, is_turso=False)


def init_db():
    # 起動時にTursoから最新状態をローカルレプリカに同期
    if TURSO_URL and TURSO_TOKEN:
        try:
            import libsql_experimental as libsql
            os.makedirs(os.path.dirname(REPLICA_PATH), exist_ok=True)
            c = libsql.connect(REPLICA_PATH, sync_url=TURSO_URL, auth_token=TURSO_TOKEN)
            c.sync()
            c.close()
        except Exception as e:
            print(f"Turso sync warning: {e}")

    stmts = [
        """CREATE TABLE IF NOT EXISTS questions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            unit           TEXT    NOT NULL,
            law            TEXT,
            question_num   INTEGER,
            question_text  TEXT    NOT NULL,
            answer         TEXT    NOT NULL,
            explanation    TEXT,
            exam_source    TEXT,
            book           INTEGER DEFAULT 0,
            part           INTEGER DEFAULT 0,
            chapter        INTEGER DEFAULT 0,
            topic          TEXT    DEFAULT '',
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts
        USING fts5(
            unit, question_text, answer, explanation, exam_source,
            content='questions', content_rowid='id', tokenize='trigram'
        )""",
        """CREATE TRIGGER IF NOT EXISTS questions_ai AFTER INSERT ON questions BEGIN
            INSERT INTO questions_fts(rowid, unit, question_text, answer, explanation, exam_source)
            VALUES (new.id, new.unit, new.question_text, new.answer, new.explanation, new.exam_source);
        END""",
        """CREATE TRIGGER IF NOT EXISTS questions_ad AFTER DELETE ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, unit, question_text, answer, explanation, exam_source)
            VALUES ('delete', old.id, old.unit, old.question_text, old.answer, old.explanation, old.exam_source);
        END""",
        """CREATE TRIGGER IF NOT EXISTS questions_au AFTER UPDATE ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, unit, question_text, answer, explanation, exam_source)
            VALUES ('delete', old.id, old.unit, old.question_text, old.answer, old.explanation, old.exam_source);
            INSERT INTO questions_fts(rowid, unit, question_text, answer, explanation, exam_source)
            VALUES (new.id, new.unit, new.question_text, new.answer, new.explanation, new.exam_source);
        END""",
        """CREATE TABLE IF NOT EXISTS drill_questions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            book         INTEGER NOT NULL,
            part         INTEGER NOT NULL,
            chapter      INTEGER NOT NULL,
            question_num INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            answer       TEXT NOT NULL,
            explanation  TEXT DEFAULT '',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS past_exam_questions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            year          INTEGER NOT NULL,
            part          TEXT    NOT NULL,
            question_num  INTEGER NOT NULL,
            question_text TEXT    NOT NULL,
            choices       TEXT    NOT NULL DEFAULT '[]',
            correct       INTEGER,
            subject       TEXT    DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(year, part, question_num)
        )""",
        """CREATE TABLE IF NOT EXISTS past_exam_tags (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            year          INTEGER NOT NULL,
            part          TEXT    NOT NULL,
            question_num  INTEGER NOT NULL,
            book          INTEGER DEFAULT 0,
            part_num      INTEGER DEFAULT 0,
            chapter       INTEGER DEFAULT 0,
            subject       TEXT    DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(year, part, question_num)
        )""",
        """CREATE TABLE IF NOT EXISTS knowledge (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            unit       TEXT NOT NULL,
            category   TEXT,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL,
            law        TEXT,
            source     TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(
            unit, category, title, content, law,
            content='knowledge', content_rowid='id', tokenize='trigram'
        )""",
        """CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
            INSERT INTO knowledge_fts(rowid, unit, category, title, content, law)
            VALUES (new.id, new.unit, new.category, new.title, new.content, new.law);
        END""",
        """CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, unit, category, title, content, law)
            VALUES ('delete', old.id, old.unit, old.category, old.title, old.content, old.law);
        END""",
        """CREATE TABLE IF NOT EXISTS user_progress (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS audio_lessons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            volume      INTEGER NOT NULL,
            part        INTEGER NOT NULL,
            chapter     INTEGER NOT NULL,
            topic_num   INTEGER NOT NULL,
            topic_title TEXT,
            script      TEXT,
            file_path   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(volume, part, chapter, topic_num)
        )""",
        """CREATE TABLE IF NOT EXISTS audio_articles (
            article_num  INTEGER PRIMARY KEY,
            article_title TEXT,
            script       TEXT,
            file_path    TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    with get_conn() as conn:
        for stmt in stmts:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # 既に存在するテーブル・トリガーはスキップ


def migrate_columns():
    """既存DBにbook/part/chapterカラムを追加（なければ）"""
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
        if "book" not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN book INTEGER DEFAULT 0")
        if "part" not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN part INTEGER DEFAULT 0")
        if "chapter" not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN chapter INTEGER DEFAULT 0")
        if "topic" not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN topic TEXT DEFAULT ''")


def migrate_existing_data():
    """既存の即時取得データを 民法Ⅰ 基本編 第1章 に移行"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE questions SET book=1, part=1, chapter=1 WHERE unit='即時取得' AND (book IS NULL OR book=0)"
        )


def migrate_topics():
    """SEED_QUESTIONSのtopicでtopicが空の既存行を更新"""
    topic_map = {q["question_num"]: q["topic"] for q in SEED_QUESTIONS}
    with get_conn() as conn:
        for num, topic in topic_map.items():
            conn.execute(
                "UPDATE questions SET topic=? WHERE unit='即時取得' AND question_num=? AND (topic IS NULL OR topic='')",
                (topic, num)
            )


def insert_question(unit, law, question_num, question_text, answer, explanation, exam_source="", book=0, part=0, chapter=0, topic=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO questions
               (unit, law, question_num, question_text, answer, explanation, exam_source, book, part, chapter, topic)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (unit, law, question_num, question_text, answer, explanation, exam_source, book, part, chapter, topic)
        )


def get_drill_questions(book: int, part: int, chapter: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question_num, question_text, answer, explanation FROM drill_questions "
            "WHERE book=? AND part=? AND chapter=? ORDER BY question_num",
            (book, part, chapter)
        ).fetchall()
    return [dict(r) for r in rows]


def save_drill_questions(book: int, part: int, chapter: int, questions: list):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM drill_questions WHERE book=? AND part=? AND chapter=?",
            (book, part, chapter)
        )
        for q in questions:
            conn.execute(
                "INSERT INTO drill_questions (book, part, chapter, question_num, question_text, answer, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book, part, chapter, q["question_num"], q["question_text"], q["answer"], q.get("explanation", ""))
            )


def delete_drill_questions(book: int, part: int, chapter: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM drill_questions WHERE book=? AND part=? AND chapter=?",
            (book, part, chapter)
        )


def get_all_progress() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM user_progress").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_progress(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_progress (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value)
        )


def save_audio_article(article_num: int, article_title: str, script: str, file_path: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO audio_articles
               (article_num, article_title, script, file_path)
               VALUES (?, ?, ?, ?)""",
            (article_num, article_title, script, file_path)
        )


def get_audio_article(article_num: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM audio_articles WHERE article_num=?",
            (article_num,)
        ).fetchone()
    return dict(row) if row else None


def list_audio_articles_by_nums(article_nums: list) -> list:
    if not article_nums:
        return []
    placeholders = ",".join("?" * len(article_nums))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM audio_articles WHERE article_num IN ({placeholders})",
            article_nums
        ).fetchall()
    return [dict(r) for r in rows]


def save_audio_lesson(volume: int, part: int, chapter: int, topic_num: int,
                      topic_title: str, script: str, file_path: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO audio_lessons
               (volume, part, chapter, topic_num, topic_title, script, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (volume, part, chapter, topic_num, topic_title, script, file_path)
        )


def get_audio_lesson(volume: int, part: int, chapter: int, topic_num: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM audio_lessons
               WHERE volume=? AND part=? AND chapter=? AND topic_num=?""",
            (volume, part, chapter, topic_num)
        ).fetchone()
    return dict(row) if row else None


def list_audio_lessons_by_chapter(volume: int, part: int, chapter: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT volume, part, chapter, topic_num, topic_title, file_path
               FROM audio_lessons WHERE volume=? AND part=? AND chapter=?
               ORDER BY topic_num""",
            (volume, part, chapter)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_questions_by_ids(ids: list[int]):
    with get_conn() as conn:
        for id_ in ids:
            conn.execute("DELETE FROM questions WHERE id=?", (id_,))


def upsert_past_exam_question(year, part, question_num, question_text, choices, correct, subject=""):
    import json as _json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO past_exam_questions (year, part, question_num, question_text, choices, correct, subject)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(year, part, question_num) DO UPDATE SET
                 question_text=excluded.question_text,
                 choices=excluded.choices,
                 correct=excluded.correct,
                 subject=excluded.subject""",
            (year, part, question_num, question_text, _json.dumps(choices, ensure_ascii=False), correct, subject)
        )


def get_past_exam_questions(year: int, part: str) -> list:
    import json as _json
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.question_num, q.question_text, q.choices, q.correct, q.subject,
                      t.book, t.part_num, t.chapter, t.subject as tag_subject
               FROM past_exam_questions q
               LEFT JOIN past_exam_tags t
                 ON t.year=q.year AND t.part=q.part AND t.question_num=q.question_num
               WHERE q.year=? AND q.part=?
               ORDER BY q.question_num""",
            (year, part)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["choices"] = _json.loads(d["choices"] or "[]")
        # tag_subject takes priority over the legacy subject column
        if d.get("tag_subject"):
            d["subject"] = d["tag_subject"]
        result.append(d)
    return result


def get_past_exam_years() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT year, part FROM past_exam_questions ORDER BY year, part"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_past_exam_tag(year, part, question_num, book, part_num, chapter, subject=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO past_exam_tags (year, part, question_num, book, part_num, chapter, subject)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(year, part, question_num) DO UPDATE SET
                 book=excluded.book, part_num=excluded.part_num,
                 chapter=excluded.chapter, subject=excluded.subject""",
            (year, part, question_num, book, part_num, chapter, subject)
        )


def count_past_exam_by_chapter() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT book, part_num, chapter, COUNT(*) as cnt
               FROM past_exam_tags WHERE book > 0
               GROUP BY book, part_num, chapter"""
        ).fetchall()
    return {f"{r['book']}-{r['part_num']}-{r['chapter']}": r['cnt'] for r in rows}


def get_past_exam_by_chapter(book: int, part_num: int, chapter: int) -> list:
    import json as _json
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.year, q.part, q.question_num, q.question_text, q.choices, q.correct,
                      COALESCE(t.subject, q.subject) as subject
               FROM past_exam_questions q
               JOIN past_exam_tags t ON t.year=q.year AND t.part=q.part AND t.question_num=q.question_num
               WHERE t.book=? AND t.part_num=? AND t.chapter=?
               ORDER BY q.year, q.part, q.question_num""",
            (book, part_num, chapter)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["choices"] = _json.loads(d["choices"] or "[]")
        result.append(d)
    return result


def insert_knowledge(unit, category, title, content, law="", source=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO knowledge (unit, category, title, content, law, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (unit, category, title, content, law, source)
        )


def search(query: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.id, q.unit, q.question_num, q.question_text, q.answer, q.explanation, q.exam_source
               FROM questions_fts f
               JOIN questions q ON q.id = f.rowid
               WHERE questions_fts MATCH ?
               ORDER BY rank""",
            (query,)
        ).fetchall()
    return [dict(r) for r in rows]


def search_knowledge(query: str, limit: int = 4) -> list:
    with get_conn() as conn:
        # 1) FTS全文検索（trigram: 3文字以上のトークンが必要）
        rows = []
        try:
            rows = conn.execute(
                """SELECT k.unit, k.category, k.title, k.content, k.law
                   FROM knowledge_fts f JOIN knowledge k ON k.id = f.rowid
                   WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?""",
                (query, limit)
            ).fetchall()
        except Exception:
            pass
        if rows:
            return [dict(r) for r in rows]

        # 2) フォールバック: 2文字以上の部分文字列でLIKE検索
        seen: set = set()
        results = []
        tokens = [query[i:i + 2] for i in range(len(query) - 1)]
        for token in tokens:
            if not token.strip():
                continue
            matches = conn.execute(
                """SELECT unit, category, title, content, law FROM knowledge
                   WHERE title LIKE ? OR unit LIKE ? OR content LIKE ?
                   LIMIT ?""",
                (f"%{token}%", f"%{token}%", f"%{token}%", limit)
            ).fetchall()
            for m in matches:
                if m["title"] not in seen:
                    seen.add(m["title"])
                    results.append(dict(m))
            if len(results) >= limit:
                break
        return results[:limit]


def list_by_chapter(book: int, part: int, chapter: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, unit, question_num, answer, exam_source, question_text, book, part, chapter, topic "
            "FROM questions WHERE book=? AND part=? AND chapter=? ORDER BY question_num",
            (book, part, chapter)
        ).fetchall()
    return [dict(r) for r in rows]


def count_by_chapter() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT book, part, chapter, COUNT(*) as cnt FROM questions GROUP BY book, part, chapter"
        ).fetchall()
    return {f"{r['book']}-{r['part']}-{r['chapter']}": r['cnt'] for r in rows}


def list_all() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, unit, question_num, answer, exam_source, question_text FROM questions ORDER BY unit, question_num"
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_unit_num(unit: str, num: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM questions WHERE unit=? AND question_num=?", (unit, num)
        ).fetchone()
    return dict(row) if row else None


# ────────────────────────────────────────────────
# シードデータ（民法Ⅰ 第1章 民法の本質 21問）
# オートマシステム節順：節2→節3→節4→節5
# ────────────────────────────────────────────────
SEED_QUESTIONS = [
    # ── 節2: 法律的に考えるとどうなるのか（即時取得の基本・公信力・証明責任）──
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "公信力",
        "law": "民法192条",
        "question_num": 1,
        "question_text": "即時取得の制度は、取引の安全を保護するため、動産の占有に公信力を与えたものである。",
        "answer": "○",
        "explanation": "正しい。即時取得＝動産占有の公信力（192条）。",
        "exam_source": "",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "188条・権利推定",
        "law": "民法188条",
        "question_num": 2,
        "question_text": "占有者は、占有物の上に行使する権利を適法に有するものと推定される。",
        "answer": "○",
        "explanation": "民法188条の通り。",
        "exam_source": "S58-10-1",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "立証責任",
        "law": "民法192条・188条",
        "question_num": 3,
        "question_text": "Aが、Bの所有する動産甲を無権利のCから買い受けて現実の引渡しを受けた場合において、即時取得を主張するためには、自己に過失がなかったことを立証しなければならない。",
        "answer": "×",
        "explanation": "無過失は民法188条により推定される。立証不要。",
        "exam_source": "H30-8-1",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "無過失推定",
        "law": "民法188条",
        "question_num": 4,
        "question_text": "占有者が、占有物の上に行使する権利は、これを適法に有するものと推定されるので、即時取得を主張する者は、無過失を立証する責任を負わない。",
        "answer": "○",
        "explanation": "民法188条による推定。無過失の立証不要。",
        "exam_source": "H5-9-オ",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "立証責任",
        "law": "民法192条・188条",
        "question_num": 5,
        "question_text": "Aからデジタルカメラ甲を賃借していたFは、甲をBに売却し、その現実の引渡しをした。この場合において、BはAに対して甲の即時取得を主張するためには、Fが甲に関し無権利者であることについて自己が善意無過失であったことを証明しなければならない。",
        "answer": "×",
        "explanation": "民法188条の推定により立証不要。相手方がBの有過失を立証する必要がある。",
        "exam_source": "H25-8-4改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "善意のみ不十分",
        "law": "民法192条",
        "question_num": 6,
        "question_text": "CはAが所有する時計を預かっていたBとの間で、Bが所有者であると誤信してその時計の購入をし引渡しを受けた。この場合、Cが善意であれば過失があったとしてもその時計の所有権を取得することができる。",
        "answer": "×",
        "explanation": "善意だけでは不十分。無過失も必要（192条）。",
        "exam_source": "",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "即時取得の例外",
        "law": "民法192条",
        "question_num": 7,
        "question_text": "教授AがBから預かっていたビデオカメラをBに無断でCに譲渡した場合、Cは無権利者からの譲受人であるから、原則として所有権を取得することができない。",
        "answer": "×",
        "explanation": "即時取得（192条）の要件を満たせば所有権を取得できる。「原則不取得」は正しいが例外として即時取得がある。",
        "exam_source": "",
    },
    # ── 節2続き: 善意無過失の判断時点 ──
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "善意無過失の時点①",
        "law": "民法192条",
        "question_num": 8,
        "question_text": "動産の買主が引渡しを受けたとき、その動産が売主の所有に属しないことにつき善意であっても、その後に悪意となれば即時取得の効果は失われる。",
        "answer": "×",
        "explanation": "占有開始時（引渡し時）に善意無過失であれば、その後悪意になっても効果は失われない。",
        "exam_source": "S58-12-5",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "善意無過失の時点②",
        "law": "民法192条",
        "question_num": 9,
        "question_text": "Aの所有する甲動産を保管しているBが、甲動産を自己の所有物であると偽って甲動産をCに売却した場合において、代金支払時にCが甲動産の所有者がBであると信じ、かつ、そう信じるについて過失がないときは、代金支払後、引渡しを受けるまでの間に所有者がBでないことをCが知ったとしても、Cは甲動産を即時取得することができる。",
        "answer": "×",
        "explanation": "善意無過失は「占有開始時（引渡し時）」に要求される。引渡し前に悪意になれば即時取得不可。",
        "exam_source": "H17",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "善意無過失の時点③",
        "law": "民法192条",
        "question_num": 10,
        "question_text": "Aからデジタルカメラ甲の寄託を受けていたEは、甲をBに売却したが、その際、Bは、Eが甲に関し無権利者であることについて善意無過失であった。この場合において、Bは、その後にEから甲の現実の引渡しを受けた際、Eが甲に関し無権利者であることについて悪意となっていたときは、甲を即時取得しない。",
        "answer": "○",
        "explanation": "引渡し時（占有開始時）に悪意→即時取得しない。",
        "exam_source": "H25-8-3改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "善意無過失の時点④",
        "law": "民法192条",
        "question_num": 11,
        "question_text": "A所有の甲動産をAから預かっていたBが、甲動産がBの所有であると過失なく信じていたCとの間で甲動産の売買契約を締結した後、Cが、甲動産についてBが無権利であることを知り、甲動産の現実の引渡しを受けた場合には、Cは、甲動産を即時取得することができない。",
        "answer": "○",
        "explanation": "引渡し時に悪意→即時取得不可。",
        "exam_source": "R7-9-ウ",
    },
    # ── 節3: 帰責事由（盗品・193条）──
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "盗品・2年回復",
        "law": "民法193条",
        "question_num": 12,
        "question_text": "A所有の甲動産を盗んだBが、甲動産がBの所有であると過失なく信じているCに対して動産を売却し、現実の引渡しをした場合には、Aは、その盗難から2年間は、Cに対し、甲動産の返還を求めることができる。",
        "answer": "○",
        "explanation": "盗品の場合、被害者は盗難の時から2年間、善意無過失の占有者に対しても無償で回復請求できる（民法193条）。",
        "exam_source": "R7-9-才",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "横領と盗品の違い",
        "law": "民法193条",
        "question_num": 13,
        "question_text": "乙が甲から時計を横領した場合、内がその時計を乙の所有物であると過失なく信じて買い受けたときは、甲は横領の時から2年間はその時計の返還を内に請求することができる。",
        "answer": "×",
        "explanation": "横領は「盗品」に当たらない。甲が乙に時計を渡した事実があるため甲に帰責事由があり193条は適用されない。",
        "exam_source": "",
    },
    # ── 節4: 占有の意味（占有移転の4類型・指図による占有移転）──
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "占有移転の4類型",
        "law": "民法182条・183条・184条",
        "question_num": 14,
        "question_text": "占有権の譲渡は占有の目的物に対する外形的な支配の移転によってのみ効力を生ずる。",
        "answer": "×",
        "explanation": "簡易の引渡し・占有改定・指図による占有移転など、外形的支配の移転を伴わない方法もある（182条〜184条）。",
        "exam_source": "S63-15-5",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "指図・代理人の拒絶",
        "law": "民法184条",
        "question_num": 15,
        "question_text": "AがBに対して甲動産を貸し渡している。Aが、Fに甲動産を譲渡し、Bに対し、以後Fのために甲動産を占有すべき旨を命じたところ、BはFと不仲であるとして、これを拒絶した。この場合には、Fは、甲動産に対する占有権を取得しない。",
        "answer": "×",
        "explanation": "指図による占有移転（184条）は代理人（B）の承諾不要。第三者（F）が承諾すれば成立。Bが拒絶してもFは占有権を取得できる。",
        "exam_source": "H16-13-工改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "指図・承諾者はE",
        "law": "民法184条",
        "question_num": 16,
        "question_text": "Cが自己の所有する宝石をDに預けていたが、これをEに売却し、Dに対し、以後Eのためにその宝石を占有すべき旨を命じた場合、DがEのために宝石を占有することを承諾したときは、Eは、その宝石の占有権を取得するが、Dが承諾していない場合には、Eの占有権は認められない。",
        "answer": "×",
        "explanation": "承諾するのは第三者（E）であってDではない。Dが承諾しなくてもEが承諾すれば占有権を取得する（184条）。",
        "exam_source": "H22-8-1改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "指図・買受人の承諾",
        "law": "民法184条",
        "question_num": 17,
        "question_text": "Aがその所有する動産甲をBに賃貸している場合において、Aが動産甲をCに譲渡した。この場合において、Cが指図による占有移転により甲の引渡しを受けるためには、AがBに対して以後Cのためにその物を占有することを命じ、Cがこれを承諾することが必要である。",
        "answer": "○",
        "explanation": "指図による占有移転（184条）の成立要件：本人（A）が代理人（B）に命じ、第三者（C）が承諾すること。",
        "exam_source": "H23-8-ウ改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "指図・買主が命じる",
        "law": "民法184条",
        "question_num": 18,
        "question_text": "Aは、Bが所有しCに寄託している動産甲をBから買い受け、自らCに対し以後Aのために動産甲を占有することを命じ、Cがこれを承諾した。この場合には、Bの動産甲の占有権は、Aに移転する。",
        "answer": "×",
        "explanation": "指図による占有移転（184条）は「本人（売主B）」が代理人（C）に命じることが必要。買主Aが自ら命じても成立しない。",
        "exam_source": "H28-9-イ",
    },
    # ── 節5: 包括承継の意味 ──
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "包括承継と即時取得①",
        "law": "民法192条",
        "question_num": 19,
        "question_text": "即時取得は取引の安全を保護する制度だから、被相続人による他人の動産の占有を相続によって承継しても所有権を取得しない。",
        "answer": "○",
        "explanation": "相続による占有承継は「取引行為」でないため即時取得の要件を満たさない（192条）。",
        "exam_source": "",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "包括承継と即時取得②",
        "law": "民法192条",
        "question_num": 20,
        "question_text": "Aからデジタルカメラ甲を賃借していたCが死亡し、その相続人Bは、その相続によって甲の占有を取得した。この場合において、Bは、Cが甲に関し無権利者であったことについて善意無過失であるときは、甲を即時取得する。",
        "answer": "×",
        "explanation": "相続は「取引行為」でないため即時取得は成立しない（192条）。善意無過失でも取得不可。",
        "exam_source": "H25-8-1改",
    },
    {
        "unit": "即時取得", "book": 1, "part": 1, "chapter": 1,
        "topic": "包括承継と即時取得③",
        "law": "民法192条",
        "question_num": 21,
        "question_text": "A所有の甲動産をAから預かっていたBが死亡し、甲動産がBの所有であると過失なく信じているCが、Bを相続し、甲動産の占有を承継した場合には、Cは、甲動産を即時取得する。",
        "answer": "×",
        "explanation": "相続（包括承継）は「取引行為」でないため即時取得は成立しない（192条）。",
        "exam_source": "R7-9-イ",
    },
]


SEED_KNOWLEDGE = [
    {
        "unit": "即時取得",
        "category": "原則",
        "title": "民法の大原則：空のバスケット（承継）",
        "content": """民法の大原則「空のバスケットからリンゴは生じない」。
リンゴは所有権のこと。前主に権利がなければ、承継人にも権利はない（無からは無しか生じない）。
AがXから預かったのは所有権の入っていない「空のバスケット」。
YがAからもらったバスケットにリンゴ（所有権）があるはずがない。
これを法律用語で「承継」という——前主と同じ地位に立つこと。

例：X（真の所有者）→ A（無権利者）→ Y　この場合、原則としてYは無権利。""",
        "law": "民法192条",
        "source": "IMG_9131.JPG",
    },
    {
        "unit": "即時取得",
        "category": "例外・制度",
        "title": "民法の例外：空のバスケットからリンゴが生じる（公信力）",
        "content": """民法192条（即時取得）は例外的に「空のバスケットからリンゴが生じる」手品を認める。
これを「公信力」という——虚偽の外観（無権利者が占有している姿）を信じた結果として生じる法的効果。

即時取得の3つの柱：
1. 帰責事由（Xが信頼できないAに宝石を渡した）
2. 取引の安全（安心して売買できる社会の仕組み）
3. 善意・無過失（YがAを権利者と過失なく信じた）

この3点が揃ったとき、「無から有が生じる」。
不動産には公信力なし——民法192条に相当する条文が不動産取引にはないため。""",
        "law": "民法192条",
        "source": "IMG_9131.JPG, IMG_9132.JPG",
    },
    {
        "unit": "即時取得",
        "category": "条文",
        "title": "民法192条 条文（即時取得）",
        "content": """民法192条（即時取得）
取引行為によって、平穏に、かつ、公然と動産の占有を始めた者は、善意であり、かつ、過失がないときは、即時にその動産について行使する権利を取得する。

要件まとめ：
① 取引行為（売買・贈与など）による取得
② 平穏・公然と占有を開始
③ 動産であること（不動産は対象外）
④ 善意（無権利を知らない）
⑤ 無過失（知らなかったことに過失がない）
⑥ 占有の取得（引渡しを受けた時点）

善意・無過失の判断時点：占有開始時（引渡し時）。その後悪意になっても効果は失われない。""",
        "law": "民法192条",
        "source": "IMG_9131.JPG",
    },
    {
        "unit": "即時取得",
        "category": "条文",
        "title": "民法188条 条文（占有権利の推定）",
        "content": """民法188条（占有物について行使する権利の適法の推定）
占有者が占有物について行使する権利は、適法に有するものと推定する。

実務上の意味：
・Yの無過失は推定される（最判昭41.6.9）
・即時取得を主張する者は無過失を自分で証明しなくてよい
・相手方（X）がYの「過失」を立証しなければならない
・立証に成功すればXの勝ち、失敗すればYが即時取得する

推定を覆すには：「Aから買う前になぜ一本電話しなかったのか」など、YがAを疑う事情があったことをXが証明する。""",
        "law": "民法188条",
        "source": "IMG_9133.JPG",
    },
    {
        "unit": "即時取得",
        "category": "条文",
        "title": "民法193条 条文（盗品・遺失物の回復）",
        "content": """民法193条（盗品又は遺失物の回復）
前条（192条）の場合において、占有物が盗品又は遺失物であるときは、被害者又は遺失者は、盗難又は遺失の時から2年間、占有者に対してその物の回復を請求することができる。

ポイント：
・盗品・遺失物の場合、Xに帰責事由がない（Xは被害者）
・Yが善意・無過失であっても、2年間はXが無償で取り戻せる
・2年を過ぎると取り戻せなくなる
・ただし競売や公開市場で買った場合は代価弁償が必要（194条）

192条との違い：盗品・遺失物はXの帰責事由なし → Yが泣く（2年間）。""",
        "law": "民法193条",
        "source": "IMG_9135.JPG",
    },
    {
        "unit": "即時取得",
        "category": "用語",
        "title": "善意・悪意の定義",
        "content": """法律用語の「善意」「悪意」は日常語と意味が異なる。

善意 = ある事情を「知らないこと」
悪意 = ある事情を「知っていること」

「よい行い」「悪い行い」という道徳的な意味ではない。

即時取得での使い方：
・善意 = Aが無権利者であることを「知らない」
・悪意 = Aが無権利者であることを「知っている」

善意は民法188条により推定される。""",
        "law": "民法188条",
        "source": "IMG_9131.JPG",
    },
    {
        "unit": "即時取得",
        "category": "用語",
        "title": "帰責事由",
        "content": """帰責事由 = 責任を取るべき理由・事情。

即時取得の文脈での意味：
真の所有者X自身が、信頼できないAに物を引き渡した（Xに落ち度がある）。
→ YはXに「あなたが信用できない人物のAを信じて渡したから事件が起きた」と主張できる。
→ XにはAを信じて渡したという帰責事由がある。

帰責事由がない場合（盗品）：
Xは盗まれた被害者。自ら渡したのではないので帰責事由なし。
→ 民法193条でXが保護される。""",
        "law": "民法193条",
        "source": "IMG_9130.JPG, IMG_9135.JPG",
    },
    {
        "unit": "即時取得",
        "category": "用語",
        "title": "取引の安全",
        "content": """取引の安全 = 取引を行った者の利益を図ること。虚偽の外観を信頼して取引に入った者の信頼を保護する法理。

資本主義社会では「買ったものが自分のものにならない」と安心して売買できない。
→ 即時取得は「取引の安全」を守るための制度。

動産の占有には公信力がある = 占有している人を所有者だと信じていい。
不動産には公信力がない = 登記があっても即時取得は成立しない。""",
        "law": "民法192条",
        "source": "IMG_9130.JPG, IMG_9132.JPG",
    },
    {
        "unit": "即時取得",
        "category": "用語",
        "title": "証明責任（立証責任）",
        "content": """証明責任 = 事実の真偽が不明な場合に、証明責任を負う側が負ける、というルール。

「証明責任のあるところ敗訴あり」。

即時取得における証明責任：
・無過失の証明責任 → X（真の所有者）が負う（Yの過失を立証する）
・民法188条でYの無過失は推定されるため、Yは自ら証明する必要がない
・XがYの過失の立証に成功 → Xの勝ち（Yは即時取得せず）
・XがYの過失の立証に失敗 → Yの勝ち（Yは即時取得する）

裁判官は「お手上げ」判決を出せないルールがある（憲法32条：裁判を受ける権利）。""",
        "law": "民法188条",
        "source": "IMG_9133.JPG, IMG_9134.JPG",
    },
    {
        "unit": "即時取得",
        "category": "注意点",
        "title": "即時取得が成立しないケース",
        "content": """以下の場合は即時取得が成立しない。

① 不動産の場合（登記に公信力なし）
例：立木法による登記がされた立木は不動産 → 即時取得不可（S63-10-4改）

② 事実行為の場合（取引行為でない）
例：他人の山林を自分のと誤信して立木を伐採 → 「取引行為」でないので不可（H13-7-ア改）

③ 占有開始時に悪意・有過失の場合
引渡し前に無権利を知ってしまった場合は即時取得不可（H17、H25-8-3改、R7-9-ウ）

④ 善意だけで無過失でない場合（民法192条）""",
        "law": "民法192条",
        "source": "IMG_9132.JPG, IMG_9133.JPG, IMG_9135.JPG",
    },
]


SEED_KNOWLEDGE_CHAPTER1 = [
    {
        "unit": "民法の本質",
        "category": "概要",
        "title": "第1章 民法の本質 ── 5つのテーマ",
        "content": """民法の本質（基本編 第1章）では以下の5つを学ぶ。

1. 利益衡量 ── 対立する利益を天秤にかけて、どちらを守るべきか判断する法的思考法
2. 法律的に考えるとどうなるのか ── 条文のルールを当てはめて答えを出す思考プロセス
3. 帰責事由 ── 責任を取るべき理由・事情（自分に落ち度があるかどうか）
4. 占有の意味 ── 占有は「支配している外観」であり、動産に公信力を与える根拠になる
5. 包括承継の意味 ── 相続のように、権利・義務を一括して引き継ぐこと""",
        "law": "民法1条",
        "source": "オートマシステム民法Ⅰ 基本編第1章",
    },
    {
        "unit": "民法の本質",
        "category": "思考法",
        "title": "利益衡量（りえきこうりょう）",
        "content": """利益衡量 = 対立する利益を比較して、どちらをより保護すべきか判断する法的思考法。

民法の解釈では条文だけでは解決できないことも多い。そのとき「A と B のどちらの利益が重いか」を丁寧に考えることが大事。

具体例①：即時取得（民法192条）
・元の所有者の利益（取り返したい）vs 善意の買主の利益（正当に買った）
→ 取引の安全を守るため、善意の買主を保護

具体例②：不動産の二重売買
・先に買った人の利益 vs 先に登記した人の利益
→ 登記制度への信頼を守るため、先に登記した人を保護

「なぜこのルールなの？」と思ったら、誰の利益を守ると社会全体がうまくいくかを考えればよい。""",
        "law": "民法1条2項（信義則）",
        "source": "オートマシステム民法Ⅰ 基本編第1章1節",
    },
    {
        "unit": "民法の本質",
        "category": "思考法",
        "title": "帰責事由（きせきじゆう）",
        "content": """帰責事由 = 責任を取るべき理由・事情。「自分に落ち度があるかどうか」。

即時取得での使い方：
・真の所有者Xが信用できないAに物を渡した → Xに帰責事由あり
・Yは「あなたが悪いAを信じて渡したから事件が起きた」とXに言える
→ Yが即時取得で保護される根拠になる

帰責事由がない場合（盗品）：
・Xは被害者。自ら渡したのではないので帰責事由なし
→ 民法193条でXが2年間取り戻せる

損害賠償との関係：
・債務不履行や不法行為で損害賠償が認められるには、原則として帰責事由（故意・過失）が必要。""",
        "law": "民法192条・193条・415条",
        "source": "オートマシステム民法Ⅰ 基本編第1章3節",
    },
    {
        "unit": "民法の本質",
        "category": "概念",
        "title": "占有の意味",
        "content": """占有 = 物を実際に支配している状態・外観のこと。

民法における占有の2つの役割：
① 動産に公信力を与える根拠（即時取得 民法192条）
  占有している人を所有者だと信じて取引した人を保護する。

② 占有権として独立した権利（民法180条以下）
  たとえ無権利者でも、占有を奪われたら取り返せる（占有訴権）。

重要な区別：
・自主占有 = 所有の意思をもって占有（例：買主、時効取得の要件）
・他主占有 = 所有の意思なく占有（例：賃借人、借用者）
  → 他主占有では取得時効は成立しない

「占有」は民法全体に関わる基礎概念。""",
        "law": "民法180条・192条",
        "source": "オートマシステム民法Ⅰ 基本編第1章4節",
    },
    {
        "unit": "民法の本質",
        "category": "概念",
        "title": "包括承継（ほうかつしょうけい）の意味",
        "content": """包括承継 = 権利・義務を一括してまるごと引き継ぐこと。

代表例：相続
・被相続人が死亡すると、相続人はプラスの財産もマイナスの財産（借金）も一括して承継する。
・「都合のいいものだけ引き継ぐ」ことはできない（例外：限定承認・相続放棄）。

「空のバスケット」の原則との関係：
・Aが無権利者であれば、Aから譲り受けたBも無権利（前主と同じ地位を承継）。
・包括承継も同じ原理：前主の地位をそのまま引き継ぐ。

特定承継との違い：
・特定承継 = 特定の権利だけを個別に引き継ぐ（売買など）。
・包括承継 = すべての権利義務をまとめて引き継ぐ（相続・会社合併など）。""",
        "law": "民法896条・920条",
        "source": "オートマシステム民法Ⅰ 基本編第1章5節",
    },
]


SEED_KNOWLEDGE_CH2 = [
    {
        "unit": "物権の世界",
        "category": "概要",
        "title": "第2章 物権の世界 ── 概要",
        "content": """物権とは、物を直接・排他的に支配する権利のこと。
代表的な物権：所有権・抵当権・地上権・地役権・留置権など。

物権の特徴：
1. 直接支配性 ── 他人の助けなしに物を支配できる
2. 排他性 ── 同一物に同一内容の物権は2つ成立しない（一物一権主義）
3. 絶対性 ── 誰に対しても主張できる（対世的効力）

物権変動（所有権の移転）の原則：民法176条
→ 意思表示のみで効力を生じる（引渡しや登記は不要）

対抗要件：第三者に物権取得を主張するために必要な要件
→ 不動産：登記（民法177条）
→ 動産：引渡し（民法178条）""",
        "law": "民法175条・176条・177条・178条",
        "source": "オートマシステム民法Ⅰ 基本編第2章",
    },
    {
        "unit": "物権の世界",
        "category": "条文",
        "title": "民法176条 物権変動の意思主義",
        "content": """民法176条（物権の設定及び移転）
物権の設定及び移転は、当事者の意思表示のみによって、その効力を生ずる。

ポイント：
・売買契約を結んだ瞬間に所有権は移転する（原則）
・引渡しも登記も不要（当事者間では）
・例外：当事者が「登記時に移転」など別の合意をした場合はその合意による

ただし！第三者への対抗には登記が必要（177条）。
「当事者間では有効、でも第三者には言えない」という二段構造。""",
        "law": "民法176条",
        "source": "オートマシステム民法Ⅰ 基本編第2章",
    },
    {
        "unit": "物権の世界",
        "category": "条文",
        "title": "民法177条 不動産物権変動の対抗要件（登記）",
        "content": """民法177条（不動産に関する物権の変動の対抗要件）
不動産に関する物権の得喪及び変更は、不動産登記法その他の登記に関する法律の定めるところに従いその登記をしなければ、第三者に対抗することができない。

ポイント：
・不動産の物権変動を第三者に主張するには登記が必要
・登記なき物権変動は第三者に対抗できない

「第三者」の範囲（重要）：
・当事者および包括承継人（相続人）は含まない
・正当な利益を有する者のみ（背信的悪意者は除外）
・背信的悪意者 = 登記のないことを知りながら、売主と結託するなど不正な目的で取得した者
→ 背信的悪意者には対抗できる（登記なくても勝てる）

二重譲渡の例：AがBとCの両方に土地を売った場合
→ 先に登記したほうが所有権を取得する""",
        "law": "民法177条",
        "source": "オートマシステム民法Ⅰ 基本編第2章",
    },
    {
        "unit": "物権の世界",
        "category": "条文",
        "title": "民法178条 動産物権変動の対抗要件（引渡し）",
        "content": """民法178条（動産に関する物権の譲渡の対抗要件）
動産に関する物権の譲渡は、その動産の引渡しがなければ、第三者に対抗することができない。

ポイント：
・動産の物権変動を第三者に主張するには引渡しが必要
・不動産の登記に相当するのが動産の引渡し

引渡しの4種類（民法182条〜184条）：
① 現実の引渡し ── 実際に物を手渡す
② 簡易の引渡し ── 既に占有している者への譲渡（現実の引渡し省略可）
③ 占有改定 ── 売主が引き続き物を保管する場合（代理占有）
④ 指図による占有移転 ── 第三者が保管している物を、その第三者に命じてから譲渡

占有改定と即時取得：
・占有改定では即時取得は成立しない（外形的な占有移転がないため）""",
        "law": "民法178条・182条・183条・184条",
        "source": "オートマシステム民法Ⅰ 基本編第2章",
    },
    {
        "unit": "物権の世界",
        "category": "応用",
        "title": "二重譲渡と対抗関係",
        "content": """二重譲渡とは：同一の不動産を同一人が2人に売ること。

例：AがBに土地を売り、さらにCにも同じ土地を売った場合
→ BとCは「対抗関係」に立つ
→ 先に登記をした方が所有権を確定的に取得する（民法177条）

対抗関係の図：
A → B（先に売買契約、でも未登記）
A → C（後から売買契約、でも先に登記）
→ Cが勝つ！

登記を先にした者が勝つのが原則だが、例外として：
・背信的悪意者 ── Bが先に契約したと知りながら、Aと組んでわざとBを害する目的で登記を取ったCは、背信的悪意者として保護されない
→ Bは登記なくてもCに勝てる

「先に登記」vs「背信的悪意者」の判断が出題ポイント。""",
        "law": "民法177条",
        "source": "オートマシステム民法Ⅰ 基本編第2章",
    },
]

SEED_KNOWLEDGE_CH3 = [
    {
        "unit": "債権の世界",
        "category": "概要",
        "title": "第3章 債権の世界 ── 物権との違い",
        "content": """債権とは、特定の人（債権者）が特定の人（債務者）に対して、一定の行為（給付）を請求できる権利。

物権 vs 債権の根本的違い：
・物権 = 物に対する支配権（誰にでも主張できる＝絶対権）
・債権 = 人に対する請求権（特定の相手にしか主張できない＝相対権）

例：Aの土地をBが賃借している場合
→ BはAに対して「土地を使わせろ」と言える（債権）
→ でもCが土地を不法占拠してもBは直接Cを追い出せない（原則）
→ 例外：借地借家法で賃借権の登記や引渡しで物権的保護が与えられる

民法の重要概念：債権の効力
① 履行請求権 ── 債務の履行を請求できる
② 損害賠償請求権 ── 不履行があれば損害賠償を請求できる
③ 強制執行 ── 裁判所の力を借りて強制的に実現できる""",
        "law": "民法399条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "条文",
        "title": "意思表示の瑕疵（民法93〜96条）",
        "content": """意思表示に問題がある場合のルール：

民法93条（心裡留保）：
・冗談や本心でない意思表示。原則として有効。
・相手方が知っていた or 知れた場合は無効。

民法94条（虚偽表示・通謀虚偽表示）：
・当事者が合意して虚偽の意思表示。無効。
・ただし善意の第三者には無効を対抗できない。

民法95条（錯誤）：
・重要な事項に関する錯誤で、かつ表意者に重大な過失がない場合は取消し可能。
・動機の錯誤は、動機が表示されていれば取消し可能（改正後）。

民法96条（詐欺・強迫）：
・詐欺：取消し可能。善意無過失の第三者には取消しを対抗できない。
・強迫：取消し可能。第三者にも対抗できる（善意でも不可）。

重要な区別：強迫は善意の第三者にも主張できる（詐欺と違う！）""",
        "law": "民法93条・94条・95条・96条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "条文",
        "title": "民法121条 取消しの効果（遡及効）",
        "content": """民法121条（取消しの効果）
取り消された行為は、初めから無効であったものとみなす。

ポイント：取消しには遡及効（そきゅうこう）がある。
→ 取り消すと、最初から無効だったことになる。

返還義務：
・取消し後は原状回復義務が生じる（民法121条の2）
・受け取ったものを返還しなければならない

取消しができる者（民法120条）：
・制限行為能力者（本人・代理人・承継人・同意権者）
・詐欺・強迫を受けた者（本人・代理人・承継人）

取消権の消滅（民法126条）：
・追認できる時から5年（主観的起算点）
・行為の時から20年（客観的起算点）
→ どちらか早い方で時効消滅""",
        "law": "民法121条・121条の2・120条・126条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "条文",
        "title": "民法415条 債務不履行と損害賠償",
        "content": """民法415条（債務不履行による損害賠償）
債務者がその債務の本旨に従った履行をしないとき又は債務の履行が不能であるときは、債権者は、これによって生じた損害の賠償を請求することができる。ただし、その債務の不履行が契約その他の債務の発生原因及び取引上の社会通念に照らして債務者の責めに帰することができない事由によるものであるときは、この限りでない。

債務不履行の3類型：
① 履行遅滞 ── 履行できるのに遅れている
② 履行不能 ── 履行することが不可能になった
③ 不完全履行 ── 一応履行したが不完全

損害賠償の要件：
・債務不履行の事実
・損害の発生
・因果関係
・債務者の帰責事由（故意・過失）
→ 帰責事由がなければ損害賠償不要（免責）

損害賠償の範囲（民法416条）：
・通常損害 + 予見可能な特別損害""",
        "law": "民法415条・416条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "条文",
        "title": "民法541〜545条 契約解除",
        "content": """解除とは：契約の効力を遡って消滅させること。

民法541条（催告解除）：
・相当の期間を定めて催告し、履行がなければ解除できる。
・軽微な不履行では解除できない（改正後）。

民法542条（催告なし解除）：
・履行不能の場合は催告不要で即座に解除できる。
・その他一定の場合も催告不要。

民法545条（解除の効果）：
・解除すると各当事者は原状回復義務を負う。
・第三者の権利を害することはできない（解除前に権利を取得した善意の第三者は保護）。
・損害賠償請求権は妨げられない（解除しても損害賠償は別途請求可能）。

解除と第三者：
・解除前に登場した第三者 → 保護される（対抗要件が必要）
・解除後に登場した第三者 → 対抗要件で決まる（解除は登記なしでは対抗不可）""",
        "law": "民法541条・542条・545条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "条文",
        "title": "民法536条 危険負担",
        "content": """危険負担とは：双務契約において、一方の債務が消滅した場合に、他方の債務はどうなるか、という問題。

民法536条（債務者の危険負担等）：
・改正後（令和2年）：債務者の責めに帰すことができない事由で債務が不能になった場合、債権者は反対給付の履行を拒否できる（履行拒絶権）。

改正前 vs 改正後：
・改正前：「債権者主義」と「債務者主義」で分かれていた
  → 不動産売買は債権者主義（買主が危険負担）
  → 改正後：債務者主義に統一（売主が危険負担）

例：売買契約後、引渡し前に目的物が自然災害で滅失
→ 売主（債務者）の責めに帰すべき事由なし
→ 買主は代金支払いを拒絶できる
→ 解除も可能（541条・542条）""",
        "law": "民法536条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
    {
        "unit": "債権の世界",
        "category": "応用",
        "title": "保証・連帯保証・物上保証",
        "content": """保証とは：主債務者が債務を履行しない場合に、保証人が代わりに履行する義務を負う契約。

保証の特徴（付従性・随伴性・補充性）：
・付従性 ── 主債務が消滅すれば保証債務も消滅する
・随伴性 ── 債権が譲渡されれば保証も一緒に移転する
・補充性 ── 催告の抗弁権・検索の抗弁権がある

連帯保証：補充性なし（催告・検索の抗弁権なし）
→ 債権者はいきなり連帯保証人に請求できる
→ 通常の保証より保証人の責任が重い

物上保証人：自分の財産に担保を設定して他人の債務を担保する人
→ 主債務者の債務が弁済されないと、物上保証人の財産が競売される
→ 弁済すれば主債務者に求償できる（民法351条・372条）

保証と物上保証の違い：
・保証人 ── 無限責任（全財産で責任）
・物上保証人 ── 有限責任（担保物の限度で責任）""",
        "law": "民法446条・447条・448条・351条",
        "source": "オートマシステム民法Ⅰ 基本編第3章",
    },
]

SEED_KNOWLEDGE_CH4 = [
    {
        "unit": "物権と債権",
        "category": "概要",
        "title": "第4章 物権と債権どちらが強いか ── 概要",
        "content": """第4章では、物権と債権が交差するテーマを扱う。
「本来は当事者間にしか効力がない債権が、特殊な状況で第三者にも効力を持つ場合」がテーマ。

主なテーマ（p.110〜141）：
1. 連帯債務 ── 複数の債務者が同一債務を負う（債権者保護）
2. 債権者代位権（民法423条）── 債務者が権利行使しない場合に債権者が代わりに行使
3. 詐害行為取消請求（民法424条）── 債務者が債権者を害する行為を取り消す
4. 債権譲渡（民法466条・467条）── 債権を第三者に売ること・対抗要件
5. 相殺（民法505条・469条）── 互いの債権を消し合う・担保的効力
6. 物権的請求権 ── 物権から派生する人に対する請求権
7. 取得時効（民法162条）── 長期間占有で所有権取得
8. 賃借権の物権化（借地借家法）── 債権的賃借権の物権的保護""",
        "law": "民法423条・424条・466条・467条・505条・162条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.110-147",
    },
    {
        "unit": "物権と債権",
        "category": "条文",
        "title": "民法423条 債権者代位権",
        "content": """民法423条（債権者代位権の要件）
1項：債権者は、自己の債権を保全するため必要があるときは、債務者に属する権利（被代位権利）を行使することができる。
ただし、一身専属権・差押禁止権利は除く。
2項：弁済期到来前は原則行使不可（保存行為は除く）。
3項：強制執行により実現できない債権には使えない。

要件まとめ：
① 債権者の債権が強制執行で実現できるものであること
② 債務者の無資力
③ 債務者が被代位権利を行使しないこと
④ 弁済期が到来していること（原則）

裁判外でも行使できる（詐害行為取消と違う！）

民法423条の3（債権者への支払・引渡し）：
被代位権利が金銭支払・動産引渡しを目的とする場合、債権者は相手方に直接自己への支払いを求めることができる。""",
        "law": "民法423条・423条の3",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.110-115",
    },
    {
        "unit": "物権と債権",
        "category": "条文",
        "title": "民法424条 詐害行為取消請求",
        "content": """民法424条（詐害行為取消請求）
1項：債権者は、債務者が債権者を害することを知ってした行為の取消しを裁判所に請求できる。
ただし、受益者がその行為の時に債権者を害することを知らなかった場合は除く。
2項：財産権を目的としない行為（相続放棄・離婚など）には適用しない。
3項：債権が詐害行為の前の原因に基づいて生じたものでなければならない。
4項：強制執行により実現できない債権には使えない。

要件まとめ：
① 詐害行為（債務者が無資力になったり財産を減らす行為）
② 債務者の悪意（債権者を害することを知っていた）
③ 受益者の悪意（行為の時に債権者を害することを知っていた）
④ 被保全債権が詐害行為前の原因に基づくこと

裁判上でのみ行使できる（債権者代位と違う！）

詐害行為 vs 債権者代位：
・両方とも「強制執行の前提として債務者の責任財産を充実させる制度」
・代位権：訴訟外でも可 / 詐害行為取消：裁判上のみ""",
        "law": "民法424条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.116-121",
    },
    {
        "unit": "物権と債権",
        "category": "条文",
        "title": "民法466条・467条 債権譲渡と対抗要件",
        "content": """債権譲渡とは：債権を第三者に売ること（債務者に断りなく可能）。

民法466条（債権の譲渡性）：
・債権は原則として自由に譲渡できる。
・ただし、性質上譲渡できない場合は除く（肖像画制作債権・扶養請求権など）。

民法467条（債権譲渡の対抗要件）：
1項：債権譲渡を債務者・第三者に対抗するには、
→ 「譲渡人からの通知」または「債務者の承諾」が必要。
※ 譲受人からの通知は効力なし（債務者の保護が目的のため）

2項：第三者に対抗するには、
→ 「確定日付のある証書」による通知または承諾が必要。

二重譲渡の優劣：
→ 確定日付ある通知が債務者に到達した時間の前後で決まる（判例：最判昭49.3.7）
→ 確定日付の日付自体の前後ではない

確定日付とは：当事者が後から変更できない公的な日付（内容証明郵便の日付、公正証書の日付など）""",
        "law": "民法466条・467条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.124-133",
    },
    {
        "unit": "物権と債権",
        "category": "条文",
        "title": "民法505条・469条 相殺と担保的効力",
        "content": """相殺とは：2人が互いに同種の債務を負う場合、一方の意思表示で対当額を消滅させること。

民法505条（相殺の要件）：
・双方の債権が弁済期にあること
・同種の給付を目的とすること
・金銭債務の相殺が典型例

相殺の担保的効力：
相手が無資力になった場合でも、相殺できれば自己の債権を100%回収したのと同じ効果がある。
（他の債権者は平等配当しか受けられないのに対し、相殺できる者は有利）

民法469条（債権譲渡における三角相殺）：
・対抗要件具備時より前に取得した譲渡人への反対債権で、譲受人に相殺を対抗できる。
→ XがAの甲への債権を譲渡。通知前に甲がAへの貸付を取得 → 甲はXへの支払いに際しAへの貸付債権で相殺できる。

一問一答：
Q: XがAの甲への債権を取得した通知がされた後で、甲がAへの債権を取得した。甲は相殺できるか？
A: 原則できない（対抗要件具備後の反対債権取得のため）""",
        "law": "民法505条・469条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.136-139",
    },
    {
        "unit": "物権と債権",
        "category": "概念",
        "title": "物権的請求権",
        "content": """物権的請求権とは：物権（所有権など）の排他的支配から派生する、人に対する請求権。
民法に明文規定はないが、物権の性質上当然に認められる。

3種類：
① 返還請求権 ── 占有を奪われた場合に返還を求める（例：土地の明渡し請求）
② 妨害排除請求権 ── 物権行使が妨害されている場合に除去を求める（例：不法建物の収去）
③ 妨害予防請求権 ── 将来の妨害のおそれがある場合に予防措置を求める

重要な特徴：
・相手の善意・悪意・過失の有無と無関係に主張できる
・物権は「排他的支配権」なので効力が強い

具体例（事例38）：
BがAの土地上に建物を建てた（A善意無過失でも関係なし）
→ 土地所有者X：①土地の明渡し請求（返還請求権）＋②建物の収去請求（妨害排除請求権）ができる
→ 建物は壊すしかない（引っ越しができる例外的ケースを除く）

取得時効との関係：
占有者Aが10年（善意無過失）または20年で土地の所有権を時効取得するおそれあり
→ Xは早めに訴訟提起して時効を中断すべき""",
        "law": "民法162条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.140-141",
    },
    {
        "unit": "物権と債権",
        "category": "応用",
        "title": "取得時効と登記",
        "content": """取得時効の要件（民法162条）：
・所有の意思をもって（自主占有）
・平穏・公然と
・他人の物を占有すること
・20年間（善意・無過失なら10年間）

取得時効と登記（重要）：
・時効完成前に第三者が登記 → 時効取得者は対抗できない（第三者が優先）
・時効完成後に第三者が登記 → 対抗関係になる（先に登記した方が勝つ）

時効と自主占有・他主占有：
・自主占有 ── 所有の意思あり（取得時効成立の要件）
・他主占有 ── 所有の意思なし（賃借人・借用者など）
→ 他主占有では取得時効は成立しない""",
        "law": "民法162条・177条",
        "source": "オートマシステム民法Ⅰ 基本編第4章",
    },
    {
        "unit": "物権と債権",
        "category": "応用",
        "title": "賃借権の物権化と借地借家法",
        "content": """賃借権（不動産の賃貸借）は本来「債権」だが、借地借家法により強力な保護を受ける。

借地権（土地の賃借権）の対抗要件：
・原則：登記（民法605条）
・借地借家法：建物の登記があれば土地賃借権を第三者に対抗できる（借地借家法10条）
→ 地主が土地を第三者に譲渡しても、借地人は建物登記があれば追い出されない

借家権（建物の賃借権）の対抗要件：
・原則：登記
・借地借家法：建物の引渡しを受けていれば第三者に対抗できる（31条）
→ 大家が建物を売っても、賃借人は引渡しを受けていれば住み続けられる

対抗力ある賃借権の物権化：
・登記した賃借権は物権的効力を持つ → 不法占拠者に対して妨害停止請求ができる
・対抗力のない賃借権は妨害停止請求不可
→ ただし、地主の所有権に基づく妨害排除請求権を債権者代位で行使できる（民法423条の転用）

「売買は賃貸借を破る」という原則の例外：
・借地借家法の保護があると → 「売買は賃貸借を破らない」状態になる""",
        "law": "借地借家法10条・31条・民法605条・423条",
        "source": "オートマシステム民法Ⅰ 基本編第4章 p.142-147",
    },
]

SEED_KNOWLEDGE_CH5 = [
    {
        "unit": "担保物権",
        "category": "概要",
        "title": "第5章 担保物権 ── 4つの性質",
        "content": """担保物権とは：債権の担保として、物に設定される物権。
借金の担保として不動産に抵当権を設定するのが典型例。

担保物権の4つの性質（重要！）：
① 付従性 ── 主債務が消滅すれば担保物権も消滅する
② 随伴性 ── 債権が譲渡されれば担保物権も一緒に移転する
③ 不可分性 ── 債務の一部が残っている限り、目的物全体に担保が及ぶ
④ 物上代位性 ── 目的物が滅失・毀損した場合の賠償金・保険金にも及ぶ（差押えが必要）

主な担保物権：
・留置権 ── 法定担保物権。弁済されるまで物を留置できる。
・先取特権 ── 法定担保物権。一般先取特権・動産先取特権・不動産先取特権。
・質権 ── 約定担保物権。物の占有を移転して担保にする。
・抵当権 ── 約定担保物権。占有移転なしに担保にできる（最も重要！）""",
        "law": "民法295条・303条・342条・369条",
        "source": "オートマシステム民法Ⅰ 基本編第5章",
    },
    {
        "unit": "担保物権",
        "category": "条文",
        "title": "抵当権（民法369条）と競売手続",
        "content": """民法369条（抵当権の内容）
抵当権者は、債務者又は第三者が占有を移転しないで債務の担保に供した不動産について、他の債権者に先立って自己の債権の弁済を受ける権利を有する。

抵当権の特徴：
・非占有担保 ── 設定者（債務者）がそのまま使い続けられる
・優先弁済権 ── 他の債権者より先に弁済を受けられる
・登記が対抗要件（民法177条）

競売手続：
1. 債務不履行（返済できない）
2. 抵当権者が裁判所に競売申立
3. 裁判所が不動産を競売
4. 売却代金から抵当権者が優先的に弁済を受ける

抵当権と賃借権：
・抵当権設定後に賃借権を設定した場合 → 抵当権が優先（競売で賃借権消滅）
・例外：同意（民法387条）があれば賃借権が保護される

根抵当権（民法398条の2）：
・一定の範囲の債権を、極度額の限度で担保する抵当権
・個別の債権の消滅に関係なく担保が続く（付従性なし）""",
        "law": "民法369条・177条・387条・398条の2",
        "source": "オートマシステム民法Ⅰ 基本編第5章",
    },
    {
        "unit": "担保物権",
        "category": "応用",
        "title": "物上代位性と差押えの要件",
        "content": """物上代位性とは：担保物権の目的物が滅失・毀損・賃貸された場合に、
その代わりに生じた金銭（保険金・賃料・損害賠償金など）に対しても担保物権の効力が及ぶ性質。

根拠：民法304条（先取特権の物上代位）・民法372条（抵当権への準用）

行使するには「払渡し又は引渡しの前に差押え」が必要！
→ 差押えをしないと物上代位を行使できない
→ 差押えが対抗要件的な役割を果たす

具体例：
・建物に火災 → 火災保険金に物上代位できる（差押え要）
・賃貸している場合の賃料 → 賃料に物上代位できる（差押え要）
・建物が取り壊された場合の代金 → 代金に物上代位できる（差押え要）

物上代位 vs 付従性：
・付従性 ── 主債務が消滅すれば担保も消滅（担保の消極的側面）
・物上代位性 ── 目的物に代わるものにも担保が及ぶ（担保の積極的側面）""",
        "law": "民法304条・372条",
        "source": "オートマシステム民法Ⅰ 基本編第5章",
    },
]


SEED_QUESTIONS_CH2 = [
    # ── 参考問題（p.34）即時取得と自動車 ──
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "登録自動車と即時取得", "law": "民法192条",
        "question_num": 1,
        "question_text": "道路運送車両法による登録を受けている自動車には、即時取得の規定の適用はない。",
        "answer": "○",
        "explanation": "登録済み自動車は不動産と同様の扱いで即時取得の対象にならない。ただし未登録の自動車は動産として即時取得が可能。",
        "exam_source": "p.34 参考問題1（H5-9-ア）",
    },
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "未登録自動車と即時取得", "law": "民法192条",
        "question_num": 2,
        "question_text": "Aの所有する未登録の自動車を保管しているBが、自己の所有物であると偽ってCに売却し現実の引渡しをした。CがBを所有者と過失なく信じたとしても、Cは即時取得することができない。",
        "answer": "×",
        "explanation": "未登録の自動車は動産であり、即時取得の対象となる。Cが善意無過失で引渡しを受ければ即時取得が成立する。",
        "exam_source": "p.34 参考問題2（H17-9-エ）",
    },
    # ── 参考問題1〜5（p.36〜37）登記と対抗 ──
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "対抗関係と前主後主①", "law": "民法177条",
        "question_num": 3,
        "question_text": "Aが甲土地をBに売却したが登記されない間に、AからCへ売却・登記がされ、さらにCからAへ売却・登記がされた。Bは、Aに対して甲土地の所有権の取得を対抗することができない。",
        "answer": "○",
        "explanation": "C→Aへの再移転により登記はA名義に戻っているが、BはAに登記の欠缺を主張されても対抗できない。なお、CはBに登記あり勝ちだったので、その後のAへの再譲渡はAが前主となる。",
        "exam_source": "p.36 参考問題1（H31-8-エ）",
    },
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "贈与と遺贈の対抗関係", "law": "民法177条",
        "question_num": 4,
        "question_text": "AがBに甲土地を贈与したが登記未了の間に、AがCに甲土地を遺贈した。Cが遺贈を原因として登記をしたとしても、CはBに対して甲土地を所有している旨を主張することができない。",
        "answer": "×",
        "explanation": "BとCは対抗関係に立つ。CがBより先に登記を具備すればCの勝ち。登記を先にしたCはBに所有権を主張できる。",
        "exam_source": "p.36 参考問題2（H25-7-改）",
    },
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "贈与と遺贈の対抗関係②", "law": "民法177条",
        "question_num": 5,
        "question_text": "AがBに甲土地を贈与（未登記）し、その後Cに遺贈する旨の遺言をして死亡した。BはCに対し、登記なくして甲土地全部の所有権の取得を対抗することができない。",
        "answer": "○",
        "explanation": "BとCは対抗関係に立つ。Bは登記なければCに対抗できない（先に登記した者が勝つ原則）。",
        "exam_source": "p.36 参考問題3（H28-22-4）",
    },
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "相続・贈与と遺贈の対抗", "law": "民法177条",
        "question_num": 6,
        "question_text": "被相続人が生前、推定相続人の一人Bに不動産を贈与（未登記）後、他の推定相続人Cに特定遺贈をし相続が開始した。贈与と遺贈の優劣は登記の具備の有無によって決まる。",
        "answer": "○",
        "explanation": "贈与（B）と遺贈（C）は対抗関係。先に登記を具備した方が勝つ（民法177条）。",
        "exam_source": "p.37 参考問題4（R5-23-ア）",
    },
    {
        "unit": "物権の世界", "book": 1, "part": 1, "chapter": 2,
        "topic": "前主後主の関係", "law": "民法177条",
        "question_num": 7,
        "question_text": "AがBに甲土地を売却したが登記がされない間に、BがCに甲土地を売却した。Cは、Aに対し、甲土地の所有権の取得を対抗することができる。",
        "answer": "○",
        "explanation": "A→B→Cは前主後主の関係（水の流れと同方向）。対抗関係（枝分かれ）ではない。CはAの承継人として当然にAに登記請求できる。",
        "exam_source": "p.37 参考問題5（R2-7-ア）",
    },
]

SEED_QUESTIONS_CH3 = [
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "心裡留保", "law": "民法93条",
        "question_num": 1,
        "question_text": "表意者が真意でないことを知りながら意思表示をした場合（心裡留保）、その意思表示は原則として有効である。",
        "answer": "○",
        "explanation": "民法93条1項。心裡留保による意思表示は原則有効。相手方が真意でないことを知り、または知ることができた場合は無効（但書）。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "通謀虚偽表示と第三者", "law": "民法94条",
        "question_num": 2,
        "question_text": "通謀虚偽表示による意思表示は無効であるが、その無効は善意の第三者に対抗することができない。",
        "answer": "○",
        "explanation": "民法94条。当事者間では無効だが、善意の第三者には無効を主張できない（善意の第三者が保護される）。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "通謀虚偽表示と第三者", "law": "民法94条",
        "question_num": 3,
        "question_text": "通謀虚偽表示による無効は、悪意の第三者に対しても対抗することができない。",
        "answer": "×",
        "explanation": "民法94条2項は善意の第三者を保護する規定。悪意の第三者（仮装行為であることを知っていた者）には無効を対抗できる。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "詐欺と強迫の違い", "law": "民法96条",
        "question_num": 4,
        "question_text": "詐欺による取消しは、善意無過失の第三者に対抗することができない。",
        "answer": "○",
        "explanation": "民法96条3項。詐欺による取消しは善意無過失の第三者を保護するため、その第三者には対抗できない。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "詐欺と強迫の違い", "law": "民法96条",
        "question_num": 5,
        "question_text": "強迫による取消しは、善意の第三者に対抗することができない。",
        "answer": "×",
        "explanation": "強迫による取消しは第三者が善意であっても対抗できる（民法96条3項は詐欺のみの規定）。強迫被害者の保護が優先される。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "取消しの効果", "law": "民法121条",
        "question_num": 6,
        "question_text": "取り消された行為は、初めから無効であったものとみなされる（遡及効）。",
        "answer": "○",
        "explanation": "民法121条。取消しには遡及効がある。取消し後は最初から無効だったことになる。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "取消権の消滅", "law": "民法126条",
        "question_num": 7,
        "question_text": "取消権は、追認できる時から5年、または行為の時から20年のいずれか早い方で時効消滅する。",
        "answer": "○",
        "explanation": "民法126条。追認できる時から5年（主観的起算点）または行為時から20年（客観的起算点）のいずれか早い方で消滅。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "債務不履行と帰責事由", "law": "民法415条",
        "question_num": 8,
        "question_text": "債務者が債務の本旨に従った履行をしない場合、債権者は損害賠償を請求することができるが、債務者に帰責事由がない場合はこの限りでない。",
        "answer": "○",
        "explanation": "民法415条。債務不履行による損害賠償の要件に帰責事由が含まれる。帰責事由がなければ免責される。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "催告解除の原則", "law": "民法541条",
        "question_num": 9,
        "question_text": "債務不履行があれば、債権者は催告なしにただちに契約を解除することができる。",
        "answer": "×",
        "explanation": "民法541条（催告解除）が原則。相当の期間を定めて催告し、その期間内に履行がない場合に解除できる。履行不能等（542条）は催告不要。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "履行不能と解除", "law": "民法542条",
        "question_num": 10,
        "question_text": "債務の履行が不能となった場合、債権者は催告することなく契約を解除することができる。",
        "answer": "○",
        "explanation": "民法542条1項1号。履行不能の場合は催告不要で即座に解除できる。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "解除の効果と損害賠償", "law": "民法545条",
        "question_num": 11,
        "question_text": "契約を解除した場合、損害賠償の請求は妨げられない。",
        "answer": "○",
        "explanation": "民法545条3項。解除しても別途損害賠償請求ができる。解除と損害賠償は並立する。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "危険負担", "law": "民法536条",
        "question_num": 12,
        "question_text": "売買契約締結後、引渡し前に目的物が当事者双方の責めに帰することができない事由で滅失した場合、買主は代金の支払を拒絶することができる。",
        "answer": "○",
        "explanation": "民法536条（改正後）。債務者の責めに帰すことができない事由で債務が不能となった場合、債権者（買主）は反対給付（代金支払）の履行を拒絶できる。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "保証の催告の抗弁権", "law": "民法452条",
        "question_num": 13,
        "question_text": "通常の保証人には催告の抗弁権があり、債権者がいきなり保証人に請求してきた場合、まず主たる債務者に催告すべき旨を主張できる。",
        "answer": "○",
        "explanation": "民法452条（催告の抗弁権）。通常の保証には補充性がある。連帯保証にはこの抗弁権がない（454条）。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "連帯保証の特徴", "law": "民法454条",
        "question_num": 14,
        "question_text": "連帯保証人には、催告の抗弁権も検索の抗弁権もない。",
        "answer": "○",
        "explanation": "民法454条。連帯保証は補充性がなく、債権者はいきなり連帯保証人に請求できる。",
        "exam_source": "",
    },
    {
        "unit": "債権の世界", "book": 1, "part": 1, "chapter": 3,
        "topic": "保証の付従性", "law": "民法448条",
        "question_num": 15,
        "question_text": "主たる債務が消滅すれば、保証債務も消滅する。",
        "answer": "○",
        "explanation": "保証の付従性（民法448条）。主債務が消滅すれば保証債務も消滅する。また、保証債務の額は主債務の額を超えることができない。",
        "exam_source": "",
    },
]

SEED_QUESTIONS_CH4 = [
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "債権者代位権と裁判外行使", "law": "民法423条",
        "question_num": 1,
        "question_text": "債権者代位権は、裁判外でも行使することができる。",
        "answer": "○",
        "explanation": "民法423条。債権者代位権は裁判外でも行使できる（詐害行為取消請求とは異なる点）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "債権者代位権の要件", "law": "民法423条",
        "question_num": 2,
        "question_text": "債権者代位権を行使するためには、原則として被保全債権の弁済期が到来していることが必要である。",
        "answer": "○",
        "explanation": "民法423条2項。弁済期到来前は原則として代位権を行使できない（保存行為は除く）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "詐害行為取消と裁判上の行使", "law": "民法424条",
        "question_num": 3,
        "question_text": "詐害行為取消請求は、裁判外で行使することができる。",
        "answer": "×",
        "explanation": "民法424条1項。詐害行為取消請求は「裁判所に請求する」と規定されており、裁判上でのみ行使できる（債権者代位権との違い）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "詐害行為取消の要件（悪意）", "law": "民法424条",
        "question_num": 4,
        "question_text": "詐害行為取消請求には、債務者の悪意と受益者の悪意の両方が必要であるが、債権者の悪意は要件ではない。",
        "answer": "○",
        "explanation": "民法424条1項。①債務者の悪意（債権者を害することを知っていた）②受益者の悪意が要件。債権者の悪意は不要。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "詐害行為と被保全債権の前後", "law": "民法424条",
        "question_num": 5,
        "question_text": "詐害行為取消請求をするためには、被保全債権が詐害行為の前の原因に基づいて生じたものでなければならない。",
        "answer": "○",
        "explanation": "民法424条3項。詐害行為後に生じた債権では取消請求できない。詐害行為から逃げる行為を取り消す制度のため。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "債権譲渡と通知主体", "law": "民法467条",
        "question_num": 6,
        "question_text": "債権の譲渡を債務者に対抗するためには、譲渡人が債務者に通知をするか、債務者が承諾をしなければならない。",
        "answer": "○",
        "explanation": "民法467条1項。「譲渡人の通知」または「債務者の承諾」が対抗要件。譲受人からの通知には対抗力がない。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "債権譲渡と譲受人の通知", "law": "民法467条",
        "question_num": 7,
        "question_text": "債権の譲渡を債務者に対抗するためには、譲受人が債務者に通知をすれば足りる。",
        "answer": "×",
        "explanation": "民法467条1項。対抗要件となるのは「譲渡人からの通知」または「債務者の承諾」。譲受人からの通知には対抗力がない（債務者保護の趣旨）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "債権の二重譲渡と到達時", "law": "民法467条",
        "question_num": 8,
        "question_text": "債権が二重に譲渡された場合の第三者への対抗の優劣は、確定日付ある通知が債務者に到達した日時の前後によって決まる。",
        "answer": "○",
        "explanation": "判例（最判昭49.3.7）。確定日付の日付自体ではなく、確定日付ある通知の債務者への到達時で優劣を決する。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "相殺の担保的効力", "law": "民法469条",
        "question_num": 9,
        "question_text": "債権が譲渡された場合、債務者は対抗要件具備時より前に取得した譲渡人に対する債権によって、譲受人に相殺を対抗することができる。",
        "answer": "○",
        "explanation": "民法469条1項。通知（対抗要件具備）前に反対債権を取得していれば、譲受人に相殺を主張できる（相殺の担保的効力）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "物権的請求権の種類", "law": "民法162条",
        "question_num": 10,
        "question_text": "物権的請求権には、返還請求権・妨害排除請求権・妨害予防請求権の3種類がある。",
        "answer": "○",
        "explanation": "物権的請求権は民法上の明文規定はないが、物権の性質（排他的支配）から当然に認められる。3種類ある。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "物権的請求権と善意・悪意", "law": "民法162条",
        "question_num": 11,
        "question_text": "土地所有者は、善意無過失で他人の土地を自分の土地と誤信して建物を建てた者に対し、建物の収去と土地の明渡しを請求することができる。",
        "answer": "○",
        "explanation": "物権的請求権は相手方の善意・悪意・過失の有無と無関係に行使できる。物権の排他性から当然に認められる。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "取得時効の要件", "law": "民法162条",
        "question_num": 12,
        "question_text": "他人の土地を自己の所有と過失なく信じて10年間平穏・公然と占有した者は、その土地の所有権を時効取得する。",
        "answer": "○",
        "explanation": "民法162条2項。善意無過失で10年間平穏・公然と占有すれば取得時効が成立する。悪意または有過失の場合は20年必要（1項）。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "取得時効と第三者の登記", "law": "民法162条・177条",
        "question_num": 13,
        "question_text": "取得時効が完成した後に第三者が不動産を取得して登記を具備した場合、時効取得者は登記なくして第三者に時効取得を対抗できる。",
        "answer": "×",
        "explanation": "時効完成後に登記を得た第三者とは対抗関係になる（判例）。先に登記した方が勝つ。時効取得者も登記を具備しなければ対抗できない。",
        "exam_source": "",
    },
    {
        "unit": "物権と債権", "book": 1, "part": 1, "chapter": 4,
        "topic": "賃借権の物権化", "law": "借地借家法31条",
        "question_num": 14,
        "question_text": "建物の賃貸借において、賃借人が建物の引渡しを受けていれば、その後に建物の所有権を取得した第三者に対しても賃借権を対抗することができる。",
        "answer": "○",
        "explanation": "借地借家法31条。建物の引渡しが借家権の対抗要件。登記がなくても引渡しを受けていれば第三者に対抗できる（「売買は賃貸借を破らない」）。",
        "exam_source": "",
    },
]

SEED_QUESTIONS_CH5 = [
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "担保物権の付従性", "law": "民法369条",
        "question_num": 1,
        "question_text": "主たる債務が消滅すれば、抵当権も消滅する。",
        "answer": "○",
        "explanation": "担保物権の付従性。主債務が消滅すれば担保物権も消滅する。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "担保物権の随伴性", "law": "民法369条",
        "question_num": 2,
        "question_text": "被担保債権が第三者に譲渡された場合、抵当権もその第三者に移転する。",
        "answer": "○",
        "explanation": "担保物権の随伴性。債権が譲渡されれば、それに伴って抵当権も移転する。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "担保物権の不可分性", "law": "民法369条",
        "question_num": 3,
        "question_text": "被担保債権の一部が弁済されても、債務が完全に消滅するまで抵当権は目的物全体に及ぶ。",
        "answer": "○",
        "explanation": "担保物権の不可分性。債務の一部が残っている限り、目的物全体に担保が及ぶ。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "抵当権の非占有担保性", "law": "民法369条",
        "question_num": 4,
        "question_text": "抵当権を設定しても、設定者（担保提供者）はそのまま目的物を使用・収益することができる。",
        "answer": "○",
        "explanation": "民法369条。抵当権は非占有担保（占有移転なしに設定できる）。質権と異なり設定者はそのまま目的物を使用できる。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "抵当権の対抗要件", "law": "民法177条・369条",
        "question_num": 5,
        "question_text": "不動産の抵当権設定は、登記をしなければ第三者に対抗することができない。",
        "answer": "○",
        "explanation": "抵当権も物権であるから、民法177条の対抗要件（登記）が必要。登記なしでは第三者に抵当権を主張できない。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "物上代位と差押え", "law": "民法304条・372条",
        "question_num": 6,
        "question_text": "抵当権者が物上代位権を行使するためには、払渡し又は引渡しの前に差押えをしなければならない。",
        "answer": "○",
        "explanation": "民法304条（先取特権）・372条（抵当権への準用）。物上代位の行使には「払渡し又は引渡し前の差押え」が必要。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "物上代位と保険金", "law": "民法304条・372条",
        "question_num": 7,
        "question_text": "抵当権の目的物が火災で滅失した場合、抵当権者は差押えをすることなく火災保険金に物上代位権を行使することができる。",
        "answer": "×",
        "explanation": "民法304条・372条。物上代位権の行使には「払渡し（保険金の支払い）前の差押え」が必要。差押えなしに物上代位はできない。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "抵当権設定後の賃借権", "law": "民法369条・387条",
        "question_num": 8,
        "question_text": "抵当権設定後に設定された賃借権は、抵当権者の同意（民法387条）がない限り、抵当権の実行により消滅する。",
        "answer": "○",
        "explanation": "抵当権設定後の賃借権は抵当権に劣後するため、抵当権実行（競売）によって消滅するのが原則。民法387条の同意があれば保護される。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "根抵当権と付従性", "law": "民法398条の2",
        "question_num": 9,
        "question_text": "根抵当権は、特定の被担保債権が消滅しても根抵当権は消滅しない（付従性なし）。",
        "answer": "○",
        "explanation": "民法398条の2。根抵当権は付従性がない。個々の債権が消滅しても、極度額・債権の範囲・債務者が変わらない限り存続する。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "物上保証人の責任範囲", "law": "民法351条・372条",
        "question_num": 10,
        "question_text": "物上保証人は自己の財産に担保を設定して他人の債務を担保する者であり、担保物の価値の限度で責任を負う（有限責任）。",
        "answer": "○",
        "explanation": "物上保証人は有限責任（担保物の限度）。保証人が無限責任（全財産で責任）であるのと対比。物上保証人が弁済すれば主債務者に求償できる（民法351条・372条）。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "担保物権の種類", "law": "民法295条・303条・342条・369条",
        "question_num": 11,
        "question_text": "留置権・先取特権は法律の規定により当然に発生する法定担保物権であり、質権・抵当権は当事者の合意によって設定される約定担保物権である。",
        "answer": "○",
        "explanation": "法定担保物権（留置権295条・先取特権303条）と約定担保物権（質権342条・抵当権369条）の区別。",
        "exam_source": "",
    },
    {
        "unit": "担保物権", "book": 1, "part": 1, "chapter": 5,
        "topic": "抵当権の優先弁済権", "law": "民法369条",
        "question_num": 12,
        "question_text": "抵当権者は、競売による売却代金から、他の一般債権者に先立って弁済を受けることができる。",
        "answer": "○",
        "explanation": "民法369条（抵当権の内容）。優先弁済権は抵当権の最大の特徴。競売代金から他の債権者より先に弁済を受けられる。",
        "exam_source": "",
    },
]


def _seed_questions_by_unit(unit: str, questions: list, label: str):
    added = 0
    for q in questions:
        with get_conn() as conn:
            exists = conn.execute(
                "SELECT 1 FROM questions WHERE unit=? AND question_num=?",
                (unit, q["question_num"])
            ).fetchone()
        if not exists:
            insert_question(**q)
            added += 1
    if added:
        print(f"{label}問題 {added}件を新規投入しました")
    else:
        print(f"{label}問題全件投入済みです")


def _replace_questions_by_unit(unit: str, questions: list, label: str):
    """既存を全削除して最新リストで入れ直す（教科書改訂時に使用）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM questions WHERE unit=?", (unit,))
    for q in questions:
        insert_question(**q)
    print(f"{label}問題 全{len(questions)}件を入れ直しました")


def seed():
    init_db()
    migrate_columns()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM questions WHERE unit='即時取得'").fetchone()[0]
    if count > 0:
        print(f"既にシード済み（{count}件）。スキップします。")
    else:
        for q in SEED_QUESTIONS:
            insert_question(**q)
        print(f"{len(SEED_QUESTIONS)}件を投入しました → {DB_PATH}")
    migrate_existing_data()  # シード後に実行
    migrate_topics()         # topicが空の行を更新

    for unit, data, label in [
        ("物権の世界", SEED_QUESTIONS_CH2, "第2章"),
        ("債権の世界", [], "第3章"),
        ("物権と債権", [], "第4章"),
        ("担保物権",   [], "第5章"),
    ]:
        _seed_questions_by_unit(unit, data, label)

    with get_conn() as conn:
        kcount = conn.execute("SELECT COUNT(*) FROM knowledge WHERE unit='即時取得'").fetchone()[0]
    if kcount > 0:
        print(f"解説ナレッジ既にシード済み（{kcount}件）。スキップします。")
    else:
        for k in SEED_KNOWLEDGE:
            insert_knowledge(**k)
        print(f"解説ナレッジ {len(SEED_KNOWLEDGE)}件を投入しました")

    with get_conn() as conn:
        c1count = conn.execute("SELECT COUNT(*) FROM knowledge WHERE unit='民法の本質'").fetchone()[0]
    if c1count > 0:
        print(f"第1章ナレッジ既にシード済み（{c1count}件）。スキップします。")
    else:
        for k in SEED_KNOWLEDGE_CHAPTER1:
            insert_knowledge(**k)
        print(f"第1章ナレッジ {len(SEED_KNOWLEDGE_CHAPTER1)}件を投入しました")

    for data, label in [
        (SEED_KNOWLEDGE_CH2, "第2章"),
        (SEED_KNOWLEDGE_CH3, "第3章"),
        (SEED_KNOWLEDGE_CH4, "第4章"),
        (SEED_KNOWLEDGE_CH5, "第5章"),
    ]:
        added = 0
        for k in data:
            with get_conn() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM knowledge WHERE unit=? AND title=?",
                    (k["unit"], k["title"])
                ).fetchone()
            if not exists:
                insert_knowledge(**k)
                added += 1
        if added:
            print(f"{label}ナレッジ {added}件を新規投入しました")
        else:
            print(f"{label}ナレッジ全件投入済みです")


# ────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────
def _print_row(r):
    print(f"\n[{r['id']}] 第{r['question_num']}問 ({r['unit']}) {r['answer']}")
    print(f"  問: {r['question_text'][:60]}...")
    print(f"  解: {r['explanation']}")
    if r.get('exam_source'):
        print(f"  出典: {r['exam_source']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", help="キーワード検索")
    parser.add_argument("--list",   action="store_true", help="全件表示")
    parser.add_argument("--seed",   action="store_true", help="シードのみ実行")
    args = parser.parse_args()

    seed()

    if args.search:
        results = search(args.search)
        print(f"\n検索: 「{args.search}」→ {len(results)}件")
        for r in results:
            _print_row(r)
    elif args.list:
        rows = list_all()
        print(f"\n全{len(rows)}件:")
        for r in rows:
            print(f"  [{r['id']}] 第{r['question_num']}問 ({r['unit']}) {r['answer']}  {r['question_text'][:40]}...")
    else:
        print("使い方: --search キーワード  または  --list")
