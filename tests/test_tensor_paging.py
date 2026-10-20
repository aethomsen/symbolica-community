"""Automatic MathML paging must bound work and preserve the source expression."""

import importlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from symbolica import E, MathMLViewer, S
from symbolica.community.tensor import Representation, TensorExpression, TensorName


def polynomial(n=301):
    return E("+".join(f"{i + 1}*page_test::x^{i}" for i in range(n)))


def formatted_viewer(expression):
    """Capture the viewer created by the real native formatted-output factory."""
    viewers = []

    def create(*args, **kwargs):
        viewer = MathMLViewer(*args, **kwargs)
        viewers.append(viewer)
        return viewer

    with patch("_symbolica_paging.MathMLViewer", side_effect=create):
        expression.formatted()._repr_mimebundle_(include=["text/html"])
    assert len(viewers) == 1
    return viewers[0]


def assert_page(page):
    assert "Page rendering failed" not in page["html"], page["html"]
    assert len(page["html"].encode()) <= 256 * 1024
    math = re.findall(r"<math\b.*?</math>", page["html"], re.DOTALL)
    assert math
    roots = [ET.fromstring(m) for m in math]
    assert sum(sum(1 for _ in root.iter()) for root in roots) <= 10_000
    assert len(json.dumps(page).encode()) <= 512 * 1024
    assert "tree" not in page and "notation" not in page
    for root in roots:
        # The tensor root adds notation CSS ownership, without changing layout.
        root.attrib.pop("data-spenso-math", None)
    return roots


@pytest.fixture
def compiler():
    # The native provider loads its compiler lazily, on the first page request.
    TensorName("page_test::compiler")(Representation.mink(4)("mu")).paged()._page()
    return importlib.import_module("_spenso_paging")


def test_pages_are_contiguous_bounded_and_reversible():
    value = TensorExpression(polynomial())
    original = value.to_expression()
    pager = value.paged(page_size=100)
    assert type(pager) is MathMLViewer
    pages = []
    while True:
        page = pager._page()
        assert_page(page)
        pages.append((page["start"], page["end"]))
        if page["next"] is None:
            break
        pager._action({"action": "next"})
    assert pages[0][0] == 0 and pages[-1][1] == 301
    assert all(a[1] == b[0] for a, b in zip(pages, pages[1:]))
    for start, end in reversed(pages[:-1]):
        page = pager._action({"action": "previous"})
        assert (page["start"], page["end"]) == (start, end)
    assert value.to_expression() == original
    pager.close()
    with pytest.raises(RuntimeError, match="closed"):
        pager._page()


def test_nested_sums_keep_factors_and_subexpression_navigation():
    left, right = (
        polynomial(201),
        polynomial(203).replace(S("page_test::x"), S("page_test::y")),
    )
    value = TensorExpression(7 * left * right)
    before = value.to_expression()
    pager = value.paged()
    page = pager._page()
    assert_page(page)
    assert page["kind"] == "Product" and page["total"] == 3
    assert "<mn>7</mn>" in page["html"]
    assert "data-symbolica-marker" in page["html"]
    compact = page["layouts"][-1]
    assert_page(compact)
    target = next(path for path, label in compact["markers"] if "sum" in label)
    assert len(target) == 1 and target[0] < page["total"]
    child = pager._action(
        {"action": "open", "value": target, "layout": compact["layout"]}
    )
    assert_page(child)
    assert child["back"]
    assert child["kind"] == "Sum" and child["total"] in (201, 203)
    pager._action({"action": "size", "value": 100})
    parent = pager._action({"action": "back"})
    assert parent["page_size"] == 25
    assert parent["html"] == page["html"]
    assert value.to_expression() == before


def test_automatic_and_formatted_outputs_are_bounded():
    value = TensorExpression(polynomial(2001))
    assert value.paged()._page()["end"] == 25
    assert len(str(value)) < 200
    for output in (value, value.formatted()):
        html = output._repr_html_()
        assert len(html.encode()) < 270_000
        assert "Navigation requires a live notebook" in html
        assert "items 1–25 of 2001" in html
        bundle = output._repr_mimebundle_(include=["text/plain", "text/html"])
        assert set(bundle) == {"text/plain", "text/html"}
        assert len(bundle["text/plain"]) < 200
    assert value.to_expression() == polynomial(2001)


