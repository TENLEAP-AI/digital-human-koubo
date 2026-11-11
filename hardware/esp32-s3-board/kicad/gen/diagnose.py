"""Why does the router leave connections open? Three checks on the placed and routed board.

    /usr/bin/python3.12 diagnose.py [output_dir]

Needs the routed board and build/open.json, both written by route.py.

A. Every connection the router left open, tried on its own:
     1  no way even on the bare board (pads, board edge, keep-outs only): fan-out, rules or keep-outs are at fault
     2  a way on the bare board, none once the fixed copper is there (antenna line, USB, supply nets,
        all ground and +3V3 stubs and vias)
     3  a way past the fixed copper: only other signal tracks are in the way, the router is at fault
B. Fan-out: can every pin that needs a via get one of its own within 1 / 1.5 / 2 mm of its pad
   (a matching of pins to the via sites that fit between the pads).
C. Cuts: the nets that have to cross a line against the tracks that fit across it, for every vertical
   and horizontal line. If more have to cross than fit, the board is too small, whatever the router does.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
sys.argv = [sys.argv[0], out]

import pcbnew  # noqa: E402

import route   # noqa: E402
from route import G, GW, GH, L1, L3, L4, L6, PLANES, PWR_HI, RF, ROUTE_LAYERS, USB, net_rules  # noqa: E402

OX, OY = route.OX, route.OY
mm = pcbnew.ToMM
board = pcbnew.LoadBoard(os.path.join(out, route.NAME + ".kicad_pcb"))
r = route.Router(board)
lib = r.lib
FIXED = RF | USB | PWR_HI | set(PLANES)


def copper(want):
    tracks, vias = [], []
    for t in board.GetTracks():
        name = t.GetNetname()
        if name not in r.net_id or not want(name):
            continue
        net = r.net_id[name]
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            vias.append((net, mm(p.x) - OX, mm(p.y) - OY, mm(t.GetWidth(pcbnew.F_Cu)), mm(t.GetDrill())))
        elif t.GetLayer() in ROUTE_LAYERS:
            a, e = t.GetStart(), t.GetEnd()
            tracks.append((net, ROUTE_LAYERS.index(t.GetLayer()), mm(a.x) - OX, mm(a.y) - OY, mm(e.x) - OX, mm(e.y) - OY,
                           mm(t.GetWidth())))
    return tracks, vias


def reachable(name, group):
    """Is there a way from this group of pads to the rest of its net (or to a via, for a plane net)?"""
    net = r.net_id[name]
    comps = [p["comp"] for p in r.pads if p["net"] == net and f'{p["ref"]}.{p["num"]}' in group]
    for c in comps[1:]:
        lib.rt_unite(comps[0], c)
    rules = net_rules(name)
    plane = name in PLANES
    for width in rules["widths"]:
        if r.search(net, lib.rt_find(comps[0]), rules, width, plane, None, None):
            return True
    return False


with open(os.path.join(out, "build", "open.json"), encoding="utf-8") as f:
    open_groups = json.load(f)

# ---- A -------------------------------------------------------------------------------------------
r.tracks, r.vias = [], []
r.build_maps()
bare = [reachable(g["net"], set(g["pads"])) for g in open_groups]
r.tracks, r.vias = copper(lambda n: n in FIXED)
r.build_maps(frozen=set(r.net_name))
fixed = [reachable(g["net"], set(g["pads"])) for g in open_groups]
cls = [1 if not a else 2 if not b else 3 for a, b in zip(bare, fixed)]
print(f"A. {len(open_groups)} open connections, each tried on its own:")
print(f"   1  no way even on the bare board:              {cls.count(1)}")
print(f"   2  blocked by fixed copper (supply, planes):   {cls.count(2)}")
print(f"   3  blocked only by other signal tracks:        {cls.count(3)}")
for k in (1, 2):
    for g, c in zip(open_groups, cls):
        if c == k:
            print(f"      class {k}: {g['net']:<14} {','.join(g['pads'])[:30]:<30} at ({g['x']:.1f}, {g['y']:.1f}) {g['side']}")

# ---- B -------------------------------------------------------------------------------------------
r.tracks, r.vias = [], []
r.build_maps()
generic = r.nid("__generic__")
via_d = 0.45
nvp, vprobe = route.disc_offsets(via_d / 2 - route.W_DEF / 2 + 0.01)
pitch = via_d + route.CLR
pc = int(math.ceil(pitch / G))
legal = bytearray(GW * GH)
for iy in range(GH):
    for ix in range(GW):
        if lib.rt_via_ok(generic, ix, iy, nvp, vprobe):
            legal[iy * GW + ix] = 1
taken = bytearray(GW * GH)
sites = []
for iy in range(GH):
    row = iy * GW
    for ix in range(GW):
        if legal[row + ix] and not taken[row + ix]:
            sites.append((ix * G, iy * G))
            for dy in range(-pc, pc + 1):
                yy = iy + dy
                if 0 <= yy < GH:
                    span = int(math.sqrt(max(0.0, (pitch / G) ** 2 - dy * dy)))
                    for xx in range(max(0, ix - span), min(GW, ix + span + 1)):
                        taken[yy * GW + xx] = 1
nets = {}
for p in r.pads:
    nets.setdefault(p["net"], []).append(p)
pins = []
for net, pads in nets.items():
    name = r.net_name[net]
    if name.startswith(("unconnected-", "nonet-", "__")) or len(pads) < 2:
        continue
    done = []
    for p in pads:
        if p["pth"]:
            continue
        if name in PLANES:
            if any(route.rect_gap(p["rect"], q["rect"]) < 0.8 for q in done):
                continue
            done.append(p)
            pins.append(p)
        elif not [q for q in pads if q is not p and q["layers"] == p["layers"] and route.rect_gap(p["rect"], q["rect"]) < 4.0]:
            pins.append(p)
buckets = {}
for k, (x, y) in enumerate(sites):
    buckets.setdefault((int(x // 2), int(y // 2)), []).append(k)


def near(p, reach):
    x0, y0, x1, y1 = p["rect"]
    out_ = []
    for bx in range(int((x0 - reach) // 2), int((x1 + reach) // 2) + 1):
        for by in range(int((y0 - reach) // 2), int((y1 + reach) // 2) + 1):
            for k in buckets.get((bx, by), ()):
                x, y = sites[k]
                if math.hypot(max(x0 - x, x - x1, 0), max(y0 - y, y - y1, 0)) <= reach:
                    out_.append(k)
    return out_


def matching(reach):
    adj = [near(p, reach) for p in pins]
    owner = {}

    def augment(i, seen):
        for k in adj[i]:
            if k in seen:
                continue
            seen.add(k)
            if k not in owner or augment(owner[k], seen):
                owner[k] = i
                return True
        return False

    sys.setrecursionlimit(10000)
    left = [i for i in range(len(pins)) if not augment(i, set())]
    return left


print(f"B. fan-out with {via_d} mm vias: {len(pins)} pins need a via, {len(sites)} via sites fit between the pads")
for reach in (1.0, 1.5, 2.0):
    left = matching(reach)
    by = {}
    for i in left:
        by[pins[i]["ref"]] = by.get(pins[i]["ref"], 0) + 1
    top = ", ".join(f"{ref} {n}" for ref, n in sorted(by.items(), key=lambda kv: -kv[1])[:12])
    print(f"   within {reach} mm of the pad: {len(pins) - len(left)} of {len(pins)} get their own via; "
          f"{len(left)} do not  ({top})")

# ---- C -------------------------------------------------------------------------------------------
def crossing(axis, c):
    n = 0
    for net, pads in nets.items():
        name = r.net_name[net]
        if name in PLANES or name.startswith(("unconnected-", "nonet-", "__")) or len(pads) < 2:
            continue
        v = [(p["rect"][axis] + p["rect"][axis + 2]) / 2 for p in pads]
        if min(v) < c < max(v):
            n += 1
    return n


def fits(axis, c, layer, pitch_cells):
    """How many default tracks fit across the line on this layer (free cells in runs, one track per pitch)."""
    n = run = 0
    span = GH if axis == 0 else GW
    k = round(c / G)
    for i in range(span + 1):
        free = i < span and (lib.rt_owner_at(layer, k, i) if axis == 0 else lib.rt_owner_at(layer, i, k)) == 0
        if free:
            run += 1
        else:
            if run:
                n += (run - 1) // pitch_cells + 1
            run = 0
    return n


def profile(label, maps_note):
    print(f"C. cuts, {maps_note}; tracks at 0.15 mm width and 0.10 mm spacing (0.25 mm pitch)")
    for axis, name, lo, hi, length in ((0, "vertical line x", 2.0, 62.0, route.BOARD_H), (1, "horizontal line y", 2.0, 32.0, route.BOARD_W)):
        rows = []
        c = lo
        while c <= hi:
            d = crossing(axis, c)
            cap = {l: fits(axis, c, l, 5) for l in (L1, L3, L4, L6)}
            rows.append((c, d, cap))
            c += 0.5
        worst = sorted((row for row in rows if row[1] >= 8), key=lambda row: (row[2][L1] + row[2][L3] + row[2][L6]) / row[1])[:4]
        for c, d, cap in worst:
            tot3 = cap[L1] + cap[L3] + cap[L6]
            print(f"   {name} = {c:4.1f}: {d:3d} nets must cross ({d / length:.1f} per mm of line); room for "
                  f"{cap[L1]} on L1 + {cap[L3]} on L3 + {cap[L6]} on L6 = {tot3}  (L4 would add {cap[L4]})  -> {d / tot3 * 100:.0f} % used")
        if axis == 0:
            for c, d, cap in rows:
                if abs(c - 40.5) < 1e-6:
                    tot3 = cap[L1] + cap[L3] + cap[L6]
                    print(f"   between the two modules, x = 40.5: {d} nets must cross ({d / length:.1f} per mm); room for "
                          f"{cap[L1]} + {cap[L3]} + {cap[L6]} = {tot3}  (L4 would add {cap[L4]})  -> {d / tot3 * 100:.0f} % used")


profile("bare", "bare board (pads, edge, keep-outs)")
r.tracks, r.vias = copper(lambda n: n in FIXED)
r.build_maps(frozen=set(r.net_name))
profile("fixed", "with the fixed copper in place (supply nets, ground and +3V3 stubs and vias, antenna line, USB)")
