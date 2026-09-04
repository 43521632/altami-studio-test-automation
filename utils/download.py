"""Download installer from Jfrog with caching."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import requests

from .config import get_app_version, get_platform, get_revision

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / "downloads"
CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_key(revision: str, platform: str) -> str:
    """Unique filename for cached installer."""
    return f"{revision}_{platform}"


def _get_cached_path(revision: str, platform: str) -> Path:
    """Path to cached installer file."""
    key = _get_cache_key(revision, platform)
    # Find any file starting with this key (we don't know extension)
    for f in CACHE_DIR.glob(f"{key}.*"):
        return f
    return CACHE_DIR / f"{key}.tmp"


def _get_auth() -> Optional[tuple]:
    """Return (user, password) from environment."""
    user = os.environ.get("CACHE_USER")
    password = os.environ.get("CACHE_PASSWORD")
    if user and password:
        return (user, password)
    return None


def _build_url(revision: str, version: str, platform: str) -> str:
    """Build JFrog download URL."""
    ext = ".exe" if "windows" in platform else ".deb"
    return (
        f"https://cache.altami.ru/artifactory/app-builds/altami/"
        f"{revision}/{platform}/AS_{version}_{revision}_{platform}{ext}"
    )


def download_installer(
    revision: Optional[str] = None,
    version: Optional[str] = None,
    platform: Optional[str] = None,
    force: bool = False,
) -> Path:
    """Download installer if not cached, return local path.

    Args:
        revision: build revision (default from config)
        version: app version (default from config)
        platform: platform string (default from config)
        force: re-download even if cached

    Returns:
        Path to downloaded installer file.
    """
    revision = revision or get_revision()
    version = version or get_app_version()
    platform = platform or get_platform()

    cached = _get_cached_path(revision, platform)
    if cached.exists() and not force:
        logger.info("Используем кэшированный установщик: %s", cached)
        return cached

    url = _build_url(revision, version, platform)
    logger.info("Скачиваем установщик: %s", url)

    auth = _get_auth()
    if not auth:
        logger.warning("Не заданы CACHE_USER/CACHE_PASSWORD — попытка без аутентификации")

    # Download with streaming
    response = requests.get(url, auth=auth, stream=True, timeout=300)
    if response.status_code != 200:
        raise RuntimeError(
            f"Не удалось скачать установщик: HTTP {response.status_code} {response.reason}\n"
            f"URL: {url}\n"
            f"Проверьте ревизию, версию и аутентификацию."
        )

    # Determine extension from URL or content-type
    ext = Path(url).suffix or ".exe"
    dest = CACHE_DIR / f"{_get_cache_key(revision, platform)}{ext}"

    # Write to temporary file first
    temp = dest.with_suffix(dest.suffix + ".part")
    total = 0
    with open(temp, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total += len(chunk)

    # Rename atomically
    temp.rename(dest)
    logger.info("Установщик сохранён: %s (%.2f MB)", dest, total / 1024 / 1024)
    return dest


def cleanup_old_cache(days: int = 7) -> None:
    """Remove cached files older than `days`."""
    import time

    now = time.time()
    cutoff = now - days * 86400
    for f in CACHE_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            logger.debug("Удалён старый кэш: %s", f)
