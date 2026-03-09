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


def wrap_text_words(text, max_chars):

    words = text.split()
    lines = []
    current = ""

    for word in words:

        if len(current + " " + word) <= max_chars:
            if current == "":
                current = word
            else:
                current += " " + word
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    balanced = []
    i = 0

    while i < len(lines):

        line = lines[i]

        if i > 0 and len(line.split()) == 1:

            prev = balanced[-1]
            prev_words = prev.split()

            if len(prev_words) > 2:
                moved = prev_words.pop()
                balanced[-1] = " ".join(prev_words)
                line = moved + " " + line

        balanced.append(line)
        i += 1

    return "\n".join(balanced)


print("Select audio file")
audio_path = pick_file("Audio", [("Audio", "*.mp3 *.wav")])

print("Select subtitle file (.srt)")
srt_path = pick_file("Subtitles", [("Subtitles", "*.srt")])

print("Select background image")
image_path = pick_file("Image", [("Images", "*.png *.jpg *.jpeg")])

print("\nChoose output mode:")
print("1 = Landscape")
print("2 = Portrait")
print("3 = Both")

mode = input("Enter choice: ")

audio = AudioFileClip(audio_path)
subtitles = parse_srt(srt_path)

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


def create_video(width, height, filename):

    print("Rendering", filename)

    background = (
        ImageClip(image_path)
        .resized(height=height)
        .with_duration(audio.duration)
    )

    text_clips = []

    if width == 1920:
        max_text_width = 1700
        font_size = 70
        wrap_chars = 45
    else:
        max_text_width = 800
        font_size = 70
        wrap_chars = 15

    for start, end, text in subtitles:

        text = wrap_text_words(text, wrap_chars)

        txt = TextClip(
            text=text,
            font="Runtoe.ttf",
            font_size=font_size,
            color="white",
            stroke_color="black",
            stroke_width=3,
            method="label",
            text_align="center"
        )

        txt = txt.to_ImageClip()

        text_w, text_h = txt.size

        # invisible container to keep paragraph centered
        container = ColorClip(
            size=(max_text_width, text_h),
            color=(0,0,0)
        ).with_opacity(0)

        txt = CompositeVideoClip([
            container,
            txt.with_position(("center","center"))
        ])

        original_w = max_text_width
        original_h = text_h

        def centered_shake(t):

            scale = scale_anim(t)

            w = original_w * scale
            h = original_h * scale

            center_x = width / 2
            center_y = height / 2

            x_shake = math.sin(t * 6) * 6
            y_shake = math.cos(t * 5) * 4

            x = center_x - w/2 + x_shake
            y = center_y - h/2 + y_shake

            return (x, y)

        txt = (
            txt
            .resized(lambda t: scale_anim(t))
            .with_position(centered_shake)
            .with_start(start)
            .with_duration(end - start)
        )

        text_clips.append(txt)

    video = CompositeVideoClip(
        [background] + text_clips,
        size=(width, height)
    ).with_audio(audio)

    video = video.with_fps(30)

    video.write_videofile(
        filename,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8
    )


if mode == "1":
    create_video(1920, 1080, "lyric_video_landscape.mp4")

elif mode == "2":
    create_video(1080, 1920, "lyric_video_portrait.mp4")

elif mode == "3":
    create_video(1920, 1080, "lyric_video_landscape.mp4")
    create_video(1080, 1920, "lyric_video_portrait.mp4")

else:
    print("Invalid choice")