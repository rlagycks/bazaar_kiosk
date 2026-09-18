"""4B1: stored strings must reach the screen as text, never as markup or code.

Menu names, table names and order notes are operator input that arrives through
the JSON API and is written into the page by JavaScript. Where that is done by
building an HTML string, a name like `<img src=x onerror=...>` executes; where
it is interpolated into an inline `onclick` attribute, a name containing a
quote both breaks the button and executes.

These are source-level tests. They cannot prove a page is safe -- a browser
does that, and the run is recorded in docs/modernization/CONTENT_SECURITY.md --
but they pin the property a later edit would quietly lose: the live templates
build nodes and set text, and never assemble markup from data.
"""

import re

from django.test import Client, TestCase
from django.urls import reverse

from orders.tests.auth_support import login_client

TEMPLATES = "orders/templates/orders/"

# The templates a view actually renders. serve.html is deliberately absent and
# is covered by test_the_unused_template_is_still_unreferenced below.
LIVE_TEMPLATES = ("order.html", "b1_counter.html", "kitchen_supervisor.html")

# Templates converted to safe DOM building in 4B1. kitchen_supervisor.html
# escapes every interpolated value instead; it keeps its own test below.
CONVERTED_TEMPLATES = ("order.html", "b1_counter.html")


def read(name):
    from django.conf import settings

    return (settings.BASE_DIR / TEMPLATES / name).read_text(encoding="utf-8")


class TemplateSourceTests(TestCase):
    def test_no_live_template_uses_an_inline_event_attribute(self):
        """An inline handler puts data inside a JavaScript string inside an HTML
        attribute. Two escaping contexts, one `\\'` replacement, and a menu name
        with a quote or a backslash is enough to break out of both."""
        # Every `on*` attribute, not a list of the ones used today: reviving
        # this with `onmouseover=` would otherwise pass. No legitimate
        # attribute in these templates starts with "on".
        for name in LIVE_TEMPLATES:
            with self.subTest(template=name):
                found = re.findall(r"\son[a-z]+\s*=", read(name))
                self.assertEqual(found, [], f"{name} still wires events in markup")

    def test_the_converted_templates_never_assign_innerhtml(self):
        """textContent cannot execute anything. innerHTML with interpolated data
        is the whole of BK-R011, and a later edit that reintroduces one is
        exactly what this test exists to fail on."""
        for name in CONVERTED_TEMPLATES:
            with self.subTest(template=name):
                self.assertNotIn("innerHTML", read(name))
                self.assertNotIn("insertAdjacentHTML", read(name))

    def test_the_converted_templates_use_the_shared_dom_helper(self):
        for name in CONVERTED_TEMPLATES:
            with self.subTest(template=name):
                self.assertIn("ui/dom.js", read(name))

    def test_the_kitchen_board_escapes_every_value_it_interpolates(self):
        """The kitchen board builds markup but escapes each value. That is a
        different mitigation, not an exemption: if a raw interpolation appears
        next to one of these fields, this fails."""
        source = read("kitchen_supervisor.html")
        for field in ("item.menu_item_name", "tableLabel", "note", "statusText"):
            with self.subTest(field=field):
                self.assertIn(f"escapeHtml({field})", source)
        # The only innerHTML assignments left are the board itself and fixed
        # placeholder strings; none may interpolate a value.
        for assignment in re.findall(r"innerHTML\s*=\s*([^\n;]+)", source):
            with self.subTest(assignment=assignment.strip()):
                self.assertNotIn("${", assignment)

    def test_the_shared_helper_refuses_event_and_script_url_attributes(self):
        """The guarantee belongs in the helper, not in every future call site:
        setAttribute('onclick', ...) compiles a handler exactly like markup."""
        from django.conf import settings

        helper = (settings.BASE_DIR / "orders/static/orders/ui/dom.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("Event attributes are not allowed", helper)
        self.assertIn("javascript:", helper)

    def test_the_shared_helper_never_touches_innerhtml(self):
        from django.conf import settings

        helper = (settings.BASE_DIR / "orders/static/orders/ui/dom.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("innerHTML", helper)

    def test_the_unused_template_is_still_unreferenced(self):
        """serve.html renders data the unsafe way and no view uses it. Removing
        it is step 11's cleanup; until then this fails if something starts
        rendering it, which would put an unconverted page back on screen."""
        from django.conf import settings

        # Application code only: this module names the template on purpose.
        sources = [settings.BASE_DIR / "orders/urls.py"]
        sources += sorted((settings.BASE_DIR / "orders/views").glob("*.py"))
        for path in sources:
            with self.subTest(path=path.name):
                self.assertNotIn("serve.html", path.read_text(encoding="utf-8"))


class RenderedPageTests(TestCase):
    """The pages still render, with the helper actually loaded."""

    def test_the_order_page_loads_the_dom_helper(self):
        client = Client()
        login_client(client, "ORDER")
        response = client.get(reverse("orders:order"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui/dom.js")

    def test_the_counter_page_loads_the_dom_helper(self):
        client = Client()
        login_client(client, "B1_COUNTER")
        response = client.get(reverse("orders:b1-counter"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui/dom.js")


class ApiPayloadTests(TestCase):
    """What the page receives is JSON, not markup: the API must not be the
    place a payload becomes safe, but it must not mangle a legitimate name
    either. A menu called "A&W <cola>" has to survive the round trip."""

    def setUp(self):
        from orders.models import MenuItem

        self.client = Client()
        login_client(self.client, "ORDER")
        MenuItem.objects.create(
            name='<img src=x onerror="alert(1)">', price=1000, visible_kitchen=True
        )
        MenuItem.objects.create(name="A&W <cola>", price=2000, visible_kitchen=True)

    def test_names_are_returned_verbatim_as_json(self):
        response = self.client.get(reverse("orders:menus"), {"scope": "KITCHEN"})
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.json()["items"]}
        self.assertIn('<img src=x onerror="alert(1)">', names)
        self.assertIn("A&W <cola>", names)
        self.assertEqual(response["Content-Type"], "application/json")
