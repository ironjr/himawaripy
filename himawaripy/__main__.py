#!/usr/bin/env python3

import argparse
from datetime import timedelta, datetime
import io
import itertools as it
import json
import multiprocessing as mp
import multiprocessing.dummy as mp_dummy
import os
import os.path as path
import sys
from time import strptime, strftime, mktime
import urllib.request
from glob import iglob, glob
import threading
import time
import subprocess

import appdirs
from PIL import Image
from dateutil.tz import tzlocal

from himawaripy.utils import set_background, get_desktop_environment


# Semantic Versioning: Major, Minor, Patch
HIMAWARIPY_VERSION = (2, 1, 0)
counter = None
HEIGHT = 550
WIDTH = 550


def calculate_time_offset(latest_date, auto, preferred_offset):
    if auto:
        preferred_offset = int(datetime.now(tzlocal()).strftime("%z")[0:3])
        print("Detected offset: UTC{:+03d}:00".format(preferred_offset))
        if 11 >= preferred_offset > 10:
            preferred_offset = 10
            print("Offset is greater than +10, +10 will be used...")
        elif 12 >= preferred_offset > 11:
            preferred_offset = -12
            print("Offset is greater than +10, -12 will be used...")

    himawari_offset = 10  # UTC+10:00 is the time zone that himawari is over
    offset = int(preferred_offset - himawari_offset)

    offset_tmp = datetime.fromtimestamp(mktime(latest_date)) + timedelta(hours=offset)
    offset_time = offset_tmp.timetuple()

    return offset_time


def download_chunk(args):
    global counter

    x, y, latest, level, w, h = args
    url_format = "http://himawari8.nict.go.jp/img/D531106/{}d/{}/{}_{}_{}.png"
    url = url_format.format(level, WIDTH, strftime("%Y/%m/%d/%H%M%S", latest), x, y)

    tiledata = download(url)

    # If the tile data is 2867 bytes, it is a blank "No Image" tile.
    if tiledata.__sizeof__() == 2867:
        sys.exit('No image available for {}.'.format(strftime("%Y/%m/%d %H:%M:%S", latest)))

    with counter.get_lock():
        counter.value += 1
        if counter.value == level * level:
            print("Downloading tiles: completed.")
        else:
            print("Downloading tiles: {}/{} completed...".format(counter.value, w * h))
    return x, y, tiledata


def parse_args():
    parser = argparse.ArgumentParser(description="set (near-realtime) picture of Earth as your desktop background",
                                     epilog="http://labs.boramalper.org/himawaripy")

    parser.add_argument("--version", action="version", version="%(prog)s {}.{}.{}".format(*HIMAWARIPY_VERSION))

    group = parser.add_mutually_exclusive_group()

    group.add_argument("--auto-offset", action="store_true", dest="auto_offset", default=False,
                       help="determine offset automatically")
    group.add_argument("-o", "--offset", type=int, dest="offset", default=10,
                       help="UTC time offset in hours, must be less than or equal to +10")

    parser.add_argument("--screen-ratio", type=str, dest="screen_ratio", default="",
                        help="specify the screen ratio to crop the output image, format example: \'16:9\'")
    parser.add_argument("-t", "--tiles", type=str, dest="tiles", default="",
                        help="specify the coordinate of the box to be fetched in xyxy format")
    parser.add_argument("-l", "--level", type=int, choices=[4, 8, 16, 20], dest="level", default=4,
                        help="increases the quality (and the size) of each tile. possible values are 4, 8, 16, 20")
    parser.add_argument("-d", "--deadline", type=int, dest="deadline", default=6,
                        help="deadline in minutes to download all the tiles, set 0 to cancel")
    parser.add_argument("--save-battery", action="store_true", dest="save_battery", default=False,
                        help="stop refreshing on battery")
    parser.add_argument("--output-dir", type=str, dest="output_dir",
                        help="directory to save the temporary background image",
                        default=appdirs.user_cache_dir(appname="himawaripy", appauthor=False))
    parser.add_argument("--dont-change", action="store_true", dest="dont_change", default=False,
                        help="don't change the wallpaper (just download it)")

    args = parser.parse_args()

    if not -12 <= args.offset <= 10:
        sys.exit("OFFSET has to be between -12 and +10!\n")

    if not args.deadline >= 0:
        sys.exit("DEADLINE has to be greater than (or equal to if you want to disable) zero!\n")

    return args


def is_discharging():
    if sys.platform.startswith("linux"):
        if len(glob("/sys/class/power_supply/BAT*")) > 1:
            print("Multiple batteries detected, using BAT0.")

        with open("/sys/class/power_supply/BAT0/status") as f:
            status = f.readline().strip()

            return status == "Discharging"
    elif sys.platform == 'darwin':
        return b'discharging' in subprocess.check_output(["pmset", "-g", "batt"])

    else:
        sys.exit("Battery saving feature works only on linux or mac!\n")


