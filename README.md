# TamilLM

Tamil-first instruction tuning dataset and evaluation toolkit focused on high-quality supervised fine-tuning (SFT) data creation.

## Overview

Creating high-quality language models requires more than generating instruction-response pairs at scale. The quality of the underlying dataset plays a critical role in model behavior.

This project explores dataset curation, validation, and evaluation techniques for Tamil language models.

## Current Dataset

The repository currently contains a curated seed dataset of 50 Tamil instruction-response records.

The dataset includes:

* Spoken Tamil
* Formal Tamil
* Literary Tamil

### Task Types

* Question Answering (QA)
* Rewrite
* Summarization
* Explanation
* Classification
* Comparison
* Reasoning
* Creative Generation

### Domains

* Everyday Communication
* Food
* Travel
* Health
* Workplace
* Education
* Technical Topics
* Culture
* History
* Literature
* Current Affairs

## Dataset Quality Principles

Each record is reviewed against the following criteria:

1. Naturalness
2. Diversity
3. Correct Metadata
4. High Signal-to-Noise
5. Consistency
6. Coverage
7. Safety / Factual Reliability

The goal is to create data that sounds authentic, useful, and representative of real Tamil usage rather than machine-generated content.

## Repository Structure

```text
TamilLM/
├── data/
│   └── tamil_sft_seed.jsonl
│
├── fixtures/
│   └── bad_examples.jsonl
│
├── outputs/
│   ├── clean.jsonl
│   └── validation_report.json
│
└── validator/
    ├── validator.py
    ├── checks.py
    ├── utils.py
    └── requirements.txt
```

## Validation Philosophy

The project treats dataset quality as an evaluation problem.

Validation focuses on:

* Schema correctness
* Metadata validation
* Duplicate detection
* Language quality checks
* Consistency checks
* Coverage analysis
* Safety review

## Roadmap

* Expand dataset size
* Increase regional and dialect coverage
* Improve validation tooling
* Add evaluation benchmarks
* Build automated dataset analytics

## License

MIT License
