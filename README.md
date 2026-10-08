# Scientific Writing Skills

**中文科研写作与 Word 格式工具集**

当前版本：**1.0.0**，更新内容见[版本记录](CHANGELOG.md)。

这是一组帮助中文论文写作的 skills（计算团簇物理与化学、第一性原理方向）。它们用于根据已有材料起草、审查和修改正文，并把科学符号正确写入 Word，侧重科学含义保全、中文信息组织和可编辑格式。其他研究方向使用时，需要重新核对术语、论证习惯和符号约定。

这里的 skill 是指令、参考资料和辅助脚本组成的文件夹。项目没有训练或更新模型权重，也不提供学校官方论文模板。

## 选择哪个 skill

| 任务 | Skill | 重点 |
| --- | --- | --- |
| 背景、绪论、文献综述 | [cn-physics-introduction](skills/cn-physics-introduction/SKILL.md) | 中文搭配、跨句承接、文献比较与研究问题引出；保留事实与引用归属 |
| 理论与计算方法 | [cn-physics-computational-methods](skills/cn-physics-computational-methods/SKILL.md) | 方法对象、假设、公式含义、步骤依赖与适用范围；不补造实际计算设置 |
| 结果与讨论、图表分析 | [cn-physics-results-analysis](skills/cn-physics-results-analysis/SKILL.md) | 比较依据、数据含义、机制解释与结论范围；保留例外和负结果 |
| 资料符号读取、Word 字符格式与公式 | [word-native-math](skills/word-native-math/SKILL.md) | 先核对符号语义，再写入原生上下标、字符属性和可编辑 OMML 公式 |

按章节功能选择前三个 skill，不必同时加载全部规则。写入或修订 DOCX、从 PDF 或图片识别科学符号时，再配合 `word-native-math`。它不替代章节内容判断。

## 快速使用

### 在 Codex 中安装

在 Codex 中，可以要求 `$skill-installer` 从本仓库安装所需目录，例如：

```text
请使用 $skill-installer，从 GitHub 仓库 ssobhs/scientific-writing-skills
安装 skills/cn-physics-introduction。
```

也可以把所需的**完整 skill 文件夹**复制到项目的 `.agents/skills/`，或用户目录的 `~/.agents/skills/`。保留 `SKILL.md`、`references/`、`scripts/` 和 `agents/` 等现有内容，不要只复制入口文件。避免在多个位置重复安装同名 skill；同名技能不会自动合并。安装或更新后若未显示，再重启 Codex。

安装位置与使用方式依据 [OpenAI 官方 Build skills 文档](https://learn.chatgpt.com/docs/build-skills)（2026-10-08 查阅）。本项目以文件夹维护和发布，不单独制作或维护 ZIP 成品包。

### 调用

安装后，提供原文、来源材料和明确任务。例如：

```text
请使用 $cn-physics-introduction 审改下面的绪论段落。
只改善中文表达和段落衔接，保留科学含义、引用编号与工作完成状态。
有科学歧义时指出具体位置；已经准确自然的句子可以保留。

原文：
在这里粘贴需要修改的段落。
```

完整起草、方法审查、结果分析和 Word 修订示例见 [使用说明](docs/usage.md)。

### 脚本依赖

只使用写作指令不要求运行 Python。需要运行辅助脚本时，建议使用 Python 3.10 或更高版本，并按仓库的 [requirements.txt](requirements.txt) 安装依赖；目前没有跨 Python 版本测试结论：

```text
python -m pip install -r requirements.txt
```

Word 及来源证据工具使用 `lxml`、`python-docx`、`pdfplumber` 和 `Pillow`。一般 LaTeX 到 OMML 的转换另需 Pandoc。脚本输出仍须经过实际 Microsoft Word 打开、回存和页面检查；依赖安装成功不代表完成这些检查。

## 目录导航

```text
skills/
  cn-physics-introduction/
  cn-physics-computational-methods/
  cn-physics-results-analysis/
  word-native-math/
docs/
  usage.md
  validation.md
tools/
  check_release.py
requirements.txt
```

- [使用说明](docs/usage.md)：材料准备、四类提示词示例、Word 工作流程。
- [验证与来源边界](docs/validation.md)：历史采用版本、公开材料范围，以及检查结果能说明什么。
- [贡献说明](CONTRIBUTING.md)与[更新记录](CHANGELOG.md)：改进方式和公开版本变化。
- 每个 skill 的 `SKILL.md`：实际执行入口；按其中链接读取相关参考资料。

## 能力边界

- 写作依据来自使用者提供或授权查证的材料。规则要求保留证据强度、工作完成状态与归属，避免因润色把推测写成证明、计划写成完成，或把他人的设置写成本研究设置。
- 规则和脚本不能认证科学正确性，也不能代替作者对公式、数据、引用、贡献归属和学术规范的核验。理论介绍不代表计算已经运行、收敛或验证。
- PDF 文字层提取不等于 OCR，更不等于正确识别了上下标和粗斜体的科学含义。`source_evidence.py` 不调用 OCR；图片检查也不自动转录图中文字。
- Word 工具仅处理接口明确支持的范围。原始 DOCX 应保留，修改另存；字段、修订、受保护对象及复杂格式可能需要对象感知的局部处理。没有完成 Word 或页面核验时，应明确列出未完成项。
- 论文版式遵循使用者适用的官方模板。本仓库不分发私人研究材料、论文 PDF、学校模板或私人开发测试档案；公开题录与规则来源不构成论文全文的再发布。

这些 skill 的开发采用记录不等同于公开、可独立复现的性能评测，具体限制见 [验证说明](docs/validation.md)。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。公开文献和外部资源仍受各自权利与使用条件约束。
