# Frontdesk — AI Voice Receptionist

**Design spec** · 2026-09-07 · status: approved, not yet implemented

---

## 1. Purpose

Frontdesk is an AI voice receptionist for small businesses. A business uploads its own
documents — menu, price list, policies, opening hours, FAQ. A customer opens the page,
clicks the microphone, and **talks to it**. It answers out loud from those documents,
with citations, and can check availability, book an appointment, or escalate to a human.

### Why this project exists

This is a portfolio project built to close a specific gap. The author's shipped work is
almost entirely TypeScript/Next.js; the roles being targeted are **Python-first** AI
engineering roles asking for LLMs, RAG, embeddings, vector databases, LangChain/LangGraph,
voice AI, document processing, classification, and ML fundamentals (NumPy, Pandas,
scikit-learn, ANNs).

Every design decision below is made twice: once for the product, once for whether it
produces evidence a hiring manager can verify. Where those conflict, the spec says so.

### Success criteria

The project is done when all of these are true:

1. A stranger can open a public URL, click once, speak, and hear a correct spoken answer
   drawn from a seeded business's documents — with no signup.
2. Median time from end-of-speech to first audio byte is **under 2.5 seconds**, measured
   and displayed live in the UI as a per-stage breakdown.
3. `make eval` runs a golden-set evaluation and emits committed metrics; the README
   carries a progression table showing what each change moved.
4. The intent classifier's training, comparison and selection are reproducible from a
   committed dataset and script.
5. The whole system runs from `docker compose up` on a 4 vCPU / 8GB VPS within the
   author's existing hosting, with hosted-LLM spend bounded by a hard daily cap.

---

## 2. Constraints

| Constraint | Value | Consequence |
|---|---|---|
| Time | ~70 hours across ~12 working days | One product, ruthless cuts. No stretch goals. |
| Hosted LLM budget | $5 of OpenRouter credit, total | Embeddings, STT, TTS and reranking all run locally. LLM is called only where nothing cheaper will do. |
| Hardware | 2-4 vCPU, 8GB RAM VPS | Model weights must stay under ~500MB. Voice concurrency must be capped. |
| Language | English only | Bangla is listed as future work, not built. |

The budget constraint is treated as a **feature**. "I self-hosted inference so marginal
cost per request is zero, and spent the hosted-model budget only on generation" is a
stronger interview answer than "I called OpenAI", and it forces genuine engineering
decisions about caching, routing and degradation.

---

## 3. Scope

### In scope

- Document ingestion: PDF, DOCX, TXT, and single-URL scrape
- Cleaning, chunking, deduplication, local embedding, storage in pgvector
- Hybrid retrieval: vector similarity + Postgres full-text, fused by reciprocal rank fusion
  (k=60), then cross-encoder rerank of the top 20
- Answers carrying citations back to source chunks
- A LangGraph agent with tools: `search_docs`, `check_availability`, `book_appointment`,
  `escalate_to_human`
- Full duplex-ish voice loop: browser mic → VAD → Whisper → agent → Piper → streamed audio,
  with barge-in (the user can interrupt mid-sentence)
- Text chat over the same graph — fallback, accessibility, and the path used when voice
  capacity is exhausted
- Redis doing four distinct jobs: embedding cache, pre-synthesized TTS phrase cache,
  semantic LLM response cache, and rate limiting
- A trained intent classifier routing cheap turns away from the LLM entirely
- An evaluation harness with a golden question set and tracked, committed metrics
- Docker Compose deployment behind Caddy, with CI running lint, types and tests

### Explicitly out of scope

Named here because stating one's own scope boundaries is part of the artifact.

| Cut | Reason |
|---|---|
| Real telephony (Twilio) | Browser mic proves the same pipeline. Telephony is integration work, not AI work, and would eat two days. Listed as next step. |
| Multi-tenant auth and billing | One admin login and seeded demo businesses are enough to demo. |
| Fine-tuning any LLM | No budget, no data, and no benefit over retrieval here. |
| Any language but English | Whisper multilingual and a second Piper voice would double the eval surface. |
| OpenAI Realtime API | It would make the voice loop trivial and cost more than the entire budget. Building the loop is the part that demonstrates skill. |
| Streaming partial transcripts | Endpointed utterances are enough to hit the latency target. Revisit only if the target is missed. |

---

## 4. Architecture

Five containers, one Compose file.

| Service | Role |
|---|---|
| `api` | FastAPI — REST, WebSocket voice channel, serves built frontend |
| `worker` | arq worker — document ingestion jobs |
| `postgres` | Postgres 16 with pgvector — documents, chunks, bookings, turn metrics |
| `redis` | Cache, rate limiting, arq queue, concurrency semaphore, budget counter |
| `caddy` | TLS termination and reverse proxy |

arq is chosen over Celery: it is async-native, Redis-only, and roughly a tenth the
configuration surface. Ingestion is the only background work in the system, so Celery's
extra capability buys nothing.

### Local models

