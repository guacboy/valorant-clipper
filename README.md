# valorant-clipper

Watches your VALORANT games and builds a short montage of each round while you play. When you die (or the round ends with you alive), it saves the round from the OBS replay buffer, picks your best moments, fills a montage template with FFmpeg, and pops the result up on another monitor.

## How it works

1. **Detection:** `dxcam` captures the game monitor at a low frame rate. OpenCV matches HUD cue images (kill banner, death screen, round banners, ability icons) to produce events, and measures camera motion for "cool movement" filler.
2. **Trigger:** your death, or the round end if you survived, closes the round. Only the first trigger per round counts.
3. **Capture:** the app tells OBS (over obs-websocket) to save its replay buffer.
4. **Selection:** events are scored (kills, multikills, spike plants and defuses, utility). Slots with no scored moment are filled with the highest-motion parts of the round.
5. **Render:** FFmpeg trims the chosen segments, applies the template overlays and music, and encodes with NVENC.
6. **Viewer:** a frameless, always-on-top window plays the montage on the monitor you choose, without taking focus from the game. Click it to close early.

## Requirements

- Windows, Python 3.13
- OBS Studio 28 or newer (obs-websocket is built in)
- FFmpeg on PATH (`winget install Gyan.FFmpeg`)
- An NVIDIA GPU for `h264_nvenc` (set `"encoder": "libx264"` otherwise)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
git config core.hooksPath .githooks
copy config.example.json config.json
```

In OBS:

- **Tools > WebSocket Server Settings:** enable the server and put the port and password in `config.json`.
- **Settings > Output > Replay Buffer:** enable it and set the maximum time to at least 150 seconds so a full round fits.

Find your monitor numbers with:

```powershell
.venv\Scripts\python -m valclip monitors
```

Set `capture_monitor` to the dxcam index of the monitor VALORANT runs on and `viewer_monitor` to the Qt index where montages should appear. If the capture comes back black, switch VALORANT to windowed fullscreen.

## Usage

Live mode:

```powershell
.venv\Scripts\python -m valclip run
```

Offline test with a recorded clip and a hand-written event file (times in seconds from the clip start):

```powershell
.venv\Scripts\python -m valclip render round.mp4 events.json
```

```json
{"round_start": 2.0, "trigger": 80.0, "events": [{"kind": "kill", "time": 41.5}, {"kind": "death", "time": 80.0}]}
```

Event kinds: `round_start`, `round_end`, `kill`, `death`, `ability`, `spike_plant`, `spike_defuse`.

## Config (`config.json`)

| Key | Default | Meaning |
| --- | --- | --- |
| `obs_host`, `obs_port`, `obs_password` | `localhost`, `4455`, empty | obs-websocket connection |
| `capture_monitor` | `0` | dxcam output index of the game monitor |
| `viewer_monitor` | `1` | Qt screen index for the popup |
| `detect_fps` | `10` | detection frame rate |
| `post_roll` | `1.5` | seconds recorded after the trigger |
| `cues_dir` | `assets/cues` | folder with `cues.json` and cue images |
| `template_dir` | `templates/default` | montage template folder |
| `output_dir` | `output` | where montages are written |
| `encoder` | `h264_nvenc` | `h264_nvenc` or `libx264` |
| `ffmpeg`, `ffprobe` | from PATH | explicit binary paths |

## Templates

A template is a folder with a `template.json`. Asset paths are relative to that folder.

```json
{
  "name": "default",
  "width": 1920,
  "height": 1080,
  "fps": 60,
  "slots": [{"duration": 3.0}, {"duration": 3.0}, {"duration": 3.0}, {"duration": 3.0}],
  "overlays": [{"file": "intro.mov", "start": 0.0}],
  "music": {"file": "track.mp3", "offset": 12.0, "volume": 0.8},
  "game_volume": 1.0
}
```

- `slots` are filled in order with the chosen moments, which are sorted by time. The montage length is the sum of the slot durations.
- `overlays` are videos with transparency (for example QuickTime Animation or ProRes 4444 `.mov` exported from DaVinci Resolve), placed at `start` seconds.
- `music.offset` is where in the track the montage begins.

## Detection cues

`assets/cues/cues.json` lists the HUD images to look for. It ships empty, so live mode records nothing until cues are added from real footage.

```json
[{"kind": "kill", "image": "kill_banner.png", "roi": [0.4, 0.7, 0.2, 0.25], "threshold": 0.8, "cooldown": 0.5, "trigger": "appear"}]
```

- `roi` is x, y, width, height as fractions of the screen.
- `trigger` is `appear` (fire when the cue shows up) or `disappear` (fire when it goes away, such as an ability icon after use).
- Cue images must be cropped from footage at the resolution the game runs at.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

The pre-push hook in `.githooks/pre-push` runs the suite and blocks the push on failure. The FFmpeg tests are skipped if FFmpeg is not on PATH.

## Roadmap

- [x] OBS replay buffer control
- [x] Event tracking, moment scoring and motion filler
- [x] FFmpeg template renderer with NVENC
- [x] Popup viewer
- [ ] Detection cues tuned from real footage
- [ ] DaVinci Resolve template compiler
- [ ] Trained model for movement highlights
