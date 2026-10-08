# 原生字符格式 API

`scripts/rich_text.py` 是可导入的 python-docx 辅助模块，不是全文纠错器。适合在新段落中写入已确认语义范围的 spans，或对已有明确选中的纯文字 run 设置局部字符属性。它不修改文字，不根据字母数字猜上下标，不把截图识别为已存在的可编辑正文。

下例假定已将本skill的`scripts`目录加入Python导入路径，或调用脚本位于该目录。`rich_text`是随skill分发的本地模块，不是独立的PyPI包。

```python
from rich_text import append_spans, apply_run_format

# p 是 python-docx Paragraph。先确认 i 是变量索引，total 是说明词。
append_spans(p, [
    {"text": "E", "format": {"italic": True}},
    {"text": "i", "format": {"italic": True, "vertical": "subscript"}},
    {"text": "   E", "format": {"italic": True}},
    {"text": "total", "format": {"italic": False, "vertical": "subscript"}},
])

# 整个 selected_run 的文字范围已经由调用者确认。
apply_run_format(selected_run, bold=True)
apply_run_format(selected_run, font_eastasia="宋体",
                 font_ascii="Times New Roman", font_hansi="Times New Roman")
```

## 支持的属性

| 键 | 值 | 原生含义 |
|---|---|---|
| `bold`、`italic` | `True` / `False` / `None` | 加粗、斜体 |
| `strike`、`double_strike` | `True` / `False` / `None` | 删除线、双删除线；禁止两个直接属性同时为True |
| `small_caps`、`all_caps` | `True` / `False` / `None` | 小型大写、全部大写显示；不改实际字符 |
| `underline` | 布尔、`None`、`single`、`double`、`dotted`、`dash`、`wave`、`words` | Word原生下划线 |
| `vertical` | `baseline`、`subscript`、`superscript`、`None` | 单一互斥的原生垂直对齐值；不缩字号 |
| `font_ascii`、`font_hansi`、`font_eastasia`、`font_cs` | 非空字体名称或`None` | 独立控制ASCII、高ANSI、东亚、复杂文字字体槽 |
| `size_pt` | 1至1638之间的0.5pt整数倍或`None` | 普通字号；不写复杂文字`szCs` |
| `color` | 如`0066AA`的六位RGB或`None` | 字体颜色 |
| `highlight` | 下列名称或`None` | Word原生高亮 |

高亮名称：`yellow`、`bright_green`、`turquoise`、`pink`、`blue`、`red`、`dark_blue`、`teal`、`green`、`violet`、`dark_red`、`dark_yellow`、`gray_50`、`gray_25`、`black`、`white`。

**省略属性表示保留，`None`表示删除该直接覆盖以恢复继承，`False`表示明确关闭。** `vertical="baseline"`明确恢复基线；`vertical=None`只删除直接vertAlign以恢复继承，可能继续继承样式中的角标，也保留已有手动position。显式指定baseline、subscript或superscript则同时清除直接w:position，避免旧手动位移叠加到指定的原生对齐；不改字号。其互斥接口不接受同时上标和下标；需要对齐的同底项上下标时用OMML。

字体槽修改会清除同一槽的theme引用，避免主题字体覆盖显式字体；其他槽不动。英文通常应同时指定`font_ascii`和`font_hansi`，仅写一个不会替另一个。未安装的字体仍可能在Word中替代，必须回存和渲染检查。复杂文字的`bCs`、`iCs`、`szCs`、字距、手动位移、阴影、描边及OpenType特性不在本API范围内，不能据此声称支持全部Word字体功能。

## 操作与安全边界

- `append_spans(p, spans)`只追加runs，不清空原段落。所有span均预检成功才写入段落。文本原样写入，包括Unicode；本函数不把输入伪角标自动规范化，调用者应先提供普通字符和明确格式。
- `apply_run_format(run, **fmt)`对整个run生效。它先在复制的run属性上验证，再替换该run的rPr，保留原run身份、文字元素和未指定格式；重复相同设置不增长runs。它不负责查找、拆分或合并runs。
- 局部API保守拒绝含图片、对象、制表符、换行、域或修订属性的run，也拒绝超链接内run。两个API均检查整XML部件中的跨段复杂域，拒绝参与域的段落，以及含修订（包括pPrChange等属性修订）或内容控件的段落/祖先容器。失败时不修改原对象。对这些对象用对象感知的Word流程，不把拒绝说成修复成功。
- 参数类型和相互矛盾的直接删除线经过验证；它不计算样式链/主题后的最终有效格式。例如继承的双删除线与直接删除线的冲突，须由调用者审查样式并明确选择两个属性。语义未确定时不自行把说明词斜体或把编号下标。
- 本模块是内存中的python-docx API，保存DOCX时由python-docx重新序列化包，不保证非目标ZIP部件字节不变。已有复杂文档要求部件级保全时，不将本模块作为通用修复器；原有 `native_scripts.py` 的定向角标ZIP编辑流程仍独立使用。
- 没有公式识别、OCR、图片转公式、全文格式诊断、学校模板推断或Word自动回存功能。OMML继续使用既有公式工具。最终仍须结构检查、Word回存和逐页视觉检查。

## 开发验证边界

原开发阶段记录了11项结构测试，以及首次失败、修复和边界补强。覆盖文字/未授权格式保全、幂等、继承与显式关闭、中英字体槽隔离、角标互斥、格式类型、失败不改及受保护对象拒绝；补强覆盖跨段域、段落属性修订/容器及显式角标替换手动位移。原始日志、样张与Word回存记录未随公开包分发；这些是历史开发记录，不是本次公开发布新执行的测试，也不能证明任意Word对象或版本均可处理。实际文档仍须检查结构、Word保存重开与页面效果。