| Purpose | Model | Approx size |
|---|---|---|
| Embeddings | `BAAI/bge-small-en-v1.5` (384-dim) | 130 MB |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` | 90 MB |
| STT | `faster-whisper base.en`, int8 | 75 MB |
| VAD | Silero VAD (ONNX) | 2 MB |
| TTS | Piper, `en_US-lessac-medium` | 65 MB |

Hosted, via OpenRouter: answer generation and the evaluation judge only. Model choice is
configuration, not code — the OpenAI-compatible client is pointed at OpenRouter's endpoint.

### Frontend

Vite + Tailwind, single page, vanilla TypeScript. Deliberately small. The Python is the
subject of this project and the frontend must not consume its time — but it should look
good, because the author can do that cheaply and a shabby demo undersells the engineering.

An `AudioWorklet` captures 16kHz mono PCM and streams binary frames over the WebSocket;
playback runs through a Web Audio queue that can be flushed instantly for barge-in.

### Runtime environment

Python 3.12 pinned in `.python-version` and the Dockerfile, so the laptop, CI and the VPS all
resolve to the same interpreter. This is a conservative preference rather than a requirement:
checked on 2026-09-08, the whole ML stack publishes cp314 wheels (`tokenizers` and
`safetensors` ship abi3), so 3.14 would work too. **Corrected 2026-09-08** — this section
previously asserted that 3.14 lacked wheels, which was never tested and is false.

---

## 5. Data flow

### Ingestion (asynchronous)

Upload → persist file → sniff type (never trust the extension) → extract text
(`pypdf` / `python-docx` / `trafilatura`) → normalize whitespace → chunk recursively at
~800 tokens with 120 overlap, respecting heading boundaries → drop duplicates by content
hash → embed in batches → insert with both a `vector(384)` column and a `tsvector` column
→ build the HNSW index. Job status is a row the UI polls.

### A conversation turn

1. Browser streams PCM frames over the WebSocket.
2. Silero VAD marks speech start and end. On end-of-utterance, `faster-whisper` transcribes.
3. The transcript enters the LangGraph state machine:
   - **`classify`** — the trained intent classifier runs on the utterance embedding.
   - **Fast path** — `greeting`, `goodbye`, `smalltalk` above the confidence threshold get
     a templated reply straight from the TTS cache. No LLM call, no retrieval, sub-300ms.
   - **`retrieve`** — hybrid search plus rerank, for everything else.
   - **`guard`** — if the top reranked score falls below threshold, the agent says it does
     not have that information and offers a human. It does not guess.
   - **`answer`** or **`tool`** — generation with cited context, or a tool invocation.
4. Generated tokens stream out, are cut at sentence boundaries, and each sentence is
   synthesized by Piper and streamed back as it is ready.
5. **Barge-in** — if VAD detects speech during playback, the server cancels the pending TTS
   task and instructs the client to flush its audio queue.
6. Per-stage timings, token counts and cost are written to a `turns` table.

Steps 4 and 5 are the hardest engineering in the project and should be built with the
expectation that they take a full day each.

---

## 6. The machine learning component

The intent classifier is the ML evidence, and it is real: it removes both latency and cost
from the hot path. It is not decoration bolted on to satisfy a job description.

**Labels** (9): `greeting`, `hours`, `location`, `pricing`, `booking`, `doc_question`,
`smalltalk`, `goodbye`, `escalate`.

**Dataset**: ~1,200 utterances. Seeded by LLM generation, then **hand-corrected** —
the correction pass is what makes the dataset honest, and mislabeled generated data is
the most likely way this component quietly fails. Committed as CSV. Stratified 70/15/15.

**Models compared**, all in a committed notebook plus a reproducible `ml/train.py`:

1. TF-IDF + Logistic Regression (baseline)
2. TF-IDF + LinearSVC
3. `bge-small` embeddings + Logistic Regression
4. `bge-small` embeddings + a small PyTorch MLP — 384 → 128 → 64 → 9, ReLU, dropout 0.3,
   AdamW, early stopping on validation macro-F1

**Selection rule**: highest macro-F1 *subject to* p95 inference latency under 15ms. Stating
the constraint up front prevents choosing a model that wins on paper and loses in the
pipeline.

**Reporting**: accuracy, macro-F1, per-class precision and recall, confusion matrix, and a
written error analysis of the confusion matrix's worst cell.

**Threshold tuning**: the confidence threshold is fitted on the validation split so that
low-confidence turns fall through to the full LLM path rather than being answered from a
template. Getting a greeting wrong is cheap; answering a pricing question from a smalltalk
template is not. The threshold is chosen asymmetrically to reflect that.

NumPy and Pandas are used for dataset construction, class-balance analysis, error analysis
and metric aggregation in the eval harness — not as an ornament.

---

## 7. Evaluation

This is the part most portfolio RAG projects lack, and the fastest way to read as an
engineer rather than someone who followed a tutorial.

`eval/golden.yaml` holds ~60 questions per seeded corpus, each with expected answer facts
and expected source chunk ids. Critically, it includes questions **deliberately outside the
documents**, which the system must refuse.

| Family | Metrics |
|---|---|
| Retrieval | hit@1, hit@3, hit@5, MRR |
| Answer | LLM-judged faithfulness and relevance; regex fact checks where a fact is exact |
| Safety | refusal accuracy on out-of-corpus questions |
| Ops | p50/p95 latency per pipeline stage; cost per conversation |

`make eval` writes `eval/results/YYYY-MM-DD-HHMM.json` and a markdown diff against the
previous run. Results are committed.

**The retrieval half of this harness is built on day 3, before the agent exists.** Building
evaluation after the system is what produces evaluations that cannot fail — the harness
must be able to report a bad number before there is any incentive for it to report a good one.

The README carries the resulting progression table, including changes that did not work and
were removed. Recording a reverted experiment is worth more than recording a successful one.

---

## 8. Failure handling, cost control and abuse

- **Budget guard** — a hard daily USD cap held in Redis. On exceeding it the app does not
  error; it **degrades to local-only mode**, answering extractively from the top reranked
  chunk. The demo stays alive on a dead budget.
- **Rate limits** — per IP: 3 voice sessions/hour, 30 text turns/hour.
- **Concurrency** — a Redis semaphore capping voice sessions at 2. Overflow is routed to
  text mode with an honest message. This is a real constraint of 4 vCPU, not a shortcut.
- **Uploads** — 10MB and 50 pages maximum; type sniffed, not trusted.
- **Prompt injection** — uploaded documents are untrusted input. The system prompt states
  that retrieved content is data and never instruction; tool arguments are validated against
  pydantic schemas; `book_appointment` requires an explicit confirmation turn before any
  side effect.
- **External calls** — every one wrapped in timeout, retry with jitter, and a circuit
  breaker. LLM failure falls back to the extractive answer rather than an error.
- **Logging** — structlog, with a session id and turn id on every line.

---

## 9. Testing

- **Unit**: chunker boundaries, hybrid score fusion, VAD segmentation, the sentence chunker
  feeding TTS, budget guard arithmetic, rate limiter.
- **Integration**: the ingestion pipeline against a fixture PDF using the real embedding
  model; a full graph run against a stubbed LLM.
- **Contract**: every LangGraph node's input and output is a pydantic model, and those
  models are tested.
- Retrieval mathematics is asserted against real numbers, never mocked. A mocked retrieval
  test passes whether or not retrieval works.
- **CI**: ruff, mypy (strict on `app/`), pytest, and a Docker build, on every push.

---

## 10. Build sequence

Twelve working days. Days 11 and 12 are the compressible buffer.

| Day | Deliverable |
|---|---|
| 1 | Repo skeleton, Compose, Postgres + pgvector + Redis up, FastAPI health check, CI green |
| 2 | Ingestion pipeline: extract, chunk, embed, store. Both fixture corpora loaded. |
| 3 | Hybrid retrieval + reranker. **Retrieval eval harness, before the agent exists.** |
| 4 | LangGraph agent, text chat end to end, citations, guard node |
| 5 | Intent dataset, `train.py`, four-model comparison, fast path wired in |
| 6 | STT and VAD. Push-to-talk voice working end to end. |
| 7 | Piper TTS and streamed playback. Full voice loop closed. |
| 8 | Barge-in, per-stage latency instrumentation, TTS and LLM caching |
| 9 | Tools: availability, booking, escalation. Admin upload UI. |
| 10 | Full eval run, tuning iterations, results written up |
| 11 | Deploy to VPS, Caddy TLS, rate limits, budget guard, load sanity check |
| 12 | README, architecture diagram, demo video, polish |

### Known risks

| Risk | Mitigation |
|---|---|
| Voice latency misses 2.5s on 4 vCPU | Day 6 measures STT cold and warm before day 7 depends on it. Fallback: smaller Whisper (`tiny.en`), and push-to-talk instead of continuous VAD. |
| Barge-in proves fiddly | It is a day-8 item, after the loop already works. It can be cut without breaking the demo. |
| Generated intent data is mislabeled | The hand-correction pass is mandatory, not optional. Error analysis on day 5 is where this surfaces. |
| $5 exhausted before day 12 | Budget guard exists from day 4, not day 11. Eval judging runs on the cheapest adequate model. |

---

## 11. What this proves, mapped to the target role

| Requirement | Evidence |
|---|---|
| Strong Python and OOP | The whole codebase; typed pydantic boundaries, mypy strict |
| ML, ANNs, AI concepts | Four-model comparison including a PyTorch MLP, with selection under a latency constraint |
| NumPy, Pandas, scikit-learn | Dataset construction, error analysis, metric aggregation |
| LLMs, generative AI, embeddings, vector DBs | Local embeddings into pgvector, hybrid retrieval, reranking |
| Third-party AI APIs | OpenRouter, model-agnostic by configuration |
| Chatbots, RAG, document processing, summarization, classification | All four, in one coherent product |
| LangChain / LangGraph | The agent is a LangGraph state machine with typed nodes and real tools |
| AI pipelines end to end | Ingestion through deployment |
| Databases, APIs, caching | Postgres, FastAPI, Redis in four distinct roles |
| Voice AI | The differentiator: a hand-built loop, not a managed realtime API |
| Prompt engineering, multi-agent | Guarded generation, injection-resistant prompting, routed graph |
