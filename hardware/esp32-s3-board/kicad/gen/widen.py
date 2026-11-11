"""Widen necked-down tracks where the clearances allow it (GEN-1: 0.15 mm; 0.10 mm only between pins, at most 3 mm).

    /usr/bin/python3.12 widen.py board.kicad_pcb

Freerouting narrows a track near a pin to the pin's width. Runs of narrow track longer than 3 mm go to 0.15 mm,
pieces of 0.09 mm to 0.11 mm. A piece that KiCad's rule check then objects to gets its old width back. Run it after
finish.py and hand.py; locked copper is not touched.
"""
import collections, json, os, subprocess, sys
import pcbnew
path = sys.argv[1]
REPORT = os.path.join(os.path.dirname(os.path.abspath(path)), "build", "widen-drc.json")
mm = pcbnew.ToMM
def runs_of(board):
    narrow = [t for t in board.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and mm(t.GetWidth()) < 0.149 and not t.IsLocked()]
    key = lambda p: (round(p.x / 1000), round(p.y / 1000))
    groups = collections.defaultdict(list)
    for t in narrow: groups[(t.GetNetname(), t.GetLayer())].append(t)
    out = []
    for ts in groups.values():
        parent = list(range(len(ts)))
        def find(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        ends = collections.defaultdict(list)
        for i, t in enumerate(ts):
            ends[key(t.GetStart())].append(i); ends[key(t.GetEnd())].append(i)
        for lst in ends.values():
            for i in lst[1:]: parent[find(i)] = find(lst[0])
        members = collections.defaultdict(list)
        for i, t in enumerate(ts): members[find(i)].append(t)
        out += list(members.values())
    return out
board = pcbnew.LoadBoard(path)
old = {}
for run in runs_of(board):
    length = sum(mm(t.GetLength()) for t in run)
    for t in run:
        w = mm(t.GetWidth())
        new = 0.15 if length > 3.0 else 0.11 if w < 0.095 else None
        if new:
            old[t.m_Uuid.AsString()] = t.GetWidth()
            t.SetWidth(pcbnew.FromMM(new))
print("pieces widened:", len(old))
pcbnew.SaveBoard(path, board)
for attempt in range(4):
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all", "--format", "json", "-o", REPORT, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bad = {i["uuid"] for v in json.load(open(REPORT))["violations"] for i in v["items"]}
    back = [u for u in old if u in bad]
    print("attempt", attempt, "violations touching widened pieces:", len(back))
    if not back: break
    board = pcbnew.LoadBoard(path)
    for t in board.GetTracks():
        u = t.m_Uuid.AsString()
        if u in back: t.SetWidth(old.pop(u))
    pcbnew.SaveBoard(path, board)
board = pcbnew.LoadBoard(path)
pcbnew.ZONE_FILLER(board).Fill(board.Zones()); pcbnew.SaveBoard(path, board)
print("kept wider:", len(old))
