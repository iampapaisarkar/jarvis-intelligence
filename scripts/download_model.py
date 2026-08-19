#!/usr/bin/env python3
"""Download a local Qwen2.5 Instruct GGUF for Jarvis (internet required once)."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_DIR = REPO_ROOT / "models" / "llm"
STT_DIR = REPO_ROOT / "models" / "stt"
TTS_DIR = REPO_ROOT / "models" / "tts"

MODELS = {
    "7b": {
        "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
        "min_bytes": 3_000_000_000,
        "urls": [
            "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        ],
    },
    "1.5b": {
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "min_bytes": 10_000_000,
        "urls": [
            "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "https://huggingface.co/tensorblock/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        ],
    },
    "0.5b": {
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "min_bytes": 10_000_000,
        "urls": [
            "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
            "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        ],
    },
}

STT_MODELS = {
    "base": {
        "filename": "ggml-base.bin",
        "min_bytes": 20_000_000,
        "urls": [
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
            "https://github.com/ggerganov/whisper.cpp/raw/master/models/ggml-base.bin",
        ],
    },
    "small": {
        "filename": "ggml-small.bin",
        "min_bytes": 40_000_000,
        "urls": [
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
        ],
    },
    "tiny": {
        "filename": "ggml-tiny.bin",
        "min_bytes": 10_000_000,
        "urls": [
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        ],
    },
}

TTS_FILES = [
    {
        "filename": "en_US-ryan-medium.onnx",
        "min_bytes": 10_000_000,
        "urls": [
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
        ],
    },
    {
        "filename": "en_US-ryan-medium.onnx.json",
        "min_bytes": 500,
        "urls": [
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json",
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json",
        ],
    },
]


_last_progress = {"pct": -1}


def _progress(block_num: int, block_size: int, total_size: int) -> None:
    downloaded = block_num * block_size
    if total_size <= 0:
        print(f"\rdownloaded {downloaded / 1_048_576:.1f} MiB", end="", flush=True)
        return
    percent = min(100.0, downloaded * 100.0 / total_size)
    shown = int(percent)
    if shown == _last_progress["pct"]:
        return
    _last_progress["pct"] = shown
    print(f"\r{percent:5.1f}%  {downloaded / 1_048_576:.1f}/{total_size / 1_048_576:.1f} MiB", end="", flush=True)


def download(urls: list[str], dest: Path, min_bytes: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "jarvis-setup/0.1")]
    urllib.request.install_opener(opener)
    last_error: Exception | None = None
    global _last_progress
    _last_progress = {"pct": -1}
    for url in urls:
        print(f"Downloading\n  {url}\n  -> {dest}")
        try:
            urllib.request.urlretrieve(url, tmp, reporthook=_progress)
            print()
            if tmp.stat().st_size < min_bytes:
                raise RuntimeError(
                    f"Downloaded file is too small ({tmp.stat().st_size} bytes). "
                    "The URL may have returned an HTML error page."
                )
            tmp.replace(dest)
            print(f"Saved {dest} ({dest.stat().st_size / 1_048_576:.1f} MiB)")
            return
        except (urllib.error.URLError, OSError, RuntimeError) as exc:
            last_error = exc
            print(f"\nFailed: {exc}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink()
    raise SystemExit(f"Could not download model. Last error: {last_error}")


def _already_present(dest: Path, min_bytes: int, force: bool) -> bool:
    if dest.is_file() and dest.stat().st_size > min_bytes and not force:
        print(f"Already present: {dest} ({dest.stat().st_size / 1_048_576:.1f} MiB)")
        print("Use --force to download again.")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download local models for Jarvis")
    parser.add_argument(
        "--7b",
        dest="seven_b",
        action="store_true",
        help="Download Qwen2.5 7B Q4_K_M (~4.7 GB). Smarter, much slower on 8 GB CPU.",
    )
    parser.add_argument(
        "--small",
        action="store_true",
        help="Download Qwen2.5 0.5B Q4_K_M instead of 1.5B (less RAM)",
    )
    parser.add_argument(
        "--stt",
        action="store_true",
        help="Download the Whisper GGML model instead of the LLM",
    )
    parser.add_argument(
        "--tiny",
        action="store_true",
        help="With --stt, download ggml-tiny.bin instead of ggml-base.bin",
    )
    parser.add_argument(
        "--stt-small",
        action="store_true",
        help="With --stt, download ggml-small.bin (better Bangla; uses more RAM)",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Download the Piper English voice instead of the LLM",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if the file exists")
    args = parser.parse_args()

    if args.stt:
        if args.tiny:
            spec = STT_MODELS["tiny"]
        elif args.stt_small:
            spec = STT_MODELS["small"]
        else:
            spec = STT_MODELS["base"]
        dest = STT_DIR / spec["filename"]
        if _already_present(dest, spec["min_bytes"], args.force):
            return
        download(spec["urls"], dest, spec["min_bytes"])
        return

    if args.tts:
        for spec in TTS_FILES:
            dest = TTS_DIR / spec["filename"]
            if _already_present(dest, spec["min_bytes"], args.force):
                continue
            download(spec["urls"], dest, spec["min_bytes"])
        return

    if args.seven_b and args.small:
        raise SystemExit("Use only one of --7b or --small.")
    if args.seven_b:
        spec = MODELS["7b"]
    elif args.small:
        spec = MODELS["0.5b"]
    else:
        spec = MODELS["1.5b"]
    dest = LLM_DIR / spec["filename"]
    if _already_present(dest, spec["min_bytes"], args.force):
        return
    download(spec["urls"], dest, spec["min_bytes"])


if __name__ == "__main__":
    main()
