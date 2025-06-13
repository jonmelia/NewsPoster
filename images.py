import logging
import requests
from io import BytesIO
from PIL import Image, UnidentifiedImageError

HEADERS = {
    "User-Agent": "NewsPosterBot/1.0 (+https://yourdomain.com)"
}

FALLBACK_IMAGE_URL = "https://yourdomain.com/static/default-thumbnail.png"

def fetch_image_bytes(url, timeout=5):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logging.warning(f"Failed to fetch image from {url}: {e}")
        return None

def validate_image_bytes(image_bytes):
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        return True
    except (UnidentifiedImageError, Exception) as e:
        logging.warning(f"Image validation failed: {e}")
        return False

def get_valid_image_blob(image_url, client, fallback_url=FALLBACK_IMAGE_URL):
    """
    Attempts to fetch and validate an image from `image_url`.
    Falls back to `fallback_url` if needed.
    Uploads to Bluesky and returns the blob.
    """
    image_bytes = fetch_image_bytes(image_url)

    if image_bytes and validate_image_bytes(image_bytes):
        logging.info("Using original image")
    else:
        logging.warning("Using fallback image due to error or invalid original")
        image_bytes = fetch_image_bytes(fallback_url)
        if not image_bytes or not validate_image_bytes(image_bytes):
            logging.error("Failed to fetch or validate fallback image")
            return None

    try:
        return client.com.atproto.repo.upload_blob(BytesIO(image_bytes)).blob
    except Exception as e:
        logging.error(f"Failed to upload image blob: {e}")
        return None