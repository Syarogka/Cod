#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions: скачивает недостающие картинки Orna Codex в отдельный ZIP-артефакт.
Не изменяет сайт и не делает commit.
"""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json, zipfile, time, sys

ROOT = Path(__file__).resolve().parent
ITEMS_FILE = ROOT / "missing_orna_images.json"
OUT_DIR = ROOT / "downloaded_missing_orna_images"
ZIP_OUT = ROOT / "orna_missing_images_downloaded.zip"
LOG_OK = ROOT / "downloaded_ok.txt"
LOG_FAIL = ROOT / "downloaded_failed.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OrnaCodexMirror/1.0; GitHub Actions asset backup)"
}

def fetch(url: str, dest: Path, retries: int = 3) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True, "already exists"
    last = ""
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=30) as r:
                data = r.read()
            if not data:
                last = "empty response"
            else:
                dest.write_bytes(data)
                return True, "ok"
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            last = str(e)
        time.sleep(1.5 * attempt)
    return False, last

def main():
    if not ITEMS_FILE.exists():
        print(f"Missing file: {ITEMS_FILE}")
        sys.exit(1)

    items = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok, fail = [], []

    print(f"Images to download: {len(items)}")
    for i, item in enumerate(items, 1):
        url = item["url"]
        rel = item["path"].lstrip("/").replace("\\", "/")
        dest = OUT_DIR / rel
        print(f"[{i}/{len(items)}] {rel}")
        success, msg = fetch(url, dest)
        if success:
            ok.append(rel)
        else:
            fail.append(f"{url}\t{msg}")
            print(f"  FAILED: {msg}")

    LOG_OK.write_text("\n".join(ok) + ("\n" if ok else ""), encoding="utf-8")
    LOG_FAIL.write_text("\n".join(fail) + ("\n" if fail else ""), encoding="utf-8")

    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in OUT_DIR.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(OUT_DIR))
        z.write(LOG_OK, LOG_OK.name)
        z.write(LOG_FAIL, LOG_FAIL.name)

    print("Done")
    print(f"Downloaded: {len(ok)}")
    print(f"Failed: {len(fail)}")
    print(f"ZIP: {ZIP_OUT}")
    # Не валим workflow, если часть картинок не скачалась: пользователь всё равно сможет забрать частичный ZIP.

if __name__ == "__main__":
    main()
