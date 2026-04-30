import os
import json
import hashlib
import logging
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

STATE_FILE = "seen_jobs.json"

DESIGN_KEYWORDS = [
    "product designer",
    "ux designer",
    "ui designer",
    "ui/ux",
    "ux/ui",
    "experience designer",
    "digital designer",
    "interaction designer",
    "designer digitale",
    "creative technologist",
    "design lead",
]

FASHION_LUXURY_COMPANIES = [
    "ynap", "moncler", "prada", "zegna", "otb", "diesel", "marni", "armani",
    "dolce & gabbana", "dolce&gabbana", "tod's", "tods", "kering", "gucci",
    "bottega veneta", "lvmh", "ferragamo", "valentino", "versace", "mango",
    "luxottica", "max mara", "akqa", "accenture song", "publicis sapient",
]

INDEED_FEEDS = [
    {
        "name": "Indeed IT — core design titles",
        "url": (
            "https://it.indeed.com/rss?q=%22product+designer%22+OR+%22ux+designer%22"
            "+OR+%22ui+designer%22+OR+%22digital+designer%22"
            "&l=Milano&radius=15&sort=date&fromage=3"
        ),
    },
    {
        "name": "Indeed IT — Italian design titles",
        "url": (
            "https://it.indeed.com/rss?q=%22experience+designer%22+OR+%22interaction+designer%22"
            "+OR+%22designer+digitale%22"
            "&l=Milano&radius=15&sort=date&fromage=3"
        ),
    },
]

LINKEDIN_PARAMS = {
    "keywords": "product designer OR ux designer OR ui designer",
    "location": "Milan, Lombardy, Italy",
    "f_TPR": "r86400",  # last 24 hours
    "start": "0",
}
LINKEDIN_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── State helpers ──────────────────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def job_id(title: str, url: str) -> str:
    return hashlib.sha256(f"{title}|{url}".encode()).hexdigest()


# ── Keyword / label helpers ────────────────────────────────────────────────────

def is_design_role(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in DESIGN_KEYWORDS)


def is_fashion_luxury(company: str) -> bool:
    c = company.lower()
    return any(brand in c for brand in FASHION_LUXURY_COMPANIES)


# ── Source fetchers ────────────────────────────────────────────────────────────

def fetch_indeed(seen: set) -> list[dict]:
    new_jobs = []
    for feed_cfg in INDEED_FEEDS:
        log.info("Fetching %s", feed_cfg["name"])
        try:
            feed = feedparser.parse(feed_cfg["url"])
        except Exception as exc:
            log.error("Error parsing feed %s: %s", feed_cfg["name"], exc)
            continue

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            company = entry.get("author", "")
            if not is_design_role(title):
                continue
            jid = job_id(title, link)
            if jid in seen:
                continue
            seen.add(jid)
            new_jobs.append({
                "title": title,
                "company": company,
                "url": link,
                "source": "Indeed",
                "fashion": is_fashion_luxury(company),
            })
            log.info("New Indeed job: %s @ %s", title, company)

    return new_jobs


def fetch_linkedin(seen: set) -> list[dict]:
    new_jobs = []
    log.info("Fetching LinkedIn jobs")
    try:
        resp = requests.get(
            LINKEDIN_URL,
            params=LINKEDIN_PARAMS,
            headers=LINKEDIN_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.error("LinkedIn fetch failed: %s", exc)
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li")
        for card in cards:
            title_el = card.select_one(".base-search-card__title")
            company_el = card.select_one(".base-search-card__subtitle")
            link_el = card.select_one("a.base-card__full-link")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            link = link_el["href"].split("?")[0] if link_el else ""
            if not is_design_role(title):
                continue
            jid = job_id(title, link)
            if jid in seen:
                continue
            seen.add(jid)
            new_jobs.append({
                "title": title,
                "company": company,
                "url": link,
                "source": "LinkedIn",
                "fashion": is_fashion_luxury(company),
            })
            log.info("New LinkedIn job: %s @ %s", title, company)
    except Exception as exc:
        log.error("LinkedIn parse error: %s", exc)

    return new_jobs


# ── Email ──────────────────────────────────────────────────────────────────────

def build_email_html(jobs: list[dict]) -> str:
    rows = ""
    for j in jobs:
        badge = " ⭐" if j["fashion"] else ""
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;">
            <a href="{j['url']}" style="font-weight:600;color:#1a1a1a;text-decoration:none;">
              {j['title']}{badge}
            </a><br>
            <span style="color:#555;font-size:13px;">{j['company'] or '—'}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#888;font-size:13px;white-space:nowrap;">
            {j['source']}
          </td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;color:#1a1a1a;max-width:640px;margin:0 auto;padding:20px;">
  <h2 style="margin-bottom:4px;">🎯 {len(jobs)} nuove offerte design a Milano</h2>
  <p style="color:#666;font-size:13px;margin-top:0;">
    {datetime.now().strftime("%A %d %B %Y, %H:%M")} — ⭐ = azienda fashion/luxury
  </p>
  <table style="width:100%;border-collapse:collapse;margin-top:16px;">
    <thead>
      <tr style="background:#f5f5f5;">
        <th style="padding:8px 12px;text-align:left;font-size:13px;">Posizione</th>
        <th style="padding:8px 12px;text-align:left;font-size:13px;">Fonte</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="font-size:12px;color:#aaa;margin-top:24px;">
    Generato da milan-job-alert · GitHub Actions
  </p>
</body>
</html>"""


def send_email(jobs: list[dict]) -> None:
    api_key = os.environ["SENDGRID_API_KEY"]
    email_from = os.environ["EMAIL_FROM"]
    email_to = os.environ["EMAIL_TO"]

    payload = {
        "personalizations": [{"to": [{"email": email_to}]}],
        "from": {"email": email_from},
        "subject": f"[Job Alert] {len(jobs)} nuove offerte design Milano",
        "content": [{"type": "text/html", "value": build_email_html(jobs)}],
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    log.info("Email sent: %d jobs (status %s)", len(jobs), resp.status_code)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    seen = load_seen()
    log.info("Loaded %d seen job IDs", len(seen))

    new_jobs: list[dict] = []
    new_jobs += fetch_indeed(seen)
    new_jobs += fetch_linkedin(seen)

    save_seen(seen)
    log.info("Saved state (%d total seen)", len(seen))

    if not new_jobs:
        log.info("No new jobs found.")
        return

    log.info("Found %d new jobs — sending email", len(new_jobs))
    send_email(new_jobs)


if __name__ == "__main__":
    main()
