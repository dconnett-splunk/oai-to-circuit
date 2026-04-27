from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from oai_to_circuit.admin.auth import build_admin_guard
from oai_to_circuit.admin.service import (
    build_overview_context,
    build_policies_context,
    create_user,
    create_template,
    delete_template,
    get_quota_storage_status,
    get_user_detail,
    list_users_context,
    parse_quota_rows_from_form,
    update_global_quotas,
    update_user_profile,
    update_user_quotas,
    update_user_status,
    update_user_template,
    update_template,
)
from oai_to_circuit.config import BridgeConfig
from oai_to_circuit.quota import QuotaManager


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
    notice = request.query_params.get("notice", "")
    error = request.query_params.get("error", "")
    return {
        "request": request,
        "section": section,
        "admin_title": config.admin_title,
        "admin_auth_enabled": bool(config.admin_password),
        "notice": notice,
        "error": error,
        "quota_storage": get_quota_storage_status(),
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
    query = urlencode({key: value for key, value in params.items() if value})
    target = path if not query else f"{path}?{query}"
    return RedirectResponse(target, status_code=303)


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
        return templates.TemplateResponse(
            request,
            "overview.html",
            _render_context(request, config=config, section="overview", **context),
        )

    @router.get("/users", response_class=HTMLResponse)
    async def admin_users(request: Request):
        quota_manager = _require_quota_manager(request)
        context = list_users_context(quota_manager)
        return templates.TemplateResponse(
            request,
            "users.html",
            _render_context(request, config=config, section="users", **context),
        )

    @router.get("/policies", response_class=HTMLResponse)
    async def admin_policies(request: Request):
        quota_manager = _require_quota_manager(request)
        context = build_policies_context(quota_manager)
        return templates.TemplateResponse(
            request,
            "policies.html",
            _render_context(request, config=config, section="policies", **context),
        )

    @router.get("/users/{subkey:path}", response_class=HTMLResponse)
    async def admin_user_detail(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        detail = get_user_detail(quota_manager, subkey)
        if detail is None:
            raise HTTPException(status_code=404, detail="User not found")
        return templates.TemplateResponse(
            request,
            "user_detail.html",
            _render_context(
                request,
                config=config,
                section="users",
                user=detail,
                templates=build_policies_context(quota_manager)["template_options"],
            ),
        )

    @router.post("/users")
    async def admin_create_user(request: Request):
        quota_manager = _require_quota_manager(request)
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
                quota_rules=quota_rules,
            )
        except ValueError as exc:
            context = list_users_context(quota_manager)
            return templates.TemplateResponse(
                request,
                "users.html",
                _render_context(request, config=config, section="users", error=str(exc), **context),
                status_code=400,
            )

        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="User created")

    @router.post("/users/{subkey:path}/policy")
    async def admin_update_policy(request: Request, subkey: str):
        quota_manager = _require_quota_manager(request)
        values = await _form_values(request)
        try:
            update_user_template(
                quota_manager,
                subkey=subkey,
                template_name=(values.get("template_name") or [""])[0],
            )
        except ValueError as exc:
            return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", error=str(exc))
        return _redirect_to(f"/admin/users/{quote(subkey, safe='')}", notice="Policy template updated")

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
            return templates.TemplateResponse(
                request,
                "policies.html",
                _render_context(request, config=config, section="policies", error=str(exc), **context),
                status_code=400,
            )
        return _redirect_to("/admin/policies", notice="Template created")

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
