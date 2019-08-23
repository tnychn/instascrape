import os
import sys
import ast
import time
import traceback
from functools import partial
from collections import OrderedDict, namedtuple

from tqdm import tqdm
from colorama import Fore, Style

from instascrape import Instagram
from instascrape.commands import error_print, warn_print, prompt, load_obj, error_catcher
from instascrape.utils import to_datetime, data_dumper


def progress_bar(total: int, sub: bool = False, hide: bool = False):
    fmt = "{desc}  {percentage:3.0f}% |{bar}| {n_fmt}/{total_fmt} [{elapsed}{postfix}]" + Fore.RESET
    desc = "[" + "⧗ Loading".center(15) + "]" if not sub else "[" + "❏ Multiple".center(15) + "]"
    bar = tqdm(total=total, ascii=sub, bar_format=fmt, desc=desc, file=sys.stdout, disable=hide, maxinterval=1, smoothing=True, dynamic_ncols=True)
    return bar


def profile_picture_downloader(media, final_dest: str, filename: str):
    print(Fore.YELLOW + "⤓ Downloading...", end="")
    with error_catcher(do_exit=False):
        file_path = media.download(final_dest, filename)
    print(Fore.GREEN + "\r✓ Download Finished => {}{}".format(Fore.RESET, file_path or "Exisiting!"))


def post_downloader(insta, post, debug: bool, final_dest: str, dump_metadata: bool, dump_comments: bool, dump_likes: bool):

    def on_item_start(_, __, item):
        bar.set_description_str("[" + "⤓ Downloading".center(15) + "]")
        bar.set_postfix_str("({}) {}".format(post.shortcode, item.typename))

    def on_item_finish(_, __, ___, file_path):
        nonlocal downs, existings
        if file_path is not None:
            downs += 1
        else:
            existings += 1
            bar.set_description_str("[" + "♻︎ Existing".center(15) + "]")
            time.sleep(0.1)
        bar.update(1)

    def on_item_error(post, i, __, e):
        bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
        if not debug:
            tqdm.write(Fore.RED + "✖︎ [{} ({})] {}: {}".format(post.shortcode, i, e.__class__.__name__, str(e)))

    try:
        downs = existings = 0
        bar = progress_bar(total=post.media_count, hide=debug)
        post.download(final_dest, on_item_start=on_item_start, on_item_finish=on_item_finish, on_item_error=on_item_error)
        if any((dump_metadata, dump_comments, dump_likes)):
            bar.set_description_str("[" + "Ⓓ Dumping".center(15) + "]")
            data = {}
            # TODO: show dump progress using 'tqdm.write' with carriage return (\r)
            if dump_metadata:
                data.update(post.as_dict(extra=True))
                data.update({"media_items": [d.as_dict() for d in post.media_items()]})
            if dump_comments:
                comments = post.comments()
                comments = [comment._asdict() for comment in comments[1]]
                data.update({"comments": list(comments)})
            if dump_likes:
                likes = post.likes()
                likes = [like.username for like in likes]
                data.update({"likes": list(likes)})
            data_dumper(final_dest, post.shortcode, data)
        bar.set_description_str(Fore.GREEN + "[" + "✔︎ Finished".center(15) + "]")
    except Exception as e:
        exc_type, exc_value, tb = sys.exc_info()
        insta.logger.error("{}: {}".format(exc_type.__name__, exc_value))
        insta.logger.debug("".join(traceback.format_tb(tb)))
        if not debug:
            tqdm.write(Fore.RED + "✖︎ {}: {}".format(exc_type.__name__, str(e)))
        bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
    except KeyboardInterrupt:
        bar.set_description_str(Fore.MAGENTA + "[" + "⌧ Interrupted".center(15) + "]")
        raise
    finally:
        bar.close()
    return downs, existings


