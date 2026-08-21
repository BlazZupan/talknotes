#!/usr/bin/env /opt/miniconda3/envs/orange/bin/python
#
# Setup:
#   python -m pip install PySide6 markdown-it-py pygments pynput
#
# Usage:
#   python talknotes.py path/to/slides.md
#   python talknotes.py path/to/directory
#
# The Markdown file is split into slides at top-level "# Heading" lines.
# A directory opens name.md, or the only .md file, or asks if there are few.

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from pathlib import Path
from typing import Any

try:
    from markdown_it import MarkdownIt
except ImportError as exc:
    print(
        "Missing dependency: markdown-it-py. Install it with:\n"
        "  python -m pip install PySide6 markdown-it-py pygments pynput",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name
    from pygments.util import ClassNotFound
except ImportError as exc:
    print(
        "Missing dependency: pygments. Install it with:\n"
        "  python -m pip install PySide6 markdown-it-py pygments pynput",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

try:
    from PySide6.QtCore import (
        QEvent,
        QObject,
        QPoint,
        QRect,
        QSettings,
        QSize,
        Qt,
        QTimer,
        QUrl,
        QUrlQuery,
        Signal,
        Slot,
    )
    from PySide6.QtGui import (
        QCloseEvent,
        QCursor,
        QDesktopServices,
        QImageReader,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPixmap,
        QResizeEvent,
        QShowEvent,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMainWindow,
        QScrollArea,
        QSizePolicy,
    )
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as exc:
    print(
        "Missing dependency: PySide6 with Qt WebEngine. Install it with:\n"
        "  python -m pip install PySide6 markdown-it-py pygments pynput",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

try:
    from pynput import keyboard as pynput_keyboard  # pyright: ignore[reportMissingModuleSource]
except ImportError:
    pynput_keyboard = None

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None


TOP_LEVEL_HEADING = re.compile(r"^#(?!#)(?:\s+|$)")
BLOCKQUOTE_PREFIX = re.compile(r"^>\s?")
BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_LINK = re.compile(
    r"""<a\s+[^>]*href=(['"])(.*?)\1[^>]*>(.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
HTML_STRONG = re.compile(r"<(?:strong|b)>(.*?)</(?:strong|b)>", re.IGNORECASE | re.DOTALL)
HTML_EMPHASIS = re.compile(r"<(?:em|i)>(.*?)</(?:em|i)>", re.IGNORECASE | re.DOTALL)
HTML_CODE = re.compile(r"<code>(.*?)</code>", re.IGNORECASE | re.DOTALL)
HTML_HEADING = re.compile(
    r"<h([1-6])(?:\s[^>]*)?>(.*?)</h\1>",
    re.IGNORECASE | re.DOTALL,
)
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 72
FONT_STEP = 3
DEFAULT_FONT_SIZE = 34
DEFAULT_QUOTE_FONT_RATIO = 0.7
MIN_QUOTE_FONT_RATIO = 0.1
MAX_QUOTE_FONT_RATIO = 1.0
QUOTE_FONT_RATIO_STEP = 0.1
SETTINGS_ORG = "Talknotes"
SETTINGS_APP = "talknotes"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
HTML_A_HREF = re.compile(
    r"""(<a\b[^>]*\shref=)(['"])(.*?)\2""",
    re.IGNORECASE,
)
HTML_IMG_TAG = re.compile(
    r"""<img\b[^>]*\ssrc=(['"])(.*?)\1[^>]*>""",
    re.IGNORECASE,
)
EXTERNAL_HREF_PREFIXES = ("http://", "https://", "mailto:", "talknotes:", "javascript:", "#")


def split_slides(markdown_text: str) -> list[str]:
    """Split Markdown into slides beginning at top-level '# ' headings."""
    slides: list[list[str]] = []
    current_slide: list[str] | None = None

    for line in markdown_text.splitlines(keepends=True):
        if TOP_LEVEL_HEADING.match(line):
            if current_slide is not None:
                slides.append(current_slide)
            current_slide = [line]
        elif current_slide is not None:
            current_slide.append(line)

    if current_slide is not None:
        slides.append(current_slide)

    return ["".join(slide).strip() for slide in slides]


def normalize_quoted_markdown(text: str) -> str:
    """Keep markdown-style formatting while removing HTML quote artifacts."""
    text = BR_TAG.sub("", text)
    text = HTML_HEADING.sub(
        lambda match: "#" * int(match.group(1)) + " " + match.group(2).strip(),
        text,
    )
    text = HTML_LINK.sub(r"[\3](\2)", text)
    text = HTML_STRONG.sub(r"**\1**", text)
    text = HTML_EMPHASIS.sub(r"*\1*", text)
    text = HTML_CODE.sub(r"`\1`", text)
    return html.unescape(text)


def _finalize_quoted_block(block: list[str]) -> str | None:
    normalized = normalize_quoted_markdown("\n".join(block))
    return normalized if normalized.strip() else None


def extract_quoted_blocks(slide_markdown: str) -> list[str]:
    """Return blockquote blocks from a slide, without leading '> ' markers."""
    blocks: list[str] = []
    current_block: list[str] | None = None

    for line in slide_markdown.splitlines():
        if BLOCKQUOTE_PREFIX.match(line):
            if current_block is None:
                current_block = []
            current_block.append(BLOCKQUOTE_PREFIX.sub("", line, count=1))
        elif current_block is not None:
            if line.strip() == "":
                finalized = _finalize_quoted_block(current_block)
                if finalized is not None:
                    blocks.append(finalized)
                current_block = None
            else:
                current_block.append(line)

    if current_block is not None:
        finalized = _finalize_quoted_block(current_block)
        if finalized is not None:
            blocks.append(finalized)

    return blocks


def extract_quoted_text(slide_markdown: str) -> str | None:
    """Return all blockquote markdown from a slide."""
    blocks = extract_quoted_blocks(slide_markdown)
    if not blocks:
        return None
    return "\n\n".join(blocks)


def extract_nth_quoted_text(slide_markdown: str, index: int) -> str | None:
    """Return the 1-based blockquote block from a slide, if it exists."""
    blocks = extract_quoted_blocks(slide_markdown)
    if 1 <= index <= len(blocks):
        return blocks[index - 1]
    return None


def highlight_code(code: str, language: str, _attrs: str = "") -> str:
    """Return highlighted HTML for fenced code blocks."""
    try:
        lexer = get_lexer_by_name(language.strip()) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()

    formatter = HtmlFormatter(nowrap=True)
    highlighted = highlight(code, lexer, formatter)
    return f'<pre class="code-block"><code>{highlighted}</code></pre>'


def create_markdown_renderer() -> MarkdownIt:
    """Create a Markdown renderer with HTML, tables, and code highlighting."""
    renderer = MarkdownIt(
        "default",
        {
            "html": True,
            "typographer": True,
            "highlight": highlight_code,
        },
    )
    renderer.enable("table")
    return renderer


def local_file_url(path: Path) -> str:
    """Return a file:// URL for a local path."""
    return QUrl.fromLocalFile(str(path.resolve())).toString()


def view_image_url(path: Path) -> str:
    """Return a talknotes:// URL that opens an image in the in-app viewer."""
    url = QUrl("talknotes://view-image")
    query = QUrlQuery()
    query.addQueryItem("file", str(path.resolve()))
    url.setQuery(query)
    return url.toString()


def parse_view_image_path(url: QUrl) -> Path | None:
    """Parse a talknotes://view-image URL into a local image path."""
    file_value = QUrlQuery(url.query()).queryItemValue(
        "file",
        QUrl.ComponentFormattingOption.FullyDecoded,
    )
    if not file_value:
        return None

    if file_value.lower().startswith("file:"):
        local_path = Path(QUrl(file_value).toLocalFile()).expanduser()
    else:
        local_path = Path(file_value).expanduser()

    try:
        resolved = local_path.resolve()
    except OSError:
        return None

    return resolved if resolved.is_file() else None


def image_viewer_settings_prefix(path: Path) -> str:
    """Return a stable QSettings prefix for one image viewer window."""
    digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    return f"image_viewer/{digest}"


def window_geometry_prefix(markdown_path: Path, screen_size: QSize) -> str:
    """Return a QSettings prefix for one markdown file at one screen resolution."""
    digest = hashlib.sha256(str(markdown_path.resolve()).encode()).hexdigest()
    return f"window_geometry/{digest}/{screen_size.width()}x{screen_size.height()}"


def screen_for_window_geometry(window: QMainWindow | None = None):
    """Screen that contains the window, else the screen under the cursor, else primary."""
    if window is not None:
        screen = QApplication.screenAt(window.frameGeometry().center())
        if screen is not None:
            return screen
    return QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()


def resolve_local_path(href: str, markdown_dir: Path) -> Path | None:
    """Resolve a markdown href/src to an existing local file, or None."""
    href = href.strip()
    if not href or href.lower().startswith(EXTERNAL_HREF_PREFIXES):
        return None

    if href.lower().startswith("file:"):
        local_path = Path(QUrl(href).toLocalFile()).expanduser()
    else:
        local_path = Path(href).expanduser()
        if not local_path.is_absolute():
            local_path = markdown_dir / local_path

    try:
        resolved = local_path.resolve()
    except OSError:
        return None

    return resolved if resolved.is_file() else None


def link_local_files(body_html: str, markdown_dir: Path) -> str:
    """Rewrite local hrefs and wrap non-image file images in clickable links."""
    def rewrite_anchor(match: re.Match[str]) -> str:
        prefix, quote, href = match.group(1), match.group(2), match.group(3)
        if href.lower().startswith(
            ("talknotes:", "http://", "https://", "mailto:", "javascript:", "#")
        ):
            return match.group(0)
        path = resolve_local_path(href, markdown_dir)
        if path is None:
            return match.group(0)
        return f"{prefix}{quote}{html.escape(local_file_url(path), quote=True)}{quote}"

    def wrap_image(match: re.Match[str]) -> str:
        img_tag, src = match.group(0), match.group(2)
        path = resolve_local_path(src, markdown_dir)
        if path is None:
            return img_tag
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            href = html.escape(view_image_url(path), quote=True)
            return f'<a href="{href}" class="image-link">{img_tag}</a>'
        file_href = html.escape(local_file_url(path), quote=True)
        return f'<a href="{file_href}" class="local-file-link">{img_tag}</a>'

    body_html = HTML_IMG_TAG.sub(wrap_image, body_html)
    return HTML_A_HREF.sub(rewrite_anchor, body_html)


TALKNOTES_SHORTCUTS: list[tuple[str, str]] = [
    ("← / →", "previous / next slide"),
    ("↑ / ↓", "first / last slide"),
    ("digits + Return", "jump to slide number"),
    ("Shift + + / −", "increase / decrease text size"),
    ("Option + drag", "move window (frameless mode)"),
    ("t", "toggle window frame / title bar"),
    ("p", "toggle page numbers"),
    ("d", "toggle dark mode"),
    ("r", "reload markdown file"),
    ("c", "copy all quoted markdown"),
    ("m + 1–9", "copy i-th quoted block"),
    ("e", "open markdown in default editor"),
    ("click image", "open image in movable, resizable window"),
    ("[ / ]", "decrease / increase quoted text size"),
    ("h / ? / Escape", "show / hide this help"),
]

GLOBAL_SHORTCUTS: list[tuple[str, str]] = [
    ("⌘⌃← / ⌘⌃→", "previous / next slide"),
    ("⌘⌃↑ / ⌘⌃↓", "first / last slide"),
]


def render_help_overlay_html() -> str:
    """Return the centered shortcut help overlay."""
    rows = "".join(
        f"<tr><td class=\"help-keys\">{html.escape(keys)}</td>"
        f"<td class=\"help-desc\">{html.escape(desc)}</td></tr>"
        for keys, desc in TALKNOTES_SHORTCUTS
    )
    global_rows = "".join(
        f"<tr><td class=\"help-keys\">{html.escape(keys)}</td>"
        f"<td class=\"help-desc\">{html.escape(desc)}</td></tr>"
        for keys, desc in GLOBAL_SHORTCUTS
    )
    return f"""<div class="help-overlay">
  <div class="help-panel">
    <table class="help-table">{rows}</table>
    <div class="help-section">Global (while another app is active)</div>
    <table class="help-table">{global_rows}</table>
  </div>
</div>"""


def render_slide_html(
    slide_markdown: str,
    *,
    slide_number: int,
    slide_count: int,
    font_size: int,
    quote_font_ratio: float,
    show_page_numbers: bool,
    show_help: bool,
    dark_mode: bool,
    markdown_dir: Path,
) -> str:
    """Render one slide as a complete HTML document."""
    renderer = create_markdown_renderer()
    body = link_local_files(renderer.render(slide_markdown), markdown_dir)
    footer = ""
    if show_page_numbers:
        footer = (
            f'<footer class="slide-footer">'
            f'<a class="help-trigger" href="talknotes://toggle-help" aria-label="Show keyboard shortcuts">?</a>'
            f'<span class="page-number">{slide_number} / {slide_count}</span>'
            f"</footer>"
        )
    help_overlay = render_help_overlay_html() if show_help else ""

    theme_class = "dark" if dark_mode else "light"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    {HtmlFormatter().get_style_defs(".highlight")}

    :root {{
      color-scheme: light dark;
    }}

    html,
    body {{
      margin: 0;
      min-height: 100%;
    }}

    body {{
      background: #f8f8f6;
      color: #1f2328;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
        "Helvetica Neue", Arial, sans-serif;
      font-size: {font_size}px;
      line-height: 1.42;
    }}

    body.dark {{
      background: #111318;
      color: #f2f4f8;
    }}

    .slide {{
      box-sizing: border-box;
      min-height: 100vh;
      padding: 5.5vh 6vw 8vh;
    }}

    h1,
    h2,
    h3 {{
      line-height: 1.1;
      margin: 0 0 0.65em;
    }}

    h1 {{
      font-size: 1.8em;
    }}

    h2 {{
      font-size: 1.35em;
      margin-top: 1.1em;
    }}

    h3 {{
      font-size: 1.1em;
      margin-top: 1em;
    }}

    p,
    ul,
    ol,
    table,
    pre,
    blockquote {{
      margin-top: 0;
      margin-bottom: 0.9em;
    }}

    ul,
    ol {{
      padding-left: 1.25em;
    }}

    li {{
      margin: 0.28em 0;
    }}

    a {{
      color: #0969da;
    }}

    body.dark a {{
      color: #8ab4ff;
    }}

    strong {{
      font-weight: 700;
    }}

    em {{
      font-style: italic;
    }}

    img {{
      display: block;
      max-width: 100%;
      max-height: 62vh;
      object-fit: contain;
      margin: 1em auto;
      border-radius: 10px;
    }}

    a.local-file-link,
    a.image-link {{
      cursor: pointer;
      display: block;
    }}

    a.local-file-link img,
    a.image-link img {{
      margin: 1em auto;
    }}

    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 0.78em;
    }}

    th,
    td {{
      border: 1px solid #d0d7de;
      padding: 0.35em 0.5em;
      text-align: left;
      vertical-align: top;
    }}

    body.dark th,
    body.dark td {{
      border-color: #3d444d;
    }}

    th {{
      background: rgba(127, 127, 127, 0.12);
      font-weight: 700;
    }}

    blockquote {{
      border-left: 0.22em solid #d0d7de;
      color: #57606a;
      font-size: {quote_font_ratio:.1f}em;
      margin-left: 0;
      margin-right: 0;
      padding-left: 0.8em;
    }}

    body.dark blockquote {{
      border-left-color: #3d444d;
      color: #c9d1d9;
    }}

    code {{
      border-radius: 5px;
      font-family: "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.78em;
    }}

    :not(pre) > code {{
      background: rgba(127, 127, 127, 0.16);
      padding: 0.08em 0.24em;
    }}

    .code-block {{
      background: #f0f0ee;
      border-radius: 11px;
      overflow-x: auto;
      padding: 0.9em 1em;
      white-space: pre;
    }}

    body.dark .code-block {{
      background: #1b1f27;
    }}

    .slide-footer {{
      align-items: center;
      bottom: 2vh;
      color: #6e7781;
      display: grid;
      font-size: 0.46em;
      grid-template-columns: 1fr auto 1fr;
      left: 0;
      padding: 0 2vw;
      position: fixed;
      right: 0;
    }}

    body.dark .slide-footer {{
      color: #9ea7b3;
    }}

    .help-trigger {{
      align-items: center;
      background: rgba(127, 127, 127, 0.12);
      border: 1.5px solid currentColor;
      border-radius: 50%;
      box-sizing: border-box;
      color: inherit;
      display: inline-flex;
      font-size: 1.15em;
      font-weight: 600;
      height: 2.25em;
      justify-content: center;
      justify-self: start;
      line-height: 1;
      opacity: 0.9;
      position: relative;
      left: 0.55em;
      top: 0.45em;
      text-decoration: none;
      width: 2.25em;
    }}

    body.dark .help-trigger {{
      background: rgba(255, 255, 255, 0.08);
    }}

    .help-trigger:hover {{
      opacity: 1;
    }}

    .page-number {{
      font-size: 1.5em;
      grid-column: 2;
      text-align: center;
    }}

    .help-overlay {{
      align-items: center;
      background: rgba(0, 0, 0, 0.35);
      display: flex;
      font-size: 11px !important;
      inset: 0;
      justify-content: center;
      line-height: 1.3;
      position: fixed;
      z-index: 100;
    }}

    body.dark .help-overlay {{
      background: rgba(0, 0, 0, 0.55);
    }}

    .help-panel {{
      background: #ffffff;
      border-radius: 8px;
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
      color: #1f2328;
      font-size: 11px !important;
      line-height: 1.3;
      max-height: 70vh;
      min-width: min(270px, 85vw);
      max-width: 85%;
      overflow-y: auto;
      padding: 9px 12px;
    }}

    body.dark .help-panel {{
      background: #1b1f27;
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.45);
      color: #f2f4f8;
    }}

    .help-table {{
      border-collapse: collapse;
      font-size: 11px !important;
      width: 100%;
    }}

    .help-keys {{
      color: #1f2328;
      font-family: "SF Mono", Menlo, Consolas, monospace;
      font-size: 10px !important;
      font-weight: 500;
      padding: 1px 10px 1px 0;
      vertical-align: top;
      white-space: nowrap;
    }}

    body.dark .help-keys {{
      color: #f2f4f8;
    }}

    .help-desc {{
      color: #1f2328;
      font-size: 11px !important;
      padding: 1px 0;
    }}

    body.dark .help-desc {{
      color: #e6edf3;
    }}

    .help-section {{
      border-top: 1px solid rgba(127, 127, 127, 0.25);
      color: #57606a;
      font-size: 10px !important;
      font-weight: 600;
      margin-top: 6px;
      padding-top: 5px;
    }}

    body.dark .help-section {{
      color: #9ea7b3;
    }}
  </style>
</head>
<body class="{theme_class}">
  <main class="slide">
    {body}
  </main>
  {footer}
  {help_overlay}
</body>
</html>"""


def geometry_fits_screen(geometry: QRect) -> bool:
    """Return True if the rectangle fits entirely within some screen."""
    if geometry.width() <= 0 or geometry.height() <= 0:
        return False

    for screen in QApplication.screens():
        if screen.availableGeometry().contains(geometry):
            return True
    return False


def clamp_geometry_to_screen(geometry: QRect) -> QRect:
    """Move a rectangle onto the nearest visible screen area, preserving size."""
    if geometry_fits_screen(geometry):
        return geometry

    best_screen = None
    best_area = 0
    for screen in QApplication.screens():
        intersection = screen.availableGeometry().intersected(geometry)
        area = max(0, intersection.width()) * max(0, intersection.height())
        if area > best_area:
            best_area = area
            best_screen = screen

    if best_screen is None:
        best_screen = QApplication.screenAt(geometry.center()) or QApplication.primaryScreen()
    if best_screen is None:
        return geometry

    available = best_screen.availableGeometry()
    width = min(geometry.width(), available.width())
    height = min(geometry.height(), available.height())
    x = max(available.left(), min(geometry.x(), available.right() - width + 1))
    y = max(available.top(), min(geometry.y(), available.bottom() - height + 1))
    return QRect(x, y, width, height)


def fit_size_to_screen(size: QSize) -> QSize:
    """Return a size that fits within the primary screen's available area."""
    if size.width() <= 0 or size.height() <= 0:
        return size

    screen = QApplication.primaryScreen()
    if screen is None:
        return size

    available = screen.availableGeometry().size()
    if size.width() <= available.width() and size.height() <= available.height():
        return size

    return size.scaled(available, Qt.AspectRatioMode.KeepAspectRatio)


def load_image_pixmap(path: Path) -> QPixmap:
    """Load a raster or SVG image into a pixmap."""
    if path.suffix.lower() == ".svg":
        if QSvgRenderer is None:
            return QPixmap()
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return QPixmap()

        size = renderer.defaultSize()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(800, 600)

        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap

    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        return pixmap

    image = QImageReader(str(path)).read()
    return QPixmap.fromImage(image) if not image.isNull() else QPixmap()


def image_display_size(image_path: Path) -> QSize:
    """Return the preferred client size for showing an image at native resolution."""
    pixmap = load_image_pixmap(image_path)
    if pixmap.isNull():
        return QSize(640, 480)
    return fit_size_to_screen(pixmap.size())


def load_saved_image_viewer_geometry(image_path: Path) -> QRect | None:
    """Return saved outer geometry for an image viewer, if it looks usable."""
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    prefix = image_viewer_settings_prefix(image_path)
    x = settings.value(f"{prefix}/x", type=int)
    y = settings.value(f"{prefix}/y", type=int)
    width = settings.value(f"{prefix}/width", type=int)
    height = settings.value(f"{prefix}/height", type=int)
    if None in (x, y, width, height):
        return None

    outer = QRect(x, y, width, height)
    if outer.width() < 120 or outer.height() < 120:
        return None
    return outer


def center_window_on_screen(window: QMainWindow, client_size: QSize) -> None:
    """Resize the client area and center the window on the primary screen."""
    window.resize(client_size)
    screen = QApplication.primaryScreen()
    if screen is None:
        return

    available = screen.availableGeometry()
    frame = window.frameGeometry()
    if frame.width() > available.width() or frame.height() > available.height():
        frame_extra = QSize(
            frame.width() - window.geometry().width(),
            frame.height() - window.geometry().height(),
        )
        max_client = QSize(
            max(120, available.width() - frame_extra.width()),
            max(120, available.height() - frame_extra.height()),
        )
        fitted_client = client_size.scaled(max_client, Qt.AspectRatioMode.KeepAspectRatio)
        window.resize(fitted_client)
        frame = window.frameGeometry()

    window.move(
        available.x() + max(0, (available.width() - frame.width()) // 2),
        available.y() + max(0, (available.height() - frame.height()) // 2),
    )


def apply_default_image_viewer_geometry(window: QMainWindow, image_path: Path) -> None:
    """Size a viewer window to the image and center it on screen."""
    center_window_on_screen(window, image_display_size(image_path))


def apply_image_viewer_geometry(window: QMainWindow, image_path: Path) -> None:
    """Restore saved viewer geometry or apply a default image-sized layout."""
    saved = load_saved_image_viewer_geometry(image_path)
    if saved is not None:
        set_frame_geometry(window, clamp_geometry_to_screen(saved))
        return
    apply_default_image_viewer_geometry(window, image_path)


def save_image_viewer_geometry(window: QMainWindow, image_path: Path) -> None:
    """Persist an image viewer window's outer geometry."""
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    prefix = image_viewer_settings_prefix(image_path)
    outer = window.frameGeometry()
    settings.setValue(f"{prefix}/x", outer.x())
    settings.setValue(f"{prefix}/y", outer.y())
    settings.setValue(f"{prefix}/width", outer.width())
    settings.setValue(f"{prefix}/height", outer.height())


def set_frame_geometry(window: QMainWindow, outer: QRect) -> None:
    """Set a top-level window's outer bounds (PySide6 lacks setFrameGeometry)."""
    window.setGeometry(outer)
    frame = window.frameGeometry()
    if frame == outer:
        return

    client = window.geometry()
    window.setGeometry(
        client.x() + (outer.x() - frame.x()),
        client.y() + (outer.y() - frame.y()),
        client.width() + (outer.width() - frame.width()),
        client.height() + (outer.height() - frame.height()),
    )


def slide_index_key(markdown_path: Path) -> str:
    return f"slide_index/{markdown_path.resolve()}"


def load_quote_font_ratio(settings: QSettings) -> float:
    saved_ratio = settings.value("quote_font_ratio", DEFAULT_QUOTE_FONT_RATIO)
    try:
        quote_font_ratio = float(saved_ratio)
    except (TypeError, ValueError):
        quote_font_ratio = DEFAULT_QUOTE_FONT_RATIO
    return max(
        MIN_QUOTE_FONT_RATIO,
        min(MAX_QUOTE_FONT_RATIO, round(quote_font_ratio, 1)),
    )


def save_quote_font_ratio(ratio: float) -> None:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue("quote_font_ratio", ratio)
    settings.sync()


def restore_window_settings(window: TalknotesWindow) -> None:
    """Restore saved font size, slide index, and window geometry when it fits."""
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    font_size = settings.value("font_size", DEFAULT_FONT_SIZE, type=int)
    window.font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, font_size))
    window.quote_font_ratio = load_quote_font_ratio(settings)

    slide_index = settings.value(slide_index_key(window.markdown_path), 0, type=int)
    window.current_index = max(0, min(slide_index, len(window.slides) - 1))

    window._frameless = settings.value("window/frameless", True, type=bool)
    window._apply_window_flags()

    screen = screen_for_window_geometry()
    if screen is not None:
        prefix = window_geometry_prefix(window.markdown_path, screen.size())
        x = settings.value(f"{prefix}/x", type=int)
        y = settings.value(f"{prefix}/y", type=int)
        width = settings.value(f"{prefix}/width", type=int)
        height = settings.value(f"{prefix}/height", type=int)
        if None not in (x, y, width, height):
            geometry = QRect(x, y, width, height)
            if geometry_fits_screen(geometry):
                set_frame_geometry(window, geometry)
                return

    window.position_left_quarter()


def save_window_settings(window: TalknotesWindow) -> None:
    """Persist font size, slide index, and window geometry."""
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue("font_size", window.font_size)
    save_quote_font_ratio(window.quote_font_ratio)
    settings.setValue(slide_index_key(window.markdown_path), window.current_index)
    settings.setValue("window/frameless", window._frameless)
    screen = screen_for_window_geometry(window)
    if screen is None:
        return
    prefix = window_geometry_prefix(window.markdown_path, screen.size())
    outer = window.frameGeometry()
    settings.setValue(f"{prefix}/x", outer.x())
    settings.setValue(f"{prefix}/y", outer.y())
    settings.setValue(f"{prefix}/width", outer.width())
    settings.setValue(f"{prefix}/height", outer.height())


class ImageViewerWindow(QMainWindow):
    """Framed window for viewing a single slide image."""

    def __init__(self, image_path: Path) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.image_path = image_path.resolve()
        self._source_pixmap = load_image_pixmap(self.image_path)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )

        scroll = QScrollArea()
        scroll.setWidget(self._label)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(scroll)

        self.setWindowTitle(self.image_path.name)
        self._geometry_applied = False

        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self.close)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._geometry_applied:
            self._geometry_applied = True
            apply_image_viewer_geometry(self, self.image_path)
        self._update_scaled_pixmap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            self._label.setText(f"Could not load image:\n{self.image_path.name}")
            self._label.setPixmap(QPixmap())
            return

        viewport = self.centralWidget()
        if not isinstance(viewport, QScrollArea):
            return

        available = viewport.viewport().size()
        if available.width() <= 0 or available.height() <= 0:
            return

        scaled = self._source_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def closeEvent(self, event: QCloseEvent) -> None:
        save_image_viewer_geometry(self, self.image_path)
        super().closeEvent(event)


