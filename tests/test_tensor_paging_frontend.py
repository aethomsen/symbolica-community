"""Exercise Symbolica's actual shared widget with the native tensor provider."""

import os
import re

import pytest
from symbolica import E, MathMLViewer
from symbolica.community.tensor import Representation, TensorName

pw = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser_page():
    with pw.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                **(
                    {"executable_path": os.environ["CHROMIUM_EXECUTABLE"]}
                    if "CHROMIUM_EXECUTABLE" in os.environ
                    else {}
                )
            )
        except pw.Error as error:
            pytest.skip(f"Chromium unavailable: {error}")
        try:
            yield browser.new_page(viewport={"width": 1600, "height": 1000})
        finally:
            browser.close()


def mount_viewer(page, viewer):
    widget = viewer._get_widget()
    page.set_content('<div id="viewer"></div>')
    page.evaluate(
        """async ({esm, page}) => {
        const module = await import(URL.createObjectURL(new Blob([esm], {type:'text/javascript'})));
        // Live notebook widgets render inside a shadow root, where :root
        // variables from the tensor stylesheet are unavailable.
        const root = document.querySelector('#viewer').attachShadow({mode:'open'});
        const element = document.createElement('div');
        root.appendChild(element);
        const fields = {page, preview:{}}, callbacks = new Map();
        window.messages = [];
        window.setField = ([name, value]) => {
            fields[name] = value;
            for (const callback of callbacks.get(`change:${name}`) || []) callback();
        };
        window.callbackCount = () => [...callbacks.values()].reduce((n,s)=>n+s.size,0);
        window.dispose = module.default.render({el:element, model:{
            get:name=>fields[name], send:message=>messages.push(message),
            on:(name, callback)=>{
                if (!callbacks.has(name)) callbacks.set(name,new Set());
                callbacks.get(name).add(callback);
            },
            off:(name, callback)=>callbacks.get(name)?.delete(callback)
        }});
    }""",
        {"esm": widget._esm, "page": viewer._page()},
    )
    page.evaluate("async () => { await document.fonts.ready; }")
    return widget, page.locator("#viewer")


def test_shared_widget_hover_paging_stale_previews_zoom_and_disposal(browser_page):
    rep = Representation.mink(4)
    tensor = TensorName("frontend_page::T")(rep("mu"), rep("nu"))
    value = sum(E(f"frontend_page::x^{i}") * tensor for i in range(201))
    original, structure = value.to_expression(), value.structure
    viewer = value.paged(page_size=25)
    assert type(viewer) is MathMLViewer

    page = browser_page
    widget, host = mount_viewer(page, viewer)
    main = host.locator(".math-content")

    def main_html():
        # Preview accessibility state changes without changing the math.
        return main.evaluate("""element => {
            const copy = element.cloneNode(true);
            for (const node of copy.querySelectorAll('button.omission')) {
                for (const name of ['aria-describedby', 'aria-expanded', 'aria-controls']) {
                    node.removeAttribute(name);
                }
            }
            return copy.innerHTML;
        }""")

    page.evaluate("async () => { await document.fonts.ready; }")
    first_html = main_html()
    assert page.evaluate("callbackCount()") == 2
    attach = page.evaluate("messages[0]")
    viewer._on_message(widget, attach, [])
    assert attach["action"] == "attach"
    assert main.locator("math").count() == 1
    assert main.locator(":scope > math").count() == 1
    assert main.locator(":scope > div[data-spenso-math]").count() == 0
    assert '"STIX Two Math"' in main.locator("math").evaluate(
        "element => getComputedStyle(element).fontFamily"
    )
    assert "mu" in main.inner_text() and "nu" in main.inner_text()

    # Hover asks for only the omitted tail, while keeping the main page intact.
    marker = main.locator("button.omission").last
    marker.hover()
    page.wait_for_function("messages.at(-1).action === 'preview'")
    request = page.evaluate("messages.at(-1)")
    field, hover = viewer._message(request)
    assert field == "preview" and not request["popup"]
    assert hover["start"] == viewer._selected_page({"layout": request["layout"]})["end"]
    assert hover["end"] - hover["start"] <= 5
    page.evaluate("setField", [field, hover])
    tooltip = host.get_by_role("tooltip")
    assert tooltip.is_visible()
    assert "mu" in tooltip.inner_text() and "nu" in tooltip.inner_text()
    assert main_html() == first_html

    marker.click()
    request = page.evaluate("messages.at(-1)")
    assert request["action"] == "preview" and request["popup"]
    field, popup = viewer._message(request)
    dialog = host.get_by_role("dialog")
    assert marker.get_attribute("aria-expanded") == "true"
    assert marker.get_attribute("aria-controls") == dialog.get_attribute("id")
    # A delayed hover response must not replace a newer pinned popup.
    page.evaluate("setField", ["preview", hover])
    assert dialog.get_attribute("aria-busy") == "true"
    assert "Loading preview" in dialog.inner_text()
    page.evaluate("setField", [field, popup])
    next_button = dialog.get_by_role("button", name="Next", exact=True)
    for _ in range(4):
        before = dialog.locator(".preview-math").inner_html()
        next_button.click()
        assert next_button.is_disabled()
        request = page.evaluate("messages.at(-1)")
        field, following = viewer._message(request)
        page.evaluate("setField", ["preview", popup])
        assert next_button.is_disabled()
        assert dialog.locator(".preview-math").inner_html() == before
        page.evaluate("setField", [field, following])
        assert dialog.locator(".preview-math math").count() == 1
        assert dialog.locator(".preview-math math *").count() < 10_000
        assert "mu" in dialog.inner_text() and "nu" in dialog.inner_text()
        assert main_html() == first_html
        popup = following

    dialog.get_by_role("button", name="Inspect", exact=True).click()
    request = page.evaluate("messages.at(-1)")
    assert request["action"] == "open"
    field, inspected = viewer._message(request)
    page.evaluate("setField", [field, inspected])
    assert inspected["back"]
    host.get_by_role("button", name="Next", exact=True).click()
    page.evaluate("setField", viewer._message(page.evaluate("messages.at(-1)")))
    assert main.locator("math").count() == 1
    host.get_by_role("button", name="Back to parent").click()
    page.evaluate("setField", viewer._message(page.evaluate("messages.at(-1)")))
    assert main_html() == first_html

    expression = host.get_by_role("region", name="Expression", exact=True)
    expression.focus()
    expression.press("=")
    assert main.evaluate("e=>e.style.getPropertyValue('--expression-zoom')") == "1.25"
    expression.press("-")
    assert main.evaluate("e=>e.style.getPropertyValue('--expression-zoom')") == "1"
    expression.press("=")
    expression.press("0")
    assert main.evaluate("e=>e.style.getPropertyValue('--expression-zoom')") == "1"

    page.evaluate("dispose()")
    assert page.evaluate("callbackCount()") == 0
    dispose = page.evaluate("messages.at(-1)")
    assert dispose == {"action": "dispose", "view": attach["view"]}
    viewer._on_message(widget, dispose, [])
    assert viewer._widget is None
    assert host.locator("math").count() == 0
    assert value.to_expression() == original and value.structure == structure
    viewer.close()


