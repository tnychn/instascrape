import os
import sys
import json
import logging
import traceback
from typing import *
from io import BytesIO
from collections import namedtuple, OrderedDict

import requests

from instascrape.constants import *
from instascrape.exceptions import *
from instascrape.group import *
from instascrape.utils import get_username_from_userid, set_mtime, get_biggest_media, verify_file, to_datetime

__all__ = ("Post", "IGTV", "Profile", "Hashtag", "Explore")
logger = logging.getLogger("instascrape")
CommentItem = namedtuple("CommentItem", "author text created_time")


class DataGetterMixin:

    @property
    def raw_data(self) -> dict:
        if self._full_data is None:
            self._obtain_full_data()
        return self._full_data

    def _find_or_get(self, *keys: str, data: dict = None, i: int = None):
        i = 0 if i is None else i
        key = keys[i]
        if data is not None:
            if key in data:
                return data[key]
            else:
                # get full data & find in it
                self._obtain_full_data()
                d = self._full_data[keys[0]]
                for k in keys[1:]:
                    d = d[k]  # raises KeyError
                return d
        else:
            # [1] find in initial data
            if key in self._init_data:
                d = self._init_data[key]
            # [2] find in full data (if not None)
            elif self._full_data is not None and key in self._full_data:
                d = self._full_data[key]
            else:
                # get full data & find in it
                self._obtain_full_data()
                d = self._full_data[key]  # raises KeyError
            i += 1
            return self._find_or_get(*keys, data=d, i=i) if len(keys) > 1 else d


class AsDictMixin:

    info_vars = ()

    def as_dict(self, *, extra: bool = False) -> OrderedDict:
        """Returns all 'info_vars' as an 'OrderedDict'.

        Arguments:
            extra: Add extra data to the dictionary if True.
        """
        assert len(self.info_vars) > 0, "'AsDictMixin' should not be used in this class if 'info_vars' is intended to be empty"
        dictionary = OrderedDict({"_struct": self.__class__.__name__} if extra else {})
        for attr in self.info_vars:
            dictionary[attr] = getattr(self, attr)
        return dictionary


class MediaItem(AsDictMixin):
    """Represents a media item (image or video)."""

    info_vars = ("typename", "src", "width", "height", "is_video")

    @classmethod
    def compose_items(cls, data: dict) -> List["MediaItem"]:
        """Composes 'MediaItem' objects by extracting from 'data'."""

        def make(node: dict) -> "MediaItem":
            typename = node["__typename"]
            if typename == "GraphImage":
                item = get_biggest_media(node["display_resources"])
            elif typename == "GraphVideo":
                item = {"src": node["video_url"]}
            return cls(typename, item.get("src"), item.get("config_width"), item.get("config_height"))

        typename = data["__typename"]
        if typename in ("GraphImage", "GraphVideo"):
            items = [make(data)]
        elif typename == "GraphSidecar":
            items = []
            data = data["edge_sidecar_to_children"]["edges"]
            for node in data:
                items.append(make(node["node"]))
        else:
            raise AssertionError("unrecognized typename: '{}'".format(typename))
        return items

    def __init__(self, typename: str, src: str, width: int, height: int):
        self.typename = typename
        self.src = src
        self.width = width
        self.height = height

    def __repr__(self) -> str:
        return "MediaItem(typename='{}', src='{}', width={}, height={})".format(self.typename, self.src, self.width, self.height)

    def __eq__(self, other) -> bool:
        return isinstance(other, MediaItem) and self.src == other.src

    def __hash__(self) -> int:
        return hash(self.src)

    @property
    def is_video(self) -> bool:
        """Returns True if this media is a video."""
        return self.typename == "GraphStoryVideo"

    def download(self, dest: str, filename: str, *, write: bool = True, verify: bool = True) -> Optional[str]:
        """Download this media item to a file.

        Arguments:
            dest: Path to the destination directory.
            filename: Name of the file without extension.
            write: Write file to disk if True, write to memory otherwise (for testing and debugging).
            verify: Verify file integrity if True, check the size of file in bytes otherwise.

        Returns:
            The path to the downloaded file if download suceeded, False otherwise
        """
        try:
            f = None
            logger.debug("Downloading file {0} -> {1}".format(self.src, dest))
            r = requests.get(self.src, stream=True, timeout=30)

            # get info of the file
            mime = r.headers["Content-Type"]
            bytesize = int(r.headers["Content-Length"])
            size = int(bytesize / 1024)
            if mime == "video/mp4":
                ext = ".mp4"
            elif mime == "image/jpeg":
                ext = ".jpg"
            else:
                raise DownloadError("Unsupported MIME type: {0}".format(mime), self.src)

            finish_filename = filename + ext
            finish_path = os.path.join(dest, finish_filename)
            part_filename = filename + ext + ".part"
            part_path = os.path.join(dest, part_filename)

            # skip if the file is existing and intact
            if os.path.isfile(finish_path):
                # verify file integrity using md5
                if verify and verify_file(r.content, finish_path):
                    logger.debug("~> [{0}] {1} [skip] (already downloaded)".format(mime, finish_filename))
                    return None
                # verify file by checking the size in byte
                if os.stat(finish_path).st_size == bytesize:
                    logger.debug("~> [{0}] {1} [skip] (already downloaded)".format(mime, finish_filename))
                    return None

            # write to file
            f = open(part_path, "wb+") if write else BytesIO()
            for chunk in r.iter_content(1024):
                if chunk:
                    f.write(chunk)
            logger.debug("=> [{0}] {1} [{2}x{3}] ({4} kB)".format(mime, finish_filename, self.width or "?", self.height or "?", size))
        except Exception as e:
            raise DownloadError(str(e), self.src) from e
        else:
            # rename .part file to its real extension
            if f:
                f.close()
            os.rename(part_path, finish_path)
            return finish_path
        finally:
            if f and not f.closed:
                f.close()


