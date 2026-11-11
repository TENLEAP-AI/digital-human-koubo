"""Build the PCB from build/parts.json: outline, screw holes, nets and footprints.

Main parts are placed from the PLACE table; everything else is parked below the board.
Run with the Python that has pcbnew:   /usr/bin/python3.12 board.py [output_dir]

Coordinates are in millimetres from the top-left corner of the board seen from the front,
X to the right, Y down - the same frame as the reference-board measurements.
"""
import json
import math
import os
import sys

import pcbnew

from place import EXACT, GROUPS, MAIN
from sexpr import find, first, parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")
NAME = "zeebuddy-mainboard"
PLUG = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP)
MM = pcbnew.FromMM
OX, OY = 100.0, 60.0          # where the board's top-left corner sits on the KiCad page
SYSLIB = "/usr/share/kicad/footprints"
W, H = 64.0, 34.0


def V(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


# ---- outline of the reference board (64 x 34 mm; ours is 1.6 mm thick, six layers) --------------------------------
# ("L", x, y) = line to; ("A", cx, cy, x, y) = arc around (cx, cy) to (x, y), short way round.
OUTLINE_START = (1.5, 0.0)
OUTLINE = [
    ("L", 64.0, 0.0), ("L", 64.0, 29.5),
    ("A", 62.5, 29.5, 62.86, 30.96), ("A", 63.1, 31.93, 62.1, 31.93), ("L", 62.1, 32.0),
    ("A", 60.1, 32.0, 60.1, 34.0), ("L", 3.9, 34.0),
    ("A", 3.9, 32.0, 1.9, 32.0), ("L", 1.9, 31.93),
    ("A", 0.9, 31.93, 1.14, 30.96), ("A", 1.5, 29.5, 0.0, 29.5), ("L", 0.0, 3.0),
    ("A", 0.0, 1.5, 1.5, 1.5), ("L", 1.5, 0.0),
]
HOLE_NPTH = (62.2, 1.2)                                   # too close to the edge for a copper ring
HOLES = [(2.0, 14.5), (3.7, 32.0), (60.3, 32.0)]            # grounded ring

# ---- basic rules for a multilayer board at JLC (docs/layout-spec.md, GEN-1..7) -------------------------
RULES = {"min_clearance": 0.09, "min_track_width": 0.09, "min_copper_edge_clearance": 0.3,
         "min_through_hole_diameter": 0.2, "min_via_diameter": 0.4, "min_via_annular_width": 0.075,
         "min_hole_clearance": 0.2}
DEFAULT_CLASS = {"clearance": 0.1, "track_width": 0.15, "via_diameter": 0.45, "via_drill": 0.2,
                 "diff_pair_width": 0.15, "diff_pair_gap": 0.15}
# wider tracks for supply nets and the antenna line; used by KiCad and by an external autorouter
NET_CLASSES = {
    "PowerHi": (dict(track_width=0.6, via_diameter=0.6, via_drill=0.3),
                ["VBAT", "VSYS", "VDD_4G", "CHG_SW", "CHG_PMID"]),
    "Vbus": (dict(track_width=1.0, via_diameter=0.6, via_drill=0.3), ["VBUS"]),      # PWR-9
    "Power": (dict(track_width=0.3, via_diameter=0.5, via_drill=0.25),
              ["+3V3", "+2V8", "+1V2", "BUCK_SW", "BL_SW", "LCD_LEDA", "LCD_LEDK", "CHG_REGN", "CHG_BTST", "SIM_VDD",
               "LCD_VCI", "CAMF_IOVDD", "CAMF_DVDD", "GND"]),
    "Speaker": (dict(track_width=0.4, via_diameter=0.5, via_drill=0.25),                # PWR-17
                ["PA_OUTP", "PA_OUTN", "SPK_P", "SPK_N"]),
    # antenna line on the back over In4 (7628 prepreg, about 0.21 mm): 0.34 mm wide, 0.2 mm to the ground
    # beside it; USB pairs 0.19 / 0.15. Design values of layout-spec.md 5.1 and USB-1, to be confirmed
    # with the fab's impedance calculator.
    "RF": (dict(track_width=0.34, clearance=0.2), ["LTE_ANT", "LTE_ANT_C"]),
    "USB": (dict(track_width=0.19, diff_pair_width=0.19, diff_pair_gap=0.15),
            ["USBC_DP", "USBC_DM", "ESP_DP", "ESP_DM", "ESP_USB_DP", "ESP_USB_DM", "LTE_USB_DP", "LTE_USB_DM"]),
}

def arc_mid(cx, cy, x0, y0, x1, y1):
    a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
    d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    r = math.hypot(x0 - cx, y0 - cy)
    return cx + r * math.cos(a0 + d / 2), cy + r * math.sin(a0 + d / 2)


def draw_outline(board):
    x, y = OUTLINE_START
    for seg in OUTLINE:
        s = pcbnew.PCB_SHAPE(board)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        if seg[0] == "L":
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x, y))
            s.SetEnd(V(seg[1], seg[2]))
            x, y = seg[1], seg[2]
        else:
            _, cx, cy, ex, ey = seg
            mx, my = arc_mid(cx, cy, x, y, ex, ey)
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetArcGeometry(V(x, y), V(mx, my), V(ex, ey))
            x, y = ex, ey
        board.Add(s)


