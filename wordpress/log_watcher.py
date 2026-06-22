#!/usr/bin/env python3
"""Watch Apache access log for WP login attempts and write JSON honeypot events."""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

ACCESS_LOG = "/var/log/apache2/access.log"
OUTPUT_LOG = "/var/log/honeypot/wordpress.json"

LOGIN_PATTERNS = [
    (r"POST /wp-login\.php", "wp.login_attempt"),
    (r"POST /xmlrpc\.php", "wp.xmlrpc_attack"),
    (r"GET /wp-content/plugins/", "wp.plugin_scan"),
    (r"GET /wp-admin/", "wp.admin_access"),
    (r"POST /wp-admin/admin-ajax\.php", "wp.ajax_request"),
]

seen = set()
state_file = "/tmp/wp_honeypot_seen.txt"


def load_seen():
    if os.path.exists(state_file):
        with open(state_file) as f:
            return set(f.read().splitlines())
    return set()


def save_seen(s):
    with open(state_file, "w") as f:
        f.write("\n".join(list(s)[-1000:]))


if __name__ == "__main__":
    log_path = Path(ACCESS_LOG)
    if not log_path.exists():
        exit(0)

    seen = load_seen()
    now = datetime.now(timezone.utc).isoformat()
    events = []

    with open(log_path) as f:
        for line in f:
            line_hash = str(hash(line))
            if line_hash in seen:
                continue
            seen.add(line_hash)

            for pattern, event_type in LOGIN_PATTERNS:
                if re.search(pattern, line):
                    # Extract IP
                    ip_match = re.match(r"(\d+\.\d+\.\d+\.\d+)", line)
                    source_ip = ip_match.group(1) if ip_match else "unknown"

                    # Extract URI
                    uri_match = re.search(r"(?:GET|POST) (\S+)", line)
                    uri = uri_match.group(1) if uri_match else ""

                    events.append({
                        "timestamp": now,
                        "event_type": event_type,
                        "source_ip": source_ip,
                        "request": line.strip(),
                        "uri": uri,
                        "remote_addr": source_ip,
                    })
                    break

    if events:
        with open(OUTPUT_LOG, "a") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    save_seen(seen)