class ReelItem(MediaItem):
    """Represents a media item (image or video) of a reel."""

    info_vars = ("typename", "src", "width", "height", "is_video", "id", "owner_username", "owner_id", "owner_profile_picture_url", "created_time", "expire_time", "cta_url")

    @classmethod
    def compose_items(cls, data: dict) -> List["ReelItem"]:
        """Composes 'ReelItem' objects by extracting from 'data'."""

        def make(node: dict) -> "ReelItem":
            typename = node["__typename"]
            if typename == "GraphStoryImage":
                item = get_biggest_media(node["display_resources"])
            elif typename == "GraphStoryVideo":
                item = get_biggest_media(node["video_resources"])
            return cls(typename, item.get("src"), item.get("config_width"), item.get("config_height"), node)

        items = []
        data = data["items"]
        for node in data:
            items.append(make(node))
        return items

    def __init__(self, typename: str, src: str, width: int, height: int, data: dict):
        super().__init__(typename, src, width, height)
        self.data = data

    def __repr__(self) -> str:
        return "ReelItem(typename='{}', src='{}', width={}, height={})".format(self.typename, self.src, self.width, self.height)

    def __eq__(self, other) -> bool:
        return isinstance(other, ReelItem) and self.src == other.src and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def is_video(self) -> bool:
        """Returns True if this media item is a video."""
        return self.typename == "GraphStoryVideo"

    @property
    def id(self) -> str:
        """Returns the ID of this reel item."""
        return self.data["id"]

    @property
    def owner_username(self) -> str:
        """Returns the owner's username of this reel item."""
        return self.data["owner"]["username"]

    @property
    def owner_id(self) -> str:
        """Returns the owner's ID of this reel item."""
        return self.data["owner"]["id"]

    @property
    def owner_profile_picture_url(self) -> str:
        """Returns the URL of the owner's profile picture of this reel item."""
        return self.data["owner"]["profile_pic_url"]

    def owner_profile_picture(self) -> MediaItem:
        """Returns a 'MediaItem' that represents the owner's profile picture of this reel item."""
        return MediaItem("GraphImage", self.owner_profile_picture_url, 150, 150)

    @property
    def created_time(self) -> int:
        """Returns the created time (timestamp) of this reel item."""
        return int(self.data["taken_at_timestamp"])

    @property
    def expire_time(self) -> int:
        """Returns the expire time in timestamp of this reel item."""
        return int(self.data["expiring_at_timestamp"])

    @property
    def cta_url(self) -> Optional[str]:
        """Returns the 'swipe up for more' URL of this reel item."""
        return self.data["story_cta_url"]


