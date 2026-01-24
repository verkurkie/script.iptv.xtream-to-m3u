import xbmcaddon
import sys

from resources.utils.cron_utils import manage_job
from resources.utils.common import log
from resources.utils.system_check import system_check
from resources.utils.setup import first_setup
from resources.utils.m3u_utils import make_playlist
from resources.utils.pvr_utils import (
    reset_pvr,
    setup_pvr,
    sync_to_pvr,
    select_pvr_instance,
)
from resources.utils.xtream_utils import select_categories
from resources.utils.provider_utils import test_provider, get_iptv_data

# Initialize the addon object
ADDON = xbmcaddon.Addon()


def main():
    log(f"XTREAM-TO-M3U - SCRIPT STARTED - arguments: [{str(sys.argv)}]")

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
    old_cron = ADDON.getSettingString("auto_refresh")

    first_setup_result = first_setup()

    if not first_setup_result:
        return

    # Mapping actions to their corresponding functions
    actions = {
        "auto_refresh": lambda: sync_to_pvr(cron=True),
        "system_checks": system_check,
        "test_provider": lambda: test_provider(dialog=True),
        "select_categories": select_categories,
        "setup_pvr": setup_pvr,
        "get_iptv_data": lambda: get_iptv_data(force=True),
        "reset_pvr": lambda: reset_pvr(pvr_instance_id=params.get("pvr_instance_id"), silent=False),
        "select_pvr_instance": select_pvr_instance,
        "make_playlist": lambda: make_playlist(silent=False),
        "sync_to_pvr": sync_to_pvr,
    }

    # Execute the action if it exists, otherwise open settings
    if action in actions:
        actions[action]()
    else:
        # Default behavior: open settings if no specific action
        ADDON.openSettings()

    # Final actions go here
    new_cron = ADDON.getSettingString("auto_refresh")
    if old_cron != new_cron:
        # Cron value has changed - update the cron job!
        manage_job(new_cron)

    return

if __name__ == "__main__":
    main()
