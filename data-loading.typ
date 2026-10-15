= External data bundle

The native and WASM engines retain a small catalog of asset names, exact sizes,
SHA-256 digests and descriptions. Large payloads live in `symbolica-fonts` and `symbolica-vakint-data`.
The remaining data bundle contains numerical expressions, RustRed programs and
FORM resources; their paths and descriptions allow further splitting later.

== Building and installing

From the Community root, resolve the locked dependencies and run:

```sh
python scripts/build_data_bundle.py --out dist
```

The builder reads each resolved crate's `package.metadata.symbolica-data`
declaration. It produces extracted `dist/fonts` and `dist/vakint-data` directories, manifests with
descriptions and source identities, two universal resource wheels, and the small
`src/data_assets.rs` expectations catalog. Regenerate and commit the catalog
whenever resource contents change. CI uses `--check-catalog` to require matching
sources without rewriting those expectations.

Install the engine and its matching data wheels together. The resource wheels
own disjoint `symbolica/_data/fonts/` and `symbolica/_data/vakint-data/`
directories; they do not install or overwrite the engine's Python modules.
No path configuration is needed: ordinary import automatically
locates the installed resources; it does not read their large payloads or access
the network. A missing resource reports which package to install and its pip
command. Standalone Rust callers can configure `symbolica_data::Data::set_directory`
or set `SYMBOLICA_DATA_DIRECTORY` to one or more extracted bundles separated by
the platform path separator. `Data::set_directories` accepts multiple roots.

== Supplying data

```python
from symbolica import data

data.set_directories("/path/to/fonts", "/path/to/vakint-data")
await data.prepare("render/fonts")

await data.prepare("vakint/rustred", source="https://example.org/data/")
program = data.read("vakint/rustred/unit_mass_vacuum_k6.rrbin")
```

Applications can also call `data.install(name, payload)` with bytes supplied by
their host. Rust verifies size and digest before caching or exposing them to
native mathematical decoders. Missing or damaged payloads are never cached;
the same operation can be retried after installing valid data. Source hashes
preserve every digit and precision marker in the extracted numerical tables.

== Browser execution

Pyodide installs the same fonts wheel with `micropip`; Vakint data can be
installed separately when a supported RustRed consumer needs it. Explicit HTTP preparation
uses `pyfetch`; computation and rendering do not perform network requests.
Only requested resources are transferred into the shared runtime cache. The
default browser file cache is session-local. An application can mount persistent
browser storage and pass its directory through `cache_dir`.

The target-independent catalog allows WASM to authenticate and read native
RustRed artifacts without compiling the native-only Vakint backend. Reading
bytes does not establish codec compatibility or mathematical applicability;
the consumer must retain its existing schema, family and proof checks.

Numerical-table and font extraction does not change formulas, rounding, master
coverage, reduction rules or rendering variants. Four-loop programs retain
candidate status. This change supplies existing data; recomputation requires a
separate registered producer recipe and validation of its outputs.

== Online and offline fonts

+ Normal notebook MathML uses STIX Two Math from its configured CDN.
+ `load_math_font()` loads the WOFF2 asset to make MathML work without that CDN.
+ Native and WASM Typst rendering always needs local font files to measure text
  and generate SVG glyph paths, even when the browser has CDN fonts available.
