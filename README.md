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
| `/remote` | Guest phones: party login (name + password), search, "I don't know what to sing", own songs: reorder among your own, remove, guide-vocal volume and singing mode |
| `/library` | Song and lyrics manager (changes are host-only) |
| `/settings` | Advanced settings (processing, lyrics, game, playback) with per-setting, per-group and full reset, plus the host PIN and "Wipe Party DB". Changes are stored in `ai_karaoke/settings.json` (not in git) |

**Who may do what.** The laptop running the karaoke is the host. Other devices become host with the host PIN, which is set on the laptop's Settings page. Guests may only manage their own songs; everyone may look. Guests, sessions and the PIN hash live in `ai_karaoke/party/party.db` (not in git; override with `KARAOKE_PARTY_DB`). The login runs over plain HTTP on the home network, so guests shouldn't reuse real passwords.

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

### Desktop App (Multi-Monitor & Seamless Audio)

Double-click **`start-desktop.bat`** (or run `.\start-desktop.ps1`). This launches the Electron desktop wrapper (`desktop/`), which:
- Automatically boots the Python backend if not already running.
- Opens the **Control Panel (`/tv`)** without browser gesture or WebAudio autoplay blocks.
- Automatically detects a connected external display or projector and routes **`📺 Screen` (`/screen`)** directly to that display in fullscreen.
- Auto-grants microphone permissions for instant pitch scoring without browser popups.
- Optionally switches Tailscale Funnel on so mobile guests can join over HTTPS.

You can also run or package it from the `desktop/` directory:
```powershell
cd desktop
npm install
npm start          # Run desktop wrapper
npm run dist       # Package Windows installer (NSIS & portable)
```

### Web Server & Browser Mode

Double-click **`start-karaoke.bat`** (or run `.\start-karaoke.ps1`). It switches [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) on for port 8010, starts the server and opens the control panel. The QR code then links to the public `https://<laptop>.<tailnet>.ts.net/remote` address, so guests can join from mobile data too, over HTTPS. Funnel is switched off again when the server stops (`-KeepFunnel` keeps it on); `-NoFunnel` keeps everything on the home Wi-Fi, and `-Port 8000` picks another port. While Funnel is on, anybody with the link can open the guest page, so set a host PIN on the Settings page. Visitors coming through Funnel are never treated as the laptop. Settings → Guest access → "QR code opens" can force the Wi-Fi address.

Or start it by hand:

```powershell
python ai_karaoke/main.py
```

The server listens on port 8000 (set `KARAOKE_PORT` to change it). Startup logs print the URLs: open `/tv` on the host, `/screen` on the projector and share `/remote` with guests on the same network. The separator model (~640 MB) is downloaded on first use.

Other settings (`KARAOKE_HOST`, `KARAOKE_CACHE_DIR`, `KARAOKE_MODELS_DIR`, `KARAOKE_LYRICS_DIR`, `KARAOKE_MAX_DURATION`, `KARAOKE_VIDEO`, `KARAOKE_VIDEO_HEIGHT`, `KARAOKE_SEPARATOR_MODEL`) are environment variables read in [ai_karaoke/config.py](ai_karaoke/config.py).

## Not in the repo

`ai_karaoke/cache/`, `ai_karaoke/models/` and `ai_karaoke/lyrics_store/` are created at runtime and git-ignored (downloaded media, model weights, guest-pasted lyrics).


## ☕ Support / Sponsor

If AI Karaoke brought music and joy to your party, consider supporting ongoing development:

- **GitHub Sponsors**: [github.com/sponsors/abels-lab](https://github.com/sponsors/abels-lab)
- **Buy Me a Coffee**: [buymeacoffee.com/abelslab](https://buymeacoffee.com/abelslab)
- **Ko-fi**: [ko-fi.com/abelslab](https://ko-fi.com/abelslab)

Party hosts can customize the support / tip link under **Settings → Guest access → Sponsor / Buy Me a Coffee URL**, which updates the ☕ button displayed on the Control Panel, Settings page, and guest phones.
