from __future__ import annotations

import ast
import html
import re
import uuid
from pathlib import Path
from urllib.parse import quote
from typing import Dict, List, Optional


__version__ = "0.3.0"


# =========================
# draw.io 生成部分
# =========================

def _fmt_port_label(port: Dict) -> str:
    '''
    把 {"name": "...", "width": N} 转成 draw.io 中显示的字符串。

    约定：
    - width 为 1 / "1" / None -> 只显示名字
    - width 为整数且 >1 -> 显示 name[width]
    - width 为字符串时：
      - 若本身带 []，则直接拼接，如 name[W-1:0]
      - 否则显示为 name[width]
    '''
    name = str(port["name"])
    width = port.get("width", 1)

    if width is None:
        return name

    if isinstance(width, int):
        return f"{name}[{width}]" if width > 1 else name

    width_str = str(width).strip()
    if width_str in {"", "1"}:
        return name

    if width_str.startswith("[") and width_str.endswith("]"):
        return f"{name}{width_str}"

    return f"{name}[{width_str}]"


def _pick_special_inputs(input_list: List[Dict]) -> tuple[Optional[Dict], Optional[Dict], List[Dict]]:
    '''
    从输入端口中尽量识别 clk / rst，放到最上面两格。
    识别规则：
    - 时钟：名字包含 clk 或 clock
    - 复位：名字包含 rst 或 reset
    返回：clk_port, rst_port, remaining_inputs
    '''
    clk_port = None
    rst_port = None
    remaining = []

    for port in input_list:
        name = str(port["name"]).lower()

        if clk_port is None and ("clk" in name or "clock" in name):
            clk_port = port
            continue

        if rst_port is None and ("rst" in name or "reset" in name):
            rst_port = port
            continue

        remaining.append(port)

    return clk_port, rst_port, remaining


