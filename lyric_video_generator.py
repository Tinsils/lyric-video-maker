import tkinter as tk
from tkinter import filedialog
from moviepy import *
import re
import math
import os


def pick_file(title, types):
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(title=title, filetypes=types)
    root.destroy()
    return path


def parse_srt(file):
    with open(file, "r", encoding="utf8") as f:
        content = f.read()
    pattern = r"\d+\s+(\d+:\d+:\d+,\d+)\s-->\s(\d+:\d+:\d+,\d+)\s+([\s\S]*?)(?=\n\n|\Z)"
    matches = re.findall(pattern, content)
    subtitles = []
    for m in matches:
        start = convert_time(m[0])
        end   = convert_time(m[1])
        text  = m[2].replace("\n", " ").strip()
        subtitles.append((start, end, text))
    return subtitles


def convert_time(t):
    h, m, s = t.split(":")
    s, ms   = s.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def wrap_text_words(text, max_chars, prefer_single_line=False):
    if prefer_single_line and len(text) <= max_chars:
        return text
    words   = text.split()
    lines   = []
    current = ""
    for word in words:
        if current == "":
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > 1 and len(lines[-1].split()) == 1:
        prev_words = lines[-2].split()
        if len(prev_words) > 2:
            moved     = prev_words.pop()
            lines[-2] = " ".join(prev_words)
            lines[-1] = moved + " " + lines[-1]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scale animation  75% -> 110% -> 100%
#
# Key insight: we render every clip at the SAME fixed pixel size (render_w x render_h).
# The animation then scales it. Because all clips start at the same pixel dimensions,
# they all appear the same size on screen — regardless of how many words they have.
#
# We use RENDER_SCALE = 1/S_PEAK so that at peak the clip is exactly render_w pixels
# wide — never larger than its source, so MoviePy never needs to upscale it.
# ---------------------------------------------------------------------------

fps    = 30
t1     = 2.5 / fps
t2     = 6.0 / fps

# Viewer-perceived scale values
V_START = 0.75
V_PEAK  = 1.10
V_REST  = 1.00


def scale_anim(t):
    if t < 0:
        return V_START
    if t < t1:
        return V_START + (t / t1) * (V_PEAK - V_START)
    elif t < t2:
        return V_PEAK - ((t - t1) / (t2 - t1)) * (V_PEAK - V_REST)
    else:
        return V_REST


EDGE_BUFFER   = 80
TEST_DURATION = 45.0


