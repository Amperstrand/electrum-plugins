"""
Version information for the CLTV Plugin.

Provides git commit hash and date for UI display,
allowing easy verification that the correct version is running.
"""

import subprocess
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime


def get_plugin_dir() -> Path:
    """Get the plugin directory path."""
    return Path(__file__).parent.parent


def get_git_info() -> Tuple[str, str, str]:
    """
    Get git commit information for the plugin.
    
    Returns:
        Tuple of (commit_hash_short, commit_date, commit_message)
        Returns ('unknown', 'unknown', '') if git info unavailable
    """
    plugin_dir = get_plugin_dir()
    
    try:
        # Get short commit hash
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=plugin_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        commit_hash = result.stdout.strip() if result.returncode == 0 else 'unknown'
        
        # Get commit date
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            cwd=plugin_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse and format the date nicely
            date_str = result.stdout.strip()
            try:
                dt = datetime.strptime(date_str[:19], '%Y-%m-%d %H:%M:%S')
                commit_date = dt.strftime('%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                commit_date = date_str[:16] if date_str else 'unknown'
        else:
            commit_date = 'unknown'
        
        # Get commit message (first line)
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%s'],
            cwd=plugin_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        commit_msg = result.stdout.strip()[:50] if result.returncode == 0 else ''
        
        return commit_hash, commit_date, commit_msg
        
    except Exception as e:
        return 'unknown', 'unknown', str(e)[:30]


def get_version_string() -> str:
    """
    Get a formatted version string for UI display.
    
    Returns:
        String like "v3.1.0 (abc1234 @ 2025-11-29 10:30)"
    """
    from . import __version__
    
    commit_hash, commit_date, _ = get_git_info()
    
    if commit_hash != 'unknown':
        return f"v{__version__} ({commit_hash} @ {commit_date})"
    else:
        return f"v{__version__}"


def get_version_dict() -> dict:
    """
    Get version info as a dictionary.
    
    Returns:
        Dict with version, commit_hash, commit_date, commit_message
    """
    from . import __version__
    
    commit_hash, commit_date, commit_msg = get_git_info()
    
    return {
        'version': __version__,
        'commit_hash': commit_hash,
        'commit_date': commit_date,
        'commit_message': commit_msg,
        'display': get_version_string(),
    }


# Cache the version string on module load
_cached_version_string: Optional[str] = None

def get_cached_version_string() -> str:
    """Get cached version string (computed once at startup)."""
    global _cached_version_string
    if _cached_version_string is None:
        _cached_version_string = get_version_string()
    return _cached_version_string

