#!/usr/bin/env python3
"""Check every English quotation in an answer or research note against the library.

A quotation counts as found only when, after normalising whitespace, curly quotes and case, it occurs word
for word in one passage, or across neighbouring passages by the same speaker (the text quote.py returns).
Anything else is listed: a paraphrase put in quotation marks, a retyped or spliced quote, or a sentence the
library does not hold. Code spans are ignored; short quoted terms are counted but not checked.

Example: verify_quotes.py --library LIB research/x/研究底稿.md answer.md   (exit status 1 if any quote fails)
"""
import argparse
import json
import re
import sys
from pathlib import Path

from quote import joined_passage
from retrieve import open_corpus

CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# Straight quotes stay on one line (an unmatched inch mark must not swallow a paragraph); curly ones may
# wrap a line but never cross a blank line.
QUOTED = re.compile(r'"([^"\n]+)"|“((?:[^”\n]|\n(?!\s*\n))+)”')
FOLD = str.maketrans({"‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"', "„": '"'})
ELLIPSIS = re.compile(r"\s*(?:…|\.\s?\.\s?\.)\s*")
WORD = re.compile(r"[^\W_]+")
PROBE_WORDS = 8
PROBLEMS = ("not_found", "spliced", "truncated")


def normalize(text):
    return " ".join(text.translate(FOLD).split()).casefold()


def quotations(markdown, min_words=4):
    """[(line, quotation)] for English quotations of at least min_words words; also the count skipped as too short."""
    text = CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), markdown)
    found, short = [], 0
    for match in QUOTED.finditer(text):
        value = (match.group(1) or match.group(2)).strip()
        letters = [ch for ch in value if ch.isalpha()]
        if not letters or sum(ch.isascii() for ch in letters) < 0.9 * len(letters):
            continue                                   # Chinese quotation marks around Chinese text
        if len(re.findall(r"[A-Za-z]+", value)) < min_words:
            short += 1
            continue
        found.append((text.count("\n", 0, match.start()) + 1, value))
    return found, short


class Library:
    def __init__(self, corpus):
        self.corpus = corpus
        self.headings = None

    def _rows(self, words):
        phrase = '"' + " ".join(words) + '"'
        return self.corpus.db.execute(
            "SELECT c.* FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id WHERE chunks_fts MATCH ?", (phrase,))

    def passages(self, value):
        """Evidence records of the passages that contain `value` word for word."""
        target, words = normalize(value), WORD.findall(value)
        if not words:
            return []
        # The whole quotation usually sits in one chunk. If a chunk boundary splits it, one side holds at least
        # half the words, so a probe of min(8, n/2) words from either end finds that chunk.
        side = max(1, min(PROBE_WORDS, len(words) // 2))
        hits, checked = [], set()
        for probes in ([words], [words[:side], words[-side:]]):
            for probe in probes:
                for row in self._rows(probe):
                    if row["id"] in checked:
                        continue
                    checked.add(row["id"])
                    text, _ = joined_passage(self.corpus, row)
                    if target in normalize(text):
                        hits.append(self.corpus.evidence(row))
            if hits:
                break
        return hits

    def heading(self, value):
        """A chapter heading (an editorial title stored as a locator) containing `value`, if any."""
        if self.headings is None:
            self.headings = {}
            for (locator,) in self.corpus.db.execute("SELECT DISTINCT locator FROM chunks WHERE locator LIKE '%section%'"):
                section = json.loads(locator).get("section")
                if section:
                    self.headings.setdefault(normalize(section), section)
        target = normalize(value)
        return next((section for key, section in self.headings.items() if target in key), None)


def source(record):
    meta = record["provenance"]
    return {"title": meta["title"], "date": meta.get("date"), "speaker": record["speaker"],
            "exact_quote_candidate": record["evidence_eligibility"]["exact_quote_candidate"]}


def check(library, value):
    value = value.rstrip(",;: ")    # punctuation of the surrounding prose often sits inside the quotation marks
    hits = library.passages(value)
    if hits:
        verbatim = [h for h in hits if h["evidence_eligibility"]["exact_quote_candidate"]]
        status = "found" if verbatim else "found_non_verbatim_source"
        return {"status": status, "source": source((verbatim or hits)[0]), "matches": len(hits)}
    pieces = [p for p in ELLIPSIS.split(value) if WORD.search(p)]
    title = library.heading(" ".join(pieces) if len(pieces) == 1 else value)
    if title:
        return {"status": "chapter_heading", "heading": title}
    if len(pieces) > 1 and all(library.passages(p) for p in pieces):
        return {"status": "spliced", "note": "Each part exists but not as one continuous passage; quote whole sentences."}
    if len(pieces) == 1 and pieces[0] != value and library.passages(pieces[0]):
        return {"status": "truncated", "note": "Found only after dropping the ellipsis; quote the complete sentence."}
    return {"status": "not_found"}


def verify(corpus, paths, min_words=4):
    library, report = Library(corpus), []
    for path in paths:
        values, short = quotations(Path(path).read_text(encoding="utf-8"), min_words)
        results = [dict(line=line, quote=value, **check(library, value)) for line, value in values]
        counts = {}
        for result in results:
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        report.append({"path": str(Path(path).resolve()), "quotes_checked": len(results),
                       "skipped_short": short, "counts": counts,
                       "problems": [r for r in results if r["status"] in PROBLEMS],
                       "results": results})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files, or directories searched for *.md")
    parser.add_argument("--min-words", type=int, default=4, help="Shorter English quotations are counted, not checked")
    parser.add_argument("--problems-only", action="store_true", help="Omit the per-quote list of found quotations")
    args = parser.parse_args()
    files = []
    for path in args.paths:
        files.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    corpus = open_corpus(args.library)
    try:
        report = verify(corpus, files, args.min_words)
    finally:
        corpus.close()
    if args.problems_only:
        for item in report:
            item.pop("results")
    print(json.dumps({"files": report,
                      "note": "found = word for word in the library (whitespace, curly quotes and case normalised). "
                              "found_non_verbatim_source: only in third-party, rough, OCR or translated text; say 非逐字核对. "
                              "chapter_heading: an editorial title, not the speaker's words. A found quote can still be "
                              "misattributed or cut from its context: open it with quote.py."},
                     ensure_ascii=False, indent=2))
    return 1 if any(item["problems"] for item in report) else 0


if __name__ == "__main__":
    sys.exit(main())
