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

DB_PATH = os.path.join(os.path.dirname(__file__), "knowledge.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                unit           TEXT    NOT NULL,
                law            TEXT,
                question_num   INTEGER,
                question_text  TEXT    NOT NULL,
                answer         TEXT    NOT NULL,
                explanation    TEXT,
                exam_source    TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts
            USING fts5(
                unit,
                question_text,
                answer,
                explanation,
                exam_source,
                content='questions',
                content_rowid='id',
                tokenize='trigram'
            );

            CREATE TRIGGER IF NOT EXISTS questions_ai AFTER INSERT ON questions BEGIN
                INSERT INTO questions_fts(rowid, unit, question_text, answer, explanation, exam_source)
                VALUES (new.id, new.unit, new.question_text, new.answer, new.explanation, new.exam_source);
            END;

            CREATE TRIGGER IF NOT EXISTS questions_ad AFTER DELETE ON questions BEGIN
                INSERT INTO questions_fts(questions_fts, rowid, unit, question_text, answer, explanation, exam_source)
                VALUES ('delete', old.id, old.unit, old.question_text, old.answer, old.explanation, old.exam_source);
            END;

            CREATE TRIGGER IF NOT EXISTS questions_au AFTER UPDATE ON questions BEGIN
                INSERT INTO questions_fts(questions_fts, rowid, unit, question_text, answer, explanation, exam_source)
                VALUES ('delete', old.id, old.unit, old.question_text, old.answer, old.explanation, old.exam_source);
                INSERT INTO questions_fts(rowid, unit, question_text, answer, explanation, exam_source)
                VALUES (new.id, new.unit, new.question_text, new.answer, new.explanation, new.exam_source);
            END;

            -- ── 解説ナレッジテーブル ──
            CREATE TABLE IF NOT EXISTS knowledge (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                unit       TEXT NOT NULL,
                category   TEXT,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                law        TEXT,
                source     TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(
                unit, category, title, content, law,
                content='knowledge',
                content_rowid='id',
                tokenize='trigram'
            );

            CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts(rowid, unit, category, title, content, law)
                VALUES (new.id, new.unit, new.category, new.title, new.content, new.law);
            END;

            CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, unit, category, title, content, law)
                VALUES ('delete', old.id, old.unit, old.category, old.title, old.content, old.law);
            END;
        """)


def insert_question(unit, law, question_num, question_text, answer, explanation, exam_source=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO questions
               (unit, law, question_num, question_text, answer, explanation, exam_source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (unit, law, question_num, question_text, answer, explanation, exam_source)
        )


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
# シードデータ（即時取得 11問）
# ────────────────────────────────────────────────
SEED_QUESTIONS = [
    {
        "unit": "即時取得",
        "law": "民法192条・188条",
        "question_num": 1,
        "question_text": "Aが、Bの所有する動産甲を無権利のCから買い受けて現実の引渡しを受けた場合において、即時取得を主張するためには、自己に過失がなかったことを立証しなければならない。",
        "answer": "×",
        "explanation": "無過失は推定される（民法188条）。立証不要。",
        "exam_source": "H30-8-1",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 2,
        "question_text": "CはAが所有する時計を預かっていたBとの間で、Bが所有者であると誤信してその時計の購入をし引渡しを受けた。この場合、Cが善意であれば過失があったとしてもその時計の所有権を取得することができる。",
        "answer": "×",
        "explanation": "善意だけでは不十分。無過失も必要（192条）。",
        "exam_source": "",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 3,
        "question_text": "動産の買主が引渡しを受けたとき、その動産が売主の所有に属しないことにつき善意であっても、その後に悪意となれば即時取得の効果は失われる。",
        "answer": "×",
        "explanation": "占有開始時に善意無過失であれば、その後悪意になっても効果は失われない。",
        "exam_source": "S58-12-5",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 4,
        "question_text": "即時取得の制度は、取引の安全を保護するため、動産の占有に公信力を与えたものである。",
        "answer": "○",
        "explanation": "正しい。即時取得＝動産占有の公信力。",
        "exam_source": "",
    },
    {
        "unit": "即時取得",
        "law": "民法188条",
        "question_num": 5,
        "question_text": "占有者が、占有物の上に行使する権利は、これを適法に有するものと推定されるので、即時取得を主張する者は、無過失を立証する責任を負わない。",
        "answer": "○",
        "explanation": "民法188条による推定。無過失の立証不要。",
        "exam_source": "H5-9-オ",
    },
    {
        "unit": "即時取得",
        "law": "民法192条・188条",
        "question_num": 6,
        "question_text": "Aからデジタルカメラ甲を賃借していたFは、甲をBに売却し、その現実の引渡しをした。この場合において、BはAに対して甲の即時取得を主張するためには、Fが甲に関し無権利者であることについて自己が善意無過失であったことを証明しなければならない。",
        "answer": "×",
        "explanation": "民法188条の推定により、立証不要（相手方が有過失を立証する）。",
        "exam_source": "H25-8-4改",
    },
    {
        "unit": "即時取得",
        "law": "民法188条",
        "question_num": 7,
        "question_text": "占有者は、占有物の上に行使する権利を適法に有するものと推定される。",
        "answer": "○",
        "explanation": "民法188条の通り。",
        "exam_source": "S58-10-1",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 8,
        "question_text": "Aの所有する甲動産を保管しているBが、甲動産を自己の所有物であると偽って甲動産をCに売却した場合において、代金支払時にCが甲動産の所有者がBであると信じ、かつ、そう信じるについて過失がないときは、代金支払後、引渡しを受けるまでの間に所有者がBでないことをCが知ったとしても、Cは甲動産を即時取得することができる。",
        "answer": "×",
        "explanation": "無過失の要件は「占有開始時（引渡し時）」に要求される。引渡し前に悪意になれば即時取得不可。",
        "exam_source": "H17",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 9,
        "question_text": "Aからデジタルカメラ甲の寄託を受けていたEは、甲をBに売却したが、その際、Bは、Eが甲に関し無権利者であることについて善意無過失であった。この場合において、Bは、その後にEから甲の現実の引渡しを受けた際、Eが甲に関し無権利者であることについて悪意となっていたときは、甲を即時取得しない。",
        "answer": "○",
        "explanation": "引渡し時（占有開始時）に悪意→即時取得しない。",
        "exam_source": "H25-8-3改",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 10,
        "question_text": "A所有の甲動産をAから預かっていたBが、甲動産がBの所有であると過失なく信じていたCとの間で甲動産の売買契約を締結した後、Cが、甲動産についてBが無権利であることを知り、甲動産の現実の引渡しを受けた場合には、Cは、甲動産を即時取得することができない。",
        "answer": "○",
        "explanation": "引渡し時に悪意→即時取得不可。",
        "exam_source": "R7-9-ウ",
    },
    {
        "unit": "即時取得",
        "law": "民法192条",
        "question_num": 11,
        "question_text": "教授AがBから預かっていたビデオカメラをBに無断でCに譲渡した場合、Cは無権利者からの譲受人であるから、原則として所有権を取得することができない。",
        "answer": "×",
        "explanation": "即時取得（192条）の要件を満たせば取得できる可能性あり。「原則としてできない」は正しいが、例外として即時取得がある。",
        "exam_source": "",
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


def seed():
    init_db()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM questions WHERE unit='即時取得'").fetchone()[0]
    if count > 0:
        print(f"既にシード済み（{count}件）。スキップします。")
    else:
        for q in SEED_QUESTIONS:
            insert_question(**q)
        print(f"{len(SEED_QUESTIONS)}件を投入しました → {DB_PATH}")

    with get_conn() as conn:
        kcount = conn.execute("SELECT COUNT(*) FROM knowledge WHERE unit='即時取得'").fetchone()[0]
    if kcount > 0:
        print(f"解説ナレッジ既にシード済み（{kcount}件）。スキップします。")
    else:
        for k in SEED_KNOWLEDGE:
            insert_knowledge(**k)
        print(f"解説ナレッジ {len(SEED_KNOWLEDGE)}件を投入しました")


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
