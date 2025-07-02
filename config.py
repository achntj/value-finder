# config.py
INTEREST_CONFIG = {
    "categories": {
        "ai_tech": {
            "name": "AI + Emerging Tech",
            "keywords": ["GPT", "Claude", "AGI", "alignment", "LLM", "transformer"],
            "sources": ["arxiv", "lobste.rs", "hackernews", "lesswrong"],
            "weight": 1.2,
        },
        "productivity": {
            "name": "Productivity + Systems Thinking",
            "keywords": ["Zettelkasten", "deep work", "time management", "focus"],
            "sources": ["hackernews", "reddit/productivity", "blog"],
            "weight": 1.1,
        },
        "startups": {
            "name": "Startup + Indie Hacking",
            "keywords": ["bootstrapped", "MRR", "SaaS", "founder"],
            "sources": ["indiehackers", "hackernews", "reddit/startups"],
            "weight": 1.0,
        },
        "philosophy": {
            "name": "Philosophy + Mental Clarity",
            "keywords": ["stoicism", "Buddhism", "antifragile", "meditation"],
            "sources": ["hackernews", "reddit/philosophy", "blog"],
            "weight": 0.9,
        },
        "writing": {
            "name": "Writing + Creativity",
            "keywords": ["storytelling", "writing", "creativity"],
            "sources": ["reddit/writing", "blog", "hackernews"],
            "weight": 0.8,
        },
        "markets": {
            "name": "Markets + Macro + Investing",
            "keywords": ["Fed", "macro", "valuation", "risk"],
            "sources": ["reddit/investing", "newsletter", "blog"],
            "weight": 0.7,
        },
        "serendipity": {
            "name": "Wildcards / Serendipity",
            "keywords": [],
            "sources": ["hackernews", "reddit/all", "twitter"],
            "weight": 0.5,
        },
    },
    "source_weights": {
        "hackernews": 1.2,
        "arxiv": 1.3,
        "lesswrong": 1.2,
        "indiehackers": 1.1,
        "reddit": 1.0,
        "blog": 1.0,
        "twitter": 0.8,
        "newsletter": 1.1,
    },
}

FEEDBACK_OPTIONS = {
    "relevance": ["not relevant", "somewhat relevant", "very relevant"],
    "quality": ["low", "medium", "high"],
    "novelty": ["common", "somewhat new", "breakthrough"],
}
