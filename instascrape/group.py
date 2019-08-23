import sys
import logging
import traceback
from typing import *
from threading import Thread, Event
from collections import deque, namedtuple

__all__ = ("Group", "PostGroup")
logger = logging.getLogger("instascrape")


class Group:
    """An intermediate class that holds a group of Post/Profile objects. Responsible for performing iteration and filtering."""

    @staticmethod
    def of_posts(*args, **kwargs) -> "PostGroup":
        """A factory method that produces a new 'PostGroup' instance."""
        return PostGroup(*args, **kwargs)

    def __init__(self, length: int, iterable: Generator):
        # iterable
        self.__total = length  # the first item yielded back from the generator is the estimated amount of items
        self.__iterable = iterable
        self.__cached_iterable = None
        # handling errors
        self._ignore_errors = False
        self._error_bucket = []
        self.__ErrorItem = namedtuple("ErrorItem", "name exc_type exc_value traceback")
        # iterator
        self._preload = False
        self.__iterator = self.__generator()  # default iterator
        # conditions
        self._limit = self.__total  # default limit -> all
        self._filter = lambda x: True  # default filter -> all return True

    @property
    def length(self) -> int:
        """Get the amount of items in this group.

        Returns:
            When no cache item is found ('self.__cached_iterable=None'),
                the 'limit' number set by the user (if applicable), or
                the total amount number yielded from the first result of 'self.__iterable' when 'limit' is greater than the total amount.
            When cache items are found,
                the '__len__' of list 'self.__cached_iterable', or
                the same conditions when no cache item is found, when the length of 'self.__cached_iterable' is smaller.
        """
        if self.__cached_iterable is None:
            return min(self.__total, self._limit)
        return max(len(self.__cached_iterable), min(self.__total, self._limit))

    def limit(self, value: Optional[int]) -> "Group":
        """To set the maximum amount of items will be yielded from this group."""
        self._limit = value if value is not None else self.__total
        return self

    def filter(self, checker: Optional[Callable]) -> "Group":
        """To set a filter which controls which items will be yielded from this group.

        Arguments:
            checker: A callable, i.e. function or lambda, that accepts one parameter -> the structure object.
        """
        self._filter = checker if checker is not None else (lambda x: True)
        return self

    def preload(self, value: bool) -> "Group":
        """To turn the 'preload' option on or off. If 'preload=True', this group will call the 'obtain_full_data()' method
        for each structure object when iterating through this group using at most 15 worker threads.
        Items will be yielded out after the 'preload' process finished.

        Note:
            If 'self.length' > 500, this option is forced to be disabled.
        """
        if value is True and self.length > 500:
            logger.warning("'preload' option is forced to be disabled when the estimated amount of items are (> 500)")
            value = False
        self._preload = value
        return self

    def ignore_errors(self, value: bool) -> "Group":
        """To turn the 'ignore_errors' option on or off. If 'ignore_errors=True', this group will collect all errors when
        during iteration. Collected errors can be obtained by calling the 'self.collect_errors()' method.
        """
        self._ignore_errors = value
        return self

    def has_error(self) -> bool:
        """Returns True when there is error collected, returns False otherwise."""
        return bool(self._error_bucket)

    def collect_errors(self) -> list:
        """To obtain collected errors raised during iteration.

        Returns:
            A list of 'ErrorItem' -> namedtuple(name, exc_type, exc_value, traceback).
        """
        return self._error_bucket

    def __repr__(self) -> str:
        return "Group(length={}, preload={})".format(self.length, self._preload)

    def __bool__(self) -> bool:
        return self.length > 0

    def __iter__(self):
        if self.__cached_iterable is None:
            logger.debug("{0}: no cache found. do cache in this iteration.".format(repr(self)))
            self._do_cache = True
            self.__cached_iterable = []
        else:
            logger.debug("{0}: found cached items. use them instead.".format(repr(self)))
            self._do_cache = False
            self.__iterable = iter(self.__cached_iterable)  # use cached items instead
        self.__iterator = self.__preloader() if self._preload else self.__generator()
        return self

    def __next__(self):
        if self.length <= 0:
            raise StopIteration()
        return next(self.__iterator)

    def __preloader(self):
        # TODO: use asyncio producer/consumer for simplicity and better performance ?
        logger.info("[*] Started Preloading")

        def worker(queue):
            while True:
                if not queue:
                    continue
                item = queue.popleft()
                if item is sentinel:
                    logger.debug("sentinel received -> suicide")
                    break
                try:
                    item._obtain_full_data()
                except Exception as e:
                    exc = sys.exc_info()
                    self._error_bucket.append(self.__ErrorItem(repr(item), *exc))
                    if not self._ignore_errors:
                        event.set()
                        return
                    logger.error("{0} -> {1}: {2}".format(repr(item), e.__class__.__name__, e))
                    logger.debug("".join(traceback.format_exception(*exc)))
                else:
                    results.append(item)

        def producer():
            # terminate when there is error raised
            counter = 0
            try:
                for item in self.__iterable:
                    # check limit
                    if counter >= self._limit:
                        break
                    # check filter
                    if not self._filter(item):
                        continue
                    # add to queue
                    if self._do_cache:
                        self.__cached_iterable.append(item)
                    queue.append(item)
                    counter += 1
                for _ in range(i):
                    queue.append(sentinel)
            except Exception as e:
                exc = sys.exc_info()
                self._error_bucket.append(self.__ErrorItem(repr(item), *exc))
                errors.append(e)
                event.set()

        event = Event()
        sentinel = object()
        queue = deque()  # item queue
        errors = []  # errors pipe exclusively for producer
        results = []

        # spawn workers
        i = min(15, self.length)
        threads = []
        logger.debug("using {0} workers...".format(i))
        for x in range(i):
            thread = Thread(target=worker, args=(queue,))
            thread.setName("Worker-{}".format(x))
            thread.setDaemon(True)
            thread.start()
            threads.append(thread)

        # start producer
        thread = Thread(target=producer)
        thread.setName("Producer")
        thread.setDaemon(True)
        thread.start()
        threads.append(thread)

        while True:
            if event.is_set():
                logger.debug("(stop) error event flag -> True")
                break
            if all([not t.is_alive() for t in threads]):
                logger.debug("(stop) workers alive -> False")
                break
        if errors:
            raise errors[0]
        if self._error_bucket and not self._ignore_errors:
            e = self._error_bucket[0]
            raise e.exc_type(e.exc_value)

        logger.info("[*] Completed Preloading")
        for item in results:
            yield item
        if len(results) < self.length:
            logger.warning("Only {}/{} items are returned.".format(len(results), self.length))

    def __generator(self):
        counter = 0
        for item in self.__iterable:
            # check limit
            if self._limit is not None and counter >= self._limit:
                break
            # check filter
            if not self._filter(item):
                continue
            # add to queue
            if self._do_cache:
                self.__cached_iterable.append(item)
            try:
                # item._obtain_full_data()
                yield item
            except Exception as e:
                exc = sys.exc_info()
                self._error_bucket.append(self.__ErrorItem(repr(item), *exc))
                if not self._ignore_errors:
                    raise
                logger.error("{0} -> {1}: {2}".format(repr(item), e.__class__.__name__, e))
                logger.debug("".join(traceback.format_exception(*exc)))
            counter += 1
        if counter < self.length:
            logger.warning("Only {}/{} items are returned.".format(counter, self.length))


