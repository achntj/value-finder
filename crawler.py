from playwright.sync_api import sync_playwright
import requests
import sqlite3

DATABASE = "database.db"

def create_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT,
            content TEXT,
            score INTEGER,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def scrape_hacker_news():
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.goto("https://news.ycombinator.com/")
        posts = []

        for item in page.query_selector_all("tr.athing"):
            titleline = item.query_selector(".titleline")
            if not titleline:
                continue

            link = titleline.query_selector("a")
            if not link:
                continue

            title = link.inner_text()
            url = link.get_attribute("href")
            post_id = item.get_attribute("id")
            posts.append((post_id, "Hacker News", title, url, None, None, None))

        browser.close()
    return posts

def scrape_reddit(subreddit="technology"):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    data = response.json()

    posts = [
        (
            str(post["data"]["id"]),
            "Reddit",
            post["data"]["title"],
            post["data"]["url"],
            post["data"]["selftext"],
            post["data"]["score"],
            post["data"]["created_utc"],
        )
        for post in data["data"]["children"]
    ]
    return posts

def save_to_db(posts):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR IGNORE INTO posts (id, source, title, url, content, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, posts)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_db()
    hn_posts = scrape_hacker_news()
    reddit_posts = scrape_reddit("technology")
    save_to_db(hn_posts + reddit_posts)

