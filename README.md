# KaraokeFuture

A local, self-hosted AI karaoke app for home parties. Guests pick songs from their phones; the host machine does everything else, offline-first and with no accounts.

## How it works

1. **Search** YouTube (yt-dlp) and queue a song; audio and a muted video track are downloaded and cached (5 GB LRU limit).
2. **Vocal separation** with BS-Roformer (audio-separator) produces an instrumental and a vocal stem.
3. **Lyrics** come from, in order of preference: text pasted by a guest, online synced LRC (syncedlyrics), or Whisper transcription with stable-ts word-level alignment. LRC-anchored repair fixes drift, and a vocal-activity map shows where singing actually happens.
4. **Playback** shows word-highlighted lyrics over the video/theater backdrop.

Target hardware: Windows 11 with an RTX 3060 (6 GB VRAM). Only one model is held in VRAM at a time.

## Pages

| Path | Purpose |
|------|---------|
| `/tv` | Host control panel; plays the audio |
| `/screen` | Projector / TV display (lyrics and video) |
| `/remote` | Guest phones: search and queue songs |
| `/library` | Song and lyrics manager |
| `/settings` | Advanced settings (processing, lyrics, game, playback) with per-setting, per-group and full reset; only the laptop can change them unless allowed. Changes are stored in `ai_karaoke/settings.json` (not in git) |

## Setup (Windows)

Full notes are in the header of [ai_karaoke/requirements.txt](ai_karaoke/requirements.txt). In short, from the repo root (Python 3.10-3.12):

```powershell
python -m venv ai_karaoke/.venv
ai_karaoke\.venv\Scripts\activate
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
winget install Gyan.FFmpeg
winget install DenoLand.Deno
pip install -r ai_karaoke/requirements.txt
pip uninstall -y onnxruntime
pip install --force-reinstall --no-deps onnxruntime-gpu
```

Install the PyTorch CUDA trio **first**, otherwise pip may swap in a CPU-only torch. Verify with `python -c "import torch; print(torch.cuda.is_available())"`. FFmpeg must be on `PATH` (reopen the terminal after installing). Deno is recommended for yt-dlp's YouTube extraction. On laptops, use the vendor's Performance mode on the charger.

## Run

```powershell
python ai_karaoke/main.py
```

The server listens on port 8000 (set `KARAOKE_PORT` to change it). Startup logs print the URLs: open `/tv` on the host, `/screen` on the projector and share `/remote` with guests on the same network. The separator model (~640 MB) is downloaded on first use.

Other settings (`KARAOKE_HOST`, `KARAOKE_CACHE_DIR`, `KARAOKE_MODELS_DIR`, `KARAOKE_LYRICS_DIR`, `KARAOKE_MAX_DURATION`, `KARAOKE_VIDEO`, `KARAOKE_VIDEO_HEIGHT`, `KARAOKE_SEPARATOR_MODEL`) are environment variables read in [ai_karaoke/config.py](ai_karaoke/config.py).

## Not in the repo

`ai_karaoke/cache/`, `ai_karaoke/models/` and `ai_karaoke/lyrics_store/` are created at runtime and git-ignored (downloaded media, model weights, guest-pasted lyrics).
