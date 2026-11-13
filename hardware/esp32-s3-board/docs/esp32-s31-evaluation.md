# ESP32-S31 评估：要不要把主控从 ESP32-S3 换成 ESP32-S31

日期：2026-11-13。依据是乐鑫官方的规格书、技术参考手册、ESP-IDF 源码和组件清单（第 7 节），不是二手文章。
**芯片和模组的规格书都还是"预发布 v0.5"版**，数字可能会改，定型前要再核一次。

## 1. 结论

**2026-11-13 已决定换。**引脚分配见 [esp32-s31-pinmap.md](esp32-s31-pinmap.md)。开发板验证照做，用来定细节，不再决定换不换。它正好解决我们现在最卡的三件事：引脚不够、屏刷新慢、USB 要切换。
ESP-IDF 和我们要用的几个驱动组件都已经正式支持它。风险是芯片太新、规格书还是预发布版、国内货源和价格还没查。

## 2. 对我们最重要的几点

| 项目 | ESP32-S3（现在） | ESP32-S31 | 对我们意味着什么 |
|---|---|---|---|
| 模组可用 GPIO | 33 个，**已全部用完** | **54 个**（WROOM-1U） | 多出 21 个。屏 8 根数据线全接、TF 卡 4 线、独立调试串口，还有余量 |
| PSRAM | 八线，80 MHz | 八线 DDR，**250 MHz**，封装在芯片里 | 内存带宽大约 3 倍。屏刷新慢、和摄像头抢带宽的问题会好很多 |
| USB | 一个全速口（12 Mbps） | **两个独立的口**：一个高速 OTG（480 Mbps，专用 DM/DP 脚），一个全速"串口/JTAG"口（GPIO33/34） | Type-C 接全速口做下载调试，Air780E 接高速口。**USB 切换芯片 FSUSB42 可以去掉**，4G 也不再被 USB 速度卡住 |
| 屏接口 | 并口 RGB / 8080 | 并口 RGB / 8080，8 / 16 / 24 位；另有 PARLIO 可驱动 8080 屏 | 串行 RGB、QSPI 屏都能用。**仍然没有 MIPI** |
| QSPI | 有 | GP-SPI2 / SPI3 都支持四线，主模式最高 80 MHz | ST7102 的 QSPI 屏可以用 |
| 摄像头 | 8 位并口 | 8 / 16 位并口；硬件 JPEG 编解码（720P 30 帧） | 拍照压缩交给硬件，后摄 200 万像素更从容 |
| 图像加速 | 无 | PPA：缩放、旋转、镜像、叠图；2D-DMA | 取景画面缩放、旋转不占 CPU |
| TF 卡 | SD 主机 | SD 主机 2 个槽，最多 4 线，**引脚固定**（GPIO20 ~ 25） | 4 线读卡更快，但这 6 个脚要留给 TF 卡 |
| 处理器 | 双核 240 MHz | 双核 RISC-V 320 MHz，带浮点和 SIMD；另有低功耗核 | 更快 |
| 无线 | Wi-Fi 4、蓝牙 5 | Wi-Fi 6、蓝牙 5.4（含经典蓝牙）、Thread / Zigbee、千兆以太网 | 多了经典蓝牙，可接蓝牙耳机 |
| 供电 | 3.3 V | 3.0 ~ 3.6 V；Wi-Fi 发射峰值约 375 mA | 和 S3 差不多，现在的 3.3 V 降压（1 A）够用 |
| 模组尺寸 | WROOM-1U：18 × 19.2 × 3.2 mm | WROOM-1U：**18.0 × 20.5 × 3.2 mm**，64 个焊盘 | 长 1.3 mm，脚位完全不同，原理图和 PCB 都要改 |
| 模组型号 | N16R8 | **WROOM-1U 只有一个型号：N16R16V**（16 MB Flash + 16 MB PSRAM） | 内存比现在多一倍 |

## 2.1 我们的屏能不能带（2026-11-13 补）

**两家的屏都能带，而且比 S3 好得多。**下面的帧率是按官方给的时钟上限算的，样品到了要实测。

