import os
import io
import json
import time
import logging
import hashlib
from datetime import datetime

import requests

from instascrape.constants import USER_ID_URL
from instascrape.exceptions import NotFoundError

logger = logging.getLogger("instascrape")


def data_dumper(dest: str, filename: str, data: dict, *, write: bool = True):
    """Dumps data to a file.

    Arguments:
        dest: Path to the destination directory.
        filename: Name of the file without the extension.
        data: A dictionary of some data.
        write: Indeed writes to disk if True, writes to memory otherwise (for debugging and testing).
    """
    filename = filename + ".json"
    path = os.path.join(dest, filename)
    existing = os.path.isfile(path)
    if existing:
        with open(path, "r") as f:
            current_data = json.load(f)
        if current_data == data:
            logger.debug("=> [json] {} [skip] (identical)".format(filename))
            return
    f = None
    try:
        f = open(path, "w+") if write else io.StringIO()
        json.dump(data, f, indent=4, sort_keys=True)
    finally:
        if f:
            f.close()
    if existing:
        logger.debug("=> [json] {} [metadata] (updated)".format(filename))
    else:
        logger.debug("=> [json] {} [metadata] ({} kB)".format(filename, os.stat(path).st_size if write else "?"))


def get_biggest_media(resources: list) -> dict:
    """Retunrs the biggest media by its dimension (width & height)."""
    if not resources:
        return {}
    return sorted(resources, key=lambda i: i["config_width"] * i["config_height"], reverse=True)[0]


def get_username_from_userid(user_id: str) -> str:
    """Sends a HTTP GET API request to Instagram in order to obtain the username of a user by its user ID."""
    headers = {"User-Agent": "Instagram 52.0.0.8.83 (iPhone; CPU iPhone OS 11_4 like Mac OS X; en_US; en-US; scale=2.00; 750x1334) AppleWebKit/605.1.15"}
    resp = requests.get(USER_ID_URL.format(user_id=user_id), headers=headers, timeout=30)
    if resp.status_code == 404:
        raise NotFoundError("No user with ID {0} is found.".format(user_id))
    resp.raise_for_status()
    data = resp.json()
    return data["user"]["username"]


def verify_file(content, file_path: str) -> bool:
    """Verify file integrity by comparing the md5 hashes of the response content body and the existing file on disk.

    Arguments:
        content: The response content body in bytes.
        file_path: Path to the existing file on disk.
    """
    checksum = hashlib.md5(content).hexdigest()
    filehash = hashlib.md5(open(file_path, "rb").read()).hexdigest()
    if checksum == filehash:
        return True
    return False


def set_mtime(path: str, timestamp: int = None):
    """Set the last modified time of a file.

    Arguments:
        path: Path to the target file.
        timestamp: New value for the last modified time, use the current time otherwise.
    """
    date = datetime.fromtimestamp(timestamp if timestamp is not None else int(time.time()))
    mtime = time.mktime(date.timetuple())
    os.utime(path, (mtime, mtime))


def copy_session(session: requests.Session) -> requests.Session:
    """Obtain a copy of a given session (copy cookies and headers)."""
    s = requests.Session()
    s.headers = session.headers.copy()
    s.cookies = requests.utils.cookiejar_from_dict(requests.utils.dict_from_cookiejar(session.cookies).copy())
    return s


def to_datetime(timestamp: int, fmt: str = None) -> str:
    """Converts a timestamp to a datetime formatted string."""
    return str(datetime.fromtimestamp(float(timestamp)).strftime(fmt or "%Y-%m-%d-%H%M%S"))


def to_timestamp(dt: str) -> int:
    """Converts a datetime formatted string to a timestamp."""
    return int(datetime.strptime(str(dt), "%Y-%m-%d-%H%M%S").timestamp())
