= Selective polynomial sharing

Sharing 19 large polynomial algorithm bodies reduces the Linux x86-64 wheel
from 88.97 MB to 74.57 MB. This saves 14.40 MB (16.2%) and retains 67.9% of
the size saving from blanket generic sharing. The large rational-power slowdown
found in the initial prototype is eliminated by preserving heap powering's
original source and caller specialization.

Compilation remains O3 with ThinLTO, one codegen unit, the existing inlining
budget and safe identical-code folding. The prototype needs stable source
attributes, with no unstable compiler flags.

== Implementation

The patch marks large GCD, interpolation, heap multiplication/division, Hensel
lifting and factorization routines inline(never). It extracts the full public
GCD algorithm behind a small inlineable wrapper, preserving the simple-GCD
fast path. Arithmetic helpers retain their existing specialization. The final
patch adds 25 lines across three kernel files; algorithm statements are unchanged.

Each shared body remains specialized for its concrete coefficient and exponent
types. Rust reuses an upstream exported instantiation for the same types.
The compiler rule is present in both Rust 1.96 (the declared minimum) and the
Rust 1.98 compiler used for the builds. See the
#link("https://github.com/rust-lang/rust/blob/1.98.0/compiler/rustc_middle/src/ty/instance.rs#L188-L203")[upstream lookup rule]
and the
#link("https://github.com/rust-lang/rust/blob/1.98.0/compiler/rustc_codegen_ssa/src/back/symbol_export.rs#L305-L314")[export rule].

The initial 20-body prototype also shared heap powering. Its wheel was 73.98 MB,
but the nine-variable rational-power probe repeatedly cost 6.6% more CPU.
Preserving heap powering costs just 0.59 MB and restores that performance.
The initial source patch, complete measurements and symbol audit are retained
separately with the 20-bodies filename suffix.

== Size and runtime

The stripped extension falls from 227.05 MB to 191.41 MB. Executable code
falls from 182.19 MB to 148.01 MB. The unstripped 20-body audit showed Symbolica
definitions falling from 68.51 MB to 35.91 MB, while Rubi stayed at 27.74 MB.
Function ownership was not re-audited after preserving heap powering; the
final ELF section sizes are measured directly from the selected wheel's binary.
Rubi source and generated rules are unchanged.

Fresh comparisons on CPU 34 give these representative CPU timings:

#table(columns: 3,
  [Workload], [Baseline ms], [Selected ms],
  [Expansion], [10.783], [10.721],
  [Derivative], [8.281], [8.281],
  [Multivariate GCD], [0.285], [0.290],
  [Rational cancellation], [0.00493], [0.00491],
  [Five integrations], [69.667], [67.783],
  [Tensor trace], [0.04863], [0.04926],
  [RustRed reduction], [0.05829], [0.05971],
  [Sparse rational power, three fresh processes], [21.198], [21.010],
)

The polynomial benchmark exercises nine active variables to force sparse heap
multiplication/division, multivariate powers, univariate heap powers, factorization,
simple GCD, constant powers and monomial powers. The five coefficient domains
are rationals, 32-/64-bit prime fields, a quadratic Galois field and a quadratic
rational number field, with nontrivial algebraic coefficients in the latter two.
All 40 workload fixtures pass their answer checks. Powers are cross-checked
against repeated multiplication. The larger operations range from 8.8% faster
to 1.3% slower in this run. Sub-microsecond fast-path timings include substantial
Python overhead.

Alternating five fresh processes per build gives first-integration wall-time
medians of 165.29 ms and 165.01 ms. The measured rule-loading latency is preserved.
Each environment runs serially; all timing samples, CPU affinity and library
hashes are retained in selective-polynomial-sharing-20261014.json.

== Validation and reproduction

The complete selected Community extension passed 19 focused Python checks and
offline QCD, 48 two-loop diagrams, cross-section, tensor-network and Typst
rendering checks. The patched kernel passed its wasm32-unknown-emscripten
compilation check with wasm features. All 319 polynomial unit cases pass:
318 run together serially, and the projective large-coefficient case runs in
a fresh process using the same test binary. That case stalls after preceding
tests in combined parallel and serial runs, but passes immediately in a fresh
process on both original and modified binaries. Tests alter global algorithm
settings; their contribution to this interaction was not isolated. No test
assertions were changed.

The portable source patch is selective-polynomial-sharing-20261014.patch,
based on kernel revision 1deccb8538ccb91dc2c1e58fc0a2e900d2276bf4. The local
source snapshot is de91afe168f81e384b6feaad1f980568e7f477cf. Apply the patch
to an isolated kernel checkout and use a local Community dependency override
for the trial. Build the complete wheel with the existing release profile.
Install it into a private environment together with the fonts and Vakint data
wheels, then run scripts/benchmark_release_size.py and
scripts/benchmark_polynomial_sharing.py on the same CPU. Run environments
serially, and alternate fresh processes for startup and short consumer probes.

Community's published dependency pins remain unchanged; this review contains
the portable source prototype and its measurements. Local manifest overrides
were restored before committing. Reports and source patches are excluded from
release distributions.
