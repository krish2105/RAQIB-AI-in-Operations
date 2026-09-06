"""Watch: VLM second opinions (advisory, non-downgrading)."""

from .opinion import OpinionResult, opine_event, qualifies_for_auto, record_opinion, second_opinion

__all__ = ["OpinionResult", "opine_event", "qualifies_for_auto", "record_opinion", "second_opinion"]
