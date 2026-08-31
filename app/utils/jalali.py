"""Gregorian -> Jalali (Shamsi) date conversion, no external deps."""
import time

_G_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def g2j(gy: int, gm: int, gd: int):
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += _G_DAYS[gm2] + gd2
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + (j_day_no - 186) % 30
    return jy, jm, jd


def now_str(ts: float | None = None) -> str:
    """Return e.g. '1405/06/09 - 14:27' for the given unix time (local)."""
    t = time.localtime(ts if ts is not None else time.time())
    jy, jm, jd = g2j(t.tm_year, t.tm_mon, t.tm_mday)
    return f"{jy:04d}/{jm:02d}/{jd:02d} - {t.tm_hour:02d}:{t.tm_min:02d}"


def date_str(ts: float | None = None) -> str:
    t = time.localtime(ts if ts is not None else time.time())
    jy, jm, jd = g2j(t.tm_year, t.tm_mon, t.tm_mday)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"
