from app.models.schemas import Segment, TimelineEntry, Window


def merge_timeline(windows: list[Window]) -> list[TimelineEntry]:
    """Merge only identical event sets with the same status and contiguous times."""
    groups: list[list[Window]] = []
    for window in windows:
        names = {e.name for e in window.events}
        previous = groups[-1][-1] if groups else None
        if previous and abs(previous.end - window.start) < 1e-6 and previous.status == window.status and names == {e.name for e in previous.events}:
            groups[-1].append(window)
        else:
            groups.append([window])
    merged = []
    for group in groups:
        duration = sum(w.end - w.start for w in group)
        totals: dict[str, float] = {}
        for w in group:
            for event in w.events:
                totals[event.name] = totals.get(event.name, 0) + event.confidence * (w.end - w.start)
        merged.append(TimelineEntry(start=group[0].start, end=group[-1].end,
                                   events=sorted(totals), confidences={n: round(s / duration, 4) for n, s in totals.items()},
                                   status=group[0].status))
    return merged


def instrument_segments(windows: list[Window]) -> dict[str, list[Segment]]:
    result: dict[str, list[Segment]] = {}
    for window in windows:
        for event in window.events:
            segments = result.setdefault(event.name, [])
            if segments and abs(segments[-1].end - window.start) < 1e-6:
                previous = segments[-1]
                old_duration = previous.end - previous.start
                new_duration = window.end - window.start
                previous.average_confidence = (previous.average_confidence * old_duration + event.confidence * new_duration) / (old_duration + new_duration)
                previous.end = window.end
            else:
                segments.append(Segment(start=window.start, end=window.end, average_confidence=event.confidence))
    return result
