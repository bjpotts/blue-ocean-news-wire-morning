#!/usr/bin/env python3
"""Shared test helpers.

`build.py` is a script: it runs its freshness guards, loads data/*.json and
writes public/digest.html at import time. Importing it from a test would
overwrite the published digest as a side effect, so its pure helpers are
lifted out of the source with `ast` and executed in an isolated namespace
instead.
"""
import ast
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_from_source(filename, names):
    """Exec only the named top-level defs/assignments from a module's source.

    Top-level imports are always included so the extracted functions can reach
    the names they close over. Avoids the module's import-time side effects.
    """
    path = os.path.join(ROOT, filename)
    with open(path) as f:
        src = f.read()
    tree = ast.parse(src)
    imports, wanted, missing = [], [], set(names)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)
            continue
        found = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            found = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            found = node.targets[0].id
        if found in missing:
            wanted.append(node)
            missing.discard(found)
    if missing:
        raise AssertionError("not found in %s: %s" % (filename, sorted(missing)))
    ns = {"__name__": "extracted", "__file__": path}
    # Imports run one at a time so an optional heavy dependency (playwright)
    # missing from the test environment does not block extraction.
    for node in imports:
        try:
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
        except ImportError:
            pass
    exec(compile(ast.Module(body=wanted, type_ignores=[]), path, "exec"), ns)
    return ns


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def rss(items, channel_extra=""):
    """Minimal RSS document around the given <item> bodies."""
    return ("<?xml version='1.0'?><rss version='2.0'><channel>%s%s</channel></rss>"
            % (channel_extra, "".join(items)))


def rss_item(title="A headline", link="https://example.com/a",
             date="Wed, 02 Sep 2026 08:00:00 GMT", description="Some detail."):
    parts = []
    if title is not None:
        parts.append("<title>%s</title>" % title)
    if link is not None:
        parts.append("<link>%s</link>" % link)
    if date is not None:
        parts.append("<pubDate>%s</pubDate>" % date)
    if description is not None:
        parts.append("<description>%s</description>" % description)
    return "<item>%s</item>" % "".join(parts)


def source_of(filename):
    """A module's raw source, for assertions about the code itself."""
    with open(os.path.join(ROOT, filename)) as f:
        return f.read()


def digest_path():
    return os.path.join(ROOT, "public", "digest.html")


def read_digest():
    """The most recently built digest, or None when the page has not been built."""
    path = digest_path()
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()
