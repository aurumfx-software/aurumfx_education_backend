from pydantic import BaseModel, ConfigDict, StrictBool


class SidebarNavigationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nav_links: dict[str, StrictBool]
