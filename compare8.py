"""
compare.py — Polymarket US vs. Kalshi Arbitrage Scanner
--------------------------------------------------------
Fetches live prices for four championship markets and checks for arbitrage.
Each sport prints TWO tables:

  TABLE A: PM YES + Kalshi NO  — buy team wins on Polymarket, team loses on Kalshi
    Arb when: PM_yes_total + KAL_no_total < $100

  TABLE B: PM NO + Kalshi YES  — buy team loses on Polymarket, team wins on Kalshi
    Arb when: PM_no_total + KAL_yes_total < $100

  PM No Ask  = 1 − bestBidQuote.value  (best bid for Yes = best ask for No)
  PM Yes Ask = bestAskQuote.value

Sports covered:
  1.  MLB World Series Champion
  2.  NHL Stanley Cup Champion
  3.  FIFA Men's World Cup Winner
  4.  MLB American League Champion
  5.  MLB National League Champion
  6.  MLB AL MVP
  7.  MLB NL MVP
  8.  MLB AL Rookie of the Year
  9.  MLB NL Rookie of the Year
  10. MLB AL Cy Young
  11. MLB NL Cy Young
  12. MLS Cup Champion

All prices fetched directly from public REST APIs — no SDK needed.
  Polymarket: https://gateway.polymarket.us/v1/events/slug/<event-slug>
  Kalshi:     https://api.elections.kalshi.com/trade-api/v2/events/<event-ticker>

Fee formulas:
  Polymarket (taker): Fee = 0.05 × C × p × (1 − p)
  Kalshi (taker):     Fee = ceil(0.07 × C × p × (1 − p))  [rounded up to cent]

SETUP (one time):
    pip install requests python-dotenv

    Optional — create "polymarket.env" (or ".env") in the same folder:
        POLYMARKET_KEY_ID=your-key-id-here
        POLYMARKET_SECRET_KEY=your-secret-key-here
    (Credentials not required for read-only price fetching.)

USAGE:
    python compare.py                   # all markets, sort by return desc
    python compare.py --sort alpha      # sort alphabetically by name
    python compare.py --sort pm         # sort by PM ask price desc
    python compare.py --contracts 50    # change share quantity (default 100)
    python compare.py --arb-only        # only show rows where arb exists
"""

import argparse
import math
import os
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path

# ── Load credentials (optional for read-only) ─────────────────────────────────
try:
    from dotenv import load_dotenv
    for directory in [Path(__file__).parent, Path.cwd()]:
        for filename in ["polymarket.env", ".env"]:
            candidate = directory / filename
            if candidate.exists():
                load_dotenv(dotenv_path=candidate)
                print(f"✓ Credentials loaded from: {candidate}")
                break
except ImportError:
    pass

# ── API base URLs ─────────────────────────────────────────────────────────────
PM_BASE      = "https://gateway.polymarket.us/v1"
KALSHI_BASE  = "https://api.elections.kalshi.com/trade-api/v2"
KAL_HEADERS  = {"Accept": "application/json"}

# ── Fee constants ─────────────────────────────────────────────────────────────
PM_THETA     = 0.05
KAL_THETA    = 0.07
CONTRACTS    = 100
PAYOUT       = 100.0

# ── Settlement dates (used for IRR annualization) ──────────────────────────────
# IRR = (PAYOUT / combined_cost) ^ (365 / days_to_settlement) - 1
from datetime import date as _date
SETTLEMENT_DATES = {
    "nhl":   _date(2026,  6, 30),   # NHL Stanley Cup
    "mlb":   _date(2026, 11, 30),   # All MLB markets (WS, pennants, awards)
    "wc":    _date(2026,  7, 30),   # FIFA World Cup
    "mls":   _date(2026, 12, 30),   # MLS Cup
}

def _settlement_days(sport_key: str) -> int:
    """Return days from today to this sport's settlement date (min 1)."""
    delta = (SETTLEMENT_DATES[sport_key] - _date.today()).days
    return max(delta, 1)

def _irr(combined: float, days: int) -> float:
    """Annualized IRR: (PAYOUT / combined)^(365/days) - 1."""
    return (PAYOUT / combined) ** (365.0 / days) - 1.0

