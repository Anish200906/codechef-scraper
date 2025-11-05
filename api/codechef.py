from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

# ---- Scraper function ----
def fetch_all_user_submissions(handle):
    all_rows = []
    page = 0

    while True:
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
        page += 1

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
    df["language"] = df["language"].str.upper().replace({
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


# ---- Vercel-compatible HTTP handler ----
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(self.path).query)
        handle = query.get("handle", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if not handle:
            self.wfile.write(json.dumps({"error": "Missing 'handle' parameter"}).encode())
            return

        try:
            result = fetch_all_user_submissions(handle)
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)}).encode())