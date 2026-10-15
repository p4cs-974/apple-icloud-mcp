"""Read-only iCloud MCP server (Calendar, Reminders, Contacts). stdio transport.

Environment variables:
  APPLE_ID            (required) Apple ID email; used for CalDAV/CardDAV login.
  APPLE_APP_PASSWORD  (required) App-specific password created at account.apple.com.

The password is read from the environment, never logged, never returned by any tool, and never
written to disk. This server only reads data: it has no send, delete or modify tools.
"""
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import httpx
from icalendar import Calendar
from mcp.server.fastmcp import FastMCP



def _env(name: str) -> str:
    """Return a stripped env var, treating empty values and unexpanded ${PLACEHOLDER}s as unset."""
    v = os.environ.get(name, "").strip()
    return "" if (not v or (v.startswith("${") and v.endswith("}"))) else v


APPLE_ID = _env("APPLE_ID")
CALDAV = "https://caldav.icloud.com/"
CARDDAV = "https://contacts.icloud.com/"

mcp = FastMCP("apple-icloud")

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "card": "urn:ietf:params:xml:ns:carddav"}


def _require_credentials() -> None:
    missing = [n for n in ("APPLE_ID", "APPLE_APP_PASSWORD") if not _env(n)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing) + ". "
            "Set APPLE_ID to your Apple ID email and APPLE_APP_PASSWORD to an app-specific password "
            "created at https://account.apple.com (Sign-In and Security > App-Specific Passwords). "
            "Never use your normal Apple ID password.")


def _pw() -> str:
    _require_credentials()
    return _env("APPLE_APP_PASSWORD")


def _client() -> httpx.Client:
    pw = _pw()
    return httpx.Client(auth=(APPLE_ID, pw), follow_redirects=True, timeout=20,
                        headers={"User-Agent": "apple-icloud-mcp/0.1"})


def _dav(c: httpx.Client, method: str, url: str, body: str, depth: str = "0") -> ET.Element:
    r = c.request(method, url, content=body.encode(),
                  headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"})
    if r.status_code == 401:
        raise RuntimeError("iCloud rejected the Apple ID / app-specific password (401)")
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {url.split('/')[2]} failed: HTTP {r.status_code}")
    return ET.fromstring(r.content)


def _first_href(root: ET.Element, prop_path: str) -> str | None:
    el = root.find(f".//{prop_path}/d:href", NS)
    return el.text if el is not None else None


def _home(c: httpx.Client, base: str, home_prop: str) -> str:
    body = f'<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
    root = _dav(c, "PROPFIND", base, body)
    principal = _first_href(root, "d:current-user-principal")
    if not principal:
        raise RuntimeError("could not discover principal")
    principal = urljoin(base, principal)
    body = f'<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><{home_prop}/></d:prop></d:propfind>'
    root = _dav(c, "PROPFIND", principal, body)
    home = _first_href(root, home_prop)
    if not home:
        raise RuntimeError("could not discover home set")
    return urljoin(principal, home)


def _collections(c: httpx.Client, home: str, kind: str) -> list[dict]:
    """kind: 'calendar' or 'addressbook'."""
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav">'
            "<d:prop><d:resourcetype/><d:displayname/><c:supported-calendar-component-set/></d:prop></d:propfind>")
    root = _dav(c, "PROPFIND", home, body, depth="1")
    out = []
    for resp in root.findall("d:response", NS):
        rt = resp.find(".//d:resourcetype", NS)
        if rt is None:
            continue
        tag = "c:calendar" if kind == "calendar" else "card:addressbook"
        if rt.find(tag, NS) is None:
            continue
        comps = [x.get("name") for x in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)]
        name = resp.find(".//d:displayname", NS)
        out.append({"name": (name.text if name is not None and name.text else "(unnamed)"),
                    "url": urljoin(home, resp.find("d:href", NS).text), "components": comps})
    return out


def _cal_collections() -> tuple[httpx.Client, list[dict]]:
    c = _client()
    home = _home(c, CALDAV, "c:calendar-home-set")
    return c, _collections(c, home, "calendar")


def _fmt(v) -> str | None:
    if v is None:
        return None
    d = getattr(v, "dt", v)
    return d.isoformat() if isinstance(d, (date, datetime)) else str(d)


def _s(v) -> str | None:
    return str(v) if v is not None else None


@mcp.tool()
def calendar_list_calendars() -> list[dict]:
    """List iCloud calendars (name, supported component types)."""
    c, cols = _cal_collections()
    c.close()
    return [{"name": x["name"], "components": x["components"]} for x in cols if "VEVENT" in x["components"]]


