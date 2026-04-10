"""Omada Hotspot Voucher API Client – v2.8 FINAL.

CONFIRMED FROM BROWSER TRAFFIC:
- Controller login: POST /{omadacId}/api/v2/login with CSRF token
  → Token returned in response body as result.token
  → Sets TPOMADA_SESSIONID cookie
- This SAME session works for ALL endpoints including hotspot API:
  GET /{omadacId}/api/v2/hotspot/sites/{siteId}/voucherGroups → ✅
  GET /{omadacId}/api/v2/hotspot/sites/{siteId}/voucherGroups/{id}/vouchers → ✅
- No separate hotspot login needed!

CSRF TOKEN FLOW:
1. GET /{omadacId}/api/v2/current/login-status?needToken=true → csrfToken
2. POST /{omadacId}/api/v2/login + Csrf-Token header → session cookie + result.token
3. All requests: Csrf-Token header
"""
from __future__ import annotations

import logging
import ssl
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

INFO_PATH          = "/api/info"
LOGIN_STATUS_PATH  = "/{omadac_id}/api/v2/current/login-status"
LOGIN_PATH         = "/{omadac_id}/api/v2/login"
SITES_PATH         = "/{omadac_id}/api/v2/user/sites"

VOUCHER_GROUPS_PATH = "/{omadac_id}/api/v2/hotspot/sites/{site_id}/voucherGroups"
VOUCHER_GROUP_PATH  = "/{omadac_id}/api/v2/hotspot/sites/{site_id}/voucherGroups/{group_id}"
GROUP_VOUCHERS_PATH = "/{omadac_id}/api/v2/hotspot/sites/{site_id}/voucherGroups/{group_id}/vouchers"


class OmadaApiError(Exception):
    pass

class OmadaAuthError(OmadaApiError):
    pass

class OmadaSiteNotFoundError(OmadaApiError):
    pass


