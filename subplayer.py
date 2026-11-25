import argparse
import ctypes
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
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
CACHE_DIR_NAME = ".cache"
SUBS_DIR_NAME = "subs"
AUDIO_DIR_NAME = "audio"
ARGOS_MODELS_DIR_NAME = "argos_models"
ARGOS_PKG_DIR_NAME = "argos_pkg"
WHISPER_MODE_MARKER = ".whisper_mode"
FFMPEG_GITHUB_RELEASES_API = "https://api.github.com/repos/FFmpeg-Builds/FFmpeg-Builds/releases"
WHISPER_GITHUB_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases"

WHISPER_MODEL_URLS: dict[str, str] = {
    "ggml-tiny.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
    "ggml-tiny.en.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin",
    "ggml-base.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    "ggml-base.en.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin",
    "ggml-small.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
    "ggml-small.en.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin",
    "ggml-medium.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
    "ggml-medium.en.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin",
    "ggml-large-v3.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
    "ggml-large-v3-turbo.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
}

FALLBACK_URLS = {
    "model_base": WHISPER_MODEL_URLS["ggml-base.bin"],
    "whisper_cuda_zip": "",
    "whisper_cpu_zip": "https://sourceforge.net/projects/whisper-cpp.mirror/files/v1.9.2/whisper-bin-x64.zip/download",
    "ffmpeg_zip": "",
    "mplayer_archive": "https://sourceforge.net/projects/mplayer-win32/files/MPlayer%20and%20MEncoder/r38154+g9fe07908c3/MPlayer-x86_64-r38154+g9fe07908c3.7z/download",
}

DEFAULT_MODEL = "ggml-small.bin"
DEFAULT_SUB_SCALE = 2.2
PROMPT_TIMEOUT_SEC = 15
MAX_CONSECUTIVE_MUSIC_BLOCKS = 2

QUICK_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English (base EN subtitles)"),
    ("sk", "Slovak (offline translation EN -> SK)"),
    ("cs", "Czech (offline translation EN -> CS)"),
    ("de", "German (offline translation EN -> DE)"),
    ("pl", "Polish (offline translation EN -> PL)"),
    ("ru", "Russian (offline translation EN -> RU)"),
    ("uk", "Ukrainian (offline translation EN -> UK)"),
    ("hu", "Hungarian (offline translation EN -> HU)"),
    ("es", "Spanish (offline translation EN -> ES)"),
    ("fr", "French (offline translation EN -> FR)"),
    ("it", "Italian (offline translation EN -> IT)"),
    ("ja", "Japanese (offline translation EN -> JA)"),
    ("zh", "Chinese (offline translation EN -> ZH)"),
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

# ==============================================================================
# ANSI COLOR HELPERS (MUTED YELLOW FOR ACTIVE ACTIONS, SOFT WHITE/GRAY FOR REST)
# ==============================================================================
ESC = chr(27)
RESET = f"{ESC}[0m"
SOFT_WHITE = f"{ESC}[37m"
MUTED_GRAY = f"{ESC}[90m"
SOFT_YELLOW = f"{ESC}[33m"
SOFT_GREEN = f"{ESC}[32m"
SOFT_RED = f"{ESC}[31m"
SOFT_CYAN = f"{ESC}[36m"
ANSI_STRIP_RE = re.compile(re.escape(ESC) + r"\[[0-9;]*m")

_COLOR_ENABLED = False


def enable_windows_ansi() -> None:
    """Enable virtual terminal ANSI sequences on Windows consoles."""
    global _COLOR_ENABLED
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            h_out = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            pass
    _COLOR_ENABLED = sys.stdout.isatty() or os.name == "nt"


def bracket_tag(tag_text: str, inner_color: str = "") -> str:
    """Format a status tag with soft-white brackets and muted inner color."""
    if not _COLOR_ENABLED:
        return f"[{tag_text}]"
    if inner_color:
        return f"{SOFT_WHITE}[{RESET}{inner_color}{tag_text}{RESET}{SOFT_WHITE}]{RESET}"
    return f"{SOFT_WHITE}[{RESET}{SOFT_WHITE}{tag_text}{RESET}{SOFT_WHITE}]{RESET}"


def ok_tag() -> str:
    return bracket_tag("OK", SOFT_GREEN)


def warn_tag(label: str = "WARN") -> str:
    return bracket_tag(label, SOFT_YELLOW)


def err_tag(label: str = "ERROR") -> str:
    return bracket_tag(label, SOFT_RED)


def colorize_message(msg: str, important: bool = False) -> str:
    """Colorize bracketed tags; important messages use soft yellow, others muted gray/white."""
    if not _COLOR_ENABLED:
        return msg

    def repl(match: re.Match) -> str:
        inner = match.group(1)
        upper = inner.strip().upper()
        if upper == "OK":
            color = SOFT_GREEN
        elif upper in ("WARN", "WARNING"):
            color = SOFT_YELLOW
        elif upper in ("ERROR", "ERR", "STOP"):
            color = SOFT_RED
        elif upper in ("INFO", "FETCH", "MISSING"):
            color = SOFT_YELLOW if important else SOFT_CYAN
        else:
            color = SOFT_YELLOW if important else SOFT_WHITE
        return bracket_tag(inner, color)

    colored = re.sub(r"\[([^\[\]\r\n]+)\]", repl, msg)
    text_color = SOFT_YELLOW if important else MUTED_GRAY
    return f"{text_color}{colored}{RESET}"


def cprint(msg: str = "", end: str = "\n", flush: bool = True, important: bool = False) -> None:
    """Print a message: important actions in soft yellow, secondary lines in muted gray."""
    print(colorize_message(msg, important=important), end=end, flush=flush)


def cprint_step(msg: str) -> None:
    """Print an active step / action message in soft yellow."""
    cprint(msg, important=True)


def _supports_unicode_bar() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if "utf" in enc:
        return True
    try:
        "\u2501".encode(enc or "ascii")
        return True
    except Exception:
        return False


def render_bar_segment(
    ratio: float | None,
    elapsed_sec: float,
    bar_width: int = 32,
    done: bool = False,
) -> str:
    """Render a determinate or indeterminate progress bar segment."""
    use_unicode = _supports_unicode_bar()
    fill_char = "\u2501" if use_unicode else "#"
    empty_char = "\u2501" if use_unicode else "-"

    if ratio is not None:
        clamped = min(1.0, max(0.0, ratio))
        filled = int(round(bar_width * clamped))
        empty = bar_width - filled
        if _COLOR_ENABLED:
            bar_color = SOFT_GREEN if done else SOFT_YELLOW
            return f"{bar_color}{fill_char * filled}{RESET}{MUTED_GRAY}{empty_char * empty}{RESET}"
        return f"[{fill_char * filled}{empty_char * empty}]"

    pos = int(elapsed_sec * 10) % bar_width
    seg_len = 6
    chars = []
    for i in range(bar_width):
        in_seg = (pos <= i < pos + seg_len) or (
            pos + seg_len > bar_width and i < (pos + seg_len) % bar_width
        )
        if in_seg:
            chars.append(f"{SOFT_YELLOW}{fill_char}{RESET}" if _COLOR_ENABLED else fill_char)
        else:
            chars.append(f"{MUTED_GRAY}{empty_char}{RESET}" if _COLOR_ENABLED else empty_char)
    return "".join(chars) if _COLOR_ENABLED else f"[{''.join(chars)}]"


def write_live_line(line: str, state: dict, newline: bool = False) -> None:
    """Overwrite the current console line cleanly without leftover characters."""
    plain_len = len(ANSI_STRIP_RE.sub("", line))
    last_len = state.get("last_len", 0)
    pad = " " * max(0, last_len - plain_len)
    state["last_len"] = plain_len
    end = "\n" if newline else ""
    sys.stdout.write(f"\r{line}{pad}{end}")
    sys.stdout.flush()


