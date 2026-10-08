# PDF/图片只读证据工具

`scripts/source_evidence.py`只采集证据，不是科学符号识别器。PDF文字层中的字符、字体名、字号和坐标不能单独证明下标、上标、斜体或加粗的语义；普通小字号、参考文献编号和化学计量角标须靠原页视觉、完整上下文及符号定义区分。识别工作仍须人工/视觉回查，不可将此工具运行成功当作识别正确。

```powershell
python -B -X utf8 scripts/source_evidence.py 'input.pdf' --pages '1,3-4' --output 'new-evidence.json'
python -B -X utf8 scripts/source_evidence.py 'input.pdf' --pages '3' --bbox 20 80 300 240 --output 'new-crop-evidence.json'
python -B -X utf8 scripts/source_evidence.py 'input.png' --output 'new-image-evidence.json'
```

- 必须显式提供新输出路径；已存在路径、原件自身或其链接均不覆盖。源文件只读并记录读取前后SHA256，不相同则失败。工具不联网、不上传材料、不调用OCR，也不写PDF或图片。
- PDF必须指定物理页码，从1起，与论文印刷页码可能不同。逗号/闭区间均可，禁止0、越界及倒序区间。不要默认扫描全篇。
- 裁剪框为pdfplumber原页坐标`(x0, top, x1, bottom)`，单位pt，左上方向参照字段说明；不接受图像像素坐标。框须位于原页内且宽高为正。同一框应用于所有选页，跨页时须自行确认适用。`rotation`、原页bbox、请求框及选择框均记录。
- `extracted_text`是文字层的未经校正输出，不是对原文的可靠复原；保留字符顺序/编码错误的可能。`chars`保留所选区字符的坐标、字号、字体、矩阵等原始属性。裁剪可能截断边界字符的bbox，所以同时保存`full_page_chars`及`full_page_extracted_text`供追溯；不做Unicode归一化或角标替换。
- 空文字层只报告`no_characters_in_selected_region`，绝不推断“页面无内容”；需渲染页图、视觉读取，必要时用可用的本地OCR辅助并回查。文字层乱码/错序同理；本工具不要求为普通本地读取再确认许可。
- 图片仅验证容器并输出格式、尺寸、模式、帧数和哈希；`ocr_status=not_performed`、`recognized_text=null`。尺寸/hash并非“已经看过图像”。多帧图像需另行检查每帧，容器验证不证明每帧已渲染。

使用证据时记录“物理页号 + bbox + 原截图/页图 + 候选逐字符转录 + 确认状态”。例如经原页确认的`LaU@D_{3h}(5)-C_{78}`，下标范围是整个`3h`与`78`，`(5)`仍是基线异构体编号；不能因只有数字容易被检索就遗漏h，不能从模糊图猜出5或78。PDF字体名可提示斜体/粗体候选，仍要核对页图以及量符号、点群、化学元素等角色。确认后的范围交给原生Word工具，而非把坐标或小字号直接复制为Word格式。
