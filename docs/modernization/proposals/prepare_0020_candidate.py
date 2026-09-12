"""Prepare a disposable candidate copy; do not modify application source files."""

from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    repo = Path(__file__).resolve().parents[3]
    proposals = Path(__file__).resolve().parent
    output = repo / ".venv" / "phase-1b"
    output.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix="0020-candidate-", dir=output))
    for name in ("orders", "bazaar_kiosk"):
        shutil.copytree(repo / name, candidate / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(repo / "manage.py", candidate / "manage.py")
    source = repo / "orders/migrations/0020_create_floor_sequences.py"
    original = source.read_bytes()
    shutil.copy2(source, candidate / "orders/tests/original_0020.py")
    shutil.copy2(proposals / "test_0020_candidate.py", candidate / "orders/tests/test_candidate.py")
    subprocess.run(
        ["patch", "-p1", "-i", str(proposals / "0020-empty-sequence.patch")],
        cwd=candidate, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    if source.read_bytes() != original:
        raise RuntimeError("Original migration unexpectedly changed")
    print(candidate)


if __name__ == "__main__":
    main()
