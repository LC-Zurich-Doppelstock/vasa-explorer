#!/usr/bin/env python3
"""
Scrape Vasaloppet 90km race results from results.vasaloppet.se.

Usage:
    # Scraping
    python scrape_vasaloppet.py --year 2025
    python scrape_vasaloppet.py --year 2026
    python scrape_vasaloppet.py --year 2025 --test       # Only 2 pages per sex
    python scrape_vasaloppet.py --year 2025 --resume     # Resume from saved progress

    # Clean raw CSV into analysis-ready format
    python scrape_vasaloppet.py --clean
    python scrape_vasaloppet.py --clean --input results_raw.csv --output results_clean.csv

    # Summary statistics
    python scrape_vasaloppet.py --summary                   # Overall summary
    python scrape_vasaloppet.py --summary --year 2025       # Detailed year summary
    python scrape_vasaloppet.py --summary --input results_clean.csv  # From clean CSV

Progress is saved incrementally to:
    .scrape_progress/{year}_stubs.jsonl   — participant list (Phase 1)
    .scrape_progress/{year}_details.jsonl — fetched detail rows (Phase 2)

On --resume, already-fetched stubs and details are loaded from disk and
only the remaining work is done.

Outputs a CSV file: vasaloppet_{year}.csv
"""

import argparse
import csv
import hashlib
import json
import os
import re
import struct
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

warnings.filterwarnings("ignore", message=".*Unverified HTTPS.*")

BASE_URL = "https://results.vasaloppet.se"
EVENT_CODES = {
    2025: "VL_HCH8NDMR2500",
    2026: "VL_HCH8NDMR2600",
}

PROGRESS_DIR = Path(".scrape_progress")

# CSV columns in exact order
CSV_COLUMNS = [
    "index",
    "Year",
    "Status",
    "Name",
    "Nation",
    "Sex",
    "Time_Finish",
    "Place_Finish",
    "PlaceOverall",
    "Bib",
    "Time_Mångsbodarna",
    "Place_Mångsbodarna",
    "Time_Risberg",
    "Place_Risberg",
    "Time_Evertsberg",
    "Place_Evertsberg",
    "Time_Oxberg",
    "Place_Oxberg",
    "Time_Hökberg",
    "Place_Hökberg",
    "Time_Eldris",
    "Place_Eldris",
    "Time_Smågan",
    "Place_Smågan",
    "StartGroup",
    "Group",
    "Time_Högsta punkten",
    "Place_Högsta punkten",
]

# Map split names from the website to CSV column prefixes
SPLIT_NAME_MAP = {
    "Högsta punkten": "Högsta punkten",
    "Smågan": "Smågan",
    "Mångsbodarna": "Mångsbodarna",
    "Risberg": "Risberg",
    "Evertsberg": "Evertsberg",
    "Oxberg": "Oxberg",
    "Hökberg": "Hökberg",
    "Eldris": "Eldris",
}

# Defaults
MAX_WORKERS = 20
NUM_RESULTS = 100
MAX_RETRIES = 8
RETRY_BASE_DELAY = 2.0


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def progress_dir(year: int) -> Path:
    d = PROGRESS_DIR / str(year)
    d.mkdir(parents=True, exist_ok=True)
    return d


def stubs_path(year: int) -> Path:
    return progress_dir(year) / "stubs.jsonl"


def details_path(year: int) -> Path:
    return progress_dir(year) / "details.jsonl"


