"""
FinBERT sentiment scoring for news headlines.
Uses HuggingFace transformers — model loads once at startup.
"""
import logging
from typing import List, Dict
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_finbert():
    """Load FinBERT model once and cache it."""
    try:
        from transformers import pipeline
        logger.info("Loading FinBERT model...")
        classifier = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            return_all_scores=False,
            device=-1,  # CPU; set to 0 for GPU
        )
        logger.info("FinBERT loaded.")
        return classifier
    except Exception as e:
        logger.error(f"Failed to load FinBERT: {e}")
        return None


def score_headlines(news_items: List[Dict]) -> List[Dict]:
    """
    Score a list of news items with FinBERT.
    Adds finbert_label and finbert_score to each item.
    Falls back to neutral if model unavailable.
    """
    classifier = load_finbert()

    headlines = [item.get("headline", "")[:512] for item in news_items]

    if classifier is None or not headlines:
        for item in news_items:
            item["finbert_label"] = "neutral"
            item["finbert_score"] = 0.5
        return news_items

    try:
        # Batch inference
        results = classifier(headlines, batch_size=16, truncation=True)
        for item, result in zip(news_items, results):
            item["finbert_label"] = result["label"].lower()   # positive/negative/neutral
            item["finbert_score"] = round(result["score"], 4)
    except Exception as e:
        logger.error(f"FinBERT inference error: {e}")
        for item in news_items:
            item["finbert_label"] = "neutral"
            item["finbert_score"] = 0.5

    return news_items
