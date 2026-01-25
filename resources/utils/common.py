import os
import re
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import urllib.request
from contextlib import contextmanager
import threading
import sqlite3

ADDON = xbmcaddon.Addon()


def db_exec(db_name=None, query="", params=None):
    if params is None:
        params = ()
    elif not isinstance(params, (tuple, list)):
        # Automatically wrap single values in a tuple for sqlite3
        params = (params,)

    # Safety check: Match '?' placeholders with param count
    placeholder_count = query.count("?")
    if placeholder_count != len(params):
        log(f"[db_exec] Parameter mismatch: Query has {placeholder_count} placeholders but {len(params)} params were provided.", xbmc.LOGERROR)
        return None

    db_dir = xbmcvfs.translatePath("special://profile/Database/")
    
    # 1. Regex to match the DB name (case-insensitive)
    pattern = re.compile(f"^{db_name}.*\\.db$", re.IGNORECASE)
    
    # 2. List and SORT the files so the highest number (latest version) is at the end
    try:
        files = [f for f in os.listdir(db_dir) if pattern.match(f)]
        files.sort() # Alphabetical sort: TV45.db, TV46.db...
    except Exception as e:
        log(f"[db_exec] Error listing directory {db_dir}: {str(e)}", xbmc.LOGERROR)
        return None

    if not files:
        log(f"[db_exec] No database file found for name [{db_name}]", xbmc.LOGERROR)
        return None

    path = os.path.join(db_dir, files[-1])

    try:
        # Use 'with' for the connection to handle transactions
        with sqlite3.connect(path) as conn:
            conn.set_trace_callback(log)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.set_trace_callback(None)

            # If it's a SELECT query, return the results
            if query.strip().upper().startswith("SELECT"):
                log("[db_exec] Fetching data from DB...")
                rows = cursor.fetchall()
                if rows:
                    return [dict(row) for row in rows]
                else:
                    log("[db_exec] No data to return for SELECT...")
                    return []
            
            # For DELETE/UPDATE/INSERT, commit is handled by the 'with' block
            conn.commit()
            log(f"[db_exec] Query executed. Affected rows: {cursor.rowcount}")
            return cursor.rowcount

    except Exception as e:
        log(f"[db_exec] Error executing query on {path}: {str(e)}", xbmc.LOGERROR)
        return None


def log(message, level=xbmc.LOGINFO):
    # Look for presence of password in the message
    password = get_setting("password")
    if password in message:
        message = message.replace(password, "********")

    # Also do a generic check for 'password=' in string - replace any word that follows the '=' with '********'
    if "password=" in message:
        message = re.sub(r"password=\w+", "password=********", message)

    xbmc.log(f"[script.iptv.xtream-to-m3u] {message}", level)


@contextmanager
def busy_dialog(caller=None, active=True):
    if active:
        xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
        try:
            yield
        finally:
            xbmc.executebuiltin("Dialog.Close(busydialognocancel)")
    else:
        yield

def get_setting(key, window=True):
    """
    Returns the value of a setting in the following priority order:
    - from the ADDON WINDOW (session memory) - this is populated by python code and does not contain "fresh" UI values
    - from the ADDON (disk) - does not contain "fresh" UI values
    """
    if window:
        WINDOW = xbmcgui.Window(10000)
        session_value = WINDOW.getProperty(f"script.iptv.xtream-to-m3u.{key}")
    else:
        session_value = None
    disk_value = ADDON.getSetting(key)

    if session_value and session_value != disk_value:
        return session_value
    else:
        return disk_value


def set_setting(key, value, addon=True):
    WINDOW = xbmcgui.Window(10000)
    WINDOW.setProperty(f"script.iptv.xtream-to-m3u.{key}", value)
    if addon:
        ADDON.setSetting(key, value)  # This won't be save until user hits OK button


def make_request(api_action=None, timeout=10):
    # Test provider connection
    api_url = get_api_url()
    if not api_url:
        return

    if api_action:
        api_url += f"&action={api_action}"

    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})

    # Log the request URL with masked password
    log(f"Making HTTP request: {api_url}")

    # Enforce strict timeout by running in a separate thread
    # This is necessary because socket timeouts on Windows may not affect DNS resolution or multiple IP retries
    result = [None]
    error = [None]

    def _request_worker():
        try:
            # We still use a socket timeout for the internal operation
            # This helps the thread eventually die if it hangs
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result[0] = response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_request_worker)
    t.start()
    t.join(timeout=timeout + 0.1)  # Strict wall-clock timeout

    if t.is_alive():
        raise TimeoutError(f"Connection timed out ({timeout}s timeout)")

    if error[0]:
        raise error[0]

    return result[0]


def get_api_url():
    host = get_setting("xtream_host").rstrip("/")
    port = get_setting("xtream_port")
    user = get_setting("username")
    password = get_setting("password")

    # Check if the host is a valid URL
    is_valid_url = re.match(r"^https?://", host)

    if not host or not user or not password or not is_valid_url:
        log(
            f"Missing account details for API URL: host: {host}, port: {port}, user: {user}, password: {password}",
            xbmc.LOGERROR,
        )
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "Missing or invalid IPTV Provider account details.\nPlease complete and save them first.",
        )
        return None

    return f"{host}:{port}/player_api.php?username={user}&password={password}"


def get_m3u_file_path():
    from .pvr_utils import check_pvr

    if not check_pvr():
        return None

    m3u_path = get_setting("m3u_path").strip()
    pvr_instance_name = get_setting("pvr_instance_name").strip()

    if not m3u_path:
        m3u_path = "special://home/userdata/playlists"

    # Normalize path by translating special:// to absolute native paths
    full_path = xbmcvfs.translatePath(m3u_path)

    # Convert PVR instance name to lower-kebab case
    pvr_instance_name = pvr_instance_name.lower().replace(" ", "-")

    m3u_file_path = os.path.join(full_path, f"{pvr_instance_name}.m3u8")
    return m3u_file_path
