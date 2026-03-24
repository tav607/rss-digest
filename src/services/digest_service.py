#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Any
import datetime
import json

# 导入项目模块
from src.config import (
    FRESHRSS_DB_PATH,
    AI_API_KEY,
    AI_STAGE1_MODEL,
    AI_STAGE2_MODEL,
    AI_BASE_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    HOURS_BACK,
    PROJECT_ROOT,
)
from src.utils import (
    get_recent_entries,
    AIProcessor,
    TelegramSender
)

# 获取记录器
logger = logging.getLogger(__name__)

# Define the path for storing processed entry IDs
PROCESSED_IDS_FILE = PROJECT_ROOT / "logs" / "processed_entry_ids.json"
# Define the path for storing digest history (for deduplication)
DIGEST_HISTORY_FILE = PROJECT_ROOT / "logs" / "digest_history.json"
# Number of recent digests to keep for deduplication
DIGEST_HISTORY_LIMIT = 10


class DigestGenerationError(Exception):
    """Raised when digest generation fails."""
    pass


def _load_digest_history() -> list[str]:
    """Load recent digest history for deduplication."""
    try:
        if DIGEST_HISTORY_FILE.exists():
            with open(DIGEST_HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        logger.error(f"Failed to load digest history: {e}")
    return []


def _save_digest_to_history(digest: str):
    """Save digest to history, keeping only the most recent N entries."""
    try:
        history = _load_digest_history()
        # Add new digest to the beginning
        history.insert(0, digest)
        # Keep only the most recent N entries
        history = history[:DIGEST_HISTORY_LIMIT]
        # Write back to file
        with open(DIGEST_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved digest to history. Total history entries: {len(history)}")
    except Exception as e:
        logger.error(f"Failed to save digest to history: {e}")

def generate_digest(entries: List[Dict[Any, Any]]) -> str:
    """
    Generate a digest from the RSS entries

    Args:
        entries: List of entry dictionaries

    Returns:
        Generated digest text including timestamp header

    Raises:
        DigestGenerationError: If digest generation fails at any stage
    """
    logger.info(
        f"Generating digest from {len(entries)} entries using two-stage pipeline"
    )

    # Initialize AI processor
    ai_processor = AIProcessor(
        api_key=AI_API_KEY,
        stage2_model=AI_STAGE2_MODEL,
        base_url=AI_BASE_URL,
        stage1_model=AI_STAGE1_MODEL,
    )
    # Stage 1: summarize each article individually
    logger.info("Stage1: Summarizing each article individually...")
    merged_summaries, url_map = ai_processor.summarize_articles(entries)
    if not merged_summaries or not merged_summaries.strip():
        raise DigestGenerationError("Stage1 produced no summaries.")

    # Load digest history for deduplication
    digest_history = _load_digest_history()
    logger.info(f"Loaded {len(digest_history)} historical digests for deduplication")

    # Stage 2: finalize digest from stage1 abstracts
    logger.info("Stage2: Finalizing digest from per-article summaries...")
    ai_generated_digest = ai_processor.finalize_digest_from_article_summaries(
        merged_summaries,
        digest_history=digest_history,
        url_map=url_map,
    )
    if not ai_generated_digest or not ai_generated_digest.strip():
        raise DigestGenerationError("Stage2 returned empty content.")

    # Format the current datetime
    formatted_datetime = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")

    # Create the title and full digest
    title = f"# RSS 新闻摘要 - {formatted_datetime}"
    full_digest_with_title = f"{title}\n\n{ai_generated_digest}"

    logger.info(f"Digest generated successfully, final length: {len(full_digest_with_title)} characters.")
    logger.debug(f"Final digest content (first 150 chars): {full_digest_with_title[:150]}...")

    return full_digest_with_title

def send_digest(digest_text: str) -> Dict[str, Any]:
    """
    Send the digest via Telegram using Telegraph.

    Args:
        digest_text: Digest text to send

    Returns:
        Response from Telegram API
    """
    logger.info("Sending digest via Telegram (using Telegraph)")

    telegram = TelegramSender(
        bot_token=TELEGRAM_BOT_TOKEN,
        chat_id=TELEGRAM_CHAT_ID
    )

    return telegram.send_message(digest_text)

def _update_processed_ids(entry_ids: List[int], hours_back: int = None):
    """Helper function to update the processed IDs file incrementally and clean old IDs.

    Uses {id, ts} structure for reliable timestamp-based pruning.
    """
    now_ts = int(datetime.datetime.now().timestamp())
    pruning_hours = max(48, (hours_back or HOURS_BACK) * 2)

    try:
        existing_entries = []
        if PROCESSED_IDS_FILE.exists():
            with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    if data and isinstance(data[0], dict):
                        # New {id, ts} format
                        existing_entries = data
                    else:
                        # Backward compat: migrate old [id, ...] format
                        existing_entries = [{"id": eid, "ts": now_ts} for eid in data]

        # Build set of existing IDs for dedup
        existing_id_set = {entry["id"] for entry in existing_entries}

        # Add new IDs
        new_entries = [
            {"id": eid, "ts": now_ts}
            for eid in entry_ids
            if eid not in existing_id_set
        ]
        all_entries = existing_entries + new_entries

        # Prune old entries
        cutoff_ts = int((datetime.datetime.now() - datetime.timedelta(hours=pruning_hours)).timestamp())
        filtered_entries = [entry for entry in all_entries if entry["ts"] >= cutoff_ts]

        # Write back to file
        with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(filtered_entries, f, ensure_ascii=False, indent=4)
        logger.info(f"Successfully updated processed IDs file with {len(filtered_entries)} entries (pruning window: {pruning_hours}h): {PROCESSED_IDS_FILE}")
    except Exception as e:
        logger.error(f"Failed to update processed IDs file {PROCESSED_IDS_FILE}: {e}")

def run_digest_process(hours_back: int = None, send: bool = True) -> str:
    """
    Run the complete digest generation and sending process

    Args:
        hours_back: Hours back to look for entries (overrides config)
        send: Whether to send the digest via Telegram

    Returns:
        Generated digest text
    """
    # Use config value if not provided
    if hours_back is None:
        hours_back = HOURS_BACK

    logger.info(f"Starting RSS digest process (looking back {hours_back} hours, using processed IDs file: {PROCESSED_IDS_FILE})")

    # Get entries from database
    entries = get_recent_entries(
        db_path=FRESHRSS_DB_PATH,
        hours_back=hours_back,
        processed_ids_file_path=str(PROCESSED_IDS_FILE)
    )

    if not entries:
        message = f"No new entries found in the past {hours_back} hours (after filtering processed IDs)."
        logger.warning(message)
        return message

    logger.info(f"Found {len(entries)} new entries in the past {hours_back} hours (after filtering)")

    # Attempt digest generation with retry
    max_attempts = 2
    last_error = None
    digest = ""
    for attempt in range(1, max_attempts + 1):
        logger.info(f"Generating digest attempt {attempt}/{max_attempts}")
        try:
            digest = generate_digest(entries)
            break  # Success
        except DigestGenerationError as e:
            last_error = e
            logger.error(f"Digest generation attempt {attempt} failed: {e}")
            if attempt < max_attempts:
                logger.info("Retrying digest generation...")
        except Exception as e:
            last_error = e
            logger.error(f"Digest generation attempt {attempt} unexpected error: {e}")
            if attempt < max_attempts:
                logger.info("Retrying digest generation...")

    # Final check for failure
    if last_error and not digest:
        logger.error(f"Digest generation failed after {max_attempts} attempts. Not updating processed IDs.")
        if send:
            telegram = TelegramSender(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
            telegram.send_message(f"Digest generation failed after {max_attempts} attempts. Error: {last_error}")
        return ""

    # Digest generated successfully
    current_entry_ids = [entry['id'] for entry in entries]
    _update_processed_ids(current_entry_ids, hours_back=hours_back)

    if send:
        response = send_digest(digest)
        # Save to history only after successful send
        if response.get("success"):
            _save_digest_to_history(digest)

    return digest
