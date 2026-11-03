"""Task 1 fingerprint v1: TF-IDF + logistic regression, stored as plain arrays (no pickle).

One transform for build, forecast and scoring, so every year is featurized identically:
  text = title + abstract + public health relevance;
  counts over the frozen vocabulary (unigrams + bigrams, lowercase, English stop words removed);
  sublinear tf (1 + log tf) x frozen IDF, then L2 normalization;
  score = sigmoid(x . coef + intercept).
explain() returns the per-term contributions (tf-idf weight x coefficient), for classifier_explain.
"""

from __future__ import annotations

import gzip
import json

import numpy as np

VECTORIZER = {"ngram_range": [1, 2], "lowercase": True, "stop_words": "english",
              "token_pattern": r"(?u)\b[a-zA-Z][a-zA-Z0-9]+\b", "sublinear_tf": True, "norm": "l2",
              "smooth_idf": True}


def text_of(rec: dict) -> str:
    return "\n".join(rec.get(k) or "" for k in ("title", "abstract", "phr"))


def count_vectorizer(vocabulary=None, min_df=1):
    from sklearn.feature_extraction.text import CountVectorizer
    return CountVectorizer(ngram_range=tuple(VECTORIZER["ngram_range"]), lowercase=True,
                           stop_words=VECTORIZER["stop_words"], token_pattern=VECTORIZER["token_pattern"],
                           vocabulary=vocabulary, min_df=min_df, dtype=np.float32)


def smooth_idf(df: np.ndarray, n_docs: int) -> np.ndarray:
    return (np.log((1.0 + n_docs) / (1.0 + df)) + 1.0).astype(np.float32)


def tfidf(counts, idf: np.ndarray):
    from sklearn.preprocessing import normalize
    x = counts.tocsr().astype(np.float32, copy=True)
    x.data = 1.0 + np.log(x.data)
    x = x.multiply(idf).tocsr()
    return normalize(x, norm="l2", copy=False)


class Model:
    def __init__(self, vocab: list[str], idf, coef, intercept: float, meta: dict | None = None):
        self.vocab, self.idf = list(vocab), np.asarray(idf, dtype=np.float32)
        self.coef, self.intercept, self.meta = np.asarray(coef, dtype=np.float64), float(intercept), meta or {}
        self._cv = None

    def transform(self, texts):
        if self._cv is None:
            self._cv = count_vectorizer(vocabulary={t: i for i, t in enumerate(self.vocab)})
        return tfidf(self._cv.transform(texts), self.idf)

    def decision(self, x) -> np.ndarray:
        return np.asarray(x @ self.coef).ravel() + self.intercept

    def score(self, x) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.decision(x)))

    def explain(self, text: str, top: int = 10) -> list[tuple[str, float]]:
        row = self.transform([text]).tocoo()
        contrib = sorted(((self.vocab[j], float(v * self.coef[j])) for j, v in zip(row.col, row.data)),
                         key=lambda t: -abs(t[1]))
        return contrib[:top]

    def to_bytes(self) -> bytes:
        body = {"meta": self.meta, "vectorizer": VECTORIZER, "vocab": self.vocab,
                "idf": [round(float(v), 7) for v in self.idf], "coef": [round(float(v), 9) for v in self.coef],
                "intercept": round(self.intercept, 9)}
        return gzip.compress(json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), mtime=0)

    @classmethod
    def from_bytes(cls, data: bytes) -> Model:
        b = json.loads(gzip.decompress(data))
        if b["vectorizer"] != VECTORIZER:
            raise ValueError("model vectorizer settings differ from this code's VECTORIZER")
        return cls(b["vocab"], b["idf"], b["coef"], b["intercept"], b["meta"])


def rank(scores: np.ndarray, appl_ids: np.ndarray) -> np.ndarray:
    """Indices in shortlist order: score descending, ties by appl_id ascending."""
    return np.lexsort((appl_ids, -scores))


def shortlist_size(fraction: float, n_universe: int) -> int:
    return int(np.ceil(fraction * n_universe))
