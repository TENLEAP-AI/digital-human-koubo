#!/usr/bin/env bash
# Regenerate everything: schematic, footprint library, PCB (placement stage) and the check reports.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$here/.."
name=zeebuddy-mainboard
py_kicad=/usr/bin/python3.12          # the interpreter KiCad's pcbnew module is built for

python3 "$here/design.py" "$out"
python3 "$here/verify.py" "$out" "$name"
kicad-cli sch erc --severity-all -o "$out/build/erc.rpt" "$out/$name.kicad_sch" >/dev/null || true
echo "ERC:"; grep -E "^\[" "$out/build/erc.rpt" | sed 's/\]:.*/]/' | sort | uniq -c || true
kicad-cli sch export pdf -o "$out/$name.pdf" "$out/$name.kicad_sch" >/dev/null

"$py_kicad" "$here/footprints.py" "$out"
"$py_kicad" "$here/board.py" "$out"
"$py_kicad" "$here/route.py" "$out" 2>&1 | grep -v "Debug: Adding"      # takes about five minutes
"$py_kicad" "$here/preview.py" "$out" 2>&1 | grep -v "Debug: Adding"
"$py_kicad" "$here/freeroute.py" "$out" 2>&1 | grep -v -e "Debug: Adding" -e "memory leak"   # refresh freerouting/*.dsn
kicad-cli pcb drc --severity-all --schematic-parity --format report -o "$out/build/drc.rpt" "$out/$name.kicad_pcb" >/dev/null || true
echo "DRC (unconnected items = connections the router has not made yet):"
grep -E "^\[" "$out/build/drc.rpt" | sed 's/\]:.*/]/' | sort | uniq -c || true
