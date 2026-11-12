"""Copper that is laid by hand: the supply paths, the three switching regulators and their ground returns
(docs/layout-spec.md section 4, and step 3 of section 2: these go in before anything is routed, and are locked).

Coordinates are millimetres from the board's top-left corner as seen from the front, on both sides, like
place.py. The positions belong to the placement in place.py: when a part of these groups moves, the copper
here has to move with it. lay() checks every piece against the pads and against the pieces laid before it,
with the router's own clearance test, and stops when one does not fit.

A wide piece of copper is drawn as a wide track (round ends): an autorouter treats a locked track as an
obstacle, which it does not do reliably for a filled zone.
"""
F, L3, B = 0, 1, 3     # index of the front layer, the inner signal layer and the back layer among the router's layers
TRACKS = []            # (net, layer, width, [(x, y), ...])
VIAS = []              # (net, x, y, diameter, drill, in_pad)


def t(net, layer, width, *pts):
    TRACKS.append((net, layer, width, list(pts)))


def v(net, x, y, dia=0.6, drill=0.3, in_pad=False):
    VIAS.append((net, x, y, dia, drill, in_pad))


# ============================== back ==============================================================
# ---- system supply (VSYS): chip pins 15 / 16 -> neck -> 2 mm strip along y = 6.2 .. 8.2 -> Air780E load switch.
# The strip passes through the supply pads of C5, C6 and L1; the star point of PWR-16 is where the neck meets it:
# the Air780E branch runs right, the vias to the front (amplifier, 3.3 V, backlight) sit at the left end.
t("VSYS", B, 2.0, (6.15, 7.2), (17.36, 7.2))
t("VSYS", B, 0.78, (7.9, 10.2), (7.9, 9.6))                 # on the two pins
t("VSYS", B, 1.1, (7.8, 8.9), (7.8, 8.5))                   # neck, widening away from the pins
for x in (5.45, 6.35):
    for y in (6.7, 7.6):
        v("VSYS", x, y)                                     # PWR-8: four vias to the front trunk
v("VSYS", 16.4, 7.06, 0.45, 0.2)                            # gate pull-up of the load switch (no load current)

# ---- battery (VBAT): pad -> 2 mm band -> BAT pins 13 / 14, C7 on the way
t("VBAT", B, 2.0, (1.85, 10.5), (3.5, 10.5))
t("VBAT", B, 1.5, (3.5, 10.5), (4.65, 9.52))                # the two bands overlap here; this fills the corner
t("VBAT", B, 2.0, (4.65, 9.52), (6.05, 9.52))               # past the corner of the chip, level with the pins
t("VBAT", B, 0.78, (6.9, 9.6), (6.9, 10.2))                 # on the two pins
v("VBAT", 3.9, 9.9, 0.45, 0.2)                              # test pad on the front
t("VBAT", F, 0.3, (3.9, 9.9), (3.5, 8.4))

# ---- charger switch node, bootstrap, REGN, PMID (PWR-12: 2.7 mm of copper from the pins to the inductor)
t("CHG_SW", B, 0.78, (9.83, 11.2), (13.2, 11.2))
t("CHG_BTST", B, 0.25, (9.83, 11.95), (11.05, 12.05))
t("CHG_REGN", B, 0.15, (9.83, 12.45), (10.3, 12.45), (10.5, 12.65), (12.6, 12.65), (13.465, 13.05))
t("CHG_PMID", B, 0.28, (9.83, 12.95), (11.3, 13.2))

# ---- charger ground (PWR-11): PGND pins -> ground pads of the system capacitors, same side, 0.6 mm away;
# PGND and the two grounded control pins -> the pad under the chip; six vias in that pad (PWR-14)
t("GND", B, 0.78, (8.9, 10.2), (8.9, 9.3))
t("GND", B, 0.8, (9.0, 8.91), (10.8, 8.91))
t("GND", B, 0.6, (8.9, 10.3), (8.9, 11.2))
t("GND", B, 0.78, (5.98, 12.7), (6.9, 12.7))
for x, y in ((8.0, 12.2), (7.2, 11.4), (8.8, 11.4), (7.2, 13.0), (8.8, 13.0), (8.0, 11.05)):
    v("GND", x, y, 0.45, 0.2, True)