def append_jsonl(path: Path, obj: dict):
    """Append a single JSON object as a line to a JSONL file."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_jsonl_batch(path: Path, objs: list[dict]):
    """Append multiple JSON objects to a JSONL file."""
    with open(path, "a", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    """Read all JSON objects from a JSONL file."""
    if not path.exists():
        return []
    results = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def load_completed_idps(year: int) -> set[str]:
    """Load the set of idp values already fetched in detail phase."""
    details = read_jsonl(details_path(year))
    return {d["idp"] for d in details if "idp" in d}


def load_stubs_progress(year: int) -> tuple[dict[str, int], list[dict]]:
    """Load stubs progress. Returns (pages_done dict, stubs list).
    pages_done maps 'M' / 'W' to the last page number fetched."""
    meta_path = progress_dir(year) / "stubs_meta.json"
    stubs = read_jsonl(stubs_path(year))

    pages_done = {"M": 0, "W": 0}
    if meta_path.exists():
        with open(meta_path) as f:
            pages_done = json.load(f)

    return pages_done, stubs


def save_stubs_meta(year: int, pages_done: dict[str, int]):
    meta_path = progress_dir(year) / "stubs_meta.json"
    with open(meta_path, "w") as f:
        json.dump(pages_done, f)


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------


def make_index(year: int, name: str, bib: str) -> int:
    """Generate a deterministic int64 index from year + name + bib."""
    key = f"{year}|{name}|{bib}"
    h = hashlib.sha256(key.encode("utf-8")).digest()
    return struct.unpack(">q", h[:8])[0]


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------


def get_session(pool_size: int = 25) -> requests.Session:
    """Create a requests session with connection pooling, SSL verify off."""
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_with_retry(session: requests.Session, url: str) -> requests.Response:
    """Fetch a URL with exponential backoff retry."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                delay = RETRY_BASE_DELAY * (2**attempt)
                print(
                    f"  [Retry] HTTP {resp.status_code} — "
                    f"waiting {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"  [Error] HTTP {resp.status_code} for {url[:80]}", file=sys.stderr)
            return resp
        except requests.RequestException as e:
            delay = RETRY_BASE_DELAY * (2**attempt)
            print(
                f"  [Retry] {type(e).__name__} — "
                f"waiting {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url[:100]}")


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def format_time(time_str: str) -> str:
    """Convert HH:MM:SS to '0 days HH:MM:SS' format."""
    if not time_str or time_str in ("–", "-"):
        return ""
    if time_str.startswith("0 days"):
        return time_str
    parts = time_str.strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
        return f"0 days {int(h):02d}:{int(m):02d}:{int(s):02d}"
    return ""


def format_place(place_str: str) -> str:
    """Convert place string to float format like '1.0'."""
    if not place_str or place_str in ("–", "-"):
        return ""
    try:
        return f"{int(place_str)}.0"
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def get_max_page(
    session: requests.Session, year: int, sex: str, event_code: str
) -> int:
    url = (
        f"{BASE_URL}/{year}/?pid=search&lang=EN_CAP&event={event_code}"
        f"&search[sex]={sex}&num_results={NUM_RESULTS}&page=1"
        f"&search_sort=name"
    )
    resp = fetch_with_retry(session, url)
    soup = BeautifulSoup(resp.text, "lxml")
    pag = soup.select_one(".pages")
    if not pag:
        return 1
    page_links = [a for a in pag.select("a") if a.get_text(strip=True).isdigit()]
    if not page_links:
        return 1
    return max(int(a.get_text(strip=True)) for a in page_links)


# ---------------------------------------------------------------------------
# Phase 1: List page parsing
# ---------------------------------------------------------------------------


def parse_list_page(html: str, year: int, sex: str, event_code: str) -> list[dict]:
    """Parse a search results list page and extract participant stubs."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for item in soup.select("li.list-group-item.row"):
        link = item.select_one('a[href*="idp"]')
        if not link:
            continue

        href = str(link.get("href", ""))
        parsed = parse_qs(urlparse(href).query)
        idp = parsed.get("idp", [None])[0]
        if not idp:
            match = re.search(r"idp=([A-Za-z0-9]+)", href)
            if match:
                idp = match.group(1)
            else:
                continue

        raw_name = link.get_text(strip=True)
        name_match = re.match(r"^(.+?)\s*\(([A-Z]{2,3})\)\s*$", raw_name)
        if name_match:
            name = name_match.group(1).strip()
            nation = name_match.group(2)
        else:
            name = raw_name.strip()
            nation = ""

        bib = ""
        for div in item.select(".list-field.type-field"):
            label = div.select_one(".list-label")
            if label and "Bib" in label.get_text():
                bib = (
                    div.get_text(strip=True)
                    .replace(label.get_text(strip=True), "")
                    .strip()
                )
                break

        group = ""
        age_div = item.select_one(".list-field.type-age_class")
        if age_div:
            label = age_div.select_one(".list-label")
            group = age_div.get_text(strip=True)
            if label:
                group = group.replace(label.get_text(strip=True), "").strip()

        place_div = item.select_one(".list-field.type-place")
        place_finish = ""
        if place_div:
            place_text = place_div.get_text(strip=True)
            if place_text.isdigit():
                place_finish = f"{int(place_text)}.0"

        time_div = item.select_one(".list-field.type-time")
        time_finish = ""
        if time_div:
            label = time_div.select_one(".list-label")
            raw_time = time_div.get_text(strip=True)
            if label:
                raw_time = raw_time.replace(label.get_text(strip=True), "").strip()
            time_finish = format_time(raw_time)

        results.append(
            {
                "idp": idp,
                "Year": year,
                "Name": name,
                "Nation": nation,
                "Sex": sex,
                "Bib": bib,
                "Group": group,
                "Place_Finish": place_finish,
                "Time_Finish": time_finish,
                "event_code": event_code,
            }
        )

    return results


def fetch_list_pages(
    session: requests.Session,
    year: int,
    sex: str,
    event_code: str,
    max_pages: int | None = None,
    start_page: int = 1,
    save_progress: bool = True,
) -> list[dict]:
    """Fetch list pages for a year/sex, starting from start_page.
    Each page's stubs are appended to disk immediately when save_progress=True."""
    total_pages = get_max_page(session, year, sex, event_code)
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    if start_page > total_pages:
        print(f"  {sex}: all {total_pages} pages already fetched, skipping.")
        return []

    print(f"  Fetching pages {start_page}-{total_pages} for {year} {sex}...")

    sp = stubs_path(year)
    all_results = []

    for page in range(start_page, total_pages + 1):
        url = (
            f"{BASE_URL}/{year}/?pid=search&lang=EN_CAP&event={event_code}"
            f"&search[sex]={sex}&num_results={NUM_RESULTS}&page={page}"
            f"&search_sort=name"
        )
        resp = fetch_with_retry(session, url)
        page_results = parse_list_page(resp.text, year, sex, event_code)

        if save_progress:
            append_jsonl_batch(sp, page_results)
        all_results.extend(page_results)

        if save_progress:
            pages_done_all = load_stubs_progress(year)[0]
            pages_done_all[sex] = page
            save_stubs_meta(year, pages_done_all)

        if page % 5 == 0 or page == total_pages or page == start_page:
            print(
                f"    Page {page}/{total_pages} — {len(all_results)} new participants",
                flush=True,
            )

        time.sleep(0.3)

    return all_results


# ---------------------------------------------------------------------------
# Phase 2: Detail page parsing
# ---------------------------------------------------------------------------


def parse_detail_page(html: str) -> dict:
    """Parse a participant detail page."""
    soup = BeautifulSoup(html, "lxml")
    data = {}
    tables = soup.select("table")

    for table in tables:
        for row in table.select("tr"):
            cells = [td.get_text(strip=True) for td in row.select("th, td")]
            if len(cells) < 2:
                continue
            key, value = cells[0], cells[1]
            if key == "Place (Total)":
                data["PlaceOverall"] = format_place(value)
            elif key == "Start Group":
                data["StartGroup"] = value
            elif key == "Race Status":
                data["Status"] = value
            elif key == "Place":
                data["Place_Finish_detail"] = format_place(value)
            elif key in ("Finish Time", "Finish Time (Net)", "Finish Time (Gun)"):
                data["Time_Finish_detail"] = format_time(value)

    # Splits table
    for table in tables:
        header_row = table.select_one("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True) for th in header_row.select("th")]
        if "Split" not in headers:
            continue
        try:
            time_idx = headers.index("Time") - 1
            place_idx = headers.index("Place") - 1
        except ValueError:
            continue

        for row in table.select("tr")[1:]:
            th = row.select_one("th")
            tds = row.select("td")
            if not th or not tds:
                continue
            split_name = th.get_text(strip=True)
            if len(tds) <= max(time_idx, place_idx):
                continue
            split_time = tds[time_idx].get_text(strip=True)
            split_place = tds[place_idx].get_text(strip=True)
            if split_name in SPLIT_NAME_MAP:
                csv_name = SPLIT_NAME_MAP[split_name]
                data[f"Time_{csv_name}"] = format_time(split_time)
                data[f"Place_{csv_name}"] = format_place(split_place)
        break

    return data


def stub_to_row(stub: dict, detail: dict) -> dict:
    """Merge a stub (from list page) with detail page data into a CSV row."""
    row = {col: "" for col in CSV_COLUMNS}
    row["Year"] = stub["Year"]
    row["Name"] = stub["Name"]
    row["Nation"] = stub["Nation"]
    row["Sex"] = stub["Sex"]
    row["Bib"] = stub["Bib"]
    row["Group"] = stub["Group"]
    row["Place_Finish"] = detail.get("Place_Finish_detail") or stub.get(
        "Place_Finish", ""
    )
    row["Time_Finish"] = detail.get("Time_Finish_detail") or stub.get("Time_Finish", "")
    row["PlaceOverall"] = detail.get("PlaceOverall", "")
    row["StartGroup"] = detail.get("StartGroup", "")
    row["Status"] = detail.get("Status", "")

    for split_name in SPLIT_NAME_MAP.values():
        row[f"Time_{split_name}"] = detail.get(f"Time_{split_name}", "")
        row[f"Place_{split_name}"] = detail.get(f"Place_{split_name}", "")

    row["index"] = str(make_index(stub["Year"], stub["Name"], stub["Bib"]))
    return row


def fetch_detail_and_save(session: requests.Session, stub: dict, year: int) -> dict:
    """Fetch one detail page, build CSV row, append to disk, return row."""
    idp = stub["idp"]
    event_code = stub["event_code"]

    url = (
        f"{BASE_URL}/{year}/?content=detail&fpid=search&pid=search"
        f"&idp={idp}&lang=EN_CAP&event={event_code}"
    )

    try:
        resp = fetch_with_retry(session, url)
        detail = parse_detail_page(resp.text)
    except Exception as e:
        print(f"  [Error] Detail for {stub['Name']}: {e}", file=sys.stderr)
        detail = {}

    row = stub_to_row(stub, detail)

    # Persist immediately — include idp so we can track what's done
    record = {**row, "idp": idp}
    append_jsonl(details_path(year), record)

    return row


# ---------------------------------------------------------------------------
# Main scrape orchestration
# ---------------------------------------------------------------------------


def load_existing_csv(csv_path: str) -> tuple[list[dict], set[str]]:
    """Load an existing output CSV and return (rows, set of Name|Bib keys)."""
    rows = []
    keys = set()
    if not os.path.exists(csv_path):
        return rows, keys
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            keys.add(f"{r['Name']}|{r['Bib']}")
    return rows, keys


def fetch_details_parallel(
    session: requests.Session,
    stubs: list[dict],
    year: int,
    workers: int,
    already_done_idps: set[str],
    completed_rows: list[dict],
) -> list[dict]:
    """Fetch detail pages in parallel for the given stubs, skipping already-done
    idps. Returns all rows (completed + newly fetched)."""
    remaining = [s for s in stubs if s["idp"] not in already_done_idps]
    total = len(stubs)

    if already_done_idps:
        print(
            f"\nPhase 2: {len(already_done_idps)} already fetched, "
            f"{len(remaining)} remaining",
            flush=True,
        )
    else:
        print(
            f"\nPhase 2: Fetching {len(remaining)} detail pages "
            f"(with {workers} workers)...",
            flush=True,
        )

    if not remaining:
        print("  All detail pages already fetched!")
        return list(completed_rows)

    all_rows = list(completed_rows)
    done_count = len(completed_rows)
    errors = 0
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_detail_and_save, session, stub, year): stub
            for stub in remaining
        }

        for future in as_completed(futures):
            try:
                row = future.result()
                all_rows.append(row)
            except Exception as e:
                stub = futures[future]
                print(f"  [Error] {stub['Name']}: {e}", file=sys.stderr)
                errors += 1

            done_count += 1
            fetched_so_far = done_count - len(completed_rows)
            if fetched_so_far % 50 == 0 or done_count == total or fetched_so_far == 1:
                elapsed = time.time() - t_start
                rate = fetched_so_far / elapsed if elapsed > 0 else 0
                left = total - done_count
                eta = left / rate if rate > 0 else 0
                print(
                    f"  Progress: {done_count}/{total} "
                    f"({done_count * 100 / total:.1f}%) — "
                    f"{rate:.1f} req/s — "
                    f"ETA: {eta / 60:.1f} min — "
                    f"{errors} errors",
                    flush=True,
                )

    elapsed = time.time() - t_start
    fetched_new = len(all_rows) - len(completed_rows)
    print(
        f"\nDone! Fetched {fetched_new} new results in {elapsed:.1f}s ({errors} errors)"
    )

    return all_rows