class Post(AsDictMixin, DataGetterMixin):
    """Represents a Post entity."""

    info_vars = ("shortcode", "url", "typename", "id", "owner_username", "owner_id", "owner_profile_picture_url",
                 "created_time", "caption", "media_count", "likes_count", "comments_count")

    @classmethod
    def from_shortcode(cls, insta, shortcode: str):
        """Returns a 'Post' instance by shortcode."""
        post = cls(insta, {"shortcode": shortcode})
        post._obtain_full_data()
        return post

    def __init__(self, insta, data: dict):
        self._insta = insta
        self._init_data = data
        self._full_data = None
        self.shortcode = data["shortcode"]

    def _obtain_full_data(self):
        if self._full_data is None:
            logger.debug("Fetching initial json data of Post(shortcode='{}')...".format(self.shortcode))
            self._full_data = self._insta._fetch_json_data(POST_URL.format(shortcode=self.shortcode))["shortcode_media"]

    def __repr__(self) -> str:
        return "Post(shortcode='{0}', typename='{1}')".format(self.shortcode, self.typename)

    def __eq__(self, other) -> bool:
        return isinstance(other, Post) and self.shortcode == other.shortcode and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.shortcode)

    def __len__(self) -> int:
        return self.media_count

    def __getitem__(self, index: int) -> MediaItem:
        return self.media_items()[index]

    def __iter__(self) -> MediaItem:
        for media in self.media_items():
            yield media

    @property
    def url(self) -> str:
        """Returns the URL of this post."""
        return "https://instagram.com/p/" + self.shortcode

    @property
    def typename(self) -> str:
        """Returns the typename of this post (one of 'GraphImage', 'GraphVideo', 'GraphSidecar')."""
        return self._find_or_get("__typename")

    @property
    def id(self) -> str:
        """Returns the ID of this post."""
        return self._find_or_get("id")

    @property
    def owner_username(self) -> str:
        """Returns the owner's username this post."""
        return self._find_or_get("owner")["username"]

    @property
    def owner_id(self) -> str:
        """Returns the owner's ID of this post."""
        return self._find_or_get("owner")["id"]

    @property
    def owner_profile_picture_url(self) -> str:
        """Returns the URL of the owner's profile picture of this post."""
        return self._find_or_get("owner", "profile_pic_url")

    def owner_profile_picture(self) -> MediaItem:
        """Returns a 'MediaItem' object of the owner's profile picture of this post."""
        return MediaItem("GraphImage", self.owner_profile_picture_url, 150, 150)

    @property
    def created_time(self) -> int:
        """Returns the created_time (timestamp) of this post."""
        return int(self._find_or_get("taken_at_timestamp"))

    @property
    def caption(self) -> str:
        """Returns the caption of this post."""
        edges = self._find_or_get("edge_media_to_caption", "edges")
        if not edges:
            return ""
        return edges[0]["node"]["text"]

    @property
    def likes_count(self) -> int:
        """Returns the amount of likes of this post."""
        return self._find_or_get("edge_media_preview_like")["count"]

    @property
    def comments_count(self) -> int:
        """Returns the amount of comments of this post."""
        try:
            return self._find_or_get("edge_media_preview_comment")["count"]
        except KeyError:
            # fallback
            return self._find_or_get("edge_media_to_parent_comment")["count"]

    @property
    def media_count(self) -> int:
        """Returns the amount of media items in this post."""
        return len(self.media_items())

    def media_items(self) -> List[MediaItem]:
        """Returns a list of 'MediaItem' of this post."""
        self._obtain_full_data()
        return MediaItem.compose_items(self._full_data)

    def likes(self) -> Group:
        """Retrieves likes of this post in the form of usernames.

        Returns:
            A 'Group' object that yields 'Profile' objects.
        """
        logger.info("Retrieving likes of :{0}".format(self.shortcode))
        variables = {"shortcode": self.shortcode}
        nodes = self._insta._graphql_query_edges(QUERYHASH_LIKES, variables, "shortcode_media", "edge_liked_by")
        return Group(next(nodes), (Profile(self._insta, node) for node in nodes))

    def comments(self):
        """Retrieves likes of this post in the form of usernames.

        Returns:
            - An integer that idicates the estimated amount of items.
            - A generator that yields 'CommentItem' -> namedtuple(author, text, created_time).
        """
        logger.info("Retrieving comments of :{0}".format(self.shortcode))
        variables = {"shortcode": self.shortcode}
        nodes = self._insta._graphql_query_edges(QUERYHASH_COMMENTS, variables, "shortcode_media", "edge_media_to_comment")
        return next(nodes), (CommentItem(node["owner"]["username"], node["text"], node["created_at"]) for node in nodes)

    def download(self, dest: str = None, *, write: bool = True, verify: bool = True,
                 on_item_start: Callable = None, on_item_finish: Callable = None, on_item_error: Callable = None):
        """Download all media items of this post.

        Arguments:
            dest: Path to the destination directory.
            write: Write file to disk if True, write to memory otherwise.
            verify: Verify file integrity if True, check the size of file in bytes otherwise. See 'MediaItem.download()'.
            on_item_start: A callable (Post, int, MediaItem). Called on start of each item.
            on_item_finish: A callable (Post, int, MediaItem, str). Called on finish of each item.
            on_item_error: A callable (Post, int, MediaItem, Exception). Called on error of each item.
        """
        dest = os.path.abspath(dest or "./")
        media_items = self.media_items()
        multi = self.media_count > 1
        subdest = os.path.join(dest, self.shortcode) if multi else None
        if subdest and not os.path.isdir(subdest):
            os.mkdir(subdest)

        logger.debug("Downloading {0} ({1} media) [{2}]...".format(repr(self), len(media_items), self.typename))
        logger.debug("Dest: " + dest)
        for i, item in enumerate(media_items):
            if on_item_start is not None:
                on_item_start(self, i, item)
            try:
                filename = str(i) if multi else self.shortcode
                file_path = item.download(subdest or dest, filename, write=write, verify=verify)
                if file_path is not None:
                    set_mtime(file_path, self.created_time)
                if on_item_finish is not None:
                    on_item_finish(self, i, item, file_path)
            except Exception as e:
                # NOTE: if the Post has multiple media items to download, the occurrence of exception will NOT interrupt
                # the whole download of the post, unless user reraises the exception in 'on_item_error()'.
                exc_type, exc_value, tb = sys.exc_info()
                logger.error("{}: {}".format(exc_type.__name__, exc_value))
                logger.debug("".join(traceback.format_tb(tb)))
                if on_item_error is not None:
                    on_item_error(self, i, item, e)
                continue


