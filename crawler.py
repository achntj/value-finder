# crawler.py
from playwright.sync_api import sync_playwright
from newspaper import Article
import sqlite3
import datetime
import time
import requests
from bs4 import BeautifulSoup
import random
from config import INTEREST_CONFIG

DATABASE = "database.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WebScout/1.0)"}
CRAWL_INTERVAL = 3600  # 1 hour between crawls

TARGETED_SOURCES = {
    "ai_tech": [
        "https://arxiv.org/list/cs.AI/recent",
        "https://lobste.rs/t/ai",
        "https://news.ycombinator.com/",
    ],
    "productivity": [
        "https://news.ycombinator.com/",
        "https://www.reddit.com/r/productivity/",
        "https://www.reddit.com/r/Zettelkasten/",
    ],
    "startups": [
        "https://www.indiehackers.com/",
        "https://news.ycombinator.com/",
        "https://www.reddit.com/r/startups/",
    ],
    "philosophy": [
        "https://www.reddit.com/r/philosophy/",
        "https://news.ycombinator.com/",
        "https://www.reddit.com/r/Stoicism/",
    ],
    "writing": [
        "https://www.reddit.com/r/writing/",
        "https://news.ycombinator.com/",
        "https://www.reddit.com/r/KeepWriting/",
    ],
    "markets": [
        "https://www.reddit.com/r/investing/",
        "https://www.reddit.com/r/economy/",
        "https://news.ycombinator.com/",
    ],
    "serendipity": [
        "https://news.ycombinator.com/newest",
        "https://www.reddit.com/r/all/",
        "https://www.reddit.com/r/Serendipity/",
    ],
}


def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                return ""
            soup = BeautifulSoup(res.text, "html.parser")

            # Try to find main content
            article = soup.find("article")
            if article:
                return article.get_text()

            # Fallback to paragraph collection
            paragraphs = soup.find_all("p")
            return "\n".join(p.get_text() for p in paragraphs if p.get_text())
        except Exception:
            return ""


def post_exists(conn, post_id):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,))
    exists = cursor.fetchone() is not None
    return exists


def save_post(conn, post):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO posts 
        (id, title, url, content, source, created_at, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            post["id"],
            post["title"],
            post["url"],
            post["content"],
            post["source"],
            post["created_at"],
            post["created_at"],
        ),
    )
    conn.commit()


def scrape_targeted_sources():
    conn = sqlite3.connect(DATABASE)

    # Rotate through categories to ensure coverage
    category = random.choice(list(INTEREST_CONFIG["categories"].keys()))
    sources = TARGETED_SOURCES[category]

    print(f"Scraping sources for category: {category}")

    for source in sources:
        if "hackernews" in source:
            scrape_hacker_news(conn, limit=10)
        elif "reddit" in source:
            subreddit = source.split("/")[-2] if "/" in source else "all"
            scrape_reddit_subreddit(conn, subreddit=subreddit, limit=10)
        elif "arxiv" in source:
            scrape_arxiv(conn)
        elif "indiehackers" in source:
            scrape_indie_hackers(conn)

    conn.close()


def scrape_hacker_news(conn, limit=30):
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.goto("https://news.ycombinator.com/")
        posts_fetched = 0

        items = page.query_selector_all("tr.athing")
        for item in items:
            if posts_fetched >= limit:
                break

            post_id = item.get_attribute("id")
            if not post_id or post_exists(conn, post_id):
                continue

            title_link = item.query_selector(".titleline a")
            if not title_link:
                continue

            title = title_link.inner_text().strip()
            external_url = title_link.get_attribute("href")
            hn_comments_url = f"https://news.ycombinator.com/item?id={post_id}"

            article_text = (
                extract_article_text(external_url)
                if external_url.startswith("http")
                else ""
            )

            if not article_text:
                article_text = extract_article_text(hn_comments_url)

            content = title + "\n\n" + article_text.strip()

            post = {
                "id": post_id,
                "title": title,
                "url": (
                    external_url if external_url.startswith("http") else hn_comments_url
                ),
                "content": content,
                "source": "hackernews",
                "created_at": datetime.datetime.utcnow(),
            }

            save_post(conn, post)
            posts_fetched += 1
            print(f"Saved HN post: {title[:60]}...")

        browser.close()
        print(f"Finished scraping {posts_fetched} Hacker News posts.")


