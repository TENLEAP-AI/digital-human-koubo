"""Zeebuddy mainboard V1 schematic (ESP32-S3 module + Air780E).

Run:  python3 design.py [output_dir]
The pin plan follows docs/requirements.md (方案三).
"""
import os
import sys

from kisch import POWER, Design, box_symbol

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..")

d = Design("zeebuddy-mainboard", "Zeebuddy 主板 V1（ESP32-S3 + Air780E）", "V1.0-draft", "2026-11-10")

# ---- rails ------------------------------------------------------------------
POWER["+2V8"] = ("power:+2V8", True)
POWER["+1V2"] = ("power:+1V2", True)
d.rail("VSYS")     # charger system output, 3.5 ~ 4.4 V
d.rail("VBAT")     # battery +
d.rail("VDD_4G")   # Air780E supply after the load switch

# ---- footprints -------------------------------------------------------------
FP_0603 = "Capacitor_SMD:C_0603_1608Metric"
FP_0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_SOT23 = "Package_TO_SOT_SMD:SOT-23"
FP_FPC = "zeebuddy:FPC_0.5mm_%dP_Placeholder"
FP_L_SMALL = "Inductor_SMD:L_Changjiang_FNR252012S"
FP_L_BIG = "Inductor_SMD:L_Sunlord_MWSA0402S"

# ---- project symbols --------------------------------------------------------
AIR780_GND = [1, 10, 27, 34, 36, 37, 40, 41, 45, 46, 47, 48, 70, 71, 72, 73, 88, 89, 90, 91, 92, 93, 94, 95]
AIR780_NC = [2, 3, 4, 5, 6, 8, 9, 26, 28, 29, 30, 31, 32, 33, 44, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58,
             66, 67, 68, 69, 74, 75, 76, 77, 78, 80, 81, 83, 84, 85, 86, 87, 96, 97, 98,
             101, 102, 103, 104, 105, 106, 107, 108, 109]
assert len(AIR780_GND) + len(AIR780_NC) + 32 == 109

AIR780E = d.define(box_symbol(
    "Air780E", "U",
    left=[([42, 43], "VBAT", "power_in"), None,
          (7, "PWRKEY", "input"), (15, "RESET_N", "input"), (25, "STATUS", "output"),
          (16, "NET_STATUS", "output"), None,
          (24, "VDD_EXT", "power_out"), (99, "RefVolt", "power_out"), (100, "IO_Volt_Set", "input"), None,
          (59, "USB_DP", "bidirectional"), (60, "USB_DM", "bidirectional"), (61, "VBUS", "input"),
          (82, "USB_BOOT", "input"), None,
          (17, "MAIN_RXD", "input"), (18, "MAIN_TXD", "output"), (19, "MAIN_DTR", "input"),
          (20, "MAIN_RI", "output"), (21, "MAIN_DCD", "output"), (22, "MAIN_CTS", "passive"),
          (23, "MAIN_RTS", "passive"), None,
          (38, "DBG_RXD", "input"), (39, "DBG_TXD", "output")],
    right=[(35, "LTE_ANT", "passive"), None,
           (14, "USIM_VDD", "power_out"), (12, "USIM_RST", "output"), (13, "USIM_CLK", "output"),
           (11, "USIM_DAT", "bidirectional"), (79, "USIM_DET", "input"), None,
           (65, "USIM2_VDD", "power_out"), (63, "USIM2_RST", "output"), (62, "USIM2_CLK", "output"),
           (64, "USIM2_DAT", "bidirectional"), None, None, None, None, None, None, None, None, None, None,
           None, None, None, (AIR780_GND, "GND", "power_in")],
    hidden_nc=AIR780_NC, minw=40.64, fp="zeebuddy:Air780E",
    desc="合宙 Air780E / Air780EEN Cat.1 模组，AT 方式的管脚定义（LGA-109，两个型号封装相同）",
    datasheet="https://docs.openluat.com/air780e/product/"))

MUX3257 = d.define(box_symbol(
    "74CBTLV3257", "U",
    left=[(16, "VCC", "power_in"), (1, "S", "input"), (15, "~{OE}", "input"), None,
          (4, "1A"), (7, "2A"), (9, "3A"), (12, "4A"), (8, "GND", "power_in")],
    right=[(2, "1B1"), (3, "1B2"), (5, "2B1"), (6, "2B2"), (11, "3B1"), (10, "3B2"), (14, "4B1"), (13, "4B2")],
    desc="4 位 1 选 2 总线开关。S=0：A 接 B1；S=1：A 接 B2", minw=20.32))


def fpc(name, pins, desc):
    """Single-row FPC connector with named pins and the two mounting tabs."""
    return d.define(box_symbol(name, "J", [], [(i + 1, n) for i, n in enumerate(pins)] + [("MP", "SHELL")],
                               fp=FP_FPC % len(pins), desc=desc, minw=15.24))


LCD_PINS = ["LEDA", "LEDK", "SDA", "SCL", "NC", "VCI", "G7", "G6", "G5", "G4", "G3", "G2", "G1", "G0",
            "CS", "DOTCLK", "HSYNC", "DE", "VSYNC", "RST", "GND", "GND"]
LCD_FPC = fpc("LCD_FPC_22P", LCD_PINS, "屏 LB28BOE47 的 22 脚排线（NV3049F，三线 SPI + 8 位串行 RGB）")
# De-facto 24-pin DVP camera module pinout (OV2640 modules as used on ESP32-CAM).
CAM_PINS = ["STROBE", "AGND", "SIO_D", "AVDD", "SIO_C", "RESET", "VSYNC", "PWDN", "HREF", "DVDD", "DOVDD",
            "Y9", "XCLK", "Y8", "DGND", "Y7", "PCLK", "Y6", "Y2", "Y5", "Y3", "Y4", "Y1", "Y0"]
CAM_FPC = fpc("CAM_FPC_24P", CAM_PINS, "24 脚并口摄像头排线（OV2640 模组的通用脚位）")
TP_FPC = fpc("TP_FPC_6P", ["VDD", "GND", "SCL", "SDA", "INT", "RST"], "触摸屏排线，脚位待屏厂确认")
KEY_FPC = fpc("KEY_FPC_6P", ["GND", "K1", "K2", "K3", "NC", "GND"], "按键排线，脚位待定")