class TalknotesWebPage(QWebEnginePage):
    """Open slide links in the system default browser."""

    def __init__(self, window: TalknotesWindow, parent: QWebEngineView) -> None:
        super().__init__(parent)
        self._window = window

    def acceptNavigationRequest(
        self,
        url: QUrl,
        navigation_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if (
            not is_main_frame
            or navigation_type
            != QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        ):
            return True

        scheme = url.scheme().lower()
        if scheme == "talknotes":
            action = url.host()
            if action == "toggle-help":
                self._window.toggle_help()
            elif action == "close-help":
                self._window.close_help()
            elif action == "view-image":
                image_path = parse_view_image_path(url)
                if (
                    image_path is not None
                    and image_path.suffix.lower() in IMAGE_EXTENSIONS
                ):
                    self._window.open_image_viewer(image_path)
            return False

        if scheme in ("http", "https", "mailto", "file"):
            self._open_external_url(url)
        return False

    def _open_external_url(self, url: QUrl) -> None:
        if url.scheme().lower() == "file":
            path = Path(url.toLocalFile()).expanduser()
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            return
        QDesktopServices.openUrl(url)


class TalknotesWebView(QWebEngineView):
    """Route talknotes keyboard shortcuts before Qt WebEngine handles them."""

    def __init__(self, window: TalknotesWindow) -> None:
        super().__init__(window)
        self._window = window

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._window._handle_quote_font_shortcut(event):
            event.accept()
            return
        self._window.handle_key_press(event)
        if event.isAccepted():
            return
        super().keyPressEvent(event)


class TalknotesWindow(QMainWindow):
    """Main talknotes window with keyboard-driven slide state."""

    def __init__(self, markdown_path: Path, slides: list[str]) -> None:
        super().__init__()
        self._frameless = True
        self.markdown_path = markdown_path
        self.slides = slides
        self.current_index = 0
        self.font_size = DEFAULT_FONT_SIZE
        self.quote_font_ratio = DEFAULT_QUOTE_FONT_RATIO
        self.show_page_numbers = True
        self.show_help = False
        self.dark_mode = False
        self.page_number_input = ""
        self.quote_copy_pending = False
        self._move_dragging = False
        self._move_drag_offset = QPoint()
        self._focus_proxy_filter_installed = False
        self._image_viewers: dict[str, ImageViewerWindow] = {}

        self.web_view = TalknotesWebView(self)
        self.web_view.setPage(TalknotesWebPage(self, self.web_view))
        self.web_view.installEventFilter(self)
        self.setCentralWidget(self.web_view)
        self.setWindowTitle(markdown_path.name)
        restore_window_settings(self)
        self._setup_quote_font_shortcuts()
        self._setup_escape_shortcut()
        self.render_current_slide()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._ensure_focus_proxy_filter()

    def _ensure_focus_proxy_filter(self) -> None:
        if self._focus_proxy_filter_installed:
            return
        focus_proxy = self.web_view.focusProxy()
        if focus_proxy is not None:
            focus_proxy.installEventFilter(self)
            self._focus_proxy_filter_installed = True

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.Window
        if self._frameless:
            flags |= Qt.WindowType.FramelessWindowHint
        outer = self.frameGeometry()
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        self._focus_proxy_filter_installed = False
        if was_visible:
            self.show()
        set_frame_geometry(self, outer)
        self._ensure_focus_proxy_filter()

    def toggle_window_frame(self) -> None:
        self._frameless = not self._frameless
        self._apply_window_flags()

    def _begin_window_move(self, event: QMouseEvent) -> bool:
        if (
            not self._frameless
            or event.button() != Qt.MouseButton.LeftButton
            or not (
                QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier
            )
        ):
            return False

        window_handle = self.windowHandle()
        if window_handle is not None and window_handle.startSystemMove():
            event.accept()
            return True

        global_pos = event.globalPosition().toPoint()
        self._move_drag_offset = global_pos - self.frameGeometry().topLeft()
        self._move_dragging = True
        event.accept()
        return True

    def _continue_window_move(self, event: QMouseEvent) -> bool:
        if not self._move_dragging:
            return False

        global_pos = event.globalPosition().toPoint()
        self.move(global_pos - self._move_drag_offset)
        event.accept()
        return True

    def _end_window_move(self, event: QMouseEvent) -> bool:
        if not self._move_dragging or event.button() != Qt.MouseButton.LeftButton:
            return False

        self._move_dragging = False
        event.accept()
        return True

    def _setup_quote_font_shortcuts(self) -> None:
        bindings = (
            ("[", self.decrease_quote_font_ratio),
            ("]", self.increase_quote_font_ratio),
        )
        for sequence, handler in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)

    def _setup_escape_shortcut(self) -> None:
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._on_escape_pressed)

    def _on_escape_pressed(self) -> None:
        if self.show_help:
            self.close_help()

    @Slot()
    def decrease_quote_font_ratio(self) -> None:
        self.change_quote_font_ratio(-QUOTE_FONT_RATIO_STEP)

    @Slot()
    def increase_quote_font_ratio(self) -> None:
        self.change_quote_font_ratio(QUOTE_FONT_RATIO_STEP)

    def _is_decrease_quote_ratio_key(self, event: QKeyEvent) -> bool:
        return event.key() == Qt.Key_BracketLeft or event.text() == "["

    def _is_increase_quote_ratio_key(self, event: QKeyEvent) -> bool:
        return event.key() == Qt.Key_BracketRight or event.text() == "]"

    def _handle_quote_font_shortcut(self, event: QKeyEvent) -> bool:
        if not (
            self._is_decrease_quote_ratio_key(event)
            or self._is_increase_quote_ratio_key(event)
        ):
            return False

        if event.modifiers() not in (Qt.NoModifier, Qt.KeypadModifier):
            return False

        if self._is_decrease_quote_ratio_key(event):
            self.decrease_quote_font_ratio()
            return True
        if self._is_increase_quote_ratio_key(event):
            self.increase_quote_font_ratio()
            return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        focus_proxy = self.web_view.focusProxy()
        is_web_view = watched is self.web_view
        is_focus_proxy = focus_proxy is not None and watched is focus_proxy
        if not is_web_view and not is_focus_proxy:
            return super().eventFilter(watched, event)

        if is_focus_proxy:
            if event.type() == QEvent.Type.MouseButtonPress:
                if isinstance(event, QMouseEvent):
                    if self._dismiss_help_on_click(event):
                        return True
                    if self._begin_window_move(event):
                        return True
            elif event.type() == QEvent.Type.MouseMove:
                if isinstance(event, QMouseEvent) and self._continue_window_move(event):
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if isinstance(event, QMouseEvent) and self._end_window_move(event):
                    return True
            elif (
                self.show_help
                and event.type() == QEvent.Type.KeyPress
                and isinstance(event, QKeyEvent)
            ):
                self.handle_key_press(event)
                event.accept()
                return True
        elif is_web_view and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent):
                if self._handle_quote_font_shortcut(event):
                    event.accept()
                    return True
                self.handle_key_press(event)
                if event.isAccepted():
                    return True

        return super().eventFilter(watched, event)

    def toggle_help(self) -> None:
        self.show_help = not self.show_help
        self.render_current_slide()

    def _is_help_shortcut(self, event: QKeyEvent) -> bool:
        return event.key() in (Qt.Key_H, Qt.Key_Question) or event.text() == "?"

    def close_help(self) -> None:
        if not self.show_help:
            return
        self.show_help = False
        self.render_current_slide()

    def _dismiss_help_on_click(self, event: QMouseEvent) -> bool:
        if (
            not self.show_help
            or event.button() != Qt.MouseButton.LeftButton
            or QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier
        ):
            return False

        self.close_help()
        event.accept()
        return True

    def render_current_slide(self) -> None:
        html = render_slide_html(
            self.slides[self.current_index],
            slide_number=self.current_index + 1,
            slide_count=len(self.slides),
            font_size=self.font_size,
            quote_font_ratio=self.quote_font_ratio,
            show_page_numbers=self.show_page_numbers,
            show_help=self.show_help,
            dark_mode=self.dark_mode,
            markdown_dir=self.markdown_path.parent,
        )
        base_url = QUrl.fromLocalFile(str(self.markdown_path.parent.resolve()) + "/")
        self.web_view.setHtml(html, base_url)

    def position_left_quarter(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        self.setGeometry(
            geometry.left(),
            geometry.top(),
            max(1, geometry.width() // 4),
            geometry.height(),
        )

    def open_image_viewer(self, path: Path) -> None:
        """Open or focus a framed viewer window for a local image file."""
        resolved = path.resolve()
        key = str(resolved)
        existing = self._image_viewers.get(key)
        if existing is not None:
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
            self._image_viewers.pop(key, None)

        viewer = ImageViewerWindow(resolved)
        viewer.destroyed.connect(lambda *_args, image_key=key: self._image_viewers.pop(image_key, None))
        self._image_viewers[key] = viewer
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def go_to_slide(self, index: int) -> None:
        clamped_index = max(0, min(index, len(self.slides) - 1))
        if clamped_index != self.current_index:
            self.current_index = clamped_index
            self.render_current_slide()

    def change_font_size(self, delta: int) -> None:
        next_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, self.font_size + delta))
        if next_size != self.font_size:
            self.font_size = next_size
            self.render_current_slide()

    def change_quote_font_ratio(self, delta: float) -> None:
        next_ratio = round(self.quote_font_ratio + delta, 1)
        next_ratio = max(MIN_QUOTE_FONT_RATIO, min(MAX_QUOTE_FONT_RATIO, next_ratio))
        if next_ratio != self.quote_font_ratio:
            self.quote_font_ratio = next_ratio
            save_quote_font_ratio(self.quote_font_ratio)
            self.render_current_slide()

    def reload_markdown(self) -> None:
        """Reload slides from disk and restore the previous slide when possible."""
        saved_index = self.current_index
        try:
            slides = load_slides(self.markdown_path)
        except (OSError, ValueError) as exc:
            print(f"Could not reload Markdown file: {exc}", file=sys.stderr)
            return

        self.slides = slides
        if saved_index < len(self.slides):
            self.current_index = saved_index
        else:
            self.current_index = len(self.slides) - 1
        self.render_current_slide()

    def copy_quoted_text(self) -> None:
        quoted = extract_quoted_text(self.slides[self.current_index])
        if quoted is None:
            return
        QApplication.clipboard().setText(quoted)

    def copy_quoted_text_by_index(self, index: int) -> None:
        quoted = extract_nth_quoted_text(self.slides[self.current_index], index)
        if quoted is None:
            return
        QApplication.clipboard().setText(quoted)

    def open_markdown_file(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.markdown_path.resolve())))

    @Slot()
    def next_slide(self) -> None:
        self.go_to_slide(self.current_index + 1)

    @Slot()
    def previous_slide(self) -> None:
        self.go_to_slide(self.current_index - 1)

    @Slot()
    def first_slide(self) -> None:
        self.go_to_slide(0)

    @Slot()
    def last_slide(self) -> None:
        self.go_to_slide(len(self.slides) - 1)

    def go_to_page_number(self, page_number: int) -> None:
        if 1 <= page_number <= len(self.slides):
            self.go_to_slide(page_number - 1)

    def handle_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        if self.show_help:
            if key == Qt.Key_Escape:
                self.close_help()
            elif self._is_help_shortcut(event):
                self.toggle_help()
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self.page_number_input:
                self.go_to_page_number(int(self.page_number_input))
                self.page_number_input = ""
            event.accept()
            return

        if self.quote_copy_pending:
            if modifiers in (Qt.NoModifier, Qt.KeypadModifier) and Qt.Key_1 <= key <= Qt.Key_9:
                self.copy_quoted_text_by_index(key - Qt.Key_0)
                self.quote_copy_pending = False
                event.accept()
                return
            self.quote_copy_pending = False

        if modifiers in (Qt.NoModifier, Qt.KeypadModifier) and Qt.Key_0 <= key <= Qt.Key_9:
            self.page_number_input += str(key - Qt.Key_0)
            event.accept()
            return

        self.page_number_input = ""

        if key == Qt.Key_Right:
            self.go_to_slide(self.current_index + 1)
        elif key == Qt.Key_Left:
            self.go_to_slide(self.current_index - 1)
        elif key == Qt.Key_Up:
            self.go_to_slide(0)
        elif key == Qt.Key_Down:
            self.go_to_slide(len(self.slides) - 1)
        elif modifiers & Qt.ShiftModifier and key in (Qt.Key_Plus, Qt.Key_Equal):
            self.change_font_size(FONT_STEP)
        elif modifiers & Qt.ShiftModifier and key in (Qt.Key_Minus, Qt.Key_Underscore):
            self.change_font_size(-FONT_STEP)
        elif key == Qt.Key_P:
            self.show_page_numbers = not self.show_page_numbers
            self.render_current_slide()
        elif key == Qt.Key_R:
            self.reload_markdown()
        elif key == Qt.Key_C:
            self.copy_quoted_text()
        elif key == Qt.Key_M:
            self.quote_copy_pending = True
            self.page_number_input = ""
        elif key == Qt.Key_D:
            self.dark_mode = not self.dark_mode
            self.render_current_slide()
        elif key == Qt.Key_E:
            self.open_markdown_file()
        elif key == Qt.Key_T:
            self.toggle_window_frame()
        elif self._is_help_shortcut(event):
            self.toggle_help()
        else:
            super().keyPressEvent(event)
            return

        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._handle_quote_font_shortcut(event):
            event.accept()
            return
        self.handle_key_press(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        for viewer in list(self._image_viewers.values()):
            viewer.close()
        self._image_viewers.clear()
        save_window_settings(self)
        super().closeEvent(event)


class GlobalHotkeyBridge(QObject):
    """Forward pynput callbacks onto Qt's main thread."""

    next_slide = Signal()
    previous_slide = Signal()
    first_slide = Signal()
    last_slide = Signal()


def start_global_hotkeys(window: TalknotesWindow) -> Any | None:
    if pynput_keyboard is None:
        print(
            "Global hotkeys disabled: missing dependency pynput. Install it with:\n"
            "  python -m pip install PySide6 markdown-it-py pygments pynput",
            file=sys.stderr,
        )
        return None

    bridge = GlobalHotkeyBridge(window)
    bridge.next_slide.connect(window.next_slide)
    bridge.previous_slide.connect(window.previous_slide)
    bridge.first_slide.connect(window.first_slide)
    bridge.last_slide.connect(window.last_slide)

    hotkeys = {
        "<cmd>+<ctrl>+<right>": bridge.next_slide.emit,
        "<cmd>+<ctrl>+<left>": bridge.previous_slide.emit,
        "<cmd>+<ctrl>+<up>": bridge.first_slide.emit,
        "<cmd>+<ctrl>+<down>": bridge.last_slide.emit,
    }

    try:
        listener = pynput_keyboard.GlobalHotKeys(hotkeys)
        listener.start()
    except Exception as exc:
        print(f"Global hotkeys disabled: {exc}", file=sys.stderr)
        return None

    return listener


def _format_cli_shortcuts(shortcuts: list[tuple[str, str]]) -> str:
    width = max(len(keys) for keys, _ in shortcuts)
    return "\n".join(f"  {keys:<{width}}  {desc}" for keys, desc in shortcuts)


KEYSTROKE_HELP = (
    "Keystrokes (talknotes window focused):\n"
    + _format_cli_shortcuts(TALKNOTES_SHORTCUTS)
    + "\n\nGlobal shortcuts (work while another app is active):\n"
    + _format_cli_shortcuts(GLOBAL_SHORTCUTS)
)


MAX_DIRECTORY_MD_PROMPT = 9


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Talknotes — present a Markdown file as keyboard-navigable notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=KEYSTROKE_HELP,
    )
    parser.add_argument(
        "markdown_file",
        type=Path,
        help="Markdown file to present, or a directory of Markdown files",
    )
    return parser.parse_args(argv)


