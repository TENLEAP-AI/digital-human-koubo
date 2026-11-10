#!/usr/bin/env bash
# Regenerate the schematic, check it against the intended netlist, run ERC and export a PDF.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$here/.."
name=zeebuddy-mainboard
python3 "$here/design.py" "$out"
python3 "$here/verify.py" "$out" "$name"
kicad-cli sch erc --severity-all --exit-code-violations -o "$out/build/erc.rpt" "$out/$name.kicad_sch" >/dev/null || true
grep -E "^\[" "$out/build/erc.rpt" | sort | uniq -c || true
kicad-cli sch export pdf -o "$out/$name.pdf" "$out/$name.kicad_sch" >/dev/null
echo "pdf: $out/$name.pdf"
