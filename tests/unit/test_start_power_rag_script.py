import os
import shutil
import subprocess
from pathlib import Path


def test_start_script_installs_node_dependencies_when_electron_is_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    temp_repo = tmp_path / "PowerRAG"
    scripts_dir = temp_repo / "scripts"
    fake_bin = tmp_path / "bin"
    npm_log = tmp_path / "npm.log"

    scripts_dir.mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(repo_root / "scripts" / "Start-PowerRAG.ps1", scripts_dir / "Start-PowerRAG.ps1")
    (temp_repo / "package.json").write_text('{"scripts":{"desktop":"electron ."}}\n', encoding="utf-8")

    (fake_bin / "npm.cmd").write_text(
        "@echo off\r\n"
        "echo %*>> \"%POWER_RAG_NPM_LOG%\"\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["POWER_RAG_NPM_LOG"] = str(npm_log)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts_dir / "Start-PowerRAG.ps1"),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert npm_log.read_text(encoding="utf-8").splitlines() == [
        "install --no-audit --fund=false",
        "run desktop",
    ]
