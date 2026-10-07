#!/usr/bin/env python3
"""Download textbooks from China's National Smart Education Platform.

Platform: https://basic.smartedu.cn/tchMaterial
No login required; uses the platform's public JSON endpoints.

Usage:
  smartedu.py search <keyword> [keyword ...] [--publisher NAME] [--limit N]
  smartedu.py download <contentId|URL> [-o DIR] [--name FILE] [--raw-name]
  smartedu.py get <keyword> [keyword ...] [--publisher NAME] [-o DIR] [--first]
  smartedu.py refresh                # rebuild the cached catalog

Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

CATALOG_INDEX = (
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"
)
DETAIL_URL = (
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{cid}.json"
)
CACHE_DIR = os.path.expanduser(
    os.environ.get("SMARTEDU_CACHE", "~/.cache/smartedu-textbook")
)
CATALOG_CACHE = os.path.join(CACHE_DIR, "catalog.json")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _ascii_url(url: str) -> str:
    """Percent-encode non-ASCII chars (e.g. Chinese filenames) but keep reserved chars."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")


def _request(url: str, headers: dict | None = None) -> urllib.request.Request:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    return urllib.request.Request(_ascii_url(url), headers=h)


def get_json(url: str, retries: int = 4, timeout: int = 60):
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def http_total_size(url: str) -> int | None:
    try:
        with urllib.request.urlopen(_request(url, {"Range": "bytes=0-0"}), timeout=60) as r:
            cr = r.headers.get("Content-Range")  # e.g. bytes 0-0/12345
            if cr and "/" in cr:
                return int(cr.split("/")[-1])
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:  # noqa: BLE001
        return None


def is_complete_pdf(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(-min(2048, os.path.getsize(path)), os.SEEK_END)
        tail = f.read()
    return head == b"%PDF-" and b"%%EOF" in tail


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def _fetch_part(url: str):
    return get_json(url, retries=4, timeout=120)


def build_catalog() -> list[dict]:
    index = get_json(CATALOG_INDEX)
    part_urls = [u.strip() for u in index["urls"].split(",") if u.strip()]
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(6, len(part_urls))) as ex:
        for part in ex.map(_fetch_part, part_urls):
            if isinstance(part, list):
                items.extend(part)
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CATALOG_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    os.replace(tmp, CATALOG_CACHE)
    return items


def load_catalog(refresh: bool = False) -> list[dict]:
    if refresh or not os.path.exists(CATALOG_CACHE):
        print("Building catalog cache (first run, ~35 MB) ...", file=sys.stderr)
        return build_catalog()
    with open(CATALOG_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _title(item: dict) -> str:
    gt = item.get("global_title") or {}
    return gt.get("zh-CN") or item.get("title") or ""


def _publisher(item: dict) -> str:
    pl = item.get("provider_list") or []
    return pl[0].get("name", "") if pl else ""


def _edition(item: dict) -> str:
    for tag in item.get("tag_list") or []:
        if tag.get("tag_dimension_id") == "zxxbb":
            return tag.get("tag_name", "")
    return ""


def search_items(catalog: list[dict], keywords: list[str], publisher: str | None):
    out = []
    kws = [k.lower() for k in keywords]
    for item in catalog:
        title = _title(item)
        pub = _publisher(item)
        haystack = " ".join([title, pub, _edition(item)]).lower()
        if all(k in haystack for k in kws) and (
            not publisher or publisher.lower() in pub.lower()
        ):
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Detail / download
# --------------------------------------------------------------------------- #
def extract_content_id(value: str) -> str:
    m = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        value,
    )
    if not m:
        raise SystemExit(f"Could not find a contentId in: {value}")
    return m.group(0)


def get_pdf_info(content_id: str) -> tuple[str, str, str, str]:
    """Return (public_pdf_url, original_filename, title, edition) for a contentId."""
    detail = get_json(DETAIL_URL.format(cid=content_id))
    title = (detail.get("global_title") or {}).get("zh-CN") or detail.get("title") or ""
    edition = _edition(detail)
    for ti in detail.get("ti_items") or []:
        for storage in ti.get("ti_storages") or []:
            if storage.lower().endswith(".pdf"):
                url = storage.replace("-private.", ".")  # public mirror
                return url, urllib.parse.unquote(os.path.basename(url)), title, edition
    raise SystemExit(
        f"No downloadable PDF found for {content_id}. "
        "This title may only be available as images."
    )


def download(url: str, dest: str, total: int | None = None, retries: int = 12) -> str:
    if total is None:
        total = http_total_size(url)
    for attempt in range(1, retries + 1):
        pos = os.path.getsize(dest) if os.path.exists(dest) else 0
        if total is not None and pos >= total:
            break
        headers = {}
        mode = "wb"
        if pos > 0:
            headers["Range"] = f"bytes={pos}-"
            mode = "ab"
        try:
            with urllib.request.urlopen(
                _request(url, headers), timeout=120
            ) as resp:
                status = getattr(resp, "status", 200)
                if status == 206:
                    cr = resp.headers.get("Content-Range", "")
                    if "/" in cr:
                        total = int(cr.split("/")[-1])
                elif status == 200:
                    pos, mode = 0, "wb"
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        total = int(cl)
                with open(dest, mode) as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                cur = os.path.getsize(dest)
                pct = f" ({cur * 100 // total}%)" if total else ""
                print(
                    f"  attempt {attempt}: {cur}/{total or '?'} bytes{pct}",
                    file=sys.stderr,
                )
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt} error: {e}", file=sys.stderr)
        if total is not None and os.path.getsize(dest) >= total:
            break
        time.sleep(min(2 * attempt, 10))
    if not is_complete_pdf(dest):
        raise SystemExit(f"Download incomplete or corrupted: {dest}")
    return dest


