from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _git_submodule_remote(name: str = "contracts") -> str:
    # Prefer parsing .gitmodules
    gm = REPO_ROOT / ".gitmodules"
    if gm.exists():
        txt = _read_text(gm)
        # Match only the URL value up to end-of-line within the submodule block
        block_re = re.compile(
            r"\[submodule \"" + re.escape(name) + r"\"\]([\s\S]*?)(?=\n\[|\Z)",
            re.M,
        )
        m_block = block_re.search(txt)
        if m_block:
            line_re = re.compile(r"^\s*url\s*=\s*(?P<url>\S+)", re.M)
            m_line = line_re.search(m_block.group(1))
            if m_line:
                return m_line.group("url").strip()
    # Fallback: git config from .gitmodules
    try:
        out = (
            subprocess.check_output(
                [
                    "git",
                    "config",
                    "--file",
                    str(gm),
                    f"submodule.{name}.url",
                ],
                cwd=str(REPO_ROOT),
            )
            .decode()
            .strip()
        )
        if out:
            return out.splitlines()[0].strip()
    except Exception:
        pass
    return ""


def _git_submodule_commit(name: str = "contracts") -> str:
    # Use git ls-tree to get the submodule commit pinned at HEAD
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "HEAD", name], cwd=str(REPO_ROOT)
        ).decode()
        # format: "160000 commit <sha>\tcontracts\n"
        parts = out.strip().split()
        if len(parts) >= 3:
            sha = parts[2]
            return sha[:7]
    except Exception:
        pass
    return ""


def _files_present() -> dict[str, bool]:
    schema = (REPO_ROOT / "contracts/schemas/manifest.schema.json").exists()
    # rule can live at root or under contracts/rules/
    rule = (REPO_ROOT / "promotion.rule.json").exists() or (
        REPO_ROOT / "contracts/rules/promotion.rule.json"
    ).exists()
    fixture = (REPO_ROOT / "contracts/fixtures/l2_fixture.parquet").exists() or (
        REPO_ROOT / "contracts/fixtures/l2_fixture.csv"
    ).exists()
    return {"schema": schema, "rule": rule, "fixture": fixture}


def _ci_checkout_submodules() -> bool:
    wf_dir = REPO_ROOT / ".github/workflows"
    if not wf_dir.exists():
        return False
    ok = True
    any_checkout = False
    files: list[pathlib.Path] = [*wf_dir.glob("*.yml"), *wf_dir.glob("*.yaml")]
    for p in files:
        txt = _read_text(p)
        if "uses: actions/checkout" in txt:
            any_checkout = True
            if "submodules: true" not in txt:
                ok = False
    return ok and any_checkout


def _cross_consume_workflow() -> bool:
    return (REPO_ROOT / ".github/workflows/cross-smoke-trading.yml").exists()


def _validator_cli_present() -> bool:
    return (REPO_ROOT / "src/tools/validate_export_manifest.py").exists()


def _fixture_schema_test_present() -> bool:
    return (REPO_ROOT / "tests/test_l2_fixture_schema.py").exists()


def _docs_link_contracts() -> dict[str, bool]:
    readme_txt = _read_text(REPO_ROOT / "README.md")
    copilot_txt = _read_text(REPO_ROOT / ".github/workflows/copilot-instructions.md")
    readme = ("contracts/" in readme_txt) or ("Contracts and Validator" in readme_txt)
    copilot = ("Contracts Governance" in copilot_txt) or ("ml-contracts" in copilot_txt)
    return {"readme": bool(readme), "copilot": bool(copilot)}


def _observability_keys_test() -> bool | None:
    p = REPO_ROOT / "tests/test_tool_observability.py"
    if not p.exists():
        return None
    txt = _read_text(p)
    need = ["run_id", "stage_latency_ms"]
    return all(k in txt for k in need)


def _tests_summary() -> dict[str, bool | None]:
    # Static presence-based summary (no execution to keep it fast).
    fixture_schema = _fixture_schema_test_present()
    validator_smoke = _validator_cli_present() and (
        (REPO_ROOT / "examples/tf1_export_manifest.sample.json").exists()
    )
    return {
        "fixture_schema": True if fixture_schema else None,
        "validator_smoke": True if validator_smoke else None,
    }


def main() -> None:
    data: collections.OrderedDict[str, object] = collections.OrderedDict()
    data["repo"] = REPO_ROOT.name
    data["submodule_remote"] = _git_submodule_remote("contracts")
    data["submodule_commit"] = _git_submodule_commit("contracts")
    data["files_present"] = _files_present()
    data["ci_checkout_submodules"] = _ci_checkout_submodules()
    data["cross_consume_workflow"] = _cross_consume_workflow()
    data["validator_cli_present"] = _validator_cli_present()
    data["fixture_schema_test_present"] = _fixture_schema_test_present()
    data["docs_link_contracts"] = _docs_link_contracts()
    data["observability_keys_test"] = _observability_keys_test()
    data["tests"] = _tests_summary()

    print(json.dumps(data))


if __name__ == "__main__":
    main()
