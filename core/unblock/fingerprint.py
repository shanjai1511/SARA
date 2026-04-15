"""
Browser fingerprint rotation for anti-bot bypass.

Provides realistic HTTP header sets matching specific Chrome / Firefox / Edge /
Safari versions on Windows, macOS, and Linux.  Rotating through these makes
each request look like a different real user rather than a constant bot.

What makes a fingerprint realistic:
  - User-Agent matches the browser version exactly
  - Accept headers match what that browser version sends
  - sec-ch-ua / sec-ch-ua-platform are consistent with the UA
  - sec-fetch-* headers are set correctly (bots typically omit these)
  - Accept-Encoding includes modern algorithms (br, zstd for Chrome 120+)
  - Header order matches the browser's canonical order (some WAFs check this)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BrowserProfile:
    name: str
    user_agent: str
    # Header values (not including User-Agent — added separately to preserve order)
    accept: str
    accept_language: str
    accept_encoding: str
    extra: Dict[str, str] = field(default_factory=dict)
    # curl_cffi impersonation target (empty = not supported)
    impersonate: str = ""

    def to_headers(
        self,
        referer: Optional[str] = None,
        extra_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build ordered header dict that matches how the browser sends them."""
        h: Dict[str, str] = {
            "User-Agent":        self.user_agent,
            "Accept":            self.accept,
            "Accept-Language":   self.accept_language,
            "Accept-Encoding":   self.accept_encoding,
        }
        if referer:
            h["Referer"] = referer
        h.update(self.extra)
        if referer and "sec-fetch-site" in h:
            h["sec-fetch-site"] = "same-origin"
        if extra_override:
            h.update(extra_override)
        return h


# ---------------------------------------------------------------------------
# Profile library — each entry is a verified real-browser header set
# ---------------------------------------------------------------------------

_PROFILES: List[BrowserProfile] = [

    BrowserProfile(
        name="Chrome 124 / Windows",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        accept=(
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="chrome124",
        extra={
            "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest":     "document",
            "sec-fetch-mode":     "navigate",
            "sec-fetch-site":     "none",
            "sec-fetch-user":     "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Chrome 124 / macOS",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        accept=(
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="chrome124",
        extra={
            "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest":     "document",
            "sec-fetch-mode":     "navigate",
            "sec-fetch-site":     "none",
            "sec-fetch-user":     "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Chrome 120 / Linux",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        accept=(
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="chrome120",
        extra={
            "sec-ch-ua":          '"Chromium";v="120", "Google Chrome";v="120", "Not-A.Brand";v="24"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest":     "document",
            "sec-fetch-mode":     "navigate",
            "sec-fetch-site":     "none",
            "sec-fetch-user":     "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Firefox 125 / Windows",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        accept_language="en-US,en;q=0.5",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="firefox120",
        extra={
            "sec-fetch-dest":  "document",
            "sec-fetch-mode":  "navigate",
            "sec-fetch-site":  "none",
            "sec-fetch-user":  "?1",
            "Upgrade-Insecure-Requests": "1",
            "TE":              "trailers",
        },
    ),

    BrowserProfile(
        name="Firefox 125 / macOS",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        accept_language="en-US,en;q=0.5",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="firefox120",
        extra={
            "sec-fetch-dest":  "document",
            "sec-fetch-mode":  "navigate",
            "sec-fetch-site":  "none",
            "sec-fetch-user":  "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Edge 124 / Windows",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        ),
        accept=(
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="chrome124",
        extra={
            "sec-ch-ua":          '"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest":     "document",
            "sec-fetch-mode":     "navigate",
            "sec-fetch-site":     "none",
            "sec-fetch-user":     "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Safari 17 / macOS",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.4.1 Safari/605.1.15"
        ),
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        impersonate="safari17_0",
        extra={
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "Upgrade-Insecure-Requests": "1",
        },
    ),

    BrowserProfile(
        name="Chrome 124 / Android",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.6367.82 Mobile Safari/537.36"
        ),
        accept=(
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br, zstd",
        impersonate="chrome124",
        extra={
            "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile":   "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-dest":     "document",
            "sec-fetch-mode":     "navigate",
            "sec-fetch-site":     "none",
            "sec-fetch-user":     "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
]


def get_random_profile() -> BrowserProfile:
    """Return a random browser profile."""
    return random.choice(_PROFILES)


def get_profile_for_domain(domain: str) -> BrowserProfile:
    """
    Return a deterministic profile for a domain (consistent within a session,
    different across domains — avoids rotating UA mid-session for the same site).
    """
    import hashlib
    idx = int(hashlib.md5(domain.encode()).hexdigest(), 16) % len(_PROFILES)
    return _PROFILES[idx]


def rotate_profile(exclude: Optional[BrowserProfile] = None) -> BrowserProfile:
    """Return a random profile that is different from the currently used one."""
    candidates = [p for p in _PROFILES if p is not exclude]
    return random.choice(candidates) if candidates else random.choice(_PROFILES)
