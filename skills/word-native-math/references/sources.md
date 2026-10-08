# 开源依据与边界

## 2026-10-08 扩展依据

- [python-docx文字与格式接口](https://python-docx.readthedocs.io/en/latest/user/text.html)：run原生字符格式，True、False和None不同，样式继承与局部覆盖分开。字符工具在此基础上独立实现，未复制外部项目脚本。
- [pdfplumber官方仓库](https://github.com/jsvine/pdfplumber)：用字符坐标、字号、字体和矩阵保留PDF证据。upright对应页面文字方向，不等于语义上的非斜体；文字提取并不恢复科学符号关系。读取工具不含OCR或自动科学识别模型。
- [IUPAC Green Book官方入口](https://iupac.org/what-we-do/books/greenbook/)及[第四版简编PDF](https://iupac.org/wp-content/uploads/2025/03/IUPAC-GB4Abridged.pdf)，第1.3、1.6、1.7节：根据物理量、变量、单位、标签、元素、函数算符和矢量等角色确定正斜体及必要的粗体。具体符号仍须核对文稿定义，不用规范掩盖不清晰来源。官方旧报告指南页本轮返回403，未宣称读到该页全文，改读上述公开Green Book。

本skill提供资料读取到Word格式的保真流程，并非全部OCR、字体识别或Word格式引擎。字符工具支持的属性和局限见[字符接口](rich-text-api.md)，只读证据工具见[证据接口](source-evidence-api.md)。原开发测试日志和样张未随公开包分发；实际使用者仍须依据来源确认符号，并检查目标环境中的文档结构和页面。

## 原有角标与公式依据

2026-10-07已检索GitHub及官方文档。本skill独立编写操作规则与局部工具，复用已安装基础库和外部转换器，不复制其他项目整包代码，也不是模型权重训练。

|资源|许可与用途|采用方式|
|---|---|---|
|[python-openxml/python-docx](https://github.com/python-openxml/python-docx)|MIT；DOCX基础库|新文档生成和run原生角标API；已有包的局部修复用lxml保留其他部件|
|[python-docx文字API](https://python-docx.readthedocs.io/en/latest/api/text.html)|官方subscript/superscript接口及段落赋值行为|避免整段赋值破坏run格式|
|[jgm/pandoc](https://github.com/jgm/pandoc)、[官方手册](https://pandoc.org/MANUAL.html)|GPL-2.0-or-later；DOCX公式输出OMML|调用外部程序转换单个公式片段，未把程序二进制重新分发进skill包|
|[Kantyc/pandoc-math-docx](https://github.com/Kantyc/pandoc-math-docx)|MIT；相近的公式skill示例|借鉴结构与渲染双重核验思路；不照搬环境相关的绝对禁令|
|[keh9mark/math2docx](https://github.com/keh9mark/math2docx)|MIT；多段公式转换封装|评估为备选，本轮未引入也未声明运行通过|

Word结构参考：[w:vertAlign](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.verticaltextalignment?view=openxml-3.0.1)、[m:sPre](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.math.presubsuper?view=openxml-3.0.1)。使用普通字符和真实格式属性；原生对象的存在不自动证明角标范围或数学含义正确。

原开发环境记录为Windows Microsoft Word 16.0、Python/lxml/python-docx及Pandoc 3.12，不能当作其他平台或版本的验证。本skill为Word DOCX设计，不承诺WPS、旧版Equation Editor/OLE或所有LaTeX宏均相同。实际报告应区分结构检查、Word回存及页面查看，未完成的环境验证如实说明。上表许可信息沿用开发时的来源记录，第三方资源当前条款以各自官方仓库为准；本包不分发外部程序或第三方论文全文。
