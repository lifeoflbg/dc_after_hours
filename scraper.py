"""
DC Cultural & Policy Events Aggregator
=======================================
Sources:
  THINK TANKS    — Brookings, CATO, Heritage Foundation, CFR
  SMITHSONIAN    — si.edu/events (all museums + zoo)
  SHAKESPEARE    — Folger Shakespeare Library
  CULTURAL CTR   — Kennedy Center, National Gallery of Art,
                   Library of Congress, Mexican Cultural Institute,
                   French Embassy / Alliance Française,
                   Italian Cultural Institute, Korean Cultural Center,
                   Goethe-Institut (German), British Council DC
  EMBASSIES      — Eventbrite embassy/culture aggregator,
                   Passport DC (Events DC),
                   Embassy Experiences

Generates:
  docs/events.json  — consumed by the GitHub Pages site
  docs/events.ics   — iCal feed for calendar apps / Squarespace
"""

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event as ICalEvent
from datetime import datetime, timezone, date
import uuid, json, re, logging, os
from dataclasses import dataclass, field
from typing import Optional
from dateutil import parser as dateparser
from dateutil.tz import gettz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
EASTERN = gettz("America/New_York")
TIMEOUT = 18


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class DCEvent:
    title: str
    url: str
    source: str
    category: str            # one of the CATEGORIES keys
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    description: str = ""
    location: str = ""


# ── Category taxonomy ─────────────────────────────────────────────────────────
# Each source maps to one of these display categories.

CATEGORIES = {
    "Think Tanks":       "#4a9eff",   # blue
    "Smithsonian":       "#f97316",   # orange
    "Shakespeare":       "#a78bfa",   # violet
    "Cultural Centers":  "#4ecf8a",   # green
    "Embassies":         "#f472b6",   # pink
}

