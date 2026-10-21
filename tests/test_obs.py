import time
from types import SimpleNamespace

from valclip import obs_control


class FakeClient:
    """Mimics OBS writing the replay file a while after the save request."""

    def __init__(self, path, write_delay):
        self.path, self.write_delay, self.saved = path, write_delay, None

    def save_replay_buffer(self):
        self.saved = time.time()

    def get_last_replay_buffer_replay(self):
        if self.saved is None or time.time() - self.saved < self.write_delay:
            return SimpleNamespace(saved_replay_path="old.mkv")
        self.path.write_bytes(b"x" * 100)
        return SimpleNamespace(saved_replay_path=str(self.path))


def test_replay_end_time_is_the_request_time(tmp_path, monkeypatch):
    client = FakeClient(tmp_path / "Replay.mkv", write_delay=0.6)
    monkeypatch.setattr(obs_control.obs, "ReqClient", lambda **_: client)
    before = time.time()
    path, ended_at = obs_control.ObsController("localhost", 4455, "").save_replay()
    assert path == tmp_path / "Replay.mkv"
    assert before <= ended_at <= client.saved  # not the later moment the file finished writing
    assert time.time() - ended_at >= 0.6
