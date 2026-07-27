import pytest

from split_peel.characters import character_ids, instructions_for_speaker, load_characters, voice_for_speaker, voice_speed_for_speaker


def test_load_characters_returns_defaults_for_missing_file(tmp_path):
    characters = load_characters(tmp_path / "missing.json")

    assert character_ids(characters) == ["split", "peel"]
    assert voice_for_speaker(characters, "split", "openai", "fallback") == "ash"
    assert characters["characters"][0]["appearance"]["baseOutfit"]["5"] == "eyeliner"
    assert characters["characters"][0]["appearance"]["baseOutfit"]["7"] == "gapteeth"
    assert characters["characters"][0]["appearance"]["baseOutfit"]["9"] == "sweatsuit"
    assert characters["characters"][0]["appearance"]["baseOutfit"]["12"] == "dorthy-hair"
    assert characters["characters"][1]["appearance"]["baseOutfit"]["6"] == "proff-glasses"
    assert characters["characters"][1]["appearance"]["baseOutfit"]["11"] == "zucco-tshirt"
    instructions = instructions_for_speaker(characters, "split", "fallback")
    assert "female cartoon banana lead-host voice" in instructions
    assert "whip-smart younger female lead host" in instructions
    assert "keeps Peel" in instructions
    peel_instructions = instructions_for_speaker(characters, "peel", "fallback")
    assert "old-school cartoon banana co-host" in peel_instructions
    assert "walks into double entendres" in peel_instructions


def test_voice_speed_for_speaker_reads_and_clamps_provider_speed():
    characters = {
        "characters": [
            {"id": "split", "voice": {"openaiSpeed": 1.25}},
            {"id": "peel", "voice": {"openaiSpeed": 8}},
        ]
    }

    assert voice_speed_for_speaker(characters, "split", "openai") == 1.25
    assert voice_speed_for_speaker(characters, "peel", "openai") == 4.0
    assert voice_speed_for_speaker(characters, "missing", "openai", 1.1) == 1.1


def test_voice_speed_for_speaker_rejects_invalid_speed():
    characters = {"characters": [{"id": "split", "voice": {"openaiSpeed": "fast"}}]}

    with pytest.raises(ValueError):
        voice_speed_for_speaker(characters, "split", "openai")
