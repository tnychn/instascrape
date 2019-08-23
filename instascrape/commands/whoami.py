from instascrape.commands import pretty_print, load_obj

from colorama import Fore, Style


def whoami_handler(**_):
    insta = load_obj()
    if insta is None:
        name = "NOBODY"
        print(Fore.BLUE + "Authenticated:", Fore.RED + "False")
    else:
        name = insta.my_username
        data = insta.me().as_dict()
        print(Style.BRIGHT + "\033[4m" + "Your Profile")
        pretty_print(data)
        print()
        print(Fore.BLUE + "Authenticated:", Fore.GREEN + "True")
        print(Fore.LIGHTCYAN_EX + "Your ID is", Style.BRIGHT + str(insta.my_user_id))
    print(Fore.LIGHTCYAN_EX + "You are", Style.BRIGHT + name)
    print(Fore.LIGHTBLACK_EX + "“I was basically born knowing how to casually stalk people on social media.”")
    print(Fore.LIGHTBLACK_EX + " -- Becky Albertalli, The Upside of Unrequited")
