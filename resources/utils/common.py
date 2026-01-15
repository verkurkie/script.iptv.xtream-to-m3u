import os
import re
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import urllib.request
import json
from datetime import datetime
from contextlib import contextmanager
import threading

ADDON = xbmcaddon.Addon()


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
def busy_dialog(caller=None):
    xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
    try:
        yield
    finally:
        xbmc.executebuiltin("Dialog.Close(busydialognocancel)")


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


def system_check():
    # Create a human-readable report for the text viewer
    report = []

    # Header
    report.append("SYSTEM STATUS REPORT")
    report.append("=" * 30)
    report.append("")

    # Helper to add colored lines (colors only the status tag)
    def add_line(label, status="ok", detail=""):
        color = "green" if status == "ok" else "red"

        # Color only the status part, wrapped in brackets for visibility
        colored_status = f"[[COLOR {color}]{status.upper()}[/COLOR]]"

        # Use a simpler layout that works better with proportional fonts
        report.append(f"{colored_status} {label}: {detail}")

    log("[system check] checking IPTV Provider...")
    from .provider_utils import test_provider

    data = test_provider()
    user_info = data.get("user_info", {})
    status = user_info.get("status", "Unknown")
    expiry = user_info.get("exp_date", None)

    # Format expiry (Xtream uses unix timestamp)
    if expiry:
        expiry_str = datetime.fromtimestamp(int(expiry)).strftime("%Y-%m-%d")
    else:
        expiry_str = "N/A"

    add_line(
        "Account status",
        "ok" if status == "Active" else "error",
        f"Expiry: {expiry_str}\n",
    )

    # Live categories & streams
    log("[system check] checking live categories & streams...")
    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")

    if xbmcvfs.exists(live_categories_path):
        last_modified = xbmcvfs.Stat(live_categories_path).st_mtime()
        with xbmcvfs.File(live_categories_path, "r") as f:
            categories = json.loads(f.read())

        if not categories or not isinstance(categories, list):
            add_line(
                "Categories",
                "error",
                f"0 items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
        else:
            item_count = len(categories)
            add_line(
                "Categories",
                "ok",
                f"{item_count} items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
    else:
        add_line("Categories", "error", "Count: 0")

    if xbmcvfs.exists(live_streams_path):
        last_modified = xbmcvfs.Stat(live_streams_path).st_mtime()

        with xbmcvfs.File(live_streams_path, "r") as f:
            streams = json.loads(f.read())

        if not streams or not isinstance(streams, list):
            add_line(
                "Streams",
                "error",
                f"0 items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
        else:
            item_count = len(streams)
            add_line(
                "Streams",
                "ok",
                f"{item_count} items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
    else:
        add_line("Streams", "error", "Count: 0")

    log("[system check] checking user selected categories...")

    # User selected categories
    user_categories_ids = get_setting("user_categories_ids") or None
    # Strip whitespace and split
    raw_ids = user_categories_ids.strip() if user_categories_ids else ""
    # Filter out empty strings from the list
    user_category_list = [i for i in raw_ids.split(",") if i]

    user_category_count = len(user_category_list)

    add_line(
        label="User Categories",
        status="ok" if user_category_count > 0 else "error",
        detail=f"{user_category_count} selected\n",
    )

    # IPTV Simple Client status
    log("[system check] checking PVR status...")
    try:
        # We use xbmcaddon.Addon just to check if it exists in the system
        # Note: This may fail if it's completely missing
        xbmcaddon.Addon("pvr.iptvsimple")

        # Check if it's enabled via JSON-RPC (and get version)
        rpc_query = {
            "jsonrpc": "2.0",
            "method": "Addons.GetAddonDetails",
            "params": {
                "addonid": "pvr.iptvsimple",
                "properties": ["enabled", "version"],
            },
            "id": 1,
        }

        response = xbmc.executeJSONRPC(json.dumps(rpc_query))
        result = json.loads(response)

        addon_data = result.get("result", {}).get("addon", {})
        is_enabled = addon_data.get("enabled", False)
        pvr_version = addon_data.get("version", "")
        add_line("PVR Client", "ok" if is_enabled else "error", f"v{pvr_version}")
        add_line(
            "PVR Instance",
            "ok" if get_setting("pvr_instance_id") != "" else "error",
            f"{get_setting('pvr_instance_name')} (ID:{get_setting('pvr_instance_id')})",
        )
    except RuntimeError:
        add_line("PVR Client", "error", "Not installed")

    # Playlist status
    log("[system check] checking playlist status...")
    m3u_file_path = get_m3u_file_path()

    if not m3u_file_path:
        return

    if xbmcvfs.exists(m3u_file_path):
        stat = xbmcvfs.Stat(m3u_file_path)
        last_modified = stat.st_mtime()

        content = ""
        f = xbmcvfs.File(m3u_file_path, "r")
        content = f.read()
        f.close()

        channel_count = content.count("#EXTINF")
        add_line(
            "Playlist",
            "ok",
            f"{channel_count} channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})\n",
        )
    else:
        add_line("Playlist", "error", "Count: 0\n")

    # Footer
    report.append("-" * 30)
    report.append("Addon settings:")

    # Dump Settings
    settings_dump = {
        "host": get_setting("xtream_host"),
        "port": get_setting("xtream_port"),
        "user": get_setting("username"),
        "password": "*******",
        "pvr": get_setting("pvr_instance_name"),
        "pvr_id": get_setting("pvr_instance_id"),
        "m3u": get_setting("m3u_path"),
        "categories": get_setting("user_categories_ids"),
    }
    report.append(json.dumps(settings_dump, indent=2))

    report_str = "\n".join(report)

    # Show results in a proper scrollable text viewer
    xbmcgui.Dialog().textviewer("System Status Report", report_str, True)
