"""Controls the OBS replay buffer over obs-websocket (OBS 28+ has it built in)."""

import time
from pathlib import Path

import obsws_python as obs


class ObsController:
    def __init__(self, host: str, port: int, password: str) -> None:
        self._client = obs.ReqClient(host=host, port=port, password=password, timeout=5)

    def ensure_replay_buffer(self) -> None:
        if not self._client.get_replay_buffer_status().output_active:
            self._client.start_replay_buffer()

    def _last_replay(self) -> str | None:
        try:
            return self._client.get_last_replay_buffer_replay().saved_replay_path
        except obs.error.OBSSDKRequestError:
            return None  # nothing saved yet this session

    def save_replay(self, timeout: float = 15.0) -> Path:
        """Saves the replay buffer and waits until OBS has finished writing the file."""
        previous = self._last_replay()
        self._client.save_replay_buffer()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            path = self._last_replay()
            if path and path != previous and _is_stable(Path(path)):
                return Path(path)
            time.sleep(0.2)
        raise TimeoutError("OBS did not finish saving the replay in time")


def _is_stable(path: Path) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    time.sleep(0.2)
    return size > 0 and path.stat().st_size == size
