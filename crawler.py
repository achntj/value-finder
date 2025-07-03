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
import logging
import re
import hashlib
from urllib.parse import urljoin  # For resolving relative URLs

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATABASE = "database.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WebScout/1.0)"}
SOURCE_QUALITY_THRESHOLD = 0.6

def get_db_connection():
    return sqlite3.connect(DATABASE)

def discover_new_sources(url, content):
    """Discover new potential sources from page content"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        soup = BeautifulSoup(content, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Resolve relative URLs
            absolute_url = urljoin(url, href)
            # Filter out non-http links
            if not absolute_url.startswith("http"):
                continue
            # Normalize URL
            normalized_url = absolute_url.split('#')[0].split('?')[0]
            links.add(normalized_url)
        
        for link in links:
            # Filter out non-content links
            if any(ext in link for ext in ['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.css', '.js']):
                continue
                
            # Check if source already exists
            cursor.execute("SELECT 1 FROM discovered_sources WHERE url = ?", (link,))
            if cursor.fetchone():
                continue
                
            # Determine source type
            source_type = "unknown"
            if "reddit.com" in link:
                source_type = "reddit"
            elif "arxiv.org" in link:
                source_type = "arxiv"
            elif "github.com" in link:
                source_type = "github"
            elif "substack.com" in link:
                source_type = "substack"
            elif "medium.com" in link:
                source_type = "medium"
            elif "ycombinator.com" in link:
                source_type = "hackernews"
            elif "twitter.com" in link:
                source_type = "twitter"
                
            # Add new source
            cursor.execute("""
                INSERT OR IGNORE INTO discovered_sources 
                (url, source_type, discovery_method, parent_url, quality_score)
                VALUES (?, ?, ?, ?, ?)
            """, (link, source_type, "link_follow", url, 1.0))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Discovery failed for {url}: {str(e)}")
    finally:
        conn.close()

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

def scrape_hacker_news(limit=30):
    conn = get_db_connection()
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto("https://news.ycombinator.com/")
            
            # Capture page content for source discovery
            page_content = page.content()
            discover_new_sources("https://news.ycombinator.com", page_content)
            
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
                logger.info(f"Saved HN post: {title[:60]}...")

            browser.close()
            logger.info(f"Finished scraping {posts_fetched} Hacker News posts.")
    finally:
        conn.close()

def scrape_reddit_subreddit(subreddit="all", limit=20):
    logger.info(f"Scraping Reddit r/{subreddit}...")
    url = f"https://old.reddit.com/r/{subreddit}/"
    fetched = 0

    conn = get_db_connection()
    try:
        while fetched < limit and url:
            res = requests.get(url, headers=HEADERS)
            if res.status_code != 200:
                logger.error(f"Error fetching Reddit: {res.status_code}")
                break

            # Discover sources from page content
            discover_new_sources(url, res.text)
                
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
                logger.info(f"Saved Reddit post: {title[:60]}...")

            next_btn = soup.find("span", class_="next-button")
            url = next_btn.a["href"] if next_btn else None
            time.sleep(2)  # Be polite

        logger.info(f"Finished scraping Reddit, fetched {fetched} posts.")
    finally:
        conn.close()

def scrape_arxiv():
    logger.info("Scraping arXiv for AI papers...")
    url = "https://arxiv.org/list/cs.AI/recent"
    conn = get_db_connection()
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            logger.error(f"Failed to fetch arXiv: {res.status_code}")
            return
            
        # Discover sources from page content
        discover_new_sources(url, res.text)
            
        soup = BeautifulSoup(res.text, "html.parser")
        papers = soup.select("dt + dd")  # Get all dd elements following dt

        if not papers:
            logger.warning("No papers found on arXiv page")
            return

        for paper in papers[:10]:  # Limit to 10 papers
            try:
                # Get the preceding dt element which contains the ID and links
                dt = paper.find_previous("dt")
                if not dt:
                    continue

                # Extract paper ID and URL
                paper_link = dt.find("a", href=lambda x: x and "/abs/" in x)
                if not paper_link:
                    continue

                paper_id = paper_link.get("id")
                paper_url = f"https://arxiv.org{paper_link['href']}"

                # Extract title
                title_tag = paper.find("div", class_="list-title")
                if not title_tag:
                    continue
                title = title_tag.text.replace("Title:", "").strip()

                # Extract authors
                authors_tag = paper.find("div", class_="list-authors")
                authors = (
                    authors_tag.text.replace("Authors:", "").strip()
                    if authors_tag
                    else "Unknown"
                )

                # Extract abstract - look in both meta and abstract div
                abstract = ""
                abstract_tag = paper.find("p", class_="mathjax")
                if not abstract_tag:
                    abstract_tag = paper.find("div", class_="abstract")
                if abstract_tag:
                    abstract = abstract_tag.text.replace("Abstract:", "").strip()

                # Extract subjects/categories
                subjects_tag = paper.find("div", class_="list-subjects")
                subjects = (
                    subjects_tag.text.replace("Subjects:", "").strip()
                    if subjects_tag
                    else ""
                )

                content = f"Title: {title}\n\nAuthors: {authors}\n\nSubjects: {subjects}\n\nAbstract: {abstract or 'No abstract available'}"

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
                    logger.info(f"Saved arXiv paper: {title[:60]}...")
                else:
                    logger.debug(f"Skipping existing paper: {title[:60]}...")

            except Exception as e:
                logger.error(f"Error processing arXiv paper: {str(e)}")
                continue
    finally:
        conn.close()

def scrape_indie_hackers():
    logger.info("Scraping Indie Hackers...")
    url = "https://www.indiehackers.com/"
    conn = get_db_connection()
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            logger.error(f"Error fetching Indie Hackers: {res.status_code}")
            return
            
        # Discover sources from page content
        discover_new_sources(url, res.text)
            
        soup = BeautifulSoup(res.text, "html.parser")
        posts = soup.find_all("div", class_="feed-item")

        for post in posts[:10]:  # Limit to 10 posts
            title_tag = post.find("a", class_="feed-item__title")
            if not title_tag:
                continue

            title = title_tag.text.strip()
            post_url = "https://www.indiehackers.com" + title_tag["href"]
            post_id = hashlib.md5(post_url.encode()).hexdigest()

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
                logger.info(f"Saved Indie Hackers post: {title[:60]}...")
    finally:
        conn.close()

def scrape_source(url, source_type):
    """Scrape content from a specific source"""
    logger.info(f"Scraping source: {url}")
    
    if "ycombinator" in url:
        scrape_hacker_news()
    elif "reddit" in url:
        subreddit = url.split("/")[-2] if "/" in url else "all"
        scrape_reddit_subreddit(subreddit=subreddit)
    elif "arxiv" in url:
        scrape_arxiv()
    elif "indiehackers" in url:
        scrape_indie_hackers()
    else:
        # Generic webpage scraping
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                logger.warning(f"Failed to fetch {url}: {res.status_code}")
                return
                
            # Discover sources from main page
            discover_new_sources(url, res.text)
            
            soup = BeautifulSoup(res.text, "html.parser")
            articles = soup.find_all("article") or soup.select(".post, .article, .entry")
            
            conn = get_db_connection()
            try:
                for article in articles[:10]:  # Limit to 10 articles per page
                    title_elem = article.find(["h1", "h2", "h3"])
                    link_elem = article.find("a", href=True)
                    
                    if not title_elem or not link_elem:
                        continue
                        
                    title = title_elem.text.strip()
                    link = link_elem["href"]
                    
                    if not link.startswith("http"):
                        link = urljoin(url, link)
                        
                    post_id = hashlib.md5(link.encode()).hexdigest()
                    
                    if post_exists(conn, post_id):
                        continue
                        
                    content = extract_article_text(link)
                    
                    post = {
                        "id": post_id,
                        "title": title,
                        "url": link,
                        "content": content,
                        "source": source_type,
                        "created_at": datetime.datetime.utcnow(),
                    }
                    
                    save_post(conn, post)
                    logger.info(f"Saved post: {title[:60]}...")
                    
                    # Discover new sources from content
                    if content:
                        discover_new_sources(url, content)
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")

def scrape_active_sources():
    """Scrape all active sources in rotation"""
    logger.info("Scraping active sources...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get active sources ordered by quality and last crawled
        cursor.execute("""
            SELECT url, source_type 
            FROM discovered_sources 
            WHERE is_active = 1
            ORDER BY quality_score DESC, last_crawled ASC
            LIMIT 5
        """)
        
        sources = cursor.fetchall()
    finally:
        conn.close()
    
    for url, source_type in sources:
        scrape_source(url, source_type)
        
        # Update last_crawled timestamp
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE discovered_sources 
                SET last_crawled = ?
                WHERE url = ?
            """, (datetime.datetime.utcnow().isoformat(), url))
            conn.commit()
        finally:
            conn.close()
        
        # Be polite between sources
        time.sleep(random.uniform(1, 3))

if __name__ == "__main__":
    # Run scraping of active sources
    scrape_active_sources()
