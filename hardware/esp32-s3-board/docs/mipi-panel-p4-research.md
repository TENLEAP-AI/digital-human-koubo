# MIPI 版屏（HXW661528）与 ESP32-P4 路线调研

> **状态：不采用。** 已决定主控固定用 ESP32-S3，不讨论 ESP32-P4 路线。本文只作为调研记录保留。

屏厂另有一份 MIPI 接口的总成图（HXW661528，2.8 寸，带触摸）。ESP32-S3 没有 MIPI 接口，
用这块屏就意味着主控要换成带 MIPI 的 ESP32-P4。这里记录这块屏的接口、P4 的官方资料要点，以及两条路线的对比。

## 资料来源

| 文档 | 版本 | 链接 |
|---|---|---|
| 屏厂总成图 HXW661528 | — | 用户提供的截图 |
| ESP32-P4 Series Datasheet | Pre-release v0.7 | https://www.espressif.com/sites/default/files/documentation/esp32-p4_datasheet_en.pdf |
| ESP32-P4 Hardware Design Guidelines | master | https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32p4/index.html |
| ESP-IoT-Solution《MIPI DSI LCD 详解》 | latest | https://docs.espressif.com/projects/esp-iot-solution/zh_CN/latest/display/lcd/mipi_dsi_lcd.html |
| ESP32-S3 Technical Reference Manual 第 29 章 | — | https://www.espressif.com/sites/default/files/documentation/esp32-s3_technical_reference_manual_en.pdf |

## 屏的接口（来自总成图）

- 2.83 寸，480 × 640，显示区 43.20 × 57.60 mm，总成高 65.05 mm，排线长 58.34 mm。
- 驱动芯片在图上被隐去（`*****`），需要问屏厂。
- 排线端是 30 脚板对板连接器，型号 OK-23GM030-04。**屏和触摸在同一个连接器上。**
- 背光：6 颗灯，40 mA，9.6 V。需要升压恒流驱动。
- 工作温度 −20 ~ 70 °C。

| 脚 | 信号 | 脚 | 信号 | 脚 | 信号 |
|---|---|---|---|---|---|
| 1 | VDD 2.8 V | 11 | D3P | 21 | TP_VDD 2.8 V |
| 2 | TE | 12 | D3N | 22 | IOVCC 1.8 V |
| 3 | RESET | 13 | GND | 23 | TP_SDA |
| 4 | GND | 14 | D0P | 24 | TP_SCL |
| 5 | CLKP | 15 | D0N | 25 | LEDA |
| 6 | CLKN | 16 | D1P | 26 | LEDA |
| 7 | GND | 17 | D1N | 27 | TP_RESET |
| 8 | D2P | 18 | GND | 28 | TP_INT |
| 9 | D2N | 19 | ID / NC | 29 | LEDK |
| 10 | GND | 20 | NC | 30 | LEDK |

要注意的点：

- 连接器上引出了 **4 条数据通道**（D0 ~ D3），而 ESP32-P4 最多支持 2 条。
  480 × 640、60 帧 / 秒、24 位色只需要约 557 Mbps，2 条通道每条约 279 Mbps，速率上没有问题；
  公开的 2.8 寸 480 × 640 NV3049F 驱动也是用 2 条通道。但**这块屏能否工作在 2 通道模式，必须由屏厂确认**。
- 屏的逻辑电平是 1.8 V（IOVCC），电源是 2.8 V，触摸电源也是 2.8 V。板上要有 2.8 V 和 1.8 V 两路电源，
  复位、TE、触摸信号要和主控的 IO 电平匹配。
- 参考主板 M03 上屏的位置也是一个 30 脚板对板座（YXT-BB10-30S-02）。两者是否能互配需要核对连接器规格，
  但接口形式一致，说明这块 MIPI 屏很可能就是参考整机用的屏。

## ESP32-P4 官方资料要点