class IGTV(Post):
    """Represents an IGTV Post entity."""

    info_vars = ("shortcode", "url", "typename", "id", "owner_username", "owner_id", "owner_profile_picture_url",
                 "created_time", "caption", "media_count", "likes_count", "comments_count", "title", "duration")

    def __init__(self, insta, data: dict):
        # In fact, the URL of a IGTV Post is 'instagram.com/tv/{shortcode}'
        # but I found out that using 'instagram.com/p/{shortcode}' is just the same, since it is also considered as a Post
        super().__init__(insta, data)

    def __repr__(self) -> str:
        return "IGTV(title='{0}', shortcode='{1}')".format(self.title, self.shortcode)

    @property
    def title(self) -> str:
        """Returns the title of this IGTV post."""
        return self._find_or_get("title")

    @property
    def duration(self) -> float:
        """Returns the video duration of this IGTV post."""
        return float(self._find_or_get("video_duration"))

    @property
    def view_count(self) -> int:
        """Returns the video view count of this IGTV post."""
        return self._find_or_get("video_view_count")


class Story(AsDictMixin):
    """Represents a Story entity."""

    info_vars = ("typename", "id", "reel_count")

    def __init__(self, data: dict):
        self.data = data

    def __repr__(self):
        return NotImplemented

    def __eq__(self, other) -> bool:
        return isinstance(other, Story) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __len__(self) -> int:
        return self.reel_count

    def __getitem__(self, index: int) -> ReelItem:
        return self.reel_items()[index]

    def __iter__(self) -> ReelItem:
        for reel in self.reel_items():
            yield reel

    @property
    def typename(self) -> str:
        """Returns the typename of this story."""
        return self.data["__typename"]

    @property
    def id(self) -> str:
        """Returns the ID of this story."""
        return self.data["id"]

    @property
    def reel_count(self) -> int:
        """Returns the amount of reel items in this story."""
        return len(self.reel_items())

    def reel_items(self) -> List[ReelItem]:
        """Returns a list of reel items of this story."""
        return ReelItem.compose_items(self.data)

    def download(self, dest: str = None, *, write: bool = True, verify: bool = True,
                 on_item_start: Callable = None, on_item_finish: Callable = None, on_item_error: Callable = None):
        """Download all reel items of this story.

        Arguments:
            dest: Path to the destination directory.
            write: Write file to disk if True, write to memory otherwise.
            verify: Verify file integrity if True, check the size of file in bytes otherwise. See 'MediaItem.download()'.
            on_item_start: A callable (Story, int, ReelItem). Called on start of each item.
            on_item_finish: A callable (Story, int, ReelItem, str). Called on finish of each item.
            on_item_error: A callable (Story, int, ReelItem, Exception). Called on error of each item.
        """
        dest = os.path.abspath(dest or "./")
        reel_items = self.reel_items()
        logger.debug("Downloading {0} ({1} media) [{2}]...".format(repr(self), len(reel_items), self.typename))
        logger.debug("Dest: " + dest)

        for i, item in enumerate(reel_items):
            if on_item_start is not None:
                on_item_start(self, i, item)
            try:
                filename = to_datetime(item.created_time)
                file_path = item.download(dest, filename, write=write, verify=verify)
                if file_path is not None:
                    set_mtime(file_path, item.created_time)
                if on_item_finish is not None:
                    on_item_finish(self, i, item, file_path)
            except Exception as e:
                # NOTE: if the Story has multiple reel items to download, the occurrence of exception will NOT interrupt
                # the whole download of the story, unless user reraises the exception in 'on_item_error()'.
                exc_type, exc_value, tb = sys.exc_info()
                logger.error("{}: {}".format(exc_type.__name__, exc_value))
                logger.debug("".join(traceback.format_tb(tb)))
                if on_item_error is not None:
                    on_item_error(self, i, item, e)
                continue


