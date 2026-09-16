"""Download pinned public models for the offline synthetic experiment."""

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

DENSE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DENSE_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
RERANKER = "BAAI/bge-reranker-v2-m3"
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reranker-path", type=Path, required=True)
    args = parser.parse_args()
    snapshot_download(
        DENSE, revision=DENSE_REVISION, allow_patterns=["*.json", "*.txt", "*.model", "model.safetensors"]
    )
    path = args.reranker_path.resolve()
    snapshot_download(
        RERANKER,
        revision=RERANKER_REVISION,
        local_dir=path,
        allow_patterns=[
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "sentencepiece.bpe.model",
            "model.safetensors",
        ],
    )
    (path / "evaluation-manifest.json").write_text(
        json.dumps({"repo": RERANKER, "revision": RERANKER_REVISION}, indent=2)
    )


if __name__ == "__main__":
    main()
