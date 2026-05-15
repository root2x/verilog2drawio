from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from drawio_fpga_module import (
    __version__ as DRAWIO_FPGA_MODULE_VERSION,
    parse_verilog_module_interface,
    parse_verilog_to_drawio_file,
    parse_verilog_to_drawio_module_xml,
    parse_verilog_to_drawio_url_encoded,
)


APP_VERSION = "0.3.0"


# =========================
# 输入读取
# =========================

def _read_text_file(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8")


def _read_stdin_text() -> str:
    text = sys.stdin.read()
    if not text.strip():
        raise ValueError("从 stdin 读取到的内容为空")
    return text


def _read_clipboard_text() -> str:
    # 优先用 tkinter，尽量不依赖第三方包。
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        finally:
            root.destroy()
        if text.strip():
            return text
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            text = result.stdout
            if text.strip():
                return text
        except Exception as exc:
            raise RuntimeError(f"读取剪切板失败: {exc}") from exc

    raise RuntimeError("读取剪切板失败，且当前环境没有可用的回退方案")


def _resolve_input_text(args: argparse.Namespace) -> str:
    selected = sum(
        1
        for flag in [args.text is not None, args.input_file is not None, args.stdin, args.clipboard]
        if flag
    )
    if selected == 0:
        raise ValueError("必须指定一种输入方式: --text / --input-file / --stdin / --clipboard")
    if selected > 1:
        raise ValueError("输入方式只能选择一种: --text / --input-file / --stdin / --clipboard")

    if args.text is not None:
        if not args.text.strip():
            raise ValueError("--text 对应内容为空")
        return args.text
    if args.input_file is not None:
        return _read_text_file(args.input_file)
    if args.stdin:
        return _read_stdin_text()
    return _read_clipboard_text()


# =========================
# 输出路径与剪切板
# =========================

def _sanitize_filename(name: str, default_name: str = "module") -> str:
    name = (name or "").strip()
    if not name:
        return default_name
    # Windows 非法字符全部替换掉。
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", name)
    name = name.strip(" .")
    return name or default_name


def _suffix_for_mode(mode: str) -> str:
    return {
        "drawio": ".drawio",
        "url": "_url.txt",
        "both": ".drawio",
        # 保留调试/旧用法
        "xml": ".xml",
        "json": ".json",
    }[mode]


def _resolve_output_path(
    *,
    mode: str,
    output: Optional[str],
    output_dir: Optional[str],
    module_name: str,
) -> Optional[Path]:
    if output and output_dir:
        raise ValueError("--output 和 --output-dir 只能二选一")

    if output:
        return Path(output)

    if output_dir:
        safe_module_name = _sanitize_filename(module_name)
        return Path(output_dir) / f"{safe_module_name}{_suffix_for_mode(mode)}"

    # 只有 drawio / both 必须有 .drawio 输出路径。
    if mode in {"drawio", "both"}:
        raise ValueError("mode=drawio/both 时，必须指定 --output 或 --output-dir")

    return None


def _resolve_url_output_path(
    *,
    mode: str,
    drawio_output_path: Optional[Path],
    url_output: Optional[str],
    output_dir: Optional[str],
    module_name: str,
) -> Optional[Path]:
    """
    URL 编码文本的保存路径。

    - mode=url：复用 --output / --output-dir 的结果；
    - mode=both：若用户显式指定 --url-output，就保存到该路径；
                 若用户只给 --output-dir，则保存为 <module>_url.txt；
                 若用户只给 --output，则默认只复制剪切板，不额外生成 txt 文件。
    """
    if url_output:
        return Path(url_output)

    if mode == "both" and output_dir:
        safe_module_name = _sanitize_filename(module_name)
        return Path(output_dir) / f"{safe_module_name}_url.txt"

    if mode == "both" and drawio_output_path is not None and output_dir is None:
        # 不强制保存 URL 文本文件，避免用户只想要 drawio 文件 + 剪切板时多出文件。
        return None

    return drawio_output_path if mode == "url" else None


def _write_text_output(text: str, output_path: Optional[Path]) -> None:
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(str(output_path))
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def _copy_text_to_clipboard_windows_native(text: str) -> None:
    """
    Windows 原生剪切板写入。

    之前优先使用 tkinter clipboard_append，某些 Windows 环境下进程退出后
    剪切板历史会显示“无法预览”，并且 Notepad/draw.io 都无法粘贴。
    这里直接写入 CF_UNICODETEXT，避免 tkinter 的剪切板所有权/延迟渲染问题。
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    GMEM_MOVEABLE = 0x0002
    CF_UNICODETEXT = 13

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    data = (text + "\0").encode("utf-16-le")
    h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h_global:
        raise ctypes.WinError()

    locked = False
    clipboard_opened = False
    ownership_transferred = False

    try:
        p_global = kernel32.GlobalLock(h_global)
        if not p_global:
            raise ctypes.WinError()
        locked = True
        ctypes.memmove(p_global, data, len(data))
        kernel32.GlobalUnlock(h_global)
        locked = False

        if not user32.OpenClipboard(None):
            raise ctypes.WinError()
        clipboard_opened = True

        if not user32.EmptyClipboard():
            raise ctypes.WinError()

        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            raise ctypes.WinError()

        # SetClipboardData 成功后，内存块所有权转移给系统，不能再 GlobalFree。
        ownership_transferred = True

    finally:
        if locked:
            kernel32.GlobalUnlock(h_global)
        if clipboard_opened:
            user32.CloseClipboard()
        if not ownership_transferred:
            kernel32.GlobalFree(h_global)


def _copy_text_to_clipboard(text: str) -> None:
    """
    把 URL 编码文本写入系统剪切板。

    Windows 下优先使用原生 CF_UNICODETEXT 写入，避免 tkinter 写入后
    出现“剪切板历史无法预览、实际无法粘贴”的问题。
    """
    if sys.platform.startswith("win"):
        try:
            _copy_text_to_clipboard_windows_native(text)
            return
        except Exception:
            # 极少数环境下 ctypes 剪切板被其他程序占用时，回退到 clip.exe。
            try:
                subprocess.run(["clip"], input=text, text=True, encoding="utf-8", check=True)
                return
            except Exception as exc:
                raise RuntimeError(f"写入剪切板失败: {exc}") from exc

    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, encoding="utf-8", check=True)
        return

    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        try:
            subprocess.run(cmd, input=text, text=True, encoding="utf-8", check=True)
            return
        except Exception:
            continue

    # 最后再尝试 tkinter。Linux/X11 下 tkinter 可能要求进程保持存活，
    # 所以只作为最后兜底，不作为优先方案。
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return
    except Exception as exc:
        raise RuntimeError(f"写入剪切板失败：当前系统没有可用的剪切板命令: {exc}") from exc


# =========================
# CLI
# =========================

def build_parser(us: bool = False) -> argparse.ArgumentParser:
    if us:
        parser = argparse.ArgumentParser(
            description=(
                "Parse a Verilog top-level interface and generate a draw.io file, "
                "a draw.io pasteable URL-encoded text, or both."
            ),
            formatter_class=argparse.RawTextHelpFormatter,
            add_help=False,
            epilog=(
                "Examples:\n"
                "  Generate only .drawio:\n"
                "    python verilog_to_drawio_cli.py --clipboard --mode drawio --output ctrl_cmd.drawio\n\n"
                "  Generate URL-encoded text and copy it to clipboard:\n"
                "    python verilog_to_drawio_cli.py --clipboard --mode url\n\n"
                "  Generate .drawio and copy URL-encoded text to clipboard:\n"
                "    python verilog_to_drawio_cli.py --clipboard --mode both --output ctrl_cmd.drawio\n\n"
                "  Show Chinese help:\n"
                "    python verilog_to_drawio_cli.py --help\n\n"
                "  Show English help:\n"
                "    python verilog_to_drawio_cli.py --us --help\n"
            ),
        )

        general_group = parser.add_argument_group("General options")
        general_group.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
        general_group.add_argument("--us", action="store_true", help="Use English help/messages for --help.")
        general_group.add_argument(
            "--version",
            action="version",
            version=f"%(prog)s {APP_VERSION}  (drawio_fpga_module {DRAWIO_FPGA_MODULE_VERSION})",
            help="Show version number and exit.",
        )

        input_group = parser.add_argument_group("Input source, choose exactly one")
        input_group.add_argument("--text", help="Pass Verilog text directly. Suitable for short tests.")
        input_group.add_argument("--input-file", help="Read Verilog text from a file, for example top.v.")
        input_group.add_argument("--stdin", action="store_true", help="Read Verilog text from standard input.")
        input_group.add_argument("--clipboard", action="store_true", help="Read Verilog text directly from the system clipboard.")

        output_group = parser.add_argument_group("Output mode and output path")
        output_group.add_argument(
            "--mode",
            choices=["drawio", "url", "both", "xml", "json"],
            default="drawio",
            help=(
                "Output mode:\n"
                "  drawio = generate only a .drawio file\n"
                "  url    = generate only URL-encoded text and copy it to clipboard\n"
                "  both   = generate a .drawio file and copy URL-encoded text to clipboard\n"
                "  xml    = debug mode: output module mxCell XML only\n"
                "  json   = debug mode: output parsed module interface"
            ),
        )
        output_group.add_argument(
            "--format",
            choices=["drawio", "url", "both", "xml", "json"],
            default=None,
            help="Backward-compatible alias of --mode. Do not use --mode and --format together.",
        )
        output_group.add_argument(
            "--output",
            help="Output file path. For mode=drawio/both this is the .drawio path; for mode=url this is the URL text path.",
        )
        output_group.add_argument(
            "--output-dir",
            help="Output directory. The file name is generated from the module name, for example ctrl_cmd.drawio / ctrl_cmd_url.txt.",
        )
        output_group.add_argument(
            "--url-output",
            help="Optional path for saving URL-encoded text, mainly used with mode=both.",
        )
        output_group.add_argument(
            "--no-copy",
            action="store_true",
            help="By default mode=url/both copies URL-encoded text to clipboard. Use this option to disable copying.",
        )

        layout_group = parser.add_argument_group("Module layout options")
        layout_group.add_argument("--x", type=int, default=240, help="Module top-left x coordinate.")
        layout_group.add_argument("--y", type=int, default=200, help="Module top-left y coordinate.")
        layout_group.add_argument("--port-font-size", type=int, default=10, help="Port font size.")
        layout_group.add_argument("--module-font-size", type=int, default=14, help="Module title font size.")
        layout_group.add_argument("--col-width", type=int, default=120, help="Left/right column width.")
        layout_group.add_argument("--port-row-height", type=int, default=33, help="Port row height.")
        layout_group.add_argument("--module-row-height", type=int, default=35, help="Module title row height.")

        page_group = parser.add_argument_group("draw.io page options")
        page_group.add_argument("--page-width", type=int, default=827, help="draw.io page width.")
        page_group.add_argument("--page-height", type=int, default=1169, help="draw.io page height.")
        page_group.add_argument("--page-name", default="Page-1", help="draw.io page name.")
        return parser

    parser = argparse.ArgumentParser(
        description="解析 Verilog 顶层接口，并生成 draw.io 文件、draw.io 可粘贴的 URL 编码文本，或二者同时生成。",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
        epilog=(
            "使用示例：\n"
            "  仅生成 .drawio：\n"
            "    python verilog_to_drawio_cli.py --clipboard --mode drawio --output ctrl_cmd.drawio\n\n"
            "  仅生成 URL 编码文本并复制到剪切板：\n"
            "    python verilog_to_drawio_cli.py --clipboard --mode url\n\n"
            "  生成 .drawio，同时生成 URL 编码文本并复制到剪切板：\n"
            "    python verilog_to_drawio_cli.py --clipboard --mode both --output ctrl_cmd.drawio\n\n"
            "  查看中文帮助：\n"
            "    python verilog_to_drawio_cli.py --help\n\n"
            "  查看英文帮助：\n"
            "    python verilog_to_drawio_cli.py --us --help\n"
        ),
    )

    general_group = parser.add_argument_group("通用选项")
    general_group.add_argument("-h", "--help", action="help", help="显示帮助说明并退出。")
    general_group.add_argument("--us", action="store_true", help="使用英文帮助说明，例如：--us --help。")
    general_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}  (drawio_fpga_module {DRAWIO_FPGA_MODULE_VERSION})",
        help="显示版本号并退出。",
    )

    input_group = parser.add_argument_group("输入方式，四选一")
    input_group.add_argument("--text", help="直接传入 Verilog 文本。不推荐传多行，适合短内容或测试。")
    input_group.add_argument("--input-file", help="从文件读取 Verilog 文本，例如 top.v。")
    input_group.add_argument("--stdin", action="store_true", help="从标准输入读取 Verilog 文本，最适合多行内容。")
    input_group.add_argument("--clipboard", action="store_true", help="直接读取系统剪切板中的 Verilog 文本。")

    output_group = parser.add_argument_group("输出模式与输出路径")
    output_group.add_argument(
        "--mode",
        choices=["drawio", "url", "both", "xml", "json"],
        default="drawio",
        help=(
            "输出模式：\n"
            "  drawio = 仅生成 .drawio 文件\n"
            "  url    = 仅生成 URL 编码文本并复制到剪切板\n"
            "  both   = 生成 .drawio，同时生成 URL 编码文本并复制到剪切板\n"
            "  xml    = 调试模式：仅输出模块 mxCell XML 片段\n"
            "  json   = 调试模式：仅输出 Verilog 接口解析结果"
        ),
    )
    output_group.add_argument(
        "--format",
        choices=["drawio", "url", "both", "xml", "json"],
        default=None,
        help="兼容旧参数，等价于 --mode。不要同时使用 --mode 和 --format。",
    )
    output_group.add_argument(
        "--output",
        help="输出文件完整路径。mode=drawio/both 时表示 .drawio 路径；mode=url 时表示 URL 文本路径。",
    )
    output_group.add_argument(
        "--output-dir",
        help="只指定输出目录，文件名自动使用模块名，例如 D:\\Temp -> ctrl_cmd.drawio / ctrl_cmd_url.txt。",
    )
    output_group.add_argument(
        "--url-output",
        help="可选：单独保存 URL 编码文本的路径，主要用于 mode=both。",
    )
    output_group.add_argument(
        "--no-copy",
        action="store_true",
        help="mode=url/both 时默认会复制 URL 编码文本到剪切板；加上此选项则不复制。",
    )

    layout_group = parser.add_argument_group("模块布局选项")
    layout_group.add_argument("--x", type=int, default=240, help="模块左上角 x 坐标。")
    layout_group.add_argument("--y", type=int, default=200, help="模块左上角 y 坐标。")
    layout_group.add_argument("--port-font-size", type=int, default=10, help="端口字体大小。")
    layout_group.add_argument("--module-font-size", type=int, default=14, help="模块名字体大小。")
    layout_group.add_argument("--col-width", type=int, default=120, help="左右两列宽度。")
    layout_group.add_argument("--port-row-height", type=int, default=33, help="端口行高。")
    layout_group.add_argument("--module-row-height", type=int, default=35, help="模块标题行高。")

    page_group = parser.add_argument_group("draw.io 页面选项")
    page_group.add_argument("--page-width", type=int, default=827, help="draw.io 页面宽度。")
    page_group.add_argument("--page-height", type=int, default=1169, help="draw.io 页面高度。")
    page_group.add_argument("--page-name", default="Page-1", help="draw.io 页面名。")
    return parser

def _module_drawio_kwargs(args: argparse.Namespace) -> dict:
    return {
        "x": args.x,
        "y": args.y,
        "col_width": args.col_width,
        "port_row_height": args.port_row_height,
        "module_row_height": args.module_row_height,
    }


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    use_us_help = "--us" in raw_argv
    parser = build_parser(us=use_us_help)
    args = parser.parse_args(raw_argv)

    try:
        if args.format is not None:
            # 用户显式用了旧参数 --format。
            # 如果 --mode 不是默认值，说明二者同时指定，容易产生歧义。
            if args.mode != "drawio":
                raise ValueError("--mode 和 --format 只能使用一个")
            args.mode = args.format

        mode = args.mode
        verilog_text = _resolve_input_text(args)
        parsed = parse_verilog_module_interface(verilog_text)
        module_name = parsed["module_name"]

        drawio_output_path = _resolve_output_path(
            mode=mode,
            output=args.output,
            output_dir=args.output_dir,
            module_name=module_name,
        )

        if mode == "json":
            json_text = json.dumps(parsed, ensure_ascii=False, indent=2)
            _write_text_output(json_text, drawio_output_path)
            return 0

        if mode == "xml":
            xml_text = parse_verilog_to_drawio_module_xml(
                verilog_text,
                port_font_size=args.port_font_size,
                module_font_size=args.module_font_size,
                **_module_drawio_kwargs(args),
            )
            _write_text_output(xml_text, drawio_output_path)
            return 0

        if mode in {"drawio", "both"}:
            out = parse_verilog_to_drawio_file(
                verilog_text,
                output_path=drawio_output_path,
                port_font_size=args.port_font_size,
                module_font_size=args.module_font_size,
                **_module_drawio_kwargs(args),
                page_name=args.page_name,
                page_width=args.page_width,
                page_height=args.page_height,
            )
            print(f"DRAWIO: {out}")

        if mode in {"url", "both"}:
            url_text = parse_verilog_to_drawio_url_encoded(
                verilog_text,
                port_font_size=args.port_font_size,
                module_font_size=args.module_font_size,
                **_module_drawio_kwargs(args),
            )

            url_output_path = _resolve_url_output_path(
                mode=mode,
                drawio_output_path=drawio_output_path,
                url_output=args.url_output,
                output_dir=args.output_dir,
                module_name=module_name,
            )

            if url_output_path is not None:
                url_output_path.parent.mkdir(parents=True, exist_ok=True)
                url_output_path.write_text(url_text, encoding="utf-8")
                print(f"URL_TEXT: {url_output_path}")

            if not args.no_copy:
                _copy_text_to_clipboard(url_text)
                print("CLIPBOARD: URL 编码文本已复制，可直接在 draw.io 中 Ctrl+V 粘贴")
            elif url_output_path is None:
                # 用户禁用了复制，又没给输出文件时，避免结果丢失，打印到 stdout。
                sys.stdout.write(url_text)
                if not url_text.endswith("\n"):
                    sys.stdout.write("\n")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
