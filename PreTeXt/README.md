# Math 345 lecture notes in PreTeXt

Edit the original `Notes/Chap*/Chap*-lectures.tex` files. The generated XML,
numbering stylesheet, and website are outputs, not parallel editable sources.
The TeX files and their PDF workflow are unchanged.

From the folder containing `Notes`, run:

```sh
python3 scripts/preview_pretext.py
```

Open http://127.0.0.1:8766/. The command builds the book, watches the TeX and
PNG figures, rebuilds on save, and reloads the browser after successful builds.
Keep the command running while editing. Stop it with Ctrl+C. To use another
port, add `--port 8767`.

For a one-time build without a server:

```sh
python3 scripts/preview_pretext.py --build-only
```

Prerequisites: Python 3.10+, Pandoc, and PreTeXt CLI (built with 2.21.0).
The currently installed tools already satisfy these requirements. On another
computer install Pandoc and `python3 -m pip install pretext==2.21.0`.
The HTML uses PreTeXt's standard MathJax assets; first builds and browser math
rendering may require internet access.

## Conversion rules

- `\chaptertitle{N}{Title}` and `\sectiontitle{N.M}{Title}` define divisions.
  Each section becomes its own HTML page. Section numbers are checked against
  their source order; unexpected numbering fails with an explanatory error.
- The chapter-wide shared counter for `\activity`, `\theorem`, `\definition`,
  `\note`, and the other numbered commands is preserved by the generated XSL.
  Existing activity labels and references remain connected.
- Every activity gets one initially collapsed native PreTeXt solution panel.
  Multiple `\answer[height]{...}` blocks are collected into that solution.
- Inside activities, `\shortanswer`, `\fillin`, and `\underline` become numbered
  blanks; their contents appear in the solution. Elsewhere these terms become
  bold. Boxed answers outside activities remain visible with an “Answer” label.
- Mathematical commands are read from the TeX preambles each time. Pandoc
  expands the source macros; math operators are also supplied to MathJax.
- Figures referenced by `\includegraphics` are copied from their source folders.
  Print-only spacing, page breaks, answer box heights, and minipages are omitted.
- Activities use the original unbraced `\activity` syntax. Their extent ends
  after the last boxed answer or short answer, including any enclosing list.
  For an activity containing only `\fillin`, its first answer paragraph ends
  the activity. Put additional solution parts in `\answer{...}` for clarity.

## Files

- `scripts/generate_pretext.py`: TeX semantic adapter and Pandoc-to-PreTeXt writer.
- `scripts/preview_pretext.py`: build command, file watcher, local server, reload.
- `PreTeXt/source/main.ptx`: generated book.
- `PreTeXt/source-map.json`: original chapter/section/counter for every block.
- `PreTeXt/conversion-report.json`: generated activity/section/figure counts.
- `PreTeXt/publication/publication.ptx`: editable web publication settings.
- `PreTeXt/output/web/`: generated HTML, figures, and assets.
- `PreTeXt/build.log`: most recent build details; failed builds are reported in
  the terminal. Fix the source and save again to retry automatically.

The converter deliberately rejects unsupported Pandoc structures rather than
silently dropping content. When introducing a new TeX construct, extend the
adapter if it reports an unsupported construct.

Run `python3 scripts/verify_pretext.py` to check structure, numbering, references,
all solution panels, figures, and local assets. If run with the Python installation
containing PreTeXt and lxml, it also validates against the official PreTeXt schema.
Every successful preview build runs the structural/HTML checks automatically.

## GitHub Pages

The `Build and deploy PreTeXt notes` GitHub Actions workflow builds the website
from the original TeX on pushes to `main`, validates it, and deploys the resulting
HTML to GitHub Pages. You can also run it from GitHub's Actions tab with **Run
workflow**. In repository **Settings → Pages**, the source must be **GitHub
Actions**.

After editing the TeX locally, commit and push your changes to publish them:

```sh
git add Notes
git commit -m "Update lecture notes"
git push
```

Local saves update the local preview. A push to GitHub triggers the online
rebuild. Generated HTML is uploaded as a Pages artifact, so it does not need to
be committed. A failed build keeps the previous published version available;
check the workflow's log artifact for details.

Inline `tikzpicture` figures in the original lecture TeX are rendered automatically
as SVG images for the website. Edit the TikZ in the TeX source and save to rebuild;
a content hash avoids recompiling unchanged figures. Local rendering requires
`latex` and `dvisvgm` (provided by MacTeX/TeX Live). The GitHub Actions workflow
installs the required TeX packages automatically.
