def split_segments(segments: list[dict], max_duration: float) -> list[tuple[float, float, list[dict]]]:
    """Group whisper segments into parts that each fit within max_duration."""
    if not segments:
        return []

    parts: list[tuple[float, float, list[dict]]] = []
    current_segments: list[dict] = []
    part_start = float(segments[0]["start"])

    for segment in segments:
        if current_segments and float(segment["end"]) - part_start > max_duration:
            part_end = float(current_segments[-1]["end"])
            parts.append((part_start, part_end, current_segments))
            current_segments = [segment]
            part_start = float(segment["start"])
        else:
            if not current_segments:
                part_start = float(segment["start"])
            current_segments.append(segment)

    if current_segments:
        parts.append((part_start, float(current_segments[-1]["end"]), current_segments))

    return parts
