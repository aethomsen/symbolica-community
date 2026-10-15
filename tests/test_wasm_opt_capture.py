"""Exercise optimizer selection and captured replay commands without compiling."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]
PASS = "--duplicate-function-elimination"


@pytest.mark.parametrize("selected, enabled, already_present", [
    (True, "1", False),
    (True, "1", True),
    (True, "0", False),
    (False, "1", False),
])
def test_capture_changes_only_selected_module(tmp_path, selected, enabled, already_present):
    optimizer = tmp_path / "wasm-opt"
    optimizer.write_text(f"#!{sys.executable}\n" + """
import json
import os
from pathlib import Path
import sys
arguments = sys.argv[1:]
Path(os.environ['TEST_OPTIMIZER_RECORD']).write_text(json.dumps(arguments))
output = Path(arguments[arguments.index('-o') + 1])
output.write_bytes(b'\\0asm' + b'optimized')
""")
    optimizer.chmod(0o755)
    source = tmp_path / ("symbolica_community.wasm" if selected else "dependency.wasm")
    source.write_bytes(b"\0asmoriginal")
    output = tmp_path / "output.wasm"
    record = tmp_path / "arguments.json"
    capture = tmp_path / "capture"
    arguments = ["--post-emscripten", "-O3", str(source), "-o", str(output)]
    if already_present:
        arguments.append(PASS)
    env = dict(os.environ, REAL_WASM_OPT=str(optimizer),
               WASM_OPT_CAPTURE_DIR=str(capture),
               WASM_OPT_CAPTURE_INPUT_NAME="symbolica_community.wasm",
               WASM_OPT_FORCE_LEVEL="-O0", WASM_OPT_DEDUPLICATE_FUNCTIONS=enabled,
               TEST_OPTIMIZER_RECORD=str(record))
    subprocess.run([sys.executable, str(ROOT / "scripts/capture_wasm_opt.py"), *arguments],
                   check=True, capture_output=True, text=True, env=env, timeout=10)
    actual = json.loads(record.read_text())
    if not selected:
        assert actual == arguments
        assert not capture.exists()
        return
    assert "-O0" in actual and "-O3" not in actual
    assert actual.count(PASS) == int(enabled == "1" or already_present)
    invocation = json.loads((capture / "invocation.json").read_text())
    assert invocation["arguments"] == arguments
    assert invocation["effective_arguments"] == actual
    assert json.loads((capture / "baseline-invocation.json").read_text()) == [str(optimizer), *actual]
    assert (capture / "input-0.wasm").read_bytes() == source.read_bytes()
    assert (capture / "output.wasm").read_bytes() == output.read_bytes()
