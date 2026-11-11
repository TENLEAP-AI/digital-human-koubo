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
"""
import os
import re
import shutil
import subprocess
import sys

import pcbnew

from board import NAME
from route import L4_SIGNALS, add_rf_ground, add_zone, strip_copper

EDGE = 0.32      # mm: the outline handed over is this much smaller all round (GEN-6 asks for 0.3)
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(zip(sys.argv[1:], sys.argv[2:]))
OUT = args[0] if args and args[0] not in opts.values() else os.path.join(HERE, "..")
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
    add_zone(board, "GND", pcbnew.In1_Cu)      # exported as planes: the router drops vias onto them
    add_zone(board, "GND", pcbnew.In4_Cu)
    win = add_rf_ground(board)                 # the ground under the antenna socket's opening...
    add_zone(board, "+3V3", pcbnew.In3_Cu, hole=win[1] if win else None)   # ...is left out of the +3V3 plane
    print(f"kept {kept} locked tracks and vias")
    if "--ses" not in opts:
        for_export(board)
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            raise SystemExit("DSN export failed")
        inner = [board.GetLayerName(l) for l in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu)]
        print(f"through-hole pad types given their copper on the inner layers: {solid_holes(dsn, inner)}")
        print("wrote", os.path.relpath(dsn, OUT))
    jar = opts.get("--jar")
    if jar and "--ses" not in opts:
        cmd = [JAVA, "-jar", jar, "-de", dsn, "-do", ses, "-mp", opts.get("--passes", "30"), "-da"]
        print(" ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)
    if not os.path.exists(ses) or (not jar and "--ses" not in opts):
        return 0
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
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
