"""
GENERAL INFO:
Start a ssh forwarding like this:
Open a CMD and paste:

ssh -o ServerAliveInterval=60 -R GladosSlack:80:127.0.0.1:5000 serveo.net

Hopefully, this replies with Forwarding HTTP traffic from https://uterque.serveo.net

If not uterque, change the request URL here:
https://api.slack.com/apps/A05TP78C1CG/event-subscriptions

Later down the line, use some ssh-keygen magic (needs access to DNS) to request a particular subdomain

GladOS-bot can listen to all chats in all channels it's part of.

Use:
Currently, post text like this:
client.chat_postMessage(channel="glados-bot",text="Hello World")

Or listen like this:

@ slack_event_adapter.on('message')
def message(payload):
    print(payload)
    event = payload.get('event', {})
    channel_id = event.get('channel')
    user_id = event.get('user')
    text = event.get('text')


Used this guide: https://www.pragnakalp.com/create-slack-bot-using-python-tutorial-with-examples/
"""

import slack
from flask import Flask
from slackeventsapi import SlackEventAdapter

SLACK_TOKEN = "xoxb-134470729732-5930969383473-bmD1xnNmlKPRlnNPbKrcSiQf"
SIGNING_SECRET = "e8cd04aa4cc9ec7c51729ec6ecf98c1c"

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(SIGNING_SECRET, '/slack/eventsGlados/', app)

client = slack.WebClient(token=SLACK_TOKEN)
client.chat_postMessage(channel="glados-bot",text="Hello World")
 
 
# @ slack_event_adapter.on('message')
# def message(payload):
#     event = payload.get('event', {})
#     channel_id = event.get('channel')
#     user_id = event.get('user')
#     text = event.get('text')
 
#     if text == "hi":
#         client.chat_postMessage(channel=channel_id,text="Hello")

#     if text == "bye":
#         client.chat_postMessage(channel=channel_id,text="Bye-bye")
 
# if __name__ == "__main__":
#     app.run(debug=True)