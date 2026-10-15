"""The notebook's CFF and LTD paths share one native graph and energy convention."""

import pytest
from symbolica import Replacement, S
from symbolica.community import hepkit as hep


def test_cff_and_ltd_agree_for_triangle():
    diagram = (
        hep.Model.phi3()
        .process(["phi"], ["phi", "phi"])
        .generate_diagrams(loops=1, max_vertices=3, maximum_bridges=0, progress=None)
        .diagrams[0]
    )
    cff = diagram.integrate_energy(method="cff")
    ltd = diagram.integrate_energy(method="ltd")
    assert isinstance(cff, hep.CffRepresentation)
    assert isinstance(ltd, hep.LtdRepresentation)
    assert len(cff) > 0 and len(ltd) == 3
    q, cind, p0, p1 = S(
        "gammalooprs::Q", "spenso::cind", "energy_test::p0", "energy_test::p1"
    )
    external = [p0 + p1, p0, p1]
    routing = [
        Replacement(q(edge.id, cind(0)), external[edge.external_index])
        for edge in diagram.external_edges
    ]
    difference = (cff.to_expression() - ltd.to_expression()).replace_multiple(routing)
    assert difference.together().is_zero()
    polynomial = diagram.integrate_energy(
        method="cff", numerator=q(diagram.internal_edges[0].id, cind(0)) ** 2
    )
    assert isinstance(polynomial, hep.CffRepresentation)
    assert not polynomial.to_expression().is_zero()
    with pytest.raises(ValueError, match="cff.*ltd"):
        diagram.integrate_energy(method="unknown")
