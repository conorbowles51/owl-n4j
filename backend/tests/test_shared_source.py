"""One stored copy of a file the server already holds (services/shared_source.py)."""
import hashlib
import os
import stat
from pathlib import Path

import pytest

from services import shared_source as ss

BIG = b'0123456789abcdef' * 8192  # 128 KiB


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def world(tmp_path):
    corpus = tmp_path / 'corpus'
    payload = tmp_path / 'case' / '_upload_groups' / 'g1' / 'payload'
    (corpus / 'v1' / 'Report').mkdir(parents=True)
    payload.mkdir(parents=True)
    return tmp_path, corpus, payload


def sources(world, **kw):
    tmp, corpus, payload = world
    return ss.SharedSources([corpus], tmp / 'idx', exclude=[payload.parent], **kw)


def test_identical_file_becomes_one_read_only_copy(world):
    tmp, corpus, payload = world
    source = corpus / 'v1' / 'Report' / 'video.mp4'
    source.write_bytes(BIG)
    stored = payload / 'Report' / 'video.mp4'
    stored.parent.mkdir()
    stored.write_bytes(BIG)
    before = os.stat(stored).st_ino
    s = sources(world)
    assert s.adopt(stored, digest(BIG), len(BIG), relative='Report/video.mp4') == str(source)
    assert os.stat(stored).st_ino == os.stat(source).st_ino != before
    assert os.stat(source).st_nlink == 2
    for p in (stored, source):
        assert not os.stat(p).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert stored.read_bytes() == BIG
    assert s.summary()['bytes'] == len(BIG)
    record = s.write_links(payload.parent / ss.LINKS_NAME)
    assert 'Report/video.mp4' in record.read_text()


def test_same_name_and_size_with_other_bytes_is_never_linked(world):
    tmp, corpus, payload = world
    other = b'x' * len(BIG)
    (corpus / 'v1' / 'a.bin').write_bytes(other)
    stored = payload / 'a.bin'
    stored.write_bytes(BIG)
    s = sources(world)
    assert s.adopt(stored, digest(BIG), len(BIG)) is None
    assert s.skipped.get('content_differs') == 1
    assert stored.read_bytes() == BIG and os.stat(stored).st_nlink == 1


def test_small_files_and_no_match_are_left_alone(world):
    tmp, corpus, payload = world
    (corpus / 'small.txt').write_bytes(b'hi')
    stored = payload / 'small.txt'
    stored.write_bytes(b'hi')
    assert sources(world).adopt(stored, digest(b'hi'), 2) is None
    lone = payload / 'lone.bin'
    lone.write_bytes(BIG)
    assert sources(world).adopt(lone, digest(BIG), len(BIG)) is None


def test_deleting_the_stored_name_keeps_the_source(world):
    tmp, corpus, payload = world
    source = corpus / 'v1' / 'big.bin'
    source.write_bytes(BIG)
    stored = payload / 'big.bin'
    stored.write_bytes(BIG)
    sources(world).adopt(stored, digest(BIG), len(BIG))
    import shutil
    shutil.rmtree(payload.parent)
    assert source.read_bytes() == BIG


def test_refused_when_the_source_cannot_be_made_read_only(world, monkeypatch):
    tmp, corpus, payload = world
    source = corpus / 'v1' / 'big.bin'
    source.write_bytes(BIG)
    stored = payload / 'big.bin'
    stored.write_bytes(BIG)
    monkeypatch.setattr(ss, 'make_read_only', lambda path: False)
    s = sources(world)
    assert s.adopt(stored, digest(BIG), len(BIG)) is None
    assert os.stat(stored).st_nlink == 1 and s.skipped['not_read_only'] == 1


def test_another_stored_container_is_a_source(world):
    tmp, corpus, payload = world
    first = tmp / 'case2' / 'big.bin'
    first.parent.mkdir()
    first.write_bytes(BIG)
    stored = payload / 'big.bin'
    stored.write_bytes(BIG)
    s = ss.SharedSources([], tmp / 'idx', stored_lookup=lambda sha, size: [str(first)], exclude=[payload.parent])
    assert s.adopt(stored, digest(BIG), len(BIG)) == str(first)
    assert os.stat(first).st_ino == os.stat(stored).st_ino


def test_own_group_files_are_never_a_source(world):
    tmp, corpus, payload = world
    sibling = payload / 'copy.bin'
    sibling.write_bytes(BIG)
    stored = payload / 'big.bin'
    stored.write_bytes(BIG)
    s = ss.SharedSources([], tmp / 'idx', stored_lookup=lambda sha, size: [str(sibling)], exclude=[payload.parent])
    assert s.adopt(stored, digest(BIG), len(BIG)) is None


def test_prepare_payload_links_a_stored_folder_member(world, monkeypatch):
    """The upload step itself (not only adopt) hands each verified member to the sources."""
    from routers import evidence_upload_groups as api
    seen = []

    class Fake:
        linked = []

        def adopt(self, target, sha, size, relative=None):
            seen.append((Path(target).name, relative))

    import types
    tmp, corpus, payload = world
    src = tmp / 'up'
    src.mkdir()
    (src / 'f').write_bytes(b'abc')
    group = types.SimpleNamespace(id='g1', case_id='c1', kind='folder', name='n', manifest=[
        dict(path='Dir/f.txt', size=3, sha256=digest(b'abc'), chunks=[])])
    monkeypatch.setattr(api, 'payload_root', lambda g: payload)
    monkeypatch.setattr(api, 'checked', lambda manifest, copies: [(manifest[0], src / 'f')])
    monkeypatch.setattr(api, 'uuid5', lambda *a: 'k')
    monkeypatch.setattr(api, 'case_relative', lambda g, p: str(p))
    rows = [types.SimpleNamespace(id='k', case_id='c1', filename='f', size=3, sha256=digest(b'abc'), chunks=[],
                                  chunk_size=1)]
    out = api.prepare_payload(group, rows, lambda p: {'outcome': api.NOT_A_PHONE_REPORT}, None, Fake())
    assert seen == [('f.txt', 'Dir/f.txt')] and out['members'][0]['path'] == 'Dir/f.txt'
