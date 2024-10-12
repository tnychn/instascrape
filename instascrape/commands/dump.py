import os
import ast
from collections import namedtuple

from colorama import Style, Fore

from instascrape import Instagram
from instascrape.utils import data_dumper
from instascrape.commands import load_obj, pretty_print, error_catcher, warn_print


def filterstr_to_filterfunc(filterstr: str):

    def filterfunc(struct):

        class FilterStrTransformer(ast.NodeTransformer):

            def visit_Name(self, node: ast.Name):
                # check whether the attribute name the user specified exists
                if not hasattr(struct, node.id):
                    raise AttributeError("'{}' does not have attribute: '{}'".format(struct.__class__.__name__, node.id))
                if str(node.id) not in struct.info_vars:
                    raise AttributeError("'{}' does not have info var: '{}'".format(struct.__class__.__name__, node.id))
                # assign the 'struct' to get the attribute of the structure
                new_node = ast.Attribute(ast.copy_location(ast.Name("struct", ast.Load()), node), node.id,
                                         ast.copy_location(ast.Load(), node))
                return ast.copy_location(new_node, node)

        input_filename = "<command line filter option>"
        compiled_filter = compile(FilterStrTransformer().visit(ast.parse(filterstr, filename=input_filename, mode="eval")),
                                  filename=input_filename, mode="eval")
        return bool(eval(compiled_filter, {"struct": struct}))

    return filterfunc


def dump_handler(**args):
    # Try to load object
    guest = False
    insta = load_obj()
    if insta is None:
        guest = True
        insta = Instagram()

    # Validate target
    parser = args.get("parser")
    targets = args.get("target")
    names = []
    for target in targets:
        if len(target) <= 1:
            parser.error("invalid target parsed: '{}'".format(target))
        if target[0] not in ("@", ":"):
            parser.error("invalid identifier of target: '{}'".format(target))
        if target[0] != targets[0][0]:
            parser.error("all targets must be the same type")
        names.append(target[1:])
    identifier = targets[0][0]

    # Gather options
    outfile = args.get("outfile")
    limit = args.get("limit")
    profiles_filter_str = args.get("profiles_filter")
    comments_filter_str = args.get("comments_filter")
    preload = args.get("preload")
    # Gather dump types
    followers = args.get("followers")
    followings = args.get("followings")
    comments = args.get("comments")
    likes = args.get("likes")

    # Validate dump types
    if identifier == "@" and any((comments, likes)):
        parser.error("target '@' not allowed with arguments: -comments, -likes")
    elif identifier == ":" and any((followers, followings)):
        parser.error("target ':' not allowed with arguments: -followers, -followings")

    struct_getter = None
    # Make entries
    Job = namedtuple("Job", "name handler")
    entries = []
    for name in names:
        jobs = []

        if identifier == "@":
            if not any((followers, followings)):
                jobs.append(Job("information", lambda profile: profile.as_dict()))
            else:
                if followers:
                    jobs.append(Job("followers", lambda profile: profile.followers()))
                if followings:
                    jobs.append(Job("followings", lambda profile: profile.followings()))
            if struct_getter is None:
                struct_getter = insta.profile

        elif identifier == ":":
            if not any((comments, likes)):
                jobs.append(Job("information", lambda post: post.as_dict()))
            else:
                if comments:
                    jobs.append(Job("comments", lambda post: post.comments()))
                if likes:
                    jobs.append(Job("likes", lambda post: post.likes()))
            if struct_getter is None:
                struct_getter = insta.post

        entries.append((name, jobs))

    # Start dumping entries of jobs
    if guest:
        warn_print("You are not logged in currently (Anonymous/Guest).")
    print(Style.BRIGHT + Fore.GREEN + "❖ [Dump] {} entries ({} jobs)\n".format(len(entries), sum([len(jobs) for _, jobs in entries])))
    for i, (name, jobs) in enumerate(entries, start=1):

        struct = None
        print(Style.BRIGHT + "{0}+ (Entry {1}/{2}) {3} {4}".format(Fore.BLUE, i, len(entries), struct_getter.__name__.title(), Fore.WHITE + name))
        with error_catcher(do_exit=False):
            struct = struct_getter(name)
            struct._obtain_full_data()
        if not bool(struct):
            continue

        for j, job in enumerate(jobs, start=1):
            # retrieve items
            group = None
            results = None
            print("{0}► (Job {1}/{2}) Retrieving {3}".format(Fore.CYAN, j, len(jobs), job.name.title()))
            with error_catcher(do_exit=False):
                results = job.handler(struct)
            if not bool(results):
                warn_print("No results are returned.")
                continue

            try:
                if job.name == "information":
                    if any((limit, profiles_filter_str, comments_filter_str, preload)):
                        warn_print("Disallow: -l/--limit, -PF/--profiles-filter, -CF/--comments-filter, --preload")
                elif job.name in ("likes", "followers", "followings"):
                    if comments_filter_str:
                        warn_print("Disallow: -CF/--comments-filter")
                    print(Style.BRIGHT + "~ Total:", results.length)
                    group = results
                    group.limit(limit).preload(preload).ignore_errors(True)
                    if profiles_filter_str:
                        filterfunc = filterstr_to_filterfunc(profiles_filter_str)
                        group.filter(filterfunc)
                    results = (result.username for result in group) if not outfile else (result.as_dict(extra=True) for result in group)
                elif job.name == "comments":
                    if any((profiles_filter_str, preload)):
                        warn_print("Disallow: -PF/--profiles-filter, --preload")
                    print(Style.BRIGHT + "~ Total:", results[0])
                    if comments_filter_str:
                        filterfunc = filterstr_to_filterfunc(comments_filter_str)
                    with error_catcher(do_exit=False):
                        results = [result._asdict() for result in results[1] if filterfunc(result)]
                        if limit is not None:
                            results = results[:limit]
                else:
                    raise ValueError("unable to resolve dump type")

                if outfile:
                    outfile = os.path.abspath(outfile)
                    dest, file = os.path.split(outfile)
                    filename, _ = os.path.splitext(file)
                    data_dumper(dest, filename, list(results))
                    print(Style.BRIGHT + Fore.GREEN + "⇟ Data Dumped => " + Fore.WHITE + os.path.join(dest, filename + ".json"))
                else:
                    pretty_print(results)
            finally:
                if group is not None and job.name in ("likes", "followers", "followings"):
                    errors = group.collect_errors()
                    if errors:
                        print(Fore.RED + "  [{} Errors Collected During Posts Retrieving]".format(len(errors)))
                        for error in errors:
                            print(Fore.RED + "> {} -> {}: {}".format(Fore.WHITE + Style.BRIGHT + error.name + Style.RESET_ALL +
                                                                     Fore.RED, Style.BRIGHT + error.exc_type.__name__, error.exc_value))
        print()
