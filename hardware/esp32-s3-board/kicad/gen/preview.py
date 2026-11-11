"""Draw the placement of the main parts, front and back, as labelled pictures.

    /usr/bin/python3.12 preview.py [output_dir]

The back is drawn as seen from the back (left and right swapped).
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from board import H, HOLE_NPTH, HOLES, OUTLINE, OUTLINE_START, W, arc_mid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
S = 26                    # pixels per millimetre
MARGIN = 3.0
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
LABELS = {
    "ESP32-S3-WROOM-1U-N16R8": "ESP32-S3 模组\n18 × 19.2，高 3.2",
    "Air780E（北美版换贴 Air780EEN）": "Air780E\n15.8 × 17.7，高 2.3",
    "Type-C 16P": "Type-C",
    "Nano SIM 卡座": "Nano SIM 卡座",
    "屏排线座 22P 0.5mm": "屏 22P",
    "触摸排线座 6P（脚位待定）": "触摸\n6P",
    "后摄 OV2640": "后摄 24P",
    "前摄 30 万（型号待定）": "前摄 24P",
    "IPEX 座": "4G\n天线座",
    "电池焊盘": "电\n池",
    "喇叭焊盘": "喇\n叭",
    "SY6970QCC": "充电\nSY6970",
    "1µH 4A": "电感",
    "按键排线 A": "按键\nA 6P",
    "按键排线 B": "按键 B 6P",
    "TF 卡座（带检测）": "TF 卡座",
    "MSM261S4030H0R": "麦克风",
    "下载 / 调试焊盘": "下载焊盘",
}


def outline_points():
    pts = [OUTLINE_START]
    x, y = OUTLINE_START
    for seg in OUTLINE:
        if seg[0] == "L":
            x, y = seg[1], seg[2]
            pts.append((x, y))
        else:
            _, cx, cy, ex, ey = seg
            a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ey - cy, ex - cx)
            d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            r = math.hypot(x - cx, y - cy)
            for i in range(1, 13):
                a = a0 + d * i / 12
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            x, y = ex, ey
    return pts


def draw(side, items, title, path):
    mirror = side == "B"
    img = Image.new("RGB", (int((W + 2 * MARGIN) * S), int((H + 2 * MARGIN + 4) * S)), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 26)
    small = ImageFont.truetype(FONT, 20)

    def px(x, y):
        return ((MARGIN + (W - x if mirror else x)) * S, (MARGIN + 2.5 + y) * S)

    d.text((MARGIN * S, 0.6 * S), title, fill="black", font=ImageFont.truetype(FONT, 34))
    d.polygon([px(*p) for p in outline_points()], fill=(244, 248, 240), outline="black", width=3)
    for hx, hy in HOLES + [HOLE_NPTH]:
        cx, cy = px(hx, hy)
        d.ellipse([cx - 1.4 * S, cy - 1.4 * S, cx + 1.4 * S, cy + 1.4 * S], outline=(120, 120, 120), width=2)
        d.ellipse([cx - 0.8 * S, cy - 0.8 * S, cx + 0.8 * S, cy + 0.8 * S], fill="white", outline="black", width=2)
    for it in items:
        if it["value"].startswith("Ø1.6"):
            continue
        x1, y1 = px(it["x1"], it["y1"])
        x2, y2 = px(it["x2"], it["y2"])
        x1, x2 = min(x1, x2), max(x1, x2)
        this = it["side"] == side
        if this:
            d.rectangle([x1, y1, x2, y2], fill=(214, 226, 255), outline=(30, 60, 200), width=3)
            label = LABELS.get(it["value"], it["value"])
            f = font if (x2 - x1) > 5 * S else small
            box = d.multiline_textbbox((0, 0), label, font=f, align="center")
            d.multiline_text(((x1 + x2) / 2 - (box[2] - box[0]) / 2, (y1 + y2) / 2 - (box[3] - box[1]) / 2 - 4),
                             label, fill=(10, 30, 120), font=f, align="center")
        else:
            for k in range(int(x1), int(x2), 12):          # other side: dashed outline only
                d.line([k, y1, min(k + 6, x2), y1], fill=(170, 170, 170), width=2)
                d.line([k, y2, min(k + 6, x2), y2], fill=(170, 170, 170), width=2)
            for k in range(int(y1), int(y2), 12):
                d.line([x1, k, x1, min(k + 6, y2)], fill=(170, 170, 170), width=2)
                d.line([x2, k, x2, min(k + 6, y2)], fill=(170, 170, 170), width=2)
    d.text((MARGIN * S, (MARGIN + 2.5 + H + 0.8) * S),
           "蓝色 = 这一面的器件（外框含安装间隙）   灰色虚线 = 另一面的器件   板子 64 × 34 mm",
           fill=(60, 60, 60), font=small)
    img.save(path)


if __name__ == "__main__":
    with open(os.path.join(OUT, "build", "placement.json"), encoding="utf-8") as f:
        items = json.load(f)
    draw("F", items, "正面（低的一面）：前摄、按键、TF 卡、麦克风；其余小元件之后也放这一面",
         os.path.join(OUT, "placement-front.png"))
    draw("B", items, "背面（高的一面，从背面看）：两个模组、Type-C、SIM 卡、屏和后摄排线、电池",
         os.path.join(OUT, "placement-back.png"))
    print("wrote placement-front.png, placement-back.png")
