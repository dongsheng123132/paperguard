---
name: paperguard-corpus-scan
description: >-
  Screen a research institution or author for retracted / flagged publications.
  Given an institution name, an author name, or an OpenAlex ID, it resolves the
  entity on OpenAlex, pulls its works, and cross-checks every DOI against
  OpenAlex `is_retracted` plus the local Retraction Watch database. Use this when
  asked whether an institution / author / lab has retractions or academic-integrity
  issues, to vet a body of work before citing it, or to produce a "retraction
  health check" report. There is also an offline DOI mode that only consults the
  local Retraction Watch CSV (no network). Output is "suspected / on-record" with
  confidence scores — never a fraud verdict; a clean result only means no public
  retraction record was found.
---

# PaperGuard — Institution / Author Retraction Scan

## Overview

`paperguard scan` does **corpus-level** academic screening: instead of analyzing one
PDF, it takes an **institution / author / OpenAlex ID** and reports whether any of
that entity's papers are retracted or flagged. It combines three independent signals
(the philosophy is "spend the effort on cross-source verification, not on a single
signal"):

1. **OpenAlex `is_retracted`** flag on each work.
2. **Retraction Watch — DOI hit** (strong): the paper's DOI is in the Retraction
   Watch database (`cases/rw_cache.csv`).
3. **Retraction Watch — name hit** (weak): the institution/author name appears in the
   DB but the DOI did not match the corpus — flagged MEDIUM, "needs human confirmation
   it is the same entity".

It reuses PaperGuard's `Finding` / `Report` contract, so the Markdown / HTML / JSON
renderers and the Streamlit UI all work unchanged.

## Dependencies

- Python 3.11+ with this repo installed: `pip install -r requirements.txt`
  (corpus scan itself needs **no extra dependency** — pure stdlib `urllib` + `csv`).
- `cases/rw_cache.csv` (Retraction Watch export from Crossref; already in the repo).
  Refresh it with `python -m cases.fetch_retraction_watch --email you@example.com`.
- Network access to `api.openalex.org` for entity mode (offline DOI mode needs none).

## Quick Start

```bash
# Institution (writes nothing unless -o; default prints a text summary)
python -m paperguard scan --institution "Kingfa" --mailto you@example.com

# Author, save a JSON report to a file (preferred for agent consumption)
python -m paperguard scan --author "Jennifer Doudna" --mailto you@example.com -f json > out/doudna.json

# Direct OpenAlex ID (skips name resolution)
python -m paperguard scan --openalex I4210144430 -f md -o out/kingfa.md

# Offline: only cross-check a list of DOIs against the local Retraction Watch CSV
python -m paperguard scan --doi-file dois.txt          # one DOI per line, # comments ok

# Behind a proxy (e.g. CN networks reaching OpenAlex)
python -m paperguard scan --institution "Kingfa" --proxy http://127.0.0.1:7897

# Deep scan (Phase B): also download OPEN-ACCESS PDFs and run the per-paper
# detectors (statcheck/grim/image) on each. Slow; OA-only; suspected != retraction.
python -m paperguard scan --institution "Kingfa" --deep --max-pdfs 5
```

Exit code: `0` if risk < 5, `1` if any retraction/flag is found (CI-friendly).

## Workflow (for an agent)

1. **Pick the mode.** Have a name/ID → entity mode (`--institution` / `--author` /
   `--openalex`). Only have DOIs and want offline → `--doi-file`.
2. **Run with `-f json -o <file>`** (or `> file`). Parse the JSON `Report`:
   `results[0].findings[]`, each with `severity`, `title`, `detail`, `confidence`,
   `metadata.doi`, `metadata.url`, `metadata.sources`.
3. **Interpret severities** — do not invent your own verdict:
   - `CRITICAL` → DOI is in Retraction Watch (or both sources agree): **retracted**.
   - `HIGH` → OpenAlex `is_retracted` only, not in local RW: tell the user to verify
     against the journal page / Retraction Watch.
   - `MEDIUM` → name-only RW hit: **same-name collision possible**, needs confirmation.
   - `INFO` "✅ …未发现…" → clean at the public-record level.
4. **Report faithfully.** Quote the finding `detail` and the `metadata.url`. If the
   only finding is the clean-bill INFO, say "no public retraction record found" — do
   **not** upgrade that to "no problems".
5. If you need per-paper deep analysis (image duplication, stat checks), that is a
   different tool: `python -m paperguard check <pdf>` on a specific paper.

## Rate Limiting

- OpenAlex: pass `--mailto` (or set `OPENALEX_MAILTO`) to enter the **polite pool**
  (~10 req/s, free). The scan paginates works 200 at a time; `--max-works` (default
  500) caps it. Keep it modest; don't loop many institutions without spacing calls.
- Retraction Watch CSV is local — no rate limit.

## Common Mistakes

- ❌ Treating a **name hit (MEDIUM)** as confirmed. It is not — flag it for human review.
- ❌ Concluding "fraud" from a single `is_retracted` (HIGH). Retraction ≠ misconduct,
  and OpenAlex flags can lag or err. Always point to the source URL.
- ❌ Saying an entity is "clean / has no problems" when the tool only checked **public
  retraction records**. Say exactly that: no public retraction record found.
- ❌ Forgetting the proxy on a restricted network → `OpenAlexError`. Pass `--proxy`.
- ❌ Dumping a huge report to stdout. Prefer `-f json -o <file>` and read the file.
- ❌ Reading `--deep` (`corpus_deepscan`) hits as misconduct. They are single-paper
  heuristics on OA PDFs; the `wb_clone` copy-move detector **false-positives on
  materials/chemistry figures** (uniform backgrounds, luminescence photos, CIE plots).
  Report deep-scan hits as "suspected, needs human review of the original figures" —
  never as a finding against the author/institution. `--deep` only touches OA papers;
  non-OA are skipped, and "未取到 PDF" just means the OA link was a landing page.
