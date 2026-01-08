import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import sys
import os
import json
from datetime import datetime

from resources.utils.common import log, system_check
from resources.utils.m3u_utils import make_playlist
from resources.utils.provider_utils import get_live_categories
from resources.utils.pvr_utils import setup_pvr, sync_to_pvr, select_pvr_instance
from resources.utils.xtream_utils import select_categories

# Initialize the addon object
ADDON = xbmcaddon.Addon()
WINDOW = xbmcgui.Window(10000)  # Global Home window for shared memory


def init():
    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

    # Optional: Prime shared memory with current disk values on startup
    # This ensures that properties exist even if no buttons have been clicked yet.
    # Note: We only do this if the property isn't already set to avoid overwriting "dirty" UI state
    # when init() is called multiple times in one session.
    for sid in [
        "pvr_instance_id",
        "pvr_instance_name",
        "pvr_status",
        "user_categories",
        "user_categories_ids",
    ]:
        if not WINDOW.getProperty(f"script.iptv.xtream-to-m3u.{sid}"):
            WINDOW.setProperty(
                f"script.iptv.xtream-to-m3u.{sid}", ADDON.getSetting(sid)
            )

    try:
        # Check if there are live categories, check the file's last modified time and set the category status (number of categories)
        live_categories_path = os.path.join(user_profile_path, "live_categories.json")
        category_status = ""

        if xbmcvfs.exists(live_categories_path):
            with xbmcvfs.File(live_categories_path, "r") as f:
                categories = json.loads(f.read())

            if not categories or not isinstance(categories, list):
                category_status = f"No categories found in {live_categories_path}"
            else:
                item_count = len(categories)
                last_modified = xbmcvfs.Stat(live_categories_path).st_mtime()
                category_status = f"[{item_count}] categories ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})"

        if category_status != "":
            ADDON.setSetting("category_status", category_status)

        # Check playlist status
        user_home_path = xbmcvfs.translatePath("special://home")
        playlists_path = os.path.join(user_home_path, "userdata", "playlists")
        m3u_file_path = os.path.join(playlists_path, ADDON.getSetting("m3u_filename"))

        if xbmcvfs.exists(m3u_file_path):
            last_modified = xbmcvfs.Stat(m3u_file_path).st_mtime()
            # Get the channel count from the m3u file
            channel_count = 0
            with xbmcvfs.File(m3u_file_path, "r") as f:
                content = f.read()
                channel_count = content.count("#EXTINF")

            ADDON.setSetting(
                "playlist_status",
                f"[{channel_count}] channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )

    except Exception as e:
        log(f"Error in init: {str(e)}", xbmc.LOGERROR)


def main():
    log("SCRIPT STARTED")
    log(f"Arguments: {str(sys.argv)}")

    # Run user actions
    if len(sys.argv) > 1 and any("system_check" in arg for arg in sys.argv):
        system_check()
    elif len(sys.argv) > 1 and any("get_live_categories" in arg for arg in sys.argv):
        get_live_categories()
    elif len(sys.argv) > 1 and any("select_categories" in arg for arg in sys.argv):
        # Show the category select dialog & update user settings
        select_categories()
    elif len(sys.argv) > 1 and any("make_playlist" in arg for arg in sys.argv):
        make_playlist()
    elif len(sys.argv) > 1 and any("setup_pvr" in arg for arg in sys.argv):
        setup_pvr()
    elif len(sys.argv) > 1 and any("select_pvr_instance" in arg for arg in sys.argv):
        select_pvr_instance()
    elif len(sys.argv) > 1 and any("sync_to_pvr" in arg for arg in sys.argv):
        sync_to_pvr()
    else:
        # Default behavior (e.g. running from service or manual trigger)
        ADDON.openSettings()


if __name__ == "__main__":
    main()
