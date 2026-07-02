from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_sso import claims


def authenticate_payload(payload):
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=f"{payload.get(claims.ISSUER)}_{payload.get(claims.USER_ID)}"
    )
    if not user.is_active:
        raise AuthenticationFailed(_('User inactive or deleted.'))
    return user
