# Check Python version
import sys
if not (sys.version_info.major == 3 and sys.version_info.minor >= 5):
    sys.stderr.write("Instascrape requires Python 3.5.0 or above. Python {0} detected instead!\n".format(".".join(map(str, sys.version_info[:3]))))
    sys.exit(255)

import logging
import argparse

from colorama import init, Fore, Back, Style

from instascrape import __version__
from instascrape.commands.login import login_handler
from instascrape.commands.logout import logout_handler
from instascrape.commands.whoami import whoami_handler
from instascrape.commands.cookies import cookies_handler
from instascrape.commands.dump import dump_handler
from instascrape.commands.download import download_handler


def bold(text):
    return Style.BRIGHT + text + Style.RESET_ALL


class ColorFormatter(logging.Formatter):

    def format(self, record):
        original_fmt = self._fmt
        # Customize format
        if record.levelno == logging.DEBUG:
            self._style._fmt = "    {0}%(msg)s{1}".format(Fore.LIGHTBLACK_EX, Fore.RESET)
        elif record.levelno == logging.INFO:
            self._style._fmt = "- %(msg)s"
        elif record.levelno == logging.WARNING:
            self._style._fmt = "{0} WARN {1} {2}%(msg)s{3}".format(Style.BRIGHT + Fore.BLACK + Back.YELLOW, Style.RESET_ALL, Fore.LIGHTYELLOW_EX, Fore.RESET)
        elif record.levelno == logging.ERROR:
            self._style._fmt = "{0} ERROR {1} {2}%(msg)s{3}".format(Style.BRIGHT + Fore.BLACK + Back.MAGENTA, Style.RESET_ALL, Fore.MAGENTA, Fore.RESET)
        elif record.levelno == logging.CRITICAL:
            self._style._fmt = "{0} CRITIC {1} {2}%(msg)s{3}".format(Style.BRIGHT + Fore.BLACK + Back.RED, Style.RESET_ALL, Fore.RED, Fore.RESET)

        result = logging.Formatter.format(self, record)
        # Restore the original format configured
        self._fmt = original_fmt
        return result


