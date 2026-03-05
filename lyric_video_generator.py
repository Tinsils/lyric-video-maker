import tkinter as tk
from tkinter import filedialog
from moviepy import *
import re
import math


def pick_file(title, types):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(title=title, filetypes=types)


def parse_srt(file):
    with open(file, "r", encoding="utf8") as f:
        content = f.read()

    pattern = r"(\d+)\s+(\d+:\d+:\d+,\d+)\s-->\s(\d+:\d+:\d+,\d+)\s+([\s\S]*?)(?=\n\n|\Z)"
    matches = re.findall(pattern, content)

    subtitles = []

    for m in matches:
        start = convert_time(m[1])
        end = convert_time(m[2])
        text = m[3].replace("\n", " ")
        subtitles.append((start, end, text))

    return subtitles


def convert_time(t):
    h, m, s = t.split(":")
    s, ms = s.split(",")

    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000


print("Select audio file")
audio_path = pick_file("Audio", [("Audio", "*.mp3 *.wav")])

print("Select subtitle file (.srt)")
srt_path = pick_file("Subtitles", [("Subtitles", "*.srt")])

print("Select background image")
image_path = pick_file("Image", [("Images", "*.png *.jpg *.jpeg")])


audio = AudioFileClip(audio_path)

background = (
    ImageClip(image_path)
    .resized(height=1080)
    .with_duration(audio.duration)
)


subtitles = parse_srt(srt_path)

text_clips = []

fps = 30
t1 = 2.5 / fps
t2 = 6 / fps


def scale_anim(t):

    if t < 0:
        return 0.75

    if t < t1:
        return 0.75 + (t/t1)*(1.10 - 0.75)

    elif t < t2:
        return 1.10 - ((t-t1)/(t2-t1))*(1.10 - 1.00)

    else:
        return 1.0


# faster but smooth shake
def shake_position(t):

    strength = 6
    speed = 6   # increased from 3 → 6

    x_offset = math.sin(t * speed) * strength
    y_offset = math.cos(t * speed * 0.8) * (strength * 0.6)

    return ("center", "center", x_offset, y_offset)


for start, end, text in subtitles:

    # create text clip with a generous maximum width so that
    # multi‑line lyrics don't wrap too aggressively or get clipped
    max_text_width = 1800  # leave ~60px padding on each side of 1920 frame
    txt = TextClip(
        text=text,
        font="Runtoe.ttf",
        font_size=70,
        color="white",
        stroke_color="black",
        stroke_width=3,
        size=(max_text_width, None),
        method="caption",
        text_align="center"
    )

    # convert to ImageClip so we can measure and pad it
    txt = txt.to_ImageClip()

    # add a transparent margin around the text to avoid clipping at the edges
    # some MoviePy versions throw an error if margin() is missing/unsupported,
    # so wrap it in a try/except rather than crashing the whole program
    try:
        txt = txt.margin(left=20, right=20, top=20, bottom=20, color=(0,0,0,0))
    except Exception:
        pass

    # capture the clip's size after any padding so we can use it in the
    # position calculation below
    original_w, original_h = txt.size

    # compute a position that keeps the clip centered and
    # applies a small shake; scaling is taken into account by using
    # the clip's current width/height so the base position always
    # equals the visual centre of the frame.
    def centered_shake_pos(t):
        scale = scale_anim(t)
        w = original_w * scale
        h = original_h * scale

        # centre the clip by subtracting half its scaled size from the
        # 1920×1080 frame dimensions
        x_base = (1920 - w) / 2
        y_base = (1080 - h) / 2

        # shake offsets around the centre
        x_off = math.sin(t * 6) * 6
        y_off = math.cos(t * 5) * 4

        x = x_base + x_off
        y = y_base + y_off

        # clamp to stay in bounds (optional but safety-net)
        x = max(0, min(x, 1920 - w))
        y = max(0, min(y, 1080 - h))

        return (x, y)

    txt = (
        txt
        .resized(lambda t: scale_anim(t))
        .with_position(centered_shake_pos)
        .with_start(start)
        .with_duration(end - start)
    )

    # previous absolute-position shake is no longer needed
    # txt = txt.with_position(lambda t: (960 + math.sin(t * 6) * 6, 540 + math.cos(t * 5) * 4))

    text_clips.append(txt)


video = CompositeVideoClip(
    [background] + text_clips,
    size=(1920,1080)
).with_audio(audio)

video = video.with_fps(30)


video.write_videofile(
    "lyric_video.mp4",
    fps=30,
    codec="libx264",
    audio_codec="aac",
    preset="ultrafast",
    threads=8
)