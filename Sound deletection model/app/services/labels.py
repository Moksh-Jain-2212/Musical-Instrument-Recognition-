import json
from pathlib import Path

MODEL_LABELS = frozenset(json.loads((Path(__file__).resolve().parents[1] / "models/yamnet_labels.json").read_text()))

# Exact AudioSet names only. Broad categories never imply a specific instrument.
DIRECT_LABELS = """Piano|Electric piano|Guitar|Acoustic guitar|Electric guitar|Bass guitar|Banjo|Sitar|Mandolin|Zither|Ukulele|Organ|Electronic organ|Hammond organ|Synthesizer|Sampler|Harpsichord|Percussion|Drum machine|Snare drum|Bass drum|Timpani|Tabla|Cymbal|Hi-hat|Wood block|Tambourine|Maraca|Gong|Tubular bells|Mallet percussion|Glockenspiel|Vibraphone|Steelpan|Orchestra|Brass instrument|French horn|Trumpet|Trombone|Bowed string instrument|String section|Cello|Double bass|Flute|Saxophone|Clarinet|Harp|Harmonica|Accordion|Bagpipes|Didgeridoo|Shofar|Theremin|Singing bowl|Speech|Music|Silence""".split("|")
LABEL_MAP = {name: name for name in DIRECT_LABELS}
LABEL_MAP.update({
    "Drum": "Drums", "Drum kit": "Drums", "Violin, fiddle": "Violin",
    "Singing": "Vocals", "Choir": "Vocals", "Vocal music": "Vocals",
    "A capella": "Vocals", "Humming": "Humming", "Rapping": "Rapping",
    "Narration, monologue": "Speech", "Conversation": "Speech",
    "Child speech, kid speaking": "Speech", "Keyboard (musical)": "Keyboard",
    "Marimba, xylophone": "Marimba / Xylophone",
    "Steel guitar, slide guitar": "Steel / Slide guitar",
    "Wind instrument, woodwind instrument": "Woodwind instrument",
    "Rattle (instrument)": "Rattle", "Plucked string instrument": "Plucked strings",
    "Musical instrument": "Instrument (unspecified)",
})
assert set(LABEL_MAP) <= MODEL_LABELS


def filter_events(predictions: list[dict], threshold: float):
    from app.models.schemas import Event
    scores: dict[str, float] = {}
    for item in predictions:
        name = LABEL_MAP.get(item["label"])
        score = item["score"]
        if name and score >= threshold:
            scores[name] = max(score, scores.get(name, 0))
    # Keep the underlying Music score in windows. UI shows specific events first.
    return [Event(name=name, confidence=score) for name, score in sorted(scores.items())]
