# Instascrape CLI Usage

## Index

1. [Commands](#commands)
    * [Login](#login)
    * [Logout](#logout)
    * [Whoami](#whoami)
    * [Dump](#dump)
    * [Download (Down)](#download)

---

## Commands

**Help:**
```
$ instascrape -h

usage: instascrape [-h] [-d]
                   {login,logout,cookies,whoami,dump,download,down} ...

    Instascrape -- 🚀 A fast and lightweight Instagram media downloader

Global Options:
  -h, --help            show this help message and exit
  -d, --debug           show debug (all) logging messages

Commands:
  Reminder: You may need to login first.

  {login,logout,cookies,whoami,dump,download,down}
    login               Log into Instagram.
    logout              Log out from current account.
    cookies             Manage saved cookies.
    whoami              Show the info of your currently logged in session.
    dump                Display information of the target.
    download (down)     Download media of the target.

‣ You are using [instascrape v2.0.0]
Made with ♥︎ by tnychn (https://github.com/tnychn/instascrape)
```

### Login

Log into Instagram.
> Perform authentication to Instagram.

**Usage:** `$ instascrape login [-h] [-u <username>] [-p <password>]`

* If no argument is specified, you will enter interactive login mode.
* If you have already logged into an account, you will be logged out from that account and log into this account.

### Logout

Log out from Instagram.

### Whoami

### Cookies

### Dump

### Download
