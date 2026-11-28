"""Exercise the standalone exporter against the shared confirmed-snapshot shape."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RENDERER = Path(__file__).parent / "scripts" / "render_brief.py"


class RenderBriefTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "version": 2,
            "headline": "核对客户演示范围 <img src=x onerror=alert(1)>",
            "summary": "按已确认条件准备周三演示。",
            "items": [
                {
                    "area": "demo",
                    "state": "proceed",
                    "priority": "high",
                    "action": "准备脱敏样本",
                    "owner": "项目负责人 <甲>",
                    "reason": "客户已确认样本用途。",
                    "question": "",
                    "evidence_ids": ["local-publisher-id"],
                },
                {
                    "area": "live_access",
                    "state": "waiting",
                    "priority": "normal",
                    "action": "等待读取范围的单独审批",
                    "owner": "客户 IT",
                    "reason": "记录未批准接口读取。",
                    "question": "可读取哪些字段？",
                    "evidence_ids": ["local-publisher-id"],
                },
            ],
            "evidence": [
                {
                    "id": "local-publisher-id",
                    "title": "模拟回函 <甲>",
                    "page_start": 1,
                    "page_end": 2,
                    "text": "仅供周三演示。\n</blockquote><script>alert(1)</script>",
                    "source_id": "source-internal",
                    "producer_run_id": "internal-run",
                    "sha256": "internal-fingerprint",
                },
                {
                    "id": "unreferenced",
                    "title": "未选中的材料",
                    "text": "未选中的内容",
                    "page_start": 3,
                    "page_end": 3,
                },
            ],
        }

    def run_cli(self, source, target):
        source.write_text(json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(RENDERER), str(source), str(target), "--fictional"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_renders_only_selected_evidence_and_escapes_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "snapshot.json", Path(directory) / "brief.html"
            result = self.run_cli(source, target)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = target.read_text(encoding="utf-8")

        for text in (
            '<html lang="zh-CN">',
            "版本 2",
            "模拟客户案例",
            "可继续",
            "待确认",
            "可读取哪些字段？",
            "第 1–2 页",
            "模拟回函 &lt;甲&gt;",
            "项目负责人 &lt;甲&gt;",
            "&lt;img src=x onerror=alert(1)&gt;",
            "&lt;/blockquote&gt;&lt;script&gt;",
            "<details",
            "default-src 'none'",
        ):
            self.assertIn(text, rendered)
        for forbidden in (
            "<img",
            "<script",
            "<iframe",
            "local-publisher-id",
            "source-internal",
            "internal-run",
            "internal-fingerprint",
            "未选中的材料",
            "未选中的内容",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_cli_rejects_unknown_evidence_without_overwriting_output(self):
        self.snapshot["items"][0]["evidence_ids"] = ["missing-id"]
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "snapshot.json", Path(directory) / "brief.html"
            target.write_bytes(b"previous brief")
            result = self.run_cli(source, target)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("evidence", result.stderr)
            self.assertEqual(target.read_bytes(), b"previous brief")


if __name__ == "__main__":
    unittest.main()
