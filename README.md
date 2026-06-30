# Realtime API Examples

This repository contains a set of small Python example projects demonstrating realtime and related examples. Each example is self-contained in its own folder with a `requirements.txt` and a small runner script.

Contents
- `audiobook/` — audiobook reader example (uses `audiobook_reader.py`, includes `pg345.txt` sample text).
- `hello-world/` — minimal realtime example (`minimal_realtime.py`).
- `sip/` — simple SIP/webhook example server (`app.py`).
- `translation/` — hotel translation example (`hotel_translator.py`).

Quick start

Prerequisites
- Python 3.8+ installed.
- Recommended: create a virtual environment per project.

Install dependencies (example)

```
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r audiobook/requirements.txt
```

Run an example

- Audiobook reader

```
cd audiobook
python audiobook_reader.py
```

- Hello world realtime

```
cd hello-world
python minimal_realtime.py
```

- SIP example

```
cd sip
python app.py
```

- Translation example

```
cd translation
python hotel_translator.py
```

Notes
- Each folder contains a `config.py` for local configuration. Review and update it before running examples.
- If an example requires sample data (for example `audiobook/pg345.txt`), ensure the file is present in the folder.

See https://www.meetup.com/practical-chatgpt-api-programming/events/315367955 for more info