v("GND", 9.9, 8.91, 0.45, 0.2)                              # between the ground pads of C5 and C6, 0.15 mm from each (GEN-7)
t("GND", B, 0.5, (3.2, 6.9), (4.5, 7.3))                    # battery minus -> ground pad of C7
t("GND", B, 0.25, (3.6, 7.05), (3.6, 7.5))
v("GND", 3.6, 7.5, 0.45, 0.2)                               # clear of TP1, TP3 (front) and of C7, J2 (back) by 0.15 mm
v("GND", 11.3, 16.45, 0.45, 0.2)                            # ground of the PMID capacitor
t("GND", B, 0.4, (11.565, 15.325), (11.3, 16.45))
v("GND", 13.465, 15.55, 0.45, 0.2)                          # ground of the REGN capacitor
t("GND", B, 0.4, (13.465, 14.6), (13.465, 15.55))
v("GND", 10.35, 16.65, 0.45, 0.2)                           # ground of C2 (back) and C11 (front)
t("GND", B, 0.4, (9.3, 17.04), (10.35, 16.65))

# ---- Air780E supply (VDD_4G), PWR-1 / PWR-3: drain of Q1 -> 220 uF -> the two supply pins, all one piece of copper
t("VDD_4G", B, 1.4, (19.5, 7.8), (19.5, 9.6))               # the drain pad is 1.48 mm wide
t("VDD_4G", B, 1.3, (18.3, 10.65), (20.3, 10.65))           # on the capacitor's pad
t("VDD_4G", B, 2.6, (19.9, 11.45), (20.5, 11.45))           # pad -> pins
t("VDD_4G", B, 1.7, (20.4, 11.95), (22.2, 11.95))           # the two pins (0.6 mm each, 1.1 mm apart)
for y in (10.6, 11.5, 12.4):
    v("VDD_4G", 20.75, y)                                   # to the small capacitors on the front (PWR-6)
# ground of the 220 uF: straight to the module's own ground pins, and three vias (PWR-5)
t("GND", B, 1.2, (19.5, 13.9), (22.2, 13.9))
t("GND", B, 0.6, (22.2, 13.9), (22.4, 14.7))
for x in (17.9, 18.8, 19.7):
    v("GND", x, 15.05)
    t("GND", B, 0.5, (x, 14.2), (x, 15.05))
# gate of the load switch: to a via, the gate parts are on the front
t("LTE_PWR_G", B, 0.2, (17.2, 8.75), (16.45, 8.6))
v("LTE_PWR_G", 16.45, 8.6, 0.45, 0.2)

# ---- 5 V input (VBUS) on the back: charger pin 1 -> C2 -> under the SIM socket -> vias
t("VBUS", B, 0.28, (9.15, 14.13), (9.15, 15.2))
t("VBUS", B, 0.9, (9.15, 15.49), (8.3, 15.49))
t("VBUS", B, 1.0, (8.0, 15.6), (8.0, 26.4), (8.8, 27.2), (16.9, 27.2), (17.4, 28.0), (18.3, 28.0))   # between the contact windows
v("VBUS", 17.4, 28.0)
v("VBUS", 18.3, 28.0)
# Type-C: each pair of supply pads goes up 1.3 mm to two vias (the pegs of the connector leave no room below)
t("VBUS", B, 0.6, (29.55, 25.4), (29.55, 24.4), (28.75, 24.4))
v("VBUS", 29.55, 24.4)
v("VBUS", 28.75, 24.4)
t("VBUS", B, 0.6, (34.45, 25.4), (34.45, 24.4), (35.25, 24.4))
v("VBUS", 34.45, 24.4)
v("VBUS", 35.25, 24.4)