| | 串行 RGB（NV3049F） | QSPI（ST7102） |
|---|---|---|
| 官方的时钟上限 | ESP-IDF 的 S31 文档：8 位数据宽度时像素时钟**建议低于 80 MHz** | 规格书：通用 SPI 主模式**最高 80 MHz** |
| 每帧要送多少 | 每个像素 3 个时钟，含消隐约 100 ~ 115 万个时钟 | RGB565 每帧 61.4 万字节；四线每个时钟送半个字节，约 123 万个时钟 |
| 40 MHz 时 | 约每秒 35 ~ 40 帧 | 约每秒 32 帧 |
| 60 MHz 时 | 约每秒 52 ~ 60 帧 | 约每秒 48 帧 |
| 80 MHz 时 | 约每秒 70 ~ 80 帧 | 约每秒 65 帧（理论值，不算命令开销） |
| 对比 S3 | S3 上只能到每秒 17 ~ 22 帧 | S3 上计划 40 MHz，约每秒 32 帧 |
| 占内存带宽 | 60 MHz 时每秒约 60 MB。S31 的 PSRAM 是 250 MHz 八线双沿，原始带宽每秒约 500 MB，余量很大（这是我的估算） | 屏有显存的话只在画面变化时送；没有显存要一直送，80 MHz 时每秒约 40 MB |
| 颜色 | 8 根数据线全接，就是屏的全部颜色（RGB666，26 万色） | RGB565，6.5 万色 |
| 专用高速引脚 | 数据 D0 ~ D7 = GPIO8 ~ 15，像素时钟 GPIO40，DE GPIO43，HSYNC GPIO44，VSYNC GPIO45。全部接在这些脚上时驱动自动走直连，不经过 GPIO 交换矩阵 | SPI2 四线：CS GPIO10、数据 GPIO11 / 13 / 14 / 9、时钟 GPIO12。80 MHz 要用这组脚 |
| 这块芯片在别的产品里的用法 | NV3049F 在全志 V821 的产品里就是 8 位串行 RGB、像素时钟 71 ~ 77 MHz、每秒 55 ~ 60 帧（见 nv3049f-research.md） | 没有查到 |

几点结论：

- **串行 RGB 在 S3 上最大的风险（每秒只有 20 帧左右，可能闪）在 S31 上基本没有了**：像素时钟可以开到 60 MHz 上下，和这颗芯片在别的产品里的用法一样，每秒 50 ~ 60 帧。
- QSPI 屏在 S31 上用专用引脚能到 80 MHz，整屏每秒 60 帧左右。屏有没有显存仍然是关键。
- 摄像头也有专用高速引脚：数据 GPIO46 ~ 53、像素时钟 GPIO54、主时钟 GPIO55、VSYNC GPIO56、HREF GPIO57。
  其中 GPIO54 ~ 57 同时是 JTAG 脚，用了之后调试走 USB 口的 JTAG，不影响。
- 屏和摄像头的专用引脚不重叠，可以同时用。
- 要屏厂确认的仍然是：**串行 RGB 屏的 DOTCLK 最高能到多少；QSPI 屏的 SCK 最高多少、有没有显存。**

## 3. 软件支持（已核实）

| 要用的 | 支持情况 | 出处 |
|---|---|---|
| ESP-IDF | **v6.1 起支持**，v6.1 已正式发布 | ESP-IDF 芯片支持表、版本标签 |
| RGB 屏、8080 屏、摄像头、USB OTG、USB 串口 JTAG、SD 卡、PPA、JPEG、Wi-Fi、蓝牙、低功耗 | v6.1 都标为支持 | ESP-IDF v6.1 的 `soc_caps.h` |
| 4G 模组 USB 拨号（`iot_usbh_modem`） | 支持的芯片里**有 esp32s31** | 组件的 `idf_component.yml` |
| 摄像头驱动（`esp_video`、`esp_cam_sensor`） | 支持 esp32s31，DVP 接口，**OV2640 在支持列表里** | 组件的 `idf_component.yml` 和 README |
| 旧的摄像头驱动 `esp32-camera` | **不支持 S31**，只支持 ESP32 / S2 / S3 | 组件源码 |

ESP-IDF v6.1 里还标着"待做"的只有安全下载模式、权限管理、以太网休眠保持三项，和我们无关。

**要注意：**摄像头驱动要从 `esp32-camera` 换成 `esp_video`；ESP-IDF 要用 v6.1 以上，比 S3 常用的 v5.x 新很多，固件要按新版本写。

## 4. 换了之后主板怎么变

引脚按功能粗算（详细分配等开发板验证后再做）：

