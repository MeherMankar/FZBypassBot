import requests, re
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
url = "https://vipshort.in/eLOx9Jx"

s = requests.Session()
r = s.get(url, headers={"User-Agent": UA}, timeout=15, allow_redirects=False)
print(f"Status: {r.status_code}, Location: {r.headers.get('location','none')[:100]}")
if r.status_code == 200:
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"Title: {soup.title.text.strip()[:60] if soup.title else 'none'}")
    print(f"Body: {r.text[:500]}")
