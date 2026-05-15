# Verilog2Drawio 使用说明文档

当前文档用于记录 Verilog2Drawio 工具的项目结构、核心代码、主要函数、命令行用法、打包方式和版本说明。后续功能扩展时，可以直接在本文档基础上增删修改。

---

## 1. 项目简介

Verilog2Drawio 是一个用于把 Verilog/SystemVerilog 顶层模块接口自动转换为 draw.io 模块框图的命令行工具。

主要功能：

- 从 Verilog 模块声明中解析模块名、参数、输入端口、输出端口和双向端口。
- 自动生成 draw.io 可识别的模块表格图形。
- 支持生成完整 `.drawio` 文件。
- 支持生成 draw.io 可直接粘贴的 URL 编码文本，并复制到系统剪切板。
- 支持从文件、标准输入、命令行文本或系统剪切板读取 Verilog 源码。
- 支持中文/英文帮助信息和版本号查询，便于后续打包和版本管理。

---

## 2. 项目结构

推荐目录结构如下：

```text
Verilog2Drawio/
├─ drawio_fpga_module.py          # 核心库：Verilog 解析 + draw.io XML/URL 生成
├─ verilog_to_drawio_cli.py       # 命令行入口：参数解析、文件输入输出、剪切板操作
├─ verilog_to_drawio.spec         # 可选：PyInstaller 打包配置文件
├─ verilog_drawio.ico             # 可选：exe 图标文件
├─ README_Verilog2Drawio.md       # 项目说明文档
├─ build/                         # PyInstaller 临时构建目录，自动生成
├─ dist/                          # PyInstaller 输出目录，自动生成
│  ├─ verilog_to_drawio.exe        # 控制台版本，用于调试和命令行调用
│  └─ verilog_to_drawio_quicker.exe# 无窗口版本，用于 Quicker 调用
└─ examples/                      # 可选：示例 Verilog 和输出文件
   ├─ ctrl_cmd.v
   ├─ ctrl_cmd.drawio
   └─ ctrl_cmd_url.txt
```

其中最重要的是两个 Python 文件：

```text
drawio_fpga_module.py
verilog_to_drawio_cli.py
```

`drawio_fpga_module.py` 是底层功能库，负责解析和生成内容；`verilog_to_drawio_cli.py` 是命令行封装，负责用户交互和输入输出。

---

## 3. 两个主要代码文件说明

### 3.1 drawio_fpga_module.py

该文件是核心功能库，主要负责：

1. 解析 Verilog/SystemVerilog 模块接口。
2. 生成 draw.io 模块图形 XML。
3. 生成完整 `.drawio` 文件。
4. 生成 draw.io 剪切板可粘贴的 URL 编码文本。

该文件不直接面向用户命令行，主要被 `verilog_to_drawio_cli.py` 调用。

### 3.2 verilog_to_drawio_cli.py

该文件是命令行入口，主要负责：

1. 解析命令行参数。
2. 从 `--text`、`--input-file`、`--stdin`、`--clipboard` 中读取 Verilog 源码。
3. 根据 `--mode` 选择输出模式。
4. 生成 `.drawio` 文件、URL 编码文本，或两者同时生成。
5. 将 URL 编码文本复制到系统剪切板。
6. 提供 `--help`、`--us --help`、`--version` 等辅助功能。

---

## 4. 主要函数说明

### 4.1 Verilog 解析相关函数

#### `parse_verilog_module_interface(verilog_text, is_no_parameter=True)`

解析 Verilog/SystemVerilog 顶层模块声明，返回模块接口信息。

返回结果大致结构：

```python
{
    "module_name": "ctrl_cmd",
    "param_list": [
        {"name": "CMD_ADDR_WIDTH", "value": "12"}
    ],
    "input_list": [
        {"name": "i_cmd_clk", "width": 1, "direction": "input"}
    ],
    "output_list": [
        {"name": "o_cmd_addr", "width": 12, "direction": "output"}
    ],
    "inout_list": []
}
```

支持能力：

- ANSI 风格模块声明。
- `parameter` / `localparam` 参数列表。
- `input`、`output`、`inout` 端口。
- `wire`、`reg`、`logic`、`signed`、`unsigned` 等修饰符。
- 简单位宽表达式，例如 `[7:0]`、`[CMD_W-1:0]`。
- `//` 和 `/* */` 注释。

---

### 4.2 draw.io XML 生成相关函数

#### `generate_drawio_module_xml(...)`

根据模块名、输入端口列表和输出端口列表生成 draw.io 模块表格对应的 `mxCell` XML 片段。

