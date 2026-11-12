"""Where every part goes on the board.

Coordinates are millimetres from the top-left corner of the board seen from the front
(X right, Y down), on both sides. Rotation 0 = upright as seen from the front.

MAIN holds the big parts with explicit positions. GROUPS packs the small parts: each group
is (side, x, y, rows); a row is a string of references placed left to right starting at x,
rows stack downwards from y. "R1@90" turns a part by 90 degrees.
"""

# ---- main parts: value or footprint name -> (x, y, rotation, side) --------------------------------
MAIN = {
    # back: the two modules; TF, Type-C, antenna socket and SIM along the bottom edge; display connectors on top
    "ESP32-S3-WROOM-1U-N16R8": (50.6, 10.5, 0, "B"),
    "zeebuddy:Air780E": (30.6, 14.7, 90, "B"),            # antenna pad ends up bottom-left, next to the socket
    "Type-C 16P": (32.0, 29.8, 0, "B"),
    "Nano SIM 卡座": (12.76, 26.3, 0, "B"),
    "TF 卡座（带检测）": (50.9, 27.45, 180, "B"),
    "触摸排线座 6P（脚位待定）": (5.0, 2.75, 180, "B"),
    "屏排线座 22P 0.5mm": (16.2, 2.75, 180, "B"),
    "后摄 OV2640": (32.0, 2.75, 180, "B"),
    "IPEX 座": (23.4, 30.46, 0, "B"),                     # moved down to make room for the matching parts
    "电池焊盘": (2.11, 8.7, 0, "B"),
    "喇叭焊盘": (1.27, 19.22, 0, "B"),
    "zeebuddy:SY6970_QFN-24_4x4mm": (7.9, 12.2, 270, "B"),
    # front: front camera, keys, microphone, download pads.
    # The front camera connector sits right above its bus switches (U12 .. U14) and over the ESP32 module, where the
    # back has no pads in the way. It used to be at x = 20, back to back with the display connector and 25 mm from
    # the switches: its 14 signals had to cross the Air780E's surroundings and a third of them found no way.
    "前摄 30 万（型号待定）": (51.1, 2.75, 180, "F"),
    "按键排线 B": (39.42, 2.75, 180, "F"),               # was at 49.4: made room for the camera connector
    "按键排线 A": (60.4, 25.0, 90, "F"),
    "zeebuddy:MSM261S4030H0R": (51.0, 31.3, 90, "F"),
    "下载 / 调试焊盘": (42.5, 32.4, 0, "F"),
}

