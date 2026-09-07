from app.models.schemas import InstrumentPrediction, InstrumentSegment, InstrumentWindow, TimelineEntry


def merge_timeline(windows: list[InstrumentWindow]) -> list[TimelineEntry]:
    """Merge identical instrument sets with the same status and contiguous times."""
    groups: list[list[InstrumentWindow]] = []
    for window in windows:
        names = {e.name for e in window.instruments}
        previous = groups[-1][-1] if groups else None
        if previous and abs(previous.end - window.start) < 1e-6 and previous.status == window.status and names == {e.name for e in previous.instruments}:
            groups[-1].append(window)
        else:
            groups.append([window])
    merged = []
    for group in groups:
        duration = sum(w.end - w.start for w in group)
        totals: dict[str, float] = {}
        for w in group:
            for event in w.instruments:
                totals[event.name] = totals.get(event.name, 0) + event.confidence * (w.end - w.start)
        merged.append(TimelineEntry(start=group[0].start, end=group[-1].end,
                                   instruments=[InstrumentPrediction(name=n, confidence=round(totals[n] / duration, 4)) for n in sorted(totals)],
                                   status=group[0].status))
    return merged


def instrument_segments(windows: list[InstrumentWindow]) -> dict[str, list[InstrumentSegment]]:
    result: dict[str, list[InstrumentSegment]] = {}
    for window in windows:
        for event in window.instruments:
            segments = result.setdefault(event.name, [])
            if segments and abs(segments[-1].end - window.start) < 1e-6:
                previous = segments[-1]
                old_duration = previous.end - previous.start
                new_duration = window.end - window.start
                previous.average_confidence = (previous.average_confidence * old_duration + event.confidence * new_duration) / (old_duration + new_duration)
                previous.end = window.end
            else:
                segments.append(InstrumentSegment(start=window.start, end=window.end, average_confidence=event.confidence))
    return result
