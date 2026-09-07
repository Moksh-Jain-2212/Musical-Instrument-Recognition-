import pytest

from app.models.schemas import InstrumentPrediction, InstrumentWindow
from app.services.labels import INSTRUMENT_LABEL_MAP, MODEL_LABELS, filter_instruments
from app.services.timeline_processor import instrument_segments, merge_timeline


def win(start, end, **scores):
    return InstrumentWindow(start=start, end=end, instruments=[InstrumentPrediction(name=n, confidence=s) for n, s in scores.items()])


def test_label_mapping_only_supported():
    assert len(MODEL_LABELS) == 521
    assert set(INSTRUMENT_LABEL_MAP) <= MODEL_LABELS
    assert "Viola" not in INSTRUMENT_LABEL_MAP.values()
    assert INSTRUMENT_LABEL_MAP["Violin, fiddle"] == "Violin"


def test_threshold_multi_label_and_duplicate_aliases():
    predictions = [{"label": "Piano", "score": .91}, {"label": "Drum", "score": .73},
                   {"label": "Drum kit", "score": .80}, {"label": "Singing", "score": .3},
                   {"label": "Cat", "score": .99}, {"label": "Guitar", "score": .29}]
    events = {e.name: e.confidence for e in filter_instruments(predictions, .3)}
    assert events == {"Piano": .91, "Drums": .80}


def test_merge_matching_sets_only_and_weight_confidence():
    windows = [win(0, 5, Piano=.8), win(5, 7, Piano=.9), win(7, 12, Piano=.9, Drums=.8), win(12, 17, Piano=.7)]
    result = merge_timeline(windows)
    assert [(w.start, w.end) for w in result] == [(0, 7), (7, 12), (12, 17)]
    assert result[0].instruments[0].confidence == pytest.approx((5 * .8 + 2 * .9) / 7, abs=.0001)
    tracks = instrument_segments(windows)
    assert tracks["Piano"][0].start == 0 and tracks["Piano"][0].end == 17
    assert tracks["Drums"][0].start == 7 and tracks["Drums"][0].end == 12


def test_failures_and_empty_chunks_never_infer_silence_or_instrumental():
    windows = [win(0, 5, Piano=.9), InstrumentWindow(start=5, end=10, status="failed"), win(10, 15), win(15, 20, Piano=.9)]
    assert len(merge_timeline(windows)) == 4
    assert len(instrument_segments(windows)["Piano"]) == 2
    assert filter_instruments([], .3) == []


def test_gaps_and_overlaps_do_not_overmerge():
    assert len(merge_timeline([win(0, 5, Piano=.8), win(6, 10, Piano=.8)])) == 2
    assert len(merge_timeline([win(0, 5, Piano=.8), win(4, 9, Piano=.8)])) == 2


def test_empty_timeline():
    assert merge_timeline([]) == []
    assert instrument_segments([]) == {}


@pytest.mark.parametrize("label", ["Speech", "Conversation", "Singing", "Vocal music", "Choir", "Humming", "Rapping",
    "Music", "Song", "Background music", "Pop music", "Rock music", "Jazz", "Classical music", "Silence", "Noise",
    "Orchestra", "Musical instrument", "Drum and bass", "Cat", "Car", "Rain"])
def test_non_instruments_never_become_instruments(label):
    assert filter_instruments([{"label": label, "score": 1}], .3) == []


@pytest.mark.parametrize("label,name", [("Drum", "Drums"), ("Drum kit", "Drums"), ("Violin, fiddle", "Violin"),
    ("Keyboard (musical)", "Keyboard"), ("Bass guitar", "Bass Guitar"), ("Marimba, xylophone", "Marimba / Xylophone")])
def test_instrument_aliases(label, name):
    assert filter_instruments([{"label": label, "score": .88}], .3)[0].name == name


def test_multiple_instruments_and_mixed_general_predictions():
    predictions = [{"label": "Music", "score": .98}, {"label": "Speech", "score": .90},
        {"label": "Piano", "score": .88}, {"label": "Drum", "score": .82},
        {"label": "Bass guitar", "score": .76}, {"label": "Rock music", "score": .8}]
    assert {p.name for p in filter_instruments(predictions, .3)} == {"Piano", "Drums", "Bass Guitar"}


def test_independent_tracks_when_instrument_sets_change():
    windows = [win(0, 5, Piano=.8), win(5, 10, Piano=.9, Drums=.7), win(10, 15, Drums=.9)]
    assert len(merge_timeline(windows)) == 3
    tracks = instrument_segments(windows)
    assert (tracks["Piano"][0].start, tracks["Piano"][0].end) == (0, 10)
    assert (tracks["Drums"][0].start, tracks["Drums"][0].end) == (5, 15)
