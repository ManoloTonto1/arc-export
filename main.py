#!/usr/bin/env python3

import argparse
import datetime
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GREY = "\033[90m"

    @staticmethod
    def Background(color: str) -> str:
        return color.replace("[3", "[4", 1)


class CustomFormatter(logging.Formatter):
    time_format = f"{Colors.GREY}%(asctime)s{Colors.RESET}"
    FORMATS = {
        logging.DEBUG: f"{time_format} {Colors.BOLD}{Colors.CYAN}DEBG{Colors.RESET} %(message)s",
        logging.INFO: f"{time_format} {Colors.BOLD}{Colors.GREEN}INFO{Colors.RESET} %(message)s",
        logging.WARNING: f"{time_format} {Colors.BOLD}{Colors.YELLOW}WARN{Colors.RESET} %(message)s",
        logging.ERROR: f"{time_format} {Colors.BOLD}{Colors.RED}ERRR{Colors.RESET} %(message)s",
        logging.CRITICAL: f"{time_format} {Colors.BOLD}{Colors.Background(Colors.RED)}CRIT{Colors.RESET} %(message)s",
    }

    def format(self, record: any) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M")
        return formatter.format(record)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="reads Arc Browser JSON data, converts it to HTML, and writes the output to a specified file."
    )
    parser.add_argument("-s", "--silent", action="store_true", help="silence output")
    parser.add_argument(
        "-o", "--output", type=Path, required=False, help="specify the output file path"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="enable verbose output",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the git short hash and commit time",
    )
    parser.add_argument(
        "--find-arc",
        action="store_true",
        help="show the Arc Browser data directory path and exit",
    )

    args = parser.parse_args()

    if args.silent:
        logging.disable(logging.CRITICAL)
    else:
        setup_logging(args.verbose)

    if args.version:
        commit_hash, commit_time = get_version()
        if commit_hash is None or commit_time is None:
            logging.critical("Could not fetch Git metadata.")
            return
        print(
            f"{Colors.BOLD}GIT TIME{Colors.RESET} | {Colors.GREEN}{commit_time.strftime('%Y-%m-%d')}{Colors.RESET} [{Colors.YELLOW}{int(commit_time.timestamp())}{Colors.RESET}]"
        )
        print(
            f"{Colors.BOLD}GIT HASH{Colors.RESET} | {Colors.MAGENTA}{commit_hash}{Colors.RESET}"
        )
        return

    if args.find_arc:
        try:
            arc_path = find_arc_data_path()
            print(
                f"{Colors.BOLD}Arc Data Path{Colors.RESET}: {Colors.CYAN}{arc_path}{Colors.RESET}"
            )
            if arc_path.exists():
                print(f"{Colors.GREEN}✓ File found{Colors.RESET}")
            else:
                print(f"{Colors.RED}✗ File not found{Colors.RESET}")
        except FileNotFoundError as e:
            print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        return

    data: dict = read_json()
    html: str = convert_json_to_html(data)
    write_html(html, args.output)
    logging.info("Done!")


def setup_logging(is_verbose: bool) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    logging.basicConfig(level=logging.DEBUG, handlers=[handler])

    if is_verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


def get_version() -> tuple[str, datetime]:
    try:
        commit_hash: str = (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .decode("utf-8")
            .strip()
        )
        commit_time_str: str = (
            subprocess.check_output(["git", "log", "-1", "--format=%ct"])
            .decode("utf-8")
            .strip()
        )
        commit_time = datetime.fromtimestamp(int(commit_time_str))
    except Exception:
        commit_hash = None
        commit_time = None

    return commit_hash, commit_time


