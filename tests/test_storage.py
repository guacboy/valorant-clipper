from valclip.storage import clear_game, montage_path, store_replay


def test_store_then_clear_only_touches_app_files(tmp_path):
    footage, output = tmp_path / "footage", tmp_path / "output"
    footage.mkdir()
    (output / "scan").mkdir(parents=True)
    (footage / "test.mkv").write_bytes(b"keep me")
    (output / "scan" / "round_01.json").write_text("{}")
    saved = tmp_path / "Replay 2026-10-20 18-30-01.mkv"
    saved.write_bytes(b"round")

    stored = store_replay(saved, footage)
    assert stored.parent == footage and stored.name.startswith("replay_") and stored.suffix == ".mkv"
    assert not saved.exists()
    montage = montage_path(output)
    montage.write_bytes(b"video")

    assert clear_game(footage, output) == (1, 1)
    assert not stored.exists() and not montage.exists()
    assert (footage / "test.mkv").read_bytes() == b"keep me"
    assert (output / "scan" / "round_01.json").exists()


def test_clear_on_missing_folders(tmp_path):
    assert clear_game(tmp_path / "a", tmp_path / "b") == (0, 0)
