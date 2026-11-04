"""Task 1 arm B: frozen hosted general-domain embeddings + logistic regression (no pickle).

Encoder (owner decision 2026-11-03): the Databricks-hosted foundation model endpoint
`databricks-qwen3-embedding-0-6b` (PIN). A hosted encoder has no weight file to hash and cannot be
loaded offline, so the pin is the endpoint name plus the served model version that every response
reports (`model` field). HostedEncoder refuses any response whose version, row count or dimension
differs from PIN, and the build's byte-identical second run is the determinism check. The endpoint
is the only network target and receives award text only (public NIH title/abstract/PHR).

One transform for build and scoring, so every year is featurized identically:
  text = title + abstract + public health relevance (workflow.fingerprint.text_of), sent whole
  (the endpoint takes full abstracts, checked 2026-11-03);
  fixed batches of BATCH in input order; L2 normalization; rounded to ROUND_DECIMALS;
  score = sigmoid(e . coef + intercept).

Trade-off, stated in the artifact: arm B gives up arm A's per-term explanations for semantic
similarity. A dense coefficient vector has no readable terms, so explain() returns the nearest
FY2021 exemplars instead (cosine similarity to labelled FY2021 awards, other cores only).

LocalEncoder / LOCAL_PIN: the vendored, offline, weight-pinned PubMedBERT encoder evaluated first.
It is not used by arm B v1 (about 0.75 awards/s on the 4-CPU build compute, about 23 h per run);
it stays as the documented biomedical alternative (tools/vendor_embed_model.py).
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

PIN = {
    "kind": "databricks-hosted foundation model endpoint",
    "endpoint": "databricks-qwen3-embedding-0-6b",
    "foundation_model": "system.ai.qwen3-embedding-0-6b",
    "served_model_version": "qwen3-embedding-0-6b-112025",
    "dimensions": 1024,
    "domain": "general (not biomedical)",
    "weights_sha256": None,
    "weights_note": "hosted: no weight file is available to hash; pinned by endpoint + served version",
}
ROUND_DECIMALS = 5
BATCH = 16
WORKERS = 4
ENCODING = {"text": "title + abstract + phr (workflow.fingerprint.text_of), not truncated",
            "normalize": "l2", "round_decimals": ROUND_DECIMALS, "dtype": "float32",
            "batching": "fixed batches in input order", "batch": BATCH,
            "exemplar_storage": "float16"}


class HostedEncoder:
    """The pinned hosted endpoint, called through the Databricks SDK."""

    def __init__(self, client=None) -> None:
        if client is None:
            from databricks.sdk import WorkspaceClient

            client = WorkspaceClient()
        self.client = client
        self.calls = 0
        self.versions_seen: set[str] = set()
        self.versions = {"numpy": np.__version__}

    def _batch(self, texts: list[str]) -> np.ndarray:
        path = f"/serving-endpoints/{PIN['endpoint']}/invocations"
        for attempt in range(6):
            try:
                r = self.client.api_client.do("POST", path, body={"input": texts})
                break
            except Exception:  # transient (429 / 5xx); outputs do not depend on retries
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        self.calls += 1
        self.versions_seen.add(str(r.get("model")))
        if r.get("model") != PIN["served_model_version"]:
            raise RuntimeError(f"endpoint served {r.get('model')!r}, pinned "
                               f"{PIN['served_model_version']!r}")
        data = sorted(r["data"], key=lambda d: d["index"])
        if [d["index"] for d in data] != list(range(len(texts))):
            raise RuntimeError("endpoint returned a different number of embeddings")
        e = np.array([d["embedding"] for d in data], dtype=np.float64)
        if e.shape[1] != PIN["dimensions"]:
            raise RuntimeError(f"endpoint returned dimension {e.shape[1]}")
        return e

    def embed(self, texts: list[str], progress=None) -> np.ndarray:
        texts = [t if t.strip() else " " for t in texts]
        starts = list(range(0, len(texts), BATCH))
        out = np.zeros((len(texts), PIN["dimensions"]), dtype=np.float64)
        done = 0
        with ThreadPoolExecutor(WORKERS) as pool:
            for s, e in zip(starts, pool.map(lambda s: self._batch(texts[s:s + BATCH]), starts)):
                out[s:s + len(e)] = e
                done += len(e)
                if progress:
                    progress(done, len(texts))
        return quantize(out)


LOCAL_PIN = {
    "repo": "NeuML/pubmedbert-base-embeddings",
    "revision": "b79526d6ef3645e0df4530322e266f24c829f5ef",
    "weights_file": "model.safetensors",
    "weights_sha256": "929ddc16369bb4ff6f8e92a6ee9f5e0748f2bef33989b5617533dd50beebe4ef",
    "license": "apache-2.0",
    "base": "PubMedBERT (microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext), "
            "sentence-transformers fine-tune by NeuML",
}
#: Files vendored from LOCAL_PIN["revision"] (pytorch_model.bin is not needed: safetensors only).
FILES = (
    "config.json", "model.safetensors", "modules.json", "sentence_bert_config.json",
    "config_sentence_transformers.json", "1_Pooling/config.json", "tokenizer.json",
    "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json", "vocab.txt",
)
MODEL_ROOT = Path(os.environ.get("UAC_NITRD_TASK1_MODEL_ROOT",
                                 "/Volumes/users/conroyri/nitrd_hackathon_v1_raw/models/embed"))
THREADS = 4
#: "cpu" or "cuda" for LocalEncoder.
DEVICE = os.environ.get("UAC_NITRD_TASK1_EMBED_DEVICE", "cpu")
LOCAL_ENCODING = {"text": "title + abstract + phr (workflow.fingerprint.text_of)",
                  "pooling": "mean", "normalize": "l2", "round_decimals": ROUND_DECIMALS,
                  "dtype": "float32", "batching": "token length descending, then input order",
                  "batch": BATCH, "torch_threads": THREADS, "device": DEVICE}


def local_dir() -> Path:
    return MODEL_ROOT / LOCAL_PIN["repo"].replace("/", "__") / LOCAL_PIN["revision"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_vendored() -> dict[str, str]:
    """Check every vendored file against VENDOR.json and the weights against LOCAL_PIN."""
    d = local_dir()
    vendor = json.loads((d / "VENDOR.json").read_text())
    if vendor["repo"] != LOCAL_PIN["repo"] or vendor["revision"] != LOCAL_PIN["revision"]:
        raise RuntimeError("vendored encoder is not the pinned repo/revision")
    got = {f: sha256_file(d / f) for f in FILES}
    if got != vendor["files"]:
        raise RuntimeError("vendored encoder files differ from VENDOR.json")
    if got[LOCAL_PIN["weights_file"]] != LOCAL_PIN["weights_sha256"]:
        raise RuntimeError("vendored weights differ from the pinned SHA-256")
    return got


class LocalEncoder:
    """The vendored PubMedBERT encoder, loaded offline (not used by arm B v1)."""

    def __init__(self) -> None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        self.file_sha256 = verify_vendored()
        if DEVICE == "cuda":
            os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # deterministic cuBLAS
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer

        d = local_dir()
        pooling = json.loads((d / "1_Pooling" / "config.json").read_text())
        if not pooling.get("pooling_mode_mean_tokens"):
            raise RuntimeError("pinned encoder does not use mean pooling")
        self.max_len = int(json.loads((d / "sentence_bert_config.json").read_text())["max_seq_length"])
        torch.set_num_threads(THREADS)
        torch.use_deterministic_algorithms(True)
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(d, local_files_only=True)
        self.model = AutoModel.from_pretrained(d, local_files_only=True).eval().to(DEVICE)
        self.versions = {"torch": torch.__version__, "transformers": transformers.__version__,
                         "numpy": np.__version__,
                         "gpu": torch.cuda.get_device_name(0) if DEVICE == "cuda" else None}

    def embed(self, texts: list[str], progress=None) -> np.ndarray:
        torch = self.torch
        enc = self.tok(list(texts), truncation=True, max_length=self.max_len)
        ids = enc["input_ids"]
        order = sorted(range(len(ids)), key=lambda i: (-len(ids[i]), i))
        out = np.zeros((len(ids), self.model.config.hidden_size), dtype=np.float32)
        pad = self.tok.pad_token_id
        with torch.inference_mode():
            for start in range(0, len(order), BATCH):
                idx = order[start:start + BATCH]
                width = max(len(ids[i]) for i in idx)
                x = torch.full((len(idx), width), pad, dtype=torch.long)
                m = torch.zeros((len(idx), width), dtype=torch.long)
                for r, i in enumerate(idx):
                    x[r, :len(ids[i])] = torch.tensor(ids[i])
                    m[r, :len(ids[i])] = 1
                x, m = x.to(DEVICE), m.to(DEVICE)
                h = self.model(input_ids=x, attention_mask=m).last_hidden_state
                mf = m.unsqueeze(-1).to(h.dtype)
                pooled = (h * mf).sum(1) / mf.sum(1).clamp(min=1e-9)
                out[idx] = pooled.cpu().numpy()
                if progress:
                    progress(min(start + BATCH, len(order)), len(order))
        return quantize(out)


def quantize(e: np.ndarray) -> np.ndarray:
    e = e.astype(np.float64)
    e /= np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-12)
    return np.round(e, ROUND_DECIMALS).astype(np.float32)


def _pack(a: np.ndarray, dtype: str = "<f2") -> dict:
    raw = np.ascontiguousarray(a, dtype=dtype).tobytes()
    return {"shape": list(a.shape), "dtype": dtype, "sha256": hashlib.sha256(raw).hexdigest(),
            "b64": base64.b64encode(raw).decode()}


def _unpack(d: dict) -> np.ndarray:
    raw = base64.b64decode(d["b64"])
    if hashlib.sha256(raw).hexdigest() != d["sha256"]:
        raise ValueError("exemplar block sha256 mismatch")
    return np.frombuffer(raw, dtype=d["dtype"]).reshape(d["shape"]).copy()


class Model:
    """LR coefficients over the pinned embedding, plus the exemplar bank for explanations."""

    def __init__(self, coef, intercept: float, exemplars: dict, meta: dict | None = None,
                 pin: dict | None = None, encoding: dict | None = None):
        self.coef, self.intercept = np.asarray(coef, dtype=np.float64), float(intercept)
        self.exemplars, self.meta = exemplars, meta or {}
        self.pin, self.encoding = pin or PIN, encoding or ENCODING

    def decision(self, e: np.ndarray) -> np.ndarray:
        return e.astype(np.float64) @ self.coef + self.intercept

    def score(self, e: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.decision(e)))

    def explain(self, e: np.ndarray, core: str | None = None, top: int = 5) -> dict:
        """Nearest FY2021 exemplars (cosine) on each side, excluding the award's own core."""
        out = {}
        for side in ("nitrd", "not_nitrd"):
            bank = self.exemplars[side]
            sims = bank["emb"].astype(np.float64) @ e.astype(np.float64)
            ok = np.array([c != core for c in bank["core"]]) if core else np.ones(len(sims), bool)
            idx = [i for i in np.lexsort((bank["appl_id"], -sims)) if ok[i]][:top]
            out[side] = [{"appl_id": int(bank["appl_id"][i]), "core_project_num": bank["core"][i],
                          "cosine": round(float(sims[i]), 4)} for i in idx]
        return out

    def to_bytes(self) -> bytes:
        ex = {side: {"appl_id": [int(a) for a in b["appl_id"]], "core": list(b["core"]),
                     "emb": _pack(b["emb"]), "selection": b["selection"]}
              for side, b in self.exemplars.items()}
        body = {"meta": self.meta, "embedding_pin": self.pin, "encoding": self.encoding,
                "coef": [round(float(v), 9) for v in self.coef], "intercept": round(self.intercept, 9),
                "exemplars": ex}
        return gzip.compress(json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), mtime=0)

    @classmethod
    def from_bytes(cls, data: bytes) -> Model:
        b = json.loads(gzip.decompress(data))
        if b["embedding_pin"] != PIN or b["encoding"] != ENCODING:
            raise ValueError("model embedding pin or encoding differs from this code's PIN / ENCODING")
        ex = {side: {"appl_id": np.asarray(v["appl_id"], dtype=np.int64), "core": v["core"],
                     "emb": _unpack(v["emb"]), "selection": v["selection"]}
              for side, v in b["exemplars"].items()}
        return cls(b["coef"], b["intercept"], ex, b["meta"], b["embedding_pin"], b["encoding"])
