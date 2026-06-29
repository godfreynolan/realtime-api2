# Simple OpenAI Realtime SIP Webhook

This is the smallest useful Python SIP integration for OpenAI Realtime. It receives OpenAI's `realtime.call.incoming` webhook, accepts the call with `gpt-realtime-2`, and opens a WebSocket to start and log the live call session.

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Set `OPENAI_API_KEY` and `OPENAI_WEBHOOK_SECRET`, then run:

```powershell
python app.py
```

Expose `http://localhost:8000/` publicly with a tunnel like ngrok, then add that public URL as an OpenAI project webhook.

## SIP setup

In your SIP trunk provider, point inbound SIP traffic to:

```text
sip:$PROJECT_ID@sip.api.openai.com;transport=tls
```

Your project ID starts with `proj_` and is shown in the OpenAI dashboard under Project > General.

## What this does

1. Verifies the OpenAI webhook signature with `OPENAI_WEBHOOK_SECRET`.
2. Accepts incoming calls with `model: gpt-realtime-2`.
3. Sends an initial `response.create` event over the call WebSocket.
4. Prints every Realtime event to the terminal.
