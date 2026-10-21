# valorant-clipper

Watches your VALORANT games and builds a short montage of each round while you play. When you die (or the round ends with you alive), it saves the round from the OBS replay buffer, picks your best moments, fills a montage template with FFmpeg, and pops the result up on another monitor.

## How it works

1. **Detection:** `dxcam` captures the game monitor at a low frame rate and reads the HUD (see [Detection](#detection)). It also measures on-screen motion, which fills slots when nothing else happened.
2. **Trigger:** your death closes the round. If you survive, the round end closes it instead (the next buy phase banner is a fallback). Only the first trigger per round counts.
3. **Capture:** the app tells OBS (over obs-websocket) to save its replay buffer, then moves the file into `footage/` as `replay_<timestamp>.mkv`. When a new game starts, the previous game's replays and its montages in `output/` (`round_*.mp4`) are deleted. Only files with those names are ever deleted, so anything else you put in either folder is kept.
4. **Selection:** events are scored (kills, multikills, spike plants and defuses, utility). Slots with no scored moment are filled with the highest-motion parts of the round.
5. **Render:** FFmpeg trims the chosen segments, applies the template overlays and music, and encodes with NVENC.
6. **Viewer:** a frameless, always-on-top window plays the montage centered on the monitor you choose, without taking focus from the game. Click it to close early.

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
- **Settings > Output > Recording:** record at 1920x1080 with an NVENC H.264 or HEVC encoder. 4K AV1 works, but it takes about 8 seconds per montage to decode instead of about 2.

In VALORANT, turn off the "Shooting Error" performance graph. It sits on top of the kill feed and delays death detection.

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

Offline test with a full recording. `scan` runs the same detection as live mode, prints every event, and writes one event file per round:

```powershell
.venv\Scripts\python -m valclip scan footage\match.mkv --out-dir output\scan
.venv\Scripts\python -m valclip render footage\match.mkv output\scan\round_01.json
```

Event files use seconds from the start of the video, and can also be written by hand:

```json
{"round_start": 2.0, "trigger": 80.0, "events": [{"kind": "kill", "time": 41.5}, {"kind": "death", "time": 80.0}], "motion": [[3.0, 12.5]]}
```

`motion` is optional. Without it, `render` measures motion from the video.

Event kinds: `round_start`, `round_end`, `buy_phase`, `match_start`, `kill`, `death`, `ability`, `spike_plant`, `spike_defuse`.

## Config (`config.json`)

| Key | Default | Meaning |
| --- | --- | --- |
| `obs_host`, `obs_port`, `obs_password` | `localhost`, `4455`, empty | obs-websocket connection |
| `capture_monitor` | `0` | dxcam output index of the game monitor |
| `viewer_monitor` | `1` | Qt screen index for the popup |
| `detect_fps` | `10` | detection frame rate |
| `post_roll` | `1.5` | seconds to wait after the trigger before saving the replay |
| `cues_dir` | `assets/cues` | folder with `cues.json` and cue images |
| `template_dir` | `templates/default` | montage template folder |
| `output_dir` | `output` | where montages are written, kept until the next game starts |
| `replay_dir` | `footage` | where saved round replays are kept until the next game starts |
| `viewer_scale` | `0.5` | popup size as a fraction of the monitor (0.5 is a quarter of the screen) |
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

## Detection

Detection reads the HUD only. It never touches game memory, so it is safe with Vanguard. Positions are measured on 1920x1080 and scale to any 16:9 resolution.

- **Kills and deaths:** your own kill feed entries have a yellow outline. An outline on the left portrait is your kill, and one on the far right portrait is your death. This works with every weapon skin, unlike the kill banner.
- **Utility:** each ability slot (C, Q, E and the X ult dots) has a teal charge bar. When one slot loses charge, that is a cast. When several slots change at once (buy menu, spectating), nothing fires.
- **Round end:** the two team scores at the top. A score changing and staying for 2 seconds means the round ended, whichever banner is shown (WON, LOST, FLAWLESS, ACE). Only the bright digit strokes are compared, so flashes and bright maps behind the see-through bar do not count.
- **New game:** the "ROUND1" text on the first buy phase banner. Rounds 2 and later score well below the threshold.
- **Rounds:** the "PRESS [B] TO BUY" line under every buy phase banner is a template cue. It disappearing means combat started, and it appearing means the next buy phase. Rounds shorter than 20 seconds are ignored, because opening the buy menu also hides the banner. Rounds longer than 170 seconds are ignored too, since that buy phase belongs to the next game.
- **Spike plants and defuses:** not detected yet.

Template cues live in `assets/cues/cues.json`:

```json
[{"kind": "buy_phase", "image": "buy_press.png", "roi": [0.405, 0.2, 0.19, 0.08], "threshold": 0.7, "cooldown": 1.0, "trigger": "appear"}]
```

- `roi` is x, y, width, height as fractions of the screen.
- `trigger` is `appear` (fire when the cue shows up) or `disappear` (fire when it goes away).
- Cue images are grayscale crops from 1920x1080 footage.
- The buy cue assumes the default buy key `B`. If you rebound it, crop a new `buy_press.png`.

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
- [x] Detection tuned on real footage (kills, deaths, utility, rounds)
- [ ] Spike plant and defuse detection
- [ ] DaVinci Resolve template compiler
- [ ] Trained model for movement highlights
