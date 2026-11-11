"""Route the placed board with a simple grid maze router and add the copper zones.

    /usr/bin/python3.12 route.py [output_dir]

Reads <name>.kicad_pcb written by board.py and writes it back with tracks, vias and zones.
Layers: F.Cu and B.Cu carry signals, In1.Cu is a solid GND plane, In2.Cu is the +3V3 plane
(the router may also use In2 for a signal when it has to, at a higher cost).
"""
import ctypes
import json
import math
import os
import re
import subprocess
import sys
import time

import pcbnew
from PIL import Image, ImageDraw

from board import H as BOARD_H, NAME, OX, OY, W as BOARD_W
from preview import outline_points

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")

G = 0.05                      # grid pitch, mm
CLR = 0.10                    # copper clearance, mm
W_DEF = 0.15                  # default track width
MARGIN = 0.02
R0 = CLR + W_DEF / 2 + MARGIN  # growth of every obstacle in the owner map
EDGE = 0.30                   # copper to board edge
HOLE_CLR = 0.25               # hole to hole / hole to copper
ROUTE_LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
NL = len(ROUTE_LAYERS)
GW, GH = int(round(BOARD_W / G)) + 1, int(round(BOARD_H / G)) + 1

PLANES = {"GND": pcbnew.In1_Cu}
RF = {"LTE_ANT", "LTE_ANT_C"}
RF_EXTRA = 0.2                # the antenna line keeps 0.3 mm from everything else, pours included
RF_GND_AREA = (21.3, 21.0, 26.0, 32.5)   # under the antenna line: In2 is ground here and carries no tracks
USB = {"USBC_DP", "USBC_DM", "ESP_DP", "ESP_DM", "ESP_USB_DP", "ESP_USB_DM", "LTE_USB_DP", "LTE_USB_DM"}
USB_PAIRS = [("USBC_DP", "USBC_DM"), ("ESP_DP", "ESP_DM"), ("ESP_USB_DP", "ESP_USB_DM"), ("LTE_USB_DP", "LTE_USB_DM")]
COUPLED = [("ESP_USB_DP", "ESP_USB_DM", 1)]   # long pairs laid side by side on this routing layer (1 = In2)
PAIR_W, PAIR_GAP = 0.2, 0.15
VDD_4G_AREA = [(17.6, 5.65), (20.45, 5.65), (20.45, 10.9), (23.15, 10.9), (23.15, 13.0), (20.45, 13.0),
               (20.45, 18.1), (16.9, 18.1), (16.9, 8.6), (17.6, 8.6)]   # copper pour on the back, mm
PWR_HI = {"VBUS", "VBAT", "VSYS", "VDD_4G", "CHG_SW", "CHG_PMID"}
PWR_LO = {"BUCK_SW", "BL_SW", "LCD_LEDA", "LCD_LEDK", "PA_OUTP", "PA_OUTN", "SPK_P", "SPK_N", "+2V8", "+1V2",
          "CHG_REGN", "CHG_BTST", "SIM_VDD", "LCD_VCI", "CAMF_IOVDD", "CAMF_DVDD"}


def net_rules(name):
    """widths to try (mm), via (diameter, drill) or None, layer costs (F, In2, B; 0 = not allowed), via cost."""
    if name in RF:
        return dict(widths=[0.35], via=None, lcost=(0, 0, 1), viacost=0)
    if name in PLANES:
        return dict(widths=[0.25, 0.15], via=(0.45, 0.2), lcost=(1, 0, 1), viacost=0)
    if name == "+3V3":      # trunk on In2 (a +3V3 pour fills the rest of that layer), short stubs to the pads
        return dict(widths=[0.3, 0.2, 0.15], via=(0.45, 0.2), lcost=(3, 1, 3), viacost=300)
    if name in USB:
        return dict(widths=[PAIR_W, 0.15], via=(0.45, 0.2), lcost=(1, 2, 1), viacost=500)
    if name in PWR_HI:
        return dict(widths=[0.6, 0.4, 0.25, 0.15], via=(0.6, 0.3), lcost=(1, 4, 1), viacost=600)
    if name in PWR_LO:
        return dict(widths=[0.3, 0.2, 0.15], via=(0.5, 0.25), lcost=(1, 4, 1), viacost=500)
    return dict(widths=[0.15], via=(0.45, 0.2), lcost=(2, 3, 2), viacost=1000)


def build_core():
    so = os.path.join(OUT, "build", "route_core.so")
    src = os.path.join(HERE, "route_core.c")
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        subprocess.run(["gcc", "-O2", "-shared", "-fPIC", src, "-o", so, "-lm"], check=True)
    lib = ctypes.CDLL(so)
    d, i = ctypes.c_double, ctypes.c_int
    lib.rt_paint_rect.argtypes = [i, d, d, d, d, d, i, i, i]
    lib.rt_paint_seg.argtypes = [i, d, d, d, d, d, i, i, i]
    lib.rt_viablock_rect.argtypes = [d, d, d, d, d]
    lib.rt_block_mask.argtypes = [ctypes.c_char_p, i]
    lib.rt_window.argtypes = [i, i, i, i]
    lib.rt_set_fixed.argtypes = [i]
    lib.rt_usable.argtypes = [i, i, i, i, i, ctypes.POINTER(i)]
    lib.rt_via_ok.argtypes = [i, i, i, i, ctypes.POINTER(i)]
    lib.rt_route.argtypes = [i, i, ctypes.POINTER(i), i, i, ctypes.POINTER(i), i, ctypes.POINTER(i), i, i,
                             ctypes.POINTER(ctypes.c_int32), i, ctypes.POINTER(i)]
    return lib


