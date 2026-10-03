"""Opt-in, standard-library SEC public-data collection and explicit fact selection.

``collect_company(cik, cache_dir, user_agent, cutoff=None)`` fetches only the two
documented data.sec.gov company endpoints, keeps hashed raw snapshots, and returns
issuer, sources, raw submissions/companyfacts, and cutoff-filtered filing metadata.
``select_facts(companyfacts, cutoff, accession=None, concepts=None)`` returns
normalized rows without guessing a metric, unit, period, or latest accession.
``require_fact`` resolves one fully specified concept/unit/period or raises.

Companyfacts has date-only disclosure metadata. A fact becomes eligible at the
start of the *next America/New_York day* after ``filed``, converted to UTC. If
the host lacks IANA timezone data, 05:00 UTC is a conservative fallback.
Collection time remains separate:
today's download can reconstruct public availability, never historical possession.
Custom taxonomy and dimensional facts may be absent from the SEC aggregate API.
"""

from __future__ import annotations

from datetime import date, datetime, time as day_time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib import error, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024
REQUEST_TIMEOUT = 30
SEC_API_DOCUMENTATION = "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
SEC_FAIR_ACCESS = "https://www.sec.gov/about/developer-resources"
SEC_FILING_DATE_POLICY = "https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing"


class SECError(ValueError):
    """Invalid, ambiguous, unavailable, or unverifiable SEC input."""

    def __init__(self, message, *, reason_code=None):
        super().__init__(message)
        self.reason_code = reason_code


def normalize_cik(cik: str | int) -> str:
    """Return ten digits; URLs, negative values and CIK zero are rejected."""
    if isinstance(cik, bool) or not isinstance(cik, (str, int)):
        raise SECError("CIK must be an integer or one to ten decimal digits")
    value = str(cik)
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) == 0:
        raise SECError("CIK must be one to ten decimal digits and nonzero")
    return value.zfill(10)


