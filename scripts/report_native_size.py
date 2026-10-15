#!/usr/bin/env python3
"""Attribute ELF code by demangled definition owner, counting folded aliases once.

Use an unstripped release library for function attribution. The byte counts are
uncompressed code, not individual crates' contributions to the compressed wheel.
Generic helpers reported under core/alloc may be instantiated by any consumer.
"""

import argparse
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile


def report(library, wheel=None):
    sections = {}
    headers = subprocess.check_output(["readelf", "-SW", str(library)], text=True)
    for line in headers.splitlines():
        match = re.search(
            r"\]\s+(\.\S+)\s+\S+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)", line
        )
        if match:
            sections[match[1]] = int(match[2], 16)

    process = subprocess.Popen(
        ["nm", "-S", "--demangle", str(library)],
        stdout=subprocess.PIPE,
        text=True,
    )
    functions = collections.defaultdict(set)
    repeated = collections.defaultdict(set)
    for line in process.stdout:
        parts = line.split(maxsplit=3)
        if len(parts) != 4 or parts[2] not in {"t", "T"}:
            continue
        address, size, _, name = parts
        name = name.strip()
        size = int(size, 16)
        if size:
            key = (int(address, 16), size)
            functions[key].add(name)
            repeated[name].add(key)
    if process.wait():
        raise RuntimeError("nm failed")
    if not functions:
        raise ValueError(
            "No function symbols: build with rustc argument '-C strip=none'"
        )

    # The optional v0 instantiating-crate suffix is hidden by the demangler.
    # This scan covers explicit suffixes, not backreferences or legacy mangling.
    instantiators = collections.Counter()
    instantiated = set()
    raw = subprocess.Popen(
        ["nm", "-S", "--no-demangle", str(library)],
        stdout=subprocess.PIPE,
        text=True,
    )
    for line in raw.stdout:
        parts = line.split(maxsplit=3)
        if len(parts) != 4 or parts[2] not in {"t", "T"}:
            continue
        address, size, _, name = parts
        match = re.search(r"Cs[0-9A-Za-z]+_([0-9]+)([A-Za-z_]+)$", name.strip())
        key = (int(address, 16), int(size, 16))
        if match and len(match[2]) == int(match[1]) and key not in instantiated:
            instantiators[match[2]] += key[1]
            instantiated.add(key)
    if raw.wait():
        raise RuntimeError("nm raw-symbol scan failed")

    owners = collections.Counter()
    largest = []
    for (address, size), names in functions.items():
        categories = set()
        for name in names:
            match = re.match(r"<?([a-zA-Z_][a-zA-Z_0-9]*)::", name)
            categories.add(match[1] if match else "other")
        owner = next(iter(categories)) if len(categories) == 1 else "shared_aliases"
        owners[owner] += size
        largest.append({"bytes": size, "names": sorted(names), "address": hex(address)})

    repeats = []
    for name, copies in repeated.items():
        if len(copies) > 1:
            total = sum(size for address, size in copies)
            repeats.append(
                {
                    "name": name,
                    "copies": len(copies),
                    "bytes": total,
                    "bytes_beyond_largest_copy": total
                    - max(size for address, size in copies),
                }
            )
    digest = hashlib.sha256()
    with library.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    result = {
        "library": str(library),
        "library_bytes": library.stat().st_size,
        "library_sha256": digest.hexdigest(),
        "elf_sections": sections,
        "definition_owner_bytes": dict(owners.most_common()),
        "explicit_instantiating_crate_bytes": dict(instantiators.most_common()),
        "unique_function_bytes": sum(size for address, size in functions),
        "unique_functions": len(functions),
        "repeated_function_names": len(repeats),
        "largest_functions": sorted(largest, key=lambda r: r["bytes"], reverse=True)[
            :30
        ],
        "repeated_names": sorted(repeats, key=lambda r: r["bytes"], reverse=True)[:30],
        "notes": [
            "Owners describe definitions; generic core/alloc helpers are not attributed to consumers.",
            "Folded aliases count once; cross-owner aliases have their own category.",
            "Repeated names are candidates for inspection; specialized bodies can differ.",
            "Instantiating-crate counts cover explicit v0 suffixes only, not all code.",
            "Section sizes include alignment; function sizes exclude most padding.",
            "Function attribution is uncompressed and cannot be added to compressed wheel sizes.",
        ],
    }
    if wheel:
        with ZipFile(wheel) as archive:
            result["wheel"] = {
                "path": str(wheel),
                "bytes": wheel.stat().st_size,
                "largest_members": [
                    {
                        "path": entry.filename,
                        "bytes": entry.file_size,
                        "compressed_bytes": entry.compress_size,
                    }
                    for entry in sorted(
                        archive.infolist(),
                        key=lambda entry: entry.compress_size,
                        reverse=True,
                    )[:10]
                ],
            }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = report(args.library, args.wheel)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Native code: {result['elf_sections'].get('.text', 0) / 1e6:.2f} MB")
    for owner, size in list(result["definition_owner_bytes"].items())[:15]:
        print(f"  {owner}: {size / 1e6:.2f} MB")
