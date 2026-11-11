"""Build the PCB from build/parts.json: outline, screw holes, nets and footprints.

Main parts are placed from the PLACE table; everything else is parked below the board.
Run with the Python that has pcbnew:   /usr/bin/python3.12 board.py [output_dir]

Coordinates are in millimetres from the top-left corner of the board seen from the front,
X to the right, Y down - the same frame as the reference-board measurements.
"""
import json
import math
import os
import sys

import pcbnew

from sexpr import find, first, parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
NAME = "zeebuddy-mainboard"
PLUG = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP)
MM = pcbnew.FromMM
OX, OY = 100.0, 60.0          # where the board's top-left corner sits on the KiCad page
SYSLIB = "/usr/share/kicad/footprints"
W, H = 64.0, 34.0


def V(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


# ---- outline of the reference board (64 x 34 mm, 0.8 mm thick) --------------------------------
# ("L", x, y) = line to; ("A", cx, cy, x, y) = arc around (cx, cy) to (x, y), short way round.
OUTLINE_START = (1.5, 0.0)
OUTLINE = [
    ("L", 64.0, 0.0), ("L", 64.0, 29.5),
    ("A", 62.5, 29.5, 62.86, 30.96), ("A", 63.1, 31.93, 62.1, 31.93), ("L", 62.1, 32.0),
    ("A", 60.1, 32.0, 60.1, 34.0), ("L", 3.9, 34.0),
    ("A", 3.9, 32.0, 1.9, 32.0), ("L", 1.9, 31.93),
    ("A", 0.9, 31.93, 1.14, 30.96), ("A", 1.5, 29.5, 0.0, 29.5), ("L", 0.0, 3.0),
    ("A", 0.0, 1.5, 1.5, 1.5), ("L", 1.5, 0.0),
]
HOLE_NPTH = (62.2, 1.2)                                   # too close to the edge for a copper ring
HOLES = [(2.0, 14.5), (3.7, 32.0), (60.3, 32.0)]            # grounded ring

# ---- basic rules for a 4-layer board at JLC; refined when routing starts -------------------------
RULES = {"min_clearance": 0.09, "min_track_width": 0.09, "min_copper_edge_clearance": 0.3,
         "min_through_hole_diameter": 0.2, "min_via_diameter": 0.4, "min_via_annular_width": 0.075,
         "min_hole_clearance": 0.2}
DEFAULT_CLASS = {"clearance": 0.1, "track_width": 0.15, "via_diameter": 0.45, "via_drill": 0.2,
                 "diff_pair_width": 0.15, "diff_pair_gap": 0.15}

# ---- placement of the main parts: key -> (x, y, rotation, side) --------------------------------
# key is matched against the part's value first, then against its footprint name.
# rotation 0 = upright as seen from the front, on either side.
PLACE = {
    # back side: the two modules, Type-C, SIM and the display / rear camera connectors
    "ESP32-S3-WROOM-1U-N16R8": (54.0, 16.2, 0, "B"),
    "zeebuddy:Air780E": (33.0, 12.6, 180, "B"),
    "Type-C 16P": (32.0, 29.8, 0, "B"),
    "Nano SIM 卡座": (12.76, 26.3, 0, "B"),
    "屏排线座 22P 0.5mm": (16.2, 2.75, 180, "B"),
    "触摸排线座 6P（脚位待定）": (5.0, 2.75, 180, "B"),
    "后摄 OV2640": (50.5, 2.75, 180, "B"),
    "IPEX 座": (41.0, 25.7, 0, "B"),
    "电池焊盘": (2.11, 8.7, 0, "B"),
    "喇叭焊盘": (1.27, 19.22, 0, "B"),
    "zeebuddy:SY6970_QFN-24_4x4mm": (11.0, 11.6, 0, "B"),
    "1µH 4A": (17.6, 11.6, 90, "B"),
    # front side: front camera, keys, TF card, microphone, download pads
    "前摄 30 万（型号待定）": (20.0, 2.75, 180, "F"),
    "按键排线 B": (49.4, 2.75, 180, "F"),
    "按键排线 A": (60.4, 25.0, 90, "F"),
    "TF 卡座（带检测）": (12.6, 26.9, 180, "F"),
    "zeebuddy:MSM261S4030H0R": (51.0, 31.3, 90, "F"),
    "下载 / 调试焊盘": (42.5, 32.4, 0, "F"),
}


def arc_mid(cx, cy, x0, y0, x1, y1):
    a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
    d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    r = math.hypot(x0 - cx, y0 - cy)
    return cx + r * math.cos(a0 + d / 2), cy + r * math.sin(a0 + d / 2)


def draw_outline(board):
    x, y = OUTLINE_START
    for seg in OUTLINE:
        s = pcbnew.PCB_SHAPE(board)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        if seg[0] == "L":
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x, y))
            s.SetEnd(V(seg[1], seg[2]))
            x, y = seg[1], seg[2]
        else:
            _, cx, cy, ex, ey = seg
            mx, my = arc_mid(cx, cy, x, y, ex, ey)
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetArcGeometry(V(x, y), V(mx, my), V(ex, ey))
            x, y = ex, ey
        board.Add(s)


