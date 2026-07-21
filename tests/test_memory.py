from split_peel.memory import load_episode_memory, save_episode_memory


def test_save_and_load_episode_memory(tmp_path):
    script = {
        "title": "Test Episode",
        "match": {"shortName": "ARS @ COV"},
        "beats": ["Beat one"],
        "sourceCasts": [{"username": "fan"}],
        "fallbackCasts": [{}, {}],
        "dialogue": [{"speaker": "split", "line": "hello", "tone": "dry"}],
    }

    path = save_episode_memory(script, tmp_path)
    loaded = load_episode_memory(tmp_path)

    assert path.exists()
    assert loaded[0]["title"] == "Test Episode"
    assert loaded[0]["sourceCastUsers"] == ["fan"]
    assert loaded[0]["fallbackCastCount"] == 2
