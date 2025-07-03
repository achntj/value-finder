# scorer.py
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer, util
from datetime import datetime
import json
import re
from config import INTEREST_CONFIG
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = "database.db"
VALUE_THRESHOLD = 0.6  # Threshold for marking content as high-value
LEARNING_RATE = 0.1
NOVELTY_KEYWORDS = ["new", "breakthrough", "first", "novel", "innovative", "revolutionary", "emerging"]
QUALITY_INDICATORS = ["research", "study", "analysis", "framework", "methodology", "evidence", "data"]
JUNK_INDICATORS = ["click", "viral", "trending", "hot", "must-see", "shocking", "you won't believe"]

class ValueScorer:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.conn = sqlite3.connect(DATABASE)
        self.categories = INTEREST_CONFIG["categories"]
        self.source_weights = INTEREST_CONFIG["source_weights"]
        self.category_keys = list(self.categories.keys())
        self.learning_adjustments = self.load_learning_adjustments()

    def load_learning_adjustments(self):
        """Load learning adjustments from user feedback"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT category, learning_adjustment, positive_feedback_count, negative_feedback_count
            FROM interest_profile
        """)
        
        adjustments = {}
        for row in cursor.fetchall():
            category, adj, pos_count, neg_count = row
            adjustments[category] = {
                'adjustment': float(adj or 0),
                'positive_count': int(pos_count or 0),
                'negative_count': int(neg_count or 0)
            }
        
        return adjustments

    def extract_content_features(self, content, title, source):
        """Extract features that indicate content value"""
        if not content:
            return {}
        
        text = (title + " " + content).lower()
        words = text.split()
        
        features = {
            'word_count': len(words),
            'title_length': len(title.split()) if title else 0,
            'has_numbers': bool(re.search(r'\d+', text)),
            'has_technical_terms': sum(1 for term in QUALITY_INDICATORS if term in text),
            'novelty_indicators': sum(1 for term in NOVELTY_KEYWORDS if term in text),
            'junk_indicators': sum(1 for term in JUNK_INDICATORS if term in text),
            'has_links': bool(re.search(r'http[s]?://', content or '')),
            'source_authority': self.source_weights.get(source, 1.0),
            'readability_score': self.calculate_readability(text),
            'content_depth': min(len(words) / 100, 5.0),  # Normalized depth score
        }
        
        return features

    def calculate_readability(self, text):
        """Simple readability score based on sentence and word length"""
        if not text:
            return 0.0
        
        sentences = re.split(r'[.!?]+', text)
        words = text.split()
        
        if len(sentences) == 0 or len(words) == 0:
            return 0.0
        
        avg_sentence_length = len(words) / len(sentences)
        avg_word_length = sum(len(word) for word in words) / len(words)
        
        # Normalize to 0-1 scale, favoring moderate complexity
        readability = 1.0 - abs(avg_sentence_length - 15) / 30
        readability += 1.0 - abs(avg_word_length - 5) / 10
        
        return max(0.0, min(1.0, readability / 2))

    def calculate_value_score(self, features, interest_score):
        """Calculate overall value score based on features"""
        
        # Base score from interest matching
        value_score = interest_score
        
        # Quality indicators boost
        quality_boost = min(features['has_technical_terms'] * 0.1, 0.3)
        value_score += quality_boost
        
        # Novelty indicators boost
        novelty_boost = min(features['novelty_indicators'] * 0.05, 0.2)
        value_score += novelty_boost
        
        # Junk indicators penalty
        junk_penalty = features['junk_indicators'] * 0.1
        value_score -= junk_penalty
        
        # Content depth reward
        depth_reward = min(features['content_depth'] * 0.1, 0.2)
        value_score += depth_reward
        
        # Readability reward
        readability_reward = features['readability_score'] * 0.1
        value_score += readability_reward
        
        # Source authority multiplier
        value_score *= features['source_authority']
        
        # Apply learning adjustments
        learning_adj = self.learning_adjustments.get(features.get('topic', ''), {}).get('adjustment', 0)
        value_score += learning_adj
        
        return max(0.0, min(1.0, value_score))

    def calculate_novelty_score(self, features, content):
        """Calculate novelty score"""
        novelty_score = 0.0
        
        # Recent date mentions
        if re.search(r'202[3-9]|2024|2025', content or ''):
            novelty_score += 0.2
        
        # Novelty keywords
        novelty_score += min(features['novelty_indicators'] * 0.15, 0.5)
        
        # Technical terms suggest new developments
        novelty_score += min(features['has_technical_terms'] * 0.05, 0.3)
        
        return max(0.0, min(1.0, novelty_score))

    def load_interest_embeddings(self):
        """Load interest embeddings with learning adjustments"""
        interest_texts = []
        self.weights = []

        for cat, config in self.categories.items():
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT current_weight FROM interest_profile WHERE category = ?",
                (cat,)
            )
            row = cursor.fetchone()
            base_weight = float(row[0]) if row else float(config["weight"])
            
            # Apply learning adjustments
            learning_data = self.learning_adjustments.get(cat, {})
            adjusted_weight = base_weight + learning_data.get('adjustment', 0)
            
            interest_texts.append(config["name"] + ": " + ", ".join(config["keywords"]))
            self.weights.append(adjusted_weight)

        embeddings = self.model.encode(interest_texts, normalize_embeddings=True)
        return embeddings

    def get_unscored_posts(self):
        """Get posts that need scoring"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, title, content, source 
            FROM posts 
            WHERE value_score IS NULL AND content IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 100
        """)
        return cursor.fetchall()

    def apply_learning_from_feedback(self):
        """Apply learning from user feedback"""
        cursor = self.conn.cursor()
        
        # Process feedback patterns
        cursor.execute("""
            SELECT lf.feedback_type, lf.content_features, lf.source_features, p.topic
            FROM learning_feedback lf
            JOIN posts p ON lf.post_id = p.id
            WHERE lf.timestamp > datetime('now', '-7 days')
        """)
        
        feedback_data = cursor.fetchall()
        adjustments = {cat: {'positive': 0, 'negative': 0} for cat in self.categories}
        
        for feedback_type, content_features, source_features, topic in feedback_data:
            try:
                if topic in adjustments:
                    if feedback_type in ['positive', 'false_negative']:
                        adjustments[topic]['positive'] += 1
                    elif feedback_type in ['negative', 'false_positive']:
                        adjustments[topic]['negative'] += 1
            except Exception as e:
                logger.warning(f"Error processing feedback: {e}")
                continue
        
        # Update interest profile with learning adjustments
        for category, counts in adjustments.items():
            if counts['positive'] > 0 or counts['negative'] > 0:
                net_adjustment = (counts['positive'] - counts['negative']) * LEARNING_RATE
                
                cursor.execute("""
                    UPDATE interest_profile 
                    SET learning_adjustment = learning_adjustment + ?,
                        positive_feedback_count = positive_feedback_count + ?,
                        negative_feedback_count = negative_feedback_count + ?,
                        last_updated = ?
                    WHERE category = ?
                """, (net_adjustment, counts['positive'], counts['negative'], 
                      datetime.now().isoformat(), category))
        
        self.conn.commit()

    def update_source_quality(self):
        """Update source quality based on value ratios"""
        cursor = self.conn.cursor()
        
        # Calculate value ratios for each source
        cursor.execute("""
            SELECT 
                source,
                COUNT(*) AS total_posts,
                SUM(CASE WHEN is_high_value = 1 THEN 1 ELSE 0 END) AS high_value_posts
            FROM posts
            GROUP BY source
        """)
        
        source_stats = cursor.fetchall()
        
        for source, total_posts, high_value_posts in source_stats:
            value_ratio = high_value_posts / total_posts if total_posts > 0 else 0.0
            
            # Calculate quality score
            quality_score = min(1.0, max(0.1, value_ratio * 1.2))
            
            cursor.execute("""
                INSERT OR REPLACE INTO source_penalties 
                (source, penalty_score, value_ratio, total_posts, high_value_posts)
                VALUES (?, ?, ?, ?, ?)
            """, (source, quality_score, value_ratio, total_posts, high_value_posts))
        
        self.conn.commit()

    def score_posts(self):
        """Score all unscored posts"""
        posts = self.get_unscored_posts()
        if not posts:
            logger.info("No unscored posts found")
            return
        
        interest_embeddings = self.load_interest_embeddings()
        
        for post in posts:
            post_id, title, content, source = post
            features = self.extract_content_features(content, title, source)
            
            # Calculate interest score and determine topic
            content_embedding = self.model.encode(content or title, normalize_embeddings=True)
            similarities = util.cos_sim(content_embedding, interest_embeddings)[0].numpy()
            weighted_similarities = similarities * self.weights
            best_index = np.argmax(weighted_similarities)
            interest_score = weighted_similarities[best_index]
            topic = self.category_keys[best_index]
            
            # Calculate value and novelty scores
            value_score = self.calculate_value_score(features, interest_score)
            novelty_score = self.calculate_novelty_score(features, content)
            
            # Mark as high value if above threshold
            is_high_value = 1 if value_score >= VALUE_THRESHOLD else 0
            
            # Update post with scores AND TOPIC
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE posts
                SET value_score = ?,
                    novelty_score = ?,
                    interest_score = ?,
                    is_high_value = ?,
                    topic = ? 
                WHERE id = ?
            """, (value_score, novelty_score, interest_score, is_high_value, topic, post_id))
            
            # Store content features
            cursor.execute("""
                INSERT OR REPLACE INTO content_features 
                (post_id, word_count, readability_score, technical_terms_count, 
                 source_authority, content_depth, uniqueness_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id,
                features.get('word_count', 0),
                features.get('readability_score', 0),
                features.get('has_technical_terms', 0),
                features.get('source_authority', 1.0),
                features.get('content_depth', 0),
                0.0  # Placeholder for uniqueness_score
            ))
        
        self.conn.commit()
        logger.info(f"Scored {len(posts)} posts")

    def run(self):
        logger.info("Starting scoring process")
        
        try:
            # Apply learning from recent feedback
            self.apply_learning_from_feedback()
            
            # Score new posts
            self.score_posts()
            
            # Update source quality metrics
            self.update_source_quality()
            
            logger.info("Scoring completed successfully")
        except Exception as e:
            logger.error(f"Scoring failed: {str(e)}")
            self.conn.rollback()
            raise
        finally:
            self.conn.close()

if __name__ == "__main__":
    scorer = ValueScorer()
    scorer.run()