def scrape_year(
    year: int,
    test_mode: bool = False,
    workers: int = MAX_WORKERS,
    resume: bool = False,
    supplement: str | None = None,
) -> list[dict]:
    """Scrape all results for a given year with incremental persistence.

    Args:
        supplement: path to an existing CSV to supplement with missing entries
                    (e.g. DNS/DNF that were missed by a previous scrape).
    """
    event_code = EVENT_CODES.get(year)
    if not event_code:
        print(f"Error: No event code for year {year}", file=sys.stderr)
        sys.exit(1)

    session = get_session(pool_size=workers + 5)
    max_pages = 2 if test_mode else None

    print(f"\n{'=' * 60}")
    print(f"Scraping Vasaloppet {year}")
    print(f"Event code: {event_code}")
    if supplement:
        print(f"Mode: SUPPLEMENT (adding missing entries to {supplement})")
    elif resume:
        print("Mode: RESUME (loading saved progress)")
    print(f"{'=' * 60}\n")

    # ------------------------------------------------------------------
    # Supplement mode: load existing CSV, resume stubs, find gaps
    # ------------------------------------------------------------------
    if supplement:
        existing_rows, existing_keys = load_existing_csv(supplement)
        print(f"  Loaded {len(existing_rows)} rows from {supplement}", flush=True)

        # Load previously saved stubs progress (resumable)
        pages_done, existing_stubs = load_stubs_progress(year)
        print(
            f"  Loaded {len(existing_stubs)} stubs from disk "
            f"(pages done: M={pages_done.get('M', 0)}, "
            f"W={pages_done.get('W', 0)})",
            flush=True,
        )

        # Fetch remaining list pages (name sort captures DNS/DNF too)
        print("\nPhase 1: Fetching list pages (name sort, resumable)...", flush=True)
        all_stubs = list(existing_stubs)
        for sex in ["M", "W"]:
            start_page = pages_done.get(sex, 0) + 1
            new_stubs = fetch_list_pages(
                session,
                year,
                sex,
                event_code,
                max_pages=max_pages,
                start_page=start_page,
                save_progress=True,
            )
            all_stubs.extend(new_stubs)
            total_sex = sum(1 for s in all_stubs if s["Sex"] == sex)
            print(f"  {sex}: {total_sex} participants total", flush=True)

        total = len(all_stubs)
        print(f"\nTotal from website: {total}", flush=True)
        print(f"Already in CSV:    {len(existing_rows)}", flush=True)

        # Find stubs not in the existing CSV — only these need detail fetching
        missing_stubs = [
            s for s in all_stubs if f"{s['Name']}|{s['Bib']}" not in existing_keys
        ]
        print(f"New entries not in CSV: {len(missing_stubs)}", flush=True)

        if not missing_stubs:
            print("  Nothing new to fetch!", flush=True)
            return existing_rows

        # Phase 2: Fetch detail pages ONLY for entries not in the CSV
        # Load already-completed details from previous runs
        already_done_idps = load_completed_idps(year)
        completed_new_rows: list[dict] = []
        if already_done_idps:
            # Build rows from saved details, but only for stubs that are
            # actually missing from the CSV (avoid mixing in finisher details)
            missing_idps = {s["idp"] for s in missing_stubs}
            for d in read_jsonl(details_path(year)):
                if d.get("idp") in missing_idps:
                    row = {col: d.get(col, "") for col in CSV_COLUMNS}
                    completed_new_rows.append(row)

        still_needed = [s for s in missing_stubs if s["idp"] not in already_done_idps]
        print(
            f"\nPhase 2: {len(missing_stubs)} missing entries — "
            f"{len(completed_new_rows)} already have details, "
            f"{len(still_needed)} need fetching",
            flush=True,
        )

        new_rows = fetch_details_parallel(
            session, missing_stubs, year, workers, already_done_idps, completed_new_rows
        )

        # Merge existing CSV rows + newly fetched rows
        all_rows = existing_rows + new_rows
        # Deduplicate by (Name, Bib) just in case
        seen = set()
        deduped = []
        for r in all_rows:
            key = f"{r['Name']}|{r['Bib']}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        all_rows = deduped

        # Sort
        def sort_key(r):
            try:
                return float(r["PlaceOverall"]) if r["PlaceOverall"] else 999999
            except (ValueError, TypeError):
                return 999999

        all_rows.sort(key=sort_key)
        return all_rows

    # ------------------------------------------------------------------
    # Normal / Resume mode
    # ------------------------------------------------------------------
    print("Phase 1: Fetching list pages...")

    if resume:
        pages_done, existing_stubs = load_stubs_progress(year)
        print(
            f"  Loaded {len(existing_stubs)} stubs from disk "
            f"(pages done: M={pages_done.get('M', 0)}, "
            f"W={pages_done.get('W', 0)})"
        )
    else:
        pages_done = {"M": 0, "W": 0}
        existing_stubs = []
        # Clear any old progress files for a fresh run
        for f in [
            stubs_path(year),
            details_path(year),
            progress_dir(year) / "stubs_meta.json",
        ]:
            if f.exists():
                f.unlink()

    all_stubs = list(existing_stubs)

    for sex in ["M", "W"]:
        start_page = pages_done.get(sex, 0) + 1
        new_stubs = fetch_list_pages(
            session, year, sex, event_code, max_pages=max_pages, start_page=start_page
        )
        all_stubs.extend(new_stubs)
        total_sex = sum(1 for s in all_stubs if s["Sex"] == sex)
        print(f"  {sex}: {total_sex} participants total")

    total = len(all_stubs)
    print(f"\nTotal participants: {total}")

    # Phase 2
    already_done_idps = load_completed_idps(year) if resume else set()
    completed_rows: list[dict] = []
    if already_done_idps:
        for d in read_jsonl(details_path(year)):
            row = {col: d.get(col, "") for col in CSV_COLUMNS}
            completed_rows.append(row)

    all_rows = fetch_details_parallel(
        session, all_stubs, year, workers, already_done_idps, completed_rows
    )

    # Sort by PlaceOverall
    def sort_key(r):
        try:
            return float(r["PlaceOverall"]) if r["PlaceOverall"] else 999999
        except (ValueError, TypeError):
            return 999999

    all_rows.sort(key=sort_key)
    return all_rows


