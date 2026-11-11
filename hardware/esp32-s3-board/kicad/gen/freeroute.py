"""Hand the signals over to Freerouting (https://github.com/freerouting/freerouting).

    /usr/bin/python3.12 freeroute.py [output_dir] [--jar freerouting.jar] [--passes 30]

Without --jar it only writes freerouting/<name>.dsn, which can be opened in Freerouting by hand;
the session file it saves (.ses) is then imported with --ses file.ses, and finish.py tidies up.

The locked tracks and vias of the board (the base that route.py lays: supply copper, antenna line, USB pairs,
ground and +3V3 stubs) are handed over as fixed wiring and kept when the session file is imported.

What the first round taught (2026-11-11):
- once a layer is marked as a power layer, KiCad writes the through-hole pads of parts on the back (ESP32
  thermal vias, Type-C shell) with copper on the outer layers only, and Freerouting runs inner-layer tracks
  straight through the holes: solid_holes() gives those pads their copper on every layer in the file;
- the file carries no clearance to the board edge, and Freerouting routes right up to the outline:
  for_export() hands over an outline that is drawn inside the real one.

And the second round: Freerouting keeps trying to route the pads of plane nets (ground, +3V3) to each other,
every pass, without success, and it spends minutes tidying wide tracks that overlap. So the nets that the
base has already finished are not handed over as nets at all: hide_finished() turns their copper into
keep-out areas and takes the net off their pads. Freerouting then sees obstacles and 243 signal connections.
Ground and +3V3 keep one pad each: a layer only stays closed to signal tracks while a plane lies on it, and
a plane needs a net (without the planes Freerouting routed 160 tracks on the three plane layers).
"""
import math
import os
import re
import shutil
import subprocess
import sys

import pcbnew

from board import NAME
from board import OX, OY
from route import L4_SIGNALS, PLANES, ROUTE_LAYERS, Router, add_rf_ground, add_zone, strip_copper

EDGE = 0.32      # mm: the outline handed over is this much smaller all round (GEN-6 asks for 0.3)
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(zip(sys.argv[1:], sys.argv[2:]))
OUT = args[0] if args and args[0] not in opts.values() else os.path.join(HERE, "..")
STAGE2 = "--stage2" in sys.argv     # route only what is still open; the routed signals stay and count as obstacles
JAVA = "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"


def solid_holes(dsn, inner):
    """Through-hole pads that the file shows on the two outer layers only ("[TB]") get the same shape on the
    inner layers. Returns how many pad types were changed."""
    text = open(dsn, encoding="utf-8").read()
    n = 0

    def fill(m):
        nonlocal n
        block = m.group(0)
        first = re.search(r"^(\s*)\(shape \((\w+) F\.Cu ([^\n]*)\)\)\s*$", block, re.M)
        if not first or any(f" {layer} " in block for layer in inner):
            return block
        n += 1
        extra = "".join(f"\n{first.group(1)}(shape ({first.group(2)} {layer} {first.group(3)}))" for layer in inner)
        return block[:first.end()].rstrip("\n") + extra + block[first.end():]

    text = re.sub(r"\(padstack \S*\[TB\]\S*\n(?:[^\n]*\n)*?\s*\(attach off\)", fill, text)
    with open(dsn, "w", encoding="utf-8") as f:
        f.write(text)
    return n


