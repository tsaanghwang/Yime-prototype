# Second-batch BCC review

The second batch means unresolved BCC strings with aggregate frequency from 1,000 through 9,999. It is not every BCC row in that numeric frequency range.

The current source and input-model snapshot contains 11,274 primary review items:

- 7,657 are dynamically reachable from shorter gated components and belong in `dynamic_composition_review`.
- 3,617 still require trusted source evidence or a structural explanation and belong in `source_reading_required`.
- A separate 3,981-row supplemental table covers accepted readings with multiple-reading, neutral-tone, proper-name, or source-rejection evidence.

Run:

```powershell
.\venv312\Scripts\python.exe tools\export_second_batch_bcc_review.py
```

Outputs are written under `.generated/second_batch_bcc_review/`:

- `second_batch_queue.tsv`: the 11,274 unresolved primary items;
- `second_batch_conflicts.tsv`: the cross-cutting conflict supplement;
- `summary.md`: lane counts and samples;
- `manifest.json`: input hashes, output hashes, counts, and safeguards.

The exporter opens both SQLite inputs read-only. It never writes assessments, pinyin, Yinyuan IDs, codes, or layout mappings. Suggestions remain review evidence and cannot approve a reading.