# ESP32-S31-Korvo-1 上手步骤（在 Mac 上做）

日期：2026-11-17。对应[固件开发计划](firmware-architecture.md)的阶段 0：搭好环境，在 Korvo-1 上跑通乐鑫的"拍照问通义大模型"例程。
依据：乐鑫 Korvo-1 V1.1 用户指南、ESP-ADF 主分支的 `esp_llm_tongyi_agent_app` 例程说明（2026-11-17 查）。

## 1. 开箱接线

| 部件 | 说明 |
|---|---|
| 主板 | ESP32-S31-WROOM-3 模组（16 MB Flash、16 MB PSRAM，板载天线），双麦克风，ES8389 音频编解码，两路喇叭输出，TF 卡座，DVP 摄像头 |
| 屏子板 | ESP32-S3-LCD-EV-Board-SUB3，4.3 寸，插到主板的 LCD 接口 |
| 摄像头 | SC101IOT（100 万像素，**只出 YUV，没有 JPEG**，JPEG 由 S31 的硬件编码）。我们产品用的 OV2640 自带 JPEG |
| 两个 Type-C | **UART 口**：供电 + 烧录 + 看日志，**接 Mac 用这个**。**Power 口**：只供电。喇叭开大声时两个口都插上 |
| USB-A 口 | 接 S31 的高速 USB，S31 当主机。以后可以把 Air780E 开发板插这里，提前测 4G 拨号 |
| 电源开关 | 拨到 ON，红色电源灯亮 |
| Boot 键 / Reset 键 | 烧录连不上时：按住 Boot，按一下 Reset，松开 Boot，进下载模式 |

接线顺序：插屏子板 → 接喇叭（2.0 mm 间距接口，4 Ω 3 W 以内）→ UART 口接 Mac → 拨电源开关。

## 2. 装开发环境（只需一次，约 30 分钟）

打开"终端"，依次运行：

```
# 1) 装 Homebrew（已装过跳过），再装编译工具
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install cmake ninja dfu-util python3

# 2) 下载 ESP-IDF v6.1.1（第一个支持 S31 的正式版系列）
mkdir -p ~/esp && cd ~/esp
git clone -b v6.1.1 --recursive https://github.com/espressif/esp-idf.git

# 3) 只装 S31 用的工具链
cd ~/esp/esp-idf && ./install.sh esp32s31
```

以后**每开一个新终端窗口**，先运行这一句让命令生效：

```
. ~/esp/esp-idf/export.sh
```

看串口：开发板 UART 口接 Mac 后运行 `ls /dev/cu.*`，会多出一个 `/dev/cu.usbserial-…` 或 `/dev/cu.SLAB_USBtoUART` 之类的名字，下面的 `PORT` 就填它。
看不到的话，按板上 USB 转串口芯片的型号装驱动（芯片上有丝印）。

## 3. 第一步：跑 Hello World（确认环境和板子都好）

```
cd ~/esp && cp -r esp-idf/examples/get-started/hello_world .
cd hello_world
idf.py set-target esp32s31
idf.py -p PORT flash monitor
```

看到 `Hello world!` 和芯片信息就成功。按 `Ctrl-]` 退出。

## 4. 第二步：出厂测试程序（检查屏、麦克风、喇叭、摄像头）

乐鑫给 Korvo-1 写了出厂测试程序，在 esp-dev-kits 仓库的 `examples/esp32-s31-korvo/examples/factory_demo`：

```
cd ~/esp && git clone --depth 1 https://github.com/espressif/esp-dev-kits.git
cd esp-dev-kits/examples/esp32-s31-korvo/examples/factory_demo
idf.py set-target esp32s31
idf.py -p PORT flash monitor
```

按程序的提示逐项测，哪一项不正常先记下来。

## 5. 第三步：拍照问通义大模型（阶段 0 的目标）

### 5.1 先准备阿里云的账号信息

在阿里云百炼（DashScope）控制台拿到三样东西：

1. **API Key**
2. **业务空间 ID**（Workspace ID）
3. **应用 ID**：要建一个**多模态（看图）应用**，ID 以 `mm_` 开头。只建语音应用的话拍照会报错 `images must not be empty`

**注意**：例程会把这些编进固件，只适合开发测试。量产时密钥放在我们自己的后台，不进固件（见固件架构第 4 节）。
例程里预置了乐鑫内部实验室的密钥，要换成自己的。**真实密钥不要提交到仓库**。

### 5.2 编译烧录

```
cd ~/esp && git clone --depth 1 https://github.com/espressif/esp-adf.git
cd esp-adf/adf_examples/ai_agent/esp_llm_tongyi_agent_app
idf.py set-target esp32s31          # 必须先选芯片
idf.py bmgr -b esp32_s31_korvo_1    # 再选开发板
idf.py menuconfig
```

在 menuconfig 里填：

- DashScope API key、Tongyi workspace ID、Tongyi application ID
- Application mode：**Vision**（默认就是）
- Wi-Fi：SSID 和密码（2.4 GHz）

保存退出后：

```
idf.py build
idf.py -p PORT flash monitor
```

### 5.3 试用

1. 启动后先连 Wi-Fi、对时，日志提示智能体就绪。
2. 直接说话就能和它对话；屏上是摄像头实时画面。
3. 在终端提示符 `tongyi>` 后输入：

```
snap 这道题怎么做
```

它会拍一张照片，连同问题一起发给大模型，用语音回答。

### 5.4 可能遇到的问题

- 例程说明写的是支持 ESP-IDF 5.4 / 5.5，但 S31 要 6.1 以上才有。用 v6.1.1 编译报错的话，把报错整段发给我。
- 连不上：检查 Wi-Fi 是 2.4 GHz、密钥和应用 ID 是否填对、网络能不能访问阿里云。
- 烧录连不上：按住 Boot，按一下 Reset，松开 Boot，再烧。

## 6. 阶段 0 要记下来的数字

| 测什么 | 怎么测 | 为什么要 |
|---|---|---|
| 拍照到开始回答要几秒 | 输入 `snap …` 后掐表 | 产品目标 3 ~ 5 秒 |
| 作业照片看不看得清字 | 拍一页作业，看大模型能不能读出题目 | 例程默认 640 × 480，可能不够。我们的后摄 OV2640 能拍 1600 × 1200 |
| 边放边说能不能打断 | 它说话时插话 | 回声消除效果 |
| 内存占用 | 输入 `sys_heap` | 估算产品里还剩多少内存给界面和视频 |

## 7. 让我直接在你的 Mac 上操作

环境装好后，在终端运行：

```
cd ~/esp
claude remote-control
```

在手机或电脑的 Claude App 里打开这个会话，我就能直接编译、烧录、看日志，你只需要在旁边看屏幕、听声音、按按键。
