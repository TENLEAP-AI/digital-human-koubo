"""Generate the project footprint library (zeebuddy.pretty). Run with the Python that has pcbnew:

    /usr/bin/python3.12 footprints.py [output_dir]
"""
import json
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
LIB = os.path.join(OUT, "zeebuddy.pretty")
PLUG = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP)
MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


class FP:
    def __init__(self, name, descr, smd=True, ref_y=-3.0, val_y=3.0):
        self.name = name
        self.board = pcbnew.BOARD()
        self.fp = pcbnew.FOOTPRINT(self.board)
        self.fp.SetFPID(pcbnew.LIB_ID("", name))
        self.fp.SetLibDescription(descr)
        self.fp.SetAttributes(pcbnew.FP_SMD if smd else pcbnew.FP_THROUGH_HOLE)
        for field, text, layer, y in ((self.fp.Reference(), "REF**", pcbnew.F_SilkS, ref_y),
                                      (self.fp.Value(), name, pcbnew.F_Fab, val_y)):
            field.SetText(text)
            field.SetLayer(layer)
            field.SetPosition(V(0, y))
            field.SetTextSize(V(0.8, 0.8))
            field.SetTextThickness(MM(0.12))

    def pad(self, number, x, y, w, h, shape="rect", paste=True, mask=True):
        p = pcbnew.PAD(self.fp)
        p.SetNumber(str(number))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        if shape == "roundrect":
            p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
            p.SetRoundRectRadiusRatio(0.25)
        elif shape == "circle":
            p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        else:
            p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(V(w, h))
        p.SetPosition(V(x, y))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        if mask:
            layers.AddLayer(pcbnew.F_Mask)
        if paste:
            layers.AddLayer(pcbnew.F_Paste)
        p.SetLayerSet(layers)
        self.fp.Add(p)
        return p

    def paste(self, x, y, w, h):
        p = pcbnew.PAD(self.fp)
        p.SetNumber("")
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(V(w, h))
        p.SetPosition(V(x, y))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Paste)
        p.SetLayerSet(layers)
        self.fp.Add(p)

    def hole(self, number, x, y, drill, size):
        p = pcbnew.PAD(self.fp)
        p.SetNumber(str(number))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(V(size, size))
        p.SetDrillSize(V(drill, drill))
        p.SetPosition(V(x, y))
        p.SetLayerSet(p.PTHMask())
        self.fp.Add(p)

    def _shape(self, kind, layer, width):
        s = pcbnew.PCB_SHAPE(self.fp)
        s.SetShape(kind)
        s.SetLayer(layer)
        s.SetWidth(MM(width))
        self.fp.Add(s)
        return s

    def line(self, x1, y1, x2, y2, layer=pcbnew.F_Fab, width=0.1):
        s = self._shape(pcbnew.SHAPE_T_SEGMENT, layer, width)
        s.SetStart(V(x1, y1))
        s.SetEnd(V(x2, y2))

    def poly(self, pts, layer=pcbnew.F_Fab, width=0.1):
        for a, b in zip(pts, pts[1:] + pts[:1]):
            self.line(a[0], a[1], b[0], b[1], layer, width)

    def rect(self, x1, y1, x2, y2, layer=pcbnew.F_Fab, width=0.1):
        s = self._shape(pcbnew.SHAPE_T_RECT, layer, width)
        s.SetStart(V(x1, y1))
        s.SetEnd(V(x2, y2))

    def circle(self, x, y, r, layer=pcbnew.F_Fab, width=0.1, fill=False):
        s = self._shape(pcbnew.SHAPE_T_CIRCLE, layer, width)
        s.SetCenter(V(x, y))
        s.SetEnd(V(x + r, y))
        if fill:
            s.SetFilled(True)

    def text(self, text, x, y, layer=pcbnew.F_Fab, size=0.6):
        t = pcbnew.PCB_TEXT(self.fp)
        t.SetText(text)
        t.SetLayer(layer)
        t.SetPosition(V(x, y))
        t.SetTextSize(V(size, size))
        t.SetTextThickness(MM(size * 0.15))
        self.fp.Add(t)

    def courtyard(self, x1, y1, x2, y2):
        self.rect(x1, y1, x2, y2, pcbnew.F_CrtYd, 0.05)

    def save(self):
        os.makedirs(LIB, exist_ok=True)
        PLUG.FootprintSave(LIB, self.fp)


