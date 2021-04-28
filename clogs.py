# configure logging https://coloredlogs.readthedocs.io/en/latest/api.html#id28
import logging
import coloredlogs

logger = logging.getLogger(__name__)
field_styles = {
    'levelname': {'bold': True, 'color': 'blue'},
    'asctime': {'color': 2},
    'filename': {'color': 6},
    'funcName': {'color': 5},
    'lineno': {'color': 13}
}
level_styles = coloredlogs.DEFAULT_LEVEL_STYLES
level_styles['COMMAND'] = {'color': 4}
logging.addLevelName(25, "NOTICE")
logging.addLevelName(35, "SUCCESS")
logging.addLevelName(21, "COMMAND")
coloredlogs.install(level="DEBUG", fmt='[%(asctime)s] [%(filename)s:%(funcName)s:%(lineno)d] '
                                                '%(levelname)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', field_styles=field_styles, level_styles=level_styles, logger=logger)
