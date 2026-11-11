"""Finish a board that Freerouting has routed.

    /usr/bin/python3.12 finish.py [output_dir]

Run it after freeroute.py --ses has imported the session file. Freerouting leaves three kinds of work:

- tracks that break rules it does not know: through holes that have no copper on the inner layers (it runs
  tracks straight through them), the 0.3 mm to the board edge, tracks thinner than the board's minimum.
  KiCad's rule check names them; they are taken out and the connection is made again;
- ground and +3V3 pads: it does not join pads to the planes. Every such pad gets a stub and a via,
  capacitors first, as in route.py;
- connections it could not make: route.py's router tries them with everything else left where it is.
"""
import collections
import json
import os
import subprocess
import sys
import time

import pcbnew

from board import NAME, OX, OY, keepouts_on_own_side
from route import BRANCH, PLANES, PWR_HI, RF, ROUTE_LAYERS, USB, Router, add_all_zones, net_rules, strip_copper

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
RIPUP = float(os.environ.get("RIPUP", "0"))      # seconds for pushing the last connections through; 0 = off
BAD = {"shorting_items", "clearance", "copper_edge_clearance", "items_not_allowed", "track_width",
       "hole_clearance", "hole_to_hole", "tracks_crossing"}


def rule_check(path, report):
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all", "--format", "json", "-o", report, path],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(report, encoding="utf-8") as f:
        return json.load(f)


def number_paths(r):
    """Give the imported copper path ids, so that rip-up can take out one stretch of a net and not the whole net.
    A stretch runs from a pad or a junction to the next pad or junction; locked copper gets no id."""
    key = lambda x, y: (round(x, 2), round(y, 2))
    for net in {t[0] for t in r.tracks}:
        tracks = [t for t in r.tracks if t[0] == net and t not in r.critical]
        vias = [v for v in r.vias if v[0] == net and v not in r.critical]
        ends = collections.defaultdict(list)
        for t in tracks:
            ends[key(t[2], t[3])].append(t)
            ends[key(t[4], t[5])].append(t)
        pads = [p["rect"] for p in r.pads if p["net"] == net]
        fixed = [i for i in r.critical if i[0] == net]

        def anchor(node):
            x, y = node
            if any(x0 - 0.01 <= x <= x1 + 0.01 and y0 - 0.01 <= y <= y1 + 0.01 for x0, y0, x1, y1 in pads):
                return True
            return any(key(*i[k:k + 2]) == node for i in fixed for k in ((1,) if len(i) == 5 else (2, 4)))

        stop = {n for n, ts in ends.items() if len(ts) != 2 or anchor(n)}
        via_at = collections.defaultdict(list)
        for v in vias:
            via_at[key(v[1], v[2])].append(v)
        seen = set()
        for t in tracks:
            if t in seen:
                continue
            pid, r.next_pid = r.next_pid, r.next_pid + 1
            todo = [t]
            while todo:
                cur = todo.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                r.pid[cur] = pid
                for node in (key(cur[2], cur[3]), key(cur[4], cur[5])):
                    if node in stop:
                        continue
                    for v in via_at.get(node, ()):
                        r.pid[v] = pid
                    todo += [o for o in ends[node] if o not in seen]
        for v in vias:
            if v not in r.pid:
                r.pid[v], r.next_pid = r.next_pid, r.next_pid + 1