def test_responsive_width_fit_and_inline_expansion_keep_tensor_notation(browser_page):
    rep = Representation.mink(4)
    tensor = TensorName("responsive_page::T")(rep("mu"), rep("nu"))
    left = E("+".join(f"left{i:02}" for i in range(18)))
    right = E("+".join(f"right{i:02}" for i in range(19)))
    value = tensor * left * right
    original, structure = value.to_expression(), value.structure
    viewer = value.paged()
    page = browser_page
    widget, host = mount_viewer(page, viewer)
    viewer._on_message(widget, page.evaluate("messages[0]"), [])
    main = host.locator(".math-content")
    host.evaluate("element => { element.style.width = '1400px'; }")
    page.wait_for_function(
        """() => {
        const content = document.querySelector('#viewer').shadowRoot.querySelector('div').shadowRoot.querySelector('.math-content');
        return content.dataset.layout !== undefined;
    }"""
    )
    wide_layout = int(main.get_attribute("data-layout"))
    wide_requests = page.evaluate("messages.length")
    host.evaluate("element => { element.style.width = '350px'; }")
    page.wait_for_function(
        """wide => {
        const content = document.querySelector('#viewer').shadowRoot.querySelector('div').shadowRoot.querySelector('.math-content');
        return Number(content.dataset.layout) > wide;
    }""",
        arg=wide_layout,
    )
    assert page.evaluate("messages.length") == wide_requests
    assert main.evaluate(
        "element => element.scrollWidth <= element.parentElement.clientWidth + 2"
    )
    assert "mu" in main.inner_text() and "nu" in main.inner_text()
    assert main.locator("math").count() == 1
    assert main.locator("[data-symbolica-path]").count() > 1
    assert main.locator(":scope > math").count() == 1
    assert main.locator(":scope > div[data-spenso-math]").count() == 0

    marker = main.get_by_role("button", name=re.compile(r"^Open sum")).first
    before = main.locator("math *").count()
    marker.click()
    request = page.evaluate("messages.at(-1)")
    assert request["action"] == "preview" and request["popup"]
    page.evaluate("setField", viewer._message(request))
    dialog = host.get_by_role("dialog")
    expand = dialog.get_by_role("button", name="Show more here", exact=True)
    assert expand.is_visible() and expand.is_enabled()
    expand.click()
    request = page.evaluate("messages.at(-1)")
    assert request["action"] == "expand"
    field, expanded = viewer._message(request)
    assert field == "page" and "error" not in expanded
    page.evaluate("setField", [field, expanded])
    assert main.locator("math *").count() > before
    assert not expanded["back"]
    assert "mu" in main.inner_text() and "nu" in main.inner_text()
    assert main.locator("math").count() == 1
    assert main.locator("math *").count() <= 10_000
    assert value.to_expression() == original and value.structure == structure
    page.evaluate("dispose()")
    viewer._on_message(widget, page.evaluate("messages.at(-1)"), [])
    viewer.close()
