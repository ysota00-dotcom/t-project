import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

EXTRACT_PROMPT = """
以下のテキストを読んでJSON形式で出力してください。

【テキスト】
{text}

【出力するJSONの構造】
{{
  "scene_01": {{
    "location": "場所（例：教室、喫茶店）",
    "characters": [
      {{ "name": "Yasu",   "emotion": "感情（例：困惑、焦り、ムッとした）", "pose": "ポーズ（例：前のめり、腕を組む）" }},
      {{ "name": "Tomomi", "emotion": "感情（例：冷静、真剣）",             "pose": "ポーズ（例：指を立てる、頷く）" }}
    ],
    "balloons": [
      {{ "speaker": "Yasu",   "text": "最も印象的なセリフ（20文字以内）", "position": "left" }},
      {{ "speaker": "Tomomi", "text": "最も印象的なセリフ（20文字以内）", "position": "right" }}
    ]
  }},
  "scene_02": {{
    "location": "場所",
    "characters": [
      {{ "name": "Yasu",   "emotion": "感情", "pose": "ポーズ" }},
      {{ "name": "Tomomi", "emotion": "感情", "pose": "ポーズ" }}
    ],
    "balloons": [
      {{ "speaker": "Yasu",   "text": "最も印象的なセリフ（20文字以内）", "position": "left" }},
      {{ "speaker": "Tomomi", "text": "最も印象的なセリフ（20文字以内）", "position": "right" }}
    ]
  }},
  "prop": {{
    "name": "ストーリーに登場する主な動産。時計/デジタルカメラ/ビデオカメラ/宝石/動産/なし のいずれか"
  }},
  "panel1_after": "パネル1を挿入する直前のテキスト行をそのまま抜粋（改行なし・完全一致できる行）",
  "panel2_after": "パネル2を挿入する直前のテキスト行をそのまま抜粋（改行なし・完全一致できる行）"
}}

ルール：
- scene_01：最初のYasu-Tomomiの会話シーン
- scene_02：最後のYasu-Tomomiの会話シーン
- prop.name：ストーリーの中心となる動産の種類。登場しない場合は「なし」
- panel1_after：scene_01の最後のセリフ行（この行の後にパネル1を挿入）
- panel2_after：scene_02の最後のセリフ行 または「まとめ」セクションの直前行
- JSON以外は出力しない
"""


def extract_scenes(text: str, max_retries: int = 3) -> dict:
    print("シーン抽出中...")
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": EXTRACT_PROMPT.format(text=text)}]
            )
            raw = message.content[0].text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            result = json.loads(raw)
            result["full_text"] = text
            print("シーン抽出完了")
            return result
        except json.JSONDecodeError as e:
            last_err = e
            print(f"  JSONパースエラー（試行{attempt}/{max_retries}）、リトライ...")
    raise ValueError(f"シーン抽出に{max_retries}回失敗しました: {last_err}")