| 功能 | 引脚 | 说明 |
|---|---|---|
| 摄像头 8 位并口 | 11 | D0 ~ D7、PCLK、VSYNC、HREF（主时钟仍用板上晶振） |
| 屏 | 12 或 7 | 串行 RGB 8 根数据线全接 + 4 根同步线；QSPI 是 7 根 |
| TF 卡 4 线 | 6 | 固定 GPIO20 ~ 25 |
| 音频 I²S | 4 | |
| I²C | 2 | |
| USB 串口 / JTAG（接 Type-C） | 2 | 固定 GPIO33 / 34。Air780E 用专用的 DM / DP 脚，不占 GPIO |
| 调试串口 | 2 | 固定 GPIO58 / 59，不再和屏共用 |
| 背光调光 | 1 | |
| 按键 6 个 | 6 | 直接接主控，可以唤醒 |
| 4G 控制（开机、复位、状态、电源） | 4 | |
| 摄像头控制、触摸、屏复位等 | 约 6 | |
| **合计** | **约 56（串行 RGB）/ 51（QSPI）** | 可用 54 |

所以：用 QSPI 屏的话，**两颗 I/O 扩展芯片可以全部去掉**；用串行 RGB 屏，留一颗扩展芯片放慢信号即可。
启动配置脚是 GPIO36、37、60、61（60、61 默认上拉，决定下载模式），JTAG 在 GPIO54 ~ 57，分配时避开或小心使用。

能省掉的器件：USB 切换芯片 FSUSB42、一到两颗 XL9555、R51 / R52 这类和串口共用的电阻。

## 5. 风险

| 风险 | 程度 | 怎么办 |
|---|---|---|
| 规格书是预发布 v0.5，还没有勘误表，硬件设计指南也还没发布（官网链接打不开） | 中 | 画板时按最新版再核；向乐鑫代理要硬件设计指南和参考原理图 |
| 新芯片，量产不久，可能有没公开的问题 | 中 | 先做开发板验证；关注勘误表 |
| 国内货源、价格、交期没查 | 中 | 找代理商或立创要 WROOM-1U-N16R16V 的报价和交期 |
| 固件要用 ESP-IDF v6.1 和新的摄像头驱动 | 低 ~ 中 | 固件本来就要写，从头按新版写 |
| WROOM-1U 只有一个型号 | 低 | 正好是我们需要的配置 |

## 6. 下一步

1. **买开发板**：ESP32-S31-Korvo-1（带 DVP 摄像头、4.3 寸 RGB 屏、双麦克风、TF 卡，最接近我们的产品）。
   官方另有 ESP32-S31-Function-CoreBoard-1（引出全部常用 GPIO）。两块都用的是更大的 WROOM-3 模组（22 × 30 mm），只用来验证。
2. 屏样品回来后，在 S3 和 S31 上各测一遍帧率。
3. 在 Korvo-1 上接 Air780E 开发板，试 USB 高速拨号。
4. 问代理商：模组报价、交期、硬件设计指南、参考设计。
5. 以上都没问题，就让 PCB 工程师按 S31 画，我先把引脚详细分配出来。

## 7. 出处

| 资料 | 版本 | 地址 |
|---|---|---|
| ESP32-S31 Series Datasheet | Pre-release v0.5 | documentation.espressif.com/esp32-s31_datasheet_en.pdf |
| ESP32-S31-WROOM-1 & WROOM-1U Datasheet | Pre-release v0.5 | documentation.espressif.com/esp32-s31-wroom-1_wroom-1u_datasheet_en.pdf |
| ESP32-S31-WROOM-3 & WROOM-3U Datasheet | Pre-release | documentation.espressif.com/esp32-s31-wroom-3_wroom-3u_datasheet_en.pdf |
| ESP32-S31 Technical Reference Manual | 2026 版 | documentation.espressif.com/esp32-s31_technical_reference_manual_en.pdf |
| ESP-IDF 芯片支持表 | — | dl.espressif.com/dl/esp-idf/chip-support.svg |
| ESP-IDF `soc_caps.h`（esp32s31） | v6.1 | github.com/espressif/esp-idf |
| `iot_usbh_modem` 组件 | master | github.com/espressif/esp-iot-solution |
| `esp_video`、`esp_cam_sensor` 组件 | master | github.com/espressif/esp-video-components |
| 开发板说明 | latest | docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s31/ |
