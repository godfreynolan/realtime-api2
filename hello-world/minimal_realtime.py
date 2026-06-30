import json
import os
import sys
import config
import websocket


prompt = " ".join(sys.argv[1:]) or "Say hello in one sentence."

ws = websocket.create_connection(
    "wss://api.openai.com/v1/realtime?model=gpt-realtime-2",
    header=[f"Authorization: Bearer {config.OPENAI_API_KEY}"],
)

ws.send(
    json.dumps(
        {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        }
    )
)
ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": ["text"]}}))

while True:
    event = json.loads(ws.recv())
    if event["type"] == "response.output_text.delta":
        print(event["delta"], end="", flush=True)
    elif event["type"] == "response.done":
        print()
        break

ws.close()
