# tools/theharvester.py — wrapper around theHarvester.
#
# theHarvester collects emails, subdomains, hosts and IPs for a domain.
# It works passively (does not touch the domain itself).
#
# stdout format (theHarvester 5.x):
#   [*] IPs found: 2
#   -------------------
#   1.2.3.4
#   [*] Emails found: 1
#   ----------------------
#   john@example.com
#   [*] Hosts found: 2
#   ---------------------
#   www.example.com:1.2.3.4
#   api.example.com
#
# The parser is deliberately tolerant: it first splits the output into sections,
# then validates emails/domains/IPs and additionally searches for FQDNs
# across the whole text (in case a section got mixed up with logs).

import ipaddress
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from logger import get_logger


logger = get_logger("tools.theharvester")

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9\-])"
)

_SECTION_RE = re.compile(
    r"^\[\*\]\s+(IPs|Emails|Hosts)\s+found(?:\s*:\s*\d+)?",
    re.IGNORECASE,
)

_SECTION_KEYS = {
    "ips": "ips",
    "emails": "emails",
    "hosts": "hosts",
}


def _resolve_command() -> list:
    """
    Looks for the theHarvester executable.

    Order:
      1. env THEHARVESTER_BIN (full path);
      2. theHarvester in PATH;
      3. typical local installs (~/theHarvester/.venv/bin/...).
    """
    env_bin = os.environ.get("THEHARVESTER_BIN", "").strip()
    if env_bin:
        return [env_bin]

    found = shutil.which("theHarvester")
    if found:
        return [found]

    home = Path.home()
    candidates = [
        home / "theHarvester" / ".venv" / "bin" / "theHarvester",
        home / "theHarvester" / "bin" / "theHarvester",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]

    # Fallback: run the python script from the theHarvester repository.
    script = home / "theHarvester" / "theHarvester" / "theHarvester.py"
    if script.is_file():
        venv_python = home / "theHarvester" / ".venv" / "bin" / "python"
        if venv_python.is_file():
            return [str(venv_python), str(script)]
        return [sys.executable, str(script)]

    # Let subprocess fail with FileNotFoundError — we handle it.
    return ["theHarvester"]


def _parse_sections(raw: str) -> dict:
    """Splits theHarvester stdout into ips / emails / hosts sections."""
    sections = {"ips": [], "emails": [], "hosts": []}
    current = None

    for line in (raw or "").splitlines():
        stripped = line.strip()

        match = _SECTION_RE.match(stripped)
        if match:
            current = _SECTION_KEYS[match.group(1).lower()]
            continue

        # Any new "[*] ..." line ends the current section.
        if stripped.startswith("[*]"):
            current = None
            continue

        if current is None or not stripped:
            continue

        # Separators "-----"
        if set(stripped) <= {"-", "_", "="}:
            continue

        # Service log lines inside the section.
        if stripped.startswith(("[!]", "[+]", "[-]", "[x]", "[*]")):
            continue

        sections[current].append(stripped)

    return sections


def _parse_ip(value: str):
    """Returns an ipaddress object or None."""
    value = (value or "").strip().strip("[]")
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _split_host_entry(entry: str):
    """
    Parses a theHarvester host line.

    Examples:
      "www.example.com:1.2.3.4"  -> ("www.example.com", "1.2.3.4")
      "www.example.com:443"      -> ("www.example.com", None)
      "www.example.com"          -> ("www.example.com", None)
      "1.2.3.4"                  -> (None, "1.2.3.4")
      "[2001:db8::1]:443"        -> (None, "2001:db8::1")
    """
    entry = (entry or "").strip().strip(",").strip()
    if not entry:
        return None, None

    # Plain IP (including IPv6).
    ip_only = _parse_ip(entry)
    if ip_only is not None:
        return None, str(ip_only)

    host = entry
    ip = None

    # [IPv6]:port
    bracket = re.match(r"^\[([0-9A-Fa-f:.]+)\](?::(\d+))?$", entry)
    if bracket:
        return None, bracket.group(1)

    # host:IP or host:port
    if ":" in entry:
        head, _, tail = entry.rpartition(":")
        tail_ip = _parse_ip(tail)
        if tail_ip is not None:
            host, ip = head, str(tail_ip)
        elif tail.isdigit() and head:
            host = head

    host = host.strip().strip("[]").rstrip(".").lower()
    if not host:
        return None, ip

    # The host must be a valid DNS name.
    if not re.fullmatch(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
        host,
    ):
        return None, ip

    return host, ip


