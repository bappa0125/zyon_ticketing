"""Social data filter — discard low-engagement posts using config thresholds."""
from typing import Any

from app.config import get_config


def filter_low_engagement(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Keep only posts passing engagement thresholds from config/monitoring.yaml.
    Post passes if: likes >= threshold OR retweets >= threshold OR comments >= threshold.
    """
    config = get_config()
    social = config.get("monitoring", {}).get("social_data", {})
    thresholds = social.get("engagement_thresholds", {})
    likes_t = thresholds.get("likes", 2)
    retweets_t = thresholds.get("retweets", 1)
    comments_t = thresholds.get("comments", 1)

    result = []
    for post in posts:
        engagement = post.get("engagement", {})
        if isinstance(engagement, dict):
            likes = engagement.get("likes", 0) or 0
            retweets = engagement.get("retweets", 0) or 0
            comments = engagement.get("comments", 0) or 0
        else:
            likes = retweets = comments = 0

        if likes >= likes_t or retweets >= retweets_t or comments >= comments_t:
            result.append(post)
    return result
