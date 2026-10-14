"""Bench on a hand-labelled corpus: what the human has to review and what leaks.

    uv run python scripts/bench.py --dir PATH [--show]

PATH holds `corpus/` (texts) and `golden/` (one JSON per text, see below).
The corpus is processed as one project, like `anon scan` + `review` + `apply`:

- auto: every finding is kept (the human presses Enter through the whole list).
- ideal: the human keeps exactly the findings that touch a direct or quasi
  golden mention and rejects the rest. Adds nothing by hand.

Golden file: {"file": "x.md", "entities": [{"id", "kind", "tier", "role",
"surfaces": [verbatim strings]}]}, tier is direct | quasi | public.

By default only numbers are printed, so the output can be shared even when the
corpus is real data. --show also prints the values behind leaks and false hits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from anon.detect import find_all
from anon.keep import KeepList
from anon.model import Kind
from anon.replace import plan
from anon.review import Collector, apply_decisions, group_key
from anon.text import read_text
from anon.vault import Vault

STRICT = ("direct", "quasi")
_WB_BEFORE = r"(?<![^\W_])"
_WB_AFTER = r"(?![^\W_])"


def golden_mentions(text: str, golden: dict) -> list[dict]:
    """Every occurrence of every golden surface: start, end, entity id, tier, kind.

    Longest surfaces win where occurrences overlap.
    """
    cands = []
    for e in golden["entities"]:
        for s in e.get("surfaces", []):
            if not s.strip():
                continue
            pat = re.compile(_WB_BEFORE + re.escape(s) + _WB_AFTER)
            for m in pat.finditer(text):
                cands.append((m.start(), m.end(), e))
    cands.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken = bytearray(len(text))
    out = []
    for a, b, e in cands:
        if any(taken[a:b]):
            continue
        taken[a:b] = b"\x01" * (b - a)
        out.append(
            {
                "start": a,
                "end": b,
                "id": e["id"],
                "tier": e["tier"],
                "kind": e["kind"],
                "text": text[a:b],
            }
        )
    return sorted(out, key=lambda m: m["start"])


def overlaps(a: int, b: int, c: int, d: int) -> bool:
    return a < d and c < b


def word_chars_covered(text: str, a: int, b: int, cover: bytearray) -> bool:
    return all(cover[i] for i in range(a, b) if text[i].isalnum())


def run(corpus: list[tuple[str, str]], goldens: dict[str, dict], mode: str, keep: KeepList | None = None) -> dict:
    vault = Vault()
    collector = Collector()
    spans_by_file = {}
    item_truth: dict[tuple[str, str], set[str]] = defaultdict(set)
    for name, text in corpus:
        spans = find_all(text)
        spans_by_file[name] = spans
        mentions = goldens[name]["_mentions"]
        for s in spans:
            collector.add(s.kind, s.text, name, s.sources, "", s.normal)
            key = group_key(s.kind, s.text, s.normal)
            hit = {
                m["tier"]
                for m in mentions
                if overlaps(s.start, s.end, m["start"], m["end"])
            }
            item_truth[key] |= hit or {"none"}
    by_class = Counter()
    premarked = Counter()
    wrongly_kept: list[tuple[str, str, str]] = []
    to_decide: dict[str, list] = defaultdict(list)
    items = []
    for key, item in collector._items.items():
        truth = item_truth[key]
        cls = "direct" if "direct" in truth else "quasi" if "quasi" in truth else "public" if "public" in truth else "junk"
        by_class[cls] += 1
        item.keep = True if mode == "auto" else cls in STRICT
        if keep and any(
            keep.matches(v, whole=item.kind == Kind.PERSON) for v in item.variants | {item.text}
        ):
            premarked[cls] += 1
            if cls in STRICT:
                wrongly_kept.append((cls, item.kind.value, item.text))
            if mode == "auto":
                item.keep = False
        else:
            to_decide[cls].append((item.count, item.kind.value, item.text))
        items.append(item)
    apply_decisions(items, vault)
    known = set(vault.added)
    vault.added.extend(
        (v, i.kind)
        for i in items
        if i.keep
        for v in i.variants | {i.text}
        if (v, i.kind) not in known
    )

    res = {
        "review_items": len(items),
        "review_by_class": dict(by_class),
        "premarked": dict(premarked),
        "wrongly_kept": wrongly_kept,
        "to_decide": to_decide,
        "mentions": Counter(),
        "leaked": Counter(),
        "labels_total": 0,
        "labels_false": 0,
        "labels_public": 0,
        "split_people": 0,
        "people": 0,
        "leak_examples": [],
        "false_examples": Counter(),
    }
    for name, text in corpus:
        hits = plan(text, spans_by_file[name], vault)
        cover = bytearray(len(text))
        for a, b, _ in hits:
            cover[a:b] = b"\x01" * (b - a)
        mentions = goldens[name]["_mentions"]
        labels_of: dict[str, set[int]] = defaultdict(set)
        for m in mentions:
            if m["tier"] not in STRICT:
                continue
            res["mentions"][m["tier"]] += 1
            if not word_chars_covered(text, m["start"], m["end"], cover):
                res["leaked"][m["tier"]] += 1
                res["leak_examples"].append((name, m["tier"], m["kind"], m["text"]))
            if m["kind"] == "PERSON" and m["tier"] == "direct":
                for a, b, e in hits:
                    if overlaps(a, b, m["start"], m["end"]):
                        labels_of[m["id"]].add(id(e))
        for ids in labels_of.values():
            res["people"] += 1
            res["split_people"] += len(ids) > 1
        for a, b, e in hits:
            res["labels_total"] += 1
            touched = {
                m["tier"] for m in mentions if overlaps(a, b, m["start"], m["end"])
            }
            if not touched & set(STRICT):
                if "public" in touched:
                    res["labels_public"] += 1
                else:
                    res["labels_false"] += 1
                res["false_examples"][(e.kind.value, text[a:b])] += 1
    return res


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument(
        "--show", action="store_true", help="print values behind leaks and false hits"
    )
    ap.add_argument("--mode", choices=["auto", "ideal", "both"], default="both")
    ap.add_argument("--keep", type=Path, help="keep list file (one public name per line), as `anon keep` writes it")
    args = ap.parse_args()

    corpus, goldens = [], {}
    for g in sorted((args.dir / "golden").glob("*.json")):
        data = json.loads(g.read_text(encoding="utf-8"))
        text = read_text(args.dir / "corpus" / data["file"])
        data["_mentions"] = golden_mentions(text, data)
        corpus.append((data["file"], text))
        goldens[data["file"]] = data
    if not corpus:
        sys.exit("no golden files")

    keep = None
    if args.keep:
        values = [x.strip() for x in args.keep.read_text(encoding="utf-8").splitlines() if x.strip()]
        keep = KeepList.build(values)
    t0 = time.time()
    modes = ["auto", "ideal"] if args.mode == "both" else [args.mode]
    for mode in modes:
        r = run(corpus, goldens, mode, keep)
        print(f"== {mode}  ({len(corpus)} files, {time.time() - t0:.0f}s)")
        rc = r["review_by_class"]
        print(
            f"review items: {r['review_items']}  direct {rc.get('direct', 0)}  quasi {rc.get('quasi', 0)}"
            f"  public {rc.get('public', 0)}  junk {rc.get('junk', 0)}"
        )
        if keep:
            pm = r["premarked"]
            print(
                f"kept by list: {sum(pm.values())}  of them direct {pm.get('direct', 0)}  quasi {pm.get('quasi', 0)}"
                f"  public {pm.get('public', 0)}  junk {pm.get('junk', 0)}"
                f"  -> left to decide {r['review_items'] - sum(pm.values())}"
            )
        for tier in STRICT:
            n, lk = r["mentions"][tier], r["leaked"][tier]
            print(f"{tier:<7} mentions {n:<5} leaked {lk:<4} hidden {pct(n - lk, n)}")
        print(
            f"labels {r['labels_total']}  false {r['labels_false']} ({pct(r['labels_false'], r['labels_total'])})"
            f"  public {r['labels_public']} ({pct(r['labels_public'], r['labels_total'])})"
        )
        print(f"people split across labels: {r['split_people']} of {r['people']}")
        if args.show:
            print("-- leaks")
            for name, tier, kind, s in r["leak_examples"]:
                print(f"   {name:<14} {tier:<6} {kind:<8} {s}")
            if keep:
                print("-- sensitive values the keep list would leave in the text")
                for cls, kind, text in r["wrongly_kept"]:
                    print(f"   {cls:<6} {kind:<8} {text}")
                for cls in ("public", "junk"):
                    print(f"-- left to decide, {cls} (count, kind, text)")
                    for c, kind, text in sorted(r["to_decide"][cls], reverse=True)[:60]:
                        print(f"   {c:>4} {kind:<8} {text}")
            print("-- false and public labels (kind, text, count)")
            for (kind, s), c in r["false_examples"].most_common(80):
                print(f"   {kind:<8} {c:>4}  {s}")
        t0 = time.time()


if __name__ == "__main__":
    main()
