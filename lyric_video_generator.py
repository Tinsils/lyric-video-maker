import tkinter as tk
from tkinter import filedialog
from moviepy import *
import re


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


for start, end, text in subtitles:

    txt = TextClip(
        text=text,
        font="Runtoe.ttf",
        font_size=70,
        color="white",
        stroke_color="black",
        stroke_width=3,
        size=(1600, None),
        method="caption",
        text_align="center"
    )

    txt = (
        txt
        .resized(lambda t: scale_anim(t))
        .with_position("center")
        .with_start(start)
        .with_duration(end - start)
    )

    text_clips.append(txt)


video = CompositeVideoClip(
    [background] + text_clips,
    size=(1920,1080)
).with_audio(audio)


video.write_videofile(
    "lyric_video.mp4",
    fps=30,
    codec="libx264",
    audio_codec="aac"
)