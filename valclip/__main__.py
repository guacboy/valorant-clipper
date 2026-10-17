"""Entry point.

    python -m valclip run                      live mode: watch the game, pop up montages
    python -m valclip render CLIP EVENTS.json  offline test: build a montage from a recorded clip
    python -m valclip scan VIDEO               offline test: detect events in a recording
    python -m valclip monitors                 list monitor indexes for config.json
"""

import argparse
import json
import queue
import signal
import threading
import time
import traceback
from pathlib import Path

from valclip.config import Config, load_config
from valclip.events import Event, EventKind, RoundLog, RoundTracker
from valclip.media import find_tool, iter_frames, probe
from valclip.pipeline import make_montage, montage_path
from valclip.template import load_template


def cmd_monitors(_: Config) -> None:
    import dxcam
    from PySide6.QtGui import QGuiApplication

    print("capture_monitor (dxcam):")
    print(dxcam.output_info())
    app = QGuiApplication([])
    print("viewer_monitor (Qt):")
    for i, screen in enumerate(app.screens()):
        g = screen.geometry()
        print(f"  {i}: {screen.name()} {g.width()}x{g.height()} at ({g.x()}, {g.y()})")


def build_detector(cfg: Config):
    from valclip.detector import AbilityMeter, Detector, KillFeedReader, load_cues

    return Detector(load_cues(Path(cfg.cues_dir)), [KillFeedReader(), AbilityMeter()])


def cmd_scan(cfg: Config, video: Path, out_dir: Path) -> None:
    """Runs live detection over a recording and writes one EVENTS.json per round for `render`."""
    from valclip.detector import MotionMeter

    detector, meter, tracker = build_detector(cfg), MotionMeter(), RoundTracker()
    out_dir.mkdir(parents=True, exist_ok=True)
    rounds = 0
    for t, frame in iter_frames(video, find_tool("ffmpeg", cfg.ffmpeg), cfg.detect_fps):
        if (score := meter.update(frame)) is not None:
            tracker.add_motion(t, score)
        for event in detector.process(frame, t):
            print(f"{int(t // 60)}:{t % 60:05.2f}  {event.kind.value}")
            if log := tracker.feed(event):
                rounds += 1
                path = out_dir / f"round_{rounds:02d}.json"
                path.write_text(json.dumps({
                    "round_start": log.start,
                    "trigger": log.trigger_time,
                    "events": [{"kind": e.kind.value, "time": round(e.time, 2)} for e in log.events],
                    "motion": [[round(mt, 2), round(ms, 2)] for mt, ms in log.motion],
                }), encoding="utf-8")
                print(f"  -> round {rounds} closed, wrote {path}")


def cmd_render(cfg: Config, clip: Path, events_file: Path, out: Path | None) -> None:
    """EVENTS.json uses clip-relative seconds, as written by `scan`:
    {"round_start": 2.0, "trigger": 80.0, "events": [{"kind": "kill", "time": 41.5}], "motion": [[3.0, 12.5]]}
    """
    ffmpeg, ffprobe = find_tool("ffmpeg", cfg.ffmpeg), find_tool("ffprobe", cfg.ffprobe)
    data = json.loads(events_file.read_text(encoding="utf-8"))
    duration = probe(clip, ffprobe).duration
    log = RoundLog(
        start=data.get("round_start"),
        trigger_time=float(data.get("trigger", duration)),
        events=[Event(EventKind(e["kind"]), float(e["time"])) for e in data.get("events", [])],
        motion=[(float(t), float(s)) for t, s in data.get("motion", [])],
    )
    template = load_template(Path(cfg.template_dir))
    started = time.perf_counter()
    path = make_montage(clip, log, duration, template, out or montage_path(Path(cfg.output_dir)),
                        ffmpeg, ffprobe, cfg.encoder)
    print(f"wrote {path} in {time.perf_counter() - started:.1f}s")


def cmd_run(cfg: Config) -> None:
    import dxcam
    from PySide6.QtWidgets import QApplication

    from valclip.detector import MotionMeter
    from valclip.obs_control import ObsController
    from valclip.viewer import MontageSignals, Viewer

    ffmpeg, ffprobe = find_tool("ffmpeg", cfg.ffmpeg), find_tool("ffprobe", cfg.ffprobe)
    template = load_template(Path(cfg.template_dir))
    detector = build_detector(cfg)
    obs = ObsController(cfg.obs_host, cfg.obs_port, cfg.obs_password)
    obs.ensure_replay_buffer()

    app = QApplication([])
    viewer = Viewer(cfg.viewer_monitor)
    signals = MontageSignals()
    signals.ready.connect(viewer.play)
    rounds: queue.Queue[RoundLog] = queue.Queue()
    stop = threading.Event()

    def watch() -> None:
        tracker = RoundTracker()
        meter = MotionMeter()
        camera = dxcam.create(output_idx=cfg.capture_monitor, output_color="BGR")
        camera.start(target_fps=cfg.detect_fps)
        try:
            while not stop.is_set():
                frame = camera.get_latest_frame()
                if frame is None:
                    continue
                now = time.time()
                if (score := meter.update(frame)) is not None:
                    tracker.add_motion(now, score)
                for event in detector.process(frame, now):
                    print(f"event: {event.kind.value}")
                    if log := tracker.feed(event):
                        rounds.put(log)
        finally:
            camera.stop()

    def work() -> None:
        while not stop.is_set():
            try:
                log = rounds.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                time.sleep(max(0.0, log.trigger_time + cfg.post_roll - time.time()))
                clip = obs.save_replay()
                saved_at = time.time()
                started = time.perf_counter()
                path = make_montage(clip, log, saved_at, template, montage_path(Path(cfg.output_dir)),
                                    ffmpeg, ffprobe, cfg.encoder)
                print(f"montage ready: {path} ({time.perf_counter() - started:.1f}s)")
                signals.ready.emit(str(path))
            except Exception:
                traceback.print_exc()

    threads = [threading.Thread(target=watch, daemon=True), threading.Thread(target=work, daemon=True)]
    for thread in threads:
        thread.start()
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # let Ctrl+C close the Qt event loop
    print("watching; press Ctrl+C in this window to quit")
    try:
        app.exec()
    finally:
        stop.set()


def main() -> None:
    parser = argparse.ArgumentParser(prog="valclip")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("monitors")
    render = sub.add_parser("render")
    render.add_argument("clip", type=Path)
    render.add_argument("events", type=Path)
    render.add_argument("--out", type=Path)
    scan = sub.add_parser("scan")
    scan.add_argument("video", type=Path)
    scan.add_argument("--out-dir", type=Path, default=Path("output/scan"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.command == "run":
        cmd_run(cfg)
    elif args.command == "monitors":
        cmd_monitors(cfg)
    elif args.command == "scan":
        cmd_scan(cfg, args.video, args.out_dir)
    else:
        cmd_render(cfg, args.clip, args.events, args.out)


if __name__ == "__main__":
    main()
