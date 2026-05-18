"""
export_json.py  —  runs the arb scanner and writes data.json for index.html
Usage: python export_json.py
"""

import json, math, sys
from datetime import datetime, timezone, date as _date
from pathlib import Path

# ── inline the config & logic from compare8.py so this file is self-contained ─

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

PM_BASE     = "https://gateway.polymarket.us/v1"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
KAL_HEADERS = {"Accept": "application/json"}
PM_THETA    = 0.05
KAL_THETA   = 0.07
CONTRACTS   = 100
PAYOUT      = 100.0

SETTLEMENT_DATES = {
    "nhl": _date(2026,  6, 30),
    "mlb": _date(2026, 11, 30),
    "wc":  _date(2026,  7, 30),
    "mls": _date(2026, 12, 30),
}

def settle_days(key):
    return max((_date.today() - SETTLEMENT_DATES[key]).days * -1, 1)

def irr(combined, days):
    return (PAYOUT / combined) ** (365.0 / days) - 1.0

def pm_fee(p, c):
    return PM_THETA * c * p * (1 - p)

def kal_fee(p, c):
    return math.ceil(KAL_THETA * c * p * (1 - p) * 100) / 100

def total_cost(p, fee, c):
    return p * c + fee

SPORTS = [
    {
        "label": "MLB World Series Champion", "settlement_key": "mlb",
        "pm_event_slug": "world-series-2025",
        "pm_slug_prefix": "tec-mlb-champ-2026-09-27-",
        "kal_event": "KXMLB-26",
        "team_map": [
            ("lad","LAD","Los Angeles Dodgers"),("nyy","NYY","New York Yankees"),
            ("atl","ATL","Atlanta Braves"),("sea","SEA","Seattle Mariners"),
            ("chc","CHC","Chicago Cubs"),("tb","TB","Tampa Bay Rays"),
            ("tex","TEX","Texas Rangers"),("phi","PHI","Philadelphia Phillies"),
            ("tor","TOR","Toronto Blue Jays"),("mil","MIL","Milwaukee Brewers"),
            ("det","DET","Detroit Tigers"),("ath","ATH","Athletics"),
            ("sd","SD","San Diego Padres"),("kc","KC","Kansas City Royals"),
            ("bos","BOS","Boston Red Sox"),("bal","BAL","Baltimore Orioles"),
            ("cle","CLE","Cleveland Guardians"),("pit","PIT","Pittsburgh Pirates"),
            ("nym","NYM","New York Mets"),("sf","SF","San Francisco Giants"),
            ("hou","HOU","Houston Astros"),("az","AZ","Arizona Diamondbacks"),
            ("min","MIN","Minnesota Twins"),("cin","CIN","Cincinnati Reds"),
            ("cws","CWS","Chicago White Sox"),("stl","STL","St. Louis Cardinals"),
            ("wsh","WSH","Washington Nationals"),("laa","LAA","Los Angeles Angels"),
            ("col","COL","Colorado Rockies"),("mia","MIA","Miami Marlins"),
        ],
    },
    {
        "label": "NHL Stanley Cup Champion", "settlement_key": "nhl",
        "pm_event_slug": "tec-NHL-scw-2026-06-30",
        "pm_slug_prefix": "tec-nhl-scw-2026-06-30-",
        "kal_event": "KXNHL-26",
        "team_map": [
            ("col","COL","Colorado Avalanche"),("car","CAR","Carolina Hurricanes"),
            ("veg","VGK","Vegas Golden Knights"),("mon","MTL","Montreal Canadiens"),
            ("buf","BUF","Buffalo Sabres"),
        ],
    },
    {
        "label": "FIFA Men's World Cup Winner", "settlement_key": "wc",
        "pm_event_slug": "fifa-wc-2026-07-19-winner",
        "pm_slug_prefix": "tec-fifa-wc-2026-07-19-winner-",
        "kal_event": "KXMENWORLDCUP-26",
        "team_map": [
            ("esp","ES","Spain"),("fra","FR","France"),("eng","GB","England"),
            ("arg","AR","Argentina"),("por","PT","Portugal"),("bra","BR","Brazil"),
            ("ger","DE","Germany"),("ned","NL","Netherlands"),("usa","US","United States"),
            ("jpn","JP","Japan"),("bel","BE","Belgium"),("nor","NO","Norway"),
            ("col","CO","Colombia"),("mar","MA","Morocco"),("cro","HR","Croatia"),
            ("uru","UY","Uruguay"),("mex","MX","Mexico"),("tur","TR","Turkiye"),
            ("sui","CH","Switzerland"),("can","CA","Canada"),("aus","AU","Australia"),
            ("kor","KR","Korea Republic"),("ksa","SA","Saudi Arabia"),
            ("pan","PAN","Panama"),("par","PY","Paraguay"),("sen","SN","Senegal"),
        ],
    },
    {
        "label": "MLB American League Champion", "settlement_key": "mlb",
        "pm_event_slug": "mlb-alchamp-2026-09-27",
        "pm_slug_prefix": "tec-mlb-alchamp-2026-09-27-",
        "kal_event": "KXMLBAL-26",
        "team_map": [
            ("nyy","NYY","New York Yankees"),("sea","SEA","Seattle Mariners"),
            ("tb","TB","Tampa Bay Rays"),("tex","TEX","Texas Rangers"),
            ("det","DET","Detroit Tigers"),("tor","TOR","Toronto Blue Jays"),
            ("cle","CLE","Cleveland Guardians"),("bal","BAL","Baltimore Orioles"),
            ("ath","ATH","Athletics"),("kc","KC","Kansas City Royals"),
            ("bos","BOS","Boston Red Sox"),("hou","HOU","Houston Astros"),
            ("min","MIN","Minnesota Twins"),("cws","CWS","Chicago White Sox"),
            ("laa","LAA","Los Angeles Angels"),
        ],
    },
    {
        "label": "MLB National League Champion", "settlement_key": "mlb",
        "pm_event_slug": "mlb-nlchamp-2026-09-27",
        "pm_slug_prefix": "tec-mlb-nlchamp-2026-09-27-",
        "kal_event": "KXMLBNL-26",
        "team_map": [
            ("lad","LAD","Los Angeles Dodgers"),("atl","ATL","Atlanta Braves"),
            ("chc","CHC","Chicago Cubs"),("phi","PHI","Philadelphia Phillies"),
            ("mil","MIL","Milwaukee Brewers"),("nym","NYM","New York Mets"),
            ("sd","SD","San Diego Padres"),("pit","PIT","Pittsburgh Pirates"),
            ("az","AZ","Arizona Diamondbacks"),("cin","CIN","Cincinnati Reds"),
            ("stl","STL","St. Louis Cardinals"),("sf","SF","San Francisco Giants"),
            ("col","COL","Colorado Rockies"),("mia","MIA","Miami Marlins"),
            ("wsh","WSH","Washington Nationals"),
        ],
    },
    {
        "label": "MLB AL MVP", "settlement_key": "mlb",
        "pm_event_slug": "mlb-al-2026-11-27-mvp",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-mvp-",
        "kal_event": "KXMLBALMVP-26",
        "team_map": [
            ("aarjud","AJUD","Aaron Judge"),("yoralv","YALV","Yordan Alvarez"),
            ("bobwit","RWIT","Bobby Witt Jr."),("josram","JRAM","Jose Ramirez"),
            ("gunhen","GHEN","Gunnar Henderson"),("vlague","VGUE","Vladimir Guerrero Jr."),
            ("julrod","JROD","Julio Rodriguez"),("calral","CRAL","Cal Raleigh"),
            ("jazchi","JCHI","Jazz Chisholm Jr."),("benric","BRIC","Ben Rice"),
            ("nickur","NKUR","Nick Kurtz"),("miktro","MTRO","Mike Trout"),
            ("juncam","JCAM","Junior Caminero"),("petalo","PALO","Pete Alonso"),
            ("jerpen","JPEN","Jeremy Pena"),("ranaro","RARO","Randy Arozarena"),
            ("byrbux","BBUX","Byron Buxton"),("codbel","CBEL","Cody Bellinger"),
            ("colmon","CMON","Colson Montgomery"),("jacwil","JWIL","Jacob Wilson"),
            ("stekwa","SKWA","Steven Kwan"),("zacnet","ZNET","Zach Neto"),
            ("adlrut","ARUT","Adley Rutschman"),("corsea","CSEA","Corey Seager"),
            ("romant","RANT","Roman Anthony"),
        ],
    },
    {
        "label": "MLB NL MVP", "settlement_key": "mlb",
        "pm_event_slug": "mlb-nl-2026-11-27-mvp",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-mvp-",
        "kal_event": "KXMLBNLMVP-26",
        "team_map": [
            ("shooht","SOHT","Shohei Ohtani"),("matcha","MCHA","Matt Chapman"),
            ("moobet","MBET","Mookie Betts"),("matols","MOLS","Matt Olson"),
            ("bryhar","BHAR","Bryce Harper"),("ellcru","ECRU","Elly De La Cruz"),
            ("juasot","JSOT","Juan Soto"),("frefre","FFRE","Freddie Freeman"),
            ("ronacu","RACU","Ronald Acuna Jr."),("nichoe","NHOE","Nico Hoerner"),
            ("kylsch","KSCH","Kyle Schwarber"),("jamwoo","JWOO","James Wood"),
            ("jorwal","JWAL","Jordan Walker"),("kyltuc","KTUC","Kyle Tucker"),
            ("pauske","PSKE","Paul Skenes"),("corcar","CCAR","Corbin Carroll"),
            ("fertat","FTAT","Fernando Tatis Jr."),("fralin","FLIN","Francisco Lindor"),
            ("jaccho","JCHO","Jackson Chourio"),("jacmer","JMER","Jackson Merrill"),
            ("ketmar","KMAR","Ketel Marte"),("wilada","WADA","Willy Adames"),
            ("rafdev","RDEV","Rafael Devers"),("tretur","TTUR","Trea Turner"),
            ("yosyam","YYAM","Yoshinobu Yamamoto"),
        ],
    },
    {
        "label": "MLB AL Rookie of the Year", "settlement_key": "mlb",
        "pm_event_slug": "mlb-al-2026-11-27-roy",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-roy-",
        "kal_event": "KXMLBALROTY-26",
        "team_map": [
            ("kevmcg","KMCG","Kevin McGonigle"),("munmur","MMUR","Munetaka Murakami"),
            ("chadel","CDEL","Chase DeLauter"),("kazoka","KOKA","Kazuma Okamoto"),
            ("treyes","TYES","Trey Yesavage"),("paytol","PTOL","Payton Tolle"),
            ("sambas","SBAS","Samuel Basallo"),("trabaz","TBAZ","Travis Bazzana"),
            ("carwil","CWIL","Carson Williams"),
        ],
    },
    {
        "label": "MLB NL Rookie of the Year", "settlement_key": "mlb",
        "pm_event_slug": "mlb-nl-2026-11-27-roy",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-roy-",
        "kal_event": "KXMLBNLROTY-26",
        "team_map": [
            ("jamwoo","JWOO","James Wood"),("jaccho","JCHO","Jackson Chourio"),
            ("jacmer","JMER","Jackson Merrill"),("drabal","DBAL","Drake Baldwin"),
            ("petarm","PCRO","Pete Crow-Armstrong"),("micbus","MBUS","Michael Busch"),
        ],
    },
    {
        "label": "MLB AL Cy Young", "settlement_key": "mlb",
        "pm_event_slug": "mlb-al-2026-11-27-cy-young",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-cy-young-",
        "kal_event": "KXMLBALCY-26",
        "team_map": [
            ("logweb","LWEB","Logan Webb"),("taiwal","TWAL","Taijuan Walker"),
            ("codmor","CMOR","Cody Morris"),("lucgio","LGIO","Lucas Giolito"),
        ],
    },
    {
        "label": "MLB NL Cy Young", "settlement_key": "mlb",
        "pm_event_slug": "mlb-nl-2026-11-27-cy-young",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-cy-young-",
        "kal_event": "KXMLBNLCY-26",
        "team_map": [
            ("pauske","PSKE","Paul Skenes"),("yosyam","YYAM","Yoshinobu Yamamoto"),
            ("zacwhe","ZWHE","Zack Wheeler"),("chrbas","CBAS","Chris Bassitt"),
        ],
    },
    {
        "label": "MLS Cup Champion", "settlement_key": "mls",
        "pm_event_slug": "mls-cup-2026",
        "pm_slug_prefix": "tec-mlscup-2026-12-06-",
        "kal_event": "KXMLS-26",
        "team_map": [
            ("int","INTER","Inter Miami CF"),("nycfc","NYCFC","New York City FC"),
            ("sea","SEA","Seattle Sounders"),("la","LAFC","LAFC"),
            ("atx","ATX","Austin FC"),("por","POR","Portland Timbers"),
            ("rsl","RSL","Real Salt Lake"),("col","COL","Colorado Rapids"),
            ("chi","CHI","Chicago Fire FC"),("tor","TOR","Toronto FC"),
            ("phi","PHI","Philadelphia Union"),("ner","NE","New England Revolution"),
            ("atl","ATL","Atlanta United FC"),("dal","DAL","FC Dallas"),
            ("nyr","NY","New York Red Bulls"),("skc","SKC","Sporting Kansas City"),
            ("dcu","DC","D.C. United"),("aus","ATX","Austin FC"),
        ],
    },
]

