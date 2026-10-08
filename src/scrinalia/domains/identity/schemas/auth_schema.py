"""What a sign-in sends. Nothing here is echoed back: the answer is a cookie and an account."""

from pydantic import BaseModel, Field


class LoginCommand(BaseModel):
    """The credentials of one sign-in attempt."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)