def story_downloader(story, debug: bool, final_dest: str, dump_metadata: bool):

    def on_item_start(_, __, item):
        bar.set_description_str("[" + "⤓ Downloading".center(15) + "]")
        bar.set_postfix_str(item.typename)

    def on_item_finish(_, __, item, file_path):
        nonlocal downs, existings
        if file_path is not None:
            downs += 1
        else:
            existings += 1
            bar.set_description_str("[" + "♻︎ Existing".center(15) + "]")
            time.sleep(0.1)
        if dump_metadata:
            bar.set_description_str("[" + "Ⓓ Dumping".center(15) + "]")
            data_dumper(final_dest, to_datetime(item.created_time), item.as_dict(extra=True))
        bar.update(1)

    def on_item_error(_, __, ___, e):
        bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
        if not debug:
            tqdm.write(Fore.RED + "✖︎ {}: {}".format(e.__class__.__name__, str(e)))

    try:
        downs = existings = 0
        bar = progress_bar(story.reel_count, hide=debug)
        story.download(final_dest, on_item_start=on_item_start, on_item_finish=on_item_finish, on_item_error=on_item_error)
        if dump_metadata:
            data_dumper(final_dest, "story", story.as_dict(extra=True))
        bar.set_description_str(Fore.GREEN + "[" + "✔︎ Finished".center(15) + "]")
    except KeyboardInterrupt:
        bar.set_description_str(Fore.MAGENTA + "[" + "⌧ Interrupted".center(15) + "]")
        raise
    finally:
        bar.close()
    return downs, existings


def highlights_downloader(insta, highlights: list, debug: bool, final_dest: str, limit: int, dump_metadata: bool):

    def on_item_start(_, __, item):
        if subbar is not None:
            subbar.set_postfix_str(item.typename)

    def on_item_finish(_, __, item, file_path):
        nonlocal downs, existings
        if file_path is not None:
            downs += 1
        else:
            existings += 1
            bar.set_description_str("[" + "♻︎ Existing".center(15) + "]")
            subbar.set_description_str("[" + "↻ Verifying".center(15) + "]")
            time.sleep(0.1)
        if dump_metadata:
            bar.set_description_str("[" + "Ⓓ Dumping".center(15) + "]")
            subbar.set_description_str("[" + "↻ Verifying".center(15) + "]")
            data_dumper(subdir, to_datetime(item.created_time), item.as_dict(extra=True))
        subbar.update(1)

    def on_item_error(_, i, ___, e):
        # # Interrupt the download process of the current highlight once it encounters an error
        # raise e from e
        # Ignore error and move on to the download process of the next reel item of the current highlight
        if subbar is not None:
            subbar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
        else:
            bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")

        if not debug:
            tqdm.write(Fore.RED + "✖︎ [{} ({})] {}: {}".format(highlight.title[:12], i, e.__class__.__name__, str(e)))

    try:
        highlights = highlights[:len(highlights) if limit is None else limit]
        downs = existings = 0
        bar = progress_bar(total=len(highlights), hide=debug)
        for highlight in highlights[:len(highlights) if limit is None else limit]:
            subdir = os.path.join(final_dest, highlight.title)
            subbar = progress_bar(total=highlight.reel_count, sub=True, hide=debug or highlight.reel_count == 1)
            bar.set_description_str("[" + "⤓ Downloading".center(15) + "]")
            bar.set_postfix_str("(" + highlight.title[:12] + ("..." if len(highlight.title) > 12 else "") + ")")
            if not os.path.isdir(subdir):
                os.mkdir(subdir)
            highlight.download(subdir, on_item_start=on_item_start, on_item_finish=on_item_finish, on_item_error=on_item_error)
            if dump_metadata:
                bar.set_description_str("[" + "Ⓓ Dumping".center(15) + "]")
                data_dumper(os.path.join(final_dest, highlight.title), "highlight", highlight.as_dict(extra=True))
            bar.update(1)
        bar.set_description_str(Fore.GREEN + "[" + "✔︎ Finished".center(15) + "]")
    except Exception as e:
        exc_type, exc_value, tb = sys.exc_info()
        insta.logger.error("{}: {}".format(exc_type.__name__, exc_value))
        insta.logger.debug("".join(traceback.format_tb(tb)))
        if not debug:
            tqdm.write(Fore.RED + "✖︎ {}: {}".format(exc_type.__name__, str(e)))
        bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
    except KeyboardInterrupt:
        bar.set_description_str(Fore.MAGENTA + "[" + "⌧ Interrupted".center(15) + "]")
        raise
    finally:
        bar.close()
    return downs, existings


