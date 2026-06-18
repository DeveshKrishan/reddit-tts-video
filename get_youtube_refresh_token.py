import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from config import load_config
from logger import logger

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def generate_youtube_refresh_token(client_secret_file: str = "client_secret.json") -> str:
    """Generates a YouTube API refresh token using OAuth2 flow."""
    config = load_config()
    scopes = config.get("scopes", DEFAULT_SCOPES)

    with open(client_secret_file, encoding="utf-8") as f:
        client_config = json.load(f)["installed"]

    logger.info("Opening browser for Google sign-in. Approve access for your YouTube channel.")
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
    creds = flow.run_local_server(port=0)

    if not creds.refresh_token:
        raise RuntimeError("Google did not return a refresh token. Try revoking app access and running again.")

    logger.info("Success. Add or update these values in your .env file:")
    logger.info(f"YT_CLIENT_ID={client_config['client_id']}")
    logger.info(f"YT_CLIENT_SECRET={client_config['client_secret']}")
    logger.info(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    logger.info("If you use GitHub Actions, also update the YT_* secrets there.")
    return creds.refresh_token


if __name__ == "__main__":
    if not os.path.exists("client_secret.json"):
        raise SystemExit(
            "client_secret.json not found. Download it from Google Cloud Console:\n"
            "APIs & Services → Credentials → OAuth 2.0 Client → Download JSON"
        )
    generate_youtube_refresh_token()
