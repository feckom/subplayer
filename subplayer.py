import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
import zipfile
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

# ==============================================================================
# SOURCES AND CONFIGURATION FOR SUBPLAYER
# ==============================================================================
PROJECT_NAME = "subplayer"
VERSION = "2.5"
CACHE_DIR_NAME = ".cache"
SUBS_DIR_NAME = "subs"
AUDIO_DIR_NAME = "audio"
ARGOS_MODELS_DIR_NAME = "argos_models"
ARGOS_PKG_DIR_NAME = "argos_pkg"
WHISPER_MODE_MARKER = ".whisper_mode"
FFMPEG_GITHUB_RELEASES_API = "https://api.github.com/repos/FFmpeg-Builds/FFmpeg-Builds/releases"
WHISPER_GITHUB_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases"

_HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
WHISPER_MODEL_URLS: dict[str, str] = {
    name: _HF + name
    for name in (
        "ggml-tiny.bin",
        "ggml-tiny.en.bin",
        "ggml-base.bin",
        "ggml-base.en.bin",
        "ggml-small.bin",
        "ggml-small.en.bin",
        "ggml-medium.bin",
        "ggml-medium.en.bin",
        "ggml-large-v3.bin",
        "ggml-large-v3-turbo.bin",
    )
}
_WHISPER_MODEL_URLS_LOWER = {k.lower(): v for k, v in WHISPER_MODEL_URLS.items()}

FALLBACK_URLS = {
    "model_base": WHISPER_MODEL_URLS["ggml-base.bin"],
    "whisper_cuda_zip": "",
    "whisper_cpu_zip": "https://sourceforge.net/projects/whisper-cpp.mirror/files/v1.9.2/whisper-bin-x64.zip/download",
    "ffmpeg_zip": "",
    "mplayer_archive": "https://sourceforge.net/projects/mplayer-win32/files/MPlayer%20and%20MEncoder/r38677+g1bce40cb73/MPlayer-x86_64-r38677+g1bce40cb73.7z/download",
}

DEFAULT_MODEL = "ggml-small.bin"
DEFAULT_SUB_SCALE = 2.2
PROMPT_TIMEOUT_SEC = 15
MAX_CONSECUTIVE_MUSIC_BLOCKS = 2
DOWNLOAD_CHUNK = 1 << 20  # 1 MiB
SEP_LINE = "=" * 74
MUSIC_GLYPH = "♪ ♪"

QUICK_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English (base EN subtitles)"),
    ("sk", "Slovak (offline translation -> SK)"),
    ("cs", "Czech (offline translation -> CS)"),
    ("de", "German (offline translation -> DE)"),
    ("pl", "Polish (offline translation -> PL)"),
    ("ru", "Russian (offline translation -> RU)"),
    ("uk", "Ukrainian (offline translation -> UK)"),
    ("hu", "Hungarian (offline translation -> HU)"),
    ("es", "Spanish (offline translation -> ES)"),
    ("fr", "French (offline translation -> FR)"),
    ("it", "Italian (offline translation -> IT)"),
    ("ja", "Japanese (offline translation -> JA)"),
    ("zh", "Chinese (offline translation -> ZH)"),
]

SUPPORTED_LANGUAGES: dict[str, str] = {
    "af": "Afrikaans",
    "am": "Amharic",
    "ar": "Arabic",
    "as": "Assamese",
    "az": "Azerbaijani",
    "ba": "Bashkir",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bo": "Tibetan",
    "br": "Breton",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fo": "Faroese",
    "fr": "French",
    "gl": "Galician",
    "gu": "Gujarati",
    "ha": "Hausa",
    "haw": "Hawaiian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "ht": "Haitian Creole",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "jw": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "la": "Latin",
    "lb": "Luxembourgish",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Myanmar",
    "ne": "Nepali",
    "nl": "Dutch",
    "nn": "Nynorsk",
    "no": "Norwegian",
    "oc": "Occitan",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tr": "Turkish",
    "tt": "Tatar",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "yue": "Cantonese",
    "zh": "Chinese",
}

ISO639_2_TO_1: dict[str, str] = {
    "afr": "af", "amh": "am", "ara": "ar", "asm": "as", "aze": "az",
    "bak": "ba", "bel": "be", "bul": "bg", "ben": "bn", "bod": "bo",
    "tib": "bo", "bre": "br", "bos": "bs", "cat": "ca", "ces": "cs",
    "cze": "cs", "cym": "cy", "wel": "cy", "dan": "da", "deu": "de",
    "ger": "de", "ell": "el", "gre": "el", "eng": "en", "spa": "es",
    "est": "et", "eus": "eu", "baq": "eu", "fas": "fa", "per": "fa",
    "fin": "fi", "fao": "fo", "fra": "fr", "fre": "fr", "glg": "gl",
    "guj": "gu", "hau": "ha", "haw": "haw", "heb": "he", "hin": "hi",
    "hrv": "hr", "hat": "ht", "hun": "hu", "hye": "hy", "arm": "hy",
    "ind": "id", "isl": "is", "ice": "is", "ita": "it", "jpn": "ja",
    "jav": "jw", "kat": "ka", "geo": "ka", "kaz": "kk", "khm": "km",
    "kan": "kn", "kor": "ko", "lat": "la", "ltz": "lb", "lin": "ln",
    "lao": "lo", "lit": "lt", "lav": "lv", "mlg": "mg", "mri": "mi",
    "mao": "mi", "mkd": "mk", "mac": "mk", "mal": "ml", "mon": "mn",
    "mar": "mr", "msa": "ms", "may": "ms", "mlt": "mt", "mya": "my",
    "bur": "my", "nep": "ne", "nld": "nl", "dut": "nl", "nno": "nn",
    "nor": "no", "oci": "oc", "pan": "pa", "pol": "pl", "pus": "ps",
    "por": "pt", "ron": "ro", "rum": "ro", "rus": "ru", "san": "sa",
    "snd": "sd", "sin": "si", "slk": "sk", "slo": "sk", "slv": "sl",
    "sna": "sn", "som": "so", "sqi": "sq", "alb": "sq", "srp": "sr",
    "sun": "su", "swe": "sv", "swa": "sw", "tam": "ta", "tel": "te",
    "tgk": "tg", "tha": "th", "tuk": "tk", "tgl": "tl", "tur": "tr",
    "tat": "tt", "ukr": "uk", "urd": "ur", "uzb": "uz", "vie": "vi",
    "yid": "yi", "yor": "yo", "yue": "yue", "zho": "zh", "chi": "zh",
}

# ==============================================================================
# PRECOMPILED REGEXES
# ==============================================================================
LANG_CLEAN_RE = re.compile(r"[^a-zA-Z0-9_-]+")
NON_ALPHA_RE = re.compile(r"[^a-zA-Z]+")
BLOCK_SPLIT_RE = re.compile(r"\r?\n\r?\n")
TIMESTAMP_LINE_RE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)"
)
STREAM_LINE_RE = re.compile(
    r"Stream\s+#0:(?P<stream_idx>\d+)(?:\((?P<lang>[^)]+)\))?:\s*"
    r"(?P<kind>Video|Audio|Subtitle):\s*(?P<codec>[^,(\s]+)(?P<rest>.*)"
)
INPUT_CONTAINER_RE = re.compile(r"Input\s+#0,\s*(?P<fmt>[^,]+(?:,[^,]+)*?),\s*from\s+")
DURATION_LINE_RE = re.compile(
    r"Duration:\s*(?P<dur>[^,]+),\s*start:\s*(?P<start>[^,]+),\s*bitrate:\s*(?P<br>.+)"
)
# Matches bracketed or parenthesized non-speech tags like [MUSIC], (dramatic music), [GUNSHOTS], etc.
BRACKET_TAG_RE = re.compile(r"\[[^\[\]]*\]|\([^\(\)]*\)")
MUSIC_NOTES_ONLY_RE = re.compile(r"^[\s♪♫♩♬#*~-]+$")
MUSIC_KEYWORDS = (
    "music",
    "blank audio",
    "silence",
    "singing",
    "humming",
    "instrumental",
    "melody",
    "soundtrack",
    "orchestral",
    "song",
)

# ==============================================================================
# CONSOLE OUTPUT HELPERS (MPLAYER-STYLE CLEAN OUTPUT, NO === BANNERS)
# ==============================================================================
def enable_windows_ansi() -> None:
    if os.name == "nt":
        try:
            os.system("")
        except Exception:
            pass


def ok_tag() -> str:
    return "[OK]"


def warn_tag(label: str = "WARN") -> str:
    return f"[{label}]"


def err_tag(label: str = "ERROR") -> str:
    return f"[{label}]"


def info_tag(label: str = "INFO") -> str:
    return f"[{label}]"


def cprint(msg: str = "", end: str = "\n", flush: bool = True) -> None:
    print(msg, end=end, flush=flush)


def cprint_step(msg: str) -> None:
    print(msg, flush=True)


def cprint_dim(msg: str = "", end: str = "\n", flush: bool = True) -> None:
    print(msg, end=end, flush=flush)


def cprint_sep() -> None:
    print(SEP_LINE, flush=True)


