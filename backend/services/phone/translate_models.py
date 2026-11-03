"""The translation models Loupe uses, pinned, and the one-time install of their files (05 section 17.5).

Each language pair is one MarianMT model from the OPUS-MT project, at a pinned revision of its Hugging Face
repository, with the SHA-256 of its weights file. The licence check was made at build: the model cards say
``license: apache-2.0`` and the upstream OPUS-MT weights are released under CC-BY 4.0; both allow commercial use.
Model families published under a non-commercial licence (for example NLLB-200 and M2M-100 variants under
CC-BY-NC) are excluded, because Loupe is used commercially.

Model files are never fetched while evidence is translated. An operator runs this module once on the server:

    cd backend && python -m services.phone.translate_models            # every pair
    cd backend && python -m services.phone.translate_models es         # one pair

It writes each pair to ``$LOUPE_TRANSLATION_MODEL_DIR/<folder>`` (default ``~/.cache/loupe-mt``), checks the
weights against the pinned hash before the folder is put in place, and writes ``loupe-model.json`` beside the
files naming the repository, revision and licences. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

LICENCE_WORDS = ("Model card licence: apache-2.0. Upstream OPUS-MT weights: CC-BY 4.0. Both allow commercial use.")

# iso 639-1 code of the source language -> the pinned model that translates it to English
PAIRS = {
    "es": {"language": "Spanish", "folder": "opus-mt-es-en", "repo": "Helsinki-NLP/opus-mt-es-en",
           "revision": "c96e2c5399ebfae4fc43d9669556b9afa74bb69d",
           "weights_sha256": "586a4e69e0804459ac7c176a5dc76852652100d9af1ee0db796de719899a5deb"},
    "yo": {"language": "Yoruba", "folder": "opus-mt-yo-en", "repo": "Helsinki-NLP/opus-mt-yo-en",
           "revision": "f3d791bfa5ccd8d0ff7171f177f3e55c5bb3971c",
           "weights_sha256": "40ef20144550eec583ac964c14ad1def638e5766837f4c69d9e7c38a24738ec3"},
}
WEIGHTS = "pytorch_model.bin"
FILES = ("config.json", "generation_config.json", "source.spm", "target.spm", "tokenizer_config.json", "vocab.json",
         "README.md", WEIGHTS)
MANIFEST = "loupe-model.json"


def model_root() -> Path:
    return Path(os.environ.get("LOUPE_TRANSLATION_MODEL_DIR") or Path.home() / ".cache" / "loupe-mt")


def model_dir(iso: str) -> Path | None:
    pair = PAIRS.get(iso)
    return model_root() / pair["folder"] if pair else None


def installed(iso: str) -> bool:
    d = model_dir(iso)
    return d is not None and all((d / f).is_file() for f in FILES if f != "README.md")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(iso: str, root: Path | None = None, opener=urllib.request.urlopen) -> Path:
    """Fetch one pair's files at the pinned revision into ``root`` (the model folder). The folder appears only when
    every file is fetched and the weights match the pinned hash."""
    pair = PAIRS[iso]
    root = Path(root or model_root())
    root.mkdir(parents=True, exist_ok=True)
    final = root / pair["folder"]
    with tempfile.TemporaryDirectory(prefix=".loupe-mt-", dir=root) as tmp:
        part = Path(tmp) / pair["folder"]
        part.mkdir()
        for name in FILES:
            url = "https://huggingface.co/%s/resolve/%s/%s" % (pair["repo"], pair["revision"], name)
            with opener(url) as src, open(part / name, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        got = _sha256(part / WEIGHTS)
        if got != pair["weights_sha256"]:
            raise RuntimeError("The %s weights fetched do not match the pinned hash; nothing was installed."
                               % pair["folder"])
        (part / MANIFEST).write_text(json.dumps({
            "repo": pair["repo"], "revision": pair["revision"], "weights_sha256": got, "source_language": iso,
            "target_language": "en", "licence": LICENCE_WORDS}, indent=2))
        if final.exists():
            shutil.rmtree(final)
        part.rename(final)
    return final


def main(argv=None) -> int:
    wanted = list(argv if argv is not None else sys.argv[1:]) or sorted(PAIRS)
    unknown = [w for w in wanted if w not in PAIRS]
    if unknown:
        print("No pinned translation model for: %s. Known: %s." % (", ".join(unknown), ", ".join(sorted(PAIRS))))
        return 2
    for iso in wanted:
        path = install(iso)
        print("Installed %s to English (%s at %s) in %s" % (PAIRS[iso]["language"], PAIRS[iso]["repo"],
                                                          PAIRS[iso]["revision"], path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
