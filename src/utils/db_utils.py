#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import datetime
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
import warnings
import json
import os

# Ignore the specific BeautifulSoup warning about URLs resembling file paths
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

def clean_html_content(html_content: str) -> str:
    """
    清理HTML内容，提取正文
    
    Args:
        html_content: 原始HTML内容
        
    Returns:
        清理后的文本内容
    """
    if not html_content:
        return ""
    
    # 使用BeautifulSoup解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 移除script和style元素
    for script in soup(["script", "style"]):
        script.extract()
    
    # 尝试定位微信公众号文章的主要内容
    content_candidates = soup.find_all(['div', 'section'], class_=re.compile(r'(content|rich_media_content|article)'))
    
    if content_candidates:
        main_content = max(content_candidates, key=lambda x: len(x.get_text()))
        text = main_content.get_text(separator='\n')
    else:
        # 如果找不到明确的内容div，就提取所有文本
        text = soup.get_text(separator='\n')
    
    # 清理多余空行
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)

def get_recent_entries(db_path: str, hours_back: int = 48, processed_ids_file_path: str = None) -> List[Dict[Any, Any]]:
    """
    Retrieve entries from the past few hours from the FreshRSS database,
    excluding entries that have been processed before.
    
    Args:
        db_path: Path to the SQLite database
        hours_back: How many hours back to look for entries
        processed_ids_file_path: Path to the JSON file storing processed entry IDs
        
    Returns:
        List of dictionaries containing feed entries with their content
    """
    processed_entry_ids = set()
    if processed_ids_file_path and os.path.exists(processed_ids_file_path):
        try:
            with open(processed_ids_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    if data and isinstance(data[0], dict):
                        # New {id, ts} format
                        processed_entry_ids = set(item["id"] for item in data)
                    else:
                        # Old [id, ...] format
                        processed_entry_ids = set(data)
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

    # Calculate timestamp for N hours ago
    timestamp = int((datetime.datetime.now() - datetime.timedelta(hours=hours_back)).timestamp())
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query for recent entries including their content
        query = """
        SELECT
            e.id, e.title, e.author, e.content, e.link, e.date,
            c.name as category, f.name as feed_name
        FROM entry e
        JOIN feed f ON e.id_feed = f.id
        LEFT JOIN category c ON f.category = c.id
        WHERE e.date >= ?
        ORDER BY e.date DESC
        """

        cursor.execute(query, (timestamp,))
        results = cursor.fetchall()

        # Convert to list of dictionaries and filter out processed entries
        entries = []
        for row in results:
            entry_id = row['id']
            if entry_id not in processed_entry_ids:
                raw_content = row['content']
                entries.append({
                    'id': entry_id,
                    'title': row['title'],
                    'author': row['author'],
                    'content': clean_html_content(raw_content),
                    'raw_content': raw_content,
                    'link': row['link'],
                    'date': datetime.datetime.fromtimestamp(row['date']),
                    'category': row['category'] or 'Uncategorized',
                    'feed_name': row['feed_name']
                })
    finally:
        conn.close()

    return entries

def group_entries_by_category(entries: List[Dict[Any, Any]]) -> Dict[str, List[Dict[Any, Any]]]:
    """
    Group entries by their category
    
    Args:
        entries: List of entry dictionaries
        
    Returns:
        Dictionary with categories as keys and lists of entries as values
    """
    grouped = {}
    
    for entry in entries:
        category = entry['category']
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(entry)
        
    return grouped 