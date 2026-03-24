# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (installs dependencies via uv)
./scripts/setup.sh

# Run digest generation
./scripts/run.sh [hours_back]          # Default: 48 hours
uv run python -m src.main --hours 12   # Direct execution

# CLI options
uv run python -m src.main --hours 12 --no-send --save --debug

# Run tests
uv run pytest -q
```

## Architecture

RSS Digest Generator is a two-stage AI pipeline that:
1. Fetches unread RSS entries from a FreshRSS SQLite database
2. **Stage 1**: Summarizes each article individually (parallel, via thread pool)
3. **Stage 2**: Generates a categorized digest from Stage 1 summaries
4. Sends the final digest via Telegram

### Key Components

- **`src/main.py`**: CLI entry point with argparse
- **`src/services/digest_service.py`**: Orchestrates the pipeline (`run_digest_process` → `generate_digest` → `send_digest`)
- **`src/utils/ai_utils.py`**: `AIProcessor` class handles both stages; Stage 1 uses `STAGE1_MAX_WORKERS` for parallelism; URL REF ID mapping replaces raw URLs in Stage 2
- **`src/utils/db_utils.py`**: SQLite queries against FreshRSS database
- **`src/utils/telegram_utils.py`**: `TelegramSender` sends via Telegraph pages with Telegram link delivery
- **`src/utils/system_prompt.md`**: Stage 2 prompt (global digest)
- **`src/utils/system_prompt_stage1.md`**: Stage 1 prompt (per-article summary)

### Data Flow

```
FreshRSS DB → db_utils.get_recent_entries() → entries[]
    ↓
AIProcessor.summarize_articles() [Stage 1, parallel] → (merged_summaries, url_map)
    ↓
AIProcessor.finalize_digest_from_article_summaries() [Stage 2, REF→URL post-processing]
    ↓
TelegramSender.send_message() → Telegraph page → Telegram link
```

### Deduplication

Processed entry IDs are stored in `logs/processed_entry_ids.json` as `{id, ts}` objects. IDs are pruned based on a dynamic window: `max(48h, HOURS_BACK * 2)`. On pipeline failure, IDs are not updated. Stage 1 articles returning `[SKIP]` (empty/ad content) are filtered before Stage 2.

### Error Handling

`DigestGenerationError` is raised on pipeline failure. `run_digest_process` retries up to 2 times, catching both expected and unexpected exceptions.

## Configuration

Environment variables in `src/config/.env`:
- `FRESHRSS_DB_PATH`: Path to FreshRSS SQLite database
- `AI_API_KEY`: OpenAI-compatible API key
- `GEMINI_STAGE2_MODEL_ID`: Model for Stage 2 (global digest)
- `GEMINI_STAGE1_MODEL_ID`: Optional, defaults to Stage 2 model
- `STAGE1_MAX_WORKERS`: Parallelism for Stage 1 (default: 20)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: Telegram delivery

## Code Style

- Python 3.12+, 4-space indentation, UTF-8
- Absolute imports: `from src.utils import ...`
- Use `logging` module (no print for operational messages)
- Tests go in `tests/` mirroring module paths
