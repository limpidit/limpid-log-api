"""
Parses EBP log files.

Line format:
    API {CODE} - {DD/MM/YYYY} {HH:MM:SS} : {REST}

Where REST can be:
    ERREUR !! : {message}          → level=error
    WARNING : {message}            → level=warning
    info : {message}               → level=info
    {message}                      → level=system (separator/lifecycle lines)

Special patterns in message:
    DBName - {name} - API Name {full_name} - DBId : {uuid} - user {user}
    -------------- TP {STATE} ------------------
    --------------------------------
    Dernier Fichier de log bien envoyé
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

LINE_RE = re.compile(
    r"^API\s+(?P<code>[A-Z0-9]+)\s+-\s+(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+:\s*(?P<rest>.*)$"
)

INIT_RE = re.compile(
    r"DBName\s+-\s+(?P<db_name>\S+)\s+-\s+API Name\s+(?P<api_name>.+?)\s+-\s+DBId\s+:\s+(?P<db_id>[a-f0-9-]+)\s+-\s+user\s+(?P<user>\S+)"
)

PARIS_TZ = timezone(timedelta(hours=2))  # CET+2 (Europe/Paris approximate)


@dataclass
class ParsedLine:
    api_code: str
    logged_at: datetime
    level: str  # info | warning | error | system
    message: str
    raw_line: str


@dataclass
class ParsedInitInfo:
    db_name: str
    api_name: str
    db_id: str
    user: str
    api_code: str


@dataclass
class ParseResult:
    lines: list[ParsedLine]
    init_infos: list[ParsedInitInfo]
    api_names: dict[str, str]  # code → full name
    db_id: str | None
    db_name: str | None
    ebp_file: str | None


def _parse_level_and_message(rest: str) -> tuple[str, str]:
    rest = rest.strip()

    if rest.startswith("ERREUR !!"):
        after = rest[len("ERREUR !!"):]
        if after.startswith(" : "):
            after = after[3:]
        return "error", after.strip() or "ERREUR !!"

    if rest.startswith("WARNING"):
        after = rest[len("WARNING"):]
        if after.startswith(" : "):
            after = after[3:]
        return "warning", after.strip() or "WARNING"

    if rest.startswith("info :") or rest.startswith("info:"):
        after = re.sub(r"^info\s*:\s*", "", rest)
        return "info", after.strip()

    # Detect system/lifecycle lines
    if re.match(r"^-+\s*(TP\s+\w+\s*)?-+$", rest.strip()):
        return "system", rest.strip()
    if rest.strip() == "--------------------------------":
        return "system", rest.strip()
    if "Dernier Fichier de log" in rest:
        return "system", rest.strip()

    return "info", rest.strip()


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    day, month, year = date_str.split("/")
    hour, minute, second = time_str.split(":")
    dt = datetime(
        int(year), int(month), int(day),
        int(hour), int(minute), int(second),
        tzinfo=PARIS_TZ
    )
    return dt.astimezone(timezone.utc)


def parse_log_file(
    content: str,
    filename: str | None = None,
) -> ParseResult:
    lines: list[ParsedLine] = []
    init_infos: list[ParsedInitInfo] = []
    api_names: dict[str, str] = {}
    db_id = None
    db_name = None
    ebp_file = None

    # Extract db_name from filename: LogT2M_uuid.txt → T2M
    if filename:
        m = re.match(r"Log([^_]+)_([a-f0-9-]+)\.txt", filename, re.IGNORECASE)
        if m:
            db_name = m.group(1)

    for raw_line in content.splitlines():
        raw_line_stripped = raw_line.strip()
        if not raw_line_stripped:
            continue

        m = LINE_RE.match(raw_line_stripped)
        if not m:
            continue

        code = m.group("code")
        try:
            logged_at = _parse_datetime(m.group("date"), m.group("time"))
        except (ValueError, TypeError):
            continue
        rest = m.group("rest")

        # Check if it's an init info line
        init_m = INIT_RE.search(rest)
        if init_m:
            info = ParsedInitInfo(
                api_code=code,
                db_name=init_m.group("db_name").split("_")[0],  # strip UUID part
                api_name=init_m.group("api_name").strip(),
                db_id=init_m.group("db_id"),
                user=init_m.group("user"),
            )
            init_infos.append(info)
            api_names[code] = info.api_name
            if db_id is None:
                db_id = info.db_id
            if db_name is None:
                db_name = info.db_name

            level = "system"
            message = rest.strip()
        else:
            level, message = _parse_level_and_message(rest)

        lines.append(ParsedLine(
            api_code=code,
            logged_at=logged_at,
            level=level,
            message=message,
            raw_line=raw_line_stripped,
        ))

    return ParseResult(
        lines=lines,
        init_infos=init_infos,
        api_names=api_names,
        db_id=db_id,
        db_name=db_name,
        ebp_file=ebp_file,
    )


def extract_batch_uuid_from_filename(filename: str) -> str | None:
    m = re.match(r"Log[^_]+_([a-f0-9-]+)\.txt", filename, re.IGNORECASE)
    return m.group(1) if m else None
