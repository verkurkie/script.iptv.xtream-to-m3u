import xbmcaddon
import sys

from resources.utils.common import log, system_check
from resources.utils.m3u_utils import make_playlist
from resources.utils.pvr_utils import (
    refresh_pvr,
    setup_pvr,
    sync_to_pvr,
    select_pvr_instance,
)
from resources.utils.xtream_utils import select_categories

# Initialize the addon object
ADDON = xbmcaddon.Addon()


def main():
    log("XTREAM-TO-M3U - SCRIPT STARTED")
    log(f"Arguments received: {str(sys.argv)}")

    # Parse arguments into a dictionary
    # Supports "RunScript(script.id, action=name, param=value)"
    params = {}
    for i, arg in enumerate(sys.argv[1:]):
        if "=" in arg:
            key, value = arg.split("=", 1)
            params[key.lower()] = value
        else:
            # First positional argument is treated as the action if not provided via action=
            if i == 0 and "action" not in params:
                params["action"] = arg

    action = params.get("action")

    if action == "system_checks":
        # Provide the user with system status dialog
        system_check()
    elif action == "select_categories":
        # Dialog for the user to select desired TV categories
        select_categories()
    elif action == "setup_pvr":
        # Checks if IPTV Simple Client is installed & enabled and will install/enable it if not
        # Also gets the version of the addon and updates the UI
        setup_pvr()
    elif action == "refresh_pvr":
        # Refreshes the user's PVR instance - can also be called by itself (i.e. keyboard shortcut)
        pvr_instance_id = params.get("pvr_instance_id", None)
        refresh_pvr(pvr_instance_id=pvr_instance_id, silent=False)
    elif action == "select_pvr_instance":
        # User selection of IPTV Simple Client instance
        select_pvr_instance()
    elif action == "make_playlist":
        # Configure the IPTV Simple Client instance with the playlist and EPG link
        make_playlist()
    elif action == "sync_to_pvr":
        # Configure the IPTV Simple Client instance with the playlist and EPG link
        sync_to_pvr()
    else:
        # Default behavior: open settings if no specific action
        ADDON.openSettings()


if __name__ == "__main__":
    main()
