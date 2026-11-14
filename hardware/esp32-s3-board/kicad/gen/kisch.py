"""Small schematic generator for KiCad 9.

Every pin gets a short stub that ends in a global net label or a power symbol,
so connectivity is by net name and net names are global to the project. The generator records which net every pin is
meant to be on; verify.py compares that with the netlist KiCad exports.
"""
import copy
import json
import math
import os
import uuid

import libs
from sexpr import Sym, dump, find, first

S = Sym
NS = uuid.UUID("6f1d2c1e-3b6a-4a55-9f0e-5a2f5c0d7e11")
FONT = [S("font"), [S("size"), 1.27, 1.27]]
PROJECT_LIB = "zeebuddy"

# Nets drawn with a power symbol on vertical pins. Value: (lib_id, points_up)
POWER = {
    "GND": ("power:GND", False),
    "+3V3": ("power:+3V3", True),
    "VBUS": ("power:VBUS", True),
}


def uid(*key):
    return str(uuid.uuid5(NS, "/".join(str(k) for k in key)))


def effects(justify=None, hide=False, size=1.27):
    e = [S("effects"), [S("font"), [S("size"), size, size]]]
    if justify:
        e.append([S("justify")] + [S(j) for j in justify.split()])
    if hide:
        e.append([S("hide"), S("yes")])
    return e


def kicad10(node):
    """KiCad 10 files keep a property's (hide yes) on the property itself, not inside its (effects): move it there.
    Older-format symbols copied from libraries get the same treatment."""
    if isinstance(node, list):
        for item in node:
            kicad10(item)
        if node and node[0] == "property":
            for k, item in enumerate(node):
                if isinstance(item, list) and item and item[0] == "effects":
                    def is_hide(e):
                        return isinstance(e, list) and e and e[0] == "hide"
                    if any(is_hide(e) for e in item):
                        node[k] = [e for e in item if not is_hide(e)]      # (effects) lists may be shared
                        if not any(is_hide(e) for e in node):
                            node.insert(k, [S("hide"), S("yes")])
                    break
    return node


def rot_vec(dx, dy, rot):
    """Rotate a screen-space vector counter-clockwise (screen Y points down)."""
    rot %= 360
    if rot == 0:
        return dx, dy
    if rot == 90:
        return dy, -dx
    if rot == 180:
        return -dx, -dy
    return -dy, dx


def r2(v):
    return round(v + 0.0, 4)


def snap(v, grid=2.54):
    return r2(round(v / grid) * grid)


