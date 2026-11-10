#!/bin/bash
# Check that the KiCad toolchain works end to end, in a throwaway directory:
# build a tiny board with the Python API, run DRC, export Gerbers/drill/placement,
# render it, then run ERC and a netlist export on a bundled template schematic.
set -euo pipefail

PY=/usr/bin/python3.12          # pcbnew is built against the system Python
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cd "$T"

"$PY" - board.kicad_pcb <<'EOF'
import sys, pcbnew
from pcbnew import VECTOR2I, FromMM

FP = "/usr/share/kicad/footprints"
path = sys.argv[1]
b = pcbnew.BOARD()

def net(name):
    n = pcbnew.NETINFO_ITEM(b, name); b.Add(n); return n

def place(lib, name, ref, x, y, rot=0):
    fp = pcbnew.FootprintLoad(f"{FP}/{lib}.pretty", name)
    fp.SetReference(ref); fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y))); fp.SetOrientationDegrees(rot)
    b.Add(fp); return fp

gnd, v33 = net("GND"), net("+3V3")
u1 = place("RF_Module", "ESP32-S3-WROOM-1", "U1", 30, 30)
c1 = place("Capacitor_SMD", "C_0402_1005Metric", "C1", 17, 28, 90)
for p in u1.Pads():
    if p.GetNumber() in ("1", "40", "41"): p.SetNet(gnd)
    if p.GetNumber() == "2": p.SetNet(v33)
cp = {p.GetNumber(): p for p in c1.Pads()}
cp["1"].SetNet(v33); cp["2"].SetNet(gnd)

x0, y0, x1, y1 = 10, 14, 50, 64
for a, c in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1]))); s.SetEnd(VECTOR2I(FromMM(c[0]), FromMM(c[1])))
    s.SetWidth(FromMM(0.1)); b.Add(s)

z = pcbnew.ZONE(b); z.SetLayer(pcbnew.B_Cu); z.SetNet(gnd)
o = z.Outline(); o.NewOutline()
for x, y in ((x0 + 0.5, 24), (x1 - 0.5, 24), (x1 - 0.5, y1 - 0.5), (x0 + 0.5, y1 - 0.5)):
    o.Append(FromMM(x), FromMM(y))
b.Add(z)

pcbnew.SaveBoard(path, b)
b = pcbnew.LoadBoard(path)   # zone fill crashes on a board that was never loaded from disk
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(path, b)
assert pcbnew.ExportSpecctraDSN(b, path.replace(".kicad_pcb", ".dsn"))
print(f"python api   ok  (pcbnew {pcbnew.Version()}, {len(b.GetFootprints())} footprints, {b.GetAreaCount()} zone)")
EOF

kicad-cli pcb drc --format json --severity-all -o drc.json board.kicad_pcb >/dev/null
echo "pcb drc      ok  ($("$PY" -c "import json;d=json.load(open('drc.json'));print(len(d['violations']),'violations,',len(d['unconnected_items']),'unconnected on the test board')"))"

mkdir fab
kicad-cli pcb export gerbers -o fab/ -l F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,F.SilkS,Edge.Cuts board.kicad_pcb >/dev/null
kicad-cli pcb export drill -o fab/ board.kicad_pcb >/dev/null
kicad-cli pcb export pos -o fab/pos.csv --format csv --units mm board.kicad_pcb >/dev/null
echo "fab export   ok  ($(ls fab | wc -l) files)"

kicad-cli pcb render -o render.png --side top -w 800 -h 600 board.kicad_pcb >/dev/null
echo "3d render    ok  ($(stat -c %s render.png) bytes)"

cp /usr/share/kicad/template/Arduino_Nano/Arduino_Nano.kicad_sch sch.kicad_sch
kicad-cli sch erc --format json --severity-all -o erc.json sch.kicad_sch >/dev/null
kicad-cli sch export netlist -o sch.net sch.kicad_sch >/dev/null
echo "sch erc/net  ok  ($(grep -c '(comp ' sch.net) components in template netlist)"
