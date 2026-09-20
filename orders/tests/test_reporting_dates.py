"""8C: which days the sales report covers (D-053, closing D-013).

The report used to be pinned to 2025-10-18 whatever was asked (BK-R006).
Now: with no period given it shows the most recent registered event day
that is not in the future, and today when none is registered; an explicit
`start_date`/`end_date` (Asia/Seoul, by order date) is honoured; nonsense
is refused with 400 rather than silently replaced.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import EventDay, MenuItem, NumberSeries, Order, OrderItem, Table
from orders.services import reporting
from orders.tests.auth_support import AUTH_SETTINGS, login_client

SEOUL = ZoneInfo("Asia/Seoul")


class PeriodResolutionTests(TestCase):
    today = date(2026, 9, 20)

    def resolve(self, **params):
        return reporting.resolve_period(params, as_of=self.today)

    def test_no_period_means_the_latest_event_day_not_in_the_future(self):
        EventDay.objects.create(date=date(2025, 10, 18))
        EventDay.objects.create(date=date(2026, 9, 19), label="가을 바자회")
        EventDay.objects.create(date=date(2026, 10, 3))  # registered ahead of time
        period = self.resolve()
        self.assertEqual((period.start, period.end, period.basis), (date(2026, 9, 19), date(2026, 9, 19), "event_day"))
        self.assertEqual(period.label, "가을 바자회")

    def test_no_event_day_means_today(self):
        period = self.resolve()
        self.assertEqual((period.start, period.end, period.basis), (self.today, self.today, "today"))

    def test_an_event_day_today_is_the_event_day(self):
        EventDay.objects.create(date=self.today)
        self.assertEqual(self.resolve().basis, "event_day")

    def test_explicit_single_day_and_range(self):
        one = self.resolve(start_date="2026-09-01")
        self.assertEqual((one.start, one.end, one.basis), (date(2026, 9, 1), date(2026, 9, 1), "explicit"))
        only_end = self.resolve(end_date="2026-09-02")
        self.assertEqual((only_end.start, only_end.end), (date(2026, 9, 2), date(2026, 9, 2)))
        span = self.resolve(start_date="2026-09-01", end_date="2026-09-03")
        self.assertEqual((span.start, span.end), (date(2026, 9, 1), date(2026, 9, 3)))

    def test_nonsense_is_refused_not_replaced(self):
        for params in (
            {"start_date": "2026-13-01"}, {"start_date": "yesterday"}, {"end_date": "2026-09-31"},
            {"start_date": "2026-09-03", "end_date": "2026-09-01"}, {"start_date": "20260901"},
            {"start_date": "2026-09-01T00:00"}, {"start_date": ""}, {"start_date": "2026-9-1"},
            {"start_date": "0000-01-01"}, {"start_date": "2026-02-30"}, {"start_date": 20260901},
            {"start_date": "9" * 40}, {"start_date": "２０２６-０９-０１"},
        ):
            with self.subTest(params=params):
                with self.assertRaises(reporting.PeriodError):
                    self.resolve(**params)

    def test_a_blank_parameter_is_the_same_as_none(self):
        self.assertEqual(reporting.resolve_period({"start_date": None, "end_date": None}, as_of=self.today).basis, "today")


class SeoulDayTests(SimpleTestCase):
    def test_today_is_read_in_seoul(self):
        # 2026-09-20 23:30 Seoul is 14:30 UTC the same day; 00:30 Seoul the
        # next day is 15:30 UTC still the 20th. The report's "today" is Seoul's.
        with timezone.override(SEOUL):
            self.assertEqual(reporting.today(now=datetime(2026, 9, 20, 15, 30, tzinfo=ZoneInfo("UTC"))), date(2026, 9, 21))
            self.assertEqual(reporting.today(now=datetime(2026, 9, 20, 14, 30, tzinfo=ZoneInfo("UTC"))), date(2026, 9, 20))


@override_settings(**AUTH_SETTINGS)
class DashboardPeriodHttpTests(TestCase):
    def setUp(self):
        login_client(self.client, "STATS")
        self.table = Table.objects.create(number=7)
        self.menu = MenuItem.objects.create(name="Meal", price=1000)

    def order_on(self, day, *, at=time(12, 0), series=NumberSeries.REAL, qty=1):
        order = Order.objects.create(
            table=self.table, floor="B1", order_type="DINE_IN", order_date=day,
            number_series=series, total_price=1000 * qty, payment_method="CASH",
            received_amount=1000 * qty, received_cash_amount=1000 * qty, received_ticket_amount=0,
            change_amount=0,
        )
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(day, at, SEOUL))
        OrderItem.objects.create(order=order, menu_item=self.menu, qty=qty, unit_price=1000)
        return order

    def dashboard(self, **params):
        response = self.client.get(reverse("orders:stats-dashboard"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_default_period_is_the_latest_event_day(self):
        today = timezone.localdate()
        EventDay.objects.create(date=today - timedelta(days=30), label="봄")
        EventDay.objects.create(date=today - timedelta(days=1), label="가을")
        EventDay.objects.create(date=today + timedelta(days=10))
        self.order_on(today - timedelta(days=30))
        self.order_on(today - timedelta(days=1), qty=2)
        self.order_on(today, qty=5)
        data = self.dashboard()
        self.assertEqual(data["period"], {
            "start_date": (today - timedelta(days=1)).isoformat(),
            "end_date": (today - timedelta(days=1)).isoformat(),
            "floor": None, "basis": "event_day", "label": "가을",
        })
        self.assertEqual(data["summary"]["orders"], 1)
        self.assertEqual(data["summary"]["revenue"], 2000)

    def test_default_period_without_event_days_is_today(self):
        today = timezone.localdate()
        self.order_on(today)
        self.order_on(today - timedelta(days=1))
        data = self.dashboard()
        self.assertEqual((data["period"]["basis"], data["period"]["start_date"]), ("today", today.isoformat()))
        self.assertEqual(data["summary"]["orders"], 1)

    def test_explicit_range_is_inclusive_on_both_ends(self):
        for offset in (0, 1, 2, 3):
            self.order_on(date(2026, 9, 1) + timedelta(days=offset))
        data = self.dashboard(start_date="2026-09-02", end_date="2026-09-03")
        self.assertEqual(data["summary"]["orders"], 2)
        self.assertEqual(data["period"]["basis"], "explicit")
        one = self.dashboard(start_date="2026-09-01")
        self.assertEqual(one["summary"]["orders"], 1)

    def test_bad_dates_answer_400(self):
        for params in ({"start_date": "nope"}, {"start_date": "2026-09-03", "end_date": "2026-09-01"}):
            with self.subTest(params=params):
                response = self.client.get(reverse("orders:stats-dashboard"), params)
                self.assertEqual(response.status_code, 400)

    def test_the_day_is_the_order_date_not_the_utc_clock(self):
        """An order numbered on 2026-09-02 at 00:10 Seoul is 15:10 UTC on the
        1st. It belongs to the 2nd, and its hour reads 00:00 Seoul."""
        self.order_on(date(2026, 9, 2), at=time(0, 10))
        self.order_on(date(2026, 9, 1), at=time(23, 50))
        second = self.dashboard(start_date="2026-09-02")
        self.assertEqual(second["summary"]["orders"], 1)
        self.assertEqual(second["hourly"], [{"hour": "00:00", "orders": 1, "revenue": 1000}])
        first = self.dashboard(start_date="2026-09-01")
        self.assertEqual(first["hourly"], [{"hour": "23:00", "orders": 1, "revenue": 1000}])

    def test_practice_orders_never_enter_the_report(self):
        today = timezone.localdate()
        EventDay.objects.create(date=today)
        self.order_on(today, series=NumberSeries.PRACTICE, qty=9)
        self.order_on(today)
        data = self.dashboard()
        self.assertEqual(data["summary"], {"orders": 1, "items": 1, "revenue": 1000,
                                           "cancelled_orders": 0, "legacy_unsplit_orders": 0})