def find_arc_data_path() -> Path:
    """Find the Arc Browser data directory based on the operating system."""
    filename = "StorableSidebar.json"

    # Check if we're running in WSL
    is_wsl = (
        os.path.exists("/proc/version")
        and "microsoft" in open("/proc/version").read().lower()
    )

    if os.name == "nt" or is_wsl:
        # Windows or WSL: Arc data is stored in AppData\Local\Packages
        try:
            if is_wsl:
                # In WSL, access Windows filesystem through /mnt/c/
                # Try to get Windows username from environment or use common paths
                possible_usernames = []

                # Try to get from Windows environment variables if available
                if "WSLENV" in os.environ:
                    # Try common Windows username environment variables
                    for var in ["USERNAME", "USER"]:
                        if var in os.environ:
                            possible_usernames.append(os.environ[var])

                # Add current WSL username as fallback
                possible_usernames.append(os.environ.get("USER", "user"))

                # Try each possible username
                arc_root_parent_path = None
                for username in possible_usernames:
                    test_path = Path(f"/mnt/c/Users/{username}/AppData/Local/Packages")
                    if test_path.exists():
                        arc_root_parent_path = test_path
                        logging.debug(
                            f"WSL detected, using Windows path via /mnt/c/ with username: {username}"
                        )
                        break

                if arc_root_parent_path is None:
                    # Last resort: try to find any Users directory
                    users_dir = Path("/mnt/c/Users")
                    if users_dir.exists():
                        user_dirs = [
                            d
                            for d in users_dir.iterdir()
                            if d.is_dir() and not d.name.startswith(".")
                        ]
                        for user_dir in user_dirs:
                            test_path = user_dir / "AppData" / "Local" / "Packages"
                            if test_path.exists():
                                arc_root_parent_path = test_path
                                logging.debug(f"WSL: Found AppData at {test_path}")
                                break

                if arc_root_parent_path is None:
                    raise FileNotFoundError(
                        "Could not find Windows AppData directory from WSL"
                    )

            else:
                # Native Windows
                arc_root_parent_path = Path(
                    os.path.expanduser(r"~\AppData\Local\Packages")
                )
        except Exception as e:
            logging.error(f"Failed to access AppData directory: {e}")
            raise FileNotFoundError("Cannot access Windows AppData directory")

        if not arc_root_parent_path.exists():
            logging.debug(
                f"AppData packages directory not found: {arc_root_parent_path}"
            )
            raise FileNotFoundError("Windows AppData packages directory not found")

        try:
            # Look for Arc packages with pattern: TheBrowserCompany.Arc_*
            arc_root_paths = [
                f
                for f in arc_root_parent_path.glob("TheBrowserCompany.Arc_*")
                if f.is_dir()
            ]

            # Fallback: also check for packages that start with "TheBrowserCompany.Arc"
            if len(arc_root_paths) == 0:
                arc_root_paths = [
                    f
                    for f in arc_root_parent_path.glob("*")
                    if f.name.startswith("TheBrowserCompany.Arc") and f.is_dir()
                ]

        except PermissionError:
            logging.error("Permission denied accessing AppData packages directory")
            raise FileNotFoundError("Permission denied accessing Arc data directory")

        if len(arc_root_paths) == 0:
            logging.error("No Arc installation found in Windows AppData.")
            logging.debug(f"Searched in: {arc_root_parent_path}")
            # Look for any Browser Company packages
            try:
                available_packages = [
                    f.name
                    for f in arc_root_parent_path.glob("TheBrowserCompany*")
                    if f.is_dir()
                ]
                if available_packages:
                    logging.debug(f"Found related packages: {available_packages}")
                else:
                    logging.debug("No TheBrowserCompany packages found")
            except Exception:
                pass
            raise FileNotFoundError(
                "Arc Browser not found on Windows/WSL. Expected package like 'TheBrowserCompany.Arc_*'"
            )
        elif len(arc_root_paths) > 1:
            logging.warning(
                f"Multiple Arc installations found: {[p.name for p in arc_root_paths]}"
            )
            # Sort by modification time and use the most recent one
            arc_root_paths.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            logging.info(f"Using most recent: {arc_root_paths[0].name}")

        selected_arc_path = arc_root_paths[0]
        library_path = selected_arc_path / "LocalCache" / "Local" / "Arc" / filename
        if is_wsl:
            logging.debug(f"WSL Arc data path: {library_path}")
        else:
            logging.debug(f"Windows Arc data path: {library_path}")
        logging.debug(f"Using Arc package: {selected_arc_path.name}")

    else:
        # macOS/Linux: Arc data is stored in Application Support
        library_path = (
            Path(os.path.expanduser("~/Library/Application Support/Arc/")) / filename
        )
        logging.debug(f"macOS/Linux Arc data path: {library_path}")

    return library_path


def read_json() -> dict:
    logging.info("Reading JSON...")

    filename = Path("StorableSidebar.json")
    data = {}

    # First check if file exists in current directory
    if filename.exists():
        with filename.open("r", encoding="utf-8") as f:
            logging.debug(f"Found {filename} in current directory.")
            data = json.load(f)
    else:
        # Look for file in Arc's data directory
        try:
            library_path = find_arc_data_path()
            if library_path.exists():
                with library_path.open("r", encoding="utf-8") as f:
                    if os.name == "nt":
                        logging.debug(
                            f"Found {filename.name} in Windows Arc data directory."
                        )
                    else:
                        logging.debug(
                            f"Found {filename.name} in Arc Library directory."
                        )
                    data = json.load(f)
            else:
                raise FileNotFoundError(f"Arc data file not found at: {library_path}")

        except FileNotFoundError as e:
            # Check if we're in WSL for better error messages
            is_wsl = (
                os.path.exists("/proc/version")
                and "microsoft" in open("/proc/version").read().lower()
            )

            if os.name == "nt" or is_wsl:
                logging.critical(
                    '> File not found. Look for the "StorableSidebar.json" '
                    "  file within the Arc Browser data folder:\n"
                    '  Windows: "C:\\Users\\[USERNAME]\\AppData\\Local\\Packages\\TheBrowserCompany.Arc_*\\LocalCache\\Local\\Arc\\"\n'
                    '  WSL: "/mnt/c/Users/[USERNAME]/AppData/Local/Packages/TheBrowserCompany.Arc_*/LocalCache/Local/Arc/"'
                )
            else:
                logging.critical(
                    '> File not found. Look for the "StorableSidebar.json" '
                    '  file within the "~/Library/Application Support/Arc/" folder.'
                )
            raise e

    return data


