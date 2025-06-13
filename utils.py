# utils.py

import os
import re
import regex
import time
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from nltk.sentiment import SentimentIntensityAnalyzer
from news_sources_config import get_all_news_sources
from collections import Counter

from PIL import Image, UnidentifiedImageError
import numpy as np


# —— Constants —— #

# Used when a scraped article has no valid image
FALLBACK_IMAGE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/"
    "a/ac/No_image_available.svg/768px-No_image_available.svg.png"
)

# HTTP header for feed requests
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'}

# Words to exclude from hashtags
STOP_WORDS = {
    "the", "and", "or", "but", "if", "in", "on", "to", "of", "a", "an", "can", "for",
    "with", "at", "by", "from", "about", "as", "into", "like", "through", "after",
    "over", "between", "out", "against", "during", "without", "before", "under",
    "around", "among", "is", "are", "was", "were", "be", "been", "being", "this",
    "that", "these", "those", "it", "its", "my", "your", "their", "his", "her", "our",
    "me", "you", "them", "he", "she", "we", "they", "i"
}

# Single shared sentiment analyzer
sia = SentimentIntensityAnalyzer()


def scrape_articles(news_sources):
    """
    Scrape articles from a list of news sources.
    Each source should be a dict with keys: 'rss' and 'name'.

    Returns a list of articles dicts with 'title', 'link', and 'source'.
    """
    articles = []
    for source in news_sources:
        feed = fetch_feed_with_retries(source['rss'])
        if feed is None:
            logging.warning(f"Skipping feed {source['name']} due to repeated fetch failures.")
            continue
        for entry in feed.entries:
            articles.append({'title': entry.title, 'link': entry.link, 'source': source['name']})
        logging.info(f"Added {len(feed.entries)} articles from {source['name']}")
    logging.info(f"Total articles scraped: {len(articles)}")
    return articles

# —— RSS Feed Fetching —— #

def fetch_feed(url, timeout=15):
    """Fetch and parse an RSS feed, returning a feedparser.FeedParserDict or None."""
    try:
        logging.info(f"Fetching RSS feed: {url}")
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo:
            logging.warning(f"Feed parsing error for {url}: {feed.bozo_exception}")
            return None
        return feed
    except Exception as e:
        logging.warning(f"Failed to fetch/parse RSS feed {url}: {e}")
        return None


def fetch_feed_with_retries(url, timeout=15, retries=3, delay=5):
    """Retry fetching a feed up to `retries` times, returning the first non-None result."""
    for attempt in range(1, retries + 1):
        feed = fetch_feed(url, timeout)
        if feed:
            return feed
        logging.warning(f"Retry {attempt}/{retries} for feed {url} failed, retrying in {delay}s")
        time.sleep(delay)
    logging.error(f"All retries failed for feed: {url}")
    return None


# —— Article Extraction —— #

def is_valid_image_url(url):
    """Return True if the URL points to a valid image (status 200 & PIL can open)."""
    try:
        if not url:
            return False
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        Image.open(BytesIO(resp.content))
        return True
    except Exception:
        return False


def extract_single_article(article):
    """Fetch the article page, extract text + find a valid image (or fallback)."""
    try:
        resp = requests.get(article['link'], timeout=5)
        soup = BeautifulSoup(resp.content, 'html.parser')
        article['content'] = soup.get_text()
        # find first valid <img>
        for img in soup.find_all('img'):
            src = img.get('src')
            if src and is_valid_image_url(src):
                article['image'] = src
                break
        else:
            article['image'] = FALLBACK_IMAGE_URL
    except Exception as e:
        logging.warning(f"Error scraping {article['link']}: {e}")
        article['content'] = ""
        article['image'] = FALLBACK_IMAGE_URL
    return article


def extract_article_content(articles, max_workers=10):
    """Parallelize extract_single_article over a list of article dicts."""
    updated = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(extract_single_article, art) for art in articles]
        for fut in as_completed(futures):
            updated.append(fut.result())
    return updated


# —— Sentiment Filtering —— #

def filter_debate_driven(articles, threshold=0.5, max_workers=10):
    """
    Return only those articles whose VADER compound score is above +threshold
    or below -threshold.
    """
    def check(article):
        try:
            score = sia.polarity_scores(article['content'])['compound']
            if abs(score) >= threshold:
                return article
        except Exception as e:
            logging.warning(f"Sentiment error for {article.get('title')}: {e}")
        return None

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(check, art) for art in articles]
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)
    logging.info(f"Filtered down to {len(results)} debate-driven articles")
    return results


# —— Text Utilities —— #

def truncate_to_graphemes(text, limit):
    """Truncate a string to `limit` Unicode grapheme clusters, adding “...” if cut."""
    graphemes = regex.findall(r"\X", text)
    if len(graphemes) > limit:
        return "".join(graphemes[:limit]) + "..."
    return text


def generate_hashtags(text, max_tags=5, min_len=4):
    """
    Extract up to `max_tags` meaningful hashtags from text, excluding stopwords.
    Uses frequency to prioritize words.
    Returns list of hashtags like ['#News', '#Technology'].
    """

    # Normalize and extract words (letters, digits, hyphens allowed)
    words = re.findall(r"\b[a-zA-Z][\w-]*\b", text.lower())

    # Filter out stopwords and short words
    filtered_words = [w for w in words if w not in STOP_WORDS and len(w) >= min_len]

    # Count frequency
    word_freq = Counter(filtered_words)

    # Sort by frequency descending, then alphabetically
    sorted_words = sorted(word_freq.items(), key=lambda x: (-x[1], x[0]))

    hashtags = []
    for word, _ in sorted_words:
        hashtags.append(f"#{word.capitalize()}")
        if len(hashtags) >= max_tags:
            break

    return hashtags


def create_facets_from_text(text):
    """
    Convert #hashtags in `text` into Bluesky facet objects so they render as links.
    Returns a list of facet dicts.
    """
    facets = []
    for m in re.finditer(r"#(\w+)", text):
        tag = m.group(1)
        start, end = m.span()
        facets.append({
            "$type": "app.bsky.richtext.facet",
            "features": [{
                "$type": "app.bsky.richtext.facet#tag",
                "tag": tag
            }],
            "index": {"byteStart": start, "byteEnd": end}
        })
    return facets


# —— Pagination Utility —— #

def paginate(func, key, actor_did, limit=100):
    """
    Generic paginator for Bluesky graph endpoints.
    `func(params)` should return an object with attributes `.key` (list) and `.cursor`.
    """
    cursor = None
    all_items = []
    while True:
        params = {'actor': actor_did, 'limit': limit}
        if cursor:
            params['cursor'] = cursor
        resp = func(params)
        items = getattr(resp, key, []) or []
        all_items.extend(items)
        cursor = getattr(resp, 'cursor', None)
        if not cursor:
            break
    return all_items

