# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PowerRAG Windows desktop launcher.

Not Electron. Bundles the existing FastAPI console and static frontend.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent

FIRST_PARTY_PACKAGES = (
    "chroma_rag_poc",
    "core_domain",
    "data_pipeline",
    "domain_packs",
    "fmea_application",
    "fmea_infrastructure",
    "knowledge_base",
    "kg_pipeline",
    "model_adapters",
    "rag_orchestrator",
    "retrieval_engine",
    "storage_layer",
    "structured_output_application",
    "structured_output_infrastructure",
    "workflow_runtime",
)

THIRD_PARTY_COLLECT = (
    "chromadb",
    "chromadb_rust_bindings",
    "fastapi",
    "starlette",
    "uvicorn",
    "anyio",
    "h11",
    "pydantic",
    "pydantic_core",
    "orjson",
    "jwt",
    "cryptography",
    "jieba",
    "yaml",
    "multipart",
    "python_multipart",
    "rank_bm25",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "tokenizers",
    "onnxruntime",
    "rapidocr_onnxruntime",
    "pypdf",
    "fitz",
    "docx",
    "openpyxl",
    "PIL",
    "certifi",
    "charset_normalizer",
    "requests",
    "tqdm",
    "numpy",
    "sklearn",
    "scipy",
    "torch",
    "networkx",
    "igraph",
    "leidenalg",
    "jsonschema",
    "posthog",
)

datas: list = []
binaries: list = []
hiddenimports: list[str] = [
    "chroma_rag_poc.api",
    "chroma_rag_poc.pipeline",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "tkinter",
]


def _add_dir(src: Path, dest: str) -> None:
    if src.exists():
        datas.append((str(src), dest))


def _add_package_dir(module_name: str, dest: str | None = None) -> None:
    """Collect a package directory even when `import module` fails."""
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception:
        return
    if spec is None or not spec.origin:
        return
    pkg_dir = Path(spec.origin).parent
    if pkg_dir.is_dir():
        _add_dir(pkg_dir, dest or module_name)


_add_dir(REPO_ROOT / "frontend_app" / "current_console", "frontend_app/current_console")
_add_dir(REPO_ROOT / "configs" / "fmea", "configs/fmea")
_add_dir(REPO_ROOT / "templates" / "examples", "templates/examples")
_add_dir(REPO_ROOT / "domain_packs", "domain_packs")
_add_dir(REPO_ROOT / "kg_pipeline" / "poc", "kg_pipeline/poc")
# chromadb 0.5.x can fail collect_all() on NumPy 2 (np.float_ removed).
_add_package_dir("chromadb")
_add_package_dir("chromadb_rust_bindings")

for package in FIRST_PARTY_PACKAGES:
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        hiddenimports.append(package)

for package in THIRD_PARTY_COLLECT:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Deduplicate while keeping order.
seen_hidden: set[str] = set()
unique_hidden: list[str] = []
for name in hiddenimports:
    if name not in seen_hidden:
        seen_hidden.add(name)
        unique_hidden.append(name)
hiddenimports = unique_hidden

block_cipher = None

a = Analysis(
    [str(SPEC_DIR / "power_rag_desktop.py")],
    pathex=[
        str(REPO_ROOT),
        str(REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "electron",
        "IPython",
        "notebook",
        "jupyter",
        "matplotlib.tests",
        "tkinter.test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PowerRAG",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PowerRAG",
)