def scrape_reddit_subreddit(conn, subreddit="all", limit=20):
    print(f"Scraping Reddit r/{subreddit}...")
    url = f"https://old.reddit.com/r/{subreddit}/"
    fetched = 0

    while fetched < limit and url:
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            print(f"Error fetching Reddit: {res.status_code}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        entries = soup.find_all("div", class_="thing")

        for entry in entries:
            if fetched >= limit:
                break

            post_id = entry.get("data-fullname")
            if not post_id or post_exists(conn, post_id):
                continue

            title_tag = entry.find("a", class_="title")
            if not title_tag:
                continue

            title = title_tag.text.strip()
            post_url = entry.get("data-url")
            if post_url and post_url.startswith("/"):
                post_url = "https://old.reddit.com" + post_url

            selftext_div = entry.find("div", class_="expando")
            snippet = (
                selftext_div.text.strip()[:500]
                if selftext_div and selftext_div.text.strip()
                else ""
            )

            article_text = (
                extract_article_text(post_url)
                if post_url and post_url.startswith("http")
                else ""
            )

            content = title + "\n\n" + snippet
            if article_text:
                content += "\n\n" + article_text

            post = {
                "id": post_id,
                "title": title,
                "url": post_url if post_url else "",
                "content": content,
                "source": "reddit",
                "created_at": datetime.datetime.utcnow(),
            }

            save_post(conn, post)
            fetched += 1
            print(f"Saved Reddit post: {title[:60]}...")

        next_btn = soup.find("span", class_="next-button")
        url = next_btn.a["href"] if next_btn else None
        time.sleep(2)  # Be polite

    print(f"Finished scraping Reddit, fetched {fetched} posts.")


def scrape_arxiv(conn):
    print("Scraping arXiv for AI papers...")
    url = "http://arxiv.org/list/cs.AI/recent"
    res = requests.get(url, headers=HEADERS)

    if res.status_code != 200:
        print(f"Error fetching arXiv: {res.status_code}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    papers = soup.find_all("div", class_="meta")

    for paper in papers[:10]:  # Limit to 10 papers
        title = (
            paper.find("div", class_="list-title").text.replace("Title: ", "").strip()
        )
        authors = (
            paper.find("div", class_="list-authors")
            .text.replace("Authors: ", "")
            .strip()
        )
        abstract = paper.find("p", class_="mathjax").text.strip()
        paper_id = (
            paper.find("div", class_="list-identifier").text.strip().split(" ")[0]
        )
        paper_url = f"https://arxiv.org/abs/{paper_id.split(':')[-1]}"

        content = f"{title}\n\nAuthors: {authors}\n\nAbstract: {abstract}"

        post = {
            "id": paper_id,
            "title": title,
            "url": paper_url,
            "content": content,
            "source": "arxiv",
            "created_at": datetime.datetime.utcnow(),
        }

        if not post_exists(conn, paper_id):
            save_post(conn, post)
            print(f"Saved arXiv paper: {title[:60]}...")


def scrape_indie_hackers(conn):
    print("Scraping Indie Hackers...")
    url = "https://www.indiehackers.com/"
    res = requests.get(url, headers=HEADERS)

    if res.status_code != 200:
        print(f"Error fetching Indie Hackers: {res.status_code}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    posts = soup.find_all("div", class_="feed-item")

    for post in posts[:10]:  # Limit to 10 posts
        title_tag = post.find("a", class_="feed-item__title")
        if not title_tag:
            continue

        title = title_tag.text.strip()
        post_url = "https://www.indiehackers.com" + title_tag["href"]
        post_id = post_url.split("/")[-1]

        content_tag = post.find("div", class_="feed-item__content")
        content = content_tag.text.strip() if content_tag else ""

        post_data = {
            "id": post_id,
            "title": title,
            "url": post_url,
            "content": f"{title}\n\n{content}",
            "source": "indiehackers",
            "created_at": datetime.datetime.utcnow(),
        }

        if not post_exists(conn, post_id):
            save_post(conn, post_data)
            print(f"Saved Indie Hackers post: {title[:60]}...")


if __name__ == "__main__":
    # Initialize database
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            content TEXT,
            summary TEXT,
            source TEXT,
            topic TEXT,
            score REAL,
            embedding BLOB,
            created_at TIMESTAMP,
            last_updated TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()

    # Run targeted scraping
    scrape_targeted_sources()
