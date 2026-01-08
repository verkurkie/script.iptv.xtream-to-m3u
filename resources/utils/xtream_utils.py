import os
import json
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

from .common import log
from .m3u_utils import make_playlist
from .provider_utils import get_live_categories

ADDON = xbmcaddon.Addon()


def select_categories():
    try:
        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        input_path = os.path.join(profile_path, "live_categories.json")
        selected_ids_path = os.path.join(profile_path, "selected_categories.json")

        # Get categories - fetch from provider if needed
        if not xbmcvfs.exists(input_path):
            xbmcgui.Dialog().ok("Xtream to M3U", "Fetching categories from provider...")
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

        # 4. Save Results
        # Save to JSON (for persistent storage)
        try:
            with xbmcvfs.File(selected_ids_path, "w") as f:
                f.write(json.dumps(final_ids))

            log(f"select_categories: Successfully saved {len(final_ids)} IDs to JSON")

        except Exception as e:
            log(f"Failed to save selected_categories.json: {str(e)}")

        # Update Settings (For summary and backup)
        if not final_ids:
            ADDON.setSetting("user_categories_ids", "All")
            summary = "All Categories"
            log("select_categories: No IDs selected, resetting to All Categories")
        else:
            ADDON.setSetting("user_categories_ids", ",".join(final_ids))
            id_to_name = {str(c["category_id"]): c["category_name"] for c in categories}
            selected_names = [id_to_name.get(cid, "Unknown") for cid in final_ids]

            if len(selected_names) <= 3:
                summary = ", ".join(selected_names)
            else:
                summary = f"{len(selected_names)} Categories"

        # Force update the summary setting
        ADDON.setSetting("user_categories", summary)
        log(f"Settings Summary forced to: {summary}")

        # Update the playlist with the selected IDs (only if the selection changed)
        if final_ids != current_selected:
            make_playlist(final_ids)

        return final_ids, True  # Return success tuple matching old signature

    except Exception as e:
        log(f"Unexpected error in select_categories: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"An unexpected error occurred:\n{str(e)}"
        )
        return [], False
