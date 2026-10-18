"""Quality gate for a feature branch: every check must PASS before merging.

    py tools/qa_gate.py                 # compare HEAD against origin/dev
    py tools/qa_gate.py --base dev      # another base ref
    py tools/qa_gate.py --skip-tests    # static checks only (fast)

Checks run against the branch diff (`git diff <base>...HEAD` plus any
uncommitted changes), so pre-existing debt elsewhere never blocks a branch,
but nothing new may add to it. See docs/STANDARDS.md §8.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# New/changed lines under app/ (minus app/ui/, see STANDARDS §5 "Testing UI
# code") must be at least this covered by the test suite.
DIFF_COVERAGE_MIN = 85.0
MAX_COMPLEXITY = 10
# Entry-point glue exercised only by the packaged app.
COVERAGE_EXEMPT = {"app/launcher.py"}
GIT_NAME, GIT_EMAIL = "DesvoSoft", "desvox23@gmail.com"
CONVENTIONAL = re.compile(r"^(feat|fix|refactor|test|docs|chore|perf|ci|build|style)(\([\w./-]+\))?!?: .+")
BANNED = [
    (re.compile(r"os\.startfile|_winapi"), "platform-specific call (use the cross-platform helpers)"),
    (re.compile(r"except\s*:\s*pass|except\s+Exception\s*:\s*pass"), "swallowed exception without logging"),
    (re.compile(r"\bprint\("), "print() in app code (use logging)"),
    (re.compile(r"messagebox\."), "native messagebox (use ZBBDialog/Toast)"),
]


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def run(cmd, **kw):
    # Sources and git output are UTF-8; the Windows default codepage would
    # choke on non-ASCII text (e.g. the "·" in UI strings).
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def git(*args) -> str:
    out = run(["git", *args])
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


# ----------------------------------------------------------------------
# Diff helpers
# ----------------------------------------------------------------------
def changed_files(base: str) -> list[str]:
    committed = git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD").split()
    working = git("diff", "--name-only", "--diff-filter=ACMR", "HEAD").split()
    untracked = git("ls-files", "--others", "--exclude-standard").split()
    return sorted({f.replace("\\", "/") for f in committed + working + untracked if (ROOT / f).exists()})


def added_lines(base: str) -> dict[str, set[int]]:
    """{file: {line numbers added/changed}} for the branch + working tree."""
    merge_base = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "--no-color", merge_base)
    result: dict[str, set[int]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:]
            current = path[2:] if path.startswith("b/") else None
            if current:
                result.setdefault(current, set())
        elif line.startswith("@@") and current:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(m.group(1)), int(m.group(2) or 1)
            result[current].update(range(start, start + count))
    for f in git("ls-files", "--others", "--exclude-standard").split():
        path = ROOT / f
        if path.suffix == ".py" and path.exists():
            n = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            result[f.replace("\\", "/")] = set(range(1, n + 1))
    return result


def py_files(files, prefix="app/"):
    return [f for f in files if f.endswith(".py") and f.startswith(prefix)]


def flake8(args, files=None) -> list[str]:
    out = run([sys.executable, "-m", "flake8", *args, *(files or ["app/"])])
    return [line for line in out.stdout.splitlines() if line.strip()]


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------
def check_syntax() -> Result:
    issues = flake8(["--select=E9,F63,F7,F82"])
    return Result("Syntax / undefined names (app/)", not issues, "\n".join(issues[:10]) or "0 issues")


def check_dead_code(files) -> Result:
    targets = py_files(files, "app/") + py_files(files, "tests/") + py_files(files, "tools/")
    issues = flake8(["--select=F401,F841,F811"], targets) if targets else []
    return Result("Dead imports / unused variables (changed files)", not issues,
                  "\n".join(issues[:10]) or f"0 issues in {len(targets)} files")


_C901 = re.compile(r"C901 '(?P<func>[^']+)' is too complex \((?P<score>\d+)\)")


def _complexities(path: str, source: str) -> dict[str, int]:
    """{function name: complexity} for every function over the limit."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / Path(path).name
        f.write_text(source, encoding="utf-8")
        out = run([sys.executable, "-m", "flake8", "--select=C901", f"--max-complexity={MAX_COMPLEXITY}", str(f)])
    found = {}
    for line in out.stdout.splitlines():
        m = _C901.search(line)
        if m:
            found[m.group("func")] = int(m.group("score"))
    return found


def check_complexity(files, added, base) -> Result:
    """New functions must stay <= MAX_COMPLEXITY; existing over-limit ones
    may be touched but must not get more complex than on the base."""
    issues = []
    for path in py_files(files) + py_files(files, "tools/"):
        now = _complexities(path, (ROOT / path).read_text(encoding="utf-8", errors="replace"))
        if not now:
            continue
        shown = run(["git", "show", f"{base}:{path}"])
        before = _complexities(path, shown.stdout) if shown.returncode == 0 else {}
        for func, score in now.items():
            if score > before.get(func, MAX_COMPLEXITY):
                was = f" (was {before[func]})" if func in before else " (new)"
                issues.append(f"{path}: {func} complexity {score}{was}")
    return Result(f"Complexity <= {MAX_COMPLEXITY} (no increase for existing debt)", not issues,
                  "\n".join(issues) or "ok")


