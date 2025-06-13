# utils.py

import atproto
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


def get_valid_image_blob(url, client):
    headers = {"User-Agent": "NewsBot/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        blob = client.com.atproto.repo.upload_blob(BytesIO(resp.content))
        return blob.blob
    except Exception as e:
        logging.warning(f"Invalid image {url}: {e}")
        if url != FALLBACK_IMAGE_URL:
            return get_valid_image_blob(FALLBACK_IMAGE_URL, client)

# —— Article Extraction —— #

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
    chars = regex.findall(r"\X", text)
    return "".join(chars[:limit]) + ("..." if len(chars) > limit else "")

def generate_hashtags(text, max_tags=5, min_len=4):
    words = re.findall(r"\b[a-zA-Z][\w-]*\b", text.lower())
    freq = {}
    for w in words:
        if w in STOP_WORDS or len(w) < min_len: continue
        freq[w] = freq.get(w, 0) + 1
    tags = sorted(freq.keys(), key=lambda w: (-freq[w], w))[:max_tags]
    return [f"#{w.capitalize()}" for w in tags]


def create_facets_from_text(text):
    facets = []
    for m in re.finditer(r"#([A-Za-z]\w+)", text):
        start, end = m.span()
        facets.append({
            "$type": "app.bsky.richtext.facet",
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}],
            "index": {"byteStart": start, "byteEnd": end}
        })
    return facets

# def create_facets_from_text(text):
#     rt = atproto.RichText(text)
#     rt.detect_facets()
#     return rt.facets

# —— Pagination Utility —— #

def paginate_graph(method, actor_did):
    cursor = None
    items = []
    while True:
        response = method({"actor": actor_did, "limit": 100, **({"cursor": cursor} if cursor else {})})
        batch = getattr(response, "followers", None) or getattr(response, "follows", []) or []
        items.extend(batch)
        cursor = getattr(response, "cursor", None)
        if not cursor: break
    return items

# —— Followback utility —— #

def simplified_follow_back_bluesky(client, my_did):
    graph = client.app.bsky.graph
    actor = client.app.bsky.actor

    # Fetch followers and following
    followers = graph.get_followers({'actor': my_did}).followers
    following = graph.get_follows({'actor': my_did}).follows
    following_dids = {f.did for f in following if hasattr(f, 'did')}

    logging.info(f"Currently following {len(following_dids)} users, checking {len(followers)} followers")

    for follower in followers:
        try:
            follower_did = getattr(follower, 'did', None)
            if not follower_did:
                continue

            if follower_did in following_dids:
                continue

            if not getattr(follower, 'avatar', None):
                logging.info(f"Skipping {follower_did}: No avatar")
                continue

            profile = actor.get_profile({'actor': follower_did})

            if getattr(profile, 'followersCount', 0) < 10:
                logging.info(f"Skipping {follower_did}: <10 followers")
                continue
            if getattr(profile, 'postsCount', 0) < 5:
                logging.info(f"Skipping {follower_did}: <5 posts")
                continue
            if not getattr(profile, 'lastSeenAt', None):
                logging.info(f"Skipping {follower_did}: No lastSeenAt")
                continue

            graph.follow({'subject': follower_did})
            logging.info(f"✅ Followed back {follower_did}")

        except Exception as e:
            logging.warning(f"Error processing follower {getattr(follower, 'did', 'unknown')}: {e}")