# ---- antenna socket: two ground vias beside each ground pad (RF-11)
for q in (28.7, 29.3):
    v("GND", 21.4, q, 0.45, 0.2)
    t("GND", B, 0.4, (21.4, q), (22.2, 28.98))
for x in (21.4, 20.8):                                      # the socket's own keep-out is right above this pad
    v("GND", x, 31.75, 0.45, 0.2)
t("GND", B, 0.4, (20.8, 31.75), (21.4, 31.75), (22.2, 31.94))

# ============================== front =============================================================
# ---- 5 V input: both via pairs -> past the protection chip, 0.6 mm on each side -> TVS D1 (PWR-7: the current
# passes its pad) -> test pad -> 1.0 mm along the bottom edge -> vias to the back
t("VBUS", F, 0.6, (28.75, 24.4), (29.55, 24.4), (30.2, 25.6), (30.2, 30.9), (30.6, 31.6))
t("VBUS", F, 0.6, (35.25, 24.4), (34.45, 24.4), (33.8, 25.6), (33.8, 30.3), (33.3, 30.75), (31.2, 30.75),
  (30.7, 31.4))
t("VBUS", F, 1.0, (30.65, 31.89), (29.3, 32.1), (28.6, 32.8), (20.3, 32.8), (18.3, 30.8), (18.3, 28.0), (17.4, 28.0))
t("VBUS", F, 0.6, (28.9, 31.9), (29.3, 32.1))                # test pad

# ---- system supply on the front: 2 mm trunk from the four vias down to the amplifier (PWR-16), test pad at its end
# The trunk steps 0.7 mm to the left where it passes the charger's four signal pins (back, y = 13.3 .. 14.4):
# with the 5 V strip on the back to their right, the pins had 0.4 mm of room for vias below them.
t("VSYS", F, 2.0, (5.9, 7.2), (5.6, 8.2), (5.6, 12.0), (4.9, 12.7), (4.9, 15.9), (5.6, 16.6), (5.6, 23.4))
t("VSYS", F, 0.75, (4.2, 21.7), (4.9, 21.7))               # amplifier pins 7 / 8
t("VSYS", F, 0.5, (6.0, 21.7), (6.7, 21.7))                # its 100 nF
t("VSYS", F, 1.0, (6.5, 8.05), (7.6, 8.05))                # input capacitor of the 3.3 V buck
t("VSYS", F, 0.6, (7.6, 8.05), (9.55, 8.05))               # ... and its VIN pin
t("VSYS", F, 0.3, (8.5, 8.05), (8.5, 7.3), (9.0, 6.6), (9.415, 6.5))   # enable pull-up
t("VSYS", F, 0.2, (16.4, 7.06), (16.49, 7.825))            # gate pull-up of the load switch
# backlight feed (about 0.2 A): 0.4 mm from the end of the trunk
t("VSYS", F, 0.4, (5.6, 24.4), (5.6, 24.9), (5.9, 25.2), (12.0, 25.2), (12.325, 25.8))
t("VSYS", F, 0.6, (12.325, 27.3), (12.64, 28.6))
t("VSYS", F, 0.5, (12.6, 27.3), (13.6, 27.5))

# ---- 3.3 V buck (PWR-11 / PWR-12)
t("GND", F, 0.6, (11.8, 9.0), (8.55, 9.0), (8.1, 9.5), (7.575, 9.955))   # pin 2 -> under the chip -> input capacitor
t("BUCK_SW", F, 0.6, (11.9, 8.05), (13.5, 7.9))                        # 0.65 mm from the pin to the inductor
t("+3V3", F, 1.4, (14.95, 8.2), (14.95, 9.6))                          # inductor -> C10, with two vias to the 3.3 V layer
v("+3V3", 14.55, 8.8)
v("+3V3", 15.35, 8.8)
t("GND", F, 1.0, (14.9, 11.71), (13.4, 11.71), (13.3, 9.4))               # C10 ground -> pin 2
t("GND", F, 0.6, (13.3, 9.0), (12.3, 9.0))
v("GND", 14.9, 12.65, 0.45, 0.2)
t("GND", F, 0.4, (14.9, 11.9), (14.9, 12.65))
t("BUCK_FB", F, 0.15, (9.5, 10.0), (9.5, 11.29), (10.565, 11.31), (10.565, 12.38))
t("+3V3", F, 0.3, (11.535, 11.31), (11.535, 12.38), (12.0, 14.9))      # feedback divider senses at C11
v("+3V3", 12.25, 16.65)
t("+3V3", F, 0.5, (12.25, 15.6), (12.25, 16.65))
t("GND", F, 0.4, (10.35, 15.6), (10.35, 16.65))
t("GND", F, 0.3, (9.5, 12.25), (8.8, 13.0))