# ---- parts that need an exact spot: reference -> (x of the part's centre, y, rotation, side) ----------
# Antenna matching on the back, in one straight line from the Air780E antenna pad to the socket's centre pad
# (x = 24.45): the shunt capacitors sit with their signal pad on the line, the series part in the line (RF-8).
EXACT = {
    "C29": (23.97, 24.37, 0, "B"),
    "R49": (24.45, 25.88, 90, "B"),
    "C30": (23.97, 27.39, 0, "B"),
    # Charger (SY6970 at 7.9, 12.2, turned so that BAT / SYS / PGND face up and SW faces right), PWR-11 / PWR-12:
    # the system output leaves upwards into a 2 mm copper strip that runs right to the Air780E load switch.
    "C7": (4.5, 8.135, 270, "B"),      # battery capacitor, on the battery copper next to the BAT pins
    "C5": (9.0, 8.135, 90, "B"),       # system capacitors: ground pad straight above the PGND pins,
    "C6": (10.8, 8.135, 90, "B"),      #   supply pad in the strip; 0.85 mm from C5 so that a via fits between their ground pads
    "C1": (11.05, 11.62, 270, "B"),    # bootstrap capacitor, its SW pad sits in the switch-node copper
    "L1": (14.09, 9.3, 270, "B"),      # SW pad level with the SW pins (2.7 mm of copper), output pad in the strip
    "C3": (11.565, 14.37, 90, "B"),    # PMID capacitor, 0.7 mm from the pin
    "C4": (13.465, 13.825, 90, "B"),   # REGN capacitor
    "C2": (9.15, 16.265, 90, "B"),     # VBUS capacitor under pin 1
    "R5": (4.975, 16.4, 0, "B"),       # NTC divider and input-current resistor, below the chip
    "R4": (4.975, 17.6, 180, "B"),
    "R3": (6.6, 16.9, 90, "B"),
    # Air780E supply (PWR-1, PWR-3): strip -> Q1 (source top left, drain right) -> down into the 220 uF -> module pins
    "Q1": (18.555, 7.8, 180, "B"),
    "C19": (18.8, 12.2, 90, "B"),
    # ... its small filter capacitors on the front, right opposite the supply pins (PWR-6); TVS and gate capacitor beside them
    "C20": (22.0, 10.6, 0, "F"),
    "C21": (22.0, 11.65, 0, "F"),
    "C22": (22.0, 12.7, 0, "F"),
    "D3": (20.3, 14.9, 270, "F"),
    "C18": (20.75, 9.1, 270, "F"),
    # 3.3 V buck on the front, fed from the vias at the left end of the system strip (PWR-11 / PWR-12):
    # vias -> C9 -> VIN; ground of C9 runs under the chip to pin 2; SW pin -> L2 0.65 mm; L2 -> C10 -> vias to the 3.3 V layer
    "C9": (7.575, 9.0, 270, "F"),
    "U3": (10.695, 9.0, 180, "F"),
    "L2": (14.385, 7.3, 0, "F"),
    "C10": (14.925, 10.755, 270, "F"),
    "C11": (11.3, 15.4, 180, "F"),
    "R9": (11.05, 11.31, 180, "F"),
    "C8": (11.05, 12.38, 180, "F"),
    "R10": (9.5, 11.77, 270, "F"),
    "R11": (9.9, 6.5, 0, "F"),
    # audio amplifier at the lower end of the 2 mm system-supply trunk (x = 4.7 .. 6.7 on the front), PWR-16
    "U17": (2.55, 22.2, 90, "F"),
    "FB1": (3.35, 19.025, 90, "F"),
    "FB2": (2.25, 19.025, 90, "F"),
    "C55": (7.18, 21.7, 0, "F"),
    "C54": (7.35, 22.9, 0, "F"),
    "R76": (3.6, 24.91, 0, "F"),
    "R75": (1.55, 24.91, 180, "F"),
    "C52": (3.6, 17.45, 0, "F"),
    "C53": (1.1, 18.9, 270, "F"),
    "TP4": (5.6, 24.3, 0, "F"),        # system-supply test pad: the end of the trunk
    # backlight boost at the bottom: L3 above the chip, diode and output capacitor to its left (hot loop under 2 mm)
    "U11": (11.5, 29.75, 0, "F"),
    "L3": (11.5, 26.66, 180, "F"),
    "D5": (7.71, 28.8, 0, "F"),
    "C35": (7.66, 30.88, 0, "F"),
    "C34": (13.87, 26.75, 90, "F"),
    "R62": (10.36, 32.52, 270, "F"),
    # test pads next to what they measure
    "TP1": (3.5, 6.5, 0, "F"),
    "TP3": (3.5, 8.45, 0, "F"),
    "TP2": (28.9, 31.9, 0, "F"),
    # Type-C protection: turned so that a 0.6 mm supply track passes on each side, between it and the connector's pegs
    "U1": (32.0, 25.8, 90, "F"),
}