def main():
    # Root Parser
    description = bold("    \033[4m" + "Instascrape") + " -- " + "🚀 A {f.LIGHTBLUE_EX}fast{f.RESET} and {f.LIGHTGREEN_EX}lightweight{f.RESET} Instagram media downloader".format(f=Fore)
    epilog = (
        "‣ You are using " + Fore.LIGHTYELLOW_EX + "[instascrape v{}]".format(__version__) + Fore.RESET,
        bold("Made with {f.LIGHTRED_EX}♥︎{f.RESET} by a1phat0ny".format(f=Fore)) + " " + "(https://github.com/a1phat0ny/instascrape)"
    )
    parser = argparse.ArgumentParser(prog="instascrape", description=description, epilog="\n".join(epilog),
                                     allow_abbrev=False, formatter_class=argparse.RawTextHelpFormatter)
    parser._optionals.title = bold("Global Options")
    parser.add_argument("-d", "--debug", help="show debug (all) logging messages", default=False, action="store_true")
    subparsers = parser.add_subparsers(title=bold("Commands"),
                                       description=Fore.YELLOW + "Reminder: You may need to login first." + Fore.RESET)

    # Login Parser
    login_parser = subparsers.add_parser("login", help="Log into Instagram.", allow_abbrev=False)

    login_options_group = login_parser.add_argument_group(bold("Credentials"))
    login_options_group.add_argument("-u", "--username", type=str, metavar="<username>",
                                     help="provide account login username, skip interactive login process")
    login_options_group.add_argument("-p", "--password", type=str, metavar="<password>",
                                     help="provide account login username, skip interactive login process")

    login_parser.set_defaults(func=login_handler, parser=login_parser)

    # Logout Parser
    logout_parser = subparsers.add_parser("logout", help="Log out from current account.", allow_abbrev=False)
    logout_options_group = logout_parser.add_argument_group(bold("Options"))
    logout_options_group.add_argument("-r", "--real", help="log session out from server and remove the cookie associated with the session", default=False, action="store_true")
    logout_parser.set_defaults(func=logout_handler)

    # Cookies Parser
    cookies_parser = subparsers.add_parser("cookies", help="Manage saved cookies.", allow_abbrev=False)
    cookies_subparsers = cookies_parser.add_subparsers(title=bold("Actions"),
                                                       description=Fore.YELLOW + "If there is no action specified, it will list out all cookies." + Fore.RESET)

    cookies_save_parser = cookies_subparsers.add_parser("save", help="Save the cookie of the current logged in session.")
    cookies_save_parser.set_defaults(action="save")

    cookies_remove_parser = cookies_subparsers.add_parser("remove", help="Remove specific cookies.", aliases=["rm"])
    cookies_remove_parser.add_argument("id", type=int, metavar="<id>", nargs="+",
                                       help="id of the cookie file you want to remove")
    cookies_remove_parser.set_defaults(action="remove")

    cookies_parser.set_defaults(func=cookies_handler)

    # WhoAmI Parser
    whoami_parser = subparsers.add_parser("whoami", help="Show the info of your currently logged in session.", allow_abbrev=False)
    whoami_parser.set_defaults(func=whoami_handler)

    # Dump Parser
    dump_parser = subparsers.add_parser("dump", help="Dump information of the target.", allow_abbrev=False)

    dump_options_group = dump_parser.add_argument_group(bold("Dump Options"))
    dump_options_group.add_argument("-o", "--outfile", type=str, metavar="<path/to/file>",
                                    help="dump raw JSON data to a file")

    dump_parser.add_argument("target", type=str, metavar="TARGET", nargs="+",
                             help="dump target {@profile} {:post}")

    dump_profile_types_group = dump_parser.add_argument_group(bold("Profile Types"))
    dump_profile_types_group.description = Fore.YELLOW + "These types are only available when targeting {@profile}." + Fore.RESET
    dump_profile_types_group.add_argument("-followers", default=False, action="store_true",
                                          help="dump followers of the target profile")
    dump_profile_types_group.add_argument("-followings", default=False, action="store_true",
                                          help="dump followings of the target profile")

    dump_post_types_group = dump_parser.add_argument_group(bold("Post Types"))
    dump_post_types_group.description = Fore.YELLOW + "These types are only available when targeting {:post}." + Fore.RESET
    dump_post_types_group.add_argument("-comments", default=False, action="store_true",
                                       help="dump comments of the target post")
    dump_post_types_group.add_argument("-likes", default=False, action="store_true",
                                       help="dump likes of the target post")

    dump_types_options_group = dump_parser.add_argument_group(bold("Types Options"))
    dump_types_options_group.description = Fore.YELLOW + "These options are only available (unless explictly specified) when dumping profile types (-followers, -followings) and post types (-likes, -comments)." + Fore.RESET
    dump_types_options_group.add_argument("-PF", "--profiles-filter", type=str, metavar="<expression>",
                                          help="only dump profiles that match the specified condition {}(disallow: -comments){}".format(Fore.RED, Fore.RESET))
    dump_types_options_group.add_argument("-CF", "--comments-filter", type=str, metavar="<expression>",
                                          help="only dump comments that match the specified condition {}(disallow: -followers, -followings, -likes){}".format(Fore.RED, Fore.RESET))
    dump_types_options_group.add_argument("-l", "--limit", type=int, metavar="<max count>",
                                          help="max amount of items you want to dump {}(default: all){}".format(Fore.BLUE, Fore.RESET))
    dump_types_options_group.add_argument("--preload", default=False, action="store_true",
                                          help="load items beforehand using multithreading, might help increase the speed of retrieving {}(disallow: -comments){}".format(Fore.RED, Fore.RESET))

    dump_parser.set_defaults(func=dump_handler, parser=dump_parser)

    # Download Parser
    download_parser = subparsers.add_parser("download", help="Download media of the target.", aliases=["down"], allow_abbrev=False)

    download_options_group = download_parser.add_argument_group(bold("Download Options"))
    download_options_group.add_argument("-d", "--dest", type=str, metavar="<path/to/dir>", default=".",
                                        help="path to destination directory {}(default: .){}".format(Fore.BLUE, Fore.RESET))
    download_options_group.add_argument("-l", "--limit", type=int, metavar="<max count>",
                                        help="max amount of items you want to download {}(default: all){} {}(disallow: {{:post}}, -story/--story, -pic/--profile-picture){}".format(Fore.BLUE, Fore.RESET, Fore.RED, Fore.RESET))
    download_options_group.add_argument("--dump-metadata", default=False, action="store_true",
                                        help="dump metadata of items to JSON files {}(disallow: -pic/--profile-picture){}".format(Fore.RED, Fore.RESET))

    download_posts_options_group = download_parser.add_argument_group(bold("Posts Options"))
    download_posts_options_group.description = Fore.YELLOW + "These options are only available (unless explictly specified) when downloading {:post} and --*-posts." + Fore.RESET
    download_posts_options_group.add_argument("--dump-comments", default=False, action="store_true",
                                              help="dump comments of posts to JSON files")
    download_posts_options_group.add_argument("--dump-likes", default=False, action="store_true",
                                              help="dump likes of posts to JSON files")
    download_posts_options_group.add_argument("-PF", "--posts-filter", type=str, metavar="<expression>",
                                              help="only download posts that match the specified condition {}(disallow: {{:post}}){}".format(Fore.RED, Fore.RESET))
    download_posts_options_group.add_argument("--preload", default=False, action="store_true",
                                              help="load posts beforehand using multithreading (might help increase the speed of retrieving) {}(disallow: {{:post}}){}".format(Fore.RED, Fore.RESET))

    download_parser.add_argument("target", type=str, metavar="TARGET", nargs="+",
                                 help="download target {@profile} {#hashtag} {:post} {saved} {explore}")

    download_types_group = download_parser.add_argument_group(bold("Media Types"))
    download_types_group.add_argument("-timeline", "--timeline-posts", default=False, action="store_true", dest="timeline",
                                      help="download timeline posts of the target (@#E)")
    download_types_group.add_argument("-tagged", "--tagged-posts", default=False, action="store_true", dest="tagged",
                                      help="download tagged posts of the target (@)")
    download_types_group.add_argument("-igtv", "--igtv-posts", default=False, action="store_true", dest="igtv",
                                      help="download IGTV posts of the target (@)")
    download_types_group.add_argument("-top", "--top-posts", default=False, action="store_true", dest="top",
                                      help="download top posts of the target (#)")
    download_types_group.add_argument("-recent", "--recent-posts", default=False, action="store_true", dest="recent",
                                      help="download recent posts of the target (#)")
    download_types_group.add_argument("-story", "--story", default=False, action="store_true", dest="story",
                                      help="download story of the target (@#)")
    download_types_group.add_argument("-highs", "--highlights", default=False, action="store_true", dest="highs",
                                      help="download highlights of the target (@)")
    download_types_group.add_argument("-pic", "--profile-picture", default=False, action="store_true", dest="pic",
                                      help="download profile picture of the target (@#)")

    download_parser.set_defaults(func=download_handler, parser=download_parser)

    args = parser.parse_args()
    # Init colors
    init(autoreset=True)
    # Setup logger everytime the program starts, before executing anything
    if args.debug:
        logger = logging.getLogger("instascrape")
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(ColorFormatter())
        logger.addHandler(handler)
    # Run command action
    try:
        args.func
    except AttributeError:
        # print help message if no subcommand specified
        parser.print_help()
    else:
        args.func(**vars(args))


if __name__ == "__main__":
    main()
