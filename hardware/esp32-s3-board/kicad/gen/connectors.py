"""Where the cable connectors are: one picture for the mechanical engineer and the cable suppliers.

    /usr/bin/python3.12 connectors.py [output_dir]

Two views of the board, from the front and from the back (the back view is mirrored left to right, as one sees it
with the board turned over). Each FPC connector and wire pad is drawn with its outline, pin 1, the last pin and the
side the cable comes in from. Writes connector-positions.png and prints the table that goes into the documents.
"""
import os
import sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

from board import NAME, OX, OY
from route import outline_points

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
S = 22                      # pixels per mm
M = 5.0                     # margin, mm
W, H = 64.0, 34.0
NAMES = {"J8": "屏 22P", "J9": "触摸 6P", "J10": "后摄 24P", "J11": "前摄 24P", "J4": "按键 A 6P", "J5": "按键 B 6P",
         "J1": "Type-C", "J6": "SIM 卡", "J13": "TF 卡", "J7": "天线座", "J2": "电池焊盘", "J12": "喇叭焊盘", "J3": "下载焊盘"}
FPC = {"J4", "J5", "J8", "J9", "J10", "J11"}


def main():
    board = pcbnew.LoadBoard(os.path.join(OUT, NAME + ".kicad_pcb"))
    mm = pcbnew.ToMM
    parts = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith("J"):
            continue
        pads = [p for p in fp.Pads() if p.GetNumber().isdigit()]
        if not pads:
            pads = list(fp.Pads())
        bb = fp.GetBoundingBox(False, False)
        box = (mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)
        first = min(pads, key=lambda p: int(p.GetNumber()) if p.GetNumber().isdigit() else 0)
        last = max(pads, key=lambda p: int(p.GetNumber()) if p.GetNumber().isdigit() else 0)
        xy = lambda p: (mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        px = sum(xy(p)[0] for p in pads) / len(pads)
        py = sum(xy(p)[1] for p in pads) / len(pads)
        # the cable comes in on the side away from the pad row; vec is the direction it moves when pushed in
        if abs(px - cx) > abs(py - cy):
            entry = "左边缘" if px > cx else "右边缘"
            vec = (1, 0) if px > cx else (-1, 0)
        else:
            entry = "上边缘" if py > cy else "下边缘"
            vec = (0, 1) if py > cy else (0, -1)
        parts.append(dict(ref=ref, side="B" if fp.GetLayer() == pcbnew.B_Cu else "F", box=box, first=(first.GetNumber(), xy(first)),
                          last=(last.GetNumber(), xy(last)), entry=entry, vec=vec, n=len(pads)))
    parts.sort(key=lambda p: (p["side"], p["box"][0]))

    font = ImageFont.truetype(FONT, 20)
    small = ImageFont.truetype(FONT, 15)
    big = ImageFont.truetype(FONT, 28)
    vw, vh = int((W + 2 * M) * S), int((H + 2 * M) * S)
    img = Image.new("RGB", (vw, 2 * vh + 110), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 12), "Zeebuddy 主板连接器位置（64 × 34 mm）：红点 = 第 1 脚，箭头 = 排线插入方向", fill="black", font=big)
    for k, (side, title) in enumerate((("F", "从正面看（正面的座子）"), ("B", "从背面看（背面的座子；左右和正面相反）"))):
        oy = 60 + k * (vh + 25)
        flip = side == "B"
        X = lambda x: ((W - x if flip else x) + M) * S
        Y = lambda y: oy + (y + M) * S
        d.text((20, oy + 2), title, fill=(0, 0, 120), font=font)
        pts = [(X(x), Y(y)) for x, y in outline_points()]
        d.polygon(pts, outline="black", fill=(246, 246, 240))
        d.line(pts + pts[:1], fill="black", width=3)
        for g in range(0, 65, 10):
            d.text((X(g) - 8, Y(H) + 6), str(g), fill=(120, 120, 120), font=small)
        for p in parts:
            if p["side"] != side:
                continue
            x0, y0, x1, y1 = p["box"]
            r = [min(X(x0), X(x1)), Y(y0), max(X(x0), X(x1)), Y(y1)]
            fpc = p["ref"] in FPC
            d.rectangle(r, outline=(0, 60, 200) if fpc else (120, 120, 120), width=3 if fpc else 2,
                        fill=(214, 226, 255) if fpc else (232, 232, 232))
            label = f'{p["ref"]} {NAMES.get(p["ref"], "")}'
            d.text((r[0] + 4, r[1] + 3 if r[3] - r[1] > 60 else r[3] + 3), label, fill="black", font=small)
            if fpc:
                fx, fy = p["first"][1]
                lx, ly = p["last"][1]
                d.ellipse([X(fx) - 7, Y(fy) - 7, X(fx) + 7, Y(fy) + 7], fill=(220, 30, 30))
                d.text((X(fx) - 5, Y(fy) + 9), "1", fill=(200, 0, 0), font=small)
                d.text((X(lx) - 9, Y(ly) + 9), p["last"][0], fill=(90, 90, 90), font=small)
                vx, vy = p["vec"]
                if flip:
                    vx = -vx
                cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
                # arrow from outside the board edge to the connector's mouth
                hx, hy = (r[2] - r[0]) / 2, (r[3] - r[1]) / 2
                tx, ty = cx - vx * hx, cy - vy * hy
                ex, ey = tx - vx * 60, ty - vy * 60
                d.line([ex, ey, tx - vx * 10, ty - vy * 10], fill=(0, 140, 0), width=6)
                d.polygon([(tx, ty), (tx - 16 * vx - 10 * vy, ty - 16 * vy - 10 * vx),
                           (tx - 16 * vx + 10 * vy, ty - 16 * vy + 10 * vx)], fill=(0, 140, 0))
    path = os.path.join(OUT, "connector-positions.png")
    img.save(path)
    print("wrote", os.path.relpath(path, OUT))
    print("| 座子 | 用途 | 在哪一面 | 脚数 | 第 1 脚（距左边，距上边）mm | 末脚 mm | 排线从哪一侧进 |")
    print("|---|---|---|---|---|---|---|")
    for p in parts:
        if p["ref"] in FPC:
            f, l = p["first"][1], p["last"][1]
            print(f'| {p["ref"]} | {NAMES[p["ref"]]} | {"正面" if p["side"] == "F" else "背面"} | {p["n"]} | '
                  f'({f[0]:.2f}, {f[1]:.2f}) | {p["last"][0]} 脚 ({l[0]:.2f}, {l[1]:.2f}) | {p["entry"]} |')
    return 0


if __name__ == "__main__":
    sys.exit(main())
