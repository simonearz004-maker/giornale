"""Lettura del testo degli articoli, solo dove consentito.

Regole:
- se la fonte è marcata allow_fulltext = false (paywall o condizioni d'uso) si usa solo il sommario del feed;
- si rispetta robots.txt del sito;
- nessun tentativo di aggirare paywall o blocchi.
"""
from __future__ import annotations

import logging
from urllib import robotparser
from urllib.parse import urlsplit

import httpx
import trafilatura

log = logging.getLogger(__name__)


class ArticleReader:
    def __init__(self, user_agent: str, timeout: float = 20.0, max_chars: int = 6000):
        self.user_agent = user_agent
        self.max_chars = max_chars
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True)
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{base}/robots.txt")
                if r.status_code >= 400:
                    # robots.txt assente: per convenzione accesso consentito
                    rp.parse([])
                else:
                    rp.parse(r.text.splitlines())
            except Exception:
                rp = None   # non verificabile: per prudenza non si legge
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return bool(rp and rp.can_fetch(self.user_agent, url))

    def read(self, url: str, allow_fulltext: bool) -> tuple[str, bool]:
        """Restituisce (testo, letto_integralmente). Testo vuoto se non consentito o non disponibile."""
        if not allow_fulltext:
            return "", False
        try:
            if not self.allowed(url):
                return "", False
            r = self.client.get(url)
            if r.status_code >= 400:
                return "", False
            text = trafilatura.extract(r.text, include_comments=False, include_tables=True, favor_precision=True) or ""
        except Exception as exc:
            log.info("Lettura non riuscita %s: %s", url, exc)
            return "", False
        text = text.strip()
        if len(text) < 300:      # pagine di consenso, paywall o testo troppo breve: non affidabile
            return "", False
        return text[: self.max_chars], True

    def close(self):
        self.client.close()
