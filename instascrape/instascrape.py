import re
import sys
import json
import time
import random
import logging
import traceback
from hashlib import md5
from contextlib import contextmanager

import requests
from requests.cookies import RequestsCookieJar

from instascrape.constants import *
from instascrape.structures import *
from instascrape.exceptions import *
from instascrape.utils import get_username_from_userid, copy_session

__all__ = ("Instagram", "Instascraper")


class LoggerMixin:
    """Plug a logger and allow 'Instagram' class to access 'self.logger' without having a logger object (attribute) itself.
    * Useful when pickling 'Instagram' object, since a 'thread.lock' object cannot be pickled.
    - https://stackoverflow.com/questions/3375443/how-to-pickle-loggers
    """

    @property
    def logger(self):
        return logging.getLogger("instascrape")


class Instagram(LoggerMixin):
    """The main class for interacting with Instagram's private API. Responsible for performing authentications and GraphQL queries."""

    def __init__(self, proxies: dict = None):
        # Initialise variables
        self.my_user_id = None
        self.my_username = None
        self.authenticated = False
        self._two_factor_pack = None
        self._checkpoint_pack = None
        self._rhx_gis = None
        self._session = self.get_anonymous_session()
        if proxies:
            self._session.proxies = proxies

    @property
    def _default_headers(self) -> dict:
        return {"Accept-Encoding": "gzip, deflate",
                "Accept-Language": "en-US,en;q=0.8",
                "Connection": "keep-alive",
                "Host": "www.instagram.com",
                "Origin": "https://www.instagram.com",
                "Referer": "https://www.instagram.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36",
                "X-Instagram-AJAX": "1",
                "X-Requested-With": "XMLHttpRequest"}

    @property
    def _default_cookies(self) -> dict:
        return {"rur": "ATN", "ds_user_id": ""}

    def get_anonymous_session(self) -> requests.Session:
        """Returns a new anonymous session."""
        session = requests.Session()
        session.headers.update(self._default_headers)
        session.cookies.update(self._default_cookies)
        return session

    def login(self, username: str = None, password: str = None, cookies: RequestsCookieJar = None):
        """Log in and authenticate user to Instagram.

        Note:
            There is no need to provide both username and password if 'cookies' is given.
            'username' and 'password' must be given together.

        Arguments:
            username: The user's login username.
            password: The user's login password.
            cookies: A user provided cookies data.

        Raises:
            TwoFactorAuthRequired: when 2FA is required.
            CheckpointChallengeRequired: when checkpoint challenge solving is required.
        """
        self.logger.info("Logging in...")
        session = requests.Session()
        session.headers.update(self._default_headers)

        if cookies is not None:
            # Use provided cookie
            self.logger.debug("using provided cookie -> " + str(cookies))
            session.cookies = cookies
            session.headers.update({"X-CSRFToken": cookies["csrftoken"]})
        else:
            assert all((username, password)), "both 'username' and 'password' must be specified"
            # Get a new cookie by username and password
            self.logger.debug("getting cookie by username and password")
            # get initial cookie data
            # FIXME: ugly code, to be resolved
            req = session.get("https://www.instagram.com")
            if "csrftoken" in req.cookies or "csrftoken" in session.cookies:
                session.headers.update({"X-CSRFToken": req.cookies.get("csrftoken") or session.cookies.get("csrftoken", "")})
            else:
                self.logger.debug("failed to find 'csrftoken' in first attempt, using endpoint '/web/__mid'")
                req = session.get("https://www.instagram.com/web/__mid")
                if "csrftoken" not in req.cookies or "csrftoken" not in session.cookies:
                    raise InstascrapeError("cannot find 'csrftoken' from cookies")
                session.headers.update({"X-CSRFToken": req.cookies.get("csrftoken") or session.cookies.get("csrftoken", "")})
            # send login request
            payload = {"username": username, "password": password}
            resp = session.post(LOGIN_URL, data=payload)
            data = resp.json()
            self.logger.debug("login response data -> " + str(data))

            if "two_factor_required" in data:
                info = data["two_factor_info"]
                self._two_factor_pack = (session, {"username": info["username"], "identifier": info["two_factor_identifier"]})
                self.logger.info("[2FA] Security code sent to phone number: XXXX " + str(info["obfuscated_phone_number"]))
                raise TwoFactorAuthRequired()

            elif "checkpoint_url" in data:
                checkpoint_url = data.get("checkpoint_url")
                self._checkpoint_pack = (session, checkpoint_url)
                self.logger.info("[Checkpoint] Please verify your account at '{0}'".format(checkpoint_url))
                raise CheckpointChallengeRequired()

            elif data["status"] != "ok" or not data["authenticated"]:
                msg = "wrong password"
                if data["user"] is False:
                    msg = "user does not exist".format(username)
                raise LoginError(data.get("message") or msg)
            else:
                session.headers.update({"X-CSRFToken": resp.cookies["csrftoken"] or session.cookies.get("csrftoken", "")})
        self._session = session
        self._post_login()

    def two_factor_login(self, code: str):
        """Login by performing two-factor authentication.
        * Only should be called if 'self.login()' raises 'TwoFactorAuthRequired'.

        Arguments:
            code: Security code which is sent to your phone through SMS by Instagram.
        """
        assert self._two_factor_pack is not None, "no two-factor authentication is required"
        session, payload = self._two_factor_pack
        payload.update({"verificationCode": code})
        resp = session.post("https://www.instagram.com/accounts/login/ajax/two_factor/", data=payload, allow_redirects=True)
        self.logger.debug(resp.json())
        data = resp.json()
        if data["status"] != "ok" or not data["authenticated"]:
            raise LoginError(data.get("message") or "incorrect security code")
        session.headers.update({"X-CSRFToken": resp.cookies.get("csrftoken") or session.cookies.get("csrftoken", "")})
        self._session = session
        self._two_factor_pack = None
        self._post_login()

    def checkpoint_challenge_login(self, mode: int):
        """Login by solving checkpoint challenge.
        * Only should be called if 'self.login()' raises 'CheckpointAuthRequired'.

        Arguments:
            mode: Challenge mode, either 0 or 1 (0 for SMS, 1 for Email).

        Returns:
            A function that accepts a string 'code', which represents the security code sent to the user using the above challenge mode, as the first argument.
            It performs the second step of checkpoint challege solving (authenticating with security code).
        """
        assert mode == 0 or mode == 1, "invalid 'mode' integer (must be either 0 or 1)"
        assert self._checkpoint_pack is not None, "no checkpoint challenge to be solved"
        session, checkpoint_url = self._checkpoint_pack

        url = BASE_URL + checkpoint_url
        resp = session.get(url)
        session.headers.update({"X-CSRFToken": resp.cookies.get("csrftoken") or session.cookies.get("csrftoken", ""), "Referer": url})

        payload = {"choice": mode}
        resp = session.post(url, data=payload)
        self.logger.debug(resp.json())
        session.headers.update({"X-CSRFToken": resp.cookies.get("csrftoken") or session.cookies.get("csrftoken", "")})

        def auth(code: str):
            payload = {"security_code": code}
            resp = session.post(url, data=payload)
            self.logger.debug(resp.json())
            data = resp.json()
            if data["status"] != "ok":
                raise LoginError(data.get("message") or "incorrect security code")
            session.headers.update({"X-CSRFToken": resp.cookies.get("csrftoken") or session.cookies.get("csrftoken", "")})
            self._session = session
            self._checkpoint_url = None
            self._post_login()

        return auth

    def _post_login(self):
        self.logger.debug("Cookie: " + str(self._session.cookies))
        self._rhx_gis = None
        self.my_user_id = str(self._session.cookies.get("ds_user_id", ""))
        self.my_username = get_username_from_userid(self.my_user_id)
        self.authenticated = True
        self.logger.info("Logged in -> @{0} ({1})".format(self.my_username, self.my_user_id))

    def logout(self):
        """Log client's session out from Instagram's server.
        * Requires authentication.
        """
        if not self.authenticated:
            raise AuthenticationRequired()
        self.logger.info("Logging out...")
        self._session.post(LOGOUT_URL, data={"csrfmiddlewaretoken": self._session.headers["X-CSRFToken"]})
        self._session.close()
        self._session = self.get_anonymous_session()
        self._rhx_gis = None
        self.my_user_id = None
        self.my_username = None
        self.authenticated = False
        self.logger.debug("Logged out")

    @property
    def cookies(self) -> RequestsCookieJar:
        """Returns the cookies in the current session."""
        return self._session.cookies.copy()

    @property
    def rhx_gis(self) -> str:
        """Returns the 'rhx_gis' variable. Only is helpful in an anonymous session."""
        if self._rhx_gis is not None:
            return self._rhx_gis
        self.logger.debug("getting 'rhx_gis' variable")
        resp = self._session.get(BASE_URL)
        resp.raise_for_status()
        match = re.search(r"window\._sharedData = (.+?);", resp.text)
        if match is None:
            raise ExtractionError("rhx_gis variable not found")
        self._rhx_gis = match.group(1)
        self._session.cookies.update({"X-CSRFToken": resp.cookies.get("csrftoken") or resp.cookies.get("csrftoken", "")})
        return self._rhx_gis

    def _fetch_json_data(self, url: str, **kwargs):
        err = None
        attempts = 1
        self.logger.debug("Fetching JSON data -> {} (kwargs={}) ...".format(url, kwargs))
        while attempts <= 5:
            try:
                with copy_session(self._session) as session:
                    resp = session.get(url, timeout=30, **kwargs)
                if resp.status_code == 404:
                    raise NotFoundError()
                if resp.status_code == 429:
                    raise RateLimitedError()
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                err = e
                exc = sys.exc_info()
                self.logger.debug("".join(traceback.format_exception(*exc)))
                self.logger.error("(#{}) Failed to fetch JSON data -> retrying...".format(attempts))
                attempts += 1
            else:
                data = resp.json()
                if ("status" in data and data["status"] != "ok") or "message" in data:
                    self.logger.debug(json.dumps(data))
                    raise ExtractionError(data.get("message") or "status -> {}".format(data["status"]))
                # data: '.../graphql/query/...'
                # graphql: '.../?__a=1'
                d = data.get("data") or data.get("graphql")
                return d
        else:
            self.logger.info("Reached rety limit (5)")
            if err is not None:
                raise err

    def _graphql_query(self, query_hash: str, variables: dict) -> dict:
        variables_json = json.dumps(variables)
        url = QUERY_URL.format(query_hash, variables_json)
        headers = None
        if not self.authenticated:
            value = "{}:{}".format(self.rhx_gis, variables_json)
            signature = md5(value.encode()).hexdigest()
            headers = {"X-Instagram-Gis": signature}
        data = self._fetch_json_data(url, headers=headers)
        return data

    def _graphql_query_edges(self, query_hash: str, variables: dict, struct_key: str, edge_key: str, initial_data: dict = None):
        initial_data = initial_data or {}

        if "first" not in variables:
            # amount not provided, set to 50 (maximum amount per page)
            variables["first"] = 50

        if initial_data is not None and edge_key in initial_data:
            # try extracting 'key' from initial data
            self.logger.debug("found edge key ({}) in initial data".format(edge_key))
            data = initial_data[edge_key]
        else:
            # cannot extract edge key from initial data, do GraphQL query to get the data
            self.logger.debug("doing GraphQL query for data...")
            data = self._graphql_query(query_hash, variables)[struct_key][edge_key]

        total = data.get("count")
        if total is None:
            # exceptional case
            total = 10**10 if edge_key != "edge_hashtag_to_top_posts" else 9
        self.logger.debug("Total: {}".format(total))
        if total > 0 and not data["edges"]:
            raise PrivateAccessError()
        yield total
        if total <= 0:
            self.logger.warning("No data.")
            return

        amount = 0
        page_i = 1 if edge_key not in initial_data else 0
        while amount < total and data.get("edges"):
            # extract items
            count = 0
            for edge in data["edges"]:
                yield edge["node"]
                count += 1
            self.logger.info("Page-{0} => extracted {1} items".format(page_i, count))
            amount += count

            # fetch next page if not enough
            if "page_info" in data and data["page_info"].get("has_next_page") and amount < total:
                # update url parameter
                variables["after"] = data["page_info"]["end_cursor"]
                data = self._graphql_query(query_hash, variables)[struct_key][edge_key]
            else:
                break
            page_i += 1
            secs = random.uniform(1, 5)
            self.logger.debug("Sleeping for {}s".format(round(secs, 3)))
            time.sleep(secs)

    def me(self) -> Profile:
        """Obtain the 'Profile' object of the user himself.
        * Requires authentication.
        """
        if not self.authenticated:
            raise AuthenticationRequired()
        return Profile.from_username(self, self.my_username)

    def profile(self, name: str = None, id: str = None) -> Profile:
        """Obtain a 'Profile' object by username or user ID."""
        assert name or id, "one of 'name' or 'id' must be specified"
        if name:
            return Profile.from_username(self, name)
        if id:
            return Profile.from_id(self, id)

    def post(self, shortcode: str) -> Post:
        """Obtain a 'Post' object by its shortcode."""
        return Post.from_shortcode(self, shortcode)

    def hashtag(self, tagname: str) -> Hashtag:
        """Obtain a 'Hashtag' object of the given tag name."""
        return Hashtag.from_tagname(self, tagname)

    def explore(self) -> Explore:
        """Obtain an 'Explore' object.
        * Requires authentication.
        """
        if not self.authenticated:
            raise AuthenticationRequired()
        return Explore(self)


@contextmanager
def Instascraper(username: str = None, password: str = None, cookies: dict = None, proxies: dict = None):
    """A context manager wrapper of the 'Instagram' class."""
    insta = Instagram(proxies)
    if not any((username, password, cookies)):
        yield insta
    else:
        insta.login(username, password, cookies)
        try:
            yield insta
        finally:
            insta.logout()
            insta._session.close()
