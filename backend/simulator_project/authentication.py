from rest_framework.authentication import SessionAuthentication as DRFSessionAuthentication


class SessionAuthentication(DRFSessionAuthentication):
    """
    Django session authentication that answers 401 (instead of 403) to
    unauthenticated requests, so the frontend can tell "please log in"
    apart from "permission denied" and redirect to the login page.
    """

    def authenticate_header(self, request):
        return 'Session'
