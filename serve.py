#!/usr/bin/env python3
"""
checker.py — URL reachability + latency checker.

Detects:
  - HTTP status (200/403/503/etc.)
  - Time to first byte (TTFB)
  - Total response time
  - Server header / CDN detection
  - Timeout / connection refused / DNS failure
  - Slow-response heuristic (potential DDoS / overload)

Standalone:
    python3 checker.py <url>
    python3 checker.py <url> --count 5 --interval 2
"""

import argparse
import socket
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


UA = "Mozilla/5.0 (X11; Linux x86_64) NullChecker/1.0"


def check_once(url, timeout=10.0):
    """
    One HTTP request. Returns dict:
      {ok, status, ttfb, total, server, error, ip}
    """
    result = {
        "ok": False,
        "status": 0,
        "ttfb": 0.0,
        "total": 0.0,
        "server": "",
        "error": "",
        "ip": "",
    }

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        result["error"] = "invalid URL"
        return result

    # resolve IP for reporting
    try:
        result["ip"] = socket.gethostbyname(host)
    except socket.gaierror:
        result["error"] = "DNS resolution failed"
        return result

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ttfb = time.time() - t0
            body = r.read()
            total = time.time() - t0
            result["ok"] = True
            result["status"] = r.status
            result["ttfb"] = ttfb
            result["total"] = total
            result["server"] = r.headers.get("Server", "")
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["total"] = time.time() - t0
        result["ttfb"] = result["total"]
        result["server"] = e.headers.get("Server", "") if e.headers else ""
        result["error"] = f"HTTP {e.code}"
        # 5xx = server side, 4xx = client side
        if 500 <= e.code < 600:
            result["error"] += " (server issue)"
    except urllib.error.URLError as e:
        result["total"] = time.time() - t0
        result["error"] = f"unreachable: {e.reason}"
    except socket.timeout:
        result["total"] = time.time() - t0
        result["error"] = "timeout"
    except Exception as e:
        result["total"] = time.time() - t0
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def classify(r):
    """
    Human verdict.
    """
    if r["error"] and not r["status"]:
        if "timeout" in r["error"].lower():
            return "🔴 DOWN (timeout)"
        if "dns" in r["error"].lower():
            return "🔴 DNS FAIL"
        return f"🔴 DOWN ({r['error']})"

    if r["status"] >= 500:
        return f"🟠 SERVER ERROR ({r['status']})"

    if r["status"] >= 400:
        return f"🟡 CLIENT ERROR ({r['status']})"

    ttfb_ms = r["ttfb"] * 1000
    if ttfb_ms < 300:
        return "🟢 HEALTHY"
    if ttfb_ms < 1000:
        return "🟢 OK (moderate)"
    if ttfb_ms < 3000:
        return f"🟡 SLOW ({ttfb_ms:.0f}ms)"
    return f"🟠 VERY SLOW ({ttfb_ms:.0f}ms) — possible overload"


def format_result(url, results):
    """Format multi-run report."""
    n = len(results)
    ok_n = sum(1 for r in results if r["ok"])
    ttfb_vals = [r["ttfb"] for r in results if r["ok"]]
    statuses = [r["status"] for r in results if r["status"]]

    lines = [f"🌐 {url}", ""]

    # per-run
    for i, r in enumerate(results, 1):
        verdict = classify(r)
        lines.append(f"  Run {i}: {verdict}")
        if r["ip"]:
            lines.append(f"         IP: {r['ip']}")
        if r["server"]:
            lines.append(f"         Server: {r['server']}")
        if r["ok"] or r["status"]:
            lines.append(f"         TTFB: {r['ttfb']*1000:.0f}ms  Total: {r['total']*1000:.0f}ms")
        if r["error"]:
            lines.append(f"         Error: {r['error']}")
        lines.append("")

    # summary
    if n > 1:
        lines.append("─" * 40)
        lines.append(f"Summary ({ok_n}/{n} ok)")
        if ttfb_vals:
            lines.append(f"  TTFB min/avg/max: "
                         f"{min(ttfb_vals)*1000:.0f} / "
                         f"{statistics.mean(ttfb_vals)*1000:.0f} / "
                         f"{max(ttfb_vals)*1000:.0f} ms")
        if statuses:
            from collections import Counter
            c = Counter(statuses)
            lines.append(f"  Statuses: " + ", ".join(f"{k}×{v}" for k, v in c.items()))

    return "\n".join(lines)


def check_url(url, count=1, interval=1.0, timeout=10.0):
    """Blocking multi-run checker. Returns list of result dicts."""
    results = []
    for i in range(count):
        results.append(check_once(url, timeout))
        if i < count - 1:
            time.sleep(interval)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=10.0)
    a = ap.parse_args()

    url = a.url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    results = check_url(url, a.count, a.interval, a.timeout)
    print(format_result(url, results))


if __name__ == "__main__":
    main()