def parse_theharvester_output(raw: str, domain: str) -> dict:
    """
    Parses theHarvester stdout for a specific domain.

    Returns:
      {
        "emails": [...],
        "subdomains": [...],
        "ips": [...],
        "hosts": [{"host": "...", "ip": "..."}],
      }
    """
    domain = (domain or "").strip().lower().rstrip(".")
    sections = _parse_sections(raw or "")

    # --- Emails: the section first, then the whole text as a fallback ---
    emails = set()
    for item in sections["emails"]:
        for email in _EMAIL_RE.findall(item):
            emails.add(email.lower())
    for email in _EMAIL_RE.findall(raw or ""):
        emails.add(email.lower())

    # --- IPs ---
    ips = set()
    for item in sections["ips"]:
        ip = _parse_ip(item)
        if ip is not None:
            ips.add(str(ip))

    # --- Hosts / subdomains ---
    subdomains = set()
    hosts = {}          # host -> ip (or None)
    for item in sections["hosts"]:
        host, ip = _split_host_entry(item)
        if host:
            hosts.setdefault(host, ip)
            if ip:
                ips.add(ip)
        elif ip:
            ips.add(ip)

    # Fallback: FQDNs across the whole output (in case the hosts section was lost).
    if domain:
        host_re = re.compile(
            r"(?<![A-Za-z0-9.\-])"
            r"((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            + re.escape(domain)
            + r")(?![A-Za-z0-9\-])",
            re.IGNORECASE,
        )
        for match in host_re.finditer(raw or ""):
            host = match.group(1).strip().rstrip(".").lower()
            hosts.setdefault(host, None)

    for host in list(hosts):
        if host != domain:
            subdomains.add(host)

    return {
        "emails": sorted(emails),
        "subdomains": sorted(subdomains),
        "ips": sorted(ips),
        "hosts": [
            {"host": host, "ip": ip}
            for host, ip in sorted(hosts.items())
        ],
    }


def run_theharvester(domain: str, limit: int = 100) -> dict:
    """
    Runs theHarvester for a domain.
    Returns: {"domain": ..., "emails": [...], "subdomains": [...],
                 "ips": [...], "hosts": [...], "raw": "..."}
    """
    domain = (domain or "").strip().lower().rstrip(".")
    logger.info("Запуск theHarvester: %s (limit=%s)", domain, limit)
    cmd = _resolve_command() + [
        "-d", domain,
        "-b", "all",           # all sources
        "-l", str(limit),      # result limit
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        raw = result.stdout or ""
    except FileNotFoundError:
        logger.warning("theHarvester не найден")
        return {"domain": domain, "emails": [], "subdomains": [], "ips": [],
                "hosts": [], "error": "theHarvester не найден"}
    except subprocess.TimeoutExpired:
        logger.warning("theHarvester timeout (300 сек)")
        return {"domain": domain, "emails": [], "subdomains": [], "ips": [],
                "hosts": [], "error": "theHarvester не успел за 5 минут"}
    except Exception as exc:
        logger.error("Ошибка theHarvester: %s", exc, exc_info=True)
        return {"domain": domain, "emails": [], "subdomains": [], "ips": [],
                "hosts": [], "error": f"theHarvester: {exc}"}

    parsed = parse_theharvester_output(raw, domain)

    response = {
        "domain": domain,
        "emails": parsed["emails"],
        "subdomains": parsed["subdomains"],
        "ips": parsed["ips"],
        "hosts": parsed["hosts"],
        "raw": raw[:5000],  # cap it so the JSON does not bloat
    }

    logger.info(
        "theHarvester завершен: emails=%s subdomains=%s ips=%s",
        len(parsed["emails"]), len(parsed["subdomains"]), len(parsed["ips"]),
    )

    if result.returncode != 0 and not parsed["emails"] and not parsed["subdomains"]:
        stderr = (result.stderr or "").strip()
        if stderr:
            response["error"] = stderr[:500]
            logger.warning("theHarvester код %s, stderr: %s", result.returncode, stderr[:300])

    return response
