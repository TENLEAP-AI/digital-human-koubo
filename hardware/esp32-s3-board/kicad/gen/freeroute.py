"""Route the board with Freerouting (https://github.com/freerouting/freerouting) instead of route.py.

    /usr/bin/python3.12 freeroute.py [output_dir] [--jar freerouting.jar] [--passes 30]

Without --jar it only writes freerouting/<name>.dsn, which can be opened in Freerouting by hand;
the session file it saves (.ses) is then imported with --ses file.ses.

The locked tracks and vias of the board (antenna line, USB pairs, ESP32 decoupling, written by route.py)
are handed over as fixed wiring and kept when the session file is imported; everything else is rerouted.
"""
import json
import os
import subprocess
import sys

import pcbnew

from board import NAME
from route import VDD_4G_AREA, add_pour, add_rf_ground, add_zone, strip_copper

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(zip(sys.argv[1:], sys.argv[2:]))
OUT = args[0] if args and args[0] not in opts.values() else os.path.join(HERE, "..")
JAVA = "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    dsn = os.path.join(OUT, "freerouting", NAME + ".dsn")
    ses = opts.get("--ses") or os.path.join(OUT, "freerouting", NAME + ".ses")
    bare = os.path.join(OUT, "build", NAME + "-unrouted.kicad_pcb")
    kept = strip_copper(path, bare, keep_locked=True)   # keep only the locked copper: antenna, USB, decoupling
    board = pcbnew.LoadBoard(bare)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)   # ground plane: no signal tracks on it
    add_zone(board, "GND", pcbnew.In1_Cu)      # exported as planes: the router drops vias onto them
    add_zone(board, "+3V3", pcbnew.In2_Cu)
    add_pour(board, "VDD_4G", pcbnew.B_Cu, VDD_4G_AREA)
    add_rf_ground(board)
    print(f"kept {kept} locked tracks and vias")
    if "--ses" not in opts:
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            raise SystemExit("DSN export failed")
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