# ── Fetching ──────────────────────────────────────────────────────────────────

def pm_extract_prices(mkt):
    yes_ask = no_ask = None
    baq = mkt.get("bestAskQuote")
    if baq and baq.get("value") is not None:
        yes_ask = float(baq["value"])
    bbq = mkt.get("bestBidQuote")
    if bbq and bbq.get("value") is not None:
        no_ask = round(1.0 - float(bbq["value"]), 6)
    if yes_ask is None or no_ask is None:
        for side in (mkt.get("marketSides") or []):
            if side.get("long") is True:
                raw = side.get("price")
                if raw is not None:
                    if yes_ask is None: yes_ask = float(raw)
                    if no_ask is None:  no_ask = round(1.0 - float(raw), 6)
                break
    return yes_ask, no_ask

def fetch_pm_prices(sport):
    prefix = sport["pm_slug_prefix"]
    prices = {}
    suffix_by_slug = {prefix + ps: ps for ps, _, _ in sport["team_map"]}
    try:
        r = requests.get(f"{PM_BASE}/events/slug/{sport['pm_event_slug']}", timeout=12)
        r.raise_for_status()
        data = r.json()
        event = data.get("event") or data
        for mkt in (event.get("markets") or event.get("outcomes") or []):
            slug = (mkt.get("slug") or mkt.get("marketSlug") or "").strip()
            ps = suffix_by_slug.get(slug)
            if ps is not None:
                ya, na = pm_extract_prices(mkt)
                prices[ps] = {"yes_ask": ya, "no_ask": na}
    except Exception as e:
        print(f"  PM bulk failed ({sport['pm_event_slug']}): {e}", file=sys.stderr)
    for ps, _, name in sport["team_map"]:
        existing = prices.get(ps, {})
        if existing.get("yes_ask") is None or existing.get("no_ask") is None:
            try:
                r = requests.get(f"{PM_BASE}/market/slug/{prefix + ps}", timeout=10)
                r.raise_for_status()
                mkt = r.json().get("market") or r.json()
                ya, na = pm_extract_prices(mkt)
                prices[ps] = {"yes_ask": existing.get("yes_ask") or ya,
                               "no_ask":  existing.get("no_ask")  or na}
            except Exception:
                prices.setdefault(ps, {"yes_ask": None, "no_ask": None})
    return prices

