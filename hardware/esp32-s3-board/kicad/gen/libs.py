"""Load symbols from the installed KiCad libraries and flatten derived symbols."""
import copy
import os

from sexpr import Sym, find, first, parse

SYMDIR = "/usr/share/kicad/symbols"
# Libraries kept in the repository (lib name -> file), for parts the installed KiCad libraries do not have.
EXTRA = {"Espressif": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "espressif",
                                   "ESP32-S31-WROOM-1U.kicad_sym")}
_cache = {}


def _lib(lib):
    if lib not in _cache:
        path = EXTRA.get(lib, os.path.join(SYMDIR, lib + ".kicad_sym"))
        with open(path, encoding="utf-8") as f:
            tree = parse(f.read())
        _cache[lib] = {s[1]: s for s in find(tree, "symbol")}
    return _cache[lib]


def load(lib_id):
    """Return a flattened symbol node named 'Lib:Name'."""
    lib, name = lib_id.split(":")
    sym = copy.deepcopy(_lib(lib)[name])
    ext = first(sym, "extends")
    if ext is not None:
        parent = copy.deepcopy(load(lib + ":" + ext[1]))
        pname = ext[1]
        props = {p[1]: p for p in find(sym, "property")}
        out = []
        for item in parent:
            if isinstance(item, list) and item[0] == "property" and item[1] in props:
                out.append(props.pop(item[1]))
            elif isinstance(item, list) and item[0] == "symbol":
                item[1] = name + item[1][len(pname):]
                out.append(item)
            else:
                out.append(item)
        # extra properties defined only by the child go before the first unit
        idx = next((i for i, it in enumerate(out) if isinstance(it, list) and it[0] == "symbol"), len(out))
        for p in props.values():
            out.insert(idx, p)
            idx += 1
        sym = out
    sym[1] = lib_id
    return sym


def numbers(number):
    """Pad numbers of one pin: KiCad 10 writes several pads on one pin as '[1,40,41]'."""
    if number.startswith("[") and number.endswith("]"):
        return [n.strip() for n in number[1:-1].split(",")]
    return [number]


def pins(sym):
    """List of dicts: number, name, x, y, angle, length, etype, unit."""
    res = []
    for unit in find(sym, "symbol"):
        unit_no = int(unit[1].rsplit("_", 2)[1])
        for p in find(unit, "pin"):
            at = first(p, "at")
            res.append(dict(
                number=first(p, "number")[1], name=first(p, "name")[1],
                x=float(at[1]), y=float(at[2]), angle=int(float(at[3])) if len(at) > 3 else 0,
                length=float(first(p, "length")[1]), etype=str(p[1]), unit=unit_no,
                hidden=any(isinstance(t, Sym) and t == "hide" for t in p) or (first(p, "hide") or [0, Sym("no")])[1] == "yes",
            ))
    return res
