import bcrypt
import streamlit as st
from utils.db import get_user


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def login_user(username, password):
    user = get_user(username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def is_logged_in():
    return st.session_state.get("user") is not None


def get_current_user():
    return st.session_state.get("user")


def get_current_role():
    user = get_current_user()
    return user["role"] if user else None


def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
