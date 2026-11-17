"""Read-only web tools: standards, KB outline, terms, links and help."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.web.auth import require_user_page
from app.web.commands import visible_commands
from app.web.templating import render
from app.web.tool_data import ToolService

router = APIRouter()


def _tools(request: Request) -> ToolService:
    service = getattr(request.app.state, "service", None)
    tools = getattr(request.app.state, "tool_service", None)
    if tools is None or getattr(tools, "service", None) is not service:
        tools = ToolService(
            request.app.state.settings,
            service=service,
            s3=getattr(request.app.state, "s3", None),
        )
        request.app.state.tool_service = tools
    return tools


@router.get("/tools/gosts")
async def gosts(request: Request, q: str = ""):
    user = await require_user_page(request)
    tools = _tools(request)
    return render(
        request,
        "tools/gosts.html",
        user=user,
        standards=tools.standards(q),
        query=q,
        total=len(tools.standards()),
    )


@router.get("/tools/gosts/{gost:path}")
async def standard(request: Request, gost: str, tab: str = "outline"):
    user = await require_user_page(request)
    tools = _tools(request)
    item = tools.find_standard(gost)
    if item is None:
        return render(request, "errors/404.html", status_code=404, user=user)
    if tab not in {"outline", "terms", "links"}:
        tab = "outline"
    return render(
        request,
        "tools/standard.html",
        user=user,
        standard=item,
        tab=tab,
        outline=tools.outline(item["gost_number"]),
        terms=tools.terms(gost=item["gost_number"]),
        links=tools.links(item["gost_number"]),
        gost_path=quote(item["gost_number"], safe=""),
    )


@router.get("/tools/terms")
async def terms(request: Request, q: str = "", gost: str = ""):
    user = await require_user_page(request)
    tools = _tools(request)
    return render(
        request,
        "tools/terms.html",
        user=user,
        terms=tools.terms(gost=gost or None, query=q),
        query=q,
        gost=gost,
        standards=tools.standards(),
    )


@router.get("/help")
async def help_page(request: Request, unknown: str = "", forbidden: int = 0):
    user = await require_user_page(request)
    return render(
        request,
        "help.html",
        user=user,
        commands=visible_commands(user),
        unknown=unknown,
        forbidden=bool(forbidden),
    )


@router.get("/tools")
async def tools_index():
    return RedirectResponse("/tools/gosts", status_code=303)
