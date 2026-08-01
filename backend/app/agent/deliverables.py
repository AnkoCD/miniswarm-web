from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MultiDeliverableRequest:
    count: int
    unit: str
    noun: str


_CN_NUMBERS = {
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
}

# Only nouns that normally describe independent final deliverables are included.
# Chapters, steps, pages, modules, and similar parts of one larger work are excluded.
_CN_PATTERN = re.compile(
    r"(?P<count>[2-8二两三四五六七八])\s*"
    r"(?P<unit>套|份|个|种|版|组|张|篇)\s*"
    r"(?P<modifier>[^，。；;\n]{0,18}?)"
    r"(?P<noun>试卷|卷子|考试卷|方案|报告|PPT|ppt|幻灯片|演示文稿|"
    r"简历|文档|海报|图片|表格|工作簿|清单|合同|通知|邮件|文章)",
    re.IGNORECASE,
)

_EN_PATTERN = re.compile(
    r"\b(?P<count>[2-8])\s+"
    r"(?:(?:different|distinct|independent|alternative)\s+)?"
    r"(?P<noun>exam papers?|tests?|proposals?|plans?|reports?|presentations?|"
    r"slide decks?|resumes?|documents?|posters?|images?|workbooks?|spreadsheets?)\b",
    re.IGNORECASE,
)

# Phrases that usually indicate parts of one continuous deliverable rather than
# multiple independently reviewable deliverables.
_SEQUENTIAL_PARTS = re.compile(
    r"(?:包含|分为|由).{0,12}(?:章|章节|节|步骤|阶段|部分|模块|页面|页)",
    re.IGNORECASE,
)


def detect_multi_deliverable_request(prompt: str) -> MultiDeliverableRequest | None:
    """Return an explicit 2-8 independent-deliverable request, if present.

    The detector is intentionally conservative. It only recognizes nouns that
    normally produce separate final files and ignores chapter/page/step counts.
    """

    text = " ".join(prompt.split())
    if not text:
        return None

    match = _CN_PATTERN.search(text)
    if match:
        raw_count = match.group("count")
        count = int(raw_count) if raw_count.isdigit() else _CN_NUMBERS[raw_count]
        noun = match.group("noun")
        # Avoid treating a count of internal parts as a reason to split a single
        # report/book/site when the quantity phrase is not itself the final noun.
        if _SEQUENTIAL_PARTS.search(text) and match.start() > _SEQUENTIAL_PARTS.search(text).start():
            return None
        return MultiDeliverableRequest(count=count, unit=match.group("unit"), noun=noun)

    match = _EN_PATTERN.search(text)
    if match:
        return MultiDeliverableRequest(
            count=int(match.group("count")),
            unit="items",
            noun=match.group("noun"),
        )
    return None