# ---- backlight boost: switch node and the loop diode -> output capacitor -> ground pin, all within 2 mm
t("BL_SW", F, 0.5, (10.675, 27.4), (10.5, 28.7))
t("BL_SW", F, 0.45, (10.0, 28.8), (8.8, 28.8))
t("LCD_LEDA", F, 0.45, (6.66, 28.8), (6.7, 30.5))
t("GND", F, 0.6, (8.7, 30.4), (9.4, 29.9), (10.2, 29.75))
t("LCD_LEDK", F, 0.25, (10.36, 30.7), (10.36, 32.0))

# ---- amplifier outputs to the two beads, ground vias in the pad under the chip (PWR-14)
t("PA_OUTP", F, 0.25, (3.295, 20.6), (3.35, 19.6))
t("PA_OUTN", F, 0.25, (2.795, 20.6), (2.795, 20.15), (2.25, 19.6))
for x in (2.25, 2.85):
    for y in (21.9, 22.5):
        v("GND", x, y, 0.45, 0.2, True)

# ---- Air780E supply on the front: capacitors opposite the pins, TVS, gate capacitor
t("VDD_4G", F, 0.5, (20.75, 9.6), (20.75, 12.4))
t("VDD_4G", F, 0.4, (20.75, 10.6), (21.5, 10.6))
t("VDD_4G", F, 0.4, (20.75, 11.6), (21.5, 11.65))
t("VDD_4G", F, 0.4, (20.75, 12.45), (21.5, 12.7))
t("VDD_4G", F, 0.4, (20.75, 12.4), (20.4, 13.6))
# gate of the load switch
t("LTE_PWR_G", F, 0.15, (16.45, 8.6), (17.46, 8.5), (17.46, 7.9))
t("LTE_PWR_G", F, 0.15, (17.46, 8.5), (18.74, 8.5), (18.74, 7.9))
t("LTE_PWR_G", F, 0.15, (18.74, 8.5), (20.3, 8.5), (20.6, 8.6))


# The series path battery pad -> Air780E supply pins, piece by piece: (width, length) in mm, for PWR-1 and PWR-2.
# Kept by hand next to the geometry above: where pieces overlap, the width is that of the copper they form together.
PATH = {
    "VBAT": [(2.0, 1.4), (1.5, 1.5), (2.0, 1.4), (0.78, 0.6)],     # band, corner, band, the two pins
    "VSYS": [(0.78, 0.4), (1.1, 1.25), (2.0, 9.8)],                # at the pins, neck, strip to the load switch
    "VDD_4G": [(1.4, 1.8), (2.6, 2.6), (1.7, 0.3)],                # at the drain, capacitor pad -> pins, the two pins
}

# ---- TF socket (back, bottom edge) under the microphone (front): the pins can only get out through the 1 mm
# between the microphone's two pad rows (y = 30.8 .. 31.8). Left to itself the +3V3 stub of pin 4 runs 3 mm to
# the right to find a via and shuts in pin 5 (SD_CLK_R). Both go straight up instead.
t("+3V3", B, 0.3, (51.1, 32.6), (51.1, 32.0), (50.95, 31.3))
v("+3V3", 50.95, 31.3, 0.45, 0.2)
t("SD_CLK_R", B, 0.15, (52.2, 32.6), (52.2, 32.2), (51.9, 31.35))
v("SD_CLK_R", 51.9, 31.35, 0.45, 0.2)

