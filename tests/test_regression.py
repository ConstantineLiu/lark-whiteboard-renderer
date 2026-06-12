#!/usr/bin/env python3
"""feishu-whiteboard-har 回归测试（纯标准库，python3 -m unittest discover tests）。

[INPUT]: scripts/process_har.py、tests/fixtures/*.har、tests/golden/
[OUTPUT]: 渲染回归断言；golden 不符即失败
[POS]: 渲染器的安全网——SKILL.md 的 PNG-Guided Refinement 允许 AI 反复改
       渲染逻辑，任何改动必须先过这里再提交
[PROTOCOL]: 变更时更新此头部，然后检查 SKILL.md；渲染输出有意变更时
            用 tests/regen_golden.sh 重生成 golden 并人工目检 diff
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "process_har.py"
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"


def run_script(har: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), str(har), "--out", str(out), *extra]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestSyntheticGolden(unittest.TestCase):
    """合成 HAR 全链路输出与 golden 逐字节对比。"""

    tmp: tempfile.TemporaryDirectory
    out: Path
    proc: subprocess.CompletedProcess

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "synthetic"
        cls.proc = run_script(FIXTURES / "synthetic.har", cls.out, "--extract-related-images")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_exit_code(self) -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_svg_matches_golden(self) -> None:
        for golden_svg in sorted(GOLDEN.glob("*.simple.svg")):
            produced = self.out / golden_svg.name
            self.assertTrue(produced.exists(), f"missing {golden_svg.name}")
            self.assertEqual(
                produced.read_bytes(), golden_svg.read_bytes(),
                f"{golden_svg.name} 与 golden 不一致；若是有意变更，跑 tests/regen_golden.sh 并目检",
            )

    def test_index_matches_golden(self) -> None:
        self.assertEqual((self.out / "index.md").read_text(), (GOLDEN / "index.md").read_text())

    def test_summary_matches_golden(self) -> None:
        produced = json.loads((self.out / "summary.json").read_text())
        golden = json.loads((GOLDEN / "summary.json").read_text())
        produced.pop("har"), golden.pop("har")  # 绝对路径随环境变化
        self.assertEqual(produced, golden)

    def test_source_image_ext_from_magic_bytes(self) -> None:
        # block2 的图 MIME 谎报 png、实际 JPEG，扩展名必须以 magic bytes 为准
        self.assertTrue((self.out / "whiteboard-01.source.png").exists())
        self.assertTrue((self.out / "whiteboard-02.source.jpg").exists())
        self.assertTrue((self.out / "whiteboard-extra-01.source.png").exists())

    def test_no_signed_urls_leak(self) -> None:
        # 所有 markdown 输出不得携带 URL query（飞书签名 token）
        for md in self.out.rglob("*.md"):
            self.assertNotIn("secret-sig", md.read_text(), f"{md} 泄露了签名 URL")

    def test_audit_package(self) -> None:
        # 独立输出目录，避免覆盖 setUpClass 产物
        audit_out = Path(self.tmp.name) / "audit-run"
        target = audit_out / "audit-package.json"
        proc = run_script(FIXTURES / "synthetic.har", audit_out, "--audit-package", str(target))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(target.read_text())
        self.assertEqual(len(payload["whiteboard_blocks"]), 2)
        self.assertNotIn("secret-sig", json.dumps(payload["whiteboard_image_metadata"]))


class TestTruncatedRecovery(unittest.TestCase):
    """截断 HAR 必须恢复完整 entries 并照常产出。"""

    def test_recovers_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "truncated"
            proc = run_script(FIXTURES / "truncated.har", out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("HAR is not valid JSON", proc.stderr)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["entries"], 6)  # 7 条砍掉最后 1 条
            self.assertEqual(summary["whiteboard_blocks"], 2)
            self.assertEqual(summary["cdp_whiteboard_images"], 3)


if __name__ == "__main__":
    unittest.main()