def posts_group_downloader(group, debug: bool, final_dest: str, filterstr: str, limit: int, preload: bool, dump_metadata: bool, dump_comments: bool, dump_likes: bool):

    def on_post_start(post):
        # initialize sub bar
        nonlocal subbar
        subbar = progress_bar(total=post.media_count, sub=True, hide=debug or post.media_count == 1)
        # update parent bar
        bar.set_description_str("[" + "⤓ Downloading".center(15) + "]")
        bar.set_postfix_str("({}) {}".format(post.shortcode, post.typename))

    def on_post_finish(post):
        # TODO: show dump progress using 'tqdm.write' with carriage return (\r)
        if any((dump_metadata, dump_comments, dump_likes)):
            bar.set_description_str("[" + "Ⓓ Dumping".center(15) + "]")
            data = {}
            if dump_metadata:
                data.update(post.as_dict(extra=True))
                data.update({"media_items": [d.as_dict() for d in post.media_items()]})
            if dump_comments:
                comments = post.comments()
                comments = [comment._asdict() for comment in comments[1]]
                data.update({"comments": list(comments)})
            if dump_likes:
                likes = post.likes()
                likes = [like.username for like in likes]
                data.update({"likes": list(likes)})
            data_dumper(final_dest, post.shortcode, data)
        bar.update(1)
        nonlocal subbar
        if subbar is not None:
            subbar.close()
            subbar = None

    def on_post_error(post, e):
        # error has already been logged at this time
        nonlocal subbar
        if subbar is not None:
            subbar.close()
            subbar = None
        bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
        if not debug:
            tqdm.write(Fore.RED + "✖︎ [{}] {}: {}".format(post.shortcode, e.__class__.__name__, str(e)))

    def on_item_start(_, __, item):
        if subbar is not None:
            subbar.set_postfix_str(item.typename)

    def on_item_finish(_, __, ___, file_path):
        nonlocal downs, existings
        if file_path is not None:
            downs += 1
        else:
            existings += 1
            bar.set_description_str("[" + "♻︎ Existing".center(15) + "]")
            subbar.set_description_str("[" + "↻ Verifying".center(15) + "]")
            time.sleep(0.1)
        subbar.update(1)

    def on_item_error(post, i, __, e):
        # # Interrupt the download process of the current post once it encounters an error
        # raise e from e
        # Ignore error and move on to the download process of the next media item of the current post
        if subbar is not None:
            subbar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")
        else:
            bar.set_description_str(Fore.RED + "[" + "✘ Failed".center(15) + "]")

        if not debug:
            tqdm.write(Fore.RED + "✖︎ [{} ({})] {}: {}".format(post.shortcode, i, e.__class__.__name__, str(e)))

    filterfunc = filterstr_to_filterfunc(filterstr)
    if preload and limit is None and group.length > 500:
        warn_print("Option 'preload' is forced to be disabled when trying to download more than 500 items.")
    try:
        group.filter(filterfunc if filterstr is not None else None).limit(limit).preload(preload).ignore_errors(True)
        downs = existings = 0
        bar = progress_bar(total=group.length, hide=debug)
        subbar = None
        group.download_all(final_dest,
                           on_post_start=on_post_start, on_post_finish=on_post_finish, on_post_error=on_post_error,
                           on_item_start=on_item_start, on_item_finish=on_item_finish, on_item_error=on_item_error)
        bar.set_description_str(Fore.GREEN + "[" + "✔︎ Finished".center(15) + "]")
        # NOTE: no need to use 'except' to catch error here
        # since all errors encountered in 'Group' iteration are ignored (ignore_errors=True).
        # -> summarize ignored errors in 'finally'
    except KeyboardInterrupt:
        bar.set_description_str(Fore.MAGENTA + "[" + "⌧ Interrupted".center(15) + "]")
        raise
    finally:
        bar.close()
        errors = group.collect_errors()
        if errors:
            print("\33[2K\r", end="")  # erase the current line (remove the leftover progress bar)
            print(Fore.RED + "  [{} Errors Collected During Posts Retrieving]".format(len(errors)))
            for i, error in enumerate(errors):
                print(Fore.RED + "> {} -> {}: {}".format(Fore.WHITE + Style.BRIGHT + error.name + Style.RESET_ALL +
                                                         Fore.RED, Style.BRIGHT + error.exc_type.__name__, error.exc_value))
    return downs, existings


