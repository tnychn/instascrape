__version__ = "2.0.2"

# Environment set up
import os
DIR_PATH = os.path.join(os.path.expanduser("~"), ".instascrape")
if not os.path.isdir(DIR_PATH):
    os.mkdir(DIR_PATH)

# Logger set up (file)
import logging
logger = logging.getLogger("instascrape")
logger.setLevel(logging.DEBUG)
log_file = os.path.join(DIR_PATH, "instascrape.log")
formatter = logging.Formatter("[%(asctime)s] [%(threadName)s/%(levelname)s] (file='%(filename)s' line=%(lineno)d func='%(funcName)s'): %(msg)s", "%X")
file_handler = logging.FileHandler(log_file, mode="w+")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Override except hook
import sys
import traceback


def excepthook(exctype, value, tb):
    logger.error(exctype.__name__ + ": " + str(value))
    logger.debug("".join(traceback.format_tb(tb)))
    sys.__excepthook__(type, value, traceback)


sys.excepthook = excepthook

# Expose all necessary objects
from instascrape.instascrape import *
from instascrape.structures import *
from instascrape.exceptions import *
from instascrape.utils import get_username_from_userid
