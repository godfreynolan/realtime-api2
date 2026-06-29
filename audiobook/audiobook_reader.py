from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
import config

try:
    import websocket
except ImportError:  # pragma: no cover - import guard for first-run setup
    websocket = None


DEFAULT_MODEL = "gpt-realtime-2"
DEFAULT_VOICE = "marin"
SAMPLE_RATE = 24_000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

DEFAULT_DOCUMENTS = (
    Path("books/dracula.txt"),
    Path(r"C:\Users\admin\Downloads\meetup\audiobook\pg345.txt"),
)

NARRATOR_INSTRUCTIONS = """
You are a warm, precise audiobook narrator.
Speak the user's passage only.
Do not add introductions, summaries, stage directions, or commentary.
Keep the author's words intact while using natural pacing, tasteful emotion,
and clear dialogue contrast.
""".strip()


class LivePlayer:
    def __init__(self, enabled: bool) -> None:
        self.stream: Any | None = None
        if not enabled:
            return

        try:
            import sounddevice as sd

            self.stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            )
            self.stream.start()
        except Exception as exc:  # pragma: no cover - hardware dependent
            print(f"Live playback unavailable, saving audio only: {exc}", file=sys.stderr)
            self.stream = None

    def write(self, data: bytes) -> None:
        if self.stream is not None:
            self.stream.write(data)

    def close(self) -> None:
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()


