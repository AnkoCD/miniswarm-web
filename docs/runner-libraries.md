# Runner 文档与数据支持库

Runner 镜像预装以下固定版本，Agent 不需要也无权在运行时安装包：

- `python-docx==1.2.0`：创建和检查 Word 文件。
- `openpyxl==3.1.5`：创建和检查 Excel 文件。
- `python-pptx==1.0.2`：创建和检查 PowerPoint 文件。
- `reportlab==5.0.0`：创建 PDF。
- `pypdf==6.14.2`：读取、检查和整理 PDF。
- `pdfplumber==0.11.9`：提取 PDF 文本与表格，并满足固定版 MarkItDown 的兼容要求。
- `pandas==2.3.1`：办公数据清洗、汇总和分析。
- `matplotlib==3.10.3`：生成可嵌入 Office/PDF 的静态图表。
- `Pillow==12.3.0`：图片处理。
- `defusedxml==0.7.1`：降低恶意 XML 文档解析风险。
- Debian `LibreOffice Writer/Calc/Impress`：固定只读渲染和 Excel 重新计算。
- Debian `Poppler`：PDF 逐页栅格化检查。
- Debian `Noto CJK` 与 `Liberation` 字体：中文与通用办公字体回退。

Python 包按固定版本从清华 TUNA 的 PyPI 镜像获取；Debian 包从清华 TUNA Debian 镜像获取并继续使用 Debian 官方签名验证。Agent 运行期间无权安装或升级依赖。
