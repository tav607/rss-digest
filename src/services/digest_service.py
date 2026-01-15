#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Any, Tuple
import datetime
import json
import re

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
    merged_summaries = ai_processor.summarize_articles(entries)
    if not merged_summaries or not merged_summaries.strip():
        logger.error("Stage1 produced empty summaries.")
        return "Failed to generate digest: Stage1 produced no summaries."

    # Load digest history for deduplication
    digest_history = _load_digest_history()
    logger.info(f"Loaded {len(digest_history)} historical digests for deduplication")

    # Stage 2: finalize digest from stage1 abstracts
    logger.info("Stage2: Finalizing digest from per-article summaries...")
    ai_generated_digest = ai_processor.finalize_digest_from_article_summaries(
        merged_summaries,
        digest_history=digest_history
    )
    if not ai_generated_digest or not ai_generated_digest.strip():
        logger.error("Stage2 produced empty digest.")
        return "Failed to generate digest: Stage2 returned empty content."

    if not ai_generated_digest or len(ai_generated_digest.strip()) == 0:
        logger.error("AIProcessor generated an empty or invalid digest.")
        return "Failed to generate digest: AI returned empty content."
    
    # Format the current datetime
    formatted_datetime = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")

    # Create the title and full digest
    title = f"# RSS 新闻摘要 - {formatted_datetime}"
    full_digest_with_title = f"{title}\n\n{ai_generated_digest}"

    logger.info(f"Digest generated successfully, final length: {len(full_digest_with_title)} characters.")
    logger.debug(f"Final digest content (first 150 chars): {full_digest_with_title[:150]}...")
    
    return full_digest_with_title

# Categories for Part 1 and Part 2
PART1_CATEGORIES = ['AI', 'Semi', 'Smartphone']
PART2_CATEGORIES = ['Other Tech', 'World News', 'Misc']


def _split_digest_by_category(digest_text: str) -> Tuple[str, str]:
    """
    Split digest into two parts based on categories.

    Part 1: AI, Semi, Smartphone
    Part 2: Other Tech, World News, Misc

    If only one part has content, no (1/2) or (2/2) markers are added.

    Args:
        digest_text: Full digest text with title

    Returns:
        Tuple of (part1_text, part2_text) with appropriate markers
    """
    # Extract title line (first line starting with #)
    lines = digest_text.split('\n')
    title_line = ""
    content_start = 0

    for i, line in enumerate(lines):
        if line.strip().startswith('# '):
            title_line = line.strip()
            content_start = i + 1
            break

    # Get the content after title
    content = '\n'.join(lines[content_start:])

    # Split content by category sections (## Category)
    # Pattern matches ## followed by category name
    category_pattern = r'(## (?:AI|Semi|Smartphone|Other Tech|World News|Misc)\b)'
    parts = re.split(category_pattern, content)

    # Rebuild sections as dict
    sections = {}
    current_category = None

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Check if this part is a category header
        match = re.match(r'^## (AI|Semi|Smartphone|Other Tech|World News|Misc)$', part)
        if match:
            current_category = match.group(1)
            sections[current_category] = ""
        elif current_category:
            sections[current_category] = part

    # Build Part 1 (AI, Semi, Smartphone)
    part1_sections = []
    for cat in PART1_CATEGORIES:
        if cat in sections and sections[cat].strip():
            part1_sections.append(f"## {cat}\n{sections[cat]}")

    # Build Part 2 (Other Tech, World News, Misc)
    part2_sections = []
    for cat in PART2_CATEGORIES:
        if cat in sections and sections[cat].strip():
            part2_sections.append(f"## {cat}\n{sections[cat]}")

    # Determine if we need markers based on whether both parts have content
    has_part1 = bool(part1_sections)
    has_part2 = bool(part2_sections)
    use_markers = has_part1 and has_part2

    # Create titles with or without markers
    if use_markers:
        title_with_marker_1 = (title_line.rstrip() + " (1/2)") if title_line else "# RSS 新闻摘要 (1/2)"
        title_with_marker_2 = (title_line.rstrip() + " (2/2)") if title_line else "# RSS 新闻摘要 (2/2)"
    else:
        # No markers if only one part has content
        title_with_marker_1 = title_line if title_line else "# RSS 新闻摘要"
        title_with_marker_2 = title_line if title_line else "# RSS 新闻摘要"

    # Combine into final texts
    part1_text = title_with_marker_1 + "\n\n" + "\n\n".join(part1_sections) if part1_sections else ""
    part2_text = title_with_marker_2 + "\n\n" + "\n\n".join(part2_sections) if part2_sections else ""

    return part1_text, part2_text


