from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .http import retrying_session
from .models import SourceMaterial

LOGGER = logging.getLogger(__name__)
TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def _published(entry: dict) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def _domain_allowed(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


class FeedCollector:
    def __init__(self, timeout: int = 20, max_items: int = 40) -> None:
        self.timeout = timeout
        self.max_items = max_items

    def _article_text(self, session: requests.Session, url: str, domains: list[str]) -> str:
        response = session.get(url, timeout=self.timeout)
        response.raise_for_status()
        if not _domain_allowed(response.url, domains):
            raise ValueError(f"Article redirected outside allowed domains: {response.url}")
        if "text/html" not in response.headers.get("content-type", "").lower():
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header", "form"]):
            node.decompose()
        container = soup.find("article") or soup.find("main") or soup
        paragraphs = [_clean(p.get_text(" ", strip=True)) for p in container.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p.split()) >= 5)
        paywall = ("subscribe to continue", "sign in to read", "purchase this article")
        if any(marker in text.lower() for marker in paywall):
            return ""
        return text[:18000]

    def _pubmed(self, session: requests.Session, source: dict, search_terms: list[str]) -> list[SourceMaterial]:
        terms = [term for term in search_terms if len(term.split()) <= 3][:18]
        query = " OR ".join(f'"{term}"[Title/Abstract]' for term in terms)
        search = session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "retmode": "json", "retmax": min(self.max_items, 20), "sort": "pub date", "reldate": 30, "datetype": "pdat", "term": query},
            timeout=self.timeout,
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        fetch = session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "retmode": "xml", "id": ",".join(ids)}, timeout=self.timeout,
        )
        fetch.raise_for_status()
        root = ET.fromstring(fetch.content)
        items: list[SourceMaterial] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID", "").strip()
            title_node = article.find(".//ArticleTitle")
            title = _clean("".join(title_node.itertext()) if title_node is not None else "")
            abstract = " ".join(_clean("".join(node.itertext())) for node in article.findall(".//Abstract/AbstractText"))
            date_node = article.find(".//ArticleDate") or article.find(".//JournalIssue/PubDate")
            if date_node is None:
                continue
            year, month, day = (date_node.findtext(key, "").strip() for key in ("Year", "Month", "Day"))
            month_map = {name: index for index, name in enumerate(("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
            if month in month_map:
                month = str(month_map[month])
            if not (pmid and title and abstract and year.isdigit() and month.isdigit() and day.isdigit()):
                continue
            published = datetime(int(year), int(month), int(day), tzinfo=timezone.utc).isoformat()
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            items.append(SourceMaterial(title, url, source["name"], published, f"{title}. {abstract}", float(source.get("credibility", 1)), source.get("country", "global"), "research", pmid))
        return items

    def collect(self, sources: list[dict], search_terms: list[str] | None = None) -> list[SourceMaterial]:
        results: list[SourceMaterial] = []
        session = retrying_session()
        session.headers["User-Agent"] = "MilletDaily/1.0 (+educational RSS reader)"
        for source in sources:
            if not source.get("enabled", True):
                continue
            try:
                if source.get("type") == "pubmed_api":
                    results.extend(self._pubmed(session, source, search_terms or ["millet", "sorghum"]))
                    continue
                response = session.get(source["feed_url"], timeout=self.timeout)
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                if parsed.bozo and not parsed.entries:
                    raise ValueError(str(parsed.bozo_exception))
                for entry in parsed.entries[: self.max_items]:
                    url = str(entry.get("link", "")).strip()
                    if not url or not _domain_allowed(url, source["allowed_domains"]):
                        LOGGER.warning("Rejected off-domain feed item", extra={"url": url, "source": source["name"]})
                        continue
                    title = _clean(str(entry.get("title", "")))
                    body = _clean(str(entry.get("summary", entry.get("description", ""))))
                    if not body and source.get("fetch_full_text"):
                        body = self._article_text(session, url, source["allowed_domains"])
                    if not title or not body:
                        continue
                    published_at = _published(entry)
                    if not published_at:
                        LOGGER.warning("Rejected undated feed item", extra={"url": url, "source": source["name"]})
                        continue
                    source_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
                    results.append(SourceMaterial(
                        title=title,
                        url=url,
                        source_name=source["name"],
                        published_at=published_at,
                        text=f"{title}. {body}",
                        credibility=float(source.get("credibility", 0.8)),
                        country=str(source.get("country", "global")),
                        source_id=source_id,
                    ))
            except Exception as exc:  # a broken feed must not crash the whole run
                LOGGER.error("Feed collection failed", extra={"source": source.get("name"), "error": str(exc)})
        return results
