from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

# ---------------- CACHE ----------------
# Store data for 30 minutes (1800 seconds)
CACHE_TTL = 1800
cache = {}

def fetch_and_clean_user_submissions(handle, max_pages=5):
    all_rows = []

    for page in range(max_pages):
        url = f"https://www.codechef.com/recent/user?user_handle={handle}&page={page}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("tr")
        if not rows:
            break

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            all_rows.append({
                "time": cols[0].get_text(" ", strip=True),
                "problem": cols[1].get_text(" ", strip=True),
                "result": cols[2].get_text(" ", strip=True),
                "language": cols[3].get_text(" ", strip=True),
                "score": cols[4].get_text(" ", strip=True)
            })

    df = pd.DataFrame(all_rows)
    if df.empty:
        return []

    def clean_html(text):
        if pd.isna(text):
            return ""
        return BeautifulSoup(text.replace("\\/", "/"), "html.parser").get_text(" ", strip=True)

    for col in df.columns:
        df[col] = df[col].astype(str).apply(clean_html)

    df["time"] = df["time"].str.extract(r'(\d{2}:\d{2}\s[AP]M\s\d{2}/\d{2}/\d{2})')
    df["problem_code"] = df["problem"].str.extract(r'([A-Z0-9_]+)')
    df["score"] = df["score"].str.extract(r'(\d+\.?\d*)').astype(float)
    df["status"] = df["result"].str.extract(r'(AC|WA|TLE|RTE|CE|PS)', expand=False)

    df["language"] = df["language"].str.upper()
    df["language"] = df["language"].replace({
        r"PYTH.*": "PYTHON",
        r"C\+\+.*": "C++",
        r"JAVA.*": "JAVA",
        r"KOTLIN.*": "KOTLIN",
        r"PYPY.*": "PYPY",
        r"GO.*": "GO",
        r"RUST.*": "RUST",
        r"C$": "C"
    }, regex=True)
    df["language"] = df["language"].str.extract(r"^(C\+\+|PYTHON|JAVA|C|KOTLIN|PYPY|GO|RUST)$", expand=False)

    clean_df = df[["time", "problem_code", "score", "language", "status"]].dropna(subset=["language"])
    return clean_df.to_dict(orient="records")


# ---------------- MAIN HANDLER ----------------
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            handle = query.get("handle", [None])[0]
            max_pages = int(query.get("pages", [5])[0])

            if not handle:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing ?handle=<username>"}')
                return

            # --- CACHE CHECK ---
            now = time.time()
            if handle in cache and now - cache[handle]["time"] < CACHE_TTL:
                data = cache[handle]["data"]
                from_cache = True
            else:
                data = fetch_and_clean_user_submissions(handle, max_pages)
                cache[handle] = {"data": data, "time": now}
                from_cache = False

            # --- RESPONSE ---
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {
                "user": handle,
                "cached": from_cache,
                "cache_age_sec": int(now - cache[handle]["time"]),
                "submissions": data
            }
            self.wfile.write(json.dumps(response, indent=2).encode())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