该函数只生成图形片段，不包含完整 `.drawio` 文件外壳。

主要参数：

```python
module_name        # 模块名
input_list         # 输入端口列表
output_list        # 输出端口列表
port_font_size     # 端口字体大小
module_font_size   # 模块名字体大小
x, y               # 模块左上角坐标
col_width          # 左右两列宽度
port_row_height    # 端口行高度
module_row_height  # 模块标题行高度
```

特点：

- 自动把时钟和复位端口识别并放到顶部。
- 左侧显示输入端口，右侧显示输出端口。
- 模块名显示在中间标题栏。
- 生成的 XML 可以插入到 `<mxGraphModel><root>...</root></mxGraphModel>` 中。

#### `generate_drawio_file(module_xml, output_path, ...)`

把 `generate_drawio_module_xml()` 生成的模块 XML 包装成完整 `.drawio` 文件。

输出结果可以直接用 draw.io / diagrams.net 打开。

#### `generate_drawio_graph_model(module_xml)`

把模块 XML 包装成 draw.io 剪切板需要的：

```xml
<mxGraphModel>
  <root>
    ...
  </root>
</mxGraphModel>
```

注意：这不是完整 `.drawio` 文件，而是用于粘贴的 graph model。

#### `generate_drawio_url_encoded(module_xml)`

把 `<mxGraphModel>...</mxGraphModel>` 转换成 URL 编码文本，例如：

```text
%3CmxGraphModel%3E%3Croot%3E...
```

该文本复制到剪切板后，可以直接在 draw.io 画布中 `Ctrl + V` 粘贴生成图形。

---

### 4.3 便捷封装函数

#### `parse_verilog_to_drawio_file(verilog_text, output_path, ...)`

一步完成：

```text
Verilog 源码 -> 解析模块接口 -> 生成模块 XML -> 保存为 .drawio 文件
```

#### `parse_verilog_to_drawio_module_xml(verilog_text, ...)`

一步完成：

```text
Verilog 源码 -> 模块 XML 片段
```

通常用于调试或二次开发。

#### `parse_verilog_to_drawio_url_encoded(verilog_text, ...)`

一步完成：

```text
Verilog 源码 -> draw.io 可粘贴 URL 编码文本
```

这是 `--mode url` 和 `--mode both` 的核心函数。

---

### 4.4 CLI 输入输出相关函数

这些函数主要位于 `verilog_to_drawio_cli.py`。

#### `_read_text_file(path)`

从文件读取 Verilog 源码。

#### `_read_stdin_text()`

从标准输入读取 Verilog 源码。

#### `_read_clipboard_text()`

从系统剪切板读取 Verilog 源码。

#### `_resolve_input_text(args)`

统一处理输入来源，保证四种输入方式只能选择一种：

```text
--text
--input-file
--stdin
--clipboard
```

#### `_copy_text_to_clipboard(text)`

将 URL 编码文本写入系统剪切板。

Windows 下建议优先使用原生 `CF_UNICODETEXT` 写入，避免 tkinter 剪切板写入后出现“无法预览、无法粘贴”的问题。

#### `_resolve_output_path(...)`

根据 `--output`、`--output-dir` 和模块名自动确定输出路径。

#### `_resolve_url_output_path(...)`

在 `--mode url` 或 `--mode both` 时确定 URL 文本是否需要额外保存成 `.txt` 文件。

---

## 5. 命令行使用说明

### 5.1 查看帮助

默认显示中文帮助：

```powershell
verilog_to_drawio.exe --help
```

显示英文帮助：

```powershell
verilog_to_drawio.exe --us --help
```

### 5.2 查看版本号

```powershell
verilog_to_drawio.exe --version
```

输出示例：

```text
verilog_to_drawio_cli.py 0.3.0  (drawio_fpga_module 0.3.0)
```

版本号建议同时维护在：

```python
# verilog_to_drawio_cli.py
APP_VERSION = "0.3.0"

# drawio_fpga_module.py
__version__ = "0.3.0"
```

---

## 6. 输入方式

四种输入方式只能选择一种。

### 6.1 从文件读取

```powershell
verilog_to_drawio.exe --input-file ctrl_cmd.v --mode drawio --output ctrl_cmd.drawio
```

### 6.2 从剪切板读取

先在 IDE 中复制 Verilog 模块声明，然后执行：

```powershell
verilog_to_drawio.exe --clipboard --mode url
```

### 6.3 从标准输入读取

```powershell
type ctrl_cmd.v | verilog_to_drawio.exe --stdin --mode drawio --output ctrl_cmd.drawio
```

### 6.4 从命令行直接传入文本

适合短模块或测试：

