# main.py
import feedparser
from bs4 import BeautifulSoup
import requests
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
import tweepy
import facebook
import instaloader
import random
import schedule
import time
import pytz
from datetime import datetime
from PIL import Image
from io import BytesIO
from atproto import Client
import regex
import logging

from news_sources_config import get_all_news_sources
from usernames import x_credentials, facebook_credentials, instagram_credentials, bluesky_credentials

nltk.download('vader_lexicon')
sia = SentimentIntensityAnalyzer()

# Setup logging
logging.basicConfig(
    filename='poster.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'  # Overwrite log file on each run
)

logging.info("Script started")

# Load news sources
news_sources = get_all_news_sources(include_uk=True, include_other_english=True)
logging.info(f"Loaded {len(news_sources)} news sources")

captions = [
    "What's your take on this?\n",
    "Discuss:\n",
    "Your thoughts?\n",
    "Share your opinion:\n",
    "What do you think about this?\n",
    "Debate:\n",
    "We want to hear from you:\n",
    "Your say:\n",
    "Comment below:\n",
    "Join the conversation:\n",
    "What's on your mind?\n"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'}

FALLBACK_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/768px-No_image_available.svg.png"

def fetch_feed(url, timeout=15):
    try:
        logging.info(f"Fetching RSS feed: {url}")
        response = requests.get(url, timeout=timeout, headers=HEADERS)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo:
            logging.warning(f"Feed parsing error for {url}: {feed.bozo_exception}")
            return None
        logging.info(f"Successfully fetched and parsed feed: {url}")
        return feed
    except requests.exceptions.RequestException as e:
        logging.warning(f"Failed to fetch or parse RSS feed {url}: {e}")
        return None

def fetch_feed_with_retries(url, timeout=15, retries=3, delay=5):
    for attempt in range(1, retries + 1):
        logging.info(f"Attempt {attempt} to fetch feed: {url}")
        feed = fetch_feed(url, timeout=timeout)
        if feed is not None:
            return feed
        logging.warning(f"Retrying fetching RSS feed {url} (attempt {attempt}/{retries}) after {delay}s delay")
        time.sleep(delay)
    logging.error(f"All {retries} attempts failed to fetch feed: {url}")
    return None

def scrape_articles():
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

def is_valid_image_url(url):
    try:
        if not url:
            return False
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return False
        Image.open(BytesIO(response.content))
        return True
    except Exception:
        return False

def extract_article_content(articles):
    logging.info("Starting extract_article_content")
    for article in articles:
        try:
            response = requests.get(article['link'])
            soup = BeautifulSoup(response.content, 'html.parser')
            article['content'] = soup.get_text()
            article['image'] = None
            for img in soup.find_all('img'):
                if img.has_attr('src') and is_valid_image_url(img['src']):
                    article['image'] = img['src']
                    break
            if not article['image']:
                article['image'] = FALLBACK_IMAGE_URL
        except Exception as e:
            logging.warning(f"Error scraping {article['link']}: {str(e)}")
            article['image'] = FALLBACK_IMAGE_URL
    logging.info("Completed extract_article_content")
    return articles

def filter_debate_driven(articles):
    logging.info("Starting filter_debate_driven")
    debate_articles = []
    for article in articles:
        try:
            sentiment = sia.polarity_scores(article['content'])
            if sentiment['compound'] > 0.5 or sentiment['compound'] < -0.5:
                debate_articles.append(article)
        except Exception as e:
            logging.warning(f"Sentiment analysis error for article '{article.get('title', '')}': {str(e)}")
    logging.info(f"Filtered {len(debate_articles)} debate-driven articles")
    return debate_articles


def generate_hashtags(text):
    keywords = ["BreakingNews", "CurrentAffairs", "WorldNews", "Politics", "Headlines", "GlobalUpdate"]
    if text:
        text_keywords = text.lower().split()
        filtered = [tag for tag in keywords if tag.lower() in text_keywords or tag.lower()[:-4] in text_keywords]
        tags = filtered[:3] if filtered else random.sample(keywords, k=3)
    else:
        tags = random.sample(keywords, k=3)
    return " ".join(f"#{tag}" for tag in tags)

def truncate_to_graphemes(text, limit):
    graphemes = regex.findall(r'\X', text)
    if len(graphemes) > limit:
        return ''.join(graphemes[:limit]) + "..."
    return text


def post_on_x(article, x_credentials, captions):
    if not all(x_credentials.get(k) for k in ['bearer_token']):
        logging.warning("Missing X (Twitter) API bearer token. Skipping post.")
        return

    try:
        client = tweepy.Client(bearer_token=x_credentials['bearer_token'],
                               consumer_key=x_credentials.get('consumer_key'),
                               consumer_secret=x_credentials.get('consumer_secret'),
                               access_token=x_credentials.get('access_token'),
                               access_token_secret=x_credentials.get('access_token_secret'))

        hashtags = generate_hashtags(article['title'])
        status_text = f"{random.choice(captions)}{article['title']}\n{article['link']}\n{hashtags}"
        if len(status_text) > 280:
            allowed_length = 280 - len(hashtags) - 2  # for newline and spacing
            status_text = f"{status_text[:allowed_length]}...\n{hashtags}"

        response = client.create_tweet(text=status_text)
        if response.data:
            logging.info(f"Posted to X with tweet ID {response.data['id']}")
        else:
            logging.warning("No response data returned from X API")

    except tweepy.errors.Forbidden as e:
        logging.error(f"Failed to post on X: {e}")
        logging.error("Check your X API access level and tokens: https://developer.x.com/en/portal/product")
    except Exception as e:
        logging.error(f"Unexpected X posting error: {e}")


def post_on_facebook(article):
    logging.info("Attempting to post on Facebook")
    if facebook_credentials.get('access_token'):
        try:
            graph = facebook.GraphAPI(facebook_credentials['access_token'])
            hashtags = generate_hashtags(article['title'])
            caption = f"{random.choice(captions)}{article['title']} {article['link']}\n{hashtags}"
            graph.put_object(parent_object='me', connection_name='feed', message=caption)
            logging.info("Posted to Facebook")
        except Exception as e:
            logging.error(f"Failed to post on Facebook: {str(e)}")
    else:
        logging.warning("Facebook credentials missing. Skipping post.")

def post_on_instagram(article):
    logging.info("Attempting to post on Instagram")
    if instagram_credentials.get('username') and instagram_credentials.get('password'):
        try:
            L = instaloader.Instaloader()
            L.login(instagram_credentials['username'], instagram_credentials['password'])
            hashtags = generate_hashtags(article['title'])
            caption = f"{random.choice(captions)}{article['title']} {article['link']}\n{hashtags}"
            if article['image']:
                response = requests.get(article['image'])
                img = Image.open(BytesIO(response.content))
                img.save('image.jpg')
                L.upload_pic('image.jpg', caption)
                logging.info("Posted to Instagram")
        except Exception as e:
            logging.error(f"Failed to post on Instagram: {str(e)}")
    else:
        logging.warning("Instagram credentials missing. Skipping post.")

def post_on_bluesky(article):
    logging.info("Attempting to post on Bluesky")
    if bluesky_credentials.get('did') and bluesky_credentials.get('password'):
        try:
            client = Client()
            client.login(bluesky_credentials['did'], bluesky_credentials['password'])

            hashtags = generate_hashtags(article['title'])
            prefix = random.choice(captions)
            caption_text = f"{prefix}{article['title']}\n\n{hashtags}"
            link_text = article['link']

            full_text = truncate_to_graphemes(caption_text, 300)

            facets = []

            # Fetch and upload image
            image_url = article.get('image', FALLBACK_IMAGE_URL)
            image_response = requests.get(image_url)
            image_bytes = BytesIO(image_response.content)
            uploaded_blob = client.com.atproto.repo.upload_blob(image_bytes)

            # Create embed (external card with thumbnail)
            embed = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": link_text,
                    "title": article.get('title', ''),
                    "description": article.get('description', ''),
                    "thumb": uploaded_blob.blob  # This is the correct blob object
                }
            }

            client.send_post(
                text=full_text,
                facets=facets,
                embed=embed  # NO embed_alt — it’s invalid here
            )

            logging.info("Posted to Bluesky with embedded website card and image thumbnail")
        except Exception as e:
            logging.error(f"Failed to post on Bluesky: {str(e)}")
    else:
        logging.warning("Bluesky credentials missing. Skipping post.")


