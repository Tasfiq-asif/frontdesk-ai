# Frontdesk

An AI voice receptionist for small businesses. Upload a business's documents — menu, price
list, policies, opening hours — then **talk to it in the browser**. It answers aloud from those
documents with citations, and can check availability, book an appointment, or escalate to a
human.

> **Status: in progress.** Design and the six-phase build plan are committed; implementation
> starts at Phase 0. This README is replaced at Phase 6 with the architecture diagram, the
> evaluation progression table, latency and cost measurements, and a demo video.

## The interesting constraint

Everything except answer generation runs locally: embeddings (`bge-small-en-v1.5`), reranking
(a MiniLM cross-encoder), speech-to-text (`faster-whisper`), voice activity detection (Silero),
and speech synthesis (Piper) — roughly 500MB of weights on a 4 vCPU / 8GB host. A hosted model
is called only where nothing cheaper will do, behind a hard daily spend cap that degrades to
local-only extractive answers rather than returning an error.

**Target: under 2.5 seconds** from end-of-speech to first audio, with the per-stage breakdown
displayed live.

## Stack

Python 3.12 · FastAPI · LangGraph · PostgreSQL + pgvector · Redis · arq · sentence-transformers
· scikit-learn · PyTorch · faster-whisper · Piper · Docker Compose · Caddy

## Documentation

- [Design spec](docs/superpowers/specs/2026-09-07-frontdesk-voice-receptionist-design.md) —
  architecture, data flows, evaluation design, risk register
- [Phase roadmap](docs/superpowers/plans/2026-09-08-frontdesk-phase-roadmap.md) — six phases,
  each an independently shippable increment
