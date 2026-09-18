param(
    [ValidateSet("docs", "retrieval", "graphrag", "eval", "all")]
    [string]$Group = "all",
    [switch]$CloneServices,
    [switch]$CloneSources
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$ExtrasByGroup = @{
    docs = "external-docs"
    retrieval = "external-retrieval"
    graphrag = "external-graphrag"
    eval = "external-eval"
    all = "external-all"
}

$Extra = $ExtrasByGroup[$Group]
Push-Location $RepoRoot
try {
    & $Python -m pip install -e ".[$Extra]"

    $ExternalRepos = Join-Path $RepoRoot "external_repos"
    if ($CloneServices -or $CloneSources) {
        New-Item -ItemType Directory -Force -Path $ExternalRepos | Out-Null
    }

    if ($CloneServices -or $CloneSources) {
        $serviceRepos = @(
            @{ Name = "ragflow"; Url = "https://github.com/infiniflow/ragflow.git" },
            @{ Name = "lightrag"; Url = "https://github.com/HKUDS/LightRAG.git" }
        )
        foreach ($repo in $serviceRepos) {
            $target = Join-Path $ExternalRepos $repo.Name
            if (-not (Test-Path $target)) {
                git clone --depth 1 $repo.Url $target
            }
        }
    }

    if ($CloneSources) {
        $sourceRepos = @(
            @{ Name = "docling"; Url = "https://github.com/docling-project/docling.git" },
            @{ Name = "unstructured"; Url = "https://github.com/Unstructured-IO/unstructured.git" },
            @{ Name = "haystack"; Url = "https://github.com/deepset-ai/haystack.git" },
            @{ Name = "llama_index"; Url = "https://github.com/run-llama/llama_index.git" },
            @{ Name = "ragas"; Url = "https://github.com/vibrantlabsai/ragas.git" },
            @{ Name = "deepeval"; Url = "https://github.com/confident-ai/deepeval.git" }
        )
        foreach ($repo in $sourceRepos) {
            $target = Join-Path $ExternalRepos $repo.Name
            if (-not (Test-Path $target)) {
                git clone --depth 1 $repo.Url $target
            }
        }
    }
}
finally {
    Pop-Location
}