class PostGroup(Group):
    """An intermediate class that holds a group of 'Post' objects. Responsible for performing iteration and filtering.
    Provides an additional method for downloading the 'Post' objects in this group."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self) -> str:
        return "PostGroup(length={}, preload={})".format(self.length, self._preload)

    def download_all(self, dest: str = None, *,
                     on_post_start: Callable = None, on_post_finish: Callable = None, on_post_error: Callable = None,
                     on_item_start: Callable = None, on_item_finish: Callable = None, on_item_error: Callable = None):
        """Does iteration and downloads all post items of this group.

        Arguments:
            dest: Path to the destination directory. (default: current working directory '.')
            on_post_start: A callable that must accept a 'Post' object as the first argument. Called on start of every posts.
            on_post_finish: A callable that must accept a 'Post' object as the first argument. Called on finish of every posts.
            on_post_error: A callable that must accept a 'Post' object as the first argument and an 'Exception' object as the second argument. Called on error of every posts (if applicable).
            on_item_start: See 'structures.Post.download()'
            on_item_finish: See 'structures.Post.download()'
            on_item_error: See 'structures.Post.download()'
        """
        for post in self:
            if on_post_start is not None:
                on_post_start(post)
            try:
                post.download(dest, on_item_start=on_item_start, on_item_finish=on_item_finish, on_item_error=on_item_error)
                if on_post_finish is not None:
                    on_post_finish(post)
            except Exception as e:
                # NOTE: The occurrence of exception here will NOT interrupt the whole download progress of the posts,
                # unless user reraises the exception in 'on_post_error()'.
                exc_type, exc_value, tb = sys.exc_info()
                logger.error("{}: {}".format(exc_type.__name__, exc_value))
                logger.debug("".join(traceback.format_tb(tb)))
                if on_post_error is not None:
                    on_post_error(post, e)
                continue
