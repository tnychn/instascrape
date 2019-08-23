import os

from colorama import Fore, Style

from instascrape.commands import COOKIES_DIR, OBJECT_FILE, error_print, warn_print, load_obj, error_catcher


def logout_handler(**args):
    real = args.get("real")
    insta = load_obj()
    if insta is None:
        error_print("No session is logged in currently.", exit=1)
    username = insta.my_username
    filename = username + ".cookie"
    cookie_path = os.path.join(COOKIES_DIR, filename)
    if not os.path.isfile(cookie_path):
        # force to log session out from server if cookie file does not exist
        warn_print("Failed to locate the cookie file associated with this session. Do real logout.")
        real = True

    # Logout: remove the saved insta object (session) file
    # Remove object file
    print("• Removing object file...")
    os.remove(OBJECT_FILE)
    if not real:
        print(Fore.LIGHTBLUE_EX + Style.BRIGHT + "❙❙Paused session of " + Fore.WHITE + "@{}".format(username))
        return
    # Real Logout: log session out from server. cookies will no longer be valid.
    # Log out from Instagram
    print("• Logging session out from server...")
    with error_catcher():
        insta.logout()
    # Remove cookie file
    if os.path.isfile(cookie_path):
        print("• Removing cookie file...")
        os.remove(cookie_path)
    # ---
    print(Fore.LIGHTGREEN_EX + Style.BRIGHT + "⏏ Logged out from " + Fore.WHITE + "@{}".format(username))