def push_through(r, locked, budget):
    """One open connection at a time: find its cheapest way through other signal tracks, take out the stretches
    that are in the way, lay the connection, lay the pushed nets again. The step is kept only when fewer
    connections are open afterwards; otherwise the board goes back to what it was. Returns the steps kept."""
    lib = r.lib
    frozen = locked | {r.net_id[n] for n in RF | USB | PWR_HI | set(PLANES) if n in r.net_id}
    kept, t0 = 0, time.time()
    progress = True
    while progress and time.time() - t0 < budget:
        progress = False
        for pen in (40, 10, 150):
            r.build_maps(frozen)
            for name in [n for n, _ in r.open_nets() if n not in PLANES]:
                if time.time() - t0 > budget:
                    break
                state = (list(r.tracks), list(r.vias), dict(r.pid))
                r.build_maps(frozen)
                before = r.count_open()
                net = r.net_id[name]
                rules = net_rules(name)
                width = rules["widths"][-1]
                hits = set()
                for src in sorted({lib.rt_find(c) for c in r.comps[net]}):
                    res = r.search(net, src, rules, width, False, None, None, rip_pen=pen)
                    if res:
                        hits = {h for h in r.conflicts(net, res[0], width, rules) if h[0] not in frozen}
                        if hits:
                            break
                if not hits:
                    continue
                victims = {v for v, _ in hits}
                for v in {v for v, pid in hits if pid is None}:
                    r.remove_net(v)
                r.remove_paths({pid for _, pid in hits if pid is not None})
                r.build_maps(frozen)
                if r.drop_orphans(victims):
                    r.build_maps(frozen)
                r.route_net(name, record=False)
                for v in victims:
                    r.route_net(r.net_name[v], record=False)
                r.build_maps(frozen)
                after = r.count_open()
                if after < before:
                    kept += 1
                    progress = True
                    print(f"  pushed through: {name} (moved {', '.join(sorted(r.net_name[v] for v in victims))}); "
                          f"open {before} -> {after}", flush=True)
                else:
                    r.tracks, r.vias, r.pid = state
            r.build_maps(frozen)
    r.build_maps(frozen)
    return kept


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    board = pcbnew.LoadBoard(path)
    if keepouts_on_own_side(board):
        pcbnew.SaveBoard(path, board)
    bad = {}
    for v in rule_check(path, os.path.join(OUT, "build", "drc-imported.json"))["violations"]:
        if v["type"] in BAD:
            for it in v["items"]:
                bad[it["uuid"]] = v["type"]

    board = pcbnew.LoadBoard(path)
    r = Router(board)
    r.build_maps()
    total = sum(m for _, m in r.open_nets())
    mm = pcbnew.ToMM
    removed = collections.Counter()
    breaking = {}                                # track or via -> the rule it breaks

    def shape(t):
        if t.Type() == pcbnew.PCB_VIA_T:
            return (t.GetNetname(), t.GetPosition().x, t.GetPosition().y)
        ends = sorted([(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)])
        return (t.GetNetname(), t.GetLayer(), ends[0], ends[1])

    base = {shape(t) for t in board.GetTracks() if t.IsLocked()}
    for t in board.GetTracks():
        net = r.net_id.get(t.GetNetname())
        if net is None or (t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() not in ROUTE_LAYERS):
            removed["no net or not on a routing layer"] += 1
            continue
        if not t.IsLocked() and (t.GetNetname() in RF | USB or shape(t) in base):
            removed["copy of a locked track"] += 1          # the session repeats the locked tracks it was given
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
        elif t.m_Uuid.AsString() in bad:
            breaking[item] = bad[t.m_Uuid.AsString()]
    print(f"imported: {len(r.tracks)} track segments, {len(r.vias)} vias", flush=True)

    # 1. what Freerouting itself left hanging (unused fan-out vias and their stubs) goes first: it is in the way.
    #    The locked base is never tidied: its copper is meant as laid.
    loose = set(r.net_name) - {r.net_id[n] for n in RF | USB | PWR_HI | set(PLANES) if n in r.net_id}
    r.build_maps(frozen=set(r.net_name))
    n = (len(r.tracks), len(r.vias))
    r.trim_tails(only=loose)
    print(f"left hanging by Freerouting: {n[0] - len(r.tracks)} track pieces and {n[1] - len(r.vias)} vias removed",
          flush=True)
    # 2. then the pieces that break a rule. What is left of their connection stays for now: the router can
    #    pick it up at both ends and only has to bridge the gap; loose ends are tidied away after routing
    for item, why in breaking.items():
        if item in r.tracks or item in r.vias:
            removed[why] += 1
    r.tracks = [t for t in r.tracks if t not in breaking]
    r.vias = [v for v in r.vias if v not in breaking]
    print(f"taken out for breaking a rule: {dict(removed)}", flush=True)
    r.build_maps(frozen=set(r.net_name))
    before = r.open_nets()
    print(f"open before finishing: {sum(m for _, m in before)} of {total} connections in {len(before)} nets "
          f"(ground / +3V3 pads without a via: {sum(m for n, m in before if n in PLANES)})", flush=True)

    r.failed = []
    for name in sorted(n for n in PWR_HI if n in r.net_id):          # the base is complete already: these four
        r.route_net(name, record=False, rules=BRANCH)                # steps only matter if it was not
    r.route_net("GND", record=False)
    print(f"+3V3: {r.decouple_first('+3V3')} supply pins joined to their capacitor instead of a via", flush=True)
    r.route_net("+3V3", record=False)
    for name, _ in r.open_nets():
        if name not in PLANES:
            r.route_net(name, record=False)
    if RIPUP:
        # what is still open may push other signal tracks out of the way; those are then routed again.
        # Nets with locked copper are never touched. The best state seen is kept.
        r.build_maps(frozen=set(r.net_name))
        r.failed = [f for f in r.open_nets() if f[0] not in PLANES]
        before_rip = sum(m for _, m in r.failed)
        locked = {item[0] for item in r.critical}
        number_paths(r)
        r.build_maps(frozen=locked | {r.net_id[n] for n in RF | USB | PWR_HI | set(PLANES) if n in r.net_id})
        steps = push_through(r, locked, RIPUP)
        print(f"pushed through: {steps} steps kept, open {before_rip} -> {sum(m for _, m in r.open_nets())}", flush=True)
    n = (len(r.tracks), len(r.vias))
    r.trim_tails(only=loose)
    print(f"tidied: {n[0] - len(r.tracks)} loose track pieces and {n[1] - len(r.vias)} unused vias removed", flush=True)
    r.build_maps(frozen=set(r.net_name))
    r.failed = r.open_nets()
    missing = sum(m for _, m in r.failed)
    print(f"after finishing: {total - missing} of {total} connections, {len(r.tracks)} segments, {len(r.vias)} vias",
          flush=True)
    for name, m in r.failed:
        print(f"  NOT ROUTED {name}: {m}")
    diag = r.diagnose()
    with open(os.path.join(OUT, "build", "open.json"), "w", encoding="utf-8") as f:
        json.dump(diag, f, ensure_ascii=False, indent=0)

    strip_copper(path, path)
    board = pcbnew.LoadBoard(path)
    r.board = board
    r.export()
    add_all_zones(board)
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    with open(os.path.join(OUT, "build", "routing.json"), "w", encoding="utf-8") as f:
        json.dump(dict(total=total, missing=missing, failed=r.failed, vias=len(r.vias), source="Freerouting + finish.py"),
                  f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
