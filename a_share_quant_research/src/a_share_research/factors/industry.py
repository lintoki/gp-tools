def industry_prosperity_factor(relative_return_60d: float, fundamental_breadth: float) -> float:
    return 0.6 * float(relative_return_60d) + 0.4 * float(fundamental_breadth)
