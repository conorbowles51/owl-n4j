"""Plain action/domain matrix, backed by registered tools and existing review policy."""
from __future__ import annotations

ACTIONS = [
    ('reports', 'Create and revise reports and artifacts', 'saved_draft', 'Saved in this conversation; editable revisions preserve earlier work.',
     ['create_artifact', 'revise_artifact', 'edit_report_sections', 'append_artifact_rows']),
    ('finding', 'Create a cited finding or note', 'reviewed_proposal', 'Prepared in Workspace proposals. A finding can include a dossier attachment and dated timeline event in the same review.',
     ['propose_workspace_entry']),
    ('dossier', 'Create, update or attach material to a dossier', 'reviewed_proposal', 'Prepared in Workspace proposals. Existing links remain and intervening investigator edits are protected.',
     ['propose_dossier_change']),
    ('timeline', 'Add dated events to the timeline', 'reviewed_proposal', 'Propose source-backed dated events; saved events retain their source links.', ['propose_timeline_addition']),
    ('links', 'Link evidence to casework', 'reviewed_proposal', 'Propose supporting, contradicting or contextual links.', ['propose_link']),
    ('judgements', 'Suggest payment classifications and missing periods', 'reviewed_proposal', 'Prepared in Judgement calls for an investigator decision.', ['propose_judgement_call']),
    ('investigation', 'Prepare investigative leads and challenges', 'reviewed_proposal', 'Draft lead cards, claims, entities, code-word meanings and counter-arguments with sources.',
     ['propose_lead_card', 'propose_claim', 'propose_entity', 'propose_glossary_term', 'propose_counter_arguments']),
]


def action_capabilities(bound_tools=None):
    bound = set(bound_tools) if bound_tools is not None else None
    return {'actions': [dict(id=key, label=label, mode=mode, description=description)
                        for key, label, mode, description, tools in ACTIONS
                        if bound is None or bound.intersection(tools)],
            'scope': 'Only the current conversation and cases the investigator can access. Case changes require case edit access.',
            'review': 'Artifacts are saved directly as drafts. Case changes follow the existing Workspace or Judgement calls review.',
            'unavailable_actions': ['Delete original evidence', 'Change case permissions', 'Change provider or server settings']}
