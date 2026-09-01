#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path
from urllib import request, error

ENDPOINT = "https://apis.justwatch.com/graphql"
COUNTRY = "DE"
LANGUAGE = "de"
PACKAGE = "nfx"
MONETIZATION = "FLATRATE"
PAGE_SIZE = 100

QUERY = r'''
query ProviderCatalog($country: Country!, $language: Language!, $first: Int!, $offset: Int!, $filter: TitleFilter) {
  popularTitles(country: $country, first: $first, offset: $offset, filter: $filter, sortBy: POPULAR) {
    totalCount
    edges {
      node {
        __typename
        ... on Movie {
          id objectType objectId
          content(country: $country, language: $language) {
            title originalTitle originalReleaseYear runtime fullPath posterUrl
          }
          offers(country: $country, platform: WEB) {
            monetizationType presentationType standardWebURL
            package { id packageId clearName shortName technicalName }
          }
        }
        ... on Show {
          id objectType objectId
          content(country: $country, language: $language) {
            title originalTitle originalReleaseYear runtime fullPath posterUrl
          }
          offers(country: $country, platform: WEB) {
            monetizationType presentationType standardWebURL
            package { id packageId clearName shortName technicalName }
          }
        }
      }
    }
  }
}
'''

def post(payload, attempts=4):
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(1, attempts + 1):
        req = request.Request(
            ENDPOINT,
            data=body,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "user-agent": "what2watch-netflix-de-catalog-audit/1.3",
                "origin": "https://www.justwatch.com",
                "referer": "https://www.justwatch.com/",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:4000]
            msg = f"HTTP {exc.code}: {detail}"
            if 400 <= exc.code < 500:
                raise RuntimeError(msg) from exc
            if attempt == attempts:
                raise RuntimeError(msg) from exc
            delay = min(12, 2 ** attempt)
            print(f"request failed attempt={attempt}: {msg}; retrying in {delay}s", flush=True)
            time.sleep(delay)
        except (error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                raise
            delay = min(12, 2 ** attempt)
            print(f"request failed attempt={attempt}: {exc}; retrying in {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")

def package_matches(pkg):
    vals = {
        str(pkg.get("shortName") or "").lower(),
        str(pkg.get("technicalName") or "").lower(),
        str(pkg.get("clearName") or "").lower(),
        str(pkg.get("packageId") or "").lower(),
        str(pkg.get("id") or "").lower(),
    }
    return PACKAGE in vals or any("netflix" in v for v in vals)

def normalized(node):
    content = node.get("content") or {}
    offers = node.get("offers") or []
    matching = []
    for offer in offers:
        if str(offer.get("monetizationType") or "").upper() != MONETIZATION:
            continue
        if not package_matches(offer.get("package") or {}):
            continue
        matching.append({
            "monetization_type": offer.get("monetizationType"),
            "presentation_type": offer.get("presentationType"),
            "web_url": offer.get("standardWebURL"),
            "package": offer.get("package"),
        })
    return {
        "justwatch_id": node.get("id"),
        "object_type": node.get("objectType") or node.get("__typename"),
        "object_id": node.get("objectId"),
        "title": content.get("title"),
        "original_title": content.get("originalTitle"),
        "year": content.get("originalReleaseYear"),
        "runtime": content.get("runtime"),
        "full_path": content.get("fullPath"),
        "poster_url": content.get("posterUrl"),
        "offers": matching,
        "verification": "verified" if matching else "rejected_no_exact_netflix_de_flatrate_offer",
    }

def main():
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    filt = {"packages": [PACKAGE], "monetizationTypes": [MONETIZATION]}
    seen = set()
    records = []
    reported_total = None
    errors = []
    offset = 0
    page = 0

    while True:
        variables = {
            "country": COUNTRY,
            "language": LANGUAGE,
            "first": PAGE_SIZE,
            "offset": offset,
            "filter": filt,
        }
        try:
            res = post({"operationName": "ProviderCatalog", "variables": variables, "query": QUERY})
        except Exception as exc:
            errors.append({"offset": offset, "error": str(exc)})
            break
        if res.get("errors"):
            errors.append({"offset": offset, "error": res["errors"]})
            break
        conn = ((res.get("data") or {}).get("popularTitles") or {})
        current_total = conn.get("totalCount")
        if reported_total is None:
            reported_total = current_total
        elif current_total != reported_total:
            errors.append({"offset": offset, "error": f"totalCount changed {reported_total} -> {current_total}"})
            break
        edges = conn.get("edges") or []
        if not edges:
            if offset < (reported_total or 0):
                errors.append({"offset": offset, "error": "empty page before reported_total"})
            break
        page += 1
        added = 0
        duplicate_keys = []
        for edge in edges:
            node = edge.get("node") or {}
            key = node.get("id") or f"{node.get('objectType')}:{node.get('objectId')}"
            if not key:
                continue
            if key in seen:
                duplicate_keys.append(key)
                continue
            seen.add(key)
            records.append(normalized(node))
            added += 1
        print(f"page={page} offset={offset} edges={len(edges)} added={added} dup={len(duplicate_keys)} unique={len(records)} total={reported_total}", flush=True)
        offset += len(edges)
        if reported_total is not None and offset >= reported_total:
            break
        time.sleep(0.25)

    verified = [r for r in records if r["verification"] == "verified"]
    rejected = [r for r in records if r["verification"] != "verified"]
    coverage_complete = (
        not errors
        and reported_total is not None
        and offset >= reported_total
        and len(records) == reported_total
        and len(seen) == reported_total
        and len(verified) + len(rejected) == len(records)
    )

    catalog = {
        "provider": "Netflix",
        "region": COUNTRY,
        "source": "JustWatch public website GraphQL",
        "pagination": "offset",
        "provider_package": PACKAGE,
        "monetization_type": MONETIZATION,
        "reported_total": reported_total,
        "enumerated": len(records),
        "verified": len(verified),
        "rejected": len(rejected),
        "coverage_complete": coverage_complete,
        "errors": errors,
        "records": records,
    }
    report = {k: v for k, v in catalog.items() if k != "records"}
    report["movie_count"] = sum(1 for r in verified if str(r.get("object_type")).upper() == "MOVIE")
    report["show_count"] = sum(1 for r in verified if str(r.get("object_type")).upper() in {"SHOW", "TV_SHOW"})
    report["with_poster"] = sum(1 for r in verified if r.get("poster_url"))
    report["pages"] = page
    report["final_offset"] = offset

    (out_dir / "netflix-de-catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "netflix-de-crawl-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not coverage_complete:
        print("COVERAGE_COMPLETE=false", file=sys.stderr)
        sys.exit(2)
    print("COVERAGE_COMPLETE=true", flush=True)

if __name__ == "__main__":
    main()
