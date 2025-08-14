# Value Finder

![Home Page Picture](/HomePage.png)

An automatic pipeline that discovers high-value content on the web, summarizes it,
scores it (value / novelty / interest), and stores everything in a local DB.
The content is exposed via a Streamlit UI. Learns your preferences 

## Stack

- **Tech:** Playwright, SQLite, SentenceTransformers, Ollama, Numpy
- **Pipeline:** crawler → scorer → embeddings → LLM summarizer
scheduler

## What it does

- Crawls configured sources and ingests fresh posts
- Generates short summaries, for high rated posts, with an LLM
- Scores items on **Value**, **Novelty**, and **Interest**
- Creates embeddings for search/ranking
- Saves everything to SQLite for a UI to display and for feedback loops
- **Learns preferences from 👍/👎 feedback** (boosts/demotes similar items over time)
- Repeats loop using a scheduler and queue.

## Run Locally

```
    python db_init.py
    # run these in separate tabs
    python scheduler.py
    python app.py
```
