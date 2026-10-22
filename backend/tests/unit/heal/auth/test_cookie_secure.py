"""The session cookie's Secure flag follows the scheme of WEB_DOMAIN."""
import pytest

from heal_app.configs.app_configs import cookie_secure


class TestCookieSecure:
    @pytest.mark.parametrize(
        "web_domain", ["https://heal.example.org", "HTTPS://heal.example.org"]
    )
    def test_https_deployments_mark_the_cookie_secure(self, web_domain: str) -> None:
        assert cookie_secure(web_domain)

    @pytest.mark.parametrize(
        "web_domain", ["http://heal-node.internal", "http://localhost:3000"]
    )
    def test_plain_http_keeps_the_cookie_usable(self, web_domain: str) -> None:
        assert not cookie_secure(web_domain)

    def test_the_login_cookie_uses_it(self) -> None:
        from heal_app.auth.users import cookie_transport
        from heal_app.configs.app_configs import COOKIE_SECURE

        assert cookie_transport.cookie_secure is COOKIE_SECURE
