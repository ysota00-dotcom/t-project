"""
問題番号からストーリーを自動生成する。
使い方:
  python story_generator.py --question 4
  python story_generator.py --question 4 --preview   # 生成テキストだけ表示（HTML未生成）
"""
import argparse
import os
import time
from dotenv import load_dotenv
import anthropic

load_dotenv()

from knowledge_db import get_by_unit_num, seed

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CHARACTER_PROMPT = """
■ Yasu（男性・30代・素人）
- 口調：タメ口、砕けた話し言葉
- 一人称：俺
- 性格：好奇心旺盛だが法律は苦手。すぐ混乱する。たまにズレた解釈をする
- 口癖：「えっ、それってどういうことや？」「なるほどな！つまり〜ってことか」「それ俺に関係ある話？」
- セリフ例：「えー、持ってるだけで所有者扱いされんの？それ怖くない？」

■ Tomomi（女性・30代・見習い司法書士）
- 口調：ため口、でもやさしい口調
- 一人称：私
- 性格：穏やか、論理的、Yasuの誤解を優しく正す。条文番号をさらっと言う
- Yasuのことは「Yasuさん」と呼ぶ
- 口癖：「そうやね、ポイントは〜」「民法○条がそう定めてるんよ」「いい質問やね！」
- セリフ例：「Yasuさんの言い方だと惜しいね。善意だけでなく無過失も必要なんよ」
"""

STORY_PROMPT = """\
あなたはTomomiとYasuによる法律解説ストーリーの脚本家です。

{character_prompt}

【ストーリーの構成】
1. Yasuが日常の場面（買い物・友人トラブル等）で法律に絡む問題に直面する
2. Tomomiに相談し、会話の中で概念を理解していく
3. 【図解ブロック】で重要ポイントを整理
4. YasuがTomomiの説明を自分の言葉で言い換えて「腑に落ちた」で締める

【出力フォーマット】
- 冒頭に「問題：〈問題文〉」「答え：〈○または×〉」を置く
- セリフは「Yasu（感情）「セリフ」」の形式（1行に収める）
- 感情は（驚いた顔で）（首をかしげながら）（ポンと手を叩いて）など具体的に
- 【ブロック名】で囲んだ図解を1〜2箇所挿入
- 最後に「まとめ」セクションを置く
- 全体500〜700文字程度
- ストーリー本文のみ出力（前置き・説明不要）

【今回のお題】
単元：{unit}
関連条文：{law}
問題文：{question_text}
答え：{answer}
解説：{explanation}
"""


def generate_story(unit: str, question_num: int) -> str:
    seed()
    q = get_by_unit_num(unit, question_num)
    if not q:
        raise ValueError(f"問題が見つかりません: {unit} 第{question_num}問")

    prompt = STORY_PROMPT.format(
        character_prompt=CHARACTER_PROMPT,
        unit=q["unit"],
        law=q["law"] or "",
        question_text=q["question_text"],
        answer=q["answer"],
        explanation=q["explanation"] or "",
    )

    print(f"ストーリー生成中（{unit} 第{question_num}問）...")
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", type=int, required=True, help="問題番号（1〜11）")
    parser.add_argument("--unit", default="即時取得", help="単元名（デフォルト：即時取得）")
    parser.add_argument("--preview", action="store_true", help="テキストのみ表示")
    args = parser.parse_args()

    start = time.time()
    story = generate_story(args.unit, args.question)

    if args.preview:
        print("\n" + "="*50)
        print(story)
        print("="*50)
        print(f"\n({time.time()-start:.1f}秒)")
    else:
        from svg_renderer import render_panel
        from html_builder import build_html
        from scene_extractor import extract_scenes

        data = extract_scenes(story)
        prop_name = data.get("prop", {}).get("name", "")
        svg1 = render_panel(data["scene_01"], prop_name)
        svg2 = render_panel(data["scene_02"], prop_name)
        OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
        fname = f"story_{args.question:02d}.html"
        html_path = build_html(data, svg1, svg2, OUTPUT_DIR, filename=fname)
        print(f"\n完成！({time.time()-start:.1f}秒) → {html_path}")