def write_csv(rows: list[dict], output_path: str):
    """Write rows to CSV matching the existing format."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output_path}")


# ---------------------------------------------------------------------------
# Clean mode
# ---------------------------------------------------------------------------


def clean_raw_csv(input_path: str, output_path: str):
    """Transform results_raw.csv into results_clean.csv.

    Replicates the logic from playground.ipynb cell 310:
    1. Drop the hash-based index
    2. Replace '–' with NA in Group, StartGroup, Bib, Status
    3. Fill all NaN with pd.NA
    4. Convert Time_* columns from timedelta strings to total seconds
    5. Select final column subset
    6. Write output
    """
    print(f"Reading {input_path}...")
    df = pd.read_csv(input_path, low_memory=False)

    # 1. Reset index (drop the hash-based 'index' column if present)
    if "index" in df.columns:
        df = df.drop(columns=["index"])
    df.reset_index(drop=True, inplace=True)

    # 2. Replace '–' (en-dash) with NA in specific columns
    for col in ["Group", "StartGroup", "Bib", "Status"]:
        if col in df.columns:
            df[col] = df[col].mask(df[col] == "\u2013", pd.NA)

    # 3. Fill all NaN with pd.NA
    df.fillna(pd.NA, inplace=True)

    # 4. Convert Time_* columns to total seconds (float)
    time_cols = [c for c in df.columns if "Time_" in c]
    for c in time_cols:
        new_col = c[5:]  # e.g. Time_Finish -> Finish, Time_Smågan -> Smågan
        df[new_col] = pd.to_timedelta(df[c], errors="coerce").apply(
            lambda x: x.total_seconds() if pd.notna(x) else pd.NA
        )

    # 5. Select final columns
    cols = [
        "Year",
        "Name",
        "Nation",
        "Status",
        "Sex",
        "Bib",
        "StartGroup",
        "Group",
        "Högsta punkten",
        "Smågan",
        "Mångsbodarna",
        "Risberg",
        "Evertsberg",
        "Oxberg",
        "Hökberg",
        "Eldris",
        "Finish",
    ]
    # Only keep columns that exist (historical data may lack some checkpoints)
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    # 6. Write output
    df.to_csv(output_path)
    print(f"Wrote {len(df)} rows to {output_path}")
    print(f"  Columns: {', '.join(cols)}")

    # Quick validation
    years = df["Year"].nunique()
    print(f"  Years: {years} unique ({int(df['Year'].min())}-{int(df['Year'].max())})")


# ---------------------------------------------------------------------------
# Summary mode
# ---------------------------------------------------------------------------


def summarize_data(input_path: str, year: int | None = None):
    """Print a summary of the dataset, optionally filtered to a specific year."""
    print(f"Reading {input_path}...")
    df = pd.read_csv(input_path, low_memory=False)

    if year is not None:
        df_year = df[df["Year"] == year]
        if df_year.empty:
            print(f"No data found for year {year}.")
            available = sorted(df["Year"].unique())
            print(
                f"Available years: {available[0]}-{available[-1]} ({len(available)} years)"
            )
            return
        _print_year_summary(df_year, year)
    else:
        _print_overall_summary(df)


def _print_overall_summary(df: pd.DataFrame):
    """Print an overall summary across all years."""
    years = sorted(df["Year"].unique())
    total = len(df)

    print(f"\n{'=' * 60}")
    print(f"  VASALOPPET RESULTS — OVERALL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total rows:    {total:,}")
    print(f"  Years covered: {int(years[0])}-{int(years[-1])} ({len(years)} years)")

    # Status breakdown
    if "Status" in df.columns:
        print(f"\n  Status breakdown:")
        status_counts = df["Status"].value_counts(dropna=False)
        for status, count in status_counts.items():
            pct = count / total * 100
            label = status if pd.notna(status) else "(empty/NA)"
            print(f"    {label:<20s} {count:>8,}  ({pct:5.1f}%)")

    # Sex breakdown
    if "Sex" in df.columns:
        print(f"\n  Sex breakdown:")
        sex_counts = df["Sex"].value_counts(dropna=False)
        for sex, count in sex_counts.items():
            pct = count / total * 100
            label = sex if pd.notna(sex) else "(empty/NA)"
            print(f"    {label:<20s} {count:>8,}  ({pct:5.1f}%)")

    # Participation over time (last 10 years)
    print(f"\n  Participation (last 10 years):")
    recent = sorted(years)[-10:]
    for y in recent:
        y_df = df[df["Year"] == y]
        finished = (
            (y_df["Status"] == "Finished").sum() if "Status" in y_df.columns else "?"
        )
        print(f"    {int(y)}: {len(y_df):>6,} total, {finished:>6,} finished")

    # Top nations
    if "Nation" in df.columns:
        print(f"\n  Top 10 nations (all time):")
        nation_counts = df["Nation"].value_counts().head(10)
        for nation, count in nation_counts.items():
            print(f"    {nation:<6s} {count:>8,}")

    # Finish time stats (if Time_Finish or Finish exists)
    time_col = None
    if "Finish" in df.columns:
        time_col = "Finish"
    elif "Time_Finish" in df.columns:
        time_col = "Time_Finish"

    if time_col and time_col == "Finish":
        valid = df[time_col].dropna()
        valid = pd.to_numeric(valid, errors="coerce").dropna()
        if len(valid) > 0:
            print(f"\n  Finish time stats (all finishers, seconds):")
            print(f"    Fastest:  {_seconds_to_hms(valid.min())}")
            print(f"    Median:   {_seconds_to_hms(valid.median())}")
            print(f"    Slowest:  {_seconds_to_hms(valid.max())}")
    elif time_col and time_col == "Time_Finish":
        # Raw format: "0 days HH:MM:SS"
        valid = pd.to_timedelta(df[time_col], errors="coerce").dropna()
        if len(valid) > 0:
            secs = valid.dt.total_seconds()
            print(f"\n  Finish time stats (all finishers):")
            print(f"    Fastest:  {_seconds_to_hms(secs.min())}")
            print(f"    Median:   {_seconds_to_hms(secs.median())}")
            print(f"    Slowest:  {_seconds_to_hms(secs.max())}")

    print()


def _print_year_summary(df: pd.DataFrame, year: int):
    """Print a detailed summary for a single year."""
    total = len(df)

    print(f"\n{'=' * 60}")
    print(f"  VASALOPPET {year} — DETAILED SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total entries: {total:,}")

    # Status breakdown
    if "Status" in df.columns:
        print(f"\n  Status breakdown:")
        status_counts = df["Status"].value_counts(dropna=False)
        for status, count in status_counts.items():
            pct = count / total * 100
            label = status if pd.notna(status) else "(empty/NA)"
            print(f"    {label:<20s} {count:>6,}  ({pct:5.1f}%)")

    # Sex breakdown
    if "Sex" in df.columns:
        print(f"\n  Sex breakdown:")
        sex_counts = df["Sex"].value_counts(dropna=False)
        for sex, count in sex_counts.items():
            pct = count / total * 100
            label = sex if pd.notna(sex) else "(empty/NA)"
            print(f"    {label:<20s} {count:>6,}  ({pct:5.1f}%)")

    # Finish time stats
    time_col = None
    time_is_seconds = False
    if "Finish" in df.columns:
        time_col = "Finish"
        time_is_seconds = True
    elif "Time_Finish" in df.columns:
        time_col = "Time_Finish"

    if time_col:
        if time_is_seconds:
            valid = pd.to_numeric(df[time_col], errors="coerce").dropna()
        else:
            valid = (
                pd.to_timedelta(df[time_col], errors="coerce")
                .dropna()
                .dt.total_seconds()
            )

        if len(valid) > 0:
            print(f"\n  Finish time stats ({len(valid):,} finishers):")
            print(f"    Fastest:  {_seconds_to_hms(valid.min())}")
            print(f"    Median:   {_seconds_to_hms(valid.median())}")
            print(f"    Mean:     {_seconds_to_hms(valid.mean())}")
            print(f"    Slowest:  {_seconds_to_hms(valid.max())}")

            # Percentiles
            print(f"\n  Percentiles:")
            for p in [10, 25, 50, 75, 90]:
                val = valid.quantile(p / 100)
                print(f"    P{p:<3d}      {_seconds_to_hms(val)}")

    # Top finishers (top 10)
    if "Name" in df.columns and time_col:
        print(f"\n  Top 10 finishers:")
        if time_is_seconds:
            df_with_time = df.copy()
            df_with_time["_sort_time"] = pd.to_numeric(df[time_col], errors="coerce")
        else:
            df_with_time = df.copy()
            df_with_time["_sort_time"] = pd.to_timedelta(
                df[time_col], errors="coerce"
            ).dt.total_seconds()

        top = df_with_time.dropna(subset=["_sort_time"]).nsmallest(10, "_sort_time")
        for i, (_, row) in enumerate(top.iterrows(), 1):
            sex = row.get("Sex", "?")
            nation = row.get("Nation", "?")
            t = _seconds_to_hms(row["_sort_time"])
            print(f"    {i:>2}. {row['Name']:<30s} ({sex}/{nation}) {t}")

    # Top nations for this year
    if "Nation" in df.columns:
        print(f"\n  Top 10 nations:")
        nation_counts = df["Nation"].value_counts().head(10)
        for nation, count in nation_counts.items():
            pct = count / total * 100
            print(f"    {nation:<6s} {count:>6,}  ({pct:5.1f}%)")

    # Age group breakdown
    if "Group" in df.columns:
        print(f"\n  Age group breakdown:")
        group_counts = df["Group"].value_counts(dropna=False).head(15)
        for group, count in group_counts.items():
            pct = count / total * 100
            label = group if pd.notna(group) else "(empty/NA)"
            print(f"    {label:<10s} {count:>6,}  ({pct:5.1f}%)")

    # Checkpoint completion (how many had times at each split)
    split_names = [
        "Högsta punkten",
        "Smågan",
        "Mångsbodarna",
        "Risberg",
        "Evertsberg",
        "Oxberg",
        "Hökberg",
        "Eldris",
    ]
    print(f"\n  Checkpoint completion:")
    for split in split_names:
        # Check both clean (seconds) and raw (Time_*) formats
        col = split if split in df.columns else f"Time_{split}"
        if col in df.columns:
            if col == split:
                count = pd.to_numeric(df[col], errors="coerce").notna().sum()
            else:
                count = pd.to_timedelta(df[col], errors="coerce").notna().sum()
            pct = count / total * 100
            print(f"    {split:<20s} {count:>6,} passed  ({pct:5.1f}%)")

    print()


def _seconds_to_hms(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    if pd.isna(seconds):
        return "--:--:--"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    parser = argparse.ArgumentParser(description="Scrape Vasaloppet 90km race results")
    parser.add_argument(
        "--year", type=int, default=None, help="Year to scrape or summarize"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: only 2 pages per sex (~200 results)",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from saved progress on disk"
    )
    parser.add_argument(
        "--supplement",
        type=str,
        default=None,
        help="Path to existing CSV to supplement with missing DNS/DNF entries",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Number of parallel workers (default: {MAX_WORKERS})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path (default: vasaloppet_{year}.csv for scrape, results_clean.csv for clean)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean mode: transform raw CSV to cleaned format (no scraping)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Summary mode: print dataset statistics (use --year for per-year detail)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="results_raw.csv",
        help="Input CSV path for --clean and --summary (default: results_raw.csv)",
    )

    args = parser.parse_args()

    # --clean mode: transform raw CSV → clean CSV, then exit
    if args.clean:
        output = args.output or "results_clean.csv"
        clean_raw_csv(args.input, output)
        return

    # --summary mode: print stats, then exit
    if args.summary:
        summarize_data(args.input, year=args.year)
        return

    # Scraping mode: --year is required
    if args.year is None:
        parser.error("--year is required for scraping")

    output = args.output or f"vasaloppet_{args.year}.csv"

    rows = scrape_year(
        args.year,
        test_mode=args.test,
        workers=args.workers,
        resume=args.resume,
        supplement=args.supplement,
    )
    write_csv(rows, output)

    # Summary
    finished = sum(1 for r in rows if r.get("Status") == "Finished")
    dnf = sum(1 for r in rows if r.get("Status") == "Did Not Finish")
    dns = sum(1 for r in rows if r.get("Status") == "Not Started")
    men = sum(1 for r in rows if r.get("Sex") == "M")
    women = sum(1 for r in rows if r.get("Sex") == "W")
    print(f"\nSummary:")
    print(f"  Total:    {len(rows)}")
    print(f"  Men:      {men}")
    print(f"  Women:    {women}")
    print(f"  Finished: {finished}")
    print(f"  DNF:      {dnf}")
    print(f"  DNS:      {dns}")


if __name__ == "__main__":
    main()
