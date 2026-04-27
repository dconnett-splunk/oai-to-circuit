from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from oai_to_circuit.admin.auth import build_admin_guard
from oai_to_circuit.admin.service import (
    build_backends_context,
    build_overview_context,
    build_policies_context,
    create_backend,
    create_user,
    create_template,
    delete_template,
    get_backend_storage_status,
    get_quota_storage_status,
    get_user_detail,
    list_users_context,
    parse_quota_rows_from_form,
    set_default_backend,
    update_global_quotas,
    update_backend,
    update_user_policy,
    update_user_profile,
    update_user_quotas,
    update_user_status,
    update_template,
)
from oai_to_circuit.config import BridgeConfig
from oai_to_circuit.pricing import supported_model_suggestions
from oai_to_circuit.quota import QuotaManager


FLASH_NOTICE_COOKIE = "admin_notice"
FLASH_ERROR_COOKIE = "admin_error"


def _templates() -> Jinja2Templates:
    root = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(root / "templates"))
    templates.env.filters["urlencode"] = lambda value: quote(str(value), safe="")
    return templates


def _static_path() -> Path:
    return Path(__file__).resolve().parent / "static"


def _render_context(
    request: Request,
    *,
    config: BridgeConfig,
    section: str,
    **context: Any,
) -> Dict[str, Any]:
    notice = request.cookies.get(FLASH_NOTICE_COOKIE) or request.query_params.get("notice", "")
    error = request.cookies.get(FLASH_ERROR_COOKIE) or request.query_params.get("error", "")
    current_config = getattr(request.app.state, "config", config)
    return {
        "request": request,
        "section": section,
        "admin_title": current_config.admin_title,
        "admin_auth_enabled": bool(current_config.admin_password),
        "notice": notice,
        "error": error,
        "quota_storage": get_quota_storage_status(),
        "backend_storage": get_backend_storage_status(),
        "model_suggestions": supported_model_suggestions(),
        "backend_options": list(current_config.configured_backends().keys()),
        "default_backend_id": current_config.default_backend_id,
        "legacy_default_backend_active": current_config.legacy_default_backend_active,
        **context,
    }


async def _form_values(request: Request) -> Dict[str, List[str]]:
    payload = (await request.body()).decode("utf-8")
    return {key: [value.strip() for value in values] for key, values in parse_qs(payload, keep_blank_values=True).items()}


def _require_quota_manager(request: Request) -> QuotaManager:
    quota_manager = getattr(request.app.state, "quota_manager", None)
    if quota_manager is None:
        raise HTTPException(status_code=503, detail="Quota manager is not ready")
    return quota_manager


def _redirect_to(path: str, **params: str) -> RedirectResponse:
    response = RedirectResponse(path, status_code=303)
    notice = params.get("notice", "")
    error = params.get("error", "")
    if notice:
        response.set_cookie(FLASH_NOTICE_COOKIE, notice, max_age=60, httponly=True, samesite="lax", path="/admin")
    else:
        response.delete_cookie(FLASH_NOTICE_COOKIE, path="/admin")
    if error:
        response.set_cookie(FLASH_ERROR_COOKIE, error, max_age=60, httponly=True, samesite="lax", path="/admin")
    else:
        response.delete_cookie(FLASH_ERROR_COOKIE, path="/admin")
    return response


def _current_config(request: Request, fallback: BridgeConfig) -> BridgeConfig:
    return getattr(request.app.state, "config", fallback)


