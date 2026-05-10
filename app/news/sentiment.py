from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def classify_sentiment(text: str) -> tuple[str, float]:
    """
    Returns (label, compound_score)
    Labels: BULLISH, BEARISH, NEUTRAL
    Thresholds: compound > 0.05 = BULLISH, < -0.05 = BEARISH
    """
    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound > 0.05:
        return "BULLISH", compound
    elif compound < -0.05:
        return "BEARISH", compound
    else:
        return "NEUTRAL", compound


def get_symbol_sentiment(symbol: str, articles: list[dict]) -> str | None:
    """
    Get the dominant sentiment for a symbol from a list of news articles.
    Returns 'BULLISH', 'BEARISH', or None if insufficient data.
    """
    relevant = [a for a in articles if a.get("symbol") == symbol]
    if not relevant:
        return None

    scores = [a["score"] for a in relevant]
    avg = sum(scores) / len(scores)

    if avg > 0.05:
        return "BULLISH"
    elif avg < -0.05:
        return "BEARISH"
    return "NEUTRAL"
