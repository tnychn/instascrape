import os
import re
from setuptools import setup, find_packages

# Package Meta-Data
NAME = "instascraper"
DESC = "A fast and lightweight Instagram media downloader."
LONG_DESC = (
    "**Instascrape** is a fast and lightweight utility and Python library for downloading a massive amount of media (photos and videos) from Instagram, without using the official Instagram Public API.",
    "## Features",
    "* 🔌 Powerful & simple-to-use library interface",
    "  * ⛓ calls methods in a chain (fluent interface)",
    "  * 🔩 provides hooks/callbacks in download methods"
    "* 🚸 User-friendly commad-line interface",
    "* 💨 High efficiency",
    "  * 🧵 uses multithreading to fetch data",
    "  * ⚡️ uses generators to yield results",
    "* 🔎 Provides a *filter* option to avoid downloading media that you don't want",
    "* 📑 Download media along with their metadata",
    "* ⚠️ Good exceptions handling",
    "* 🍪 Manages multiple cookies for you",
    "* 🔑 Peforms authentication effectively",
    "  * 🔐 supports 2FA",
    "  * 🖇 solves checkpoint challenge",
    "* 🕶 Can be used in anonymous mode",
)
AUTHOR = "a1phat0ny"
EMAIL = "tony.chan2342@gmail.com"
URL = "https://github.com/a1phat0ny/instascrape"
ENTRY = "instascrape=instascrape.__main__:main"
PYTHON_REQUIRES = ">=3.5.0"
REQUIRES = ["requests", "tqdm", "colorama"]
KEYWORDS = ["instagram", "scraper", "downloader", "media", "api", "cli"]


# Find version number in __init__.py using regex
def find_version_number():
    # __version__ must be defined inside the __init__.py of the package
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, "instascrape", "__init__.py"), "r") as f:
        text = f.read()
    match = re.search(r"__version__ = ['|\"](.+?)['|\"]", text)
    if not match:
        raise RuntimeError("version number not found")
    return match.group(1)


# Do the magics here!
setup(
    name=NAME,
    version=find_version_number(),
    description=DESC,
    long_description="\n".join(LONG_DESC),
    long_description_content_type="text/markdown",
    author=AUTHOR,
    author_email=EMAIL,
    url=URL,
    entry_points={
        "console_scripts": [ENTRY],
    },
    python_requires=PYTHON_REQUIRES,
    install_requires=REQUIRES,
    include_package_data=True,
    packages=find_packages(),
    license="MIT",
    keywords=KEYWORDS,
    classifiers=[  # https://pypi.org/classifiers
        "License :: OSI Approved :: MIT License",
        "Development Status :: 5 - Production/Stable",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Software Development :: Version Control :: Git",
        "Topic :: Utilities",
    ],
)
