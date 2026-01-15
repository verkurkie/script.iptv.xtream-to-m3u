import os
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import json

from .common import log, busy_dialog, make_request

ADDON = xbmcaddon.Addon()


def test_provider(dialog=False):
    if dialog:
        xbmcgui.Dialog().notification(
            "IPTV Provider", "Testing connection...", time=500, sound=False
        )

    with busy_dialog():
        try:
            data = make_request(timeout=5)

            if dialog:
                xbmcgui.Dialog().ok(
                    "IPTV Provider Test passed!", "Connection test was successful!"
                )

        except Exception as e:
            log(
                f"[test_provider] failed to test IPTV Provider: {str(e)}", xbmc.LOGERROR
            )
            if dialog:
                xbmcgui.Dialog().ok("IPTV Provider Test failed!", str(e))
            return {"status": "error", "expiry": "0", "user_info": {}}

        return json.loads(data)


def get_iptv_data(force=False):
    success = False

    xbmcgui.Dialog().notification(
        "Xtream to M3U",
        "Fetching live categories & streams...",
        time=500,
        sound=False,
    )

    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")

    with busy_dialog("get_iptv_data"):
        if not force:
            live_categories = (
                json.load(xbmcvfs.File(live_categories_path))
                if xbmcvfs.exists(live_categories_path)
                else get_live_categories()
            )
        else:
            live_categories = get_live_categories()

        if live_categories:
            if not force:
                live_streams = (
                    json.load(xbmcvfs.File(live_streams_path))
                    if xbmcvfs.exists(live_streams_path)
                    else get_live_streams()
                )
            else:
                live_streams = get_live_streams()

            if live_streams:
                success = True

    if success:
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "Successfully fetched [{}] Categories and [{}] Streams".format(
                len(live_categories), len(live_streams)
            ),
        )
        return live_categories, live_streams
    else:
        xbmcgui.Dialog().ok("Xtream to M3U", "Failed to fetch Categories and Streams")
        return None, None


def get_live_categories():
    try:
        raw_data = make_request(api_action="get_live_categories", timeout=30)

        # Parse JSON and count items
        categories = json.loads(raw_data)
        item_count = len(categories) if isinstance(categories, list) else 0

        log(f"[get_live_categories] successfully fetched {item_count} live categories")

        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        output_path = os.path.join(profile_path, "live_categories.json")

        # Save in pretty format
        with xbmcvfs.File(output_path, "w") as f:
            f.write(json.dumps(categories, indent=2))

        log(f"[get_live_categories] live categories saved to: {output_path}")

        return categories

    except Exception as e:
        log(
            f"[get_live_categories] failed to fetch xtream live categories: {str(e)}",
            xbmc.LOGERROR,
        )


def get_live_streams():
    try:
        raw_data = make_request(api_action="get_live_streams", timeout=30)

        # Parse JSON and count items
        streams = json.loads(raw_data)
        item_count = len(streams) if isinstance(streams, list) else 0

        log(f"[get_live_streams] successfully fetched {item_count} live streams")

        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        output_path = os.path.join(profile_path, "live_streams.json")

        # Save in pretty format
        with xbmcvfs.File(output_path, "w") as f:
            f.write(json.dumps(streams, indent=2))

        log(f"[get_live_streams] live streams saved to: {output_path}")

        return streams

    except Exception as e:
        log(
            f"[get_live_streams] failed to fetch xtream live streams: {str(e)}",
            xbmc.LOGERROR,
        )