class UserStory(Story):
    """Represents a Story entity that belongs to a Profile."""

    info_vars = ("typename", "id", "latest_reel_media", "reel_count", "owner_username", "owner_id", "owner_profile_picture_url", "seen_time")

    def __init__(self, data: dict):
        super().__init__(data)

    def __repr__(self) -> str:
        return "UserStory(owner_username='{0}', typename='{1}')".format(self.owner_username, self.typename)

    @property
    def latest_reel_media(self) -> int:
        """Returns the created time of the latest reel media (timestamp) of this story."""
        return int(self.data["latest_reel_media"])

    @property
    def owner_username(self) -> str:
        """Returns the owner's username of this story."""
        return self.data["owner"]["username"]

    @property
    def owner_id(self) -> str:
        """Returns the owner's ID of this story."""
        return self.data["owner"]["id"]

    @property
    def owner_profile_picture_url(self) -> str:
        """Returns the URL of the owner's profile picture of this story."""
        return self.data["owner"]["profile_pic_url"]

    def owner_profile_picture(self) -> MediaItem:
        """Returns a 'MediaItem' object of the owner's profile picture of this story."""
        return MediaItem("GraphImage", self.data["owner"]["profile_pic_url"], 150, 150)

    @property
    def seen_time(self) -> Optional[int]:
        """Returns the seen time (timestamp) of this story if it has been seen, None otherwise."""
        if self.data["seen"]:
            return int(self.data["seen"])


