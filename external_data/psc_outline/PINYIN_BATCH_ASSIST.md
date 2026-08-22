# Pinyin batch-assist workflow

This workflow stages OCR-backed pinyin suggestions for table 2 rows whose Hanzi
is present, whose pinyin is missing, and whose Hanzi OCR confidence is at least
0.85. It does not modify `entries`, `ocr_spans`, or `manual_corrections`.

## Preview without writing

Use the bundled Python shown by Codex, or any Python 3.10+ installation:

```powershell
python psc_outline_review_tool.py DATABASE.sqlite3 --preview-pinyin-proposals
```

On the clean pending snapshot used for verification, this reports 317
proposals: 302 same-column continuations, 9 next-column continuations, and 6
next-page continuations. Two rows without recoverable continuation evidence are
left untouched.

## Stage and review

Either run:

```powershell
python psc_outline_review_tool.py DATABASE.sqlite3 --prepare-pinyin-proposals
```

or open the database in the review tool and click **生成批量拼音建议**. An
optional database path can be passed to the launcher:

```powershell
.\Review-PSC-Outline.cmd C:\path\to\DATABASE.sqlite3
```

Staged suggestions live in `pinyin_proposals`; proposal changes are appended to
`pinyin_proposal_history`. They are not accepted corrections. In the review
tool, use **有批量建议** or **建议需重点复核** to inspect them. The latter filter
contains known polyphonic characters, multiple-reading suggestions, or pinyin
OCR confidence below 0.98. Suggestions with uncertain OCR spacing are also
flagged so a reviewer can check the expected hyphen or apostrophe.

Use **接受批量建议并下一条** to accept an unchanged suggestion. Acceptance goes
through `manual_corrections` and records `accept_pinyin_proposal` in
`manual_review_history`. Edited text still uses **保存修改并下一条**. Use
**撤销本条校对** to remove the accepted correction and append a `clear` history
event; the staged proposal remains available for another review. The
**已接受建议** filter makes accepted suggestions easy to find and revert.