def air780e():
    """Pad positions and sizes come from the official PADS decal (Air780E_AT, V20241030)."""
    with open(os.path.join(HERE, "air780e_pads.json"), encoding="utf-8") as f:
        pads = json.load(f)
    fp = FP("Air780E", "合宙 Air780E / Air780EEN，LGA-109，15.8 x 17.7 x 2.3 mm。焊盘取自合宙官方 PADS 封装",
            ref_y=-10.6, val_y=10.6)
    for num, p in sorted(pads.items(), key=lambda kv: int(kv[0])):
        if p["shape"] == "S":
            w = h = p["size"]
        elif p["ori"] == 0:
            w, h = p["length"], p["size"]
        else:
            w, h = p["size"], p["length"]
        fp.pad(num, p["x"], -p["y"], w, h)
    bx, by, c = 7.9, 8.85, 0.7
    fp.poly([(-bx + c, -by), (bx, -by), (bx, by), (-bx, by), (-bx, -by + c)])
    for sx in (-1, 1):
        for sy in (-1, 1):
            if (sx, sy) == (-1, -1):
                continue
            fp.line(sx * (bx + 0.15), sy * (by + 0.15), sx * (bx + 0.15), sy * (by - 1.2), pcbnew.F_SilkS, 0.12)
            fp.line(sx * (bx + 0.15), sy * (by + 0.15), sx * (bx - 1.2), sy * (by + 0.15), pcbnew.F_SilkS, 0.12)
    fp.circle(-bx - 0.5, -6.6, 0.15, pcbnew.F_SilkS, 0.3)                 # pin 1
    fp.courtyard(-9.1, -10.0, 9.1, 10.0)                                   # second outline of the decal
    fp.rect(-bx - 3, -by - 3, bx + 3, by + 3, pcbnew.Cmts_User, 0.1)       # 3 mm to other parts (Luat)
    fp.text("3 mm 间距（合宙建议）", 0, -by - 3.6, pcbnew.Cmts_User, 0.6)
    fp.save()


def sy6970():
    """Land pattern from the SY6970 datasheet Rev 0.1, 'QFN4x4-24 package outline & PCB layout'."""
    fp = FP("SY6970_QFN-24_4x4mm", "矽力杰 SY6970QCC，QFN4x4-24，间距 0.5 mm，散热焊盘 2.7 x 2.7 mm",
            ref_y=-3.4, val_y=3.4)
    c, n = 1.925, 0
    for side in range(4):
        for i in range(6):
            n += 1
            o = -1.25 + 0.5 * i
            x, y, w, h = [(-c, o, 0.55, 0.28), (o, c, 0.28, 0.55), (c, -o, 0.55, 0.28), (-o, -c, 0.28, 0.55)][side]
            fp.pad(n, x, y, w, h, "roundrect")
    fp.pad(25, 0, 0, 2.7, 2.7, paste=False)
    for px in (-0.65, 0.65):
        for py in (-0.65, 0.65):
            fp.paste(px, py, 1.05, 1.05)
    fp.poly([(-1.5, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0), (-2.0, -1.5)])
    for sx in (-1, 1):
        for sy in (-1, 1):
            if (sx, sy) == (-1, -1):
                continue
            fp.line(sx * 2.1, sy * 2.1, sx * 2.1, sy * 1.65, pcbnew.F_SilkS, 0.12)
            fp.line(sx * 2.1, sy * 2.1, sx * 1.65, sy * 2.1, pcbnew.F_SilkS, 0.12)
    fp.circle(-2.6, -1.25, 0.1, pcbnew.F_SilkS, 0.2)
    fp.courtyard(-2.45, -2.45, 2.45, 2.45)
    fp.save()


def mic():
    """Land pattern from the MSM261S4030H0R datasheet V1.0 (PCB view: 5-6-7-8 left, 4-3-2-1 right)."""
    fp = FP("MSM261S4030H0R", "敏芯 I²S 硅麦，4.0 x 3.0 x 1.25 mm，顶部进音", ref_y=-2.9, val_y=2.9)
    for i, num in enumerate((5, 6, 7, 8)):
        fp.pad(num, -0.95, -1.5 + i, 0.9, 0.6)
    for i, num in enumerate((4, 3, 2, 1)):
        fp.pad(num, 0.95, -1.5 + i, 0.9, 0.6)
    fp.rect(-1.5, -2.0, 1.5, 2.0)
    fp.circle(0, -0.58, 0.325)                              # acoustic port on the lid
    fp.circle(0, -0.58, 0.325, pcbnew.Cmts_User, 0.1)
    fp.line(-1.5, -2.15, 1.5, -2.15, pcbnew.F_SilkS, 0.12)
    fp.line(-1.5, 2.15, 1.5, 2.15, pcbnew.F_SilkS, 0.12)
    fp.circle(1.9, 1.5, 0.1, pcbnew.F_SilkS, 0.2)           # pin 1
    fp.courtyard(-1.75, -2.25, 1.75, 2.25)
    fp.save()


