"""The image search model Loupe uses, pinned, and the one-time install of its files (05 section 17.6).

One image-text embedding model: Google's SigLIP 2 base (patch 16, 224 pixels), at a pinned revision of its Hugging
Face repository, with the SHA-256 of its weights file. The licence check was made at build: the model card says
``license: apache-2.0``, which allows commercial use. The LAION OpenCLIP weights were not used: their model cards put
deployed use of the model out of scope, and Loupe is a deployed, commercial system.

Model files are never fetched while evidence is indexed or searched. An operator runs this module once on the
server:

    cd backend && python -m services.phone.image_search_models

It writes the model to ``$LOUPE_IMAGE_MODEL_DIR/<folder>`` (default ``~/.cache/loupe-image``), checks the weights
against the pinned hash before the folder is put in place, and writes ``loupe-model.json`` beside the files naming
the repository, revision and licence. Standard library only.
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

LICENCE_WORDS = "Model card licence: apache-2.0. Allows commercial use."

MODEL = {"name": "SigLIP 2 base", "folder": "siglip2-base-patch16-224", "repo": "google/siglip2-base-patch16-224",
         "revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
         "weights_sha256": "612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b"}
WEIGHTS = "model.safetensors"
FILES = ("config.json", "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer.model",
         "tokenizer_config.json", "README.md", WEIGHTS)
MANIFEST = "loupe-model.json"


def model_root() -> Path:
    return Path(os.environ.get("LOUPE_IMAGE_MODEL_DIR") or Path.home() / ".cache" / "loupe-image")


def model_dir() -> Path:
    return model_root() / MODEL["folder"]


def installed() -> bool:
    d = model_dir()
    return all((d / f).is_file() for f in FILES if f != "README.md")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(weights_hash=None) -> dict:
    """The installed model's identity as every stored vector records it: the repository at its revision, a short
    version for labels, and the SHA-256 of the weights file actually in the folder (``weights_hash`` computes it;
    the caller passes ``phone_media().weights_sha256`` so a 1.5 GB file is hashed once per process)."""
    d = model_dir()
    try:
        manifest = json.loads((d / MANIFEST).read_text())
    except (OSError, ValueError):
        manifest = {}
    repo = manifest.get("repo") or MODEL["repo"]
    revision = manifest.get("revision")
    return {"model": MODEL["folder"], "model_id": "%s@%s" % (repo, revision) if revision else repo,
            "model_revision": revision, "revision_short": revision[:7] if revision else "revision not recorded",
            "weights_sha256": (weights_hash or _sha256)(d / WEIGHTS)}


def install(root: Path | None = None, opener=urllib.request.urlopen) -> Path:
    """Fetch the model's files at the pinned revision into ``root``. The folder appears only when every file is
    fetched and the weights match the pinned hash."""
    root = Path(root or model_root())
    root.mkdir(parents=True, exist_ok=True)
    final = root / MODEL["folder"]
    with tempfile.TemporaryDirectory(prefix=".loupe-image-", dir=root) as tmp:
        part = Path(tmp) / MODEL["folder"]
        part.mkdir()
        for name in FILES:
            url = "https://huggingface.co/%s/resolve/%s/%s" % (MODEL["repo"], MODEL["revision"], name)
            with opener(url) as src, open(part / name, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        got = _sha256(part / WEIGHTS)
        if got != MODEL["weights_sha256"]:
            raise RuntimeError("The %s weights fetched do not match the pinned hash; nothing was installed."
                               % MODEL["folder"])
        (part / MANIFEST).write_text(json.dumps({
            "repo": MODEL["repo"], "revision": MODEL["revision"], "weights_sha256": got, "licence": LICENCE_WORDS},
            indent=2))
        if final.exists():
            shutil.rmtree(final)
        part.rename(final)
    return final


def main(argv=None) -> int:
    path = install()
    print("Installed the image search model (%s at %s) in %s" % (MODEL["repo"], MODEL["revision"], path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