def geometry(t):
    if t.Type() == pcbnew.PCB_VIA_T:
        return (t.GetNetname(), t.GetPosition().x, t.GetPosition().y)
    return (t.GetNetname(), t.GetLayer(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y)


def hide_finished(board):
    """Nets that are complete in the base: their tracks and vias become keep-out areas, their pads lose
    the net. Returns the names of those nets. Only for the copy that is exported."""
    mm = pcbnew.ToMM
    r = Router(board)
    for t in board.GetTracks():
        net = r.net_id.get(t.GetNetname())
        if net is None:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            r.vias.append((net, mm(q.x) - OX, mm(q.y) - OY, mm(t.GetWidth(pcbnew.F_Cu)), mm(t.GetDrill())))
        elif t.GetLayer() in ROUTE_LAYERS:
            a, e = t.GetStart(), t.GetEnd()
            r.tracks.append((net, ROUTE_LAYERS.index(t.GetLayer()), mm(a.x) - OX, mm(a.y) - OY,
                             mm(e.x) - OX, mm(e.y) - OY, mm(t.GetWidth())))
    r.build_maps(frozen=set(r.net_name))
    open_nets = {name for name, _ in r.open_nets()}
    done = {t.GetNetname() for t in board.GetTracks()} - open_nets - {""}

    def area(layers, pts):
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for layer in layers:
            ls.AddLayer(layer)
        z.SetLayerSet(ls)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowFootprints(False)
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(int(round(x)), int(round(y)))
        board.Add(z)

    def capsule(ax, ay, bx, by, radius, n=6):
        """Outline of a track: a rectangle with rounded ends (coordinates in KiCad units)."""
        ang = math.atan2(by - ay, bx - ax) if (ax, ay) != (bx, by) else 0.0
        k = radius / math.cos(math.pi / (2 * n))          # the polygon encloses the round end
        pts = [(bx + k * math.cos(ang - math.pi / 2 + i * math.pi / n), by + k * math.sin(ang - math.pi / 2 + i * math.pi / n))
               for i in range(n + 1)]
        pts += [(ax + k * math.cos(ang + math.pi / 2 + i * math.pi / n), ay + k * math.sin(ang + math.pi / 2 + i * math.pi / n))
                for i in range(n + 1)]
        return pts

    signal = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    if L4_SIGNALS:
        signal.append(pcbnew.In3_Cu)             # the vias of the finished nets cross L4 too
    n = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() not in done:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            area(signal, capsule(q.x, q.y, q.x, q.y, t.GetWidth(pcbnew.F_Cu) / 2))
        else:
            a, e = t.GetStart(), t.GetEnd()
            area([t.GetLayer()], capsule(a.x, a.y, e.x, e.y, t.GetWidth() / 2))
        board.Remove(t)
        n += 1
    pads = 0
    keep = {}                                    # plane net -> the one pad that keeps it: a through hole if there is one
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = pad.GetNetname()
            if name in done and name in PLANES:
                if name not in keep or (pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                                        and keep[name].GetAttribute() != pcbnew.PAD_ATTRIB_PTH):
                    keep[name] = pad
    held = {(p.GetParentFootprint().GetReference(), p.GetNumber(), p.GetPosition().x, p.GetPosition().y)
            for p in keep.values()}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in done:
                if (fp.GetReference(), pad.GetNumber(), pad.GetPosition().x, pad.GetPosition().y) in held:
                    continue
                pad.SetNetCode(0)
                pads += 1
    print(f"finished in the base and handed over as obstacles: {len(done)} nets, {n} tracks and vias, {pads} pads")
    return done


def for_export(board):
    """The copy handed to the autorouter gets an outline that is EDGE smaller all round."""
    outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline):
        raise SystemExit("the board outline is not closed")
    outline.Deflate(pcbnew.FromMM(EDGE), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.005))
    for d in list(board.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(d)
    shape = pcbnew.PCB_SHAPE(board)                       # the smaller outline as one closed polygon
    shape.SetShape(pcbnew.SHAPE_T_POLY)
    shape.SetPolyShape(outline)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    shape.SetFilled(False)
    board.Add(shape)
    n = outline.VertexCount(0, -1)
    print(f"for the autorouter: outline drawn {EDGE} mm inside the real one ({n} points)")


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    dsn = os.path.join(OUT, "freerouting", NAME + ".dsn")
    ses = opts.get("--ses") or os.path.join(OUT, "freerouting", NAME + ".ses")
    bare = os.path.join(OUT, "build", NAME + "-unrouted.kicad_pcb")
    free = set()                                        # second stage: what was not locked, to unlock it again
    if STAGE2:                                          # everything that is routed stays: lock it, so that neither
        whole = pcbnew.LoadBoard(path)                  # strip_copper nor the session import throws it away
        for t in whole.GetTracks():
            if not t.IsLocked():
                free.add(geometry(t))
                t.SetLocked(True)
        locked_copy = bare[:-len(".kicad_pcb")] + "-locked.kicad_pcb"
        pcbnew.SaveBoard(locked_copy, whole)
        kept = strip_copper(locked_copy, bare, keep_locked=True)
    else:
        kept = strip_copper(path, bare, keep_locked=True)   # keep only the locked copper: antenna, USB, decoupling
    # the net classes and design rules live in the project file: without a copy next to the stripped board
    # the export falls back to KiCad's defaults (0.2 mm tracks and clearance, 0.6 mm vias)
    shutil.copyfile(os.path.join(OUT, NAME + ".kicad_pro"), bare[:-len(".kicad_pcb")] + ".kicad_pro")
    board = pcbnew.LoadBoard(bare)
    planes = [pcbnew.In1_Cu, pcbnew.In4_Cu]              # ground planes: no signal tracks on them
    if not L4_SIGNALS:
        planes.append(pcbnew.In3_Cu)                     # STK-6: L4 carries +3V3 only
    for layer in planes:
        board.SetLayerType(layer, pcbnew.LT_POWER)
    print(f"kept {kept} locked tracks and vias")
    if "--ses" not in opts:
        hide_finished(board)
    add_zone(board, "GND", pcbnew.In1_Cu)      # exported as planes: they keep signal tracks off these layers
    add_zone(board, "GND", pcbnew.In4_Cu)
    win = add_rf_ground(board)                 # the ground under the antenna socket's opening...
    if not L4_SIGNALS or "--ses" in opts:      # STK-6 relaxed: no plane on L4 in the hand-off, so signals may use it;
        add_zone(board, "+3V3", pcbnew.In3_Cu, hole=win[1] if win else None)   # the +3V3 copper is poured around them
    if "--ses" not in opts:
        for_export(board)                      # last: after it pcbnew hands out zone outlines that cannot be used
    if "--ses" not in opts:
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            raise SystemExit("DSN export failed")
        inner = [board.GetLayerName(l) for l in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu)]
        print(f"through-hole pad types given their copper on the inner layers: {solid_holes(dsn, inner)}")
        print("wrote", os.path.relpath(dsn, OUT))
    jar = opts.get("--jar")
    if jar and "--ses" not in opts:
        # a time limit: Freerouting only writes its result when it stops, and the last few connections can
        # keep it busy for an hour. finish.py makes the connections that are still open
        cmd = [JAVA, "-Djava.awt.headless=true", "-jar", jar, "-de", dsn, "-do", ses,
               "--router.autorouter.max_passes=" + opts.get("--passes", "30"),
               "--router.job_timeout=" + opts.get("--time", "00:15:00"), "-mt", "1",
               "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true"]
        print(" ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)
    if not os.path.exists(ses) or (not jar and "--ses" not in opts):
        return 0
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
    for t in board.GetTracks():
        if t.IsLocked() and geometry(t) in free:
            t.SetLocked(False)
    add_zone(board, "GND", pcbnew.F_Cu)
    add_zone(board, "GND", pcbnew.B_Cu)
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    tracks = [t for t in board.GetTracks()]
    vias = sum(1 for t in tracks if t.Type() == pcbnew.PCB_VIA_T)
    print(f"imported {len(tracks) - vias} track segments and {vias} vias; run the DRC to see what is left open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