def finish_live_line_if_needed(state: dict) -> None:
    """Terminate a live progress line if one is currently active."""
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
    """Format a download progress line with speed and size."""
    speed_bps = downloaded / max(elapsed_sec, 0.001)
    if speed_bps >= 1024 * 1024:
        speed_str = f"{speed_bps / (1024 * 1024):.1f} MB/s"
    else:
        speed_str = f"{speed_bps / 1024:.0f} KB/s"

    dl_mb = downloaded / (1024 * 1024)
    meta_color = SOFT_YELLOW if _COLOR_ENABLED else ""
    rst = RESET if _COLOR_ENABLED else ""

    if total_bytes and total_bytes > 0:
        ratio = min(1.0, max(0.0, downloaded / total_bytes))
        pct = ratio * 100.0
        tot_mb = total_bytes / (1024 * 1024)
        bar_str = render_bar_segment(ratio, elapsed_sec, bar_width=bar_width, done=done)
        return (
            f"      {bar_str} {meta_color}{dl_mb:.1f}/{tot_mb:.1f} MB ({pct:3.0f}%) "
            f"{speed_str} - {label}{rst}"
        )

    bar_str = render_bar_segment(None, elapsed_sec, bar_width=bar_width, done=done)
    return f"      {bar_str} {meta_color}{dl_mb:.1f} MB {speed_str} - {label}{rst}"


def format_time_progress_bar(
    cur_sec: float,
    total_sec: float | None,
    elapsed_sec: float,
    label: str,
    extra: str = "",
    bar_width: int = 32,
    done: bool = False,
) -> str:
    """Format a time-based progress bar line with active label in soft yellow."""
    extra_part = f" | {extra}" if extra else ""
    active_color = SOFT_YELLOW if _COLOR_ENABLED else ""
    dim_color = MUTED_GRAY if _COLOR_ENABLED else ""
    rst = RESET if _COLOR_ENABLED else ""

    if total_sec and total_sec > 0:
        ratio = min(1.0, max(0.0, cur_sec / total_sec))
        pct = ratio * 100.0
        bar_str = render_bar_segment(ratio, elapsed_sec, bar_width=bar_width, done=done)
        return (
            f"  {bar_str} {dim_color}{cur_sec:6.1f}/{total_sec:6.1f}s ({pct:3.0f}%) "
            f"| {elapsed_sec:5.1f}s{extra_part} - {rst}{active_color}{label}{rst}"
        )

    bar_str = render_bar_segment(None, elapsed_sec, bar_width=bar_width, done=done)
    return (
        f"  {bar_str} {dim_color}{cur_sec:6.1f}s | {elapsed_sec:5.1f}s{extra_part} - "
        f"{rst}{active_color}{label}{rst}"
    )


