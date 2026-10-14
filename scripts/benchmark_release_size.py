#!/usr/bin/env python3
"""Measure representative computations and first integration in a fresh process."""

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path


def measure(operation, samples=9):
    operation()
    iterations = 1
    while True:
        start = time.perf_counter()
        for _ in range(iterations):
            operation()
        elapsed = time.perf_counter() - start
        if elapsed >= 0.05 or iterations >= 4096:
            break
        iterations *= 2
    timings = []
    cpu_timings = []
    for _ in range(samples):
        start = time.perf_counter()
        cpu_start = time.process_time()
        for _ in range(iterations):
            operation()
        cpu_timings.append(1000 * (time.process_time() - cpu_start) / iterations)
        timings.append(1000 * (time.perf_counter() - start) / iterations)
    return {
        "median_ms": statistics.median(timings),
        "samples_ms": timings,
        "median_cpu_ms": statistics.median(cpu_timings),
        "cpu_samples_ms": cpu_timings,
        "iterations": iterations,
    }


def main(output, cpu=None):
    if cpu is not None:
        os.sched_setaffinity(0, {cpu})

    import symbolica.core
    from symbolica import E, S
    from symbolica.community import hepkit as hep
    from symbolica.community.tensor import (
        Representation,
        Tensor,
        TensorLibrary,
        TensorName,
        TensorNetwork,
    )

    x, y, z = S("size_bench::x", "size_bench::y", "size_bench::z")
    primitive_input = 1 / (1 + x**2)
    start = time.perf_counter()
    cpu_start = time.process_time()
    primitive = primitive_input.integrate(x)
    cold_cpu_ms = 1000 * (time.process_time() - cpu_start)
    cold_ms = 1000 * (time.perf_counter() - start)
    assert primitive == x.atan()
    assert (primitive.derivative(x) - primitive_input).cancel() == E("0")

    expansion = E(
        "(1+size_bench::x+size_bench::y+size_bench::z+size_bench::a+size_bench::b)^12"
    )
    expanded = expansion.expand()
    derivative = expanded.derivative(x)
    common = (
        ((x + 2 * y + 3 * z + 1) ** 3 * (x + y * z + 4) ** 2).expand().to_polynomial()
    )
    left = common * (x**3 + y**2 + z + 3).to_polynomial()
    right = common * (x + y**3 + z**2 + 5).to_polynomial()
    assert left.gcd(right) == common
    rational = E(
        "((size_bench::x+size_bench::y+1)^6*(size_bench::x^2+size_bench::z+3))/((size_bench::x+size_bench::y+1)^6*(size_bench::y^2+size_bench::z+5))"
    )
    cancelled = rational.cancel()
    integrands = [x.cos(), x * x.sin(), 1 / (1 + x**2), x**3 * x.exp(), (1 + x) ** -2]
    primitives = [expression.integrate(x) for expression in integrands]
    for expression, answer in zip(integrands, primitives):
        assert (answer.derivative(x) - expression).expand().cancel() == E("0")
    rep = Representation.euc(8)
    tensor = Tensor.dense(
        TensorName("size_bench::matrix")(rep, rep),
        [E(str(index)) for index in range(64)],
    )
    library = TensorLibrary.hep_lib()
    library.register(tensor)

    def tensor_trace():
        network = TensorNetwork(tensor.expression()(1, 1), library=library)
        network.execute(library=library)
        return list(network.result_tensor(library=library))

    trace = tensor_trace()
    assert trace == [E("252")]
    model = hep.Model.phi3()
    process = model.process(["phi"], ["phi", "phi"])
    generation = process.generate_diagrams(
        loops=1, max_vertices=3, allow_self_loops=False
    )
    assert generation.report.completed and len(generation) > 0
    d, k = S("size_bench::d", "size_bench::k")
    kin = hep.Kinematics(d, momenta=[k])
    family = hep.IBPFamily(
        hep.IntegralFamily([k], [], [kin.scalar_product(k, k) - 1], kinematics=kin)
    )
    laporta = family.reduce_laporta([[3]], max_depth=1)
    assert (laporta.reduce([3])[0][1] - (d - 2) * (d - 4) / 8).together() == E("0")

    workloads = {
        "expand_degree12_5vars": lambda: expansion.expand(),
        "differentiate_expanded": lambda: expanded.derivative(x),
        "multivariate_gcd": lambda: left.gcd(right),
        "rational_cancel": lambda: rational.cancel(),
        "integrate_5_expressions": lambda: [
            expression.integrate(x) for expression in integrands
        ],
        "tensor_trace_8x8": tensor_trace,
        "generate_one_loop_phi3": lambda: process.generate_diagrams(
            loops=1, max_vertices=3, allow_self_loops=False
        ),
        "rustred_finite_reduction": lambda: family.reduce_laporta([[3]], max_depth=1),
    }
    results = {name: measure(operation) for name, operation in workloads.items()}
    assert expansion.expand() == expanded
    assert expanded.derivative(x) == derivative
    assert rational.cancel() == cancelled
    assert tensor_trace() == trace
    library = Path(symbolica.core.__file__)
    report = {
        "first_integration_ms": cold_ms,
        "first_integration_cpu_ms": cold_cpu_ms,
        "workloads": results,
        "native_library": str(library),
        "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "cpu_affinity": sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        "correctness_checks_passed": True,
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cpu", type=int, help="Pin the process to one CPU on Linux")
    args = parser.parse_args()
    main(args.output, args.cpu)