def _short_name(name: str, max_len: int = 28) -> str:
    if len(name) <= max_len:
        return name
    keep = max(8, (max_len - 3) // 2)
    return f"{name[:keep]}...{name[-keep:]}"


def _terminal_cols() -> int:
    try:
        cols = shutil.get_terminal_size((80, 24)).columns
        return max(40, cols)
    except Exception:
        return 80


def render_bar_segment(
    ratio: float | None,
    elapsed_sec: float,
    bar_width: int = 32,
    done: bool = False,
) -> str:
    if ratio is not None:
        clamped = min(1.0, max(0.0, ratio))
        filled = int(round(bar_width * clamped))
        empty = bar_width - filled
        return f"[{'#' * filled}{'-' * empty}]"

    pos = int(elapsed_sec * 10) % bar_width
    seg_len = 6
    chars = []
    for i in range(bar_width):
        in_seg = (pos <= i < pos + seg_len) or (
            pos + seg_len > bar_width and i < (pos + seg_len) % bar_width
        )
        chars.append("=" if in_seg else "-")
    return f"[{''.join(chars)}]"


def write_live_line(line: str, state: dict, newline: bool = False) -> None:
    max_w = _terminal_cols() - 1
    if len(line) > max_w:
        line = line[:max_w]
    plain_len = len(line)
    last_len = state.get("last_len", 0)
    pad = " " * max(0, last_len - plain_len)
    state["last_len"] = plain_len
    end = "\n" if newline else ""
    sys.stdout.write(f"\r{line}{pad}{end}")
    sys.stdout.flush()


def finish_live_line_if_needed(state: dict) -> None:
    if state.get("last_len", 0) > 0:
        sys.stdout.write("\n")
        sys.stdout.flush()
        state["last_len"] = 0


def format_pip_progress_bar(
    downloaded: int,
    total_bytes: int | None,
    elapsed_sec: float,
    label: str,
    bar_width: int = 32,
    done: bool = False,
) -> str:
    speed_bps = downloaded / max(elapsed_sec, 0.001)
    if speed_bps >= 1024 * 1024:
        speed_str = f"{speed_bps / (1024 * 1024):.1f} MB/s"
    else:
        speed_str = f"{speed_bps / 1024:.0f} KB/s"

    dl_mb = downloaded / (1024 * 1024)
    if total_bytes and total_bytes > 0:
        ratio = min(1.0, max(0.0, downloaded / total_bytes))
        pct = ratio * 100.0
        tot_mb = total_bytes / (1024 * 1024)
        bar_str = render_bar_segment(ratio, elapsed_sec, bar_width=bar_width, done=done)
        return (
            f"  {bar_str} {dl_mb:.1f}/{tot_mb:.1f} MB ({pct:3.0f}%) "
            f"{speed_str} - {label}"
        )

    bar_str = render_bar_segment(None, elapsed_sec, bar_width=bar_width, done=done)
    return f"  {bar_str} {dl_mb:.1f} MB {speed_str} - {label}"


def format_time_progress_bar(
    cur_sec: float,
    total_sec: float | None,
    elapsed_sec: float,
    label: str,
    extra: str = "",
    bar_width: int = 32,
    done: bool = False,
) -> str:
    extra_part = f" | {extra}" if extra else ""
    if total_sec and total_sec > 0:
        ratio = min(1.0, max(0.0, cur_sec / total_sec))
        pct = ratio * 100.0
        bar_str = render_bar_segment(ratio, elapsed_sec, bar_width=bar_width, done=done)
        return (
            f"  {bar_str} {cur_sec:6.1f}/{total_sec:6.1f}s ({pct:3.0f}%) "
            f"| {elapsed_sec:5.1f}s{extra_part} - {label}"
        )

    bar_str = render_bar_segment(None, elapsed_sec, bar_width=bar_width, done=done)
    return (
        f"  {bar_str} {cur_sec:6.1f}s | {elapsed_sec:5.1f}s{extra_part} - {label}"
    )


# ==============================================================================
# SUBTITLE NAMING & SELECTION HELPERS
# ==============================================================================
def normalize_lang_code(lang: str | None) -> str:
    cleaned = LANG_CLEAN_RE.sub("", (lang or "").strip().lower())
    return cleaned or "en"


def normalize_track_lang_to_iso1(raw_lang: str | None) -> str | None:
    cleaned = LANG_CLEAN_RE.sub("", (raw_lang or "").strip().lower())
    if not cleaned or cleaned in ("und", "unk", "none", "mul"):
        return None
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned
    mapped = ISO639_2_TO_1.get(cleaned)
    if mapped and mapped in SUPPORTED_LANGUAGES:
        return mapped
    return None


def format_lang_display(lang_code: str | None, raw_tag: str | None = None) -> str:
    if lang_code and lang_code in SUPPORTED_LANGUAGES:
        if raw_tag and raw_tag.lower() not in ("", "und", lang_code):
            return f"{lang_code} / {raw_tag} ({SUPPORTED_LANGUAGES[lang_code]})"
        return f"{lang_code} ({SUPPORTED_LANGUAGES[lang_code]})"
    if raw_tag and raw_tag.lower() not in ("", "und"):
        return f"{raw_tag} (unmapped tag)"
    return "und (unspecified / auto-detect)"


def build_srt_path(subs_dir: Path, media_stem: str, lang_code: str) -> Path:
    return subs_dir / f"{media_stem}_{normalize_lang_code(lang_code)}.srt"


def move_srt_to_media_dir(cached_srt_path: Path, media_dir: Path) -> Path:
    if not _file_nonempty(cached_srt_path):
        return cached_srt_path

    dest_path = media_dir / cached_srt_path.name
    try:
        if os.path.abspath(str(cached_srt_path)) == os.path.abspath(str(dest_path)):
            return cached_srt_path
    except OSError:
        pass

    try:
        dest_path.unlink(missing_ok=True)
        shutil.move(str(cached_srt_path), str(dest_path))
        if _file_nonempty(dest_path):
            cprint_step(f"SUB: Saved subtitle file: {dest_path}")
            return dest_path
    except Exception as e:
        cprint(
            f"SUB: Could not move subtitle file to {media_dir} ({e}) "
            f"-> keeping in cache: {cached_srt_path}"
        )

    return cached_srt_path


def _scan_srt_dir(directory: Path, media_stem: str) -> list[Path]:
    if not directory.is_dir():
        return []

    found: list[Path] = []
    stem_lower = media_stem.lower()
    prefix_under = f"{stem_lower}_"
    prefix_dot = f"{stem_lower}."

    try:
        with os.scandir(directory) as it:
            for entry in it:
                name = entry.name
                if not name.lower().endswith(".srt"):
                    continue
                cand_stem = name[:-4]
                cand_lower = cand_stem.lower()
                matches = (
                    cand_lower == stem_lower
                    or (cand_lower.startswith(prefix_under) and len(cand_lower) > len(prefix_under))
                    or (cand_lower.startswith(prefix_dot) and len(cand_lower) > len(prefix_dot))
                )
                if not matches:
                    continue
                try:
                    if not entry.is_file() or entry.stat().st_size <= 0:
                        continue
                except OSError:
                    continue
                found.append(Path(entry.path))
    except OSError:
        return []

    return found


def find_existing_srts_for_media(
    subs_dir: Path, media_stem: str, media_dir: Path | None = None
) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []

    def add_items(items: list[Path]) -> None:
        for p in items:
            key = os.path.normcase(os.path.abspath(str(p)))
            if key not in seen:
                seen.add(key)
                ordered.append(p)

    local_srts: list[Path] = []
    if media_dir is not None:
        local_srts = _scan_srt_dir(media_dir, media_stem)
        local_srts.sort(key=lambda p: (0 if p.stem.lower() == media_stem.lower() else 1, p.name.lower()))
        add_items(local_srts)

    cache_srts = _scan_srt_dir(subs_dir, media_stem)
    en_name = f"{media_stem}_en.srt".lower()
    cache_srts.sort(key=lambda p: (0 if p.name.lower() == en_name else 1, p.name.lower()))
    add_items(cache_srts)

    return ordered


def extract_lang_code_from_srt(srt_path: Path, media_stem: str) -> str | None:
    stem_lower = srt_path.stem.lower()
    base_lower = media_stem.lower()
    for sep in ("_", "."):
        prefix = f"{base_lower}{sep}"
        if stem_lower.startswith(prefix) and len(stem_lower) > len(prefix):
            code = stem_lower[len(prefix) :]
            if code in SUPPORTED_LANGUAGES:
                return code
    return None


def extract_lang_label_from_srt(srt_path: Path, media_stem: str, subs_dir: Path | None = None) -> str:
    src_tag = "cache"
    if subs_dir is not None:
        try:
            in_cache = os.path.commonpath(
                [os.path.abspath(str(srt_path.parent)), os.path.abspath(str(subs_dir))]
            ) == os.path.abspath(str(subs_dir))
            if not in_cache:
                src_tag = "local file"
        except ValueError:
            src_tag = "local file"

    code = extract_lang_code_from_srt(srt_path, media_stem)
    if code:
        full_name = SUPPORTED_LANGUAGES.get(code)
        lang_part = f"{code} ({full_name})" if full_name else code
    elif srt_path.stem.lower() == media_stem.lower():
        lang_part = "same-name SRT"
    else:
        lang_part = "unlabeled"

    return f"{lang_part}, {src_tag}"


def _file_nonempty(p: Path) -> bool:
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


# ==============================================================================
# MEDIA & STREAM PROBING (MPLAYER-STYLE VERBOSE REPORT)
# ==============================================================================
def probe_media_info(ffmpeg_path: Path, media_file: Path) -> dict:
    cmd = [str(ffmpeg_path), "-hide_banner", "-i", str(media_file)]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    info: dict = {
        "container": "unknown",
        "duration_str": "unknown",
        "duration_sec": None,
        "bitrate": "unknown",
        "metadata": [],
        "video_tracks": [],
        "audio_tracks": [],
        "subtitle_tracks": [],
    }

    in_metadata = False
    vid_rel = 0
    aud_rel = 0
    sub_rel = 0

    for raw_line in res.stdout.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        m_cont = INPUT_CONTAINER_RE.search(line)
        if m_cont:
            info["container"] = m_cont.group("fmt").strip()
            in_metadata = False
            continue

        m_dur = DURATION_LINE_RE.search(line)
        if m_dur:
            dur_txt = m_dur.group("dur").strip()
            info["duration_str"] = dur_txt
            info["bitrate"] = m_dur.group("br").strip()
            try:
                h_str, m_str, s_str = dur_txt.split(":")
                info["duration_sec"] = int(h_str) * 3600 + int(m_str) * 60 + float(s_str)
            except Exception:
                info["duration_sec"] = None
            in_metadata = False
            continue

        if stripped == "Metadata:":
            in_metadata = True
            continue

        m_stream = STREAM_LINE_RE.search(line)
        if m_stream:
            in_metadata = False
            kind = m_stream.group("kind")
            stream_idx = int(m_stream.group("stream_idx"))
            raw_lang = (m_stream.group("lang") or "und").strip().lower()
            iso1 = normalize_track_lang_to_iso1(raw_lang)
            codec = m_stream.group("codec").strip()
            rest = (m_stream.group("rest") or "").strip().lstrip(",").strip()
            is_default = "(default)" in rest.lower()
            is_forced = "(forced)" in rest.lower()

            if kind == "Video":
                res_m = re.search(r"\b(\d{2,5}x\d{2,5})\b", rest)
                fps_m = re.search(r"(\d+(?:\.\d+)?)\s*fps", rest)
                pix_m = re.search(r"\b(yuv[a-z0-9]+|rgb[a-z0-9]+|bgr[a-z0-9]+|gray\d*)\b", rest)
                br_m = re.search(r"(\d+(?:\.\d+)?\s*kb/s)", rest)
                info["video_tracks"].append({
                    "video_idx": vid_rel,
                    "stream_idx": stream_idx,
                    "lang": raw_lang,
                    "codec": codec,
                    "resolution": res_m.group(1) if res_m else "",
                    "fps": fps_m.group(1) if fps_m else "",
                    "pix_fmt": pix_m.group(1) if pix_m else "",
                    "bitrate": br_m.group(1) if br_m else "",
                    "default": is_default,
                    "raw_detail": rest,
                })
                vid_rel += 1
            elif kind == "Audio":
                hz_m = re.search(r"(\d+)\s*Hz", rest)
                ch_m = re.search(r",\s*(\d+\s*channels|\d+\s*ch|mono|stereo|5\.1(?:\(side\))?|7\.1)", rest, re.IGNORECASE)
                br_m = re.search(r"(\d+(?:\.\d+)?\s*kb/s)", rest)
                info["audio_tracks"].append({
                    "audio_idx": aud_rel,
                    "stream_idx": stream_idx,
                    "raw_lang": raw_lang,
                    "lang_code": iso1,
                    "codec": codec,
                    "sample_rate": hz_m.group(1) if hz_m else "",
                    "channels": ch_m.group(1) if ch_m else "",
                    "bitrate": br_m.group(1) if br_m else "",
                    "default": is_default,
                    "raw_detail": rest,
                })
                aud_rel += 1
            elif kind == "Subtitle":
                info["subtitle_tracks"].append({
                    "sub_idx": sub_rel,
                    "stream_idx": stream_idx,
                    "raw_lang": raw_lang,
                    "lang_code": iso1,
                    "codec": codec,
                    "default": is_default,
                    "forced": is_forced,
                })
                sub_rel += 1
            continue

        if in_metadata and ":" in stripped and len(info["metadata"]) < 8:
            k, v = stripped.split(":", 1)
            if k.strip() and v.strip() and len(k.strip()) <= 32:
                info["metadata"].append((k.strip(), v.strip()))

    return info


def get_default_audio_track(tracks: list[dict]) -> dict | None:
    if not tracks:
        return None
    return next((t for t in tracks if t["default"]), tracks[0])


def print_mplayer_style_media_report(
    media_file: Path,
    media_info: dict,
    default_track: dict | None,
    existing_srts: list[Path],
    subs_dir: Path,
    ffmpeg_path: Path,
    whisper_path: Path,
    mplayer_path: Path,
    model_path: Path,
    hw: dict,
) -> None:
    try:
        file_size_mb = media_file.stat().st_size / (1024 * 1024)
        size_part = f" ({file_size_mb:.1f} MB)"
    except OSError:
        size_part = ""

    gpu = hw["gpu"]
    gpu_desc = f"{gpu['name']} ({gpu['vram_free_mb']} MB free)" if gpu["has_nvidia"] else "none"
    cpu_mode = f"CPU {hw['recommended_threads']}t"
    backend_mode = "CUDA/GPU" if hw["use_gpu"] else cpu_mode

    cprint(f"\n{PROJECT_NAME} {VERSION} (C) local offline speech-to-subtitle wrapper")
    cprint(f"Analyzing {media_file}{size_part}.")
    cprint(
        f"Container format: [{media_info['container']}] | "
        f"Duration: {media_info['duration_str']} | Bitrate: {media_info['bitrate']}"
    )
    cprint(f"FFmpeg: {ffmpeg_path}")
    cprint(f"Whisper: {whisper_path} [{Path(model_path).name}, {backend_mode}, GPU={gpu_desc}]")
    cprint(f"MPlayer: {mplayer_path}")

    for vt in media_info["video_tracks"]:
        def_flag = " (default)" if vt["default"] else ""
        cprint(
            f"[subplayer] stream {vt['stream_idx']}: video ({vt['codec']}), -vid {vt['video_idx']}{def_flag}"
        )
        res_s = vt["resolution"] or "unknown"
        fps_s = f"{vt['fps']} fps" if vt["fps"] else ""
        pix_s = vt["pix_fmt"] or ""
        br_s = vt["bitrate"] or ""
        parts = [p for p in (res_s, pix_s, fps_s, br_s) if p]
        cprint(f"VIDEO:  [{vt['codec'].upper()}]  {'  '.join(parts)}")

    for at in media_info["audio_tracks"]:
        def_flag = " (default)" if at["default"] else ""
        lang_human = format_lang_display(at["lang_code"], at["raw_lang"])
        cprint(
            f"[subplayer] stream {at['stream_idx']}: audio ({at['codec']}), "
            f"-aid {at['audio_idx']}, -alang {at['raw_lang']} -> {lang_human}{def_flag}"
        )
        hz_s = f"{at['sample_rate']} Hz" if at["sample_rate"] else ""
        ch_s = at["channels"] or ""
        br_s = at["bitrate"] or ""
        a_parts = [p for p in (hz_s, ch_s, br_s) if p]
        cprint(f"AUDIO:  [{at['codec'].upper()}]  {', '.join(a_parts)}")

    for st in media_info["subtitle_tracks"]:
        flags = []
        if st["default"]:
            flags.append("default")
        if st["forced"]:
            flags.append("forced")
        flag_s = f" ({', '.join(flags)})" if flags else ""
        lang_human = format_lang_display(st["lang_code"], st["raw_lang"])
        cprint(
            f"[subplayer] stream {st['stream_idx']}: embedded subtitle ({st['codec']}), "
            f"-sid {st['sub_idx']}, -slang {st['raw_lang']} -> {lang_human}{flag_s}"
        )

    if media_info["metadata"]:
        cprint_sep()
        cprint("Clip info:")
        for k, v in media_info["metadata"]:
            cprint(f" {k}: {v}")

    cprint_sep()
    if default_track is not None:
        lang_disp = format_lang_display(default_track["lang_code"], default_track["raw_lang"])
        cprint(
            f"Default audio track: -aid {default_track['audio_idx']} "
            f"(stream 0:{default_track['stream_idx']}) | Language: {lang_disp} | Codec: [{default_track['codec']}]"
        )
    else:
        cprint("Default audio track: none detected (will attempt stream 0:a:0)")

    if existing_srts:
        for i, srt in enumerate(existing_srts, start=1):
            lbl = extract_lang_label_from_srt(srt, media_file.stem, subs_dir=subs_dir)
            cprint(f"SUB: Found external subtitle file ({i}): {srt} [{lbl}]")
    else:
        cprint(f"SUB: No external .srt files found in {media_file.parent} or {subs_dir}")
    cprint_sep()


def prompt_create_default_track_srt(
    default_track: dict,
    target_srt_name: str,
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> tuple[str, str | None]:
    track_lang = default_track["lang_code"] or "en"
    lang_label = format_lang_display(default_track["lang_code"], default_track["raw_lang"])
    short_srt = _short_name(target_srt_name, 26)

    if not sys.stdin.isatty():
        return "fallback_default", None

    cprint_step(
        f"SUB: Default audio track #{default_track['audio_idx']} is [{lang_label}], "
        f"'{target_srt_name}' does not exist."
    )
    cprint_dim(
        f"     Press Enter/'y' to create '{short_srt}', type a language code (sk, cs, de...), "
        f"or wait {timeout_sec}s for default behavior."
    )

    prompt_str = f"Create '{short_srt}' in {track_lang}? [Y / sk / cs / ...]: "
    first_attempt = True

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, "default flow"
                )
                if timed_out:
                    cprint_step(
                        f"{info_tag()} Prompt timeout ({timeout_sec}s) reached -> "
                        f"continuing with default logic."
                    )
                    return "fallback_default", None
            else:
                raw = input(prompt_str)
        except EOFError:
            return "fallback_default", None

        raw = (raw or "").strip()
        if not raw or raw.lower() in ("y", "yes", "ok", "1"):
            cprint_step(f"{ok_tag()} Confirmed: generating {target_srt_name}")
            return "track_lang", track_lang

        lower = raw.lower()
        if lower in ("n", "no", "other", "new"):
            return "other_lang", None

        if lower in SUPPORTED_LANGUAGES:
            cprint_step(f"{ok_tag()} Selected target language: {lower}")
            return "other_lang", lower

        cprint(
            f"{warn_tag()} Invalid input '{raw}'. Press Enter/'y' to create {short_srt}, "
            f"or enter a language code (e.g. sk, cs, en)."
        )


def prompt_use_or_convert_existing_srt(
    existing_srt: Path,
    default_track: dict | None,
    media_stem: str,
    subs_dir: Path | None = None,
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> tuple[bool, str | None]:
    if not sys.stdin.isatty():
        return False, None

    srt_info = extract_lang_label_from_srt(existing_srt, media_stem, subs_dir=subs_dir)
    short_srt = _short_name(existing_srt.name, 26)
    cprint_step(f"SUB: Existing subtitle file: {existing_srt.name} [{srt_info}]")
    cprint_dim(
        f"     Press Enter or wait {timeout_sec}s to play with '{short_srt}', "
        f"or enter a target language code (sk, cs, de...) / 'y' to convert."
    )

    prompt_str = f"Use '{short_srt}' or convert? [Enter=use / sk / cs / y]: "
    first_attempt = True

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, f"play {short_srt}"
                )
                if timed_out:
                    cprint_step(
                        f"{info_tag()} Prompt timeout ({timeout_sec}s) reached -> "
                        f"using {existing_srt.name}."
                    )
                    return False, None
            else:
                raw = input(prompt_str)
        except EOFError:
            return False, None

        raw = (raw or "").strip()
        if not raw or raw.lower() in ("n", "no", "use", "play", "skip"):
            cprint_step(f"{ok_tag()} Using existing subtitles: {existing_srt.name}")
            return False, None

        lower = raw.lower()
        if lower in ("y", "yes", "convert", "tr", "translate", "new"):
            return True, None

        if lower in SUPPORTED_LANGUAGES:
            cprint_step(f"{ok_tag()} Converting {existing_srt.name} -> '{lower}'")
            return True, lower

        cprint(
            f"{warn_tag()} Invalid input '{raw}'. Press Enter to use '{short_srt}', "
            f"or enter a language code (e.g. sk, cs, de)."
        )


# ==============================================================================
# OFFLINE TRANSLATION (EXTERNAL PYTHON SUBPROCESS)
# ==============================================================================
def set_argos_env_before_import(models_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGE_DIR"] = str(models_dir)
    os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(models_dir)


def _is_frozen_executable() -> bool:
    return bool(getattr(sys, "frozen", False))


def _find_external_python_executables() -> list[list[str]]:
    candidates: list[list[str]] = []
    self_exe = ""
    try:
        self_exe = os.path.normcase(os.path.abspath(sys.executable))
    except OSError:
        self_exe = ""

    def _is_self(exe_path: str | None) -> bool:
        if not exe_path or not self_exe:
            return False
        try:
            return os.path.normcase(os.path.abspath(exe_path)) == self_exe
        except OSError:
            return False

    if not _is_frozen_executable() and sys.executable and not _is_self(sys.executable):
        candidates.append([sys.executable])

    if os.name == "nt":
        py_launcher = shutil.which("py")
        if py_launcher and not _is_self(py_launcher):
            candidates.append([py_launcher, "-3"])
            candidates.append([py_launcher])

        for py_name in ("python.exe", "python3.exe"):
            found = shutil.which(py_name)
            if found and not _is_self(found) and [found] not in candidates:
                candidates.append([found])

        search_roots: list[Path] = []
        local_app = os.environ.get("LOCALAPPDATA")
        prog_files = os.environ.get("ProgramFiles")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)")
        if local_app:
            search_roots.append(Path(local_app) / "Programs" / "Python")
        if prog_files:
            search_roots.append(Path(prog_files))
        if prog_files_x86:
            search_roots.append(Path(prog_files_x86))

        for root in search_roots:
            if not root.is_dir():
                continue
            try:
                for entry in sorted(root.iterdir(), reverse=True):
                    cand_py = entry / "python.exe"
                    if cand_py.is_file() and not _is_self(str(cand_py)):
                        cmd = [str(cand_py)]
                        if cmd not in candidates:
                            candidates.append(cmd)
            except OSError:
                continue
    else:
        for py_name in ("python3", "python"):
            found = shutil.which(py_name)
            if found and not _is_self(found) and [found] not in candidates:
                candidates.append([found])

    return candidates


def _find_external_pip_commands() -> list[list[str]]:
    cmds: list[list[str]] = [py + ["-m", "pip"] for py in _find_external_python_executables()]
    pip_exe = shutil.which("pip.exe" if os.name == "nt" else "pip3") or shutil.which("pip")
    if pip_exe and [pip_exe] not in cmds:
        cmds.append([pip_exe])
    return cmds


_WORKER_SCRIPT = r"""
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path

BLOCK_SPLIT_RE = re.compile(r"\r?\n\r?\n")

def main():
    if len(sys.argv) < 6:
        print("ERR: missing arguments", file=sys.stderr)
        sys.exit(2)

    src_srt_path = Path(sys.argv[1])
    out_srt_path = Path(sys.argv[2])
    target_lang = sys.argv[3]
    models_dir = Path(sys.argv[4])
    pkg_dir = Path(sys.argv[5])
    source_lang = sys.argv[6] if len(sys.argv) >= 7 and sys.argv[6] else "en"

    models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGE_DIR"] = str(models_dir)
    os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(models_dir)

    pkg_str = os.path.abspath(str(pkg_dir))
    if pkg_str in sys.path:
        sys.path.remove(pkg_str)
    sys.path.append(pkg_str)
    importlib.invalidate_caches()

    import argostranslate.package as argos_pkg
    import argostranslate.translate as argos_tr
    import argostranslate.settings as argos_settings

    argos_settings.package_data_dir = models_dir
    argos_settings.package_dirs = [models_dir]
    if hasattr(argos_settings, "packages_dir"):
        argos_settings.packages_dir = models_dir

    def has_pair(frm: str, to: str) -> bool:
        langs = argos_tr.get_installed_languages()
        src_l = next((l for l in langs if getattr(l, "code", None) == frm), None)
        if not src_l:
            return False
        for tr in getattr(src_l, "translations_from", []) or []:
            to_l = getattr(tr, "to_lang", None)
            if getattr(to_l, "code", None) == to:
                return True
        return False

    def ensure_pair(frm: str, to: str) -> bool:
        if frm == to or has_pair(frm, to):
            return True
        print(f"STATUS:Downloading Argos model {frm}->{to}...", flush=True)
        argos_pkg.update_package_index()
        available = argos_pkg.get_available_packages()
        pkg = next((p for p in available if p.from_code == frm and p.to_code == to), None)
        if pkg is None:
            return False
        dl_path = pkg.download()
        if not dl_path or not Path(dl_path).is_file():
            return False
        argos_pkg.install_from_path(dl_path)
        importlib.reload(argos_pkg)
        importlib.reload(argos_tr)
        return has_pair(frm, to)

    use_pivot = False
    if ensure_pair(source_lang, target_lang):
        use_pivot = False
    elif source_lang != "en" and target_lang != "en" and ensure_pair(source_lang, "en") and ensure_pair("en", target_lang):
        use_pivot = True
    else:
        print(f"ERR:No offline model available for {source_lang}->{target_lang}", file=sys.stderr)
        sys.exit(3)

    langs = argos_tr.get_installed_languages()
    if not use_pivot:
        src_l = next(l for l in langs if getattr(l, "code", None) == source_lang)
        to_l = next(l for l in langs if getattr(l, "code", None) == target_lang)
        tr_obj = src_l.get_translation(to_l)
        translate_fn = tr_obj.translate if tr_obj is not None else (lambda t: argos_tr.translate(t, source_lang, target_lang))
    else:
        src_l = next(l for l in langs if getattr(l, "code", None) == source_lang)
        en_l = next(l for l in langs if getattr(l, "code", None) == "en")
        to_l = next(l for l in langs if getattr(l, "code", None) == target_lang)
        tr1 = src_l.get_translation(en_l)
        tr2 = en_l.get_translation(to_l)
        def translate_fn(t: str) -> str:
            mid = tr1.translate(t) if tr1 is not None else argos_tr.translate(t, source_lang, "en")
            return tr2.translate(mid) if tr2 is not None else argos_tr.translate(mid, "en", target_lang)

    raw_content = src_srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = BLOCK_SPLIT_RE.split(raw_content.strip())
    parsed_blocks = []
    total_lines = 0
    for blk in blocks:
        lines = [ln.rstrip("\r") for ln in blk.splitlines()]
        if len(lines) >= 3 and "-->" in lines[1]:
            txt_lines = lines[2:]
            parsed_blocks.append((lines[0].strip(), lines[1].strip(), txt_lines))
            total_lines += sum(1 for t in txt_lines if t.strip())
        elif lines:
            parsed_blocks.append(("", "", lines))

    if total_lines == 0:
        print("ERR:Source SRT has no translatable lines", file=sys.stderr)
        sys.exit(6)

    done_lines = 0
    translated_ok = 0
    fallback_lines = 0
    cache = {}
    out_blocks = []
    last_report = 0.0

    for idx_line, ts_line, txt_lines in parsed_blocks:
        if not ts_line:
            out_blocks.append("\n".join(txt_lines))
            continue

        tr_lines = []
        for ln in txt_lines:
            stripped = ln.strip()
            if not stripped:
                tr_lines.append("")
                continue

            if "♪" in stripped and not any(ch.isalpha() for ch in stripped):
                tr_lines.append(stripped)
                translated_ok += 1
                done_lines += 1
                continue

            res = cache.get(stripped)
            if res is None:
                try:
                    raw_tr = translate_fn(stripped)
                    res = " ".join((raw_tr or "").splitlines()).strip()
                except Exception:
                    res = ""
                cache[stripped] = res

            if res:
                tr_lines.append(res)
                translated_ok += 1
            else:
                tr_lines.append(stripped)
                fallback_lines += 1

            done_lines += 1
            now = time.monotonic()
            if now - last_report >= 0.15:
                last_report = now
                print(f"PROGRESS:{done_lines}/{total_lines}", flush=True)

        out_blocks.append(f"{idx_line}\n{ts_line}\n" + "\n".join(tr_lines))

    out_srt_path.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out_srt_path.with_suffix(".part.srt")
    with open(temp_out, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n\n".join(out_blocks) + "\n")
    os.replace(temp_out, out_srt_path)

    print(f"PROGRESS:{total_lines}/{total_lines}", flush=True)
    print(f"DONE:{translated_ok}/{total_lines}:{fallback_lines}", flush=True)

if __name__ == "__main__":
    main()
"""


def _ensure_argostranslate_via_pip(pkg_dir: Path, models_dir: Path) -> bool:
    pkg_dir.mkdir(parents=True, exist_ok=True)
    if (pkg_dir / "argostranslate").is_dir():
        cprint(f"  {ok_tag()} Argos Translate package found in {pkg_dir}.")
        return True

    pip_cmds = _find_external_pip_commands()
    if not pip_cmds:
        cprint(f"  {err_tag()} Cannot install 'argostranslate': no external Python/pip found.")
        return False

    cprint_step(f"  {info_tag()} Installing 'argostranslate' into {pkg_dir} via pip...")
    bar_state = {"last_len": 0}
    start_ts = time.time()
    installed_cnt = 0
    last_rc = 1
    last_tail = "no output captured"

    for base_cmd in pip_cmds:
        cmd = base_cmd + [
            "install",
            "--upgrade",
            "--no-warn-script-location",
            "--target",
            str(pkg_dir),
            "argostranslate",
        ]
        recent_lines: list[str] = []
        installed_cnt = 0
        start_ts = time.time()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as e:
            last_tail = str(e)
            continue

        try:
            if proc.stdout:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    recent_lines.append(line)
                    if len(recent_lines) > 12:
                        recent_lines.pop(0)

                    if line.startswith("Collecting "):
                        pkg_name = line.split("Collecting ", 1)[1].split()[0]
                        write_live_line(
                            f"    [pip] Resolving {pkg_name}... ({time.time() - start_ts:.0f}s)",
                            bar_state,
                            newline=False,
                        )
                    elif line.startswith("Installing collected packages:"):
                        pkgs = [p.strip() for p in line.split(":", 1)[1].split(",") if p.strip()]
                        installed_cnt = len(pkgs)
                        write_live_line(
                            f"    [pip] Installing {installed_cnt} packages into {pkg_dir}...",
                            bar_state,
                            newline=False,
                        )
                    elif line.startswith("ERROR:"):
                        finish_live_line_if_needed(bar_state)
                        cprint(f"    {warn_tag()} {line}")
            rc = proc.wait()
        except KeyboardInterrupt:
            finish_live_line_if_needed(bar_state)
            if proc.poll() is None:
                proc.terminate()
            raise

        finish_live_line_if_needed(bar_state)
        last_rc = rc
        if rc == 0 and (pkg_dir / "argostranslate").is_dir():
            cprint_step(
                f"  {ok_tag()} Package 'argostranslate' installed in {time.time() - start_ts:.1f}s ({installed_cnt} pkgs)."
            )
            return True
        if recent_lines:
            last_tail = " | ".join(recent_lines[-3:])

    cprint(f"  {err_tag()} Cannot install 'argostranslate' (pip exit code {last_rc}): {last_tail}")
    return False


def translate_srt_file_offline(
    en_srt_path: Path,
    out_srt_path: Path,
    target_lang: str,
    models_dir: Path,
    pkg_dir: Path,
    source_lang: str = "en",
) -> bool:
    if not en_srt_path.is_file() or en_srt_path.stat().st_size <= 0:
        cprint(f"  {err_tag()} Source SRT is missing or empty: {en_srt_path}")
        return False

    src_code = normalize_lang_code(source_lang)
    target = normalize_lang_code(target_lang)

    cprint_sep()
    cprint_step(f"Opening offline subtitle translator: [argostranslate] ({src_code.upper()} -> {target.upper()})")
    cprint(f"SUB: Source: {en_srt_path}")
    cprint(f"SUB: Output: {out_srt_path}")

    if not _ensure_argostranslate_via_pip(pkg_dir, models_dir):
        cprint(f"  {warn_tag()} Skipping offline translation because 'argostranslate' is unavailable.")
        return False

    py_cmds = _find_external_python_executables()
    if not py_cmds:
        cprint(
            f"  {err_tag()} Cannot run offline translation: no external python.exe found to run argostranslate."
        )
        return False

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(_WORKER_SCRIPT)
        worker_path = Path(tf.name)

    start_wall = time.time()
    bar_state = {"last_len": 0}
    last_err = ""

    try:
        for py_cmd in py_cmds:
            cmd = py_cmd + [
                str(worker_path),
                str(en_srt_path),
                str(out_srt_path),
                target,
                str(models_dir),
                str(pkg_dir),
                src_code,
            ]
            err_lines: list[str] = []
            done_summary = ""
            total_est = 1
            cur_est = 0

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as e:
                last_err = str(e)
                continue

            def _read_err():
                if proc.stderr:
                    for ln in proc.stderr:
                        s = ln.strip()
                        if s:
                            err_lines.append(s)

            t_err = threading.Thread(target=_read_err, daemon=True)
            t_err.start()

            try:
                if proc.stdout:
                    for raw_line in proc.stdout:
                        line = raw_line.strip()
                        if not line:
                            continue
                        if line.startswith("STATUS:"):
                            finish_live_line_if_needed(bar_state)
                            cprint(f"  {info_tag()} {line.split(':', 1)[1]}")
                        elif line.startswith("PROGRESS:"):
                            parts = line.split(":", 1)[1].split("/")
                            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                cur_est = int(parts[0])
                                total_est = max(1, int(parts[1]))
                                write_live_line(
                                    format_time_progress_bar(
                                        cur_sec=float(cur_est),
                                        total_sec=float(total_est),
                                        elapsed_sec=time.time() - start_wall,
                                        label=f"Translating {src_code.upper()}->{target.upper()}",
                                        done=False,
                                    ),
                                    bar_state,
                                    newline=False,
                                )
                        elif line.startswith("DONE:"):
                            done_summary = line.split(":", 1)[1]
                rc = proc.wait()
            except KeyboardInterrupt:
                finish_live_line_if_needed(bar_state)
                if proc.poll() is None:
                    proc.terminate()
                raise
            finally:
                t_err.join(timeout=2)

            finish_live_line_if_needed(bar_state)
            if rc == 0 and _file_nonempty(out_srt_path):
                write_live_line(
                    format_time_progress_bar(
                        cur_sec=float(total_est),
                        total_sec=float(total_est),
                        elapsed_sec=time.time() - start_wall,
                        label=f"Translating {src_code.upper()}->{target.upper()}",
                        done=True,
                    ),
                    bar_state,
                    newline=True,
                )
                cprint_step(
                    f"  {ok_tag()} Converted SRT saved in {time.time() - start_wall:.1f}s ({done_summary})"
                )
                return True

            if err_lines:
                last_err = err_lines[-1]
            else:
                last_err = f"worker exited with code {rc}"

        cprint(f"  {err_tag()} Offline conversion failed: {last_err}")
        cprint(f"  {warn_tag()} Offline translation {src_code} -> {target} could not proceed.")
        return False
    finally:
        worker_path.unlink(missing_ok=True)


# ==============================================================================
# LANGUAGE PROMPT & EXISTING SRT SELECTION (WITH 15s AUTO TIMEOUT ON ONE LINE)
# ==============================================================================
def print_all_supported_languages() -> None:
    cprint(f"\nSupported language codes ({len(SUPPORTED_LANGUAGES)} total):")
    items = [f"{code}: {name}" for code, name in sorted(SUPPORTED_LANGUAGES.items())]
    cols = 4
    col_width = 24
    for i in range(0, len(items), cols):
        row = "".join(entry.ljust(col_width) for entry in items[i : i + cols])
        cprint_dim(f"  {row.rstrip()}")


def _input_with_idle_timeout(
    prompt_text: str, timeout_sec: int, timeout_hint: str
) -> tuple[str | None, bool]:
    deadline = time.monotonic() + timeout_sec
    last_shown = -1

    def _fit_line(sec_left: int) -> str:
        max_w = max(30, _terminal_cols() - 1)
        prefix = f"[{sec_left:2d}s -> {timeout_hint}] "
        avail = max(10, max_w - len(prefix))
        p_txt = (
            prompt_text
            if len(prompt_text) <= avail
            else (prompt_text[: max(1, avail - 3)] + "...")
        )
        line = prefix + p_txt
        return f"{line:<{max_w}}"[:max_w]

    def _clear() -> None:
        max_w = max(30, _terminal_cols() - 1)
        sys.stdout.write("\r" + (" " * max_w) + "\r")
        sys.stdout.flush()

    def tick() -> bool:
        nonlocal last_shown
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _clear()
            return False
        sec_left = int(remaining) + 1
        if sec_left != last_shown:
            last_shown = sec_left
            sys.stdout.write("\r" + _fit_line(sec_left))
            sys.stdout.flush()
        return True

    if os.name == "nt":
        while True:
            if not tick():
                return None, True
            if msvcrt.kbhit():
                _clear()
                return input(prompt_text), False
            time.sleep(0.05)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            if not tick():
                return None, True
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    _clear()
    return input(prompt_text), False


def prompt_select_existing_srt(
    existing_srts: list[Path],
    media_stem: str,
    subs_dir: Path | None = None,
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> Path | None:
    default_target = next(
        (p for p in existing_srts if p.stem.lower() == media_stem.lower()),
        None,
    ) or next(
        (p for p in existing_srts if p.name.lower() == f"{media_stem}_en.srt".lower()),
        existing_srts[0],
    )

    if not sys.stdin.isatty():
        return default_target

    short_def = _short_name(default_target.name, 26)
    cprint_step(
        f"SUB: Found {len(existing_srts)} subtitles for '{_short_name(media_stem, 32)}' — select which to use:"
    )
    for idx, p in enumerate(existing_srts, start=1):
        lang_info = extract_lang_label_from_srt(p, media_stem, subs_dir=subs_dir)
        default_mark = "  <-- default on timeout/Enter" if p == default_target else ""
        cprint(f"    {idx:2d}) {p.name} [{lang_info}]{default_mark}")
    cprint("   new) Convert / generate subtitles in another language")
    cprint_dim(
        f"     If nothing is entered within {timeout_sec}s (or Enter is pressed), "
        f"auto-selecting: {short_def}"
    )

    prompt_str = f"Select subtitle (1..{len(existing_srts)}, lang code, or 'new'): "
    first_attempt = True
    by_lower_name = {p.name.lower(): p for p in existing_srts}

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, f"auto {short_def}"
                )
                if timed_out:
                    cprint_step(
                        f"{info_tag()} Prompt timeout ({timeout_sec}s) reached -> "
                        f"auto-selecting {default_target.name}."
                    )
                    return default_target
            else:
                raw = input(prompt_str)
        except EOFError:
            return default_target

        raw = (raw or "").strip()
        if not raw:
            cprint_step(f"{ok_tag()} Selected default subtitles: {default_target.name}")
            return default_target

        lower = raw.lower()
        if lower in ("new", "n", "gen", "generate", "tr", "translate"):
            return None

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(existing_srts):
                chosen = existing_srts[idx - 1]
                cprint_step(f"{ok_tag()} Selected subtitles: {chosen.name}")
                return chosen

        for sep in ("_", "."):
            chosen = by_lower_name.get(f"{media_stem}{sep}{lower}.srt".lower())
            if chosen is not None:
                cprint_step(f"{ok_tag()} Selected subtitles: {chosen.name}")
                return chosen

        cprint(
            f"{warn_tag()} Invalid selection '{raw}'. Enter 1..{len(existing_srts)}, a language code, or 'new'."
        )


def prompt_target_language(
    default_lang: str = "en",
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> str:
    if not sys.stdin.isatty():
        return default_lang

    cprint_step(
        "SUB: Select target subtitle language (uses existing SRT if available, or transcribes & converts offline):"
    )
    cprint_dim(
        f"     If nothing is entered within {timeout_sec}s, defaulting to '{default_lang}'."
    )
    for idx, (code, desc) in enumerate(QUICK_LANGUAGES, start=1):
        cprint(f"    {idx:2d}) {code:<4} - {desc}")
    cprint("   list) Show all supported language codes")

    prompt_str = f"Enter number, language code (en, sk, cs, de...), or 'list' [Enter={default_lang}]: "
    first_attempt = True

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, f"auto {default_lang}"
                )
                if timed_out:
                    cprint_step(
                        f"{info_tag()} Prompt timeout ({timeout_sec}s) reached -> "
                        f"auto-selecting '{default_lang}'."
                    )
                    return default_lang
            else:
                raw = input(prompt_str)
        except EOFError:
            return default_lang

        raw = (raw or "").strip()
        if not raw:
            return default_lang

        lower = raw.lower()
        if lower in ("list", "ls", "?"):
            print_all_supported_languages()
            continue

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(QUICK_LANGUAGES):
                chosen = QUICK_LANGUAGES[idx - 1][0]
                cprint_step(f"{ok_tag()} Selected language: {chosen}")
                return chosen
            cprint(f"{warn_tag()} Invalid number. Enter 1..{len(QUICK_LANGUAGES)} or a language code.")
            continue

        if lower in SUPPORTED_LANGUAGES:
            cprint_step(f"{ok_tag()} Selected language: {lower}")
            return lower

        cprint(
            f"{warn_tag()} Unknown language code '{raw}'. Enter 'list' for all codes or e.g. 'en', 'sk', 'cs'."
        )


# ==============================================================================
# HARDWARE DETECTION
# ==============================================================================
def detect_hardware() -> dict:
    cpu_threads = os.cpu_count() or 4
    gpu_info = {
        "has_nvidia": False,
        "name": "",
        "vram_free_mb": 0,
        "vram_total_mb": 0,
    }

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi and os.name == "nt":
        default_smi = (
            Path(os.environ.get("ProgramW6432", "C:\\Program Files"))
            / "NVIDIA Corporation\\NVSMI\\nvidia-smi.exe"
        )
        if default_smi.is_file():
            nvidia_smi = str(default_smi)

    if nvidia_smi:
        try:
            res = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.free,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                first_line = res.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in first_line.split(",")]
                if len(parts) >= 3:
                    gpu_info["has_nvidia"] = True
                    gpu_info["name"] = parts[0]
                    gpu_info["vram_free_mb"] = int(float(parts[1]))
                    gpu_info["vram_total_mb"] = int(float(parts[2]))
        except Exception:
            pass

    use_gpu = bool(gpu_info["has_nvidia"] and gpu_info["vram_free_mb"] >= 1024)
    if use_gpu:
        recommended_threads = min(4, max(2, cpu_threads // 2))
    else:
        recommended_threads = max(1, cpu_threads - 1) if cpu_threads > 2 else cpu_threads

    return {
        "cpu_threads": cpu_threads,
        "use_gpu": use_gpu,
        "gpu": gpu_info,
        "recommended_threads": recommended_threads,
    }


def get_work_dir() -> Path:
    return Path.cwd()


def _ensure_subdir(parent: Path, name: str) -> Path:
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cache_dir(work_dir: Path) -> Path:
    return _ensure_subdir(work_dir, CACHE_DIR_NAME)


def get_subs_dir(cache_dir: Path) -> Path:
    return _ensure_subdir(cache_dir, SUBS_DIR_NAME)


def get_audio_dir(cache_dir: Path) -> Path:
    return _ensure_subdir(cache_dir, AUDIO_DIR_NAME)


def get_argos_models_dir(cache_dir: Path) -> Path:
    return _ensure_subdir(cache_dir, ARGOS_MODELS_DIR_NAME)


def get_argos_pkg_dir(cache_dir: Path) -> Path:
    return _ensure_subdir(cache_dir, ARGOS_PKG_DIR_NAME)


def find_in_system_path(filename: str) -> Path | None:
    candidates: list[str] = [filename]
    if os.name == "nt" and not filename.lower().endswith(".exe"):
        candidates.insert(0, f"{filename}.exe")
    for cand in candidates:
        found = shutil.which(cand)
        if found:
            p = Path(found)
            if p.is_file():
                return p
    return None


def resolve_tool_path(cache_dir: Path, work_dir: Path, filename: str) -> Path:
    """
    Order for ffmpeg/mplayer:
      1. .cache
      2. system PATH
      3. work_dir / fallback .cache path
    For whisper (and others): .cache -> work_dir (never PATH).
    """
    cached_path = cache_dir / filename
    if cached_path.is_file():
        return cached_path

    base_lower = filename.lower()
    if base_lower in ("ffmpeg", "ffmpeg.exe", "mplayer", "mplayer.exe"):
        path_match = find_in_system_path(filename)
        if path_match is not None:
            return path_match

    local_path = work_dir / filename
    if local_path.is_file():
        return local_path

    return cached_path


def cleanup_wav_file(wav_path: Path, reason: str = "") -> None:
    try:
        wav_path.unlink()
    except FileNotFoundError:
        return
    except Exception as e:
        cprint(f"  {warn_tag()} Could not remove temporary WAV {wav_path}: {e}")
        return
    suffix = f" ({reason})" if reason else ""
    cprint(f"  {info_tag()} Removed temporary WAV{suffix}: {wav_path.name}")


def get_wav_duration_sec(wav_path: Path) -> float | None:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if frames > 0 and rate > 0:
                return frames / float(rate)
    except Exception:
        pass
    return None


def http_get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"{PROJECT_NAME}/{VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def download_file(url: str, dest_path: Path, label: str = "") -> bool:
    if not url:
        return False
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    bar_state = {"last_len": 0}
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"{PROJECT_NAME}/{VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as out:
            total = resp.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None
            downloaded = 0
            start_time = time.time()
            last_print = 0.0
            read = resp.read
            write = out.write

            while True:
                buf = read(DOWNLOAD_CHUNK)
                if not buf:
                    break
                write(buf)
                downloaded += len(buf)
                now = time.time()
                if now - last_print >= 0.12:
                    last_print = now
                    write_live_line(
                        format_pip_progress_bar(
                            downloaded=downloaded,
                            total_bytes=total_bytes,
                            elapsed_sec=now - start_time,
                            label=label,
                            done=False,
                        ),
                        bar_state,
                        newline=False,
                    )

            write_live_line(
                format_pip_progress_bar(
                    downloaded=downloaded,
                    total_bytes=total_bytes or downloaded,
                    elapsed_sec=time.time() - start_time,
                    label=label,
                    done=True,
                ),
                bar_state,
                newline=True,
            )

        if dest_path.stat().st_size == 0:
            cprint(f"  {err_tag()} Downloaded file for {label} is empty.")
            dest_path.unlink(missing_ok=True)
            return False
        return True
    except Exception as e:
        finish_live_line_if_needed(bar_state)
        cprint(f"  {err_tag()} Failed to download {label} ({url}): {e}")
        dest_path.unlink(missing_ok=True)
        return False


def find_latest_ffmpeg_win64_zip_url() -> str:
    try:
        releases = http_get_json(FFMPEG_GITHUB_RELEASES_API)
        if not isinstance(releases, list):
            return ""
        for rel in releases:
            for asset in rel.get("assets", []):
                name = (asset.get("name") or "").lower()
                url = asset.get("browser_download_url") or ""
                if (
                    name.endswith(".zip")
                    and "win64" in name
                    and "gpl" in name
                    and "shared" not in name
                    and "debug" not in name
                    and url
                ):
                    return url
    except Exception as e:
        cprint(f"  {info_tag()} GitHub API for FFmpeg unavailable ({e}).")
    return ""


def find_latest_whisper_zip_url(prefer_cuda: bool) -> tuple[str, str]:
    try:
        releases = http_get_json(WHISPER_GITHUB_RELEASES_API)
        if isinstance(releases, list):
            if prefer_cuda:
                for rel in releases:
                    for asset in rel.get("assets", []):
                        name = (asset.get("name") or "").lower()
                        url = asset.get("browser_download_url") or ""
                        if (
                            name.endswith(".zip")
                            and ("x64" in name or "win64" in name)
                            and ("cublas" in name or "cuda" in name)
                            and "arm64" not in name
                            and url
                        ):
                            return url, "cuda"

            for rel in releases:
                for asset in rel.get("assets", []):
                    name = (asset.get("name") or "").lower()
                    url = asset.get("browser_download_url") or ""
                    if (
                        name.endswith(".zip")
                        and ("whisper-bin-x64" in name or ("win64" in name and "whisper" in name))
                        and "cublas" not in name
                        and "cuda" not in name
                        and "vulkan" not in name
                        and "arm64" not in name
                        and url
                    ):
                        return url, "cpu"
    except Exception as e:
        cprint(f"  {info_tag()} GitHub API for whisper.cpp unavailable ({e}).")

    if prefer_cuda and FALLBACK_URLS.get("whisper_cuda_zip"):
        return FALLBACK_URLS["whisper_cuda_zip"], "cuda"
    if FALLBACK_URLS.get("whisper_cpu_zip"):
        return FALLBACK_URLS["whisper_cpu_zip"], "cpu"
    return "", "cpu"


def extract_zip_and_copy_exe(
    archive_path: Path, candidate_names: list[str], target_exe_name: str, cache_dir: Path
) -> bool:
    try:
        if not zipfile.is_zipfile(archive_path):
            cprint(f"  {err_tag()} {archive_path.name} is not a valid ZIP archive.")
            return False

        with zipfile.ZipFile(archive_path, "r") as zf:
            members = [i for i in zf.infolist() if not i.is_dir()]
            by_base: dict[str, zipfile.ZipInfo] = {}
            for info in members:
                by_base.setdefault(posixpath.basename(info.filename).lower(), info)

            found = next(
                (by_base[c.lower()] for c in candidate_names if c.lower() in by_base), None
            )
            if found is None:
                cprint(
                    f"  {err_tag()} None of the expected executables were found in archive: {', '.join(candidate_names)}"
                )
                return False

            parent = posixpath.dirname(found.filename)
            for info in members:
                if posixpath.dirname(info.filename) != parent:
                    continue
                with zf.open(info) as src, open(
                    cache_dir / posixpath.basename(info.filename), "wb"
                ) as dst:
                    shutil.copyfileobj(src, dst, DOWNLOAD_CHUNK)

            dest_exe = cache_dir / target_exe_name
            if posixpath.basename(found.filename).lower() != target_exe_name.lower():
                with zf.open(found) as src, open(dest_exe, "wb") as dst:
                    shutil.copyfileobj(src, dst, DOWNLOAD_CHUNK)

        return dest_exe.is_file()
    except Exception as e:
        cprint(f"  {err_tag()} Failed while extracting ZIP archive: {e}")
        return False
    finally:
        archive_path.unlink(missing_ok=True)


def try_extract_7z_if_possible(archive_path: Path, target_exe_name: str, cache_dir: Path) -> bool:
    seven_zip = shutil.which("7z") or shutil.which("7za")
    if not seven_zip:
        return False

    extract_tmp = cache_dir / f"_tmp_7z_{target_exe_name}"
    if extract_tmp.exists():
        shutil.rmtree(extract_tmp, ignore_errors=True)
    extract_tmp.mkdir(parents=True, exist_ok=True)

    try:
        res = subprocess.run(
            [seven_zip, "x", str(archive_path), f"-o{extract_tmp}", "-y"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if res.returncode != 0:
            return False
        target_lower = target_exe_name.lower()
        for root, _, files in os.walk(extract_tmp):
            for f in files:
                if f.lower() == target_lower:
                    found = Path(root) / f
                    for item in found.parent.iterdir():
                        if item.is_file():
                            shutil.copy2(item, cache_dir / item.name)
                    return (cache_dir / target_exe_name).is_file()
        return False
    finally:
        shutil.rmtree(extract_tmp, ignore_errors=True)
        archive_path.unlink(missing_ok=True)


def ensure_ffmpeg(cache_dir: Path, work_dir: Path) -> bool:
    """1. Check .cache -> 2. Check system PATH -> 3. Download into .cache."""
    if (cache_dir / "ffmpeg.exe").is_file():
        return True

    path_ffmpeg = find_in_system_path("ffmpeg")
    if path_ffmpeg is not None:
        return True

    cprint_step(f"{warn_tag('MISSING')} ffmpeg.exe (not in .cache or PATH) -> downloading into .cache...")
    url = find_latest_ffmpeg_win64_zip_url() or FALLBACK_URLS["ffmpeg_zip"]
    if not url:
        cprint_dim("  -> Could not resolve download URL for ffmpeg.exe.")
        return False

    tmp_zip = cache_dir / "_dl_ffmpeg.zip"
    if not download_file(url, tmp_zip, "ffmpeg"):
        return False

    ok = extract_zip_and_copy_exe(tmp_zip, ["ffmpeg.exe"], "ffmpeg.exe", cache_dir)
    if ok:
        cprint_step(f"  -> {ok_tag()} ffmpeg.exe is ready in .cache: {cache_dir / 'ffmpeg.exe'}")
    return ok


def get_cached_whisper_mode(cache_dir: Path) -> str:
    try:
        return (cache_dir / WHISPER_MODE_MARKER).read_text(encoding="utf-8").strip().lower()
    except Exception:
        return ""


def set_cached_whisper_mode(cache_dir: Path, mode: str) -> None:
    try:
        (cache_dir / WHISPER_MODE_MARKER).write_text(mode, encoding="utf-8")
    except Exception:
        pass


def ensure_whisper(cache_dir: Path, work_dir: Path, prefer_cuda: bool) -> bool:
    """Whisper stays managed in .cache/work_dir (never pulled from system PATH)."""
    exe = cache_dir / "whisper.exe"
    current_mode = get_cached_whisper_mode(cache_dir)

    if exe.is_file():
        if prefer_cuda and current_mode in ("cuda", "cpu_checked"):
            return True
        if not prefer_cuda and current_mode in ("cpu", "", "cpu_checked", "cuda"):
            return True
        if prefer_cuda:
            cprint_step(
                f"{info_tag()} NVIDIA GPU detected, upgrading whisper.exe in .cache to CUDA build..."
            )
    elif (work_dir / "whisper.exe").is_file() and not prefer_cuda:
        return True

    target_desc = "NVIDIA CUDA build" if prefer_cuda else "latest whisper.cpp release"
    cprint_step(f"{info_tag('FETCH')} whisper.exe -> searching {target_desc}...")
    url, resolved_mode = find_latest_whisper_zip_url(prefer_cuda=prefer_cuda)
    if not url:
        if exe.is_file():
            cprint(f"  -> {warn_tag()} No CUDA build found in releases; keeping existing whisper.exe.")
            set_cached_whisper_mode(cache_dir, "cpu_checked")
            return True
        cprint_dim("  -> Could not resolve download URL for whisper.exe.")
        return False

    tmp_zip = cache_dir / "_dl_whisper.zip"
    if not download_file(url, tmp_zip, f"whisper.cpp ({resolved_mode})"):
        return exe.is_file()

    ok = extract_zip_and_copy_exe(
        tmp_zip,
        ["whisper-cli.exe", "whisper.exe", "main.exe"],
        "whisper.exe",
        cache_dir,
    )
    if ok:
        saved_mode = "cpu_checked" if (prefer_cuda and resolved_mode == "cpu") else resolved_mode
        set_cached_whisper_mode(cache_dir, saved_mode)
        cprint_step(f"  -> {ok_tag()} whisper.exe ({resolved_mode}) is ready in .cache: {exe}")
    return ok


def ensure_mplayer(cache_dir: Path, work_dir: Path) -> bool:
    """1. Check .cache -> 2. Check system PATH -> 3. Download into .cache."""
    if (cache_dir / "mplayer.exe").is_file():
        return True

    path_mplayer = find_in_system_path("mplayer")
    if path_mplayer is not None:
        return True

    cprint_step(f"{warn_tag('MISSING')} mplayer.exe (not in .cache or PATH) -> downloading into .cache...")
    url = FALLBACK_URLS.get("mplayer_archive", "").strip()
    if not url:
        cprint_dim("  -> No download URL configured for mplayer.exe.")
        return False

    tmp_arc = cache_dir / "_dl_mplayer.7z"
    if not download_file(url, tmp_arc, "mplayer"):
        return False

    if zipfile.is_zipfile(tmp_arc):
        ok = extract_zip_and_copy_exe(tmp_arc, ["mplayer.exe"], "mplayer.exe", cache_dir)
    else:
        ok = try_extract_7z_if_possible(tmp_arc, "mplayer.exe", cache_dir)
        if not ok:
            tmp_arc.unlink(missing_ok=True)
            cprint(f"  -> {info_tag()} mplayer archive is .7z and 7z/7za was not found in PATH.")
            cprint_dim(f"     Extract mplayer.exe manually into {cache_dir} or set a direct .exe/.zip URL.")
            return False

    if ok:
        cprint_step(f"  -> {ok_tag()} mplayer.exe is ready in .cache: {cache_dir / 'mplayer.exe'}")
    return ok


def resolve_model_url(model_arg: str) -> str:
    raw_name = Path(model_arg).name
    name = raw_name.lower()
    known = _WHISPER_MODEL_URLS_LOWER.get(name)
    if known:
        return known
    if name.startswith("ggml-") and name.endswith(".bin"):
        return f"{_HF}{raw_name}"
    return ""


def ensure_model(cache_dir: Path, work_dir: Path, model_arg: str) -> bool:
    model_path = Path(model_arg)
    if model_path.is_absolute():
        candidate_paths = [model_path]
        target_download_path = model_path
    else:
        candidate_paths = [cache_dir / model_path, work_dir / model_path]
        target_download_path = cache_dir / model_path

    for p in candidate_paths:
        if p.is_file() and _file_nonempty(p):
            return True

    url = resolve_model_url(model_arg)
    if url:
        cprint_step(
            f"{info_tag('FETCH')} Downloading model {Path(model_arg).name} into {target_download_path.parent}..."
        )
        part_path = target_download_path.with_name(target_download_path.name + ".part")
        if download_file(url, part_path, Path(model_arg).name):
            try:
                os.replace(part_path, target_download_path)
                cprint_step(f"  -> {ok_tag()} Model is ready: {target_download_path}")
                return True
            except OSError as e:
                cprint(f"  {err_tag()} Could not finalize model file: {e}")
        part_path.unlink(missing_ok=True)

    cprint(f"{warn_tag('WARNING')} Model '{model_arg}' could not be downloaded automatically.")
    return False


def ensure_all_dependencies(cache_dir: Path, work_dir: Path, model_arg: str, hw: dict) -> dict[str, bool]:
    return {
        "ffmpeg.exe": ensure_ffmpeg(cache_dir, work_dir),
        "whisper.exe": ensure_whisper(cache_dir, work_dir, prefer_cuda=hw["use_gpu"]),
        "mplayer.exe": ensure_mplayer(cache_dir, work_dir),
        "model": ensure_model(cache_dir, work_dir, model_arg),
    }


def print_missing_summary(status: dict[str, bool], cache_dir: Path, model_arg: str) -> None:
    cprint("\nDependency status:")
    for key, ok in status.items():
        label = model_arg if key == "model" else key
        state_str = ok_tag() if ok else err_tag("MISSING")
        cprint(f"  {state_str} {label}")
    cprint_dim(f"Cache directory: {cache_dir}")


def print_usage_help(status: dict[str, bool], cache_dir: Path, model_arg: str, hw: dict) -> None:
    script_name = Path(sys.argv[0]).name
    gpu = hw["gpu"]
    gpu_desc = f"{gpu['name']} ({gpu['vram_free_mb']} MB free)" if gpu["has_nvidia"] else "none detected"
    mode_desc = "NVIDIA GPU" if hw["use_gpu"] else "CPU"
    cprint(f"\n{PROJECT_NAME} {VERSION} Usage:")
    cprint(f"  {script_name} <media_file> [options]")
    cprint_dim(
        f"Hardware: CPU threads={hw['cpu_threads']} | NVIDIA GPU={gpu_desc} | Compute={mode_desc} | Threads={hw['recommended_threads']}"
    )
    cprint("\nExamples:")
    cprint(f"  {script_name} movie.mkv")
    cprint(f"  {script_name} movie.mkv --lang sk")
    cprint(f"  {script_name} movie.mkv --lang sk --force-srt")
    cprint("\nOptions:")
    cprint("  media_file      Path to video or audio file to play")
    cprint(f"  --model         Path or filename of Whisper model (default: {DEFAULT_MODEL} in {CACHE_DIR_NAME}/)")
    cprint("  --lang          Target subtitle language (en -> <name>_en.srt; sk -> translates to <name>_sk.srt)")
    cprint(f"  --no-prompt     Skip interactive prompts (default timeout: {PROMPT_TIMEOUT_SEC}s)")
    cprint(f"  --threads       Threads per whisper.exe job (default: auto -> {hw['recommended_threads']})")
    cprint(f"  --sub-scale     MPlayer subtitle text scale (default: {DEFAULT_SUB_SCALE})")
    cprint("  --force-srt     Regenerate base SRT and target language SRT")
    print_missing_summary(status, cache_dir, model_arg)


# ==============================================================================
# FULL AUDIO EXTRACTION + SRT GENERATION & NON-SPEECH EFFECT FILTERING
# ==============================================================================
def _run_ffmpeg_audio_extract(
    ffmpeg_path: Path,
    media_file: Path,
    temp_wav: Path,
    duration_sec: float | None,
    use_speech_filter: bool,
    audio_track_idx: int = 0,
) -> tuple[bool, float]:
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-nostdin",
        "-vn",
        "-sn",
        "-dn",
        "-i",
        str(media_file),
        "-map",
        f"0:a:{max(0, audio_track_idx)}",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if use_speech_filter:
        cmd.extend(["-af", "highpass=f=80,lowpass=f=7800,dynaudnorm=f=150:g=15"])
    cmd.extend([
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(temp_wav),
        "-progress",
        "pipe:1",
        "-nostats",
        "-loglevel",
        "error",
    ])

    start_wall = time.time()
    bar_state = {"last_len": 0}
    cur_sec = 0.0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_print = 0.0
    try:
        if proc.stdout:
            for raw_line in proc.stdout:
                if not raw_line.startswith("out_time_ms="):
                    continue
                try:
                    cur_sec = max(0.0, int(raw_line.split("=", 1)[1].strip()) / 1_000_000.0)
                except ValueError:
                    continue
                now = time.time()
                if now - last_print >= 0.15:
                    last_print = now
                    write_live_line(
                        format_time_progress_bar(
                            cur_sec=cur_sec,
                            total_sec=duration_sec,
                            elapsed_sec=now - start_wall,
                            label="Audio extraction",
                            done=False,
                        ),
                        bar_state,
                        newline=False,
                    )
        rc = proc.wait()
        if rc != 0 or not temp_wav.is_file() or temp_wav.stat().st_size <= 44:
            finish_live_line_if_needed(bar_state)
            temp_wav.unlink(missing_ok=True)
            return False, time.time() - start_wall

        elapsed = time.time() - start_wall
        final_sec = duration_sec if (duration_sec and duration_sec > 0) else cur_sec
        write_live_line(
            format_time_progress_bar(
                cur_sec=final_sec,
                total_sec=duration_sec,
                elapsed_sec=elapsed,
                label="Audio extraction",
                done=True,
            ),
            bar_state,
            newline=True,
        )
        return True, elapsed
    except Exception:
        finish_live_line_if_needed(bar_state)
        if proc.poll() is None:
            proc.terminate()
        temp_wav.unlink(missing_ok=True)
        raise


def extract_full_audio(
    ffmpeg_path: Path,
    media_file: Path,
    wav_path: Path,
    duration_sec: float | None,
    audio_track_idx: int = 0,
) -> bool:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = wav_path.with_suffix(".part.wav")
    temp_wav.unlink(missing_ok=True)

    cprint_sep()
    cprint_step(f"Opening audio extractor: [ffmpeg] stream -aid {audio_track_idx} -> {wav_path}")
    ok, elapsed = _run_ffmpeg_audio_extract(
        ffmpeg_path,
        media_file,
        temp_wav,
        duration_sec,
        use_speech_filter=True,
        audio_track_idx=audio_track_idx,
    )
    if not ok:
        cprint_dim("  Speech filter failed -> retrying raw PCM 16kHz mono extraction...")
        ok, elapsed = _run_ffmpeg_audio_extract(
            ffmpeg_path,
            media_file,
            temp_wav,
            duration_sec,
            use_speech_filter=False,
            audio_track_idx=audio_track_idx,
        )
    if not ok:
        cprint(f"  {err_tag()} FFmpeg failed to extract audio from {media_file.name}.")
        return False

    os.replace(temp_wav, wav_path)
    size_mb = wav_path.stat().st_size / (1024 * 1024)
    cprint(f"  {ok_tag()} PCM WAV extracted in {elapsed:.1f}s (16000 Hz, 1ch, s16le, {size_mb:.1f} MB)")
    return True


def format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_whisper_ts_to_sec(ts: str) -> float:
    h_str, m_str, rest = ts.split(":")
    s_str, ms_str = rest.split(".")
    return int(h_str) * 3600 + int(m_str) * 60 + int(s_str) + int(ms_str) / 1000.0


def _is_music_tag_content(inner_text: str) -> bool:
    norm = NON_ALPHA_RE.sub(" ", inner_text).strip().lower()
    if not norm:
        return False
    return any(kw in norm for kw in MUSIC_KEYWORDS)


def _clean_subtitle_text(raw_text: str) -> tuple[str | None, bool]:
    """
    Normalize a subtitle block text:
      - Music / singing / blank audio markers -> '♪ ♪' (returns ('♪ ♪', True))
      - Non-speech sound effects in [...] or (...) -> stripped completely
      - If no spoken text remains -> returns (None, False) so the block is dropped
    """
    txt = " ".join(raw_text.split()).strip()
    if not txt:
        return None, False

    if MUSIC_NOTES_ONLY_RE.match(txt):
        return MUSIC_GLYPH, True

    bracket_tags = BRACKET_TAG_RE.findall(txt)
    has_music_tag = any(_is_music_tag_content(tag[1:-1]) for tag in bracket_tags)

    # Remove all [...] and (...) non-speech annotations
    spoken = BRACKET_TAG_RE.sub(" ", txt)
    # Remove stray musical symbols if mixed with tags
    spoken = spoken.replace("♪", " ").replace("♫", " ")
    spoken = " ".join(spoken.split()).strip()
    # Clean dangling leading/trailing punctuation left after stripping a tag (e.g. "- [snaps] Hey" -> "- Hey")
    spoken = re.sub(r"^[-–—,:;.\s]+$", "", spoken).strip()

    if spoken:
        return spoken, False

    if has_music_tag:
        return MUSIC_GLYPH, True

    return None, False


def _clean_srt_blocks_and_rewrite(srt_path: Path) -> int:
    if not srt_path.is_file() or srt_path.stat().st_size <= 0:
        return 0

    raw = srt_path.read_text(encoding="utf-8", errors="replace")
    cleaned_entries: list[str] = []
    consecutive_music = 0
    idx = 1

    for blk in BLOCK_SPLIT_RE.split(raw.strip()):
        lines = [ln.rstrip("\r") for ln in blk.splitlines() if ln.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        cleaned_txt, is_music = _clean_subtitle_text(" ".join(lines[2:]))
        if not cleaned_txt:
            continue

        if is_music:
            consecutive_music += 1
            if consecutive_music > MAX_CONSECUTIVE_MUSIC_BLOCKS:
                continue
        else:
            consecutive_music = 0

        cleaned_entries.append(f"{idx}\n{lines[1].strip()}\n{cleaned_txt}\n")
        idx += 1

    if not cleaned_entries:
        return 0

    with open(srt_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(cleaned_entries))

    return idx - 1


def build_srt_from_stdout_lines(lines: list[str], srt_path: Path) -> int:
    segments: list[tuple[float, float, str]] = []
    consecutive_music = 0
    for raw_line in lines:
        m = TIMESTAMP_LINE_RE.search(raw_line)
        if not m:
            continue
        s_sec = parse_whisper_ts_to_sec(m.group(1))
        e_sec = parse_whisper_ts_to_sec(m.group(2))
        if e_sec <= s_sec:
            continue
        cleaned_txt, is_music = _clean_subtitle_text(m.group(3))
        if not cleaned_txt:
            continue
        if is_music:
            consecutive_music += 1
            if consecutive_music > MAX_CONSECUTIVE_MUSIC_BLOCKS:
                continue
        else:
            consecutive_music = 0
        segments.append((s_sec, e_sec, cleaned_txt))

    if not segments:
        return 0

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    prev_end = 0.0
    for idx, (s_sec, e_sec, txt) in enumerate(segments, start=1):
        start_c = max(s_sec, prev_end)
        end_c = max(start_c + 0.8, e_sec)
        prev_end = end_c
        entries.append(
            f"{idx}\n{format_srt_timestamp(start_c)} --> {format_srt_timestamp(end_c)}\n{txt}\n"
        )

    with open(srt_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(entries))

    return len(entries)


def _build_whisper_cmds(
    whisper_path: Path,
    model_path: Path,
    wav_path: Path,
    osrt_prefix: str,
    threads: int,
    transcribe_lang: str | None = None,
) -> list[list[str]]:
    base_cmd = [
        str(whisper_path),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-t",
        str(max(1, threads)),
    ]
    if transcribe_lang:
        base_cmd.extend(["-l", transcribe_lang])
    else:
        base_cmd.append("-tr")
    base_cmd.extend(["-osrt", "-of", osrt_prefix])

    anti_loop_cmd = base_cmd + ["-mc", "0", "-et", "2.4", "-nth", "0.60"]
    return [anti_loop_cmd, base_cmd]


def transcribe_full_audio_to_srt(
    whisper_path: Path,
    model_path: Path,
    wav_path: Path,
    out_srt_path: Path,
    threads: int,
    hw: dict,
    transcribe_lang: str | None = None,
) -> bool:
    gpu = hw["gpu"]
    gpu_label = f"{gpu['name']} ({gpu['vram_free_mb']} MB free)" if gpu["has_nvidia"] else "none"
    compute_label = "NVIDIA CUDA" if hw["use_gpu"] else "CPU"
    target_label = (transcribe_lang or "en").upper()
    mode_desc = f"transcribe -> {target_label} (-l {transcribe_lang})" if transcribe_lang else "translate -> EN (-tr)"

    cprint_sep()
    cprint_step(f"Opening speech-to-text decoder: [whisper.cpp] ({compute_label}, {max(1, threads)} threads)")
    cprint(f"Selected Whisper model: [{model_path.name}] | Mode: {mode_desc} | GPU: {gpu_label}")
    cprint(f"SUB: Target output: {out_srt_path}")

    wav_duration_sec = get_wav_duration_sec(wav_path)

    temp_srt = out_srt_path.with_suffix(".part.srt")
    temp_srt.unlink(missing_ok=True)
    osrt_prefix = str(temp_srt)[:-4] if str(temp_srt).lower().endswith(".srt") else str(temp_srt)

    cmds = _build_whisper_cmds(
        whisper_path,
        model_path,
        wav_path,
        osrt_prefix,
        threads,
        transcribe_lang=transcribe_lang,
    )
    start_wall = time.time()

    for attempt_idx, cmd in enumerate(cmds):
        temp_srt.unlink(missing_ok=True)
        captured_lines: list[str] = []
        err_lines: list[str] = []
        bar_state = {"last_len": 0}
        state_lock = threading.Lock()
        latest_media_sec = 0.0
        stop_ticker = threading.Event()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def read_stderr():
            if proc.stderr:
                for ln in proc.stderr:
                    s = ln.strip()
                    if s:
                        err_lines.append(s)
                        if len(err_lines) > 50:
                            del err_lines[:25]

        def render_transcribe_line(cur: float, done: bool = False) -> str:
            elapsed = time.time() - start_wall
            effective_cur = wav_duration_sec if (done and wav_duration_sec) else cur
            effective_total = wav_duration_sec if (wav_duration_sec and (cur > 0 or done)) else None
            return format_time_progress_bar(
                cur_sec=effective_cur,
                total_sec=effective_total,
                elapsed_sec=elapsed,
                label=f"Transcribing {target_label}",
                done=done,
            )

        def ticker_loop():
            while not stop_ticker.wait(0.2):
                with state_lock:
                    if latest_media_sec > 0:
                        continue
                    write_live_line(render_transcribe_line(0.0), bar_state, newline=False)

        t_err = threading.Thread(target=read_stderr, daemon=True)
        t_tick = threading.Thread(target=ticker_loop, daemon=True)
        t_err.start()
        t_tick.start()

        try:
            if proc.stdout:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    captured_lines.append(line)
                    m = TIMESTAMP_LINE_RE.search(line)
                    if m:
                        try:
                            end_sec = parse_whisper_ts_to_sec(m.group(2))
                        except Exception:
                            continue
                        with state_lock:
                            if end_sec > latest_media_sec:
                                latest_media_sec = end_sec
                            write_live_line(
                                render_transcribe_line(latest_media_sec), bar_state, newline=False
                            )

            rc = proc.wait()
            stop_ticker.set()
            t_tick.join(timeout=1)
            t_err.join(timeout=2)

            if rc != 0:
                finish_live_line_if_needed(bar_state)
                temp_srt.unlink(missing_ok=True)
                if attempt_idx + 1 < len(cmds):
                    cprint_step(
                        f"  {info_tag()} Retrying whisper.exe with standard CLI flags..."
                    )
                    continue
                tail = " | ".join(err_lines[-3:]) if err_lines else "unknown error"
                cprint(f"  {err_tag()} whisper.exe exited with code {rc}: {tail}")
                return False

            out_srt_path.parent.mkdir(parents=True, exist_ok=True)
            srt_created = False
            entries_count = 0

            if _file_nonempty(temp_srt):
                os.replace(temp_srt, out_srt_path)
                entries_count = _clean_srt_blocks_and_rewrite(out_srt_path)
                srt_created = entries_count > 0
            else:
                count = build_srt_from_stdout_lines(captured_lines, out_srt_path)
                if count > 0 and _file_nonempty(out_srt_path):
                    entries_count = count
                    srt_created = True

            if srt_created:
                write_live_line(render_transcribe_line(0.0, done=True), bar_state, newline=True)
                elapsed = time.time() - start_wall
                suffix = f" ({entries_count} subtitle blocks)" if entries_count > 0 else ""
                cprint_step(f"  {ok_tag()} {target_label} SRT generated in {elapsed:.1f}s{suffix}")
                cleanup_wav_file(wav_path, f"{target_label} SRT created")
                return True

            finish_live_line_if_needed(bar_state)
            cprint(f"  {err_tag()} No subtitles were produced by whisper.exe.")
            return False
        except Exception:
            stop_ticker.set()
            t_tick.join(timeout=1)
            finish_live_line_if_needed(bar_state)
            if proc.poll() is None:
                proc.terminate()
            temp_srt.unlink(missing_ok=True)
            raise

    return False


def ensure_transcribed_srt(
    ffmpeg_path: Path,
    whisper_path: Path,
    model_path: Path,
    media_file: Path,
    wav_path: Path,
    out_srt_path: Path,
    threads: int,
    hw: dict,
    duration_sec: float | None = None,
    transcribe_lang: str | None = None,
    audio_track_idx: int = 0,
    force: bool = False,
) -> bool:
    label = (transcribe_lang or "en").upper()
    if not force and _file_nonempty(out_srt_path):
        cprint(f"{ok_tag()} Existing {label} SRT found: {out_srt_path}")
        cleanup_wav_file(wav_path, f"{label} SRT already exists")
        return True

    if force or not wav_path.is_file():
        if not extract_full_audio(
            ffmpeg_path, media_file, wav_path, duration_sec, audio_track_idx=audio_track_idx
        ):
            out_srt_path.unlink(missing_ok=True)
            return False
    else:
        cprint(f"{ok_tag()} Using cached audio: {wav_path}")

    ok_srt = transcribe_full_audio_to_srt(
        whisper_path=whisper_path,
        model_path=model_path,
        wav_path=wav_path,
        out_srt_path=out_srt_path,
        threads=threads,
        hw=hw,
        transcribe_lang=transcribe_lang,
    )
    if not ok_srt:
        out_srt_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
        return False
    return True


# ==============================================================================
# AUTOMATIC MPLAYER ENVIRONMENT & RUNTIME DETECTION
# ==============================================================================
def find_system_font() -> Path | None:
    if os.name == "nt":
        win_dir = Path(os.environ.get("WINDIR", "C:\\Windows"))
        fonts_dir = win_dir / "Fonts"
        candidates = [
            fonts_dir / "arial.ttf",
            fonts_dir / "segoeui.ttf",
            fonts_dir / "calibri.ttf",
            fonts_dir / "tahoma.ttf",
            fonts_dir / "consola.ttf",
            fonts_dir / "lucon.ttf",
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        ]

    for p in candidates:
        if p.is_file() and _file_nonempty(p):
            return p
    return None


def ensure_mplayer_config(cache_dir: Path) -> Path:
    mp_cfg_dir = cache_dir / "mplayer"
    (mp_cfg_dir / "sub").mkdir(parents=True, exist_ok=True)
    cfg_file = mp_cfg_dir / "config"
    if not cfg_file.is_file():
        cfg_file.write_text(
            "# Auto-generated isolated MPlayer config for subplayer\n"
            "subcp=utf-8\n"
            "ffactor=0.75\n",
            encoding="utf-8",
        )
    return cfg_file


def _build_mplayer_vo_ao_candidates() -> list[tuple[str | None, str | None]]:
    if os.name == "nt":
        return [
            (None, None),
            ("direct3d", "dsound"),
            ("gl", "dsound"),
            ("directx", "win32"),
            ("gl", "win32"),
            (None, "null"),
            ("null", "null"),
        ]
    return [
        (None, None),
        ("gl", "pulse"),
        ("gl", "alsa"),
        ("x11", "alsa"),
        ("null", "null"),
    ]


def _describe_mplayer_exit(rc: int) -> str:
    if rc == 0:
        return "exited cleanly (0)"
    if rc in (-1073741515, 3221225781):
        return f"missing required DLL dependency (STATUS_DLL_NOT_FOUND / 0xC0000135, code {rc})"
    if rc in (-1073741819, 3221225477):
        return f"access violation / crash (STATUS_ACCESS_VIOLATION / 0xC0000005, code {rc})"
    return f"exited with code {rc}"


def play_media_with_srt(
    mplayer_path: Path,
    media_file: Path,
    srt_path: Path,
    sub_scale: float,
    cache_dir: Path | None = None,
    audio_track_idx: int | None = None,
) -> int:
    cprint_sep()
    cprint_step(f"Launching MPlayer ({mplayer_path})")
    cprint(f"SUB: Active subtitle file: {srt_path}")

    base_cache = cache_dir or get_cache_dir(get_work_dir())
    cfg_file = ensure_mplayer_config(base_cache)
    font_path = find_system_font()

    if font_path:
        cprint(f"FONT: Selected TrueType subtitle font: {font_path}")
    else:
        cprint("FONT: Using MPlayer built-in OSD/subtitle font")

    common_args = [
        "-noconfig",
        "all",
        "-include",
        str(cfg_file),
        "-sub",
        str(srt_path),
        "-utf8",
        "-subfont-autoscale",
        "3",
        "-subfont-text-scale",
        f"{sub_scale:.2f}",
    ]
    if audio_track_idx is not None:
        common_args.extend(["-aid", str(audio_track_idx)])
    if font_path:
        common_args.extend(["-font", str(font_path)])

    cprint_sep()
    candidates = _build_mplayer_vo_ao_candidates()
    last_rc = 1

    for idx, (vo, ao) in enumerate(candidates):
        cmd = [str(mplayer_path)] + list(common_args)
        if vo:
            cmd.extend(["-vo", vo])
        if ao:
            cmd.extend(["-ao", ao])
        cmd.append(str(media_file))

        if idx > 0:
            cprint_step(
                f"{warn_tag()} Retrying MPlayer with fallback vo={vo or 'auto'}, ao={ao or 'auto'}..."
            )

        rc = subprocess.run(cmd).returncode
        last_rc = rc

        if rc == 0:
            return 0

        if rc in (-1073741515, 3221225781, -1073741819, 3221225477):
            cprint(f"{err_tag()} MPlayer {_describe_mplayer_exit(rc)}.")
            return rc

    if last_rc != 0:
        cprint(f"{err_tag()} MPlayer {_describe_mplayer_exit(last_rc)}.")
    return last_rc


def parse_args(argv: list[str], hw: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("media_file", nargs="?", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--threads", type=int, default=hw["recommended_threads"])
    parser.add_argument("--sub-scale", type=float, default=DEFAULT_SUB_SCALE)
    parser.add_argument("--force-srt", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return parser.parse_args(argv)


def _find_matching_srt_for_lang(
    existing_srts: list[Path], subs_dir: Path, media_stem: str, lang_code: str
) -> Path | None:
    norm = normalize_lang_code(lang_code)
    for p in existing_srts:
        if extract_lang_code_from_srt(p, media_stem) == norm:
            return p
    cache_candidate = build_srt_path(subs_dir, media_stem, norm)
    if _file_nonempty(cache_candidate):
        return cache_candidate
    return None


def main() -> int:
    enable_windows_ansi()
    work_dir = get_work_dir()
    cache_dir = get_cache_dir(work_dir)
    subs_dir = get_subs_dir(cache_dir)
    audio_dir = get_audio_dir(cache_dir)
    argos_models_dir = get_argos_models_dir(cache_dir)
    argos_pkg_dir = get_argos_pkg_dir(cache_dir)
    set_argos_env_before_import(argos_models_dir)

    hw = detect_hardware()
    args = parse_args(sys.argv[1:], hw)

    status = ensure_all_dependencies(cache_dir, work_dir, args.model, hw)

    if args.help or not args.media_file:
        print_usage_help(status, cache_dir, args.model, hw)
        return 0 if args.help else 1

    if not all(status.values()):
        cprint(f"\n{err_tag('STOP')} Cannot start playback: missing required dependencies.")
        print_missing_summary(status, cache_dir, args.model)
        return 1

    media_file = Path(args.media_file)
    if not media_file.is_absolute():
        media_file = work_dir / media_file

    if not media_file.is_file():
        cprint(f"\n{err_tag()} Media file does not exist: {media_file}")
        print_usage_help(status, cache_dir, args.model, hw)
        return 1

    media_dir = media_file.parent

    model_arg_path = Path(args.model)
    if model_arg_path.is_absolute():
        model_path = model_arg_path
    elif (cache_dir / model_arg_path).is_file():
        model_path = cache_dir / model_arg_path
    else:
        model_path = work_dir / model_arg_path

    ffmpeg_path = resolve_tool_path(cache_dir, work_dir, "ffmpeg.exe")
    whisper_path = resolve_tool_path(cache_dir, work_dir, "whisper.exe")
    mplayer_path = resolve_tool_path(cache_dir, work_dir, "mplayer.exe")

    media_info = probe_media_info(ffmpeg_path, media_file)
    audio_tracks = media_info["audio_tracks"]
    default_track = get_default_audio_track(audio_tracks)
    default_track_idx = default_track["audio_idx"] if default_track else 0
    default_track_lang = default_track["lang_code"] if default_track else None

    existing_srts = find_existing_srts_for_media(
        subs_dir, media_file.stem, media_dir=media_dir
    )

    print_mplayer_style_media_report(
        media_file=media_file,
        media_info=media_info,
        default_track=default_track,
        existing_srts=existing_srts,
        subs_dir=subs_dir,
        ffmpeg_path=ffmpeg_path,
        whisper_path=whisper_path,
        mplayer_path=mplayer_path,
        model_path=model_path,
        hw=hw,
    )

    wav_path = audio_dir / f"{media_file.stem}.wav"
    cached_en_srt_path = build_srt_path(subs_dir, media_file.stem, "en")

    selected_srt_path: Path | None = None
    preselected_lang: str | None = None
    convert_source_srt: Path | None = None
    convert_source_lang: str = "en"
    transcribe_native_lang: str | None = None

    try:
        # Track-aware interactive flow when user didn't explicitly pass --lang / --no-prompt / --force-srt
        if (
            not args.force_srt
            and args.lang is None
            and not args.no_prompt
            and default_track is not None
        ):
            track_lang_code = default_track_lang or "en"
            matched_track_srt = _find_matching_srt_for_lang(
                existing_srts, subs_dir, media_file.stem, track_lang_code
            )

            if matched_track_srt is not None:
                wants_convert, direct_lang = prompt_use_or_convert_existing_srt(
                    matched_track_srt,
                    default_track,
                    media_file.stem,
                    subs_dir=subs_dir,
                    timeout_sec=PROMPT_TIMEOUT_SEC,
                )
                if not wants_convert:
                    selected_srt_path = matched_track_srt
                    cleanup_wav_file(wav_path, "SRT already exists")
                else:
                    convert_source_srt = matched_track_srt
                    convert_source_lang = (
                        extract_lang_code_from_srt(matched_track_srt, media_file.stem)
                        or track_lang_code
                    )
                    preselected_lang = direct_lang
            elif not existing_srts:
                expected_track_srt_name = f"{media_file.stem}_{track_lang_code}.srt"
                decision, chosen_lang = prompt_create_default_track_srt(
                    default_track,
                    expected_track_srt_name,
                    timeout_sec=PROMPT_TIMEOUT_SEC,
                )
                if decision == "track_lang" and chosen_lang:
                    preselected_lang = chosen_lang
                    if default_track_lang:
                        transcribe_native_lang = default_track_lang
                elif decision == "other_lang":
                    preselected_lang = chosen_lang

        # Existing generic selection / timeout fallback flow
        if selected_srt_path is None and convert_source_srt is None and preselected_lang is None:
            if not args.force_srt:
                if args.lang is not None:
                    target_lang = normalize_lang_code(args.lang)
                    matched = _find_matching_srt_for_lang(
                        existing_srts, subs_dir, media_file.stem, target_lang
                    )
                    if matched is not None:
                        selected_srt_path = matched
                        cprint_step(f"{ok_tag()} Existing SRT found: {selected_srt_path}")
                        cleanup_wav_file(wav_path, "SRT already exists")
                elif len(existing_srts) == 1:
                    only_srt = existing_srts[0]
                    if args.no_prompt:
                        selected_srt_path = only_srt
                        cprint_step(f"{ok_tag()} Existing SRT found (--no-prompt): {selected_srt_path}")
                    else:
                        wants_translate, direct_lang = prompt_use_or_convert_existing_srt(
                            only_srt,
                            default_track,
                            media_file.stem,
                            subs_dir=subs_dir,
                            timeout_sec=PROMPT_TIMEOUT_SEC,
                        )
                        if not wants_translate:
                            selected_srt_path = only_srt
                        else:
                            convert_source_srt = only_srt
                            convert_source_lang = (
                                extract_lang_code_from_srt(only_srt, media_file.stem) or "en"
                            )
                            preselected_lang = direct_lang
                    if selected_srt_path is not None:
                        cleanup_wav_file(wav_path, "SRT already exists")
                elif len(existing_srts) > 1:
                    if args.no_prompt:
                        selected_srt_path = next(
                            (p for p in existing_srts if p.stem.lower() == media_file.stem.lower()),
                            None,
                        ) or next(
                            (p for p in existing_srts if p.name.lower() == cached_en_srt_path.name.lower()),
                            existing_srts[0],
                        )
                        cprint_step(f"{ok_tag()} Selected SRT (--no-prompt): {selected_srt_path}")
                    else:
                        selected_srt_path = prompt_select_existing_srt(
                            existing_srts, media_file.stem, subs_dir=subs_dir, timeout_sec=PROMPT_TIMEOUT_SEC
                        )
                    if selected_srt_path is not None:
                        cleanup_wav_file(wav_path, "SRT already exists")

        if selected_srt_path is None:
            existing_en_srt = (
                _find_matching_srt_for_lang(existing_srts, subs_dir, media_file.stem, "en")
                if not args.force_srt
                else None
            )

            if preselected_lang is not None:
                target_lang = normalize_lang_code(preselected_lang)
            elif args.lang is not None:
                target_lang = normalize_lang_code(args.lang)
            elif args.no_prompt:
                target_lang = "en"
            else:
                default_choice = "sk" if existing_en_srt is not None else "en"
                target_lang = prompt_target_language(default_choice, PROMPT_TIMEOUT_SEC)

            cached_target_srt_path = build_srt_path(subs_dir, media_file.stem, target_lang)

            matched_target = (
                _find_matching_srt_for_lang(existing_srts, subs_dir, media_file.stem, target_lang)
                if not args.force_srt
                else None
            )
            if matched_target is not None:
                selected_srt_path = matched_target
                cprint_step(f"{ok_tag()} Existing SRT found: {selected_srt_path}")
                cleanup_wav_file(wav_path, "SRT already exists")
            elif transcribe_native_lang is not None and target_lang == transcribe_native_lang:
                ok_native = ensure_transcribed_srt(
                    ffmpeg_path=ffmpeg_path,
                    whisper_path=whisper_path,
                    model_path=model_path,
                    media_file=media_file,
                    wav_path=wav_path,
                    out_srt_path=cached_target_srt_path,
                    threads=max(1, args.threads),
                    hw=hw,
                    duration_sec=media_info["duration_sec"],
                    transcribe_lang=transcribe_native_lang,
                    audio_track_idx=default_track_idx,
                    force=args.force_srt,
                )
                if not ok_native:
                    cprint(f"\n{err_tag()} Failed to generate {target_lang.upper()} SRT file.")
                    return 1
                selected_srt_path = move_srt_to_media_dir(cached_target_srt_path, media_dir)
            else:
                source_srt_for_conversion: Path
                source_lang_for_conversion: str

                if convert_source_srt is not None and _file_nonempty(convert_source_srt):
                    source_srt_for_conversion = convert_source_srt
                    source_lang_for_conversion = convert_source_lang
                    cprint(f"{ok_tag()} Using existing SRT for conversion: {source_srt_for_conversion}")
                    cleanup_wav_file(wav_path, "existing SRT used for conversion")
                elif existing_en_srt is not None:
                    source_srt_for_conversion = existing_en_srt
                    source_lang_for_conversion = "en"
                    cprint(f"{ok_tag()} Using existing EN SRT: {source_srt_for_conversion}")
                    cleanup_wav_file(wav_path, "EN SRT already exists")
                elif not args.force_srt and existing_srts:
                    source_srt_for_conversion = existing_srts[0]
                    source_lang_for_conversion = (
                        extract_lang_code_from_srt(source_srt_for_conversion, media_file.stem)
                        or "en"
                    )
                    cprint(
                        f"{info_tag()} Using existing SRT as conversion source: "
                        f"{source_srt_for_conversion}"
                    )
                else:
                    ok_en = ensure_transcribed_srt(
                        ffmpeg_path=ffmpeg_path,
                        whisper_path=whisper_path,
                        model_path=model_path,
                        media_file=media_file,
                        wav_path=wav_path,
                        out_srt_path=cached_en_srt_path,
                        threads=max(1, args.threads),
                        hw=hw,
                        duration_sec=media_info["duration_sec"],
                        transcribe_lang=None,
                        audio_track_idx=default_track_idx,
                        force=args.force_srt,
                    )
                    if not ok_en:
                        cprint(f"\n{err_tag()} Failed to generate base English SRT file.")
                        return 1
                    source_srt_for_conversion = move_srt_to_media_dir(cached_en_srt_path, media_dir)
                    source_lang_for_conversion = "en"

                if target_lang == source_lang_for_conversion:
                    selected_srt_path = source_srt_for_conversion
                else:
                    ok_tr = translate_srt_file_offline(
                        en_srt_path=source_srt_for_conversion,
                        out_srt_path=cached_target_srt_path,
                        target_lang=target_lang,
                        models_dir=argos_models_dir,
                        pkg_dir=argos_pkg_dir,
                        source_lang=source_lang_for_conversion,
                    )
                    if ok_tr:
                        selected_srt_path = move_srt_to_media_dir(cached_target_srt_path, media_dir)
                    else:
                        cprint(
                            f"  {warn_tag()} Conversion to '{target_lang}' failed -> "
                            f"falling back to {source_srt_for_conversion.name}."
                        )
                        selected_srt_path = source_srt_for_conversion

        return play_media_with_srt(
            mplayer_path,
            media_file,
            selected_srt_path,
            args.sub_scale,
            cache_dir=cache_dir,
            audio_track_idx=default_track_idx if len(audio_tracks) > 1 else None,
        )
    except KeyboardInterrupt:
        if selected_srt_path is not None and not _file_nonempty(selected_srt_path):
            selected_srt_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
        cprint(f"\n{warn_tag()} Interrupted by user. Incomplete output and temporary audio removed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