# ---- expander B (U8, front, over the antenna line): pin 18 is an address pin tied to ground. Left to itself its
# ground stub runs round the end of pin 17 to a via and shuts that pin in; it goes into the centre pad instead.
t("GND", F, 0.25, (26.51, 22.23), (25.95, 22.23), (24.8, 23.4))

# ---- expander A (U7, front, turned 180 degrees) sits over the ESP32's right pad column (back). Its interrupt
# pin is 0.4 mm from the ESP32's own interrupt pad: one via and 1 mm of track on the back join them, before the
# supply stubs of the neighbouring pins get in the way.
t("EXP_INT", F, 0.15, (58.22, 12.41), (58.22, 12.95), (58.15, 13.3))
v("EXP_INT", 58.15, 13.3, 0.45, 0.2)
t("EXP_INT", B, 0.15, (58.15, 13.3), (58.15, 12.6), (58.95, 12.2))

# ---- camera regulator (U16, front, top edge): its enable pin (3) lies between the supply pin above it, the
# display connector's pads on the back below it and ground vias to the left. Left to itself the 3.3 V link from
# pin 1 to the input capacitor runs round the pin and shuts it in. Its way out goes down between pins 3 and 4
# to a via below the connector's pads, before that link is laid.
t("CAM_PWR_EN", F, 0.15, (19.5, 3.3), (20.15, 3.75), (20.15, 5.8))
v("CAM_PWR_EN", 20.15, 5.8, 0.45, 0.2)
# The two regulators' output capacitors hang on the output pin by hand (DEC-2): about 1 mm of copper each, which
# an autorouter will otherwise cut off with a signal track through the gap. U16's supply pin goes to the 3.3 V
# plane beside the pin, like U15's; its link to the capacitor three pads away ran through that same gap.
t("+2V8", F, 0.3, (14.6, 1.25), (16.42, 1.25))
t("+2V8", F, 0.4, (16.42, 1.1), (16.42, 2.4))
t("+1V2", F, 0.3, (21.8, 1.25), (23.05, 1.25))
t("+1V2", F, 0.4, (23.05, 1.1), (23.05, 2.4))
t("+3V3", F, 0.3, (19.5, 1.4), (20.2, 1.4))
v("+3V3", 20.2, 1.4, 0.45, 0.2)

# ---- USB pair from the switch (U6) to the series resistors R18 / R19 (back, right edge): the two lines differ
# at their ends, not on the coupled run in between. At the switch D- has to pass under the chip to a via on its
# far side, and here it has to go round the pad of R18; no via fits beside the resistors (board edge, pads on
# both sides). That makes D- about 5 mm longer. D+ makes it good: it runs down the back first and comes back
# up on the inner layer (USB-3).
t("ESP_USB_DP", B, 0.19, (62.8, 18.6), (62.8, 21.8))
v("ESP_USB_DP", 62.8, 21.8, 0.45, 0.2)
t("ESP_USB_DP", L3, 0.19, (62.8, 21.8), (62.8, 18.4))      # the way back up, to where the coupled run ends

# ---- USB from the Type-C socket (back) through the protection chip U1 (front, right above it) to the switch U6.
# Each line has two contacts in the socket; they are joined on the back, D+ below the pads, D- above them, and
# each line leaves from the top of its B-row contact, so that both are longer by the same join when the plug is
# turned over. D+ has the longer way to the switch (its contact is on the left, its switch pin is the far one);
# D- makes that good with one bend on the back (USB-3). Each via also feeds the upper pin of U1; the lower pins
# hang on the same contacts from below.
t("USBC_DP", B, 0.19, (31.3, 26.35), (31.3, 26.5), (31.5, 26.7), (32.0, 26.7), (32.2, 26.5), (32.2, 26.35))
t("USBC_DP", B, 0.19, (31.25, 25.1), (31.25, 23.5))
v("USBC_DP", 31.25, 23.5, 0.45, 0.2)
t("USBC_DP", F, 0.19, (31.25, 23.5), (32.4, 22.35), (33.55, 22.35))
t("USBC_DP", F, 0.19, (31.25, 23.5), (31.1, 23.65), (31.1, 24.2))
t("USBC_DP", F, 0.19, (31.05, 25.2), (31.05, 26.4))                      # pin 6 to pin 1, under the chip
t("USBC_DM", B, 0.19, (31.75, 25.1), (31.75, 25.05), (32.0, 24.8), (32.5, 24.8), (32.75, 25.05), (32.75, 25.1))
t("USBC_DM", B, 0.19, (32.75, 25.05), (32.75, 24.7), (33.15, 24.3), (33.65, 24.3), (33.65, 23.6), (33.3, 23.25),
  (32.75, 23.25))
