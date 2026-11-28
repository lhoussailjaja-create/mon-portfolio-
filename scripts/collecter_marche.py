"""Collecte les cours de clôture et les ratios publics par mnémonique."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess

QUOTES_URL = "https://www.yuna.ma/bourse"
RATIOS_URL = "https://casabourse.ma/screener/"
OUTPUT = Path("opportunites-marche.json")


def download(url):
    return subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--location",
         "--max-time", "30", "--retry", "2", url],
        text=True, timeout=100,
    )


def quotes_from(html):
    payload = []
    for block in re.findall(r"<script>self\.__next_f\.push\((.*?)\)</script>", html, re.S):
        part = json.loads(block)
        if part[0] == 1:
            payload.append(part[1])
    stream = "".join(payload)
    for match in re.finditer(r'"initial":\{"date":', stream):
        data, _ = json.JSONDecoder().raw_decode(stream[match.start() + len('"initial":'):])
        if isinstance(data.get("valeurs"), list):
            return data
    raise ValueError("Tableau des cours introuvable")


def fundamentals_from(html):
    marker = "var bourseMarocComparison = "
    payload, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1].lstrip())
    rows = by_symbol(payload["allData"])
    if len(rows) < 60:
        raise ValueError("Couverture du screener insuffisante")
    return rows


def by_symbol(rows):
    result = {}
    for row in rows:
        symbol = row["symbol"]
        if not re.fullmatch(r"[A-Z0-9]{2,8}", symbol) or symbol in result:
            raise ValueError(f"Mnémonique invalide ou répété : {symbol}")
        result[symbol] = row
    return result


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def fundamentals(row, price, session_year):
    year = row.get("latest_year")
    if type(year) is not int or not 2000 <= year < session_year:
        year = None
    details = (row.get("cagr_periods", {}).get("net_income_cagr", {}).get("1") or {}).get("details") or {}
    current = number(details.get("last_value"))
    prior = number(details.get("first_value"))
    growth = None
    if year and details.get("last_year") == year and details.get("first_year") == year - 1 and current is not None and prior and prior > 0:
        growth = 100 * (current / prior - 1)
    income = number(row.get("latest_net_income"))
    shares = number(row.get("shares_outstanding"))
    per = price * shares / income if year and price and shares and shares > 0 and income and income > 0 else None
    published_price = number(row.get("current_price"))
    month = number(row.get("performance_1m")) if price and published_price == price else None
    return {"year": year, "net_income": income if year else None, "growth": growth, "per": per, "month": month}


def main():
    prior = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    now = datetime.now(timezone.utc)
    data = quotes_from(download(QUOTES_URL))
    session = date.fromisoformat(data["date"])
    if data.get("seance", {}).get("ouverte") or session > now.date():
        raise ValueError("Dernière clôture non confirmée")
    quotes = by_symbol(data["valeurs"])
    if len(quotes) < max(60, len(prior.get("rows", [])) - 3) or data["date"] < prior.get("date", ""):
        raise ValueError("Séance antérieure ou couverture insuffisante")
    collection_complete = True
    try:
        ratios = fundamentals_from(download(RATIOS_URL))
    except (KeyError, ValueError, IndexError, subprocess.SubprocessError) as error:
        print(f"Ratios indisponibles : {error}")
        ratios = {}
        collection_complete = False
    previous_rows = by_symbol(prior.get("rows", []))
    rows = []
    for symbol in sorted(quotes.keys() | ratios.keys() | previous_rows.keys()):
        quote, ratio = quotes.get(symbol, {}), ratios.get(symbol, {})
        old = previous_rows.get(symbol, {})
        # Keep symbols absent from both sources during a partial collection only.
        if not quote and not ratio and collection_complete:
            continue
        price = number(quote.get("cours"))
        volume = number(quote.get("volume_mad"))
        slug = quote.get("slug", "")
        ratio_url = ratio.get("url", "")
        row = {
            "symbol": symbol,
            "name": quote.get("nom") or ratio.get("name") or old["name"],
            "sector": ratio.get("sector_fr") or quote.get("secteur") or old.get("sector", ""),
            "price": price if price and price > 0 else None,
            "volume": volume if volume is not None and volume >= 0 else None,
            "change": number(quote.get("change_percent")),
            "quote_url": QUOTES_URL + "/" + slug if re.fullmatch(r"[a-z0-9-]+", slug) else QUOTES_URL,
            "ratio_url": ratio_url if re.fullmatch(r"https://casabourse\.ma/entreprise/[a-z0-9-]+/", ratio_url) else RATIOS_URL,
            **fundamentals(ratio, price, session.year),
        }
        rows.append(row)
    OUTPUT.write_text(json.dumps({
        "date": data["date"], "checked_at": now.isoformat(timespec="seconds"),
        "ratios_available": collection_complete, "rows": rows,
    }, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    print(f"{len(rows)} actions, {len(quotes)} valeurs dans le flux de séance, date {session}")


if __name__ == "__main__":
    main()
