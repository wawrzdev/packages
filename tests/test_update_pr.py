from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts/open-update-pr.sh"


class UpdatePRTests(unittest.TestCase):
    def test_proposal_only_pushes_new_branch_and_replay_reuses_exact_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote, source, tools = root / "remote.git", root / "source", root / "bin"
            tools.mkdir()
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote), str(source)], check=True, capture_output=True)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=source, text=True).strip()
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            git("switch", "-c", "main")
            (source / "Casks").mkdir()
            (source / "Casks/tool.rb").write_text("old\n")
            git("add", ".")
            git("commit", "-m", "base")
            git("push", "origin", "main")
            base = git("rev-parse", "HEAD")
            # A real bare Git remote checks normal push/replay semantics; only GitHub PR I/O is mocked.
            gh = tools / "gh"
            gh.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['GH_TEST_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[:2] == ['pr', 'list']:
    if '--jq' in args:
        print(os.environ.get('GH_TEST_STATE', ''))
    else:
        print('[]')
''')
            gh.chmod(0o755)
            log = root / "gh.log"
            env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "GH_TOKEN": "test-only",
                   "GITHUB_REPOSITORY": "example/packages", "DEFAULT_BRANCH": "main",
                   "GH_TEST_LOG": str(log)}
            (source / "Casks/tool.rb").write_text("new\n")
            subprocess.run(["bash", str(SCRIPT), "casks", base], cwd=source, env=env,
                           check=True, capture_output=True, text=True)
            refs = git("ls-remote", "origin", "refs/heads/*").splitlines()
            main = [line for line in refs if line.endswith("refs/heads/main")]
            self.assertEqual(main, [f"{base}\trefs/heads/main"])
            proposals = [line for line in refs if "refs/heads/automation/casks/" in line]
            self.assertEqual(len(proposals), 1)
            first_head = proposals[0].split()[0]
            git("checkout", "--detach", base)
            (source / "Casks/tool.rb").write_text("new\n")
            subprocess.run(["bash", str(SCRIPT), "casks", base], cwd=source,
                           env={**env, "GH_TEST_STATE": "OPEN"}, check=True, capture_output=True, text=True)
            self.assertEqual(git("ls-remote", "origin", "refs/heads/automation/casks/*").split()[0], first_head)
            # Closing the exact proposal is an explicit stop, not an invitation to reopen it.
            git("checkout", "--detach", base)
            (source / "Casks/tool.rb").write_text("new\n")
            closed = subprocess.run(["bash", str(SCRIPT), "casks", base], cwd=source,
                                    env={**env, "GH_TEST_STATE": "CLOSED"}, capture_output=True, text=True)
            self.assertNotEqual(closed.returncode, 0)
            self.assertIn("Leave it closed", closed.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            merges = [call for call in calls if call[:2] == ["pr", "merge"]]
            self.assertEqual(len(merges), 2)
            for call in merges:
                self.assertIn("--auto", call)
                self.assertIn("--rebase", call)
                self.assertEqual(call[call.index("--match-head-commit") + 1], first_head)


if __name__ == "__main__":
    unittest.main()