def send_digest(digest_text: str) -> Dict[str, Any]:
    """
    Send the digest via Telegram, split into two messages by category.

    Part 1: AI, Semi, Smartphone
    Part 2: Other Tech, World News, Misc

    Args:
        digest_text: Digest text to send

    Returns:
        Response from Telegram (last message sent)
    """
    logger.info("Sending digest via Telegram (split into two parts)")

    telegram = TelegramSender(
        bot_token=TELEGRAM_BOT_TOKEN,
        chat_id=TELEGRAM_CHAT_ID
    )

    # Split digest into two parts
    part1, part2 = _split_digest_by_category(digest_text)

    # Check if both parts are empty (parsing failed or no recognized categories)
    if not part1.strip() and not part2.strip():
        logger.warning("Split produced empty parts, falling back to sending original digest")
        return telegram.send_message(digest_text)

    last_response = None
    sent_count = 0

    # Send Part 1 (AI, Semi, Smartphone)
    if part1.strip():
        logger.info(f"Sending Part 1 (AI, Semi, Smartphone), length: {len(part1)}")
        response1 = telegram.send_message(part1)
        if not response1.get("success"):
            logger.error(f"Failed to send Part 1: {response1.get('error')}")
            return response1
        last_response = response1
        sent_count += 1

    # Send Part 2 (Other Tech, World News, Misc)
    if part2.strip():
        logger.info(f"Sending Part 2 (Other Tech, World News, Misc), length: {len(part2)}")
        response2 = telegram.send_message(part2)
        if not response2.get("success"):
            logger.error(f"Failed to send Part 2: {response2.get('error')}")
            return response2
        last_response = response2
        sent_count += 1

    logger.info(f"Digest sent successfully ({sent_count} part(s))")
    return last_response

def _update_processed_ids(entry_ids: List[int]):
    """Helper function to update the processed IDs file incrementally and clean old IDs."""
    try:
        existing_ids = []
        if PROCESSED_IDS_FILE.exists():
            with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_ids = data
        # Combine existing and new IDs
        all_ids_set = set(existing_ids) | set(entry_ids)
        # Calculate cutoff timestamp for 48 hours ago
        cutoff_ts = int((datetime.datetime.now() - datetime.timedelta(hours=48)).timestamp())
        # Filter out IDs older than cutoff based on first 10 digits
        filtered_ids = [eid for eid in all_ids_set if int(str(eid)[:10]) >= cutoff_ts]
        # Write back to file
        with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(filtered_ids, f, ensure_ascii=False, indent=4)
        logger.info(f"Successfully updated processed IDs file with {len(filtered_ids)} entries: {PROCESSED_IDS_FILE}")
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
    attempt = 0
    digest = ""
    error_message = ""
    while attempt < max_attempts:
        attempt += 1
        logger.info(f"Generating digest attempt {attempt}/{max_attempts}")
        digest = generate_digest(entries)
        # Check for failure indicators
        if digest and digest.strip() and not any(ind in digest for ind in ["Failed to generate digest", "无法生成摘要"]):
            break
        error_message = digest or "Empty digest"
        logger.error(f"Digest generation attempt {attempt} failed: {error_message}")
        if attempt < max_attempts:
            logger.info("Retrying digest generation...")

    # Final check for failure
    if not digest or any(ind in digest for ind in ["Failed to generate digest", "无法生成摘要"]):
        logger.error(f"Digest generation failed after {max_attempts} attempts. Not updating processed IDs.")
        if send:
            # Send error message via Telegram
            telegram = TelegramSender(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
            telegram.send_message(f"Digest generation failed after {max_attempts} attempts. Error: {error_message}")
        return digest

    # Digest generated successfully
    current_entry_ids = [entry['id'] for entry in entries]
    _update_processed_ids(current_entry_ids)

    if send:
        response = send_digest(digest)
        # Save to history only after successful send
        if response.get("success"):
            _save_digest_to_history(digest)

    return digest 
