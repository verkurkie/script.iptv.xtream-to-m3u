import xbmc
import xbmcgui
from urllib.parse import urlparse

from .common import log, get_setting, set_setting
from .provider_utils import test_provider, get_iptv_data
from .pvr_utils import select_pvr_instance


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


def first_setup(first_try=True):
    """
    Run some checks to see if this is a first-time setup. If it is, perform the following steps:
    1. Ask the user for IPTV Provider info (host, port, username, password)
    2. Ask the user to select a PVR instance (and install IPTV Simple Client if not already installed)
    3. Fetch IPTV Channel categories & streams
    """
    # Only get values that are already in the user's addon data
    host = get_setting("xtream_host", window=False) or "http://"
    port = get_setting("xtream_port", window=False) or None
    user = get_setting("username", window=False) or None
    password = get_setting("password", window=False) or None
    pvr_instance_id = get_setting("pvr_instance_id", window=False) or None
    result = True

    if (
        not host
        or host == "http://"
        or not port
        or not user
        or not password
        or not pvr_instance_id
    ):
        log("[first_setup] starting first-time setup...")
        if first_try:
            xbmcgui.Dialog().ok(
                "First-time Setup",
                "Please provide the requested info in the next few steps.",
            )

        # Ask user for IPTV Provider info using xbmc dialog
        if not setup_provider(host, port, user, password):
            result_msg = (
                "Invalid Xtream info - needs a valid host, port, username and password"
            )
            result = False
        else:
            # Ask user for PVR instance info using xbmc dialog
            selected = select_pvr_instance(sync=False)
            if selected and selected.get("id", None):
                pvr_instance_id = selected.get("id", None)
                set_setting("pvr_instance_id", selected.get("id", None))
                set_setting("pvr_instance_name", selected.get("name", None))
            else:
                result_msg = "No PVR instance selected"
                result = False

        if not result:
            log(f"[first_setup] first-time setup failed! {result_msg}", xbmc.LOGERROR)
            if xbmcgui.Dialog().yesno(
                "First-time Setup failed!", result_msg + "\n\nDo you want to try again?"
            ):
                first_setup(first_try=False)

            return False

        # Got all the stuff! Let's get the live categories & streams
        get_iptv_data()

    return True