def download(url):
    exception = None

    for i in range(1, 4):  # retry max 3 times
        try:
            with urllib.request.urlopen(url) as response:
                return response.read()
        except Exception as e:
            exception = e
            print("[{}/3] Retrying to download '{}'...".format(i, url))
            time.sleep(1)
            pass

    if exception:
        raise exception
    else:
        sys.exit("Could not download '{}'!\n".format(url))


def thread_main(args):
    global counter
    counter = mp.Value("i", 0)

    level = args.level  # since we are going to use it a lot of times
    x1, y1, x2, y2 = args.tiles
    w = x2 - x1 + 1
    h = y2 - y1 + 1

    print("Updating...")
    latest_json = download("http://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json")
    latest = strptime(json.loads(latest_json.decode("utf-8"))["date"], "%Y-%m-%d %H:%M:%S")

    print("Latest version: {} GMT.".format(strftime("%Y/%m/%d %H:%M:%S", latest)))
    requested_time = calculate_time_offset(latest, args.auto_offset, args.offset)
    if args.auto_offset or args.offset != 10:
        print("Offset version: {} GMT.".format(strftime("%Y/%m/%d %H:%M:%S", requested_time)))

    png = Image.new("RGB", (WIDTH * w, HEIGHT * h))

    p = mp_dummy.Pool(w * h)
    print("Downloading tiles...")
    res = p.map(download_chunk, it.product(
        range(x1, x2 + 1),
        range(y1, y2 + 1),
        (requested_time,),
        (args.level,),
        (w,),
        (h,),
    ))

    for (x, y, tiledata) in res:
        tile = Image.open(io.BytesIO(tiledata))
        png.paste(tile, (
            WIDTH * (x - x1),
            HEIGHT * (y - y1),
            WIDTH * (x - x1 + 1),
            HEIGHT * (y - y1 + 1)
        ))

    for file in iglob(path.join(args.output_dir, "himawari-*.png")):
        os.remove(file)

    # Crop if screen ratio is provided
    if args.screen_ratio != 0:
        aspect_ratio = float(w) / h
        if aspect_ratio > args.screen_ratio:
            # Crop the sides
            height = HEIGHT * h
            width = args.screen_ratio * height
            left = int((WIDTH * w - width) * 0.5)
            right = left + int(width)
            png = png.crop((left, 0, right, HEIGHT * h))
        elif aspect_ratio < args.screen_ratio:
            # Crop the top and the bottom
            width = WIDTH * w
            height = width / args.screen_ratio
            top = int((HEIGHT * h - height) * 0.5)
            bottom = top + int(height)
            png = png.crop((0, top, WIDTH * w, bottom))

    output_file = path.join(args.output_dir, strftime("himawari-%Y%m%dT%H%M%S.png", requested_time))
    print("Saving to '%s'..." % (output_file,))
    os.makedirs(path.dirname(output_file), exist_ok=True)
    png.save(output_file, "PNG")

    if not args.dont_change:
        r = set_background(output_file)
        if not r:
            sys.exit("Your desktop environment '{}' is not supported!\n".format(get_desktop_environment()))
    else:
        print("Not changing your wallpaper as requested.")


def main():
    args = parse_args()
    if args.tiles != "":
        tiles = [int(t.strip()) for t in args.tiles.strip().split(",") if t.strip() != ""]
        if len(tiles) < 4:
            sys.exit("Wrong box coordinates!\n")
        if tiles[2] < tiles[0] or tiles[3] < tiles[1]:
            sys.exit("Wrong box coordinates!\n")
        if tiles[2] >= args.level or tiles[3] >= args.level or tiles[0] < 0 or tiles[1] < 0:
            sys.exit("Wrong box coordinates!\n")
        args.tiles = tuple(tiles[:4])
    else:
        args.tiles = (0, 0, args.level - 1, args.level - 1)
    if args.screen_ratio != "":
        sr = [float(r.strip()) for r in args.screen_ratio.strip().split(":") if r.strip() != ""]
        if len(sr) < 2:
            sys.exit("Wrong screen ratio!\n")
        if sr[0] <= 0 or sr[1] <= 0:
            sys.exit("Wrong screen ratio!\n")
        args.screen_ratio = sr[0] / sr[1]
    else:
        args.screen_ratio = 0

    print("himawaripy {}.{}.{}".format(*HIMAWARIPY_VERSION))

    if args.save_battery and is_discharging():
        sys.exit("Discharging!\n")

    main_thread = threading.Thread(target=thread_main, args=(args,), name="himawaripy-main-thread", daemon=True)
    main_thread.start()
    main_thread.join(args.deadline * 60 if args.deadline else None)

    if args.deadline and main_thread.is_alive():
        sys.exit("Timeout!\n")

    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