def filterstr_to_filterfunc(filterstr: str):

    def filterfunc(struct):

        class FilterStrTransformer(ast.NodeTransformer):

            def visit_Name(self, node: ast.Name):
                # check whether the attribute name the user specified exists
                if not hasattr(struct, node.id):
                    raise AttributeError("'{}' does not have attribute: '{}'".format(struct.__class__.__name__, node.id))
                if str(node.id) not in struct.info_vars:
                    raise AttributeError("'{}' does not have info var: '{}'".format(struct.__class__.__name__, node.id))
                # assign the 'struct' to get the attribute of the structure (x -> struct.x)
                new_node = ast.Attribute(ast.copy_location(ast.Name("struct", ast.Load()), node), node.id,
                                         ast.copy_location(ast.Load(), node))
                return ast.copy_location(new_node, node)

        input_filename = "<command line filter option>"
        compiled_filter = compile(FilterStrTransformer().visit(ast.parse(filterstr, filename=input_filename, mode="eval")),
                                  filename=input_filename, mode="eval")
        return bool(eval(compiled_filter, {"struct": struct}))

    return filterfunc


def download_handler(**args):
    # Try to load object
    guest = False
    insta = load_obj()
    if insta is None:
        guest = True
        insta = Instagram()

    # Validate target
    parser = args.get("parser")
    targets = args.get("target")
    for target in targets:
        if len(target) <= 1:
            parser.error("invalid target parsed: '{}'".format(target))
        if target in ("saved", "explore"):
            if len(targets) > 1:
                parser.error("no more than one target should be specified for ':', 'saved' & 'explore'")
        else:
            if target[0] not in ("@", "#", ":"):
                parser.error("invalid identifier of target: '{}'".format(target))
        if target[0] != targets[0][0]:
            parser.error("all targets must be the same type")
    identifier = targets[0] if targets[0] in ("saved", "explore") else targets[0][0]

    debug = args.get("debug")
    # Gather posts options
    limit = args.get("limit")
    posts_filter_str = args.get("posts_filter")

    dump_comments = args.get("dump_comments")
    dump_likes = args.get("dump_likes")
    preload = args.get("preload")
    # Gather download options
    dest = os.path.abspath(args.get("dest"))
    dump_metadata = args.get("dump_metadata")

    all_media_types = ("timeline", "tagged", "igtv", "top", "recent", "story", "highs", "pic")
    specified_media_types = {t for t in all_media_types if args.get(t) is True}
    Job = namedtuple("Job", "func_name dest_dir")
    types_dict = {
        "@": OrderedDict((
            ("timeline", Job("timeline_posts", "timeline@{name}")),  # media type -> job (handler)
            ("tagged", Job("tagged_posts", "tagged@{name}")),
            ("igtv", Job("igtv_posts", "igtv@{name}")),
            ("story", Job("story", "story@{name}")),
            ("highs", Job("highlights", "highlights@{name}")),
            ("pic", Job("profile_picture", "")),
        )),
        "#": OrderedDict((
            ("top", Job("top_posts", "top#{name}")),
            ("recent", Job("recent_posts", "recent#{name}")),
            ("story", Job("story", "story#{name}")),
            ("pic", Job("profile_picture", "")),
        )),
        ":": OrderedDict((("", Job("", "")),)),  # placeholder
        "explore": OrderedDict(posts=Job("posts", "explore"),),
        "saved": OrderedDict(posts=Job("saved_posts", "saved"),),
    }

    # validate media types
    if identifier == "@" and bool({"top", "recent"} & specified_media_types):
        parser.error("target '@' not allowed with arguments: -top/--top-posts, -recent/--recent-posts")
    elif identifier == "#" and bool({"timeline", "tagged", "igtv", "highs"} & specified_media_types):
        parser.error("target '#' not allowed with arguments: -timeline/--timeline-posts, -tagged/--tagged-posts, -igtv/--igtv-posts, -highs/--highlights")
    elif identifier in (":", "explore", "saved") and bool(specified_media_types):
        parser.error(("target '{}' not allowed with arguments (all): ".format(identifier),
                      "-timeline/--timeline-posts, -tagged/--tagged-posts, -igtv/--igtv-posts, -top/--top-posts, ",
                      "-recent/--recent-posts, -story/--story, -highs/--highlights, -pic/--profile-pic"))

    # Make entries
    entries = []
    for target in targets:
        jobs = []

        if identifier in ("saved", "explore"):
            name = None
            media_types = types_dict[identifier]
        else:
            name = target[1:]
            media_types = types_dict[identifier]

        if not bool(specified_media_types):
            # to download all types of media of this target
            jobs = list(media_types.values())
        else:
            for t in list(specified_media_types):
                jobs.append(media_types[t])
        entries.append((name, jobs))

    # Determine structure getter function according to the target type
    getters_dict = {
        "@": insta.profile,
        "#": insta.hashtag,
        ":": insta.post,
        "saved": insta.me,
        "explore": insta.explore,
    }
    struct_getter = getters_dict[identifier]

    # Start downloading entries of jobs
    if guest:
        warn_print("You are not logged in currently (Anonymous/Guest).")
    print(Style.BRIGHT + Fore.GREEN + "❖ [Download] {} entries ({} jobs)\n".format(len(entries), sum([len(jobs) for _, jobs in entries])))
    for i, (name, jobs) in enumerate(entries, start=1):

        struct = None
        struct_getter_name = "Profile" if identifier == "saved" else struct_getter.__name__.title()
        target_name = insta.my_username if identifier == "saved" else name
        print(Style.BRIGHT + "{0}+ (Entry {1}/{2}) {3}".format(Fore.BLUE, i, len(entries), struct_getter_name), end=" ")
        print(Style.BRIGHT + target_name) if target_name is not None else print()
        with error_catcher(do_exit=False):
            struct = struct_getter(name) if name is not None else struct_getter()
            if hasattr(struct, "_obtain_full_data"):
                struct._obtain_full_data()
        if not bool(struct):
            continue

        for j, job in enumerate(jobs, start=1):
            # retrieve items
            results = None
            if not job.func_name:
                # single Post item
                results = struct
            else:
                print("{0}► (Job {1}/{2}) Retrieving {3}".format(Fore.CYAN, j, len(jobs), job.func_name.replace("_", " ").title()))
                handler = getattr(struct, job.func_name)
                with error_catcher(do_exit=False):
                    results = handler()
            if not bool(results):
                warn_print("No results are returned.")
                continue

            # prepare destination directory path
            if not os.path.isdir(dest):
                os.mkdir(dest)
            final_dest = os.path.join(dest, job.dest_dir.format(name=name))
            if not os.path.isdir(final_dest):
                os.mkdir(final_dest)

            # handle the result differently according to its type
            if job.func_name == "profile_picture":
                # validate options
                if any((preload, limit, posts_filter_str, dump_metadata, dump_comments, dump_likes)):
                    warn_print("Disallow: --preload, -l/--limit, -PF/--posts-filter, --dump-metadata, --dump-comments, --dump-likes")
                profile_picture_downloader(results, final_dest, identifier + name)
                continue
            elif job.func_name == "":  # Post
                # validate options
                if any((preload, limit, posts_filter_str)):
                    warn_print("Disallow: --preload, -l/--limit, -PF/--posts-filter")
                downloader = partial(post_downloader, insta=insta, post=results, debug=debug, final_dest=final_dest,
                                     dump_metadata=dump_metadata, dump_comments=dump_comments, dump_likes=dump_likes)
            elif job.func_name == "story":
                # validate options
                if any((preload, limit, posts_filter_str, dump_comments, dump_likes)):
                    warn_print("Disallow: --preload, -l/--limit, -PF/--posts-filter, --dump-comments, --dump-likes")
                downloader = partial(story_downloader, story=results, debug=debug, final_dest=final_dest, dump_metadata=dump_metadata)
            elif job.func_name == "highlights":
                # validate options
                if any((preload, posts_filter_str, dump_comments, dump_likes)):
                    warn_print("Disallow: --preload, -PF/--posts-filter, --dump-comments, --dump-likes")
                downloader = partial(highlights_downloader, insta=insta, highlights=results, debug=debug, final_dest=final_dest, limit=limit, dump_metadata=dump_metadata)
            elif job.func_name.endswith("posts"):
                downloader = partial(posts_group_downloader, group=results, debug=debug, final_dest=final_dest, filterstr=posts_filter_str,
                                     limit=limit, preload=preload, dump_metadata=dump_metadata, dump_comments=dump_comments, dump_likes=dump_likes)
            else:
                raise ValueError("unable to resolve media type")

            # execute downloader
            try:
                downs, existings = downloader()
            except KeyboardInterrupt:
                if j != len(jobs):  # not the last job
                    yorn = prompt("Continue to next job? (Y/n) ", lambda x: x.isalpha() and (x.lower() in ("y", "n")))
                else:
                    yorn = "n"
                if yorn == "y":
                    continue
                else:
                    error_print("Interrupted by user.", exit=1)

            # summary
            print("\33[2K\r", end="")  # erase the current line (leftover progress bar)
            print("► Items => Total {} = {} Downloads + {} Existings".format(downs + existings, downs, existings))
            print("► Destination:", final_dest)
        print()
