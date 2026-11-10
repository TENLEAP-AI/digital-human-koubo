# Zeebuddy 主板 V1 原理图（KiCad 9）

ESP32-S3-WROOM-1U-N16R8 + Air780E 的主板原理图，第一版，**草稿**。引脚分配按 `../docs/requirements.md` 的方案三。

## 文件

| 文件 | 内容 |
|---|---|
| `zeebuddy-mainboard.pdf` | 原理图 PDF，直接看这个 |
| `zeebuddy-mainboard.kicad_pro` / `.kicad_sch` | KiCad 工程和顶层图 |
| `power.kicad_sch` | 1 电源：Type-C、充电（BQ25895）、电池、3.3 V |
| `mcu.kicad_sch` | 2 主控：ESP32-S3 模组、下载口、USB 切换 |
| `expander.kicad_sch` | 3 两颗 I²C 扩展芯片、按键 |
| `cellular.kicad_sch` | 4 4G：Air780E、SIM 卡、天线 |
| `display.kicad_sch` | 5 屏、触摸、背光 |
| `camera.kicad_sch` | 6 前后摄像头、总线切换、摄像头电源 |
| `audio_tf.kicad_sch` | 7 麦克风、功放、TF 卡 |
| `zeebuddy.kicad_sym` | 工程自带的符号（Air780E、排线座等） |
| `gen/` | 生成原理图的脚本 |

## 这份图是脚本生成的

原理图不是在 KiCad 里手画的，而是由 `gen/design.py` 生成。每个引脚引出一小段线，接一个网络标号，
同名的标号就是连在一起，所以图上看不到长连线。

要改电路：改 `gen/design.py`，然后运行

```bash
gen/build.sh
```

它会重新生成全部图纸，用 KiCad 导出网表并和脚本里写的连接逐脚比对，再跑 ERC、导出 PDF。
直接在 KiCad 里改图，下次生成时会被覆盖。

## 检查结果

- 网表比对：815 个引脚全部与脚本里写的连接一致。
- KiCad ERC：0 个错误，1 个警告（功放散热焊盘接地，符号库里这个脚的类型是"未指定"，可以忽略）。

这两项只说明"图画出来和脚本写的一致、没有悬空或短接"，**不代表电路经过了实物验证**。

## 元件脚位的出处

| 元件 | 脚位出处 |
|---|---|
| ESP32-S3 模组、BQ25895、TCA9555、MAX98357A、FSUSB42、TLV62569、ME6211、TPS61165、ICS-43434、三极管、MOS 管、保护器件 | KiCad 9 官方符号库 |
| Air780E | 合宙《Air780E 硬件手册》AT 方式管脚表，109 个焊盘 |
| 摄像头 24 脚排线 | 乐鑫 ESP32-S3-EYE 主板原理图的 J4 |
| 屏 22 脚排线 | 屏厂的 LB28BOE47 确认图 |
| 74CBTLV3257 | 按标准脚位自建，对照过 KiCad 官方库里同型号的分单元符号 |
| 触摸排线、按键排线、SIM 卡座 | **占位，脚位待定** |

## 还没定的

见顶层图上的清单。封装只填了有把握的（阻容、芯片、模组）；连接器的封装是占位，画板前要按实际型号换。