def list_markdown_files(directory: Path) -> list[Path]:
    """Return .md files directly in the directory, sorted by name."""
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    )


def choose_markdown_file(files: list[Path]) -> Path:
    """Ask which Markdown file to open when a directory contains several."""
    for index, path in enumerate(files, start=1):
        print(f"  {index}. {path.name}")
    prompt = f"Open which file? [1-{len(files)}]: "
    while True:
        try:
            choice = input(prompt).strip()
        except EOFError as exc:
            raise ValueError("No Markdown file selected.") from exc
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(files):
                return files[number - 1]
        print(f"Enter a number from 1 to {len(files)}.", file=sys.stderr)


def resolve_markdown_path(path: Path) -> Path:
    """Resolve a file or directory argument to a Markdown file to present."""
    path = path.expanduser()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if path.is_file():
        return path
    if not path.is_dir():
        raise ValueError(f"Path is not a file or directory: {path}")

    same_name = path / f"{path.name}.md"
    if same_name.is_file():
        return same_name

    files = list_markdown_files(path)
    if len(files) == 1:
        return files[0]
    if not files:
        raise ValueError(f"No Markdown files in directory: {path}")
    if len(files) > MAX_DIRECTORY_MD_PROMPT:
        raise ValueError(
            f"Too many Markdown files in directory ({len(files)}). "
            "Specify which file to open."
        )
    print(f"Several Markdown files in {path}:")
    return choose_markdown_file(files)


def load_slides(markdown_path: Path) -> list[str]:
    if not markdown_path.exists():
        raise ValueError(f"Markdown file does not exist: {markdown_path}")
    if not markdown_path.is_file():
        raise ValueError(f"Path is not a file: {markdown_path}")

    markdown_text = markdown_path.read_text(encoding="utf-8")
    slides = split_slides(markdown_text)
    if not slides:
        raise ValueError(
            "No slides found. Slides must begin with top-level '# ' Markdown headings."
        )
    return slides


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        markdown_path = resolve_markdown_path(args.markdown_file).resolve()
        slides = load_slides(markdown_path)
    except OSError as exc:
        print(f"Could not read Markdown file: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    app = QApplication(sys.argv[:1])
    window = TalknotesWindow(markdown_path, slides)
    window.show()

    def start_hotkeys() -> None:
        listener = start_global_hotkeys(window)
        if listener is not None:
            app.aboutToQuit.connect(listener.stop)

    QTimer.singleShot(0, start_hotkeys)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