def fetch_kalshi_prices(sport):
    event_ticker = sport["kal_event"]
    prices = {}
    bulk = {}
    try:
        r = requests.get(f"{KALSHI_BASE}/events/{event_ticker}",
                         params={"with_nested_markets": "true"},
                         headers=KAL_HEADERS, timeout=15)
        r.raise_for_status()
        for mkt in (r.json().get("event", {}).get("markets") or []):
            if mkt.get("status") == "finalized": continue
            ticker = mkt.get("ticker", "")
            suf = ticker.rsplit("-", 1)[-1].upper() if "-" in ticker else ""
            if suf: bulk[suf] = mkt
    except Exception as e:
        print(f"  KAL bulk failed ({event_ticker}): {e}", file=sys.stderr)
    for _, ks, name in sport["team_map"]:
        mkt = bulk.get(ks.upper())
        if mkt is None:
            try:
                r = requests.get(f"{KALSHI_BASE}/markets/{event_ticker}-{ks}",
                                  headers=KAL_HEADERS, timeout=10)
                r.raise_for_status()
                mkt = r.json().get("market", r.json())
                if mkt.get("status") == "finalized":
                    prices[ks] = {"no_ask": None, "yes_ask": None}
                    continue
            except Exception:
                prices[ks] = {"no_ask": None, "yes_ask": None}
                continue
        f = lambda k: float(v) if (v := mkt.get(k)) is not None else None
        prices[ks] = {
            "no_ask":  f("no_ask_dollars") or f("no_ask") or f("no_ask_price"),
            "yes_ask": f("yes_ask_dollars") or f("yes_ask") or f("yes_ask_price"),
        }
    return prices