def clean_title(title: str) -> str:
    title = re.sub(r"^（[^）]*）", "", title).strip()  # drop leading （...修订）
    return title.replace("•", "·").replace("/", "_").strip()


def default_name(title: str, edition: str, original: str) -> str:
    base = clean_title(title) if title else os.path.splitext(original)[0]
    if edition and edition not in base:
        base = f"{base}（{edition}）"
    return f"{base}.pdf"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_search(args) -> None:
    catalog = load_catalog(refresh=args.refresh)
    matches = search_items(catalog, args.keywords, args.publisher)
    if not matches:
        print("No matching textbook found.")
        return
    seen = set()
    shown = 0
    for item in matches:
        key = (item["id"], _publisher(item))
        if key in seen:
            continue
        seen.add(key)
        ed = _edition(item)
        print(f"{item['id']}  {_title(item)}")
        print(f"    publisher: {_publisher(item) or '-'}   edition: {ed or '-'}")
        shown += 1
        if args.limit and shown >= args.limit:
            break
    print(f"\n{shown} result(s). Download with: smartedu.py download <contentId>")


def _resolve_dest(args, original, title, edition, total) -> str:
    directory = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(directory, exist_ok=True)
    if args.name:
        filename = args.name
    elif args.raw_name:
        filename = original
    else:
        filename = default_name(title, edition, original)
    path = os.path.join(directory, filename)
    # If a different (complete) revision already sits at this name, keep both.
    if os.path.exists(path) and is_complete_pdf(path) and total and os.path.getsize(path) != total:
        root, ext = os.path.splitext(filename)
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(directory, f"{root} ({n}){ext}")
    return path


def _download_by_id(content_id: str, args, title="", edition="") -> None:
    url, original, d_title, d_edition = get_pdf_info(content_id)
    title = title or d_title
    edition = edition or d_edition
    total = http_total_size(url)
    dest = _resolve_dest(args, original, title, edition, total)
    print(f"Downloading: {dest}", file=sys.stderr)
    download(url, dest, total=total)
    size = os.path.getsize(dest)
    print(f"OK  {dest}  ({size / 1048576:.1f} MB)")


def cmd_download(args) -> None:
    content_id = extract_content_id(args.target)
    _download_by_id(content_id, args)


def cmd_get(args) -> None:
    catalog = load_catalog(refresh=args.refresh)
    matches = search_items(catalog, args.keywords, args.publisher)
    if not matches:
        raise SystemExit("No matching textbook found.")
    seen, uniq = set(), []
    for item in matches:
        key = (item["id"], _publisher(item))
        if key not in seen:
            seen.add(key)
            uniq.append(item)
    if len(uniq) > 1 and not args.first:
        print(f"{len(uniq)} matches; add --publisher or --first, or download by id:\n")
        for item in uniq:
            print(f"{item['id']}  {_title(item)}  [{_publisher(item)}/{_edition(item)}]")
        return
    item = uniq[0]
    _download_by_id(item["id"], args, _title(item), _edition(item))


def cmd_refresh(args) -> None:
    items = build_catalog()
    print(f"Catalog rebuilt: {len(items)} textbooks -> {CATALOG_CACHE}")


# --------------------------------------------------------------------------- #
def add_out_args(p):
    p.add_argument("-o", "--out", default=".", help="output directory (default: .)")
    p.add_argument("--name", help="explicit output filename")
    p.add_argument("--raw-name", action="store_true", help="use the platform's original filename")


def main() -> None:
    ap = argparse.ArgumentParser(description="Download textbooks from basic.smartedu.cn")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search the textbook catalog by name")
    s.add_argument("keywords", nargs="+")
    s.add_argument("--publisher", help="filter by publisher, e.g. 人民教育出版社")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--refresh", action="store_true", help="rebuild catalog cache")
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("download", help="download by contentId or detail URL")
    d.add_argument("target", help="contentId or basic.smartedu.cn detail URL")
    add_out_args(d)
    d.set_defaults(func=cmd_download)

    g = sub.add_parser("get", help="search by name and download the match")
    g.add_argument("keywords", nargs="+")
    g.add_argument("--publisher", help="filter by publisher")
    g.add_argument("--first", action="store_true", help="take the first match without asking")
    g.add_argument("--refresh", action="store_true")
    add_out_args(g)
    g.set_defaults(func=cmd_get)

    r = sub.add_parser("refresh", help="rebuild catalog cache")
    r.set_defaults(func=cmd_refresh)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