class HashtagStory(Story):
    """Represents a Story entity that belongs to a Hashtag."""

    info_vars = ("typename", "id", "latest_reel_media", "reel_count", "tagname")

    def __init__(self, data: dict):
        super().__init__(data)

    def __repr__(self) -> str:
        return "HashtagStory(tagname='{0}', typename='{1}')".format(self.tagname, self.typename)

    @property
    def latest_reel_media(self) -> int:
        """Returns the created time of the latest reel media (timestamp) of this story."""
        return int(self.data["latest_reel_media"])

    @property
    def tagname(self) -> str:
        """Returns the hashtag's tag name of this story."""
        return self.data["owner"]["name"]


class Highlight(Story):
    """Represents a Highlight entity."""

    info_vars = ("typename", "id", "title", "cover_media_thumbnail", "owner_username", "owner_id", "owner_profile_picture_url", "reel_count")

    def __init__(self, data: dict):
        super().__init__(data)

    def __repr__(self) -> str:
        return "Highlight(title='{}')".format(self.title)

    @property
    def title(self) -> str:
        """Returns the title of this highlight."""
        return self.data["title"]

    @property
    def cover_media_thumbnail(self) -> str:
        """Returns the URL of the cover thumbnail of this highlight."""
        return self.data["cover_media"]["thumbnail_src"]

    @property
    def owner_username(self) -> str:
        """Returns the owner's username of this highlight."""
        return self.data["owner"]["username"]

    @property
    def owner_id(self) -> str:
        """Returns the owner's ID of this highlight."""
        return self.data["owner"]["id"]

    @property
    def owner_profile_picture_url(self) -> str:
        """Returns the URL of the owner's profile picture of this highlight."""
        return self.data["owner"]["profile_pic_url"]

    def owner_profile_picture(self) -> MediaItem:
        """Returns a 'MediaItem' object of the owner's profile picture of this highlight."""
        return MediaItem("GraphImage", self.data["owner"]["profile_pic_url"], 150, 150)