# ─────────────────────────────────────────────────────────────────────────────
# SPORT CONFIGURATIONS
#
# Each sport has:
#   pm_event_slug   : Polymarket event slug for /v1/events/slug/<slug>
#   pm_slug_prefix  : Prefix of individual market slugs (e.g. "tec-mlb-champ-2026-09-27-")
#   kal_event       : Kalshi event ticker (e.g. "KXMLB-26")
#   team_map        : list of (pm_slug_suffix, kalshi_ticker_suffix, display_name)
#                     pm_slug_suffix  = e.g. "lad"  → full slug = prefix + suffix
#                     kalshi_suffix   = e.g. "LAD"  → full ticker = KXMLB-26-LAD
#                     display_name    = what to show in the table
# ─────────────────────────────────────────────────────────────────────────────
SPORTS = [

    # ── 1. MLB World Series ───────────────────────────────────────────────────
    {
        "label":          "MLB World Series Champion",
        "settlement_key":  "mlb",
        "pm_event_slug":  "world-series-2025",
        "pm_slug_prefix": "tec-mlb-champ-2026-09-27-",
        "kal_event":      "KXMLB-26",
        # (pm_suffix, kalshi_suffix, display_name)
        "team_map": [
            ("lad", "LAD", "Los Angeles Dodgers"),
            ("nyy", "NYY", "New York Yankees"),
            ("atl", "ATL", "Atlanta Braves"),
            ("sea", "SEA", "Seattle Mariners"),
            ("chc", "CHC", "Chicago Cubs"),
            ("tb",  "TB",  "Tampa Bay Rays"),
            ("tex", "TEX", "Texas Rangers"),
            ("phi", "PHI", "Philadelphia Phillies"),
            ("tor", "TOR", "Toronto Blue Jays"),
            ("mil", "MIL", "Milwaukee Brewers"),
            ("det", "DET", "Detroit Tigers"),
            ("ath", "ATH", "Athletics"),
            ("sd",  "SD",  "San Diego Padres"),
            ("kc",  "KC",  "Kansas City Royals"),
            ("bos", "BOS", "Boston Red Sox"),
            ("bal", "BAL", "Baltimore Orioles"),
            ("cle", "CLE", "Cleveland Guardians"),
            ("pit", "PIT", "Pittsburgh Pirates"),
            ("nym", "NYM", "New York Mets"),
            ("sf",  "SF",  "San Francisco Giants"),
            ("hou", "HOU", "Houston Astros"),
            ("az",  "AZ",  "Arizona Diamondbacks"),
            ("min", "MIN", "Minnesota Twins"),
            ("cin", "CIN", "Cincinnati Reds"),
            ("cws", "CWS", "Chicago White Sox"),
            ("stl", "STL", "St. Louis Cardinals"),
            ("wsh", "WSH", "Washington Nationals"),
            ("laa", "LAA", "Los Angeles Angels"),
            ("col", "COL", "Colorado Rockies"),
            ("mia", "MIA", "Miami Marlins"),
        ],
    },

    # ── 2. NHL Stanley Cup ────────────────────────────────────────────────────
    # Only active playoff teams are listed (others have no liquid market).
    # Kalshi has: BUF, CAR, COL, MTL, VGK
    # PM has:     buf, car, col, mon, veg  (+ all other teams at minimal prices)
    {
        "label":          "NHL Stanley Cup Champion",
        "settlement_key":  "nhl",
        "pm_event_slug":  "tec-NHL-scw-2026-06-30",
        "pm_slug_prefix": "tec-nhl-scw-2026-06-30-",
        "kal_event":      "KXNHL-26",
        "team_map": [
            ("col", "COL", "Colorado Avalanche"),
            ("car", "CAR", "Carolina Hurricanes"),
            ("veg", "VGK", "Vegas Golden Knights"),
            ("mon", "MTL", "Montréal Canadiens"),
            ("buf", "BUF", "Buffalo Sabres"),
        ],
    },

    # ── 3. FIFA Men's World Cup ───────────────────────────────────────────────
    # PM uses 3-letter FIFA-style codes; Kalshi uses 2-letter ISO (mostly).
    # PM event fetched via /v1/events/slug/fifa-wc-2026-07-19-winner
    # Individual market slugs: tec-fifa-wc-2026-07-19-winner-{pm_suffix}
    {
        "label":          "FIFA Men's World Cup Winner",
        "settlement_key":  "wc",
        "pm_event_slug":  "fifa-wc-2026-07-19-winner",
        "pm_slug_prefix": "tec-fifa-wc-2026-07-19-winner-",
        "kal_event":      "KXMENWORLDCUP-26",
        "team_map": [
            ("esp", "ES",  "Spain"),
            ("fra", "FR",  "France"),
            ("eng", "GB",  "England"),
            ("arg", "AR",  "Argentina"),
            ("por", "PT",  "Portugal"),
            ("bra", "BR",  "Brazil"),
            ("ger", "DE",  "Germany"),
            ("ned", "NL",  "Netherlands"),
            ("usa", "US",  "United States"),
            ("jpn", "JP",  "Japan"),
            ("bel", "BE",  "Belgium"),
            ("nor", "NO",  "Norway"),
            ("col", "CO",  "Colombia"),
            ("mar", "MA",  "Morocco"),
            ("cro", "HR",  "Croatia"),
            ("uru", "UY",  "Uruguay"),
            ("mex", "MX",  "Mexico"),
            ("tur", "TR",  "Türkiye"),
            ("sui", "CH",  "Switzerland"),
            ("irq", "IRQ", "Iraq"),
            ("bih", "BIH", "Bosnia-Herzegovina"),
            ("can", "CA",  "Canada"),
            ("civ", "CIV", "Côte d'Ivoire"),
            ("cze", "CZE", "Czechia"),
            ("ecu", "EC",  "Ecuador"),
            ("cod", "COD", "Congo DR"),
            ("egy", "EGY", "Egypt"),
            ("aut", "AT",  "Austria"),
            ("swe", "SE",  "Sweden"),
            ("tun", "TN",  "Tunisia"),
            ("aus", "AU",  "Australia"),
            ("irn", "IR",  "IR Iran"),
            ("alg", "DZA", "Algeria"),
            ("gha", "GH",  "Ghana"),
            ("cpv", "CPV", "Cabo Verde"),
            ("cuw", "CUW", "Curacao"),
            ("hai", "HTI", "Haiti"),
            ("jor", "JOR", "Jordan"),
            ("kor", "KR",  "Korea Republic"),
            ("ksa", "SA",  "Saudi Arabia"),
            ("nzl", "NZL", "New Zealand"),
            ("pan", "PAN", "Panama"),
            ("par", "PY",  "Paraguay"),
            ("qat", "QAT", "Qatar"),
            ("rsa", "RSA", "South Africa"),
            ("sco", "SC",  "Scotland"),
            ("sen", "SN",  "Senegal"),
            ("uzb", "UZB", "Uzbekistan"),
        ],
    },

    # ── 4. MLB AL Champion ────────────────────────────────────────────────────
    {
        "label":          "MLB American League Champion",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-alchamp-2026-09-27",
        "pm_slug_prefix": "tec-mlb-alchamp-2026-09-27-",
        "kal_event":      "KXMLBAL-26",
        # (pm_suffix, kalshi_suffix, display_name)
        "team_map": [
            ("nyy", "NYY", "New York Yankees"),
            ("sea", "SEA", "Seattle Mariners"),
            ("tb",  "TB",  "Tampa Bay Rays"),
            ("tex", "TEX", "Texas Rangers"),
            ("det", "DET", "Detroit Tigers"),
            ("tor", "TOR", "Toronto Blue Jays"),
            ("cle", "CLE", "Cleveland Guardians"),
            ("bal", "BAL", "Baltimore Orioles"),
            ("ath", "ATH", "Athletics"),
            ("kc",  "KC",  "Kansas City Royals"),
            ("bos", "BOS", "Boston Red Sox"),
            ("hou", "HOU", "Houston Astros"),
            ("min", "MIN", "Minnesota Twins"),
            ("cws", "CWS", "Chicago White Sox"),
            ("laa", "LAA", "Los Angeles Angels"),
        ],
    },

    # ── 5. MLB NL Champion ────────────────────────────────────────────────────
    {
        "label":          "MLB National League Champion",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-nlchamp-2026-09-27",
        "pm_slug_prefix": "tec-mlb-nlchamp-2026-09-27-",
        "kal_event":      "KXMLBNL-26",
        # (pm_suffix, kalshi_suffix, display_name)
        "team_map": [
            ("lad", "LAD", "Los Angeles Dodgers"),
            ("atl", "ATL", "Atlanta Braves"),
            ("chc", "CHC", "Chicago Cubs"),
            ("phi", "PHI", "Philadelphia Phillies"),
            ("mil", "MIL", "Milwaukee Brewers"),
            ("nym", "NYM", "New York Mets"),
            ("sd",  "SD",  "San Diego Padres"),
            ("pit", "PIT", "Pittsburgh Pirates"),
            ("az",  "AZ",  "Arizona Diamondbacks"),
            ("cin", "CIN", "Cincinnati Reds"),
            ("stl", "STL", "St. Louis Cardinals"),
            ("sf",  "SF",  "San Francisco Giants"),
            ("col", "COL", "Colorado Rockies"),
            ("mia", "MIA", "Miami Marlins"),
            ("wsh", "WSH", "Washington Nationals"),
        ],
    },

    # ── 6. MLB AL MVP ─────────────────────────────────────────────────────────
    # Only players listed on BOTH Polymarket and Kalshi are included.
    {
        "label":          "MLB AL MVP",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-al-2026-11-27-mvp",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-mvp-",
        "kal_event":      "KXMLBALMVP-26",
        # (pm_suffix, kalshi_suffix, display_name)
        "team_map": [
            ("aarjud", "AJUD", "Aaron Judge"),
            ("yoralv", "YALV", "Yordan Álvarez"),
            ("bobwit", "RWIT", "Bobby Witt Jr."),
            ("benric", "BRIC", "Ben Rice"),
            ("nickur", "NKUR", "Nick Kurtz"),
            ("miktro", "MTRO", "Mike Trout"),
            ("juncam", "JCAM", "Junior Caminero"),
            ("julrod", "JROD", "Julio Rodríguez"),
            ("josram", "JRAM", "Jose Ramírez"),
            ("petalo", "PALO", "Pete Alonso"),
            ("jerpen", "JPEN", "Jeremy Peña"),
            ("vlague", "VGUE", "Vladimir Guerrero Jr."),
            ("calral", "CRAL", "Cal Raleigh"),
            ("ranaro", "RARO", "Randy Arozarena"),
            ("byrbux", "BBUX", "Byron Buxton"),
            ("codbel", "CBEL", "Cody Bellinger"),
            ("colmon", "CMON", "Colson Montgomery"),
            ("gunhen", "GHEN", "Gunnar Henderson"),
            ("jacwil", "JWIL", "Jacob Wilson"),
            ("jazchi", "JCHI", "Jazz Chisholm Jr."),
            ("stekwa", "SKWA", "Steven Kwan"),
            ("zacnet", "ZNET", "Zach Neto"),
            ("adlrut", "ARUT", "Adley Rutschman"),
            ("corsea", "CSEA", "Corey Seager"),
            ("geospr", "GSPR", "George Springer"),
            ("josalt", "JALT", "Jose Altuve"),
            ("wyalan", "WLAN", "Wyatt Langford"),
            ("yandia", "YDIA", "Yandy Diaz"),
            ("maigar", "MGAR", "Maikel García"),
            ("romant", "RANT", "Roman Anthony"),
        ],
    },

    # ── 7. MLB NL MVP ─────────────────────────────────────────────────────────
    # Only players listed on BOTH Polymarket and Kalshi are included.
    {
        "label":          "MLB NL MVP",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-nl-2026-11-27-mvp",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-mvp-",
        "kal_event":      "KXMLBNLMVP-26",
        # (pm_suffix, kalshi_suffix, display_name)
        "team_map": [
            ("shooht", "SOHT", "Shohei Ohtani"),
            ("matcha", "MCHA", "Matt Chapman"),
            ("moobet", "MBET", "Mookie Betts"),
            ("matols", "MOLS", "Matt Olson"),
            ("bryhar", "BHAR", "Bryce Harper"),
            ("nichoe", "NHOE", "Nico Hoerner"),
            ("ellcru", "ECRU", "Elly De La Cruz"),
            ("kylsch", "KSCH", "Kyle Schwarber"),
            ("jamwoo", "JWOO", "James Wood"),
            ("juasot", "JSOT", "Juan Soto"),
            ("jorwal", "JWAL", "Jordan Walker"),
            ("kyltuc", "KTUC", "Kyle Tucker"),
            ("pauske", "PSKE", "Paul Skenes"),
            ("drabal", "DBAL", "Drake Baldwin"),
            ("britur", "BTUR", "Brice Turang"),
            ("corcar", "CCAR", "Corbin Carroll"),
            ("fertat", "FTAT", "Fernando Tatis Jr."),
            ("fralin", "FLIN", "Francisco Lindor"),
            ("frefre", "FFRE", "Freddie Freeman"),
            ("jaccho", "JCHO", "Jackson Chourio"),
            ("jacmer", "JMER", "Jackson Merrill"),
            ("ketmar", "KMAR", "Ketel Marte"),
            ("ronacu", "RACU", "Ronald Acuna Jr."),
            ("wilada", "WADA", "Willy Adames"),
            ("alebre", "ABRE", "Alex Bregman"),
            ("manmac", "MMAC", "Manny Machado"),
            ("micbus", "MBUS", "Michael Busch"),
            ("michar", "MHAR", "Michael Harris II"),
            ("onecru", "OCRU", "Oneil Cruz"),
            ("petarm", "PCRO", "Pete Crow-Armstrong"),
            ("rafdev", "RDEV", "Rafael Devers"),
            ("tretur", "TTUR", "Trea Turner"),
            ("wilsmi", "WSMI", "Will Smith"),
            ("yosyam", "YYAM", "Yoshinobu Yamamoto"),
        ],
    },


    # ── 9. MLB AL Rookie of the Year ──────────────────────────────────────────
    {
        "label":          "MLB AL Rookie of the Year",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-al-2026-11-27-roy",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-roy-",
        "kal_event":      "KXMLBALROTY-26",
        "team_map": [
            ("kevmcg", "KMCG", "Kevin McGonigle"),
            ("munmur", "MMUR", "Munetaka Murakami"),
            ("chadel", "CDEL", "Chase DeLauter"),
            ("kazoka", "KOKA", "Kazuma Okamoto"),
            ("treyes", "TYES", "Trey Yesavage"),
            ("paytol", "PTOL", "Payton Tolle"),
            ("sambas", "SBAS", "Samuel Basallo"),
            ("trabaz", "TBAZ", "Travis Bazzana"),
            ("carwil", "CWIL", "Carson Williams"),
            ("brimat", "BMAT", "Brice Matthews"),
            ("noasch", "NSCH", "Noah Schultz"),
            ("carjen", "CJEN", "Carter Jensen"),
            ("conear", "CEAR", "Connelly Early"),
            ("coleme", "CEME", "Colt Emerson"),
            ("tatima", "TIMA", "Tatsuya Imai"),
        ],
    },

    # ── 10. MLB NL Rookie of the Year ─────────────────────────────────────────
    {
        "label":          "MLB NL Rookie of the Year",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-nl-2026-11-27-roy",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-roy-",
        "kal_event":      "KXMLBNLROTY-26",
        "team_map": [
            ("kongri", "KGRI", "Konnor Griffin"),
            ("nolmcl", "NMCL", "Nolan McLean"),
            ("jjwet",  "JWET", "JJ Wetherholt"),
            ("salste", "SSTE", "Sal Stewart"),
            ("moibal", "MBAL", "Moises Ballesteros"),
            ("bryeld", "BELD", "Bryce Eldridge"),
            ("carben", "CBEN", "Carson Benge"),
            ("owecai", "OCAI", "Owen Caissie"),
            ("ryawal", "RWAL", "Ryan Waldschmidt"),
            ("robsne", "RSNE", "Robby Snelling"),
            ("jrrit",  "JRIT", "JR Ritchie"),
            ("rhelow", "RLOW", "Rhett Lowder"),
            ("bubcha", "BCHA", "Bubba Chandler"),
            ("chapet", "CPET", "Chase Petty"),
            ("juscra", "JCRA", "Justin Crawford"),
            ("andpai", "APAI", "Andrew Painter"),
            ("hunbar", "HBAR", "Hunter Barco"),
            ("jonton", "JTON", "Jonah Tong"),
            ("joemac", "JMAC", "Joe Mack"),
            ("alefre", "AFRE", "Alex Freeland"),
        ],
    },

    # ── 11. MLB AL Cy Young ───────────────────────────────────────────────────
    {
        "label":          "MLB AL Cy Young",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-al-2026-11-27-cy",
        "pm_slug_prefix": "tec-mlb-al-2026-11-27-cy-",
        "kal_event":      "KXMLBALCY-26",
        "team_map": [
            ("camsch", "CSCH",  "Cam Schlittler"),
            ("geokir", "GKIR",  "George Kirby"),
            ("dylcea", "DCEA",  "Dylan Cease"),
            ("jacdeg", "JDEG",  "Jacob deGrom"),
            ("jossor", "JSOR",  "Jose Soriano"),
            ("maxfri", "MFRI",  "Max Fried"),
            ("loggil", "LGILB", "Logan Gilbert"),
            ("brywoo", "BWOO",  "Bryan Woo"),
            ("dreras", "DRAS",  "Drew Rasmussen"),
            ("ransua", "RSUA",  "Ranger Suarez"),
            ("gavwil", "GWIL",  "Gavin Williams"),
            ("colrag", "CRAG",  "Cole Ragans"),
            ("gercol", "GCOL",  "Gerrit Cole"),
            ("hunbro", "HBRO",  "Hunter Brown"),
            ("joerya", "JRYA",  "Joe Ryan"),
            ("kevgau", "KGAU",  "Kevin Gausman"),
            ("shamcc", "SMCC",  "Shane McClanahan"),
            ("carrod", "CROD",  "Carlos Rodon"),
            ("kylbra", "KBRA",  "Kyle Bradish"),
            ("macgor", "MGOR",  "MacKenzie Gore"),
            ("nateov", "NEOV",  "Nathan Eovaldi"),
            ("parmes", "PMES",  "Parker Messick"),
            ("tanbib", "TBIB",  "Tanner Bibee"),
            ("trerog", "TROG",  "Trevor Rogers"),
            ("treyes", "TYES",  "Trey Yesavage"),
            ("jacfla", "JFLA",  "Jack Flaherty"),
            ("micwac", "MWAC",  "Michael Wacha"),
            ("songra", "SGRA",  "Sonny Gray"),
            ("kribub", "KBUB",  "Kris Bubic"),
        ],
    },

    # ── 12. MLB NL Cy Young ───────────────────────────────────────────────────
    {
        "label":          "MLB NL Cy Young",
        "settlement_key":  "mlb",
        "pm_event_slug":  "mlb-nl-2026-11-27-cy",
        "pm_slug_prefix": "tec-mlb-nl-2026-11-27-cy-",
        "kal_event":      "KXMLBNLCY-26",
        "team_map": [
            ("pauske", "PSKE",  "Paul Skenes"),
            ("crisan", "CSAN",  "Cristopher Sanchez"),
            ("shooht", "SOHT",  "Shohei Ohtani"),
            ("jacmis", "JMIS",  "Jacob Misiorowski"),
            ("chrsal", "CSAL",  "Chris Sale"),
            ("yosyam", "YYAM",  "Yoshinobu Yamamoto"),
            ("chabur", "CBUR",  "Chase Burns"),
            ("masmil", "MMIL",  "Mason Miller"),
            ("nolmcl", "NMCL",  "Nolan McLean"),
            ("shoima", "SIMA",  "Shota Imanaga"),
            ("joemus", "JMUS",  "Joe Musgrove"),
            ("zacwhe", "ZWHE",  "Zack Wheeler"),
            ("brawoo", "BWOO",  "Brandon Woodruff"),
            ("freper", "FPER",  "Freddy Peralta"),
            ("logweb", "LWEB",  "Logan Webb"),
            ("niclod", "NLOD",  "Nick Lodolo"),
            ("andabb", "AABB",  "Andrew Abbott"),
            ("brasin", "BSIN",  "Brady Singer"),
            ("edwcab", "ECAB",  "Edward Cabrera"),
            ("eurper", "EPER",  "Eury Perez"),
            ("nicpiv", "NPIV",  "Nick Pivetta"),
            ("quipri", "QPRI",  "Quinn Priester"),
            ("robray", "RRAY",  "Robbie Ray"),
            ("spestr", "SSTR",  "Spencer Strider"),
            ("tylgla", "TGAS",  "Tyler Glasnow"),
            ("jarjon", "JJON",  "Jared Jones"),
            ("kodsen", "KSEN",  "Kodai Senga"),
            ("mitkel", "MIKEL", "Mitch Keller"),
            ("sanalc", "SALC",  "Sandy Alcantara"),
            ("blasne", "BSNE",  "Blake Snell"),
            ("davpet", "DPET",  "David Peterson"),
            ("jesluz", "JLUZ",  "Jesus Luzardo"),
        ],
    },

    # ── 13. MLS Cup ───────────────────────────────────────────────────────────
    # PM event slug: mls-winner-2026-11-07
    # PM market slugs: tec-mls-winner-2026-11-07-{pm_suffix}
    # Kalshi event: KXMLSCUP-26, tickers: KXMLSCUP-26-{kal_suffix}
    {
        "label":          "MLS Cup Champion",
        "settlement_key":  "mls",
        "pm_event_slug":  "mls-winner-2026-11-07",
        "pm_slug_prefix": "tec-mls-winner-2026-11-07-",
        "kal_event":      "KXMLSCUP-26",
        "team_map": [
            ("mia",  "MIA",  "Inter Miami CF"),
            ("vwh",  "VAN",  "Vancouver Whitecaps FC"),
            ("laf",  "LAFC", "Los Angeles FC"),
            ("nas",  "NSH",  "Nashville SC"),
            ("sje",  "SJ",   "San Jose Earthquakes"),
            ("fcc",  "CIN",  "FC Cincinnati"),
            ("lag",  "LAG",  "Los Angeles Galaxy"),
            ("sea",  "SEA",  "Seattle Sounders FC"),
            ("nyc",  "NYC",  "New York City FC"),
            ("min",  "MIN",  "Minnesota United FC"),
            ("orl",  "ORL",  "Orlando City SC"),
            ("sdg",  "SD",   "San Diego FC"),
            ("clb",  "CLB",  "Columbus Crew"),
            ("chi",  "CHI",  "Chicago Fire FC"),
            ("tor",  "TOR",  "Toronto FC"),
            ("col",  "COL",  "Colorado Rapids SC"),
            ("hou",  "HOU",  "Houston Dynamo"),
            ("clt",  "CLT",  "Charlotte FC"),
            ("phi",  "PHI",  "Philadelphia Union"),
            ("rsl",  "RSL",  "Real Salt Lake"),
            ("ner",  "NE",   "New England Revolution"),
            ("atl",  "ATL",  "Atlanta United FC"),
            ("dal",  "DAL",  "FC Dallas"),
            ("nyr",  "NY",   "New York Red Bulls"),
            ("por",  "POR",  "Portland Timbers"),
            ("stl",  "STL",  "St. Louis City SC"),
            ("mim",  "MTL",  "CF Montréal"),
            ("dcu",  "DC",   "D.C. United"),
            ("aus",  "ATX",  "Austin FC"),
            ("skc",  "SKC",  "Sporting Kansas City"),
        ],
    },
]