@mcp.tool()
def calendar_list_events(start: str, end: str, calendar_name: str | None = None, limit: int = 200) -> list[dict]:
    """List events between start and end (ISO dates/datetimes, e.g. 2026-10-15 and 2026-10-29). Recurrences are expanded.
    Optionally filter by calendar name."""
    def parse(s):
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    s_, e_ = parse(start), parse(end)
    f = "%Y%m%dT%H%M%SZ"
    su, eu = s_.astimezone(timezone.utc).strftime(f), e_.astimezone(timezone.utc).strftime(f)
    body = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data>'
            f'<c:expand start="{su}" end="{eu}"/></c:calendar-data></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
            f'<c:comp-filter name="VEVENT"><c:time-range start="{su}" end="{eu}"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    c, cols = _cal_collections()
    events = []
    try:
        for col in cols:
            if "VEVENT" not in col["components"]:
                continue
            if calendar_name and col["name"].lower() != calendar_name.lower():
                continue
            root = _dav(c, "REPORT", col["url"], body, depth="1")
            for el in root.iterfind(".//c:calendar-data", NS):
                if not el.text:
                    continue
                cal = Calendar.from_ical(el.text)
                for ev in cal.walk("VEVENT"):
                    events.append({"calendar": col["name"], "summary": _s(ev.get("SUMMARY")),
                                   "start": _fmt(ev.get("DTSTART")), "end": _fmt(ev.get("DTEND")),
                                   "location": _s(ev.get("LOCATION")), "description": (_s(ev.get("DESCRIPTION")) or "")[:500] or None})
    finally:
        c.close()
    events.sort(key=lambda e: e["start"] or "")
    return events[:limit]


@mcp.tool()
def reminders_list_lists() -> list[dict]:
    """List iCloud reminder lists (calendars that support VTODO)."""
    c, cols = _cal_collections()
    c.close()
    return [{"name": x["name"]} for x in cols if "VTODO" in x["components"]]


@mcp.tool()
def reminders_list_incomplete(list_name: str | None = None, limit: int = 200) -> list[dict]:
    """List incomplete reminders (VTODOs), optionally from one list."""
    body = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data/></d:prop>'
            '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>')
    c, cols = _cal_collections()
    out = []
    try:
        for col in cols:
            if "VTODO" not in col["components"]:
                continue
            if list_name and col["name"].lower() != list_name.lower():
                continue
            root = _dav(c, "REPORT", col["url"], body, depth="1")
            for el in root.iterfind(".//c:calendar-data", NS):
                if not el.text:
                    continue
                for t in Calendar.from_ical(el.text).walk("VTODO"):
                    if _s(t.get("STATUS")) in ("COMPLETED", "CANCELLED") or t.get("COMPLETED"):
                        continue
                    out.append({"list": col["name"], "title": _s(t.get("SUMMARY")), "due": _fmt(t.get("DUE")),
                                "priority": _s(t.get("PRIORITY")), "notes": (_s(t.get("DESCRIPTION")) or "")[:500] or None})
    finally:
        c.close()
    out.sort(key=lambda r: r["due"] or "9999")
    return out[:limit]


def _load_contacts() -> list[dict]:
    import vobject
    c = _client()
    try:
        home = _home(c, CARDDAV, "card:addressbook-home-set")
        books = _collections(c, home, "addressbook")
        body = ('<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
                "<d:prop><card:address-data/></d:prop></card:addressbook-query>")
        out = []
        for b in books:
            root = _dav(c, "REPORT", b["url"], body, depth="1")
            for el in root.iterfind(".//card:address-data", NS):
                if not el.text:
                    continue
                try:
                    v = vobject.readOne(el.text)
                except Exception:
                    continue
                g = lambda k: [x.value for x in v.contents.get(k, [])]
                out.append({"name": (g("fn") or [None])[0], "emails": g("email"), "phones": g("tel"),
                            "org": [str(o) for o in g("org")], "birthday": (g("bday") or [None])[0]})
        return out
    finally:
        c.close()


@mcp.tool()
def contacts_search(query: str = "", limit: int = 50) -> list[dict]:
    """Search iCloud contacts by name/email/phone/org substring (empty query lists all, up to limit)."""
    q = query.lower()
    res = [x for x in _load_contacts() if not q or q in str(x).lower()]
    res.sort(key=lambda x: (x["name"] or "").lower())
    return res[:limit]


if __name__ == "__main__":
    mcp.run()
