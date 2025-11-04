#!/usr/bin/env python3
"""
TikTok Playwright Scraper with:
 - Random video selection from a profile using embedded JSON
 - Views, likes, top comments scraping
 - Simulated comment with hashtags
 - Logs and CSV report
 - Environment variable support (ACCOUNT, HEADLESS)
"""

import random
import time
import datetime
import csv
import os
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# -------- CONFIG ----------
ACCOUNT = os.environ.get("ACCOUNT", "poriaktar250")        # TikTok username from env
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"  # run headless

ACCOUNT_URL = f"https://www.tiktok.com/@{ACCOUNT}"
LOG_FILE = "tiktok_playwright_log.txt"
CSV_REPORT = "tiktok_playwright_report.csv"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118 Safari/537.36"
]

CUSTOM_COMMENTS = [
    "Amazing content! 🔥",
    "Love this video 😍",
    "Keep up the great work!",
    "So creative and fun ✨"
]

HASHTAGS = ["#trending", "#foryou", "#viral", "#towsif_aktar", "#towsif_aktar", "#towsif_aktar"]

SCROLL_ITERATIONS = 6
NAV_TIMEOUT_MS = 40000
WAIT_FOR_JSON_MS = 15000
# ---------------------------

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def append_csv_row(row):
    exists = os.path.exists(CSV_REPORT)
    with open(CSV_REPORT, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "video_url", "views", "likes", "top_comments", "simulated_comment", "notes"])
        writer.writerow(row)

def start_browser(playwright, headless=True):
    browser = playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
    return browser

def human_scroll(page, steps=6, pause_min=0.8, pause_max=2.0):
    for _ in range(steps):
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.9);")
        time.sleep(random.uniform(pause_min, pause_max))

def collect_video_links(page, profile_url):
    log(f"Opening profile page: {profile_url}")
    page.goto(profile_url, timeout=NAV_TIMEOUT_MS)
    page.set_extra_http_headers({"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"})
    time.sleep(3 + random.uniform(0, 2))

    # Scroll a bit to trigger JSON loading
    human_scroll(page, steps=SCROLL_ITERATIONS, pause_min=1.0, pause_max=2.0)

    # Extract embedded JSON
    video_links = set()
    try:
        maybe_json = page.evaluate(
            """() => window['SIGI_STATE'] || window['__NEXT_DATA__'] || {}"""
        )
        item_module = maybe_json.get("ItemModule") or maybe_json.get("itemModule") or {}
        for vid_id in item_module.keys():
            video_links.add(f"https://www.tiktok.com/@{ACCOUNT}/video/{vid_id}")
    except Exception as e:
        log(f"Error extracting JSON video links: {e}")

    log(f"Collected {len(video_links)} unique video links from JSON.")
    return list(video_links)

def scrape_video(page, video_url):
    log(f"Navigating to video: {video_url}")
    page.goto(video_url, timeout=NAV_TIMEOUT_MS)
    time.sleep(random.uniform(2.0, 4.5))

    views, likes = "N/A", "N/A"
    top_comments = []

    try:
        v_elem = page.query_selector('strong[data-e2e="video-views"], div[data-e2e="video-views"]')
        if v_elem:
            views = v_elem.inner_text().strip()
    except Exception:
        pass

    try:
        l_elem = page.query_selector('strong[data-e2e="like-count"], div[data-e2e="like-count"]')
        if l_elem:
            likes = l_elem.inner_text().strip()
    except Exception:
        pass

    try:
        comment_selectors = page.query_selector_all('p[data-e2e="comment-level-1"], div[data-e2e="comment-level-1"], p[class*="comment"]')
        for el in comment_selectors[:3]:
            try:
                ct = el.inner_text().strip()
                if ct:
                    top_comments.append(ct)
            except Exception:
                continue
    except Exception:
        pass

    return {
        "url": video_url,
        "views": views,
        "likes": likes,
        "top_comments": top_comments
    }

def simulate_comment():
    fake_comment = random.choice(CUSTOM_COMMENTS)
    chosen_tags = random.sample(HASHTAGS, k=random.randint(3, 6))
    hashtag_str = " ".join(chosen_tags)
    return f"{fake_comment} {hashtag_str}"

def main():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    log("=== TikTok Playwright Headless Scraper Started ===")
    log(f"ACCOUNT: {ACCOUNT} | HEADLESS: {HEADLESS}")

    with sync_playwright() as p:
        browser = start_browser(p, headless=HEADLESS)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS), locale="en-US")
        page = context.new_page()

        try:
            video_links = collect_video_links(page, ACCOUNT_URL)
            if not video_links:
                log("No video links found. Exiting.")
                return

            chosen = random.choice(video_links)
            log(f"Randomly selected video: {chosen}")

            human_scroll(page, steps=1, pause_min=0.6, pause_max=1.2)
            time.sleep(random.uniform(1.0, 2.5))

            result = scrape_video(page, chosen)
            log(f"Scrape result: views={result['views']} likes={result['likes']} comments_found={len(result['top_comments'])}")

            sim_comment = simulate_comment()
            log(f"Simulated comment (not posted): {sim_comment}")

            top_comments_join = " || ".join(result['top_comments']) if result['top_comments'] else ""
            append_csv_row([
                datetime.datetime.now().isoformat(),
                result['url'],
                result['views'],
                result['likes'],
                top_comments_join,
                sim_comment,
                "ok"
            ])

        except PlaywrightTimeoutError as te:
            log(f"Playwright Timeout: {te}")
        except Exception as e:
            log(f"Unhandled error: {e}")
        finally:
            try: page.close()
            except: pass
            try: context.close()
            except: pass
            try: browser.close()
            except: pass

    log("=== Finished ===")

if __name__ == "__main__":
    main()
