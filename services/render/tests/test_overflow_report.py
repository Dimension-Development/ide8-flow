"""A missing or failed Scribus check is never evidence of no overflow."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from fastapi import HTTPException
    from service.app import _overflows, package
except ModuleNotFoundError as exc:
    if exc.name != "fastapi":
        raise
    _overflows = None


@unittest.skipIf(_overflows is None, "requires render service dependencies")
class TestOverflowReport(unittest.TestCase):
    def test_missing_invalid_and_incomplete_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "out.pdf"
            report = Path(str(pdf) + ".report.json")
            for value in (None, "bad json", "[]", "{}", '{"overflows":null}',
                          '{"overflows":[],"error":"Scribus readback failed"}',
                          '{"overflows":[],"error":""}'):
                if value is not None:
                    report.write_text(value)
                with self.subTest(value=value), self.assertRaises(HTTPException) as cm:
                    _overflows(pdf)
                self.assertEqual(cm.exception.status_code, 500)
            report.write_text('{"overflows":[]}')
            self.assertEqual(_overflows(pdf), [])

    def test_package_rejects_overflow_and_missing_evidence(self):
        class Request:
            headers = {}
            async def body(self):
                return b"sla"
        for report, status in ((None, 500), ({"overflows": [{"item": "legal"}]}, 422)):
            def export(sla, kind, workdir):
                pdf = workdir / "out.pdf"
                pdf.write_bytes(b"pdf")
                if report is not None:
                    Path(str(pdf) + ".report.json").write_text(json.dumps(report))
                return pdf
            with patch("service.app._export_pdf", side_effect=export), self.assertRaises(HTTPException) as cm:
                asyncio.run(package(Request()))
            self.assertEqual(cm.exception.status_code, status)


if __name__ == "__main__":
    unittest.main()
