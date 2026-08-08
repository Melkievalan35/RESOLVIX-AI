"""
Priority Prediction Module - Resolvix AI
Combines sentiment, emotion flags, and complaint metadata to assign
a priority score used by the Workflow Agent for routing/escalation.
"""

from ai.sentiment.sentiment_analysis import analyze_sentiment


PRIORITY_WEIGHTS = {
    "sentiment": 0.4,
    "emotion_flags": 0.35,
    "customer_tier": 0.15,
    "complaint_age_hours": 0.10,
}

EMOTION_FLAG_SCORES = {
    "LEGAL_RISK": 1.0,
    "HIGH_ANGER": 0.7,
    "URGENT_LANGUAGE": 0.6,
    "CHURN_RISK": 0.8,
}

CUSTOMER_TIER_SCORES = {
    "platinum": 1.0,
    "gold": 0.7,
    "silver": 0.4,
    "standard": 0.2,
}


def predict_priority(
    complaint_text: str,
    customer_tier: str = "standard",
    complaint_age_hours: float = 0.0,
) -> dict:
    """
    Returns a priority classification for the Workflow/Escalation Agent.

    Output:
        {
            "priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
            "priority_score": 0.0-1.0,
            "reasoning": [...]   # for Explainable AI panel in dashboard
        }
    """
    sentiment_result = analyze_sentiment(complaint_text)
    reasoning = []

    # 1. Sentiment component (negative sentiment → higher urgency)
    sentiment_component = max(0, -sentiment_result["sentiment_score"])
    if sentiment_component > 0.5:
        reasoning.append(f"Strongly negative sentiment detected ({sentiment_result['label']}, "
                          f"confidence {sentiment_result['score']:.2f})")

    # 2. Emotion flags component
    flag_scores = [EMOTION_FLAG_SCORES.get(f, 0) for f in sentiment_result["emotion_flags"]]
    emotion_component = max(flag_scores) if flag_scores else 0.0
    if sentiment_result["emotion_flags"]:
        reasoning.append(f"Emotion flags triggered: {', '.join(sentiment_result['emotion_flags'])}")

    # 3. Customer tier component
    tier_component = CUSTOMER_TIER_SCORES.get(customer_tier.lower(), 0.2)
    if customer_tier.lower() in ("platinum", "gold"):
        reasoning.append(f"High-value customer tier: {customer_tier}")

    # 4. Complaint age component (older unresolved complaints escalate)
    age_component = min(complaint_age_hours / 48.0, 1.0)  # caps at 48h
    if complaint_age_hours > 24:
        reasoning.append(f"Complaint open for {complaint_age_hours:.0f}h — SLA risk")

    priority_score = (
        sentiment_component * PRIORITY_WEIGHTS["sentiment"]
        + emotion_component * PRIORITY_WEIGHTS["emotion_flags"]
        + tier_component * PRIORITY_WEIGHTS["customer_tier"]
        + age_component * PRIORITY_WEIGHTS["complaint_age_hours"]
    )
    priority_score = round(min(priority_score, 1.0), 4)

    if priority_score >= 0.75:
        priority = "CRITICAL"
    elif priority_score >= 0.5:
        priority = "HIGH"
    elif priority_score >= 0.25:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "priority": priority,
        "priority_score": priority_score,
        "sentiment": sentiment_result,
        "reasoning": reasoning if reasoning else ["Standard complaint, no escalation triggers detected"],
    }


if __name__ == "__main__":
    result = predict_priority(
        "This is unacceptable, I have been waiting 3 days and I want a refund now or I'm contacting my lawyer.",
        customer_tier="gold",
        complaint_age_hours=72,
    )
    print(result)