def generate_drawio_module_xml(
    module_name: str,
    input_list: List[Dict],
    output_list: List[Dict],
    port_font_size: int = 10,
    module_font_size: int = 14,
    *,
    x: int = 240,
    y: int = 200,
    col_width: int = 120,
    port_row_height: int = 33,
    module_row_height: int = 35,
    stroke_color: str = "#98bf21",
    title_fill_color: str = "#A7C942",
    top_fill_color: str = "#E6FFCC",
    body_fill_color: str = "#FFFFFF",
    shadow: bool = True,
) -> str:
    '''
    生成一个 draw.io 模块的 XML 片段（mxCell 列表），可插入到 .drawio 的 <root> 节点中。

    参数
    ----
    module_name : 模块名
    input_list  : 输入端口列表，例如 [{"name": "clk", "width": 1}, ...]
    output_list : 输出端口列表
    port_font_size : 端口字体大小
    module_font_size : 模块名字体大小

    其他可选参数
    ----------
    x, y : 模块左上角坐标
    col_width : 左右两列的宽度
    port_row_height : 端口行高度
    module_row_height : 模块标题行高度

    返回
    ----
    一个字符串，内容是若干个 <mxCell ...>...</mxCell>，可以插入到 draw.io 的 <root> 中。
    '''
    module_name_esc = html.escape(str(module_name))
    total_width = 2 * col_width

    clk_port, rst_port, normal_inputs = _pick_special_inputs(input_list)

    has_top_row = (clk_port is not None) or (rst_port is not None)
    body_rows = max(len(normal_inputs), len(output_list))
    if body_rows == 0:
        body_rows = 1  # 至少留一行，避免模块太怪

    total_height = (port_row_height if has_top_row else 0) + module_row_height + body_rows * port_row_height

    prefix = "mod_" + uuid.uuid4().hex[:10]

    root_id = f"{prefix}_root"

    def geom(width: int, height: int, x_pos: Optional[int] = None, y_pos: Optional[int] = None, include_alt: bool = False) -> str:
        attrs = [f'height="{height}"', f'width="{width}"']
        if x_pos is not None:
            attrs.append(f'x="{x_pos}"')
        if y_pos is not None:
            attrs.append(f'y="{y_pos}"')
        if include_alt:
            return (
                f'<mxGeometry {" ".join(attrs)} as="geometry">'
                f'<mxRectangle height="{height}" width="{width}" as="alternateBounds" />'
                f'</mxGeometry>'
            )
        return f'<mxGeometry {" ".join(attrs)} as="geometry" />'

    parts = []

    table_style = (
        f"childLayout=tableLayout;recursiveResize=0;strokeColor={stroke_color};"
        f"fillColor={title_fill_color};shadow={1 if shadow else 0};"
    )
    parts.append(
        f'<mxCell id="{root_id}" parent="1" style="{table_style}" value="FPGA Module" vertex="1">'
        f'{geom(total_width, total_height, x, y)}'
        f'</mxCell>'
    )

    current_y = 0

    if has_top_row:
        top_row_id = f"{prefix}_row_top"
        parts.append(
            f'<mxCell id="{top_row_id}" parent="{root_id}" '
            f'style="shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;'
            f'top=0;left=0;bottom=0;right=0;dropTarget=0;collapsible=0;recursiveResize=0;'
            f'expand=0;fontStyle=0;strokeColor=inherit;fillColor=#ffffff;" '
            f'vertex="1">{geom(total_width, port_row_height, y_pos=current_y)}</mxCell>'
        )

        clk_label = html.escape(_fmt_port_label(clk_port)) if clk_port else ""
        rst_label = html.escape(_fmt_port_label(rst_port)) if rst_port else ""

        parts.append(
            f'<mxCell id="{prefix}_top_l" parent="{top_row_id}" '
            f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={top_fill_color};'
            f'align=center;fontStyle=1;fontColor=light-dark(#000000,#121212);html=1;'
            f'fontSize={port_font_size};" '
            f'value="{clk_label}" vertex="1">{geom(col_width, port_row_height, include_alt=True)}</mxCell>'
        )

        parts.append(
            f'<mxCell id="{prefix}_top_r" parent="{top_row_id}" '
            f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={top_fill_color};'
            f'align=center;fontStyle=1;fontColor=light-dark(#000000,#121212);html=1;'
            f'fontSize={port_font_size};" '
            f'value="{rst_label}" vertex="1">{geom(col_width, port_row_height, x_pos=col_width, include_alt=True)}</mxCell>'
        )

        current_y += port_row_height

    title_row_id = f"{prefix}_row_title"
    parts.append(
        f'<mxCell id="{title_row_id}" parent="{root_id}" '
        f'style="shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;'
        f'top=0;left=0;bottom=0;right=0;dropTarget=0;collapsible=0;recursiveResize=0;'
        f'expand=0;fontStyle=0;strokeColor=inherit;fillColor=#ffffff;" '
        f'vertex="1">{geom(total_width, module_row_height, y_pos=current_y)}</mxCell>'
    )

    parts.append(
        f'<mxCell id="{prefix}_title" parent="{title_row_id}" '
        f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={title_fill_color};'
        f'align=center;fontStyle=1;fontColor=#FFFFFF;html=1;rowspan=1;colspan=2;'
        f'fontSize={module_font_size};" '
        f'value="{module_name_esc}" vertex="1">'
        f'{geom(total_width, module_row_height, include_alt=True)}'
        f'</mxCell>'
    )

    # 为了兼容 draw.io 的 table colspan 习惯，补一个隐藏单元格
    parts.append(
        f'<mxCell id="{prefix}_title_hidden" parent="{title_row_id}" '
        f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={title_fill_color};'
        f'align=center;fontStyle=1;fontColor=#FFFFFF;html=1;" '
        f'value="" vertex="1" visible="0">'
        f'{geom(col_width, module_row_height, x_pos=col_width, include_alt=True)}'
        f'</mxCell>'
    )

    current_y += module_row_height

    for idx in range(body_rows):
        row_id = f"{prefix}_row_{idx}"
        parts.append(
            f'<mxCell id="{row_id}" parent="{root_id}" '
            f'style="shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;'
            f'top=0;left=0;bottom=0;right=0;dropTarget=0;collapsible=0;recursiveResize=0;'
            f'expand=0;fontStyle=0;strokeColor=inherit;fillColor=#ffffff;" '
            f'value="" vertex="1">{geom(total_width, port_row_height, y_pos=current_y)}</mxCell>'
        )

        left_value = html.escape(_fmt_port_label(normal_inputs[idx])) if idx < len(normal_inputs) else ""
        right_value = html.escape(_fmt_port_label(output_list[idx])) if idx < len(output_list) else ""

        parts.append(
            f'<mxCell id="{prefix}_l_{idx}" parent="{row_id}" '
            f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={body_fill_color};'
            f'align=left;whiteSpace=wrap;html=1;fontSize={port_font_size};spacingLeft=6;" '
            f'value="{left_value}" vertex="1">{geom(col_width, port_row_height, include_alt=True)}</mxCell>'
        )

        parts.append(
            f'<mxCell id="{prefix}_r_{idx}" parent="{row_id}" '
            f'style="connectable=0;recursiveResize=0;strokeColor=inherit;fillColor={body_fill_color};'
            f'align=right;whiteSpace=wrap;html=1;fontSize={port_font_size};spacingRight=6;" '
            f'value="{right_value}" vertex="1">{geom(col_width, port_row_height, x_pos=col_width, include_alt=True)}</mxCell>'
        )

        current_y += port_row_height

    return "\n".join(parts)


