"""
SVGキャラクターパネル生成
感情・ポーズに応じてYasu/Tomomiのキャラクターを描画する
"""

BACKGROUNDS = {
    "教室":  ("#e8e4d8", "#3a6b4a", "#4a7a58", "民法 条文"),
    "喫茶店": ("#f0e8d8", "#6b4a3a", "#7a5a48", "café"),
    "カフェ": ("#f0e8d8", "#6b4a3a", "#7a5a48", "café"),
    "図書館": ("#e4e8e0", "#3a4a6b", "#485878", "Library"),
    "事務所": ("#e8e8e4", "#4a4a6b", "#5a5a78", "Law Office"),
    "default": ("#e8e4d8", "#3a5a6b", "#4a6a7a", ""),
}


def _classify_emotion(emotion: str) -> str:
    if any(w in emotion for w in ["ムッ", "困", "焦", "不満", "驚", "戸惑", "呆"]):
        return "troubled"
    if any(w in emotion for w in ["ほっ", "安心", "笑", "納得", "嬉", "微笑", "苦笑", "喜", "満足"]):
        return "happy"
    if any(w in emotion for w in ["真剣", "考え", "冷静", "落ち着", "確信", "鋭", "集中", "首"]):
        return "serious"
    return "default"


def _classify_pose(pose: str) -> str:
    if any(w in pose for w in ["前のめり", "身を乗", "乗り出"]):
        return "forward"
    if any(w in pose for w in ["指差", "指を立", "人差し指", "指摘"]):
        return "pointing"
    if any(w in pose for w in ["腕を組", "腕組", "両腕"]):
        return "crossed"
    if any(w in pose for w in ["頭", "顎", "あご", "考え", "手を当", "頷"]):
        return "thinking"
    if any(w in pose for w in ["脱力", "肩落", "がっく", "落と"]):
        return "drooping"
    return "default"


# ── 顔パーツ定義 ──────────────────────────────
FACE_FEATURES = {
    "troubled": {
        "brows": '<path d="M-26,22 Q-16,15 -6,20" stroke="#333" stroke-width="3" fill="none" stroke-linecap="round"/>'
                 '<path d="M6,20 Q16,15 26,22" stroke="#333" stroke-width="3" fill="none" stroke-linecap="round"/>',
        "eyes": '<ellipse cx="-16" cy="33" rx="9" ry="9" fill="white"/>'
                '<ellipse cx="16" cy="33" rx="9" ry="9" fill="white"/>'
                '<circle cx="-16" cy="34" r="6" fill="#2a1a0a"/><circle cx="-14" cy="32" r="2" fill="white"/>'
                '<circle cx="16" cy="34" r="6" fill="#2a1a0a"/><circle cx="18" cy="32" r="2" fill="white"/>',
        "mouth": '<path d="M-10,56 Q0,52 10,56" stroke="#a05050" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "blush": "",
    },
    "happy": {
        "brows": '<path d="M-24,20 Q-14,18 -5,21" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
                 '<path d="M5,21 Q14,18 24,20" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "eyes": '<path d="M-24,32 Q-16,26 -8,32" stroke="#2a1a0a" stroke-width="3" fill="none" stroke-linecap="round"/>'
                '<path d="M8,32 Q16,26 24,32" stroke="#2a1a0a" stroke-width="3" fill="none" stroke-linecap="round"/>',
        "mouth": '<path d="M-12,53 Q0,64 12,53" stroke="#a05050" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "blush": '<ellipse cx="-27" cy="46" rx="11" ry="7" fill="#ffaaaa" opacity="0.4"/>'
                 '<ellipse cx="27" cy="46" rx="11" ry="7" fill="#ffaaaa" opacity="0.4"/>',
    },
    "serious": {
        "brows": '<path d="M-24,20 Q-14,18 -5,20" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
                 '<path d="M5,20 Q14,18 24,20" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "eyes": '<ellipse cx="-15" cy="32" rx="8" ry="9" fill="white"/>'
                '<ellipse cx="15" cy="32" rx="8" ry="9" fill="white"/>'
                '<circle cx="-15" cy="33" r="6" fill="#2a1a0a"/><circle cx="-13" cy="31" r="2" fill="white"/>'
                '<circle cx="15" cy="33" r="6" fill="#2a1a0a"/><circle cx="17" cy="31" r="2" fill="white"/>',
        "mouth": '<path d="M-8,54 Q0,56 8,54" stroke="#a05050" stroke-width="2" fill="none" stroke-linecap="round"/>',
        "blush": "",
    },
    "default": {
        "brows": '<path d="M-24,21 Q-14,19 -5,21" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
                 '<path d="M5,21 Q14,19 24,21" stroke="#333" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "eyes": '<ellipse cx="-15" cy="32" rx="8" ry="8" fill="white"/>'
                '<ellipse cx="15" cy="32" rx="8" ry="8" fill="white"/>'
                '<circle cx="-15" cy="33" r="5" fill="#2a1a0a"/><circle cx="-13" cy="31" r="1.5" fill="white"/>'
                '<circle cx="15" cy="33" r="5" fill="#2a1a0a"/><circle cx="17" cy="31" r="1.5" fill="white"/>',
        "mouth": '<path d="M-7,53 Q0,57 7,53" stroke="#a05050" stroke-width="2" fill="none" stroke-linecap="round"/>',
        "blush": "",
    },
}

