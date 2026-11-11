"""Route the placed board with a simple grid maze router and add the copper zones.

    /usr/bin/python3.12 route.py [output_dir]

Reads <name>.kicad_pcb written by board.py and writes it back with tracks, vias and zones.
Six layers (docs/layout-spec.md): F.Cu and B.Cu carry parts and short tracks, In1.Cu and In4.Cu are
solid ground, In2.Cu is the main signal layer (mostly horizontal), In3.Cu carries +3V3 and signals
(mostly vertical).
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
ROUTE_LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu]   # the two ground planes are not routed
NL = len(ROUTE_LAYERS)
L1, L3, L4, L6 = 0, 1, 2, 3    # index of each routing layer (L2 and L5 are the planes)
L4_SIGNALS = os.environ.get("L4_SIGNALS", "0") == "1"   # STK-6: L4 is a pure +3V3 layer unless this is set
NEGOTIATE = os.environ.get("NEGOTIATE", "0") == "1"     # route by negotiation instead of one net after the other (experimental)
LAYER_DIRS = (0, 1, 2, 0) if L4_SIGNALS else (0, 0, 0, 0)   # 1 = mostly horizontal, 2 = mostly vertical (STK-2)
GW, GH = int(round(BOARD_W / G)) + 1, int(round(BOARD_H / G)) + 1

PLANES = {"GND": pcbnew.In1_Cu, "+3V3": pcbnew.In3_Cu}   # a ground via also lands on In4, the second plane
RF = {"LTE_ANT", "LTE_ANT_C"}
# Antenna line (layout-spec.md 5.1): on the back over the In4 ground, ground beside it on the back.
# In4 is opened only under the socket's signal pad; In3 is ground under that opening.
# Width and gap are design values until the fab's impedance calculator confirms them.
RF_W, RF_GAP = 0.34, 0.2
RF_EXTRA = RF_GAP - CLR       # the line and its pads keep RF_GAP from all other copper, pours included
RF_KEEP = 1.0                 # other signals on the back stay this far from the line (ground may be closer)
RF_SOCKET = "J7"
RF_WIN, RF_WIN_GND, RF_ISLAND = 0.3, 0.2, 1.0   # opening = pad + 0.3, at least 0.2 from ground pads; In3 ground 1 mm larger
USB = {"USBC_DP", "USBC_DM", "ESP_DP", "ESP_DM", "ESP_USB_DP", "ESP_USB_DM", "LTE_USB_DP", "LTE_USB_DM"}
USB_PAIRS = [("USBC_DP", "USBC_DM"), ("ESP_DP", "ESP_DM"), ("ESP_USB_DP", "ESP_USB_DM"), ("LTE_USB_DP", "LTE_USB_DM")]
COUPLED = [("ESP_USB_DP", "ESP_USB_DM", L3)]  # long pairs laid side by side on this routing layer
PAIR_W, PAIR_GAP = 0.19, 0.15
VDD_4G_AREA = [(17.6, 5.65), (20.45, 5.65), (20.45, 10.9), (23.15, 10.9), (23.15, 13.0), (20.45, 13.0),
               (20.45, 18.1), (16.9, 18.1), (16.9, 8.6), (17.6, 8.6)]   # copper pour on the back, mm
PWR_HI = {"VBUS", "VBAT", "VSYS", "VDD_4G", "CHG_SW", "CHG_PMID"}
PWR_LO = {"BUCK_SW", "BL_SW", "LCD_LEDA", "LCD_LEDK", "PA_OUTP", "PA_OUTN", "SPK_P", "SPK_N", "+2V8", "+1V2",
          "CHG_REGN", "CHG_BTST", "SIM_VDD", "LCD_VCI", "CAMF_IOVDD", "CAMF_DVDD"}


def net_rules(name):
    """widths to try (mm), via (diameter, drill) or None, layer costs (L1, L3, L4, L6; 0 = not allowed), via cost."""
    s4 = 1 if L4_SIGNALS else 0     # signals on L4 only when STK-6 has to be relaxed
    if name in RF:
        return dict(widths=[RF_W], via=None, lcost=(0, 0, 0, 1), viacost=0)
    if name == "+3V3":      # a plane on L4: every pad gets a short stub and a via (capacitors first, DEC-2)
        return dict(widths=[0.3, 0.2, 0.15], via=(0.45, 0.2), lcost=(1, 0, 0, 1), viacost=0)
    if name in PLANES:
        return dict(widths=[0.25, 0.15], via=(0.45, 0.2), lcost=(1, 0, 0, 1), viacost=0)
    if name in USB:
        return dict(widths=[PAIR_W, 0.15], via=(0.45, 0.2), lcost=(1, 2, 3 * s4, 1), viacost=500)
    if name == "VBUS":      # PWR-9: 1.0 mm
        return dict(widths=[1.0, 0.8, 0.6], via=(0.6, 0.3), lcost=(1, 0, 0, 1), viacost=600)
    if name in PWR_HI:      # PWR-1: high current stays on the outer layers (1 oz copper)
        return dict(widths=[0.6, 0.4, 0.25, 0.15], via=(0.6, 0.3), lcost=(1, 0, 0, 1), viacost=600)
    if name in PWR_LO:
        return dict(widths=[0.3, 0.2, 0.15], via=(0.5, 0.25), lcost=(1, 4, 3 * s4, 1), viacost=500)
    return dict(widths=[0.15], via=(0.45, 0.2), lcost=(2, 1, s4, 2), viacost=700)


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
    lib.rt_set_dirs.argtypes = [ctypes.POINTER(i)]
    lib.rt_cnt_seg.argtypes = [i, d, d, d, d, d, i]
    lib.rt_cnt_via.argtypes = [d, d, d, d, i]
    lib.rt_erase_seg.argtypes = [i, d, d, d, d, d, i]
    lib.rt_erase_rect.argtypes = [i, d, d, d, d, d, i]
    lib.rt_conflict_seg.argtypes = [i, d, d, d, d, d, i]
    lib.rt_conflict_via.argtypes = [d, d, d, i]
    lib.rt_route_neg.argtypes = [i, i, ctypes.POINTER(i), i, i, ctypes.POINTER(i), i, ctypes.POINTER(i), i,
                                 ctypes.POINTER(ctypes.c_int32), i, ctypes.POINTER(i)]
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
        self.lib.rt_set_dirs((ctypes.c_int * NL)(*LAYER_DIRS))
        self.net_id, self.net_name = {}, {}
        self.comps = {}            # net id -> list of component ids (one per pad)
        self.pads = []             # (net id, layers, rect mm, is_pth, comp id)
        self.tracks = []           # (net id, layer index, x0, y0, x1, y1, width)
        self.vias = []             # (net id, x, y, diameter, drill)
        self.failed = []
        self.critical = set()      # tracks and vias of the nets routed by rule: exported locked
        self.pid, self.cur_pid, self.next_pid = {}, None, 1   # track / via tuple -> id of the path it was laid in
        self.comp_of = {}          # track / via tuple -> component id (refreshed by build_maps)
        self.neg = False           # negotiated routing in progress: new copper is counted, it does not block
        self.cur_items = None      # where add_track / add_via note what they laid while negotiating
        self.mov = {}              # net id -> [("t", track) | ("v", via)] of the nets being negotiated
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
        # KiCad writes footprints and pads in the order of their (random) ids: sort them, so that the same
        # placement always gives the same routing
        ref_key = lambda fp: ("".join(c for c in fp.GetReference() if not c.isdigit()),
                              int("".join(c for c in fp.GetReference() if c.isdigit()) or 0))
        pad_key = lambda pad: (pad.GetNumber(), pad.GetPosition().x, pad.GetPosition().y)
        for fp in sorted(self.board.GetFootprints(), key=ref_key):
            for pad in sorted(fp.Pads(), key=pad_key):
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
            else:
                lib.rt_paint_rect(l, x0, y0, x1, y1, grow / G, p["net"], 0, 0)
        self.paint_pad_copper(p, comp)
        # no via centre inside or right next to a pad
        lib.rt_viablock_rect(x0, y0, x1, y1, (0.40 if p["pth"] else 0.20) / G)

    def paint_pad_copper(self, p, comp):
        """The core of a pad as copper of component `comp`: where a track of its net may start or end."""
        lib = self.lib
        x0, y0, x1, y1 = [v / G for v in p["rect"]]
        w, h = x1 - x0, y1 - y0
        shrink = 0.35 * min(w, h)
        for l in p["layers"]:
            if p["round"]:
                cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, w / 2
                lib.rt_paint_seg(l, cx, cy, cx, cy, max(0.6, r * 0.5), p["net"], 1, comp)
            else:
                lib.rt_paint_rect(l, x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink, 0.3, p["net"], 1, comp)

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
        sig = [p["rect"] for p in self.pads if p["ref"] == RF_SOCKET and self.net_name[p["net"]] in RF]
        if sig and "GND" in self.net_id:                       # In3 under the socket's opening is ground (RF-4)
            gnd_pads = [p["rect"] for p in self.pads if self.net_name[p["net"]] == "GND" and L6 in p["layers"]]
            x0, y0, x1, y1 = [v / G for v in rf_window(sig[0], gnd_pads)[1]]
            lib.rt_paint_rect(L4, x0, y0, x1, y1, (W_DEF / 2 + MARGIN) / G, self.net_id["GND"], 0, 0)
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
        self.paint_rf_moat()
        lib.rt_set_fixed(0)

    def paint_rf_moat(self):
        """Around the finished antenna line only ground may run on the back (RF-9)."""
        lib = self.lib
        gnd = self.net_id.get("GND")
        if gnd is None:
            return
        lib.rt_set_fixed(1)
        routed = False
        for net, l, x0, y0, x1, y1, w in self.tracks:
            if self.net_name[net] in RF:
                routed = True
                lib.rt_paint_seg(l, x0 / G, y0 / G, x1 / G, y1 / G, (w / 2 + RF_KEEP + W_DEF / 2 + MARGIN) / G, gnd, 0, 0)
        if routed:                                   # the matching parts and the socket pad are part of the line
            for p in self.pads:
                if self.net_name[p["net"]] in RF and not p["ref"].startswith("U"):
                    x0, y0, x1, y1 = [v / G for v in p["rect"]]
                    for l in p["layers"]:
                        lib.rt_paint_rect(l, x0, y0, x1, y1, (RF_KEEP + W_DEF / 2 + MARGIN) / G, gnd, 0, 0)
        lib.rt_set_fixed(0)

    def remove_net(self, net):
        self.tracks = [t for t in self.tracks if t[0] != net]
        self.vias = [v for v in self.vias if v[0] != net]

    def remove_paths(self, pids):
        self.tracks = [t for t in self.tracks if self.pid.get(t) not in pids]
        self.vias = [v for v in self.vias if self.pid.get(v) not in pids]

    def drop_orphans(self, nets):
        """After paths were taken out: remove copper of these nets that no longer reaches any pad."""
        lib = self.lib
        roots = {}
        for p in self.pads:
            if p["net"] in nets:
                roots.setdefault(p["net"], set()).add(lib.rt_find(p["comp"]))
        keep = lambda item: item[0] not in nets or lib.rt_find(self.comp_of[item]) in roots.get(item[0], ())
        n = len(self.tracks) + len(self.vias)
        self.tracks = [t for t in self.tracks if keep(t)]
        self.vias = [v for v in self.vias if keep(v)]
        return n - len(self.tracks) - len(self.vias)

    def count_open(self):
        """Connections still missing, counted from the pads."""
        lib = self.lib
        groups = {}
        for p in self.pads:
            groups.setdefault(p["net"], set()).add(lib.rt_find(p["comp"]))
        n = 0
        for net, g in groups.items():
            if self.net_name[net] in PLANES:
                n += sum(1 for r in g if not lib.rt_plane(r))
            else:
                n += len(g) - 1
        return n

    def conflicts(self, net, cells, width, rules):
        """Tracks and vias of other nets that are too close to a path found in rip-up mode,
        as a set of (net, path id); the id is None for copper that was not laid by commit()."""
        via_pts, runs = [], []
        run_start = last = cells[0]
        direction = None
        for c in cells[1:]:
            if c[0] != last[0]:
                via_pts.append((last[2] * G, last[1] * G))
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
        for t in self.tracks:
            onet, l, x0, y0, x1, y1, w = t
            if onet == net:
                continue
            need = w / 2 + width / 2 + CLR + MARGIN
            if any(rl == l and seg_seg(a0, b0, a1, b1, x0, y0, x1, y1) < need for rl, a0, b0, a1, b1 in runs) or \
                    any(pt_seg(vx, vy, x0, y0, x1, y1) < w / 2 + via[0] / 2 + CLR + MARGIN for vx, vy in via_pts):
                hit.add((onet, self.pid.get(t)))
        for v in self.vias:
            onet, x, y, dia, drill = v
            if onet == net:
                continue
            if any(pt_seg(x, y, a0, b0, a1, b1) < dia / 2 + width / 2 + CLR + MARGIN for rl, a0, b0, a1, b1 in runs) or \
                    any(math.hypot(vx - x, vy - y) < max(dia / 2 + via[0] / 2 + CLR, drill / 2 + via[1] / 2 + HOLE_CLR) + MARGIN
                        for vx, vy in via_pts):
                hit.add((onet, self.pid.get(v)))
        return hit

    def add_track(self, net, l, x0, y0, x1, y1, width, comp):
        lib = self.lib
        if comp is None:
            comp = lib.rt_new_comp(0)
            self.comps.setdefault(net, []).append(comp)
        a = (x0 / G, y0 / G, x1 / G, y1 / G)
        if self.neg:                 # copper only; neg_route counts the net's space in once the net is done
            lib.rt_paint_seg(l, *a, 0.6, net, 1, comp)
            self.cur_items.append(("t", (net, l, x0, y0, x1, y1, width)))
            return comp
        extra = RF_EXTRA if self.net_name[net] in RF else 0.0
        lib.rt_paint_seg(l, *a, (width / 2 + R0 + extra) / G, net, 0, 0)
        lib.rt_paint_seg(l, *a, 0.6, net, 1, comp)
        t = (net, l, x0, y0, x1, y1, width)
        self.tracks.append(t)
        self.comp_of[t] = comp
        if self.cur_pid is not None:
            self.pid[t] = self.cur_pid
        return comp

    def add_via(self, net, x, y, dia, drill, comp):
        lib = self.lib
        if comp is None:
            comp = lib.rt_new_comp(1 if self.net_name[net] in PLANES else 0)
            self.comps.setdefault(net, []).append(comp)
        cx, cy = x / G, y / G
        if self.neg:
            for l in range(NL):
                lib.rt_paint_seg(l, cx, cy, cx, cy, 0.6, net, 1, comp)
            self.cur_items.append(("v", (net, x, y, dia, drill)))
            return comp
        for l in range(NL):
            lib.rt_paint_seg(l, cx, cy, cx, cy, (dia / 2 + R0) / G, net, 0, 0)
            lib.rt_paint_seg(l, cx, cy, cx, cy, 0.6, net, 1, comp)
        lib.rt_viablock_rect(cx, cy, cx, cy, (drill / 2 + HOLE_CLR + 0.15 + MARGIN) / G)
        v = (net, x, y, dia, drill)
        self.vias.append(v)
        self.comp_of[v] = comp
        if self.cur_pid is not None:
            self.pid[v] = self.cur_pid
        return comp

    # ---- nets that need more than "connect the pads" -------------------------------------------
    def pad(self, ref, net_name):
        net = self.net_id[net_name]
        return next(p for p in self.pads if p["ref"] == ref and p["net"] == net)

    def preroute_decoupling(self):
        """ESP32 supply: via -> 22 uF -> 100 nF -> pin 2, so the current passes the capacitors first."""
        net = self.net_id["+3V3"]
        rules = dict(widths=[0.4, 0.25], via=(0.45, 0.2), lcost=(0, 0, 0, 1), viacost=0)
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

    def local_first(self, names, reach=6.0):
        """Short connections before long ones: for the given nets, join every pair of pads that are close
        together (the short edges of each net's spanning tree), shortest first across all nets, so that a
        pad is not walled in by long tracks before its own short connection is made."""
        lib = self.lib
        edges = []
        for name in names:
            net = self.net_id.get(name)
            pads = [p for p in self.pads if p["net"] == net]
            if len(pads) < 2:
                continue
            todo, tree = pads[1:], [pads[0]]
            while todo:                                   # Prim: always add the pad closest to the tree
                d, a, b = min(((rect_gap(t["rect"], q["rect"]), t, q) for t in tree for q in todo), key=lambda e: e[0])
                todo.remove(b)
                tree.append(b)
                if d <= reach:
                    edges.append((d, name, a, b))
        made = 0
        for d, name, a, b in sorted(edges, key=lambda e: e[0]):
            if lib.rt_find(a["comp"]) == lib.rt_find(b["comp"]):
                continue
            net = self.net_id[name]
            rules = net_rules(name)
            box = (min(a["rect"][0], b["rect"][0]), min(a["rect"][1], b["rect"][1]),
                   max(a["rect"][2], b["rect"][2]), max(a["rect"][3], b["rect"][3]))
            for width in rules["widths"]:
                res = self.search(net, lib.rt_find(a["comp"]), rules, width, False, box, 1.5)
                if res:
                    self.commit(net, lib.rt_find(a["comp"]), res[0], res[1], rules, width, False)
                    made += 1
                    break
        return made, len(edges)

    def decouple_first(self, name):
        """DEC-2 for a plane net: every capacitor gets its via first; a supply pin with a capacitor of the same
        net close by is then joined to that capacitor by a track instead of getting a via of its own."""
        lib = self.lib
        net = self.net_id.get(name)
        if net is None:
            return 0
        rules = net_rules(name)
        pads = [p for p in self.pads if p["net"] == net and not p["pth"]]
        caps = [p for p in pads if p["ref"].startswith("C")]
        for p in caps:
            if lib.rt_plane(p["comp"]):
                continue
            for width in rules["widths"]:
                res = self.search(net, p["comp"], rules, width, True, p["rect"], 3.0)
                if res:
                    self.commit(net, p["comp"], res[0], res[1], rules, width, True)
                    break
        joined = 0
        for p in pads:
            if p["ref"][0] in "CRLDQF" or p["ref"].startswith("TP") or lib.rt_plane(p["comp"]):
                continue                                  # only pins of chips, modules and connectors
            near = [c for c in caps if rect_gap(p["rect"], c["rect"]) <= 2.5]
            if not near:
                continue
            c = min(near, key=lambda q: rect_gap(p["rect"], q["rect"]))
            box = (min(p["rect"][0], c["rect"][0]), min(p["rect"][1], c["rect"][1]),
                   max(p["rect"][2], c["rect"][2]), max(p["rect"][3], c["rect"][3]))
            for width in rules["widths"]:
                res = self.search(net, p["comp"], rules, width, False, box, 1.0)
                if res:
                    self.commit(net, p["comp"], res[0], res[1], rules, width, False)
                    joined += 1
                    break
        return joined

    def stitch_rf(self):
        """RF-5: ground vias on both sides of the antenna line, about 1 mm apart, beside tracks and pads alike.
        The line is taken as straight from the module's antenna pad to the socket's signal pad."""
        lib = self.lib
        gnd = self.net_id["GND"]
        via = net_rules("GND")["via"]
        nvp, vprobe = disc_offsets(via[0] / 2 - W_DEF / 2 + 0.01)
        shapes = [(min(x0, x1) - w / 2, min(y0, y1) - w / 2, max(x0, x1) + w / 2, max(y0, y1) + w / 2)
                  for net, l, x0, y0, x1, y1, w in self.tracks if self.net_name[net] in RF]
        rf_pads = [p for p in self.pads if self.net_name[p["net"]] in RF]
        shapes += [p["rect"] for p in rf_pads]
        sock = [p for p in rf_pads if p["ref"] == RF_SOCKET]
        far = [p for p in rf_pads if p["ref"].startswith("U")]
        if not sock or not far or not shapes:
            return 0
        mid = lambda r: ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        (ax, ay), (bx, by) = mid(far[0]["rect"]), mid(sock[0]["rect"])
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        nx, ny = -uy, ux
        added, placed = 0, []
        t = -0.5
        while t <= length + 0.5:
            px, py = ax + ux * t, ay + uy * t
            for side in (1, -1):
                half = 0.0                         # how far the line's copper reaches sideways at this point
                for x0, y0, x1, y1 in shapes:
                    cs = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                    along = [(cx - ax) * ux + (cy - ay) * uy for cx, cy in cs]
                    if min(along) - 0.3 <= t <= max(along) + 0.3:
                        half = max(half, max(side * ((cx - px) * nx + (cy - py) * ny) for cx, cy in cs))
                for extra in (0.1, 0.25, 0.4, 0.6, 0.9):
                    off = half + RF_GAP + via[0] / 2 + extra
                    x, y = px + side * nx * off, py + side * ny * off
                    ix, iy = round(x / G), round(y / G)
                    if not (0 <= ix < GW and 0 <= iy < GH) or not lib.rt_via_ok(gnd, ix, iy, nvp, vprobe):
                        continue
                    if any(math.hypot(ix * G - qx, iy * G - qy) < 0.9 for qx, qy in placed):
                        break
                    self.add_via(gnd, ix * G, iy * G, via[0], via[1], None)
                    placed.append((ix * G, iy * G))
                    added += 1
                    break
            t += 1.0
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
        self.cur_pid, self.next_pid = self.next_pid, self.next_pid + 1

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
        self.cur_pid = None

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

    # ---- negotiated routing ------------------------------------------------------------------
    # All nets that are not fixed are routed together. A track may run through the space another net's
    # track needs, but pays for it; the price rises every round and cells that stay contested get a
    # lasting extra cost, so the nets sort out among themselves who goes where. A round in which no net is
    # in another's way ends it: the result then obeys the same clearances as the strict router.
    def search_neg(self, net, src, rules, width, box, margin, pf):
        """Returns (cells, how much of the path lies in another net's way), or None when there is no way."""
        lib = self.lib
        if box is None:
            lib.rt_window(0, 0, GW - 1, GH - 1)
        else:
            lib.rt_window(int((box[0] - margin) / G), int((box[1] - margin) / G),
                          int((box[2] + margin) / G) + 1, int((box[3] + margin) / G) + 1)
        np_, probe = disc_offsets(width / 2 - W_DEF / 2)
        via = rules["via"]
        nvp, vprobe = disc_offsets((via[0] / 2 if via else 0.3) - W_DEF / 2 + 0.01)
        lcost = (ctypes.c_int * NL)(*rules["lcost"])
        conf = ctypes.c_int(0)
        n = lib.rt_route_neg(net, src, lcost, rules["viacost"] if via else 0, np_, probe, nvp, vprobe, pf,
                             self.outbuf, len(self.outbuf), ctypes.byref(conf))
        if n == 0:
            return None
        return [(s // (GW * GH), (s % (GW * GH)) // GW, s % GW) for s in reversed(self.outbuf[:n])], conf.value

    def neg_route(self, net, pf, margin):
        """Make the connections a net still lacks. Returns the new paths (one list of tracks and vias per
        connection) and how many connections found no way. Each connection takes the widest track that
        has a free way; where none has, the one least in the way of other nets. A wider search area is
        tried before settling for a way that is not free."""
        lib = self.lib
        rules = net_rules(self.net_name[net])
        paths = []
        bad = set()
        while True:
            roots = sorted({lib.rt_find(c) for c in self.comps[net]})
            todo = [r for r in roots if r not in bad] if len(roots) > 1 else []
            if not todo:
                break
            src = todo[0]
            best = None
            for width in rules["widths"]:
                for box, m in ((self.net_box[net], margin), (None, None)):
                    res = self.search_neg(net, src, rules, width, box, m, pf)
                    if res and (best is None or res[1] < best[1]):
                        best = (res[0], res[1], width)
                    if res and res[1] == 0:
                        break
                if best and best[1] == 0:
                    break
            if best:
                self.cur_items = []
                self.commit(net, src, best[0], 0, rules, best[2], False)
                paths.append(self.cur_items)
                self.cur_items = None
                bad = {lib.rt_find(b) for b in bad}
            else:
                bad.add(src)
        return paths, len({lib.rt_find(c) for c in self.comps[net]}) - 1

    def neg_count(self, items, delta):
        """Add (or take away) the space these tracks and vias need from the count the other nets see."""
        lib = self.lib
        for kind, it in items:
            if kind == "t":
                _, l, x0, y0, x1, y1, w = it
                lib.rt_cnt_seg(l, x0 / G, y0 / G, x1 / G, y1 / G, (w / 2 + R0) / G, delta)
            else:                                 # the same hole spacing for every via, whatever its drill:
                _, x, y, dia, drill = it          # two vias must agree on whether they are too close
                lib.rt_cnt_via(x / G, y / G, (dia / 2 + R0) / G, (0.15 + HOLE_CLR + 0.15 + MARGIN) / G, delta)

    def neg_lift(self, net, items):
        """Take a net's tracks and vias out of the maps; its pads stand alone again."""
        lib = self.lib
        self.neg_count(items, -1)
        for kind, it in items:
            if kind == "t":
                _, l, x0, y0, x1, y1, w = it
                lib.rt_erase_seg(l, x0 / G, y0 / G, x1 / G, y1 / G, 1.2, net)
            else:
                _, x, y, dia, drill = it
                for l in range(NL):
                    lib.rt_erase_seg(l, x / G, y / G, x / G, y / G, 1.2, net)
        # the pads' copper has to go too: components cannot be split again, and painting a pad over its
        # old copper would join it to the component the whole net was in
        self.comps[net] = []
        for p in self.pads_of[net]:
            x0, y0, x1, y1 = [v / G for v in p["rect"]]
            for l in p["layers"]:
                lib.rt_erase_rect(l, x0, y0, x1, y1, 1.0, net)
        for p in self.pads_of[net]:
            p["comp"] = lib.rt_new_comp(0)
            self.comps[net].append(p["comp"])
            self.paint_pad_copper(p, p["comp"])

    def neg_copper(self, net, items):
        """Put tracks and vias back as copper of their net (not yet counted as space taken)."""
        lib = self.lib
        for kind, it in items:
            comp = lib.rt_new_comp(0)
            self.comps[net].append(comp)
            if kind == "t":
                _, l, x0, y0, x1, y1, w = it
                lib.rt_paint_seg(l, x0 / G, y0 / G, x1 / G, y1 / G, 0.6, net, 1, comp)
            else:
                _, x, y, dia, drill = it
                for l in range(NL):
                    lib.rt_paint_seg(l, x / G, y / G, x / G, y / G, 0.6, net, 1, comp)

    def neg_conflicts(self, items, add):
        """Cells of these tracks and vias that lie in another net's way (call while the net is lifted).
        The radii are the exact ones, without the half cell the search adds to be on the safe side: with the
        rounded-up radius a via would count as being in the way of a track that was laid next to it at a
        distance the track's own check allows, and the two would be taken out and laid again for ever."""
        lib = self.lib
        n = 0
        for kind, it in items:
            if kind == "t":
                _, l, x0, y0, x1, y1, w = it
                r = max(0.5, (w / 2 - W_DEF / 2) / G)
                n += lib.rt_conflict_seg(l, x0 / G, y0 / G, x1 / G, y1 / G, r, add)
            else:
                _, x, y, dia, drill = it
                n += lib.rt_conflict_via(x / G, y / G, (dia / 2 - W_DEF / 2) / G, add)
        return n

    def negotiate(self, names, max_iter=80, pf=400, grow=1.3, pf_max=4000):
        """Route the named nets together (see above). Everything already in the maps must be fixed copper.
        From the second round on, only the connections that are in another net's way are taken out and
        laid again; the rest of the net stays where it is."""
        lib = self.lib
        nets = [self.net_id[n] for n in names]
        self.pads_of = {}
        for p in self.pads:
            self.pads_of.setdefault(p["net"], []).append(p)
        self.mov = {n: [] for n in nets}                 # net -> list of paths, a path = list of items
        missing = {n: 0 for n in nets}
        self.neg = True
        lib.rt_clear_hist()
        for it in range(1, max_iter + 1):
            t0 = time.time()
            dirty = cells = relaid = 0
            margin = 6.0 if it <= 3 else 12.0
            for net in nets:
                keep = self.mov[net]
                if it > 1:
                    self.neg_lift(net, [i for p in keep for i in p])
                    bad = [self.neg_conflicts(p, pf // 4) for p in keep]      # contested cells get dearer for good
                    keep = [p for p, n in zip(keep, bad) if not n]
                    flat = [i for p in keep for i in p]
                    self.neg_copper(net, flat)
                    if not any(bad) and not (missing[net] and it % 5 == 0):
                        self.neg_count(flat, 1)
                        continue
                    if any(bad):
                        dirty += 1
                        cells += sum(bad)
                        relaid += sum(1 for n in bad if n)
                new, missing[net] = self.neg_route(net, pf, margin)
                self.mov[net] = keep + new
                self.neg_count([i for p in self.mov[net] for i in p], 1)
            print(f"  round {it}: {dirty} nets were in another's way ({relaid} connections, {cells} cells), "
                  f"{sum(missing.values())} connections with no way at all, price x{pf / 8:.0f}, "
                  f"{time.time() - t0:.0f} s", flush=True)
            if it > 1 and dirty == 0:
                break
            pf = min(int(pf * grow), pf_max)
        return it

    def neg_finish(self, names):
        """Back to strict maps. Connections that are still in another net's way are taken out, worst first."""
        nets = [self.net_id[n] for n in names]
        dropped = 0
        while True:
            worst = (0, None, None)
            for net in nets:
                paths = self.mov[net]
                flat = [i for p in paths for i in p]
                if not flat:
                    continue
                self.neg_lift(net, flat)
                for k, p in enumerate(paths):
                    n = self.neg_conflicts(p, 0)
                    if n > worst[0]:
                        worst = (n, net, k)
                self.neg_copper(net, flat)
                self.neg_count(flat, 1)
            if worst[1] is None:
                break
            net, k = worst[1], worst[2]
            flat = [i for p in self.mov[net] for i in p]
            self.neg_lift(net, flat)
            del self.mov[net][k]
            flat = [i for p in self.mov[net] for i in p]
            self.neg_copper(net, flat)
            self.neg_count(flat, 1)
            dropped += 1
        self.neg = False
        for net in nets:
            for p in self.mov[net]:
                for kind, it in p:
                    (self.tracks if kind == "t" else self.vias).append(it)
        self.mov = {}
        self.build_maps()
        return dropped

    def open_nets(self):
        """(net name, connections missing) for every net that is not complete, counted from the pads."""
        lib = self.lib
        groups = {}
        for p in self.pads:
            groups.setdefault(p["net"], set()).add(lib.rt_find(p["comp"]))
        out = []
        for net, g in sorted(groups.items()):
            name = self.net_name[net]
            miss = sum(1 for r in g if not lib.rt_plane(r)) if name in PLANES else len(g) - 1
            if miss:
                out.append((name, miss))
        return out

    def rip_up(self, limit=1500, pen=40, budget=600.0):
        """Rip-up and reroute: let a failed net push through other nets' tracks, take out only the paths
        that are in the way, route the failed net, then reconnect the nets that lost a path.
        The best state seen is the one that is kept."""
        lib = self.lib
        queue = []
        for name, _ in self.failed:
            if name not in queue:
                queue.append(name)
        ripped = {}
        self.walled = 0
        frozen = {self.net_id[n] for n in RF | USB | PWR_HI | set(PLANES) if n in self.net_id}   # never pushed out
        best = (self.count_open(), list(self.tracks), list(self.vias))
        rounds, stale = 0, 0
        t0 = time.time()
        while queue and rounds < limit and time.time() - t0 < budget and stale < 250:
            name = queue.pop(0)
            net = self.net_id[name]
            if not self.route_net(name, record=False) or name in PLANES:
                continue
            rules = net_rules(name)
            width = rules["widths"][-1]
            hits = set()
            for src in sorted({lib.rt_find(c) for c in self.comps[net]}):
                res = self.search(net, src, rules, width, False, None, None, rip_pen=pen)
                if res:
                    hits = {h for h in self.conflicts(net, res[0], width, rules) if h[0] not in frozen}
                    if hits:
                        break
            if not hits:
                self.walled += 1                 # no way through even when other nets' tracks may be pushed out
                continue
            rounds += 1
            stale += 1
            victims = {v for v, _ in hits}
            for v in {v for v, pid in hits if pid is None}:
                self.remove_net(v)
            self.remove_paths({pid for _, pid in hits if pid is not None})
            for v in victims:
                ripped[v] = ripped.get(v, 0) + 1
                if ripped[v] >= 8:
                    frozen.add(v)
            self.build_maps(frozen)
            if self.drop_orphans(victims):
                self.build_maps(frozen)
            if self.route_net(name, record=False):
                queue.append(name)
            for v in victims:                    # reconnect what was taken out, before anything else
                if self.route_net(self.net_name[v], record=False) and self.net_name[v] not in queue:
                    queue.append(self.net_name[v])
            now = self.count_open()
            if now < best[0]:
                best = (now, list(self.tracks), list(self.vias))
                stale = 0
            if rounds % 25 == 0:
                print(f"  rip-up round {rounds}: {now} open (best {best[0]}), {len(queue)} queued, "
                      f"{time.time() - t0:.0f} s", flush=True)
        self.tracks, self.vias = best[1], best[2]
        self.build_maps()
        self.failed = []
        for net in sorted(self.comps):
            name = self.net_name[net]
            groups = {lib.rt_find(p["comp"]) for p in self.pads if p["net"] == net}
            miss = sum(1 for g in groups if not lib.rt_plane(g)) if name in PLANES else len(groups) - 1
            if miss:
                self.failed.append((name, miss))
        return rounds

    def trim_tails(self):
        """Tidy up after routing: cut back track ends that stick out past the point where the track is
        joined, remove tracks that end in the air, and remove vias that no longer join two layers."""
        changed = 0
        for _ in range(80):
            again = False
            by = {}
            for t in self.tracks:
                by.setdefault((t[0], t[1]), []).append(t)
            vias_of, pads_of = {}, {}
            for v in self.vias:
                vias_of.setdefault(v[0], []).append(v)
            for p in self.pads:
                pads_of.setdefault(p["net"], []).append(p)
            for i, t in enumerate(self.tracks):
                net, l, x0, y0, x1, y1, w = t
                same = [o for o in by[(net, l)] if o is not t]
                vias = vias_of.get(net, [])
                pads = [p for p in pads_of.get(net, []) if l in p["layers"]]

                def held(x, y, ox, oy):
                    # a track that also covers this track's other end does not hold this end: the piece between
                    # the two ends lies inside that track's copper and leads nowhere
                    return (any(pt_seg(x, y, o[2], o[3], o[4], o[5]) <= o[6] / 2 < pt_seg(ox, oy, o[2], o[3], o[4], o[5])
                                for o in same)
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
                free0, free1 = not held(x0, y0, x1, y1), not held(x1, y1, x0, y0)
                if free0 and joints:
                    a = min(joints)
                if free1 and joints:
                    b = max(joints)
                plane = self.net_name[net] in PLANES
                if (free0 or free1) and not joints and not plane:
                    a = b = 0.0                    # hangs on nothing at all
                if (a, b) == (0.0, 1.0):
                    continue
                if b - a <= 1e-9:                  # nothing but a tail: one end joined, the other in the air
                    if plane:
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
            keep = []
            for v in self.vias:                    # a via must join copper on two layers
                net, x, y, dia, drill = v
                if self.net_name[net] in PLANES:
                    keep.append(v)
                    continue
                layers = {t[1] for t in self.tracks if t[0] == net and
                          (math.hypot(t[2] - x, t[3] - y) <= dia / 2 or math.hypot(t[4] - x, t[5] - y) <= dia / 2)}
                for p in pads_of.get(net, []):
                    if p["rect"][0] <= x <= p["rect"][2] and p["rect"][1] <= y <= p["rect"][3]:
                        layers |= set(p["layers"])
                if len(layers) >= 2:
                    keep.append(v)
                else:
                    self.critical.discard(v)
                    changed += 1
                    again = True
            self.vias = keep
            if not again:
                break
        return changed

    def diagnose(self):
        """For every connection that is still open: is the pad group shut in by fixed things (pads, locked
        tracks, plane vias), or only by other nets' tracks that a better router could move?"""
        lib = self.lib
        out = []
        for name, _ in self.failed:
            net = self.net_id[name]
            rules = net_rules(name)
            groups = {}
            for p in self.pads:
                if p["net"] == net:
                    groups.setdefault(lib.rt_find(p["comp"]), []).append(p)
            if name in PLANES:
                open_groups = [g for g in groups if not lib.rt_plane(g)]
            else:
                open_groups = sorted(groups, key=lambda g: len(groups[g]))[:-1]
            for g in open_groups:
                res = self.search(net, g, rules, rules["widths"][-1], name in PLANES, None, None, rip_pen=40)
                p = groups[g][0]
                out.append(dict(net=name, pads=[f'{q["ref"]}.{q["num"]}' for q in groups[g]],
                                x=round((p["rect"][0] + p["rect"][2]) / 2, 2), y=round((p["rect"][1] + p["rect"][3]) / 2, 2),
                                side="F" if L1 in p["layers"] and L6 not in p["layers"] else "B" if L6 in p["layers"] and L1 not in p["layers"] else "FB",
                                walled=res is None))
        return out

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


def rect_gap(a, b):
    return math.hypot(max(a[0] - b[2], b[0] - a[2], 0), max(a[1] - b[3], b[1] - a[3], 0))


def rf_window(sig, gnd_pads):
    """Opening in In4 under the antenna socket's signal pad, and the In3 ground below it (RF-3, RF-4).
    sig: rectangle of the signal pad; gnd_pads: rectangles of the ground pads on the same side.
    The opening is the pad grown by RF_WIN, pulled back where it would come closer than RF_WIN_GND to a
    ground pad (those pads need the In4 ground under them)."""
    x0, y0, x1, y1 = sig[0] - RF_WIN, sig[1] - RF_WIN, sig[2] + RF_WIN, sig[3] + RF_WIN
    for gx0, gy0, gx1, gy1 in gnd_pads:
        gx0, gy0, gx1, gy1 = gx0 - RF_WIN_GND, gy0 - RF_WIN_GND, gx1 + RF_WIN_GND, gy1 + RF_WIN_GND
        if gx1 <= x0 or gx0 >= x1 or gy1 <= y0 or gy0 >= y1:
            continue
        cuts = [(gx1 - x0, "l"), (x1 - gx0, "r"), (gy1 - y0, "t"), (y1 - gy0, "b")]   # how much each side must give
        cuts = [(d, side) for d, side in cuts if d > 0]
        d, side = min(cuts)
        if side == "l":
            x0 = gx1
        elif side == "r":
            x1 = gx0
        elif side == "t":
            y0 = gy1
        else:
            y1 = gy0
    return (x0, y0, x1, y1), (x0 - RF_ISLAND, y0 - RF_ISLAND, x1 + RF_ISLAND, y1 + RF_ISLAND)


def rule_area(board, layer, pts, name, no_tracks=False, no_pour=False):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetLayer(layer)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(no_tracks)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowCopperPour(no_pour)
    z.SetDoNotAllowFootprints(False)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in pts:
        outline.Append(vec(x, y))
    board.Add(z)


def add_rf_ground(board):
    """RF-3, RF-4: In4 stays whole except for an opening under the antenna socket's signal pad; In3 below
    the opening is ground and carries no tracks."""
    def rect(pad):
        bb = pad.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)

    sig, gnd = None, []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if fp.GetReference() == RF_SOCKET and pad.GetNetname() in RF:
                sig = rect(pad)
            elif pad.GetNetname() == "GND" and pad.IsOnLayer(pcbnew.B_Cu):
                gnd.append(rect(pad))
    if sig is None:
        return None
    (wx0, wy0, wx1, wy1), (ix0, iy0, ix1, iy1) = rf_window(sig, gnd)
    island = [(ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)]
    add_pour(board, "GND", pcbnew.In3_Cu, island, priority=2)
    rule_area(board, pcbnew.In3_Cu, island, "antenna socket: In3 is ground here, no tracks", no_tracks=True)
    rule_area(board, pcbnew.In4_Cu, [(wx0, wy0), (wx1, wy0), (wx1, wy1), (wx0, wy1)],
              "antenna socket: In4 opened under the signal pad", no_pour=True)
    return (wx0, wy0, wx1, wy1), (ix0, iy0, ix1, iy1)


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


def add_zone(board, net, layer, priority=0, hole=None):
    """A pour over the whole board; hole = (x0, y0, x1, y1) leaves a rectangle out of it."""
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    outline = z.Outline()
    outline.NewOutline()
    for x, y in ((-1, -1), (BOARD_W + 1, -1), (BOARD_W + 1, BOARD_H + 1), (-1, BOARD_H + 1)):
        outline.Append(vec(x, y))
    if hole:
        h = outline.NewHole()
        for x, y in ((hole[0], hole[1]), (hole[0], hole[3]), (hole[2], hole[3]), (hole[2], hole[1])):
            outline.Append(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y), 0, h)
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
    r.paint_rf_moat()
    for pname, nname, layer in COUPLED:                       # long USB pair side by side
        ok = r.route_pair(pname, nname, layer)
        print(f"pair {pname} / {nname}: {'laid side by side' if ok else 'no room for a coupled run'}", flush=True)
    for name in sorted((n for n in multi if n in USB), key=size.get):
        r.route_net(name)
    r.critical = set(r.tracks) | set(r.vias)                  # everything so far is locked in the board file
    if NEGOTIATE:
        # fixed first: supply and planes; then every other net together, by negotiation
        for name in sorted((n for n in multi if n in PWR_HI), key=size.get) + ["GND"]:
            r.route_net(name)
        print(f"+3V3: {r.decouple_first('+3V3')} supply pins joined to their capacitor instead of a via", flush=True)
        r.route_net("+3V3")
        movable = (sorted((n for n in multi if n in PWR_LO), key=size.get)   # the wider supply tracks first
                   + sorted((n for n in multi if n not in special), key=size.get))
        print(f"fixed nets laid, {sum(m for _, m in r.failed)} of their connections open, {time.time() - t0:.0f} s; "
              f"negotiating the other {len(movable)} nets", flush=True)
        r.build_maps(frozen=set(r.net_name))                  # everything laid so far is fixed from here on
        rounds = r.negotiate(movable)
        dropped = r.neg_finish(movable)
        print(f"negotiation: {rounds} rounds, {dropped} connections taken out because they were still in "
              f"another's way", flush=True)
        for name, _ in r.open_nets():                         # what is open gets one more try, strictly
            r.route_net(name, record=False)
        r.failed = r.open_nets()
    else:
        for name in sorted((n for n in multi if n in PWR_HI), key=size.get):
            r.route_net(name)
        made, short = r.local_first([n for n in multi if n not in RF | USB | PWR_HI | set(PLANES)])
        print(f"short connections first: {made} of {short} made", flush=True)
        for name in sorted((n for n in multi if n in PWR_LO), key=size.get) + ["GND"]:
            r.route_net(name)
        print(f"+3V3: {r.decouple_first('+3V3')} supply pins joined to their capacitor instead of a via", flush=True)
        order = ["+3V3"] + sorted((n for n in multi if n not in special), key=size.get)
        for k, name in enumerate(order):
            t1 = time.time()
            miss = r.route_net(name)
            if time.time() - t1 > 8:
                print(f"  [{k + 1}/{len(order)}] {name}: {miss} missing, {time.time() - t1:.1f} s", flush=True)
        first = sum(m for _, m in r.failed)
        print(f"first pass: {total - first} of {total} connections, {time.time() - t0:.0f} s", flush=True)
        rounds = r.rip_up()
        print(f"rip-up: {rounds} rounds; {r.walled} attempts found no way through even with other tracks pushed "
              f"aside", flush=True)
    missing = sum(m for _, m in r.failed)
    print(f"trimmed {r.trim_tails()} track ends", flush=True)
    length = sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in r.tracks)
    print(f"routing: {total - missing} of {total} connections, {len(r.tracks)} segments, {len(r.vias)} vias, "
          f"{length:.0f} mm of track, {time.time() - t0:.0f} s")
    for name, m in r.failed:
        print(f"  NOT ROUTED {name}: {m}")
    diag = r.diagnose()
    print(f"open pad groups: {len(diag)}, of which {sum(1 for d in diag if d['walled'])} are shut in by fixed copper",
          flush=True)
    with open(os.path.join(OUT, "build", "open.json"), "w", encoding="utf-8") as f:
        json.dump(diag, f, ensure_ascii=False, indent=0)
    usb = []
    for pname, nname in USB_PAIRS:
        ln = {n: sum(math.hypot(t[4] - t[2], t[5] - t[3]) for t in r.tracks if r.net_name[t[0]] == n)
              for n in (pname, nname)}
        usb.append(dict(pair=f"{pname} / {nname}", p=round(ln[pname], 1), n=round(ln[nname], 1),
                        diff=round(abs(ln[pname] - ln[nname]), 1)))
        print(f"  USB {pname} {ln[pname]:.1f} mm, {nname} {ln[nname]:.1f} mm, difference {abs(ln[pname] - ln[nname]):.1f} mm")

    r.export()
    add_zone(board, "GND", pcbnew.In1_Cu)
    add_zone(board, "GND", pcbnew.In4_Cu)
    add_zone(board, "+3V3", pcbnew.In3_Cu)
    add_zone(board, "GND", pcbnew.F_Cu)
    add_zone(board, "GND", pcbnew.B_Cu)
    add_pour(board, "VDD_4G", pcbnew.B_Cu, VDD_4G_AREA)       # Air780E supply: a pour, not just a track
    win = add_rf_ground(board)
    if win:
        print("antenna socket: In4 opening %.2f x %.2f mm, In3 ground %.2f x %.2f mm"
              % (win[0][2] - win[0][0], win[0][3] - win[0][1], win[1][2] - win[1][0], win[1][3] - win[1][1]))
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    with open(os.path.join(OUT, "build", "routing.json"), "w", encoding="utf-8") as f:
        json.dump(dict(total=total, missing=missing, failed=r.failed, vias=len(r.vias), length=round(length), usb=usb,
                       l4_signals=L4_SIGNALS), f,
                  ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