def generate_drawio_file(
    module_xml: str,
    output_path: str | Path,
    *,
    page_name: str = "Page-1",
    page_width: int = 827,
    page_height: int = 1169,
    dx: int = 624,
    dy: int = 541,
    host: str = "Electron",
    version: str = "29.6.6",
) -> Path:
    '''
    把 generate_drawio_module_xml 的输出包装成一个完整的 .drawio 文件。
    '''
    page_name_esc = html.escape(str(page_name))
    content = f'''<mxfile host="{host}" version="{version}">
  <diagram name="{page_name_esc}" id="{uuid.uuid4().hex[:16]}">
    <mxGraphModel dx="{dx}" dy="{dy}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page_width}" pageHeight="{page_height}" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
{module_xml}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
'''
    output_path = Path(output_path)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _compact_xml(xml: str) -> str:
    '''
    压缩 XML，去掉标签之间的换行和缩进。
    draw.io 剪切板中的 URL 编码文本通常是紧凑的 mxGraphModel。
    '''
    return re.sub(r">\s+<", "><", xml.strip())


def generate_drawio_graph_model(module_xml: str) -> str:
    '''
    把模块 mxCell XML 片段包装成 draw.io 粘贴用的 mxGraphModel XML。

    注意：
    - 这里不是完整 .drawio 文件；
    - 这里生成的是 <mxGraphModel>...</mxGraphModel>；
    - 再经过 URL 编码后，就可以直接放入剪切板并在 draw.io 里粘贴。
    '''
    content = f'''<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
{module_xml}
  </root>
</mxGraphModel>
'''
    return _compact_xml(content)


def generate_drawio_url_encoded(module_xml: str) -> str:
    '''
    把模块 mxCell XML 片段转换成 draw.io 可直接粘贴的 URL 编码文本。
    '''
    graph_model = generate_drawio_graph_model(module_xml)
    return quote(graph_model, safe="")


# =========================
# Verilog 解析部分
# =========================

_PORT_QUALIFIERS = {
    "wire", "reg", "logic", "signed", "unsigned", "var", "tri", "uwire",
    "supply0", "supply1", "wand", "wor", "tri0", "tri1", "trireg",
}