def box_symbol(name, ref, left, right, fp="", desc="", datasheet="~", pinlen=2.54, minw=0.0, hidden_nc=()):
    """Build a rectangular symbol.

    left/right: lists of (number, name[, etype]) or None for a gap. `number` may be a list:
    the first pin is drawn, the others are hidden passive pins stacked on it (same net).
    hidden_nc: pad numbers that must stay unconnected; added as hidden no-connect pins.
    """
    def width_of(side):
        return max([len(p[1]) for p in side if p] or [0])

    w = max((width_of(left) + width_of(right) + 4) * 1.0, minw, len(name) * 1.0 + 2)
    w = math.ceil(w / 5.08) * 5.08
    rows = max(len(left), len(right))
    h = (rows + 1) * 2.54
    x0, y0 = -w / 2, h / 2
    unit0 = [S("symbol"), f"{name}_0_1",
             [S("rectangle"), [S("start"), r2(x0), r2(y0)], [S("end"), r2(-x0), r2(-y0)],
              [S("stroke"), [S("width"), 0.254], [S("type"), S("default")]],
              [S("fill"), [S("type"), S("background")]]]]
    unit1 = [S("symbol"), f"{name}_1_1"]

    def pin(number, pname, etype, x, y, ang, hide=False, length=pinlen):
        node = [S("pin"), S(etype), S("line"), [S("at"), r2(x), r2(y), ang], [S("length"), length]]
        if hide:
            node.append([S("hide"), S("yes")])
        node += [[S("name"), pname, effects()], [S("number"), str(number), effects()]]
        unit1.append(node)

    for side, x, ang in ((left, x0 - pinlen, 0), (right, -x0 + pinlen, 180)):
        for i, p in enumerate(side):
            if not p:
                continue
            etype = p[2] if len(p) > 2 else "passive"
            numbers = p[0] if isinstance(p[0], (list, tuple)) else [p[0]]
            y = y0 - 2.54 * (i + 1)
            pin(numbers[0], p[1], etype, x, y, ang)
            for extra in numbers[1:]:
                pin(extra, p[1], "passive", x, y, ang, hide=True)
    cols = max(1, int(w / 2.54) - 1)
    for i, number in enumerate(hidden_nc):
        pin(number, "NC", "no_connect", x0 + 2.54 * (i % cols + 1), -y0 + 1.27 * (i // cols + 1), 90,
            hide=True, length=0)
    sym = [S("symbol"), f"{PROJECT_LIB}:{name}",
           [S("pin_names"), [S("offset"), 0.762]],
           [S("exclude_from_sim"), S("no")], [S("in_bom"), S("yes")], [S("on_board"), S("yes")],
           [S("property"), "Reference", ref, [S("at"), r2(x0), r2(y0 + 1.27), 0], effects("left bottom")],
           [S("property"), "Value", name, [S("at"), r2(x0), r2(-y0 - 1.27), 0], effects("left top")],
           [S("property"), "Footprint", fp, [S("at"), 0, 0, 0], effects(hide=True)],
           [S("property"), "Datasheet", datasheet, [S("at"), 0, 0, 0], effects(hide=True)],
           [S("property"), "Description", desc, [S("at"), 0, 0, 0], effects(hide=True)],
           unit0, unit1, [S("embedded_fonts"), S("no")]]
    return sym


def power_symbol(net, up=True):
    base = copy.deepcopy(libs.load("power:+3V3" if up else "power:GND"))
    old = "+3V3" if up else "GND"
    base[1] = f"{PROJECT_LIB}:{net}"
    for item in base:
        if isinstance(item, list) and item[0] == "symbol":
            item[1] = net + item[1][len(old):]
        if isinstance(item, list) and item[0] == "property" and item[1] in ("Value", "Description"):
            item[2] = item[2].replace(old, net)
    return base


class Design:
    def __init__(self, name, title, rev, date, company=""):
        self.name, self.title, self.rev, self.date, self.company = name, title, rev, date, company
        self.root_uuid = uid("root", name)
        self.sheets = []
        self.refs = {}
        self.custom = {}
        self.expect = {}      # (ref, pin) -> net name, or None for no-connect
        self.parts = {}       # ref -> symbol uuid, sheet, footprint ... (used to build the PCB)
        self.net_sheets = {}  # net -> set of sheet names
        self.root_text = []

    def define(self, sym):
        """Register a project-library symbol built with box_symbol()/power_symbol()."""
        self.custom[sym[1]] = sym
        return sym[1]

    def rail(self, net, up=True):
        POWER[net] = (self.define(power_symbol(net, up)), up)

    def symbol(self, lib_id):
        if lib_id in self.custom:
            return self.custom[lib_id]
        return libs.load(lib_id)

    def next_ref(self, prefix):
        self.refs[prefix] = self.refs.get(prefix, 0) + 1
        return f"{prefix}{self.refs[prefix]}"

    def sheet(self, fname, title, paper="A3"):
        sh = Sheet(self, fname, title, paper, page=len(self.sheets) + 2)
        self.sheets.append(sh)
        return sh

    # ---- output -----------------------------------------------------------
    def write(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        for sh in self.sheets:
            with open(os.path.join(outdir, sh.fname), "w", encoding="utf-8") as f:
                f.write(dump(kicad10(sh.render())) + "\n")
        with open(os.path.join(outdir, self.name + ".kicad_sch"), "w", encoding="utf-8") as f:
            f.write(dump(kicad10(self.render_root())) + "\n")
        lib = [S("kicad_symbol_lib"), [S("version"), 20251024], [S("generator"), "zeebuddy_gen"],
               [S("generator_version"), "10.0"]]
        for lib_id, sym in sorted(self.custom.items()):
            s = copy.deepcopy(sym)
            s[1] = lib_id.split(":", 1)[1]
            lib.append(s)
        with open(os.path.join(outdir, PROJECT_LIB + ".kicad_sym"), "w", encoding="utf-8") as f:
            f.write(dump(kicad10(lib)) + "\n")
        with open(os.path.join(outdir, "sym-lib-table"), "w", encoding="utf-8") as f:
            f.write('(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")'
                    '(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Project symbols"))\n'
                    '  (lib (name "Espressif")(type "KiCad")'
                    '(uri "${KIPRJMOD}/lib/espressif/ESP32-S31-WROOM-1U.kicad_sym")(options "")'
                    '(descr "Espressif official library (only the parts this board uses)"))\n)\n'
                    % (PROJECT_LIB, PROJECT_LIB))
        pro = os.path.join(outdir, self.name + ".kicad_pro")
        if not os.path.exists(pro):
            with open(pro, "w", encoding="utf-8") as f:
                json.dump({"meta": {"filename": self.name + ".kicad_pro", "version": 3}}, f, indent=2)
        os.makedirs(os.path.join(outdir, "build"), exist_ok=True)
        with open(os.path.join(outdir, "build", "expected_nets.json"), "w", encoding="utf-8") as f:
            json.dump({f"{r}.{p}": n for (r, p), n in sorted(self.expect.items())}, f, indent=0,
                      ensure_ascii=False)
        parts = {ref: dict(info, pins={p: n for (r, p), n in self.expect.items() if r == ref})
                 for ref, info in self.parts.items()}
        with open(os.path.join(outdir, "build", "parts.json"), "w", encoding="utf-8") as f:
            json.dump(parts, f, indent=0, ensure_ascii=False)

    def title_block(self, title):
        return [S("title_block"), [S("title"), title], [S("date"), self.date], [S("rev"), self.rev],
                [S("company"), self.company]]

    def render_root(self):
        root = [S("kicad_sch"), [S("version"), 20260306], [S("generator"), "eeschema"],
                [S("generator_version"), "10.0"], [S("uuid"), self.root_uuid], [S("paper"), "A4"],
                self.title_block(self.title), [S("lib_symbols")]]
        for i, (x, y, text, size) in enumerate(self.root_text):
            root.append([S("text"), text, [S("exclude_from_sim"), S("no")], [S("at"), x, y, 0],
                         effects("left top", size=size), [S("uuid"), uid("roottext", i)]])
        cols = 3
        for i, sh in enumerate(self.sheets):
            x = 25.4 + (i % cols) * 81.28
            y = 40.64 + (i // cols) * 30.48
            root.append([
                S("sheet"), [S("at"), x, y], [S("size"), 60.96, 15.24],
                [S("exclude_from_sim"), S("no")], [S("in_bom"), S("yes")], [S("on_board"), S("yes")],
                [S("dnp"), S("no")],
                [S("stroke"), [S("width"), 0.1524], [S("type"), S("solid")]],
                [S("fill"), [S("color"), 0, 0, 0, 0.0]],
                [S("uuid"), sh.uuid],
                [S("property"), "Sheetname", sh.title, [S("at"), x, r2(y - 0.7), 0], effects("left bottom")],
                [S("property"), "Sheetfile", sh.fname, [S("at"), x, r2(y + 15.24 + 0.6), 0],
                 effects("left top")],
                [S("instances"), [S("project"), self.name,
                                  [S("path"), "/" + self.root_uuid, [S("page"), str(sh.page)]]]],
            ])
        root.append([S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]])
        root.append([S("embedded_fonts"), S("no")])
        return root


class Sheet:
    def __init__(self, design, fname, title, paper, page):
        self.d, self.fname, self.title, self.paper, self.page = design, fname, title, paper, page
        self.uuid = uid("sheet", fname)
        self.items = []
        self.libsyms = {}
        self.pending = []   # (net, x, y, angle) labels, resolved to local/global at render time
        self.n = 0

    def _u(self, kind):
        self.n += 1
        return uid(self.fname, kind, self.n)

    # ---- primitives -------------------------------------------------------
    def wire(self, x1, y1, x2, y2):
        if (r2(x1), r2(y1)) == (r2(x2), r2(y2)):
            return
        self.items.append([S("wire"), [S("pts"), [S("xy"), r2(x1), r2(y1)], [S("xy"), r2(x2), r2(y2)]],
                           [S("stroke"), [S("width"), 0], [S("type"), S("default")]],
                           [S("uuid"), self._u("wire")]])

    def text(self, x, y, text, size=1.5):
        self.items.append([S("text"), text, [S("exclude_from_sim"), S("no")], [S("at"), r2(x), r2(y), 0],
                           effects("left top", size=size), [S("uuid"), self._u("text")]])

    def frame(self, x1, y1, x2, y2, title=None):
        self.items.append([S("rectangle"), [S("start"), r2(x1), r2(y1)], [S("end"), r2(x2), r2(y2)],
                           [S("stroke"), [S("width"), 0.15], [S("type"), S("dash")]],
                           [S("fill"), [S("type"), S("none")]], [S("uuid"), self._u("rect")]])
        if title:
            self.text(x1 + 1.5, y1 + 1.5, title, size=2.0)

    def noconnect(self, x, y):
        self.items.append([S("no_connect"), [S("at"), r2(x), r2(y)], [S("uuid"), self._u("nc")]])

    def label(self, net, x, y, angle):
        self.d.net_sheets.setdefault(net, set()).add(self.fname)
        self.pending.append((net, r2(x), r2(y), angle))

    def _power(self, net, x, y, rot):
        lib_id, _ = POWER[net]
        self.d.net_sheets.setdefault(net, set()).update({self.fname, "*power*"})
        self._instance(lib_id, x, y, rot, self.d.next_ref("#PWR"), net, None, {}, power=True)

    def attach(self, net, x, y, dx, dy, stub=2.54, vertical_power=True):
        """Draw a stub from a pin end at (x, y) in direction (dx, dy) and terminate it on `net`."""
        ex, ey = x + dx * stub, y + dy * stub
        self.wire(x, y, ex, ey)
        if net in POWER and vertical_power and dx == 0:
            up = POWER[net][1]
            if (up and dy < 0) or (not up and dy > 0):
                self._power(net, ex, ey, 0)
                return
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        self.label(net, ex, ey, angle)

    def flag(self, x, y, net):
        """PWR_FLAG on a rail, so ERC knows the net is driven."""
        x, y = snap(x), snap(y)
        self._instance("power:PWR_FLAG", x, y, 0, self.d.next_ref("#FLG"), "PWR_FLAG", None, {}, power=True)
        self.wire(x, y, x + 10.16, y)
        self.attach(net, x + 10.16, y, 0, 1 if net == "GND" else -1, stub=0 if net in POWER else 2.54)

    # ---- symbols ----------------------------------------------------------
    def _instance(self, lib_id, x, y, rot, ref, value, fp, fields, power=False, dnp=False, prop_pos=None,
                  in_bom=True):
        sym = self.d.symbol(lib_id)
        self.libsyms[lib_id] = sym
        sym_uuid = self._u("sym")
        node = [S("symbol"), [S("lib_id"), lib_id], [S("at"), r2(x), r2(y), rot], [S("unit"), 1],
                [S("exclude_from_sim"), S("no")], [S("in_bom"), S("no" if power or not in_bom else "yes")],
                [S("on_board"), S("yes")], [S("dnp"), S("yes" if dnp else "no")],
                [S("uuid"), sym_uuid]]
        info = dict(uuid=sym_uuid, sheet=self.uuid, sheetname=self.title, sheetfile=self.fname,
                    lib_id=lib_id, value=value, dnp=dnp, footprint="")
        for prop in find(sym, "property"):
            name = prop[1]
            if name.startswith("ki_"):
                continue
            val = prop[2]
            if name == "Reference":
                val = ref
            elif name == "Value":
                val = value
            elif name == "Footprint" and fp is not None:
                val = fp
            if name == "Footprint":
                info["footprint"] = val
            at = first(prop, "at")
            px, py, pa = float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0
            eff = copy.deepcopy(first(prop, "effects"))
            if prop_pos and name in prop_pos:
                if prop_pos[name] is None:
                    ax, ay, eff = x, y, effects(hide=True)
                else:
                    ax, ay, pa, just = prop_pos[name]
                    eff = effects(just)
            else:
                ddx, ddy = rot_vec(px, -py, rot)
                ax, ay = x + ddx, y + ddy
            pnode = [S("property"), name, val, [S("at"), r2(ax), r2(ay), pa]]
            if first(prop, "hide") is not None and first(prop, "hide")[1] == "yes" \
                    and not (prop_pos and name in prop_pos and prop_pos[name] is not None):
                pnode.append([S("hide"), S("yes")])     # KiCad 10 libraries mark hidden fields on the property
            node.append(pnode + [eff])
        for k, v in fields.items():
            node.append([S("property"), k, v, [S("at"), r2(x), r2(y), 0], effects(hide=True)])
        for p in libs.pins(sym):
            node.append([S("pin"), p["number"], [S("uuid"), self._u("pin")]])
        node.append([S("instances"), [S("project"), self.d.name,
                                      [S("path"), f"/{self.d.root_uuid}/{self.uuid}",
                                       [S("reference"), ref], [S("unit"), 1]]]])
        self.items.append(node)
        if not power:
            self.d.parts[ref] = info
        return sym

    def place(self, lib_id, x, y, nets, value=None, ref=None, rot=0, fp=None, nc=(), stub=2.54,
              dnp=False, fields=None, prop_pos=None, in_bom=True):
        """Place a symbol. nets maps pin number or pin name -> net. nc lists unconnected pins
        ('*' = every pin not in nets)."""
        x, y = snap(x), snap(y)
        sym = self.d.symbol(lib_id)
        pins = libs.pins(sym)
        if any(p["unit"] > 1 for p in pins):
            raise ValueError(f"{lib_id}: multi-unit symbols are not supported")
        prefix = first([p for p in find(sym, "property") if p[1] == "Reference"], "property")[2]
        ref = ref or self.d.next_ref(prefix)
        if value is None:
            value = [p for p in find(sym, "property") if p[1] == "Value"][0][2]
        self._instance(lib_id, x, y, rot, ref, value + (" (不贴)" if dnp else ""), fp, fields or {},
                       dnp=dnp, prop_pos=prop_pos, in_bom=in_bom)
        numbers = {p["number"] for p in pins}
        names = {p["name"] for p in pins}
        for key in list(nets) + [k for k in nc if k != "*"]:
            if str(key) not in numbers and key not in names:
                raise KeyError(f"{ref} ({lib_id}): no pin '{key}'")
        drawn = set()
        for p in pins:
            if p["number"] in nets:
                net = nets[p["number"]]
            elif p["name"] in nets and p["name"] not in numbers:
                net = nets[p["name"]]
            elif p["number"] in nc or p["name"] in nc or "*" in nc:
                net = None
            else:
                raise KeyError(f"{ref} ({lib_id}): pin {p['number']} '{p['name']}' has no net and is not in nc")
            for n in libs.numbers(p["number"]):
                if (ref, n) in self.d.expect:
                    raise KeyError(f"duplicate reference {ref}")
                self.d.expect[(ref, n)] = net
            ddx, ddy = rot_vec(p["x"], -p["y"], rot)
            px, py = r2(x + ddx), r2(y + ddy)
            a = math.radians(p["angle"])
            ox, oy = rot_vec(-round(math.cos(a)), round(math.sin(a)), rot)
            if net is None:
                if p["etype"] != "no_connect" and (px, py) not in drawn:
                    self.noconnect(px, py)
                    drawn.add((px, py))
                continue
            if (px, py, net) in drawn:
                continue
            drawn.add((px, py, net))
            self.attach(net, px, py, ox, oy, stub=stub)
        return ref

    # ---- two-pin helpers --------------------------------------------------
    def two(self, lib_id, x, y, a, b, value, horizontal=False, fp=None, dnp=False, ref=None, stub=2.54):
        """Two-pin part. Vertical: pin 1 (net a) on top. Horizontal: pin 1 (net a) on the left."""
        x, y = snap(x), snap(y)
        if horizontal:
            off = 3.3 if lib_id.startswith(("Device:C", "Device:FerriteBead")) else 2.54
            pos = {"Reference": (x, y - off, 90, None), "Value": (x, y + off, 90, None)}
            rot = 90
        else:
            pos = {"Reference": (x + 2.3, y - 1.1, 0, "left"), "Value": (x + 2.3, y + 1.1, 0, "left")}
            rot = 0
        return self.place(lib_id, x, y, {"1": a, "2": b}, value=value, rot=rot, fp=fp, dnp=dnp, ref=ref,
                          prop_pos=pos, stub=stub)

    def R(self, x, y, a, b, value, horizontal=False, dnp=False, fp="Resistor_SMD:R_0402_1005Metric"):
        return self.two("Device:R", x, y, a, b, value, horizontal, fp, dnp)

    def C(self, x, y, a, b, value, horizontal=False, dnp=False, fp="Capacitor_SMD:C_0402_1005Metric"):
        return self.two("Device:C", x, y, a, b, value, horizontal, fp, dnp)

    def caps(self, x, y, net, values, gnd="GND", pitch=12.7):
        """Row of decoupling capacitors from `net` to ground. values: list of value or (value, footprint)."""
        for i, v in enumerate(values):
            val, fp = v if isinstance(v, tuple) else (v, None)
            if fp is None:
                big = val.replace("µ", "u").lower()
                fp = "Capacitor_SMD:C_0402_1005Metric"
                if big.endswith("uf") and float(big[:-2].split("u")[0] or 0) >= 4.7:
                    fp = "Capacitor_SMD:C_0603_1608Metric"
            self.C(x + i * pitch, y, net, gnd, val, fp=fp)

    def D(self, x, y, anode, cathode, value, lib_id="Device:D", point="down", fp="Diode_SMD:D_SOD-323",
          dnp=False):
        """Diode-like part (pin 1 = K, pin 2 = A). point: direction of current flow on the page."""
        x, y = snap(x), snap(y)
        rot = {"left": 0, "down": 90, "right": 180, "up": 270}[point]
        if point in ("down", "up"):
            pos = {"Reference": (x + 2.54, y - 1.1, 90, "left"), "Value": (x + 2.54, y + 1.1, 90, "left")}
        else:
            pos = {"Reference": (x, y - 3.0, 0, None), "Value": (x, y + 3.0, 0, None)}
        return self.place(lib_id, x, y, {"1": cathode, "2": anode}, value=value, rot=rot, fp=fp, dnp=dnp,
                          prop_pos=pos)

    def hlist(self, x, y, rows, pitch=7.62):
        """Column of horizontal two-pin parts. rows: (kind, left_net, right_net, value[, 'dnp']).
        kind: R, C, L, FB or a lib_id."""
        kinds = {"R": ("Device:R", "Resistor_SMD:R_0402_1005Metric"),
                 "C": ("Device:C", "Capacitor_SMD:C_0402_1005Metric"),
                 "L": ("Device:L", ""), "FB": ("Device:FerriteBead", "Inductor_SMD:L_0402_1005Metric")}
        refs = []
        prev_cap = False
        for i, row in enumerate(rows):
            if row is None:
                y += pitch
                continue
            kind, a, b, value = row[:4]
            lib_id, fp = kinds.get(kind, (kind, None))
            if len(row) > 5:
                fp = row[5]
            is_cap = lib_id.startswith("Device:C")
            if i and (is_cap or prev_cap):
                y += 2.54          # capacitor symbols are taller than resistors
            prev_cap = is_cap
            refs.append(self.two(lib_id, x, y, a, b, value, horizontal=True, fp=fp,
                                 dnp=len(row) > 4 and row[4] == "dnp"))
            y += pitch
        return refs

    def tp(self, x, y, net, fp="zeebuddy:TestPad_D1.0mm"):
        """Test point; the pad hangs below its net label."""
        x, y = snap(x), snap(y)
        return self.place("Connector:TestPoint", x, y, {"1": net}, value="TP", rot=180, fp=fp, in_bom=False,
                          prop_pos={"Reference": (x + 1.8, y + 3.3, 0, "right"), "Value": None})

    # ---- output -----------------------------------------------------------
    def render(self):
        root = [S("kicad_sch"), [S("version"), 20260306], [S("generator"), "eeschema"],
                [S("generator_version"), "10.0"], [S("uuid"), self.uuid], [S("paper"), self.paper],
                self.d.title_block(self.title)]
        root.append([S("lib_symbols")] + [self.libsyms[k] for k in sorted(self.libsyms)])
        for i, (net, x, y, angle) in enumerate(self.pending):
            just = "left" if angle in (0, 90) else "right"
            root.append([S("global_label"), net, [S("shape"), S("passive")], [S("at"), x, y, angle],
                         effects(just), [S("uuid"), uid(self.fname, "glabel", i)],
                         [S("property"), "Intersheetrefs", "${INTERSHEET_REFS}", [S("at"), x, y, 0],
                          effects(hide=True)]])
        root.extend(self.items)
        root.append([S("embedded_fonts"), S("no")])
        return root
