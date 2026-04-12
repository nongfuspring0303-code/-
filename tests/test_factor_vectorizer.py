from transmission_engine.core.factor_vectorizer import FactorVectorizer


def test_factor_vectorizer_tariff_shape_and_range():
    vectorizer = FactorVectorizer()
    result = vectorizer.vectorize(
        event_type_lv2="tariff_shock",
        severity="E3",
        lifecycle_state="Active",
        novelty_score=1.0,
        fatigue_final=0.0,
    )
    assert len(result) == 9
    for value in result.values():
        assert -100.0 <= value <= 100.0
        assert round(value, 2) == value


def test_factor_vectorizer_severity_monotonicity():
    vectorizer = FactorVectorizer()
    low = vectorizer.vectorize("tariff_shock", severity="E1", lifecycle_state="Active")
    high = vectorizer.vectorize("tariff_shock", severity="E4", lifecycle_state="Active")
    assert abs(high["inflation"]) > abs(low["inflation"])
