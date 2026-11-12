"""Measure the board against the rules of docs/layout-spec.md that the locked base is responsible for.

    /usr/bin/python3.12 check.py [output_dir]

Prints a table: rule, what it asks, what the board has, pass or not; the same table goes to build/check.md.
This is a first part of the checks that section 11 of the spec asks for: supply copper, switching
regulators, ground vias, antenna line, USB lengths. The signal rules are not covered yet.
"""
import json
import math
import os
import re
import subprocess
import sys

import pcbnew

import power
from board import NAME, OX, OY
from route import PLANES, PWR_HI, RF, RF_W, USB, pt_seg, rect_gap, seg_seg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
MOHM_PER_SQUARE = 0.5          # 1 oz outer copper
mm = pcbnew.ToMM


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    board = pcbnew.LoadBoard(path)
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            rect = (mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)
            pads.setdefault((fp.GetReference(), p.GetNumber()), []).append(
                dict(net=p.GetNetname(), rect=rect, pth=p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                     layers=[l for l in (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)]))
    vias, tracks = [], []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            vias.append((t.GetNetname(), mm(q.x) - OX, mm(q.y) - OY, mm(t.GetWidth(pcbnew.F_Cu)), mm(t.GetDrill())))
        else:
            a, e = t.GetStart(), t.GetEnd()
            tracks.append((t.GetNetname(), t.GetLayer(), mm(a.x) - OX, mm(a.y) - OY, mm(e.x) - OX, mm(e.y) - OY,
                           mm(t.GetWidth())))

    def rect(ref, num):
        return max(pads[(ref, num)], key=lambda p: (p["rect"][2] - p["rect"][0]) * (p["rect"][3] - p["rect"][1]))["rect"]

    def near(r, net, dist, drill=0.0):
        """Vias of a net whose copper comes within dist of a rectangle."""
        return [v for v in vias if v[0] == net and v[4] >= drill - 1e-6 and
                math.hypot(max(r[0] - v[1], v[1] - r[2], 0), max(r[1] - v[2], v[2] - r[3], 0)) - v[3] / 2 <= dist]

    def inside(r, net):
        return [v for v in vias if v[0] == net and r[0] <= v[1] <= r[2] and r[1] <= v[2] <= r[3]]

    rows = []

    def row(rule, asks, has, ok):
        rows.append((rule, asks, has, "通过" if ok is True else "不通过" if ok is False else ok))

    # ---- what KiCad itself finds ---------------------------------------------------------------------
    rep = os.path.join(OUT, "build", "drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all", "--schematic-parity", "--format", "json", "-o", rep, path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(rep, encoding="utf-8") as f:
        drc = json.load(f)
    kinds = {}
    for v in drc["violations"]:
        kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    other = {k: n for k, n in kinds.items() if k != "lib_footprint_mismatch"}
    row("DRC", "间距、短路、孔距、板边等 0 条", "0 条" if not other else str(other), not other)
    row("原理图一致性", "0 处差异", f"{len(drc.get('schematic_parity', []))} 处", not drc.get("schematic_parity"))
    base = RF | USB | PWR_HI | set(PLANES)
    open_base, open_all = 0, len(drc.get("unconnected_items", []))
    for u in drc.get("unconnected_items", []):
        m = re.search(r"\[([^\]]+)\]", u["items"][0]["description"])
        open_base += bool(m and m.group(1) in base)
    row("底子完整", "电源、地、3.3 V、天线、USB 全部连上", f"{open_base} 处没连", open_base == 0)
    row("其余连接", "留给自动布线", f"{open_all - open_base} 处没连", "—")

    # ---- supply copper (PWR-1, PWR-2): from the path that power.py describes ------------------------------
    total_len = total_r = 0.0
    for net, pieces in power.PATH.items():
        total_len += sum(length for _, length in pieces)
        total_r += sum(MOHM_PER_SQUARE * length / width for width, length in pieces)
        at_pins = [(w, n) for w, n in pieces if w < 1.0]
        necks = [(w, n) for w, n in pieces if 1.0 <= w < 2.0]
        ok = all(n <= 2.0 for _, n in necks)
        has = "全程 ≥2.0 mm" if not necks else "；".join(f"{w} mm 宽的一段长 {n} mm" for w, n in necks)
        if at_pins:
            has += "；引脚处 " + "、".join(f"{w} mm × {n} mm" for w, n in at_pins)
        row(f"PWR-1 {net}", "铜皮 ≥2.0 mm；收窄处 ≥1.0 mm、长 ≤2 mm；引脚处按引脚宽", has, ok)
    row("PWR-2", "电池焊盘到 Air780E 供电脚：铜皮 ≤30 mm、≤15 mΩ",
        f"约 {total_len:.0f} mm、约 {total_r:.1f} mΩ（按方块数估算，不含充电芯片和开关管）", total_len <= 30 and total_r <= 15)
    d = min(rect_gap(rect("C19", "1"), rect("U9", n)) for n in ("42", "43"))
    row("PWR-3", "220 µF 正极到模组供电脚 ≤1.8 mm，电容在电流的路上", f"{d:.2f} mm；开关管 → 电容焊盘 → 供电脚是同一块铜皮", d <= 1.8)
    n = len(near(rect("C19", "2"), "GND", 1.0, 0.3))
    row("PWR-5", "220 µF 地焊盘旁 ≥3 个 0.3 mm 地孔，≤1 mm", f"{n} 个", n >= 3)
    for label, net, r, want in (("VSYS 到正面", "VSYS", (4.9, 6.2, 6.9, 8.2), 4), ("VBUS 在 Type-C 左侧", "VBUS", (28.2, 23.9, 30.1, 24.9), 2),
                                ("VBUS 在 Type-C 右侧", "VBUS", (33.9, 23.9, 35.8, 24.9), 2), ("VBUS 回到背面", "VBUS", (16.9, 27.5, 18.8, 28.5), 2),
                                ("3.3 V 降压输出到第 4 层", "+3V3", (14.0, 8.3, 15.9, 9.3), 2)):
        n = len([v for v in inside(r, net) if v[4] >= 0.3 - 1e-6])
        row(f"PWR-8 {label}", f"≥{want} 个 0.3 mm 过孔", f"{n} 个", n >= want)
    widths = sorted({round(w, 2) for name, layer, w, pts in power.TRACKS if name == "VBUS"})
    row("PWR-9", "VBUS 线宽 ≥1.0 mm", f"主干 1.0 mm；Type-C 两侧各一条 0.6 mm（两条并联）；充电芯片引脚处 {widths[0]} mm", "见说明")
    for label, pin, others in (("充电", ("U2", "19"), [("L1", "1")]), ("3.3 V 降压", ("U3", "3"), [("L2", "1")]),
                               ("背光升压", ("U11", "1"), [("L3", "2"), ("D5", "2")])):
        d = max(rect_gap(rect(*pin), rect(*o)) for o in others)
        net = pads[pin][0]["net"]
        nv = len([v for v in vias if v[0] == net])
        row(f"PWR-12 {label}", "开关节点铜长 ≤3 mm，不打过孔", f"{d:.2f} mm，{nv} 个过孔", d <= 3.0 and nv == 0)
    for label, key, want in (("充电芯片", ("U2", "25"), 5), ("功放", ("U17", "17"), 4)):
        n = len(inside(rect(*key), "GND"))
        row(f"PWR-14 {label}", f"散热焊盘 ≥{want} 个地孔", f"{n} 个", n >= want)
    n = len([p for p in pads.get(("U4", "41"), []) if p["pth"]])
    row("DEC-6", "ESP32 底部地焊盘 ≥9 个地孔", f"{n} 个（封装自带）", n >= 9)

    # ---- antenna line -----------------------------------------------------------------------------------
    rf = [t for t in tracks if t[0] in RF]
    if rf:
        length = sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in rf)
        row("RF-6", "天线线总长 ≤15 mm", f"{length:.1f} mm（不含焊盘）", length <= 15)
        gap = 99.0
        for name, layer, x0, y0, x1, y1, w in tracks:
            if name in RF or name == "GND" or layer != pcbnew.B_Cu:
                continue
            gap = min(gap, min(seg_seg(x0, y0, x1, y1, t[2], t[3], t[4], t[5]) - w / 2 - t[6] / 2 for t in rf))
        for name, x, y, dia, drill in vias:
            if name not in RF and name != "GND":
                gap = min(gap, min(pt_seg(x, y, t[2], t[3], t[4], t[5]) - dia / 2 - t[6] / 2 for t in rf))
        row("RF-9", "背面其它信号离天线线 ≥1 mm", f"最近 {gap:.2f} mm" if gap < 50 else "附近没有别的走线", gap >= 1.0)
        ends = [(t[2], t[3]) for t in rf] + [(t[4], t[5]) for t in rf]
        a = min(ends, key=lambda p: p[1])
        b = max(ends, key=lambda p: p[1])
        axis = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / axis, (b[1] - a[1]) / axis
        worst = 0.0
        count = 0
        far = 0.0
        for side in (1, -1):
            beside = [v for v in vias if v[0] == "GND"
                      and 0 < side * ((v[1] - a[0]) * -uy + (v[2] - a[1]) * ux) <= 2.0
                      and -0.6 <= (v[1] - a[0]) * ux + (v[2] - a[1]) * uy <= axis + 0.6]
            along = sorted((v[1] - a[0]) * ux + (v[2] - a[1]) * uy for v in beside)
            far = max([far] + [side * ((v[1] - a[0]) * -uy + (v[2] - a[1]) * ux) for v in beside])
            count += len(along)
            # the socket's own ground pads count as ground beside the line where they lie along it
            for p in pads.get(("J7", "2"), []):
                x0, y0, x1, y1 = p["rect"]
                lat = [side * ((x - a[0]) * -uy + (y - a[1]) * ux) for x in (x0, x1) for y in (y0, y1)]
                if min(lat) <= 1.6 and max(lat) > 0:
                    ts = [(x - a[0]) * ux + (y - a[1]) * uy for x in (x0, x1) for y in (y0, y1)]
                    along += [t for t in (min(ts), (min(ts) + max(ts)) / 2, max(ts)) if 0 <= t <= axis]
            pts = [0.0] + sorted(along) + [axis]
            worst = max(worst, max(q - p for p, q in zip(pts, pts[1:])))
        row("RF-5", "线两侧地孔，间距 ≤2 mm（天线座的地焊盘算作地）", f"{count} 个，最大间隔 {worst:.1f} mm；最远的一个离线中心 {far:.2f} mm", worst <= 2.0)
        for k, p in enumerate(sorted(pads.get(("J7", "2"), []), key=lambda p: p["rect"][1])):
            n = len(near(p["rect"], "GND", 1.2))
            row(f"RF-11 天线座地焊盘 {k + 1}", "旁边 ≥2 个地孔", f"{n} 个", n >= 2)

    # ---- USB ----------------------------------------------------------------------------------------------
    try:
        with open(os.path.join(OUT, "build", "routing.json"), encoding="utf-8") as f:
            usb = json.load(f).get("usb", [])
    except OSError:
        usb = []
    def path(net, a, b):
        """Length of copper from pad a to pad b of a net, along the tracks, branches to test pads left out.
        Also the total copper of the net, so that the length of those branches can be told."""
        segs = [t for t in tracks if t[0] == net]
        pts = {}                                             # (layer, x, y) -> node
        node = lambda l, x, y: pts.setdefault((l, round(x, 3), round(y, 3)), len(pts))
        cuts = {i: [0.0, 1.0] for i in range(len(segs))}
        for i, (_, l, x0, y0, x1, y1, w) in enumerate(segs):  # an end that lands on the body of another piece
            for j, (_, l2, a0, b0, a1, b1, w2) in enumerate(segs):
                if i == j or l != l2:
                    continue
                for ex, ey in ((x0, y0), (x1, y1)):
                    d2 = (a1 - a0) ** 2 + (b1 - b0) ** 2
                    f = max(0.0, min(1.0, ((ex - a0) * (a1 - a0) + (ey - b0) * (b1 - b0)) / d2)) if d2 else 0.0
                    if math.hypot(ex - a0 - f * (a1 - a0), ey - b0 - f * (b1 - b0)) <= w2 / 2 + 1e-6:
                        cuts[j].append(f)
        edges = {}
        def link(u, v, d):
            edges.setdefault(u, []).append((v, d))
            edges.setdefault(v, []).append((u, d))
        for i, (_, l, x0, y0, x1, y1, w) in enumerate(segs):
            fs = sorted(set(cuts[i]))
            for f, g in zip(fs, fs[1:]):
                link(node(l, x0 + f * (x1 - x0), y0 + f * (y1 - y0)), node(l, x0 + g * (x1 - x0), y0 + g * (y1 - y0)),
                     (g - f) * math.hypot(x1 - x0, y1 - y0))
        items = list(pts.items())
        for (l, x, y), u in items:                           # ends that touch: on a layer, through a via, in a pad
            for (l2, x2, y2), v in items:
                if u < v and l == l2 and math.hypot(x - x2, y - y2) <= 0.1:
                    link(u, v, math.hypot(x - x2, y - y2))
        for name, vx, vy, dia, drill in vias:
            if name == net:
                hub = node("via", vx, vy)
                for (l, x, y), u in items:
                    if l != "via" and math.hypot(x - vx, y - vy) <= dia / 2:
                        link(hub, u, math.hypot(x - vx, y - vy))
        ends = {}
        for key, group in pads.items():                      # every pad of the net joins what ends in it
            for pad in group:
                if pad["net"] != net:
                    continue
                hub = ends.setdefault(key, node("pad", len(pts), 0))
                x0, y0, x1, y1 = pad["rect"]
                for (l, x, y), u in list(pts.items()):
                    if l in pad["layers"] and x0 - 1e-3 <= x <= x1 + 1e-3 and y0 - 1e-3 <= y <= y1 + 1e-3:
                        link(hub, u, 0.0)
        ends = [ends[a], ends[b]]
        dist, todo = {ends[0]: 0.0}, [ends[0]]
        while todo:                                          # small graphs: plain relaxation
            u = todo.pop()
            for v, d in edges.get(u, []):
                if dist[u] + d < dist.get(v, 1e9) - 1e-9:
                    dist[v] = dist[u] + d
                    todo.append(v)
        return dist.get(ends[1]), sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in segs)

    # USB-3 is about the two lines between the same two parts: the way from pin to pin, not all copper of the net
    # (the branches to the test pads would count as length otherwise).
    PAIRS = [("Type-C → 切换芯片（A 面触点）", ("USBC_DP", ("J1", "A6"), ("U6", "7")), ("USBC_DM", ("J1", "A7"), ("U6", "6"))),
             ("Type-C → 切换芯片（B 面触点）", ("USBC_DP", ("J1", "B6"), ("U6", "7")), ("USBC_DM", ("J1", "B7"), ("U6", "6"))),
             ("Air780E → 切换芯片", ("LTE_USB_DP", ("U9", "59"), ("U6", "9")), ("LTE_USB_DM", ("U9", "60"), ("U6", "8"))),
             ("切换芯片 → 串联电阻", ("ESP_USB_DP", ("U6", "3"), ("R18", "2")), ("ESP_USB_DM", ("U6", "4"), ("R19", "2"))),
             ("串联电阻 → ESP32", ("ESP_DP", ("R18", "1"), ("U4", "14")), ("ESP_DM", ("R19", "1"), ("U4", "13")))]
    for title, dp, dm in PAIRS:
        if (dp[1] not in pads) or (dp[2] not in pads):
            continue
        (lp, tp), (ln, tn) = path(*dp), path(*dm)
        if lp is None or ln is None:
            row(f"USB-3 {title}", "两根线引脚到引脚的长度差 ≤0.5 mm", "还没连通", False)
            continue
        row(f"USB-3 {title}", "两根线引脚到引脚的长度差 ≤0.5 mm", f"{abs(lp - ln):.2f} mm（D+ {lp:.2f} / D− {ln:.2f}）",
            abs(lp - ln) <= 0.5)

    lines = ["| 规则 | 要求 | 实测 | 结论 |", "|---|---|---|---|"] + ["| " + " | ".join(r) + " |" for r in rows]
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(OUT, "build", "check.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
