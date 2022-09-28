#!/usr/bin/env python3

import argparse
import os
from tqdm import trange, tqdm
from PIL import Image, ImageStat, ImageDraw, ImageEnhance
import PIL
import cv2
import math

OUT_WIDTH_DEFAULT = 1280
OUT_HEIGHT_DEFAULT = 512


def buildGradientOverlay(out_width, out_height):
    class Point(object):
        def __init__(self, x, y):
            self.x, self.y = x, y

    class Rect(object):
        def __init__(self, x1, y1, x2, y2):
            minx, maxx = (x1, x2) if x1 < x2 else (x2, x1)
            miny, maxy = (y1, y2) if y1 < y2 else (y2, y1)
            self.min = Point(minx, miny)
            self.max = Point(maxx, maxy)

        width = property(lambda self: self.max.x - self.min.x)
        height = property(lambda self: self.max.y - self.min.y)

    def gradient_color(minval, maxval, val, color_palette):
        """ Computes intermediate RGB color of a value in the range of minval
            to maxval (inclusive) based on a color_palette representing the range.
        """
        max_index = len(color_palette)-1
        delta = maxval - minval
        if delta == 0:
            delta = 1
        v = float(val-minval) / delta * max_index
        i1, i2 = int(v), min(int(v)+1, max_index)
        (r1, g1, b1), (r2, g2, b2) = color_palette[i1], color_palette[i2]
        f = v - i1
        return int(r1 + f*(r2-r1)), int(g1 + f*(g2-g1)), int(b1 + f*(b2-b1))

    def vert_gradient(draw, rect, color_func, color_palette):
        minval, maxval = 1, len(color_palette)
        delta = maxval - minval
        height = float(rect.height)  # Cache.
        for y in range(rect.min.y, rect.max.y+1):
            f = (y - rect.min.y) / height
            val = minval + f * delta
            color = color_func(minval, maxval, val, color_palette)
            draw.line([(rect.min.x, y), (rect.max.x, y)], fill=color)

    ovl = Image.new("RGB", (out_width, out_height))
    gradient_overlay_draw = ImageDraw.Draw(ovl)
    color_palette = [(0, 0, 0), (255, 255, 255), (0, 0, 0)]
    # color_palette = [
    #     (255, 255, 255),
    #     (0, 0, 0),
    #     (0, 0, 0),
    #     (0, 0, 0),
    #     (255, 255, 255)]
    region = Rect(0, 0, out_width, out_height)
    vert_gradient(gradient_overlay_draw, region, gradient_color, color_palette)
    return ovl


##################################################################
parser = argparse.ArgumentParser()
parser.add_argument(dest="input_file", nargs=1,
                    help="Input video (mp4|m4v|webm|etc)")

parser.add_argument('-iw', '--width', default=OUT_WIDTH_DEFAULT, type=int,
                    help="Width in pixels")

parser.add_argument('-ih', '--height', default=OUT_HEIGHT_DEFAULT, type=int,
                    help="Height in pixels")

parser.add_argument('-over', '--overlay_strength', default=0.15, type=float,
                    help="Overlay intensity (0 to 1; 0.15 default)")

parser.add_argument('-sat', '--saturation', default=1.5, type=float,
                    help="Saturation scale (1.0 == normal)")

parser.add_argument('-con', '--contrast', default=1.2, type=float,
                    help="Contrast scale (1.0 == normal)")

parser.add_argument('-sm', '--smoother', action='store_true',
                    help="Use a smoother frame transition")

parser.add_argument('-nr', '--no-reveal', action='store_true',
                    help="Don't open resulting image")

parser.add_argument('-o', dest="output_file",
                    help="Output file", default="output.png")

args = parser.parse_args()

try:
    # delete the target file if it exists
    if args.output_file and os.path.exists(args.output_file):
        os.unlink(args.output_file)

    src_video = cv2.VideoCapture(args.input_file[0])

    frame_count = src_video.get(cv2.CAP_PROP_FRAME_COUNT)

    print(f"Frame count: {frame_count}")

    frame_stride = math.ceil(frame_count / args.width)

    print(f"Frame stride:", frame_stride)

    # Build gradient overlay
    gradient_overlay = buildGradientOverlay(args.width, args.height)

    # Build vertical frame stack
    out_framestack = Image.new("RGB", (args.width, args.height))
    out_framestack_draw = ImageDraw.Draw(out_framestack)

    frame_index = 0
    avg_c = 0

    prev_avg = None
    pal_avg = None

    print("Building frame stack...")

    for i in trange(0, int(frame_count), frame_stride):
        src_video.set(cv2.CAP_PROP_POS_FRAMES, frame_index-1)
        success, image = src_video.read()
        frame = Image.fromarray(image)

        avg = ImageStat.Stat(frame)

        if args.smoother:
            if prev_avg:
                pal_avg[0], pal_avg[1], pal_avg[2] = \
                    prev_avg[0] + avg.median[0] / 2, \
                    prev_avg[1] + avg.median[1] / 2, \
                    prev_avg[2] + avg.median[2] / 2
                prev_avg = avg.median
            else:
                pal_avg = avg.median
                prev_avg = pal_avg
        else:
            pal_avg = avg.median

        out_framestack_draw.line((avg_c, 0) + (avg_c, args.height), fill=(
            math.floor(pal_avg[2]), math.floor(pal_avg[1]), math.floor(pal_avg[0])))

        frame_index += frame_stride
        avg_c += 1

    # overlay the shading gradient and do some final tweaks
    blend = PIL.Image.blend(
        out_framestack, gradient_overlay, args.overlay_strength)

    contr = PIL.ImageEnhance.Contrast(blend).enhance(args.contrast)

    final_img = PIL.ImageEnhance.Color(contr).enhance(args.saturation)

    if not args.no_reveal:
        final_img.show()

    if args.output_file:
        final_img.save(args.output_file, "PNG")

except Exception as e:
    print("Oops...")
    print(e)
