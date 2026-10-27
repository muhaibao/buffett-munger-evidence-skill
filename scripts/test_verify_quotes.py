"""A quotation in an answer must exist word for word in the library; anything else must be listed, never passed."""
import json
from pathlib import Path
import tempfile
import unittest

import library
import retrieve
import verify_quotes


class VerifyQuotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.writer = library.Library(self.root / "library")
        self.ingest("meeting", [
            {"text": "WARREN BUFFETT: We never want to depend on", "speaker": "Buffett", "section": "3. Rule one of finance"},
            {"text": "the kindness of strangers. That is rule one.", "speaker": "Buffett", "section": "3. Rule one of finance"},
            {"text": "BECKY QUICK: Thank you very much for that answer.", "speaker": "Becky Quick", "section": "3. Rule one of finance"}])
        self.ingest("notes", [{"text": "Munger said the market is crazy at times and you should wait."}],
                    source_type="meeting_notes", primary_status="secondary", transcript_quality="rough", speaker=None)

    def tearDown(self):
        self.writer.close()
        self.temp.cleanup()

    def ingest(self, name, segments, **meta):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps({"segments": segments}))
        base = {"id": name, "title": name, "date": "2008", "speaker": "mixed", "url": f"https://example.test/{name}",
                "source_type": "annual_meeting", "primary_status": "primary", "transcript_quality": "official"}
        self.writer.ingest(dict(base, **meta), path)

    def statuses(self, markdown):
        path = self.root / "answer.md"
        path.write_text(markdown, encoding="utf-8")
        corpus = retrieve.open_corpus(self.writer.root)
        try:
            report = verify_quotes.verify(corpus, [path])[0]
        finally:
            corpus.close()
        return [(r["quote"], r["status"]) for r in report["results"]], report

    def test_fabricated_quote_is_caught_while_the_real_one_passes(self):
        # The real sentence crosses a chunk boundary (as quote.py returns it); the invented one reverses its meaning.
        results, report = self.statuses('巴菲特说："We never want to depend on the kindness of strangers."\n'
                                         '另一处写成："We always depend on the kindness of strangers."\n')
        self.assertEqual(results, [("We never want to depend on the kindness of strangers.", "found"),
                                   ("We always depend on the kindness of strangers.", "not_found")])
        self.assertEqual([p["line"] for p in report["problems"]], [2])

    def test_curly_quotes_case_and_line_wrapping_do_not_cause_false_alarms(self):
        results, _ = self.statuses("“we never want to depend on the\nkindness of strangers.”")
        self.assertEqual(results[0][1], "found")

    def test_spliced_and_truncated_quotes_are_problems(self):
        # The rules require whole sentences; an ellipsis can hide a condition or join two separate remarks.
        results, _ = self.statuses('"We never want to depend on … That is rule one."\n"We never want to depend on the kindness…"')
        self.assertEqual([status for _, status in results], ["spliced", "truncated"])

    def test_editorial_headings_and_third_party_notes_are_labelled_not_passed_as_speech(self):
        results, _ = self.statuses('章节 “Rule one of finance” 。笔记："Munger said the market is crazy at times and you should wait."')
        self.assertEqual([status for _, status in results], ["chapter_heading", "found_non_verbatim_source"])

    def test_commands_chinese_quotes_and_short_terms_are_not_checked(self):
        results, report = self.statuses('`retrieve.py search "own a stock for ten years" --exact`\n'
                                        '```\nquote.py --match "an invented sentence that is not there"\n```\n'
                                        '篮子：“可以 / 不行 / 太难”；术语 "too hard"。')
        self.assertEqual(results, [])
        self.assertEqual(report["skipped_short"], 1)


if __name__ == "__main__":
    unittest.main()