class OmadaVoucherApi:

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        site_name: str,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
        omadac_id: str | None = None,
        site_id: str | None = None,
        # Legacy params – ignored but kept for config entry compatibility
        hotspot_username: str | None = None,
        hotspot_password: str | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._site_name = site_name
        self._verify_ssl = verify_ssl
        self._ext_session = session
        self._session: aiohttp.ClientSession | None = None
        self._csrf_token: str = ""
        self._cookie_jar = aiohttp.CookieJar(unsafe=True)
        self._omadac_id: str = omadac_id or ""
        self._site_id: str = site_id or ""

    @property
    def omadac_id(self) -> str:
        return self._omadac_id

    @property
    def site_id(self) -> str:
        return self._site_id

    def _ssl(self) -> ssl.SSLContext | bool:
        if not self._verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return True

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._ext_session and not self._ext_session.closed:
            return self._ext_session
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=self._ssl())
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=self._cookie_jar,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._csrf_token:
            h["Csrf-Token"] = self._csrf_token
        return h

    async def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
        retry_auth: bool = True,
        hotspot: bool = False,  # kept for backwards compat, ignored
    ) -> Any:
        session = await self._get_session()
        url = f"{self._host}{path}"
        _LOGGER.debug("%s %s", method, url)
        try:
            async with session.request(method, url, json=data, params=params, headers=self._headers()) as resp:
                if resp.status == 401 and retry_auth:
                    await self.login()
                    return await self._request(method, path, data, params, retry_auth=False)
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise OmadaApiError(f"HTTP {resp.status}: {text[:300]}")
                payload = await resp.json(content_type=None)
                ec = payload.get("errorCode", -1)
                if ec != 0:
                    msg = payload.get("msg", "Unknown")
                    if ec in (-30109, -1001, 2, -7131):
                        raise OmadaAuthError(f"Auth error {ec}: {msg}")
                    raise OmadaApiError(f"API error {ec}: {msg}")
                return payload.get("result", payload)
        except (OmadaApiError, OmadaAuthError):
            raise
        except Exception as err:
            raise OmadaApiError(f"Request failed: {err}") from err

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def _discover_omadac_id(self) -> str:
        session = await self._get_session()
        url = f"{self._host}{INFO_PATH}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise OmadaApiError(f"GET /api/info HTTP {resp.status}")
                payload = await resp.json(content_type=None)
                omadac_id = payload.get("result", {}).get("omadacId", "")
                if not omadac_id:
                    raise OmadaApiError("No omadacId in /api/info")
                _LOGGER.debug("Discovered omadacId: %s...", omadac_id[:8])
                return omadac_id
        except OmadaApiError:
            raise
        except Exception as err:
            raise OmadaApiError(f"Cannot reach {url}: {err}") from err

    async def _discover_site_id(self, site_name: str) -> str:
        path = SITES_PATH.format(omadac_id=self._omadac_id)
        result = await self._request("GET", path, params={"currentPage": 1, "currentPageSize": 100})
        sites = result.get("data", [])
        available = [s.get("name", "") for s in sites]
        _LOGGER.debug("Available sites: %s", available)
        name_lower = site_name.lower().strip()
        for site in sites:
            if site.get("name", "").lower().strip() == name_lower:
                site_id = site.get("id", "")
                _LOGGER.debug("Found siteId '%s'", site_id)
                return site_id
        raise OmadaSiteNotFoundError(f"Site \'{site_name}\' not found. Available: {available}")

    # ------------------------------------------------------------------
    # Login: CSRF token → POST credentials → one session for everything
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Login using CSRF token flow. One session handles all API calls."""
        session = await self._get_session()

        # Step 1: Get CSRF token (with omadacId prefix!)
        csrf_url = f"{self._host}{LOGIN_STATUS_PATH.format(omadac_id=self._omadac_id)}"
        _LOGGER.debug("Fetching CSRF token from %s", csrf_url)
        csrf_token = ""
        try:
            async with session.get(csrf_url, params={"needToken": "true"}) as resp:
                if resp.status == 200:
                    d = await resp.json(content_type=None)
                    csrf_token = d.get("result", {}).get("csrfToken", "")
                    _LOGGER.debug("CSRF token: %s...", csrf_token[:8] if csrf_token else "EMPTY")
        except Exception as err:
            _LOGGER.debug("CSRF fetch failed: %s", err)

        # Step 2: Login with CSRF header
        login_url = f"{self._host}{LOGIN_PATH.format(omadac_id=self._omadac_id)}"
        _LOGGER.debug("Logging in as '%s' at %s", self._username, login_url)
        headers = {"Content-Type": "application/json"}
        if csrf_token:
            headers["Csrf-Token"] = csrf_token

        try:
            async with session.post(
                login_url,
                json={"username": self._username, "password": self._password},
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise OmadaAuthError(f"Login HTTP {resp.status}: {text[:200]}")
                payload = await resp.json(content_type=None)
                ec = payload.get("errorCode", -1)
                if ec != 0:
                    raise OmadaAuthError(f"Login failed ({ec}): {payload.get('msg', 'Unknown')}")
                # Token in response body is the session token
                self._csrf_token = payload.get("result", {}).get("token", "") or csrf_token
                _LOGGER.info("Logged in as '%s', token: %s...", self._username, self._csrf_token[:8] if self._csrf_token else "EMPTY")
        except OmadaAuthError:
            raise
        except Exception as err:
            raise OmadaAuthError(f"Login error: {err}") from err

    # Dummy hotspot login – not needed, kept for compat
    async def _hotspot_login(self) -> None:
        _LOGGER.debug("Hotspot login skipped – controller session covers all endpoints")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def async_setup(self) -> dict[str, str]:
        if not self._omadac_id:
            self._omadac_id = await self._discover_omadac_id()
        await self.login()
        if not self._site_id:
            self._site_id = await self._discover_site_id(self._site_name)
        return {"omadac_id": self._omadac_id, "site_id": self._site_id}

    async def async_validate_credentials(self) -> bool:
        try:
            await self.async_setup()
            return True
        except OmadaSiteNotFoundError:
            raise
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Voucher API – all use same session
    # ------------------------------------------------------------------

    async def async_get_voucher_groups(self, page: int = 1, page_size: int = 100) -> list[dict]:
        path = VOUCHER_GROUPS_PATH.format(omadac_id=self._omadac_id, site_id=self._site_id)
        result = await self._request("GET", path, params={"currentPage": page, "currentPageSize": page_size})
        return result.get("data", [])

    async def async_get_voucher_group(self, group_id: str) -> dict:
        path = VOUCHER_GROUP_PATH.format(omadac_id=self._omadac_id, site_id=self._site_id, group_id=group_id)
        return await self._request("GET", path)

    async def async_get_group_vouchers(self, group_id: str, page_size: int = 10) -> list[dict]:
        """Fetch unused voucher codes for a specific group.

        Strategy 1: /voucherGroups/{id}/vouchers - best but needs hotspot session
        Strategy 2: /vouchers filtered by duration (groups have different durations)
        Strategy 3: /vouchers filtered by any group-ID field found in response
        """
        group_path = GROUP_VOUCHERS_PATH.format(
            omadac_id=self._omadac_id, site_id=self._site_id, group_id=group_id
        )
        all_path = "/{omadac_id}/api/v2/hotspot/sites/{site_id}/vouchers".format(
            omadac_id=self._omadac_id, site_id=self._site_id
        )

        # Strategy 1: group-specific endpoint
        try:
            result = await self._request("GET", group_path,
                                        params={"currentPage": 1, "currentPageSize": page_size})
            data = result.get("data", [])
            _LOGGER.debug("Strategy 1 OK: %d vouchers for %s", len(data), group_id[:8])
            return data
        except OmadaApiError as err:
            _LOGGER.debug("Strategy 1 failed: %s", err)

        # Get group metadata for filtering
        group_duration = None
        try:
            group_meta = await self.async_get_voucher_group(group_id)
            group_duration = group_meta.get("duration")  # e.g. 1440 for 1 day, 5256000 for long
        except Exception:
            pass

        # Fetch all vouchers
        try:
            result = await self._request("GET", all_path,
                                        params={"currentPage": 1, "currentPageSize": 200})
            all_vouchers = result.get("data", [])

            if not all_vouchers:
                return []

            fields = list(all_vouchers[0].keys())
            _LOGGER.debug("All vouchers: %d, fields: %s", len(all_vouchers), fields)

            # Strategy 2a: filter by group ID field in voucher data
            for field in fields:
                unique = {v.get(field) for v in all_vouchers if v.get(field)}
                if group_id in unique:
                    filtered = [v for v in all_vouchers if v.get(field) == group_id]
                    _LOGGER.debug("Strategy 2a field '%s': %d vouchers", field, len(filtered))
                    return filtered[:page_size]

            # Strategy 2b: filter by duration (each group has unique duration)
            if group_duration is not None:
                dur_field = None
                for field in fields:
                    vals = {v.get(field) for v in all_vouchers if v.get(field) is not None}
                    if group_duration in vals and len(vals) > 1:
                        dur_field = field
                        break
                if dur_field:
                    filtered = [v for v in all_vouchers if v.get(dur_field) == group_duration]
                    _LOGGER.debug("Strategy 2b duration=%s field='%s': %d vouchers",
                                  group_duration, dur_field, len(filtered))
                    return filtered[:page_size]

            # Log for diagnosis
            _LOGGER.warning(
                "Cannot filter by group %s (duration=%s). "
                "Field unique counts: %s",
                group_id[:8], group_duration,
                {f: len({v.get(f) for v in all_vouchers if v.get(f) is not None}) for f in fields}
            )
            return []

        except OmadaApiError as err:
            _LOGGER.warning("All strategies failed for %s: %s", group_id[:8], err)
            return []


    async def async_create_voucher_group(
        self, name: str, count: int = 10, code_length: int = 6,
        code_format: list[str] | None = None, type_: int = 0, type_value: int = 1,
        portal_logout: bool = True, expire_start: str | None = None, expire_end: str | None = None,
    ) -> dict:
        path = VOUCHER_GROUPS_PATH.format(omadac_id=self._omadac_id, site_id=self._site_id)
        body: dict[str, Any] = {
            "name": name, "codeLength": code_length,
            "codeFormat": code_format or ["NUM"], "num": count,
            "portalLogout": portal_logout, "type": type_,
        }
        if type_ in (0, 1):
            body["typeNum"] = type_value
        if expire_start:
            body["expireTimeStart"] = expire_start
        if expire_end:
            body["expireTimeEnd"] = expire_end
        return await self._request("POST", path, data=body)

    async def async_delete_voucher_group(self, group_id: str) -> None:
        path = VOUCHER_GROUP_PATH.format(omadac_id=self._omadac_id, site_id=self._site_id, group_id=group_id)
        await self._request("DELETE", path)

    async def async_replenish_voucher_group(self, group_id: str, count: int) -> dict:
        path = VOUCHER_GROUP_PATH.format(omadac_id=self._omadac_id, site_id=self._site_id, group_id=group_id) + "/replenish"
        return await self._request("POST", path, data={"num": count})

    async def async_get_remaining_count(self, group_id: str) -> int:
        group = await self.async_get_voucher_group(group_id)
        return int(group.get("unusedCount", 0) or 0)
