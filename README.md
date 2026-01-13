# RSS Digest Generator

An automated RSS digest generator that fetches articles from FreshRSS, categorizes and summarizes them using AI, and sends the digest via Telegram.

## Directory Structure

```
.
├── logs/                   # Log file directory
├── scripts/                # Utility scripts
│   ├── run.sh              # Main execution script
│   └── setup.sh            # Installation and setup script
├── src/                    # Source code
│   ├── config/             # Configuration files
│   │   ├── config.py       # Main configuration
│   │   ├── .env            # Environment variables (gitignored)
│   │   └── .env.example    # Environment variable template
│   ├── services/           # Business logic
│   │   └── digest_service.py   # Digest generation service
│   ├── utils/              # Helper utilities
│   │   ├── ai_utils.py     # AI processing utility
│   │   ├── db_utils.py     # Database interaction utility
│   │   ├── telegram_utils.py   # Telegram notification utility
│   │   ├── system_prompt.md  # Stage-2 (global digest) system prompt
│   │   └── system_prompt_stage1.md  # Stage-1 (per-article) system prompt
│   ├── __init__.py         # Package initializer
│   └── main.py             # Main application entry point
├── pyproject.toml          # Python dependencies (managed by uv)
├── README.md               # This file
└── crontab.example         # Example crontab configuration
```

## Features

- Reads recent RSS entries for a specified user from a FreshRSS database.
- Two-stage pipeline: per-article summaries (parallel) then a global categorized digest.
- Uses an AI model (e.g., OpenAI-compatible endpoint) to process and summarize content.
- Categorizes content by topics (AI, Tech, World News, etc.).
- Generates a digest in bullet-point format.
- Sends the digest via a Telegram Bot.
- Supports scheduled execution via cron jobs.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A FreshRSS instance with database access.
- An OpenAI compatible AI API key.
- A Telegram Bot token and chat ID.

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://your-repository-url/rss-digest.git
    cd rss-digest
    ```

2.  **Run the setup script:**
    This script will use uv to install the required dependencies.
    ```bash
    ./scripts/setup.sh
    ```

3.  **Configure environment variables:**
    Copy the example `.env` file. **Important:** The `.env` file must be located in the `src/config/` directory.
    ```bash
    cp src/config/.env.example src/config/.env
    ```

4.  **Edit the configuration file:**
    Fill in your details in `src/config/.env`.
    ```bash
    nano src/config/.env
    ```
    You need to set:
    - `FRESHRSS_DB_PATH`: The absolute path to your FreshRSS SQLite database file.
    - `USERNAME`: The FreshRSS user for whom to fetch articles.
    - `AI_API_KEY`: Your AI provider API key.
    - `GEMINI_STAGE2_MODEL_ID`: Model for the stage-2 global digest (fallback to `GEMINI_MODEL_ID`).
    - `GEMINI_STAGE1_MODEL_ID`: (Optional) Model for per-article summaries; defaults to the stage-2 model when omitted.
    - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
    - `TELEGRAM_CHAT_ID`: The destination chat ID for the digest.

## Usage

### Using the Run Script

The easiest way to run the generator is by using the provided script.

```bash
./scripts/run.sh [hours_back]
```

- **`hours_back`**: (Optional) The number of hours to look back for new articles. Defaults to the value in your configuration (8 hours).

Example:
```bash
# Generate a digest for articles from the last 12 hours
./scripts/run.sh 12
```

### Direct Execution with Python

You can also run the main script directly with more granular control using uv.

```bash
uv run python -m src.main [options]
```

**Options:**

- `--hours <number>`: Specify the look-back period in hours.
- `--no-send`: Generate the digest but do not send it via Telegram.
- `--save`: Save the generated digest to a `.txt` file in the project root.
- `--debug`: Enable detailed debug logging.

Example:
```bash
uv run python -m src.main --hours 12 --save --debug
```

## Automation with Cron

You can automate the digest generation using a cron job.

1.  Open your crontab for editing:
    ```bash
    crontab -e
    ```

2.  Add a new line to schedule the script. Refer to `crontab.example` for more samples.

    ```crontab
    # Run every day at 7 AM and 7 PM, generating a digest for the last 12 hours.
    0 7,19 * * * cd /path/to/your/rss-digest && ./scripts/run.sh 12
    ```
    **Important:** Make sure to use the absolute path to your project directory.

## Advanced Configuration

You can customize the application's behavior by editing `src/config/config.py`:

- **Stage-2 Model:** Change `GEMINI_STAGE2_MODEL_ID` (or legacy `GEMINI_MODEL_ID`) to use a different provider model for the final digest.
- **Stage-1 Model:** Optionally set `GEMINI_STAGE1_MODEL_ID` to override the per-article summarization model.
- **API Provider:** Modify `AI_BASE_URL` to use a different API endpoint.
- **Categorization:** Adjust the keywords and logic for categorization within `digest_service.py`.
- **Output Language:** Modify the `system_prompt.md` to change the output language or format.
- **Stage-1 Concurrency:** Control per-article parallelism via `STAGE1_MAX_WORKERS` (default `20`).

## Troubleshooting

If you encounter issues, please check the following:
- Ensure all variables in `src/config/.env` are correctly set.
- Verify that the path to your FreshRSS database is correct and the file is readable.
- Check the log files in the `logs/` directory for detailed error messages (`rss-digest.log` and `api_debug.log`).

## Notes

- The application always uses a two-stage pipeline: per-article summaries (parallel) then a global categorized digest.
- For dry runs without sending to Telegram, use `--no-send` with `src.main`, and optionally `--save` to persist output.
