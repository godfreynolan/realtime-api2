# AI Audiobook Reader

A tiny Python reader that turns a text document into streamed audiobook audio with OpenAI Realtime voice models.

It defaults to the attached Dracula file at C:\Users\admin\Downloads\pg345.txt, uses gpt-realtime-2, and saves a WAV file while audio streams in.

## Setup

    pip install -r requirements.txt
    $env:OPENAI_API_KEY = "your_api_key_here"

## Run Dracula

Narrate the first chunk and save it to out/dracula.wav:

    python audiobook_reader.py

Play it live while saving:

    python audiobook_reader.py --play

Narrate the whole book:

    python audiobook_reader.py --max-chunks 0 --output out/dracula-full.wav

Try a different voice:

    python audiobook_reader.py --voice cedar --max-chunks 3

Preview chunking without using the API:

    python audiobook_reader.py --dry-run

Use another text-like file:

    python audiobook_reader.py C:\path\to\article.txt --voice marin

## Notes

- The output is 24 kHz mono PCM audio wrapped as a WAV file.
- --max-chunks defaults to 1 so you can test cheaply before narrating a long book.
- Project Gutenberg header and footer text are removed by default.
- This uses the Realtime WebSocket API pattern from OpenAI's docs.

Sources: Realtime guide https://platform.openai.com/docs/guides/realtime, Realtime WebSockets https://developers.openai.com/api/docs/guides/realtime-websocket, Realtime conversations https://developers.openai.com/api/docs/guides/realtime-conversations.
