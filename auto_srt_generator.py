"""
Lyrics to SRT
=============
Picks an MP3, finds synced lyrics, and saves a .srt subtitle file
next to the MP3. No audio playback required.

Requirements:
    pip install mutagen syncedlyrics lyricsgenius
"""

import os
import re
import sys
import tkinter as tk
from tkinter import filedialog

# ── third-party ───────────────────────────────────────────────────────────────
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    import syncedlyrics
    import lyricsgenius
except ImportError as e:
    print(f"\n[ERROR] Missing dependency: {e}")
    print("Install with:\n  pip install mutagen syncedlyrics lyricsgenius\n")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
#  🔑  PASTE YOUR GENIUS ACCESS TOKEN HERE  (only needed as a fallback)
# ─────────────────────────────────────────────────────────────────────────────
GENIUS_ACCESS_TOKEN = "YOUR_GENIUS_ACCESS_TOKEN_HERE"
# ─────────────────────────────────────────────────────────────────────────────


# ── helpers ───────────────────────────────────────────────────────────────────

def srt_timestamp(seconds: float) -> str:
    """Convert float seconds → SRT timestamp  HH:MM:SS,mmm"""
    ms  = int(round(seconds * 1000))
    h   = ms // 3_600_000;  ms %= 3_600_000
    m   = ms // 60_000;     ms %= 60_000
    s   = ms // 1_000;      ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_lrc(lrc_text: str) -> list[tuple[float, str]]:
    """Parse LRC text → sorted list of (start_seconds, line)."""
    pattern = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d+))?\](.*)")
    lines = []
    for raw in lrc_text.splitlines():
        m = pattern.match(raw.strip())
        if m:
            mins = int(m.group(1))
            secs = int(m.group(2))
            frac = m.group(3) or "0"
            frac_sec = int(frac) / (10 ** len(frac))
            timestamp = mins * 60 + secs + frac_sec
            text = m.group(4).strip()
            if text:                        # skip blank timing lines
                lines.append((timestamp, text))
    lines.sort(key=lambda x: x[0])
    return lines


def plain_to_timed(lyrics_text: str, duration: float) -> list[tuple[float, str]]:
    """Distribute plain lyrics evenly across the song duration as a fallback."""
    raw = [l for l in lyrics_text.splitlines() if l.strip()]
    if not raw:
        return []
    interval = duration / len(raw)
    return [(i * interval, line) for i, line in enumerate(raw)]


def timed_to_srt(timed_lines: list[tuple[float, str]], duration: float) -> str:
    """Convert timed lines → SRT string. Each line ends where the next begins."""
    blocks = []
    for i, (start, text) in enumerate(timed_lines):
        # End time = start of next line, or song end for the last line
        end = timed_lines[i + 1][0] if i + 1 < len(timed_lines) else duration
        # Clamp: end must be after start
        if end <= start:
            end = start + 2.0
        blocks.append(
            f"{i + 1}\n"
            f"{srt_timestamp(start)} --> {srt_timestamp(end)}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)


def get_metadata(path: str) -> tuple[str, str, float]:
    """Return (title, artist, duration). Falls back to filename parsing."""
    audio    = MP3(path)
    duration = audio.info.length
    title, artist = "", ""

    try:
        tags       = ID3(path)
        raw_title  = str(tags.get("TIT2", "")).split(":")[-1].strip()
        raw_artist = str(tags.get("TPE1", "")).split(":")[-1].strip()
        if raw_title  not in ("", "None"):  title  = raw_title
        if raw_artist not in ("", "None"):  artist = raw_artist
    except Exception:
        pass

    if not title or not artist:
        stem = os.path.splitext(os.path.basename(path))[0]
        if " - " in stem:
            parts = stem.split(" - ", 1)
            if not artist: artist = parts[0].strip()
            if not title:  title  = parts[1].strip()
            print(f"[INFO] Filename parsed  →  artist='{artist}'  title='{title}'")
        else:
            if not title:  title  = stem
            if not artist: artist = "Unknown Artist"

    return title, artist, duration


def fetch_timed_lyrics(title: str, artist: str, duration: float) -> tuple[list, bool]:
    """
    1. Try syncedlyrics with  'Artist - Title'  then  'Title Artist'.
    2. Fall back to Genius plain lyrics with estimated timing.
    Returns (timed_lines, is_synced).
    """
    for query in (f"{artist} - {title}", f"{title} {artist}"):
        print(f"[INFO] Searching synced lyrics: {query}")
        lrc = syncedlyrics.search(query)
        if lrc:
            print("[INFO] Synced (LRC) lyrics found ✓")
            return parse_lrc(lrc), True

    print("[INFO] No synced lyrics found. Trying Genius …")
    if GENIUS_ACCESS_TOKEN == "YOUR_GENIUS_ACCESS_TOKEN_HERE":
        print("[WARN] No Genius token set — skipping Genius lookup.")
        return [], False

    try:
        genius = lyricsgenius.Genius(
            GENIUS_ACCESS_TOKEN,
            skip_non_songs=True,
            verbose=False,
            remove_section_headers=False,
        )
        song = genius.search_song(title, artist)
        if song and song.lyrics:
            print("[INFO] Genius plain lyrics found ✓ (estimated timing)")
            return plain_to_timed(song.lyrics, duration), False
    except Exception as exc:
        print(f"[WARN] Genius error: {exc}")

    return [], False


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    # File picker
    root = tk.Tk()
    root.withdraw()
    mp3_path = filedialog.askopenfilename(
        title="Select an MP3 file",
        filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")]
    )
    root.destroy()

    if not mp3_path:
        print("No file selected. Exiting.")
        sys.exit(0)

    print(f"\n[INFO] File: {mp3_path}")

    title, artist, duration = get_metadata(mp3_path)
    print(f"[INFO] Artist : {artist}")
    print(f"[INFO] Title  : {title}")
    print(f"[INFO] Duration: {duration:.1f}s")

    timed_lines, is_synced = fetch_timed_lyrics(title, artist, duration)

    if not timed_lines:
        print("\n[ERROR] Could not find any lyrics. Exiting.")
        sys.exit(1)

    srt_content = timed_to_srt(timed_lines, duration)

    # Save .srt next to the MP3 with the same base name
    srt_path = os.path.splitext(mp3_path)[0] + ".srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    sync_note = "synced" if is_synced else "estimated timing (no LRC found)"
    print(f"\n[DONE] SRT saved ({sync_note}):\n  {srt_path}\n")


if __name__ == "__main__":
    main()