# ---- small parts ---------------------------------------------------------------------------------
# (side, x, y, rows[, gap between parts, gap between rows]); the default gaps leave room for a via
T = (0.12, 0.12)        # tight packing where there is no room to spare
GROUPS = [
    # ---------------- back ----------------
    ("B", 61.3, 3.2, ["C13@180", "C12@90", "R12", "C14@180"], *T),      # ESP32: 3V3 decoupling (3V3 pads face pin 2), EN
    ("B", 61.3, 16.8, ["R19@180", "R18@180"], *T),                      # ESP32 USB series resistors, in pin order
    # ---------------- front ----------------
    ("F", 1.9, 0.7, ["R53 R54 C31 C32", "R61 R55 R56 R57", "C33"]),           # LCD / touch
    ("F", 0.8, 5.9, ["R6", "R7", "D2", "R8"]),                                            # charger LED, pull-ups
    # Below the front camera connector (pads end at y = 5.25) a band of about 2 mm stays free of parts: its 0.5 mm
    # pins need the room to get out. C46 / C47 and Q2 used to sit in it.
    ("F", 16.0, 7.31, ["R29 R30"]),                                                       # Air780E switch gate
    ("F", 61.25, 2.6, ["C48", "C49", "R66", "R67", "R71", "R72", "R73"], 0.3, 0.3),      # front camera options, beside its connector
    ("F", 21.5, 7.88, ["C46", "C47"], 0.3, 0.12),
    ("F", 15.4, 14.75, ["Q2"]),                                                           # Air780E supply switch driver
    ("F", 11.6, 18.5, ["R45 R46 R47 R48", "C24 C25 C26 C27", "U10 C28"]),                 # SIM
    ("F", 16.37, 26.0, ["TP5 TP6 TP7"]),                                                  # 3.3 V and ground test pads
    ("F", 25.55, 7.1, ["Q3 Q4 Q5"]),                                                      # Air780E control
    ("F", 23.7, 10.8, ["R31 R32 R33 R34 R35 R36 C23",
                       "R42 R37 R38 R39 R40 R41 R43",        # R43 (not fitted): beside module pin 100
                       "R44 D4"], 0.3, 0.2),
    ("F", 21.3, 14.78, ["Q6"]),
    ("F", 29.6, 14.9, ["TP11 TP12 TP13 TP14 TP15", "TP16"]),                              # Air780E test pads ...
    ("F", 61.3, 11.85, ["TP10"]),                     # spare expander output, beside chip A
    ("F", 25.55, 14.9, ["TP20", "TP19"]),             # ... debug UART: beside module pins 39 / 38 (they were 13 mm away)
    ("F", 37.55, 13.3, ["TP17", "TP18"]),             # ... main UART: beside module pins 17 / 18
    ("F", 39.0, 6.0, ["R51", "R52", "R70"]),                                              # UART0 / LCD sync; CAM_SEL pull-down
    # U8 is 0.8 mm lower than U6: its top pins then face the gap between two pad rows of the Air780E on the back,
    # and each can drop a via right above itself. At y = 20.0 only one via fitted there, both +3V3 pins had to share
    # it and their link shut in the interrupt pin between them.
    ("F", 21.9, 20.8, ["U8 C17@90"]),
    ("F", 28.9, 20.0, ["U6 C15@90 R17@90"]),      # expander B, USB switch; the pad under U8 takes the
                                                            # ground vias beside the antenna line on the back (RF-5)
    ("F", 30.6, 28.2, ["R1@90 R2@90"]),                                                   # Type-C: CC resistors
    ("F", 29.8, 30.7, ["D1"]),                                                            # Type-C: TVS
    # Camera LDOs and clock: one strip under y = 4.2, the capacitors between the chips and not below them. The display
    # and rear camera connectors on the back have their pads at y = 4.05 .. 5.25: the front stays free from there down
    # to y = 7, so that their pins can drop a via right below the pad.
    # U15 stands 0.6 mm to the left of where the strip would put it: the gap to its capacitors (1.35 mm between
    # the pads) is the one column above the display connector's data pins where vias fit 0.15 mm clear of the
    # pads on both sides of the board (GEN-7).
    ("F", 10.9, 0.6, ["U15"]),
    ("F", 15.95, 0.6, ["C39", "C40", "C44"], 0.3, 0.3),          # output capacitors on top, level with the output pin
    ("F", 18.12, 0.6, ["U16"]),
    ("F", 22.57, 0.6, ["C42", "C43", "C45"], 0.3, 0.3),
    ("F", 24.74, 0.6, ["Y1"]),
    ("F", 29.29, 0.6, ["C41"], 0.3, 0.3),
    ("F", 31.46, 0.6, ["R63", "R64"], 0.3, 0.3),                                          # clock series resistors, at the oscillator
    ("F", 33.67, 0.6, ["R68", "R69", "R65"], 0.3, 0.3),
    # 2.5 mm below the camera connector's pads (they end at y = 5.25) stays free: room for its pins to get out
    ("F", 41.4, 7.8, ["U12", "U13"]),                                                     # camera bus switches
    ("F", 49.3, 7.8, ["C36@90", "C37@90"], 0.3, 0.3),    # upright, one above the other: clear of the vias in the ESP32's ground pad
    ("F", 49.5, 12.4, ["C38"]),
    ("F", 49.5, 13.9, ["U14"]),
    # expander A (keys), turned 180 degrees: the six key pins face right, towards their pull-ups below and the key
    # connector; the two front camera pins face up, towards the camera connector. The side that is over the ESP32's
    # pad column on the back (no room for vias there) carries next to nothing. Unturned, every key track had to go
    # round the chip.
    ("F", 55.3, 7.8, ["U7@180"]),
    # (Tried: the pull-ups of keys 4 to 6 beside connector B at the top edge, where those lines go. The corner here
    # got easier, but at (34.7 .. 38.9, 5.75 .. 8) they stand where the rear camera connector's last pins drop
    # their vias, and four camera lines stayed open instead.)
    ("F", 59.0, 13.3, ["R20 R21", "R22 R23", "R24 R25", "R27 R28", "C16"], 0.3, 0.2),
    ("F", 27.3, 15.0, ["R26"]),                                                           # touch interrupt pull-up, beside chip B
    ("F", 38.9, 20.9, ["R50 R16 R13 R14 R15", "U5 SW1", "SW2 TP8 TP9"]),                  # ESP32 misc, buttons
    ("F", 50.3, 20.9, ["R77 R78 R79", "R80 R81 R82", "C57 C56"]),                         # TF card
    ("F", 53.7, 29.6, ["C50@90 C51@90 R74@90"]),                                          # microphone
]
