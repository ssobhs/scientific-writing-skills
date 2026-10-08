# 操作与输入

依赖：建议Python 3.10及以上；XML角标与公式工具需要lxml，字符格式API需要python-docx，PDF证据工具需要pdfplumber，图片证据工具需要Pillow。一般LaTeX公式转换另需Pandoc（原开发环境为3.12），通过 `--pandoc` 指定可执行文件，或 `PANDOC_PATH` / PATH定位。工具不自动安装依赖。所有输出使用新路径；原件保持。

本文`scripts/...`命令以该skill文件夹为当前目录；在仓库根目录使用前先进入`skills/word-native-math`。来源证据接口里的相对脚本命令采用同一约定。独立复制skill时请一并复制参考和脚本。

## 新写普通上下标

```python
from docx import Document
doc = Document()
p = doc.add_paragraph()
p.add_run('LaU@D')
p.add_run('3h').font.subscript = True
p.add_run('(5)-C')
p.add_run('78').font.subscript = True
doc.save('example.docx')
```

字号继承同一正文基准，Word自行执行角标缩放。此例仅展示字符位置，正式字体、正斜体和段落设置来自模板及原稿。上标使用 `font.superscript=True`。一个run不能同时承担两个不同的上下标范围；复杂对齐使用OMML。

## 显式修复映射

```json
{
  "replacements": [
    {
      "find": "LaU@D₃h(5)-C₇₈",
      "notation": "LaU@D_{3h}(5)-C_{78}",
      "part": "word/document.xml",
      "paragraph_contains": "目标段落的唯一片段",
      "expected_count": 1
    }
  ]
}
```

`notation`使用普通字符；`_{...}`指定下标，`^{...}`指定上标。该标记是工具输入，不会留在Word。无标记部分保持基线。以既有来源确认上下标范围，不把工具当化学式解析器。

Unicode角标按对应普通字符匹配，因此已修成原生格式后可再次检查。同一目标中的可见字符须一致，不能利用本工具改元素或删除未声明的文字。例如源中含原样字符 `SO4^2−` 而目标删除 `^` 会被拒绝；应先明确这是输入标记，再另作有记录的文本修正，或使用公式转换路径。字号确需从伪角标恢复时可另加 `"base_size_pt": 12`，这个值必须来自实际段落样式，不默认所有文稿12磅。

```text
python scripts/native_scripts.py audit input.docx --report audit.json
python scripts/native_scripts.py apply input.docx mapping.json output.docx --report changes.json
```

匹配数量、字段或保护边界不符合预期则不生成部分完成稿。精确范围优于过宽的全文匹配。不要覆盖已有报告而丢失前一轮结果。

## 可编辑公式

先在新稿的目标位置写一个唯一占位符，如 `[[EQ1]]`。整行公式让占位符独占一个普通段落；行内公式设置 `display:false`，占位符需完整位于一个普通text run内。该小工具不处理跨run的行内公式占位、链接内占位或受保护对象；需要这些布局时使用已有Word公式编辑或另做有据局部操作。

```json
{
  "equations": [
    {
      "placeholder": "[[EQ1]]",
      "latex": "x_i^2",
      "display": true,
      "expected_count": 1,
      "expected_omml": ["m:sSubSup"]
    },
    {
      "placeholder": "[[EQ2]]",
      "latex": "\\frac{1}{2\\pi}\\int_{-\\infty}^{\\infty} f(x)\\,\\mathrm{d}x",
      "expected_omml": ["m:f", "m:nary"]
    },
    {
      "placeholder": "[[EQ3]]",
      "prescript": {"base": "U", "sub": "92", "sup": "238", "upright": true},
      "expected_omml": ["m:sPre"]
    }
  ]
}
```

```text
python scripts/word_equations.py input.docx equations.json output.docx --pandoc PATH_TO_PANDOC --report equations-report.json
```

公式源不包含 `$` 包围符。转换时使用Pandoc的沙箱和警告即失败模式，禁止静默降级。只把公式OMML节点嵌入原文档，其他包部件保持；公式字体局部设为Cambria Math，保留转换器给出的直立文本/变量差异，不全局删 `m:nor` 或强制所有符号斜体。

本轮实测发现：Pandoc 3.12把 `{}^{238}_{92}\mathrm{U}` 转成空底项右角标后接U；`\prescript`、`\sideset`不受支持。需要明确绑定U的左侧上下标时，使用上面的显式 `prescript`，由脚本生成标准 `m:sPre`。这是已验证的窄补充，不宣称支持任意LaTeX宏。

程序也提供 `append_equation(paragraph, latex, pandoc, scratch, display=False)`；可用于python-docx新文档。display模式要求空段落。`prescript_fragment(spec)`返回可加入段落的原生节点。输出均需实际Word与页面核验，函数成功不代替公式内容核验。

## 审查的含义

Unicode小字符、手动位移和相对较小字号都是定位线索，不自动等于科学错误。脚本统计直接XML属性；审查样式继承、旧Equation/MathType OLE、图形文本或图片中的公式时应另外核对，不把这些对象误报为已修复。保持符号含义和原稿格式比一键批量替换更重要。