v("USBC_DM", 32.75, 23.25, 0.45, 0.2)
t("USBC_DM", F, 0.19, (32.75, 23.25), (33.2, 22.8), (33.55, 22.8))
t("USBC_DM", F, 0.19, (32.75, 23.25), (32.75, 23.7), (32.95, 23.9), (32.95, 24.1))
t("USBC_DM", B, 0.19, (32.8, 26.4), (32.8, 27.85), (33.0, 28.05))        # pin 3, from the contact's lower end
v("USBC_DM", 33.0, 28.05, 0.45, 0.2)
t("USBC_DM", F, 0.19, (33.0, 28.05), (33.0, 27.5))

# ---- Type-C CC lines: from the socket's contacts (back) down under its body to a via each between the pads of
# the protection diode D1, and on the front along the bottom edge to the two resistors right of the diode. CC1
# passes between the pads of R2 on its way to R1.
t("USBC_CC2", B, 0.15, (30.25, 26.4), (30.25, 30.5), (31.25, 31.5), (31.75, 31.5))
v("USBC_CC2", 31.75, 31.5, 0.45, 0.2)
t("USBC_CC2", F, 0.15, (31.75, 31.5), (31.6, 31.65), (31.6, 33.05), (31.9, 33.35), (34.7, 33.35))
t("USBC_CC1", B, 0.15, (33.25, 26.4), (33.25, 27.2), (33.55, 27.5), (33.55, 31.05), (32.3, 32.3))
v("USBC_CC1", 32.3, 32.3, 0.45, 0.2)
t("USBC_CC1", F, 0.15, (32.3, 32.3), (32.9, 32.9), (35.6, 32.9), (35.95, 33.25))

# ---- right edge, level with expander A: three 3.3 V pads share one via, R71 and R67 on the front and the
# pull-up R12 of the enable line on the back. R12 has no room for a via of its own (board edge on one side,
# its other pad on the other); laid by hand so that the short signal connections do not cut its way to the via.
t("+3V3", F, 0.3, (61.65, 8.25), (61.25, 7.85))
t("+3V3", F, 0.3, (61.65, 7.2), (61.25, 7.6))
v("+3V3", 61.2, 7.75, 0.45, 0.2)
t("+3V3", B, 0.2, (62.7, 8.35), (62.6, 8.35), (62.05, 7.8), (61.2, 7.8))


def lay(r):
    """Put the copper into the router. Returns the list of pieces that do not fit (empty when all is well)."""
    bad = []
    for name, layer, width, pts in TRACKS:
        net = r.net_id[name]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            hit = r.blocked(net, layer, x0, y0, x1, y1, width)
            if hit:
                bad.append(f"{name} {'F3?B'[layer]} track {width} mm ({x0}, {y0}) - ({x1}, {y1}): too close to "
                           f"{hit[2]} at ({hit[0]:.2f}, {hit[1]:.2f})")
            r.add_track(net, layer, x0, y0, x1, y1, width, None)
    for name, x, y, dia, drill, in_pad in VIAS:
        net = r.net_id[name]
        why = r.via_blocked(net, x, y, dia, in_pad)
        if why:
            bad.append(f"{name} via {dia}/{drill} at ({x}, {y}): {why}")
        r.add_via(net, x, y, dia, drill, None)
    return bad
