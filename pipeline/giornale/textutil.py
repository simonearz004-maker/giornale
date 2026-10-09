"""Funzioni di testo: normalizzazione, token per il raggruppamento, estrazione dei numeri."""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

STOPWORDS = set("""
il lo la i gli le un uno una di a da in con su per tra fra e ed o od ma se che chi cui non piu più del dello della dei degli delle
al allo alla ai agli alle dal dallo dalla dai dagli dalle nel nello nella nei negli nelle sul sullo sulla sui sugli sulle col coi
è e' sono era essere ha hanno ho anche come dopo prima oggi ieri domani ancora già gia sì si no nuovo nuova nuovi nuove verso contro
oltre mentre quando dove perché perche quale quali questo questa questi queste quello quella sotto sopra fino senza
the a an of to in on for and or but with from by at as is are was were be been it its this that these those after before over
into new says said will would could should may up out about than more most not no
ansa video foto live diretta ultime ultima ora news breaking
""".split())

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "refresh_ce",
                    "fbclid", "gclid", "ito", "src", "cmpid"}


def clean_html(text: str | None, limit: int | None = None) -> str:
    if not text:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = _WS_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize(text: str) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r"[^\w%]+", " ", text)
    return _WS_RE.sub(" ", text).strip()


def tokens(text: str) -> set[str]:
    out = set()
    for tok in normalize(text).split():
        if tok in STOPWORDS or len(tok) < 2:
            continue
        if tok.isdigit() and len(tok) < 3:
            continue
        # radice grossolana: tronca a 6 caratteri per accorpare singolare/plurale (tasso/tassi, banca/banche)
        out.add(tok[:6] if len(tok) > 6 else tok)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def canonical_url(url: str) -> str:
    """Rimuove parametri di tracciamento e frammenti per riconoscere lo stesso articolo."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _TRACKING_PARAMS]
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def registered_domain(url_or_domain: str) -> str:
    """ansa.it, ilsole24ore.com, ecb.europa.eu … (approssimazione sufficiente per contare testate indipendenti)."""
    d = domain(url_or_domain) if "/" in url_or_domain else url_or_domain.lower().removeprefix("www.")
    parts = d.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "gov", "europa", "ac", "org"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) >= 3 and parts[-1] == "eu" and parts[-2] == "europa":
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ---------------------------------------------------------------------------
# Numeri
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)*(?![\d])")
_UNIT_AFTER = re.compile(r"^\s*(%|per\s*cento|percento|punti|pb|bp|bps|miliard|milion|mila|euro|€|dollar|\$|sterlin|yen|"
                         r"barili|tonnellat|trimestr|anni|mesi|giorni|volte|posti|lavorator|dipendent|famigli|imprese|"
                         r"seggi|voti|ore|minuti|km|gw|mw)", re.I)
_UNIT_BEFORE = re.compile(r"(€|\$|£|euro|usd|eur)\s*$", re.I)


def _candidates(raw: str) -> set[str]:
    """Possibili valori di un numero scritto all'italiana o all'inglese, in forma canonica."""
    s = raw.replace("−", "-").replace("+", "").replace(" ", "").replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("-")
    vals: set[float] = set()

    def add(text: str):
        try:
            vals.add(float(text))
        except ValueError:
            pass

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 1.234,5 (italiano)
            add(s.replace(".", "").replace(",", "."))
        else:                                     # 1,234.5 (inglese)
            add(s.replace(",", ""))
    elif "," in s:
        add(s.replace(",", "."))                  # 2,5
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            add(s.replace(",", ""))               # 1,234 (inglese)
    elif "." in s:
        add(s)                                    # 2.5 (inglese)
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            add(s.replace(".", ""))               # 1.234 (italiano)
    else:
        add(s)
    out = set()
    for v in vals:
        v = -v if neg else v
        out.add(_fmt(v))
        out.add(_fmt(abs(v)))                     # il segno spesso è espresso a parole ("in calo dello 0,3%")
    return out


def _fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def extract_numbers(text: str) -> list[dict]:
    """Restituisce i numeri 'significativi' di un testo, con i loro valori candidati.

    Si ignorano gli interi da 0 a 10 senza unità (spesso conteggi generici o parti di date)
    e i numeri dentro le sigle (es. G7, Covid-19, PM10).
    """
    results = []
    for m in _NUM_RE.finditer(text or ""):
        raw = m.group(0).strip()
        if not raw:
            continue
        start, end = m.span()
        before = text[max(0, start - 6):start]
        after = text[end:end + 14]
        if before and re.search(r"[A-Za-z]-?$", before):      # G7, Covid-19, PM10
            continue
        has_unit = bool(_UNIT_AFTER.match(after) or _UNIT_BEFORE.search(before))
        digits = re.sub(r"\D", "", raw)
        if not has_unit and re.fullmatch(r"\d{1,2}", digits) and int(digits) <= 10 and not re.search(r"[.,]", raw):
            continue
        results.append({"raw": raw, "candidates": _candidates(raw), "has_unit": has_unit})
    return results


def number_index(texts: list[str]) -> set[str]:
    idx: set[str] = set()
    for t in texts:
        for m in _NUM_RE.finditer(t or ""):
            idx |= _candidates(m.group(0))
    return idx


def unsupported_numbers(text: str, index: set[str]) -> list[str]:
    missing = []
    for n in extract_numbers(text):
        if not (n["candidates"] & index):
            missing.append(n["raw"])
    return missing


def slugify(text: str) -> str:
    s = normalize(text).replace("%", "")
    return re.sub(r"\s+", "-", s).strip("-")[:80]