def build_rows(sport, pm, kal, contracts, direction):
    days = settle_days(sport["settlement_key"])
    rows = []
    for ps, ks, name in sport["team_map"]:
        pmd  = pm.get(ps) or {}
        kald = kal.get(ks) or {}
        pm_ask  = pmd.get("yes_ask")  if direction == "A" else pmd.get("no_ask")
        kal_ask = kald.get("no_ask")  if direction == "A" else kald.get("yes_ask")
        pm_fee_v  = pm_fee(pm_ask, contracts)   if pm_ask  is not None else None
        pm_tot    = total_cost(pm_ask, pm_fee_v, contracts) if pm_ask is not None else None
        kal_fee_v = kal_fee(kal_ask, contracts) if kal_ask is not None else None
        kal_tot   = total_cost(kal_ask, kal_fee_v, contracts) if kal_ask is not None else None
        if pm_tot is not None and kal_tot is not None:
            combined = pm_tot + kal_tot
            is_arb   = combined < PAYOUT
            ret      = irr(combined, days)
        else:
            combined = is_arb = None
            ret = None
            is_arb = False
        rows.append({"name": name, "pm_ask": pm_ask, "pm_fee": pm_fee_v,
                     "pm_total": pm_tot, "kal_ask": kal_ask, "kal_fee": kal_fee_v,
                     "kal_total": kal_tot, "combined": combined,
                     "arb": is_arb, "return": ret})
    rows.sort(key=lambda r: r["return"] if r["return"] is not None else -9999, reverse=True)
    return rows

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Starting scan...")
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "contracts": CONTRACTS,
        "sports": []
    }
    for sport in SPORTS:
        print(f"  Fetching {sport['label']}...")
        pm  = fetch_pm_prices(sport)
        kal = fetch_kalshi_prices(sport)
        sport_data = {"label": sport["label"], "tables": {}}
        for direction in ("A", "B"):
            rows = build_rows(sport, pm, kal, CONTRACTS, direction)
            sport_data["tables"][direction] = rows
        output["sports"].append(sport_data)

    out_path = Path(__file__).parent / "data.json"
    with open(out_path, "w") as f:
        json.dump(output, f)
    print(f"Wrote {out_path}  ({len(output['sports'])} sports)")

if __name__ == "__main__":
    main()