def disc_offsets(radius_mm):
    r = max(0.0, radius_mm) / G
    if r > 0:
        r += 0.5                       # round up: the probe must cover the whole track width
    n = int(math.ceil(r))
    pts = [(dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1) if dx * dx + dy * dy <= r * r + 1e-9]
    flat = [v for p in pts for v in p]
    return len(pts), (ctypes.c_int * len(flat))(*flat)


class Router:
    def __init__(self, board):
        self.board = board
        self.lib = build_core()
        self.lib.rt_init(GW, GH, NL)
        self.net_id, self.net_name = {}, {}
        self.comps = {}            # net id -> list of component ids (one per pad)
        self.pads = []             # (net id, layers, rect mm, is_pth, comp id)
        self.tracks = []           # (net id, layer index, x0, y0, x1, y1, width)
        self.vias = []             # (net id, x, y, diameter, drill)
        self.failed = []
        self.critical = set()      # tracks and vias of the nets routed by rule: exported locked
        self.masks = []
        self.outbuf = (ctypes.c_int32 * 20000)()
        self.load_pads()

    # ---- geometry helpers -------------------------------------------------------------------
    def nid(self, name):
        if name not in self.net_id:
            self.net_id[name] = len(self.net_id) + 1
            self.net_name[self.net_id[name]] = name
        return self.net_id[name]

    def load_pads(self):
        lib = self.lib
        cu = [l for l in ROUTE_LAYERS]
        self.npth, self.keepouts = [], []
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                on = [k for k, layer in enumerate(cu) if pad.IsOnLayer(layer)]
                bb = pad.GetBoundingBox()
                rect = (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                        pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
                attr = pad.GetAttribute()
                if attr == pcbnew.PAD_ATTRIB_NPTH:
                    self.npth.append(rect)
                    continue
                if not on:
                    continue                      # paste-only aperture
                name = pad.GetNetname()
                if not name:
                    name = f"nonet-{fp.GetReference()}-{pad.GetNumber()}"
                net = self.nid(name)
                pth = attr == pcbnew.PAD_ATTRIB_PTH
                round_pad = pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
                self.pads.append(dict(net=net, layers=on, rect=rect, pth=pth, round=round_pad,
                                      ref=fp.GetReference(), num=pad.GetNumber()))
            for zone in fp.Zones():
                if not zone.GetIsRuleArea():
                    continue
                bb = zone.GetBoundingBox()
                rect = (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                        pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
                layers = [k for k, layer in enumerate(cu) if zone.IsOnLayer(layer)]
                self.keepouts.append((layers, rect, zone.GetDoNotAllowTracks(), zone.GetDoNotAllowVias()))

    def paint_pad(self, p, comp):
        lib = self.lib
        x0, y0, x1, y1 = [v / G for v in p["rect"]]
        w, h = x1 - x0, y1 - y0
        shrink = 0.35 * min(w, h)
        grow = R0 + (RF_EXTRA if self.net_name[p["net"]] in RF else 0.0)
        for l in p["layers"]:
            if p["round"]:
                cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, w / 2
                lib.rt_paint_seg(l, cx, cy, cx, cy, r + grow / G, p["net"], 0, 0)
                lib.rt_paint_seg(l, cx, cy, cx, cy, max(0.6, r * 0.5), p["net"], 1, comp)
            else:
                lib.rt_paint_rect(l, x0, y0, x1, y1, grow / G, p["net"], 0, 0)
                lib.rt_paint_rect(l, x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink, 0.3, p["net"], 1, comp)
        # no via centre inside or right next to a pad
        lib.rt_viablock_rect(x0, y0, x1, y1, (0.40 if p["pth"] else 0.20) / G)

    def build_maps(self, frozen=()):
        """(Re)paint every map from the pad list and the tracks / vias routed so far.
        Tracks of plane nets and of the nets in `frozen` count as fixed: rip-up never crosses them."""
        lib = self.lib
        lib.rt_clear()
        lib.rt_set_fixed(1)
        # usable board area: inside the outline, minus the edge clearance
        if not self.masks:
            pts = [(x / G, y / G) for x, y in outline_points()]
            for vias_only, grow in ((0, EDGE + W_DEF / 2 + MARGIN), (1, EDGE + 0.30 + MARGIN)):
                img = Image.new("L", (GW, GH), 0)
                d = ImageDraw.Draw(img)
                d.polygon(pts, fill=255)
                wpx = int(math.ceil(2 * grow / G))
                d.line(pts + pts[:1], fill=0, width=wpx)
                for x, y in pts:
                    d.ellipse([x - wpx / 2, y - wpx / 2, x + wpx / 2, y + wpx / 2], fill=0)
                self.masks.append((img.tobytes(), vias_only))
        for mask, vias_only in self.masks:
            lib.rt_block_mask(mask, vias_only)
        for x0, y0, x1, y1 in self.npth:
            cx, cy, r = (x0 + x1) / 2 / G, (y0 + y1) / 2 / G, (x1 - x0) / 2 / G
            for l in range(NL):
                lib.rt_paint_seg(l, cx, cy, cx, cy, r + (HOLE_CLR + W_DEF / 2 + MARGIN) / G, -1, 0, 0)
            lib.rt_viablock_rect(cx, cy, cx, cy, r + (HOLE_CLR + 0.15 + MARGIN) / G)
        for layers, (x0, y0, x1, y1), no_tracks, no_vias in self.keepouts:
            if no_tracks:
                for l in layers:
                    lib.rt_paint_rect(l, x0 / G, y0 / G, x1 / G, y1 / G, (W_DEF / 2 + MARGIN) / G, -1, 0, 0)
            if no_vias or no_tracks:
                lib.rt_viablock_rect(x0 / G, y0 / G, x1 / G, y1 / G, 0.3 / G)
        x0, y0, x1, y1 = [v / G for v in RF_GND_AREA]          # the antenna line needs unbroken ground below it
        lib.rt_paint_rect(1, x0, y0, x1, y1, (W_DEF / 2 + MARGIN) / G, -1, 0, 0)
        self.comps, self.comp_rect, self.net_box = {}, {}, {}
        for p in self.pads:
            plane = p["pth"] and self.net_name[p["net"]] in PLANES
            comp = lib.rt_new_comp(1 if plane else 0)
            p["comp"] = comp
            self.comp_rect[comp] = p["rect"]
            box = self.net_box.setdefault(p["net"], list(p["rect"]))
            box[0], box[1] = min(box[0], p["rect"][0]), min(box[1], p["rect"][1])
            box[2], box[3] = max(box[2], p["rect"][2]), max(box[3], p["rect"][3])
            self.comps.setdefault(p["net"], []).append(comp)
            self.paint_pad(p, comp)
        tracks, vias = self.tracks, self.vias
        self.tracks, self.vias = [], []
        fixed = set(frozen) | {self.net_id[n] for n in PLANES if n in self.net_id}
        for keep in (1, 0):
            lib.rt_set_fixed(keep)
            for t in tracks:
                if (t[0] in fixed) == bool(keep):
                    self.add_track(*t, comp=None)
            for v in vias:
                if (v[0] in fixed) == bool(keep):
                    self.add_via(*v, comp=None)
        lib.rt_set_fixed(0)

    def remove_net(self, net):
        self.tracks = [t for t in self.tracks if t[0] != net]
        self.vias = [v for v in self.vias if v[0] != net]

    def conflicts(self, net, cells, width, rules):
        """Nets whose tracks or vias are too close to a path found in rip-up mode."""
        segs, via_pts = [], []
        start = prev = cells[0]
        for c in cells[1:]:
            if c[0] != prev[0]:
                segs.append((start[0], start[2] * G, start[1] * G, prev[2] * G, prev[1] * G))
                via_pts.append((prev[2] * G, prev[1] * G))
                start = c
            prev = c
        segs.append((start[0], start[2] * G, start[1] * G, prev[2] * G, prev[1] * G))
        # the path between two layer changes is not straight: test it cell run by cell run
        runs = []
        run_start = cells[0]
        last = cells[0]
        direction = None
        for c in cells[1:]:
            d = (c[0] - last[0], c[2] - last[2], c[1] - last[1])
            if d != direction and direction is not None:
                if run_start[0] == last[0]:
                    runs.append((last[0], run_start[2] * G, run_start[1] * G, last[2] * G, last[1] * G))
                run_start = last
            direction = d
            last = c
        if run_start[0] == last[0]:
            runs.append((last[0], run_start[2] * G, run_start[1] * G, last[2] * G, last[1] * G))
        via = rules["via"] or (0.45, 0.2)
        hit = set()
        for onet, l, x0, y0, x1, y1, w in self.tracks:
            if onet == net:
                continue
            need = w / 2 + width / 2 + CLR + MARGIN
            for rl, a0, b0, a1, b1 in runs:
                if rl == l and seg_seg(a0, b0, a1, b1, x0, y0, x1, y1) < need:
                    hit.add(onet)
                    break
            else:
                for vx, vy in via_pts:
                    if pt_seg(vx, vy, x0, y0, x1, y1) < w / 2 + via[0] / 2 + CLR + MARGIN:
                        hit.add(onet)
                        break
        for onet, x, y, dia, drill in self.vias:
            if onet == net:
                continue
            for rl, a0, b0, a1, b1 in runs:
                if pt_seg(x, y, a0, b0, a1, b1) < dia / 2 + width / 2 + CLR + MARGIN:
                    hit.add(onet)
                    break
            else:
                for vx, vy in via_pts:
                    if math.hypot(vx - x, vy - y) < max(dia / 2 + via[0] / 2 + CLR, drill / 2 + via[1] / 2 + HOLE_CLR) + MARGIN:
                        hit.add(onet)
                        break
        return hit

    def add_track(self, net, l, x0, y0, x1, y1, width, comp):
        lib = self.lib
        if comp is None:
            comp = lib.rt_new_comp(0)
            self.comps.setdefault(net, []).append(comp)
        a = (x0 / G, y0 / G, x1 / G, y1 / G)
        extra = RF_EXTRA if self.net_name[net] in RF else 0.0
        lib.rt_paint_seg(l, *a, (width / 2 + R0 + extra) / G, net, 0, 0)
        lib.rt_paint_seg(l, *a, 0.6, net, 1, comp)
        self.tracks.append((net, l, x0, y0, x1, y1, width))
        return comp

    def add_via(self, net, x, y, dia, drill, comp):
        lib = self.lib
        if comp is None:
            comp = lib.rt_new_comp(1 if self.net_name[net] in PLANES else 0)
            self.comps.setdefault(net, []).append(comp)
        cx, cy = x / G, y / G
        for l in range(NL):
            lib.rt_paint_seg(l, cx, cy, cx, cy, (dia / 2 + R0) / G, net, 0, 0)
            lib.rt_paint_seg(l, cx, cy, cx, cy, 0.6, net, 1, comp)
        lib.rt_viablock_rect(cx, cy, cx, cy, (drill / 2 + HOLE_CLR + 0.15 + MARGIN) / G)
        self.vias.append((net, x, y, dia, drill))
        return comp

    # ---- nets that need more than "connect the pads" -------------------------------------------
    def pad(self, ref, net_name):
        net = self.net_id[net_name]
        return next(p for p in self.pads if p["ref"] == ref and p["net"] == net)

    def preroute_decoupling(self):
        """ESP32 supply: via -> 22 uF -> 100 nF -> pin 2, so the current passes the capacitors first."""
        net = self.net_id["+3V3"]
        rules = dict(widths=[0.4, 0.25], via=(0.45, 0.2), lcost=(0, 0, 1), viacost=0)
        bulk, small = self.pad("C12", "+3V3"), self.pad("C13", "+3V3")
        res = self.search(net, bulk["comp"], rules, 0.4, True, bulk["rect"], 3.0)
        if res:
            self.commit(net, bulk["comp"], res[0], res[1], rules, 0.4, True)
        for _ in range(2):                       # 100 nF to its nearest neighbour, twice: bulk cap and pin
            for width in rules["widths"]:
                res = self.search(net, small["comp"], rules, width, False, small["rect"], 4.0)
                if res:
                    self.commit(net, small["comp"], res[0], res[1], rules, width, False)
                    break

    def stitch_rf(self):
        """Ground vias on both sides of the antenna line."""
        lib = self.lib
        gnd = self.net_id["GND"]
        via = net_rules("GND")["via"]
        nvp, vprobe = disc_offsets(via[0] / 2 - W_DEF / 2 + 0.01)
        added = 0
        for net, l, x0, y0, x1, y1, w in list(self.tracks):
            if self.net_name[net] not in RF:
                continue
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 0.3:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            off = w / 2 + 0.3 + via[0] / 2 + 0.15
            steps = max(1, int(length / 1.2))
            for k in range(steps + 1):
                for side in (1, -1):
                    x = x0 + ux * length * k / steps - side * uy * off
                    y = y0 + uy * length * k / steps + side * ux * off
                    ix, iy = round(x / G), round(y / G)
                    if 0 <= ix < GW and 0 <= iy < GH and lib.rt_via_ok(gnd, ix, iy, nvp, vprobe):
                        self.add_via(gnd, ix * G, iy * G, via[0], via[1], None)
                        added += 1
        return added

    def route_pair(self, pname, nname, layer):
        """Lay two nets side by side: find a path for one fat track, then put the two real tracks at
        +/- half the pitch from its centre line. The ends are joined to the pads afterwards by route_net."""
        lib = self.lib
        P, N = self.net_id[pname], self.net_id[nname]
        ppads = [p for p in self.pads if p["net"] == P]
        npads = [p for p in self.pads if p["net"] == N]

        def mid(p):
            return (p["rect"][0] + p["rect"][2]) / 2, (p["rect"][1] + p["rect"][3]) / 2

        ends = []
        for p in ppads:
            q = min(npads, key=lambda n: math.dist(mid(p), mid(n)))
            ends.append((mid(p), mid(q)))
        a_end = ends[0]
        b_end = max(ends, key=lambda e: math.dist(e[0], a_end[0]))     # the end farthest from the first one
        fat = 2 * PAIR_W + PAIR_GAP + 0.2                 # a little extra for the corners
        np_, probe = disc_offsets(fat / 2 - W_DEF / 2)
        X = self.nid(f"pair-{pname}")

        def port(end):
            cx, cy = round((end[0][0] + end[1][0]) / 2 / G), round((end[0][1] + end[1][1]) / 2 / G)
            best = None
            for r in range(0, int(5.0 / G)):
                for dx in range(-r, r + 1):
                    for dy in (range(-r, r + 1) if abs(dx) == r else (-r, r)):
                        x, y = cx + dx, cy + dy
                        if 0 <= x < GW and 0 <= y < GH and lib.rt_usable(X, layer, x, y, np_, probe):
                            d = dx * dx + dy * dy
                            if best is None or d < best[0]:
                                best = (d, x, y)
                if best and best[0] <= r * r:
                    return best[1], best[2]
            return None

        pa, pb = port(a_end), port(b_end)
        if not pa or not pb or math.dist(pa, pb) * G < 3.0:
            return False
        ca, cb = lib.rt_new_comp(0), lib.rt_new_comp(0)
        lib.rt_paint_seg(layer, pa[0], pa[1], pa[0], pa[1], 0.6, X, 1, ca)
        lib.rt_paint_seg(layer, pb[0], pb[1], pb[0], pb[1], 0.6, X, 1, cb)
        rules = dict(via=None, lcost=tuple(1 if l == layer else 0 for l in range(NL)), viacost=0)
        res = self.search(X, ca, rules, fat, False)
        if not res:
            return False
        cells = res[0]
        pts, prev = [cells[0]], None
        for i in range(1, len(cells)):
            d = (cells[i][2] - cells[i - 1][2], cells[i][1] - cells[i - 1][1])
            if prev is not None and d != prev:
                pts.append(cells[i - 1])
            prev = d
        pts.append(cells[-1])
        line = [(c[2] * G, c[1] * G) for c in pts]
        norms = []
        for i in range(len(line) - 1):
            ux, uy = line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]
            ln = math.hypot(ux, uy)
            norms.append((-uy / ln, ux / ln))

        def shifted(d):
            out = []
            for j, (x, y) in enumerate(line):
                if j == 0:
                    nx, ny, k = norms[0][0], norms[0][1], 1.0
                elif j == len(line) - 1:
                    nx, ny, k = norms[-1][0], norms[-1][1], 1.0
                else:
                    ax, ay = norms[j - 1]
                    bx, by = norms[j]
                    nx, ny, k = ax + bx, ay + by, 1.0 / (1.0 + ax * bx + ay * by)
                out.append((x + d * k * nx, y + d * k * ny))
            return out

        m = ((a_end[0][0] + a_end[1][0]) / 2, (a_end[0][1] + a_end[1][1]) / 2)
        side = 1 if (a_end[0][0] - m[0]) * norms[0][0] + (a_end[0][1] - m[1]) * norms[0][1] >= 0 else -1
        half = (PAIR_W + PAIR_GAP) / 2
        for net, d in ((P, side * half), (N, -side * half)):
            pl = shifted(d)
            for (x0, y0), (x1, y1) in zip(pl, pl[1:]):
                self.add_track(net, layer, x0, y0, x1, y1, PAIR_W, None)
        return True

    # ---- routing ----------------------------------------------------------------------------
    def search(self, net, src, rules, width, plane_mode, box=None, margin=None, rip_pen=0):
        """box (mm) limits the search area; None searches the whole board."""
        lib = self.lib
        if box is None:
            lib.rt_window(0, 0, GW - 1, GH - 1)
        else:
            lib.rt_window(int((box[0] - margin) / G), int((box[1] - margin) / G),
                          int((box[2] + margin) / G) + 1, int((box[3] + margin) / G) + 1)
        np_, probe = disc_offsets(width / 2 - W_DEF / 2 + (RF_EXTRA if self.net_name.get(net) in RF else 0.0))
        via = rules["via"]
        nvp, vprobe = disc_offsets((via[0] / 2 if via else 0.3) - W_DEF / 2 + 0.01)
        lcost = (ctypes.c_int * NL)(*rules["lcost"])
        kind = ctypes.c_int(0)
        viacost = rules["viacost"] if via else 0
        n = lib.rt_route(net, src, lcost, viacost, np_, probe, nvp, vprobe, 1 if plane_mode else 0, rip_pen,
                         self.outbuf, len(self.outbuf), ctypes.byref(kind))
        if n == 0:
            return None
        cells = []
        for k in range(n - 1, -1, -1):
            s = self.outbuf[k]
            cells.append((s // (GW * GH), (s % (GW * GH)) // GW, s % GW))
        return cells, kind.value

    def commit(self, net, src, cells, kind, rules, width, plane_mode):
        lib = self.lib
        root = lib.rt_find(src)
        start, prev, direction = cells[0], cells[0], None
        via = rules["via"]
        end = cells[-1]
        joined = lib.rt_comp_at(end[0], end[2], end[1])      # read before the new track is painted over it

        def seg(a, b):
            if a != b:
                self.add_track(net, a[0], a[2] * G, a[1] * G, b[2] * G, b[1] * G, width, root)

        for c in cells[1:]:
            if c[0] != prev[0]:
                seg(start, prev)
                self.add_via(net, prev[2] * G, prev[1] * G, via[0], via[1], root)
                start, direction = c, None
            else:
                d = (c[2] - prev[2], c[1] - prev[1])
                if direction is not None and d != direction:
                    seg(start, prev)
                    start = prev
                direction = d
            prev = c
        seg(start, prev)
        if plane_mode and kind == 1:
            self.add_via(net, end[2] * G, end[1] * G, via[0], via[1], root)
            lib.rt_set_plane(root)
        else:
            lib.rt_unite(root, joined)

    def route_net(self, name, record=True):
        """Connect all pads of a net. Returns the number of connections that could not be made."""
        lib = self.lib
        net = self.net_id.get(name)
        if net is None or net not in self.comps:
            return 0
        rules = net_rules(name)
        plane_mode = name in PLANES
        bad = set()
        while True:
            roots = sorted({lib.rt_find(c) for c in self.comps[net]})
            if plane_mode:
                todo = [r for r in roots if not lib.rt_plane(r) and r not in bad]
            else:
                todo = [r for r in roots if r not in bad] if len(roots) > 1 else []
            if not todo:
                break
            src = todo[0]
            if plane_mode:
                windows = [(self.comp_rect.get(src), 3.0), (self.comp_rect.get(src), 8.0), (None, None)]
                windows = [w for w in windows if w[0] or w[1] is None]
            else:
                windows = [(self.net_box[net], 2.5), (None, None)]
            done = False
            for width in rules["widths"]:
                for box, margin in windows:
                    res = self.search(net, src, rules, width, plane_mode, box, margin)
                    if res:
                        self.commit(net, src, res[0], res[1], rules, width, plane_mode)
                        bad = {lib.rt_find(b) for b in bad}
                        done = True
                        break
                if done:
                    break
            if not done:
                bad.add(src)
        roots = {lib.rt_find(c) for c in self.comps[net]}
        missing = sum(1 for r in roots if not lib.rt_plane(r)) if plane_mode else len(roots) - 1
        if missing and record:
            self.failed.append((name, missing))
        return missing

    def rip_up(self, limit=300, pen=40, budget=240.0):
        """Rip-up and reroute: let a failed net push through other nets' tracks, remove those nets,
        route the failed one, then route the removed ones again."""
        lib = self.lib
        queue = []
        for name, _ in self.failed:
            if name not in queue:
                queue.append(name)
        self.failed = []
        ripped, final = {}, {}
        frozen = {self.net_id[n] for n in RF | USB | PWR_HI | {"+3V3"} if n in self.net_id}   # never pushed out
        rounds = 0
        t0 = time.time()
        while queue and rounds < limit and time.time() - t0 < budget:
            name = queue.pop(0)
            net = self.net_id[name]
            miss = self.route_net(name, record=False)
            if not miss:
                final.pop(name, None)
                continue
            final[name] = miss
            if name in PLANES:
                continue
            rules = net_rules(name)
            width = rules["widths"][-1]
            roots = sorted({lib.rt_find(c) for c in self.comps[net]})
            victims = set()
            for src in roots:
                res = self.search(net, src, rules, width, False, None, None, rip_pen=pen)
                if res:
                    victims = {v for v in self.conflicts(net, res[0], width, rules) if v not in frozen}
                    if victims:
                        break
            if not victims:
                continue
            rounds += 1
            if rounds % 10 == 0:
                print(f"  rip-up round {rounds}: {name} pushes out {len(victims)} nets, {len(queue)} queued, "
                      f"{sum(final.values())} missing, {time.time() - t0:.0f} s", flush=True)
            for v in victims:
                self.remove_net(v)
                ripped[v] = ripped.get(v, 0) + 1
                if ripped[v] >= 3:
                    frozen.add(v)
            self.build_maps(frozen)
            miss = self.route_net(name, record=False)
            if miss:
                final[name] = miss
                queue.append(name)
            else:
                final.pop(name, None)
            for v in victims:
                vname = self.net_name[v]
                if vname not in queue:
                    queue.insert(0, vname)
        for name in queue:
            miss = self.route_net(name, record=False)
            if miss:
                final[name] = miss
            else:
                final.pop(name, None)
        self.failed = sorted(final.items())
        return rounds

    def trim_tails(self):
        """Cut back track ends that stick out past the point where the track is joined (a via or another
        track met it a little before its end)."""
        changed = 0
        for _ in range(4):
            again = False
            for i, t in enumerate(self.tracks):
                net, l, x0, y0, x1, y1, w = t
                same = [o for j, o in enumerate(self.tracks) if j != i and o[0] == net and o[1] == l]
                vias = [v for v in self.vias if v[0] == net]
                pads = [p for p in self.pads if p["net"] == net and l in p["layers"]]

                def held(x, y):
                    return (any(pt_seg(x, y, o[2], o[3], o[4], o[5]) <= o[6] / 2 for o in same)
                            or any(math.hypot(x - v[1], y - v[2]) <= v[3] / 2 for v in vias)
                            or any(p["rect"][0] <= x <= p["rect"][2] and p["rect"][1] <= y <= p["rect"][3] for p in pads))

                length = math.hypot(x1 - x0, y1 - y0)
                if length == 0:
                    continue
                joints = []                        # positions (0..1) where something is attached to this track
                for o in same:
                    for px, py in ((o[2], o[3]), (o[4], o[5])):
                        if pt_seg(px, py, x0, y0, x1, y1) <= w / 2:
                            joints.append(((px - x0) * (x1 - x0) + (py - y0) * (y1 - y0)) / length ** 2)
                for v in vias:
                    if pt_seg(v[1], v[2], x0, y0, x1, y1) <= w / 2:
                        joints.append(((v[1] - x0) * (x1 - x0) + (v[2] - y0) * (y1 - y0)) / length ** 2)
                joints = [min(1.0, max(0.0, j)) for j in joints]
                a, b = 0.0, 1.0
                if not held(x0, y0) and joints:
                    a = min(joints)
                if not held(x1, y1) and joints:
                    b = max(joints)
                if (a, b) == (0.0, 1.0):
                    continue
                if b - a <= 1e-9:                  # nothing but a tail: one end joined, the other in the air
                    if self.net_name[net] in PLANES or self.net_name[net] == "+3V3":
                        continue                   # may end in a pour
                    self.critical.discard(t)
                    self.tracks[i] = (net, l, x0, y0, x0, y0, w)
                    changed += 1
                    again = True
                    continue
                new = (net, l, x0 + a * (x1 - x0), y0 + a * (y1 - y0), x0 + b * (x1 - x0), y0 + b * (y1 - y0), w)
                if t in self.critical:
                    self.critical.discard(t)
                    self.critical.add(new)
                self.tracks[i] = new
                changed += 1
                again = True
            self.tracks = [t for t in self.tracks if (t[2], t[3]) != (t[4], t[5])]
            if not again:
                break
        return changed

    # ---- writing the result back into the KiCad board ------------------------------------------
    def export(self):
        b = self.board
        nets = {n: b.FindNet(name) for n, name in self.net_name.items()}
        for net, l, x0, y0, x1, y1, w in self.tracks:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(vec(x0, y0))
            t.SetEnd(vec(x1, y1))
            t.SetWidth(pcbnew.FromMM(w))
            t.SetLayer(ROUTE_LAYERS[l])
            t.SetNet(nets[net])
            t.SetLocked((net, l, x0, y0, x1, y1, w) in self.critical)
            b.Add(t)
        for net, x, y, dia, drill in self.vias:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(vec(x, y))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetDrill(pcbnew.FromMM(drill))
            try:
                v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(dia))
            except TypeError:
                v.SetWidth(pcbnew.FromMM(dia))
            v.SetNet(nets[net])
            v.SetLocked((net, x, y, dia, drill) in self.critical)
            b.Add(v)


def pt_seg(px, py, ax, ay, bx, by):
    vx, vy, wx, wy = bx - ax, by - ay, px - ax, py - ay
    len2 = vx * vx + vy * vy
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / len2)) if len2 > 0 else 0.0
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    def orient(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    o1, o2 = orient(ax, ay, bx, by, cx, cy), orient(ax, ay, bx, by, dx, dy)
    o3, o4 = orient(cx, cy, dx, dy, ax, ay), orient(cx, cy, dx, dy, bx, by)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(pt_seg(ax, ay, cx, cy, dx, dy), pt_seg(bx, by, cx, cy, dx, dy),
               pt_seg(cx, cy, ax, ay, bx, by), pt_seg(dx, dy, ax, ay, bx, by))


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def add_rf_ground(board):
    """Ground on In2 under the antenna line (the layer right below it), and no tracks allowed there."""
    x0, y0, x1, y1 = RF_GND_AREA
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    add_pour(board, "GND", pcbnew.In2_Cu, pts, priority=2)
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetLayer(pcbnew.In2_Cu)
    z.SetZoneName("antenna line: keep In2 ground unbroken")
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowCopperPour(False)
    z.SetDoNotAllowFootprints(False)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in pts:
        outline.Append(vec(x, y))
    board.Add(z)


def strip_copper(src, dst, keep_locked=False):
    """Copy a .kicad_pcb without its tracks, vias and zones (optionally keeping the locked tracks and vias).
    Done on the file text: removing filled zones through the pcbnew Python API is not reliable."""
    text = open(src, encoding="utf-8").read()
    out, depth, start, last, kept = [], 0, None, 0, 0
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|\(|\)', text):
        tok = m.group()
        if tok == "(":
            depth += 1
            if depth == 2:
                start = m.start()
        elif tok == ")":
            depth -= 1
            if depth == 1:
                node = text[start:m.end()]
                head = node[1:].split(None, 1)[0]
                drop = head in ("segment", "arc", "via", "zone")
                if drop and keep_locked and head != "zone" and re.search(r"\(locked yes\)|\blocked\b", node):
                    drop = False
                    kept += 1
                if drop:
                    out.append(text[last:start].rstrip(" \t"))
                    last = m.end()
                    if text[last:last + 1] == "\n":
                        last += 1
    out.append(text[last:])
    with open(dst, "w", encoding="utf-8") as f:
        f.write("".join(out))
    return kept


def add_zone(board, net, layer, priority=0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    outline = z.Outline()
    outline.NewOutline()
    for x, y in ((-1, -1), (BOARD_W + 1, -1), (BOARD_W + 1, BOARD_H + 1), (-1, BOARD_H + 1)):
        outline.Append(vec(x, y))
    z.SetLocalClearance(pcbnew.FromMM(0.15))
    z.SetMinThickness(pcbnew.FromMM(0.15))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.15))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.25))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(priority)
    board.Add(z)


