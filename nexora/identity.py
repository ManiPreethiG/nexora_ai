"""Website Identity and Memory Namespace Resolver for Nexora AI.

Ensures that multiple audits of the same domain (regardless of protocol, www prefix,
or trailing slashes) resolve to a single stable identity and Hindsight memory bank.
"""

import re
import urllib.parse
from typing import Dict, Any


def normalize_url(url: str) -> str:
    """Normalize a URL to its canonical base representation for identity mapping."""
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip port if standard
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Normalize path (keep root as empty or specific path)
    path = parsed.path.rstrip("/")
    
    return f"{scheme}://{netloc}{path}"


def extract_domain(url: str) -> str:
    """Extract normalized base domain without www or protocol.
    
    e.g. 'https://www.example.com/path/' -> 'example.com'
         'http://example.com' -> 'example.com'
    """
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def derive_bank_id(domain_or_url: str) -> str:
    """Derive a stable, clean Hindsight bank_id for the website namespace.
    
    e.g. 'example.com' -> 'site_example_com'
         'https://sub.domain.org/' -> 'site_sub_domain_org'
    """
    domain = extract_domain(domain_or_url)
    if not domain:
        domain = "unknown"
    clean = re.sub(r"[^a-zA-Z0-9]", "_", domain).strip("_")
    return f"site_{clean}"


class WebsiteIdentity:
    """Stable website identity model representing a tracked property across audits."""

    def __init__(self, raw_url: str, brand_name: str | None = None, site_type: str | None = None):
        self.raw_url = raw_url
        self.domain = extract_domain(raw_url)
        self.normalized_url = normalize_url(raw_url)
        self.bank_id = derive_bank_id(self.domain)
        self.brand_name = brand_name
        self.site_type = site_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "normalized_url": self.normalized_url,
            "bank_id": self.bank_id,
            "brand_name": self.brand_name,
            "site_type": self.site_type,
        }

    def __repr__(self) -> str:
        return f"<WebsiteIdentity domain='{self.domain}' bank_id='{self.bank_id}'>"
