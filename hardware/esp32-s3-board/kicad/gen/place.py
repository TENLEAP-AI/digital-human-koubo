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
    "IPEX 座": (23.4, 29.6, 0, "B"),
    "电池焊盘": (2.11, 8.7, 0, "B"),
    "喇叭焊盘": (1.27, 19.22, 0, "B"),
    "zeebuddy:SY6970_QFN-24_4x4mm": (8.6, 11.6, 0, "B"),
    "1µH 4A": (14.3, 11.6, 90, "B"),
    # front: front camera, keys, microphone, download pads
    "前摄 30 万（型号待定）": (20.0, 2.75, 180, "F"),
    "按键排线 B": (49.4, 2.75, 180, "F"),
    "按键排线 A": (60.4, 25.0, 90, "F"),
    "zeebuddy:MSM261S4030H0R": (51.0, 31.3, 90, "F"),
    "下载 / 调试焊盘": (42.5, 32.4, 0, "F"),
}

# ---- parts that need an exact spot: reference -> (x of the part's centre, y, rotation, side) ----------
# Antenna matching on the back, in one straight line from the Air780E antenna pad to the socket's centre pad
# (x = 24.45): the shunt capacitors sit with their signal pad on the line, the series part in the line (RF-8).
EXACT = {
    "C29": (23.97, 23.9, 0, "B"),
    "R49": (24.45, 25.4, 90, "B"),
    "C30": (23.97, 26.9, 0, "B"),
}

# ---- small parts ---------------------------------------------------------------------------------
# (side, x, y, rows[, gap between parts, gap between rows]); the default gaps leave room for a via
T = (0.12, 0.12)        # tight packing where there is no room to spare
GROUPS = [
    # ---------------- back ----------------
    ("B", 4.3, 6.0, ["C3 C4 C1 C2"], *T),                               # charger: PMID, REGN, BTST, VBUS
    ("B", 4.3, 14.7, ["C7 C5 C6", "R3 R5 R4"], *T),                     # charger: BAT, SYS, ILIM, NTC
    ("B", 17.9, 8.7, ["C19@270"]),                                      # 220 uF, + pad within 1 mm of the Air780E supply pads (PWR-3)
    ("B", 17.8, 5.7, ["C20", "C21"], *T),
    ("B", 17.0, 14.0, ["Q1@90"]),                                       # Air780E load switch
    ("B", 61.3, 3.2, ["C13@180", "C12@90", "R12", "C14@180"], *T),      # ESP32: 3V3 decoupling (3V3 pads face pin 2), EN
    ("B", 61.3, 16.8, ["R19@180", "R18@180"], *T),                      # ESP32 USB series resistors, in pin order
    # ---------------- front ----------------
    ("F", 1.9, 0.7, ["R53 R54 C31 C32", "R61 R55 R56 R57", "C33 R58 R59 R60"]),           # LCD / touch
    ("F", 0.8, 6.2, ["U3 L2 C9@90 C10@90 C11@90", "R11 R9 C8 R10"]),                      # 3.3 V buck
    ("F", 16.0, 5.8, ["R66 R67", "R71 R72", "R73 C46", "C47 C48", "C49"]),                # front camera options
    ("F", 4.0, 11.9, ["U11 L3 D5", "C35 C34 R62"]),                                       # backlight boost
    ("F", 0.8, 18.5, ["R6 R7 D2 R8 TP1"]),                                                # charger LED
    ("F", 0.8, 20.3, ["U17 C54@90 C55@90 FB1@90 FB2@90", "R76 R75 C52 C53"]),             # audio amplifier
    ("F", 11.6, 18.5, ["R45 R46 R47 R48", "C24 C25 C26 C27", "U10 C28"]),                 # SIM
    ("F", 11.6, 26.0, ["TP2 TP3 TP4 TP5 TP6 TP7"]),                                       # power test pads
    ("F", 21.3, 6.2, ["Q2 Q3 Q4 Q5",                                                      # Air780E control
                      "R31 R32 R33 R34 R35 R36 C23",
                      "C22 R37 R38 R39 R40 R41 R42",                                  # C22 sits opposite the supply pads
                      "R43 R44 R29 R30 C18 D4",
                      "Q6 D3"]),
    ("F", 29.6, 14.9, ["TP11 TP12 TP13 TP14 TP15", "TP16 TP17 TP18 TP19 TP20", "TP10"]),  # Air780E test pads
    ("F", 39.0, 6.0, ["R51", "R52"]),                                                     # UART0 / LCD sync
    ("F", 21.3, 20.0, ["U8 C17@90 U6 C15@90 R17@90"]),                                    # expander B, USB switch
    ("F", 29.9, 24.2, ["U1"]),                                                            # Type-C: ESD
    ("F", 30.6, 28.2, ["R1@90 R2@90"]),                                                   # Type-C: CC resistors
    ("F", 29.8, 30.7, ["D1"]),                                                            # Type-C: TVS
    ("F", 28.6, 0.6, ["U15 U16 Y1", "C44 C39 C40 C45 C42 C43 C41"]),                      # camera LDOs, clock
    ("F", 42.3, 0.6, ["R63", "R64"]),                                                     # camera clock resistors
    ("F", 53.3, 0.6, ["R68 R69 R70", "R65"]),
    ("F", 41.4, 6.2, ["U12", "U13"]),                                                     # camera bus switches
    ("F", 49.5, 6.2, ["C36 C37"]),
    ("F", 49.5, 12.4, ["C38"]),
    ("F", 49.5, 13.9, ["U14"]),
    ("F", 55.3, 6.2, ["U7"]),                                                             # expander A (keys)
    ("F", 59.0, 12.0, ["R20 R21", "R22 R23", "R24 R25", "R26 R27", "R28 C16"]),
    ("F", 38.9, 20.9, ["R50 R16 R13 R14 R15", "U5 SW1", "SW2 TP8 TP9"]),                  # ESP32 misc, buttons
    ("F", 50.3, 20.9, ["R77 R78 R79", "R80 R81 R82", "C57 C56"]),                         # TF card
    ("F", 53.7, 29.6, ["C50@90 C51@90 R74@90"]),                                          # microphone
]
