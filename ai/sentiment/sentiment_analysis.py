"""
Sentiment Analysis Module - Resolvix AI
Analyzes customer complaint text to detect emotional tone.
Used by: Customer Agent, Escalation Agent, Priority Prediction
"""

from transformers import pipeline
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# Model choice: distilbert fine-tuned on SST-2 is fast (~250MB) and good enough
# for hackathon demo latency. Swap for "cardiffnlp/twitter-roberta-base-sentiment"
# if you want more nuanced (negative/neutral/positive) 3-class output.
MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"


class SentimentAnalyzer:
    def __init__(self, model_name: str = MODEL_NAME):
        try:
            self.pipe = pipeline(
                "sentiment-analysis",
                model=model_name,
                truncation=True,
                max_length=512,
            )
            self.available = True
        except Exception as e:
            logger.error(f"Failed to load sentiment model: {e}")
            self.available = False

    def analyze(self, text: str) -> dict:
        """
        Returns:
            {
                "label": "NEGATIVE" | "POSITIVE",
                "score": 0.0-1.0,          # confidence
                "sentiment_score": -1.0-1.0,  # normalized, negative = angry customer
                "emotion_flags": [...]      # rule-based add-ons for explainability
            }
        """
        if not text or not text.strip():
            return self._empty_result()

        if not self.available:
            return self._fallback(text)

        try:
            result = self.pipe(text[:512])[0]
            label = result["label"]
            score = float(result["score"])

            # Normalize to -1 (very negative) .. +1 (very positive)
            sentiment_score = score if label == "POSITIVE" else -score

            return {
                "label": label,
                "score": round(score, 4),
                "sentiment_score": round(sentiment_score, 4),
                "emotion_flags": self._detect_emotion_flags(text),
            }
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return self._fallback(text)

    def _detect_emotion_flags(self, text: str) -> list:
        """Lightweight rule-based flags for explainability (judges love this)."""
        text_lower = text.lower()
        flags = []

        anger_words = ["furious", "angry", "unacceptable", "worst", "scam", "fraud", "disgusted"]
        urgency_words = ["immediately", "urgent", "asap", "now", "emergency"]
        legal_words = ["lawyer", "legal action", "sue", "court", "consumer forum"]
        threat_words = ["cancel", "never buy", "switch to", "social media", "review"]

        if any(w in text_lower for w in anger_words):
            flags.append("HIGH_ANGER")
        if any(w in text_lower for w in urgency_words):
            flags.append("URGENT_LANGUAGE")
        if any(w in text_lower for w in legal_words):
            flags.append("LEGAL_RISK")
        if any(w in text_lower for w in threat_words):
            flags.append("CHURN_RISK")

        return flags

    def _fallback(self, text: str) -> dict:
        """Rule-based fallback if model fails to load (keeps demo alive)."""
        negative_words = ["bad", "worst", "angry", "terrible", "refund", "broken", "disappointed"]
        text_lower = text.lower()
        neg_count = sum(1 for w in negative_words if w in text_lower)

        label = "NEGATIVE" if neg_count > 0 else "POSITIVE"
        score = min(0.6 + neg_count * 0.1, 0.95)

        return {
            "label": label,
            "score": round(score, 4),
            "sentiment_score": round(score if label == "POSITIVE" else -score, 4),
            "emotion_flags": self._detect_emotion_flags(text),
            "fallback_mode": True,
        }

    def _empty_result(self) -> dict:
        return {
            "label": "NEUTRAL",
            "score": 0.0,
            "sentiment_score": 0.0,
            "emotion_flags": [],
        }


# Singleton pattern — load model once, reuse across requests
@lru_cache(maxsize=1)
def get_sentiment_analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()


def analyze_sentiment(text: str) -> dict:
    """Convenience function for direct import into agents/services."""
    analyzer = get_sentiment_analyzer()
    return analyzer.analyze(text)


if __name__ == "__main__":
    # Quick test
    samples = [
        "This is the worst product I have ever bought, I want a refund immediately!",
        "Thank you so much, the support team resolved my issue quickly.",
        "I am considering legal action if this is not fixed within 24 hours.",
    ]
    for s in samples:
        print(s, "→", analyze_sentiment(s))
