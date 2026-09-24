# Contextual Spanish Spaced-Repetition Trainer

IE University · SDD/DevOps Assignment 1.

## Setup and run

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
python app.py
```

The app binds to `0.0.0.0` on port `8000` by default.

## Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Server port |
| `DATA_DIR` | `./data` | Where `trainer.db` will live |
| `SCHEDULER` | `sm2` | Scheduling algorithm |
| `NEW_CARDS_PER_DAY` | `15` | Daily new-card limit |
