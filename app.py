import asyncio
import json
import os
import threading
import config

import requests
import websockets
from flask import Flask, Response, request
from openai import InvalidWebhookSignatureError, OpenAI


app = Flask(__name__)
client = OpenAI(webhook_secret=config.OPENAI_WEBHOOK_SECRET, api_key=config.OPENAI_API_KEY)

AUTH_HEADERS = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}

CALL_ACCEPT_CONFIG = {
    "type": "realtime",
    "model": "gpt-realtime-2",
    "instructions": "You are a friendly, concise phone assistant.",
}

FIRST_RESPONSE = {
    "type": "response.create",
    "response": {
        "instructions": "Greet the caller and ask how you can help.",
    },
}


async def monitor_call(call_id: str) -> None:
    async with websockets.connect(
        f"wss://api.openai.com/v1/realtime?call_id={call_id}",
        additional_headers=AUTH_HEADERS,
    ) as websocket:
        await websocket.send(json.dumps(FIRST_RESPONSE))

        async for event in websocket:
            print(event)


@app.post("/")
def webhook() -> Response:
    try:
        event = client.webhooks.unwrap(request.get_data(), request.headers)
    except InvalidWebhookSignatureError:
        return Response("Invalid signature", status=400)

    if event.type != "realtime.call.incoming":
        return Response(status=204)

    call_id = event.data.call_id
    accept_response = requests.post(
        f"https://api.openai.com/v1/realtime/calls/{call_id}/accept",
        headers={**AUTH_HEADERS, "Content-Type": "application/json"},
        json=CALL_ACCEPT_CONFIG,
        timeout=10,
    )
    accept_response.raise_for_status()

    threading.Thread(
        target=lambda: asyncio.run(monitor_call(call_id)),
        daemon=True,
    ).start()

    return Response(status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