# ==============================================================================
# SUBTITLE NAMING & SELECTION HELPERS
# ==============================================================================
def normalize_lang_code(lang: str | None) -> str:
    """Normalize a language code into a safe filename tag."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "", (lang or "").strip().lower())
    return cleaned or "en"


def build_srt_path(subs_dir: Path, media_stem: str, lang_code: str) -> Path:
    """Build `<media_stem>_<lang>.srt` inside `<subs_dir>`."""
    return subs_dir / f"{media_stem}_{normalize_lang_code(lang_code)}.srt"


def find_existing_srts_for_media(subs_dir: Path, media_stem: str) -> list[Path]:
    """Find non-empty subtitle files matching `<media_stem>_<lang>.srt` or `<media_stem>.srt`."""
    if not subs_dir.is_dir():
        return []

    found: list[Path] = []
    prefix = f"{media_stem}_"
    for entry in subs_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".srt":
            continue
        try:
            if entry.stat().st_size <= 0:
                continue
        except OSError:
            continue

        stem = entry.stem
        if stem == media_stem or (stem.startswith(prefix) and len(stem) > len(prefix)):
            found.append(entry)

    en_name = f"{media_stem}_en.srt".lower()
    found.sort(key=lambda p: (0 if p.name.lower() == en_name else 1, p.name.lower()))
    return found


def extract_lang_label_from_srt(srt_path: Path, media_stem: str) -> str:
    """Return a human-readable language label extracted from a subtitle filename."""
    prefix = f"{media_stem}_"
    stem = srt_path.stem
    if stem.startswith(prefix) and len(stem) > len(prefix):
        code = stem[len(prefix) :].lower()
        full_name = SUPPORTED_LANGUAGES.get(code)
        return f"{code} ({full_name})" if full_name else code
    return "unlabeled"


# ==============================================================================
# OFFLINE TRANSLATION (PIP INSTALL INTO .cache/argos_pkg + MODELS IN .cache/argos_models)
# ==============================================================================
def set_argos_env_before_import(models_dir: Path) -> None:
    """Set Argos Translate directory environment variables before importing `argostranslate`."""
    models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGE_DIR"] = str(models_dir)
    os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(models_dir)


def ensure_argostranslate_installed(pkg_dir: Path, models_dir: Path) -> bool:
    """Ensure `argostranslate` is available in `<pkg_dir>`."""
    set_argos_env_before_import(models_dir)
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pkg_str = str(pkg_dir)
    if pkg_str not in sys.path:
        sys.path.insert(0, pkg_str)

    try:
        import argostranslate  # noqa: F401
        cprint(f"  {ok_tag()} Package 'argostranslate' is ready (cache pkg dir: {pkg_dir}).")
        return True
    except ImportError:
        pass

    cprint_step(
        f"  {bracket_tag('FETCH', SOFT_YELLOW)} Installing 'argostranslate' into {pkg_dir} via pip..."
    )
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        pkg_str,
        "argostranslate",
    ]
    recent_lines: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        if proc.stdout:
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if line.strip():
                    recent_lines.append(line.strip())
                    if len(recent_lines) > 10:
                        recent_lines.pop(0)
                    cprint(f"    [pip] {line.strip()}")
        rc = proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.terminate()
        cprint(f"\n  {warn_tag()} Installation of 'argostranslate' was interrupted.")
        raise

    if rc != 0:
        tail = " | ".join(recent_lines[-4:]) if recent_lines else "no output captured"
        cprint(f"  {err_tag()} Cannot install 'argostranslate' (pip exit code {rc}): {tail}")
        return False

    importlib.invalidate_caches()
    try:
        import argostranslate  # noqa: F401
        cprint_step(f"  {ok_tag()} Package 'argostranslate' installed into {pkg_dir}.")
        return True
    except ImportError as e:
        cprint(
            f"  {err_tag()} 'argostranslate' installed into {pkg_dir}, but import failed: {e}"
        )
        return False


def _sync_argos_settings_dirs(models_dir: Path) -> None:
    """Ensure `argostranslate.settings` points exclusively to `<models_dir>`."""
    set_argos_env_before_import(models_dir)
    try:
        import argostranslate.settings as argos_settings

        argos_settings.package_data_dir = models_dir
        argos_settings.package_dirs = [models_dir]
        if hasattr(argos_settings, "packages_dir"):
            argos_settings.packages_dir = models_dir
    except Exception:
        pass


def _has_en_to_target_route(argos_tr, target_code: str) -> bool:
    """Check whether Argos Translate exposes an `en -> <target_code>` translation route."""
    try:
        installed_langs = argos_tr.get_installed_languages()
    except Exception:
        return False

    en_lang = next((lang for lang in installed_langs if getattr(lang, "code", None) == "en"), None)
    if en_lang is None:
        return False

    for tr in getattr(en_lang, "translations_from", []) or []:
        to_lang = getattr(tr, "to_lang", None)
        if getattr(to_lang, "code", None) == target_code:
            return True
    return False


def ensure_argos_en_to_target_module(models_dir: Path, pkg_dir: Path, target_lang: str):
    """Ensure `argostranslate` and offline model `en -> <target_lang>` are ready."""
    if not ensure_argostranslate_installed(pkg_dir, models_dir):
        cprint(f"  {warn_tag()} Skipping offline translation because 'argostranslate' is unavailable.")
        return None

    target = normalize_lang_code(target_lang)
    _sync_argos_settings_dirs(models_dir)

    try:
        import argostranslate.package as argos_pkg
        import argostranslate.translate as argos_tr
    except Exception as e:
        cprint(f"  {err_tag()} Failed to load Argos Translate modules: {e}")
        return None

    if _has_en_to_target_route(argos_tr, target):
        cprint(f"  {ok_tag()} Offline model en -> {target} is ready in {models_dir}.")
        return argos_tr

    cprint_step(
        f"  {bracket_tag('FETCH', SOFT_YELLOW)} Downloading offline model en -> {target} into {models_dir}..."
    )
    try:
        argos_pkg.update_package_index()
        available = argos_pkg.get_available_packages()
        pkg = next(
            (p for p in available if p.from_code == "en" and p.to_code == target),
            None,
        )
        if pkg is None:
            cprint(
                f"  {err_tag()} No offline model available in Argos index for direction en -> {target}."
            )
            return None

        dl_path = pkg.download()
        if not dl_path or not Path(dl_path).is_file():
            cprint(f"  {err_tag()} Model download failed for en -> {target}.")
            return None

        argos_pkg.install_from_path(dl_path)
    except Exception as e:
        cprint(f"  {err_tag()} Failed to download or install model en -> {target}: {e}")
        return None

    _sync_argos_settings_dirs(models_dir)
    try:
        importlib.reload(argos_pkg)
        importlib.reload(argos_tr)
    except Exception:
        pass

    if _has_en_to_target_route(argos_tr, target):
        cprint_step(f"  {ok_tag()} Offline model en -> {target} installed into {models_dir}.")
        return argos_tr

    cprint(
        f"  {err_tag()} Model package en -> {target} was installed into {models_dir}, "
        f"but route en -> {target} was not loaded."
    )
    return None


def translate_srt_file_offline(
    en_srt_path: Path,
    out_srt_path: Path,
    target_lang: str,
    models_dir: Path,
    pkg_dir: Path,
) -> bool:
    """Translate `<name>_en.srt` into `<name>_<target_lang>.srt` with animated progress bar."""
    if not en_srt_path.is_file() or en_srt_path.stat().st_size <= 0:
        cprint(f"  {err_tag()} Source English SRT is missing or empty: {en_srt_path}")
        return False

    target = normalize_lang_code(target_lang)
    argos_tr = ensure_argos_en_to_target_module(models_dir, pkg_dir, target)
    if argos_tr is None:
        cprint(f"  {warn_tag()} Offline translation en -> {target} could not proceed.")
        return False

    cprint_step(
        f"\n=== Translating subtitles {en_srt_path.name} -> {out_srt_path.name} (offline model) ==="
    )
    raw_content = en_srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\r?\n\r?\n", raw_content.strip())

    parsed_blocks: list[tuple[str, str, list[str]]] = []
    text_lines_total = 0

    for blk in blocks:
        lines = [ln.rstrip("\r") for ln in blk.splitlines()]
        if len(lines) >= 3 and "-->" in lines[1]:
            idx_line = lines[0].strip()
            ts_line = lines[1].strip()
            txt_lines = lines[2:]
            parsed_blocks.append((idx_line, ts_line, txt_lines))
            text_lines_total += sum(1 for t in txt_lines if t.strip())
        elif lines:
            parsed_blocks.append(("", "", lines))

    if not parsed_blocks or text_lines_total == 0:
        cprint(f"  {err_tag()} Source English SRT contains no translatable subtitle text.")
        return False

    start_wall = time.time()
    bar_state = {"last_len": 0}
    state_lock = threading.Lock()
    done_lines = 0
    translated_ok = 0
    fallback_lines = 0
    out_blocks: list[str] = []
    stop_ticker = threading.Event()

    def render_translate_line(done: bool = False) -> str:
        with state_lock:
            cur = done_lines
        elapsed = time.time() - start_wall
        return format_time_progress_bar(
            cur_sec=float(text_lines_total if done else cur),
            total_sec=float(max(1, text_lines_total)),
            elapsed_sec=elapsed,
            label=f"Translating EN->{target}",
            done=done,
        )

    def ticker_loop():
        while not stop_ticker.is_set():
            write_live_line(render_translate_line(done=False), bar_state, newline=False)
            stop_ticker.wait(0.12)

    t_tick = threading.Thread(target=ticker_loop, daemon=True)
    t_tick.start()

    try:
        for idx_line, ts_line, txt_lines in parsed_blocks:
            if not ts_line:
                out_blocks.append("\n".join(txt_lines))
                continue

            translated_lines: list[str] = []
            for ln in txt_lines:
                stripped = ln.strip()
                if not stripped:
                    translated_lines.append("")
                    continue
                try:
                    tr_raw = argos_tr.translate(stripped, "en", target)
                    tr_clean = " ".join((tr_raw or "").splitlines()).strip()
                    if tr_clean:
                        translated_lines.append(tr_clean)
                        translated_ok += 1
                    else:
                        translated_lines.append(stripped)
                        fallback_lines += 1
                except Exception:
                    translated_lines.append(stripped)
                    fallback_lines += 1

                with state_lock:
                    done_lines += 1
                write_live_line(render_translate_line(done=False), bar_state, newline=False)

            block_str = f"{idx_line}\n{ts_line}\n" + "\n".join(translated_lines)
            out_blocks.append(block_str)
    finally:
        stop_ticker.set()
        t_tick.join(timeout=1)

    out_srt_path.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out_srt_path.with_suffix(".part.srt")
    try:
        with open(temp_out, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n\n".join(out_blocks) + "\n")
        os.replace(temp_out, out_srt_path)
    except Exception as e:
        finish_live_line_if_needed(bar_state)
        temp_out.unlink(missing_ok=True)
        cprint(f"  {err_tag()} Failed to write translated SRT file {out_srt_path}: {e}")
        return False

    elapsed = time.time() - start_wall
    write_live_line(render_translate_line(done=True), bar_state, newline=True)

    summary = f"translated={translated_ok}/{text_lines_total}"
    if fallback_lines > 0:
        summary += f", fallback_en={fallback_lines}"
    cprint_step(f"  {ok_tag()} Translated SRT saved in {elapsed:.1f}s ({summary}): {out_srt_path}")
    return True


# ==============================================================================
# LANGUAGE PROMPT & EXISTING SRT SELECTION (WITH 15s AUTO TIMEOUT)
# ==============================================================================
def print_all_supported_languages() -> None:
    """Print all supported language codes in columns."""
    cprint(f"\n--- Supported language codes ({len(SUPPORTED_LANGUAGES)} total) ---")
    items = [f"{code}: {name}" for code, name in sorted(SUPPORTED_LANGUAGES.items())]
    cols = 4
    col_width = 24
    for i in range(0, len(items), cols):
        row = "".join(entry.ljust(col_width) for entry in items[i : i + cols])
        cprint(f"  {row.rstrip()}")


def _input_with_idle_timeout(
    prompt_text: str, timeout_sec: int, timeout_hint: str
) -> tuple[str | None, bool]:
    deadline = time.monotonic() + timeout_sec
    last_shown = -1

    if os.name == "nt":
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                sys.stdout.write("\r" + " " * 110 + "\r")
                sys.stdout.flush()
                return None, True

            sec_left = int(remaining) + 1
            if sec_left != last_shown:
                last_shown = sec_left
                msg = colorize_message(f"[{sec_left:2d}s -> {timeout_hint}] {prompt_text}", important=True)
                sys.stdout.write(f"\r{msg}")
                sys.stdout.flush()

            if msvcrt.kbhit():
                sys.stdout.write("\r" + " " * 110 + "\r")
                sys.stdout.flush()
                return input(colorize_message(prompt_text, important=True)), False

            time.sleep(0.05)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    key_pressed = False
    try:
        tty.setcbreak(fd)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                sys.stdout.write("\r" + " " * 110 + "\r")
                sys.stdout.flush()
                return None, True

            sec_left = int(remaining) + 1
            if sec_left != last_shown:
                last_shown = sec_left
                msg = colorize_message(f"[{sec_left:2d}s -> {timeout_hint}] {prompt_text}", important=True)
                sys.stdout.write(f"\r{msg}")
                sys.stdout.flush()

            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                key_pressed = True
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    if key_pressed:
        sys.stdout.write("\r" + " " * 110 + "\r")
        sys.stdout.flush()
        return input(colorize_message(prompt_text, important=True)), False

    return None, True


def prompt_translate_single_existing_srt(
    existing_srt: Path,
    media_stem: str,
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> tuple[bool, str | None]:
    if not sys.stdin.isatty():
        return False, None

    lang_info = extract_lang_label_from_srt(existing_srt, media_stem)
    cprint_step(f"\n=== Existing SRT found: {existing_srt.name} [{lang_info}] ===")
    cprint(
        f"  {bracket_tag('INFO', SOFT_CYAN)} Press Enter or wait {timeout_sec}s to play with {existing_srt.name}."
    )
    cprint("  Type 'y' to choose a target language, or enter a language code directly (e.g. sk, cs, de).")

    prompt_str = "Translate subtitles to another language? [y/N/lang]: "
    first_attempt = True

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, f"play {existing_srt.name}"
                )
                if timed_out:
                    cprint_step(
                        f"  {bracket_tag('INFO', SOFT_YELLOW)} Prompt timeout ({timeout_sec}s) reached -> "
                        f"playing with {existing_srt.name}."
                    )
                    return False, None
            else:
                raw = input(colorize_message(prompt_str, important=True))
        except EOFError:
            return False, None

        raw = (raw or "").strip()
        if not raw:
            cprint_step(f"  {ok_tag()} Using existing subtitles: {existing_srt.name}")
            return False, None

        lower = raw.lower()
        if lower in ("n", "no", "skip", "play"):
            cprint_step(f"  {ok_tag()} Using existing subtitles: {existing_srt.name}")
            return False, None

        if lower in ("y", "yes", "new", "tr", "translate"):
            return True, None

        if lower in SUPPORTED_LANGUAGES:
            cprint_step(f"  {ok_tag()} Selected target translation language: {lower}")
            return True, lower

        cprint(
            f"  {warn_tag()} Invalid input '{raw}'. Enter 'y', 'n', Enter, or a valid language code (e.g. sk, cs, de)."
        )


def prompt_select_existing_srt(
    existing_srts: list[Path],
    media_stem: str,
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> Path | None:
    en_target = next(
        (p for p in existing_srts if p.name.lower() == f"{media_stem}_en.srt".lower()),
        existing_srts[0],
    )

    if not sys.stdin.isatty():
        return en_target

    cprint_step(f"\n=== Multiple subtitles found in {CACHE_DIR_NAME}/{SUBS_DIR_NAME} ===")
    for idx, p in enumerate(existing_srts, start=1):
        lang_info = extract_lang_label_from_srt(p, media_stem)
        default_mark = "  <-- default on timeout/Enter" if p == en_target else ""
        cprint(f"    {idx:2d}) {p.name} [{lang_info}]{default_mark}")
    cprint("   new) Translate / generate subtitles in another language")
    cprint(
        f"  {bracket_tag('INFO', SOFT_CYAN)} If nothing is entered within {timeout_sec}s (or Enter is pressed), "
        f"auto-selecting: {en_target.name}"
    )

    prompt_str = f"Select subtitle number (1..{len(existing_srts)}), language code, or 'new': "
    first_attempt = True

    while True:
        try:
            if first_attempt:
                first_attempt = False
                raw, timed_out = _input_with_idle_timeout(
                    prompt_str, timeout_sec, f"auto {en_target.name}"
                )
                if timed_out:
                    cprint_step(
                        f"  {bracket_tag('INFO', SOFT_YELLOW)} Prompt timeout ({timeout_sec}s) reached -> "
                        f"auto-selecting {en_target.name}."
                    )
                    return en_target
            else:
                raw = input(colorize_message(prompt_str, important=True))
        except EOFError:
            return en_target

        raw = (raw or "").strip()
        if not raw:
            cprint_step(f"  {ok_tag()} Selected default subtitles: {en_target.name}")
            return en_target

        lower = raw.lower()
        if lower in ("new", "n", "gen", "generate", "tr", "translate"):
            return None

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(existing_srts):
                chosen = existing_srts[idx - 1]
                cprint_step(f"  {ok_tag()} Selected subtitles: {chosen.name}")
                return chosen

        for p in existing_srts:
            if p.name.lower() == f"{media_stem}_{lower}.srt".lower():
                cprint_step(f"  {ok_tag()} Selected subtitles: {p.name}")
                return p

        cprint(
            f"  {warn_tag()} Invalid selection '{raw}'. Enter 1..{len(existing_srts)}, a language code, or 'new'."
        )


def prompt_target_language(
    default_lang: str = "en",
    timeout_sec: int = PROMPT_TIMEOUT_SEC,
) -> str:
    if not sys.stdin.isatty():
        return default_lang

    cprint_step(
        "\n=== Subtitle Language (base EN SRT first, offline EN -> target translation for others) ==="
    )
    cprint(
        f"  {bracket_tag('INFO', SOFT_CYAN)} If nothing is entered within {timeout_sec}s, "
        f"defaulting to '{default_lang}'."
    )
    cprint("  Quick selection:")
    for idx, (code, desc) in enumerate(QUICK_LANGUAGES, start=1):
        cprint(f"    {idx:2d}) {code:<4} - {desc}")
    cprint("   list) Show all supported language codes")
    cprint(f"  Enter = default ({default_lang})")

    prompt_str = "Enter number, language code (e.g. en, sk, cs, de), or 'list': "
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
                        f"  {bracket_tag('INFO', SOFT_YELLOW)} Prompt timeout ({timeout_sec}s) reached -> "
                        f"auto-selecting '{default_lang}'."
                    )
                    return default_lang
            else:
                raw = input(colorize_message(prompt_str, important=True))
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
                cprint_step(f"  {ok_tag()} Selected language: {chosen}")
                return chosen
            cprint(f"  {warn_tag()} Invalid number. Enter 1..{len(QUICK_LANGUAGES)} or a language code.")
            continue

        if lower in SUPPORTED_LANGUAGES:
            cprint_step(f"  {ok_tag()} Selected language: {lower}")
            return lower

        cprint(
            f"  {warn_tag()} Unknown language code '{raw}'. Enter 'list' for all codes or e.g. 'en', 'sk', 'cs'."
        )


# ==============================================================================
# HARDWARE DETECTION
# ==============================================================================
TIMESTAMP_LINE_RE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)"
)


def detect_hardware() -> dict:
    """Detect CPU core count and NVIDIA GPU availability/free VRAM."""
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


def get_cache_dir(work_dir: Path) -> Path:
    cache_dir = work_dir / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_subs_dir(cache_dir: Path) -> Path:
    subs_dir = cache_dir / SUBS_DIR_NAME
    subs_dir.mkdir(parents=True, exist_ok=True)
    return subs_dir


def get_audio_dir(cache_dir: Path) -> Path:
    audio_dir = cache_dir / AUDIO_DIR_NAME
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def get_argos_models_dir(cache_dir: Path) -> Path:
    models_dir = cache_dir / ARGOS_MODELS_DIR_NAME
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_argos_pkg_dir(cache_dir: Path) -> Path:
    pkg_dir = cache_dir / ARGOS_PKG_DIR_NAME
    pkg_dir.mkdir(parents=True, exist_ok=True)
    return pkg_dir


def resolve_tool_path(cache_dir: Path, work_dir: Path, filename: str) -> Path:
    cached_path = cache_dir / filename
    if cached_path.is_file():
        return cached_path
    local_path = work_dir / filename
    if local_path.is_file():
        return local_path
    return cached_path


def cleanup_wav_file(wav_path: Path, reason: str = "") -> None:
    """Remove temporary WAV file once no longer needed."""
    if wav_path.exists():
        try:
            wav_path.unlink()
            suffix = f" ({reason})" if reason else ""
            cprint(f"  {bracket_tag('INFO', SOFT_CYAN)} Removed temporary WAV{suffix}: {wav_path.name}")
        except Exception as e:
            cprint(f"  {warn_tag()} Could not remove temporary WAV {wav_path}: {e}")


def get_wav_duration_sec(wav_path: Path) -> float | None:
    """Return WAV duration in seconds."""
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
            "User-Agent": f"{PROJECT_NAME}/2.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def download_file(url: str, dest_path: Path, label: str = "") -> bool:
    """Download a file from `url` to `dest_path` with a live progress bar."""
    if not url:
        return False
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    bar_state = {"last_len": 0}
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"{PROJECT_NAME}/2.0"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as out:
            total = resp.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None
            downloaded = 0
            start_time = time.time()
            last_print = 0.0

            while True:
                buf = resp.read(1024 * 128)
                if not buf:
                    break
                out.write(buf)
                downloaded += len(buf)
                now = time.time()
                if now - last_print >= 0.12:
                    last_print = now
                    line = format_pip_progress_bar(
                        downloaded=downloaded,
                        total_bytes=total_bytes,
                        elapsed_sec=now - start_time,
                        label=label,
                        done=False,
                    )
                    write_live_line(line, bar_state, newline=False)

            final_line = format_pip_progress_bar(
                downloaded=downloaded,
                total_bytes=total_bytes or downloaded,
                elapsed_sec=time.time() - start_time,
                label=label,
                done=True,
            )
            write_live_line(final_line, bar_state, newline=True)

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
        cprint(f"  {bracket_tag('INFO', SOFT_CYAN)} GitHub API for FFmpeg unavailable ({e}).")
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
        cprint(f"  {bracket_tag('INFO', SOFT_CYAN)} GitHub API for whisper.cpp unavailable ({e}).")

    if prefer_cuda and FALLBACK_URLS.get("whisper_cuda_zip"):
        return FALLBACK_URLS["whisper_cuda_zip"], "cuda"
    if FALLBACK_URLS.get("whisper_cpu_zip"):
        return FALLBACK_URLS["whisper_cpu_zip"], "cpu"
    return "", "cpu"


def extract_zip_and_copy_exe(
    archive_path: Path, candidate_names: list[str], target_exe_name: str, cache_dir: Path
) -> bool:
    extract_tmp = cache_dir / f"_tmp_zip_{target_exe_name}"
    if extract_tmp.exists():
        shutil.rmtree(extract_tmp, ignore_errors=True)
    extract_tmp.mkdir(parents=True, exist_ok=True)

    try:
        if not zipfile.is_zipfile(archive_path):
            cprint(f"  {err_tag()} {archive_path.name} is not a valid ZIP archive.")
            return False

        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_tmp)

        found_file = None
        lower_candidates = [c.lower() for c in candidate_names]

        for cand in lower_candidates:
            for root, _, files in os.walk(extract_tmp):
                for f in files:
                    if f.lower() == cand:
                        found_file = Path(root) / f
                        break
                if found_file:
                    break
            if found_file:
                break

        if not found_file:
            cprint(
                f"  {err_tag()} None of the expected executables were found in archive: {', '.join(candidate_names)}"
            )
            return False

        for item in found_file.parent.iterdir():
            if item.is_file():
                shutil.copy2(item, cache_dir / item.name)

        dest_exe = cache_dir / target_exe_name
        if found_file.name.lower() != target_exe_name.lower():
            shutil.copy2(found_file, dest_exe)

        return dest_exe.is_file()
    except Exception as e:
        cprint(f"  {err_tag()} Failed while extracting ZIP archive: {e}")
        return False
    finally:
        shutil.rmtree(extract_tmp, ignore_errors=True)
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
        for root, _, files in os.walk(extract_tmp):
            for f in files:
                if f.lower() == target_exe_name.lower():
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
    if (cache_dir / "ffmpeg.exe").is_file():
        cprint(f"  {ok_tag()} ffmpeg.exe found in .cache.")
        return True
    if (work_dir / "ffmpeg.exe").is_file():
        cprint(f"  {ok_tag()} ffmpeg.exe found in current directory.")
        return True

    cprint_step(f"  {bracket_tag('MISSING', SOFT_YELLOW)} ffmpeg.exe -> searching for latest Windows build...")
    url = find_latest_ffmpeg_win64_zip_url() or FALLBACK_URLS["ffmpeg_zip"]
    if not url:
        cprint("    -> Could not resolve download URL for ffmpeg.exe.")
        return False

    tmp_zip = cache_dir / "_dl_ffmpeg.zip"
    if not download_file(url, tmp_zip, "ffmpeg"):
        return False

    ok = extract_zip_and_copy_exe(tmp_zip, ["ffmpeg.exe"], "ffmpeg.exe", cache_dir)
    if ok:
        cprint_step(f"    -> {ok_tag()} ffmpeg.exe is ready in .cache.")
    return ok


def get_cached_whisper_mode(cache_dir: Path) -> str:
    marker = cache_dir / WHISPER_MODE_MARKER
    if marker.is_file():
        try:
            return marker.read_text(encoding="utf-8").strip().lower()
        except Exception:
            return ""
    return ""


def set_cached_whisper_mode(cache_dir: Path, mode: str) -> None:
    try:
        (cache_dir / WHISPER_MODE_MARKER).write_text(mode, encoding="utf-8")
    except Exception:
        pass


def ensure_whisper(cache_dir: Path, work_dir: Path, prefer_cuda: bool) -> bool:
    exe = cache_dir / "whisper.exe"
    current_mode = get_cached_whisper_mode(cache_dir)

    if exe.is_file():
        if prefer_cuda and current_mode == "cuda":
            cprint(f"  {ok_tag()} whisper.exe (CUDA/NVIDIA build) found in .cache.")
            return True
        if not prefer_cuda and current_mode in ("cpu", ""):
            cprint(f"  {ok_tag()} whisper.exe found in .cache.")
            return True
        if prefer_cuda and current_mode != "cuda":
            cprint_step(
                f"  {bracket_tag('INFO', SOFT_YELLOW)} NVIDIA GPU detected, upgrading whisper.exe in .cache to CUDA build..."
            )
    elif (work_dir / "whisper.exe").is_file() and not prefer_cuda:
        cprint(f"  {ok_tag()} whisper.exe found in current directory.")
        return True

    target_desc = "NVIDIA CUDA build" if prefer_cuda else "latest whisper.cpp release"
    cprint_step(f"  {bracket_tag('FETCH', SOFT_YELLOW)} whisper.exe -> searching {target_desc}...")
    url, resolved_mode = find_latest_whisper_zip_url(prefer_cuda=prefer_cuda)
    if not url:
        if exe.is_file():
            cprint(f"    -> {warn_tag()} No CUDA build found in releases; keeping existing whisper.exe.")
            return True
        cprint("    -> Could not resolve download URL for whisper.exe.")
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
        set_cached_whisper_mode(cache_dir, resolved_mode)
        cprint_step(f"    -> {ok_tag()} whisper.exe ({resolved_mode}) is ready in .cache.")
    return ok


def ensure_mplayer(cache_dir: Path, work_dir: Path) -> bool:
    if (cache_dir / "mplayer.exe").is_file():
        cprint(f"  {ok_tag()} mplayer.exe found in .cache.")
        return True
    if (work_dir / "mplayer.exe").is_file():
        cprint(f"  {ok_tag()} mplayer.exe found in current directory.")
        return True

    cprint_step(f"  {bracket_tag('MISSING', SOFT_YELLOW)} mplayer.exe -> attempting to fetch package into .cache...")
    url = FALLBACK_URLS.get("mplayer_archive", "").strip()
    if not url:
        cprint("    -> No download URL configured for mplayer.exe.")
        return False

    tmp_arc = cache_dir / "_dl_mplayer.7z"
    if not download_file(url, tmp_arc, "mplayer"):
        return False

    if zipfile.is_zipfile(tmp_arc):
        ok = extract_zip_and_copy_exe(tmp_arc, ["mplayer.exe"], "mplayer.exe", cache_dir)
    else:
        ok = try_extract_7z_if_possible(tmp_arc, "mplayer.exe", cache_dir)
        if not ok and tmp_arc.exists():
            tmp_arc.unlink(missing_ok=True)
            cprint(f"    -> {bracket_tag('INFO', SOFT_CYAN)} mplayer archive is .7z and 7z/7za was not found in PATH.")
            cprint(f"       Extract mplayer.exe manually into {cache_dir} or set a direct .exe/.zip URL.")
            return False

    if ok:
        cprint_step(f"    -> {ok_tag()} mplayer.exe is ready in .cache.")
    return ok


def resolve_model_url(model_arg: str) -> str:
    """Resolve Hugging Face URL for known Whisper model filenames."""
    name = Path(model_arg).name.lower()
    for known_name, url in WHISPER_MODEL_URLS.items():
        if known_name.lower() == name:
            return url
    if name.startswith("ggml-") and name.endswith(".bin"):
        return f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{Path(model_arg).name}"
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
        if p.is_file() and p.stat().st_size > 0:
            cprint(f"  {ok_tag()} Model found: {p}")
            return True

    url = resolve_model_url(model_arg)
    if url:
        cprint_step(
            f"  {bracket_tag('FETCH', SOFT_YELLOW)} Downloading model {Path(model_arg).name} into {target_download_path.parent}..."
        )
        if download_file(url, target_download_path, Path(model_arg).name):
            cprint_step(f"    -> {ok_tag()} Model is ready: {target_download_path}")
            return True

    cprint(f"  {warn_tag('WARNING')} Model '{model_arg}' could not be downloaded automatically.")
    return False


def ensure_all_dependencies(cache_dir: Path, work_dir: Path, model_arg: str, hw: dict) -> dict[str, bool]:
    cprint_step(f"=== {PROJECT_NAME}: Checking and preparing dependencies (cache: {cache_dir}) ===")
    status = {
        "ffmpeg.exe": ensure_ffmpeg(cache_dir, work_dir),
        "whisper.exe": ensure_whisper(cache_dir, work_dir, prefer_cuda=hw["use_gpu"]),
        "mplayer.exe": ensure_mplayer(cache_dir, work_dir),
        "model": ensure_model(cache_dir, work_dir, model_arg),
    }
    return status


def print_missing_summary(status: dict[str, bool], cache_dir: Path, model_arg: str) -> None:
    cprint("\n--- Dependency Status ---")
    for key, ok in status.items():
        label = model_arg if key == "model" else key
        state_str = ok_tag() if ok else err_tag("MISSING")
        cprint(f"  {state_str} {label}")
    cprint(f"Cache directory: {cache_dir}")


def print_usage_help(status: dict[str, bool], cache_dir: Path, model_arg: str, hw: dict) -> None:
    script_name = Path(sys.argv[0]).name
    gpu = hw["gpu"]
    gpu_desc = f"{gpu['name']} ({gpu['vram_free_mb']} MB free)" if gpu["has_nvidia"] else "none detected"
    mode_desc = "NVIDIA GPU" if hw["use_gpu"] else "CPU"
    cprint(f"\n=== {PROJECT_NAME} Usage ===")
    cprint(f"  python {script_name} <media_file> [options]")
    cprint(
        f"Detected hardware: CPU threads={hw['cpu_threads']} | NVIDIA GPU={gpu_desc} | Compute={mode_desc}"
    )
    cprint(f"Auto profile: threads={hw['recommended_threads']}")
    cprint("\nExamples:")
    cprint(f"  python {script_name} movie.mkv")
    cprint(f"  python {script_name} movie.mkv --lang sk")
    cprint(f"  python {script_name} movie.mkv --lang sk --force-srt")
    cprint("\nOptions:")
    cprint("  media_file      Path to video or audio file to play")
    cprint(f"  --model         Path or filename of Whisper model (default: {DEFAULT_MODEL} in {CACHE_DIR_NAME}/)")
    cprint("  --lang          Target subtitle language (en -> <name>_en.srt; sk -> translates EN to <name>_sk.srt)")
    cprint(f"  --no-prompt     Skip interactive prompts (default timeout: {PROMPT_TIMEOUT_SEC}s)")
    cprint(f"  --threads       Threads per whisper.exe job (default: auto -> {hw['recommended_threads']})")
    cprint(f"  --sub-scale     MPlayer subtitle text scale (default: {DEFAULT_SUB_SCALE})")
    cprint("  --force-srt     Regenerate base EN SRT and target language SRT")
    print_missing_summary(status, cache_dir, model_arg)


# ==============================================================================
# FULL AUDIO EXTRACTION + ENGLISH SRT GENERATION
# ==============================================================================
def get_media_duration_sec(ffmpeg_path: Path, media_file: Path) -> float | None:
    cmd = [str(ffmpeg_path), "-i", str(media_file), "-hide_banner"]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in res.stdout.splitlines():
        line = line.strip()
        if "Duration:" in line:
            try:
                part = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
                h_str, m_str, s_str = part.split(":")
                return int(h_str) * 3600 + int(m_str) * 60 + float(s_str)
            except Exception:
                return None
    return None


def _run_ffmpeg_audio_extract(
    ffmpeg_path: Path,
    media_file: Path,
    temp_wav: Path,
    duration_sec: float | None,
    use_speech_filter: bool,
) -> tuple[bool, float]:
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(media_file),
        "-vn",
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
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_print = 0.0
    try:
        if proc.stdout:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        out_us = int(line.split("=", 1)[1].strip())
                        cur_sec = max(0.0, out_us / 1_000_000.0)
                        now = time.time()
                        if now - last_print >= 0.15:
                            last_print = now
                            live = format_time_progress_bar(
                                cur_sec=cur_sec,
                                total_sec=duration_sec,
                                elapsed_sec=now - start_wall,
                                label="Audio extraction",
                                done=False,
                            )
                            write_live_line(live, bar_state, newline=False)
                    except ValueError:
                        pass
        rc = proc.wait()
        if rc != 0 or not temp_wav.is_file() or temp_wav.stat().st_size <= 44:
            finish_live_line_if_needed(bar_state)
            temp_wav.unlink(missing_ok=True)
            return False, time.time() - start_wall

        elapsed = time.time() - start_wall
        final_sec = duration_sec if (duration_sec and duration_sec > 0) else cur_sec
        done_line = format_time_progress_bar(
            cur_sec=final_sec,
            total_sec=duration_sec,
            elapsed_sec=elapsed,
            label="Audio extraction",
            done=True,
        )
        write_live_line(done_line, bar_state, newline=True)
        return True, elapsed
    except Exception:
        finish_live_line_if_needed(bar_state)
        if proc.poll() is None:
            proc.terminate()
        temp_wav.unlink(missing_ok=True)
        raise


def extract_full_audio(
    ffmpeg_path: Path, media_file: Path, wav_path: Path, duration_sec: float | None
) -> bool:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = wav_path.with_suffix(".part.wav")
    temp_wav.unlink(missing_ok=True)

    cprint_step(f"\n=== Step 1/2: Extracting full audio into {wav_path} ===")
    ok, elapsed = _run_ffmpeg_audio_extract(
        ffmpeg_path, media_file, temp_wav, duration_sec, use_speech_filter=True
    )
    if not ok:
        ok, elapsed = _run_ffmpeg_audio_extract(
            ffmpeg_path, media_file, temp_wav, duration_sec, use_speech_filter=False
        )
    if not ok:
        cprint(f"  {err_tag()} FFmpeg failed to extract full audio from {media_file.name}.")
        return False

    os.replace(temp_wav, wav_path)
    size_mb = wav_path.stat().st_size / (1024 * 1024)
    cprint(f"  {ok_tag()} Full audio extracted in {elapsed:.1f}s ({size_mb:.1f} MB): {wav_path}")
    return True


def format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours = ms_total // 3_600_000
    rem = ms_total % 3_600_000
    minutes = rem // 60_000
    rem = rem % 60_000
    secs = rem // 1000
    millis = rem % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_whisper_ts_to_sec(ts: str) -> float:
    h_str, m_str, rest = ts.split(":")
    s_str, ms_str = rest.split(".")
    return int(h_str) * 3600 + int(m_str) * 60 + int(s_str) + int(ms_str) / 1000.0


def _is_non_speech_music_tag(text: str) -> bool:
    norm = re.sub(r"[^a-zA-Z]+", " ", text).strip().lower()
    return norm in ("music", "music playing", "blank audio", "applause")


def _clean_srt_blocks_and_rewrite(srt_path: Path) -> int:
    """Filter repetitive non-speech `[Music]` hallucination runs and re-index SRT cleanly."""
    if not srt_path.is_file() or srt_path.stat().st_size <= 0:
        return 0

    raw = srt_path.read_text(encoding="utf-8", errors="replace")
    raw_blocks = re.split(r"\r?\n\r?\n", raw.strip())
    cleaned_entries: list[str] = []
    consecutive_music = 0
    idx = 1

    for blk in raw_blocks:
        lines = [ln.rstrip("\r") for ln in blk.splitlines() if ln.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        ts_line = lines[1].strip()
        txt = " ".join(" ".join(lines[2:]).split()).strip()
        if not txt:
            continue

        if _is_non_speech_music_tag(txt):
            consecutive_music += 1
            if consecutive_music > MAX_CONSECUTIVE_MUSIC_BLOCKS:
                continue
        else:
            consecutive_music = 0

        cleaned_entries.append(f"{idx}\n{ts_line}\n{txt}\n")
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
        line = raw_line.strip()
        m = TIMESTAMP_LINE_RE.search(line)
        if m:
            s_sec = parse_whisper_ts_to_sec(m.group(1))
            e_sec = parse_whisper_ts_to_sec(m.group(2))
            txt = " ".join(m.group(3).split()).strip()
            if txt and e_sec > s_sec:
                if _is_non_speech_music_tag(txt):
                    consecutive_music += 1
                    if consecutive_music > MAX_CONSECUTIVE_MUSIC_BLOCKS:
                        continue
                else:
                    consecutive_music = 0
                segments.append((s_sec, e_sec, txt))

    if not segments:
        return 0

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    idx = 1
    prev_end = 0.0
    for s_sec, e_sec, txt in segments:
        start_c = max(s_sec, prev_end)
        end_c = max(start_c + 0.8, e_sec)
        prev_end = end_c
        entries.append(
            f"{idx}\n{format_srt_timestamp(start_c)} --> {format_srt_timestamp(end_c)}\n{txt}\n"
        )
        idx += 1

    with open(srt_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(entries))

    return idx - 1


def _build_whisper_cmds(
    whisper_path: Path, model_path: Path, wav_path: Path, osrt_prefix: str, threads: int
) -> list[list[str]]:
    base_cmd = [
        str(whisper_path),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-t",
        str(max(1, threads)),
        "-tr",
        "-osrt",
        "-of",
        osrt_prefix,
    ]
    anti_loop_cmd = base_cmd + ["-mc", "0", "-et", "2.4", "-nth", "0.60"]
    return [anti_loop_cmd, base_cmd]


def transcribe_full_audio_to_en_srt(
    whisper_path: Path,
    model_path: Path,
    wav_path: Path,
    en_srt_path: Path,
    threads: int,
    hw: dict,
) -> bool:
    """Transcribe/translate full WAV audio into base English `<name>_en.srt` via whisper.exe (-tr)."""
    gpu = hw["gpu"]
    gpu_label = f"{gpu['name']} ({gpu['vram_free_mb']} MB free)" if gpu["has_nvidia"] else "none"
    compute_label = "NVIDIA GPU" if hw["use_gpu"] else "CPU"

    cprint_step(f"\n=== Step 2/2: Generating base English SRT -> {en_srt_path} ===")
    cprint(f"Hardware: CPU={hw['cpu_threads']} threads | GPU={gpu_label} | Active={compute_label}")
    cprint(f"Whisper threads: {max(1, threads)} | Mode: translate -> English (-tr)")

    wav_duration_sec = get_wav_duration_sec(wav_path)

    temp_srt = en_srt_path.with_suffix(".part.srt")
    temp_srt.unlink(missing_ok=True)
    osrt_prefix = str(temp_srt)[:-4] if str(temp_srt).lower().endswith(".srt") else str(temp_srt)

    cmds = _build_whisper_cmds(whisper_path, model_path, wav_path, osrt_prefix, threads)
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

        def render_transcribe_line(done: bool = False) -> str:
            with state_lock:
                cur = latest_media_sec
            elapsed = time.time() - start_wall
            effective_cur = wav_duration_sec if (done and wav_duration_sec) else cur
            effective_total = wav_duration_sec if (wav_duration_sec and (cur > 0 or done)) else None
            return format_time_progress_bar(
                cur_sec=effective_cur,
                total_sec=effective_total,
                elapsed_sec=elapsed,
                label="Transcribing EN",
                done=done,
            )

        def ticker_loop():
            while not stop_ticker.is_set():
                with state_lock:
                    cur = latest_media_sec
                if cur <= 0:
                    write_live_line(render_transcribe_line(done=False), bar_state, newline=False)
                stop_ticker.wait(0.2)

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
                            with state_lock:
                                if end_sec > latest_media_sec:
                                    latest_media_sec = end_sec
                        except Exception:
                            pass
                        write_live_line(render_transcribe_line(done=False), bar_state, newline=False)

            rc = proc.wait()
            stop_ticker.set()
            t_tick.join(timeout=1)
            t_err.join(timeout=2)

            if rc != 0:
                finish_live_line_if_needed(bar_state)
                temp_srt.unlink(missing_ok=True)
                if attempt_idx + 1 < len(cmds):
                    cprint_step(
                        f"  {bracket_tag('INFO', SOFT_YELLOW)} Retrying whisper.exe with standard CLI flags..."
                    )
                    continue
                tail = " | ".join(err_lines[-3:]) if err_lines else "unknown error"
                cprint(f"  {err_tag()} whisper.exe exited with code {rc}: {tail}")
                return False

            en_srt_path.parent.mkdir(parents=True, exist_ok=True)
            srt_created = False
            entries_count = 0

            if temp_srt.is_file() and temp_srt.stat().st_size > 0:
                os.replace(temp_srt, en_srt_path)
                entries_count = _clean_srt_blocks_and_rewrite(en_srt_path)
                srt_created = entries_count > 0
            else:
                count = build_srt_from_stdout_lines(captured_lines, en_srt_path)
                if count > 0 and en_srt_path.is_file() and en_srt_path.stat().st_size > 0:
                    entries_count = count
                    srt_created = True

            if srt_created:
                write_live_line(render_transcribe_line(done=True), bar_state, newline=True)
                elapsed = time.time() - start_wall
                suffix = f" ({entries_count} entries)" if entries_count > 0 else ""
                cprint_step(f"  {ok_tag()} EN SRT generated in {elapsed:.1f}s{suffix}: {en_srt_path}")
                cleanup_wav_file(wav_path, "EN SRT created")
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


def ensure_english_srt(
    ffmpeg_path: Path,
    whisper_path: Path,
    model_path: Path,
    media_file: Path,
    wav_path: Path,
    en_srt_path: Path,
    threads: int,
    hw: dict,
    force: bool = False,
) -> bool:
    """Ensure `<name>_en.srt` exists, extracting WAV and running Whisper only if needed."""
    if en_srt_path.is_file() and en_srt_path.stat().st_size > 0 and not force:
        cprint(f"\n{ok_tag()} Existing EN SRT found: {en_srt_path}")
        cleanup_wav_file(wav_path, "EN SRT already exists")
        return True

    duration_sec = get_media_duration_sec(ffmpeg_path, media_file)
    if not wav_path.is_file() or force:
        ok_audio = extract_full_audio(ffmpeg_path, media_file, wav_path, duration_sec)
        if not ok_audio:
            en_srt_path.unlink(missing_ok=True)
            return False
    else:
        cprint(f"\n{ok_tag()} Using cached audio: {wav_path}")

    ok_srt = transcribe_full_audio_to_en_srt(
        whisper_path=whisper_path,
        model_path=model_path,
        wav_path=wav_path,
        en_srt_path=en_srt_path,
        threads=threads,
        hw=hw,
    )
    if not ok_srt:
        en_srt_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
        return False
    return True


def play_media_with_srt(mplayer_path: Path, media_file: Path, srt_path: Path, sub_scale: float) -> int:
    """Launch MPlayer with the selected subtitle file."""
    cprint_step(f"\n=== Launching mplayer.exe with subtitles: {srt_path.name} ===")
    cmd = [
        str(mplayer_path),
        "-sub",
        str(srt_path),
        "-utf8",
        "-subfont-autoscale",
        "3",
        "-subfont-text-scale",
        f"{sub_scale:.2f}",
        str(media_file),
    ]
    res = subprocess.run(cmd)
    return res.returncode


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

    required_ok = (
        status["ffmpeg.exe"]
        and status["whisper.exe"]
        and status["mplayer.exe"]
        and status["model"]
    )
    if not required_ok:
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

    wav_path = audio_dir / f"{media_file.stem}.wav"
    en_srt_path = build_srt_path(subs_dir, media_file.stem, "en")

    selected_srt_path: Path | None = None
    preselected_lang: str | None = None

    try:
        existing_srts = find_existing_srts_for_media(subs_dir, media_file.stem)

        if not args.force_srt:
            if args.lang is not None:
                target_lang = normalize_lang_code(args.lang)
                candidate_srt = build_srt_path(subs_dir, media_file.stem, target_lang)
                if candidate_srt.is_file() and candidate_srt.stat().st_size > 0:
                    selected_srt_path = candidate_srt
                    cprint_step(f"\n{ok_tag()} Existing SRT found: {selected_srt_path}")
                    cleanup_wav_file(wav_path, "SRT already exists")
            elif len(existing_srts) == 1:
                only_srt = existing_srts[0]
                if args.no_prompt:
                    selected_srt_path = only_srt
                    cprint_step(f"\n{ok_tag()} Existing SRT found (--no-prompt): {selected_srt_path}")
                else:
                    wants_translate, direct_lang = prompt_translate_single_existing_srt(
                        only_srt, media_file.stem, PROMPT_TIMEOUT_SEC
                    )
                    if not wants_translate:
                        selected_srt_path = only_srt
                    else:
                        preselected_lang = direct_lang
                if selected_srt_path is not None:
                    cleanup_wav_file(wav_path, "SRT already exists")
            elif len(existing_srts) > 1:
                if args.no_prompt:
                    selected_srt_path = next(
                        (p for p in existing_srts if p.name.lower() == en_srt_path.name.lower()),
                        existing_srts[0],
                    )
                    cprint_step(f"\n{ok_tag()} Selected SRT (--no-prompt): {selected_srt_path}")
                else:
                    selected_srt_path = prompt_select_existing_srt(
                        existing_srts, media_file.stem, PROMPT_TIMEOUT_SEC
                    )
                if selected_srt_path is not None:
                    cleanup_wav_file(wav_path, "SRT already exists")

        if selected_srt_path is None:
            if preselected_lang is not None:
                target_lang = normalize_lang_code(preselected_lang)
            elif args.lang is not None:
                target_lang = normalize_lang_code(args.lang)
            elif args.no_prompt:
                target_lang = "en"
            else:
                default_choice = "sk" if (not args.force_srt and en_srt_path.is_file()) else "en"
                target_lang = prompt_target_language(default_choice, PROMPT_TIMEOUT_SEC)

            target_srt_path = build_srt_path(subs_dir, media_file.stem, target_lang)

            if target_srt_path.is_file() and target_srt_path.stat().st_size > 0 and not args.force_srt:
                selected_srt_path = target_srt_path
                cprint_step(f"\n{ok_tag()} Existing SRT found: {selected_srt_path}")
                cleanup_wav_file(wav_path, "SRT already exists")
            else:
                source_en_for_translation = en_srt_path
                if (
                    not args.force_srt
                    and target_lang != "en"
                    and not (en_srt_path.is_file() and en_srt_path.stat().st_size > 0)
                    and len(existing_srts) == 1
                ):
                    source_en_for_translation = existing_srts[0]
                    cprint(
                        f"\n{bracket_tag('INFO', SOFT_CYAN)} Using existing SRT as translation source: "
                        f"{source_en_for_translation}"
                    )
                else:
                    ok_en = ensure_english_srt(
                        ffmpeg_path=ffmpeg_path,
                        whisper_path=whisper_path,
                        model_path=model_path,
                        media_file=media_file,
                        wav_path=wav_path,
                        en_srt_path=en_srt_path,
                        threads=max(1, args.threads),
                        hw=hw,
                        force=args.force_srt,
                    )
                    if not ok_en:
                        cprint(f"\n{err_tag()} Failed to generate base English SRT file.")
                        return 1

                if target_lang == "en":
                    selected_srt_path = en_srt_path
                else:
                    ok_tr = translate_srt_file_offline(
                        en_srt_path=source_en_for_translation,
                        out_srt_path=target_srt_path,
                        target_lang=target_lang,
                        models_dir=argos_models_dir,
                        pkg_dir=argos_pkg_dir,
                    )
                    if ok_tr:
                        selected_srt_path = target_srt_path
                    else:
                        cprint(
                            f"  {warn_tag()} Translation to '{target_lang}' failed -> "
                            f"falling back to {source_en_for_translation.name}."
                        )
                        selected_srt_path = source_en_for_translation

        return play_media_with_srt(mplayer_path, media_file, selected_srt_path, args.sub_scale)
    except KeyboardInterrupt:
        if selected_srt_path is not None and (
            not selected_srt_path.is_file() or selected_srt_path.stat().st_size == 0
        ):
            selected_srt_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
        cprint(f"\n{warn_tag()} Interrupted by user. Incomplete output and temporary audio removed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
