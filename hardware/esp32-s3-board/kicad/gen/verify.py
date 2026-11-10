"""Export the netlist with kicad-cli and compare it with what the generator intended."""
import json
import os
import subprocess
import sys

from sexpr import find, first, parse


def main(outdir, name):
    sch = os.path.join(outdir, name + ".kicad_sch")
    net = os.path.join(outdir, "build", name + ".net")
    os.makedirs(os.path.dirname(net), exist_ok=True)
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", net, sch],
                   check=True, stdout=subprocess.DEVNULL)
    with open(net, encoding="utf-8") as f:
        tree = parse(f.read())
    actual = {}
    for n in find(first(tree, "nets"), "net"):
        nm = first(n, "name")[1]
        for node in find(n, "node"):
            actual[(first(node, "ref")[1], first(node, "pin")[1])] = nm
    with open(os.path.join(outdir, "build", "expected_nets.json"), encoding="utf-8") as f:
        expected = {tuple(k.split(".", 1)): v for k, v in json.load(f).items()}
    errors = []
    merged = {}
    for key, want in sorted(expected.items()):
        got = actual.get(key)
        if want is None:
            if got is not None and not got.startswith("unconnected-"):
                errors.append(f"{key[0]}.{key[1]}: should be unconnected, is on {got}")
            continue
        if got is None:
            errors.append(f"{key[0]}.{key[1]}: missing from netlist (want {want})")
        elif got.split("/")[-1] != want:
            errors.append(f"{key[0]}.{key[1]}: want {want}, got {got}")
        else:
            merged.setdefault(got, set()).add(want)
    for key in sorted(set(actual) - set(expected)):
        errors.append(f"{key[0]}.{key[1]}: in netlist but not expected ({actual[key]})")
    single = {}
    for key, want in expected.items():
        if want is not None:
            single.setdefault(want, []).append(key)
    lonely = sorted(n for n, pins in single.items() if len(pins) == 1)
    comps = len({r for r, _ in expected})
    print(f"netlist check: {len(expected)} pins on {comps} parts, {len(single)} nets, {len(errors)} errors")
    for e in errors[:60]:
        print("  ERROR", e)
    if lonely:
        print("  nets with a single pin:", ", ".join(lonely))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
