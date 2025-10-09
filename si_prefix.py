import math


def si_prefix(number: float | int, sigfigs: int = 3) -> str:
    prefixes = {
        30: 'Q',  # quetta
        27: 'R',  # ronna
        24: 'Y',  # yotta
        21: 'Z',  # zetta
        18: 'E',  # exa
        15: 'P',  # peta
        12: 'T',  # tera
        9: 'G',  # giga
        6: 'M',  # mega
        3: 'k',  # kilo
        0: '',  # none
        -3: 'm',  # milli
        -6: 'µ',  # micro
        -9: 'n',  # nano
        -12: 'p',  # pico
        -15: 'f',  # femto
        -18: 'a',  # atto
        -21: 'z',  # zepto
        -24: 'y',  # yocto
        -27: 'r',  # ronto
        -30: 'q',  # quecto
    }
    exponent = math.log10(number)
    # floor to nearest multiple of 10^3 (1000)
    # you might think that youd want to round towards 0, but sub-10^1 prefixes behave different
    exponent3 = (exponent // 3) * 3
    prefix = prefixes.get(exponent3, '')
    # if exponent out of range or prefix went wrong somehow, default to no prefix and reset exponent
    if prefix == "":
        exponent3 = 0
    scaled = number / (10 ** exponent3)
    return f"{scaled:.{sigfigs}g}{' ' if prefix else ''}{prefix}"
