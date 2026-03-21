import os
from dataclasses import dataclass, field


@dataclass
class LinearConfig:
    api_key: str
    webhook_secret: str
    team_id: str
    project_id: str = ""

    @classmethod
    def from_env(cls) -> "LinearConfig":
        return cls(
            api_key=os.environ.get("LINEAR_API_KEY", ""),
            webhook_secret=os.environ.get("LINEAR_WEBHOOK_SECRET", ""),
            team_id=os.environ.get("LINEAR_TEAM_ID", ""),
            project_id=os.environ.get("LINEAR_PROJECT_ID", ""),
        )
