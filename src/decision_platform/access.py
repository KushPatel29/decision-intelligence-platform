"""Optional OIDC identity and deny-by-default production authorization."""
import hashlib
import os
import time

def require_access(st):
    production=os.environ.get("CORRIDOR_ENV","local")=="production"
    mode=os.environ.get("CORRIDOR_AUTH","local")
    if mode not in {"local","oidc"} or production and mode!="oidc":
        st.error("Production access requires configured identity-provider sign-in.");st.stop()
    if mode=="local":return "local-owner"
    try:
        configured="auth" in st.secrets
    except Exception:
        configured=False
    if not configured:
        st.error("Sign-in is not configured. Contact the deployment owner.");st.stop()
    if not st.user.is_logged_in:
        st.title("Corridor")
        st.caption("Sign in to your private decision workspace.")
        if st.button("Sign in",type="primary"):st.login()
        st.stop()
    subject=st.user.get("sub","")
    issuer=st.user.get("iss","")
    allowlist={value.strip() for value in os.environ.get("CORRIDOR_ALLOWED_SUBJECTS","").split(",") if value.strip()}
    expires=st.user.get("exp")
    if not subject or subject not in allowlist or expires is not None and float(expires)<time.time():
        st.error("This identity does not have access to this workspace.")
        if st.button("Sign out"):st.logout()
        st.stop()
    if st.sidebar.button("Sign out"):st.logout()
    return hashlib.sha256((issuer+"|"+subject).encode()).hexdigest()