def _template_response(
    templates: Jinja2Templates,
    request: Request,
    template_name: str,
    context: Dict[str, Any],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    response = templates.TemplateResponse(request, template_name, context, status_code=status_code)
    if request.cookies.get(FLASH_NOTICE_COOKIE):
        response.delete_cookie(FLASH_NOTICE_COOKIE, path="/admin")
    if request.cookies.get(FLASH_ERROR_COOKIE):
        response.delete_cookie(FLASH_ERROR_COOKIE, path="/admin")
    return response


def register_admin_routes(app: FastAPI, *, config: BridgeConfig) -> None:
    templates = _templates()
    require_admin = build_admin_guard(config)
    router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

    if not any(getattr(route, "path", None) == "/admin/static" for route in app.routes):
        app.mount("/admin/static", StaticFiles(directory=str(_static_path())), name="admin-static")

    @router.get("", response_class=HTMLResponse)
    async def admin_overview(request: Request):
        quota_manager = _require_quota_manager(request)
        context = build_overview_context(quota_manager)
        return _template_response(
            templates,
            request,
            "overview.html",
            _render_context(request, config=config, section="overview", **context),
        )

    @router.get("/users", response_class=HTMLResponse)
    async def admin_users(request: Request):
        quota_manager = _require_quota_manager(request)
        context = list_users_context(quota_manager)
        return _template_response(
            templates,
            request,
            "users.html",
            _render_context(request, config=config, section="users", **context),
        )

    @router.get("/policies", response_class=HTMLResponse)
    async def admin_policies(request: Request):
        quota_manager = _require_quota_manager(request)
        context = build_policies_context(quota_manager)
        return _template_response(
            templates,
            request,
            "policies.html",
            _render_context(request, config=config, section="policies", **context),
        )

    @router.get("/backends", response_class=HTMLResponse)
    async def admin_backends(request: Request):
        quota_manager = _require_quota_manager(request)
        current_config = _current_config(request, config)
        context = build_backends_context(current_config, quota_manager)
        return _template_response(
            templates,
            request,
            "backends.html",
            _render_context(request, config=current_config, section="backends", **context),
        )

    @router.get("/users/{subkey:path}", response_class=HTMLResponse)
    async def admin_user_detail(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        current_config = _current_config(request, config)
        detail = get_user_detail(quota_manager, subkey)
        if detail is None:
            raise HTTPException(status_code=404, detail="User not found")
        return _template_response(
            templates,
            request,
            "user_detail.html",
            _render_context(
                request,
                config=current_config,
                section="users",
                user=detail,
                templates=build_policies_context(quota_manager)["template_options"],
            ),
        )

    @router.post("/users")
    async def admin_create_user(request: Request):
        quota_manager = _require_quota_manager(request)
        current_config = _current_config(request, config)
        values = await _form_values(request)
        try:
            quota_rules = parse_quota_rows_from_form(values)
            subkey = create_user(
                quota_manager,
                friendly_name=(values.get("friendly_name") or [""])[0],
                email=(values.get("email") or [""])[0],
                description=(values.get("description") or [""])[0],
                custom_subkey=(values.get("custom_subkey") or [""])[0],
                prefix=(values.get("prefix") or [""])[0],
                template_name=(values.get("template_name") or [""])[0],
                backend_id=(values.get("backend_id") or [""])[0],
                available_backend_ids=list(current_config.configured_backends().keys()),
                quota_rules=quota_rules,
            )
        except ValueError as exc:
            context = list_users_context(quota_manager)
            return _template_response(
                templates,
                request,
                "users.html",
                _render_context(request, config=current_config, section="users", error=str(exc), **context),
                status_code=400,
            )

        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="User created")

    @router.post("/users/{subkey:path}/policy")
    async def admin_update_policy(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        current_config = _current_config(request, config)
        values = await _form_values(request)
        try:
            update_user_policy(
                quota_manager,
                subkey=subkey,
                template_name=(values.get("template_name") or [""])[0],
                backend_id=(values.get("backend_id") or [""])[0],
                available_backend_ids=list(current_config.configured_backends().keys()),
            )
        except ValueError as exc:
            return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", error=str(exc))
        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="Routing and policy updated")

    @router.post("/users/{subkey:path}/profile")
    async def admin_update_profile(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            update_user_profile(
                quota_manager,
                subkey=subkey,
                friendly_name=(values.get("friendly_name") or [""])[0],
                email=(values.get("email") or [""])[0],
                description=(values.get("description") or [""])[0],
            )
        except ValueError as exc:
            return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", error=str(exc))
        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="Profile updated")

    @router.post("/users/{subkey:path}/status")
    async def admin_update_status(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        update_user_status(
            quota_manager,
            subkey=subkey,
            status=(values.get("status") or ["active"])[0],
            revoke_reason=(values.get("revoke_reason") or [""])[0],
        )
        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="Access updated")

    @router.post("/users/{subkey:path}/quotas")
    async def admin_update_quotas(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            update_user_quotas(
                quota_manager,
                subkey=subkey,
                quota_rules=parse_quota_rows_from_form(values),
            )
        except ValueError as exc:
            return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", error=str(exc))
        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="Quotas updated")

    @router.post("/policies/global")
    async def admin_update_global_policies(request: Request):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            update_global_quotas(
                quota_manager,
                quota_rules=parse_quota_rows_from_form(values, field_prefix="global_quota"),
            )
        except ValueError as exc:
            return _redirect_to("/admin/policies", error=str(exc))
        return _redirect_to("/admin/policies", notice="Global rules updated")

    @router.post("/policies/templates")
    async def admin_create_template(request: Request):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            create_template(
                quota_manager,
                name=(values.get("template_name") or [""])[0],
                description=(values.get("template_description") or [""])[0],
                quota_rules=parse_quota_rows_from_form(values, field_prefix="template_quota"),
            )
        except ValueError as exc:
            context = build_policies_context(quota_manager)
            return _template_response(
                templates,
                request,
                "policies.html",
                _render_context(request, config=_current_config(request, config), section="policies", error=str(exc), **context),
                status_code=400,
            )
        return _redirect_to("/admin/policies", notice="Template created")

    @router.post("/backends/default")
    async def admin_set_default_backend(request: Request):
        current_config = _current_config(request, config)
        values = await _form_values(request)
        try:
            request.app.state.config = set_default_backend(
                current_config,
                backend_id=(values.get("backend_id") or [""])[0],
            )
        except ValueError as exc:
            return _redirect_to("/admin/backends", error=str(exc))
        return _redirect_to("/admin/backends", notice="Default backend updated")

    @router.post("/backends")
    async def admin_create_backend(request: Request):
        current_config = _current_config(request, config)
        values = await _form_values(request)
        try:
            request.app.state.config = create_backend(
                current_config,
                backend_id=(values.get("backend_id") or [""])[0],
                client_id=(values.get("client_id") or [""])[0],
                client_secret=(values.get("client_secret") or [""])[0],
                appkey=(values.get("appkey") or [""])[0],
                token_url=(values.get("token_url") or [""])[0],
                circuit_base=(values.get("circuit_base") or [""])[0],
                api_version=(values.get("api_version") or [""])[0],
                make_default=bool((values.get("make_default") or [""])[0]),
            )
        except ValueError as exc:
            return _redirect_to("/admin/backends", error=str(exc))
        return _redirect_to("/admin/backends", notice="Backend added")

    @router.post("/backends/{backend_id:path}")
    async def admin_update_backend(request: Request, backend_id: str):
        current_config = _current_config(request, config)
        values = await _form_values(request)
        try:
            request.app.state.config = update_backend(
                current_config,
                backend_id=backend_id,
                client_id=(values.get("client_id") or [""])[0],
                client_secret=(values.get("client_secret") or [""])[0],
                appkey=(values.get("appkey") or [""])[0],
                token_url=(values.get("token_url") or [""])[0],
                circuit_base=(values.get("circuit_base") or [""])[0],
                api_version=(values.get("api_version") or [""])[0],
            )
        except ValueError as exc:
            return _redirect_to("/admin/backends", error=str(exc))
        return _redirect_to("/admin/backends", notice="Backend updated")

    @router.post("/policies/templates/{template_name:path}")
    async def admin_update_template(request: Request, template_name: str):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            update_template(
                quota_manager,
                template_name=template_name,
                description=(values.get("template_description") or [""])[0],
                quota_rules=parse_quota_rows_from_form(values, field_prefix="template_quota"),
            )
        except ValueError as exc:
            return _redirect_to("/admin/policies", error=str(exc))
        return _redirect_to("/admin/policies", notice="Template updated")

    @router.post("/policies/templates/{template_name:path}/delete")
    async def admin_delete_template(request: Request, template_name: str):
        quota_manager = _require_quota_manager(request)
        try:
            delete_template(quota_manager, template_name=template_name)
        except ValueError as exc:
            return _redirect_to("/admin/policies", error=str(exc))
        return _redirect_to("/admin/policies", notice="Template deleted")

    app.include_router(router)
