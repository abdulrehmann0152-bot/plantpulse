"""Remember a sign-in across page refreshes with a cookie that holds a random, server-checked token.

The cookie never holds a name, a password or anything else about the user. It is written by a tiny embedded page,
so that page must only ever contain the token the server generated, never text typed by a user.
"""
import json

import streamlit as st

COOKIE = "pp_session"
JS = """<!doctype html><html><body><script>(function(){var T=__TOKEN__,AGE=__AGE__;
var c=__NAME__+'='+encodeURIComponent(T)+'; path=/; max-age='+AGE+'; SameSite=Lax'+(location.protocol==='https:'?'; Secure':'');
try{window.parent.document.cookie=c;}catch(e){try{document.cookie=c;}catch(e2){}}})();</script></body></html>"""


def read_token():
    """The sign-in token sent by the browser, or None."""
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def _page(token, days):
    safe_token = json.dumps(token).replace("</", "<\\/")          # a '</script>' can never end the script early
    return JS.replace("__TOKEN__", safe_token).replace("__AGE__", str(int(days * 86400))).replace("__NAME__", json.dumps(COOKIE))


def write_cookie(token, days=14):
    st.iframe(_page(str(token), days), height=1)


def clear_cookie():
    st.iframe(_page("", 0), height=1)