def load_footprint(fpid):
    lib, name = fpid.split(":", 1)
    path = os.path.join(OUT, lib + ".pretty") if lib == "zeebuddy" else os.path.join(SYSLIB, lib + ".pretty")
    fp = PLUG.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def pose(fp, x, y, rot, side):
    """Put a footprint at (x, y); rot 0 = upright as seen from the front, on either side."""
    on_back = fp.GetLayer() == pcbnew.B_Cu
    fp.SetOrientationDegrees(0)
    fp.SetPosition(V(x, y))
    if (side == "B") != on_back:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # on the back, KiCad's own angle is 180 for a part that is upright when seen from the front
    fp.SetOrientationDegrees(rot + 180 if side == "B" else rot)


def keepouts_on_own_side(board):
    """A library footprint may carry a keep-out on every copper layer (the U.FL socket does). Under a part
    on this board a keep-out only makes sense on the side the part sits on; on the other layers it would
    cut holes into the ground planes and forbid tracks that have nothing to do with the part."""
    n = 0
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if z.GetIsRuleArea() and sum(1 for l in z.GetLayerSet().Seq() if pcbnew.IsCopperLayer(l)) > 1:
                own = pcbnew.LSET()
                own.AddLayer(fp.GetLayer())
                z.SetLayerSet(own)
                n += 1
    return n


def bbox_mm(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd)
    bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
            pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)


