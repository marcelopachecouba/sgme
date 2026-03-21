import urllib.parse

from flask import current_app, has_request_context, request, url_for


def build_public_url(endpoint, **values):
    public_base_url = (current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")

    if public_base_url:
        path = url_for(endpoint, _external=False, **values)
        return urllib.parse.urljoin(f"{public_base_url}/", path.lstrip("/"))

    if has_request_context():
        path = url_for(endpoint, _external=False, **values)
        return urllib.parse.urljoin(request.url_root, path.lstrip("/"))

    return url_for(endpoint, _external=True, **values)
