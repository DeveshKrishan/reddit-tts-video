from google_auth_oauthlib.flow import InstalledAppFlow

from logger import logger

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]


def generate_youtube_refresh_token(client_secret_file: str = "client_secret.json"):
    """Generates a YouTube API refresh token using OAuth2 flow."""
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    creds = flow.run_local_server(port=0)
    logger.info(f"Refresh Token: {creds.refresh_token}")


if __name__ == "__main__":
    generate_youtube_refresh_token()