# ── 腕ポーズ定義 ──────────────────────────────
YASU_ARMS = {
    "default":  ('<path d="M-38,112 Q-65,148 -56,180" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-54" cy="183" rx="13" ry="11" fill="#f0c8a0"/>'
                 '<path d="M38,112 Q65,148 56,180" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="54" cy="183" rx="13" ry="11" fill="#f0c8a0"/>'),
    "forward":  ('<path d="M-38,112 Q-72,135 -62,168" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-60" cy="171" rx="13" ry="11" fill="#f0c8a0"/>'
                 '<path d="M38,112 Q75,130 80,100" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="80" cy="96" rx="13" ry="11" fill="#f0c8a0"/>'),
    "pointing": ('<path d="M-38,112 Q-65,148 -56,180" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-54" cy="183" rx="13" ry="11" fill="#f0c8a0"/>'
                 '<path d="M38,112 Q75,95 80,60" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="80" cy="56" rx="12" ry="11" fill="#f0c8a0"/>'
                 '<rect x="76" y="36" width="8" height="26" rx="4" fill="#f0c8a0"/>'),
    "crossed":  ('<path d="M-38,112 Q-10,145 30,148" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<path d="M38,112 Q10,145 -30,148" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'),
    "thinking": ('<path d="M-38,112 Q-65,148 -56,180" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-54" cy="183" rx="13" ry="11" fill="#f0c8a0"/>'
                 '<path d="M38,112 Q72,105 78,80" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="78" cy="76" rx="13" ry="11" fill="#f0c8a0"/>'),
    "drooping": ('<path d="M-38,112 Q-55,165 -45,198" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-43" cy="201" rx="13" ry="11" fill="#f0c8a0"/>'
                 '<path d="M38,112 Q55,165 45,198" stroke="#c8a878" stroke-width="22" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="43" cy="201" rx="13" ry="11" fill="#f0c8a0"/>'),
}

TOMOMI_ARMS = {
    "default":  ('<path d="M-36,112 Q-62,148 -52,178" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-50" cy="181" rx="12" ry="10" fill="#f0c8a0"/>'
                 '<path d="M36,112 Q62,148 52,178" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="50" cy="181" rx="12" ry="10" fill="#f0c8a0"/>'),
    "forward":  ('<path d="M-36,112 Q-68,132 -60,165" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-58" cy="168" rx="12" ry="10" fill="#f0c8a0"/>'
                 '<path d="M36,112 Q72,128 76,100" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="76" cy="96" rx="12" ry="10" fill="#f0c8a0"/>'),
    "pointing": ('<path d="M-36,112 Q-62,148 -52,178" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-50" cy="181" rx="12" ry="10" fill="#f0c8a0"/>'
                 '<path d="M36,112 Q72,96 76,62" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="76" cy="58" rx="11" ry="10" fill="#f0c8a0"/>'
                 '<rect x="73" y="38" width="7" height="24" rx="3.5" fill="#f0c8a0"/>'),
    "crossed":  ('<path d="M-36,112 Q-8,142 28,145" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<path d="M36,112 Q8,142 -28,145" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'),
    "thinking": ('<path d="M-36,112 Q-62,148 -52,178" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-50" cy="181" rx="12" ry="10" fill="#f0c8a0"/>'
                 '<path d="M36,112 Q70,104 74,78" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="74" cy="74" rx="12" ry="10" fill="#f0c8a0"/>'),
    "drooping": ('<path d="M-36,112 Q-52,162 -42,194" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="-40" cy="197" rx="12" ry="10" fill="#f0c8a0"/>'
                 '<path d="M36,112 Q52,162 42,194" stroke="#c8a878" stroke-width="20" fill="none" stroke-linecap="round"/>'
                 '<ellipse cx="40" cy="197" rx="12" ry="10" fill="#f0c8a0"/>'),
}


