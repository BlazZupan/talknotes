# Markdown in Talknotes

Talknotes renders ordinary Markdown. A top-level `#` starts a new slide; `##` and `###` are headings on the slide.

## On this slide

Text can be **bold**, *italic*, or `inline code`. Links work, including [orangedatamining.com](https://orangedatamining.com).

1. Numbered lists
2. Nested ideas in order

* Bullets for unordered lists
* Mix them freely

# Tables

Tables are Markdown with pipes. Alignment uses `:---` (left), `:---:` (center), `---:` (right).

| Construct | Markdown |
| :-------- | -------: |
| Slide     | `# Title` |
| Heading   | `## Title` |
| Bold      | `**text**` |
| Italic    | `*text*` |
| Link      | `[label](url)` |
| Image     | `![](file.png)` |
| Quote     | `> text` |

# Code

Fenced blocks are highlighted. Click a local file link to open it.

```python
python talknotes.py examples/markdown
```

This folder also sits next to the Orange example: [orange.md](../orange/orange.md).

# Edit While You Talk

Keep the notes beside a browser or chatbot and change them live.

* **`e`** opens this Markdown file in the default editor
* Change a line, save, then **`r`** reloads without leaving the slide
* While another app is focused, **⌘⌃← / →** still move between slides
