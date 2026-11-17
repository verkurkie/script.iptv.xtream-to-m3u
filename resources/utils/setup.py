import xbmc
import xbmcgui
from urllib.parse import urlparse

from .common import log, get_setting, set_setting
from .provider_utils import test_provider, get_iptv_data
from .pvr_utils import select_pvr_instance, sync_to_pvr
from .xtream_utils import select_categories


def port_check(port):
    return port and port.isdigit() and int(port) >= 1 and int(port) <= 65535


def host_check(host):
    host_no_port = ":".join(host.rsplit(":"))
    parsed_url = urlparse(host_no_port)

    return host and parsed_url.scheme and parsed_url.netloc


def setup_provider(host, port, user, password):
    dialog = xbmcgui.Dialog()

    host = dialog.input(
        "Enter Xtream host", defaultt=host or "http://", type=xbmcgui.INPUT_ALPHANUM
    )
    set_setting("xtream_host", host)

    port = dialog.input(
        "Enter Xtream port", defaultt=port or "80", type=xbmcgui.INPUT_NUMERIC
    )
    set_setting("xtream_port", port)

    user = dialog.input(
        "Enter Xtream username", defaultt=user or "", type=xbmcgui.INPUT_ALPHANUM
    )
    set_setting("username", user)

    password = dialog.input(
        "Enter Xtream password",
        defaultt=password or "",
        type=xbmcgui.INPUT_ALPHANUM,
        option=xbmcgui.ALPHANUM_HIDE_INPUT,
    )
    set_setting("password", password)

    if not host or not port or not user or not password:
        return False

    # Test the IPTV provider
    provider_info = test_provider()

    if not provider_info or not provider_info.get("user_info", None):
        return False

    return True


def first_setup(first_try=True, force_sync=False):
    """
    Collect any missing provider, PVR instance, or category settings, then sync the PVR.
    """
    # Only get values that are already in the user's addon data
    host = get_setting("xtream_host", window=False) or "http://"
    port = get_setting("xtream_port", window=False) or None
    user = get_setting("username", window=False) or None
    password = get_setting("password", window=False) or None
    pvr_instance_id = get_setting("pvr_instance_id", window=False) or None
    needs_provider = not (host and host != "http://" and port and user and password)
    needs_pvr_instance = not pvr_instance_id
    needs_categories = not (
        get_setting("user_categories_ids", window=False) or ""
    ).strip()

    if not (needs_provider or needs_pvr_instance or needs_categories or force_sync):
        return True

    log("[first_setup] starting first-time setup...")
    if first_try:
        xbmcgui.Dialog().ok(
            "First-time Setup",
            "Please provide the requested info in the next few steps.",
        )

    result = True
    result_msg = ""
    provider_updated = False

    if needs_provider:
        if setup_provider(host, port, user, password):
            provider_updated = True
        else:
            result_msg = (
                "Invalid Xtream info - needs a valid host, port, username and password"
            )
            result = False

    if result and needs_pvr_instance:
        selected = select_pvr_instance(sync=False)
        if selected and selected.get("id", None):
            pvr_instance_id = selected.get("id", None)
            set_setting("pvr_instance_id", selected.get("id", None))
            set_setting("pvr_instance_name", selected.get("name", None))
        else:
            result_msg = "No PVR instance selected"
            result = False

    if result and (needs_categories or provider_updated):
        live_categories, live_streams = get_iptv_data(force=provider_updated)
        if not live_categories or not live_streams:
            result_msg = "Failed to fetch IPTV categories and streams"
            result = False

    if result and needs_categories:
        category_selection = select_categories(update_pvr=False)
        if not category_selection:
            result_msg = "No categories selected"
            result = False
        elif not category_selection[1]:
            result_msg = "Failed to save category selection"
            result = False
        elif not category_selection[0]:
            result_msg = "No categories selected"
            result = False

    if result and (
        needs_provider or needs_pvr_instance or needs_categories or force_sync
    ):
        if not sync_to_pvr():
            result_msg = "Failed to configure the selected PVR instance"
            result = False

    if not result:
        log(f"[first_setup] first-time setup failed! {result_msg}", xbmc.LOGERROR)
        if xbmcgui.Dialog().yesno(
            "First-time Setup failed!", result_msg + "\n\nDo you want to try again?"
        ):
            return first_setup(first_try=False, force_sync=True)

        return False

    return True
