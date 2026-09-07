import json
from pathlib import Path

MODEL_LABELS = frozenset(json.loads((Path(__file__).resolve().parents[1] / "models/yamnet_labels.json").read_text()))

# Exact AudioSet names only. Broad categories never imply a specific instrument.
DIRECT_LABELS = """Piano|Electric piano|Guitar|Acoustic guitar|Electric guitar|Bass guitar|Banjo|Sitar|Mandolin|Zither|Ukulele|Organ|Electronic organ|Hammond organ|Synthesizer|Sampler|Harpsichord|Percussion|Drum machine|Snare drum|Bass drum|Timpani|Tabla|Cymbal|Hi-hat|Wood block|Tambourine|Maraca|Gong|Tubular bells|Mallet percussion|Glockenspiel|Vibraphone|Steelpan|Brass instrument|French horn|Trumpet|Trombone|Bowed string instrument|String section|Cello|Double bass|Flute|Saxophone|Clarinet|Harp|Harmonica|Accordion|Bagpipes|Didgeridoo|Shofar|Theremin|Singing bowl""".split("|")
INSTRUMENT_LABEL_MAP = {name: name.title() for name in DIRECT_LABELS}
INSTRUMENT_LABEL_MAP.update({
    "Drum": "Drums", "Drum kit": "Drums", "Violin, fiddle": "Violin",
    "Keyboard (musical)": "Keyboard",
    "Marimba, xylophone": "Marimba / Xylophone",
    "Steel guitar, slide guitar": "Steel / Slide Guitar",
    "Wind instrument, woodwind instrument": "Woodwind Instrument",
    "Rattle (instrument)": "Rattle", "Plucked string instrument": "Plucked Strings",
})
if not set(INSTRUMENT_LABEL_MAP) <= MODEL_LABELS:
    raise RuntimeError("Instrument allowlist contains unsupported YAMNet labels")

SUPPORTED_INSTRUMENTS = tuple(sorted(set(INSTRUMENT_LABEL_MAP.values())))
# Gemini is a generative model, not an AudioSet classifier. This is our output
# vocabulary constraint, not a claim that it has a trained fixed-label head.
GEMINI_INSTRUMENTS = tuple(sorted(set(SUPPORTED_INSTRUMENTS) | {"Strings", "Woodwinds", "Brass"}))
GEMINI_LABEL_MAP = {name.casefold(): name for name in GEMINI_INSTRUMENTS}
GEMINI_LABEL_MAP.update({name.casefold(): normalized for name, normalized in INSTRUMENT_LABEL_MAP.items()})


def filter_instruments(predictions: list[dict], threshold: float):
    from app.models.schemas import InstrumentPrediction
    scores: dict[str, float] = {}
    for item in predictions:
        name = INSTRUMENT_LABEL_MAP.get(item["label"])
        score = item["score"]
        if name and score >= threshold:
            scores[name] = max(score, scores.get(name, 0))
    return [InstrumentPrediction(name=name, confidence=score) for name, score in sorted(scores.items())]
