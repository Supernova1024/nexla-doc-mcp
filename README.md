# Nexla Doc MCP

A Model Context Protocol (MCP) server that lets AI agents ask natural-language questions about PDF documents and receive grounded, source-attributed answers via retrieval-augmented generation (RAG).

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Setup Instructions](#setup-instructions)
- [Docker](#docker)
- [Configuration](#configuration)
- [MCP Tool Documentation](#mcp-tool-documentation)
- [Example Interaction Log](#example-interaction-log)
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)
- [Vibe Coding: AI-Assisted Development](#vibe-coding-ai-assisted-development)
- [License](#license)

---

## Architecture Overview

```
                              ┌──────────────────────┐
                              │     MCP Client       │
                              │  (Claude Desktop /   │
                              │   ChatGPT / Agent)   │
                              └──────────┬───────────┘
                                         │ stdio / SSE
                                         ▼
                    ┌────────────────────────────────────────────┐
                    │        FastMCP Server  (server.py)         │
                    │                                            │
                    │  ┌──────────────┐   ┌───────────────────┐  │
                    │  │ query_       │   │ list_documents    │  │
                    │  │ documents    │   │                   │  │
                    │  └──────────────┘   └───────────────────┘  │
                    │  ┌──────────────┐   ┌───────────────────┐  │
                    │  │ reingest_    │   │ get_document_     │  │
                    │  │ documents    │   │ summary           │  │
                    │  └──────────────┘   └───────────────────┘  │
                    └───────────┬──────────────────┬─────────────┘
                                │                  │
                  ┌─────────────▼───┐      ┌───────▼──────────────┐
                  │   Ingestion     │      │   Retrieval Layer    │
                  │   Pipeline      │      │   (retrieval.py)     │
                  │ (ingestion.py)  │      │                      │
                  └──┬──────────────┘      └──┬────────────────┬──┘
                     │                        │                │
               ┌─────▼──────┐         ┌──────▼──────┐  ┌──────▼──────────┐
               │ pdfplumber │         │  ChromaDB   │  │  LLM Provider  │
               │ (PDF text  │         │  (vectors + │  │  (OpenAI /     │
               │  extract)  │         │  embeddings)│  │   Anthropic)   │
               └────────────┘         └─────────────┘  └────────────────┘

               ┌─────────────────────────────────────────────────────────┐
               │                     data/ (PDFs)                        │
               │  Mounted from host filesystem or Docker volume          │
               └─────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **MCP Server** | `src/server.py` | Exposes 4 tools via the Model Context Protocol; handles request routing and auto-ingestion |
| **Config** | `src/config.py` | Centralizes all settings with environment variable overrides |
| **Ingestion Pipeline** | `src/ingestion.py` | Parses PDFs with pdfplumber, chunks text with overlap, stores embeddings in ChromaDB with hash-based deduplication |
| **Retrieval Layer** | `src/retrieval.py` | Performs semantic search over ChromaDB, builds grounded context, calls LLM for answer generation |
| **ChromaDB** | `.chroma_db/` (auto-created) | Local persistent vector store with built-in sentence-transformer embeddings |
| **LLM Provider** | OpenAI / Anthropic API | Generates grounded answers from retrieved context; switchable via `LLM_PROVIDER` env var (default: OpenAI) |

---

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- An OpenAI API key (or Anthropic API key if switching providers)

### 1. Clone and enter the project

```bash
git clone <repository-url>
cd nexla-doc-mcp
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### 5. Add PDF documents

Place any PDF files you want to query into the `data/` directory:

```bash
cp ~/Documents/my-report.pdf data/
```

### 6. Run the server

```bash
python main.py
```

The server auto-ingests all PDFs on first run, then listens for MCP connections over stdio.

### Claude Desktop Configuration

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "nexla-doc-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/nexla-doc-mcp/main.py"],
      "env": {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Restart Claude Desktop after saving. The tools will appear in the tools menu (hammer icon).

---

## Docker

### Build and run with Docker Compose

```bash
cp .env.example .env
# Edit .env with your OPENAI_API_KEY
# Place PDFs in data/

docker compose up --build
```

The server starts inside the container, auto-ingests PDFs from the mounted `data/` volume, and persists the ChromaDB index in a named Docker volume (`chroma_data`).

### Run with plain Docker

```bash
docker build -t nexla-doc-mcp .

docker run --rm -it \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY=sk-... \
  -v "$(pwd)/data:/app/data" \
  nexla-doc-mcp
```

### Claude Desktop with Docker

```json
{
  "mcpServers": {
    "nexla-doc-mcp": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "LLM_PROVIDER=openai",
        "-e", "OPENAI_API_KEY=sk-...",
        "-v", "/absolute/path/to/data:/app/data",
        "nexla-doc-mcp"
      ]
    }
  }
}
```

---

## Configuration

All settings are defined in `src/config.py` and can be overridden via environment variables.

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM backend: `openai` or `anthropic` |
| `OPENAI_API_KEY` | — | API key for OpenAI |
| `ANTHROPIC_API_KEY` | — | API key for Anthropic Claude (if using `anthropic` provider) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model identifier |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model identifier |
| `TEMPERATURE` | `0.1` | LLM temperature (lower = more deterministic) |
| `CHUNK_SIZE` | `800` | Characters per text chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `COLLECTION_NAME` | `nexla_documents` | ChromaDB collection name |
| `PROJECT_ROOT` | Auto-detected | Override the project root directory |

---

## MCP Tool Documentation

### 1. `query_documents`

Ask a natural-language question about your indexed PDF documents.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `question` | `string` | Yes | — | The natural-language question to answer |
| `top_k` | `integer` | No | `5` | Number of relevant chunks to retrieve |

**Example Input:**

```json
{
  "question": "What are the main data integration patterns described in the document?",
  "top_k": 5
}
```

**Example Output:**

```json
{
  "answer": "The document describes three main data integration patterns: batch ETL, real-time streaming, and change data capture (CDC). Batch ETL is recommended for large historical loads [Source: integration-guide.pdf, Page 12], while streaming is preferred for low-latency use cases [Source: integration-guide.pdf, Page 15]. CDC provides an efficient middle ground by capturing only changed records [Source: integration-guide.pdf, Page 18].",
  "sources": [
    {"document": "integration-guide.pdf", "page": 12, "relevance_score": 0.8432},
    {"document": "integration-guide.pdf", "page": 15, "relevance_score": 0.7891},
    {"document": "integration-guide.pdf", "page": 18, "relevance_score": 0.7654}
  ],
  "chunks_used": 3
}
```

### 2. `list_documents`

List all indexed PDF documents with metadata.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| *(none)* | — | — | — | No parameters |

**Example Output:**

```json
[
  {
    "document": "integration-guide.pdf",
    "pages": 24,
    "chunks": 47,
    "file_hash": "a1b2c3d4e5f6..."
  }
]
```

### 3. `reingest_documents`

Force re-ingestion of all PDFs in the `data/` directory (clears and rebuilds the index).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| *(none)* | — | — | — | No parameters |

**Example Output:**

```json
{
  "status": "complete",
  "documents_processed": 2,
  "documents_ingested": 2,
  "details": [
    {"document": "report.pdf", "status": "ingested", "pages": 10, "chunks": 22},
    {"document": "guide.pdf", "status": "ingested", "pages": 5, "chunks": 11}
  ]
}
```

### 4. `get_document_summary`

Get a summary and metadata preview of a specific indexed document.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `document_name` | `string` | Yes | — | Exact filename of the document (e.g., `"report.pdf"`) |

**Example Output:**

```json
{
  "document": "report.pdf",
  "total_pages": 10,
  "total_chunks": 22,
  "file_hash": "a1b2c3d4...",
  "preview": "Executive Summary\n\nThis report presents an analysis of data pipeline architectures..."
}
```

---

## Example Interaction Log

Below are real Q&A interactions captured by running the `query_documents` tool inside Docker against 5 indexed PDFs (72 total chunks):

| Document | Pages | Chunks |
|----------|-------|--------|
| `nexla-platform-overview.pdf` | 5 | 10 |
| `data-engineering-best-practices.pdf` | 5 | 14 |
| `ai-ml-pipeline-architecture.pdf` | 5 | 16 |
| `data-security-compliance-guide.pdf` | 5 | 15 |
| `api-design-best-practices.pdf` | 5 | 17 |

### Example 1: Single-Document Factual Question

**Question:** *"What is a Nexset and how does it work in the Nexla platform?"*

```json
{
  "answer": "A Nexset is a core abstraction in the Nexla platform, described as a self-describing, portable data unit that encapsulates schema, metadata, and transformation logic. It allows data engineers and analysts to treat data products as composable building blocks rather than brittle pipelines. Nexsets facilitate the creation, management, and monitoring of data flows across disparate systems without the need for writing custom ETL code [Source: nexla-platform-overview.pdf, Page 1].",
  "sources": [
    { "document": "nexla-platform-overview.pdf", "page": 1, "relevance_score": 0.5392 },
    { "document": "nexla-platform-overview.pdf", "page": 1, "relevance_score": 0.4043 },
    { "document": "data-engineering-best-practices.pdf", "page": 4, "relevance_score": 0.2509 },
    { "document": "data-security-compliance-guide.pdf", "page": 3, "relevance_score": 0.2201 },
    { "document": "nexla-platform-overview.pdf", "page": 2, "relevance_score": 0.1367 }
  ],
  "chunks_used": 5
}
```

### Example 2: Cross-Document Comparison

**Question:** *"Compare the approaches to data pipeline orchestration and workflow management described across the documents."*

```json
{
  "answer": "The documents describe several approaches to data pipeline orchestration and workflow management:\n\n1. **Apache Airflow**: It is the most popular orchestrator for batch data pipelines, used by major companies like Airbnb, Google, and PayPal. Airflow DAGs (Directed Acyclic Graphs) define task dependencies, scheduling, and retry behavior. Managed offerings include Google Cloud Composer, Amazon MWAA, and Astronomer [Source: data-engineering-best-practices.pdf, Page 4].\n\n2. **Prefect and Dagster**: These are modern alternatives to Airflow. Prefect emphasizes a Pythonic API and dynamic workflows, while Dagster introduces software-defined assets for more intuitive data lineage and dependency management [Source: data-engineering-best-practices.pdf, Page 4].\n\n3. **Event-driven architectures**: In these architectures, orchestration is often replaced by choreography, where each service reacts to events independently without a central coordinator. This pattern is compatible with tools like Kafka and cloud event buses such as AWS EventBridge and Google Eventarc, but it requires careful attention to failure handling and observability [Source: data-engineering-best-practices.pdf, Page 4].\n\n4. **Nexla's Flow Engine**: This provides built-in orchestration that can eliminate the need for a separate orchestrator in many use cases. It supports scheduling, retry logic, and exactly-once delivery semantics. Dependencies between flows are managed through Nexset lineage tracking [Source: nexla-platform-overview.pdf, Page 2].\n\nEach approach has its strengths, with Airflow being widely adopted for its robust DAG-based orchestration, Prefect and Dagster offering modern features for dynamic workflows and intuitive management, event-driven architectures providing decentralized orchestration, and Nexla's Flow Engine offering integrated orchestration with advanced features like exactly-once delivery.",
  "sources": [
    { "document": "data-engineering-best-practices.pdf", "page": 4, "relevance_score": 0.4304 },
    { "document": "data-engineering-best-practices.pdf", "page": 1, "relevance_score": 0.2434 },
    { "document": "data-engineering-best-practices.pdf", "page": 4, "relevance_score": 0.101 },
    { "document": "ai-ml-pipeline-architecture.pdf", "page": 1, "relevance_score": -0.0014 },
    { "document": "nexla-platform-overview.pdf", "page": 2, "relevance_score": -0.0403 }
  ],
  "chunks_used": 5
}
```

### Example 3: Specific Detail Extraction

**Question:** *"What companies and organizations are mentioned across all the documents?"*

```json
{
  "answer": "The companies and organizations mentioned across the documents are:\n\n1. Alation [Source: data-engineering-best-practices.pdf, Page 5]\n2. Collibra [Source: data-engineering-best-practices.pdf, Page 5]\n3. DataHub (by LinkedIn) [Source: data-engineering-best-practices.pdf, Page 5]\n4. Amundsen (by Lyft) [Source: data-engineering-best-practices.pdf, Page 5]\n5. Google [Source: data-security-compliance-guide.pdf, Page 5]\n6. Etsy [Source: data-security-compliance-guide.pdf, Page 5]\n7. PagerDuty [Source: data-security-compliance-guide.pdf, Page 5]\n8. Nexla [Source: data-security-compliance-guide.pdf, Page 2; nexla-platform-overview.pdf, Page 1]\n9. Snowflake [Source: data-security-compliance-guide.pdf, Page 2; nexla-platform-overview.pdf, Page 1]\n10. Databricks [Source: data-security-compliance-guide.pdf, Page 2]\n11. Salesforce [Source: nexla-platform-overview.pdf, Page 1]\n12. HubSpot [Source: nexla-platform-overview.pdf, Page 1]\n13. Workday [Source: nexla-platform-overview.pdf, Page 1]\n14. Palo Alto Networks [Source: nexla-platform-overview.pdf, Page 5]\n15. DoorDash [Source: nexla-platform-overview.pdf, Page 5]\n16. Postmates (now part of Uber) [Source: nexla-platform-overview.pdf, Page 5]\n\nThese companies are mentioned in various contexts related to data engineering, security compliance, and platform capabilities.",
  "sources": [
    { "document": "data-engineering-best-practices.pdf", "page": 5, "relevance_score": -0.3718 },
    { "document": "data-security-compliance-guide.pdf", "page": 5, "relevance_score": -0.397 },
    { "document": "data-security-compliance-guide.pdf", "page": 2, "relevance_score": -0.4686 },
    { "document": "nexla-platform-overview.pdf", "page": 1, "relevance_score": -0.5405 },
    { "document": "data-security-compliance-guide.pdf", "page": 2, "relevance_score": -0.545 },
    { "document": "api-design-best-practices.pdf", "page": 5, "relevance_score": -0.5524 },
    { "document": "nexla-platform-overview.pdf", "page": 5, "relevance_score": -0.5569 }
  ],
  "chunks_used": 7
}
```

---

## Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| **ChromaDB with built-in embeddings** | Zero-config vector store that works locally with no external services; built-in `all-MiniLM-L6-v2` embeddings are good enough for document QA | Embedding quality is lower than OpenAI `text-embedding-3-large`; limited to single-machine scale |
| **pdfplumber over PyMuPDF** | Better table extraction and text positioning; cleaner API for page-by-page extraction | Slower on large PDFs compared to PyMuPDF; does not handle scanned/image-only PDFs |
| **800-char chunks with 200-char overlap** | Balances retrieval precision (small enough to be specific) with context coherence (large enough to capture full paragraphs). Overlap prevents information loss at boundaries | Larger chunks would provide more context per retrieval but reduce precision; smaller chunks increase retrieval calls |
| **Sentence-boundary-aware chunking** | Avoids splitting mid-sentence which would degrade both embedding quality and answer readability | Slightly variable chunk sizes; adds complexity to the chunking logic |
| **MD5 hash-based deduplication** | Prevents redundant re-processing when the server restarts or `ingest_all()` is called again without file changes | MD5 is not collision-resistant for adversarial inputs (acceptable for local document hashing) |
| **Batch upserts (100 at a time)** | ChromaDB performs better with batched writes than individual inserts | Memory usage spikes slightly during batch assembly |
| **Grounding-enforced system prompt** | Forces the LLM to cite sources and refuse to answer from prior knowledge, ensuring answer traceability | May occasionally refuse to answer a question it could synthesize from context if the grounding prompt is too strict |
| **Dual LLM provider support** | Users can choose between Anthropic and OpenAI based on preference, cost, or availability | Two code paths to maintain; slight inconsistency in response formatting between providers |
| **LLM fallback to raw chunks** | If the LLM API call fails (rate limit, network error), the user still gets the retrieved text | Raw chunk output is less readable and lacks synthesis; user must interpret results manually |
| **stdio transport (FastMCP default)** | Standard MCP transport that Claude Desktop and other MCP clients expect | Cannot be accessed over HTTP without a transport adapter |
| **Docker with volume mounts** | Reproducible environment; PDFs mounted from host, ChromaDB persisted in a named volume so the index survives container restarts | Adds image build time; stdio-based MCP requires `docker run -i` (interactive stdin) |

---

## Vibe Coding: AI-Assisted Development

### Tools Used

- **Cursor IDE** as the primary editor, with Claude (Agent mode) for code generation and iteration.
- I kept a single long-running conversation thread so the AI had full context of earlier decisions when building later modules.

### How I Prompted — What Worked, What Didn't

**What worked:**

- *Specification-first prompting.* I wrote out the full project structure, every class name, every function signature, and the exact return types before asking the AI to generate any code. This front-loaded effort paid off — the first drafts of `config.py`, `ingestion.py`, and `retrieval.py` were all usable without major rewrites.
- *Dependency-ordered generation.* Asking for files in order (config → ingestion → retrieval → server → main) meant each file could import from the ones already built. When I tried generating everything at once in an earlier attempt, the AI produced imports that didn't match across files.
- *Naming specific failure modes.* Telling the AI "ChromaDB's `query()` throws if `n_results` is 0 — guard against that" produced a precise `min(top_k, collection.count())` check. Saying "add error handling" produced a generic `try/except` that caught everything and returned nothing useful.

**What didn't work:**

- *Vague prompts produce vague code.* Early on I said "add error handling to the retrieval layer." The AI wrapped the entire `generate_answer` method in a broad `except Exception` and returned an empty dict. I had to be specific: "if the LLM API call fails, fall back to returning the raw retrieved chunks with their source metadata."
- *The AI confidently uses wrong API signatures.* The FastMCP constructor takes `instructions=` as its keyword argument, not `description=`. The AI used `description=` and it looked perfectly reasonable — no syntax error, no runtime crash, it just silently did nothing. I caught it only because I cross-referenced the MCP SDK source. This is the most dangerous category of AI mistake: code that runs fine but doesn't do what you think.
- *Multi-file state bugs are invisible to AI.* After adding force re-ingestion (which deletes and recreates the ChromaDB collection), the retriever's collection handle became stale — it still pointed at the old, deleted collection. The AI didn't flag this because it generated each file in isolation. I only discovered it when Docker tests crashed with `NotFoundError`. The fix was adding a `_refresh_collection()` fallback, but the bug itself is the kind of cross-module state issue that AI consistently misses.

### Where AI Helped vs. Where I Stepped In

**AI was strong at:**

- *Boilerplate and SDK wiring.* The ChromaDB client setup, OpenAI/Anthropic SDK calls, FastMCP tool decorators, and Dockerfile were all correct on the first try. This is where AI saves the most time — wiring up libraries according to their docs.
- *Algorithmic suggestions.* The sentence-boundary-aware chunking logic (searching backward with `rfind` for `. ` or `\n\n` within the chunk window) was proposed by the AI and was cleaner than what I would have written from scratch.
- *Structural scaffolding.* The project layout, `pyproject.toml`, `docker-compose.yml`, and `.gitignore` were all generated correctly without iteration.

**Where I had to override or correct:**

- *The grounding prompt took three iterations.* The AI's first system prompt was too loose — it let the LLM "fill in gaps" from general knowledge, which defeats the point of RAG. I rewrote the constraints to explicitly say: answer ONLY from provided context, cite every claim, say "I don't know" if the context is insufficient.
- *Hash-based deduplication scope.* The AI's first version computed hashes per chunk, which meant re-ingesting the same PDF would create duplicate chunks with different IDs. I changed it to hash at the file level — one MD5 per PDF, skip the whole file if the hash matches.
- *Docker environment differences.* The AI didn't account for the fact that ChromaDB downloads its embedding model (~80MB) on first run inside a fresh container. I had to verify this worked and ensure the container had network access during the initial run.

### Real Challenges in Vibe Coding (Lessons Learned)

These are the patterns I hit repeatedly — not just on this project, but in general when building with AI:

1. **"It compiles, so it must be right."** AI-generated code almost always runs without syntax errors. The bugs are semantic — wrong parameter names, stale references, logic that handles the happy path but breaks on edge cases. You have to actually *run* the code against real inputs. The Docker test run caught two bugs that looked fine in the editor.

2. **Context window amnesia.** In a long conversation, the AI gradually loses track of earlier decisions. I defined `collection_name` in `config.py`, but by the time I was building `server.py`, the AI sometimes hardcoded `"documents"` instead of referencing `settings.collection_name`. Keeping the conversation focused on one file at a time helped, but you have to watch for drift.

3. **Confidence without calibration.** The AI never says "I'm not sure about this API." It will use `description=` instead of `instructions=` with complete confidence. The only defense is reading the actual library source or docs — which is what engineering judgment means.

4. **AI underestimates integration complexity.** Each module in isolation was correct. The bugs appeared at the *boundaries* — ingester deletes a collection, retriever doesn't know about it; config loads env vars, but the Docker entrypoint passes them differently. AI is great at single-file code, weaker at system-level thinking.

5. **Over-generation is real.** The AI will happily add features you didn't ask for — extra error classes, verbose logging wrappers, configuration options nobody needs. I had to actively trim generated code to keep the project focused and readable. More code is not better code.

### My View on AI Tooling in Forward-Deployed Engineering

For a forward-deployed engineering role — where you're shipping integrations on tight timelines for customers with unique requirements — AI coding tools are genuinely transformative, but not in the way people usually describe.

The value isn't "AI writes the code for me." The value is *compression of the routine parts* so you can spend your time on the parts that actually matter: understanding the customer's data model, designing for the edge cases they'll hit in production, and making architecture decisions you can defend.

On this project, AI handled maybe 70% of the raw code generation. But I spent most of my time on the other 30% — the grounding prompt wording, the deduplication strategy, the stale-handle bug, the Docker testing. That 30% is where the engineering judgment lives, and it's exactly the part AI can't do for you.

The engineers who get the most out of these tools are the ones who already know what good code looks like. If you can't spot a wrong API signature or a missing state refresh, the AI will confidently ship those bugs for you. The tool amplifies whatever level of judgment you bring to it.

---

## License

MIT — see [LICENSE](LICENSE) for details.