def _yasu_svg(emotion: str, pose: str, cx: int, cy: int) -> str:
    em  = _classify_emotion(emotion)
    po  = _classify_pose(pose)
    f   = FACE_FEATURES[em]
    arms = YASU_ARMS.get(po, YASU_ARMS["default"])
    transform = f"translate({cx},{cy})"
    if po == "forward":
        transform = f"translate({cx},{cy}) rotate(-5,0,130)"
    return f'''<g transform="{transform}">
      <!-- ジーンズ -->
      <rect x="-30" y="188" width="26" height="88" rx="10" fill="#5878a8"/>
      <rect x="4"   y="188" width="26" height="88" rx="10" fill="#5878a8"/>
      <!-- 体（ベージュセーター） -->
      <rect x="-40" y="88" width="80" height="106" rx="13" fill="#c8a878"/>
      <rect x="-40" y="88" width="80" height="22"  rx="13" fill="#b89860"/>
      <!-- 首 -->
      <rect x="-13" y="72" width="26" height="22" rx="4" fill="#f0c8a0"/>
      <!-- 腕 -->
      {arms}
      <!-- 頭 -->
      <ellipse cx="0" cy="44" rx="49" ry="53" fill="#f0c8a0"/>
      <!-- 黒髪 -->
      <path d="M-49,18 Q-46,-30 0,-40 Q46,-30 49,18 Q38,4 20,0 Q0,-8 -20,0 Q-38,4 -49,18Z" fill="#1a1a1a"/>
      <path d="M-49,14 Q-57,32 -53,48" stroke="#1a1a1a" stroke-width="9" fill="none" stroke-linecap="round"/>
      <!-- 顔パーツ -->
      {f["brows"]}
      {f["eyes"]}
      {f["mouth"]}
      {f["blush"]}
      <!-- 名前 -->
      <text x="0" y="302" text-anchor="middle" fill="#666" font-size="14" font-family="sans-serif">Yasu</text>
    </g>'''


def _tomomi_svg(emotion: str, pose: str, cx: int, cy: int) -> str:
    em   = _classify_emotion(emotion)
    po   = _classify_pose(pose)
    f    = FACE_FEATURES[em]
    arms = TOMOMI_ARMS.get(po, TOMOMI_ARMS["default"])
    transform = f"translate({cx},{cy})"
    if po == "forward":
        transform = f"translate({cx},{cy}) rotate(5,0,130)"
    return f'''<g transform="{transform}">
      <!-- ジーンズ -->
      <rect x="-28" y="186" width="24" height="88" rx="10" fill="#5878a8"/>
      <rect x="4"   y="186" width="24" height="88" rx="10" fill="#5878a8"/>
      <!-- 体 -->
      <rect x="-38" y="88" width="76" height="104" rx="13" fill="#c8a878"/>
      <rect x="-38" y="88" width="76" height="22"  rx="13" fill="#b89860"/>
      <!-- 首 -->
      <rect x="-12" y="72" width="24" height="22" rx="4" fill="#f0c8a0"/>
      <!-- 腕 -->
      {arms}
      <!-- 頭 -->
      <ellipse cx="0" cy="44" rx="45" ry="51" fill="#f0c8a0"/>
      <!-- 茶色ショートボブ -->
      <path d="M-45,16 Q-43,-26 0,-35 Q43,-26 45,16 Q35,0 16,-3 Q0,-9 -16,-3 Q-35,0 -45,16Z" fill="#8B5E3C"/>
      <path d="M-45,13 Q-54,34 -47,56 Q-43,66 -39,70" stroke="#8B5E3C" stroke-width="11" fill="none" stroke-linecap="round"/>
      <path d="M45,13 Q54,34 47,58 Q43,68 39,72" stroke="#8B5E3C" stroke-width="11" fill="none" stroke-linecap="round"/>
      <!-- 顔パーツ -->
      {f["brows"]}
      {f["eyes"]}
      {f["mouth"]}
      {f["blush"]}
      <!-- 名前 -->
      <text x="0" y="300" text-anchor="middle" fill="#666" font-size="14" font-family="sans-serif">Tomomi</text>
    </g>'''


