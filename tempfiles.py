import multiprocessing
import os
import random
import string
from multiprocessing import current_process
import config
import inspect
from clogs import logger


if current_process().name == 'MainProcess':
    mgr = multiprocessing.Manager()
globallist = None


def get_random_string(length):
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def is_named_used(name):
    return os.path.exists(name)


def temp_file_name(extension="png"):
    while True:
        name = f"{config.temp_dir}{get_random_string(8)}.{extension}"
        if not is_named_used(name):
            return name


def get_session_list():
    if globallist is not None:
        return globallist
    frame = inspect.currentframe()
    try:
        while "tempfilesession" not in frame.f_locals:
            frame = frame.f_back
        return frame.f_locals["tempfilesession"]
    except AttributeError:
        logger.warning("Session list requested outside of TempFileSession")
        return False


def temp_file(extension="png", temp_name=None):
    """
    generates and reserves the name of a file in temp/
    :param extension: the extension of the file
    :param temp_name: optionally reserve a specific name for deletion
    :return: the reserved name (no file is created)
    """
    if temp_name is None:
        temp_name = temp_file_name(extension)
    frame = inspect.currentframe()
    try:
        while "tempfilesession" not in frame.f_locals:
            frame = frame.f_back
        frame.f_locals["tempfilesession"].append(temp_name)
    except AttributeError:
        if globallist is not None:
            globallist.append(temp_name)
        else:
            logger.warning("Temp file created outside TempFileSession.")
    logger.debug(f"temp_file reserved {temp_name}")
    return temp_name


def reserve_names(names):
    for name in names:
        temp_file(temp_name=name)


class TempFileSession(object):
    def __init__(self):
        self.id = random.randint(0, 999999999999)
        logger.debug(f"Temp File Session #{self.id} init.")
        self.files_created = mgr.list()

    def __enter__(self):
        logger.debug(f"Temp File Session #{self.id} entered.")
        return self.files_created

    def __exit__(self, type, value, traceback):
        logger.info(f"Cleaning up {len(self.files_created)} files created by TFS #{self.id}")
        logger.debug(f"Temp File Session #{self.id} exiting.")
        for file in self.files_created:
            try:
                os.remove(file)
                logger.debug(f"Removed {file}")
            except FileNotFoundError:
                logger.debug(f"Tried to remove {file}, already removed.")
            except PermissionError:
                logger.debug(f"Tried to remove {file}, file is in use.")
        logger.debug(f"Temp File Session #{self.id} exited.")
