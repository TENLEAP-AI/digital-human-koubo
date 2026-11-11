"""Signal connections laid by hand, for what the autorouters leave open.

    /usr/bin/python3.12 hand.py [output_dir] [--try]

Run it after finish.py. Every piece in HAND is checked against the copper that is on the board with the router's
own clearance map; a piece that does not fit is reported with the spot and what is in the way, and nothing is
written. --try only reports.

HAND is a list of (net, steps). A step is ("F" | "L3" | "B", width, [(x, y), ...]) for a track or
("via", x, y) for a 0.45 / 0.2 mm via. Coordinates as in place.py: millimetres from the board's top-left corner.
"""
import json
import os
import sys

import pcbnew

from board import NAME, OX, OY
from route import ROUTE_LAYERS, Router, add_all_zones, strip_copper

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = args[0] if args else os.path.join(HERE, "..")
LAYER = {"F": 0, "L3": 1, "B": 3}

HAND = [
]


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
    bad = lay(r)
    for b in bad:
        print("  DOES NOT FIT:", b)
    r.build_maps(frozen=set(r.net_name))
    left = r.open_nets()
    print(f"by hand: {len(HAND)} connections laid, open {before} -> {sum(m for _, m in left)}")
    for name, m in left:
        print(f"  NOT ROUTED {name}: {m}")
    if bad or "--try" in sys.argv:
        return 1 if bad else 0
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
