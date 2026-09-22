"""Which address the login throttle counts against, behind a proxy (issue #61).

gunicorn does not rewrite REMOTE_ADDR from X-Forwarded-For -- it sets it from
the socket peer, and `--forwarded-allow-ips` only gates the forwarded scheme and
script-name headers. So behind a reverse proxy every request arrives with the
proxy's address, and a per-IP failure budget becomes one shared budget: ten
wrong passwords from anyone lock out every device on that shared account.

`client_ip` is the trust boundary. It reads X-Forwarded-For only when the
immediate peer is a configured proxy, so a client cannot choose its own bucket.
"""

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from orders.client_ip import client_ip
from orders.models import AuthDevice, LoginAttempt
from orders.tests.auth_support import EVENT_PASSWORD, ensure_account


def request_meta(remote_addr, forwarded=None):
    meta = {"REMOTE_ADDR": remote_addr}
    if forwarded is not None:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded
    return type("Request", (), {"META": meta})()


@override_settings(TRUSTED_PROXY_IPS=[])
class UntrustedPeerTests(SimpleTestCase):
    """With no proxy configured, the header is just a header."""

    def test_the_forwarded_header_is_ignored(self):
        """A direct deployment must not let a client pick its own bucket by
        sending one line of header; that would make the throttle decorative."""
        self.assertEqual(
            client_ip(request_meta("198.51.100.4", "203.0.113.9")), "198.51.100.4"
        )

    def test_the_peer_address_is_used(self):
        self.assertEqual(client_ip(request_meta("198.51.100.4")), "198.51.100.4")


@override_settings(TRUSTED_PROXY_IPS=["10.89.0.10"])
class TrustedProxyTests(SimpleTestCase):
    def test_the_client_address_comes_from_the_trusted_proxy(self):
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "203.0.113.9")), "203.0.113.9"
        )

    def test_a_chain_is_read_from_the_right_and_trusted_hops_are_skipped(self):
        """Each proxy appends the peer it saw, so the rightmost entry a trusted
        proxy did not add is the closest address that was not chosen by the
        client. Entries further left are client-supplied and unverifiable."""
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "203.0.113.9, 10.89.0.10")),
            "203.0.113.9",
        )

    def test_a_forged_chain_cannot_reach_past_the_proxy(self):
        """The client sends "1.2.3.4" and the proxy appends the real peer, so
        the rightmost untrusted entry is the real one."""
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "1.2.3.4, 203.0.113.9")),
            "203.0.113.9",
        )

    def test_a_malformed_forwarded_value_falls_back_to_the_peer(self):
        """Garbage must not become a bucket key of its own, and must not raise:
        a failed login is exactly when an attacker controls this header."""
        for value in ("", "   ", "not-an-ip", ",", "10.89.0.10", "::gg"):
            with self.subTest(forwarded=value):
                self.assertEqual(
                    client_ip(request_meta("10.89.0.10", value)), "10.89.0.10"
                )

    def test_a_port_suffix_is_removed(self):
        """Some proxies append the source port. Keeping it would split one
        client across buckets, because the port changes per connection."""
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "203.0.113.9:51234")), "203.0.113.9"
        )

    def test_a_bracketed_ipv6_client_with_a_port_is_unwrapped(self):
        """The bracketed form is what a proxy sends when it appends the port to
        an IPv6 address. Without this branch the whole entry fails to parse and
        the client silently shares the proxy's bucket."""
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "[2001:db8::1]:51234")), "2001:db8::1"
        )

    def test_an_ipv6_client_is_preserved(self):
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "2001:db8::1")), "2001:db8::1"
        )


@override_settings(TRUSTED_PROXY_IPS=["not-an-ip", "10.89.0.10"])
class MalformedConfigurationTests(SimpleTestCase):
    """Settings refuse a malformed entry at startup (see test_runtime_config),
    so this should be unreachable. It still must not raise: this code runs on
    the login path, and a 500 on every login is worse than the mis-bucketing
    issue #61 is about."""

    def test_an_unusable_entry_is_ignored_rather_than_raising(self):
        self.assertEqual(
            client_ip(request_meta("10.89.0.10", "203.0.113.9")), "203.0.113.9"
        )

    def test_a_peer_matching_no_usable_entry_is_the_client(self):
        self.assertEqual(
            client_ip(request_meta("192.0.2.50", "203.0.113.9")), "192.0.2.50"
        )


@override_settings(TRUSTED_PROXY_IPS=["10.89.0.10"])
class MappedAddressTests(SimpleTestCase):
    def test_an_ipv4_mapped_peer_is_not_matched_against_an_ipv4_proxy(self):
        """Python compares address versions, so ::ffff:10.89.0.10 does not fall
        inside 10.89.0.10/32. That fails closed -- the header is ignored -- and
        this test records it so a later change cannot flip it silently."""
        self.assertEqual(
            client_ip(request_meta("::ffff:10.89.0.10", "203.0.113.9")),
            "::ffff:10.89.0.10",
        )


@override_settings(TRUSTED_PROXY_IPS=["10.89.0.0/24"])
class TrustedProxyRangeTests(SimpleTestCase):
    def test_a_range_matches_any_address_inside_it(self):
        self.assertEqual(
            client_ip(request_meta("10.89.0.7", "203.0.113.9")), "203.0.113.9"
        )

    def test_an_address_outside_the_range_is_not_a_proxy(self):
        self.assertEqual(
            client_ip(request_meta("10.90.0.7", "203.0.113.9")), "10.90.0.7"
        )


@override_settings(TRUSTED_PROXY_IPS=["10.89.0.10"])
class ThrottleBucketTests(TestCase):
    """The behaviour issue #61 is about, end to end."""

    def setUp(self):
        ensure_account("ORDER")

    def login(self, client, password="wrong", forwarded=None):
        headers = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        return client.post(
            reverse("orders:login"),
            {"name": "order", "password": password},
            REMOTE_ADDR="10.89.0.10",
            **headers,
        )

    def test_two_clients_behind_the_proxy_do_not_share_a_failure_budget(self):
        for _ in range(10):
            blocked = self.login(Client(), forwarded="203.0.113.9")
        self.assertEqual(blocked.status_code, 429)

        other = self.login(Client(), forwarded="203.0.113.10")
        self.assertEqual(other.status_code, 200, "a second client was locked out")

        allowed = self.login(
            Client(), password=EVENT_PASSWORD, forwarded="203.0.113.10"
        )
        self.assertEqual(allowed.status_code, 302)
        self.assertEqual(AuthDevice.objects.count(), 1)

    def test_the_blocked_client_stays_blocked_on_its_own_address(self):
        for _ in range(10):
            self.login(Client(), forwarded="203.0.113.9")
        correct = self.login(
            Client(), password=EVENT_PASSWORD, forwarded="203.0.113.9"
        )
        self.assertEqual(correct.status_code, 429)
        self.assertEqual(AuthDevice.objects.count(), 0)
        self.assertEqual(LoginAttempt.objects.count(), 1)