```powershell
verilog_to_drawio.exe --text "module test(input clk, output done); endmodule" --mode drawio --output test.drawio
```

---

## 7. 输出模式

当前主要有三种正式模式。

### 7.1 仅生成 `.drawio`

```powershell
verilog_to_drawio.exe --clipboard --mode drawio --output ctrl_cmd.drawio
```

或者自动按模块名保存：

```powershell
verilog_to_drawio.exe --clipboard --mode drawio --output-dir D:\Temp
```

如果模块名是 `ctrl_cmd`，则输出：

```text
D:\Temp\ctrl_cmd.drawio
```

---

### 7.2 仅生成 URL 编码文本并复制到剪切板

```powershell
verilog_to_drawio.exe --clipboard --mode url
```

执行完成后，直接到 draw.io 画布中 `Ctrl + V`，即可粘贴模块框图。

如果同时想保存 URL 文本：

```powershell
verilog_to_drawio.exe --clipboard --mode url --output ctrl_cmd_url.txt
```

---

### 7.3 同时生成 `.drawio` 和 URL 编码文本

```powershell
verilog_to_drawio.exe --clipboard --mode both --output ctrl_cmd.drawio
```

此模式会：

1. 生成 `ctrl_cmd.drawio`。
2. 生成 URL 编码文本。
3. 自动复制 URL 编码文本到剪切板。

如果还想把 URL 编码文本保存成 `.txt`：

```powershell
verilog_to_drawio.exe --clipboard --mode both --output ctrl_cmd.drawio --url-output ctrl_cmd_url.txt
```

如果使用输出目录：

```powershell
verilog_to_drawio.exe --clipboard --mode both --output-dir D:\Temp
```

假设模块名是 `ctrl_cmd`，则输出：

```text
D:\Temp\ctrl_cmd.drawio
D:\Temp\ctrl_cmd_url.txt
```

---

## 8. 其他调试模式

除了正式的三种模式，代码中可以保留两个调试模式。

### 8.1 XML 模式

```powershell
verilog_to_drawio.exe --input-file ctrl_cmd.v --mode xml --output ctrl_cmd.xml
```

用于查看模块对应的 `mxCell` XML 片段。

### 8.2 JSON 模式

```powershell
verilog_to_drawio.exe --input-file ctrl_cmd.v --mode json --output ctrl_cmd.json
```

用于查看 Verilog 接口解析结果。

---

## 9. 常用参数说明

### 9.1 输入参数

| 参数 | 说明 |
|---|---|
| `--text` | 直接传入 Verilog 文本 |
| `--input-file` | 从 Verilog 文件读取 |
| `--stdin` | 从标准输入读取 |
| `--clipboard` | 从系统剪切板读取 |

### 9.2 输出参数

| 参数 | 说明 |
|---|---|
| `--mode drawio` | 仅生成 `.drawio` 文件 |
| `--mode url` | 仅生成 URL 编码文本并复制到剪切板 |
| `--mode both` | 同时生成 `.drawio` 和 URL 编码文本 |
| `--output` | 指定输出文件路径 |
| `--output-dir` | 指定输出目录，文件名自动使用模块名 |
| `--url-output` | 单独指定 URL 文本保存路径，主要用于 `both` 模式 |
| `--no-copy` | `url/both` 模式下不复制到剪切板 |

### 9.3 图形布局参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--x` | 240 | 模块左上角 x 坐标 |
| `--y` | 200 | 模块左上角 y 坐标 |
| `--port-font-size` | 10 | 端口字体大小 |
| `--module-font-size` | 14 | 模块名字体大小 |
| `--col-width` | 120 | 左右两列宽度 |
| `--port-row-height` | 33 | 端口行高度 |
| `--module-row-height` | 35 | 模块标题行高度 |
| `--page-width` | 827 | draw.io 页面宽度 |
| `--page-height` | 1169 | draw.io 页面高度 |
| `--page-name` | Page-1 | draw.io 页面名称 |

---

## 10. PyInstaller 打包说明

### 10.1 控制台版本

用于调试、查看帮助和查看版本号。

```powershell
python -m PyInstaller --onefile --console --clean --name verilog_to_drawio verilog_to_drawio_cli.py
```

输出：

```text
dist\verilog_to_drawio.exe
```

### 10.2 Quicker 无窗口版本

用于 Quicker 调用，避免弹出命令行窗口。

```powershell
python -m PyInstaller --onefile --windowed --clean --name verilog_to_drawio_quicker verilog_to_drawio_cli.py
```

输出：

```text
dist\verilog_to_drawio_quicker.exe
```

