= Native wheel size audit

The Linux x86-64 wheel at Community revision fd736475 is 88.97 MB compressed.
The extension accounts for 88.55 MB of that; Python sources, stubs, metadata,
licenses and examples account for about 0.42 MB.

== Installed extension

The stripped extension is 227.05 MB. Its principal ELF sections are:

#table(columns: 2,
  [Section], [Uncompressed MB],
  [Executable code], [182.19],
  [Read-only data], [22.32],
  [Exception and unwind tables], [16.37],
  [Dynamic relocations], [3.41],
  [Read-only data containing pointers], [2.33],
)

The audit binary retains symbols for inspection. Those symbol tables are removed
from the wheel; their size must not be added to the installed extension.

== Definition attribution

#table(columns: 2,
  [Definition owner], [Uncompressed code MB],
  [Symbolica], [68.51],
  [Rubi / symbolica-integrate], [27.74],
  [core and alloc generic helpers], [18.81],
  [RustRed core], [6.24],
  [Spenso], [5.48],
  [Numerica], [3.92],
  [AMFlow], [3.26],
  [Typst library], [2.75],
  [Idenso], [2.45],
  [Vakint], [2.12],
  [Graphica], [1.93],
)

These are definition owners, not the crates that instantiated every generic.
Folded aliases count once. Core and alloc templates can originate in any
consumer. Per-crate code bytes are uncompressed and do not directly partition
compressed wheel bytes.

Polynomial algebra accounts for about 55.55 MB of Symbolica's code. The raw Rust
v0 names show copies of the same polynomial functions instantiated in Vakint,
RustRed, AMFlow, FeynKit, Hyperbolica and one-loop reduction. Several large
heap-powering, Hensel lifting and GCD routines occur 6--11 times. Repeated names
are opportunities for inspection; their specialized bodies can differ.

Rubi source changes are handled by another worker. This audit leaves its rules,
algorithms and bindings unchanged.

== Trials

+ Size-oriented compilation of 19 rendering packages: wheel 88.42 MB, a 0.56 MB
  saving. Warm four-fermion process rendering measured 3.72 ms versus 3.38 ms.
  Offline QCD, two-loop diagrams, cross sections, networks and Typst rendering
  passed. The small saving does not justify these package overrides by default.
+ Forced cross-crate generic sharing, keeping O3 and ThinLTO: wheel 67.76 MB.
  The code section falls to 149.06 MB and Symbolica-defined code falls from
  68.51 MB to 25.07 MB. Large repeated polynomial functions fall from 6--11
  copies to typically one or two. All 19 focused checks and offline rendering
  passed. The measured CPU cost rises about 7--22% for most workloads and 48%
  for the small tensor trace. This uses the unstable share-generics compiler
  option as a local experiment; the stable default remains unchanged.
  Alternating fresh-process first integration medians are 170.6 ms with sharing
  and 163.9 ms for the current build (five processes per build).

+ Fat LTO at O3, with the existing inlining budget: wheel 91.12 MB, larger
  than ThinLTO. Representative computations are about 0--7% faster, but
  the build takes 38 minutes and maximum process RSS is 15.77 GB.

+ Forced sharing plus fat LTO: wheel 75.24 MB. It recovers much of the
  lost runtime performance: expansion is approximately unchanged, derivative
  is about 9% faster, GCD is 3% slower, rational cancel 15% slower, integration
  7% slower, tensor trace 18% slower and finite RustRed reduction 6% slower,
  relative to the current ThinLTO build. All 19 focused checks and offline
  rendering passed. The shared kernel remains O3, and this variant still
  requires the unstable sharing flag. Fresh-process first integration medians
  are 167.2 ms versus 165.0 ms for the current build (five per build).

== Reproduction

Keep the locked dependencies and build a complete Community wheel. The audit
needs an unstripped library; append `-- -C strip=none` to maturin build. Then run
`python scripts/report_native_size.py target/release/libsymbolica_community.so
--wheel dist/symbolica-*.whl --output reports/native-size.json` with GNU nm and
readelf available. Benchmark each complete wheel in a separate environment with
`python scripts/benchmark_release_size.py reports/performance.json --cpu N`.
Use the same CPU and alternate fresh processes for rule-loading measurements.

#link("https://doc.rust-lang.org/cargo/reference/profiles.html#overrides-and-generics")[Cargo profiles and generics]
explains Rust's default policy of disabling cross-crate generic sharing at
optimization levels 2 and 3. Forced sharing changes which crate provides the
implementation before LLVM LTO. ThinLTO uses module summaries and selective
function importing; it can recover some cross-module optimization, but sharing
can remove caller-specific specialization opportunities. This explanation is
consistent with the measurements, rather than a demonstrated attribution of
each slowdown.

#link("https://clang.llvm.org/docs/ThinLTO.html")[LLVM ThinLTO design]