def _date(value: str, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SECError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SECError(f"{label} must be a valid ISO date") from None


def _cutoff(value: str | date | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, day_time.max, timezone.utc)
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        parsed = datetime.combine(_date(value, "cutoff"), day_time.max, timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise SECError("cutoff must be an ISO date or timezone-aware timestamp") from None
    else:
        raise SECError("cutoff must be an ISO date or timezone-aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SECError("cutoff timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def public_available_at(filed: str) -> str:
    """Next midnight Eastern Time for date-only disclosure metadata, in UTC.

    Some same-date forms are disseminated until 10 p.m. ET, which may fall on
    the next UTC date. This policy avoids inventing an intraday timestamp. A
    missing host IANA database falls back to 05:00 UTC, never earlier than
    modern Eastern Time midnight, without requiring a tzdata dependency.
    """
    try:
        next_day = _date(filed, "filed") + timedelta(days=1)
    except OverflowError:
        raise SECError("filed date exceeds supported date range") from None
    try:
        eastern = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        return datetime.combine(next_day, day_time(5), timezone.utc).isoformat()
    return datetime.combine(next_day, day_time.min, eastern).astimezone(timezone.utc).isoformat()


def _accession(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", value):
        raise SECError("accession must have SEC format ##########-##-######")
    return value


def filing_url(cik: str | int, accession: str, document: str | None = None) -> str:
    """Build an SEC archive link, never fetch it or accept an arbitrary URL."""
    cik = normalize_cik(cik)
    accession = _accession(accession)
    document = document or f"{accession}-index.htm"
    if not isinstance(document, str) or not re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", document):
        raise SECError("primary document must be a safe relative SEC document path")
    if any(segment in (".", "..") for segment in document.split("/")):
        raise SECError("primary document must be a safe relative SEC document path")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"


def select_facts(companyfacts: dict, cutoff: str | date | datetime,
                 accession: str | None = None,
                 concepts: list[str] | tuple[str, ...] | set[str] | None = None) -> list[dict]:
    """Normalize eligible rows; ``concepts`` uses ``taxonomy:Concept`` names.

    Conflicting duplicates within an accession fail closed. Equivalent duplicate
    contexts collapse. Multiple units, periods and accessions remain separate;
    callers must use ``require_fact`` to obtain an unambiguous model input.
    Neither ``fy`` nor ``frame`` is used to infer a fact's economic period.
    """
    limit = _cutoff(cutoff)
    if accession is not None:
        _accession(accession)
    if not isinstance(companyfacts, dict) or not isinstance(companyfacts.get("facts"), dict):
        raise SECError("companyfacts must contain a facts object")
    normalize_cik(companyfacts.get("cik"))
    chosen = set(concepts) if concepts is not None else None
    if chosen is not None and any(not isinstance(c, str) or ":" not in c for c in chosen):
        raise SECError("concepts must contain taxonomy:Concept names")
    normalized = {}
    for taxonomy, tags in companyfacts["facts"].items():
        if not isinstance(tags, dict):
            raise SECError("taxonomy must contain a concept object")
        for concept, details in tags.items():
            if chosen is not None and f"{taxonomy}:{concept}" not in chosen:
                continue
            if not isinstance(details, dict) or not isinstance(details.get("units"), dict):
                raise SECError(f"{taxonomy}:{concept} must contain units")
            for unit, rows in details["units"].items():
                if not isinstance(unit, str) or not unit or not isinstance(rows, list):
                    raise SECError("unit must be named and contain an array")
                for row in rows:
                    if not isinstance(row, dict):
                        raise SECError("fact must be an object")
                    if accession is not None and row.get("accn") != accession:
                        continue
                    available = public_available_at(row.get("filed"))
                    if _cutoff(available) > limit:
                        continue
                    accn = _accession(row.get("accn"))
                    end = _date(row.get("end"), "end")
                    start = _date(row["start"], "start") if "start" in row else None
                    filed = _date(row["filed"], "filed")
                    if (start and start > end) or end > filed:
                        raise SECError("fact has an invalid or future economic period")
                    value = row.get("val")
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or (isinstance(value, float) and not math.isfinite(value))):
                        raise SECError("fact value must be a finite number")
                    if not isinstance(row.get("form"), str) or not row["form"]:
                        raise SECError("fact form is required")
                    fact = {
                        "taxonomy": taxonomy, "concept": concept, "unit": unit,
                        "start": start.isoformat() if start else None, "end": end.isoformat(),
                        "filed": filed.isoformat(), "accn": accn, "form": row["form"],
                        "val": value, "available_at": available,
                        "period_type": "duration" if start else "instant",
                    }
                    identity = (taxonomy, concept, unit, fact["start"], fact["end"], accn)
                    prior = normalized.get(identity)
                    if prior is not None and prior != fact:
                        raise SECError(f"conflicting duplicate fact: {taxonomy}:{concept} {accn}")
                    normalized[identity] = fact
    return sorted(normalized.values(), key=lambda f: (
        f["taxonomy"], f["concept"], f["unit"], f["end"], f["start"] or "", f["filed"], f["accn"]))


def require_fact(facts: list[dict], *, taxonomy: str, concept: str,
                 unit: str, start: str | None, end: str,
                 accession: str | None = None) -> dict:
    """Select exactly one row with explicit unit/period; no fallback or summation."""
    _date(end, "end")
    if start is not None:
        _date(start, "start")
    if accession is not None:
        _accession(accession)
    matches = [f for f in facts if f.get("taxonomy") == taxonomy and f.get("concept") == concept
               and f.get("unit") == unit and f.get("start") == start and f.get("end") == end
               and (accession is None or f.get("accn") == accession)]
    if len(matches) != 1:
        raise SECError(f"expected exactly one {taxonomy}:{concept} {unit} {start}/{end}; found {len(matches)}")
    return dict(matches[0])


def select_filings(submissions: dict, cutoff: str | date | datetime) -> list[dict]:
    """Return recent, cutoff-eligible filing rows; older paged files are not fetched."""
    limit = _cutoff(cutoff)
    cik = normalize_cik(submissions.get("cik"))
    recent = submissions.get("filings", {}).get("recent", {})
    fields = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    if not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in fields):
        raise SECError("submissions recent filing arrays are missing")
    count = len(recent["accessionNumber"])
    if any(len(recent[k]) != count for k in fields):
        raise SECError("submissions filing arrays have inconsistent lengths")
    output = []
    for i in range(count):
        available = public_available_at(recent["filingDate"][i])
        if _cutoff(available) > limit:
            continue
        row = {k: recent[k][i] for k in fields}
        row["available_at"] = available
        row["source_url"] = filing_url(cik, row["accessionNumber"], row["primaryDocument"])
        acceptance = recent.get("acceptanceDateTime", [])
        if len(acceptance) == count:
            row["acceptanceDateTime"] = acceptance[i]
        output.append(row)
    return output


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SECError("SEC endpoint redirect refused; review the documented endpoint")


def _fetch_json(url: str, user_agent: str) -> tuple[dict, bytes, dict]:
    if not re.fullmatch(r"https://data\.sec\.gov/(?:submissions|api/xbrl/companyfacts)/CIK[0-9]{10}\.json", url):
        raise SECError("only the documented SEC company JSON endpoints may be fetched")
    req = request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json",
                                       "Accept-Encoding": "identity"})
    try:
        with request.build_opener(_NoRedirect()).open(req, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 200:
                raise SECError(f"SEC request failed (HTTP {response.status})")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SECError("SEC response exceeds the 16 MiB limit")
            metadata = {
                "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "http_status": response.status, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "headers": {k: response.headers[k] for k in ("Content-Type", "ETag", "Last-Modified")
                            if response.headers.get(k)},
            }
    except error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read(8192).decode('utf-8', errors='replace').lower()
        except (AttributeError, OSError):
            body = ''
        exc.close()
        diagnostic = 'undeclared_automated_tool' if 'undeclared automated tool' in body else 'rate_threshold' if 'request rate threshold exceeded' in body else 'access_denied' if 'access denied' in body else None
        raise SECError(f"SEC request failed (HTTP {status}); no automatic retry", reason_code=diagnostic) from None
    except (error.URLError, TimeoutError, OSError):
        raise SECError("SEC request failed (network/timeout); no automatic retry") from None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise SECError("SEC response is not valid JSON") from None
    if not isinstance(data, dict):
        raise SECError("SEC response must be a JSON object")
    return data, raw, metadata