SOURCE_META = {
    # Think Tanks
    "Brookings Institution":            "Think Tanks",
    "CATO Institute":                   "Think Tanks",
    "Heritage Foundation":              "Think Tanks",
    "Council on Foreign Relations":     "Think Tanks",
    # Smithsonian
    "Smithsonian Institution":          "Smithsonian",
    # Shakespeare
    "Folger Shakespeare Library":       "Shakespeare",
    # Cultural Centers
    "Kennedy Center":                   "Cultural Centers",
    "National Gallery of Art":          "Cultural Centers",
    "Library of Congress":              "Cultural Centers",
    "Mexican Cultural Institute":       "Cultural Centers",
    "Alliance Française DC":            "Cultural Centers",
    "Italian Cultural Institute":       "Cultural Centers",
    "Korean Cultural Center":           "Cultural Centers",
    "Goethe-Institut Washington":       "Cultural Centers",
    "British Council DC":               "Cultural Centers",
    # Embassies
    "Embassy Events (Eventbrite)":      "Embassies",
    "Passport DC":                      "Embassies",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_soup(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        log.warning(f"  ✗ fetch failed [{url}]: {e}")
        return None


def safe_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = re.sub(r"\s+", " ", str(text).strip())
    try:
        dt = dateparser.parse(text, fuzzy=True)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=EASTERN)
        return dt
    except Exception:
        return None


def abs_url(href: str, base: str) -> str:
    if not href:
        return base
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin
    return urljoin(base, href)


def html_cards(soup: BeautifulSoup, base_url: str, source: str,
               category: str, max_items: int = 25) -> list[DCEvent]:
    """Generic card extractor — tries article tags, then class patterns."""
    events = []
    seen: set[str] = set()
    cards = (soup.find_all("article") or
             soup.find_all(class_=re.compile(r"event|card|item|listing", re.I)))
    for card in cards[:max_items]:
        title_el = (card.find(["h2", "h3", "h4"]) or
                    card.find(class_=re.compile(r"title|heading|name", re.I)))
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or title in seen:
            continue
        seen.add(title)

        link_el = card.find("a", href=True)
        url = abs_url(link_el["href"] if link_el else "", base_url)

        date_el = (card.find("time") or
                   card.find(class_=re.compile(r"date|when|time", re.I)))
        raw_date = ""
        if date_el:
            raw_date = date_el.get("datetime") or date_el.get_text(strip=True)
        start = safe_date(raw_date)

        desc_el = card.find("p")
        desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

        events.append(DCEvent(title=title, url=url, source=source,
                               category=category, start=start, description=desc))
    return events


def jsonld_events(soup: BeautifulSoup, base_url: str, source: str,
                  category: str) -> list[DCEvent]:
    """Extract events from JSON-LD structured data."""
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                typ = item.get("@type", "")
                if not isinstance(typ, str):
                    typ = " ".join(typ) if isinstance(typ, list) else ""
                if "event" not in typ.lower():
                    continue
                title = item.get("name", "").strip()
                if not title:
                    continue
                url = item.get("url", base_url)
                start = safe_date(item.get("startDate", ""))
                end = safe_date(item.get("endDate", ""))
                desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()[:400]
                loc = item.get("location", {})
                location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                events.append(DCEvent(title=title, url=url, source=source,
                                       category=category, start=start, end=end,
                                       description=desc, location=location))
        except Exception:
            pass
    return events


# ── Think Tank scrapers ───────────────────────────────────────────────────────

def scrape_brookings() -> list[DCEvent]:
    log.info("Scraping Brookings...")
    BASE = "https://www.brookings.edu/events/"
    soup = get_soup(BASE)
    if not soup:
        return []
    evs = jsonld_events(soup, BASE, "Brookings Institution", "Think Tanks")
    if not evs:
        evs = html_cards(soup, BASE, "Brookings Institution", "Think Tanks")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_cato() -> list[DCEvent]:
    log.info("Scraping CATO Institute...")
    BASE = "https://www.cato.org/events"
    soup = get_soup(BASE)
    if not soup:
        return []
    evs = html_cards(soup, BASE, "CATO Institute", "Think Tanks")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_heritage() -> list[DCEvent]:
    log.info("Scraping Heritage Foundation...")
    evs = []
    # Try JSON API first
    try:
        resp = requests.get("https://www.heritage.org/api/events",
                            headers=HEADERS, params={"per_page": 20}, timeout=TIMEOUT)
        resp.raise_for_status()
        items = resp.json()
        if isinstance(items, dict):
            items = items.get("data", items.get("events", []))
        for item in items[:20]:
            title = item.get("title") or item.get("name", "")
            if not title:
                continue
            slug = item.get("slug") or ""
            url = (f"https://www.heritage.org/events/{slug}"
                   if slug and not slug.startswith("http")
                   else slug or "https://www.heritage.org/events")
            start = safe_date(item.get("start_date") or item.get("starts_at", ""))
            end = safe_date(item.get("end_date") or item.get("ends_at", ""))
            desc = re.sub(r"<[^>]+>", "",
                          item.get("description") or item.get("summary", "")).strip()[:400]
            evs.append(DCEvent(title=title, url=url, source="Heritage Foundation",
                                category="Think Tanks", start=start, end=end, description=desc))
    except Exception:
        soup = get_soup("https://www.heritage.org/events")
        if soup:
            evs = html_cards(soup, "https://www.heritage.org/events",
                             "Heritage Foundation", "Think Tanks")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_cfr() -> list[DCEvent]:
    log.info("Scraping CFR...")
    BASE = "https://www.cfr.org/calendar"
    soup = get_soup(BASE)
    if not soup:
        return []
    evs = jsonld_events(soup, BASE, "Council on Foreign Relations", "Think Tanks")
    if not evs:
        evs = html_cards(soup, BASE, "Council on Foreign Relations", "Think Tanks")
    log.info(f"  → {len(evs)} events")
    return evs


# ── Smithsonian ───────────────────────────────────────────────────────────────

def scrape_smithsonian() -> list[DCEvent]:
    log.info("Scraping Smithsonian...")
    BASE = "https://www.si.edu/events"
    evs = []

    # Smithsonian publishes JSON-LD and has a clean events listing
    soup = get_soup(BASE)
    if soup:
        evs = jsonld_events(soup, BASE, "Smithsonian Institution", "Smithsonian")
        if not evs:
            evs = html_cards(soup, BASE, "Smithsonian Institution", "Smithsonian", max_items=40)

    # Also hit the Natural History Museum directly (it's very active)
    nh_url = "https://naturalhistory.si.edu/events"
    soup2 = get_soup(nh_url)
    if soup2:
        more = jsonld_events(soup2, nh_url, "Smithsonian Institution", "Smithsonian")
        if not more:
            more = html_cards(soup2, nh_url, "Smithsonian Institution", "Smithsonian", max_items=20)
        evs.extend(more)

    # Deduplicate by title
    seen: set[str] = set()
    deduped = []
    for ev in evs:
        if ev.title not in seen:
            seen.add(ev.title)
            deduped.append(ev)

    log.info(f"  → {len(deduped)} events")
    return deduped


# ── Folger Shakespeare Library ────────────────────────────────────────────────

def scrape_folger() -> list[DCEvent]:
    log.info("Scraping Folger Shakespeare Library...")
    BASE = "https://www.folger.edu/whats-on/"
    soup = get_soup(BASE)
    if not soup:
        return []

    evs = jsonld_events(soup, BASE, "Folger Shakespeare Library", "Shakespeare")
    if not evs:
        evs = html_cards(soup, BASE, "Folger Shakespeare Library", "Shakespeare", max_items=30)

    # Also grab theater sub-page
    theater_url = "https://www.folger.edu/whats-on/events/theater/"
    soup2 = get_soup(theater_url)
    if soup2:
        more = html_cards(soup2, theater_url, "Folger Shakespeare Library",
                          "Shakespeare", max_items=15)
        titles = {e.title for e in evs}
        evs.extend(e for e in more if e.title not in titles)

    log.info(f"  → {len(evs)} events")
    return evs


# ── Kennedy Center ────────────────────────────────────────────────────────────

def scrape_kennedy_center() -> list[DCEvent]:
    log.info("Scraping Kennedy Center...")
    BASE = "https://www.kennedy-center.org/whats-on/"
    soup = get_soup(BASE)
    if not soup:
        return []
    evs = jsonld_events(soup, BASE, "Kennedy Center", "Cultural Centers")
    if not evs:
        evs = html_cards(soup, BASE, "Kennedy Center", "Cultural Centers", max_items=30)

    # Millennium Stage (free nightly performances)
    ms_url = "https://www.kennedy-center.org/whats-on/millennium-stage/"
    soup2 = get_soup(ms_url)
    if soup2:
        more = jsonld_events(soup2, ms_url, "Kennedy Center", "Cultural Centers")
        if not more:
            more = html_cards(soup2, ms_url, "Kennedy Center", "Cultural Centers", max_items=20)
        titles = {e.title for e in evs}
        evs.extend(e for e in more if e.title not in titles)

    log.info(f"  → {len(evs)} events")
    return evs


# ── National Gallery of Art ───────────────────────────────────────────────────

def scrape_nga() -> list[DCEvent]:
    log.info("Scraping National Gallery of Art...")
    BASE = "https://www.nga.gov/calendar.html"
    soup = get_soup(BASE)
    if not soup:
        soup = get_soup("https://www.nga.gov/calendar")
    if not soup:
        return []
    evs = jsonld_events(soup, "https://www.nga.gov/calendar", "National Gallery of Art", "Cultural Centers")
    if not evs:
        evs = html_cards(soup, "https://www.nga.gov/calendar", "National Gallery of Art",
                         "Cultural Centers", max_items=25)
    log.info(f"  → {len(evs)} events")
    return evs


# ── Library of Congress ───────────────────────────────────────────────────────

def scrape_loc() -> list[DCEvent]:
    log.info("Scraping Library of Congress...")
    BASE = "https://www.loc.gov/events/"
    soup = get_soup(BASE)
    if not soup:
        return []

    # LOC often uses <div class="event-item"> or similar
    evs = jsonld_events(soup, BASE, "Library of Congress", "Cultural Centers")
    if not evs:
        evs = html_cards(soup, BASE, "Library of Congress", "Cultural Centers", max_items=25)

    # LOC also publishes an RSS/JSON feed
    try:
        resp = requests.get("https://www.loc.gov/events/?fo=json&count=25",
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("results", data.get("items", []))
        titles = {e.title for e in evs}
        for item in items:
            title = item.get("title", "").strip()
            if not title or title in titles:
                continue
            titles.add(title)
            url = item.get("url") or item.get("id", BASE)
            start_raw = item.get("dates", {})
            if isinstance(start_raw, dict):
                start_raw = start_raw.get("start", "")
            start = safe_date(str(start_raw))
            desc = item.get("description") or item.get("summary", "")
            if isinstance(desc, list):
                desc = " ".join(desc)
            evs.append(DCEvent(title=title, url=url, source="Library of Congress",
                                category="Cultural Centers", start=start,
                                description=str(desc)[:400]))
    except Exception:
        pass

    log.info(f"  → {len(evs)} events")
    return evs


# ── Cultural Institutes / Centers ─────────────────────────────────────────────

def _generic_scrape(name: str, url: str, category: str = "Cultural Centers",
                    max_items: int = 20) -> list[DCEvent]:
    soup = get_soup(url)
    if not soup:
        return []
    evs = jsonld_events(soup, url, name, category)
    if not evs:
        evs = html_cards(soup, url, name, category, max_items=max_items)
    return evs


def scrape_mexican_cultural_institute() -> list[DCEvent]:
    log.info("Scraping Mexican Cultural Institute...")
    evs = _generic_scrape("Mexican Cultural Institute",
                          "https://www.instituteofmexicanculture.org/events/")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_alliance_francaise() -> list[DCEvent]:
    log.info("Scraping Alliance Française DC...")
    evs = _generic_scrape("Alliance Française DC",
                          "https://www.francedc.org/events")
    if not evs:
        evs = _generic_scrape("Alliance Française DC",
                              "https://afdc.com/events/")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_italian_cultural_institute() -> list[DCEvent]:
    log.info("Scraping Italian Cultural Institute...")
    evs = _generic_scrape("Italian Cultural Institute",
                          "https://iicwashington.esteri.it/en/gli_eventi/")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_korean_cultural_center() -> list[DCEvent]:
    log.info("Scraping Korean Cultural Center...")
    evs = _generic_scrape("Korean Cultural Center",
                          "https://www.kccdc.org/events")
    log.info(f"  → {len(evs)} events")
    return evs


def scrape_goethe() -> list[DCEvent]:
    log.info("Scraping Goethe-Institut Washington...")
    evs = _generic_scrape("Goethe-Institut Washington",
                          "https://www.goethe.de/ins/us/en/sta/was/ver.html")
    log.info(f"  → {len(evs)} events")
    return evs


# ── Embassy aggregators ───────────────────────────────────────────────────────

def scrape_eventbrite_embassy() -> list[DCEvent]:
    """Scrape Eventbrite's DC embassy/culture event listing."""
    log.info("Scraping Eventbrite (Embassy & Culture)...")
    BASE = "https://www.eventbrite.com/d/dc--washington/embassy/"
    soup = get_soup(BASE)
    if not soup:
        return []

    evs = []
    seen: set[str] = set()

    # Eventbrite renders event cards with data attributes
    cards = soup.find_all(attrs={"data-event-id": True})
    if not cards:
        cards = soup.find_all(class_=re.compile(r"event-card|eds-event-card", re.I))

    for card in cards[:30]:
        title_el = (card.find(class_=re.compile(r"title|name|heading", re.I)) or
                    card.find(["h2", "h3", "h4"]))
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or title in seen:
            continue
        seen.add(title)

        link_el = card.find("a", href=True)
        url = abs_url(link_el["href"] if link_el else "", BASE)

        date_el = card.find("time") or card.find(class_=re.compile(r"date", re.I))
        raw_date = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
        start = safe_date(raw_date)

        evs.append(DCEvent(title=title, url=url, source="Embassy Events (Eventbrite)",
                            category="Embassies", start=start))

    log.info(f"  → {len(evs)} events")
    return evs


def scrape_passport_dc() -> list[DCEvent]:
    """Passport DC — month-long embassy open houses (May, annual)."""
    log.info("Scraping Passport DC...")
    BASE = "https://eventsdc.com/passportdc"
    soup = get_soup(BASE)
    if not soup:
        return []
    evs = html_cards(soup, BASE, "Passport DC", "Embassies", max_items=25)
    log.info(f"  → {len(evs)} events")
    return evs


# ── Calendar builder ──────────────────────────────────────────────────────────

def build_ical(events: list[DCEvent]) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//DC Cultural & Policy Events//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "DC Cultural & Policy Events")
    cal.add("x-wr-caldesc",
            "Think Tanks · Smithsonian · Folger · Kennedy Center · "
            "National Gallery · Library of Congress · Cultural Centers · Embassies")
    cal.add("x-wr-timezone", "America/New_York")
    cal.add("refresh-interval;value=duration", "PT6H")
    cal.add("x-published-ttl", "PT6H")

    now = datetime.now(tz=timezone.utc)
    color_map = {v: k for k, v in CATEGORIES.items()}  # unused but kept for reference

    for ev in events:
        iev = ICalEvent()
        iev.add("uid", str(uuid.uuid4()) + "@dc-events-calendar")
        iev.add("summary", f"[{ev.source}] {ev.title}")
        iev.add("url", ev.url)
        iev.add("dtstamp", now)

        if ev.start:
            iev.add("dtstart", ev.start)
            if ev.end:
                iev.add("dtend", ev.end)
        else:
            iev.add("dtstart", now.date())

        desc = "\n\n".join(filter(None, [ev.description,
                                          f"Source: {ev.source}",
                                          f"Category: {ev.category}",
                                          f"Link: {ev.url}"]))
        iev.add("description", desc)
        if ev.location:
            iev.add("location", ev.location)
        iev.add("categories", [ev.category, ev.source])
        cal.add_component(iev)

    return cal.to_ical()


# ── Main ──────────────────────────────────────────────────────────────────────

SCRAPERS = [
    # Think Tanks
    scrape_brookings,
    scrape_cato,
    scrape_heritage,
    scrape_cfr,
    # Smithsonian
    scrape_smithsonian,
    # Shakespeare
    scrape_folger,
    # Cultural Centers
    scrape_kennedy_center,
    scrape_nga,
    scrape_loc,
    scrape_mexican_cultural_institute,
    scrape_alliance_francaise,
    scrape_italian_cultural_institute,
    scrape_korean_cultural_center,
    scrape_goethe,
    # Embassies
    scrape_eventbrite_embassy,
    scrape_passport_dc,
]


def main():
    os.makedirs("docs", exist_ok=True)
    all_events: list[DCEvent] = []

    for scraper in SCRAPERS:
        try:
            result = scraper()
            all_events.extend(result)
        except Exception as e:
            log.error(f"Scraper {scraper.__name__} crashed: {e}")

    log.info(f"\n{'─'*50}")
    log.info(f"Total events collected: {len(all_events)}")
    by_cat: dict[str, int] = {}
    for ev in all_events:
        by_cat[ev.category] = by_cat.get(ev.category, 0) + 1
    for cat, count in sorted(by_cat.items()):
        log.info(f"  {cat}: {count}")
    log.info(f"{'─'*50}\n")

    # Sort: upcoming first, undated last
    def sort_key(e: DCEvent):
        if e.start:
            return (0, e.start)
        return (1, datetime.now(tz=timezone.utc))
    all_events.sort(key=sort_key)

    # Write iCal
    ics = build_ical(all_events)
    with open("docs/events.ics", "wb") as f:
        f.write(ics)
    log.info("✓ docs/events.ics written")

    # Write JSON manifest
    manifest = []
    for ev in all_events:
        manifest.append({
            "title": ev.title,
            "source": ev.source,
            "category": ev.category,
            "url": ev.url,
            "start": ev.start.isoformat() if ev.start else None,
            "end": ev.end.isoformat() if ev.end else None,
            "description": ev.description,
            "location": ev.location,
        })
    with open("docs/events.json", "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(tz=timezone.utc).isoformat(),
                   "count": len(manifest),
                   "events": manifest}, f, indent=2, default=str)
    log.info("✓ docs/events.json written")


if __name__ == "__main__":
    main()
