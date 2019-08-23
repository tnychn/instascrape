import os

from instascrape.utils import to_datetime
from instascrape.commands import COOKIES_DIR, error_print, dump_cookie, load_cookie, load_obj

from colorama import Fore, Style


def cookies_handler(**args):
    action = args.get("action")
    insta = load_obj()
    cookies = [f for f in os.listdir(COOKIES_DIR) if os.path.splitext(f)[1] == ".cookie"]

    if action == "save":
        if insta is None:
            error_print("No session is logged in currently.", exit=1)
        dump_cookie(insta.my_username, insta.cookies)
        print(Fore.LIGHTGREEN_EX + Style.BRIGHT + "⬇ Saved cookie for session of " + Fore.WHITE + "@{}".format(insta.my_username))

    elif action == "remove":
        ids = args.get("id")
        valid = False
        for id in ids:
            for i, filename in enumerate(cookies, start=1):
                if i == id:
                    os.remove(os.path.join(COOKIES_DIR, filename))
                    print(Fore.LIGHTGREEN_EX + "♻ Removed cookie file of", Style.BRIGHT + "@{}".format(os.path.splitext(filename)[0]))
                    valid = True
        if not valid:
            error_print("Invalid ID. No cookie was removed.")

    else:
        print("\n" + "    " + Style.BRIGHT + "\033[4mSaved Cookies\n" + Style.RESET_ALL)
        print(Style.BRIGHT + "Location:", COOKIES_DIR, end="\n\n")
        for i, filename in enumerate(cookies):
            username, ext = os.path.splitext(filename)
            # print entry
            symbol = (Fore.LIGHTYELLOW_EX + "*" + Fore.RESET) if insta and username == insta.my_username else " "
            modtime = os.path.getmtime(os.path.join(COOKIES_DIR, filename))
            expiretime = next(x for x in load_cookie(username, modtime=True) if x.name == "csrftoken").expires
            print(Fore.MAGENTA + "(" + str(i + 1) + ")", symbol, username)
            print(Fore.CYAN + "Last Login:", Fore.LIGHTBLACK_EX + to_datetime(int(modtime), "%Y-%m-%d %X"))
            print(Fore.CYAN + "Expire Time:", Fore.LIGHTBLACK_EX + to_datetime(int(expiretime), "%Y-%m-%d %X"), end="\n\n")
        print(Style.DIM + "If the cookie file of your current logged in session is removed, you will be forced to perform a REAL logout in the next logout action.")