def main():
    with open(os.path.join(OUT, "build", "parts.json"), encoding="utf-8") as f:
        parts = json.load(f)

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)       # F, In1 = GND, In2 = signal, In3 = power + signal, In4 = GND, B
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    ds.SetAuxOrigin(V(0, 0))
    draw_outline(board)

    # pad nets come from the netlist KiCad exported, so they carry KiCad's own names,
    # including the "unconnected-(...)" nets it gives to pins that are deliberately left open
    with open(os.path.join(OUT, "build", NAME + ".net"), encoding="utf-8") as f:
        netlist = parse(f.read())
    pad_net, nets = {}, {}
    for n in find(first(netlist, "nets"), "net"):
        name = first(n, "name")[1]
        nets[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(nets[name])
        for node in find(n, "node"):
            pad_net[(first(node, "ref")[1], first(node, "pin")[1])] = name

    problems, placed, summary, loaded = [], {}, [], {}
    holes = list(HOLES)
    park = {}
    for ref in sorted(parts, key=lambda r: (parts[r]["sheetfile"], "".join(c for c in r if c.isalpha()),
                                             int("".join(c for c in r if c.isdigit()) or 0))):
        info = parts[ref]
        fp = load_footprint(info["footprint"])
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetPath(pcbnew.KIID_PATH(f"/{info['sheet']}/{info['uuid']}"))
        fp.SetSheetfile(info["sheetfile"])
        fp.SetSheetname("/" + info["sheetname"] + "/")
        if info["dnp"]:
            fp.SetDNP(True)
        # the board is too dense for designators on the silkscreen: keep them on the fabrication layer
        fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(MM(0.5), MM(0.5)))
        fp.Reference().SetTextThickness(MM(0.08))
        fp.Value().SetVisible(False)
        board.Add(fp)

        pad_names = {p.GetNumber() for p in fp.Pads()}
        for pin, net in info["pins"].items():
            if pin not in pad_names:
                problems.append(f"{ref} ({info['footprint']}): no pad '{pin}' for net {net}")
        for pad in fp.Pads():
            net = pad_net.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        extra = sorted(n for n in pad_names - set(info["pins"]) if n)
        if extra:
            problems.append(f"{ref} ({info['footprint']}): pads without a schematic pin: {' '.join(extra)}")

        spot = EXACT.get(ref) or MAIN.get(info["value"]) or MAIN.get(info["footprint"])
        if info["footprint"] == "zeebuddy:MountingHole_1.6mm_Pad":
            spot = holes.pop(0) + (0, "F")
        elif info["footprint"] == "zeebuddy:MountingHole_1.6mm_NPTH":
            spot = HOLE_NPTH + (0, "F")
        loaded[ref] = fp
        if spot:
            pose(fp, *spot)
            placed[ref] = fp
            summary.append((ref, info["value"], spot[3]) + bbox_mm(fp))

    # small parts: pack each group's rows left to right, rows stacked downwards
    for side, gx, gy, rows, *gaps in GROUPS:
        gap, row_gap = gaps if gaps else (0.3, 0.5)
        y = gy
        for row in rows:
            x, row_h = gx, 0.0
            for item in row.split():
                ref, _, rot = item.partition("@")
                rot = int(rot or 0)
                if ref not in loaded:
                    raise SystemExit(f"placement: unknown reference {ref}")
                if ref in placed:
                    raise SystemExit(f"placement: {ref} is placed twice")
                fp = loaded[ref]
                pose(fp, 0, 0, rot, side)
                l, t, r, b = bbox_mm(fp)
                pose(fp, x - l, y - t, rot, side)
                x += (r - l) + gap
                row_h = max(row_h, b - t)
                placed[ref] = fp
            y += row_h + row_gap
    for ref, fp in loaded.items():
        if ref not in placed:
            park.setdefault(parts[ref]["sheetname"], []).append(fp)

    # park the rest below the board, one block per schematic sheet
    y0 = H + 12.0
    for sheet, fps in park.items():
        label = pcbnew.PCB_TEXT(board)
        label.SetText(f"未摆放：{sheet}")
        label.SetLayer(pcbnew.Cmts_User)
        label.SetPosition(V(-2, y0 - 2.2))
        label.SetTextSize(pcbnew.VECTOR2I(MM(1.2), MM(1.2)))
        label.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        board.Add(label)
        x, row_h = 0.0, 0.0
        for fp in fps:
            fp.SetPosition(V(0, 0))
            l, t, r, b = bbox_mm(fp)
            w, h = r - l + 0.8, b - t + 0.8
            if x + w > 110:
                x, y0, row_h = 0.0, y0 + row_h, 0.0
            fp.SetPosition(V(x - l + 0.4, y0 - t + 0.4))
            x += w
            row_h = max(row_h, h)
        y0 += row_h + 6.0

    keepouts_on_own_side(board)
    path = os.path.join(OUT, NAME + ".kicad_pcb")
    pcbnew.SaveBoard(path, board)
    pro = os.path.join(OUT, NAME + ".kicad_pro")
    with open(pro, encoding="utf-8") as f:
        project = json.load(f)
    project["board"]["design_settings"]["rules"].update(RULES)
    project["board"]["design_settings"]["rule_severities"].update(
        {"silk_overlap": "ignore", "silk_over_copper": "ignore", "silk_edge_clearance": "ignore",
         "text_height": "ignore", "text_thickness": "ignore",
         # The footprints are written into the board by footprints.py / board.py. Whether a KiCad installation
         # has the same footprint in its own libraries says nothing about this board: another KiCad version
         # reports dozens of these. The one footprint changed on purpose (J7: its keep-out only on the back) is
         # in the README.
         "lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore"})
    default = project["net_settings"]["classes"][0]
    default.update(DEFAULT_CLASS)
    classes, patterns = [default], []
    for cname, (values, members) in NET_CLASSES.items():
        classes.append(dict(default, name=cname, priority=len(classes) - 1, **values))
        patterns += [{"netclass": cname, "pattern": n} for n in members]
    project["net_settings"]["classes"] = classes
    project["net_settings"]["netclass_patterns"] = patterns
    with open(pro, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(OUT, "build", "placement.json"), "w", encoding="utf-8") as f:
        json.dump([dict(ref=r, value=v, side=s, x1=round(a, 2), y1=round(b, 2), x2=round(c, 2), y2=round(d, 2))
                   for r, v, s, a, b, c, d in summary], f, ensure_ascii=False, indent=0)
    named = sum(1 for n in nets if not n.startswith("unconnected-"))
    print(f"board: {len(parts)} footprints, {len(placed)} placed, {named} nets -> {os.path.basename(path)}")
    for p in problems:
        print("  CHECK", p)
    for fpid, key, what in (("zeebuddy:Air780E", "35", "Air780E antenna pad"),
                            ("RF_Module:ESP32-S3-WROOM-1U", "1", "ESP32 module pad 1"),
                            ("Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical", "1", "antenna socket centre pad")):
        for ref, fp in placed.items():
            if parts[ref]["footprint"] != fpid:
                continue
            for pad in fp.Pads():
                if pad.GetNumber() == key:
                    pos = pad.GetPosition()
                    print(f"  {what} at ({pcbnew.ToMM(pos.x) - OX:.2f}, {pcbnew.ToMM(pos.y) - OY:.2f})")
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main())