- 双核 RISC-V，最高 400 MHz；芯片内合封 16 MB 或 32 MB PSRAM；55 个 GPIO。
- **MIPI DSI：2 条数据通道，每条最高 1.5 Gbps，目前只支持 Video 模式。** MIPI 用专用引脚，不占 GPIO。
- MIPI CSI（2 通道）、并口摄像头接口、图像信号处理器（ISP）、硬件 JPEG 编解码、H.264 编码、像素处理加速器。
- USB 2.0 高速 + 全速、SD 卡主机、5 路串口、3 路 I2S。
- **没有 Wi-Fi 和蓝牙。** 官方开发板是外挂一颗无线芯片（ESP32-C6 或 C5）。
- 封装 QFN104，10 × 10 mm。**乐鑫只列了开发板，没有列官方模组**，要自己做芯片级设计。
- 外围：除约 40 个阻容外，还要一颗外部 DCDC（给内核供 1.1 V 左右，官方给了验证过的型号清单）、
  一颗 SPI Flash、一颗 40 MHz 晶振。电源脚种类多（内核、IO 分组、MIPI PHY、USB PHY、Flash、PSRAM 等）。
- 最小工作供电电流 380 mA（含 Flash 和 PSRAM），外设另算。
- Layout：至少四层板；MIPI 差分阻抗 100 Ω ±10%，对内长度差控制在 10 mil 以内，下方参考地平面连续。
- 乐鑫的 USB 4G 组件支持列表里，Air780E 在 ESP32-P4 一栏也是"支持"。

## ESP32-S3 能不能接 MIPI 屏

不能直接接。MIPI 转接芯片要么需要 16 ~ 24 根并口 RGB 输入（比现在的屏占的引脚还多），
要么要求屏带显存。在 ESP32-S3 上用 MIPI 屏没有可行的做法。

## 两条路线对比

| | ESP32-S3 + 串行 RGB 屏（LB28BOE47） | ESP32-P4 + MIPI 屏（HXW661528） |
|---|---|---|
| 屏刷新率 | 约 20 ~ 30 帧 / 秒，是否够用未知 | 60 帧 / 秒 |
| 颜色 | 32768 色（接 5 根数据线） | 全色 |
| 屏占的 GPIO | 9 个 + 背光 | 0 个（专用 MIPI 脚），另加复位和背光 |
| 触摸 | 另一条排线、另一个座子 | 和屏同一个 30 脚座 |
| 摄像头 | OV2640 并口；取景约 10 帧 / 秒（估算） | 可用 MIPI 摄像头，有 ISP 和硬件 JPEG；也能继续用 OV2640 |
| GPIO 余量 | 33 个用满 | 55 个，宽裕 |
| Wi-Fi / 蓝牙 | 自带 | 没有，要加一颗 ESP32-C6 或 C5 |
| 主控硬件 | 模组，外围简单 | 只有芯片，要外配 DCDC、Flash、晶振和约 40 个阻容 |
| 元件高度 | 模组高 2.4 ~ 3.2 mm，超过参考板的 1.75 mm | 芯片级设计，高度能压到参考板的水平 |
| 功耗 | 低 | 高（芯片最小供电电流 380 mA） |
| 物料成本 | 低 | 高（P4 + 无线芯片 + Flash + DCDC） |
| 软件 | 现有的 ESP32-S3 界面代码直接用 | 同为 ESP-IDF，界面代码可移植，驱动和无线部分要改 |
| 主要风险 | 刷新率够不够、屏和摄像头同时跑的流畅度 | 硬件设计复杂、板子更挤、周期更长 |

## 走 P4 路线前要向屏厂确认的

1. 驱动芯片型号和 MIPI 初始化代码。
2. **是否支持 2 通道模式**；支持的通道速率范围。
3. 推荐时序（前后沿、同步脉宽）和刷新率范围。
4. 30 脚连接器 OK-23GM030-04 的配对母座型号，是否与参考主板上的座子通用。
5. 触摸芯片型号。
