import os
import json
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

from .common import log, set_setting, get_setting
from .m3u_utils import make_playlist
from .provider_utils import get_live_categories
from .pvr_utils import reset_pvr, check_pvr

ADDON = xbmcaddon.Addon()


def select_categories(update_pvr=True):
    log("[select_categories] starting category selection process.")
    if not check_pvr():
        return

    try:
        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            log(f"[select_categories] creating profile directory [{profile_path}]")
            xbmcvfs.mkdir(profile_path)

        log(f"[select_categories] checking for live categories in [{profile_path}]")
        log(
            f"[select_categories] files in [{profile_path}]: {os.listdir(profile_path)}"
        )

        input_path = os.path.join(profile_path, "live_categories.json")
        selected_ids_path = os.path.join(profile_path, "selected_categories.json")

        pDialog = xbmcgui.DialogProgress()
        if not xbmcvfs.exists(input_path):
            xbmcgui.Dialog().notification(
                "Xtream to M3U", "Fetching categories from provider..."
            )
            categories = get_live_categories()
            if not categories:
                return
        else:
            with xbmcvfs.File(input_path, "r") as f:
                categories = json.loads(f.read())

        if not categories or not isinstance(categories, list):
            log("[select_categories] no categories found in live_categories.json")
            return

        categories.sort(key=lambda x: x.get("category_name", ""))

        # 2. Load Selected IDs (Source of Truth is now JSON to avoid Settings Dialog conflicts)
        current_selected = None
        if xbmcvfs.exists(selected_ids_path):
            try:
                with xbmcvfs.File(selected_ids_path, "r") as f:
                    current_selected = json.loads(f.read())
                log(f"[select_categories] loaded {len(current_selected)} IDs from JSON")
            except Exception as e:
                log(
                    f"[select_categories] error reading selected_categories.json: {str(e)}"
                )

        # Fallback to settings ONLY if JSON was never found/loaded
        if current_selected is None:
            current_ids_raw = get_setting("user_categories_ids")
            log(
                f"[select_categories] no JSON found, falling back to settings. Raw: '{current_ids_raw}'"
            )
            if current_ids_raw and current_ids_raw not in ["All", "0", "None"]:
                current_selected = [
                    s.strip() for s in current_ids_raw.split(",") if s.strip()
                ]
            else:
                current_selected = []

        log(
            f"[select_categories] opening Category Selection Window. Pre-selected count: {len(current_selected)}"
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
            log("[select_categories] category selection cancelled by user.")
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
            log("[select_categories] empty selection blocked.")
            return

        # 4. Save Results
        # Save to JSON (for persistent storage)
        try:
            with xbmcvfs.File(selected_ids_path, "w") as f:
                f.write(json.dumps(final_ids))

            log(f"[select_categories] successfully saved {len(final_ids)} IDs to JSON")

        except Exception as e:
            log(
                f"[select_categories] failed to save selected_categories.json: {str(e)}"
            )

        # Update Settings (For summary and backup)
        set_setting("user_categories_ids", ",".join(final_ids))

        # Update the playlist with the selected IDs (only if the selection changed)
        if final_ids != current_selected and update_pvr:
            pDialog.create(
                heading="Xtream to M3U", message="Updating playlist and PVR ..."
            )
            make_playlist(final_ids)

            # Pass final_ids to reset_pvr to ensure it uses the latest selection!
            pDialog.update(percent=50, message="Updating PVR ...")
            if reset_pvr(silent=True, categories=final_ids):
                pDialog.close()
                xbmcgui.Dialog().ok(
                    "Xtream to M3U",
                    f"Updated playlist to [{len(final_ids)}] categories\n\nPVR reload triggered.",
                )
            else:
                pDialog.close()
                xbmcgui.Dialog().ok(
                    "Xtream to M3U",
                    f"Updated playlist to [{len(final_ids)}] categories\n\nPVR reload failed.",
                )

        return final_ids, True  # Return success tuple matching old signature

    except Exception as e:
        log(f"[select_categories] unexpected error: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"An unexpected error occurred:\n{str(e)}"
        )
        return [], False
