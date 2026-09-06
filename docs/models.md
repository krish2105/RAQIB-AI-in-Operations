# Models and free-tier providers

Every LLM, VLM and embedding call goes through `cloud/raqib_api/llm` (`get_provider(task)`) or `cloud/raqib_api/rag/embed.py` (`embed_texts`). Inference budget: **$0**. Measured on an Apple M4 Pro, 24 GB, Ollama 0.33.2, 6 September 2026.

## Local models (Ollama), verified with `ollama pull`

| Task | Tag | Size on disk | Measured (cold call, includes model load) |
|---|---|---|---|
| route (query → plan, strict JSON) | `qwen3:4b-instruct` | 2.5 GB | 2.2 s, valid JSON first attempt |
| answer, judge | `qwen3:8b` (`think=false`) | 5.2 GB | 4.8 s, valid JSON first attempt |
| caption, opinion (vision) | `qwen2.5vl:7b` | 6.0 GB | 3 blurred 768-px keyframes: 32.4 s cold (load), 5.5 s warm, 3,220 tokens in, valid JSON first attempt |
| embeddings | `bge-m3:567m` | 1.2 GB | see spike below |
| fallback text (already present) | `llama3.2:3b` | 2.0 GB | 22.6 s cold; kept as a last local resort only |

Ask end to end on the seeded store (856 chunks), warm models: route 2.3–2.9 s (`qwen3:4b-instruct`), retrieve < 0.1 s, answer 9–10 s (`qwen3:8b`, 700–1,100 prompt tokens, 6 hits capped at 700 characters each). `qwen3:4b-instruct` as the answer model was 30 percent faster but failed the citation rule on the SOP question and picked the wrong day on the Hindi footfall question, so the 8B model stays.

`bge-reranker-v2-m3` is not in the Ollama library; reranking uses `sentence-transformers` on the Mac when `RERANK_ENABLED=true` and is off on Render.

## Embedding spike (Task 24b)

Corpus: 416 chunks (319 simulated retail events, 70 daily/hourly footfall KPI chunks, 27 document chunks from three SOP/policy files). 20 queries: 8 English, 6 Hindi, 6 Arabic, ground truth derived programmatically from the seed. recall@5 = hits in the top 5 ÷ min(relevant, 5). Vector-only search; the product retriever adds SQL filters and BM25, so these numbers are the floor, not the product's recall. Raw data: `docs/results/embed_spike.json`.

| Candidate | Dim | Where it can run | Index 416 chunks | Query p95 | recall@5 all | EN / HI / AR | RSS delta |
|---|---|---|---|---|---|---|---|
| **bge-m3 via Ollama (chosen)** | 1024 | Mac, edge box | 11.6 s | 64 ms | **0.65** | 0.63 / 0.67 / 0.67 | 56 MB (client only) |
| nomic-embed-text via Ollama | 768 | Mac, edge box | 5.2 s | 31 ms | 0.46 | 0.83 / 0.17 / 0.25 | 17 MB |
| paraphrase-multilingual-MiniLM-L12 via fastembed ONNX | 384 | in-process | 39.6 s | 3.6 ms | 0.47 | 0.50 / 0.50 / 0.42 | **940 MB**, does not fit Render free (512 MB) |
| gemini-embedding-001 (free API) | 1024 | anywhere with a key | not measured | – | – | – | no `GEMINI_API_KEY` yet |

**Decision.** `EMBED_MODEL=ollama:bge-m3:567m`, `EMBED_DIM=1024`. It is the only candidate that is both multilingual and private, and it has the best overall recall. nomic is strong in English only; the ONNX model is the only one that could have run inside the Render process and it costs almost twice the instance's memory.

**Consequence for the live deployment.** Render cannot embed queries with bge-m3 (no Ollama). Indexing runs on the Mac and pushes vectors to Supabase; on Render the semantic leg is skipped and `/ask` answers from SQL filters plus BM25, which cover the time- and kind-bounded questions that dominate operations. When a Gemini key is added the spike is re-run with `gemini-embedding-001` at 1024 dimensions; if it is competitive, `EMBED_MODEL` switches to it on both the indexer and Render so the live semantic leg comes back (re-indexing 416 chunks is five API calls).

## Ask eval (Task 27), live local models

30 cases (10 intents × EN/HI/AR) over the seeded store, `cloud/evals/ask/cases.yaml`, run with `qwen3:4b-instruct` (route), `qwen3:8b` (answer and judge), `bge-m3` (vectors). Raw data: `docs/results/ask_eval.json`; CI mode (no model, hashed vectors) in `docs/results/ask_eval_ci.json`.

| Metric | Live models | CI mode | Gate |
|---|---|---|---|
| recall@5 | 1.00 | 1.00 | ≥ 0.80 |
| faithfulness (judge, retrieved records + retrieval facts) | 0.93 | – | ≥ 0.90 |
| citation coverage (deterministic, every factual sentence cited) | 1.00 | 1.00 | – |
| citation precision | 0.93 | 0.56 (template cites top hits) | – |
| language match | 1.00 | 1.00 | – |
| hallucination tripwires | 0 | 0 | 0 |
| latency mean / p95 | 18.1 s / 24.0 s | 7 ms | – |
| tokens per query | 1488 | 0 | – |
| answer paths | {'model': 27, 'template': 0, 'no_match': 3} | template 27, no_match 3 | – |

Per language, faithfulness: EN 0.95, HI 0.90, AR 0.95. The judge's remaining disagreements are two Hindi superlative sentences, one Arabic paraphrase of "floor manager", and "400 days" restated as "13 months": all cited, none invented. A first pass without retrieval facts in the judge context scored 0.87 because a single record cannot prove "longest"; the ranking field and window are now part of both the answer prompt and the judge prompt.

## Free-tier API providers

Requests per day are enforced by `Quota` (table `quota_counters`) below the published tiers so a burst never becomes a 429 storm; minute limits by a per-process bucket (`LLM_RPM`, default 10). Published numbers below are third-party summaries from September 2026 and are confirmed in each console once a key exists.

| Provider | Models | Our daily cap (config) | Published free tier |
|---|---|---|---|
| Gemini | `gemini-2.5-flash` (answer, judge, vision), `gemini-2.5-flash-lite` (route) | `GEMINI_DAILY_REQUESTS=800` | about 15 RPM, 1,500 RPD Flash; 1,000 RPD Flash-Lite; 250k TPM |
| Groq | `llama-3.1-8b-instant` (text only) | `GROQ_DAILY_REQUESTS=800` | about 30 RPM, 1,000 RPD, 12k TPM, 100k TPD for 8B-class models |
| Anthropic | `claude-sonnet-4-6` | `CLAUDE_DAILY_REQUESTS=0` (off) | paid; only when `LLM_PROVIDER=claude` and a key is set |

## Degradation ladder

| Feature | With a provider | Without any provider |
|---|---|---|
| Caption | strict JSON caption stored | `Caption(model="none")` row with the reason; indexing continues |
| Route | validated plan | regex + dateparser plan |
| Answer | cited prose in the query language | template answer over the top hits, still cited, `confidence=0.3` |
| Opinion | Opinion row | `agrees=None, observed="unavailable"` |
| Judge | faithfulness score | citation-coverage only |