CHARGER = d.define(box_symbol(
    "SY6970QCC", "U",
    left=[(1, "BUS", "power_in"), (2, "DP", "bidirectional"), (3, "DM", "bidirectional"), None,
          (5, "SCL", "input"), (6, "SDA", "bidirectional"), (7, "INT", "open_collector"), None,
          (8, "OTG", "input"), (9, "~{CE}", "input"), (12, "~{QON}", "input"), (10, "ILIM"), None,
          ([17, 18, 25], "PGND", "power_in")],
    right=[(4, "STAT", "open_collector"), (24, "DSEL", "open_collector"), None,
           (23, "PMID"), ([19, 20], "LX"), (21, "BST"), None,
           ([15, 16], "SYS"), ([13, 14], "BAT"), None,
           (22, "REGN"), (11, "NTC")],
    fp="zeebuddy:SY6970_QFN-24_4x4mm", minw=25.4,
    desc="矽力杰 I²C 开关充电芯片，带电源路径和电压电流检测，QFN4x4-24，脚位与 BQ25895RTW 相同",
    datasheet="https://www.electronics-lab.com/wp-content/uploads/2023/12/SY6970-.pdf"))

MIC = d.define(box_symbol(
    "MSM261S4030H0R", "MK",
    left=[(8, "VDD", "power_in"), (4, "CHIPEN", "input"), (5, "L/R", "input"), (1, "GND", "power_in")],
    right=[(3, "WS", "input"), (6, "SCK", "input"), (7, "SD", "output")],
    hidden_nc=[2], minw=20.32, fp="zeebuddy:MSM261S4030H0R",
    desc="敏芯 I²S 硅麦，4 × 3 × 1.25 mm，顶部进音",
    datasheet="https://www.waveshare.com/w/upload/0/01/MSM261S4030H0R.pdf"))

WLED = d.define(box_symbol(
    "SY7200AABC", "U",
    left=[(6, "IN", "power_in"), (4, "EN/PWM", "input"), (2, "GND", "power_in")],
    right=[(1, "LX"), (5, "OVP"), (3, "FB", "input")],
    fp="Package_TO_SOT_SMD:SOT-23-6", minw=20.32,
    desc="矽力杰白光 LED 升压恒流驱动，SOT-23-6，反馈 0.2 V，过压保护 30 V",
    datasheet="https://www.lcsc.com/datasheet/C107309.pdf"))

NANO_SIM = d.define(box_symbol(
    "NanoSIM_PushPush", "J",
    [("1", "VCC"), ("2", "RST"), ("3", "CLK"), ("7", "IO"), ("6", "VPP"), ("SW", "DET"),
     ("5", "GND"), ("SH", "SHELL")], [],
    fp="Connector_Card:nanoSIM_GCT_SIM8060-6-1-14-00",
    desc="Nano SIM 自弹卡座，带插卡检测。具体型号和检测脚极性待定，封装先用 GCT SIM8060 占位", minw=15.24))