def test_hover_previews_only_the_omitted_tail_and_keeps_main_navigation():
    value = TensorExpression(polynomial(301))
    original, structure = value.to_expression(), value.structure
    viewer = value.paged()
    first = viewer._page()
    target = next(
        path
        for (path, _), start in zip(first["markers"], first["marker_starts"])
        if start == first["end"]
    )
    field, hover = viewer._message(
        {"action": "preview", "value": target, "request": "hover"}
    )
    assert field == "preview" and hover["request"] == "hover"
    assert_page(hover)
    assert hover["start"] == first["end"]
    assert 0 < hover["end"] - hover["start"] <= 5
    assert hover["can_expand"] and first["supports_expansion"]
    assert viewer._page() == first

    _, popup = viewer._message(
        {"action": "preview", "value": target, "popup": True, "size": 100}
    )
    assert_page(popup)
    assert popup["start"] == 0 and popup["end"] <= 100
    assert popup["total"] == 301
    assert viewer._page() == first
    assert value.to_expression() == original and value.structure == structure


def test_small_notebook_output_uses_shared_viewer_and_export_stays_complete():
    small = TensorExpression(E("a+b"))
    assert type(small.paged()) is MathMLViewer
    assert "<math" in small._repr_html_()
    assert "Navigation requires" not in small._repr_html_()
    assert not small.paged()._page()["markers"]
    large = TensorExpression(polynomial(101))
    assert "Navigation requires" not in large.to_html()
    assert len(large.to_html()) > 1000


def test_missing_widget_dependency_static_preview_and_disposal(compiler):
    pager = TensorExpression(polynomial()).paged()
    with patch.dict(sys.modules, {"anywidget": None}):
        bundle = pager._repr_mimebundle_()
    assert set(bundle) == {"text/plain", "text/html"}
    widget = pager._get_widget()
    assert len(widget.page["html"].encode()) <= 256 * 1024
    pager._on_message(widget, {"action": "attach", "view": "test"}, [])
    first = pager._page()
    pager._on_message(widget, {"action": "dispose", "view": "test"}, [])
    assert pager._widget is None
    assert pager._page() == first
    recreated = pager._get_widget()
    assert recreated is not widget
    assert recreated.page == first
    pager.close()


def test_renderer_failure_does_not_fall_back_to_full_output(compiler):
    value = TensorName("page_failure::T")(Representation.mink(4)("mu"))
    pager = value.paged()
    with patch.object(compiler, "compile_leaf", side_effect=TimeoutError("deadline")):
        page = pager._page()
    assert "Page rendering failed" in page["html"]
    assert len(page["html"]) < 1000
    assert value.rank == 1


def test_native_page_budget_bounds_work_and_rejects_invalid_navigation():
    value = TensorExpression(polynomial(1001))
    pager = value.paged(page_size=500)
    for layout in range(8):
        page = pager._render_page(layout)
        assert_page(page)
        assert 0 < page["end"] <= 500
        assert page["total"] == 1001
    assert pager._render_page(0)["end"] < 500
    with pytest.raises(ValueError):
        pager._action({"action": "size", "value": 1000000})
    with pytest.raises(ValueError):
        pager._action({"action": "open", "value": [123456789, 0]})


def test_oversized_function_has_bounded_argument_navigation():
    # A single term exceeds the node budget; entering it pages its arguments.
    value = TensorExpression(
        E("page_test::f(" + ",".join(f"a{i}" for i in range(3000)) + ")")
    )
    before = value.to_expression()
    pager = value.paged(page_size=100)
    page = pager._page()
    assert_page(page)
    assert page["unit"] == "arguments" and page["total"] == 3000
    assert page["end"] <= 100
    assert value.to_expression() == before
    page = pager._action({"action": "next"})
    assert_page(page)
    assert page["start"] == 100


def test_signs_and_tensor_ports_survive_pages():
    from symbolica.community.tensor import Representation, TensorName

    rep = Representation.mink(4)
    tensor = TensorName("page_test::T")
    # Fix the logical interface before selecting any sum fragment.
    value = sum(
        (-1) ** i * E(f"page_test::z^{i}") * tensor(rep("mu"), rep("nu"))
        for i in range(130)
    )
    before = value.to_expression()
    pager = value.paged(page_size=25)
    first = pager._page()
    assert_page(first)
    assert "<mtext>mu</mtext>" in first["html"] and "<mtext>nu</mtext>" in first["html"]
    assert "−" in first["html"]
    second = pager._action({"action": "next"})
    assert_page(second)
    assert (
        "<mtext>mu</mtext>" in second["html"] and "<mtext>nu</mtext>" in second["html"]
    )
    assert value.to_expression() == before
    assert pager._action({"action": "previous"})["html"] == first["html"]


