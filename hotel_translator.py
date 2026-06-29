import argparse
import base64
import json
import math
import os
import queue
import sys
import threading
import time

import sounddevice as sd
import websocket


RATE = 24_000
MODEL = "gpt-realtime-translate"
URL = f"wss://api.openai.com/v1/realtime/translations?model={MODEL}"


def api_key():
    try:
        import config

        return getattr(config, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    except ImportError:
        return os.environ.get("OPENAI_API_KEY")


def rms16(chunk):
    samples = memoryview(chunk).cast("h")
    if not samples:
        return 0
    return int(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))


def meter(level):
    bars = min(20, level * 20 // 8000)
    return "#" * bars + "-" * (20 - bars)


def send_json(ws, lock, payload):
    with lock:
        ws.send(json.dumps(payload))


def test_mic(device, chunk_frames):
    levels = queue.Queue(maxsize=10)

    def on_mic(indata, frames, timing, status):
        try:
            levels.put_nowait(rms16(bytes(indata)))
        except queue.Full:
            pass

    print("Testing mic for 10 seconds. Talk normally.")
    with sd.RawInputStream(
        samplerate=RATE,
        blocksize=chunk_frames,
        channels=1,
        dtype="int16",
        latency="low",
        device=device,
        callback=on_mic,
    ):
        end = time.time() + 10
        last = 0
        while time.time() < end:
            try:
                last = levels.get(timeout=0.2)
            except queue.Empty:
                pass
            print(f"\rmic [{meter(last)}] {last:5d}", end="", flush=True)
    print("\nIf the bar moved while you talked, Python can hear your mic.")


def main():
    parser = argparse.ArgumentParser(description="Tiny live hotel check-in translator.")
    parser.add_argument("--to", default="es", help="target language code, e.g. es, fr, ja")
    parser.add_argument("--chunk-ms", type=int, default=20, help="mic chunk size")
    parser.add_argument("--input-device", type=int, help="input device number")
    parser.add_argument("--output-device", type=int, help="output device number")
    parser.add_argument("--list-devices", action="store_true", help="show audio devices and exit")
    parser.add_argument("--test-mic", action="store_true", help="show local mic level and exit")
    parser.add_argument("--quiet", action="store_true", help="hide mic level status")
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    chunk_frames = RATE * args.chunk_ms // 1000

    if args.test_mic:
        test_mic(args.input_device, chunk_frames)
        return

    key = api_key()
    if not key:
        sys.exit("Set OPENAI_API_KEY first.")

    mic_chunks = queue.Queue(maxsize=30)
    stop = threading.Event()
    send_lock = threading.Lock()
    stats = {"level": 0, "sent": 0, "dropped": 0}
    stats_lock = threading.Lock()

    safety_id = os.environ.get("OPENAI_SAFETY_IDENTIFIER", "hotel-checkin-demo")

    ws = websocket.WebSocket()
    ws.connect(
        URL,
        header=[
            f"Authorization: Bearer {key}",
            f"OpenAI-Safety-Identifier: {safety_id}",
        ],
    )
    send_json(
        ws,
        send_lock,
        {"type": "session.update", "session": {"audio": {"output": {"language": args.to}}}},
    )

    def on_mic(indata, frames, timing, status):
        if status:
            print(status, file=sys.stderr)
        chunk = bytes(indata)
        with stats_lock:
            stats["level"] = rms16(chunk)
        try:
            mic_chunks.put_nowait(chunk)
        except queue.Full:
            with stats_lock:
                stats["dropped"] += 1

    def send_mic():
        while not stop.is_set():
            try:
                chunk = mic_chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            send_json(
                ws,
                send_lock,
                {
                    "type": "session.input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode("ascii"),
                },
            )
            with stats_lock:
                stats["sent"] += 1

    def show_status():
        while not stop.is_set():
            time.sleep(0.5)
            with stats_lock:
                level = stats["level"]
                sent = stats["sent"]
                dropped = stats["dropped"]
            print(
                f"\rmic [{meter(level)}] sent={sent} dropped={dropped}",
                end="",
                flush=True,
            )

    def receive_translations(speaker):
        while True:
            try:
                event = json.loads(ws.recv())
            except Exception as exc:
                if not stop.is_set():
                    print(f"\nTranslation stream ended: {exc}", file=sys.stderr)
                break
            kind = event.get("type")
            if kind == "session.output_audio.delta":
                speaker.write(base64.b64decode(event["delta"]))
            elif kind == "session.output_transcript.delta":
                print(f"\n> {event['delta']}", end="", flush=True)
            elif kind == "session.input_transcript.delta":
                print(f"\n< {event['delta']}", end="", flush=True)
            elif kind == "error":
                print(f"\n{event}", file=sys.stderr)
            elif kind == "session.closed":
                break

    print(f"Hotel check-in translator -> {args.to}. Speak now. Ctrl+C to stop.")
    print("Use earbuds or keep the speaker away from the mic to avoid audio looping.\n")

    with sd.RawInputStream(
        samplerate=RATE,
        blocksize=chunk_frames,
        channels=1,
        dtype="int16",
        latency="low",
        device=args.input_device,
        callback=on_mic,
    ), sd.RawOutputStream(
        samplerate=RATE,
        blocksize=chunk_frames,
        channels=1,
        dtype="int16",
        latency="low",
        device=args.output_device,
    ) as speaker:
        sender = threading.Thread(target=send_mic, daemon=True)
        receiver = threading.Thread(target=receive_translations, args=(speaker,), daemon=True)
        sender.start()
        receiver.start()
        if not args.quiet:
            threading.Thread(target=show_status, daemon=True).start()
        try:
            while receiver.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            stop.set()
            send_json(ws, send_lock, {"type": "session.close"})
            receiver.join(timeout=8)
        finally:
            stop.set()
            ws.close()


if __name__ == "__main__":
    main()
