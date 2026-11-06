Optional benchmark-local extension directory.

If `registry.json` exists here, treat it as the compatibility contract for any local ranker hook that should be loaded before finalizing the search pipeline. The benchmark-local extension loader in `/workspace/workspace/rd3_plugin_loader_template.py` already understands this registry format and can be vendored into `parallel_solution.py` when you want the final artifact to keep extension loading behavior stable across reruns.
