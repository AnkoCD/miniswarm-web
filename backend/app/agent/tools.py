TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "install_skill_from_github",
            "description": (
                "仅在用户明确要求安装 Skill 并提供公开 GitHub 地址时使用。"
                "系统会锁定提交、运行 NVIDIA SkillSpector 静态安全扫描，"
                "只有扫描通过且用户审批后才会原子安装；不会覆盖已有 Skill。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "pattern": "^https://(www\\.)?github\\.com/.+",
                        "maxLength": 2048,
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "读取当前任务已启用 Skill 中的 UTF-8 说明或资源索引。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_skill_file",
            "description": "把当前任务已启用 Skill 的模板或资源复制到 workspace、shared 或 output；覆盖需要审批。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "anysearch",
            "description": "通过 AnySearch 官方服务执行实时搜索、批量搜索、垂直领域发现或网页正文提取。联网会经过风险审批。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["search", "batch_search", "extract", "get_sub_domains"]},
                    "query": {"type": "string", "maxLength": 500},
                    "queries": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "maxLength": 500},
                                        "domain": {"type": "string", "maxLength": 80},
                                        "sub_domain": {"type": "string", "maxLength": 120},
                                        "sub_domain_params": {"type": "object"},
                                        "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                                    },
                                    "required": ["query"],
                                },
                            ]
                        },
                    },
                    "url": {"type": "string", "maxLength": 2000},
                    "domain": {"type": "string", "maxLength": 80},
                    "domains": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                    "sub_domain": {"type": "string", "maxLength": 120},
                    "sub_domain_params": {"type": "object"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_document",
            "description": (
                "使用服务器内置 LibreOffice 把任务目录中的 DOCX、XLSX 或 PPTX "
                "转换为真实 PDF；适合先制作可编辑 Office 原稿，再稳定交付 PDF。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "pattern": "^(input|workspace|shared|output)/.+\\.(docx|xlsx|pptx)$",
                    },
                    "target": {
                        "type": "string",
                        "pattern": "^(workspace|shared|output)/.+\\.pdf$",
                    },
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_to_markdown",
            "description": "使用 Microsoft MarkItDown 把任务内文档转换为 Markdown 文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string", "pattern": "^(workspace|shared|output)/.+\\.md$"},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_swiss_deck",
            "description": "使用 guizang-ppt-skill 官方只读校验器检查任务内的瑞士风 HTML deck。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出任务目录内的文件。路径使用相对任务根目录的路径。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对路径，默认 ."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text",
            "description": "读取任务目录内不超过 2MB 的 UTF-8 文本文件。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_document",
            "description": (
                "只读质检单个最终文件，不能传目录。DOCX 会检查正文、标题、列表、表格并逐页渲染；"
                "XLSX 会检查工作表、公式、公式错误、格式并重新计算和渲染；PDF 会逐页渲染检查空白或异常页面；"
                "PPTX 检查文本越界、显著重叠以及低于 14pt 的长文本块；"
                "另支持图片、HTML、CSV、JSON、Markdown、代码、文本和 ZIP。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_text",
            "description": "写入 UTF-8 文本，只能写 workspace、shared 或 output。覆盖已有文件会等待用户审批。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "复制任务目录内的文件；覆盖目标会等待审批。",
            "parameters": {
                "type": "object",
                "properties": {"source": {"type": "string"}, "target": {"type": "string"}},
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "移动任务文件。此操作始终需要用户审批。",
            "parameters": {
                "type": "object",
                "properties": {"source": {"type": "string"}, "target": {"type": "string"}},
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_to_trash",
            "description": "把文件移入任务回收站。此操作始终需要用户审批。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "在 workspace、shared 或 output 内创建目录。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_zip",
            "description": "把任务内文件打包到 output 目录中的 ZIP。覆盖会等待审批。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "target": {"type": "string"},
                },
                "required": ["sources", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "通过固定的 Bing News RSS 端点检索最新新闻，返回标题、摘要、发布时间和来源链接。访问外网前需要用户审批。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "运行已经由 write_text 写入 workspace 的 Python 文件。script 必须是任务根目录相对路径，例如 workspace/create_pptx.py；禁止填写 Python 代码、exec/open 表达式、命令或绝对路径。最长 300 秒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Python 文件路径，例如 workspace/create_pptx.py，不是代码内容",
                        "pattern": "^workspace/.+\\.py$",
                    },
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                "required": ["script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "在隔离 Runner 中用固定的 python -m pytest -q 命令运行 workspace 内测试；不接受任意 Shell 参数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                },
            },
        },
    },
]

READ_ONLY_TOOLS = [
    tool for tool in TOOL_DEFINITIONS
    if tool["function"]["name"]
    in {
        "list_files",
        "read_text",
        "read_skill_file",
        "validate_swiss_deck",
        "inspect_document",
        "convert_to_markdown",
    }
]


def tool_definitions_for_skills(
    active_skills: list[str],
    *,
    reviewer: bool,
    allow_skill_install: bool = False,
) -> list[dict]:
    active = set(active_skills)
    result: list[dict] = []
    for tool in TOOL_DEFINITIONS:
        name = tool["function"]["name"]
        if name == "install_skill_from_github" and not allow_skill_install:
            continue
        if name in {"read_skill_file", "copy_skill_file"} and not active:
            continue
        if name == "validate_swiss_deck" and "guizang-ppt-skill" not in active:
            continue
        if name == "anysearch" and "anysearch" not in active:
            continue
        if name == "convert_to_markdown" and not (
            {"markitdown", "docx", "pdf", "xlsx"} & active
        ):
            continue
        if reviewer and name not in {
            "list_files", "read_text", "read_skill_file", "validate_swiss_deck",
            "inspect_document", "anysearch", "convert_to_markdown",
        }:
            continue
        result.append(tool)
    return result