def _cache_snapshot(directory: Path, cik: str, kind: str, raw: bytes, metadata: dict, *, suffix='.json') -> dict:
    if suffix not in {'.json', '.html', '.txt'}:
        raise SECError('Unsupported public snapshot format')
    if directory.is_symlink():
        raise SECError('Public snapshot directory must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"sec-{cik}-{kind}-{metadata['sha256']}"
    raw_path = directory / f"{stem}{suffix}"
    meta_path = directory / f"{stem}.metadata.json"
    meta_bytes = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    current = sum(p.stat().st_size for p in directory.glob("sec-*") if p.is_file())
    addition = sum(len(payload) for path, payload in ((raw_path, raw), (meta_path, meta_bytes))
                   if not path.exists())
    if current + addition > MAX_CACHE_BYTES:
        raise SECError("SEC cache would exceed 64 MiB; choose a reviewed empty cache directory")
    for path, payload in ((raw_path, raw), (meta_path, meta_bytes)):
        if path.is_symlink():
            raise SECError("SEC snapshot path must not be a symlink")
        if path.exists():
            if path == raw_path and hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
                raise SECError("cached SEC snapshot hash mismatch")
            continue
        fd, temporary = tempfile.mkstemp(prefix=".sec-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {**metadata, "cache_path": str(raw_path.resolve()), "metadata_path": str(meta_path.resolve())}


def collect_submissions(cik, cache_dir, user_agent, cutoff=None):
    """One explicit SEC GET for filing discovery; do not download companyfacts."""
    cik = normalize_cik(cik)
    if not isinstance(user_agent, str) or len(user_agent.strip()) < 10 or any(c in user_agent for c in '\r\n'):
        raise SECError('an identifying, single-line SEC User-Agent is required')
    limit = _cutoff(cutoff) if cutoff is not None else datetime.now(timezone.utc)
    data, raw, metadata = _fetch_json(f'https://data.sec.gov/submissions/CIK{cik}.json', user_agent.strip())
    if normalize_cik(data.get('cik')) != cik:
        raise SECError('SEC response CIK differs from requested issuer')
    filings = select_filings(data, limit)
    source = _cache_snapshot(Path(cache_dir), cik, 'submissions', raw, metadata)
    return {'issuer':{'cik':cik, 'name':data.get('name'), 'tickers':data.get('tickers',[]), 'exchanges':data.get('exchanges',[])},
        'cutoff':limit.isoformat(), 'as_of':source['retrieved_at'], 'sources':[{'kind':'submissions', **source}],
        'filings':filings, 'scope':'Recent SEC submissions metadata only; no companyfacts or report content fetched'}


def collect_company(cik: str | int, cache_dir: str | Path, user_agent: str,
                    cutoff: str | date | datetime | None = None) -> dict:
    """Explicit network action, two sequential GETs, no auth, retries or auto-refresh.

    Supply an identifying User-Agent with your own public contact details per SEC
    fair-access guidance. User-Agent is never copied into snapshots or exceptions.
    The 64 MiB cache refuses additional snapshots when full and never prunes them.
    Raw snapshots preserve the response, including later facts; selection applies
    the requested public-information cutoff separately. No local database is used.
    """
    cik = normalize_cik(cik)
    if not isinstance(user_agent, str) or len(user_agent.strip()) < 10 or any(c in user_agent for c in "\r\n"):
        raise SECError("an identifying, single-line SEC User-Agent is required")
    limit = _cutoff(cutoff) if cutoff is not None else datetime.now(timezone.utc)
    urls = {
        "submissions": f"https://data.sec.gov/submissions/CIK{cik}.json",
        "companyfacts": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
    }
    payloads, sources = {}, []
    for index, (kind, url) in enumerate(urls.items()):
        if index:
            time.sleep(1.0)
        data, raw, metadata = _fetch_json(url, user_agent.strip())
        if normalize_cik(data.get("cik")) != cik:
            raise SECError("SEC response CIK differs from requested issuer")
        payloads[kind] = data
        sources.append({"kind": kind, **_cache_snapshot(Path(cache_dir), cik, kind, raw, metadata)})
    submissions = payloads["submissions"]
    return {
        "issuer": {"cik": cik, "name": submissions.get("name"),
                   "entity_name": payloads["companyfacts"].get("entityName"),
                   "tickers": submissions.get("tickers", []), "exchanges": submissions.get("exchanges", [])},
        "cutoff": limit.isoformat(), "as_of": max(s["retrieved_at"] for s in sources),
        "sources": sources, **payloads, "filings": select_filings(submissions, limit),
        "availability_basis": "next midnight America/New_York after filed converted to UTC; 05:00 UTC fallback without IANA data; public availability reconstruction only",
        "limitations": ["Present snapshots cannot prove historical acquisition or original dissemination.",
                        "Only recent submission metadata is fetched; older pagination is not automatic.",
                        "Companyfacts can omit custom taxonomy, segment and dimensional facts.",
                        "Malformed historical rows fail closed; select explicit concepts and accessions for scoped extraction."],
    }