# ── Fee calculations ──────────────────────────────────────────────────────────

def pm_fee(price: float, contracts: int) -> float:
    return PM_THETA * contracts * price * (1 - price)


def kal_fee(price: float, contracts: int) -> float:
    """Kalshi fee rounded UP to nearest cent."""
    return math.ceil(KAL_THETA * contracts * price * (1 - price) * 100) / 100


def total_cost(price: float, fee: float, contracts: int) -> float:
    return price * contracts + fee


# ── Polymarket REST fetching ──────────────────────────────────────────────────

def pm_fetch_event(event_slug: str) -> dict | None:
    """Fetch a Polymarket event with nested markets via /v1/events/slug/<slug>."""
    url = f"{PM_BASE}/events/slug/{event_slug}"
    try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        data = r.json()
        return data.get("event") or data
    except Exception as e:
        print(f"  ⚠ PM event fetch failed ({event_slug}): {e}", file=sys.stderr)
        return None


def pm_fetch_market(market_slug: str) -> dict | None:
    """Fetch a single Polymarket market via /v1/market/slug/<slug>."""
    try:
        r = requests.get(f"{PM_BASE}/market/slug/{market_slug}", timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("market") or data
    except Exception:
        return None


def pm_extract_prices(mkt: dict) -> tuple[float | None, float | None]:
    """
    Extract Yes ask and No ask from a Polymarket market dict.

    Yes ask = bestAskQuote.value
              (lowest price to buy the Yes/win contract)
    No ask  = 1 − bestBidQuote.value
              (best bid for Yes = best offer for No; subtracting from 1
               gives the lowest price to buy the No/lose contract)

    Fallback for Yes ask: long=True marketSide price field.
    Fallback for No ask:  1 − long=True price (Yes bid approximation).

    Returns (yes_ask, no_ask) — either may be None.
    """
    yes_ask = no_ask = None

    baq = mkt.get("bestAskQuote")
    if baq and baq.get("value") is not None:
        yes_ask = float(baq["value"])

    bbq = mkt.get("bestBidQuote")
    if bbq and bbq.get("value") is not None:
        no_ask = round(1.0 - float(bbq["value"]), 6)

    # Fallbacks from marketSides
    if yes_ask is None or no_ask is None:
        for side in (mkt.get("marketSides") or []):
            if side.get("long") is True:
                raw = side.get("price")
                if raw is not None:
                    if yes_ask is None:
                        yes_ask = float(raw)
                    if no_ask is None:
                        no_ask = round(1.0 - float(raw), 6)
                break

    return yes_ask, no_ask


def fetch_pm_prices(sport: dict) -> dict[str, dict]:
    """
    Returns {pm_suffix: {"yes_ask": float|None, "no_ask": float|None}}
    for every team in the sport.

    Strategy:
      1. Fetch the event endpoint — one request gets all markets with
         bestAskQuote (Yes ask) and bestBidQuote (→ No ask = 1 − bid).
      2. Fall back to individual /v1/market/slug/<slug> for any missing.
    """
    prefix   = sport["pm_slug_prefix"]
    team_map = sport["team_map"]
    prices: dict[str, dict] = {}

    # Build a slug → suffix lookup (strip spaces from PDF-artifact slugs)
    suffix_by_slug = {prefix + pm_suf: pm_suf for pm_suf, _, _ in team_map}

    # Step 1: bulk event endpoint
    event = pm_fetch_event(sport["pm_event_slug"])
    if event:
        markets = event.get("markets") or event.get("outcomes") or []
        for mkt in markets:
            slug = (mkt.get("slug") or mkt.get("marketSlug") or "").strip()
            pm_suf = suffix_by_slug.get(slug)
            if pm_suf is not None:
                ya, na = pm_extract_prices(mkt)
                prices[pm_suf] = {"yes_ask": ya, "no_ask": na}

    # Step 2: per-market fallback for any missing or incomplete entries
    total = len(team_map)
    for i, (pm_suf, _, name) in enumerate(team_map, 1):
        print(f"  PM  [{i:>2}/{total}] {name:<35} ...", end="\r", flush=True)
        existing = prices.get(pm_suf, {})
        if existing.get("yes_ask") is None or existing.get("no_ask") is None:
            mkt = pm_fetch_market(prefix + pm_suf)
            if mkt:
                ya, na = pm_extract_prices(mkt)
                prices[pm_suf] = {
                    "yes_ask": existing.get("yes_ask") or ya,
                    "no_ask":  existing.get("no_ask")  or na,
                }
            else:
                prices.setdefault(pm_suf, {"yes_ask": None, "no_ask": None})

    print(" " * 70, end="\r")
    return prices


# ── Kalshi REST fetching ──────────────────────────────────────────────────────

def fetch_kalshi_prices(sport: dict) -> dict[str, float | None]:
    """
    Returns {kal_suffix: {"no_ask": float|None, "yes_ask": float|None}} for every team.
    Fetches all markets in one bulk event request, then falls back per-market.
    Skips finalized markets.
    """
    event_ticker = sport["kal_event"]
    team_map     = sport["team_map"]
    prices: dict[str, float | None] = {}

    # Bulk fetch
    bulk: dict[str, dict] = {}
    try:
        r = requests.get(
            f"{KALSHI_BASE}/events/{event_ticker}",
            params={"with_nested_markets": "true"},
            headers=KAL_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        for mkt in (r.json().get("event", {}).get("markets") or []):
            if mkt.get("status") == "finalized":
                continue
            ticker = mkt.get("ticker", "")
            suffix = ticker.rsplit("-", 1)[-1].upper() if "-" in ticker else ""
            if suffix:
                bulk[suffix] = mkt
    except Exception as e:
        print(f"  ⚠ Kalshi bulk fetch failed ({event_ticker}): {e}", file=sys.stderr)

    total = len(team_map)
    for i, (_, kal_suf, name) in enumerate(team_map, 1):
        print(f"  KAL [{i:>2}/{total}] {name:<35} ...", end="\r", flush=True)
        mkt = bulk.get(kal_suf.upper())
        if mkt is None:
            # Per-market fallback
            try:
                r = requests.get(
                    f"{KALSHI_BASE}/markets/{event_ticker}-{kal_suf}",
                    headers=KAL_HEADERS,
                    timeout=10,
                )
                r.raise_for_status()
                mkt = r.json().get("market", r.json())
                if mkt.get("status") == "finalized":
                    prices[kal_suf] = None
                    continue
            except Exception:
                prices[kal_suf] = None
                continue

        def _f(key):
            v = mkt.get(key)
            return float(v) if v is not None else None

        prices[kal_suf] = {
            "no_ask":  _f("no_ask_dollars")  or _f("no_ask")  or _f("no_ask_price"),
            "yes_ask": _f("yes_ask_dollars") or _f("yes_ask") or _f("yes_ask_price"),
        }

    print(" " * 70, end="\r")
    return prices


# ── Row builder ───────────────────────────────────────────────────────────────

def build_rows(sport: dict, pm_prices: dict, kal_prices: dict,
               contracts: int, direction: str = "A") -> list[dict]:
    """
    Build one row per team for the given direction:
      "A": PM YES + Kalshi NO   → buy team wins on PM, team loses on Kalshi
      "B": PM NO  + Kalshi YES  → buy team loses on PM, team wins on Kalshi
    Both legs together always pay $100 (exactly one wins).
    """
    rows = []
    for pm_suf, kal_suf, name in sport["team_map"]:
        pm_data  = pm_prices.get(pm_suf) or {}
        kal_data = kal_prices.get(kal_suf) or {}

        if direction == "A":
            pm_ask  = pm_data.get("yes_ask")   # buy Yes on PM
            kal_ask = kal_data.get("no_ask")    # buy No  on Kalshi
        else:
            pm_ask  = pm_data.get("no_ask")     # buy No  on PM
            kal_ask = kal_data.get("yes_ask")   # buy Yes on Kalshi

        pm_fee_v  = pm_fee(pm_ask, contracts)                if pm_ask  is not None else None
        pm_total  = total_cost(pm_ask, pm_fee_v, contracts)  if pm_ask  is not None else None
        kal_fee_v = kal_fee(kal_ask, contracts)               if kal_ask is not None else None
        kal_total = total_cost(kal_ask, kal_fee_v, contracts) if kal_ask is not None else None

        if pm_total is not None and kal_total is not None:
            combined = pm_total + kal_total
            is_arb   = combined < PAYOUT
            days     = _settlement_days(sport["settlement_key"])
            ret      = _irr(combined, days)
        else:
            combined = None
            is_arb   = False
            ret      = None

        rows.append({
            "name":      name,
            "pm_ask":    pm_ask,
            "pm_fee":    pm_fee_v,
            "pm_total":  pm_total,
            "kal_ask":   kal_ask,
            "kal_fee":   kal_fee_v,
            "kal_total": kal_total,
            "combined":  combined,
            "arb":       is_arb,
            "return":    ret,
        })
    return rows


# ── Display ───────────────────────────────────────────────────────────────────

def fmt(val: float | None, decimals: int = 4) -> str:
    return "    —    " if val is None else f"${val:.{decimals}f}"


def fmt_pct(val: float | None) -> str:
    if val is None:
        return "    —    "
    pct = val * 100
    return f"+{pct:.2f}%" if pct >= 0 else f"({abs(pct):.2f}%)"


def print_table(sport: dict, rows: list[dict], contracts: int,
                arb_only: bool, direction: str = "A") -> None:
    if arb_only:
        rows = [r for r in rows if r["arb"]]

    arb_count = sum(1 for r in rows if r["arb"])
    now       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if direction == "A":
        dir_label  = "TABLE A — PM YES + Kalshi NO   [buy team WINS on Polymarket / team LOSES on Kalshi]"
        pm_col     = "PM Yes Ask"
        kal_col    = "KAL No Ask"
        pm_note    = f"PM Yes Ask × {contracts} + PM Fee  (Θ={PM_THETA})"
        kal_note   = f"KAL No Ask × {contracts} + KAL Fee (Θ={KAL_THETA}, ceil to ¢)"
    else:
        dir_label  = "TABLE B — PM NO  + Kalshi YES  [buy team LOSES on Polymarket / team WINS on Kalshi]"
        pm_col     = "PM No Ask"
        kal_col    = "KAL Yes Ask"
        pm_note    = f"PM No Ask  × {contracts} + PM Fee  (Θ={PM_THETA})  [No Ask = 1 − Yes Bid]"
        kal_note   = f"KAL Yes Ask × {contracts} + KAL Fee (Θ={KAL_THETA}, ceil to ¢)"

    print(f"\n{'═'*100}")
    print(f"  {sport['label']}")
    print(f"  {dir_label}")
    print(f"  {now}  |  Contracts: {contracts}")
    print(f"  Arb when PM Total + KAL Total < ${PAYOUT:.2f}  |  "
          f"Ann. IRR = (${PAYOUT:.2f} / Combined)^(365/days_to_settlement) − 1")
    if arb_count:
        print(f"  ⚡ {arb_count} arbitrage opportunity(ies) found!")
    print(f"{'═'*100}")

    if not rows:
        print("  No rows to display.\n")
        return

    name_w  = max(max(len(r["name"]) for r in rows), 22)
    pm_w    = max(len(pm_col), 10)
    kal_w   = max(len(kal_col), 10)
    H = [
        ("Team",    name_w, "<"),
        (pm_col,     pm_w,  ">"),
        ("PM Fee",      7,  ">"),
        ("PM Total",    9,  ">"),
        (kal_col,   kal_w,  ">"),
        ("KAL Fee",     7,  ">"),
        ("KAL Total",   9,  ">"),
        ("Combined",    9,  ">"),
        ("Arb?",        5,  "^"),
        ("Ann. IRR",   10,  ">"),
    ]

    header = "  " + "  ".join(f"{h:{d}{w}}" for h, w, d in H)
    sep    = "  " + "─" * (sum(w for _, w, _ in H) + 2 * (len(H) - 1))
    print(header)
    print(sep)

    for r in rows:
        flag = "✓" if r["arb"] else ""
        print("  " + "  ".join([
            f"{r['name']:<{name_w}}",
            f"{fmt(r['pm_ask']):>{pm_w}}",
            f"{fmt(r['pm_fee']):>7}",
            f"{fmt(r['pm_total']):>9}",
            f"{fmt(r['kal_ask']):>{kal_w}}",
            f"{fmt(r['kal_fee']):>7}",
            f"{fmt(r['kal_total']):>9}",
            f"{fmt(r['combined']):>9}",
            f"{flag:^5}",
            f"{fmt_pct(r['return']):>10}",
        ]))

    print(sep)
    print(f"\n  PM Total   = {pm_note}")
    print(f"  KAL Total  = {kal_note}")
    print(f"  Arb ✓      = Combined < ${PAYOUT:.2f}")
    print(f"  Return     = (${PAYOUT:.2f} − Combined) / Combined")



# ── Summary tables ────────────────────────────────────────────────────────────

def print_summary(arb_a: list[dict], arb_b: list[dict], contracts: int) -> None:
    """
    Print two compact summary tables of all flagged arb opportunities.
      arb_a : rows from direction "A" (PM YES + Kalshi NO)
      arb_b : rows from direction "B" (PM NO  + Kalshi YES)
    Each entry is a dict with keys: market, name, pm_ask, pm_total,
                                    kal_ask, kal_total, combined, return.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for direction, rows, dir_label in [
        ("A", arb_a, "SUMMARY A — PM YES + Kalshi NO   [buy WINS on Polymarket / LOSES on Kalshi]"),
        ("B", arb_b, "SUMMARY B — PM NO  + Kalshi YES  [buy LOSES on Polymarket / WINS on Kalshi]"),
    ]:
        print(f"\n{'═'*110}")
        print(f"  {dir_label}")
        print(f"  {now}  |  Contracts: {contracts}")
        print(f"{'═'*110}")

        if not rows:
            print("  No arbitrage opportunities found.")
            continue

        # sort by IRR descending
        rows = sorted(rows, key=lambda r: r["return"] if r["return"] is not None else -9999,
                      reverse=True)

        mkt_w  = max(max(len(r["market"]) for r in rows), 30)
        name_w = max(max(len(r["name"])   for r in rows), 22)
        if direction == "A":
            pm_col, kal_col = "PM Yes Ask", "KAL No Ask"
        else:
            pm_col, kal_col = "PM No Ask ", "KAL Yes Ask"

        H = [
            ("Market",    mkt_w,  "<"),
            ("Name",      name_w, "<"),
            (pm_col,         10,  ">"),
            ("PM Total",      9,  ">"),
            (kal_col,        11,  ">"),
            ("KAL Total",     9,  ">"),
            ("Combined",      9,  ">"),
            ("Ann. IRR",     10,  ">"),
        ]
        header = "  " + "  ".join(f"{h:{d}{w}}" for h, w, d in H)
        sep    = "  " + "─" * (sum(w for _, w, _ in H) + 2 * (len(H) - 1))
        print(header)
        print(sep)
        for r in rows:
            print("  " + "  ".join([
                f"{r['market']:<{mkt_w}}",
                f"{r['name']:<{name_w}}",
                f"{fmt(r['pm_ask']):>10}",
                f"{fmt(r['pm_total']):>9}",
                f"{fmt(r['kal_ask']):>11}",
                f"{fmt(r['kal_total']):>9}",
                f"{fmt(r['combined']):>9}",
                f"{fmt_pct(r['return']):>10}",
            ]))
        print(sep)
        print(f"  ⚡ {len(rows)} arbitrage opportunit{'y' if len(rows)==1 else 'ies'} found.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polymarket vs. Kalshi arb scanner — MLB, NHL, FIFA, MLS, MVP awards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sort", choices=["arb", "pm", "alpha"], default="arb",
                        help="Sort by: IRR desc (default), PM ask desc, or name")
    parser.add_argument("--contracts", type=int, default=CONTRACTS,
                        help=f"Contracts per leg (default: {CONTRACTS})")
    parser.add_argument("--arb-only", action="store_true",
                        help="Only show rows where an arbitrage exists")
    args = parser.parse_args()

    print(f"\n✓ compare.py  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Contracts: {args.contracts}  |  Sort: {args.sort}  |  Arb-only: {args.arb_only}\n")

    all_arb_a: list[dict] = []   # PM YES + Kalshi NO
    all_arb_b: list[dict] = []   # PM NO  + Kalshi YES

    for sport in SPORTS:
        print(f"── {sport['label']} ──")

        print("  Fetching Polymarket prices...")
        pm_prices  = fetch_pm_prices(sport)

        print("  Fetching Kalshi prices...")
        kal_prices = fetch_kalshi_prices(sport)

        for direction in ("A", "B"):
            rows = build_rows(sport, pm_prices, kal_prices, args.contracts, direction)

            if args.sort == "arb":
                rows.sort(key=lambda r: r["return"] if r["return"] is not None else -9999,
                          reverse=True)
            elif args.sort == "pm":
                rows.sort(key=lambda r: r["pm_ask"] or 0, reverse=True)
            else:
                rows.sort(key=lambda r: r["name"])

            print_table(sport, rows, args.contracts, args.arb_only, direction)

            # Accumulate arb hits for summary tables
            for r in rows:
                if r["arb"]:
                    entry = {**r, "market": sport["label"]}
                    if direction == "A":
                        all_arb_a.append(entry)
                    else:
                        all_arb_b.append(entry)
        print()

    print_summary(all_arb_a, all_arb_b, args.contracts)


if __name__ == "__main__":
    main()
