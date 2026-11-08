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

# Run a Local App

Prefix a link with `run:` to launch a command when you click it. Use angle brackets when the command contains spaces:

```markdown
[Logistic regression](<run:python /Users/blaz/Documents/lectures/apps/ml/log-reg-simple/app.py>)
```

Relative paths are resolved from the notes file:

```markdown
[Orange demo](<run:python ../orange/run-demo.py>)
```

Ordinary file links still open in the default app; only `run:` links execute.

# Math

Inline math uses single dollar signs: $e^{i\pi}+1=0$, or LaTeX parentheses: \(a(i)\) = average distance from point \(i\) to other points in its **own cluster**.

Display math uses double dollar signs on their own lines:

$$
s(i)=\frac{b(i)-a(i)}{\max(a(i),b(i))}
$$

Math inside fenced code is not parsed:

```
$a = 1$
```

# Edit While You Talk

Keep the notes beside a browser or chatbot and change them live.

* **`e`** opens this Markdown file in the default editor
* Change a line, save, then **`r`** or **`R`** reloads without leaving the slide
* While another app is focused, **⌘⌃← / →** still move between slides