class _SafeExprEvaluator(ast.NodeVisitor):
    '''仅用于非常小范围的常量表达式求值，例如 8-1、4*2、(16>>1)-1。'''

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            return int(node.value)
        raise ValueError("unsupported constant")

    def visit_Num(self, node):  # py<3.8 兼容写法
        return int(node.n)

    def visit_UnaryOp(self, node):
        value = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.Invert):
            return ~value
        raise ValueError("unsupported unary operator")

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Div):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        if isinstance(op, ast.BitOr):
            return left | right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitXor):
            return left ^ right
        raise ValueError("unsupported binary operator")

    def generic_visit(self, node):
        raise ValueError(f"unsupported node: {type(node).__name__}")


def _replace_comment_with_spaces(match: re.Match) -> str:
    text = match.group(0)
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _sanitize_verilog_text_preserve_layout(text: str) -> str:
    '''
    去掉 // 和 /* */ 注释，但保留原字符串长度和换行位置，便于后续索引切片。
    '''
    text = re.sub(r"/\*.*?\*/", _replace_comment_with_spaces, text, flags=re.S)
    text = re.sub(r"//.*?$", _replace_comment_with_spaces, text, flags=re.M)
    return text


def _extract_balanced_region(text: str, start_idx: int, open_ch: str = "(", close_ch: str = ")") -> tuple[str, int]:
    '''
    从 text[start_idx] == open_ch 开始，提取配对括号内的内容。
    返回 (括号内内容, 右括号索引)
    '''
    if start_idx >= len(text) or text[start_idx] != open_ch:
        raise ValueError(f"expected '{open_ch}' at index {start_idx}")

    depth = 0
    for idx in range(start_idx, len(text)):
        ch = text[idx]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start_idx + 1:idx], idx

    raise ValueError(f"unmatched '{open_ch}' in verilog text")


def _split_top_level_items(text: str) -> List[str]:
    '''
    按顶层逗号切分，忽略括号/中括号/大括号/注释/字符串中的逗号。
    '''
    items: List[str] = []
    buf: List[str] = []
    paren = bracket = brace = 0
    in_line_comment = False
    in_block_comment = False
    in_string = False
    escape = False

    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        if in_string:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_line_comment = True
            continue

        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_block_comment = True
            continue

        if ch == '"':
            buf.append(ch)
            in_string = True
            i += 1
            continue

        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(paren - 1, 0)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(bracket - 1, 0)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(brace - 1, 0)

        if ch == "," and paren == 0 and bracket == 0 and brace == 0:
            items.append("".join(buf))
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    if buf:
        items.append("".join(buf))

    return items




def _move_leading_comments_to_previous(items: List[str]) -> List[str]:
    """
    顶层按逗号切分后，像下面这种写法：
        a, // comment for a
        b
    注释会落到下一项开头。这里把“项首注释”回挂到上一项。
    """
    fixed: List[str] = []

    def split_leading_comments(s: str) -> tuple[str, str]:
        i = 0
        leading: List[str] = []
        while i < len(s):
            m = re.match(r"\s+", s[i:])
            if m:
                leading.append(m.group(0))
                i += len(m.group(0))
                continue

            if s.startswith("//", i):
                j = i + 2
                while j < len(s) and s[j] != "\n":
                    j += 1
                if j < len(s):
                    j += 1
                leading.append(s[i:j])
                i = j
                continue

            if s.startswith("/*", i):
                j = i + 2
                while j + 1 < len(s) and not (s[j] == "*" and s[j + 1] == "/"):
                    j += 1
                j = min(j + 2, len(s))
                leading.append(s[i:j])
                i = j
                continue

            break

        return "".join(leading), s[i:]

    for item in items:
        leading, rest = split_leading_comments(item)
        if fixed and leading.strip():
            fixed[-1] += leading
            fixed.append(rest)
        else:
            fixed.append(item)

    return fixed