def _background_svg(location: str) -> str:
    colors = BACKGROUNDS.get(location, BACKGROUNDS["default"])
    bg, board_dark, board_light, label = colors
    return f'''
      <rect width="800" height="420" fill="{bg}"/>
      <rect x="130" y="35" width="540" height="190" rx="6" fill="{board_dark}"/>
      <rect x="144" y="47" width="512" height="166" rx="4" fill="{board_light}"/>
      <text x="400" y="142" fill="rgba(255,255,255,0.2)" font-size="20" text-anchor="middle"
            font-family="serif">{label}</text>
      <rect x="130" y="35" width="540" height="190" rx="6" fill="none" stroke="#1a3a22" stroke-width="3"/>
      <rect x="0" y="360" width="800" height="60" fill="#c0b090"/>
      <line x1="0" y1="360" x2="800" y2="360" stroke="#a09070" stroke-width="2"/>'''


def _balloons_svg(balloons: list) -> str:
    DEFS = '''<defs>
      <filter id="bshadow" x="-15%" y="-15%" width="140%" height="155%">
        <feDropShadow dx="1" dy="2" stdDeviation="2.5" flood-color="#00000028"/>
      </filter>
    </defs>'''

    parts = [DEFS]

    for b in balloons:
        text = b.get("text", "")
        pos  = b.get("position", "left")

        # 1行9文字で折り返し
        lines, line = [], ""
        for ch in text:
            line += ch
            if len(line) >= 9:
                lines.append(line); line = ""
        if line:
            lines.append(line)
        if not lines:
            continue

        line_h = 24
        w  = max(max(len(l) for l in lines) * 15 + 36, 90)
        h  = len(lines) * line_h + 22
        r  = 14   # 角丸半径
        th = 20   # 尻尾の高さ
        tw = 13   # 尻尾の半幅

        if pos == "left":
            cx, cy  = 148, 48
            fill    = "#eaf2ff"   # Yasu: 薄青
            stroke  = "#88aacc"
            tail_cx = cx + 30     # 尻尾の中心X（左寄り→Yasuの方向）
        else:
            cx  = 652 - w
            cy  = 48
            fill   = "#edfaed"    # Tomomi: 薄緑
            stroke = "#88bb88"
            tail_cx = cx + w - 30

        # ── 吹き出し本体（シャドウ付きグループ）──
        parts.append(f'<g filter="url(#bshadow)">')
        parts.append(
            f'<rect x="{cx}" y="{cy}" width="{w}" height="{h}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        # 尻尾: fill のみの三角（境界線を上書き）
        parts.append(
            f'<polygon points="{tail_cx-tw},{cy+h} {tail_cx},{cy+h+th} {tail_cx+tw},{cy+h}" '
            f'fill="{fill}"/>'
        )
        # 尻尾の左右の輪郭線だけ引く
        parts.append(
            f'<line x1="{tail_cx-tw}" y1="{cy+h}" x2="{tail_cx}" y2="{cy+h+th}" '
            f'stroke="{stroke}" stroke-width="1.5" stroke-linecap="round"/>'
        )
        parts.append(
            f'<line x1="{tail_cx+tw}" y1="{cy+h}" x2="{tail_cx}" y2="{cy+h+th}" '
            f'stroke="{stroke}" stroke-width="1.5" stroke-linecap="round"/>'
        )
        # 尻尾の付け根の rect ボーダーを fill 色の線で消す
        parts.append(
            f'<line x1="{tail_cx-tw+1}" y1="{cy+h}" x2="{tail_cx+tw-1}" y2="{cy+h}" '
            f'stroke="{fill}" stroke-width="3"/>'
        )
        parts.append('</g>')

        # テキスト（シャドウ外でシャープに）
        for i, l in enumerate(lines):
            ty = cy + 19 + i * line_h
            parts.append(
                f'<text x="{cx + w//2}" y="{ty}" text-anchor="middle" '
                f'font-size="14" fill="#1a1a1a" font-family="sans-serif" font-weight="500">{l}</text>'
            )

    return "\n".join(parts)


# ── プロップ（小道具）定義 ────────────────────────────────
def _prop_svg(name: str) -> str:
    """小道具SVG。キャラクター間の床面（中央 x=400, y≈330）に配置"""
    if not name or name == "なし":
        return ""

    cx, cy = 400, 330  # 配置中心

    if name == "時計":
        return f'''<g transform="translate({cx},{cy})">
          <!-- 小テーブル -->
          <rect x="-36" y="10" width="72" height="8" rx="3" fill="#a08060"/>
          <rect x="-28" y="18" width="8" height="20" rx="2" fill="#a08060"/>
          <rect x="20" y="18" width="8" height="20" rx="2" fill="#a08060"/>
          <!-- 時計本体 -->
          <circle cx="0" cy="0" r="26" fill="white" stroke="#555" stroke-width="3"/>
          <circle cx="0" cy="0" r="24" fill="#f8f8f0"/>
          <!-- 文字盤の点 -->
          <circle cx="0" cy="-19" r="2" fill="#333"/>
          <circle cx="0" cy="19" r="2" fill="#333"/>
          <circle cx="19" cy="0" r="2" fill="#333"/>
          <circle cx="-19" cy="0" r="2" fill="#333"/>
          <!-- 針 -->
          <line x1="0" y1="0" x2="0" y2="-15" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>
          <line x1="0" y1="0" x2="11" y2="6" stroke="#222" stroke-width="2" stroke-linecap="round"/>
          <!-- 中心 -->
          <circle cx="0" cy="0" r="3" fill="#444"/>
          <!-- ラベル -->
          <text x="0" y="44" text-anchor="middle" font-size="11" fill="#888" font-family="sans-serif">時計</text>
        </g>'''

    elif name == "デジタルカメラ":
        return f'''<g transform="translate({cx},{cy})">
          <!-- 小テーブル -->
          <rect x="-42" y="12" width="84" height="8" rx="3" fill="#a08060"/>
          <rect x="-32" y="20" width="8" height="20" rx="2" fill="#a08060"/>
          <rect x="24" y="20" width="8" height="20" rx="2" fill="#a08060"/>
          <!-- カメラ本体 -->
          <rect x="-32" y="-18" width="64" height="30" rx="5" fill="#2a2a2a"/>
          <rect x="-28" y="-14" width="56" height="22" rx="3" fill="#3a3a3a"/>
          <!-- レンズ -->
          <circle cx="0" cy="-3" r="10" fill="#1a1a1a" stroke="#555" stroke-width="1.5"/>
          <circle cx="0" cy="-3" r="7" fill="#222"/>
          <circle cx="0" cy="-3" r="4" fill="#0a0a3a"/>
          <circle cx="-2" cy="-5" r="1.5" fill="rgba(255,255,255,0.4)"/>
          <!-- シャッターボタン -->
          <circle cx="22" cy="-14" r="4" fill="#cc4444"/>
          <!-- フラッシュ -->
          <rect x="-28" y="-16" width="12" height="6" rx="2" fill="#ffeeaa"/>
          <!-- ラベル -->
          <text x="0" y="46" text-anchor="middle" font-size="11" fill="#888" font-family="sans-serif">デジタルカメラ</text>
        </g>'''

    elif name == "ビデオカメラ":
        return f'''<g transform="translate({cx},{cy})">
          <!-- 小テーブル -->
          <rect x="-46" y="14" width="92" height="8" rx="3" fill="#a08060"/>
          <rect x="-36" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <rect x="28" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <!-- 本体 -->
          <rect x="-36" y="-20" width="60" height="34" rx="6" fill="#2a2a2a"/>
          <!-- レンズ部 -->
          <rect x="24" y="-14" width="22" height="22" rx="4" fill="#1a1a1a"/>
          <circle cx="35" cy="-3" r="8" fill="#111" stroke="#444" stroke-width="1.5"/>
          <circle cx="35" cy="-3" r="5" fill="#0a0a2a"/>
          <circle cx="33" cy="-5" r="1.5" fill="rgba(255,255,255,0.4)"/>
          <!-- グリップ -->
          <rect x="-36" y="-8" width="16" height="22" rx="4" fill="#333"/>
          <!-- 録画ランプ -->
          <circle cx="10" cy="-16" r="3" fill="#ff3333"/>
          <!-- ラベル -->
          <text x="0" y="48" text-anchor="middle" font-size="11" fill="#888" font-family="sans-serif">ビデオカメラ</text>
        </g>'''

    elif name == "宝石":
        return f'''<g transform="translate({cx},{cy})">
          <!-- 小テーブル -->
          <rect x="-30" y="14" width="60" height="8" rx="3" fill="#a08060"/>
          <rect x="-22" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <rect x="14" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <!-- 台座 -->
          <rect x="-10" y="8" width="20" height="8" rx="2" fill="#aaaaaa"/>
          <!-- ダイヤ形状 -->
          <polygon points="0,-22 18,0 0,14 -18,0" fill="#7ad4f0" stroke="#4aaad0" stroke-width="1.5" opacity="0.9"/>
          <polygon points="0,-22 18,0 0,4" fill="#a8e8ff" opacity="0.7"/>
          <polygon points="0,-22 -18,0 0,4" fill="#5bbfe0" opacity="0.8"/>
          <polygon points="18,0 0,14 0,4" fill="#3a9fc0" opacity="0.8"/>
          <polygon points="-18,0 0,14 0,4" fill="#5bbfe0" opacity="0.7"/>
          <!-- 輝き -->
          <line x1="0" y1="-30" x2="0" y2="-26" stroke="#fff" stroke-width="2" opacity="0.8"/>
          <line x1="26" y1="-4" x2="22" y2="-2" stroke="#fff" stroke-width="2" opacity="0.8"/>
          <line x1="-26" y1="-4" x2="-22" y2="-2" stroke="#fff" stroke-width="2" opacity="0.8"/>
          <!-- ラベル -->
          <text x="0" y="50" text-anchor="middle" font-size="11" fill="#888" font-family="sans-serif">宝石</text>
        </g>'''

    else:  # 動産（汎用の箱）
        return f'''<g transform="translate({cx},{cy})">
          <!-- 小テーブル -->
          <rect x="-34" y="14" width="68" height="8" rx="3" fill="#a08060"/>
          <rect x="-26" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <rect x="18" y="22" width="8" height="18" rx="2" fill="#a08060"/>
          <!-- 箱 -->
          <rect x="-26" y="-20" width="52" height="34" rx="4" fill="#d4a050" stroke="#a07030" stroke-width="2"/>
          <!-- 箱の線（蓋） -->
          <line x1="-26" y1="-6" x2="26" y2="-6" stroke="#a07030" stroke-width="1.5"/>
          <!-- リボン -->
          <line x1="0" y1="-20" x2="0" y2="14" stroke="#cc4444" stroke-width="2"/>
          <line x1="-26" y1="-6" x2="26" y2="-6" stroke="#cc4444" stroke-width="2"/>
          <!-- ラベル -->
          <text x="0" y="50" text-anchor="middle" font-size="11" fill="#888" font-family="sans-serif">動産</text>
        </g>'''


def render_panel(scene: dict, prop_name: str = "") -> str:
    """シーンデータからSVG文字列を返す"""
    location   = scene.get("location", "教室")
    characters = scene.get("characters", [])
    balloons   = scene.get("balloons", [])

    yasu   = next((c for c in characters if c.get("name") == "Yasu"),   {"emotion": "default", "pose": "default"})
    tomomi = next((c for c in characters if c.get("name") == "Tomomi"), {"emotion": "default", "pose": "default"})

    bg       = _background_svg(location)
    yasu_g   = _yasu_svg(yasu.get("emotion",""), yasu.get("pose",""), 185, 108)
    tomomi_g = _tomomi_svg(tomomi.get("emotion",""), tomomi.get("pose",""), 618, 108)
    blns     = _balloons_svg(balloons)
    prop     = _prop_svg(prop_name)

    return f'''<svg viewBox="0 0 800 420" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%">
  {bg}
  {prop}
  {yasu_g}
  {tomomi_g}
  {blns}
  <rect x="2" y="2" width="796" height="416" rx="4" fill="none" stroke="#222" stroke-width="3"/>
</svg>'''