def add_pour(board, net, layer, points, priority=1):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    outline = z.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(vec(x, y))
    z.SetLocalClearance(pcbnew.FromMM(0.15))
    z.SetMinThickness(pcbnew.FromMM(0.15))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(priority)
    board.Add(z)


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    strip_copper(path, path)                   # start clean: a second run must not stack on the first
    board = pcbnew.LoadBoard(path)
    r = Router(board)
    r.build_maps()

    span = {}
    for p in r.pads:
        x0, y0, x1, y1 = p["rect"]
        a = span.setdefault(p["net"], [x0, y0, x1, y1])
        a[0], a[1], a[2], a[3] = min(a[0], x0), min(a[1], y0), max(a[2], x1), max(a[3], y1)
    size = {r.net_name[n]: (a[2] - a[0]) + (a[3] - a[1]) for n, a in span.items()}
    multi = [r.net_name[n] for n, c in r.comps.items() if len(c) > 1 or r.net_name[n] in PLANES]
    lib = r.lib
    total = sum(sum(1 for c in comps if not lib.rt_plane(c)) if r.net_name[n] in PLANES else len(comps) - 1
                for n, comps in r.comps.items())
    special = RF | USB | PWR_HI | PWR_LO | set(PLANES) | {"+3V3"}
    t0 = time.time()
    r.preroute_decoupling()                                   # ESP32: capacitors before the pin
    for name in sorted(n for n in multi if n in RF):          # antenna line first, then its ground vias
        r.route_net(name)
    print(f"antenna line: {r.stitch_rf()} ground vias beside it", flush=True)
    for pname, nname, layer in COUPLED:                       # long USB pair side by side
        ok = r.route_pair(pname, nname, layer)
        print(f"pair {pname} / {nname}: {'laid side by side' if ok else 'no room for a coupled run'}", flush=True)
    for name in sorted((n for n in multi if n in USB), key=size.get):
        r.route_net(name)
    r.critical = set(r.tracks) | set(r.vias)                  # everything so far is locked in the board file
    order = (sorted((n for n in multi if n in PWR_HI), key=size.get)
             + sorted((n for n in multi if n in PWR_LO), key=size.get) + [n for n in multi if n in PLANES]
             + [n for n in multi if n == "+3V3"]
             + sorted((n for n in multi if n not in special), key=size.get))
    for k, name in enumerate(order):
        t1 = time.time()
        miss = r.route_net(name)
        if time.time() - t1 > 8:
            print(f"  [{k + 1}/{len(order)}] {name}: {miss} missing, {time.time() - t1:.1f} s", flush=True)
    first = sum(m for _, m in r.failed)
    print(f"first pass: {total - first} of {total} connections, {time.time() - t0:.0f} s", flush=True)
    rounds = r.rip_up()
    missing = sum(m for _, m in r.failed)
    print(f"rip-up: {rounds} rounds", flush=True)
    print(f"trimmed {r.trim_tails()} track ends", flush=True)
    length = sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in r.tracks)
    print(f"routing: {total - missing} of {total} connections, {len(r.tracks)} segments, {len(r.vias)} vias, "
          f"{length:.0f} mm of track, {time.time() - t0:.0f} s")
    for name, m in r.failed:
        print(f"  NOT ROUTED {name}: {m}")
    usb = []
    for pname, nname in USB_PAIRS:
        ln = {n: sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in r.tracks if r.net_name[t[0]] == n)
              for n in (pname, nname)}
        usb.append(dict(pair=f"{pname} / {nname}", p=round(ln[pname], 1), n=round(ln[nname], 1),
                        diff=round(abs(ln[pname] - ln[nname]), 1)))
        print(f"  USB {pname} {ln[pname]:.1f} mm, {nname} {ln[nname]:.1f} mm, difference {abs(ln[pname] - ln[nname]):.1f} mm")

    r.export()
    add_zone(board, "GND", pcbnew.In1_Cu)
    add_zone(board, "+3V3", pcbnew.In2_Cu)
    add_zone(board, "GND", pcbnew.F_Cu)
    add_zone(board, "GND", pcbnew.B_Cu)
    add_pour(board, "VDD_4G", pcbnew.B_Cu, VDD_4G_AREA)       # Air780E supply: a pour, not just a track
    add_rf_ground(board)
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    with open(os.path.join(OUT, "build", "routing.json"), "w", encoding="utf-8") as f:
        json.dump(dict(total=total, missing=missing, failed=r.failed, vias=len(r.vias), length=round(length), usb=usb), f,
                  ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
