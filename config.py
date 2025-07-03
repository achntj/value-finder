INTEREST_CONFIG = {
    "categories": {
        "ai_tech": {
            "name": "AI + Emerging Tech",
            "keywords": ["GPT", "Claude", "AGI", "alignment", "LLM", "transformer"],
            "sources": ["arxiv", "lobste.rs", "hackernews", "lesswrong"],
            "weight": 1.2,
            "boost": 1.1  # 10% boost for AI content
        },
        "productivity": {
            "name": "Productivity + Systems Thinking",
            "keywords": ["Zettelkasten", "deep work", "time management", "focus"],
            "sources": ["hackernews", "reddit/productivity", "blog"],
            "weight": 1.1,
            "boost": 1.0
        },
        "startups": {
            "name": "Startup",
            "keywords": ["bootstrapped", "MRR", "SaaS", "founder"],
            "sources": ["hackernews", "reddit/startups"],
            "weight": 1.0,
            "boost": 1.0
        },
        "philosophy": {
            "name": "Philosophy + Mental Clarity",
            "keywords": ["stoicism", "Buddhism", "antifragile", "meditation"],
            "sources": ["hackernews", "reddit/philosophy", "blog"],
            "weight": 0.9,
            "boost": 1.0
        },
        "writing": {
            "name": "Writing + Creativity",
            "keywords": ["storytelling", "writing", "creativity"],
            "sources": ["reddit/writing", "blog", "hackernews"],
            "weight": 0.8,
            "boost": 1.0
        },
        "markets": {
            "name": "Markets + Macro + Investing",
            "keywords": ["Fed", "macro", "valuation", "risk"],
            "sources": ["reddit/investing", "newsletter", "blog"],
            "weight": 0.7,
            "boost": 1.0
        },
        "serendipity": {
            "name": "Wildcards / Serendipity",
            "keywords": [],
            "sources": ["hackernews", "reddit/all", "twitter"],
            "weight": 0.5,
            "boost": 0.9  # Slightly penalize serendipity content
        },
    },
    "source_weights": {
        "hackernews": 1.2,
        "arxiv": 1.3,
        "lesswrong": 1.2,
        "reddit": 1.0,
        "blog": 1.0,
        "twitter": 0.8,
        "newsletter": 1.1,
    },
}
