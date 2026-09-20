"""Shared User-Agent string for anything that talks to a real website —
web_fetch/web_search (talaria/tools/web.py) and the browser tools
(talaria/tools/browser.py) both use this, so they present as the same
ordinary desktop Chrome rather than two different Talaria-specific
fingerprints that would each need updating separately.
"""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