def load_footprint(fpid):
    lib, name = fpid.split(":", 1)
    path = os.path.join(OUT, lib + ".pretty") if lib == "zeebuddy" else os.path.join(SYSLIB, lib + ".pretty")
    fp = PLUG.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def bbox_mm(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd)
    bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
            pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)


def main():
    with open(os.path.join(OUT, "build", "parts.json"), encoding="utf-8") as f:
        parts = json.load(f)

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(0.8))
    ds.SetAuxOrigin(V(0, 0))
    draw_outline(board)

    # pad nets come from the netlist KiCad exported, so they carry KiCad's own names,
    # including the "unconnected-(...)" nets it gives to pins that are deliberately left open
    with open(os.path.join(OUT, "build", NAME + ".net"), encoding="utf-8") as f:
        netlist = parse(f.read())
    pad_net, nets = {}, {}
    for n in find(first(netlist, "nets"), "net"):
        name = first(n, "name")[1]
        nets[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(nets[name])
        for node in find(n, "node"):
            pad_net[(first(node, "ref")[1], first(node, "pin")[1])] = name

    problems, placed, summary = [], {}, []
    holes = list(HOLES)
    park = {}
    for ref in sorted(parts, key=lambda r: (parts[r]["sheetfile"], "".join(c for c in r if c.isalpha()),
                                             int("".join(c for c in r if c.isdigit()) or 0))):
        info = parts[ref]
        fp = load_footprint(info["footprint"])
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetPath(pcbnew.KIID_PATH(f"/{info['sheet']}/{info['uuid']}"))
        fp.SetSheetfile(info["sheetfile"])
        fp.SetSheetname("/" + info["sheetname"] + "/")
        if info["dnp"]:
            fp.SetDNP(True)
        board.Add(fp)

        pad_names = {p.GetNumber() for p in fp.Pads()}
        for pin, net in info["pins"].items():
            if pin not in pad_names:
                problems.append(f"{ref} ({info['footprint']}): no pad '{pin}' for net {net}")
        for pad in fp.Pads():
            net = pad_net.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        extra = sorted(n for n in pad_names - set(info["pins"]) if n)
        if extra:
            problems.append(f"{ref} ({info['footprint']}): pads without a schematic pin: {' '.join(extra)}")

        spot = PLACE.get(info["value"]) or PLACE.get(info["footprint"])
        if info["footprint"] == "zeebuddy:MountingHole_1.6mm_Pad":
            spot = holes.pop(0) + (0, "F")
        elif info["footprint"] == "zeebuddy:MountingHole_1.6mm_NPTH":
            spot = HOLE_NPTH + (0, "F")
        if spot:
            x, y, rot, side = spot
            fp.SetPosition(V(x, y))
            if side == "B":
                fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            # on the back, KiCad's own angle is 180 for a part that is upright when seen from the front
            fp.SetOrientationDegrees(rot + 180 if side == "B" else rot)
            placed[ref] = fp
            summary.append((ref, info["value"], side) + bbox_mm(fp))
        else:
            park.setdefault(info["sheetname"], []).append(fp)

    # park the rest below the board, one block per schematic sheet
    y0 = H + 12.0
    for sheet, fps in park.items():
        label = pcbnew.PCB_TEXT(board)
        label.SetText(f"未摆放：{sheet}")
        label.SetLayer(pcbnew.Cmts_User)
        label.SetPosition(V(-2, y0 - 2.2))
        label.SetTextSize(pcbnew.VECTOR2I(MM(1.2), MM(1.2)))
        label.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        board.Add(label)
        x, row_h = 0.0, 0.0
        for fp in fps:
            fp.SetPosition(V(0, 0))
            l, t, r, b = bbox_mm(fp)
            w, h = r - l + 0.8, b - t + 0.8
            if x + w > 110:
                x, y0, row_h = 0.0, y0 + row_h, 0.0
            fp.SetPosition(V(x - l + 0.4, y0 - t + 0.4))
            x += w
            row_h = max(row_h, h)
        y0 += row_h + 6.0

    path = os.path.join(OUT, NAME + ".kicad_pcb")
    pcbnew.SaveBoard(path, board)
    pro = os.path.join(OUT, NAME + ".kicad_pro")
    with open(pro, encoding="utf-8") as f:
        project = json.load(f)
    project["board"]["design_settings"]["rules"].update(RULES)
    project["net_settings"]["classes"][0].update(DEFAULT_CLASS)
    with open(pro, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(OUT, "build", "placement.json"), "w", encoding="utf-8") as f:
        json.dump([dict(ref=r, value=v, side=s, x1=round(a, 2), y1=round(b, 2), x2=round(c, 2), y2=round(d, 2))
                   for r, v, s, a, b, c, d in summary], f, ensure_ascii=False, indent=0)
    named = sum(1 for n in nets if not n.startswith("unconnected-"))
    print(f"board: {len(parts)} footprints, {len(placed)} placed, {named} nets -> {os.path.basename(path)}")
    for p in problems:
        print("  CHECK", p)
    for ref, key in (("U9", "35"), ("U9", "1"), ("U4", "1")):
        if ref in placed:
            for pad in placed[ref].Pads():
                if pad.GetNumber() == key:
                    pos = pad.GetPosition()
                    print(f"  {ref} pad {key} at ({pcbnew.ToMM(pos.x) - OX:.2f}, {pcbnew.ToMM(pos.y) - OY:.2f})")
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main())