# =============================================================================
# 1. Power: Type-C, charger, battery, 3.3 V
# =============================================================================
def power():
    sh = d.sheet("power.kicad_sch", "1 电源：Type-C、充电、电池、3.3V")

    sh.frame(12.7, 17.78, 137.16, 132.08, "Type-C 输入")
    sh.place("Connector:USB_C_Receptacle_USB2.0_16P", 35.56, 68.58,
             {"VBUS": "VBUS", "GND": "GND", "SHIELD": "GND", "CC1": "USBC_CC1", "CC2": "USBC_CC2",
              "D+": "USBC_DP", "D-": "USBC_DM"}, nc=["SBU1", "SBU2"],
             value="Type-C 16P", fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12")
    sh.place("Power_Protection:USBLC6-2SC6", 106.68, 50.8,
             {"I/O1": "USBC_DP", "I/O2": "USBC_DM", "GND": "GND", "VBUS": "VBUS"})   # pin 5 to VBUS, as in ST's circuit
    sh.hlist(106.68, 81.28, [("R", "USBC_CC1", "GND", "5.1k"), ("R", "USBC_CC2", "GND", "5.1k")])
    sh.D(88.9, 114.3, "GND", "VBUS", "TVS 5V", "Device:D_TVS", "up", fp="Diode_SMD:D_SOD-123F")
    sh.text(15.24, 121.92, "USB 数据线只去 ESD 管和 USB 切换芯片，不接充电芯片，\n"
                           "所以不会触发快充升压，VBUS 一直是 5 V。", 1.3)

    sh.frame(142.24, 17.78, 406.4, 132.08, "充电和电源路径（SY6970，I²C 地址 0x6A）")
    sh.place(CHARGER, 198.12, 66.04,
             {"BUS": "VBUS", "DP": "CHG_DPDM", "DM": "CHG_DPDM", "SCL": "I2C_SCL", "SDA": "I2C_SDA",
              "INT": "CHG_INT", "OTG": "GND", "~{CE}": "GND", "~{QON}": "CHG_QON", "ILIM": "CHG_ILIM",
              "STAT": "CHG_STAT", "PMID": "CHG_PMID", "LX": "CHG_SW", "BST": "CHG_BTST", "SYS": "VSYS",
              "BAT": "VBAT", "REGN": "CHG_REGN", "NTC": "CHG_TS", "PGND": "GND"}, nc=["DSEL"])
    sh.hlist(274.32, 33.02, [
        ("C", "CHG_BTST", "CHG_SW", "47nF"),
        ("L", "CHG_SW", "VSYS", "1µH 4A", "", FP_L_BIG),
        ("R", "CHG_ILIM", "GND", RILIM),
        ("R", "CHG_REGN", "CHG_TS", TS_TOP),
        ("R", "CHG_TS", "GND", TS_BOT),
        ("R", "+3V3", "CHG_INT", "10k"),
        ("R", "+3V3", "CHG_LED_A", "2.2k"),
        ("R", "CHG_QON", "KEY1", "0R", "dnp"),
    ])
    sh.D(345.44, 78.74, "CHG_LED_A", "CHG_STAT", "充电灯", "Device:LED", "right", fp="LED_SMD:LED_0402_1005Metric")
    sh.caps(322.58, 111.76, "VBUS", [("1µF 25V", FP_0603)])
    sh.caps(340.36, 111.76, "CHG_PMID", [("10µF 25V", FP_0805)])
    sh.caps(358.14, 111.76, "CHG_REGN", [("4.7µF", FP_0603)])
    sh.caps(373.38, 111.76, "VSYS", [("10µF", FP_0603), ("10µF", FP_0603)])
    sh.caps(162.56, 104.14, "VBAT", [("10µF", FP_0603)])
    sh.tp(345.44, 43.18, "CHG_QON")
    sh.text(144.78, 117.5,
            "没接电池温度电阻：NTC 脚用两颗 10k 固定在正常窗口。OTG、CE 接地：不用反向升压，充电默认打开。\n"
            "电池 2000 mAh，最大充电 0.5C = 1 A。芯片上电默认的充电电流是 2.048 A，所以默认状态靠硬件压住输入功率：\n"
            "  ILIM = 680 Ω → 输入约 0.53 A（360 / 680），5 V 下最多约 3 W，电池电流最坏约 0.94 A；\n"
            "  DP、DM 互相短接、不接 USB 数据线 → 不会和快充适配器握手，VBUS 一直是 5 V。\n"
            "固件运行时：充电电流设 960 mA，关掉 ILIM 脚的限制并把输入限流设到 1.5 ~ 2 A，定时喂 I²C 看门狗。\n"
            "固件死机后看门狗 40 秒超时，芯片回到默认状态，重新受上面的硬件限制（这一点打样后要实测确认）。", 1.3)

    sh.frame(12.7, 137.16, 213.36, 248.92, "电池座和 3.3 V 降压")
    sh.place("Connector_Generic:Conn_01x02", 48.26, 162.56, {"1": "VBAT", "2": "GND"}, value="电池焊盘",
             fp="zeebuddy:BatteryPads")
    sh.place("Regulator_Switching:TLV62569DBV", 111.76, 162.56,
             {"VIN": "VSYS", "EN": "BUCK_EN", "SW": "BUCK_SW", "FB": "BUCK_FB", "GND": "GND"},
             value="SY8089AAAC（可换 TLV62569DBV）", fp="Package_TO_SOT_SMD:SOT-23-5")
    sh.hlist(175.26, 152.4, [
        ("L", "BUCK_SW", "+3V3", "2.2µH 2A", "", FP_L_SMALL),
        ("R", "+3V3", "BUCK_FB", "100k 1%"),
        ("C", "+3V3", "BUCK_FB", "22pF"),
        ("R", "BUCK_FB", "GND", "22.1k 1%"),
        ("R", "VSYS", "BUCK_EN", "100k"),
    ])
    sh.caps(60.96, 218.44, "VSYS", [("22µF", FP_0805)])
    sh.caps(86.36, 218.44, "+3V3", [("22µF", FP_0805), ("22µF", FP_0805)], pitch=12.7)
    sh.text(15.24, 238.76, "输出 = 0.6 V × (1 + 100k / 22.1k) = 3.31 V。电池低于 3.4 V 左右时输出会跟着往下掉，固件要提前关机。", 1.3)

    sh.frame(218.44, 137.16, 406.4, 248.92, "电源标记、测试点、螺丝孔")
    for i, net in enumerate(["GND", "VBUS", "VBAT", "VSYS", "+3V3"]):
        sh.flag(228.6 + (i % 3) * 33.02, 165.1 + (i // 3) * 25.4, net)
    for i, net in enumerate(["VBUS", "VBAT", "VSYS", "+3V3", "GND", "GND"]):
        sh.tp(340.36 + i * 10.16, 170.18, net)
    for i in range(4):
        if i == 0:      # the top-right hole is only 1.2 mm from the board edge: no room for a copper ring
            sh.place("Mechanical:MountingHole", 238.76, 228.6, {}, value="Ø1.6 螺丝孔（无铜环）",
                     fp="zeebuddy:MountingHole_1.6mm_NPTH")
            continue
        sh.place("Mechanical:MountingHole_Pad", 238.76 + i * 20.32, 228.6, {"1": "GND"}, value="Ø1.6 螺丝孔",
                 fp="zeebuddy:MountingHole_1.6mm_Pad")
    return sh


# =============================================================================
# 2. MCU
# =============================================================================
ESP_PINS = {
    "EN": "ESP_EN", "IO0": "I2S_BCLK", "IO1": "I2C_SDA", "IO2": "I2C_SCL", "IO3": "I2S_DOUT",
    "IO4": "CAM_D0", "IO5": "CAM_D1", "IO6": "CAM_D2", "IO7": "CAM_D3", "IO8": "CAM_D4", "IO9": "CAM_D5",
    "IO10": "CAM_D6", "IO11": "CAM_D7", "IO12": "CAM_PCLK", "IO13": "CAM_VSYNC", "IO14": "CAM_HREF",
    "IO15": "SD_CLK", "IO16": "EXP_INT", "IO17": "SD_CMD", "IO18": "I2S_DIN",
    "USB_D-": "ESP_DM", "USB_D+": "ESP_DP", "IO21": "SD_D0",
    "IO38": "LCD_G3", "IO39": "LCD_G4", "IO40": "LCD_G5", "IO41": "LCD_G6", "IO42": "LCD_G7",
    "TXD0": "U0TXD", "RXD0": "U0RXD", "IO45": "LCD_BL_PWM", "IO46": "I2S_WS",
    "IO47": "LCD_PCLK", "IO48": "LCD_DE", "3V3": "+3V3", "GND": "GND",
}


def mcu():
    sh = d.sheet("mcu.kicad_sch", "2 主控：ESP32-S3 模组、下载口、USB 切换")

    sh.frame(12.7, 17.78, 251.46, 248.92, "ESP32-S3-WROOM-1U-N16R8")
    sh.place("RF_Module:ESP32-S3-WROOM-1", 167.64, 99.06, ESP_PINS, nc=["IO35", "IO36", "IO37"],
             value="ESP32-S3-WROOM-1U-N16R8", fp="RF_Module:ESP32-S3-WROOM-1U")
    sh.caps(43.18, 50.8, "+3V3", [("22µF", FP_0805), "100nF"], pitch=12.7)
    sh.hlist(58.42, 83.82, [
        ("R", "+3V3", "ESP_EN", "10k"),
        ("C", "ESP_EN", "GND", "1µF"),
        ("R", "+3V3", "I2S_BCLK", "10k"),
        ("R", "+3V3", "I2C_SDA", "2.2k"),
        ("R", "+3V3", "I2C_SCL", "2.2k"),
        ("R", "LCD_BL_PWM", "GND", "100k"),
    ])
    sh.tp(33.02, 149.86, "I2C_SDA")
    sh.tp(43.18, 149.86, "I2C_SCL")
    sh.place("Switch:SW_Push", 58.42, 165.1, {"1": "ESP_EN", "2": "GND"}, value="复位",
             fp="Button_Switch_SMD:SW_SPST_B3U-1000P")
    sh.place("Switch:SW_Push", 58.42, 177.8, {"1": "I2S_BCLK", "2": "GND"}, value="BOOT（GPIO0）",
             fp="Button_Switch_SMD:SW_SPST_B3U-1000P")
    sh.place("Connector_Generic:Conn_01x06", 68.58, 200.66,
             {"1": "+3V3", "2": "GND", "3": "ESP_EN", "4": "I2S_BCLK", "5": "U0TXD", "6": "U0RXD"},
             value="下载 / 调试焊盘", fp="zeebuddy:ProgPads_1x06")
    sh.place("Power_Supervisor:LM809", 116.84, 190.5, {"VCC": "+3V3", "GND": "GND", "~{RESET}": "ESP_EN"},
             value="803 型 3.08V 开漏", dnp=True, fp=FP_SOT23)
    sh.text(96.52, 209.55, "预留的复位监控芯片：电池供电时 3.3 V 可能缓慢下降，\n"
                           "如果实测有上电不启动的情况就贴上。要用开漏输出的型号。", 1.3)
    sh.text(15.24, 220.98,
            "启动配置脚：\n"
            "GPIO0（音频 BCLK）：上拉；BOOT 键或下载焊盘拉低进下载模式。\n"
            "GPIO3（功放数据）：不加上下拉。\n"
            "GPIO45（背光调光）：下拉，上电背光关。\n"
            "GPIO46（音频 WS）：不能接上拉。\n"
            "GPIO35 ~ 37 被模组内的八线 PSRAM 占用，悬空。\n"
            "GPIO43 / 44 是串口 0（下载、日志），同时经电阻去屏的 VSYNC / HSYNC。", 1.3)
    sh.text(193.04, 144.78,
            "GPIO 分配\n0  音频 BCLK\n1  I²C SDA\n2  I²C SCL\n3  功放数据\n4 ~ 11  摄像头 D0 ~ D7\n"
            "12  摄像头 PCLK\n13  摄像头 VSYNC\n14  摄像头 HREF\n15  TF CLK\n16  扩展芯片中断\n17  TF CMD", 1.3)
    sh.text(223.52, 144.78,
            "\n18  麦克风数据\n19  USB D−\n20  USB D+\n21  TF D0\n38 ~ 42  屏 G3 ~ G7\n43  屏 VSYNC / 串口发\n"
            "44  屏 HSYNC / 串口收\n45  背光调光\n46  音频 WS\n47  屏 DOTCLK\n48  屏 DE", 1.3)

    sh.frame(256.54, 17.78, 406.4, 137.16, "USB 切换（FSUSB42）")
    sh.place("Interface_USB:FSUSB42MUX", 332.74, 66.04,
             {"VCC": "+3V3", "GND": "GND", "~{OE}": "GND", "SEL": "USB_SEL",
              "D+": "ESP_USB_DP", "D-": "ESP_USB_DM", "HSD1+": "USBC_DP", "HSD1-": "USBC_DM",
              "HSD2+": "LTE_USB_DP", "HSD2-": "LTE_USB_DM"})
    sh.hlist(332.74, 99.06, [
        ("R", "USB_SEL", "GND", "4.7k"),
        ("R", "ESP_DP", "ESP_USB_DP", "0R"),
        ("R", "ESP_DM", "ESP_USB_DM", "0R"),
    ])
    sh.caps(383.54, 50.8, "+3V3", ["100nF"])
    sh.text(259.08, 123.19, "USB_SEL = 0（默认）：ESP32-S3 的 USB 接 Type-C，插电脑可直接下载和看日志。\n"
                            "USB_SEL = 1：ESP32-S3 做主机，接 Air780E 的 USB。\n"
                            "两颗 0R 贴近模组，USB 信号有问题时可换成 22 ~ 33 Ω。", 1.3)
    return sh


# =============================================================================
# 3. IO expanders and keys
# =============================================================================
# Which chip a signal sits on follows the board: chip A is on the right, next to the keys, the TF socket, the front
# camera connector and the camera bus switches; chip B is left of the middle, next to the display, touch and rear
# camera connectors, the charger, the amplifier and the Air780E. (TP_INT and CHG_INT used to be on A, CAMF_PWDN and
# CAM_SEL on B: four tracks of 30 .. 65 mm across the whole board.)
# Chip B sits over the antenna line on the back and holds the line's ground vias in its centre pad and below its
# bottom row: P07 and P11 (pins 8 and 11) are shut in by them and stay unused.
EXP_A = {"P00": "KEY1", "P01": "KEY2", "P02": "KEY3", "P03": "KEY4", "P04": "KEY5", "P05": "KEY6",
         "P06": "CAMF_PWDN", "P07": "SD_DET", "P10": "CAM_SEL", "P11": "LTE_STATUS_N",
         "P12": "CAM_RST", "P13": "EXP_SPARE"}
EXP_B = {"P00": "LCD_RST", "P01": "LCD_CS", "P02": "LCD_SCL", "P03": "LCD_SDA", "P04": "TP_RST",
         "P05": "CAM_PWR_EN", "P06": "CAMR_PWDN", "P10": "CHG_INT",
         "P12": "PA_EN", "P13": "LTE_PWR_EN", "P14": "LTE_PWRKEY_EN", "P15": "LTE_RESET_EN",
         "P16": "USB_SEL", "P17": "TP_INT"}


def expander():
    sh = d.sheet("expander.kicad_sch", "3 IO 扩展芯片、按键")
    common = {"SDA": "I2C_SDA", "SCL": "I2C_SCL", "~{INT}": "EXP_INT", "VCC": "+3V3", "GND": "GND",
              "EPAD": "GND"}

    sh.frame(12.7, 17.78, 175.26, 248.92, "两颗 16 位 I²C 扩展芯片")
    sh.place("Interface_Expansion:TCA9555RTWR", 91.44, 78.74,
             dict(common, A0="GND", A1="GND", A2="GND", **EXP_A),
             nc=["P14", "P15", "P16", "P17"], value=EXP_VALUE)
    sh.place("Interface_Expansion:TCA9555RTWR", 91.44, 185.42,
             dict(common, A0="GND", A1="+3V3", A2="GND", **EXP_B), nc=["P07", "P11"], value=EXP_VALUE)
    sh.text(15.24, 121.92, "上：地址 0x20，在板子右侧。按键、TF 卡检测、4G 状态是输入；前摄 PWDN、摄像头切换、摄像头复位、备用脚是输出。\n"
                           "    没用到的 P14 ~ P17 固件里设成输出，避免悬空的输入脚乱触发中断。\n"
                           "下：地址 0x22，在板子中间偏左。触摸中断、充电中断是输入，其余是输出。P07、P11 不用（被天线线的地孔围住，\n"
                           "    线出不来），固件里设成输出。不用 0x21，前摄常见型号占这个地址。\n"
                           "两颗的 INT 并在一起：任何一个输入脚变化都会把 INT 拉低。信号按器件在板上的位置分配，不按输入输出分。", 1.3)
    sh.text(15.24, 231.14, "XL9555 上电后所有脚是输入，芯片内部每个脚有 100 kΩ 上拉。可换脚位相同的 TCA9555RTWR（没有内部上拉）。\n"
                           "需要默认为低的输出都在各自的页上加了能压过它的下拉（2.2k ~ 10k）。", 1.3)

    sh.frame(180.34, 17.78, 281.94, 248.92, "上拉、去耦")
    sh.hlist(231.14, 40.64, [("R", f"KEY{i}", "+3V3", "10k") for i in range(1, 7)] + [
        ("R", "TP_INT", "+3V3", "10k"),
        ("R", "SD_DET", "+3V3", "10k"),
        ("R", "EXP_INT", "+3V3", "10k"),
    ])
    sh.caps(208.28, 132.08, "+3V3", ["100nF", "100nF"], pitch=12.7)
    sh.tp(231.14, 175.26, "EXP_SPARE")

    sh.frame(287.02, 17.78, 406.4, 248.92, "按键排线座（脚位待定）")
    sh.place(KEY_FPC, 314.96, 60.96,
             {"1": "GND", "2": "KEY1", "3": "KEY2", "4": "KEY3", "6": "GND", "MP": "GND"}, nc=["5"],
             value="按键排线 A")
    sh.place(KEY_FPC, 314.96, 116.84,
             {"1": "GND", "2": "KEY4", "3": "KEY5", "4": "KEY6", "6": "GND", "MP": "GND"}, nc=["5"],
             value="按键排线 B")
    sh.text(289.56, 147.32, "参考主板有两个 6 脚按键排线座，\n这里先按每个座 3 个键 + 地来画。\n按键按下接地。", 1.3)
    return sh


# =============================================================================
# 4. Cellular
# =============================================================================
def cellular():
    sh = d.sheet("cellular.kicad_sch", "4 4G：Air780E（可换贴 Air780EEN）、SIM 卡、天线")

    def npn(x, y, base, collector):
        sh.place("Transistor_BJT:MMBT3904", x, y, {"B": base, "C": collector, "E": "GND"}, fp=FP_SOT23)

    sh.frame(12.7, 17.78, 177.8, 109.22, "模组电源开关（可彻底断电）")
    sh.flag(137.16, 40.64, "VDD_4G")
    sh.place("Transistor_FET:AO3401A", 35.56, 53.34, {"G": "LTE_PWR_G", "S": "VSYS", "D": "VDD_4G"},
             fp=FP_SOT23)
    npn(35.56, 88.9, "LTE_PWR_B", "LTE_PWR_C")
    sh.hlist(93.98, 35.56, [
        ("R", "VSYS", "LTE_PWR_G", "470k"),
        ("R", "LTE_PWR_G", "LTE_PWR_C", "100k"),
        ("C", "LTE_PWR_G", "VDD_4G", "22nF"),
        ("R", "LTE_PWR_EN", "LTE_PWR_B", "10k"),
        ("R", "LTE_PWR_B", "GND", "10k"),
    ])
    sh.place("Device:C_Polarized", 132.08, 88.9, {"1": "VDD_4G", "2": "GND"}, value="220µF 钽",
             fp="Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
             prop_pos={"Reference": (134.4, 87.8, 0, "left"), "Value": (134.4, 90.0, 0, "left")})
    sh.caps(149.86, 88.9, "VDD_4G", ["100nF", "33pF"], pitch=10.16)
    sh.caps(170.18, 88.9, "VDD_4G", ["10pF"])
    sh.D(119.38, 88.9, "GND", "VDD_4G", "TVS 5V", "Device:D_TVS", "up", fp="Diode_SMD:D_SOD-323")
    sh.text(88.9, 73.66, "栅极到漏极的 22nF 让输出慢慢升起来，\n给 220µF 充电时不会把 VSYS 拉垮。", 1.3)

    sh.frame(12.7, 114.3, 177.8, 248.92, "开机、关机、状态（全部经三极管，与模组 IO 电平无关）")
    npn(40.64, 152.4, "LTE_PWRKEY_B", "LTE_PWRKEY")
    npn(86.36, 152.4, "LTE_RESET_B", "LTE_RESET_N")
    npn(40.64, 208.28, "LTE_STATUS_B", "LTE_STATUS_N")
    npn(86.36, 208.28, "LTE_NET_B", "LTE_NETLED_K")
    sh.hlist(142.24, 132.08, [
        ("R", "LTE_PWRKEY_EN", "LTE_PWRKEY_B", "10k"),
        ("R", "LTE_PWRKEY_B", "GND", "10k"),
        ("R", "LTE_RESET_EN", "LTE_RESET_B", "10k"),
        ("R", "LTE_RESET_B", "GND", "10k"),
        ("C", "LTE_RESET_N", "GND", "10nF"),
        ("R", "LTE_STATUS", "LTE_STATUS_B", "4.7k"),
        ("R", "LTE_STATUS_B", "GND", "47k"),
        ("R", "+3V3", "LTE_STATUS_N", "10k"),
        ("R", "LTE_NET_STATUS", "LTE_NET_B", "4.7k"),
        ("R", "LTE_NET_B", "GND", "47k"),
        ("R", "VDD_4G", "LTE_NETLED_A", "2.2k"),
    ])
    sh.D(142.24, 223.52, "LTE_NETLED_A", "LTE_NETLED_K", "网络灯", "Device:LED", "right",
         fp="LED_SMD:LED_0402_1005Metric")
    sh.text(15.24, 231.14, "PWRKEY、RESET_N 模组内部已有上拉，外面不能再加上拉。\n"
                           "PWRKEY 拉低 1.5 s 开机；RESET_N 拉低是硬关机，不是重启。\n"
                           "STATUS 经三极管反相：模组开机后 LTE_STATUS_N 为低。", 1.3)

    sh.frame(182.88, 17.78, 292.1, 248.92, "Air780E")
    sh.place(AIR780E, 238.76, 86.36, {
        "VBAT": "VDD_4G", "GND": "GND", "PWRKEY": "LTE_PWRKEY", "RESET_N": "LTE_RESET_N",
        "STATUS": "LTE_STATUS", "NET_STATUS": "LTE_NET_STATUS", "VDD_EXT": "LTE_VDD_EXT",
        "RefVolt": "LTE_VREF", "IO_Volt_Set": "LTE_IOSEL", "USB_DP": "LTE_USB_DP", "USB_DM": "LTE_USB_DM",
        "VBUS": "LTE_VBUS", "USB_BOOT": "LTE_USB_BOOT", "MAIN_RXD": "LTE_RXD", "MAIN_TXD": "LTE_TXD",
        "DBG_RXD": "LTE_DBG_RX", "DBG_TXD": "LTE_DBG_TX", "LTE_ANT": "LTE_ANT",
        "USIM_VDD": "SIM_VDD", "USIM_RST": "SIM_RST", "USIM_CLK": "SIM_CLK", "USIM_DAT": "SIM_DAT",
        "USIM_DET": "SIM_DET",
    }, nc=["MAIN_DTR", "MAIN_RI", "MAIN_DCD", "MAIN_CTS", "MAIN_RTS",
           "USIM2_VDD", "USIM2_RST", "USIM2_CLK", "USIM2_DAT", "NC"],
        value="Air780E（北美版换贴 Air780EEN）")
    sh.hlist(238.76, 142.24, [
        ("R", "LTE_IOSEL", "GND", "0R", "dnp"),
        ("R", "VDD_4G", "LTE_VBUS", "10k"),      # fitted: the module's USB-detect pin is high whenever the module has power
    ])
    tps = ["LTE_PWRKEY", "LTE_VDD_EXT", "LTE_USB_BOOT", "LTE_USB_DP", "LTE_USB_DM", "LTE_VBUS",
           "LTE_RXD", "LTE_TXD", "LTE_DBG_RX", "LTE_DBG_TX"]
    for i, net in enumerate(tps):
        sh.tp(190.5 + (i % 5) * 20.32, 185.42 + (i // 5) * 33.02, net)
    sh.text(185.42, 205.74, "61 脚（VBUS，USB 插入检测）经 10k 接模组自己的供电：板上 4G 的数据只走 USB，\n"
                            "电池供电时没有外部 5 V，这个脚不拉高模组可能不枚举。接法和阻值待合宙确认。", 1.3)
    sh.text(185.42, 228.6, "100 脚不接（Air780EEN 只有 1.8 V 电平）。主串口、调试串口、USB、\n"
                           "USB_BOOT 只引到测试点，用于升级模组固件和抓日志。\n"
                           "53 个悬空焊盘（AT 方式下不接）在符号里是隐藏脚，不能接地。", 1.3)

    sh.frame(297.18, 17.78, 406.4, 180.34, "SIM 卡（Nano SIM 自弹卡座）")
    sh.place(NANO_SIM, 381, 45.72,
             {"1": "SIM_VDD", "2": "SIM_RST_C", "3": "SIM_CLK_C", "7": "SIM_DAT_C", "SW": "SIM_DET",
              "5": "GND", "SH": "GND"}, nc=["6"], value="Nano SIM 卡座")
    sh.hlist(350.52, 71.12, [
        ("R", "SIM_RST", "SIM_RST_C", "22R"),
        ("R", "SIM_CLK", "SIM_CLK_C", "22R"),
        ("R", "SIM_DAT", "SIM_DAT_C", "22R"),
        ("R", "LTE_VREF", "SIM_DET", "100k"),
    ])
    sh.caps(309.88, 124.46, "SIM_VDD", ["100nF", "33pF"])
    for i, net in enumerate(["SIM_RST_C", "SIM_CLK_C", "SIM_DAT_C"]):
        sh.caps(340.36 + i * 12.7, 124.46, net, ["33pF"])
    sh.place("Power_Protection:SRV05-4", 375.92, 154.94,
             {"IO1": "SIM_RST_C", "IO2": "SIM_CLK_C", "IO3": "SIM_DAT_C", "IO4": "SIM_DET",
              "VP": "SIM_VDD", "VN": "GND"})

    sh.frame(297.18, 185.42, 406.4, 248.92, "4G 天线（50 Ω，π 型匹配）")
    sh.hlist(337.82, 198.12, [("R", "LTE_ANT", "LTE_ANT_C", "0R")])
    sh.C(312.42, 223.52, "LTE_ANT", "GND", "待调", dnp=True)
    sh.C(337.82, 223.52, "LTE_ANT_C", "GND", "待调", dnp=True)
    sh.place("Connector:Conn_Coaxial", 388.62, 215.9, {"In": "LTE_ANT_C", "Ext": "GND"}, value="IPEX 座",
             fp="Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical")
    sh.text(299.72, 238.76, "两颗对地电容先不贴，天线调试后定值。Wi-Fi 天线座在 ESP32 模组上。", 1.3)
    return sh


# =============================================================================
# 5. Display
# =============================================================================
def display():
    sh = d.sheet("display.kicad_sch", "5 屏、触摸、背光")

    sh.frame(12.7, 17.78, 213.36, 248.92, "屏 LB28BOE47（480 × 640，NV3049F）和触摸")
    sh.place(LCD_FPC, 38.1, 73.66, {
        "1": "LCD_LEDA", "2": "LCD_LEDK", "3": "LCD_SDA", "4": "LCD_SCL", "6": "LCD_VCI",
        "7": "LCD_G7", "8": "LCD_G6", "9": "LCD_G5", "10": "LCD_G4", "11": "LCD_G3", "12": "LCD_G2",
        "13": "LCD_G1", "14": "LCD_G0", "15": "LCD_CS", "16": "LCD_PCLK_R", "17": "LCD_HSYNC",
        "18": "LCD_DE", "19": "LCD_VSYNC", "20": "LCD_RST", "21": "GND", "22": "GND", "MP": "GND",
    }, nc=["5"], value="屏排线座 22P 0.5mm")
    sh.hlist(134.62, 38.1, [
        ("R", "LCD_PCLK", "LCD_PCLK_R", "33R"),
        ("R", "U0TXD", "LCD_VSYNC", "470R"),
        ("R", "U0RXD", "LCD_HSYNC", "100R"),
        ("R", "LCD_RST", "GND", "4.7k"),
        ("R", "+3V3", "LCD_VCI", "0R"),
        ("R", "LCD_G0", "GND", "0R"),
        ("R", "LCD_G1", "GND", "0R"),
        ("R", "LCD_G2", "GND", "0R"),
    ])
    # R58 .. R60 were three unfitted 0R links from G0 .. G2 to the TF card lines (all 8 data lines, but then no TF
    # card). The first board uses 5 data lines and keeps the TF card (decided 2026-11-11); the links are gone: each
    # dragged a 40 mm track across the whole board. Their numbers are not used again, so every later R keeps its own.
    d.refs["R"] += 3
    sh.caps(180.34, 50.8, "LCD_VCI", ["1µF", "100nF"], pitch=12.7)
    sh.text(96.52, 121.92,
            "数据线只接高 5 位（G3 ~ G7），低 3 位经 0R 接地。\n"
            "首版不做 8 位全接：那要借 TF 卡的 3 根线，两者不能同时用。\n"
            "要 8 位全接又保留 TF 卡，需要重新分配 ESP32 的引脚。\n"
            "屏的复位有下拉：扩展芯片初始化之前屏保持复位，\n"
            "上电时串口 0 打印的启动信息不会被屏当成同步信号。\n"
            "屏的三线 SPI（CS、SCL、SDA）和复位在扩展芯片上。", 1.3)
    sh.place(TP_FPC, 38.1, 190.5,
             {"1": "+3V3", "2": "GND", "3": "I2C_SCL", "4": "I2C_SDA", "5": "TP_INT", "6": "TP_RST",
              "MP": "GND"}, value="触摸排线座 6P（脚位待定）")
    sh.hlist(134.62, 185.42, [("R", "+3V3", "TP_RST", "10k")])
    sh.caps(180.34, 193.04, "+3V3", ["100nF"])
    sh.text(15.24, 223.52, "触摸芯片型号和排线脚位还没拿到，这里按常见的 6 脚定义占位。", 1.3)

    backlight(sh)
    return sh


# =============================================================================
# 6. Cameras
# =============================================================================
def camera():
    sh = d.sheet("camera.kicad_sch", "6 摄像头：后摄 OV2640、前摄、总线切换、电源")

    def cam(y, side, name, dvdd, iovdd):
        p = "CAM" + side
        sh.place(CAM_FPC, 33.02, y, {
            "2": "GND", "3": "I2C_SDA", "4": "+2V8", "5": "I2C_SCL", "6": "CAM_RST",
            "7": p + "_VSYNC", "8": p + "_PWDN", "9": p + "_HREF", "10": dvdd, "11": iovdd,
            "12": p + "_D7", "13": p + "_XCLK", "14": p + "_D6", "15": "GND", "16": p + "_D5",
            "17": p + "_PCLK", "18": p + "_D4", "19": p + "_D0", "20": p + "_D3", "21": p + "_D1",
            "22": p + "_D2", "MP": "GND"}, nc=["1", "23", "24"], value=name)

    sh.frame(12.7, 17.78, 101.6, 248.92, "摄像头排线座（24P 0.5mm）")
    cam(71.12, "R", "后摄 OV2640", "+1V2", "+3V3")
    cam(187.96, "F", "前摄 30 万（型号待定）", "CAMF_DVDD", "CAMF_IOVDD")

    sh.frame(106.68, 17.78, 251.46, 248.92, "并口总线切换（CAM_SEL = 0 后摄，1 前摄）")
    groups = [["D0", "D1", "D2", "D3"], ["D4", "D5", "D6", "D7"], ["PCLK", "VSYNC", "HREF", None]]
    for i, sigs in enumerate(groups):
        nets = {"VCC": "+3V3", "GND": "GND", "S": "CAM_SEL", "~{OE}": "GND"}
        nc = []
        for ch, sig in enumerate(sigs, start=1):
            if sig is None:
                nc += [f"{ch}A", f"{ch}B1", f"{ch}B2"]
                continue
            nets[f"{ch}A"] = "CAM_" + sig
            nets[f"{ch}B1"] = "CAMR_" + sig
            nets[f"{ch}B2"] = "CAMF_" + sig
        sh.place(MUX3257, 177.8, 53.34 + i * 48.26, nets, nc=nc, value="74CBTLV3257",
                 fp="Package_SO:TSSOP-16_4.4x5mm_P0.65mm")
    sh.caps(127, 208.28, "+3V3", ["100nF", "100nF", "100nF"], pitch=12.7)
    sh.text(109.22, 226.06,
            "两颗摄像头不直接并在一起：前摄型号没定，\n"
            "不确定它待机时数据脚是不是高阻，所以第一版先用总线开关隔开。\n"
            "以后确认两颗都能高阻，这三颗芯片可以去掉。", 1.3)

    sh.frame(256.54, 17.78, 406.4, 248.92, "摄像头电源、时钟、控制")
    sh.place("Regulator_Linear:ME6211C28M5", 317.5, 43.18,
             {"1": "+3V3", "2": "GND", "3": "CAM_PWR_EN", "5": "+2V8"}, nc=["4"], value="2.8 V LDO")
    sh.place("Regulator_Linear:ME6211C12M5", 317.5, 76.2,
             {"1": "+3V3", "2": "GND", "3": "CAM_PWR_EN", "5": "+1V2"}, nc=["4"], value="1.2 V LDO")
    sh.caps(360.68, 45.72, "+2V8", ["1µF", "100nF", "100nF"], pitch=12.7)
    sh.caps(360.68, 78.74, "+1V2", ["1µF", "100nF"], pitch=12.7)
    sh.caps(271.78, 109.22, "+3V3", ["1µF", "1µF", "100nF", "100nF"], pitch=12.7)
    sh.caps(335.28, 109.22, "CAMF_DVDD", ["100nF"])
    sh.caps(353.06, 109.22, "CAMF_IOVDD", ["100nF"])
    sh.place("Oscillator:ASE-xxxMHz", 317.5, 144.78,
             {"EN": "CAM_PWR_EN", "Vdd": "+3V3", "GND": "GND", "OUT": "CAM_XCLK"}, value="24 MHz 有源晶振",
             fp="Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm")
    sh.hlist(332.74, 175.26, [
        ("R", "CAM_XCLK", "CAMR_XCLK", "33R"),
        ("R", "CAM_XCLK", "CAMF_XCLK", "33R"),
        ("R", "+3V3", "CAMR_PWDN", "10k"),
        ("R", "+3V3", "CAMF_PWDN", "10k"),
        ("R", "+3V3", "CAM_RST", "10k"),
        ("R", "CAM_PWR_EN", "GND", "4.7k"),
        ("R", "+3V3", "CAM_PWR_EN", "10k", "dnp"),
        ("R", "CAM_SEL", "GND", "10k"),
    ])
    sh.hlist(383.54, 175.26, [
        ("R", "+3V3", "CAMF_IOVDD", "0R"),
        ("R", "+2V8", "CAMF_IOVDD", "0R", "dnp"),
        ("R", "+1V2", "CAMF_DVDD", "0R", "dnp"),
    ])
    sh.text(259.08, 236.22,
            "CAM_PWR_EN 同时开 2.8 V、1.2 V 和晶振，默认关。PWDN 默认上拉，两颗摄像头上电后都在待机。\n"
            "摄像头的 IO 电源（排线 11 脚）必须一直有电，否则断电的摄像头会把共用的 I²C 总线拉死。\n"
            "前摄如果是 GC0308 这类只用 11 脚单独供 2.8 V 的型号：11 脚改接 2.8 V，\n"
            "并把 CAM_PWR_EN 的下拉换成上拉（让 2.8 V 上电即有）；10 脚的 0R 不贴。", 1.3)
    return sh


# =============================================================================
# 7. Audio and TF card
# =============================================================================
def audio_tf():
    sh = d.sheet("audio_tf.kicad_sch", "7 音频、TF 卡")

    sh.frame(12.7, 17.78, 137.16, 132.08, "I²S 麦克风")
    microphone(sh)

    sh.frame(142.24, 17.78, 406.4, 132.08, "I²S 功放（MAX98357A）和喇叭")
    sh.place("Audio:MAX98357A", 200.66, 66.04,
             {"DIN": "I2S_DOUT", "BCLK": "I2S_BCLK", "LRCLK": "I2S_WS", "~{SD_MODE}": "PA_EN",
              "GAIN_SLOT": "PA_GAIN", "OUTP": "PA_OUTP", "OUTN": "PA_OUTN", "VDD": "VSYS", "GND": "GND",
              "PAD": "GND"}, nc=["NC"])
    sh.hlist(289.56, 40.64, [
        ("FB", "PA_OUTP", "SPK_P", "磁珠"),
        ("FB", "PA_OUTN", "SPK_N", "磁珠"),
        ("C", "SPK_P", "GND", "220pF", "dnp"),
        ("C", "SPK_N", "GND", "220pF", "dnp"),
        ("R", "PA_GAIN", "GND", "0R", "dnp"),
        ("R", "PA_EN", "GND", "2.2k"),
    ])
    sh.place("Connector_Generic:Conn_01x02", 373.38, 48.26, {"1": "SPK_P", "2": "SPK_N"}, value="喇叭焊盘",
             fp="zeebuddy:SpeakerPads")
    sh.caps(160.02, 109.22, "VSYS", [("10µF", FP_0603), "100nF"], pitch=12.7)
    sh.text(233.68, 96.52,
            "功放直接用电池电压供电，输出功率比用 3.3 V 大。\n"
            "PA_EN 高：工作（取左声道）；低：关断。2.2k 下拉保证上电时是关断。\n"
            "不用更便宜的 NS4168：它的逻辑高电平要到 0.7 × 供电电压，用电池供电时 3.3 V 信号不够。\n"
            "增益脚悬空 = 9 dB；贴 0R 接地 = 12 dB。", 1.3)

    sh.frame(12.7, 137.16, 406.4, 248.92, "TF 卡（SD 一线模式：CLK、CMD、D0）")
    sh.place("Connector:Micro_SD_Card_Det_Hirose_DM3AT", 111.76, 195.58,
             {"DAT2": "SD_D2", "DAT3/CD": "SD_D3", "CMD": "SD_CMD", "VDD": "+3V3", "CLK": "SD_CLK_R",
              "VSS": "GND", "DAT0": "SD_D0", "DAT1": "SD_D1", "DET_B": "SD_DET", "DET_A": "GND",
              "SHIELD": "GND"},
             value="TF 卡座（带检测）", fp="Connector_Card:microSD_HC_Molex_104031-0811")
    sh.hlist(220.98, 162.56, [
        ("R", "SD_CLK", "SD_CLK_R", "22R"),
        ("R", "+3V3", "SD_CMD", "10k"),
        ("R", "+3V3", "SD_D0", "10k"),
        ("R", "+3V3", "SD_D1", "10k"),
        ("R", "+3V3", "SD_D2", "10k"),
        ("R", "+3V3", "SD_D3", "10k"),
    ])
    sh.caps(289.56, 180.34, "+3V3", [("10µF", FP_0603), "100nF"], pitch=12.7)
    sh.text(271.78, 210.82,
            "D1、D2、D3 不接主控，只上拉。D3 必须为高，卡才会进 SD 模式。\n"
            "卡检测开关接扩展芯片，插卡时拉低（极性随卡座型号，待核对）。", 1.3)
    return sh


# ---- values taken from the datasheets ----------------------------------------------
RILIM = "680R 1%"     # SY6970: IINMAX = K / R, K = 360 A·Ω typ -> about 0.53 A (see the note on the sheet)
TS_TOP = "10k"        # 50 % of REGN sits between the 44.75 % and 68.25 % thresholds
TS_BOT = "10k"
EXP_VALUE = "XL9555QF24"


def microphone(sh):
    sh.place(MIC, 73.66, 66.04,
             {"VDD": "+3V3", "CHIPEN": "+3V3", "L/R": "GND", "GND": "GND",
              "WS": "I2S_WS", "SCK": "I2S_BCLK", "SD": "I2S_DIN"}, nc=["NC"])
    sh.hlist(73.66, 99.06, [("R", "I2S_DIN", "GND", "100k")])
    sh.caps(22.86, 99.06, "+3V3", [("10µF", FP_0603), "100nF"])
    sh.text(15.24, 114.3, "L/R 接地 = 左声道；CHIPEN 接高 = 一直工作。\n"
                          "数据线下拉 100k 是数据手册的要求。\n"
                          "这颗是顶部进音，外壳的进音孔要对着它；要底部进音得换型号。", 1.3)


def backlight(sh):
    sh.frame(218.44, 17.78, 406.4, 248.92, "背光升压恒流（SY7200A）")
    sh.place(WLED, 289.56, 60.96,
             {"IN": "VSYS", "EN/PWM": "LCD_BL_PWM", "GND": "GND", "LX": "BL_SW", "OVP": "LCD_LEDA",
              "FB": "LCD_LEDK"})
    sh.hlist(350.52, 96.52, [
        ("L", "VSYS", "BL_SW", "22µH", "", FP_L_SMALL),
        ("R", "LCD_LEDK", "GND", "10R 1%"),
    ])
    sh.D(350.52, 119.38, "BL_SW", "LCD_LEDA", "肖特基 40V", "Device:D_Schottky", "right",
         fp="Diode_SMD:D_SOD-323")
    sh.caps(243.84, 111.76, "VSYS", [("4.7µF", FP_0603)])
    sh.caps(269.24, 111.76, "LCD_LEDA", [("2.2µF 50V", FP_0805)])
    sh.text(220.98, 147.32,
            "LED 电流 = 0.2 V / 10 Ω = 20 mA。\n"
            "按华迪创显 HD28142C22 的规格书：6 颗灯串联，18 V、20 mA，\n"
            "电流的绝对上限也是 20 mA，不能再调高。\n"
            "GPIO45 输出 PWM 调光（20 kHz ~ 1 MHz），上电默认低 = 背光关。\n"
            "屏没插时输出会升到过压保护点（约 30 V），输出电容选 50 V。", 1.3)


if __name__ == "__main__":
    power()
    mcu()
    expander()
    cellular()
    display()
    camera()
    audio_tf()
    d.root_text = [
        (25.4, 17.78, "Zeebuddy 主板 V1 原理图（草稿）", 3.0),
        (25.4, 26.67, "主控 ESP32-S3-WROOM-1U-N16R8，4G 模组 Air780E（可换贴北美版 Air780EEN）。\n"
                      "各页之间靠同名的网络标号连接；引脚分配见 docs/requirements.md 的方案三。", 1.5),
        (25.4, 137.16,
         "画板之前还要确认的：\n"
         "1. 屏 LB28BOE47：背光电压电流、VCI 电压、排线间距和上下接、8 根数据线里哪几根有效、能否只用 DE。\n"
         "2. 触摸屏：芯片型号、排线脚位。\n"
         "3. 前摄：型号、排线脚位、10 脚要不要供电。\n"
         "4. 电池（2000 mAh，最大充电 0.5C）：电池座型号、有没有温度电阻脚。\n"
         "5. 按键：排线脚位，是否包含开关机键。\n"
         "6. 各连接器的具体型号（Type-C、SIM 卡座、TF 卡座、排线座、电池座、喇叭座）。\n"
         "7. 220 µF 钽电容的高度是否放得进外壳。", 1.5),
        (25.4, 172.72,
         "本图由 gen/design.py 生成。改电路请改脚本后运行 gen/build.sh，不要直接在 KiCad 里改图。", 1.5),
    ]
    d.write(OUT)
    print(f"wrote {len(d.sheets)} sheets, {len({r for r, _ in d.expect})} parts, "
          f"{len({n for n in d.expect.values() if n})} nets -> {os.path.abspath(OUT)}")
