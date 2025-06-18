# -*- coding: utf-8 -*-

# Sample Python code for youtube.channels.list
# See instructions for running these code samples locally:
# https://developers.google.com/explorer-help/code-samples#python

import os

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()  # Loads variables from .env

creds = Credentials(
    None,
    refresh_token=os.getenv("YT_REFRESH_TOKEN"),
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.getenv("YT_CLIENT_ID"),
    client_secret=os.getenv("YT_CLIENT_SECRET"),
    scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"],
)

youtube = build("youtube", "v3", credentials=creds)

# Sample API call: Get your channel info
response = youtube.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()

print("Channel info:")
print(response)


# ...existing code for uploading or interacting with YouTube...
