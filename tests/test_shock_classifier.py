from transmission_engine.core.shock_classifier import ShockClassifier


def test_shock_classifier_tariff_keywords():
    classifier = ShockClassifier()
    result = classifier.classify(
        category="C",
        headline="US considers new tariff on EV imports",
        summary="Tariff hike raises input costs",
        severity="E3",
    )
    assert result["event_type_lv2"] == "tariff_shock"
    shock = result["shock_profile"]
    assert "inflationary_shock" in shock["primary"]
    assert result["classification_confidence"] >= 70


def test_shock_classifier_fallback_category():
    classifier = ShockClassifier()
    result = classifier.classify(
        category="E",
        headline="",
        summary="",
        severity="E2",
    )
    assert result["event_type_lv1"] == "monetary_policy"
    assert result["event_type_lv2"] == "rates_down"
    assert result["market_impact_confidence"] >= 50
