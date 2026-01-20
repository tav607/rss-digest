#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegraph publishing utilities for RSS Digest.
Creates Telegraph pages for long content with preserved hyperlinks.
"""

import os
import re
import logging
from html import escape as html_escape
from urllib.parse import urlparse
from telegraph import Telegraph
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Environment variable name for Telegraph token
TELEGRAPH_TOKEN_ENV = "TELEGRAPH_ACCESS_TOKEN"


def _get_telegraph_client() -> Telegraph:
    """
    Get Telegraph client using environment variable token.

    If token is not set, creates a new account and logs the token
    for the user to save.
    """
    token = os.getenv(TELEGRAPH_TOKEN_ENV)

    if token:
        logger.debug("Using Telegraph token from environment variable")
        return Telegraph(access_token=token)

    # Create new account and prompt user to save token
    logger.warning(
        f"No {TELEGRAPH_TOKEN_ENV} found in environment. "
        "Creating new Telegraph account..."
    )
    telegraph = Telegraph()
    result = telegraph.create_account(short_name="RSSDigest", author_name="RSS Digest Bot")
    new_token = result["access_token"]

    logger.warning(
        f"New Telegraph account created. Please add to your .env file:\n"
        f"{TELEGRAPH_TOKEN_ENV}={new_token}"
    )

    return Telegraph(access_token=new_token)


def _is_safe_url(url: str) -> bool:
    """Check if URL uses a safe protocol (http/https only)."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https", "")
    except Exception:
        return False


def _process_inline_formatting(text: str) -> str:
    """
    Process inline Markdown formatting to HTML with proper escaping.

    Handles:
    - **bold** -> <strong>bold</strong>
    - [text](url) -> <a href="url">text</a> (with URL validation)
    - Escapes HTML special characters in regular text
    """
    result = []
    pos = 0

    # Combined pattern for bold and links
    pattern = re.compile(r'\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)')

    for match in pattern.finditer(text):
        # Add escaped text before this match
        if match.start() > pos:
            result.append(html_escape(text[pos:match.start()]))

        if match.group(1):  # Bold: **text**
            result.append(f'<strong>{html_escape(match.group(1))}</strong>')
        elif match.group(2) and match.group(3):  # Link: [text](url)
            link_text = html_escape(match.group(2))
            url = match.group(3)
            if _is_safe_url(url):
                # Escape URL for HTML attribute
                safe_url = html_escape(url, quote=True)
                result.append(f'<a href="{safe_url}">{link_text}</a>')
            else:
                # Unsafe URL, just show the text
                logger.warning(f"Skipping unsafe URL: {url[:50]}...")
                result.append(link_text)

        pos = match.end()

    # Add remaining text
    if pos < len(text):
        result.append(html_escape(text[pos:]))

    return ''.join(result)


def _markdown_to_telegraph_html(markdown_text: str) -> str:
    """
    Convert digest Markdown to Telegraph-compatible HTML.

    Handles:
    - # Title -> skipped (Telegraph page already has title)
    - ## Heading -> <h4>Heading</h4>
    - **bold** -> <strong>bold</strong>
    - [text](url) -> <a href="url">text</a>
    - - bullet -> <li>bullet</li> (wrapped in <ul>)
    """
    lines = markdown_text.strip().split('\n')
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<p><br/></p>')
            continue

        # Skip top-level title (# ...) - Telegraph page already has title
        if stripped.startswith('# ') and not stripped.startswith('## '):
            continue

        # Handle headings
        if stripped.startswith('## '):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            content = _process_inline_formatting(stripped[3:])
            html_parts.append(f'<h4>{content}</h4>')

        # Handle bullet points
        elif stripped.startswith('- '):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            content = _process_inline_formatting(stripped[2:])
            html_parts.append(f'<li>{content}</li>')

        # Regular paragraph
        else:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            content = _process_inline_formatting(stripped)
            html_parts.append(f'<p>{content}</p>')

    # Close any open list
    if in_list:
        html_parts.append('</ul>')

    # Join without newlines - Telegraph interprets newlines as empty list items
    return ''.join(html_parts)


def create_telegraph_page(title: str, markdown_content: str) -> str:
    """
    Create a Telegraph page from Markdown content.

    Args:
        title: Page title
        markdown_content: Markdown formatted content (digest output)

    Returns:
        Telegraph page URL

    Raises:
        RequestException: If Telegraph API request fails
        ValueError: If response is invalid
    """
    telegraph = _get_telegraph_client()

    html_content = _markdown_to_telegraph_html(markdown_content)
    logger.debug(f"Converted Markdown to HTML, length: {len(html_content)}")

    response = telegraph.create_page(
        title=title,
        html_content=html_content,
        author_name="RSS Digest Bot"
    )

    if not response or 'path' not in response:
        raise ValueError("Invalid response from Telegraph API")

    page_url = f"https://telegra.ph/{response['path']}"
    logger.info(f"Created Telegraph page: {page_url}")

    return page_url
