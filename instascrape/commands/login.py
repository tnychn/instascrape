import os

from instascrape import Instagram, InstascrapeError
from instascrape.utils import to_datetime
from instascrape.exceptions import TwoFactorAuthRequired, CheckpointChallengeRequired
from instascrape.commands import COOKIES_DIR, error_print, warn_print, prompt, dump_obj, load_obj, dump_cookie, load_cookie, error_catcher
from instascrape.commands.logout import logout_handler

from colorama import Fore, Style


def login_handler(**args):
    parser = args.get("parser")
    username = args.get("username")
    password = args.get("password")
    cookie_name = None
    if password and not username:
        parser.error("username must be specified together with password")
    insta = load_obj()
    cookies = [f for f in os.listdir(COOKIES_DIR) if os.path.splitext(f)[1] == ".cookie"]

    if username:
        for filename in cookies:
            name, _ = os.path.splitext(filename)
            if name == username:
                cookie_name = name
                break
        else:
            if not password:
                warn_print("No cookie file associated with user", Style.BRIGHT + Fore.WHITE + "'{}'".format(username))
                password = prompt("Password: ", password=True)

    else:
        # List all saved cookies
        print("\n" + "    " + Style.BRIGHT + "\033[4mSaved Cookies\n" + Style.RESET_ALL)
        for i, filename in enumerate(cookies):
            name, ext = os.path.splitext(filename)
            # print entry
            symbol = (Fore.LIGHTYELLOW_EX + "*" + Fore.RESET) if insta and name == insta.my_username else " "
            mtime = os.path.getmtime(os.path.join(COOKIES_DIR, filename))
            print(Fore.MAGENTA + "(" + str(i+1) + ")", symbol, name)
            print(Fore.CYAN + "Last Login:", Fore.LIGHTBLACK_EX + to_datetime(int(mtime), "%Y-%m-%d %X"), end="\n\n")
        # print option: Login New Account
        print(Fore.MAGENTA + "(" + str(len(cookies)+1) + ")", Fore.LIGHTGREEN_EX + "+", "[Login New Account]\n")
        # user choice input
        choice = prompt("(1-{})choice> ".format(len(cookies)+1), lambda x: x.isdigit() and 0 < int(x) <= len(cookies)+1, "invalid index")
        index = int(choice) - 1
        if index == len(cookies):
            username = prompt("Username: ")
            password = prompt("Password: ", password=True)
        else:
            cookie_name = os.path.splitext(cookies[index])[0]

    if insta is not None:
        warn_print("You have already logged into", Style.BRIGHT + Fore.WHITE + "@{}".format(insta.my_username))
        yorn = prompt("Are you sure you want to give up the current session? (Y/n)> ", lambda x: x.isalpha() and (x.lower() in ("y", "n")))
        if yorn == "y":
            logout_handler(real=False)
        else:
            error_print("Operation aborted.", exit=1)
    insta = Instagram()

    # Login
    try:
        insta.login(username, password, load_cookie(cookie_name) if cookie_name else None)

    # handle 2FA
    except TwoFactorAuthRequired:
        code = prompt("[2FA] Security Code: ", lambda x: x.isdigit() and len(str(x)) == 6, "invalid security code")
        with error_catcher():
            insta.two_factor_login(code)

    # handle Checkpoint
    except CheckpointChallengeRequired:
        print("ⓘ Note that if there is no phone number bound to this account, choosing SMS will fail the challenge.")
        mode = prompt("[Checkpoint] (0)-SMS (1)-Email (0|1)> ", lambda x: x.isdigit() and (int(x) in (0, 1)), "invalid choice, only 0 or 1 is accepted")
        with error_catcher():
            auth = insta.checkpoint_challenge_login(int(mode))
        code = prompt("[Checkpoint] Security Code: ", lambda x: x.isdigit() and len(str(x)) == 6, "invalid security code")
        with error_catcher():
            auth(code)

    except InstascrapeError as e:
        error_print(str(e), exit=1)

    print("• Dumping cookie...")
    dump_cookie(insta.my_username, insta.cookies)
    print("• Dumping object...")
    dump_obj(insta)
    if cookie_name:
        print(Fore.LIGHTBLUE_EX + Style.BRIGHT + "▶︎ Resumed session of " + Fore.WHITE + "@{}".format(insta.my_username))
    else:
        print(Fore.LIGHTGREEN_EX + Style.BRIGHT + "✔ Logged in as " + Fore.WHITE + "@{}".format(insta.my_username))
