# 🌺 SPATHODEA R4 FASTLAB

> **Competition-ready local-first AI experimentation environment**
> POLYCC Agentic AI League 2026

---

## Purpose

Build and validate high-quality synthetic training datasets locally before uploading to AWS SageMaker AI for model customization. This lab operates independently of AWS Console access.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  INTERNAL MASTER FORMAT                       │
│  { id, input, output, system_prompt, metadata{...} }        │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
   ┌──────────────┐ ┌───────────┐ ┌──────────────────┐
   │ AWS Standard │ │ AWS Msgs  │ │ Future Format    │
   │ prompt/      │ │ messages  │ │ (competition     │
   │ completion   │ │ [{role,   │ │  specific)       │
   │              │ │  content}]│ │                  │
   └──────────────┘ └───────────┘ └──────────────────┘
```

**Key principle:** Internal format is decoupled from export formats. If the competition format changes, only the exporter needs updating — not the entire dataset.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Check system health
python fastlab.py doctor

# Validate existing records
python fastlab.py validate

# View dataset statistics
python fastlab.py stats

# Split into train/validation/test
python fastlab.py split

# Export to AWS format
python fastlab.py export --format prompt-completion
python fastlab.py export --format messages

# Run benchmark evaluation
python fastlab.py benchmark
```

## Project Structure

```
spathodea-r4-fastlab/
├── config/              # Pipeline configuration (YAML)
├── schemas/             # JSON schemas (internal + export formats)
├── prompts/             # LLM prompt templates
│   ├── generator/       # Data generation prompts
│   ├── reviewer/        # Quality review prompts
│   └── adversarial/     # Adversarial example prompts
├── seeds/               # Human-curated seed examples
├── generated/           # Pipeline staging area
│   ├── raw/             # Unvalidated output
│   ├── accepted/        # Passed quality gates
│   └── rejected/        # Failed (with reasons)
├── datasets/            # Production splits
│   ├── train/
│   ├── validation/
│   ├── test/
│   └── hidden_test/
├── adapters/            # LLM provider adapters
├── pipeline/            # Core processing modules
├── evaluation/          # Benchmarking & analysis
├── reports/             # Generated reports
├── logs/                # Execution logs
├── tests/               # Unit tests
├── fastlab.py           # CLI entry point
└── requirements.txt     # Python dependencies
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Current | Structure, schemas, validator, dedup, splitter, exporter, CLI |
| 2 | Planned | LLM-powered generation (OpenAI/Gemini adapters) |
| 3 | Planned | Quality scoring, semantic dedup, balancing |
| 4 | Planned | Full-scale generation (10K–100K records) |
| 5 | Planned | Competition submission & model fine-tuning |

## Security

- API keys are **never** hardcoded
- `.env` is **never** committed (in `.gitignore`)
- No credential scanning of the operating system
- Provider adapters read keys from environment variables only

## Dataset Format

The internal master record:

```json
{
  "id": "r4-a1b2c3d4-e5f6-4a7b-8c9d-e0f1a2b3c4d5",
  "input": "Macam mana nak tukar password?",
  "output": "Untuk tukar kata laluan, pergi ke Tetapan > Keselamatan > Tukar Kata Laluan.",
  "system_prompt": "Anda adalah pembantu AI dwibahasa.",
  "metadata": {
    "intent": "account_management",
    "difficulty": "easy",
    "language": "ms",
    "persona": "general_user",
    "noise_type": null,
    "generator": "manual_seed",
    "quality_score": null
  }
}
```

---

*Version: 0.1.0 | Phase 1 | 2026-08-24*
