"""Exercise the installed bundle and recoverable external-data boundary."""

import asyncio
import hashlib
import subprocess
import sys

from symbolica import data


def test_installed_data_matches_the_compiled_consumer_catalog():
    asyncio.run(data.prepare("render/fonts"))
    for asset in data.manifest()["assets"]:
        if asset["name"].startswith("render/fonts/"):
            payload = data.read(asset["name"])
            assert len(payload) == asset["size"]
            assert hashlib.sha256(payload).hexdigest() == asset["sha256"]
    # Numerical data remains text, including the original precision markers.
    expression = data.read("vakint/numerics/matad_numerics/0000.txt").decode()
    assert len(expression) > 80_000
    assert "`20096." in expression


def test_missing_or_corrupt_data_can_be_supplied_without_restarting(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from pathlib import Path
import sys
import symbolica_fonts
from symbolica import E, S, data

data.set_directory(sys.argv[1])
assert E('1/(1+x^2)').integrate(S('x')) == E('atan(x)')
name = 'render/fonts/NewCMMath-Book.otf'
for operation in [lambda: data.read(name), lambda: data.install(name, b'damaged')]:
    try:
        operation()
    except ValueError:
        pass
    else:
        raise AssertionError('Missing/corrupt resource was accepted')
assert not next(a for a in data.manifest()['assets'] if a['name'] == name)['loaded']
payload = (symbolica_fonts.directory() / name).read_bytes()
data.install(name, payload)
assert data.read(name) == payload
""",
            str(tmp_path),
        ],
        check=True,
    )
