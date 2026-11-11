"""Signal connections laid by hand, for what the autorouters leave open.

    /usr/bin/python3.12 hand.py [output_dir] [--try | --kicad-decides]

Run it after finish.py. Every piece in HAND is checked against the copper that is on the board with the router's
own clearance map; a piece that does not fit is reported with the spot and what is in the way, and nothing is
written. --try only reports.

HAND is a list of (net, steps). A step is ("F" | "L3" | "B", width, [(x, y), ...]) for a track or
("via", x, y) for a 0.45 / 0.2 mm via. Coordinates as in place.py: millimetres from the board's top-left corner.

RIP is a list of (net, (x, y)) or (net, (x, y), radius). Without a radius the stretch of that net's track that
passes nearest to the point is taken out first (from one pad or junction to the next); with a radius only the
pieces of that net that lie wholly within it (vias too). Locked copper is never touched. A net that lost copper
must get it back, by a HAND entry or by AUTO.

AUTO is a list of nets that the grid router connects after the hand-laid pieces are in: for a connection that
only needed an opening, or to close what RIP opened.
"""
import json
import math
import os
import sys

import pcbnew

from board import NAME, OX, OY
import route
from route import ROUTE_LAYERS, Router, add_all_zones, pt_seg, strip_copper

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = args[0] if args else os.path.join(HERE, "..")
LAYER = {"F": 0, "L3": 1, "B": 3}

# The charger's I2C clock pin (U2.5, back) was the last open connection. Vias fit only in a strip 0.24 mm wide below
# the chip: left of it the 2 mm system-supply trunk runs on the front, right of it the VBUS track on the back, below
# it is R3. Four nets change layer here (CHG_INT, I2C_SDA, I2C_SCL, CHG_STAT); the autorouter had placed three vias
# and the clock pin was left over. The three vias in the strip now stand one above the other at the smallest pitch
# the rules allow (0.55 mm), CHG_STAT keeps its via beside them.
RIP = [
    ("CHG_INT", (6.47, 15.34), 0.52),     # the spur on L3 to the old via, and the via
    ("CHG_INT", (6.3, 14.5), 1.12),       # the track on the back from that via to pin 7
    ("I2C_SDA", (6.6, 14.2), 1.7),        # pin 6 -> via -> first stretch on L3
]

HAND = [
    ("I2C_SCL", [("B", 0.15, [(7.15, 14.12), (7.15, 14.45), (7.07, 14.69)]), ("via", 7.07, 14.69)]),   # 0.40 mm from CHG_STAT on L3
    ("I2C_SDA", [("B", 0.15, [(6.65, 14.12), (6.65, 14.9), (6.85, 15.24), (7.0, 15.24)]), ("via", 7.0, 15.24),
                 ("L3", 0.15, [(7.0, 15.24), (5.42, 13.66), (5.42, 13.04)])]),
    ("CHG_INT", [("B", 0.15, [(5.97, 13.45), (5.97, 14.9), (6.7, 15.69), (6.8, 15.79), (7.0, 15.79)]),
                 ("via", 7.0, 15.79),
                 ("L3", 0.15, [(7.0, 15.79), (6.43, 15.79), (5.98, 15.34)])]),
]

AUTO = [
    "I2C_SCL",
]

# The pieces above sit exactly on the board's clearances (0.10 mm copper to copper, 0.55 mm between via centres).
# The router adds a safety margin of 0.02 mm to its own checks; for hand-laid copper it is left out and KiCad's
# rule check has the last word (run it after this script; if it reports anything, the board goes back).
route.MARGIN = 0.0


def load(path):
    """The board's copper in a Router; locked items are marked as such."""
    board = pcbnew.LoadBoard(path)
    r = Router(board)
    mm = pcbnew.ToMM
    for t in board.GetTracks():
        net = r.net_id.get(t.GetNetname())
        if net is None or (t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() not in ROUTE_LAYERS):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            item = (net, mm(p.x) - OX, mm(p.y) - OY, mm(t.GetWidth(pcbnew.F_Cu)), mm(t.GetDrill()))
            r.vias.append(item)
        else:
            a, e = t.GetStart(), t.GetEnd()
            item = (net, ROUTE_LAYERS.index(t.GetLayer()), mm(a.x) - OX, mm(a.y) - OY, mm(e.x) - OX, mm(e.y) - OY,
                    mm(t.GetWidth()))
            r.tracks.append(item)
        if t.IsLocked():
            r.critical.add(item)
    r.build_maps(frozen=set(r.net_name))
    return r


