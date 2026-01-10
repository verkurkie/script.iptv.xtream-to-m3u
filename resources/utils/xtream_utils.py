import os
import json
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

from .common import log
from .m3u_utils import make_playlist
from .provider_utils import get_live_categories
from .pvr_utils import refresh_pvr

ADDON = xbmcaddon.Addon()
WINDOW = xbmcgui.Window(10140)


def select_categories():
    log("select_categories: Starting category selection process.")
    try:
        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        input_path = os.path.join(profile_path, "live_categories.json")
        selected_ids_path = os.path.join(profile_path, "selected_categories.json")

        # Get categories - fetch from provider if needed
        if not xbmcvfs.exists(input_path):
            xbmcgui.Dialog().notification(
                "Xtream to M3U", "Fetching categories from provider..."
            )
            categories = get_live_categories()
        else:
            with xbmcvfs.File(input_path, "r") as f:
                categories = json.loads(f.read())

        if not categories or not isinstance(categories, list):
            log("No categories found in live_categories.json")
            return

        categories.sort(key=lambda x: x.get("category_name", ""))

        # 2. Load Selected IDs (Source of Truth is now JSON to avoid Settings Dialog conflicts)
        current_selected = None
        if xbmcvfs.exists(selected_ids_path):
            try:
                with xbmcvfs.File(selected_ids_path, "r") as f:
                    current_selected = json.loads(f.read())
                log(f"select_categories: Loaded {len(current_selected)} IDs from JSON")
            except Exception as e:
                log(f"Error reading selected_categories.json: {str(e)}")

        # Fallback to settings ONLY if JSON was never found/loaded
        if current_selected is None:
            current_ids_raw = ADDON.getSetting("user_categories_ids")
            log(
                f"select_categories: No JSON found, falling back to settings. Raw: '{current_ids_raw}'"
            )
            if current_ids_raw and current_ids_raw not in ["All", "0", "None"]:
                current_selected = [
                    s.strip() for s in current_ids_raw.split(",") if s.strip()
                ]
            else:
                current_selected = []

        log(
            f"Opening Category Selection Window. Pre-selected count: {len(current_selected)}"
        )

        # 3. Use xbmcgui.Dialog().multiselect
        # Sort categories by name for easier reading (already done above)

        # Prepare data for the native dialog
        list_items = [cat.get("category_name", "Unknown") for cat in categories]

        # Map current selected_ids to list indices
        preselect = []
        for idx, cat in enumerate(categories):
            if str(cat.get("category_id")) in current_selected:
                preselect.append(idx)

        # Show the Native MultiSelect Dialog
        # This guarantees 100% integration with the user's current skin
        dialog = xbmcgui.Dialog()
        selected_indices = dialog.multiselect(
            "Select Categories", list_items, preselect=preselect
        )

        # Handle Result
        if selected_indices is None:  # User cancelled
            log("Category selection cancelled by user.")
            return

        # Map indices back to IDs
        final_ids = []
        for idx in selected_indices:
            cat_id = str(categories[idx].get("category_id"))
            final_ids.append(cat_id)

        if len(final_ids) == 0:
            xbmcgui.Dialog().ok(
                "Xtream to M3U",
                "Requirement: You must select at least one category! Changes were not saved.",
            )
            log("select_categories: Empty selection blocked.")
            return

        # 4. Save Results
        # Save to JSON (for persistent storage)
        try:
            with xbmcvfs.File(selected_ids_path, "w") as f:
                f.write(json.dumps(final_ids))

            log(f"select_categories: Successfully saved {len(final_ids)} IDs to JSON")

        except Exception as e:
            log(f"Failed to save selected_categories.json: {str(e)}")

        # Update Settings (For summary and backup)
        ADDON.setSetting("user_categories_ids", ",".join(final_ids))
        WINDOW.setProperty(
            "script.iptv.xtream-to-m3u.user_categories_ids", ",".join(final_ids)
        )

        # Update the playlist with the selected IDs (only if the selection changed)
        if final_ids != current_selected:
            xbmcgui.Dialog().notification("Xtream to M3U", "Updating playlist...")
            make_playlist(final_ids)
            # Pass final_ids to refresh_pvr to ensure it uses the latest selection!
            if refresh_pvr(silent=True, categories=",".join(final_ids)):
                xbmcgui.Dialog().ok(
                    "Xtream to M3U",
                    f"Successfully updated to [{len(final_ids)}] categories\n\nPVR reload triggered.",
                )

        return final_ids, True  # Return success tuple matching old signature

    except Exception as e:
        log(f"Unexpected error in select_categories: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"An unexpected error occurred:\n{str(e)}"
        )
        return [], False
