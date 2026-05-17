# PolarityIQ Stage 1 Local RAG

Local-first, evidence-bound RAG repository for the PolarityIQ Stage 1 Differentiator submission.

## Submission Map

Open these files first during review:

- `SUBMISSION_COVER.md` - packet index, demo map, and known limits.
- `EFFORT_AND_AI_DISCLOSURE.md` - hours breakdown and AI-vs-human disclosure.
- `fo_dataset_pipeline/reports/methodology_summary.md` - dataset methodology and honest limitations.
- `fo_dataset_pipeline/reports/validation_chains.md` - source-to-field validation chains with uncertainty.
- `reports/eval_report.md` - 45-question adversarial RAG evaluation, including known misses.
- `DEPLOYMENT_OR_RECORDING_NOTES.md` - live-demo or screen-recording checklist.

## What This Builds

- Locked corpus: `data/raw/family_offices_validated.json`, copied from `fo_dataset_pipeline/data/processed/family_offices_validated.json`.
- Dense retrieval: local persistent ChromaDB index in `data/index/chroma/`.
- Lexical retrieval: separate `rank_bm25` index in `data/index/bm25/`.
- Answering: deterministic extractive mode by default; optional local Ollama rewrite mode only rewrites selected evidence.
- UI: Streamlit app with query input, mode toggle, final answer, missing data, caveats, citations, and retrieved evidence.
- Evaluation: 20-question golden set plus local metrics in `reports/eval_report.md`.

No paid API keys, hosted vector databases, SaaS tracing, or billing-dependent services are required.
The dependency audit command used here is `pip-audit -r requirements.txt`; some pip installations do not expose a `pip audit` subcommand.

## Setup: Windows PowerShell

```powershell
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

python scripts\build_all.py
pytest tests\ -v --cov=. --cov-report=term-missing --cov-fail-under=80
ruff check .
pip-audit -r requirements.txt
python -m src.eval.run_eval --eval data\processed\golden_eval.jsonl --out reports\eval_report.md
streamlit run src\ui\app.py
```

## Setup: Linux/macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

python scripts/build_all.py
pytest tests/ -v --cov=. --cov-report=term-missing --cov-fail-under=80
ruff check .
pip-audit -r requirements.txt
python -m src.eval.run_eval --eval data/processed/golden_eval.jsonl --out reports/eval_report.md
streamlit run src/ui/app.py
```

## Stack Choice

ChromaDB gives a simple local persistent dense index. BM25 is kept separate so exact names, CRD numbers, contact fields, and field labels remain inspectable. The default embedding target is `BAAI/bge-small-en-v1.5`, with `sentence-transformers/all-MiniLM-L6-v2` as fallback and `BAAI/bge-m3` documented as a higher-end path. If local model loading fails during a build, the code falls back to a deterministic local hashing embedder so the repository remains runnable without paid credentials.

## Chunking Strategy

Each accepted record becomes:

- `record_profile`: discovery-level profile, type, location, description, sectors, source notes.
- `contact_policy`: exact contact/AUM policy and missing-data handling.
- `regulatory`: SEC/IAPD fields, CRD, status, confidence, regulatory URLs.
- `recent_activity`: only when recent-activity evidence exists.
- `field_evidence`: exact-value chunks for contact, address, website, principal, LinkedIn, and AUM fields when present.

Every chunk carries rich metadata: record ID, chunk type, office name/type, geography, source URLs, field name/value, confidence, validation status, SEC fields, recent activity fields, audit flags, uncertainty notes, validation period, and safe answer policy.

## Retrieval Approach

The query path is:

1. classify intent
2. parse metadata filters
3. query local Chroma dense index
4. query local BM25 index
5. fuse with reciprocal rank fusion
6. apply parsed filters and record diversity caps
7. optionally rerank with a local cross-encoder
8. group evidence by record
9. run deterministic sufficiency/abstention logic
10. answer or abstain

## Abstention Logic

The system never invents principal email, phone, LinkedIn, AUM, SEC registration, or recent activity. Blank sensitive fields are rendered as `not evidenced in the locked dataset`. SEC-negative answers are phrased as dataset snapshot claims, not legal conclusions. Recent-activity answers are explicitly snapshot-bound and do not claim live recency.

## What Works

- Exact entity lookup and field lookup.
- Regulatory lookup with SEC/CRD citations.
- Conservative contact and AUM missing-data answers.
- Recent-activity lookup when evidence exists.
- Filtered listings over parsed metadata.
- Comparison across selected records.
- UI-level visibility into retrieval ranks, metadata, source URLs, and uncertainty notes.

## What Does Not

- No live web research or enrichment.
- No paid LLM or hosted embedding API.
- No claim that the dataset is current beyond its validation period.
- No inference of missing private or principal contact details.
- Optional local LLM mode is not an authority; it is only a rewrite layer.
- No claim that the eval covers true aggregate reasoning, typo tolerance, SMTP deliverability, or Form ADV PDF parsing.

## Next Improvements

- Add a stronger local reranker if hardware allows.
- Add richer alias handling for entity names.
- Add per-field evidence provenance scoring beyond the current confidence labels.
- Add a browser-recorded demo script with the seven built-in queries.
- Add a fully offline model-cache setup guide for air-gapped assessment environments.

## Demo Queries

The UI and `scripts/run_demo.py` include seven built-in queries:

1. What type of family office is Cat Trail Capital and where is it based?
2. Show me the evidence for Ohana Advisors' SEC registration.
3. Which SEC-registered family offices in California are in the dataset?
4. What recent activity is recorded for Pathstone?
5. Do we have a direct phone number for Ralph Family Office?
6. Compare Cat Trail Capital and Ohana Advisors on type, geography, SEC status, and contact availability.
7. What is the AUM of Cat Trail Capital?