def rip(r, rips=RIP):
    """Take out the stretches named in RIP. Returns what could not be found."""
    from finish import number_paths
    number_paths(r)
    bad = []
    for name, (x, y), *rad in rips:
        net = r.net_id[name]
        if rad:
            near = lambda px, py: math.hypot(px - x, py - y) <= rad[0]
            n = len(r.tracks) + len(r.vias)
            r.tracks = [t for t in r.tracks if not (t[0] == net and t not in r.critical and near(t[2], t[3]) and near(t[4], t[5]))]
            r.vias = [v for v in r.vias if not (v[0] == net and v not in r.critical and near(v[1], v[2]))]
            print(f"  taken out: {name} within {rad[0]} mm of ({x}, {y}), {n - len(r.tracks) - len(r.vias)} pieces")
            continue
        best = None
        for t in r.tracks:
            if t[0] != net or t in r.critical:
                continue
            d = pt_seg(x, y, t[2], t[3], t[4], t[5])
            if best is None or d < best[0]:
                best = (d, t)
        if best is None or best[0] > 0.3:
            bad.append(f"{name}: no track of this net within 0.3 mm of ({x}, {y})")
            continue
        pid = r.pid[best[1]]
        n = len(r.tracks) + len(r.vias)
        r.remove_paths({pid})
        print(f"  taken out: {name} near ({x}, {y}), {n - len(r.tracks) - len(r.vias)} pieces")
    r.build_maps(frozen=set(r.net_name))
    return bad


def lay(r, hand=HAND):
    bad = []
    for name, steps in hand:
        net = r.net_id[name]
        for step in steps:
            if step[0] == "via":
                _, x, y = step
                why = r.via_blocked(net, x, y, 0.45)
                if why:
                    bad.append(f"{name} via at ({x}, {y}): {why}")
                r.add_via(net, x, y, 0.45, 0.2, None)
                continue
            layer, width, pts = step
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                hit = r.blocked(net, LAYER[layer], x0, y0, x1, y1, width)
                if hit:
                    bad.append(f"{name} {layer} ({x0}, {y0}) - ({x1}, {y1}): too close to {hit[2]} "
                               f"at ({hit[0]:.2f}, {hit[1]:.2f})")
                r.add_track(net, LAYER[layer], x0, y0, x1, y1, width, None)
    return bad


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    r = load(path)
    before = sum(m for _, m in r.open_nets())
    bad = rip(r) + lay(r)
    for b in bad:
        print("  DOES NOT FIT:", b)
    r.build_maps(frozen=set(r.net_name))
    for name in AUTO:
        if r.route_net(name, record=False):
            print(f"  AUTO could not finish {name}")
    r.build_maps(frozen=set(r.net_name))
    left = r.open_nets()
    print(f"by hand: {len(RIP)} stretches taken out, {len(HAND)} nets laid, {len(AUTO)} finished by the grid router; "
          f"open {before} -> {sum(m for _, m in left)}")
    for name, m in left:
        print(f"  NOT ROUTED {name}: {m}")
    if "--try" in sys.argv or (bad and "--kicad-decides" not in sys.argv):
        return 1 if bad else 0            # --kicad-decides: write anyway, for pieces that sit exactly on a limit
    r.failed = left
    with open(os.path.join(OUT, "build", "open.json"), "w", encoding="utf-8") as f:
        json.dump(r.diagnose(), f, ensure_ascii=False, indent=0)
    strip_copper(path, path)
    board = pcbnew.LoadBoard(path)
    r.board = board
    r.export()
    add_all_zones(board)
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    with open(os.path.join(OUT, "build", "routing.json"), encoding="utf-8") as f:
        info = json.load(f)
    info.update(missing=sum(m for _, m in left), failed=left, vias=len(r.vias), source="Freerouting + finish.py + hand.py")
    with open(os.path.join(OUT, "build", "routing.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
