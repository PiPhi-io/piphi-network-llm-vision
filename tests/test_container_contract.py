import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_container_declares_release_provenance() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert dockerfile.count("@sha256:") == 2
    assert "COPY pyproject.toml pdm.lock ./" in dockerfile
    assert "pdm export --prod" in dockerfile
    assert 'org.opencontainers.image.source="${SOURCE_REPOSITORY}"' in dockerfile
    assert 'org.opencontainers.image.revision="${SOURCE_REVISION}"' in dockerfile
    assert 'org.opencontainers.image.version="${RELEASE_VERSION}"' in dockerfile


def test_container_declares_non_root_writable_ledger() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    container = manifest["runtime"]["linux"]["container"]

    assert "useradd --create-home --uid 10001 piphi" in dockerfile
    assert "chown -R piphi:piphi /data/piphi" in dockerfile
    assert 'VOLUME ["/data/piphi"]' in dockerfile
    assert "USER piphi" in dockerfile
    assert container["environment"]["PIPHI_AUTOMATION_LEDGER_PATH"].startswith("/data/piphi/")
    assert container["volumes"] == [
        {
            "host": "/var/lib/piphi/llm-vision",
            "container": "/data/piphi",
            "mode": "rw",
        }
    ]
