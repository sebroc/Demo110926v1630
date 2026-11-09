# Math 345 lecture notes

[Read the notes online](https://sebroc.github.io/Demo110926v1630/)

The original lecture TeX files in `Notes/Chap*/` are the editable source. The
PreTeXt website is generated from them, with one page per section, the original
numbering, bold vocabulary, and collapsible activity solutions.

## Edit and preview

```sh
python3 -m pip install -r PreTeXt/requirements.txt
# Install Pandoc separately if it is not already on your PATH.
python3 scripts/preview_pretext.py
```

The local preview at http://127.0.0.1:8766/ watches the TeX files and rebuilds on
save. Push changes to `main` to rebuild and publish the online notes through
GitHub Actions.

See [the PreTeXt workflow documentation](PreTeXt/README.md) for conversion rules,
one-time builds, and validation instructions.
