def caller_from_event(event):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    if not isinstance(claims, dict):
        claims = {}

    sub = str(claims.get("sub") or "unknown")
    username = claims.get("email") or claims.get("cognito:username") or claims.get("username") or sub
    return {"sub": sub, "username": str(username)}
