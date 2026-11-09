# Eval corpora

PDFs used to check ingest quality. Put the files in `eval/data/` (they're gitignored) and add a row here.

## Measuring topic recall

1. Write the labels: `eval/data/<id>.topics.txt`, one topic per line, usually from the material's table of contents. `|` separates accepted names for one topic, `#` starts a comment. Label files are committed.

   ```
   # DBMS: from the syllabus
   Third Normal Form | 3NF
   B+ Tree
   ```

2. Ingest the PDF (`--dry-run` is enough) and score the graph JSON it writes:

   ```bash
   uv run python scripts/ingest_pdf.py eval/data/dbms.pdf --new-space "eval: dbms" --dry-run
   uv run python eval/run_eval.py data/cache/<space-id>.graph.json eval/data/dbms.topics.txt
   ```

   It prints recall, precision, the labels no topic matched, and the topics no label matched. Precision is a lower bound: read the unmatched topics, since some are real topics the labels left out.

3. Record the numbers in the table below with the model and the date.

| id | file | what it is | pages | why it's in the set |
|----|------|------------|-------|---------------------|
| dbms | `eval/data/dbms.pdf` | DBMS lecture notes | | main target course |

## Results

| corpus | model | date | recall | precision | notes |
|--------|-------|------|--------|-----------|-------|
| dbms | | | | | not run yet |

## What to check per corpus

- **Topics**: do the merged topics match the syllabus? Note missing topics and duplicates the merge step didn't catch.
- **Units**: would an instructor recognise the grouping and order?
- **Prereqs**: spot-check 20 edges; count wrong ones and obvious missing ones.

Pick corpora that stress different parts of the pipeline: slide decks (short pages, heavy headers/footers), textbook chapters (long pages), and scanned notes (poor text extraction).