def _extract_code_and_comment(text: str) -> tuple[str, str]:
    '''
    从一段 parameter / port 声明中提取：
    - 去掉注释后的代码
    - 合并后的注释文本
    '''
    code_buf: List[str] = []
    comments: List[str] = []

    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if ch == "/" and nxt == "/":
            j = i + 2
            while j < len(text) and text[j] != "\n":
                j += 1
            comment = text[i + 2:j].strip()
            if comment:
                comments.append(comment)
            i = j
            continue

        if ch == "/" and nxt == "*":
            j = i + 2
            while j + 1 < len(text) and not (text[j] == "*" and text[j + 1] == "/"):
                j += 1
            comment = text[i + 2:j].strip()
            if comment:
                comments.append(re.sub(r"\s+", " ", comment))
            i = min(j + 2, len(text))
            continue

        code_buf.append(ch)
        i += 1

    code = "".join(code_buf).strip()
    code = re.sub(r"\s+", " ", code)
    comment = " ".join(c for c in comments if c)
    comment = re.sub(r"\s+", " ", comment).strip()
    return code, comment


def _strip_outer_parentheses(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        if not inner:
            break
        # 只有整段完全被一层括号包住时才剥离
        depth = 0
        ok = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    ok = False
                    break
        if ok:
            text = inner
        else:
            break
    return text


def _verilog_int_literal_to_int(token: str) -> Optional[int]:
    token = token.strip().replace("_", "")
    if not token:
        return None

    if re.fullmatch(r"[+-]?\d+", token):
        return int(token, 10)

    m = re.fullmatch(r"(?:(\d+))?'([sS]?)([bBoOdDhH])([0-9a-fA-FxXzZ?]+)", token)
    if not m:
        return None

    base_ch = m.group(3).lower()
    digits = m.group(4)
    if re.search(r"[xXzZ?]", digits):
        return None

    base = {"b": 2, "o": 8, "d": 10, "h": 16}[base_ch]
    return int(digits, base)


def _replace_verilog_numeric_literals(expr: str) -> str:
    pattern = re.compile(r"(?:(?:\d+)?'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?]+)|(?:\b\d+\b)")

    def repl(match: re.Match) -> str:
        token = match.group(0)
        value = _verilog_int_literal_to_int(token)
        return token if value is None else str(value)

    return pattern.sub(repl, expr)


def _try_eval_const_expr(expr: str) -> Optional[int]:
    expr = expr.strip()
    if not expr:
        return None

    converted = _replace_verilog_numeric_literals(expr)
    if re.search(r"[^0-9\s\+\-\*\/%\(\)<<>>\|&\^~]", converted):
        return None

    try:
        node = ast.parse(converted, mode="eval")
        return int(_SafeExprEvaluator().visit(node))
    except Exception:
        return None


def _width_from_range_text(range_text: Optional[str]) -> int | str:
    '''
    把 packed range 解析成适合显示的 width：
    - [7:0]          -> 8
    - [CMD_W-1:0]    -> CMD_W
    - [0:7]          -> 8
    - 复杂表达式      -> 原样字符串（带 []）
    '''
    if not range_text:
        return 1

    cleaned = re.sub(r"\s+", "", range_text)
    matches = re.findall(r"\[([^\[\]]+)\]", cleaned)
    if not matches:
        return 1

    # 多维 packed range，优先尝试全部算成整数乘积；不行就原样保留
    if len(matches) > 1:
        dims: List[int] = []
        for inner in matches:
            if ":" not in inner:
                return cleaned
            msb, lsb = inner.split(":", 1)
            msb_v = _try_eval_const_expr(msb)
            lsb_v = _try_eval_const_expr(lsb)
            if msb_v is None or lsb_v is None:
                return cleaned
            dims.append(abs(msb_v - lsb_v) + 1)
        prod = 1
        for d in dims:
            prod *= d
        return prod

    inner = matches[0]
    if ":" not in inner:
        return cleaned

    msb, lsb = inner.split(":", 1)
    msb = _strip_outer_parentheses(msb)
    lsb = _strip_outer_parentheses(lsb)

    msb_v = _try_eval_const_expr(msb)
    lsb_v = _try_eval_const_expr(lsb)
    if msb_v is not None and lsb_v is not None:
        width = abs(msb_v - lsb_v) + 1
        return width if width > 0 else cleaned

    if lsb == "0":
        m = re.fullmatch(r"(.+)-1", msb)
        if m:
            expr = _strip_outer_parentheses(m.group(1).strip())
            expr_v = _try_eval_const_expr(expr)
            if expr_v is not None:
                return expr_v
            return expr

    return cleaned


def _consume_leading_qualifiers(rest: str) -> str:
    rest = rest.strip()
    while True:
        m = re.match(r"^([A-Za-z_]\w*)\b", rest)
        if not m:
            break
        token = m.group(1)
        if token not in _PORT_QUALIFIERS:
            break
        rest = rest[m.end():].strip()
    return rest


def _consume_leading_ranges(rest: str) -> tuple[Optional[str], str]:
    rest = rest.strip()
    ranges: List[str] = []
    while rest.startswith("["):
        depth = 0
        end_idx = None
        for idx, ch in enumerate(rest):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end_idx = idx
                    break
        if end_idx is None:
            break
        ranges.append(rest[:end_idx + 1].strip())
        rest = rest[end_idx + 1:].strip()
    if not ranges:
        return None, rest
    return " ".join(ranges), rest


def _parse_port_decl_item(item_code: str, inherited_direction: Optional[str], inherited_range: Optional[str]) -> tuple[Optional[Dict], Optional[str], Optional[str]]:
    '''
    解析一个顶层逗号分割后的端口项。
    返回：port_dict, new_direction, new_range
    '''
    code = item_code.strip().rstrip(",").rstrip(";").strip()
    if not code:
        return None, inherited_direction, inherited_range

    direction = inherited_direction
    current_range = inherited_range

    m = re.match(r"^(input|output|inout)\b(.*)$", code, flags=re.I | re.S)
    rest = code
    if m:
        direction = m.group(1).lower()
        current_range = None
        rest = m.group(2).strip()
    else:
        rest = code

    if direction is None:
        return None, inherited_direction, inherited_range

    rest = _consume_leading_qualifiers(rest)

    parsed_range, rest = _consume_leading_ranges(rest)
    if parsed_range is not None:
        current_range = parsed_range

    rest = _consume_leading_qualifiers(rest)

    name_match = re.match(r"^([A-Za-z_]\w*)", rest)
    if not name_match:
        return None, direction, current_range

    name = name_match.group(1)
    width = _width_from_range_text(current_range)

    port = {
        "name": name,
        "width": width,
    }
    if current_range:
        port["range"] = current_range
    if direction:
        port["direction"] = direction

    return port, direction, current_range


def _parse_param_block(param_text: str) -> List[Dict]:
    param_list: List[Dict] = []
    for item in _move_leading_comments_to_previous(_split_top_level_items(param_text)):
        code, comment = _extract_code_and_comment(item)
        code = code.strip().rstrip(",").rstrip(";").strip()
        if not code:
            continue

        code = re.sub(r"^\s*(parameter|localparam)\b", "", code, flags=re.I).strip()
        if not code:
            continue

        if "=" in code:
            left, value = code.split("=", 1)
            value = value.strip()
        else:
            left, value = code, ""

        left = left.strip()
        name_matches = re.findall(r"[A-Za-z_]\w*", left)
        if not name_matches:
            continue
        name = name_matches[-1]

        item_dict = {
            "name": name,
            "value": value,
        }
        if comment:
            item_dict["comment"] = comment
        param_list.append(item_dict)

    return param_list


def _parse_port_block(port_text: str) -> tuple[List[Dict], List[Dict], List[Dict]]:
    input_list: List[Dict] = []
    output_list: List[Dict] = []
    inout_list: List[Dict] = []

    inherited_direction: Optional[str] = None
    inherited_range: Optional[str] = None

    for item in _move_leading_comments_to_previous(_split_top_level_items(port_text)):
        code, comment = _extract_code_and_comment(item)
        port, inherited_direction, inherited_range = _parse_port_decl_item(
            code,
            inherited_direction=inherited_direction,
            inherited_range=inherited_range,
        )
        if port is None:
            continue
        if comment:
            port["comment"] = comment

        direction = port.get("direction")
        if direction == "input":
            input_list.append(port)
        elif direction == "output":
            output_list.append(port)
        elif direction == "inout":
            inout_list.append(port)

    return input_list, output_list, inout_list

def _fmt_param_number(value: str) -> str:
    value = value.strip()
    if not value:
        return value

    int_value = _verilog_int_literal_to_int(value)
    if int_value is not None:
        return str(int_value)

    return value

def parse_verilog_module_interface(verilog_text: str, is_no_parameter: bool = True) -> Dict:
    '''
    解析 Verilog / SystemVerilog 顶层 ANSI 风格模块头，返回：
    {
        "module_name": str,
        "param_list":  [{"name": ..., "value": ..., "comment": ...}, ...],
        "input_list":  [{"name": ..., "width": ..., "comment": ...}, ...],
        "output_list": [{"name": ..., "width": ..., "comment": ...}, ...],
        "inout_list":  [...],
    }

    说明：
    - 支持 module name #( ... ) ( ... );
    - 支持无参数模块 module name ( ... );
    - 支持 // 与 /* */ 注释、换行、空格干扰
    - width 对简单数值范围会转成整数；参数表达式会尽量简化，如 [CMD_W-1:0] -> "CMD_W"
    - 更复杂的范围会保留为字符串，例如 "[W*2-1:0]" 或 "[3:0][1:0]"
    '''
    if not isinstance(verilog_text, str) or not verilog_text.strip():
        raise ValueError("verilog_text 不能为空")

    text = verilog_text.replace("\r\n", "\n").replace("\r", "\n")
    sanitized = _sanitize_verilog_text_preserve_layout(text)

    module_match = re.search(r"\bmodule\b\s+(?:automatic\s+|static\s+)?([A-Za-z_]\w*)", sanitized)
    if not module_match:
        raise ValueError("未找到 module 声明")

    module_name = module_match.group(1)
    idx = module_match.end()

    while idx < len(sanitized) and sanitized[idx].isspace():
        idx += 1

    param_block = ""
    if idx < len(sanitized) and sanitized[idx] == "#":
        idx += 1
        while idx < len(sanitized) and sanitized[idx].isspace():
            idx += 1
        if idx >= len(sanitized) or sanitized[idx] != "(":
            raise ValueError("检测到 # 但后面不是参数括号")
        _, param_end = _extract_balanced_region(sanitized, idx, "(", ")")
        param_block = text[idx + 1:param_end]
        idx = param_end + 1

    while idx < len(sanitized) and sanitized[idx].isspace():
        idx += 1

    if idx >= len(sanitized) or sanitized[idx] != "(":
        raise ValueError("未找到模块端口列表")

    _, port_end = _extract_balanced_region(sanitized, idx, "(", ")")
    port_block = text[idx + 1:port_end]

    param_list = _parse_param_block(param_block) if param_block.strip() else []
    input_list, output_list, inout_list = _parse_port_block(port_block)

    # 如果是无参数模式，把位宽表达式中的参数替换成默认值，方便后续显示；否则保留原样，避免误导用户参数值不固定
    if is_no_parameter:
        param_defaults = {param["name"]: param["value"] for param in param_list}
        for port in input_list + output_list + inout_list:
            width = port["width"]
            if isinstance(width, str) and width in param_defaults:
                port["width"] = _fmt_param_number(param_defaults[width])

    return {
        "module_name": module_name,
        "param_list": param_list,
        "input_list": input_list,
        "output_list": output_list,
        "inout_list": inout_list,
    }


def parse_verilog_to_drawio_file(
    verilog_text: str,
    output_path: str | Path,
    port_font_size: int = 10,
    module_font_size: int = 14,
    **drawio_kwargs,
) -> Path:
    '''
    便捷函数：直接把 Verilog 顶层声明解析并生成独立 .drawio 文件。
    其中 page_name / page_width / page_height 等页面参数也通过 **drawio_kwargs 传入。
    '''
    parsed = parse_verilog_module_interface(verilog_text)

    page_kwargs = {}
    module_kwargs = dict(drawio_kwargs)
    for key in ["page_name", "page_width", "page_height", "dx", "dy", "host", "version"]:
        if key in module_kwargs:
            page_kwargs[key] = module_kwargs.pop(key)

    module_xml = generate_drawio_module_xml(
        module_name=parsed["module_name"],
        input_list=parsed["input_list"],
        output_list=parsed["output_list"],
        port_font_size=port_font_size,
        module_font_size=module_font_size,
        **module_kwargs,
    )

    return generate_drawio_file(
        module_xml=module_xml,
        output_path=output_path,
        **page_kwargs,
    )


def parse_verilog_to_drawio_module_xml(
    verilog_text: str,
    port_font_size: int = 10,
    module_font_size: int = 14,
    **drawio_kwargs,
) -> str:
    '''
    便捷函数：直接把 Verilog 顶层声明解析成 draw.io 模块 XML。
    '''
    parsed = parse_verilog_module_interface(verilog_text)
    return generate_drawio_module_xml(
        module_name=parsed["module_name"],
        input_list=parsed["input_list"],
        output_list=parsed["output_list"],
        port_font_size=port_font_size,
        module_font_size=module_font_size,
        **drawio_kwargs,
    )


def parse_verilog_to_drawio_url_encoded(
    verilog_text: str,
    port_font_size: int = 10,
    module_font_size: int = 14,
    **drawio_kwargs,
) -> str:
    '''
    便捷函数：直接把 Verilog 顶层声明解析成 draw.io 可粘贴的 URL 编码文本。
    '''
    module_xml = parse_verilog_to_drawio_module_xml(
        verilog_text,
        port_font_size=port_font_size,
        module_font_size=module_font_size,
        **drawio_kwargs,
    )
    return generate_drawio_url_encoded(module_xml)

if __name__ == "__main__":
    sample_text = r'''
module ctrl_cmd#(
    parameter CMD_ADDR_WIDTH = 12,
    parameter CMD_MAX_ADDR = 12'hFFF
)(
    input  wire                      i_cmd_clk       ,  // Control clock
    input  wire                      i_cmd_rst_n     ,  // Control reset (active low)

    input  wire                      i_decode_done   ,  // Signal to indicate that the command decoding is done and the next command can be issued
    input  wire                      i_once_start    ,  // Signal to indicate the start of a new control transaction, only valid for the first transaction
    input  wire                      i_is_jump       ,  // Signal to indicate whether the current command is a jump command
    input  wire [CMD_ADDR_WIDTH-1:0] i_jump_addr     ,  // Control address input [CMD_ADDR_WIDTH-1:0]

    output wire                      o_cmd_start     ,  // Signal to indicate the start of a new control transaction (asserted for one clock cycle at the start of each transaction)
    output wire                      o_cmd_addr_valid,  // Signal to indicate that the command address output is valid
    output wire [CMD_ADDR_WIDTH-1:0] o_cmd_addr         // Command address
);
'''

    parsed = parse_verilog_module_interface(sample_text)
    # 保存到json文件
    import json

    with open("parsed_module.json", "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=4, ensure_ascii=False)


    # print(parsed)

    # module_xml = generate_drawio_module_xml(
    #     module_name=parsed["module_name"],
    #     input_list=parsed["input_list"],
    #     output_list=parsed["output_list"],
    #     port_font_size=10,
    #     module_font_size=14,
    # )
    # print(module_xml)
    # generate_drawio_file(module_xml, "example_ctrl_cmd.drawio")
