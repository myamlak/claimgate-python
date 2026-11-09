#!/usr/bin/env python3
"""The fresh-clone outsider check.

Clone this repository to a temporary directory and run the documented
commands from the clone, with no path into the original tree:

    python tools/outsider_check.py [--keep]

Exit status 0 when every documented command behaves as the README says, 1
otherwise.  The script does not need the network: the clone is local.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXAMPLES = (
    ("boost-airy", 1, {"exceeded": 4}),
    ("crlibm-sinh", 1, {"exceeded": 3, "verified": 1}),
    ("row-types", 1, {"exceeded": 1, "vacuous": 1, "evidence_absent": 1}),
    ("boys-gate", 0, {"verified": 29, "met_over_domain": 9}),
)


class Failure(Exception):
    pass


def run(command, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    return result


def check(condition, message):
    if not condition:
        raise Failure(message)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the temporary clone")
    args = parser.parse_args(argv)

    temp = Path(tempfile.mkdtemp(prefix="claimgate-outsider-"))
    clone = temp / "claimgate"
    reports = temp / "reports"
    reports.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    try:
        result = run(
            ["git", "clone", "--quiet", str(ROOT), str(clone)], cwd=temp, env=env
        )
        check(result.returncode == 0, f"git clone failed: {result.stderr.strip()}")
        check(clone.is_dir(), "the clone has no working tree")
        print(f"clone        : {clone}")

        files = sorted(
            str(path.relative_to(clone)).replace("\\", "/")
            for path in clone.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )
        print(f"checked out  : {len(files)} files")
        for required in (
            "README.md",
            "LICENSE",
            "schema/claimgate-book.schema.json",
            "claimgate/cli.py",
            "examples/boost-airy/book.json",
            "examples/boost-airy/data/boost_airy_reference.csv",
            "examples/crlibm-sinh/data/crlibm_sinh_reference.csv",
            "examples/boys-gate/anchor-slices/index.json",
            "tests/test_examples.py",
        ):
            check((clone / required).is_file(), f"the clone is missing {required}")

        # 1. The tool's own test suite, from the clone.
        result = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                     cwd=clone, env=env)
        check(
            result.returncode == 0,
            "the test suite failed:\n" + result.stderr[-4000:],
        )
        print("tests        : OK")

        # 2. Every example validates and runs with the documented exit status.
        for name, expected_status, expected_counts in EXAMPLES:
            book = f"examples/{name}/book.json"
            result = run([sys.executable, "-m", "claimgate", "validate", book],
                         cwd=clone, env=env)
            check(result.returncode == 0, f"{book}: validate failed: {result.stderr[-2000:]}")
            report_path = reports / f"{name}.json"
            result = run(
                [sys.executable, "-m", "claimgate", "run", book,
                 "--report", str(report_path)],
                cwd=clone,
                env=env,
            )
            check(
                result.returncode == expected_status,
                f"{book}: run exited {result.returncode}, the README says {expected_status}",
            )
            check(report_path.is_file(), f"{book}: no report written")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            check(report["exit_status"] == expected_status,
                  f"{book}: report exit_status disagrees with the process")
            for verdict, count in expected_counts.items():
                actual = report["summary"].get(verdict, 0)
                check(actual == count,
                      f"{book}: summary {verdict} is {actual}, the record says {count}")
            check(
                report["checks"]["anchors"]["failed"] == [],
                f"{book}: anchor check failed: {report['checks']['anchors']['failed']}",
            )
            check(
                report["checks"]["figures"]["failed"] == [],
                f"{book}: figure check failed: {report['checks']['figures']['failed']}",
            )
            check(
                report["checks"]["bindings"]["failed"] == [],
                f"{book}: binding check failed: {report['checks']['bindings']['failed']}",
            )
            print(
                f"{name:13s}: exit {expected_status}, "
                f"{report['summary']['met']} of {report['summary']['judged']} judged met, "
                f"anchors {report['checks']['anchors']['mode']}"
            )

        # 3. The boys run record is checked, not merely read.
        boys = json.loads((reports / "boys-gate.json").read_text(encoding="utf-8"))
        external = boys["checks"]["external_run"]
        check(external["exit_status"] == 0, "the boys external run exit status changed")
        check(external["failed"] == [], "the boys external run record failed its checks")
        check(boys["summary"]["met"] == 38, "the boys run did not meet 38 of 38")

        # 4. The two pilots reproduce the paper's witnesses.
        boost = json.loads((reports / "boost-airy.json").read_text(encoding="utf-8"))
        boost_rows = {row["id"]: row for row in boost["rows"]}
        bi = boost_rows["boost.airy.bi.a2_grid"]["worst"]["value"]
        ai = boost_rows["boost.airy.ai.named"]["worst"]["value"]
        check(abs(bi - 414.11089562284541) < 1e-9, f"the bi witness moved: {bi!r}")
        check(abs(ai - 121.39533957606637) < 1e-9, f"the ai witness moved: {ai!r}")
        crlibm = json.loads((reports / "crlibm-sinh.json").read_text(encoding="utf-8"))
        crlibm_rows = {row["id"]: row for row in crlibm["rows"]}
        check(crlibm_rows["crlibm.sinh.rn"]["verdict"] == "verified",
              "sinh_rn is no longer verified")
        check(crlibm_rows["crlibm.sinh.rz"]["failures"] == 2,
              "sinh_rz no longer has two mismatches")

        print("pilots       : the Airy and sinh witnesses reproduce")
        print("OUTSIDER CHECK: PASS")
        return 0
    except Failure as exc:
        print(f"OUTSIDER CHECK: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.keep:
            print(f"kept         : {temp}")
        else:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
