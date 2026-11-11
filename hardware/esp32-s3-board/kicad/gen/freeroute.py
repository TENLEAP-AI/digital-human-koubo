"""Route the board with Freerouting (https://github.com/freerouting/freerouting) instead of route.py.

    /usr/bin/python3.12 freeroute.py [output_dir] [--jar freerouting.jar] [--passes 30]

Without --jar it only writes build/<name>.dsn, which can be opened in Freerouting by hand;
the session file it saves (.ses) is then imported with --ses file.ses.
"""
import json
import os
import subprocess
import sys

import pcbnew

from board import NAME
from route import BOARD_H, BOARD_W, add_zone

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(zip(sys.argv[1:], sys.argv[2:]))
OUT = args[0] if args and args[0] not in opts.values() else os.path.join(HERE, "..")
JAVA = "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"


def main():
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    dsn = os.path.join(OUT, "build", NAME + ".dsn")
    ses = opts.get("--ses") or os.path.join(OUT, "build", NAME + ".ses")
    board = pcbnew.LoadBoard(path)
    for t in list(board.GetTracks()):          # start from the placed, unrouted board
        board.Remove(t)
    for z in list(board.Zones()):
        board.Remove(z)
    add_zone(board, "GND", pcbnew.In1_Cu)      # exported as planes: the router drops vias onto them
    add_zone(board, "+3V3", pcbnew.In2_Cu)
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
