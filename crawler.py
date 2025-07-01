from playwright.sync_api import sync_playwright
from newspaper import Article
import sqlite3
import datetime
import time
import requests
from bs4 import BeautifulSoup

DATABASE = "database.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WebScout/1.0)"}


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
            # Fallback basic extraction: all <p> tags
            paragraphs = soup.find_all("p")
            return "\n".join(p.get_text() for p in paragraphs if p.get_text())
        except Exception:
            return ""


def post_exists(post_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def save_post(post):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO posts (id, title, url, content, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (post["id"], post["title"], post["url"], post["content"], post["source"], post["created_at"]))
    conn.commit()
    conn.close()


def scrape_hacker_news(limit=30):
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
            if not post_id or post_exists(post_id):
                continue

            title_link = item.query_selector(".titleline a")
            if not title_link:
                continue

            title = title_link.inner_text().strip()
            external_url = title_link.get_attribute("href")
            hn_comments_url = f"https://news.ycombinator.com/item?id={post_id}"

            article_text = ""
            # Use external article content if valid HTTP link
            if external_url and external_url.startswith("http"):
                article_text = extract_article_text(external_url)

            # If no article or it's an internal HN link, use comments page
            if not article_text:
                article_text = extract_article_text(hn_comments_url)

            content = title + "\n\n" + article_text.strip()

            post = {
                "id": post_id,
                "title": title,
                "url": external_url if external_url.startswith("http") else hn_comments_url,
                "content": content,
                "source": "hackernews",
                "created_at": datetime.datetime.utcnow()
            }

            save_post(post)
            posts_fetched += 1
            print(f"Saved HN post: {title[:60]}...")

        browser.close()
        print(f"Finished scraping {posts_fetched} Hacker News posts.")

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            content TEXT,
            source TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def scrape_reddit_subreddit(subreddit="all", limit=50):
    print(f"Scraping Reddit r/{subreddit}...")
    url = f"https://old.reddit.com/r/{subreddit}/"
    posts = []
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
            if not post_id or post_exists(post_id):
                continue

            title_tag = entry.find("a", class_="title")
            if not title_tag:
                continue
            title = title_tag.text.strip()
            post_url = entry.get("data-url")
            # Handle relative URLs
            if post_url and post_url.startswith("/"):
                post_url = "https://old.reddit.com" + post_url

            selftext_div = entry.find("div", class_="expando")
            snippet = ""
            if selftext_div and selftext_div.text.strip():
                snippet = selftext_div.text.strip()[:500]

            article_text = ""
            if post_url and post_url.startswith("http"):
                article_text = extract_article_text(post_url)

            content = title + "\n\n" + snippet
            if article_text:
                content += "\n\n" + article_text

            post = {
                "id": post_id,
                "title": title,
                "url": post_url if post_url else "",
                "content": content,
                "source": "reddit",
                "created_at": datetime.datetime.utcnow()
            }
            save_post(post)
            fetched += 1
            print(f"Saved Reddit post: {title[:60]}...")

        next_btn = soup.find("span", class_="next-button")
        url = next_btn.a["href"] if next_btn else None
        time.sleep(2)  # Be polite

    print(f"Finished scraping Reddit, fetched {fetched} posts.")


if __name__ == "__main__":
    init_db()
    scrape_reddit_subreddit(subreddit="all", limit=30)
    scrape_hacker_news(limit=30)