class Profile(AsDictMixin, DataGetterMixin):
    """Represents a user Profile entity."""

    info_vars = ("username", "url", "id", "fullname", "biography", "website", "followers_count", "followings_count",
                 "mutual_followers_count", "is_verified", "is_private", "profile_picture_url")

    @classmethod
    def from_id(cls, insta, id: str):
        """Returns a Post instance from user ID.
        * This takes one more step to obtain the username of the user.
        """
        username = get_username_from_userid(id)
        return cls.from_username(insta, username)

    @classmethod
    def from_username(cls, insta, username: str):
        """Returns a Post instance from username."""
        profile = cls(insta, {"username": username})
        profile._obtain_full_data()
        return profile

    def __init__(self, insta, data: dict):
        self._insta = insta
        self._init_data = data
        self._full_data = None
        self.username = data["username"]

    def _obtain_full_data(self):
        if self._full_data is None:
            logger.debug("Obtaining full data of Profile(username='{}')".format(self.username))
            self._full_data = self._insta._fetch_json_data(PROFILE_URL.format(username=self.username))["user"]

    def __repr__(self):
        return "Profile(username='{0}', id='{1}')".format(self.username, self.id)

    def __eq__(self, other):
        return isinstance(other, Profile) and self.username == other.username and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def url(self) -> str:
        """Returns the URL of this profile."""
        return "https://instagram.com/" + self.username

    @property
    def id(self) -> str:
        """Returns the ID (user ID) of this profile."""
        return self._find_or_get("id")

    @property
    def fullname(self) -> str:
        """Returns the fullname of this profile."""
        return self._find_or_get("full_name")

    @property
    def biography(self) -> str:
        """Returns the biography of this profile."""
        return self._find_or_get("biography")

    @property
    def website(self) -> Optional[str]:
        """Returns the website of this profile if applicable, None otherwise."""
        return self._find_or_get("external_url")

    @property
    def followers_count(self) -> int:
        """Returns the amount of followers this profile has."""
        return self._find_or_get("edge_followed_by")["count"]

    @property
    def followings_count(self) -> int:
        """Returns the amount of users this profile is following."""
        return self._find_or_get("edge_follow")["count"]

    @property
    def mutual_followers_count(self) -> int:
        """Returns the amount of mutual followers of this profile."""
        return self._find_or_get("edge_mutual_followed_by")["count"]

    @property
    def is_verified(self) -> bool:
        """Returns True if this profile is verified, False otherwise"""
        return self._find_or_get("is_verified")

    @property
    def is_private(self) -> bool:
        """Returns True if this profile is private, False otherwise"""
        return self._find_or_get("is_private")

    @property
    def profile_picture_url(self) -> str:
        """Retunrs the URL of the profile picture of this profile."""
        return self._find_or_get("profile_pic_url_hd")

    def profile_picture(self) -> MediaItem:
        """Retunrs a 'MediaItem' of the profile picture of this profile."""
        return MediaItem("GraphImage", self.profile_picture_url, 320, 320)

    def timeline_posts(self) -> PostGroup:
        """Retrieves timeline posts of this profile.

        Returns:
            A 'PostGroup' object.
        """
        self._obtain_full_data()
        logger.info("Retrieving timeline posts of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_TIMELINE, variables, "user", "edge_owner_to_timeline_media", self._full_data)
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))

    def saved_posts(self) -> PostGroup:
        """Retrieves saved posts of this profile.
        * Requires authentication.

        Returns:
            A 'PostGroup' object.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        self._obtain_full_data()
        logger.info("Retrieving saved posts of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_SAVED, variables, "user", "edge_saved_media", self._full_data)
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))

    def tagged_posts(self) -> PostGroup:
        """Retrieves tagged posts of this profile.

        Returns:
            A 'PostGroup' object.
        """
        logger.info("Retrieving tagged posts of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_TAGGED, variables, "user", "edge_user_to_photos_of_you")
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))

    def igtv_posts(self) -> PostGroup:
        """Retrieves IGTV posts of this profile.

         Returns:
            A 'PostGroup' object.
        """
        self._obtain_full_data()
        logger.info("Retrieving IGTV video posts of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_IGTV, variables, "user", "edge_felix_video_timeline", self._full_data)
        return Group.of_posts(next(nodes), (IGTV(self._insta, node) for node in nodes))

    def followers(self) -> Group:
        """Retrieves followers of this profile.
        * Requires authentication.

        Returns:
            A 'Group' object that yields 'Profile' instances.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving followers of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_FOLLOWERS, variables, "user", "edge_followed_by")
        return Group(next(nodes), (Profile(self._insta, node) for node in nodes))

    def followings(self) -> Group:
        """Retrieves profiles that this profile is following.
        * Requires authentication.

        Returns:
            A 'Group' object that yields 'Profile' instances.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving followings of @{0}".format(self.username))
        variables = {"id": self.id}
        nodes = self._insta._graphql_query_edges(QUERYHASH_FOLLOWINGS, variables, "user", "edge_follow")
        return Group(next(nodes), (Profile(self._insta, node) for node in nodes))

    def highlights(self) -> List[Highlight]:
        """Retrieves highlights of this profile.
        * Requires authentication.

        Returns:
            A list of 'Highlight' objects.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving story highlights of @{0}".format(self.username))
        # [1] retrieve all available highlights of this user
        variables = {"user_id": self.id, "include_chaining": False, "include_reel": False,
                     "include_suggested_users": False, "include_logged_out_extras": False, "include_highlight_reels": True}
        data = self._insta._graphql_query(QUERYHASH_HIGHLIGHTS, variables)["user"]["edge_highlight_reels"]
        nodes = [edge["node"] for edge in data["edges"]]
        if not nodes:
            logger.warning("No visible highlight is found for this profile.")
            return []
        # [2] do GraphQL query to get the reel items data of all highlights at once
        logger.debug("Fetching json data of highlights of @{} ...".format(self.username))
        variables = {"highlight_reel_ids": [str(node["id"]) for node in nodes], "precomposed_overlay": False, "show_story_viewer_list": False}
        url = QUERY_URL.format(QUERYHASH_REELITEMS, json.dumps(variables))
        data = self._insta._fetch_json_data(url)["reels_media"]
        hs = []
        for d in data:
            for node in nodes:
                if node["id"] == d["id"]:
                    d.update(node)
                    break
            else:
                continue
            # produce 'Highlight' object
            hs.append(Highlight(d))
        return hs

    def story(self) -> Optional[UserStory]:
        """Retrieves the currently visible story of this profile.
        * Requires authentication.

        Returns:
            A 'UserStory' object if applicable, None otherwise.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving story of @{0}".format(self.username))
        variables = {"reel_ids": [self.id], "precomposed_overlay": False, "show_story_viewer_list": False}
        data = self._insta._graphql_query(QUERYHASH_REELITEMS, variables)["reels_media"]
        if not data:
            logger.warning("No visible story is available now for this profile.")
            return
        return UserStory(data[0])


class Hashtag(DataGetterMixin):
    """Represents a Hashtag entity."""

    @classmethod
    def from_tagname(cls, insta, tagname: str):
        """Returns a Hashtag instance from tag name."""
        hashtag = cls(insta, {"name": tagname})
        hashtag._obtain_full_data()
        return hashtag

    def __init__(self, insta, data: dict):
        self._insta = insta
        self._init_data = data
        self._full_data = None
        self.tagname = data["name"]

    def _obtain_full_data(self):
        if self._full_data is None:
            logger.debug("Obtaining full data of Hashtag(tagname='{}')".format(self.tagname))
            self._full_data = self._insta._fetch_json_data(HASHTAG_URL.format(tagname=self.tagname))["hashtag"]

    def __repr__(self):
        return "Hashtag(tagname='{0}')".format(self.tagname)

    def __eq__(self, other):
        return isinstance(other, Hashtag) and self.tagname == other.tagname and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.tagname)

    @property
    def id(self) -> str:
        """Returns the ID of this hashtag."""
        return self._find_or_get("id")

    @property
    def profile_picture_url(self) -> str:
        """Returns the URl of the profile picture of this hashtag."""
        return self._find_or_get("profile_pic_url")

    def profile_picture(self) -> MediaItem:
        """Returns a 'MediaItem' of the profile picture of this hashtag."""
        return MediaItem("GraphImage", self.profile_picture_url, 320, 320)

    def top_posts(self) -> PostGroup:
        """Retrieves top posts if this hashtag.
        * Only 9 posts at most.

        Returns:
            A 'PostGroup' object.
        """
        self._obtain_full_data()
        logger.info("Retrieving top posts of #{0}".format(self.tagname))
        nodes = self._insta._graphql_query_edges("", {}, "hashtag", "edge_hashtag_to_top_posts", self._full_data)
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))

    def recent_posts(self) -> PostGroup:
        """Retrieves most recent posts if this hashtag.

        Returns:
            A 'PostGroup' object.
        """
        logger.info("Retrieving recent posts of #{0}".format(self.tagname))
        variables = {"tag_name": self.tagname}
        nodes = self._insta._graphql_query_edges(QUERYHASH_HASHTAG, variables, "hashtag", "edge_hashtag_to_media")
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))

    def story(self) -> Optional[HashtagStory]:
        """Retrieves the current visible Story of this hashtag.
        * Requires authentication.

        Returns:
            A 'HashtagStory' object.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving story of #{0}".format(self.tagname))
        variables = {"tag_names": [self.tagname], "precomposed_overlay": False, "show_story_viewer_list": False}
        data = self._insta._graphql_query(QUERYHASH_REELITEMS, variables)["reels_media"]
        if not data:
            logger.warning("No visible story is avaliable now for this hashtag.")
            return
        return HashtagStory(data[0])


class Explore:
    """Represents the Explore entity in the discover section."""

    def __init__(self, insta):
        self._insta = insta

    def __repr__(self):
        return "Explore()"

    def posts(self) -> PostGroup:
        """Retrieves posts of explore.
        * Requires authentication.

        Returns:
            A 'PostGroup' object.
        """
        if not self._insta.authenticated:
            raise AuthenticationRequired()
        logger.info("Retrieving explore posts...")
        nodes = self._insta._graphql_query_edges(QUERYHASH_EXPLORE, {}, "user", "edge_web_discover_media")
        return Group.of_posts(next(nodes), (Post(self._insta, node) for node in nodes))