def main() -> int:
    args = parse_args()
    document = args.document or find_default_document()
    if document is None:
        print("No document provided and Dracula was not found.", file=sys.stderr)
        print(r"Try: python audiobook_reader.py C:\path\to\book.txt", file=sys.stderr)
        return 2

    text = load_document(document, strip_gutenberg=not args.keep_gutenberg)
    chunks = chunk_text(text, args.chunk_size)
    chunks = chunks[args.start_chunk - 1 :]
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]

    if not chunks:
        print("No readable text found.", file=sys.stderr)
        return 2

    print(f"Document: {document}")
    print(f"Model: {args.model}")
    print(f"Voice: {args.voice}")
    print(f"Chunks queued: {len(chunks)}")

    if args.dry_run:
        print("\nFirst chunk preview:\n")
        print(chunks[0][:1200])
        return 0

    if websocket is None:
        print("Missing dependency: websocket-client", file=sys.stderr)
        print("Install with: pip install -r requirements.txt", file=sys.stderr)
        return 2

    api_key = config.OPENAI_API_KEY
    if not api_key:
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        print("Set it first, then run this again.", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    player = LivePlayer(args.play)
    try:
        with wave.open(str(args.output), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(SAMPLE_RATE)

            for offset, chunk in enumerate(chunks, start=args.start_chunk):
                print(f"Narrating chunk {offset} ({len(chunk)} chars)...")
                narrate_chunk(
                    api_key=api_key,
                    model=args.model,
                    voice=args.voice,
                    text=chunk,
                    chunk_number=offset,
                    timeout=args.timeout,
                    wav_file=wav_file,
                    player=player,
                )
    finally:
        player.close()

    print(f"Saved: {args.output.resolve()}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Turn a text document into streamed AI audiobook narration.",
    )
    parser.add_argument(
        "document",
        nargs="?",
        type=Path,
        help="Text, Markdown, or HTML-ish file to narrate. Defaults to the attached Dracula text.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--output", type=Path, default=Path("out/dracula.wav"))
    parser.add_argument("--chunk-size", type=int, default=2600)
    parser.add_argument("--start-chunk", type=int, default=1)
    parser.add_argument("--max-chunks", type=int, default=1, help="0 means narrate the whole document.")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--play", action="store_true", help="Play audio live while also saving WAV.")
    parser.add_argument("--dry-run", action="store_true", help="Show chunking without calling OpenAI.")
    parser.add_argument("--keep-gutenberg", action="store_true", help="Keep Project Gutenberg header/footer.")
    return parser.parse_args()


def find_default_document() -> Path | None:
    for path in DEFAULT_DOCUMENTS:
        if path.exists():
            return path
    return None


def load_document(path: Path, *, strip_gutenberg: bool) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if strip_gutenberg:
        text = remove_gutenberg_matter(text)

    if path.suffix.lower() in {".html", ".htm"}:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_gutenberg_matter(text: str) -> str:
    start = re.search(
        r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if start:
        text = text[start.end() :]

    end = re.search(
        r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if end:
        text = text[: end.start()]

    return text


def chunk_text(text: str, max_chars: int) -> list[str]:
    if max_chars < 800:
        raise ValueError("--chunk-size should be at least 800 characters.")

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for paragraph in paragraphs:
        paragraph = re.sub(r"\s+", " ", paragraph)
        pieces = split_long_paragraph(paragraph, max_chars)

        for piece in pieces:
            extra = len(piece) + (2 if current else 0)
            if current and current_len + extra > max_chars:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0

            current.append(piece)
            current_len += extra

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current.strip())
                current = ""
            pieces.extend(split_at_words(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip()
        if len(candidate) > max_chars and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = candidate

    if current:
        pieces.append(current.strip())

    return pieces


def split_at_words(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in text.split():
        if current and current_len + len(word) + 1 > max_chars:
            pieces.append(" ".join(current))
            current = []
            current_len = 0
        current.append(word)
        current_len += len(word) + 1

    if current:
        pieces.append(" ".join(current))

    return pieces


def narrate_chunk(
    *,
    api_key: str,
    model: str,
    voice: str,
    text: str,
    chunk_number: int,
    timeout: float,
    wav_file: wave.Wave_write,
    player: LivePlayer,
) -> None:
    url = "wss://api.openai.com/v1/realtime?" + urlencode({"model": model})
    headers = [f"Authorization: Bearer {api_key}"]
    ws = websocket.create_connection(url, header=headers, timeout=timeout)

    try:
        update_session(ws, model=model, voice=voice)
        create_audio_response(ws, text=text, chunk_number=chunk_number)
        stream_audio_response(ws, wav_file=wav_file, player=player)
    finally:
        ws.close()


def update_session(ws: Any, *, model: str, voice: str) -> None:
    ws.send(
        json.dumps(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": model,
                    "instructions": NARRATOR_INSTRUCTIONS,
                    "output_modalities": ["audio"],
                    "audio": {
                        "output": {
                            "voice": voice,
                            "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                        },
                    },
                },
            }
        )
    )
    wait_for_event(ws, "session.updated")


def create_audio_response(ws: Any, *, text: str, chunk_number: int) -> None:
    prompt = (
        "Narrate this passage as an audiobook.\n"
        "Speak only the passage text. Do not announce chunk numbers.\n\n"
        f"Passage:\n{text}"
    )
    ws.send(
        json.dumps(
            {
                "type": "response.create",
                "response": {
                    "conversation": "none",
                    "metadata": {"chunk": str(chunk_number)},
                    "output_modalities": ["audio"],
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": prompt}],
                        }
                    ],
                },
            }
        )
    )


def stream_audio_response(
    ws: Any,
    *,
    wav_file: wave.Wave_write,
    player: LivePlayer,
) -> None:
    while True:
        event = receive_json(ws)
        event_type = event.get("type")

        if event_type in {"response.audio.delta", "response.output_audio.delta"}:
            audio = base64.b64decode(event["delta"])
            wav_file.writeframes(audio)
            player.write(audio)
            continue

        if event_type == "response.done":
            response = event.get("response", {})
            status = response.get("status")
            if status and status != "completed":
                details = response.get("status_details") or response
                raise RuntimeError(f"Response did not complete: {details}")
            return

        if event_type == "error":
            raise RuntimeError(format_api_error(event))


def wait_for_event(ws: Any, wanted_type: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        event = receive_json(ws)
        event_type = event.get("type")
        if event_type == wanted_type:
            return event
        if event_type == "error":
            raise RuntimeError(format_api_error(event))
    raise TimeoutError(f"Timed out waiting for {wanted_type}.")


def receive_json(ws: Any) -> dict[str, Any]:
    raw = ws.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def format_api_error(event: dict[str, Any]) -> str:
    error = event.get("error") or event
    if isinstance(error, dict):
        message = error.get("message") or json.dumps(error)
        code = error.get("code")
        return f"{message} ({code})" if code else message
    return str(error)


if __name__ == "__main__":
    raise SystemExit(main())

