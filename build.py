import os
import zipfile
import xml.etree.ElementTree as ET
import argparse
import subprocess


def get_addon_info():
    tree = ET.parse("addon.xml")
    root = tree.getroot()
    return root.get("id"), root.get("version")


def update_addon_xml(new_version, dry_run=False):
    tree = ET.parse("addon.xml")
    root = tree.getroot()
    current_version = root.get("version")

    if current_version == new_version:
        print(f"addon.xml already at version {new_version}, skipping update.")
        return

    print(f"Updating addon.xml from {current_version} to {new_version}...")
    if dry_run:
        print("[DRY-RUN] Would update addon.xml version.")
        return

    root.set("version", new_version)
    tree.write("addon.xml", encoding="UTF-8", xml_declaration=True)


def update_changelog(new_version, dry_run=False):
    print(f"Updating changelog.txt for version {new_version}...")

    # Get all commits since last tag
    try:
        # Get the name of the last tag
        last_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        commit_range = f"{last_tag}..HEAD"
    except subprocess.CalledProcessError:
        # No tags found, get all commits
        commit_range = "HEAD"

    try:
        commits = subprocess.check_output(
            ["git", "log", commit_range, "--pretty=- %s"], text=True
        ).strip()
    except Exception:
        commits = "- Manual build/release"

    if not commits:
        commits = "- No changes recorded"

    new_entry = f"v{new_version}\n{commits}\n\n"

    if dry_run:
        print(f"[DRY-RUN] Would prepend to changelog.txt:\n{new_entry}")
        return

    content = ""
    if os.path.exists("changelog.txt"):
        with open("changelog.txt", "r") as f:
            content = f.read()

    # Ensure we don't duplicate the version if it's already there (e.g. from a failed run)
    if not content.startswith(f"v{new_version}"):
        with open("changelog.txt", "w") as f:
            f.write(new_entry + content)
    else:
        print(f"Changelog already has entry for {new_version}, skipping write.")


def build_zip(addon_id, version, dry_run=False):
    zip_name = f"{addon_id}-{version}.zip"

    # Files and directories to include as per RELEASE.md
    includes = ["addon.xml", "main.py", "resources", "changelog.txt", "README.md"]

    print(f"Building {zip_name}...")
    if dry_run:
        print(f"[DRY-RUN] Would create {zip_name} with files: {', '.join(includes)}")
        return

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item in includes:
            if not os.path.exists(item):
                print(f"Warning: {item} not found, skipping.")
                continue

            if os.path.isfile(item):
                zipf.write(item, arcname=os.path.join(addon_id, item))
            elif os.path.isdir(item):
                for root, dirs, files in os.walk(item):
                    if "__pycache__" in dirs:
                        dirs.remove("__pycache__")

                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(addon_id, file_path)
                        zipf.write(file_path, arcname=arcname)

    print(f"Successfully created {zip_name}")


def main():
    parser = argparse.ArgumentParser(description="Build and version Kodi Addon")
    parser.add_argument("--version", help="New version number to set")
    parser.add_argument("--dry-run", action="store_true", help="Do not write any files")

    args = parser.parse_args()

    addon_id, current_version = get_addon_info()
    version = args.version if args.version else current_version

    if args.version:
        update_addon_xml(version, args.dry_run)
        update_changelog(version, args.dry_run)

    build_zip(addon_id, version, args.dry_run)


if __name__ == "__main__":
    main()
