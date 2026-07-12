def event_catalyst_factor(
    grade: str,
    verified: bool,
    independent_sources: int,
    contradiction_penalty: float,
    *,
    days_old: int,
) -> float:
    if not verified or days_old < 0 or days_old > 30:
        return 0.0
    normalized_grade = grade.upper()
    if normalized_grade == "A":
        base = 1.0
    elif normalized_grade == "B":
        base = 0.8
    elif normalized_grade == "C" and independent_sources >= 2:
        base = 0.6
    else:
        return 0.0
    decay = 1.0 - days_old / 30.0
    return max(0.0, base * decay - float(contradiction_penalty))
