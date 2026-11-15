"""Markdown 與 HTML 的共用轉換工具。"""

from __future__ import annotations

import html as html_module
import re

import markdown as markdown_lib
from bs4 import BeautifulSoup

_DROP_TAGS = ("script", "style", "noscript")


def markdown_to_html(text: str) -> str:
    """把 Markdown 轉成 HTML 片段（支援表格、程式碼區塊）。"""
    return markdown_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
        output_format="html5",
    )


def _clean_soup(text: str) -> BeautifulSoup:
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    if soup.head is not None:
        soup.head.decompose()  # <title> 不是內文
    return soup


def html_to_markdown(text: str) -> str:
    """把 HTML 轉成 Markdown，保留標題、清單、連結與表格。"""
    from markdownify import markdownify

    soup = _clean_soup(text)
    result = markdownify(str(soup), heading_style="ATX", bullets="-")
    return collapse_blank_lines(result)


def html_to_text(text: str) -> str:
    """去除所有標籤，只留下段落文字。"""
    soup = _clean_soup(text)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return collapse_blank_lines(soup.get_text("\n"))


def html_body(text: str) -> str:
    """取出 HTML 的 body 內容；同時保留 head 裡的樣式。"""
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    body = soup.body.decode_contents() if soup.body else str(soup)
    return body.strip()


def html_styles(text: str) -> str:
    soup = BeautifulSoup(text, "html.parser")
    return "\n".join(str(style) for style in soup.find_all("style"))


def collapse_blank_lines(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def escape(text: str) -> str:
    return html_module.escape(text, quote=False)


_DOCUMENT_STYLE = """
:root { color-scheme: light dark; }
body {
  max-width: 46rem;
  margin: 2rem auto;
  padding: 0 1.25rem;
  font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", system-ui, sans-serif;
  font-size: 16px;
  line-height: 1.75;
  color: #1f2328;
  background: #ffffff;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.3; margin: 1.6em 0 0.6em; }
h1 { font-size: 2rem; border-bottom: 1px solid #d8dee4; padding-bottom: 0.3em; }
h2 { font-size: 1.5rem; border-bottom: 1px solid #eaeef2; padding-bottom: 0.25em; }
p, ul, ol, blockquote, table, pre { margin: 0 0 1em; }
blockquote { margin-left: 0; padding-left: 1em; border-left: 4px solid #d0d7de; color: #57606a; }
code { font-family: "Cascadia Code", Consolas, "Courier New", monospace; font-size: 0.9em; }
pre { padding: 1em; overflow-x: auto; background: #f6f8fa; border-radius: 6px; }
pre code { font-size: 0.85em; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #d0d7de; padding: 0.45em 0.7em; text-align: left; }
th { background: #f6f8fa; }
img { max-width: 100%; height: auto; }
hr { border: 0; border-top: 1px solid #d8dee4; margin: 2em 0; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  h1, h2, hr { border-color: #30363d; }
  blockquote { border-color: #3d444d; color: #9198a1; }
  pre, th { background: #161b22; }
  th, td { border-color: #30363d; }
}
""".strip()


def html_document(body: str, title: str, extra_head: str = "") -> str:
    """包成一份完整、可直接開啟的 HTML 文件。"""
    head = f"\n{extra_head}" if extra_head else ""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)}</title>
<style>
{_DOCUMENT_STYLE}
</style>{head}
</head>
<body>
{body}
</body>
</html>
"""


__all__ = [
    "collapse_blank_lines",
    "escape",
    "html_body",
    "html_document",
    "html_styles",
    "html_to_markdown",
    "html_to_text",
    "markdown_to_html",
]
