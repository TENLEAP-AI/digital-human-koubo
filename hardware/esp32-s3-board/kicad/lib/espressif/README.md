# 乐鑫官方 KiCad 库里的 ESP32-S31-WROOM-1U

从 https://github.com/espressif/kicad-libraries 原样复制（2026-11-14）：

- `ESP32-S31-WROOM-1U.kicad_sym`：符号（从 `symbols/Espressif.kicad_sym` 里单独取出）。
- `ESP32-S31-WROOM-1U.kicad_mod`：封装。`gen/footprints.py` 把它复制进项目封装库 `zeebuddy.pretty`。

许可见 [LICENSE.md](LICENSE.md)（CC-BY-SA 4.0，带 KiCad 官方库同样的例外：用它做的电路设计不受署名-相同方式共享的约束）。
这两个文件是 KiCad 10 格式，需要 KiCad 10 打开。
