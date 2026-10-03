"""Presentation contracts for login and the reusable permission-aware menu."""
from html.parser import HTMLParser
from itertools import combinations
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils.html import escape

from orders.roles import HALL_MONITOR, SERVING, STATS, TAKEOUT_MONITOR
from orders.views.pages import _account_context


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def find(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


class AccountMenuTemplateTests(SimpleTestCase):
    def render_menu(self, permissions=(), name="김바자"):
        request = RequestFactory().get("/orders/order/")
        request.auth_permissions = frozenset(permissions)
        request.auth_account = SimpleNamespace(name=name)
        return render_to_string("orders/_account_menu.html", _account_context(request), request=request)

    def test_all_permission_combinations_show_only_available_destinations(self):
        permissions = (SERVING, HALL_MONITOR, TAKEOUT_MONITOR, STATS)
        destinations = {
            SERVING: "order", HALL_MONITOR: "kitchen-hall",
            TAKEOUT_MONITOR: "kitchen-takeout", STATS: "b1-counter",
        }
        for count in range(5):
            for held in combinations(permissions, count):
                with self.subTest(permissions=held):
                    expected = {reverse("orders:" + destinations[p]) for p in held}
                    if HALL_MONITOR in held and TAKEOUT_MONITOR in held:
                        expected.add(reverse("orders:kitchen"))
                    actual = {a["href"] for a in Elements(self.render_menu(held)).find("a")}
                    self.assertEqual(actual, expected)

    def test_account_name_is_text_and_logout_is_a_csrf_protected_post(self):
        name = '<img src=x onerror="alert(1)">'
        html = self.render_menu((STATS,), name=name)
        elements = Elements(html)
        self.assertIn(str(escape(name)), html)
        self.assertEqual(elements.find("img"), [])
        form, = elements.find("form")
        self.assertEqual(form["method"], "post")
        self.assertEqual(form["action"], reverse("orders:logout"))
        csrf, = [i for i in elements.find("input") if i.get("name") == "csrfmiddlewaretoken"]
        self.assertTrue(csrf["value"])
        dialog, = elements.find("dialog")
        self.assertEqual(dialog["id"], "account-menu")
        self.assertIn('id="' + dialog["aria-labelledby"] + '"', html)


class LoginTemplateTests(SimpleTestCase):
    def render_login(self, **context):
        return render_to_string("orders/login.html", context, request=RequestFactory().get("/orders/login/"))

    def test_login_keeps_form_contract_and_loads_shared_styles(self):
        html = self.render_login()
        elements = Elements(html)
        form, = elements.find("form")
        self.assertEqual(form["method"], "post")
        self.assertEqual(form["action"], reverse("orders:login"))
        inputs = {i["name"]: i for i in elements.find("input")}
        self.assertEqual(set(inputs), {"csrfmiddlewaretoken", "name", "password"})
        self.assertTrue(inputs["csrfmiddlewaretoken"]["value"])
        self.assertEqual(inputs["name"]["maxlength"], "50")
        self.assertEqual(inputs["password"]["type"], "password")
        self.assertEqual(inputs["password"]["maxlength"], "1024")
        self.assertNotIn("value", inputs["password"])
        styles = {link["href"] for link in elements.find("link")}
        self.assertIn("/static/orders/ui/ui05.css", styles)
        self.assertIn("/static/orders/ui/account.css", styles)
        self.assertIn("등록된 이름과 행사 비밀번호로 맡은 업무를 시작하세요", html)
        self.assertIn("이름 등록과 권한 변경은 관리자에게 문의하세요", html)

    def test_authentication_error_is_announced_and_escaped(self):
        error = '<script>alert("error")</script>'
        html = self.render_login(error=error)
        self.assertIn(str(escape(error)), html)
        self.assertEqual(Elements(html).find("script"), [])
        self.assertIn('role="alert"', html)
