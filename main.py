# main.py
import logging, random, schedule, time, pytz
from datetime import datetime
from io import BytesIO
from news_sources_config import get_all_news_sources
from images import get_valid_image_blob

from usernames          import (
    x_credentials,
    facebook_credentials,
    instagram_credentials,
    bluesky_credentials,
)
from utils import (
    scrape_articles,
    extract_article_content,
    filter_debate_driven,
    generate_hashtags,
    truncate_to_graphemes,
    create_facets_from_text,
    FALLBACK_IMAGE_URL,
    simplified_follow_back_bluesky
)

import tweepy, facebook, instaloader, requests
from atproto import Client

# Setup logging
logging.basicConfig(
    filename='poster.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w',
)
logging.info("Script started")

# Load news sources
news_sources = get_all_news_sources(include_uk=True, include_other_english=True)
logging.info(f"Loaded {len(news_sources)} news sources")


captions = [
    "What's your take on this?\n",
    "Discuss:\n\n",
    "Your thoughts?\n\n",
    "Share your opinion:\n\n",
    "What do you think about this?\n\n",
    "How do you feel about this?\n\n",
    "We want to hear from you:\n\n",
    "Have your say:\n\n",
    "Comment below:\n\n",
    "Join the conversation:\n\n",
    "What's on your mind?\n\n"
]


def post_on_x(article, x_credentials, captions):
    if not all(x_credentials.get(k) for k in ['bearer_token']):
        logging.warning("Missing X (Twitter) API bearer token. Skipping post.")
        return

    try:
        client = tweepy.Client(
            bearer_token=x_credentials['bearer_token'],
            consumer_key=x_credentials.get('consumer_key'),
            consumer_secret=x_credentials.get('consumer_secret'),
            access_token=x_credentials.get('access_token'),
            access_token_secret=x_credentials.get('access_token_secret')
        )

        hashtags = generate_hashtags(article['title'])  # Returns list like ['#AI', '#News']
        hashtags_text = ' '.join(hashtags)
        prefix = random.choice(captions)
        title = article['title']
        link = article['link']

        base_text = f"{prefix}{title}\n{link}\n{hashtags_text}"

        if len(base_text) > 280:
            max_title_length = 280 - len(prefix) - len(link) - len(hashtags_text) - 4  # extra for \n and "..."
            title = title[:max_title_length].rstrip() + "..."
            base_text = f"{prefix}{title}\n{link}\n{hashtags_text}"

        response = client.create_tweet(text=base_text)
        if response.data:
            logging.info(f"Posted to X with tweet ID {response.data['id']}")
        else:
            logging.warning("No response data returned from X API")

    except tweepy.errors.Forbidden as e:
        logging.error(f"Failed to post on X: {e}")
        logging.error("Check your X API access level and tokens: https://developer.x.com/en/portal/product")
    except Exception as e:
        logging.error(f"Unexpected X posting error: {e}")

def post_on_bluesky(article, captions, bluesky_credentials, fallback_image_url):
    if not (bluesky_credentials.get("did") and bluesky_credentials.get("password")):
        logging.warning("Missing Bluesky credentials. Skipping post.")
        return

    try:
        client = Client()
        client.login(bluesky_credentials["did"], bluesky_credentials["password"])
        logging.info("Logged into Bluesky")

        hashtags = generate_hashtags(article["title"])
        prefix = random.choice(captions)
        base_text = f"{prefix}{article['title']}\n\n{' '.join(hashtags)}"
        text = truncate_to_graphemes(base_text, 300)

        # Properly detect hashtags and attach as facets
        facets = create_facets_from_text(text)

        embed = {
            "$type": "app.bsky.embed.external",
            "external": {
                "uri": article.get("link", ""),
                "title": article.get("title", ""),
                "description": article.get("description", "") or article.get("title", ""),
                "thumb": get_valid_image_blob(article.get("image") or fallback_image_url, client),
            }
        }

        client.send_post(text=text, facets=facets, embed=embed)
        logging.info("Posted to Bluesky")
    except Exception as e:
        logging.error(f"Error posting on Bluesky: {e}")

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

def follow_back_bluesky():
    logging.info("Attempting to follow back users on Bluesky")

    if bluesky_credentials.get('did') and bluesky_credentials.get('password'):
        try:
            client = Client()
            client.login(bluesky_credentials['did'], bluesky_credentials['password'])
            my_did = client.me.did
            logging.info(f"Authenticated as DID: {my_did}")

            simplified_follow_back_bluesky(client, my_did)

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
    articles = scrape_articles(news_sources)
    articles = extract_article_content(articles)
    debate_articles = filter_debate_driven(articles)

    if debate_articles:
        article = random.choice(debate_articles)
        logging.info(f"Selected article for posting: {article['title']}")
        post_on_x(article, x_credentials, captions)
        # post_on_facebook(article)
        # post_on_instagram(article)
        post_on_bluesky(article, captions, bluesky_credentials, FALLBACK_IMAGE_URL)
        follow_back_x(x_credentials)
        follow_back_bluesky()
    else:
        logging.info("No debate-driven articles found to post.")

def job_in_timezone(tz):
    now = datetime.now(tz)
    logging.info(f"Running job at {now.isoformat()} in timezone {tz.zone}")
    post_articles_and_followback()

def get_randomized_time(hour):
    """Return a time string like '07:13' with randomized minutes (1–14)."""
    minute = random.randint(1, 14)
    return f"{hour:02d}:{minute:02d}"

def schedule_jobs():
    logging.info("Scheduling jobs with randomized times")
    europe_tz = pytz.timezone('Europe/London')
    us_tz = pytz.timezone('US/Eastern')

    # Define desired hours to run
    hours_to_schedule = [7, 12, 17, 19]

    for hour in hours_to_schedule:
        eu_time = get_randomized_time(hour)
        us_time = get_randomized_time(hour)

        schedule.every().day.at(eu_time).do(job_in_timezone, tz=europe_tz)
        schedule.every().day.at(us_time).do(job_in_timezone, tz=us_tz)

        logging.info(f"Scheduled EU job at {eu_time}, US job at {us_time}")

    logging.info("All jobs scheduled with randomized offsets")


if __name__ == '__main__':
    logging.info("Main loop started")
    post_articles_and_followback()  # Post once immediately on startup
    schedule_jobs()
    while True:
        schedule.run_pending()
        time.sleep(10)