def fpc(n):
    """Stand-in for a 0.5 mm flip-lock FPC connector; the real part is not chosen yet."""
    w = n * 0.5 + 3.5
    fp = FP(f"FPC_0.5mm_{n}P_Placeholder", f"0.5 mm 间距 {n} 脚翻盖排线座的占位封装，具体型号待定，画板前要换",
            ref_y=-3.6, val_y=3.2)
    for i in range(n):
        fp.pad(i + 1, (i - (n - 1) / 2) * 0.5, -1.9, 0.3, 1.2)
    for sx in (-1, 1):
        fp.pad("MP", sx * (w / 2 - 0.9), 0.9, 1.6, 1.8)
    fp.rect(-w / 2, -1.6, w / 2, 2.1)
    fp.text("占位", 0, 0.3, pcbnew.F_Fab, 0.7)
    fp.line(-w / 2, 2.25, w / 2, 2.25, pcbnew.F_SilkS, 0.12)
    fp.circle(-(n - 1) / 4 - 0.6, -2.8, 0.1, pcbnew.F_SilkS, 0.2)
    fp.text("排线从这一侧插入", 0, 2.9, pcbnew.Cmts_User, 0.5)
    fp.courtyard(-w / 2 - 0.25, -2.75, w / 2 + 0.25, 2.35)
    fp.save()


def mounting_hole():
    fp = FP("MountingHole_1.6mm_Pad", "Ø1.6 螺丝孔，铜环 Ø2.8，接地（位置和孔径取自参考主板）", smd=False,
            ref_y=-2.6, val_y=2.6)
    fp.hole(1, 0, 0, 1.6, 2.8)
    fp.circle(0, 0, 1.8, pcbnew.F_CrtYd, 0.05)
    fp.circle(0, 0, 1.8, pcbnew.Cmts_User, 0.1)
    fp.save()


def mounting_hole_npth():
    fp = FP("MountingHole_1.6mm_NPTH", "Ø1.6 螺丝孔，无铜环（离板边太近）", smd=False, ref_y=-2.6, val_y=2.6)
    p = pcbnew.PAD(fp.fp)
    p.SetNumber("")
    p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(V(1.6, 1.6))
    p.SetDrillSize(V(1.6, 1.6))
    p.SetPosition(V(0, 0))
    p.SetLayerSet(p.UnplatedHoleMask())
    fp.fp.Add(p)
    fp.circle(0, 0, 1.8, pcbnew.Cmts_User, 0.1)
    fp.save()


def wire_pads(name, descr, pads, size):
    fp = FP(name, descr, ref_y=min(p[2] for p in pads) - 1.6, val_y=max(p[2] for p in pads) + 1.6)
    for num, x, y, label in pads:
        fp.pad(num, x, y, size[0], size[1], paste=False)
        if label:
            fp.text(label, x + size[0] / 2 + 0.7, y, pcbnew.F_SilkS, 0.8)
    xs = [p[1] for p in pads]
    ys = [p[2] for p in pads]
    fp.courtyard(min(xs) - size[0] / 2 - 0.25, min(ys) - size[1] / 2 - 0.25,
                 max(xs) + size[0] / 2 + 0.25, max(ys) + size[1] / 2 + 0.25)
    fp.save()


def prog_pads():
    fp = FP("ProgPads_1x06", "6 个下载 / 调试焊盘，间距 1.5 mm：3V3、GND、EN、IO0、TXD0、RXD0", ref_y=-1.6, val_y=1.6)
    for i in range(6):
        fp.pad(i + 1, -3.75 + 1.5 * i, 0, 1.0, 1.0, "rect" if i == 0 else "circle", paste=False)
    fp.courtyard(-4.5, -0.75, 4.5, 0.75)
    fp.save()


if __name__ == "__main__":
    air780e()
    sy6970()
    mic()
    for pins in (6, 22, 24):
        fpc(pins)
    mounting_hole()
    mounting_hole_npth()
    wire_pads("BatteryPads", "电池焊线焊盘，位置和尺寸同参考主板：1 = 正，2 = 负，3 = 温度电阻（没接）",
              [(2, 0, -2.21, "-"), (3, 0, 0, ""), (1, 0, 2.2, "+")], (2.58, 1.2))
    wire_pads("SpeakerPads", "喇叭焊线焊盘，位置和尺寸同参考主板", [(1, 0, -1.7, ""), (2, 0, 1.7, "")], (1.7, 1.2))
    prog_pads()
    with open(os.path.join(OUT, "fp-lib-table"), "w", encoding="utf-8") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "zeebuddy")(type "KiCad")'
                '(uri "${KIPRJMOD}/zeebuddy.pretty")(options "")(descr "Project footprints"))\n)\n')
    print("footprints:", ", ".join(sorted(n[:-10] for n in os.listdir(LIB))))
