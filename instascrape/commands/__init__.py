import os
import sys
import pickle
import logging
import traceback
from getpass import getpass
from datetime import datetime
from contextlib import contextmanager

from colorama import Fore
from requests import RequestException

from instascrape.utils import set_mtime
from instascrape.exceptions import InstascrapeError

DIR_PATH = os.path.join(os.path.expanduser("~"), ".instascrape")
OBJECT_FILE = os.path.join(DIR_PATH, "instasession.pickle")
COOKIES_DIR = os.path.join(DIR_PATH, "cookies")
if not os.path.isdir(COOKIES_DIR):
    os.mkdir(COOKIES_DIR)


def pretty_print(data):
    if isinstance(data, dict):
        for key, value in data.items():
            print("·", key, end=": ")

            if "time" in key.split("_"):
                print(Fore.LIGHTCYAN_EX + str(datetime.fromtimestamp(value)))

            # boolean
            elif isinstance(value, bool):
                if value:
                    print(Fore.LIGHTGREEN_EX + str(value))
                else:
                    print(Fore.LIGHTRED_EX + str(value))

            # integer
            elif isinstance(value, int):
                print(Fore.LIGHTMAGENTA_EX + str(value))

            # NoneType
            elif value is None:
                print(Fore.LIGHTBLACK_EX + str(value))

            # string or other types
            else:
                splitted = str(value).split("\n")
                print(splitted[0])
                for text in splitted[1:]:
                    print(" "*(len(key)+4) + text)
    else:
        # GeneratorType or List
        for i, item in enumerate(data, start=1):
            if isinstance(item, dict):
                print(Fore.LIGHTMAGENTA_EX + "[{0}]".format(i))
                pretty_print(item)
                print()
            else:
                print(Fore.LIGHTMAGENTA_EX + "[{0}]".format(i), str(item))


def error_print(*message: str, exit: int = None):
    print(Fore.RED + "✖ " + " ".join(message))
    if exit is not None:
        sys.exit(exit)


def warn_print(*message: str):
    print(Fore.YELLOW + "⚡︎" + " ".join(message))


def prompt(text: str, check=None, err_msg: str = None, *, password: bool = False) -> str:
    try:
        if password:
            answer = getpass(text)
        else:
            answer = input(text)
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
    if answer == "":
        return prompt(text, check, err_msg, password=password)
    if check and check(answer) is False:
        if err_msg is not None:
            error_print(err_msg)
        return prompt(text, check, err_msg, password=password)
    return answer


def load_obj():
    if os.path.isfile(OBJECT_FILE):
        with open(OBJECT_FILE, "rb") as f:
            insta = pickle.load(f)
        set_mtime(OBJECT_FILE)
        return insta


def dump_obj(insta):
    with open(OBJECT_FILE, "wb+") as f:
        pickle.dump(insta, f)


def load_cookie(username: str, modtime: bool = True):
    path = os.path.join(COOKIES_DIR, username + ".cookie")
    with open(path, "rb") as f:
        cookie = pickle.load(f)
    if modtime:
        set_mtime(path)
    return cookie


def dump_cookie(username: str, cookie):
    path = os.path.join(COOKIES_DIR, username + ".cookie")
    if os.path.isfile(path):
        warn_print("Overwriting cookie file...")
    with open(path, "wb+") as f:
        pickle.dump(cookie, f)


@contextmanager
def error_catcher(do_exit: bool = True):
    try:
        yield
    except (InstascrapeError, RequestException):
        logger = logging.getLogger("instascrape")
        exc_type, exc_value, tb = sys.exc_info()
        logger.error("{}: {}".format(exc_type.__name__, exc_value))
        logger.debug("".join(traceback.format_tb(tb)))
        error_print("{}: {}".format(exc_type.__name__, exc_value), exit=1 if do_exit else None)
    except KeyboardInterrupt:
        error_print("Interrupted by user.", exit=130)
