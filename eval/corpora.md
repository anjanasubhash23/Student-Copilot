# Eval corpora

PDFs used to check ingest quality. Put the files in `eval/data/` (they're gitignored) and add a row here.

| id | file | what it is | pages | why it's in the set |
|----|------|------------|-------|---------------------|
| dbms | `eval/data/dbms.pdf` | DBMS lecture notes | | main target course |

## What to check per corpus

- **Topics**: do the merged topics match the syllabus? Note missing topics and duplicates the merge step didn't catch.
- **Units**: would an instructor recognise the grouping and order?
- **Prereqs**: spot-check 20 edges; count wrong ones and obvious missing ones.

Pick corpora that stress different parts of the pipeline: slide decks (short pages, heavy headers/footers), textbook chapters (long pages), and scanned notes (poor text extraction).