def paginate(func, key, actor_did):
    cursor = None
    all_profiles = []
    while True:
        params = {
            'actor': actor_did,
            'limit': 100
        }
        if cursor:
            params['cursor'] = cursor
        response = func(params)  # <--- FIXED: pass entire dict as single argument
        items = getattr(response, key, [])
        all_profiles.extend(items)
        cursor = getattr(response, 'cursor', None)
        if not cursor:
            break
    return all_profiles

def follow_back_bluesky():
    logging.info("Attempting to follow back users on Bluesky")

    if bluesky_credentials.get('did') and bluesky_credentials.get('password'):
        try:
            client = Client()
            client.login(bluesky_credentials['did'], bluesky_credentials['password'])

            me = client.me
            my_did = me.did
            logging.info(f"Authenticated as DID: {my_did}")

            def paginate(method, key, actor_did):
                cursor = None
                all_items = []
                while True:
                    params = {'actor': actor_did, 'limit': 100}
                    if cursor:
                        params['cursor'] = cursor
                    response = method(params)
                    items = getattr(response, key, []) or []
                    logging.info(f"Fetched {len(items)} items from {key}")
                    all_items.extend(items)
                    cursor = getattr(response, 'cursor', None)
                    if not cursor:
                        break
                return all_items

            graph_api = client.app.bsky.graph

            followers = paginate(graph_api.get_followers, 'followers', my_did)
            following = paginate(graph_api.get_follows, 'follows', my_did)

            following_dids = {f.did for f in following if hasattr(f, 'did')}
            logging.info(f"Currently following {len(following_dids)} users")

            for follower in followers:
                try:
                    follower_did = follower.did
                    logging.info(f"Evaluating follower: {follower_did}")

                    if follower_did in following_dids:
                        logging.info(f"Already following {follower_did}, skipping")
                        continue

                    if not getattr(follower, 'avatar', None):
                        logging.info(f"Follower {follower_did} has no avatar, skipping")
                        continue

                    profile_response = client.app.bsky.actor.get_profile({'actor': follower_did})
                    profile = profile_response

                    logging.info(f"Follower {follower_did} profile: followers={getattr(profile, 'followersCount', 0)}, posts={getattr(profile, 'postsCount', 0)}")

                    if getattr(profile, 'followersCount', 0) < 10:
                        logging.info(f"Follower {follower_did} has less than 10 followers, skipping")
                        continue
                    if getattr(profile, 'postsCount', 0) < 5:
                        logging.info(f"Follower {follower_did} has less than 5 posts, skipping")
                        continue
                    if not getattr(profile, 'lastSeenAt', None):
                        logging.info(f"Follower {follower_did} has no lastSeenAt, skipping")
                        continue

                    response = graph_api.follow({'subject': follower_did})
                    logging.info(f"Successfully followed back user: {follower_did}, Response: {response}")

                except Exception as inner_e:
                    logging.warning(f"Error on follower {getattr(follower, 'did', 'unknown')}: {inner_e}")

        except Exception as e:
            logging.error(f"Failed to follow back on Bluesky: {str(e)}")
    else:
        logging.warning("Bluesky credentials missing. Skipping follow-back.")


