"""What a sign-in sends. Nothing here is echoed back: the answer is a cookie and an account."""

from pydantic import Field

from scrinalia.core.schemas import RequestModel


class LoginCommand(RequestModel):
    """The credentials of one sign-in attempt."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)
