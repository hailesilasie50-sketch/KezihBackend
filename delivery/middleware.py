from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

class JWTAuthMiddleware(BaseMiddleware):

    async def __call__(self, scope, receive, send):
        # Import models lazily, after Django is ready
        from django.contrib.auth import get_user_model
        from delivery.models import Profile

        User = get_user_model()

        print("JWT MIDDLEWARE RUNNING")

        query_string = scope.get("query_string", b"").decode()
        print("QUERY STRING:", query_string)

        token = None
        if "token=" in query_string:
            token = query_string.split("token=")[-1]

        if token:
            try:
                access_token = await database_sync_to_async(AccessToken)(token)
                user_id = access_token.get("user_id")

                user = await database_sync_to_async(User.objects.get)(id=user_id)
                profile = await database_sync_to_async(Profile.objects.get)(user=user)

                scope["user"] = profile

            except Exception as e:
                print("JWT ERROR:", e)
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
