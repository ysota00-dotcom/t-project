"""
使い方:
  python main.py --input story.txt
  python main.py --text "Yasu（焦った顔で）..."
"""
import argparse
import os
import time
from dotenv import load_dotenv

load_dotenv()

from scene_extractor import extract_scenes
from svg_renderer    import render_panel
from html_builder    import build_html

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def run(text: str):
    start = time.time()
    print("\n" + "="*50)
    print("  TomomiとYasu 法律ストーリー生成")
    print("="*50)

    # STEP 1: シーン抽出
    print("\n[STEP 1] シーン抽出中...")
    data = extract_scenes(text)
    scene_01 = data["scene_01"]
    scene_02 = data["scene_02"]
    print(f"  シーン1: {scene_01['location']} / {[c['emotion'] for c in scene_01['characters']]}")
    print(f"  シーン2: {scene_02['location']} / {[c['emotion'] for c in scene_02['characters']]}")

    # STEP 2: SVGパネル生成（ゼロ秒）
    print("\n[STEP 2] SVGパネル生成中...")
    prop_name = data.get("prop", {}).get("name", "")
    svg1 = render_panel(scene_01, prop_name)
    svg2 = render_panel(scene_02, prop_name)
    print("  完了（APIコールなし）")

    # STEP 3: HTML出力
    print("\n[STEP 3] HTML出力中...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_path = build_html(data, svg1, svg2, OUTPUT_DIR)

    elapsed = time.time() - start
    print("\n" + "="*50)
    print(f"  完成！ ({elapsed:.1f}秒)")
    print(f"  → {html_path} をブラウザで開いてください")
    print("="*50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="TomomiとYasu 法律ストーリー生成")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="テキストファイルのパス")
    group.add_argument("--text",  help="テキストを直接入力")
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text

    run(text)


if __name__ == "__main__":
    main()
