#!/usr/bin/env python3
"""
tiktok_playwright_scraper.py
Playwright-based headless scraper that:
 - visits a TikTok profile,
 - collects video links (by waiting & scrolling),
 - picks a random video,
 - scrapes views, likes and up to 3 top comments,
 - logs results to a timestamped log file and writes a CSV report.

No proxies required. No comment posting (simulated only).
"""

import random
import time
import datetime
import csv
import os
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# -------- CONFIG ----------
ACCOUNT = "poriaktar250"                    # TikTok username (without @)
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

HASHTAGS = ["#trending", "#foryou", "#viral", "#awesome"]

SCROLL_ITERATIONS = 6      # how many times to scroll on profile to load videos
MAX_VIDEO_LINKS = 50       # maximum video links to collect
NAV_TIMEOUT_MS = 30000     # navigation timeout in milliseconds
WAIT_FOR_VIDEO_SELECTOR_MS = 15000  # wait for video anchors
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
    # Launch Chromium with some stealthy args
    browser = playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
    return browser

def human_scroll(page, steps=6, pause_min=0.8, pause_max=2.0):
    """Scroll the page a few times to load dynamic content."""
    for i in range(steps):
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.9);")
        time.sleep(random.uniform(pause_min, pause_max))

def collect_video_links(page, profile_url, scroll_iterations=SCROLL_ITERATIONS, max_links=MAX_VIDEO_LINKS):
    """
    Visit the profile URL and collect links that contain '/video/'.
    Returns a list of absolute URLs.
    """
    log(f"Opening profile page: {profile_url}")
    page.goto(profile_url, timeout=NAV_TIMEOUT_MS)
    # choose a random UA per session
    ua = random.choice(USER_AGENTS)
    try:
        # attempt to set UA for the page context (works best if set prior to new page)
        page.set_extra_http_headers({"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    except Exception:
        pass

    # Wait for video anchors to appear (best-effort)
    try:
        page.wait_for_selector("a[href*=\"/video/\"]", timeout=WAIT_FOR_VIDEO_SELECTOR_MS)
    except PlaywrightTimeoutError:
        log("Timed out waiting for video links to appear (profile may be private or heavily JS-based).")

    # Scroll a few times to load more videos
    links = set()
    for i in range(scroll_iterations):
        human_scroll(page, steps=2, pause_min=1.0, pause_max=2.5)
        # collect anchors
        anchors = page.query_selector_all('a[href*="/video/"]')
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if href and "/video/" in href:
                    # normalize
                    if href.startswith("/"):
                        href = urljoin("https://www.tiktok.com", href)
                    links.add(href.split("?")[0])  # strip query params
                    if len(links) >= max_links:
                        break
            except Exception:
                continue
        if len(links) >= max_links:
            break
        # small random wait before next scroll iteration
        time.sleep(random.uniform(0.8, 2.0))

    links_list = list(links)
    log(f"Collected {len(links_list)} unique video links from profile.")
    return links_list

def scrape_video(page, video_url):
    """
    Navigate to the video page and extract views, likes and up to 3 top comments.
    Returns dict with scraped data.
    """
    log(f"Navigating to video: {video_url}")
    page.goto(video_url, timeout=NAV_TIMEOUT_MS)
    # wait for page to render important elements
    time.sleep(random.uniform(2.0, 4.5))

    # Try to extract via data-e2e attributes first
    views, likes = "N/A", "N/A"
    top_comments = []

    # Best-effort selectors (TikTok changes often)
    try:
        # views
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

    # Try alternate approach: look for numeric text near icons
    try:
        if views == "N/A":
            maybe_views = page.query_selector_all('strong')
            for el in maybe_views:
                txt = el.inner_text().strip()
                if txt and ("views" in txt.lower() or txt.replace(",", "").isdigit()):
                    views = txt
                    break
    except Exception:
        pass

    # collect up to 3 comments
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

    # Final fallback: attempt to extract JSON state embedded in page
    if (views == "N/A" or likes == "N/A") and not top_comments:
        try:
            # Attempt to read window.__INITIAL_DATA__ or SIGI_STATE if available
            maybe_json = page.evaluate("""() => {
                try {
                    return window['SIGI_STATE'] || window['__INITIAL_DATA__'] || window['__NEXT_DATA__'] || null;
                } catch(e) {
                    return null;
                }
            }""")
            if isinstance(maybe_json, dict):
                # try to find item module or stats
                item_module = maybe_json.get("ItemModule") or maybe_json.get("itemModule")
                if isinstance(item_module, dict):
                    # there may be one item keyed by id
                    for vid, meta in item_module.items():
                        stats = meta.get("stats") or {}
                        if stats:
                            views = stats.get("playCount", views)
                            likes = stats.get("diggCount", likes)
                            break
        except Exception:
            pass

    # return result
    return {
        "url": video_url,
        "views": views,
        "likes": likes,
        "top_comments": top_comments
    }

def simulate_comment():
    fake_comment = random.choice(CUSTOM_COMMENTS)
    fake_tags = " ".join(random.sample(HASHTAGS, min(2, len(HASHTAGS))))
    return f"{fake_comment} {fake_tags}"

def main(headless=True):
    # reset logs
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    log("=== TikTok Playwright Headless Scraper Started ===")

    with sync_playwright() as p:
        browser = start_browser(p, headless=headless)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS), locale="en-US")
        page = context.new_page()

        try:
            # collect video links
            video_links = collect_video_links(page, ACCOUNT_URL, scroll_iterations=SCROLL_ITERATIONS, max_links=MAX_VIDEO_LINKS)

            if not video_links:
                # Try mobile variant if main failed
                log("No links found on www; trying mobile site (m.tiktok.com)")
                mobile_profile = ACCOUNT_URL.replace("www.tiktok.com", "m.tiktok.com")
                video_links = collect_video_links(page, mobile_profile, scroll_iterations=SCROLL_ITERATIONS, max_links=MAX_VIDEO_LINKS)

            if not video_links:
                log("No video links found. Exiting.")
                return

            chosen = random.choice(video_links)
            log(f"Randomly selected video: {chosen}")

            # Scrape the chosen video; do small human-like wait and interactions
            # small human action: scroll a bit before scraping
            human_scroll(page, steps=1, pause_min=0.6, pause_max=1.2)
            time.sleep(random.uniform(1.0, 2.5))

            result = scrape_video(page, chosen)
            log(f"Scrape result: views={result['views']} likes={result['likes']} comments_found={len(result['top_comments'])}")

            # Simulate a comment (log only)
            sim_comment = simulate_comment()
            log(f"Simulated comment (not posted): {sim_comment}")

            # Save to CSV report
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
            try:
                page.close()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    log("=== Finished ===")

if __name__ == "__main__":
    # headless=True runs without opening a visible browser window
    main(headless=True)
