"""Google requests signed by Hermes. The plugin never sees, stores or refreshes a Google token: plugin.yaml
declares the user's own OAuth client under `oauth:` (id `google`), the user signs in once with
`hermes auth add creator-studio:google`, and Hermes attaches the token to each request it sends for us.
No gcloud file, Application Default Credentials or other tool's login is read."""
HOST = 'aiplatform.googleapis.com'
SIGN_IN = 'hermes auth add creator-studio:google'
SETUP = ('Gemini speech needs a one-time Google sign-in held by Hermes: create a Google Cloud OAuth client of type '
         '"Desktop app" in your own project, put its id and secret in the plugin settings (CREATOR_STUDIO_GOOGLE_CLIENT_ID, '
         'CREATOR_STUDIO_GOOGLE_CLIENT_SECRET), set gemini_project, then run in a terminal: ' + SIGN_IN)

_config = None  # set by the plugin's register(ctx): ctx.get_config


class NotSent(RuntimeError):
    """Raised when Hermes refused or could not sign the request, so nothing was sent to Google."""


def configure(get_config):
    global _config
    _config = get_config


def configured_project():
    """The Google Cloud project from the plugin setting gemini_project; None when not set. Never printed."""
    import re
    try: value = _config('gemini_project') if _config else ''
    except Exception: value = ''
    value = value.strip() if isinstance(value, str) else ''
    return value if re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) else None


def helper_available():
    try:
        from hermes_cli.plugin_provider_requests import credentialed_provider_request  # noqa: F401
        return True
    except Exception:
        return False


def post(url, body, project, timeout=240.0):
    """POST JSON to Vertex with the Hermes-held sign-in. Returns (status, content bytes)."""
    try:
        from hermes_cli.auth_constants import AuthError
        from hermes_cli.plugin_provider_requests import ProviderNotSignedIn, credentialed_provider_request
    except Exception:
        raise NotSent('This Hermes version has no plugin sign-in support (0.22.3 or later is needed); no request was sent') from None
    try:
        response = credentialed_provider_request('google', 'POST', url, json=body, headers={'x-goog-user-project': project}, timeout=timeout)
    except ProviderNotSignedIn:
        raise NotSent('Not signed in to Google through Hermes; no request was sent. ' + SETUP) from None
    except AuthError as exc:
        raise NotSent('Hermes could not use the Google sign-in (%s); no request was sent. %s' % (getattr(exc, 'code', 'auth_error'), SETUP)) from None
    except PermissionError as exc:
        raise NotSent('Hermes refused to sign this request (%s); no request was sent' % str(exc)[:200]) from None
    return response.status, response.body
