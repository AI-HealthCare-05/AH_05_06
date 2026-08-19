from datetime import date

from app.patient.models import (
    FollowUpAlert,
    FollowUpResponse,
    OtpChallenge,
    PatientLink,
    PatientSession,
    PendingDelivery,
)


class PatientFlowStore:
    """Storage boundary; production adapters can map this to DB/Redis."""

    def __init__(self) -> None:
        self.links: dict[str, PatientLink] = {}
        self.links_by_digest: dict[str, str] = {}
        self.challenges: dict[str, OtpChallenge] = {}
        self.sessions_by_digest: dict[str, PatientSession] = {}
        self.follow_ups: dict[str, FollowUpResponse] = {}
        self.follow_up_alerts: dict[tuple[str, str], FollowUpAlert] = {}
        self.pending_deliveries: dict[str, PendingDelivery] = {}
        self.reissues_by_episode_and_date: dict[tuple[str, date], int] = {}

    def save_link(self, link: PatientLink) -> None:
        self.links[link.id] = link
        self.links_by_digest[link.token_digest] = link.id

    def find_link_by_digest(self, digest: str) -> PatientLink | None:
        link_id = self.links_by_digest.get(digest)
        return self.links.get(link_id) if link_id else None

    def save_challenge(self, challenge: OtpChallenge) -> None:
        self.challenges[challenge.id] = challenge

    def save_session(self, session: PatientSession) -> None:
        self.sessions_by_digest[session.token_digest] = session

    def find_session(self, digest: str) -> PatientSession | None:
        return self.sessions_by_digest.get(digest)
