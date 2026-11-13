# Eval corpora

The claim "works on any notes" needs evidence across different kinds of material. The spec asks for five corpora, each stressing a different part of the pipeline:

| id | what | why it's in the set | suggested source |
|----|------|---------------------|------------------|
| `cs` | a computer science course (e.g. databases or algorithms) | technical, diagram-heavy, numerical questions | your own course notes, or MIT OpenCourseWare lecture notes |
| `bio` | a science textbook chapter set | definitions and processes, little maths | OpenStax Biology (CC BY) |
| `stats` | a statistics or physics course | formula-heavy; tests numerical validation | OpenStax Introductory Statistics or University Physics (CC BY) |
| `history` | a humanities course | few real prerequisites; tests that the graph doesn't invent them | OpenStax U.S. History (CC BY) |
| `scanned` | your own handwritten or scanned notes | OCR, bad layout, real-world mess | photos/scans of your notes as a PDF |

Put the files in `eval/data/` (they're gitignored; licences permitting, note the link here instead). Label files (`*.topics.txt`, `*.edges.csv`, `*.merges.csv`, `*.questions.csv`) are committed.

## Workflow per corpus

All commands run from the project root. Expect about an hour of labelling per corpus.

1. **Ingest** the corpus into its own space, owned by your account so you can practise on it in the web app:

   ```bash
   uv run python scripts/ingest.py eval/data/cs.pdf --new-space "eval: cs" --owner you@example.com
   ```

   It prints the space id. `uv run python eval/run_eval.py ingest --space <id>` then gives the time and LLM usage.

2. **Topics.** Write `eval/data/cs.topics.txt` from the material's table of contents: one topic per line, `|` between accepted names for one topic, `#` for comments. Score it:

   ```bash
   uv run python eval/run_eval.py topics data/cache/<id>.graph.json eval/data/cs.topics.txt
   ```

   Precision is a lower bound: read the unmatched topics, since some are real topics the table of contents left out.

3. **Generate questions** by using the space: take the diagnostic and practise for a while in the web app (questions are made the first time a topic is practised). Aim for 50.

4. **Export** the CSVs to label:

   ```bash
   uv run python eval/run_eval.py export --space <id> --corpus cs
   ```

   This writes `eval/data/cs.edges.csv` (40 random prerequisite edges), `cs.merges.csv` (up to 30 pairs the pipeline merged and 30 similar names it kept apart) and `cs.questions.csv` (up to 50 questions, rejected ones included, each with the excerpt it came from; `*` marks the options keyed as correct).

5. **Label.** Open each CSV in a spreadsheet and fill in the last column with `y` or `n`:
   - edges, `correct`: must a student understand `requires` before learning `topic`?
   - merges, `same`: are `a` and `b` the same topic?
   - questions, `correct`: is the question clear, with exactly the keyed answer correct, supported by the excerpt?

   Blank rows are skipped, so a half-labelled file still scores.

6. **Score** and record the numbers in the table below:

   ```bash
   uv run python eval/run_eval.py edges eval/data/cs.edges.csv
   uv run python eval/run_eval.py merges eval/data/cs.merges.csv
   uv run python eval/run_eval.py questions eval/data/cs.questions.csv
   ```

## Results

Targets from the spec: topic recall/precision ≥ 0.80/0.80, prerequisite precision ≥ 0.80, merge precision/recall ≥ 0.90/0.80, kept questions correct ≥ 90%, ingestion of 100 pages < 5 min and < $0.20.

| corpus | model | date | topic recall / precision | prereq precision | merge precision / recall | questions correct | ingest per 100 pages |
|--------|-------|------|------|------|------|------|------|
| cs | | | | | | | |
| bio | | | | | | | |
| stats | | | | | | | |
| history | | | | | | | |
| scanned | | | | | | | |

Simulated-learner results (diagnostic accuracy, mastery AUC) don't need a corpus; they're in the README's Evaluation section and checked in CI.

## What else to look at per corpus

- **Units**: would an instructor recognise the grouping and order? Note topics that ended up in "Other".
- **Missing prerequisites**: the edge sample measures precision only; note obvious prerequisites the map lacks.
- **History**: count edges that are chronology rather than dependency ("comes earlier" isn't "needed first").
- **Scanned**: compare a few OCR'd pages with the originals.