def test_serialized_page_never_contains_undisplayed_terms(compiler):
    pager = TensorExpression(polynomial(6001)).paged(page_size=25)
    # Scalar arithmetic belongs entirely to the shared native renderer.
    with patch.object(compiler, "compile_leaf", wraps=compiler.compile_leaf) as render:
        page = pager._page()
    assert_page(page)
    assert page["end"] == 25 and page["total"] == 6001
    assert not render.called
    assert len(page["html"].encode()) < 64 * 1024
    assert "6001" not in page["html"]
    assert "5999" not in page["html"]
    assert page["markers"] and page["marker_starts"] == [25]


@pytest.mark.parametrize(
    "source",
    [
        "(a+b*c^2)*(d+e+f+g+h)/(j+k)",
        "f(a+b+c+d+e,g(h+i),j^2)",
        "+".join(f"parity::x{i}^2" for i in range(301)),
        "(" + "+".join(f"parity::x{i}" for i in range(41)) + ")*(a+b+c)",
    ],
)
def test_scalar_tensor_and_expression_use_identical_responsive_layouts(source):
    value = TensorExpression(E(source))
    original, structure = value.to_expression(), value.structure
    tensor_viewer, expression_viewer = value.paged(), formatted_viewer(original)
    try:
        for layout in range(8):
            tensor_page = tensor_viewer._render_page(layout)
            expression_page = expression_viewer._render_page(layout)
            assert [ET.tostring(root) for root in assert_page(tensor_page)] == [
                ET.tostring(root) for root in assert_page(expression_page)
            ]
            for field in (
                "start",
                "end",
                "total",
                "kind",
                "unit",
                "markers",
                "marker_ids",
                "marker_starts",
                "layout",
            ):
                assert tensor_page[field] == expression_page[field], (layout, field)
        assert tensor_viewer._page()["supports_expansion"]
        assert value.to_expression() == original and value.structure == structure
    finally:
        tensor_viewer.close()
        expression_viewer.close()


def test_jupyter_bundle_contains_live_widget_and_bounded_fallbacks():
    value = TensorExpression(polynomial(1001))
    for output in (value, value.formatted()):
        bundle = output._repr_mimebundle_()
        assert "application/vnd.jupyter.widget-view+json" in bundle
        assert len(bundle["text/plain"]) < 200
        assert len(bundle["text/html"].encode()) < 270_000


def test_page_source_can_serve_jupyter_comm_thread():
    from concurrent.futures import ThreadPoolExecutor

    pager = TensorExpression(polynomial(301)).paged()
    with ThreadPoolExecutor(max_workers=1) as worker:
        page = worker.submit(pager._page).result(timeout=15)
    assert_page(page)


def test_three_rung_ladder_pages_keep_factorization_and_budgets():
    """The 6,001-term example that formerly produced 380,000 MathML nodes."""
    from symbolica import Graph
    from symbolica.community.hepkit import Model

    target = Graph()
    for _ in range(8):
        target.add_node(0)
    target.add_node(-1)
    target.add_node(2)
    for i in range(8):
        target.add_edge(i, (i + 1) % 8, data=21)
    for i, j in ((1, 7), (2, 6), (3, 5), (0, 8), (4, 9)):
        target.add_edge(i, j, data=21)
    target = target.canonize()[0]

    def accept(graph, completed):
        if completed < len(graph):
            return True
        if len(graph) != 10 or graph.num_edges() != 13:
            return False
        for edge in range(graph.num_edges()):
            graph.set_directed(edge, False)
        return graph.canonize()[0] == target

    model = Model.qcd()
    diagram = model.process(["g"], ["g"], vertex_allow=["V_36"]).generate_diagrams(
        loops=4, max_vertices=8, filter=accept
    )[0]
    dimension = S("paging_ladder::D")
    numerator = TensorExpression(
        model.expand_couplings(
            diagram.numerator_expression(in_lmb=True).to_expression()
        )
    ).with_lorentz_dimension(dimension)
    slots = [slot.dual() for slot in numerator.structure.slots()]
    projector = (
        TensorExpression.g(slots[0], slots[1])
        * TensorExpression.g(slots[2], slots[3])
        / 8
    )
    value = (
        (projector * numerator)
        .simplify_algebra(
            contract="dots", color_substitute_cof_dimension_invariants=True
        )
        .expand()
        .collect_factors()
        .collect_num()
    )
    original = value.to_expression()
    pager = value.paged()
    outline = pager._page()
    target = None
    for candidate in reversed([outline, *outline["layouts"]]):
        for path, label in candidate["markers"]:
            if "sum" not in label:
                continue
            _, preview = pager._message(
                {"action": "preview", "value": path, "layout": candidate["layout"]}
            )
            assert_page(preview)
            if preview["total"] == 6001:
                target = path, candidate["layout"]
                break
        if target is not None:
            break
    assert target is not None, "The factorized ladder retains its 6,001-term sum"
    pager._action({"action": "open", "value": target[0], "layout": target[1]})
    end = 0
    for _ in range(8):
        page = pager._page()
        assert_page(page)
        assert page["total"] == 6001
        assert page["start"] == end
        assert 0 < page["end"] - page["start"] <= 25
        end = page["end"]
        pager._action({"action": "next"})
    assert value.to_expression() == original