def convert_json_to_html(json_data: dict) -> str:
    containers: list = json_data["sidebar"]["containers"]
    try:
        target: int = next(i + 1 for i, c in enumerate(containers) if "global" in c)
    except StopIteration:
        raise ValueError("No container with 'global' found in the sidebar data")

    spaces: dict = get_spaces(json_data["sidebar"]["containers"][target]["spaces"])
    items: list = json_data["sidebar"]["containers"][target]["items"]

    bookmarks: dict = convert_to_bookmarks(spaces, items)
    html_content: str = convert_bookmarks_to_html(bookmarks)

    return html_content


def get_spaces(spaces: list) -> dict:
    logging.info("Getting spaces...")

    spaces_names: dict = {"pinned": {}, "unpinned": {}}
    spaces_count: int = 0
    n: int = 1

    for space in spaces:
        if "title" in space:
            title: str = space["title"]
        else:
            title: str = "Space " + str(n)
            n += 1

        # TODO: Find a better way to determine if a space is pinned or not
        if isinstance(space, dict):
            containers: list = space["newContainerIDs"]

            for i in range(len(containers)):
                if isinstance(containers[i], dict):
                    if "pinned" in containers[i]:
                        spaces_names["pinned"][str(containers[i + 1])] = title
                    elif "unpinned" in containers[i]:
                        spaces_names["unpinned"][str(containers[i + 1])] = title

            spaces_count += 1

    logging.debug(f"Found {spaces_count} spaces.")

    return spaces_names


def convert_to_bookmarks(spaces: dict, items: list) -> dict:
    logging.info("Converting to bookmarks...")

    bookmarks: dict = {"bookmarks": []}
    bookmarks_count: int = 0
    item_dict: dict = {item["id"]: item for item in items if isinstance(item, dict)}

    def recurse_into_children(parent_id: str) -> list:
        nonlocal bookmarks_count
        children: list = []
        for item_id, item in item_dict.items():
            if item.get("parentID") == parent_id:
                if "data" in item and "tab" in item["data"]:
                    children.append(
                        {
                            "title": item.get("title", None)
                            or item["data"]["tab"].get("savedTitle", ""),
                            "type": "bookmark",
                            "url": item["data"]["tab"].get("savedURL", ""),
                        }
                    )
                    bookmarks_count += 1
                elif "title" in item:
                    child_folder: dict = {
                        "title": item["title"],
                        "type": "folder",
                        "children": recurse_into_children(item_id),
                    }
                    children.append(child_folder)
        return children

    for space_id, space_name in spaces["pinned"].items():
        space_folder: dict = {
            "title": space_name,
            "type": "folder",
            "children": recurse_into_children(space_id),
        }
        bookmarks["bookmarks"].append(space_folder)

    logging.debug(f"Found {bookmarks_count} bookmarks.")

    return bookmarks


def convert_bookmarks_to_html(bookmarks: dict) -> str:
    logging.info("Converting bookmarks to HTML...")

    html_str: str = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>"""

    def traverse_dict(d: dict, html_str: str, level: int) -> str:
        indent: str = "\t" * level
        for item in d:
            if item["type"] == "folder":
                html_str += f'\n{indent}<DT><H3>{item["title"]}</H3>'
                html_str += f"\n{indent}<DL><p>"
                html_str = traverse_dict(item["children"], html_str, level + 1)
                html_str += f"\n{indent}</DL><p>"
            elif item["type"] == "bookmark":
                html_str += f'\n{indent}<DT><A HREF="{item["url"]}">{item["title"]}</A>'
        return html_str

    html_str = traverse_dict(bookmarks["bookmarks"], html_str, 1)
    html_str += "\n</DL><p>"

    logging.debug("HTML converted.")

    return html_str


def write_html(html_content: str, output: Path = None) -> None:
    logging.info("Writing HTML...")

    if output is not None:
        output_file: Path = output
    else:
        current_date: str = datetime.now().strftime("%Y_%m_%d")
        output_file: Path = Path("arc_bookmarks_" + current_date).with_suffix(".html")

    with output_file.open("w", encoding="utf-8") as f:
        f.write(html_content)

    logging.debug(f"HTML written to {output_file}.")


if __name__ == "__main__":
    main()
