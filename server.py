"""iCloud MCP server (Calendar, Reminders, Contacts). stdio transport.

Environment variables:
  APPLE_ID            (required) Apple ID email; used for CalDAV/CardDAV login.
  APPLE_APP_PASSWORD  (required) App-specific password created at account.apple.com.

The password is read from the environment, never logged, never returned by any tool, and never
written to disk. Contacts are read-only. Calendar events and reminders can be created, updated and
deleted; there are no mail tools.
"""
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import httpx
from icalendar import Alarm, Calendar, Event, Todo
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
                        headers={"User-Agent": "apple-icloud-mcp/0.3"})


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
                    events.append({"uid": _s(ev.get("UID")), "calendar": col["name"], "summary": _s(ev.get("SUMMARY")),
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
                    out.append({"uid": _s(t.get("UID")), "list": col["name"], "title": _s(t.get("SUMMARY")), "due": _fmt(t.get("DUE")),
                                "priority": _s(t.get("PRIORITY")), "notes": (_s(t.get("DESCRIPTION")) or "")[:500] or None})
    finally:
        c.close()
    out.sort(key=lambda r: r["due"] or "9999")
    return out[:limit]


# ---------------- Write tools: calendar events and reminders ----------------
def _parse_when(value: str, tz: str | None):
    """Parse an ISO date or datetime. A date gives an all-day value. A naive datetime uses tz if
    given, otherwise it is a floating time that iCloud shows in the device's own time zone."""
    if len(value) == 10:
        return date.fromisoformat(value)
    d = datetime.fromisoformat(value)
    if d.tzinfo is None and tz:
        d = d.replace(tzinfo=ZoneInfo(tz))
    return d


def _pick(cols: list[dict], component: str, name: str | None, what: str) -> dict:
    cand = [x for x in cols if component in x["components"]]
    if name:
        cand = [x for x in cand if x["name"].lower() == name.lower()]
        if not cand:
            raise RuntimeError(f"No {what} named {name!r}. Use the list tool to see the names.")
    if not cand:
        raise RuntimeError(f"No {what} found on this account.")
    return cand[0]


def _wrap(item) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//apple-icloud-mcp//EN")
    cal.add("version", "2.0")
    cal.add_component(item)
    if hasattr(cal, "add_missing_timezones"):
        cal.add_missing_timezones()
    return cal.to_ical()


def _put(c: httpx.Client, url: str, data: bytes, etag: str | None) -> None:
    headers = {"Content-Type": "text/calendar; charset=utf-8"}
    headers["If-Match" if etag else "If-None-Match"] = etag or "*"
    r = c.put(url, content=data, headers=headers)
    if r.status_code == 401:
        raise RuntimeError("iCloud rejected the Apple ID / app-specific password (401)")
    if r.status_code == 412:
        raise RuntimeError("The item changed or already exists on iCloud (HTTP 412). Read it again and retry.")
    if r.status_code >= 400:
        raise RuntimeError(f"Saving to iCloud failed: HTTP {r.status_code}")


def _find(c: httpx.Client, cols: list[dict], component: str, uid: str, name: str | None):
    """Find one item by UID. Returns (collection, item url, etag, parsed component)."""
    body = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>'
            f'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="{component}"/></c:comp-filter></c:filter></c:calendar-query>')
    for col in cols:
        if component not in col["components"]:
            continue
        if name and col["name"].lower() != name.lower():
            continue
        # Fast path: items created by this plugin are stored as <uid>.ics.
        url = col["url"] + uid + ".ics"
        r = c.get(url)
        if r.status_code == 200:
            for comp in Calendar.from_ical(r.text).walk(component):
                if str(comp.get("UID")) == uid:
                    return col, url, r.headers.get("ETag"), comp
        # Slow path: scan the collection and match the UID locally.
        root = _dav(c, "REPORT", col["url"], body, depth="1")
        for resp in root.findall("d:response", NS):
            data = resp.find(".//c:calendar-data", NS)
            if data is None or not data.text:
                continue
            for comp in Calendar.from_ical(data.text).walk(component):
                if str(comp.get("UID")) == uid:
                    et = resp.find(".//d:getetag", NS)
                    return col, urljoin(col["url"], resp.find("d:href", NS).text), (et.text if et is not None else None), comp
    raise RuntimeError(f"No {component} with uid {uid!r} found. Use the list tool to get its uid.")


def _set(comp, key: str, value) -> None:
    if key in comp:
        del comp[key]
    comp.add(key, value)


@mcp.tool()
def calendar_create_event(title: str, start: str, end: str | None = None, calendar_name: str | None = None,
                          location: str | None = None, description: str | None = None,
                          timezone_name: str | None = None, alarm_minutes_before: int | None = None) -> dict:
    """Create a calendar event. start and end are ISO dates or datetimes. A plain date such as 2026-11-06 makes an
    all-day event. timezone_name is an IANA name such as America/Sao_Paulo and applies to datetimes without an offset.
    end defaults to one hour after start, or the next day for all-day events. Returns the new event's uid."""
    c, cols = _cal_collections()
    try:
        col = _pick(cols, "VEVENT", calendar_name, "calendar")
        st = _parse_when(start, timezone_name)
        if end:
            en = _parse_when(end, timezone_name)
        else:
            en = st + (timedelta(days=1) if type(st) is date else timedelta(hours=1))
        uid = str(uuid.uuid4()).upper()
        ev = Event()
        ev.add("uid", uid)
        ev.add("dtstamp", datetime.now(timezone.utc))
        ev.add("summary", title)
        ev.add("dtstart", st)
        ev.add("dtend", en)
        if location:
            ev.add("location", location)
        if description:
            ev.add("description", description)
        if alarm_minutes_before is not None:
            al = Alarm()
            al.add("action", "DISPLAY")
            al.add("description", title)
            al.add("trigger", timedelta(minutes=-alarm_minutes_before))
            ev.add_component(al)
        _put(c, col["url"] + uid + ".ics", _wrap(ev), None)
        return {"uid": uid, "calendar": col["name"], "summary": title, "start": _fmt(ev.get("DTSTART")), "end": _fmt(ev.get("DTEND"))}
    finally:
        c.close()


@mcp.tool()
def calendar_update_event(uid: str, title: str | None = None, start: str | None = None, end: str | None = None,
                          location: str | None = None, description: str | None = None,
                          timezone_name: str | None = None, calendar_name: str | None = None) -> dict:
    """Change fields of an existing event, found by uid (from calendar_list_events). Only the fields you pass change.
    Not for recurring events with exceptions: those are updated as a whole series."""
    c, cols = _cal_collections()
    try:
        col, url, etag, ev = _find(c, cols, "VEVENT", uid, calendar_name)
        if title is not None:
            _set(ev, "summary", title)
        if start is not None:
            _set(ev, "dtstart", _parse_when(start, timezone_name))
        if end is not None:
            _set(ev, "dtend", _parse_when(end, timezone_name))
        if location is not None:
            _set(ev, "location", location)
        if description is not None:
            _set(ev, "description", description)
        _set(ev, "dtstamp", datetime.now(timezone.utc))
        _put(c, url, _wrap(ev), etag)
        return {"uid": uid, "calendar": col["name"], "summary": _s(ev.get("SUMMARY")),
                "start": _fmt(ev.get("DTSTART")), "end": _fmt(ev.get("DTEND"))}
    finally:
        c.close()


@mcp.tool()
def calendar_delete_event(uid: str, calendar_name: str | None = None) -> dict:
    """Permanently delete an event by uid (from calendar_list_events). This cannot be undone."""
    c, cols = _cal_collections()
    try:
        col, url, etag, ev = _find(c, cols, "VEVENT", uid, calendar_name)
        r = c.delete(url, headers={"If-Match": etag} if etag else {})
        if r.status_code >= 400:
            raise RuntimeError(f"Deleting failed: HTTP {r.status_code}")
        return {"deleted": uid, "calendar": col["name"], "summary": _s(ev.get("SUMMARY"))}
    finally:
        c.close()


@mcp.tool()
def reminders_create(title: str, list_name: str | None = None, due: str | None = None, notes: str | None = None,
                     priority: int | None = None, timezone_name: str | None = None) -> dict:
    """Create a reminder. due is an optional ISO date or datetime. priority is 1 (high) to 9 (low). Returns its uid."""
    c, cols = _cal_collections()
    try:
        col = _pick(cols, "VTODO", list_name, "reminder list")
        uid = str(uuid.uuid4()).upper()
        t = Todo()
        t.add("uid", uid)
        t.add("dtstamp", datetime.now(timezone.utc))
        t.add("summary", title)
        t.add("status", "NEEDS-ACTION")
        if due:
            t.add("due", _parse_when(due, timezone_name))
        if notes:
            t.add("description", notes)
        if priority:
            t.add("priority", priority)
        _put(c, col["url"] + uid + ".ics", _wrap(t), None)
        return {"uid": uid, "list": col["name"], "title": title, "due": _fmt(t.get("DUE"))}
    finally:
        c.close()


@mcp.tool()
def reminders_update(uid: str, title: str | None = None, due: str | None = None, notes: str | None = None,
                     priority: int | None = None, completed: bool | None = None,
                     timezone_name: str | None = None, list_name: str | None = None) -> dict:
    """Change a reminder found by uid (from reminders_list_incomplete). Pass completed=true to mark it done."""
    c, cols = _cal_collections()
    try:
        col, url, etag, t = _find(c, cols, "VTODO", uid, list_name)
        if title is not None:
            _set(t, "summary", title)
        if due is not None:
            _set(t, "due", _parse_when(due, timezone_name))
        if notes is not None:
            _set(t, "description", notes)
        if priority is not None:
            _set(t, "priority", priority)
        if completed is True:
            _set(t, "status", "COMPLETED")
            _set(t, "completed", datetime.now(timezone.utc))
        elif completed is False:
            _set(t, "status", "NEEDS-ACTION")
            if "COMPLETED" in t:
                del t["COMPLETED"]
        _set(t, "dtstamp", datetime.now(timezone.utc))
        _put(c, url, _wrap(t), etag)
        return {"uid": uid, "list": col["name"], "title": _s(t.get("SUMMARY")), "status": _s(t.get("STATUS"))}
    finally:
        c.close()


@mcp.tool()
def reminders_delete(uid: str, list_name: str | None = None) -> dict:
    """Permanently delete a reminder by uid. This cannot be undone."""
    c, cols = _cal_collections()
    try:
        col, url, etag, t = _find(c, cols, "VTODO", uid, list_name)
        r = c.delete(url, headers={"If-Match": etag} if etag else {})
        if r.status_code >= 400:
            raise RuntimeError(f"Deleting failed: HTTP {r.status_code}")
        return {"deleted": uid, "list": col["name"], "title": _s(t.get("SUMMARY"))}
    finally:
        c.close()



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