注意：无窗口版本看不到 `print()` 输出、错误信息、`--help` 和 `--version` 显示内容，因此建议只用于 Quicker 自动调用。

### 10.3 spec 打包方式

如果需要同时打包控制台版本和 Quicker 版本，推荐使用 `.spec` 文件统一管理。

典型输出：

```text
dist\verilog_to_drawio.exe
dist\verilog_to_drawio_quicker.exe
```

构建命令：

```powershell
python -m PyInstaller --clean --noconfirm verilog_to_drawio.spec
```

---

## 11. Quicker 调用建议

Quicker 中建议使用无窗口版本：

```text
D:\Tools\verilog_to_drawio\verilog_to_drawio_quicker.exe
```

常用参数：

```powershell
--clipboard --mode url
```

含义：

1. 从剪切板读取 Verilog 模块声明。
2. 生成 draw.io URL 编码文本。
3. 自动复制回剪切板。
4. 用户切换到 draw.io 后直接 `Ctrl + V`。

如果希望同时落盘保存 `.drawio`：

```powershell
--clipboard --mode both --output-dir D:\Temp
```

---

## 12. 当前版本说明

### v0.3.0

主要功能：

- 增加三种正式输出模式：
  - `drawio`：仅生成 `.drawio` 文件。
  - `url`：仅生成 URL 编码文本并复制到剪切板。
  - `both`：同时生成 `.drawio` 文件和 URL 编码文本。
- 增加 URL 编码文本生成能力，可直接在 draw.io 中粘贴。
- 修复 Windows 剪切板写入问题，优先使用原生 `CF_UNICODETEXT`。
- 增加 `--help` 中文帮助。
- 增加 `--us --help` 英文帮助。
- 增加 `--version` 版本号查询。
- 保留 `xml/json` 调试模式。

### v0.2.x

主要功能：

- 增加命令行调用入口。
- 支持从文件、剪切板、标准输入读取 Verilog。
- 支持自动按模块名生成输出文件。

### v0.1.x

主要功能：

- 实现 Verilog 顶层模块解析。
- 实现 draw.io 模块表格 XML 生成。
- 实现 `.drawio` 文件保存。

---

## 13. 维护建议

### 13.1 新增版本时需要同步修改

建议每次发布新版本时同步修改：

```python
# verilog_to_drawio_cli.py
APP_VERSION = "x.y.z"

# drawio_fpga_module.py
__version__ = "x.y.z"
```

同时更新本文档中的“版本说明”。

### 13.2 修改核心生成逻辑时优先改库文件

如果是 Verilog 解析、draw.io XML 格式、URL 编码格式变化，优先修改：

```text
drawio_fpga_module.py
```

如果是命令行参数、输入输出、剪切板、打包调用变化，优先修改：

```text
verilog_to_drawio_cli.py
```

### 13.3 建议保留调试模式

`xml` 和 `json` 模式虽然不是主要面向用户的功能，但对调试很有用，建议保留。

### 13.4 建议保留控制台版 exe

即使 Quicker 使用无窗口版本，也建议保留控制台版本，便于：

- 查看 `--help`。
- 查看 `--version`。
- 观察错误信息。
- 手动测试命令行参数。

---

## 14. 常见问题

### 14.1 URL 模式生成后 draw.io 粘贴不了

优先检查：

1. 生成的 URL 文本是否能粘贴到记事本。
2. 是否以 `%3CmxGraphModel%3E` 开头。
3. 是否使用了修复后的 Windows 原生剪切板写入方式。
4. draw.io 当前焦点是否在画布区域。

### 14.2 `.drawio` 文件生成了但打不开

检查：

1. 文件是否完整写入。
2. 是否包含 `<mxfile>` 外壳。
3. 是否手动修改过 XML 导致标签不匹配。

### 14.3 Quicker 调用时弹出命令行窗口

使用无窗口版本：

```text
verilog_to_drawio_quicker.exe
```

不要在 Quicker 中调用控制台版本：

```text
verilog_to_drawio.exe
```

### 14.4 无窗口版本看不到错误信息

这是正常现象。调试时请使用控制台版本：

```powershell
verilog_to_drawio.exe --clipboard --mode url
```

---

## 15. 后续可扩展方向

后续考虑增加：

- 多模块批量解析。
- 一个 Verilog 文件内多个模块自动生成多个 draw.io 图形。
- 支持 inout 端口单独显示。
- 支持参数表显示。
- 支持黑金主题、浅色主题等不同样式模板。
- 支持直接输出 draw.io library 元件库。
- 支持图形中显示端口注释。
- 支持 GUI 小工具。