def follow_back_x(x_credentials):
    logging.info("Checking for new followers to follow back on X")
    if not all(x_credentials.get(k) for k in ['bearer_token', 'access_token', 'access_token_secret', 'consumer_key', 'consumer_secret']):
        logging.warning("Missing X x_credentials for follow-back functionality.")
        return

    try:
        client = tweepy.Client(
            bearer_token=x_credentials['bearer_token'],
            consumer_key=x_credentials['consumer_key'],
            consumer_secret=x_credentials['consumer_secret'],
            access_token=x_credentials['access_token'],
            access_token_secret=x_credentials['access_token_secret']
        )

        auth = tweepy.OAuth1UserHandler(
            x_credentials['consumer_key'],
            x_credentials['consumer_secret'],
            x_credentials['access_token'],
            x_credentials['access_token_secret']
        )
        api = tweepy.API(auth)

        followers = api.get_followers()
        for follower in followers:
            if not follower.following:
                api.create_friendship(user_id=follower.id_str)
                logging.info(f"Followed back user: {follower.screen_name}")

    except Exception as e:
        logging.error(f"Failed to follow back users on X: {str(e)}")

def post_articles_and_followback():
    logging.info("Starting post_articles_and_followback")
    articles = scrape_articles()
    articles = extract_article_content(articles)
    debate_articles = filter_debate_driven(articles)

    if debate_articles:
        article = random.choice(debate_articles)
        logging.info(f"Selected article for posting: {article['title']}")
        # post_on_x(article, x_credentials, captions)
        # post_on_facebook(article)
        # post_on_instagram(article)
        post_on_bluesky(article)
        follow_back_x(x_credentials)
        follow_back_bluesky()
    else:
        logging.info("No debate-driven articles found to post.")

def job_in_timezone(tz):
    now = datetime.now(tz)
    logging.info(f"Running job at {now.isoformat()} in timezone {tz.zone}")
    post_articles_and_followback()

def schedule_jobs():
    logging.info("Scheduling jobs")
    europe_tz = pytz.timezone('Europe/London')
    us_tz = pytz.timezone('US/Eastern')

    schedule.every().day.at("07:00").do(job_in_timezone, tz=europe_tz)
    schedule.every().day.at("12:00").do(job_in_timezone, tz=europe_tz)
    schedule.every().day.at("18:00").do(job_in_timezone, tz=europe_tz)
    schedule.every().day.at("07:00").do(job_in_timezone, tz=us_tz)
    schedule.every().day.at("12:00").do(job_in_timezone, tz=us_tz)
    schedule.every().day.at("18:00").do(job_in_timezone, tz=us_tz)
    logging.info("Jobs scheduled")


if __name__ == '__main__':
    logging.info("Main loop started")
    post_articles_and_followback()  # Post once immediately on startup
    schedule_jobs()
    while True:
        schedule.run_pending()
        time.sleep(10)