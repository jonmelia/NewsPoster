# README.md

# News Poster

This Python module automates the scraping, processing, and social posting of news articles. It extracts articles from RSS feeds, analyzes sentiment, gathers imagery, and publishes to multiple platforms including Twitter, Facebook, Instagram, and Bluesky. It also includes a follow-back system for Bluesky to enhance audience engagement.

---

## Features

- **News Aggregation** from global and UK-specific RSS feeds.
- **Content Extraction** with automatic fallback image support.
- **Sentiment Analysis** using NLTK's VADER.
- **Multi-Platform Posting** (Twitter/X, Facebook, Instagram, Bluesky).
- **User Engagement**: Follow-back automation for Bluesky.
- **Logging** to `poster.log` with detailed traceability.
- **Scheduled Automation** via `schedule` module (not yet configured in main script).

---

## Key Files

- `main.py` — Core logic for scraping, processing, and posting news.
- `news_sources_config.py` — Defines news source RSS feeds.
- `usernames.py` — Stores platform API credentials.

---

## Functions

### Feed and Article Handling

- `fetch_feed(url, timeout=15)`
  Fetch and parse a single RSS feed.

- `fetch_feed_with_retries(url, timeout=15, retries=3, delay=5)`
  Retry logic wrapper for feed fetching.

- `scrape_articles()`
  Collects article titles and URLs from all configured sources.

- `extract_article_content(articles)`
  Scrapes full article content and retrieves a valid image or fallback.

- `is_valid_image_url(url)`
  Verifies if an image URL is valid and opens correctly with PIL.

---

### Social Platform Automation

- `follow_back_bluesky()`
  Automatically follows back users on Bluesky that meet engagement thresholds (e.g., followers > 10, posts > 5).

  **Logs detailed reasons** for skipping users (e.g., no avatar, inactive, low count).

---

## Credentials Setup

`usernames.py` must define the following:

```python
x_credentials = {
    "api_key": "...",
    "api_secret": "...",
    "access_token": "...",
    "access_token_secret": "..."
}

facebook_credentials = {
    "access_token": "..."
}

instagram_credentials = {
    "username": "...",
    "password": "..."
}

bluesky_credentials = {
    "did": "...",  # or email address
    "password": "..."
}
```

---

## Logging

Logs are saved to `poster.log` in the working directory. Example entries:

- `INFO - Fetched 42 articles from BBC`
- `WARNING - Follower xyz has less than 10 followers, skipping`
- `ERROR - Failed to fetch feed: Timeout`

---

## Dependencies

Install with pip:

```bash
pip install -r requirements.txt
```

Dependencies include:

- `feedparser`
- `beautifulsoup4`
- `nltk`
- `tweepy`
- `facebook-sdk`
- `instaloader`
- `Pillow`
- `atproto` (for Bluesky)
- `schedule`
- `regex`
- `pytz`
- `requests`

---

## Future Improvements

- Add scheduled posting loop using `schedule`.
- Add engagement metrics to evaluate post performance.
- Extend to other platforms (e.g., Threads, LinkedIn).
- Add filters for news topics or sentiment thresholds.

---

## License

MIT License — Free for personal or commercial use with attribution.