def test_generated_index_names_survive_cache_eviction():
    from symbolica.community.tensor import TensorName, TensorStructure

    TensorName("page_indices::v")
    TensorName("page_indices::w")
    left, right, rep = S("page_indices::v", "page_indices::w", "spenso::mink")
    expression = sum(
        left(rep(4, S(f"page_indices::i{i}", tags=["spenso::dummy-index"])))
        * right(rep(4, S(f"page_indices::i{i}", tags=["spenso::dummy-index"])))
        for i in range(130)
    )
    # Establish the scalar interface before display, preserving the dummy names.
    value = TensorExpression(expression, structure=TensorStructure([]))
    original = value.to_expression()
    pager = value.paged(page_size=25)
    first = pager._page()["html"]
    for _ in range(4):
        assert_page(pager._action({"action": "next"}))
        for layout in (7, 0):
            assert_page(pager._render_page(layout))
    for _ in range(4):
        assert_page(pager._action({"action": "previous"}))
    assert pager._page()["html"] == first
    assert value.to_expression() == original


def test_oversized_tensor_leaf_defers_to_bounded_structural_children(compiler):
    rep = Representation.mink(4)
    value = TensorName("page_oversized::T")(rep("mu"), rep("nu"))
    original = value.to_expression()
    pager = value.paged()
    with patch.object(compiler, "compile_leaf", return_value=None) as render:
        page = pager._page()
    assert render.called
    native = formatted_viewer(original)._page()
    assert [ET.tostring(root) for root in assert_page(page)] == [
        ET.tostring(root) for root in assert_page(native)
    ]
    assert page["kind"] == "Function" and page["unit"] == "arguments"
    assert value.to_expression() == original


def test_two_expanded_binomials_share_responsive_layout_and_inline_expansion():
    value = TensorExpression((E("x+1") ** 100).expand() * (E("y+1") ** 100).expand())
    original = value.to_expression()
    viewer = value.paged()
    page = viewer._page()
    assert page["kind"] == "Product" and page["total"] == 2
    assert page["supports_expansion"]
    assert "Expression structure" not in page["html"]
    for layout in range(8):
        page = viewer._render_page(layout)
        assert_page(page)
        assert page["total"] == 2
        math = re.findall(r"<math\b.*?</math>", page["html"], re.DOTALL)
        assert len(math) == 1
        assert "data-symbolica-path" in math[0]
        assert value.to_expression() == original
    compact = viewer._page()["layouts"][-1]
    target = next(path for path, label in compact["markers"] if "sum" in label)
    expanded = viewer._action(
        {
            "action": "expand",
            "value": target,
            "layout": compact["layout"],
            "size": 25,
        }
    )
    assert_page(expanded)
    assert not expanded["back"]
    expanded_compact = viewer._render_page(compact["layout"])
    assert sum(len(list(root.iter())) for root in assert_page(expanded_compact)) > sum(
        len(list(root.iter())) for root in assert_page(compact)
    )
    assert value.to_expression() == original


def test_dot_product_power_keeps_compact_tensor_notation():
    from symbolica.community.tensor import Representation, TensorName, dot

    rep = Representation.mink(4)
    left = TensorName.vector("page_power::k")(rep)
    right = TensorName.vector("page_power::p")(rep)
    value = dot(left, right) ** 2
    page = value.paged()._page()
    assert_page(page)
    math = ET.fromstring(
        re.search(r"<math\b.*?</math>", page["html"], re.DOTALL).group()
    )
    # Dot operands are vector labels; the exponent applies to their contraction.
    operators = [n.text for n in math.iter() if n.tag.rsplit("}", 1)[-1] == "mo"]
    assert "(" not in operators and ")" not in operators
    assert any(n.tag.rsplit("}", 1)[-1] == "msup" for n in math.iter())
