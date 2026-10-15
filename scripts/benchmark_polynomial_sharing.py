#!/usr/bin/env python3
"""Exercise shared polynomial algorithms and the small inlineable paths."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from benchmark_release_size import measure


def main(output, cpu=None):
    if cpu is not None:
        os.sched_setaffinity(0, {cpu})
    import symbolica.core
    from symbolica import S

    variables = S(
        "sharing_bench::x",
        "sharing_bench::y",
        "sharing_bench::z",
        "sharing_bench::a",
        "sharing_bench::b",
        "sharing_bench::c",
        "sharing_bench::d",
        "sharing_bench::e",
        "sharing_bench::f",
    )
    x, y, z = variables[:3]
    alpha = S("sharing_bench::alpha")
    workloads = {}
    for label, options, scalar in [
        ("rational", {}, 1),
        ("prime32", {"modulus": 101}, 1),
        ("prime64", {"modulus": 4294967311}, 1),
        ("galois32", {"modulus": 101, "power": (2, alpha)}, alpha + 1),
        ("numberfield", {"minimal_poly": (alpha**2 - 2).to_polynomial()}, alpha + 1),
    ]:
        # Nine active variables prevent packed exponents and keep the dense box sparse.
        a, b, c, d, e, f = variables[3:]
        p = (
            (1 + scalar * x + 2 * y + 3 * z + a + b + c + d + e + f) ** 2
        ).to_polynomial(vars=variables, **options)
        q = ((2 + x * y + y * z + x * z + a * b + c * d + e * f) ** 2).to_polynomial(
            vars=variables, **options
        )
        univariate = (1 + scalar * x + x**2).to_polynomial(vars=[x], **options)
        product = p * q
        quotient, remainder = product.quot_rem(p)
        assert quotient - q == 0 and remainder == 0
        assert p**3 - (p * p) * p == 0
        univariate_reference = univariate * 0 + 1
        for _ in range(7):
            univariate_reference *= univariate
        assert univariate**7 - univariate_reference == 0
        assert p.gcd(p * 3) - p.gcd(p) == 0
        constant = (x * 0 + 7).to_polynomial(vars=variables, **options)
        monomial = (x * y**2).to_polynomial(vars=variables, **options)
        expected_constant = (x * 0 + 16807).to_polynomial(vars=variables, **options)
        assert constant**5 - expected_constant == 0
        assert (
            monomial**5 - (x**5 * y**10).to_polynomial(vars=variables, **options) == 0
        )
        factor_input = (
            (x + scalar * y + z + 1) * (x * y + y * z + 2) * (x**2 + z + 3)
        ).to_polynomial(**options)
        factors = factor_input.factor()
        reconstructed = factor_input * 0 + 1
        for factor, multiplicity in factors:
            reconstructed *= factor**multiplicity
        assert reconstructed - factor_input == 0
        workloads.update(
            {
                f"{label}_heap_multiply": lambda p=p, q=q: p * q,
                f"{label}_heap_divide": lambda product=product, p=p: product.quot_rem(
                    p
                ),
                f"{label}_heap_power": lambda p=p: p**3,
                f"{label}_univariate_heap_power": lambda p=univariate: p**7,
                f"{label}_simple_gcd": lambda p=p: p.gcd(p),
                f"{label}_constant_power": lambda p=constant: p**5,
                f"{label}_monomial_power": lambda p=monomial: p**5,
                f"{label}_factor": lambda p=factor_input: p.factor(),
            }
        )
    results = {name: measure(operation) for name, operation in workloads.items()}
    library = Path(symbolica.core.__file__)
    report = {
        "workloads": results,
        "correctness_checks_passed": True,
        "cpu_affinity": sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
    }
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cpu", type=int, help="Pin the process to one CPU on Linux")
    args = parser.parse_args()
    main(args.output, args.cpu)