def check_banned(added) -> Result:
    hits = []
    for path, lines in added.items():
        if not (path.startswith("app/") and path.endswith(".py")) or not (ROOT / path).exists():
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()
        for n in sorted(lines):
            if n <= len(text):
                for pattern, why in BANNED:
                    if pattern.search(text[n - 1]):
                        hits.append(f"{path}:{n}: {why}")
    return Result("No banned patterns on added lines", not hits, "\n".join(hits[:10]) or "ok")


def check_tests_and_coverage(added) -> list[Result]:
    with tempfile.TemporaryDirectory() as tmp:
        cov_json = Path(tmp) / "cov.json"
        out = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--cov=app",
                   f"--cov-report=json:{cov_json}", "--cov-report="], timeout=900)
        summary = (out.stdout.strip().splitlines() or ["(no output)"])[-1]
        results = [Result("Full test suite", out.returncode == 0,
                          summary if out.returncode == 0 else out.stdout[-3000:])]
        if not cov_json.exists():
            return results + [Result("Diff coverage", False, "coverage report missing")]
        data = json.loads(cov_json.read_text(encoding="utf-8"))

    files = {k.replace("\\", "/"): v for k, v in data["files"].items()}
    covered = total = 0
    worst = []
    for path, lines in added.items():
        if not path.startswith("app/") or path.startswith("app/ui/") or not path.endswith(".py") \
                or path in COVERAGE_EXEMPT:
            continue
        info = files.get(path)
        if info is None:
            continue
        executable = set(info["executed_lines"]) | set(info["missing_lines"])
        mine = lines & executable
        hit = mine & set(info["executed_lines"])
        covered += len(hit)
        total += len(mine)
        if mine and len(hit) < len(mine):
            missing = sorted(mine - hit)
            worst.append(f"{path}: {len(hit)}/{len(mine)} (missing {_ranges(missing)})")
    pct = 100.0 * covered / total if total else 100.0
    detail = f"{pct:.1f}% of {total} new executable lines (min {DIFF_COVERAGE_MIN:.0f}%)"
    if worst:
        detail += "\n" + "\n".join(worst[:12])
    return results + [Result("Diff coverage (app/ excl. ui)", pct >= DIFF_COVERAGE_MIN, detail)]


def _ranges(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(out[:8]) + ("..." if len(out) > 8 else "")


def check_changelog(base, files) -> Result:
    log = git("log", "--format=%s", f"{base}..HEAD").splitlines()
    needs = any(s.startswith(("feat", "fix", "perf")) for s in log) or any(
        f.startswith("app/") for f in files)
    if not needs:
        return Result("Changelog updated", True, "no user-facing change")
    diff = git("diff", f"{base}...HEAD", "--", "docs/changelog.md") + git("diff", "HEAD", "--", "docs/changelog.md")
    unreleased_touched = bool(re.search(r"^\+[^+]", diff, re.M))
    return Result("Changelog updated", unreleased_touched,
                  "docs/changelog.md has new [Unreleased] entries" if unreleased_touched
                  else "app/ changed but docs/changelog.md was not updated")


# Bots allowed as commit authors (dependency PRs); their messages are still
# checked for conventional subjects and attribution text.
TRUSTED_BOT_AUTHORS = {
    ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
}


def check_commits(base) -> Result:
    problems = []
    for line in git("log", "--no-merges", "--format=%H%x1f%an%x1f%ae%x1f%s%x1f%b%x1e", f"{base}..HEAD").split("\x1e"):
        if not line.strip():
            continue
        sha, name, email, subject, body = (line.strip("\n").split("\x1f") + [""] * 5)[:5]
        short = sha[:7]
        if (name, email) != (GIT_NAME, GIT_EMAIL) and (name, email) not in TRUSTED_BOT_AUTHORS:
            problems.append(f"{short}: author {name} <{email}>")
        if not CONVENTIONAL.match(subject):
            problems.append(f"{short}: subject not conventional: {subject}")
        if re.search(r"co-authored-by|claude|anthropic", subject + "\n" + body, re.I):
            problems.append(f"{short}: attribution text in message")
    count = len([x for x in git("log", "--no-merges", "--format=%H", f"{base}..HEAD").split() if x])
    return Result("Commit hygiene (author, conventional, no attribution)", not problems,
                  "\n".join(problems) or f"{count} commits ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/dev")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    files = changed_files(args.base)
    added = added_lines(args.base)
    results = [
        check_syntax(),
        check_dead_code(files),
        check_complexity(files, added, args.base),
        check_banned(added),
        check_changelog(args.base, files),
        check_commits(args.base),
    ]
    if not args.skip_tests:
        results += check_tests_and_coverage(added)

    width = max(len(r.name) for r in results)
    print(f"\nQA gate: {len(files)} changed files vs {args.base}\n")
    for r in results:
        print(f"  [{'PASS' if r.ok else 'FAIL'}] {r.name.ljust(width)}")
        if not r.ok or r.name.startswith(("Diff coverage", "Full test")):
            for detail in r.detail.splitlines():
                print(f"         {detail}")
    passed = sum(r.ok for r in results)
    print(f"\n  {passed}/{len(results)} checks passed -> {'READY' if passed == len(results) else 'NOT READY'}\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
