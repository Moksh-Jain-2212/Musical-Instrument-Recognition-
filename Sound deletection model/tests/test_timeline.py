import pytest

from app.models.schemas import Event, Window
from app.services.labels import LABEL_MAP, MODEL_LABELS, filter_events
from app.services.timeline_processor import instrument_segments, merge_timeline


def win(start, end, **scores):
    return Window(start=start, end=end, events=[Event(name=n, confidence=s) for n, s in scores.items()])


def test_label_mapping_only_supported():
    assert len(MODEL_LABELS) == 521
    assert set(LABEL_MAP) <= MODEL_LABELS
    assert "Viola" not in LABEL_MAP.values()
    assert LABEL_MAP["Violin, fiddle"] == "Violin"


def test_threshold_multi_label_and_duplicate_aliases():
    predictions = [{"label": "Piano", "score": .91}, {"label": "Drum", "score": .73},
                   {"label": "Drum kit", "score": .80}, {"label": "Singing", "score": .3},
                   {"label": "Cat", "score": .99}, {"label": "Guitar", "score": .29}]
    events = {e.name: e.confidence for e in filter_events(predictions, .3)}
    assert events == {"Piano": .91, "Drums": .80, "Vocals": .3}


def test_merge_matching_sets_only_and_weight_confidence():
    windows = [win(0, 5, Piano=.8), win(5, 7, Piano=.9), win(7, 12, Piano=.9, Drums=.8), win(12, 17, Piano=.7)]
    result = merge_timeline(windows)
    assert [(w.start, w.end) for w in result] == [(0, 7), (7, 12), (12, 17)]
    assert result[0].confidences["Piano"] == pytest.approx((5 * .8 + 2 * .9) / 7, abs=.0001)
    tracks = instrument_segments(windows)
    assert tracks["Piano"][0].start == 0 and tracks["Piano"][0].end == 17
    assert tracks["Drums"][0].start == 7 and tracks["Drums"][0].end == 12


def test_failures_and_empty_chunks_never_infer_silence_or_instrumental():
    windows = [win(0, 5, Piano=.9), Window(start=5, end=10, status="failed"), win(10, 15), win(15, 20, Piano=.9)]
    assert len(merge_timeline(windows)) == 4
    assert len(instrument_segments(windows)["Piano"]) == 2
    assert filter_events([], .3) == []


def test_gaps_and_overlaps_do_not_overmerge():
    assert len(merge_timeline([win(0, 5, Piano=.8), win(6, 10, Piano=.8)])) == 2
    assert len(merge_timeline([win(0, 5, Piano=.8), win(4, 9, Piano=.8)])) == 2


def test_empty_timeline():
    assert merge_timeline([]) == []
    assert instrument_segments([]) == {}
