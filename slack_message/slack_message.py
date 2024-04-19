from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

class SlackMessage(object):

    def __init__(self):
        self.token = os.environ.get('SLACK_TOKEN')
        self.channel = os.environ.get('SLACK_CHANNEL')
        self.client = WebClient(token=self.token)

    def post_message(self, text=""):
        try:
            response = self.client.chat_postMessage(channel=self.channel, text=text)
            assert response['message']['text'] == text
        except SlackApiError as e:
            assert e.response['ok'] is False
            assert e.response['error']
            print(f"Got an error: {e.response['error']}")