def create_video(width, height, filename, subtitles, test_mode=False):
    print(f"\nRendering {filename}  ({width}x{height})")
    if test_mode:
        print(f"TEST MODE — first {int(TEST_DURATION)} seconds only")

    clip_audio = audio.subclipped(0, min(TEST_DURATION, audio.duration)) if test_mode else audio

    background = (
        ImageClip(image_path)
        .resized(height=height)
        .with_duration(clip_audio.duration)
    )

    is_portrait = width < height

    if not is_portrait:
        font_size          = 90
        wrap_chars         = 22
        # Width the text occupies at V_REST (100%) scale
        rest_w             = int((width - 2 * EDGE_BUFFER) * 0.65)
        stroke_width       = 4
        prefer_single_line = False
    else:
        font_size          = 100
        wrap_chars         = 18
        rest_w             = int((width - 2 * EDGE_BUFFER) * 0.90)
        stroke_width       = 4
        prefer_single_line = True

    # render_w: the pixel width of the TextClip source image.
    # We render bigger than rest_w so that at V_PEAK (1.10x) the displayed
    # size equals rest_w * V_PEAK — and the source is never upscaled.
    # render_w / V_PEAK = rest_w  =>  render_w = rest_w * V_PEAK
    render_w = int(rest_w * V_PEAK)

    # render_h: fixed height for ALL clips — guarantees uniform vertical size.
    # Large enough for 3 lines at the given font size.
    render_h = int(font_size * 3.5)

    text_clips = []

    for orig_start, orig_end, raw_text in sorted(subtitles, key=lambda x: x[0]):

        start = orig_start
        end   = orig_end
        dur   = end - start

        if dur <= 0:
            continue
        if test_mode and start >= TEST_DURATION:
            continue
        if test_mode and end > TEST_DURATION:
            end   = TEST_DURATION
            dur   = end - start

        wrapped = wrap_text_words(raw_text, wrap_chars,
                                  prefer_single_line=prefer_single_line)

        # Render at render_w x render_h.
        # bg_color=None makes the background transparent (no black box).
        # method='caption' with explicit size gives us the fixed canvas we need
        # for uniform sizing — but we set bg_color to transparent to kill the black.
        txt = TextClip(
            text=wrapped,
            font="Runtoe.ttf",
            font_size=font_size,
            color="white",
            stroke_color="black",
            stroke_width=stroke_width,
            method="caption",
            size=(render_w, render_h),
            text_align="center",
            bg_color=None,          # transparent background — no black box
        )

        clip_w, clip_h = txt.size

        # The scale factor applied to the clip at time t.
        # At t>=t2 scale = V_REST, so displayed size = render_w * V_REST = rest_w. ✓
        # At peak      scale = V_PEAK, displayed size = render_w * V_PEAK / V_PEAK... 
        # Wait — we need: displayed = render_w * scale_factor
        # We want displayed at rest = rest_w, so scale_factor at rest = rest_w / render_w = 1/V_PEAK
        # We want displayed at peak = rest_w * V_PEAK, so scale_factor at peak = rest_w*V_PEAK/render_w = 1.0
        # So the playback scale = scale_anim(t) / V_PEAK
        def make_clip_scale(vp=V_PEAK):
            return lambda t: scale_anim(t) / vp

        clip_scale_fn = make_clip_scale()

        # Position: centre the scaled clip on the canvas, add shake on top.
        # We pass clip_w/clip_h (the render dimensions) so the math is consistent
        # with the actual scale applied above.
        def make_position(cw, ch, canv_w, canv_h):
            def pos(t):
                s       = scale_anim(t) / V_PEAK   # matches clip_scale_fn
                disp_w  = cw * s
                disp_h  = ch * s
                x       = canv_w / 2 - disp_w / 2 + math.sin(t * 6) * 6
                y       = canv_h / 2 - disp_h / 2 + math.cos(t * 5) * 4
                return (x, y)
            return pos

        clip = (
            txt
            .resized(clip_scale_fn)
            .with_position(make_position(clip_w, clip_h, width, height))
            .with_start(start)
            .with_duration(dur)
        )

        text_clips.append(clip)

    video = CompositeVideoClip(
        [background] + text_clips,
        size=(width, height)
    ).with_audio(clip_audio)

    out_file = filename.replace(".mp4", "_TEST.mp4") if test_mode else filename

    video.write_videofile(
        out_file,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8,
    )
    print(f"\nSaved: {out_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

print("Select audio file (.mp3 / .wav)")
audio_path = pick_file("Audio", [("Audio", "*.mp3 *.wav")])
if not audio_path:
    raise SystemExit("No audio file selected.")

print("Select subtitle file (.srt)")
srt_path = pick_file("Subtitles", [("Subtitles", "*.srt")])
if not srt_path:
    raise SystemExit("No subtitle file selected.")

print("Select background image")
image_path = pick_file("Image", [("Images", "*.png *.jpg *.jpeg")])
if not image_path:
    raise SystemExit("No image selected.")

print("\nChoose output mode:")
print("1 = Landscape only")
print("2 = Portrait only")
print("3 = Both")
print("4 = TEST (landscape, first 45 seconds only)")
print("5 = TEST (portrait, first 45 seconds only)")
print("6 = TEST both (landscape + portrait, first 45 seconds only)")
mode = input("Enter choice: ").strip()

audio     = AudioFileClip(audio_path)
subtitles = parse_srt(srt_path)

if mode == "1":
    create_video(1920, 1080, "lyric_video_landscape.mp4", subtitles)
elif mode == "2":
    create_video(1080, 1920, "lyric_video_portrait.mp4", subtitles)
elif mode == "3":
    create_video(1920, 1080, "lyric_video_landscape.mp4", subtitles)
    create_video(1080, 1920, "lyric_video_portrait.mp4", subtitles)
elif mode == "4":
    create_video(1920, 1080, "lyric_video_landscape.mp4", subtitles, test_mode=True)
elif mode == "5":
    create_video(1080, 1920, "lyric_video_portrait.mp4", subtitles, test_mode=True)
elif mode == "6":
    create_video(1920, 1080, "lyric_video_landscape.mp4", subtitles, test_mode=True)
    create_video(1080, 1920, "lyric_video_portrait.mp4", subtitles, test_mode=True)
else:
    print("Invalid choice — please enter 1, 2, 3, 4, 5, or 6.")